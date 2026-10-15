import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { createSandbox } from "../adapters/sandbox";
import { App } from "../App";
import type { DayProblem } from "../wasm/optimizer";
import "../styles.css";

export const BANNER =
  "Sandbox mode: model and optimizer run locally in your browser; agent responses are recorded from the live system.";

// Test hook for the browser parity test: solve a saved case in the same worker the UI uses.
declare global {
  interface Window {
    edipSolve?: (p: DayProblem) => Promise<{ objective_usd: number }>;
    edipForecastDay1?: () => Promise<Record<"point" | "p10" | "p50" | "p90", number[]>>;
  }
}
window.edipSolve = async (p) => {
  const { Solver } = await import("../wasm/solver");
  const solver = ((window as unknown as { __solver?: InstanceType<typeof Solver> }).__solver ??= new Solver());
  return solver.solve(p);
};

window.edipForecastDay1 = async () => {
  const { Forecaster } = await import("../wasm/forecaster");
  const base = import.meta.env.BASE_URL;
  const slice = await (await fetch(`${base}data/sandbox/slice.json`)).json();
  const f = await Forecaster.load(base);
  return f.day(slice.load_kw, slice.hours_utc, slice.slice_start_index);
};

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <div className="sticky top-0 z-50 bg-amber-300 px-6 py-2 text-center text-sm font-semibold text-amber-950" role="status" data-testid="sandbox-banner">
      {BANNER}
    </div>
    <App api={createSandbox()} />
  </StrictMode>,
);
