// One React tree, three data adapters (PRD section 4): live (this gate), replay and
// sandbox (Gate 7). Every payload carries its provenance.

export type Role = "operator" | "viewer" | "sandbox";

export interface TableRef {
  source: string;
  delta_version: number;
  rows: number;
  sha256: string;
}

export interface Provenance {
  mode: string;
  result_label: string;
  dataset_sha256: string;
  model_version: string;
  evaluation_period: string;
  client: string;
  published_at: string;
  tables: Record<string, TableRef>;
  units: Record<string, string>;
  measured: string[];
  assumed: string[];
}

export interface Meta {
  role: Role;
  provenance: Provenance;
  cells: string[];
  allowed_fields: Record<string, (string | number)[]>;
  base_cell: string;
}

export interface StrategyRow {
  tariff_id: string;
  strategy: string;
  bill_usd: number;
  net_benefit_usd: number;
  max_billing_demand_kw: number;
  peak_grid_kw: number;
  throughput_kwh: number;
  degradation_usd: number;
  regret_vs_hindsight_usd: number;
  violations: number;
  passes_frozen_target: boolean | null;
}

export interface Strategies {
  cell: string;
  rows: StrategyRow[];
  source: TableRef;
  label: string;
}

export interface OperatingRow {
  hour_start_utc: string;
  actual: number | null;
  point: number | null;
  p10: number | null;
  p50: number | null;
  p90: number | null;
  planned_charge_kw: number;
  planned_discharge_kw: number;
  charge_kw: number;
  discharge_kw: number;
  soc_kwh: number;
  grid_kw: number;
  guard_clipped_kw: number;
}

export interface Operating {
  cell: string;
  tariff_id: string;
  strategy: string;
  day: string;
  days: string[];
  rows: OperatingRow[];
  sources: { forecasts: TableRef | string; schedule: TableRef | string };
  label: string;
  synthetic?: boolean;
  reserve?: number;
}

export interface Verdicts {
  frozen_decision: string;
  frozen_reasons: string;
  a1_decision: string;
  a1_reasons: string;
  a1_scope: string;
  display: string;
  a1_ref: string;
}

export type Row = Record<string, unknown>;

export interface BusinessCase {
  cell: string;
  verdicts: Verdicts;
  stress: Row[];
  excess_months: Row[];
  targets: Row;
  battery: { base_case: Row; operating_cost: Row };
  capital: Row;
  sources: Record<string, TableRef>;
  label: string;
}

export interface Sensitivity {
  flip_boundary: Row;
  base_cost_cells: Row[];
  source: TableRef;
  label: string;
}

export interface Scenario {
  scenario_id: string;
  name: string;
  settings: Record<string, string | number>;
  created_at: string;
  objective?: string; // sandbox: the recorded scenario's objective
}

export interface Checkpoint {
  step: string;
  payload: Row;
  created_at: string;
}

export interface AgentCall {
  agent: string;
  prompt_version: string;
  status: string;
  latency_ms: number | null;
  prompt_tokens: number | null;
  completion_tokens: number | null;
  mlflow_trace_id: string | null;
  error_type: string | null;
}

export interface RunDetail {
  run: {
    run_id: string;
    status: string;
    dataset_hash: string;
    model_version: string;
    prompt_versions: Record<string, string>;
    mlflow_trace_ids: string[];
    created_at: string;
  };
  scenario: Scenario;
  checkpoints: Checkpoint[];
  agent_calls: AgentCall[];
  approvals: { decision: string; comment: string | null; created_at: string }[];
}

export interface DataAdapter {
  mode: "live" | "replay" | "sandbox";
  meta(): Promise<Meta>;
  strategies(cell: string): Promise<Strategies>;
  operating(q: { cell: string; tariff_id: string; strategy: string; day?: string; reserve?: number }): Promise<Operating>;
  sensitivity(): Promise<Sensitivity>;
  businessCase(cell: string): Promise<BusinessCase>;
  scenarios(): Promise<Scenario[]>;
  createScenario(body: Record<string, string | number>): Promise<Scenario>;
  runs(): Promise<RunDetail["run"][]>;
  run(id: string): Promise<RunDetail>;
  startRun(body: { scenario_id: string; objective: string; concerns: string }): Promise<RunDetail>;
  confirm(id: string, confirmed: boolean): Promise<RunDetail>;
  decide(id: string, decision: string, comment: string): Promise<RunDetail>;
}
