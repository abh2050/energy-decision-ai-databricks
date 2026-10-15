import { useEffect, useState } from "react";
import type { BusinessCase as BC, DataAdapter, Meta, Row, Sensitivity } from "../adapters/types";
import { Badge, Card, ErrorNote, Select } from "../components/ui";
import { VerdictBanner } from "../components/VerdictBanner";
import { label, num, pct, usd } from "../lib/format";

const SPREADS = [1, 1.5, 2, 3];
const CELLS: [number, number][] = [[0.25, 2], [0.25, 4], [0.5, 2], [0.5, 4], [1, 2], [1, 4]];

function colour(v: number) {
  if (v > 0) return v > 20000 ? "bg-emerald-500 text-white" : "bg-emerald-200";
  return v < -20000 ? "bg-rose-500 text-white" : "bg-rose-200";
}

function SensitivityMap({ s, strategy }: { s: Sensitivity; strategy: string }) {
  const cells = s.base_cost_cells.filter((r) => r.strategy === strategy && r.tariff_id === "pge_b19_secondary");
  const at = (pf: number, d: number, m: number) =>
    cells.find((r) => r.power_fraction === pf && r.duration_hours === d && r.spread_multiplier === m);
  return (
    <table className="w-full text-center text-xs" data-testid="sensitivity-map">
      <thead>
        <tr>
          <th className="text-left">Battery (fraction of peak / hours)</th>
          {SPREADS.map((m) => (
            <th key={m}>Spread x{m}{m === 1 ? " (B-19)" : " (synthetic)"}</th>
          ))}
        </tr>
      </thead>
      <tbody>
        {CELLS.map(([pf, d]) => (
          <tr key={`${pf}/${d}`}>
            <td className="text-left">{pf * 100}% / {d} h</td>
            {SPREADS.map((m) => {
              const r = at(pf, d, m);
              const v = r?.net_benefit_usd as number | undefined;
              return (
                <td key={m} className={`border border-white p-1 ${v === undefined ? "" : colour(v)}`}>
                  {v === undefined ? "n/a" : usd(v)}
                </td>
              );
            })}
          </tr>
        ))}
      </tbody>
    </table>
  );
}

export function BusinessCase(props: { api: DataAdapter; meta: Meta; cell: string; setCell: (c: string) => void }) {
  const [bc, setBc] = useState<BC>();
  const [sens, setSens] = useState<Sensitivity>();
  const [strategy, setStrategy] = useState("robust_quantile");
  const [err, setErr] = useState<unknown>();
  useEffect(() => {
    props.api.businessCase(props.cell).then(setBc, setErr);
  }, [props.api, props.cell]);
  useEffect(() => {
    props.api.sensitivity().then(setSens, setErr);
  }, [props.api]);

  const flips = ((sens?.flip_boundary.flip_boundaries as Row[] | undefined) ?? []).filter(
    (f) => f.strategy === strategy && f.round_trip_efficiency === 0.9 && f.degradation_usd_per_kwh === 0.03 && f.demand_charge_multiplier === 1,
  );
  const base = bc?.battery.base_case ?? {};
  const capital = (bc?.capital.rows as Row[] | undefined)?.filter(
    (r) => r.cost_case === "mid" && r.strategy === strategy && r.tariff_id === "pge_b19_secondary",
  );

  return (
    <div className="grid gap-4">
      <Select label="Battery (power fraction / hours)" value={props.cell} options={props.meta.cells} onChange={props.setCell} testId="cell" />
      <ErrorNote error={err} />
      {bc && (
        <Card title={`Final recommendation for battery ${bc.cell}`} source={bc.sources.cell_verdicts} testId="final-recommendation">
          <VerdictBanner v={bc.verdicts} />
        </Card>
      )}
      {sens && (
        <Card title="Sensitivity map: net benefit against no battery, USD per year (base costs)" source={sens.source} testId="sensitivity">
          <div className="mb-2 flex items-end gap-3">
            <Select label="Strategy" value={strategy} options={["robust_quantile", "ml_forecast"]} onChange={setStrategy} render={label} />
            <p className="text-xs text-slate-500">
              <Badge kind="measured" /> load and replay; spreads above x1.0 are <Badge kind="synthetic" /> tariffs. Excludes
              battery capital cost.
            </p>
          </div>
          <SensitivityMap s={sens} strategy={strategy} />
          <h3 className="mt-3 text-sm font-semibold">Flip boundaries (smallest spread at which the strategy wins)</h3>
          <table className="w-full text-center text-xs" data-testid="flip-boundaries">
            <thead><tr><th className="text-left">Battery</th><th>Beats fixed schedule</th><th>Beats no battery</th></tr></thead>
            <tbody>
              {flips.map((f) => (
                <tr key={`${f.power_fraction}/${f.duration_hours}`}>
                  <td className="text-left">{Number(f.power_fraction) * 100}% / {Number(f.duration_hours)} h</td>
                  <td>{f.smallest_spread_beating_fixed === null ? "never (up to x3)" : `x${f.smallest_spread_beating_fixed}`}</td>
                  <td>{f.smallest_spread_beating_no_battery === null ? "never (up to x3)" : `x${f.smallest_spread_beating_no_battery}`}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </Card>
      )}
      {bc && (
        <>
          <Card title="Stress test results" source={bc.sources.cell_stress_results} testId="stress-table">
            <div className="overflow-x-auto">
              <table className="w-full text-right text-xs">
                <thead className="text-slate-500">
                  <tr>
                    <th className="text-left">Test</th><th className="text-left">Tariff</th><th className="text-left">Strategy</th>
                    <th>Unstressed</th><th>Stressed</th><th>Change</th><th>Retained</th><th>Worst month vs no battery</th><th>Result</th>
                  </tr>
                </thead>
                <tbody>
                  {bc.stress
                    .filter((r) => ["ml_forecast", "robust_quantile"].includes(String(r.strategy)))
                    .map((r, i) => (
                      <tr key={i} className="border-t border-slate-100">
                        <td className="text-left">{label(String(r.test))}</td>
                        <td className="text-left">{label(String(r.tariff_id))}</td>
                        <td className="text-left">{label(String(r.strategy))}</td>
                        <td>{usd(r.net_benefit_unstressed_usd)}</td>
                        <td>{usd(r.net_benefit_stressed_usd)}</td>
                        <td>{usd(r.absolute_change_usd)}</td>
                        <td data-testid="retained">{r.retained_pct === null ? String(r.retained_display) : pct(r.retained_pct)}</td>
                        <td>{pct(r.worst_month_vs_no_battery_pct)}</td>
                        <td>{r.passed ? "pass" : "fail"}</td>
                      </tr>
                    ))}
                </tbody>
              </table>
            </div>
            <p className="mt-2 text-xs text-slate-500">
              Limits (frozen): net benefit retained at least 50 percent; no month more than 1 percent above no battery;
              zero violations. When the unstressed net benefit is not positive the test is judged on the monthly limit and
              the dollar change. Test parameters are <Badge kind="assumed" />.
            </p>
          </Card>
          <Card title="Known limit: months billed above no battery" source={bc.sources.cell_excess_months} testId="known-limit">
            <p className="text-sm">
              Every such month exceeds through the all-hours maximum demand charge. The battery was charging under the
              guard's limit, and as built the guard carries the highest month-start peak forward instead of resetting to
              the previous month's billed demand. Strategies are unchanged; a maximum demand aware guard is future work.
            </p>
            <p className="mt-1 text-xs text-slate-600">
              Months above the limit for this battery (all cases): {bc.excess_months.length}.
            </p>
          </Card>
          <Card title="Assumptions" source="config/battery.yaml (published with the snapshot)" testId="assumptions">
            <ul className="grid gap-1 text-sm md:grid-cols-2">
              {Object.entries(base)
                .filter(([, v]) => typeof v !== "object")
                .map(([k, v]) => (
                  <li key={k}>
                    <Badge kind="assumed" /> {label(k)}: {String(v)}
                  </li>
                ))}
              <li>
                <Badge kind="assumed" /> operating cost: {usd((bc.battery.operating_cost as Row).annual_usd)} per year
              </li>
            </ul>
          </Card>
          {capital && capital.length > 0 && (
            <Card title="Capital layer (evidence, not a gate): mid ATB cost, B-19" source="docs/business_case_capital.json (NREL ATB 2025)" testId="capital">
              <p className="mb-2 text-xs text-slate-500">
                <Badge kind="assumed" /> installed cost, {String(bc.capital.life_years)} year life, discount rate{" "}
                {pct(Number(bc.capital.discount_rate) * 100)}.
              </p>
              <table className="w-full text-right text-xs">
                <thead className="text-slate-500"><tr><th className="text-left">Battery</th><th>Installed</th><th>Annual net benefit</th><th>Simple payback</th><th>NPV</th></tr></thead>
                <tbody>
                  {capital.map((r, i) => (
                    <tr key={i} className="border-t border-slate-100">
                      <td className="text-left">{num(r.power_kw, 0)} kW / {num(r.energy_kwh, 0)} kWh</td>
                      <td>{usd(r.installed_cost_usd)}</td>
                      <td>{usd(r.annual_net_benefit_usd)}</td>
                      <td>{r.simple_payback_years === null ? "never" : `${num(r.simple_payback_years)} years`}</td>
                      <td>{usd(r.npv_usd)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </Card>
          )}
        </>
      )}
    </div>
  );
}
