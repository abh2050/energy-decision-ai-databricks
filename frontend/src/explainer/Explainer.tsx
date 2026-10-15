// Public page two (PRD 4.3): system explainer. Every number is read from exported files
// of the live system (data/replay, data/explainer, data/traces); nothing is computed here.
import { useEffect, useState } from "react";
import type { BusinessCase, Sensitivity, Strategies } from "../adapters/types";
import { VerdictBanner } from "../components/VerdictBanner";
import { Badge, DecisionPill } from "../components/ui";
import { label, pct, usd } from "../lib/format";
import { SensitivityMap } from "../views/BusinessCase";

const BASE = import.meta.env.BASE_URL;
const get = async <T,>(p: string): Promise<T> => (await fetch(`${BASE}${p}`)).json() as Promise<T>;

const LAYERS = [
  {
    id: "data",
    title: "Source data",
    runs: "UCI ElectricityLoadDiagrams20112014 snapshot in a Unity Catalog volume; parsed, cleaned (daylight saving rows), and written to Delta as hourly and 15 minute load for client MT_189, with chronological train, validation, and test splits.",
    why: "A real load profile, stored once with its SHA256, so every later number traces back to the same bytes.",
  },
  {
    id: "forecast",
    title: "Forecasting",
    runs: "LightGBM point and P10, P50, P90 quantile models on lagged load and Lisbon calendar features; conformal corrections per forecast hour; MLflow registry (version 2 pinned); ONNX export.",
    why: "Quantiles give the robust strategy a P90 to plan peaks on; ONNX lets the public sandbox run the same model in the browser.",
  },
  {
    id: "optimize",
    title: "Dispatch and settlement",
    runs: "A daily mixed integer program (SciPy milp with HiGHS, deterministic settings) per strategy; settlement against actual 15 minute load with tariff demand intervals, a charge guard, and Facility Capacity history.",
    why: "Settling against actual load, not the plan, is what exposed day-ahead charging setting new demand peaks.",
  },
  {
    id: "replay",
    title: "Replay and sensitivity",
    runs: "The full 2014 test year for six strategies on two real tariffs and a synthetic spread family; 540 grid cells; stress tests; both decision verdicts. Databricks jobs and local processes, persisted to Delta.",
    why: "A pilot decision needs the whole year and the boundaries where the answer flips, not one good day.",
  },
  {
    id: "agents",
    title: "Agents",
    runs: "Three bounded agents on the Foundation Model API (Llama 3.3 70B): planning (typed scenario change with quotes), risk (chooses predefined stress tests), business (restates the deterministic verdict). One call each; every number and comparison is validated against evidence rows; template fallback.",
    why: "Agents explain and challenge; the deterministic rule decides. Hard constraints live in code, not prompts.",
  },
  {
    id: "app",
    title: "Live app",
    runs: "FastAPI and React on Databricks Apps behind OAuth; operator and viewer roles on the server; runs, checkpoints, approvals, and agent calls in Lakebase PostgreSQL; read-only evidence snapshots from Delta.",
    why: "The operator sees provenance and decides; every step of a decision run is persisted.",
  },
  {
    id: "public",
    title: "Public pages",
    runs: "GitHub Pages: this explainer and a sandbox that runs the ONNX forecaster (onnxruntime web) and the optimizer (highs js) in the browser, with agent traces recorded from the live system.",
    why: "The pages outlive the cloud resources, which are torn down after the export.",
  },
];

function Architecture() {
  const [sel, setSel] = useState("agents");
  const layer = LAYERS.find((l) => l.id === sel)!;
  return (
    <div className="grid gap-4 md:grid-cols-[1fr_1fr]">
      <svg viewBox="0 0 420 470" className="w-full" role="img" aria-label="Architecture diagram" data-testid="architecture">
        {LAYERS.map((l, i) => (
          <g key={l.id} transform={`translate(10, ${10 + i * 65})`} onClick={() => setSel(l.id)} className="cursor-pointer" data-testid={`layer-${l.id}`}>
            <rect width="400" height="52" rx="8" fill={sel === l.id ? "#0369a1" : "#e2e8f0"} />
            <text x="16" y="31" fontSize="16" fill={sel === l.id ? "#fff" : "#0f172a"} fontFamily="system-ui">
              {i + 1}. {l.title}
            </text>
            {i < LAYERS.length - 1 && <path d="M200 52 L200 65" stroke="#94a3b8" strokeWidth="2" />}
          </g>
        ))}
      </svg>
      <div className="rounded-lg border border-slate-200 p-4" data-testid="layer-detail">
        <h3 className="text-lg font-semibold">{layer.title}</h3>
        <p className="mt-2 text-sm">
          <strong>What runs here:</strong> {layer.runs}
        </p>
        <p className="mt-2 text-sm">
          <strong>Why:</strong> {layer.why}
        </p>
        <p className="mt-3 text-xs text-slate-500">Click a layer in the diagram.</p>
      </div>
    </div>
  );
}

interface Trace {
  scenario_id: string;
  title: string;
  operator_objective: string;
  applied_settings: Record<string, string | number>;
  tests_run: string[];
  planning: { interpretation: string; changes: { field: string; new_value: unknown; quote?: string }[] };
  risk: { selection: { tests: string[]; reason: string }; unresolved_risks: string[] };
  business: { decision: string; rationale: string };
  agents: { agent: string; prompt_version: string; status: string; latency_s: number }[];
}

function Walkthrough() {
  const [trace, setTrace] = useState<Trace>();
  const [step, setStep] = useState(0);
  const [playing, setPlaying] = useState(true);
  useEffect(() => {
    get<Trace>("data/traces/h02.json").then(setTrace);
  }, []);
  useEffect(() => {
    if (!playing) return;
    const id = setInterval(() => setStep((s) => (s + 1) % 9), 3500);
    return () => clearInterval(id);
  }, [playing]);
  if (!trace) return null;
  const agent = (n: string) => trace.agents.find((a) => a.agent === n)!;
  const steps: [string, string][] = [
    ["Operator request", `"${trace.operator_objective}"`],
    ["Planning proposal", `${trace.planning.interpretation} ${trace.planning.changes.map((c) => `Change ${c.field} to ${String(c.new_value)} (quote: "${c.quote ?? ""}").`).join(" ")} [${agent("planning").prompt_version}, ${agent("planning").status}]`],
    ["Operator confirmation", `The operator confirms; applied settings: ${Object.entries(trace.applied_settings).map(([k, v]) => `${k} ${v}`).join(", ")}.`],
    ["Forecast", "The pinned forecaster's day-ahead P10, P50, P90 for the battery cell's replay (persisted results, Delta)."],
    ["Optimization", "Daily mixed integer program per strategy (HiGHS), robust planning on P90 in peak hours."],
    ["Settlement and validation", "Against actual 15 minute load: billing demand, charge guard, zero constraint violations."],
    ["Risk challenge", `Tests chosen: ${trace.risk.selection.tests.join(", ")}. ${trace.risk.selection.reason} [${agent("risk").prompt_version}]`],
    ["Business recommendation", `${trace.business.decision}: ${trace.business.rationale} [${agent("business").prompt_version}, ${agent("business").status}]`],
    ["Operator decision", "Only the operator approves, revises, or rejects; the decision is persisted."],
  ];
  return (
    <div data-testid="walkthrough">
      <p className="mb-3 text-sm text-slate-600">
        Recorded run of held-out scenario {trace.scenario_id} ({trace.title}); scenario evidence is scripted for evaluation.
      </p>
      <ol className="grid gap-2">
        {steps.map(([name, text], i) => (
          <li
            key={name}
            onClick={() => {
              setStep(i);
              setPlaying(false);
            }}
            className={`cursor-pointer rounded-lg border p-3 transition-all duration-500 ${i === step ? "scale-[1.01] border-sky-600 bg-sky-50 shadow" : i < step ? "border-slate-200 opacity-80" : "border-slate-100 opacity-50"}`}
            data-testid={`step-${i}`}
          >
            <strong>
              {i + 1}. {name}
            </strong>
            {i === step && <p className="mt-1 text-sm">{text}</p>}
          </li>
        ))}
      </ol>
      <button className="btn mt-3" onClick={() => setPlaying((p) => !p)} data-testid="play">
        {playing ? "Pause" : "Play"}
      </button>
    </div>
  );
}

interface Excerpts {
  label: string;
  spans: { trace_id: string; span: string; duration_ms: number; attributes: Record<string, unknown> }[];
}
interface Evaluation {
  label: string;
  splits: Record<string, Record<string, Record<string, number | null>> & { targets?: unknown }>;
}

export function Explainer() {
  const [bc, setBc] = useState<BusinessCase>();
  const [st, setSt] = useState<Strategies>();
  const [sens, setSens] = useState<Sensitivity>();
  const [ex, setEx] = useState<Excerpts>();
  const [ev, setEv] = useState<Evaluation>();
  useEffect(() => {
    get<BusinessCase>("data/replay/business_0.5_2.json").then(setBc);
    get<Strategies>("data/replay/strategies_0.5_2.json").then(setSt);
    get<Sensitivity>("data/replay/sensitivity.json").then(setSens);
    get<Excerpts>("data/explainer/trace_excerpts.json").then(setEx);
    get<Evaluation>("data/explainer/evaluation.json").then(setEv);
  }, []);
  const Section = (p: { id: string; title: string; children: React.ReactNode }) => (
    <section id={p.id} className="border-t border-slate-200 py-10" data-testid={`section-${p.id}`}>
      <h2 className="mb-4 text-2xl font-semibold">{p.title}</h2>
      {p.children}
    </section>
  );
  const metric = (sp: string, path: string, k: string) => {
    const v = ev?.splits[sp]?.[path]?.[k];
    return typeof v === "number" ? (k.includes("cost") ? `${v.toFixed(4)} USD` : pct(v)) : "n/a";
  };
  return (
    <main className="mx-auto max-w-5xl px-4 pb-16">
      <header className="py-10">
        <h1 className="text-3xl font-bold">Energy Decision Intelligence Platform</h1>
        <p className="mt-2 text-lg text-slate-700">
          Should a facility run a forecast-driven battery schedule? A decision-support system on Databricks that compares six
          scheduling strategies on real load, with three bounded AI agents and the operator in charge.
        </p>
        <p className="mt-2 text-sm">
          <a className="text-sky-700 underline" href={`${BASE}sandbox/`}>
            Open the working sandbox
          </a>{" "}
          (the forecaster and optimizer run in your browser).
        </p>
      </header>

      <section data-testid="section-video">
        <video controls preload="metadata" className="w-full rounded-lg border border-slate-200" src={`${BASE}media/demo.webm`} data-testid="video" />
        <p className="mt-2 text-xs text-slate-500">
          Three minute captioned screen recording of the live app on Databricks Apps (recorded 2026-10-15, before teardown).
        </p>
      </section>

      <Section id="recommendation" title="Recommendation">
        <p className="text-lg font-semibold" data-testid="recommendation-text">
          Do not buy a battery for this load profile. If a battery already exists, run robust dispatch and fix the maximum
          demand guard before a pilot.
        </p>
        {bc && (
          <div className="mt-3">
            <VerdictBanner v={bc.verdicts} />
          </div>
        )}
        <p className="mt-2 text-sm text-slate-600">
          Base battery (50 percent of peak, 2 hours) on PG&amp;E B-19, revised strategy with the corrected charge guard. The
          frozen strategy settings were tuned under a guard defect that has since been corrected; they were not retuned.
        </p>
      </Section>

      <Section id="architecture" title="Architecture">
        <Architecture />
      </Section>

      <Section id="walkthrough" title="One decision run, step by step">
        <Walkthrough />
      </Section>

      <Section id="screenshots" title="The live app">
        <div className="grid gap-4 md:grid-cols-2" data-testid="screenshots">
          {["operating_workspace", "strategy_comparison", "agent_decision_brief", "pilot_business_case", "decision_run"].map((s) => (
            <figure key={s}>
              <img src={`${BASE}media/screens/${s}.png`} alt={label(s)} className="rounded border border-slate-200" loading="lazy" />
              <figcaption className="mt-1 text-xs text-slate-500">{label(s)}</figcaption>
            </figure>
          ))}
        </div>
      </Section>

      <Section id="traces" title="MLflow trace excerpts">
        {ex && (
          <>
            <p className="mb-2 text-xs text-slate-500">{ex.label}</p>
            <div className="overflow-x-auto">
              <table className="w-full text-xs" data-testid="trace-table">
                <thead className="text-slate-500">
                  <tr><th className="text-left">Span</th><th>Prompt</th><th>Status</th><th>Duration</th><th className="text-left">Validator</th></tr>
                </thead>
                <tbody>
                  {ex.spans.map((s, i) => (
                    <tr key={i} className="border-t border-slate-100 align-top">
                      <td className="py-1">{s.span}</td>
                      <td className="text-center">{String(s.attributes.prompt_version ?? "")}</td>
                      <td className="text-center">{String(s.attributes.status ?? "")}</td>
                      <td className="text-center">{(s.duration_ms / 1000).toFixed(1)} s</td>
                      <td>{Array.isArray(s.attributes.rejection_reasons) ? (s.attributes.rejection_reasons as string[]).join("; ").slice(0, 200) : ""}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </>
        )}
      </Section>

      <Section id="results" title="Results">
        {st && (
          <>
            <h3 className="mb-2 font-semibold">2014 replay, base battery, PG&amp;E B-19 (USD per year, before tax)</h3>
            <table className="w-full text-right text-sm" data-testid="results-table">
              <thead className="text-xs text-slate-500">
                <tr><th className="text-left">Strategy</th><th>Bill</th><th>Net benefit vs no battery</th><th>Billed peak (kW)</th><th>Violations</th></tr>
              </thead>
              <tbody>
                {st.rows.filter((r) => r.tariff_id === "pge_b19_secondary").map((r) => (
                  <tr key={r.strategy} className="border-t border-slate-100">
                    <td className="text-left">{label(r.strategy)}</td>
                    <td>{usd(r.bill_usd)}</td>
                    <td className={r.net_benefit_usd < 0 ? "text-rose-700" : "text-emerald-700"}>{usd(r.net_benefit_usd)}</td>
                    <td>{r.max_billing_demand_kw.toFixed(1)}</td>
                    <td>{r.violations}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            <p className="mt-1 text-xs text-slate-500">
              <Badge kind="measured" /> {st.label}; source {st.source.source} (Delta version {st.source.delta_version}).
            </p>
          </>
        )}
        {sens && (
          <div className="mt-8">
            <h3 className="mb-2 font-semibold">Sensitivity map: robust dispatch, net benefit against no battery</h3>
            <SensitivityMap s={sens} strategy="robust_quantile" />
            <p className="mt-1 text-xs text-slate-500">
              Spreads above x1.0 are <Badge kind="synthetic" /> tariffs. Excludes battery capital cost; at the mid NREL ATB cost no
              size pays back within 15 years.
            </p>
          </div>
        )}
        {ev && (
          <div className="mt-8">
            <h3 className="mb-2 font-semibold">Agent evaluation (final configuration)</h3>
            <table className="w-full text-right text-sm" data-testid="evaluation-table">
              <thead className="text-xs text-slate-500">
                <tr><th className="text-left">Metric (agent-assisted)</th><th>Development, 30 (optimistic)</th><th>Held-out, 10</th></tr>
              </thead>
              <tbody>
                {[
                  ["Recommendation accuracy", "recommendation_accuracy_pct"],
                  ["Supported claims (original definition)", "supported_claim_rate_pct"],
                  ["Supported claims (stricter definition)", "supported_claim_rate_strict_pct"],
                  ["Format compliance", "format_compliance_pct"],
                  ["Citation accuracy", "citation_accuracy_pct"],
                  ["Stress test selection", "stress_test_selection_accuracy_pct"],
                  ["Prohibited actions refused by the agent", "prohibited_action_refusals_by_agent_pct"],
                  ["Cost per run", "cost_usd_per_run"],
                ].map(([name, k]) => (
                  <tr key={k} className="border-t border-slate-100">
                    <td className="text-left">{name}</td>
                    <td>{metric("development", "agent_assisted", k)}</td>
                    <td>{metric("held_out", "agent_assisted", k)}</td>
                  </tr>
                ))}
                <tr className="border-t border-slate-100">
                  <td className="text-left">Numbers-only baseline accuracy</td>
                  <td>{metric("development", "numbers_only", "recommendation_accuracy_pct")}</td>
                  <td>{metric("held_out", "numbers_only", "recommendation_accuracy_pct")}</td>
                </tr>
              </tbody>
            </table>
            <p className="mt-1 text-xs text-slate-500">{ev.label}. Not every frozen agent target is met; see the Gate 6 review report.</p>
          </div>
        )}
        {bc && (
          <div className="mt-8" data-testid="final-recommendation">
            <h3 className="mb-2 font-semibold">Final recommendation by the rule</h3>
            <p className="text-sm">
              Base battery: <DecisionPill d={bc.verdicts.a1_decision} /> ({bc.verdicts.a1_reasons}).
            </p>
          </div>
        )}
      </Section>
    </main>
  );
}
