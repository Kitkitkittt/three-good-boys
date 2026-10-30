import { createExperimentAction } from "../../actions.ts";
import { ConfigNotice, ErrorNotice } from "../../components.tsx";
import { apiClientFromRequest } from "../../../lib/server.ts";
import { newIdempotencyKey } from "../../../lib/idempotency.ts";
import { roleLimits } from "../../../lib/roles.ts";
import { isAppRole } from "../../../lib/format.ts";

export const dynamic = "force-dynamic";

export default async function NewRunPage({
  searchParams,
}: {
  searchParams: Promise<{ error?: string }>;
}) {
  const { error } = await searchParams;

  let client;
  try {
    client = await apiClientFromRequest();
  } catch (reason) {
    return <ConfigNotice detail={reason instanceof Error ? reason.message : "unknown"} />;
  }

  const [me, models] = await Promise.all([client.getMe(), client.getModels()]);
  if (!me.ok || !me.data) return <ErrorNotice code={me.error ?? "api_error"} />;
  if (!isAppRole(me.data.role)) return <ErrorNotice code="forbidden" />;

  const limits = roleLimits(me.data.role);
  if (!limits.canSubmit) {
    return (
      <>
        <h1>New run</h1>
        <p className="error" role="alert">
          Role {limits.label} cannot submit runs. Ask an owner to change your role.
        </p>
      </>
    );
  }

  if (!models.ok || !models.data) return <ErrorNotice code={models.error ?? "api_error"} />;

  const templates = models.data.experiments ?? [];
  if (templates.length === 0) {
    return (
      <>
        <h1>New run</h1>
        <ErrorNotice code={error} />
        <p className="muted" role="status">
          No approved experiment templates are registered. An owner registers them in the API
          catalog; the dashboard cannot invent one.
        </p>
      </>
    );
  }

  // One key per create and one per submit; the API owns conflict semantics for
  // both, so a retry after a partial failure never duplicates anything.
  const createKey = newIdempotencyKey();
  const submitKey = newIdempotencyKey();

  return (
    <>
      <h1>New run</h1>
      <ErrorNotice code={error} />
      <p className="muted">
        A run starts from an approved template and an approved dataset and model. The template
        fixes the benchmark, mode, decoding, machine, region, timeout, retries and source/image
        pins; none of that is browser input. Submitting the same key and body again returns the
        same experiment instance and run; a different body conflicts.
      </p>
      <form action={createExperimentAction}>
        <input type="hidden" name="idempotency_key" value={createKey} />
        <input type="hidden" name="submit_idempotency_key" value={submitKey} />
        <label>
          Template
          <br />
          <select name="template_id" required>
            {templates.map((template) => (
              <option key={template.id} value={template.id}>
                {template.label} · {template.benchmark_id} ({template.cases} cases)
              </option>
            ))}
          </select>
        </label>
        <label>
          Dataset
          <br />
          <select name="dataset_id" required>
            {models.data.datasets.map((dataset) => (
              <option key={dataset.id} value={dataset.id}>
                {dataset.label}
              </option>
            ))}
          </select>
        </label>
        <label>
          Model
          <br />
          <select name="model_id" required>
            {models.data.models.map((model) => (
              <option key={model.id} value={model.id}>
                {model.label}
              </option>
            ))}
          </select>
        </label>
        <label>
          Label (optional)
          <br />
          <input name="label" maxLength={128} />
        </label>
        <p>
          <button type="submit">Create experiment and submit run</button>
        </p>
      </form>
    </>
  );
}
