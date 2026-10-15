// Sandbox adapter (PRD 4.2): no backend. Forecasting (onnxruntime web) and optimization
// (highs js in a web worker) run in the browser on a frozen 90 day slice of real load,
// plus seeded synthetic days labelled synthetic. Results views read the live system's
// recorded responses. Agent responses are recorded traces keyed by scenario; a scenario
// without a recording gets the deterministic template summary, labelled as a template.
import type {
  BusinessCase,
  Checkpoint,
  DataAdapter,
  Meta,
  Operating,
  OperatingRow,
  RunDetail,
  Scenario,
  Sensitivity,
  Strategies,
  Verdicts,
} from "./types";
import type { BatterySpec, DemandTerm } from "../wasm/optimizer";

const BASE = import.meta.env.BASE_URL;
const SYNTHETIC_DAYS = 30;
const SEED = 20261015;

interface Slice {
  label: string;
  result_set: string;
  hours_utc: string[];
  load_kw: number[];
  slice_start_index: number;
  observed_peak_kw: number;
  model_version: string;
  battery_base_case: Record<string, number | boolean | object>;
  robust_charge_band_k: number;
  tariffs: Record<
    string,
    {
      price_usd_per_kwh: number[];
      protected: number[];
      local_month: string[];
      demand_charges: { name: string; in_window: number[]; rate: number[] }[];
    }
  >;
}

interface TraceIndexRow {
  scenario_id: string;
  title: string;
  split: string;
  operator_objective: string;
  operator_concerns: string;
  operator_confirms: boolean;
  current_settings: Record<string, string | number>;
  verdicts: Verdicts;
}

interface Trace {
  scenario_id: string;
  title: string;
  label: string;
  steps: string[];
  applied_settings: Record<string, string | number>;
  tests_run: string[];
  planning: unknown;
  risk: unknown;
  business: { decision: string; rationale: string };
  agents: { agent: string; prompt_version: string; status: string; used_fallback: boolean; latency_s: number }[];
}

const json = async <T>(path: string): Promise<T> => {
  const r = await fetch(`${BASE}data/${path}`);
  if (!r.ok) throw new Error(`${path}: ${r.status}`);
  return (await r.json()) as T;
};

/** Small seeded PRNG (mulberry32): the same synthetic days on every visit. */
function prng(seed: number) {
  let a = seed >>> 0;
  return () => {
    a = (a + 0x6d2b79f5) >>> 0;
    let t = a;
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

/** Real series plus SYNTHETIC_DAYS generated days: each copies the same weekday one week
 * earlier, scaled by a seeded factor (0.95 to 1.05) with seeded hourly noise (plus or minus
 * 3 percent). Tariff calendars repeat the week before. */
function extend(slice: Slice) {
  const rand = prng(SEED);
  const load = [...slice.load_kw];
  const hours = [...slice.hours_utc];
  const calIndex = hours.map((_, i) => i - slice.slice_start_index); // index into tariff arrays
  const lastReal = slice.load_kw.length;
  for (let d = 0; d < SYNTHETIC_DAYS; d++) {
    const scale = 0.95 + 0.1 * rand();
    for (let h = 0; h < 24; h++) {
      const i = load.length;
      load.push(load[i - 168] * scale * (1 + 0.06 * (rand() - 0.5)));
      const t = new Date(hours[i - 1].replace(" ", "T") + "Z").getTime() + 3600_000;
      hours.push(new Date(t).toISOString().slice(0, 19).replace("T", " "));
      calIndex.push(calIndex[i - 168]);
    }
  }
  return { load, hours, calIndex, lastReal };
}

export function createSandbox(): DataAdapter {
  let slice: Promise<Slice> | null = null;
  let ext: ReturnType<typeof extend> | null = null;
  let tools: Promise<{ forecaster: import("../wasm/forecaster").Forecaster; solver: import("../wasm/solver").Solver }> | null =
    null;
  const getSlice = async () => {
    slice ??= json<Slice>("sandbox/slice.json");
    const s = await slice;
    ext ??= extend(s);
    return { s, e: ext };
  };
  const getTools = () =>
    (tools ??= (async () => {
      const [{ Forecaster }, { Solver }] = await Promise.all([
        import("../wasm/forecaster"),
        import("../wasm/solver"),
      ]);
      return { forecaster: await Forecaster.load(BASE), solver: new Solver() };
    })());

  const runs = new Map<string, RunDetail>();
  const created: Scenario[] = [];
  let traceIndex: Promise<TraceIndexRow[]> | null = null;
  const index = () => (traceIndex ??= json<TraceIndexRow[]>("traces/index.json"));

  const meta = async (): Promise<Meta> => {
    const m = await json<Meta>("replay/meta.json");
    return {
      ...m,
      role: "sandbox",
      provenance: {
        ...m.provenance,
        mode: "sandbox",
        measured: [
          ...m.provenance.measured,
          "sandbox: 90 days of real load (2014-06-01 to 2014-08-29 UTC) for live forecasting and optimization",
        ],
        assumed: [...m.provenance.assumed, "sandbox: synthetic days (seeded generator), labelled synthetic"],
      },
    };
  };

  async function operating(q: { cell: string; tariff_id: string; strategy: string; day?: string; reserve?: number }): Promise<Operating> {
    const { s, e } = await getSlice();
    const days: string[] = [];
    for (let i = s.slice_start_index; i < e.load.length; i += 24) {
      days.push(i < e.lastReal ? e.hours[i].slice(0, 10) : `synthetic ${e.hours[i].slice(0, 10)}`);
    }
    const day = q.day && days.includes(q.day) ? q.day : days[0];
    const start = s.slice_start_index + days.indexOf(day) * 24;
    const synthetic = start >= e.lastReal;
    if (q.strategy === "fixed_schedule") throw new Error("The fixed schedule is not run in the sandbox; see Strategy comparison.");
    const { forecaster, solver } = await getTools();
    const fc = await forecaster.day(e.load, e.hours, start);
    const actual = e.load.slice(start, start + 24);
    const tariff = s.tariffs[q.tariff_id];
    const cal = Array.from({ length: 24 }, (_, h) => e.calIndex[start + h]);
    const [pf, dur] = q.cell.split("/").map(Number);
    const b = s.battery_base_case as Record<string, number>;
    const power = s.observed_peak_kw * pf;
    const energy = power * dur;
    const eta = Math.sqrt(b.round_trip_efficiency);
    const reserve = q.reserve ?? b.terminal_reserve_fraction;
    const spec: BatterySpec = {
      power_kw: power,
      energy_kwh: energy,
      eta_charge: eta,
      eta_discharge: eta,
      soc_min_kwh: energy * b.soc_min_fraction,
      soc_max_kwh: energy * b.soc_max_fraction,
      terminal_reserve_kwh: energy * reserve,
      degradation_usd_per_kwh: b.degradation_cost_usd_per_kwh_discharged,
    };
    const soc0 = energy * b.initial_soc_fraction;
    let planLoad: number[];
    let demandLoad: number[] | null = null;
    if (q.strategy === "robust_quantile") {
      planLoad = cal.map((c, h) => (tariff.protected[c] ? fc.p90[h] : fc.p50[h]));
      demandLoad = planLoad.map((v, h) => Math.max(v, fc.p50[h] + s.robust_charge_band_k * (fc.p90[h] - fc.p50[h])));
    } else if (q.strategy === "ml_forecast") planLoad = fc.point;
    else if (q.strategy === "seasonal_forecast") planLoad = e.load.slice(start - 168, start - 144);
    else planLoad = actual; // hindsight, and the no-battery reference
    // Demand terms: each charge, per local month in the day; running peak = highest
    // no-battery load earlier in the same month inside the charge window.
    const terms: DemandTerm[] = [];
    for (const ch of tariff.demand_charges) {
      const months = [...new Set(cal.map((c) => tariff.local_month[c]))];
      for (const m of months) {
        const mask = cal.map((c) => ch.in_window[c] === 1 && tariff.local_month[c] === m);
        if (!mask.some(Boolean)) continue;
        let peak = 0;
        for (let i = s.slice_start_index; i < start; i++) {
          const c = e.calIndex[i];
          if (tariff.local_month[c] === m && ch.in_window[c] === 1) peak = Math.max(peak, e.load[i]);
        }
        terms.push({ name: `${ch.name}|${m}`, mask, rate_usd_per_kw: ch.rate[cal[mask.indexOf(true)]], running_peak_kw: peak });
      }
    }
    const price = cal.map((c) => tariff.price_usd_per_kwh[c]);
    const noBattery = q.strategy === "no_battery";
    const plan = noBattery
      ? { charge_kw: Array(24).fill(0), discharge_kw: Array(24).fill(0), soc_kwh: Array(24).fill(soc0), grid_kw: actual, objective_usd: 0, status: "no battery" }
      : await solver.solve({
          load_kw: planLoad,
          price_usd_per_kwh: price,
          demand_terms: terms,
          spec,
          soc0_kwh: soc0,
          terminal_min_kwh: spec.terminal_reserve_kwh,
          demand_load_kw: demandLoad,
        });
    // Hourly settlement against actual load in the browser: discharge clipped to load,
    // state of charge recomputed (no 15 minute billing and no charge guard here).
    let soc = soc0;
    const rows: OperatingRow[] = [];
    for (let h = 0; h < 24; h++) {
      const d = Math.min(plan.discharge_kw[h], actual[h], Math.max(soc - spec.soc_min_kwh, 0) * eta);
      const c = d > 0 ? 0 : Math.min(plan.charge_kw[h], Math.max(spec.soc_max_kwh - soc, 0) / eta);
      soc = soc + eta * c - d / eta;
      rows.push({
        hour_start_utc: e.hours[start + h],
        actual: actual[h],
        point: fc.point[h],
        p10: fc.p10[h],
        p50: fc.p50[h],
        p90: fc.p90[h],
        planned_charge_kw: plan.charge_kw[h],
        planned_discharge_kw: plan.discharge_kw[h],
        charge_kw: c,
        discharge_kw: d,
        soc_kwh: soc,
        grid_kw: actual[h] - d + c,
        guard_clipped_kw: 0,
      });
    }
    const label = synthetic ? "synthetic day (seeded generator)" : s.label;
    return {
      cell: q.cell,
      tariff_id: q.tariff_id,
      strategy: q.strategy,
      day,
      days,
      rows,
      sources: {
        forecasts: `${label}; forecast computed in your browser (onnxruntime web, ${s.model_version})`,
        schedule: `${label}; schedule solved in your browser (highs js), day objective ${plan.objective_usd.toFixed(2)} USD (energy, demand above the month's running peak so far, wear); hourly settlement, no charge guard`,
      },
      label: synthetic ? "synthetic" : "sandbox",
      synthetic,
      reserve,
    };
  }

  function templateRun(sc: Scenario, objective: string, verdicts: Verdicts): RunDetail {
    const now = new Date().toISOString();
    const cp = (step: string, payload: Record<string, unknown>): Checkpoint => ({ step, payload, created_at: now });
    return {
      run: { run_id: `sandbox-${runs.size + 1}`, status: "planning_proposed", dataset_hash: "frozen slice", model_version: "recorded", prompt_versions: { planning: "template", risk: "template", business: "template" }, mlflow_trace_ids: [], created_at: now },
      scenario: sc,
      checkpoints: [
        cp("operator_request", { objective }),
        cp("planning_proposal", {
          planning: { interpretation: "Template: no recording for this scenario; the operator's settings stand.", changes: [], refused: [], claims: [] },
          agent: { agent: "planning", prompt_version: "template", status: "template", used_fallback: true, latency_s: 0, rejection_reasons: [] },
          verdicts,
        }),
      ],
      agent_calls: [],
      approvals: [],
    };
  }

  return {
    mode: "sandbox",
    meta,
    strategies: (cell) => json<Strategies>(`replay/strategies_${cell.replace("/", "_")}.json`),
    operating,
    sensitivity: () => json<Sensitivity>("replay/sensitivity.json"),
    businessCase: (cell) => json<BusinessCase>(`replay/business_${cell.replace("/", "_")}.json`),
    scenarios: async () => {
      const rows = await index();
      return [
        ...rows.map((r) => ({
          scenario_id: r.scenario_id,
          name: `${r.scenario_id} (recorded): ${r.title}`,
          settings: r.current_settings,
          created_at: "",
          objective: r.operator_objective,
        })),
        ...created,
      ];
    },
    createScenario: async (body) => {
      const sc: Scenario = {
        scenario_id: `custom-${created.length + 1}`,
        name: `${String(body.name)} (no recording: template)`,
        settings: body as Record<string, string | number>,
        created_at: new Date().toISOString(),
      };
      created.push(sc);
      return sc;
    },
    runs: async () => [...runs.values()].map((r) => r.run).reverse(),
    run: async (id) => {
      const r = runs.get(id);
      if (!r) throw new Error("unknown run");
      return r;
    },
    startRun: async (body) => {
      const rows = await index();
      const rec = rows.find((r) => r.scenario_id === body.scenario_id);
      const now = new Date().toISOString();
      let detail: RunDetail;
      if (rec) {
        const t = await json<Trace>(`traces/${rec.scenario_id}.json`);
        const agent = (name: string) => t.agents.find((a) => a.agent === name)!;
        detail = {
          run: { run_id: `sandbox-${runs.size + 1}`, status: "planning_proposed", dataset_hash: "scripted for evaluation", model_version: "recorded", prompt_versions: Object.fromEntries(t.agents.map((a) => [a.agent, a.prompt_version])), mlflow_trace_ids: [], created_at: now },
          scenario: { scenario_id: rec.scenario_id, name: rec.title, settings: rec.current_settings, created_at: "" },
          checkpoints: [
            { step: "operator_request", payload: { objective: rec.operator_objective, recorded_objective: true }, created_at: now },
            { step: "planning_proposal", payload: { planning: t.planning, agent: { ...agent("planning"), rejection_reasons: [] }, trace: t, verdicts: rec.verdicts }, created_at: now },
          ],
          agent_calls: t.agents.map((a) => ({ agent: a.agent, prompt_version: a.prompt_version, status: a.status, latency_ms: Math.round(a.latency_s * 1000), prompt_tokens: null, completion_tokens: null, mlflow_trace_id: "recorded (sanitized)", error_type: null })),
          approvals: [],
        };
      } else {
        const sc = created.find((c) => c.scenario_id === body.scenario_id);
        if (!sc) throw new Error("unknown scenario");
        const cell = `${sc.settings.power_fraction}/${sc.settings.duration_hours}`;
        const bc = await json<BusinessCase>(`replay/business_${cell.replace("/", "_")}.json`);
        detail = templateRun(sc, body.objective, bc.verdicts);
      }
      runs.set(detail.run.run_id, detail);
      return detail;
    },
    confirm: async (id) => {
      const r = runs.get(id)!;
      const now = new Date().toISOString();
      const plan = r.checkpoints.find((c) => c.step === "planning_proposal")!.payload as {
        trace?: Trace;
        verdicts: Verdicts;
      };
      const cp = (step: string, payload: Record<string, unknown>): Checkpoint => ({ step, payload, created_at: now });
      const ref = { source_table: "recorded results (live system)", label: "sandbox replay" };
      const steps = [cp("operator_confirmation", {}), cp("forecast", ref), cp("optimization", ref), cp("settlement_and_validation", ref)];
      if (plan.trace) {
        const t = plan.trace;
        const agent = (name: string) => ({ ...t.agents.find((a) => a.agent === name)!, rejection_reasons: [] });
        steps.push(cp("risk_challenge", { risk: t.risk, tests_run: t.tests_run, agent: agent("risk") }));
        steps.push(
          cp("business_recommendation", {
            business: t.business,
            agent: agent("business"),
            verdicts: plan.verdicts,
            rule_on_agent_evidence: { decision: plan.verdicts.a1_decision, reasons: [] },
            agrees_with_rule: t.business.decision === plan.verdicts.a1_decision,
            agrees_with_live_verdict: t.business.decision === plan.verdicts.a1_decision,
          }),
        );
      } else {
        const v = plan.verdicts;
        const tmpl = { agent: "business", prompt_version: "template", status: "template", used_fallback: true, latency_s: 0, rejection_reasons: [] };
        steps.push(cp("risk_challenge", { risk: { selection: { tests: ["forecast_error_injection", "heat_week_replay", "reserve_floor_raise"], reason: "Template: run every test." }, findings: [], unresolved_risks: [] }, tests_run: ["forecast_error_injection", "heat_week_replay", "reserve_floor_raise"], agent: { ...tmpl, agent: "risk" } }));
        steps.push(
          cp("business_recommendation", {
            business: { decision: v.a1_decision, rationale: `Template: ${v.display} ${v.a1_reasons}`, scope_tariffs: [], scope_strategies: [], claims: [] },
            agent: tmpl,
            verdicts: v,
            rule_on_agent_evidence: { decision: v.a1_decision, reasons: [] },
            agrees_with_rule: true,
            agrees_with_live_verdict: true,
          }),
        );
      }
      const updated = { ...r, run: { ...r.run, status: "recommended" }, checkpoints: [...r.checkpoints, ...steps] };
      runs.set(id, updated);
      return updated;
    },
    decide: async (id, decision, comment) => {
      const r = runs.get(id)!;
      const updated = {
        ...r,
        run: { ...r.run, status: "decided" },
        approvals: [...r.approvals, { decision, comment: comment ? `${comment} (kept in this browser only)` : "kept in this browser only", created_at: new Date().toISOString() }],
      };
      runs.set(id, updated);
      return updated;
    },
  };
}

export const sandbox: DataAdapter | null = null; // created lazily by the sandbox page
