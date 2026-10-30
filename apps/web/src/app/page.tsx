import Link from "next/link";
import { ConfigNotice, ErrorNotice, RolePanel, RunLink, StateBadge } from "./components.tsx";
import { apiClientFromRequest } from "../lib/server.ts";
import { describeCancellation, isAppRole, isRunState, shortHash } from "../lib/format.ts";

export const dynamic = "force-dynamic";

export default async function RunsPage({
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

  const [me, runs] = await Promise.all([client.getMe(), client.listRuns()]);
  if (!me.ok || !me.data) return <ErrorNotice code={me.error ?? "api_error"} />;
  const identity = me.data;
  if (!isAppRole(identity.role)) return <ErrorNotice code="forbidden" />;

  return (
    <>
      <h1>Runs</h1>
      <ErrorNotice code={error} />
      <RolePanel role={identity.role} />
      <p className="muted">
        The API returns runs you own (owners see all runs). Each run echoes its benchmark id and a
        configuration digest, so runs are comparable on identity rather than status text.
      </p>

      {!runs.ok || !runs.data ? (
        <ErrorNotice code={runs.error ?? "api_error"} />
      ) : runs.data.length === 0 ? (
        <p className="muted">No runs yet. Start one from “New run”.</p>
      ) : (
        <table>
          <thead>
            <tr>
              <th>Run</th>
              <th>Benchmark</th>
              <th>Owner</th>
              <th>State</th>
              <th>Batch phase</th>
              <th>Cancellation</th>
              <th>Failure</th>
            </tr>
          </thead>
          <tbody>
            {runs.data.map((run) => (
              <tr key={run.run_id}>
                <td>
                  <RunLink runId={run.run_id} />
                </td>
                <td className="muted">{run.benchmark_id ?? "—"}</td>
                <td>{run.owner}</td>
                <td>{isRunState(run.state) ? <StateBadge state={run.state} /> : run.state}</td>
                <td className="muted">{run.batch_phase ?? "—"}</td>
                <td className="muted">{describeCancellation(run.state, run.cancel_requested)}</td>
                <td className="muted">
                  {run.failure ? (
                    <>
                      <strong>{run.failure.code}</strong> — {run.failure.summary}
                    </>
                  ) : (
                    "—"
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      <p>
        <Link href="/runs/new">Submit a run</Link> · <Link href="/compare">Compare runs</Link>
      </p>
    </>
  );
}
