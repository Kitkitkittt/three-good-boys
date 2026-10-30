import contextlib
import hashlib
import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from . import main
from .manifest import ManifestError, verify_files

SHA_X = hashlib.sha256(b"x").hexdigest()
SHA_SRC = hashlib.sha256(b"src").hexdigest()


def entry(sample_id, state="0" * 64, stop="model_finished"):
    return {"id": sample_id, "tool_calls": [], "state_hash": state, "stop_reason": stop}


class World:
    """Synthetic run root, injected seams and a recording artifact store."""

    def __init__(self, mode="ok"):
        self._tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.root = Path(self._tmp.name) / "run"
        self.root.mkdir()
        self.mode = mode
        self.faults = {"b"} if mode == "boom" else set()
        self.seeds = seeds = dict.fromkeys(("config", "model", "audio"), SHA_X)
        self.jar = {SHA_X: self.write("data/audio/a.wav", "x")}
        self.objects = {}
        self.object_generations = {}
        files = {"data/audio/a.wav": SHA_X}
        if mode == "hash":   # smoke artifact already committed, but decodes as a list
            smoke = hashlib.sha256(b"[]").hexdigest()
            self.write("results/a.json", "[]")
            files["results/a.json"] = smoke
            self.jar[smoke] = self.root / "results/a.json"
            self.objects["results/a.json"] = b"[]"
        inputs = {"ids": ["a", "b", "c"], "files": files, "seeds": seeds}
        self.pinned = {"dataset": "gs://dataset/fixture", "model": "gs://models/qwen@1",
                       "source": SHA_SRC, "checksums": dict(seeds)}
        self.materialized = {"model": "gs://models/qwen@1", "source": SHA_SRC}
        self.object_gen = 42
        self.committed = []
        self.calls = []
        self.manifest = main.read_manifest(self.write("manifest.json", json.dumps(inputs)))

    @property
    def service(self):
        return self.pinned

    @service.setter
    def service(self, value):
        self.pinned = value

    def write(self, name, text):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
        return path

    def identities(self, pinned):
        """What was actually materialized locally, independent of the pin."""
        return dict(self.materialized)

    def fetch(self, uri, checksum):
        self.calls.append(("fetch", uri, checksum))
        return self.jar.get(checksum), self.object_gen

    def execute(self, sample):
        self.calls.append(("execute", sample.id))
        if sample.id in self.faults:
            self.faults.discard(sample.id)
            raise RuntimeError("simulator died")
        return entry(sample.id)

    def commit(self, key, content, generation):
        self.calls.append(("commit", key))
        if key not in self.objects:
            # the store owns generation numbering; the caller's hint is ignored
            self.objects[key] = content
            self.object_generations[key] = self.object_gen
            self.committed.append((key, content, self.object_gen))
            return "created"
        return "identical" if self.objects[key] == content else "conflict"

    def adapter(self, **seams):
        override = {name: seams.pop(name) for name in ("execute", "commit") if name in seams}
        return main.Adapter(self.manifest, pinned=seams.pop("pinned", self.pinned),
                            read_identities=self.identities, fetch=self.fetch,
                            read=self.store_read,
                            execute=override.get("execute", self.execute),
                            commit=override.get("commit", self.commit), **seams)

    def run_adapter(self, **seams):
        pinned = seams.pop("pinned", None) or self.pinned
        seams.setdefault("attempt", "0")
        return self.adapter(pinned=pinned, **seams).run()

    def read(self, *parts):
        return json.loads(self.root.joinpath(*parts).read_text())

    def store_read(self, key):
        if key not in self.objects:
            return None, None
        return self.objects[key], self.object_generations.get(key)

    def generation_of(self, key):
        return self.object_generations.get(key)

    def close(self):
        self._tmp.cleanup()

    def __del__(self):
        self.close()


class ManifestTests(unittest.TestCase):
    def setUp(self):
        self.world = World()
        self.addCleanup(self.world.close)

    def test_manifest_paths_are_arguments_and_resolve_against_the_manifest(self):
        manifest = main.read_manifest(self.world.root / "manifest.json")
        self.assertEqual(manifest.ids, ("a", "b", "c"))
        self.assertEqual(manifest.file("data/audio/a.wav"),
                         (self.world.root / "data" / "audio" / "a.wav").resolve())

    def test_manifest_rejects_unknown_fields_unsafe_paths_and_duplicate_ids(self):
        base = self.world.read("manifest.json")
        cases = [
            (dict(base, extra=1), "unknown manifest fields"),
            (dict(base, files={"../outside": SHA_X}), "escapes"),
            (dict(base, ids=["a", "a", "b"]), "unique sample ids"),
            ({k: base[k] for k in ("files", "seeds")}, "ids"),
            (dict(base, seeds={"model": SHA_X}), "'config'"),
            (dict(base, files={"data/missing.wav": SHA_X}), "missing file"),
            (dict(base, seeds={"config": SHA_X[:-1], "model": SHA_X, "audio": SHA_X}), "config"),
            (dict(base, checksums={"bucket/object": SHA_X}), "gs://"),
        ]
        for doc, message in cases:
            with self.subTest(message=message):
                with self.assertRaisesRegex(main.ManifestError, message):
                    main.read_manifest(self.world.write("bad.json", json.dumps(doc)))
        with self.assertRaises(main.ManifestError):
            main.read_manifest(self.world.write("bad.json", "{"))

    def test_runner_manifest_shape_is_accepted(self):
        # the runner's own manifest_for(...) identity document, as the real seam produces
        doc = {"version": "lifemate-v1", "split": "train", "sample_ids": "a,c",
               "source_sha256": SHA_X, "input_sha256": SHA_X, "catalog_sha256": SHA_X,
               "llm": {"config.json": SHA_X}, "asr": {"config.json": SHA_X},
               "organizer_library": {"__init__.py": SHA_X}}
        path = self.world.write("runner.json", json.dumps(doc))
        (self.world.root / "llm").mkdir(); (self.world.root / "llm/config.json").write_text("x")
        (self.world.root / "asr").mkdir(); (self.world.root / "asr/config.json").write_text("x")
        (self.world.root / "organizer_library").mkdir()
        (self.world.root / "organizer_library/__init__.py").write_text("x")
        manifest = main.read_manifest(path)
        self.assertEqual(manifest.ids, ("a", "c"))
        self.assertEqual(manifest.seeds["config"], SHA_X)
        self.assertIn("llm/config.json", manifest.files)

    def test_changed_input_bytes_are_refused(self):
        (self.world.root / "data" / "audio" / "a.wav").write_text("changed")
        with self.assertRaisesRegex(ManifestError, "changed"):
            verify_files(self.world.manifest)

    def test_pinned_service_must_carry_complete_checksums(self):
        for missing in ("model", "source", "checksums"):
            with self.subTest(missing=missing):
                pinned = dict(self.world.pinned)
                pinned.pop(missing)
                with self.assertRaisesRegex(main.IdentityError, "incomplete"):
                    main.check_identity(self.world.manifest, pinned, self.world.identities)


class IdentityTests(unittest.TestCase):
    def test_identity_mismatch_fails_before_fetching_or_running_anything(self):
        world = World()
        self.addCleanup(world.close)
        world.pinned = dict(world.pinned, model="gs://models/other@2")
        with self.assertRaisesRegex(main.IdentityError, "model"):
            world.run_adapter()

    def test_checksum_mismatch_fails_closed_and_keeps_the_evidence(self):
        world = World()
        self.addCleanup(world.close)
        world.pinned = dict(world.pinned, checksums={"model": hashlib.sha256(b"y").hexdigest()})
        with self.assertRaises(main.IdentityError):
            world.run_adapter()
        evidence = world.read("run.json")
        self.assertEqual(evidence["outcome"], "failed")
        self.assertIn("failed-0", evidence["attempt"])
        self.assertEqual(world.objects, {})

    def test_smoke_sample_result_is_refused_before_the_loop(self):
        world = World(mode="hash")   # smoke artifact exists and decodes, but as a list
        self.addCleanup(world.close)
        with self.assertRaisesRegex(main.ConflictError, "smoke"):
            world.run_adapter(resume="reuse")
        self.assertEqual([c for c in world.calls if c[0] == "execute"], [])

    def test_committed_manifest_is_a_valid_shared_result_manifest(self):
        from services.lifemate_cloud.manifest import ResultManifest
        world = World()
        self.addCleanup(world.close)
        manifest = world.run_adapter(run_id="run-7")["manifest"]
        parsed = ResultManifest.from_dict(
            {k: v for k, v in manifest.items() if k != "coverage"})
        self.assertEqual(parsed.run_id, "run-7")
        parsed.verify_complete()
        self.assertEqual({e.name for e in parsed.entries}, set(parsed.required))
        self.assertTrue(all(e.generation == 42 for e in parsed.entries))

    def test_adapter_imports_without_the_shared_services_package(self):
        code = ("import sys; sys.path.insert(0, 'workers');"
                "sys.modules['services'] = None;"  # simulate services/ being absent
                "import workers.gpu_eval.main as m;"
                "print(m._shared_manifest()); sys.exit(0 if m._shared_manifest() is None else 1)")
        done = subprocess.run([sys.executable, "-c", code],
                              cwd=Path(main.__file__).parents[2], capture_output=True, text=True)
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)

    def test_adapter_imports_no_cloud_or_network_sdk(self):
        code = ("import sys, workers.gpu_eval.main;"
                "bad = sorted(m for m in sys.modules if m.split('.')[0] in "
                "('google', 'requests', 'urllib3', 'httpx', 'pandas'));"
                "print(bad) or sys.exit(bool(bad))")
        done = subprocess.run([sys.executable, "-c", code],
                              cwd=Path(main.__file__).parents[2], capture_output=True, text=True)
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)


class CommitTests(unittest.TestCase):
    def test_completed_samples_commit_once_with_generation_in_input_order(self):
        world = World()
        self.addCleanup(world.close)
        evidence = world.run_adapter()
        self.assertEqual([key for key, _, _ in world.committed],
                         ["results/a.json", "results/b.json", "results/c.json",
                          "results/manifest.json"])
        per_sample = [gen for key, _, gen in world.committed if key != "results/manifest.json"]
        self.assertEqual(set(per_sample), {42})
        self.assertEqual(evidence["outcome"], "complete")
        self.assertEqual([s["id"] for s in evidence["samples"]], ["a", "b", "c"])
        self.assertNotIn("smoke", json.dumps(evidence["samples"]))
        manifest = evidence["manifest"]
        self.assertEqual(manifest["coverage"], {"expected": 3, "committed": 3, "unique": 3})
        self.assertEqual(manifest["required"],
                         ["results/a.json", "results/b.json", "results/c.json"])
        self.assertEqual([e["name"] for e in manifest["entries"]], manifest["required"])
        self.assertTrue(all(e["generation"] == 42 for e in manifest["entries"]))
        self.assertEqual(world.read("results", "manifest.json"), manifest)

    def test_completed_sample_commits_carry_verified_identity_checksums(self):
        world = World()
        self.addCleanup(world.close)
        evidence = world.run_adapter()
        for sample in evidence["samples"]:
            self.assertEqual(sample["checksums"],
                             {path: SHA_X for path in ("config", "model", "audio")})
            self.assertEqual(set(sample["timing"]),
                             {"cold_load", "asr", "planning_execution", "total"})
            self.assertEqual(sample["output_sha256"],
                             hashlib.sha256(world.objects[sample["key"]]).hexdigest())

    def test_rerun_reuses_identical_artifacts_and_never_redoes_samples(self):
        world = World()
        first = world.run_adapter()
        world.calls.clear()
        second = world.run_adapter(resume="reuse")
        stored = world.read("results", "manifest.json")
        self.assertEqual(stored, world.objects["results/manifest.json"].decode() and
                         json.loads(world.objects["results/manifest.json"]))
        self.assertEqual([c for c in world.calls if c[0] == "execute"], [])
        self.assertEqual([e["name"] for e in second["manifest"]["entries"]],
                         ["results/a.json", "results/b.json", "results/c.json"])

    def test_conflicting_artifact_fails_and_writes_no_manifest(self):
        world = World()
        self.addCleanup(world.close)
        world.objects["results/b.json"] = main._json_bytes(entry("b", "f" * 64))
        with self.assertRaises(main.ConflictError):
            world.run_adapter()
        self.assertEqual(world.read("run.json")["outcome"], "failed")
        self.assertFalse((world.root / "results" / "manifest.json").exists())

    def test_result_for_the_wrong_sample_is_refused(self):
        world = World()
        self.addCleanup(world.close)
        spoof = lambda sample: entry("spoofed")
        with self.assertRaisesRegex(main.CoverageError, "spoofed"):
            world.run_adapter(execute=spoof)
        self.assertNotIn("results/a.json", world.objects)

    def test_completed_sample_is_verified_against_its_marker(self):
        world = World()
        self.addCleanup(world.close)
        adapter = world.adapter(resume="reuse")
        started = adapter.process(main.Sample("a"))
        again = adapter.process(main.Sample("a"))
        self.assertEqual(again["sample_sha256"], started["sample_sha256"])
        self.assertEqual(again["output_sha256"],
                         hashlib.sha256(world.objects["results/a.json"]).hexdigest())
        world.objects["results/a.json"] = main._json_bytes(entry("a", "f" * 64))
        with self.assertRaisesRegex(main.ConflictError, "conflicts"):
            adapter.process(main.Sample("a"))


class CoverageTests(unittest.TestCase):
    def test_incomplete_coverage_is_never_a_complete_manifest(self):
        world = World()
        self.addCleanup(world.close)
        adapter = world.adapter(resume="reuse")
        samples = [adapter.process(main.Sample(sample_id)) for sample_id in ("a", "c")]
        failed = main.Timing(cold_load=0.1, asr=[], planning_execution=[], total=1.0)
        with self.assertRaisesRegex(main.CoverageError, "'b'"):
            adapter.finish(samples, failed)
        self.assertFalse((world.root / "results" / "manifest.json").exists())

    def test_failure_mid_loop_keeps_completed_samples_and_fails_closed(self):
        world = World(mode="boom")
        self.addCleanup(world.close)
        with self.assertRaisesRegex(RuntimeError, "simulator died"):
            world.run_adapter()
        self.assertEqual([key for key, _, _ in world.committed], ["results/a.json"])
        evidence = world.read("run.json")
        self.assertEqual(evidence["outcome"], "failed")
        self.assertEqual(evidence["samples"], [])
        self.assertFalse((world.root / "results" / "manifest.json").exists())
        # `a` was committed before the death and `b` may have started (its execute
        # marker exists). A reuse adopts only byte-identical committed artifacts, so
        # it must fail closed on `b` and never retry it (plan:134); the explicit
        # restart reproduces `b` under a new attempt and pins all three.
        transient = [c for c in world.calls if c[0] == "execute"]
        self.assertEqual(transient, [("execute", "a"), ("execute", "b")])
        world.calls.clear()
        with self.assertRaisesRegex(main.AmbiguousExecution,
                                    "no committed artifact.*--resume restart"):
            world.run_adapter(resume="reuse")
        self.assertEqual([c for c in world.calls if c[0] == "execute"], [])
        self.assertFalse((world.root / "results" / "manifest.json").exists())
        world.calls.clear()
        resumed = world.run_adapter(resume="restart", accept_restart=True, attempt="2")
        self.assertEqual([c["id"] for c in resumed["samples"]], ["a", "b", "c"])
        self.assertEqual([e["name"] for e in resumed["manifest"]["entries"]],
                         ["results/a.json", "results/b.json", "results/c.json"])
        self.assertEqual([c for c in world.calls if c[0] == "execute"],
                         [("execute", "b"), ("execute", "c")])

    def test_reuse_refuses_a_marked_sample_without_a_committed_artifact(self):
        # plan:134: a sample that may already have started is never retried
        # implicitly. A start marker with no committed artifact must fail closed
        # under --resume reuse and name the explicit restart remediation.
        world = World()
        self.addCleanup(world.close)
        adapter = world.adapter()
        adapter.write_marker(main.Sample("a"), "execute")
        world.calls.clear()
        with self.assertRaisesRegex(
                main.AmbiguousExecution,
                r"sample\(s\) \['a'\] carry start markers but no committed artifact.*"
                r"--resume restart --accept-restart --attempt <new>"):
            world.run_adapter(resume="reuse")
        # Refused before any sample ran: no second execution, no committed object.
        self.assertEqual([c for c in world.calls if c[0] == "execute"], [])
        self.assertEqual(world.objects, {})
        self.assertEqual(world.read("run.json")["outcome"], "failed")

    def test_reuse_completion_publishes_the_manifest_without_a_second_execution(self):
        # A resumed run whose earlier attempt died before finalizing must still
        # publish a durable generation-pinned manifest; it may not report complete
        # with no manifest, and must not re-execute any sample (finding 6).
        world = World(mode="boom")
        self.addCleanup(world.close)
        with self.assertRaisesRegex(RuntimeError, "simulator died"):
            world.run_adapter()
        self.assertEqual(set(world.objects), {"results/a.json"})
        # Simulate the death having happened after every sample committed but
        # before the manifest: commit the remaining samples' artifacts directly.
        for sample_id in ("b", "c"):
            key = f"results/{sample_id}.json"
            content = main._json_bytes(entry(sample_id))
            world.objects[key] = content
            world.object_generations[key] = world.object_gen
            world.write(f"started/{sample_id}-committed-1.json",
                        json.dumps({"id": sample_id, "stage": "committed", "pid": 1,
                                    "attempt": "failed-0",
                                    "output_sha256": hashlib.sha256(content).hexdigest()}))
        world.calls.clear()
        resumed = world.run_adapter(resume="reuse")
        self.assertEqual(resumed["outcome"], "complete")
        self.assertEqual([c for c in world.calls if c[0] == "execute"], [])
        self.assertIn("results/manifest.json", world.objects)
        self.assertEqual(world.read("results", "manifest.json"), resumed["manifest"])
        self.assertEqual(sorted({e["name"] for e in resumed["manifest"]["entries"]}),
                         ["results/a.json", "results/b.json", "results/c.json"])
        self.assertTrue(all(e["generation"] == 42
                            for e in resumed["manifest"]["entries"]))
        manifest = json.loads(world.objects["results/manifest.json"])
        self.assertEqual(manifest["coverage"], {"expected": 3, "committed": 3, "unique": 3})


class ResilienceTests(unittest.TestCase):
    def test_start_marker_fails_closed_after_a_worker_death(self):
        world = World()
        self.addCleanup(world.close)
        world.adapter(clock=lambda: 5.0).process(main.Sample("a"))
        markers = [json.loads(p.read_text()) for p in sorted((world.root / "started").glob("*.json"))]
        self.assertEqual(sorted({(m["id"], m["attempt"]) for m in markers}), [("a", "failed-0")])
        with self.assertRaisesRegex(main.AmbiguousExecution, "may already have started"):
            world.run_adapter()
        self.assertEqual([c for c in world.calls if c[0] == "execute"], [("execute", "a")])
        self.assertEqual([key for key, _, _ in world.committed], ["results/a.json"])
        self.assertEqual(world.read("run.json")["outcome"], "failed")

    def test_restart_attempt_after_death_completes_without_redoing_samples(self):
        world = World()
        self.addCleanup(world.close)
        world.adapter().process(main.Sample("a"))
        world.calls.clear()
        evidence = world.run_adapter(resume="restart", accept_restart=True, attempt="2")
        # `a` may already have started, so a restart never reruns it; the remaining
        # samples had not started and are executed normally.
        self.assertEqual([c for c in world.calls if c[0] == "execute"],
                         [("execute", "b"), ("execute", "c")])
        self.assertEqual(evidence["outcome"], "complete")
        self.assertEqual(evidence["attempt"], "restart-2")
        self.assertIn("failed-0", {m["attempt"] for m in evidence["superseded_markers"]["a"]})

    def test_restart_with_the_marker_attempt_is_refused(self):
        world = World()
        self.addCleanup(world.close)
        world.adapter().process(main.Sample("a"))       # marker: failed-0
        world.calls.clear()
        with self.assertRaisesRegex(main.AmbiguousExecution, "new attempt label"):
            world.run_adapter(resume="restart", accept_restart=True, attempt="0")
        # Refused before the loop: the pre-existing committed artifact stays the
        # only object and no sample ran under the old attempt label.
        self.assertEqual([c for c in world.calls if c[0] == "execute"], [])
        self.assertEqual(set(world.objects), {"results/a.json"})

    def test_restart_without_accept_is_refused(self):
        world = World()
        self.addCleanup(world.close)
        world.adapter().process(main.Sample("a"))
        world.calls.clear()
        with self.assertRaisesRegex(main.AmbiguousExecution, "requires --accept-restart"):
            world.run_adapter(resume="restart", attempt="2")
        self.assertEqual([c for c in world.calls if c[0] == "execute"], [])

    def test_restart_with_a_distinct_attempt_records_the_superseded_markers(self):
        world = World()
        self.addCleanup(world.close)
        world.adapter(attempt="1").process(main.Sample("a"))   # marker: failed-1
        evidence = world.run_adapter(resume="restart", accept_restart=True, attempt="2")
        self.assertEqual(evidence["outcome"], "complete")
        self.assertEqual(evidence["attempt"], "restart-2")
        superseded = world.read("run.json")["superseded_markers"]
        self.assertEqual(sorted(superseded), ["a"])
        self.assertIn("failed-1", {m["attempt"] for m in superseded["a"]})
        self.assertEqual(world.read("run.json")["attempt"], "restart-2")


LAUNCHER_TEMPLATE = '''
import hashlib, json
from pathlib import Path

ROOT = Path(__file__).with_name("run")
STATE = ROOT / "launcher-state.json"

def _state():
    return json.loads(STATE.read_text()) if STATE.is_file() else {"objects": {}}

def _save(state):
    STATE.write_text(json.dumps(state, sort_keys=True))

def read_identities(pinned):
    return {"model": pinned["model"], "source": pinned["source"]}

def fetch(uri, checksum):
    return b"", 1

def read(key):
    state = _state()
    blob = state["objects"].get(key)
    return (None, None) if blob is None else (blob.encode(), 7)

def execute(sample):
    if sample.id == "boom":
        raise RuntimeError("synthetic failure")
    return ({"id": sample.id, "tool_calls": [], "state_hash": "0" * 64,
              "stop_reason": "model_finished"},
            {"cold_load": 0.1, "asr": 0.2, "planning_execution": 0.3})

def commit(key, content, generation):
    state = _state()
    existing = state["objects"].get(key)
    if existing is None:
        state["objects"][key] = content.decode()
        _save(state)
        return "created"
    return "identical" if existing.encode() == content else "conflict"
'''


class CliTests(unittest.TestCase):
    """The real entrypoint: launcher module on disk plus a synthetic manifest."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name) / "run"
        self.root.mkdir()
        world = World()
        self.addCleanup(world.close)
        (self.root / "inputs.txt").write_text("x")
        (self.root / "manifest.json").write_text(json.dumps(
            {"ids": ["a", "b"], "files": {"inputs.txt": SHA_X}, "seeds": world.seeds}))
        (self.root / "pinned.json").write_text(json.dumps({
            "dataset": "gs://dataset/fixture", "model": world.pinned["model"],
            "source": SHA_SRC, "checksums": world.seeds}))
        self.launcher = self.write_launcher("launcher.py", LAUNCHER_TEMPLATE)

    def write_launcher(self, name, source):
        path = Path(self._tmp.name) / name
        path.write_text(source)
        (Path(self._tmp.name) / "run").mkdir(exist_ok=True)
        return path

    def argv(self, *extra):
        return [str(self.root / "manifest.json"), "--run-dir", str(self.root),
                "--run-id", "run-1", *extra]

    def main(self, argv):
        with contextlib.redirect_stderr(io.StringIO()) as err:
            code = main.main(argv)
        return code, err.getvalue()

    def test_missing_launcher_fails_cleanly(self):
        code, err = self.main(self.argv("--launcher", str(self.root / "nope.py"),
                                        "--pinned", str(self.root / "pinned.json")))
        self.assertEqual(code, 2)
        self.assertIn("launcher module not found", err)
        self.assertFalse((self.root / "started").exists())

    def test_incomplete_launcher_fails_cleanly(self):
        partial = self.write_launcher(
            "partial.py", "def fetch(uri, checksum):\n    return b'', 1\n")
        code, err = self.main(self.argv("--launcher", str(partial),
                                        "--pinned", str(self.root / "pinned.json")))
        self.assertEqual(code, 2)
        self.assertIn("missing required callables", err)
        self.assertIn("execute", err)
        self.assertFalse((self.root / "started").exists())

    def test_launcher_without_the_flag_is_a_usage_error(self):
        with contextlib.redirect_stderr(io.StringIO()) as err:
            with self.assertRaises(SystemExit) as raised:
                main.main(self.argv())
        self.assertNotEqual(raised.exception.code, 0)
        self.assertIn("--launcher", err.getvalue())

    def test_cli_runs_a_synthetic_manifest_end_to_end(self):
        code, err = self.main(self.argv("--launcher", str(self.launcher),
                                        "--pinned", str(self.root / "pinned.json")))
        self.assertEqual(code, 0, err)
        evidence = json.loads((self.root / "run.json").read_text())
        self.assertEqual(evidence["outcome"], "complete")
        self.assertEqual(evidence["run_id"], "run-1")
        self.assertEqual([s["id"] for s in evidence["samples"]], ["a", "b"])
        self.assertEqual(evidence["manifest"]["required"],
                         ["results/a.json", "results/b.json"])
        self.assertTrue((self.root / "results" / "manifest.json").is_file())
        self.assertEqual(sorted({p.name.split("-")[0] for p in (self.root / "started").glob("*")}),
                         ["a", "b"])
        self.assertEqual(len(list((self.root / "started").glob("*.json"))), 4)

    def test_cli_restart_same_attempt_is_refused_and_distinct_attempt_proceeds(self):
        pinned = ("--pinned", str(self.root / "pinned.json"), "--launcher", str(self.launcher))
        (self.root / "started").mkdir()
        (self.root / "started" / "a-execute-1.json").write_text(json.dumps(
            {"id": "a", "stage": "execute", "pid": 1, "attempt": "failed-0",
             "started": 1.0}))
        code, err = self.main(self.argv(*pinned, "--resume", "restart",
                                        "--accept-restart", "--attempt", "0"))
        self.assertEqual(code, 1)
        self.assertIn("new attempt label", err)
        self.assertEqual(json.loads((self.root / "run.json").read_text())["outcome"], "failed")
        code, err = self.main(self.argv(*pinned, "--resume", "restart",
                                        "--accept-restart", "--attempt", "1"))
        self.assertEqual(code, 0, err)
        evidence = json.loads((self.root / "run.json").read_text())
        self.assertEqual(evidence["attempt"], "restart-1")
        self.assertEqual(sorted({m["attempt"] for m in evidence["superseded_markers"]["a"]}),
                         ["failed-0"])


class TimingTests(unittest.TestCase):
    def test_timing_stages_are_recorded_separately(self):
        world = World()
        self.addCleanup(world.close)
        tick = iter(range(0, 1000, 3))
        evidence = world.run_adapter(clock=lambda: next(tick))
        self.assertEqual(set(evidence["timing"]),
                         {"cold_load", "asr", "planning_execution", "total"})
        self.assertEqual(evidence["timing"]["asr"]["count"], 3)
        self.assertGreaterEqual(evidence["timing"]["total"]["max"],
                                max(s["timing"]["total"] for s in evidence["samples"]))
        self.assertGreaterEqual(evidence["timing"]["cold_load"], 0)


if __name__ == "__main__":
    unittest.main()
