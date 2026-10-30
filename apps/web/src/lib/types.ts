// View types for the private API (plan §4) as implemented by services/lifemate_api.
// Only approved metadata is modeled; restricted audio/transcript/label/trace
// content has no type here and no route returns it.

export const RUN_STATES = [
  "QUEUED",
  "SUBMITTING",
  "ACTIVE",
  "SUCCEEDED",
  "FAILED",
  "CANCELED",
] as const;

export type RunState = (typeof RUN_STATES)[number];

export const TERMINAL_RUN_STATES: Readonly<Record<RunState, boolean>> = {
  QUEUED: false,
  SUBMITTING: false,
  ACTIVE: false,
  SUCCEEDED: true,
  FAILED: true,
  CANCELED: true,
};

export const APP_ROLES = ["owner", "maintainer", "researcher", "viewer"] as const;

export type AppRole = (typeof APP_ROLES)[number];

export interface Me {
  role: AppRole;
}

export interface ApprovedArtifact {
  id: string;
  label: string;
}

/** `GET /api/models`: only owner-registered dataset and model ids/labels. */
export interface ModelsResponse {
  datasets: ApprovedArtifact[];
  models: ApprovedArtifact[];
  /** Absent on older API versions; treat a missing list as empty. */
  experiments?: ApprovedExperiment[];
}

/** `POST /api/experiments` body: an approved template plus concrete dataset/model. */
export interface ExperimentCreateRequest {
  template_id: string;
  dataset_id: string;
  model_id: string;
  label?: string;
}

/**
 * `GET /api/models` also lists approved experiment templates the dashboard may
 * instantiate. Only identity the server already approves is modelled.
 */
export interface ApprovedExperiment {
  id: string;
  label: string;
  benchmark_id: string;
  cases: number;
}

/** `POST /api/experiments` response: the durable instance the server created. */
export interface ExperimentInstance {
  experiment_id: string;
  template_id: string;
  label: string;
  benchmark_id: string;
  dataset_id: string;
  model_id: string;
  mode: string;
  created_by: string;
  created_at: string;
  configuration_hash: string;
}

/**
 * `POST /api/experiments/{id}/runs` body. Exactly the three client fields the API
 * accepts; system policy (mode, machine, timeout, region, source/image pins) is
 * deployment configuration and is never sent from the browser.
 */
export interface RunRequest {
  dataset_id: string;
  model_id: string;
  decoding: Record<string, string | number | boolean>;
}

export interface ArtifactMetadata {
  name: string;
  generation: string;
  checksum: string;
  bytes: number | null;
}

export interface RunFailure {
  code: string;
  summary: string;
}

/** The `RunView` the API returns for list, submit, get and cancel. */
export interface RunMeta {
  run_id: string;
  owner: string;
  state: RunState;
  cancel_requested: boolean;
  /** Observed Batch phase; kept distinct from the run state. */
  batch_phase: string | null;
  /** Already redacted by the API, or null. */
  failure: RunFailure | null;
  /** Sanitized benchmark identity the server echoed, or null when absent. */
  benchmark_id: string | null;
  /** Owner-registered benchmark content hash; distinguishes a revised benchmark. */
  benchmark_hash: string | null;
  benchmark_cases: number | null;
  /** The approved experiment instance or template this run was submitted with. */
  experiment_id: string | null;
  dataset_id: string | null;
  model_id: string | null;
  mode: string | null;
  /** Digest of the pinned configuration; never the configuration itself. */
  configuration_hash: string | null;
}

/** Extended run detail the dashboard renders when artifact metadata is fetched. */
export interface RunDetail extends RunMeta {
  artifacts: ArtifactMetadata[];
}

export interface RunsResponse {
  runs: RunMeta[];
}
