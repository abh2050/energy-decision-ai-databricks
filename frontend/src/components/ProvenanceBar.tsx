import type { Meta } from "../adapters/types";
import { short } from "../lib/format";
import { Badge } from "./ui";

// Shown on every view (PRD section 4): mode, provenance, units, evaluation period, and
// which values are measured versus assumed.
export function ProvenanceBar({ meta }: { meta: Meta }) {
  const p = meta.provenance;
  return (
    <div className="border-b border-slate-200 bg-slate-100 px-6 py-2 text-xs text-slate-700" data-testid="provenance">
      <div className="flex flex-wrap gap-x-5 gap-y-1">
        <span>
          Mode: <strong data-testid="mode-label">{p.mode === "live" ? "Live (Databricks)" : p.mode}</strong>
        </span>
        <span>
          Results: <strong>{p.result_label}</strong>
        </span>
        <span>Evaluation period: {p.evaluation_period}</span>
        <span>Client: {p.client}</span>
        <span>Model: {p.model_version}</span>
        <span>Dataset SHA256: {short(p.dataset_sha256)}</span>
        <span>Published from Delta: {p.published_at}</span>
        <span data-testid="role">
          Signed in as: <strong>{meta.role}</strong>
        </span>
      </div>
      <details className="mt-1">
        <summary className="cursor-pointer">Units, measured and assumed values</summary>
        <div className="mt-1 grid gap-2 md:grid-cols-3">
          <ul>
            {Object.entries(p.units).map(([k, v]) => (
              <li key={k}>
                <code>{k}</code>: {v}
              </li>
            ))}
          </ul>
          <ul>
            {p.measured.map((m) => (
              <li key={m}>
                <Badge kind="measured" /> {m}
              </li>
            ))}
          </ul>
          <ul>
            {p.assumed.map((m) => (
              <li key={m}>
                <Badge kind="assumed" /> {m}
              </li>
            ))}
          </ul>
        </div>
      </details>
    </div>
  );
}
