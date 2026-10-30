import assert from "node:assert/strict";
import { test } from "node:test";
import {
  createApiClient,
  IAP_ASSERTION_HEADER,
  IDEMPOTENCY_HEADER,
  type FetchLike,
} from "../src/lib/api.ts";
import type { RunRequest } from "../src/lib/types.ts";

interface Call {
  url: string;
  init: RequestInit | undefined;
}

function recordingFetch(response: () => Response): { fetch: FetchLike; calls: Call[] } {
  const calls: Call[] = [];
  const fetch: FetchLike = async (url, init) => {
    calls.push({ url, init });
    return response();
  };
  return { fetch, calls };
}

function json(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "content-type": "application/json" },
  });
}

// Exactly the three client fields the API accepts.
const REQUEST: RunRequest = { dataset_id: "ds-1", model_id: "mdl-1", decoding: {} };
const IDENTITY = {
  benchmark_id: "public-test",
  benchmark_hash: "c".repeat(64),
  benchmark_cases: 12,
  experiment_id: "exp-1",
  dataset_id: "ds-1",
  model_id: "mdl-1",
  mode: "agent",
  configuration_hash: "f".repeat(64),
};
const RUN_VIEW = {
  run_id: "run-1",
  owner: "researcher@example.com",
  state: "QUEUED",
  cancel_requested: false,
  batch_phase: null,
  failure: null,
  ...IDENTITY,
};

function client(fetch: FetchLike) {
  return createApiClient({
    baseUrl: "https://api.example.test/",
    iapAssertion: "signed.assertion.token",
    serviceIdToken: "id-token",
    fetch,
  });
}

test("submitRun posts the three client fields with the idempotency key", async () => {
  const { fetch, calls } = recordingFetch(() => json(RUN_VIEW, 202));
  const result = await client(fetch).submitRun("exp-1", REQUEST, "key-abcdefghijklmnop");

  assert.equal(result.ok, true);
  assert.equal(result.status, 202);
  assert.equal(result.data?.run_id, "run-1");
  assert.equal(calls[0].url, "https://api.example.test/api/experiments/exp-1/runs");
  assert.equal(calls[0].init?.method, "POST");
  assert.equal(calls[0].init?.cache, "no-store");

  const headers = calls[0].init?.headers as Record<string, string>;
  assert.equal(headers[IDEMPOTENCY_HEADER], "key-abcdefghijklmnop");
  assert.equal(headers[IAP_ASSERTION_HEADER], "signed.assertion.token");
  assert.equal(headers.authorization, "Bearer id-token");
  const sent = JSON.parse(String(calls[0].init?.body));
  assert.deepEqual(sent, REQUEST);
  assert.deepEqual(Object.keys(sent).sort(), ["dataset_id", "decoding", "model_id"]);
});

test("reads omit the idempotency key", async () => {
  const { fetch, calls } = recordingFetch(() => json({ runs: [] }));
  await client(fetch).listRuns();
  const headers = calls[0].init?.headers as Record<string, string>;
  assert.equal(headers[IDEMPOTENCY_HEADER], undefined);
  assert.equal(calls[0].init?.method, "GET");
  assert.equal(calls[0].url, "https://api.example.test/api/runs");
});

test("listRuns unwraps the runs array", async () => {
  const { fetch } = recordingFetch(() => json({ runs: [RUN_VIEW, { ...RUN_VIEW, run_id: "b" }] }));
  const result = await client(fetch).listRuns();
  assert.equal(result.ok, true);
  assert.deepEqual(
    result.data?.map((r) => r.run_id),
    ["run-1", "b"],
  );
});

test("getRun encodes the run id and preserves server artifacts", async () => {
  const artifact = { name: "predictions.jsonl", generation: "7", checksum: "a".repeat(64), bytes: 1024 };
  const { fetch, calls } = recordingFetch(() =>
    json({ ...RUN_VIEW, artifacts: [artifact] }),
  );
  const result = await client(fetch).getRun("a/b");
  assert.equal(calls[0].url, "https://api.example.test/api/runs/a%2Fb");
  assert.equal(result.data?.state, "QUEUED");
  assert.deepEqual(result.data?.artifacts, [artifact]);
  assert.equal(result.data?.benchmark_id, "public-test");
  assert.equal(result.data?.configuration_hash, "f".repeat(64));
});

test("getRun keeps a real empty artifact list when the API sends none", async () => {
  const { fetch } = recordingFetch(() => json({ ...RUN_VIEW, artifacts: [] }));
  const result = await client(fetch).getRun("run-1");
  assert.deepEqual(result.data?.artifacts, []);
});

test("createExperiment posts the template, dataset and model with a key", async () => {
  const created = {
    experiment_id: "exp-instance-1",
    template_id: "exp-1",
    label: "Compare",
    benchmark_id: "public-test",
    dataset_id: "ds-1",
    model_id: "mdl-1",
    mode: "agent",
    created_by: "researcher@example.com",
    created_at: "2026-10-30T12:00:00+00:00",
    configuration_hash: "f".repeat(64),
  };
  const { fetch, calls } = recordingFetch(() => json(created, 201));
  const result = await client(fetch).createExperiment(
    { template_id: "exp-1", dataset_id: "ds-1", model_id: "mdl-1" },
    "key-abcdefghijklmnop",
  );

  assert.equal(result.ok, true);
  assert.equal(result.status, 201);
  assert.equal(result.data?.experiment_id, "exp-instance-1");
  assert.equal(calls[0].url, "https://api.example.test/api/experiments");
  assert.equal(calls[0].init?.method, "POST");
  const headers = calls[0].init?.headers as Record<string, string>;
  assert.equal(headers[IDEMPOTENCY_HEADER], "key-abcdefghijklmnop");
  assert.equal(headers[IAP_ASSERTION_HEADER], "signed.assertion.token");
  const sent = JSON.parse(String(calls[0].init?.body));
  assert.deepEqual(Object.keys(sent).sort(), ["dataset_id", "model_id", "template_id"]);
});

test("createExperiment surfaces a conflict as a code, not a payload", async () => {
  const { fetch } = recordingFetch(() => json({ code: "conflict" }, 409));
  const result = await client(fetch).createExperiment(
    { template_id: "exp-1", dataset_id: "ds-1", model_id: "mdl-1" },
    "key-abcdefghijklmnop",
  );
  assert.equal(result.error, "conflict");
  assert.equal(result.data, null);
});

test("createExperiment surfaces unknown_artifact for an unapproved id", async () => {
  const { fetch } = recordingFetch(() => json({ code: "unknown_artifact" }, 400));
  const result = await client(fetch).createExperiment(
    { template_id: "exp-9", dataset_id: "ds-1", model_id: "mdl-1" },
    "key-abcdefghijklmnop",
  );
  assert.equal(result.status, 400);
  assert.equal(result.error, "unknown_artifact");
});

test("cancelRun posts with no body", async () => {
  const { fetch, calls } = recordingFetch(() =>
    json({ ...RUN_VIEW, state: "ACTIVE", cancel_requested: true }),
  );
  const result = await client(fetch).cancelRun("run-1");
  assert.equal(result.ok, true);
  assert.equal(calls[0].init?.body, undefined);
  assert.equal(calls[0].init?.method, "POST");
  assert.equal(calls[0].url, "https://api.example.test/api/runs/run-1/cancel");
});

test("getModels returns the approved datasets and models", async () => {
  const { fetch } = recordingFetch(() =>
    json({ datasets: [{ id: "ds-1", label: "Public test" }], models: [] }),
  );
  const result = await client(fetch).getModels();
  assert.equal(result.data?.datasets[0].id, "ds-1");
});

test("conflict is surfaced as an error code, not a payload", async () => {
  const { fetch } = recordingFetch(() => json({ code: "conflict" }, 409));
  const result = await client(fetch).submitRun("exp-1", REQUEST, "key-abcdefghijklmnop");
  assert.equal(result.ok, false);
  assert.equal(result.status, 409);
  assert.equal(result.error, "conflict");
  assert.equal(result.data, null);
});

test("denied requests map to forbidden for 403 and unauthenticated for 401", async () => {
  const forbidden = await client(() => Promise.resolve(json({ code: "forbidden" }, 403))).getMe();
  assert.equal(forbidden.error, "forbidden");
  const unauthenticated = await client(() =>
    Promise.resolve(json({ code: "unauthenticated" }, 401)),
  ).getMe();
  assert.equal(unauthenticated.error, "unauthenticated");
});

test("network failure returns a category and never leaks the URL", async () => {
  const failing: FetchLike = async () => {
    throw new Error("connect ECONNREFUSED https://internal.example.test/?token=secret");
  };
  const result = await client(failing).getModels();
  assert.equal(result.ok, false);
  assert.equal(result.status, 0);
  assert.equal(result.error, "network_error");
  assert.equal(JSON.stringify(result).includes("secret"), false);
});

test("non-JSON error bodies still yield a category", async () => {
  const { fetch } = recordingFetch(() => new Response("<html>oops</html>", { status: 502 }));
  const result = await client(fetch).getRun("run-1");
  assert.equal(result.error, "api_error");
});
