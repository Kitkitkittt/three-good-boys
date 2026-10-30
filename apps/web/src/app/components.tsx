import Link from "next/link";
import { stateBadge } from "../lib/format.ts";
import type { AppRole, RunState } from "../lib/types.ts";
import { roleLimits } from "../lib/roles.ts";

export function StateBadge({ state }: { state: RunState }) {
  return <span className={`badge ${stateBadge(state)}`}>{state}</span>;
}

const ERROR_TEXT: Record<string, string> = {
  unauthenticated: "No signed-in identity was presented.",
  forbidden: "Your account is not authorized for this action.",
  not_found: "That run does not exist or is not visible to you.",
  conflict: "The idempotency key was already used for a different request.",
  unknown_artifact: "An experiment, dataset or model id is not approved.",
  bad_request: "The API rejected the request shape.",
  network_error: "The private API was unreachable.",
  api_error: "The private API returned an error.",
  missing_fields: "Fill in the template, dataset and model.",
  invalid_idempotency_key: "The submission key was malformed. Reload and try again.",
  submit_failed: "The run was not accepted.",
  cancel_failed: "The cancellation request was not accepted.",
  create_failed: "The experiment was not created.",
};

export function ErrorNotice({ code }: { code?: string }) {
  if (!code) return null;
  const text = ERROR_TEXT[code] ?? "Request failed.";
  return (
    <p className="error" role="alert">
      {text} <span className="muted">({code})</span>
    </p>
  );
}

export function ConfigNotice({ detail }: { detail: string }) {
  return (
    <p className="error" role="alert">
      Web tier is not configured: {detail}. Set <code>LIFEMATE_API_URL</code> and{" "}
      <code>LIFEMATE_API_ID_TOKEN</code> on the server.
    </p>
  );
}

export function RolePanel({ role }: { role: AppRole }) {
  const limits = roleLimits(role);
  return (
    <section>
      <h2>Your role</h2>
      <p>
        <strong>{limits.label}</strong>
      </p>
      <ul>
        <li>Submit runs: {limits.canSubmit ? "yes" : "no"}</li>
        <li>Cancel runs: {limits.canCancel ? "yes" : "no"}</li>
        <li>Manage artifacts: {limits.canManageArtifacts ? "yes" : "no"}</li>
        <li>Approve artifacts: {limits.canApprove ? "yes" : "no"}</li>
        <li>Set cost policy: {limits.canSetCostPolicy ? "yes" : "no"}</li>
      </ul>
    </section>
  );
}

export function RunLink({ runId }: { runId: string }) {
  return <Link href={`/runs/${encodeURIComponent(runId)}`}>{runId}</Link>;
}
