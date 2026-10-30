import Link from "next/link";
import { notFound } from "next/navigation";
import { cancelRunAction } from "../../actions.ts";
import { ConfigNotice, ErrorNotice, StateBadge } from "../../components.tsx";
import { apiClientFromRequest } from "../../../lib/server.ts";
import { scrubRun } from "../../../lib/compare.ts";
import { roleLimits } from "../../../lib/roles.ts";
import {
  attemptPhaseLabel,
  describeCancellation,
  formatBytes,
  shortHash,
} from "../../../lib/format.ts";

export const dynamic = "force-dynamic";

export default async function RunDetailPage({
  params,
  searchParams,
}: {
  params: Promise<{ id: string }>;
  searchParams: Promise<{ error?: string; notice?: string }>;
}) {
  const [{ id }, { error, notice }] = await Promise.all([params, searchParams]);

  let client;
  try {
    client = await apiClientFromRequest();
  } catch (reason) {
    return <ConfigNotice detail={reason instanceof Error ? reason.message : "unknown"} />;
  }

  const [me, run] = await Promise.all([client.getMe(), client.getRun(id)]);
  if (!me.ok || !me.data) return <ErrorNotice code={me.error ?? "api_error"} />;
  if (!run.ok || !run.data) {
    if (run.status === 404) notFound();
    return <ErrorNotice code={run.error ?? "api_error"} />;
  }

  const detail = scrubRun(run.data);
  const limits = roleLimits(me.data.role);
  const terminal = ["SUCCEEDED", "FAILED", "CANCELED"].includes(detail.state);

  return (
    <>
      <p className="muted">
        <Link href="/">← Runs</Link>
      </p>
      <h1>
        Run <code>{detail.run_id}</code>
      </h1>
      <ErrorNotice code={error} />
      {notice === "cancel_requested" ? (
        <p className="muted" role="status">
          Cancellation intent recorded; the terminal state is reconciled by the dispatcher.
        </p>
      ) : null}

      <p>
        <StateBadge state={detail.state} />{" "}
        <span className="muted">
          owner {detail.owner} · Batch phase {detail.batch_phase ?? "—"}
        </span>
      </p>
      <p className="muted">{describeCancellation(detail.state, detail.cancel_requested)}</p>

      {limits.canCancel && !detail.cancel_requested && !terminal ? (
        <form action={cancelRunAction}>
          <input type="hidden" name="run_id" value={detail.run_id} />
          <button type="submit">Request cancellation</button>
        </form>
      ) : null}

      <section>
        <h2>State</h2>
        <table>
          <tbody>
            <tr>
              <th>Run state</th>
              <td>
                {detail.state} ({attemptPhaseLabel(detail.state)})
              </td>
            </tr>
            <tr>
              <th>Observed Batch phase</th>
              <td>{detail.batch_phase ?? "—"}</td>
            </tr>
            <tr>
              <th>Cancellation intent</th>
              <td>{detail.cancel_requested ? "requested" : "none"}</td>
            </tr>
          </tbody>
        </table>
        <p className="muted">
          Cancellation intent is recorded separately from the terminal CANCELED state; a requested
          cancel with an ACTIVE state is not terminal.
        </p>
      </section>

      <section>
        <h2>Benchmark and configuration</h2>
        <p className="muted">
          Benchmark and configuration identity the API echoed for this run. The configuration is a
          digest of the pinned values, not the values themselves.
        </p>
        <table>
          <tbody>
            <tr>
              <th>Experiment</th>
              <td>
                <code>{detail.experiment_id ?? "—"}</code>
              </td>
            </tr>
            <tr>
              <th>Benchmark</th>
              <td>{detail.benchmark_id ?? "—"}</td>
            </tr>
            <tr>
              <th>Configuration</th>
              <td>
                <code>{detail.configuration_hash ?? "—"}</code>
              </td>
            </tr>
            <tr>
              <th>Dataset</th>
              <td>
                <code>{detail.dataset_id ?? "—"}</code>
              </td>
            </tr>
            <tr>
              <th>Model</th>
              <td>
                <code>{detail.model_id ?? "—"}</code>
              </td>
            </tr>
            <tr>
              <th>Mode</th>
              <td>{detail.mode ?? "—"}</td>
            </tr>
            <tr>
              <th>Owner</th>
              <td>{detail.owner}</td>
            </tr>
          </tbody>
        </table>
      </section>

      <section>
        <h2>Artifacts</h2>
        <p className="muted">
          Metadata only: name, pinned generation, checksum and size. Object contents remain private;
          there is no download endpoint.
        </p>
        {detail.artifacts.length === 0 ? (
          <p className="muted">The API returned no artifact metadata for this run.</p>
        ) : (
          <table>
            <thead>
              <tr>
                <th>Name</th>
                <th>Generation</th>
                <th>Checksum</th>
                <th>Size</th>
              </tr>
            </thead>
            <tbody>
              {detail.artifacts.map((artifact) => (
                <tr key={`${artifact.name}-${artifact.generation}`}>
                  <td>{artifact.name}</td>
                  <td>
                    <code>{artifact.generation}</code>
                  </td>
                  <td>
                    <code>{shortHash(artifact.checksum)}</code>
                  </td>
                  <td>{formatBytes(artifact.bytes)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </section>

      <section>
        <h2>Failure</h2>
        {detail.failure ? (
          <p>
            <strong>{detail.failure.code}</strong> — {detail.failure.summary}
          </p>
        ) : (
          <p className="muted">No redacted failure summary.</p>
        )}
      </section>

      <p>
        <Link href={`/compare?left=${encodeURIComponent(detail.run_id)}`}>
          Compare this run with another
        </Link>
      </p>
    </>
  );
}
