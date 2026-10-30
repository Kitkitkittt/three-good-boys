// Display helpers. Pure functions so they run under `node --test` without a DOM.
import {
  APP_ROLES,
  RUN_STATES,
  TERMINAL_RUN_STATES,
  type AppRole,
  type RunMeta,
  type RunState,
} from "./types.ts";

export function isRunState(value: string): value is RunState {
  return (RUN_STATES as readonly string[]).includes(value);
}

export function isAppRole(value: string): value is AppRole {
  return (APP_ROLES as readonly string[]).includes(value);
}

export function isTerminal(state: RunState): boolean {
  return TERMINAL_RUN_STATES[state];
}

const STATE_BADGE: Record<RunState, string> = {
  QUEUED: "queued",
  SUBMITTING: "submitting",
  ACTIVE: "active",
  SUCCEEDED: "succeeded",
  FAILED: "failed",
  CANCELED: "canceled",
};

export function stateBadge(state: RunState): string {
  return STATE_BADGE[state];
}

/** Terminal states are labelled distinctly from in-flight ones. */
export function attemptPhaseLabel(state: RunState): string {
  return isTerminal(state) ? `terminal: ${state}` : state;
}

export function formatTimestamp(iso: string | null): string {
  if (!iso) return "—";
  const ms = Date.parse(iso);
  if (Number.isNaN(ms)) return "invalid date";
  return new Date(ms).toISOString().replace("T", " ").replace(".000Z", "Z");
}

export function formatBytes(bytes: number | null): string {
  if (bytes === null) return "unknown size";
  if (bytes < 1024) return `${bytes} B`;
  const units = ["KB", "MB", "GB", "TB"];
  let value = bytes / 1024;
  let unit = 0;
  while (value >= 1024 && unit < units.length - 1) {
    value /= 1024;
    unit += 1;
  }
  return `${value.toFixed(1)} ${units[unit]}`;
}

export function shortHash(hash: string, length = 12): string {
  return hash.length <= length ? hash : hash.slice(0, length);
}

/**
 * Cancellation intent is separate from the terminal CANCELED state: a run can
 * have cancel_requested set while still QUEUED/SUBMITTING/ACTIVE.
 */
export function describeCancellation(state: RunState, cancelRequested: boolean): string {
  if (!cancelRequested) return "no cancellation requested";
  if (state === "CANCELED") return "canceled";
  if (isTerminal(state)) return `cancel requested, but run already ${state}`;
  return `cancellation requested; not yet terminal (${state})`;
}

export function runTitle(run: Pick<RunMeta, "run_id" | "owner">): string {
  return run.owner ? `${run.run_id} · ${run.owner}` : run.run_id;
}
