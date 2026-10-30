import assert from "node:assert/strict";
import { test } from "node:test";
import { compareRuns, scrubRun, selectForComparison } from "../src/lib/compare.ts";
import type { RunDetail, RunMeta } from "../src/lib/types.ts";

function meta(overrides: Partial<RunMeta> = {}): RunMeta {
  return {
    run_id: "run-1",
    owner: "researcher@example.com",
    state: "SUCCEEDED",
    cancel_requested: false,
    batch_phase: "SUCCEEDED",
    failure: null,
    benchmark_id: "public-test",
    benchmark_hash: "c".repeat(64),
    benchmark_cases: 12,
    experiment_id: "exp-1",
    dataset_id: "ds-1",
    model_id: "mdl-1",
    mode: "agent",
    configuration_hash: "f".repeat(64),
    ...overrides,
  };
}

test("the same benchmark and configuration compares as matching", () => {
  const comparison = compareRuns(meta(), meta({ run_id: "run-2" }));
  assert.equal(comparison.comparable, true);
  assert.deepEqual(comparison.blockers, []);
  assert.match(comparison.comparableWhen, /benchmark and pinned configuration/);
});

test("status and owner are context, not identity", () => {
  const comparison = compareRuns(
    meta(),
    meta({ run_id: "run-2", owner: "other@example.com", state: "FAILED", batch_phase: "FAILED" }),
  );
  assert.equal(comparison.comparable, true);
  assert.deepEqual(comparison.blockers, []);
  assert.ok(comparison.notes.includes("state differs"));
  assert.ok(comparison.notes.includes("batch phase differs"));
});

test("a different benchmark id blocks comparability", () => {
  const comparison = compareRuns(meta(), meta({ run_id: "run-2", benchmark_id: "other" }));
  assert.equal(comparison.comparable, false);
  assert.deepEqual(comparison.blockers, ["benchmark differs"]);
});

test("a different configuration digest blocks comparability", () => {
  const comparison = compareRuns(meta(), meta({ run_id: "run-2", configuration_hash: "a".repeat(64) }));
  assert.equal(comparison.comparable, false);
  assert.deepEqual(comparison.blockers, ["configuration differs"]);
});

test("dataset, model, experiment and mode differences are identity too", () => {
  const comparison = compareRuns(
    meta(),
    meta({ run_id: "run-2", dataset_id: "ds-2", model_id: "mdl-2", experiment_id: "exp-2", mode: "plain" }),
  );
  assert.equal(comparison.comparable, false);
  assert.deepEqual(comparison.blockers.sort(), [
    "dataset differs",
    "experiment differs",
    "mode differs",
    "model differs",
  ]);
});

test("missing identity on either side is reported, not assumed equal", () => {
  const comparison = compareRuns(meta({ benchmark_id: null }), meta({ run_id: "run-2" }));
  assert.equal(comparison.comparable, false);
  assert.deepEqual(comparison.blockers, ["benchmark differs"]);
});

test("state differences are reported as field differences, not averaged away", () => {
  const comparison = compareRuns(meta(), meta({ run_id: "run-2", state: "FAILED" }));
  const state = comparison.fields.find((f) => f.label === "State");
  assert.deepEqual(state, { label: "State", left: "SUCCEEDED", right: "FAILED", differs: true });
  assert.equal(comparison.comparable, true); // status is context on the same identity
});

test("cancellation intent and failure codes are compared but do not decide identity", () => {
  const comparison = compareRuns(
    meta(),
    meta({
      run_id: "run-2",
      cancel_requested: true,
      failure: { code: "manifest_incomplete", summary: "results were incomplete" },
    }),
  );
  assert.ok(comparison.notes.includes("cancel requested differs"));
  assert.ok(comparison.notes.includes("failure differs"));
  assert.equal(comparison.comparable, true);
});

test("batch phase difference alone is a context note", () => {
  const comparison = compareRuns(meta(), meta({ run_id: "run-2", batch_phase: "RUNNING" }));
  assert.deepEqual(comparison.notes, ["batch phase differs"]);
  assert.deepEqual(comparison.blockers, []);
});

test("selection keeps the first choice and the second, toggling off", () => {
  const byId = { a: meta({ run_id: "a" }), b: meta({ run_id: "b" }), c: meta({ run_id: "c" }) };
  assert.deepEqual(selectForComparison([], "a", byId), { selection: ["a"], rejected: null });
  assert.deepEqual(selectForComparison(["a"], "b", byId), { selection: ["a", "b"], rejected: null });
  assert.deepEqual(selectForComparison(["a", "b"], "b", byId), { selection: ["a"], rejected: null });
  assert.deepEqual(selectForComparison(["a"], "zzz", byId), { selection: ["a"], rejected: "zzz" });
});

test("scrubRun keeps approved metadata and drops restricted fields", () => {
  const detail: RunDetail = {
    ...meta({ state: "FAILED", failure: { code: "worker_lost", summary: "the worker stopped" } }),
    artifacts: [{ name: "manifest.json", generation: "5", checksum: "c", bytes: 42 }],
  };
  const polluted = {
    ...detail,
    decoding: { temperature: 0 },
    objects: { "datasets/train.jsonl": 99 },
    audio_url: "gs://private/audio.wav",
    transcript: "secret transcript text",
    artifacts: [{ ...detail.artifacts[0], trace: ["tool call with private input"] }],
  };

  const clean = scrubRun(polluted);
  const serialized = JSON.stringify(clean);
  for (const leak of [
    "audio",
    "transcript",
    "tool call with private input",
    "temperature",
    "train.jsonl",
  ]) {
    assert.equal(serialized.includes(leak), false, `leaked: ${leak}`);
  }
  assert.equal(clean.run_id, "run-1");
  assert.equal(clean.failure?.code, "worker_lost");
  assert.equal(clean.artifacts[0].name, "manifest.json");
});

test("scrubRun keeps the echoed identity fields", () => {
  const clean = scrubRun({ ...meta(), artifacts: [] });
  assert.equal(clean.benchmark_id, "public-test");
  assert.equal(clean.experiment_id, "exp-1");
  assert.equal(clean.dataset_id, "ds-1");
  assert.equal(clean.model_id, "mdl-1");
  assert.equal(clean.mode, "agent");
  assert.equal(clean.configuration_hash, "f".repeat(64));
});

test("scrubRun drops a decoding or object payload the server should never send", () => {
  const polluted = {
    ...meta(),
    artifacts: [],
    decoding: { temperature: 0.2 },
    model_hash: "b".repeat(64),
    objects: { "models/mdl-1.bin": 1 },
  } as unknown as RunDetail;
  const serialized = JSON.stringify(scrubRun(polluted));
  for (const leak of ["temperature", "models/mdl-1.bin", "models/mdl"]) {
    assert.equal(serialized.includes(leak), false, `leaked: ${leak}`);
  }
});

test("scrubRun tolerates missing artifacts", () => {
  const partial = { run_id: "r", state: "QUEUED" } as unknown as RunDetail;
  const clean = scrubRun(partial);
  assert.deepEqual(clean.artifacts, []);
  assert.equal(clean.owner, null);
});
