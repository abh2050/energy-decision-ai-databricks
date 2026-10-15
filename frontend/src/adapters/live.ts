// Live adapter: the FastAPI backend on Databricks Apps (OAuth by the Apps proxy).
import type { DataAdapter } from "./types";

export class ApiError extends Error {
  constructor(public status: number, message: string) {
    super(message);
  }
}

async function call<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(path, {
    ...init,
    headers: { "Content-Type": "application/json", ...(init?.headers ?? {}) },
    credentials: "same-origin",
  });
  if (!res.ok) {
    let detail = res.statusText;
    try {
      detail = (await res.json()).detail ?? detail;
    } catch {
      /* not JSON */
    }
    throw new ApiError(res.status, String(detail));
  }
  return (await res.json()) as T;
}

const post = <T>(path: string, body: unknown) =>
  call<T>(path, { method: "POST", body: JSON.stringify(body) });

const q = (o: Record<string, string | undefined>) =>
  new URLSearchParams(Object.entries(o).filter(([, v]) => v !== undefined) as [string, string][]);

export const live: DataAdapter = {
  mode: "live",
  meta: () => call("/api/meta"),
  strategies: (cell) => call(`/api/strategies?${q({ cell })}`),
  operating: (o) => call(`/api/operating?${q(o)}`),
  sensitivity: () => call("/api/sensitivity"),
  businessCase: (cell) => call(`/api/business-case?${q({ cell })}`),
  scenarios: () => call("/api/scenarios"),
  createScenario: (body) => post("/api/scenarios", body),
  runs: () => call("/api/runs"),
  run: (id) => call(`/api/runs/${id}`),
  startRun: (body) => post("/api/runs", body),
  confirm: (id, confirmed) => post(`/api/runs/${id}/confirm`, { confirmed }),
  decide: (id, decision, comment) => post(`/api/runs/${id}/decision`, { decision, comment }),
};
