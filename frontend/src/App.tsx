import { useEffect, useState } from "react";
import type { DataAdapter, Meta } from "./adapters/types";
import { ProvenanceBar } from "./components/ProvenanceBar";
import { ErrorNote } from "./components/ui";
import { AgentBrief } from "./views/AgentBrief";
import { BusinessCase } from "./views/BusinessCase";
import { OperatingWorkspace } from "./views/OperatingWorkspace";
import { StrategyComparison } from "./views/StrategyComparison";

const VIEWS = [
  ["operating", "Operating workspace"],
  ["strategies", "Strategy comparison"],
  ["brief", "Agent decision brief"],
  ["business", "Pilot business case"],
] as const;
type View = (typeof VIEWS)[number][0];

export function App({ api }: { api: DataAdapter }) {
  const [meta, setMeta] = useState<Meta>();
  const [err, setErr] = useState<unknown>();
  const [view, setView] = useState<View>("operating");
  const [cell, setCell] = useState("0.5/2");
  const [runId, setRunId] = useState<string>();
  useEffect(() => {
    api.meta().then((m) => {
      setMeta(m);
      setCell(m.base_cell);
    }, setErr);
  }, [api]);

  if (err) return <div className="p-6"><ErrorNote error={err} /></div>;
  if (!meta) return <p className="p-6 text-sm">Loading…</p>;
  return (
    <div>
      <header className="flex flex-wrap items-center justify-between gap-2 bg-slate-900 px-6 py-3 text-white">
        <h1 className="text-lg font-semibold">Energy Decision Intelligence Platform</h1>
        <nav className="flex gap-1" aria-label="Views">
          {VIEWS.map(([k, name]) => (
            <button key={k} data-testid={`nav-${k}`} aria-current={view === k ? "page" : undefined}
              className={`rounded px-3 py-1 text-sm ${view === k ? "bg-white text-slate-900" : "hover:bg-slate-700"}`}
              onClick={() => setView(k)}>
              {name}
            </button>
          ))}
        </nav>
      </header>
      <ProvenanceBar meta={meta} />
      <main className="mx-auto max-w-7xl p-6">
        <p className="mb-4 text-xs text-slate-500">
          Decision support only: the product never controls equipment, exports power, trades electricity, or makes payments.
        </p>
        {view === "operating" && (
          <OperatingWorkspace api={api} meta={meta} cell={cell} setCell={setCell} onRun={(id) => setRunId(id)} />
        )}
        {view === "strategies" && <StrategyComparison api={api} meta={meta} cell={cell} setCell={setCell} />}
        {view === "brief" && <AgentBrief api={api} runId={runId} setRunId={setRunId} />}
        {view === "business" && <BusinessCase api={api} meta={meta} cell={cell} setCell={setCell} />}
      </main>
    </div>
  );
}
