// Comparison and selection helpers.
//
// The API's RunView now echoes sanitized identity: the approved benchmark id,
// the experiment/dataset/model ids, the mode and a configuration digest (never
// raw decoding, input object URIs or trace content). The comparison therefore
// keys on benchmark and configuration identity first, and reports each shared
// field difference explicitly instead of implying two runs used the same
// benchmark or configuration.
import type { RunDetail, RunMeta } from "./types.ts";

export interface ComparisonField {
  label: string;
  left: string;
  right: string;
  differs: boolean;
}

export interface Comparison {
  comparable: boolean;
  blockers: string[];
  fields: ComparisonField[];
  /** Plain-language statement of what comparability means here. */
  comparableWhen: string;
  /** Differences that are context, not identity, so they do not block. */
  notes: string[];
}

function render(value: unknown): string {
  if (value === null || value === undefined) return "—";
  return typeof value === "string" ? value : JSON.stringify(value);
}

/**
 * Compare two runs on the identity the API exposes. ``comparable`` means the
 * two runs name the same benchmark and pinned configuration; status and owner
 * are shown for context but never decide comparability.
 */
export function compareRuns(left: RunMeta, right: RunMeta): Comparison {
  const fields: ComparisonField[] = [
    field("Benchmark", left.benchmark_id, right.benchmark_id),
    field("Benchmark content", left.benchmark_hash, right.benchmark_hash),
    field("Benchmark cases", left.benchmark_cases, right.benchmark_cases),
    field("Configuration", left.configuration_hash, right.configuration_hash),
    field("Experiment", left.experiment_id, right.experiment_id),
    field("Dataset", left.dataset_id, right.dataset_id),
    field("Model", left.model_id, right.model_id),
    field("Mode", left.mode, right.mode),
    field("State", left.state, right.state),
    field("Batch phase", left.batch_phase ?? null, right.batch_phase ?? null),
    field("Cancel requested", left.cancel_requested, right.cancel_requested),
    field("Failure", left.failure?.code ?? null, right.failure?.code ?? null),
  ];
  const identity = ["benchmark", "benchmark content", "benchmark cases", "configuration",
                    "experiment", "dataset", "model", "mode"];
  const blockers = fields
    .filter((entry) => entry.differs && identity.includes(entry.label.toLowerCase()))
    .map((entry) => `${entry.label.toLowerCase()} differs`);
  const notes = fields
    .filter((entry) => entry.differs && !identity.includes(entry.label.toLowerCase()))
    .map((entry) => `${entry.label.toLowerCase()} differs`);
  return {
    comparable: blockers.length === 0,
    comparableWhen: "the two runs name the same benchmark and pinned configuration",
    blockers,
    notes,
    fields,
  };
}

function field(label: string, left: unknown, right: unknown): ComparisonField {
  const a = render(left);
  const b = render(right);
  return { label, left: a, right: b, differs: a !== b };
}

/**
 * Select two runs for comparison, keeping the first and rejecting a third. Any
 * two runs may be placed side by side; the view reports rather than forbids.
 */
export function selectForComparison(
  current: string[],
  candidate: string,
  byId: Readonly<Record<string, RunMeta>>,
): { selection: string[]; rejected: string | null } {
  if (!byId[candidate]) return { selection: current, rejected: candidate };
  if (current.includes(candidate)) {
    return { selection: current.filter((id) => id !== candidate), rejected: null };
  }
  if (current.length === 0) return { selection: [candidate], rejected: null };
  return { selection: [current[0], candidate], rejected: null };
}

/** Fields allowed to leave the server for a run view. */
const ALLOWED_RUN_FIELDS = [
  "run_id",
  "owner",
  "state",
  "cancel_requested",
  "batch_phase",
  "failure",
  "benchmark_id",
  "experiment_id",
  "dataset_id",
  "model_id",
  "mode",
  "configuration_hash",
  "benchmark_hash",
  "benchmark_cases",
] as const;

const RESTRICTED_FIELD = /audio|transcript|label|trace|prompt|gold|prediction|decoding|objects/i;

/**
 * Keep approved metadata and drop anything else before rendering. Defense in
 * depth: the API does not return restricted fields, and the UI must never show
 * them if a deviating server sends one.
 */
export function scrubRun(detail: RunDetail): RunDetail {
  const source = detail as unknown as Record<string, unknown>;
  const clean: Record<string, unknown> = {};
  for (const name of ALLOWED_RUN_FIELDS) {
    if (RESTRICTED_FIELD.test(name)) continue;
    clean[name] = source[name] ?? null;
  }
  clean.artifacts = Array.isArray(source.artifacts)
    ? source.artifacts.map((entry) => scrubArtifact(entry))
    : [];
  return clean as unknown as RunDetail;
}

function scrubArtifact(value: unknown): Record<string, unknown> {
  const result: Record<string, unknown> = {};
  if (!value || typeof value !== "object") return result;
  const source = value as Record<string, unknown>;
  for (const name of ["name", "generation", "checksum", "bytes"]) {
    if (RESTRICTED_FIELD.test(name)) continue;
    result[name] = source[name] ?? null;
  }
  return result;
}
