import type { ReactNode } from "react";
import type { TableRef } from "../adapters/types";
import { short } from "../lib/format";

export function Card(props: { title: string; children: ReactNode; source?: TableRef | string; testId?: string }) {
  return (
    <section className="rounded-lg border border-slate-200 bg-white p-4 shadow-sm" data-testid={props.testId}>
      <h2 className="mb-3 text-base font-semibold">{props.title}</h2>
      {props.children}
      {props.source && <SourceLine source={props.source} />}
    </section>
  );
}

export function SourceLine({ source }: { source: TableRef | string }) {
  return (
    <p className="mt-3 text-xs text-slate-500" data-testid="source">
      Source:{" "}
      {typeof source === "string" ? (
        source
      ) : (
        <>
          <code>{source.source}</code> (Delta version {source.delta_version}, {source.rows} rows,
          SHA256 {short(source.sha256)})
        </>
      )}
    </p>
  );
}

export function Badge({ kind }: { kind: "measured" | "assumed" | "synthetic" | "template" }) {
  const cls = {
    measured: "bg-emerald-100 text-emerald-800",
    assumed: "bg-amber-100 text-amber-800",
    synthetic: "bg-fuchsia-100 text-fuchsia-800",
    template: "bg-slate-200 text-slate-700",
  }[kind];
  return <span className={`rounded px-1.5 py-0.5 text-xs font-medium ${cls}`}>{kind}</span>;
}

export function DecisionPill({ d }: { d: string }) {
  const cls =
    d === "proceed"
      ? "bg-emerald-600"
      : d === "revise"
        ? "bg-amber-500"
        : d === "withhold"
          ? "bg-rose-600"
          : "bg-slate-500";
  return <span className={`rounded px-2 py-0.5 text-sm font-semibold text-white ${cls}`}>{d}</span>;
}

export function ErrorNote({ error }: { error: unknown }) {
  if (!error) return null;
  return (
    <p role="alert" className="rounded bg-rose-50 p-2 text-sm text-rose-800">
      {error instanceof Error ? error.message : String(error)}
    </p>
  );
}

export function Select<T extends string | number>(props: {
  label: string;
  value: T;
  options: T[];
  onChange: (v: T) => void;
  testId?: string;
  render?: (v: T) => string;
}) {
  return (
    <label className="flex flex-col text-xs text-slate-600">
      {props.label}
      <select
        className="mt-1 rounded border border-slate-300 bg-white px-2 py-1 text-sm text-slate-900"
        value={String(props.value)}
        data-testid={props.testId}
        onChange={(e) => {
          const v = props.options.find((o) => String(o) === e.target.value);
          if (v !== undefined) props.onChange(v);
        }}
      >
        {props.options.map((o) => (
          <option key={String(o)} value={String(o)}>
            {props.render ? props.render(o) : String(o)}
          </option>
        ))}
      </select>
    </label>
  );
}
