import { useEffect, useState } from "react";
import type { DataAdapter, RunDetail } from "../adapters/types";
import { Badge, Card, DecisionPill, ErrorNote } from "../components/ui";
import { VerdictBanner } from "../components/VerdictBanner";
import { num } from "../lib/format";
import type { AgentOutcome, Claim, Comparison, Planning, Recommendation } from "./OperatingWorkspace";

function Claims({ claims }: { claims: Claim[] }) {
  return (
    <ul className="mt-1 grid gap-1 text-sm">
      {claims.map((c, i) => (
        <li key={i} data-testid="claim">
          {c.text}{" "}
          <span className="text-xs text-slate-500">
            [evidence: <code>{c.evidence_ref.table}</code> row <code>{c.evidence_ref.row_key}</code> column{" "}
            <code>{c.evidence_ref.column}</code>
            {c.value !== null ? ` = ${num(c.value, 2)}` : ""}]
          </span>
        </li>
      ))}
    </ul>
  );
}

function Comparisons({ items }: { items?: Comparison[] }) {
  if (!items || items.length === 0) return null;
  const ref = (r: Comparison["left"]) => `${r.row_key} ${r.column}`;
  return (
    <ul className="mt-1 grid gap-1 text-sm" data-testid="comparisons">
      {items.map((c, i) => (
        <li key={i}>
          {c.text}{" "}
          <span className="text-xs text-slate-500">
            [checked comparison: <code>{ref(c.left)}</code> {c.operator}{" "}
            <code>{c.right ? ref(c.right) : String(c.right_value)}</code>]
          </span>
        </li>
      ))}
    </ul>
  );
}

export function AgentBrief(props: { api: DataAdapter; runId?: string; setRunId: (id: string) => void }) {
  const [runs, setRuns] = useState<RunDetail["run"][]>([]);
  const [run, setRun] = useState<RunDetail>();
  const [err, setErr] = useState<unknown>();
  useEffect(() => {
    props.api.runs().then((r) => {
      setRuns(r);
      if (!props.runId && r.length) props.setRunId(r[0].run_id);
    }, setErr);
  }, [props.api]); // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => {
    if (props.runId) props.api.run(props.runId).then(setRun, setErr);
  }, [props.api, props.runId]);

  const step = (n: string) => run?.checkpoints.find((c) => c.step === n)?.payload;
  const plan = step("planning_proposal") as { planning: Planning; agent: AgentOutcome } | undefined;
  const risk = step("risk_challenge") as
    | { risk: { selection: { tests: string[]; reason: string }; findings: Claim[]; unresolved_risks: string[]; comparisons?: Comparison[] }; tests_run: string[]; agent: AgentOutcome }
    | undefined;
  const rec = step("business_recommendation") as Recommendation | undefined;

  return (
    <div className="grid gap-4">
      <label className="text-xs text-slate-600">
        Decision run
        <select className="ml-2 rounded border border-slate-300 px-2 py-1 text-sm" value={props.runId ?? ""}
          data-testid="run-select" onChange={(e) => props.setRunId(e.target.value)}>
          {runs.map((r) => (
            <option key={r.run_id} value={r.run_id}>
              {r.created_at.slice(0, 19)} {r.run_id} ({r.status})
            </option>
          ))}
        </select>
      </label>
      <ErrorNote error={err} />
      {runs.length === 0 && <p className="text-sm text-slate-600">No decision runs yet.</p>}
      {run && (
        <>
          <Card title="Planning interpretation" testId="brief-planning" source="edip.eval.cell_evidence (evidence rows) and Lakebase checkpoints">
            {plan ? (
              <>
                <p className="text-sm">
                  {plan.planning.interpretation} {plan.agent.used_fallback && <Badge kind="template" />}
                </p>
                <Claims claims={plan.planning.claims} />
                <Comparisons items={plan.planning.comparisons} />
              </>
            ) : (
              <p className="text-sm">Not reached.</p>
            )}
          </Card>
          <Card title="Risk findings" testId="brief-risk" source="edip.eval.cell_stress_results via edip.eval.cell_evidence">
            {risk ? (
              <>
                <p className="text-sm">
                  Stress tests chosen: <strong>{risk.tests_run.join(", ") || "none"}</strong>. {risk.risk.selection.reason}{" "}
                  {risk.agent.used_fallback && <Badge kind="template" />}
                </p>
                <Claims claims={risk.risk.findings} />
                <Comparisons items={risk.risk.comparisons} />
                {risk.risk.unresolved_risks.length > 0 && (
                  <ul className="mt-2 list-disc pl-5 text-sm text-rose-800">
                    {risk.risk.unresolved_risks.map((u) => (
                      <li key={u}>{u}</li>
                    ))}
                  </ul>
                )}
              </>
            ) : (
              <p className="text-sm">Not reached.</p>
            )}
          </Card>
          <Card title="Business recommendation" testId="brief-business" source="edip.eval.cell_verdicts and edip.eval.cell_evidence">
            {rec ? (
              <>
                <p className="text-sm">
                  <DecisionPill d={rec.business.decision} /> {rec.business.rationale}{" "}
                  {rec.agent.used_fallback && <Badge kind="template" />}
                </p>
                <Claims claims={rec.business.claims} />
                <Comparisons items={rec.business.comparisons} />
                <div className="mt-2">
                  <VerdictBanner v={rec.verdicts} />
                </div>
                <p className="mt-1 text-xs">
                  Agent agrees with the deterministic rule on the evidence it saw: {rec.agrees_with_rule ? "yes" : "no"};
                  with the live verdict for this battery: {rec.agrees_with_live_verdict ? "yes" : "no"}.
                </p>
              </>
            ) : (
              <p className="text-sm">Not reached.</p>
            )}
          </Card>
          <Card title="Agent call records (one call per agent)" testId="brief-calls" source="Lakebase edip.agent_calls">
            <table className="w-full text-sm">
              <thead className="text-xs text-slate-500">
                <tr><th className="text-left">Agent</th><th>Prompt</th><th>Status</th><th>Latency</th><th>Tokens in / out</th><th>MLflow trace</th></tr>
              </thead>
              <tbody>
                {run.agent_calls.map((c) => (
                  <tr key={c.agent} className="border-t border-slate-100 text-center">
                    <td className="text-left">{c.agent}</td>
                    <td>{c.prompt_version}</td>
                    <td>{c.status}</td>
                    <td>{num((c.latency_ms ?? 0) / 1000)} s</td>
                    <td>{c.prompt_tokens ?? "n/a"} / {c.completion_tokens ?? "n/a"}</td>
                    <td><code className="text-xs">{c.mlflow_trace_id ?? "none"}</code></td>
                  </tr>
                ))}
              </tbody>
            </table>
            <p className="mt-2 text-xs text-slate-500">
              Run provenance: dataset {run.run.dataset_hash.slice(0, 12)}…, model {run.run.model_version}, prompts{" "}
              {Object.values(run.run.prompt_versions).join(", ")}. Operator decisions:{" "}
              {run.approvals.map((a) => a.decision).join(", ") || "none yet"}.
            </p>
          </Card>
        </>
      )}
    </div>
  );
}
