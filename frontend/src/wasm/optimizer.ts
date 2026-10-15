// Browser port of src/edip/core/optimizer.py (FR14, FR15, FR17): the same daily mixed
// integer program, written in CPLEX LP format and solved by highs-js (HiGHS compiled to
// WebAssembly). Variables, constraints, tie-break, and the reported objective (energy plus
// demand increase above the running peak plus degradation) match the Python model; the
// parity test compares 20 saved cases within 0.5 percent of cost.

export const T = 24;
export const TIE_BREAK_USD_PER_KWH = 1e-7;

export interface BatterySpec {
  power_kw: number;
  energy_kwh: number;
  eta_charge: number;
  eta_discharge: number;
  soc_min_kwh: number;
  soc_max_kwh: number;
  initial_soc_kwh?: number;
  terminal_reserve_kwh: number;
  degradation_usd_per_kwh: number;
}

export interface DemandTerm {
  name: string;
  mask: boolean[];
  rate_usd_per_kw: number;
  running_peak_kw: number;
}

export interface DayProblem {
  load_kw: number[];
  price_usd_per_kwh: number[];
  demand_terms: DemandTerm[];
  spec: BatterySpec;
  soc0_kwh: number;
  terminal_min_kwh: number | null;
  demand_load_kw?: number[] | null;
}

export interface Plan {
  charge_kw: number[];
  discharge_kw: number[];
  soc_kwh: number[];
  grid_kw: number[];
  objective_usd: number;
  status: string;
}

interface HighsSolution {
  Status: string;
  ObjectiveValue: number;
  Columns: Record<string, { Primal: number }>;
}

export interface Highs {
  solve(lp: string, options?: Record<string, number | string | boolean>): HighsSolution;
}

const num = (x: number) => (Number.isFinite(x) ? x.toPrecision(15) : "0");

function expr(terms: [number, string][]): string {
  let out = "";
  for (const [coef, v] of terms) {
    if (coef === 0) continue;
    const sign = coef < 0 ? "-" : "+";
    out += ` ${sign} ${num(Math.abs(coef))} ${v}`;
  }
  return out.trim().replace(/^\+ /, "") || "0 c0";
}

export function buildLp(p: DayProblem): string {
  const s = p.spec;
  const load = p.load_kw.map((x) => Math.max(x, 0));
  if (load.length !== T || p.price_usd_per_kwh.length !== T) throw new Error("need 24 hourly values");
  const c = (t: number) => `c${t}`;
  const d = (t: number) => `d${t}`;
  const so = (t: number) => `s${t}`;
  const g = (t: number) => `g${t}`;
  const b = (t: number) => `b${t}`;
  const m = (k: number) => `m${k}`;

  const obj: [number, string][] = [];
  for (let t = 0; t < T; t++) {
    obj.push([p.price_usd_per_kwh[t], g(t)]);
    obj.push([s.degradation_usd_per_kwh + TIE_BREAK_USD_PER_KWH, d(t)]);
    obj.push([TIE_BREAK_USD_PER_KWH, c(t)]);
  }
  p.demand_terms.forEach((term, k) => obj.push([term.rate_usd_per_kw, m(k)]));

  const rows: string[] = [];
  for (let t = 0; t < T; t++) {
    rows.push(`bal${t}: ${expr([[1, g(t)], [1, d(t)], [-1, c(t)]])} = ${num(load[t])}`);
    rows.push(`cm${t}: ${expr([[1, c(t)], [-s.power_kw, b(t)]])} <= 0`);
    rows.push(`dm${t}: ${expr([[1, d(t)], [s.power_kw, b(t)]])} <= ${num(s.power_kw)}`);
    const socTerms: [number, string][] = [[1, so(t)], [-s.eta_charge, c(t)], [1 / s.eta_discharge, d(t)]];
    if (t) socTerms.push([-1, so(t - 1)]);
    rows.push(`soc${t}: ${expr(socTerms)} = ${num(t === 0 ? p.soc0_kwh : 0)}`);
    rows.push(`ex${t}: ${expr([[1, d(t)], [-1, c(t)]])} <= ${num(load[t])}`);
  }
  p.demand_terms.forEach((term, k) => {
    term.mask.forEach((on, t) => {
      if (!on) return;
      if (p.demand_load_kw) {
        rows.push(`pk${k}_${t}: ${expr([[1, m(k)], [-1, c(t)], [1, d(t)]])} >= ${num(p.demand_load_kw[t])}`);
      } else {
        rows.push(`pk${k}_${t}: ${expr([[1, m(k)], [-1, g(t)]])} >= 0`);
      }
    });
  });

  const bounds: string[] = [];
  for (let t = 0; t < T; t++) {
    bounds.push(`0 <= ${c(t)} <= ${num(s.power_kw)}`);
    bounds.push(`0 <= ${d(t)} <= ${num(s.power_kw)}`);
    let lo = s.soc_min_kwh;
    if (t === T - 1 && p.terminal_min_kwh !== null) {
      const reachable = Math.min(s.soc_max_kwh, p.soc0_kwh + T * s.power_kw * s.eta_charge);
      lo = Math.max(s.soc_min_kwh, Math.min(p.terminal_min_kwh, reachable));
    }
    bounds.push(`${num(lo)} <= ${so(t)} <= ${num(s.soc_max_kwh)}`);
    bounds.push(`${g(t)} >= 0`);
  }
  p.demand_terms.forEach((term, k) => bounds.push(`${m(k)} >= ${num(term.running_peak_kw)}`));

  const binaries = Array.from({ length: T }, (_, t) => b(t)).join(" ");
  return [
    "Minimize",
    ` obj: ${expr(obj)}`,
    "Subject To",
    ...rows.map((r) => ` ${r}`),
    "Bounds",
    ...bounds.map((r) => ` ${r}`),
    "Binary",
    ` ${binaries}`,
    "End",
  ].join("\n");
}

export const HIGHS_OPTIONS = { mip_rel_gap: 1e-6, random_seed: 0 };

export function solveDay(highs: Highs, p: DayProblem): Plan {
  const sol = highs.solve(buildLp(p), HIGHS_OPTIONS);
  if (sol.Status !== "Optimal") throw new Error(`no optimal plan: ${sol.Status}`);
  const col = (v: string) => sol.Columns[v]?.Primal ?? 0;
  const pick = (f: (t: number) => string) => Array.from({ length: T }, (_, t) => col(f(t)));
  const charge = pick((t) => `c${t}`).map((x) => (x < 1e-7 ? 0 : x));
  const discharge = pick((t) => `d${t}`).map((x) => (x < 1e-7 ? 0 : x));
  const offset = p.demand_terms.reduce((a, t) => a + t.rate_usd_per_kw * t.running_peak_kw, 0);
  const tie =
    TIE_BREAK_USD_PER_KWH *
    (pick((t) => `c${t}`).reduce((a, x) => a + x, 0) + pick((t) => `d${t}`).reduce((a, x) => a + x, 0));
  return {
    charge_kw: charge,
    discharge_kw: discharge,
    soc_kwh: pick((t) => `s${t}`),
    grid_kw: pick((t) => `g${t}`),
    objective_usd: sol.ObjectiveValue - offset - tie,
    status: sol.Status,
  };
}
