import type { Verdicts } from "../adapters/types";
import { DecisionPill } from "./ui";

export const A1_URL =
  "https://github.com/abh2050/energy-decision-ai-databricks/blob/main/docs/business_case.md#amendment-a1-2026-10-15-owner-decision";

// Both deterministic verdicts, always side by side (owner decision 2026-10-15).
export function VerdictBanner({ v }: { v: Verdicts }) {
  return (
    <div className="rounded-lg border border-slate-300 bg-white p-3" data-testid="verdicts">
      <p className="text-sm" data-testid="verdict-display">
        Frozen rule: <DecisionPill d={v.frozen_decision} />. With amendment A1 (dated, stricter):{" "}
        <DecisionPill d={v.a1_decision} />.{" "}
        <a className="text-sky-700 underline" href={A1_URL} target="_blank" rel="noreferrer" data-testid="a1-link">
          Why A1 exists
        </a>
      </p>
      <p className="mt-1 text-xs text-slate-600">
        Frozen rule reasons: {v.frozen_reasons || "all criteria met"}. A1 reasons: {v.a1_reasons}.
        A1 requires positive net benefit over both no battery and the fixed schedule; it is the
        live recommendation.
      </p>
      <p className="sr-only">{v.display}</p>
    </div>
  );
}
