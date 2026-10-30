"use server";

import { redirect } from "next/navigation";
import { apiClientFromRequest } from "../lib/server.ts";
import { isValidIdempotencyKey } from "../lib/idempotency.ts";
import type { ExperimentCreateRequest, RunRequest } from "../lib/types.ts";

function stringField(form: FormData, name: string): string {
  const value = form.get(name);
  return typeof value === "string" ? value.trim() : "";
}

function fail(path: string, code: string): never {
  redirect(`${path}?error=${encodeURIComponent(code)}`);
}

const ERROR_CODE_PATTERN = /^[a-z0-9_]{1,64}$/;

function sanitize(code: string | null | undefined, fallback: string): string {
  return code && ERROR_CODE_PATTERN.test(code) ? code : fallback;
}

/**
 * Create a durable experiment instance from an approved template.
 *
 * Two steps, each independently idempotent: the instance is created first (a
 * real persisted experiment, not a catalog echo), then the first run for that
 * instance is submitted. A failure between them leaves a created instance the
 * user can submit again; repeating the same keys never duplicates either.
 */
export async function createExperimentAction(formData: FormData): Promise<void> {
  const templateId = stringField(formData, "template_id");
  const datasetId = stringField(formData, "dataset_id");
  const modelId = stringField(formData, "model_id");
  const label = stringField(formData, "label");
  if (!templateId || !datasetId || !modelId) fail("/runs/new", "missing_fields");

  const createKey = stringField(formData, "idempotency_key");
  const submitKey = stringField(formData, "submit_idempotency_key");
  if (!isValidIdempotencyKey(createKey) || !isValidIdempotencyKey(submitKey)) {
    fail("/runs/new", "invalid_idempotency_key");
  }

  const api = await apiClientFromRequest();

  // Only the template id and the approved dataset/model ids are sent; policy
  // (mode, decoding, machine, region, pins) stays on the server-side template.
  const experiment: ExperimentCreateRequest = {
    template_id: templateId,
    dataset_id: datasetId,
    model_id: modelId,
  };
  if (label) experiment.label = label;

  const created = await api.createExperiment(experiment, createKey);
  if (!created.ok || !created.data) fail("/runs/new", sanitize(created.error, "create_failed"));

  // The created instance pins the dataset/model, so the submission echoes them.
  const request: RunRequest = { dataset_id: datasetId, model_id: modelId, decoding: {} };
  const run = await api.submitRun(created.data.experiment_id, request, submitKey);
  if (!run.ok || !run.data) fail("/runs/new", sanitize(run.error, "submit_failed"));
  redirect(`/runs/${encodeURIComponent(run.data.run_id)}`);
}

export async function cancelRunAction(formData: FormData): Promise<void> {
  const runId = stringField(formData, "run_id");
  if (!runId) fail("/", "missing_run_id");
  const api = await apiClientFromRequest();
  const result = await api.cancelRun(runId);
  if (!result.ok) fail(`/runs/${encodeURIComponent(runId)}`, sanitize(result.error, "cancel_failed"));
  redirect(`/runs/${encodeURIComponent(runId)}?notice=cancel_requested`);
}
