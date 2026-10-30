"""Offline GPU evaluation adapter: check in, run samples, commit conditionally.

Task-neutral Batch entrypoint. Every effectful step is an injected callable so
this module imports nothing beyond the standard library and never imports a
cloud client: the operator supplies a launcher module (`--launcher <path.py>`)
that defines `read_identities`, `fetch`, `read`, `execute` and `commit`; the
existing inference/evaluation code backs `execute`, which receives one `Sample`
and returns `(submission_row, stages)`. `main()` refuses to run when the
launcher or any of its callables is missing.

`commit` follows the shared artifact contract (ticket 15's
`InMemoryArtifactStore.put_if_absent`): it returns the stored generation on
create, reuses an object whose bytes are identical, and refuses a name whose
content differs. The final manifest is ticket 15's `ResultManifest`
`{run_id, required, entries:[{name, generation, checksum}]}`.

Recovery: the organizer SDK has no documented session-restore API, so a sample
that may have started (it has a start marker) is never retried implicitly. The
next attempt fails closed until an operator picks `--resume reuse` (adopt only
byte-identical committed artifacts) or forces an explicit new attempt with
`--resume restart --accept-restart`, whose attempt label is recorded in
`run.json` along with the superseded markers.
"""

import argparse
import hashlib
import importlib.util
import json
import os
import sys
import time
from dataclasses import dataclass
from pathlib import Path


LAUNCHER_SEAMS = ("read_identities", "fetch", "read", "execute", "commit")


class LauncherError(RuntimeError):
    """The launcher module is missing or does not define the required seams."""


def load_launcher(path):
    """Import the operator-supplied launcher module and check its seam contract."""
    source = Path(path).resolve()
    if not source.is_file():
        raise LauncherError(f"launcher module not found: {source}")
    spec = importlib.util.spec_from_file_location(
        f"gpu_eval_launcher_{source.stem}_{abs(hash(str(source))) & 0xFFFFFF:06x}", source)
    if spec is None or spec.loader is None:
        raise LauncherError(f"launcher {source} is not an importable Python module")
    module = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(module)
    except Exception as exc:
        raise LauncherError(
            f"launcher {source} failed to import: {type(exc).__name__}: {exc}") from exc
    missing = [name for name in LAUNCHER_SEAMS if not callable(getattr(module, name, None))]
    if missing:
        raise LauncherError(
            f"launcher {source} is missing required callables: {sorted(missing)}; "
            f"it must define {list(LAUNCHER_SEAMS)}")
    return {name: getattr(module, name) for name in LAUNCHER_SEAMS}


from . import manifest as checkin
from .manifest import ManifestError, is_sha256

read_manifest = checkin.read_manifest

# The candidate runner treats only these stop reasons as a complete sample; every
# other reason (turn/call/format/inference limits) is an incomplete episode and
# must never be committed as a result.
COMPLETE_STOPS = frozenset({"model_finished", "asked_missing_info"})
TIMING_KEYS = ("cold_load", "asr", "planning_execution", "total")
MANIFEST_KEY = "results/manifest.json"


class IdentityError(RuntimeError):
    """Pinned identities are incomplete or disagree with what was materialized."""


class ConflictError(RuntimeError):
    """An artifact exists with content that does not match this sample's output."""


class CoverageError(RuntimeError):
    """A sample result is missing, duplicated, incomplete or belongs to another sample."""


class AmbiguousExecution(RuntimeError):
    """A sample may already have started; nothing may retry it automatically."""


@dataclass(frozen=True)
class Timing:
    cold_load: float
    asr: list
    planning_execution: list
    total: float


@dataclass(frozen=True)
class Sample:
    id: str


def _shared_manifest():
    """Ticket 15's manifest module, when the shared services package is importable."""
    try:
        from services.lifemate_cloud import manifest as shared
    except ImportError:
        return None
    return shared


def _json_bytes(value):
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"),
                      sort_keys=True).encode("utf-8")


def _atomic(path, content):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    with tmp.open("wb") as handle:
        handle.write(content)
        handle.flush()
        os.fsync(handle.fileno())
    tmp.replace(path)


def _stats(values):
    ordered = sorted(round(v, 6) for v in values)
    if not ordered:
        return {"count": 0}
    return {"count": len(ordered), "sum": round(sum(ordered), 6),
            "min": ordered[0], "max": ordered[-1]}


def build_parser():
    parser = argparse.ArgumentParser(description="Batch GPU evaluation worker adapter")
    parser.add_argument("manifest", type=Path,
                        help="run manifest JSON; identity paths are relative to it")
    parser.add_argument("--run-dir", type=Path,
                        help="durable worker state (markers, evidence); "
                             "defaults to the manifest's directory")
    parser.add_argument("--run-id", help="cloud run identity the manifest must belong to")
    parser.add_argument("--attempt", default="0", help="attempt label recorded in evidence")
    parser.add_argument("--resume", choices=("reuse", "restart"), default=None,
                        help="adopt byte-identical committed results (`reuse`), or start an "
                             "explicit new attempt for marked samples (`restart`)")
    parser.add_argument("--accept-restart", action="store_true",
                        help="required with --resume restart: acknowledge that marked, "
                             "uncommitted samples start a new attempt")
    parser.add_argument("--launcher", type=Path, required=True,
                        help="operator-supplied Python module defining read_identities, fetch, "
                             "read, execute and commit")
    parser.add_argument("--pinned", type=Path,
                        help="pinned dataset/model/source/checksums JSON; "
                             "required for real execution")
    return parser


def parse_args(argv=None):
    return build_parser().parse_args(argv)


def pinned_from_file(path):
    document = json.loads(Path(path).read_text(encoding="utf-8"))
    unknown = set(document) - {"dataset", "model", "source", "checksums"}
    if unknown:
        raise IdentityError(f"unknown pinned identity fields: {sorted(unknown)}")
    return document


def check_identity(manifest, pinned, read_identities):
    """Pinned identities must be complete and agree with seeds and materialized bytes."""
    if pinned is None:
        raise IdentityError("no pinned dataset/model/source identity was supplied; "
                            "real execution is refused until identities are pinned")
    if (not isinstance(pinned, dict) or set(pinned) != {"dataset", "model", "source", "checksums"}
            or not all(isinstance(pinned[k], str) and pinned[k]
                       for k in ("dataset", "model", "source"))
            or not isinstance(pinned["checksums"], dict) or not pinned["checksums"]):
        raise IdentityError(f"incomplete pinned identity: {pinned!r}")
    for name, digest in pinned["checksums"].items():
        if not is_sha256(digest):
            raise IdentityError(f"pinned checksum for {name!r} is not sha256")
        if digest not in manifest.seeds.values():
            raise IdentityError(f"pinned {name} checksum is not one of the manifest seeds")
    if not manifest.files and not manifest.checksums:
        raise IdentityError("run manifest has no verified identities")
    actual = read_identities(pinned)
    for key in ("model", "source"):
        if actual.get(key) != pinned[key]:
            raise IdentityError(f"materialized {key} {actual.get(key)!r} "
                                f"does not match pinned {pinned[key]!r}")


def check_result(sample_id, output):
    """A result is committable only when it is this sample's own complete session."""
    if not isinstance(output, dict):
        raise CoverageError(f"result for {sample_id!r} is not an object")
    if output.get("id") != sample_id:
        raise CoverageError(f"result for {sample_id!r} is for {output.get('id')!r}")
    stop = output.get("stop_reason")
    if stop not in COMPLETE_STOPS:
        raise CoverageError(f"sample {sample_id!r} did not finish: stop_reason {stop!r}")
    calls = output.get("tool_calls")
    digest = output.get("state_hash")
    if not isinstance(calls, list) or not is_sha256(digest):
        raise CoverageError(f"sample {sample_id!r} has an invalid session log")
    return output


class Adapter:
    """One job attempt over a run directory."""

    def __init__(self, manifest, *, pinned, read_identities, fetch, execute, commit,
                 read=None, resume=None, accept_restart=False, attempt="0", run_id=None,
                 run_dir=None, clock=time.time):
        self.manifest = manifest
        self.pinned = pinned
        self.read_identities = read_identities
        self.fetch = fetch
        self.execute = execute
        self.commit = commit
        self.read = read or (lambda key: (None, None))
        self.resume = resume
        self.accept_restart = accept_restart
        self.attempt = attempt
        self.run_id = run_id
        self.clock = clock
        self.root = Path(run_dir or manifest.root).resolve()
        self.evidence = {"ids": list(manifest.ids), "samples": [], "errors": [],
                         "run_id": run_id, "attempt": f"failed-{attempt}"}
        self.cold_load = 0.0

    @property
    def now(self):
        value = self.clock() if callable(self.clock) else self.clock
        return value.timestamp() if hasattr(value, "timestamp") else float(value)

    def attempt_label(self, outcome):
        return f"{outcome}-{self.attempt}"

    def path(self, *parts):
        path = self.root.joinpath(*parts).resolve()
        if not path.is_relative_to(self.root):
            raise ManifestError(f"path escapes the run directory: {parts}")
        return path

    # -- check-in -----------------------------------------------------------

    def prepare(self):
        """Verify every identity before a single sample can start."""
        checkin.verify_files(self.manifest)
        check_identity(self.manifest, self.pinned, self.read_identities)
        for uri, digest in sorted(self.manifest.checksums.items()):
            content, generation = self.fetch(uri, digest)
            if content is None or hashlib.sha256(content).hexdigest() != digest:
                raise IdentityError(f"checksum mismatch for {uri}")

    # -- entry --------------------------------------------------------------

    def run(self):
        started = self.now
        self.evidence["attempt"] = self.attempt_label("failed")
        try:
            self.prepare()
            self.refuse_ambiguous_samples()
            samples = [self.process(Sample(sample_id)) for sample_id in self.manifest.ids]
            return self.finish(samples, Timing(
                cold_load=self.cold_load, asr=[s["timing"]["asr"] for s in samples],
                planning_execution=[s["timing"]["planning_execution"] for s in samples],
                total=self.now - started))
        except BaseException as exc:
            self.evidence.update(outcome="failed", samples=[])
            self.evidence["errors"].append(f"{type(exc).__name__}: {exc}")
            _atomic(self.path("run.json"), _json_bytes(self.evidence))
            raise

    def finish(self, samples, timing):
        """Emit the generation-pinned manifest only for complete, unique coverage."""
        expected, seen = list(self.manifest.ids), [entry["id"] for entry in samples]
        missing = sorted(set(expected) - set(seen))
        extra = sorted(set(seen) - set(expected))
        if missing or extra or len(seen) != len(expected) or len(set(seen)) != len(seen):
            raise CoverageError(f"coverage mismatch: expected {len(expected)}, "
                                f"committed {len(seen)}, missing {missing}, extra {extra}")
        # The committed manifest records which attempt produced the result, not who
        # read it back: a reuse that finds one keeps it, and one that finds none
        # publishes this run's own (never a second execution's) manifest.
        label = self.attempt_label({"reuse": None, "restart": "restart"}.get(
            self.resume, "complete") or "complete")
        summary = {"cold_load": round(timing.cold_load, 6), "asr": _stats(timing.asr),
                   "planning_execution": _stats(timing.planning_execution),
                   "total": _stats([timing.total] + [s["timing"]["total"] for s in samples])}
        stored = self._read_artifact(MANIFEST_KEY)[0]
        # A reuse keeps the artifact already durable under the name (it is
        # byte-identical to this run's own output, checked per sample); a run that
        # completes but finds no committed manifest -- a resumed run whose earlier
        # attempt died before finalizing -- must still publish one, never report
        # complete with no durable manifest, and never a second result.
        document = json.loads(stored) if stored is not None else self._manifest(samples)
        if stored is None:
            accepted = self.commit(MANIFEST_KEY, _json_bytes(document), None)
            if accepted == "conflict":
                raise ConflictError("final manifest already exists with different content")
            _atomic(self.path("results", "manifest.json"), _json_bytes(document))
        self.evidence.update(outcome="complete", attempt=label, timing=summary,
                             samples=samples, manifest=document)
        _atomic(self.path("run.json"), _json_bytes(self.evidence))
        return self.evidence

    def _manifest(self, samples):
        """Ticket 15's generation-pinned ResultManifest, plus local coverage evidence."""
        document = {"run_id": self.run_id,
                    "required": sorted(entry["key"] for entry in samples),
                    "entries": [{"name": entry["key"], "generation": entry["generation"],
                                 "checksum": entry["output_sha256"],
                                 "size": len(_json_bytes(entry["output"]))}
                                for entry in samples]}
        shared = _shared_manifest()
        if shared is not None:   # the offline adapter must import without services/
            built = shared.ResultManifest.create(self.run_id, document["required"])
            for entry in document["entries"]:
                built = built.add(shared.ManifestEntry(**entry))
            document = built.verify_complete().to_dict()
        document["coverage"] = {"expected": len(self.manifest.ids),
                                "committed": len(samples),
                                "unique": len({s["id"] for s in samples})}
        return document

    # -- recovery markers ---------------------------------------------------

    def markers(self, sample_id):
        directory = self.path("started")
        if not directory.is_dir():
            return []
        found = [json.loads(marker.read_text()) for marker in sorted(directory.glob("*.json"))]
        return [marker for marker in found if marker["id"] == sample_id]

    def write_marker(self, sample, stage, **extra):
        marker = {"id": sample.id, "stage": stage, "pid": os.getpid(),
                  "attempt": self.evidence["attempt"], "started": self.now, **extra}
        _atomic(self.path("started", f"{sample.id}-{stage}-{os.getpid()}.json"),
                _json_bytes(marker))
        return marker

    def refuse_ambiguous_samples(self):
        """A sample that may have started is never retried implicitly.

        `--resume reuse` adopts a marked sample only when its committed artifact
        is byte-identical (checked in `accept_existing`); a marked sample with no
        committed artifact fails closed and names the restart remediation.
        `--resume restart` is an explicit operator decision and must carry a
        distinct attempt label plus `--accept-restart`, otherwise the marker
        attempt would silently be re-executed.
        """
        marked = {sample_id: markers for sample_id, markers in
                  ((sample_id, self.markers(sample_id)) for sample_id in self.manifest.ids)
                  if markers}
        if not marked:
            return
        if self.resume == "reuse":
            uncommitted = sorted(sample_id for sample_id in marked
                                 if self._read_artifact(self.artifact_key(sample_id))[0] is None)
            if uncommitted:
                raise AmbiguousExecution(
                    f"sample(s) {uncommitted} carry start markers but no committed artifact; "
                    "--resume reuse adopts only byte-identical committed artifacts and never "
                    "retries a sample that may already have started: pass --resume restart "
                    "--accept-restart --attempt <new> to start a new attempt")
            self.record_superseded(marked)
            return
        if self.resume == "restart":
            if not self.accept_restart:
                raise AmbiguousExecution(
                    f"samples {sorted(marked)} carry start markers; --resume restart starts "
                    "a new attempt and requires --accept-restart "
                    "(or --resume reuse to adopt byte-identical committed artifacts)")
            own = self.attempt_label("failed")   # what this attempt's markers carry
            collisions = sorted(sample_id for sample_id, markers in marked.items()
                                if own in {m["attempt"] for m in markers})
            if collisions:
                raise AmbiguousExecution(
                    f"attempt {self.attempt!r} ({own}) already started sample(s) {collisions}; "
                    "restart needs a new attempt label, e.g. --resume restart "
                    f"--accept-restart --attempt {self.attempt}-1")
            self.evidence["superseded_markers"] = marked
            return
        sample_id, markers = next(iter(marked.items()))
        raise AmbiguousExecution(
            f"sample {sample_id!r} may already have started "
            f"(marker {markers[-1]['attempt']}/{markers[-1]['stage']}); pass --resume reuse "
            "to adopt byte-identical committed artifacts, or --resume restart "
            "--accept-restart with a new --attempt to start a new attempt")

    def record_superseded(self, marked):
        """A reuse records the committed markers it adopted and the attempt it extends."""
        prev = self._read_run_json() or {}
        if prev.get("superseded_markers"):
            self.evidence["superseded_markers"] = prev["superseded_markers"]
        if prev.get("attempt"):
            self.evidence["supersedes_attempt"] = prev["attempt"]
        self.evidence["adopted_markers"] = {
            sample_id: [m for m in markers if m["stage"] == "committed"]
            for sample_id, markers in marked.items()}

    def _read_run_json(self):
        path = self.path("run.json")
        if not path.is_file():
            return None
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except ValueError:
            return None

    # -- one sample ---------------------------------------------------------

    def artifact_key(self, sample_id):
        return f"results/{sample_id}.json"

    def process(self, sample):
        key = self.artifact_key(sample.id)
        existing, generation = self._read_artifact(key)
        if existing is not None:
            return self.accept_existing(sample, existing, generation, key)

        started = self.now
        self.write_marker(sample, "execute")
        output, stages = self._execute(sample)
        check_result(sample.id, output)
        content = _json_bytes(output)
        digest = hashlib.sha256(content).hexdigest()
        accepted = self.commit(key, content, None)
        if accepted == "conflict":
            raise ConflictError(f"{key} already exists with different content")
        stored = self._read_artifact(key)[1]
        self.write_marker(sample, "committed", output_sha256=digest)
        self.cold_load = stages["cold_load"]
        return {"id": sample.id, "key": key, "sample_sha256": digest,
                "output_sha256": digest, "generation": stored,
                "attempt": self.evidence["attempt"], "output": output,
                "checksums": dict(self.manifest.seeds),
                "timing": {"cold_load": stages["cold_load"], "asr": stages["asr"],
                           "planning_execution": stages["planning_execution"],
                           "total": self.now - started}}

    def _execute(self, sample):
        """Call the existing inference/evaluation seam, which owns ASR and planning."""
        result = self.execute(sample)
        output, stages = result if isinstance(result, tuple) else (result, {})
        return output, {"cold_load": float(stages.get("cold_load", 0.0)),
                        "asr": float(stages.get("asr", 0.0)),
                        "planning_execution": float(stages.get("planning_execution", 0.0))}

    def _read_artifact(self, key):
        """Read a committed artifact and its store generation, when one exists."""
        result = self.read(key)
        return result if isinstance(result, tuple) else (result, None)

    def accept_existing(self, sample, existing, generation, key):
        digest = hashlib.sha256(existing).hexdigest()
        committed = [m for m in self.markers(sample.id) if m["stage"] == "committed"]
        if not committed:
            raise ConflictError(f"{key} exists with no commit marker; refusing a "
                                f"smoke or foreign artifact for {sample.id!r}")
        if committed[-1]["output_sha256"] != digest:
            raise ConflictError(f"{key} conflicts with its committed artifact")
        if not self.resume:
            raise AmbiguousExecution(f"{key} already exists for {sample.id!r}; pass --resume")
        check_result(sample.id, json.loads(existing))
        return {"id": sample.id, "key": key, "sample_sha256": digest, "output_sha256": digest,
                "generation": generation, "attempt": committed[-1]["attempt"],
                "output": json.loads(existing),
                "checksums": dict(self.manifest.seeds),
                "timing": dict.fromkeys(TIMING_KEYS, 0.0)}


def run(args, **seams):
    """Load the manifest, pinned identities and launcher seams, then run one attempt."""
    manifest = read_manifest(args.manifest)
    seams = {**load_launcher(args.launcher), **seams}
    return Adapter(manifest, pinned=pinned_from_file(args.pinned),
                   resume=args.resume, accept_restart=args.accept_restart,
                   attempt=args.attempt, run_id=args.run_id,
                   run_dir=args.run_dir, **seams).run()


def main(argv=None):
    args = parse_args(argv)
    try:
        run(args)
    except LauncherError as exc:
        print(f"worker: {exc}", file=sys.stderr)
        return 2
    except (ManifestError, IdentityError, AmbiguousExecution, ConflictError,
            CoverageError) as exc:
        print(f"worker: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
