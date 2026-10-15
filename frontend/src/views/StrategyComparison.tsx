import { useEffect, useState } from "react";
import type { DataAdapter, Meta, Strategies } from "../adapters/types";
import { Badge, Card, ErrorNote, Select } from "../components/ui";
import { label, num, usd } from "../lib/format";

export function StrategyComparison(props: { api: DataAdapter; meta: Meta; cell: string; setCell: (c: string) => void }) {
  const [data, setData] = useState<Strategies>();
  const [err, setErr] = useState<unknown>();
  useEffect(() => {
    props.api.strategies(props.cell).then(setData, setErr);
  }, [props.api, props.cell]);
  const tariffs = [...new Set(data?.rows.map((r) => r.tariff_id))];
  return (
    <div className="grid gap-4">
      <Select label="Battery (power fraction / hours)" value={props.cell} options={props.meta.cells} onChange={props.setCell} testId="cell" />
      <ErrorNote error={err} />
      {data &&
        tariffs.map((t) => (
          <Card key={t} title={`All six strategies, ${label(t)}, 2014`} source={data.source} testId="strategy-table">
            <p className="mb-2 text-xs text-slate-500">
              <Badge kind="measured" /> settled replay ({data.label}). Net benefit is against no battery, after
              degradation and, for ML and robust, the <Badge kind="assumed" /> operating cost. Units: USD per year
              before tax, kW, kWh.
            </p>
            <div className="overflow-x-auto">
              <table className="w-full text-right text-sm">
                <thead className="text-xs text-slate-500">
                  <tr>
                    <th className="text-left">Strategy</th>
                    <th>Bill</th>
                    <th>Net benefit</th>
                    <th>Billed peak (kW)</th>
                    <th>Throughput (kWh)</th>
                    <th>Degradation</th>
                    <th>Regret vs hindsight</th>
                    <th>Violations</th>
                    <th>Frozen target</th>
                  </tr>
                </thead>
                <tbody>
                  {data.rows
                    .filter((r) => r.tariff_id === t)
                    .map((r) => (
                      <tr key={r.strategy} className="border-t border-slate-100">
                        <td className="text-left">{label(r.strategy)}</td>
                        <td>{usd(r.bill_usd)}</td>
                        <td className={r.net_benefit_usd < 0 ? "text-rose-700" : "text-emerald-700"}>{usd(r.net_benefit_usd)}</td>
                        <td>{num(r.max_billing_demand_kw)}</td>
                        <td>{num(r.throughput_kwh, 0)}</td>
                        <td>{usd(r.degradation_usd)}</td>
                        <td>{usd(r.regret_vs_hindsight_usd)}</td>
                        <td data-testid="violations">{r.violations}</td>
                        <td>{r.passes_frozen_target === null ? "n/a" : r.passes_frozen_target ? "pass" : "fail"}</td>
                      </tr>
                    ))}
                </tbody>
              </table>
            </div>
          </Card>
        ))}
    </div>
  );
}
