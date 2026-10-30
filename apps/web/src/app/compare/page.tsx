import Link from "next/link";
import { ConfigNotice, ErrorNotice, StateBadge } from "../components.tsx";
import { apiClientFromRequest } from "../../lib/server.ts";
import { compareRuns, selectForComparison } from "../../lib/compare.ts";
import { describeCancellation, shortHash } from "../../lib/format.ts";
import type { RunMeta } from "../../lib/types.ts";

export const dynamic = "force-dynamic";

export default async function ComparePage({
  searchParams,
}: {
  searchParams: Promise<{ left?: string; right?: string }>;
}) {
  const { left, right } = await searchParams;

  let client;
  try {
    client = await apiClientFromRequest();
  } catch (reason) {
    return <ConfigNotice detail={reason instanceof Error ? reason.message : "unknown"} />;
  }

  const runs = await client.listRuns();
  if (!runs.ok || !runs.data) return <ErrorNotice code={runs.error ?? "api_error"} />;

  const byId: Record<string, RunMeta> = {};
  for (const run of runs.data) byId[run.run_id] = run;

  // Apply the same selection rule the helper enforces, so the URL can never
  // leave a stale second selection behind.
  let selection: string[] = [];
  if (left) selection = selectForComparison(selection, left, byId).selection;
  if (right) selection = selectForComparison(selection, right, byId).selection;
  const [first, second] = selection;

  return (
    <>
      <h1>Compare runs</h1>
      <p className="muted">
        Select two runs. Comparability keys on benchmark and pinned configuration identity (the
        benchmark id and a configuration digest). State, owner and Batch phase are context. Raw
        decoding, input object locations and trace content are never returned by the API.
      </p>

      {runs.data.length < 2 ? (
        <p className="muted">At least two runs are needed.</p>
      ) : (
        <table>
          <thead>
            <tr>
              <th>Run</th>
              <th>Benchmark</th>
              <th>Configuration</th>
              <th>Owner</th>
              <th>State</th>
              <th>Select</th>
            </tr>
          </thead>
          <tbody>
            {runs.data.map((run) => {
              const selected = selection.includes(run.run_id);
              const href = selected
                ? `/compare?left=${encodeURIComponent(
                    selection.filter((id) => id !== run.run_id)[0] ?? "",
                  )}`
                : `/compare?left=${encodeURIComponent(first ?? run.run_id)}&right=${encodeURIComponent(
                    first ? run.run_id : "",
                  )}`;
              return (
                <tr key={run.run_id}>
                  <td>
                    <Link href={`/runs/${encodeURIComponent(run.run_id)}`}>{run.run_id}</Link>
                  </td>
                  <td className="muted">{run.benchmark_id ?? "—"}</td>
                  <td className="muted">
                    <code>{run.configuration_hash ? shortHash(run.configuration_hash) : "—"}</code>
                  </td>
                  <td>{run.owner}</td>
                  <td>
                    <StateBadge state={run.state} />
                  </td>
                  <td>
                    <Link href={href}>{selected ? "selected" : "select"}</Link>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      )}

      {first && second && byId[first] && byId[second] ? (
        <ComparisonView left={byId[first]} right={byId[second]} />
      ) : (
        <p className="muted">Pick a second run to see the field-by-field comparison.</p>
      )}
    </>
  );
}

function ComparisonView({ left, right }: { left: RunMeta; right: RunMeta }) {
  const comparison = compareRuns(left, right);
  return (
    <section>
      <h2>Comparison</h2>
      <p>
        <code>{left.run_id}</code> <StateBadge state={left.state} /> vs{" "}
        <code>{right.run_id}</code> <StateBadge state={right.state} />
      </p>
      <p className="muted">
        {left.run_id}: {describeCancellation(left.state, left.cancel_requested)} · {right.run_id}:{" "}
        {describeCancellation(right.state, right.cancel_requested)}
      </p>
      {comparison.comparable ? (
        <p role="status">Comparable: {comparison.comparableWhen}.</p>
      ) : (
        <div className="error" role="alert">
          <p>Identity differs, so these runs are not comparable:</p>
          <ul>
            {comparison.blockers.map((blocker) => (
              <li key={blocker}>{blocker}</li>
            ))}
          </ul>
        </div>
      )}
      {comparison.notes.length > 0 ? (
        <p className="muted">Context differences (not identity): {comparison.notes.join(", ")}.</p>
      ) : null}
      <table>
        <thead>
          <tr>
            <th>Field</th>
            <th>Left</th>
            <th>Right</th>
          </tr>
        </thead>
        <tbody>
          {comparison.fields.map((entry) => (
            <tr key={entry.label}>
              <td>
                {entry.label}
                {entry.differs ? <strong> *</strong> : null}
              </td>
              <td>
                <code>{entry.left}</code>
              </td>
              <td>
                <code>{entry.right}</code>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      <p className="muted">
        * marks a field that differs. Identity fields decide comparability; all fields shown are
        approved metadata, never decoding values or input locations.
      </p>
    </section>
  );
}
