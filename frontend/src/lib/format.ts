export const usd = (v: unknown) =>
  typeof v === "number"
    ? v.toLocaleString("en-US", { maximumFractionDigits: 0 }) + " USD"
    : "n/a";
export const num = (v: unknown, digits = 1) =>
  typeof v === "number" ? v.toLocaleString("en-US", { maximumFractionDigits: digits }) : "n/a";
export const pct = (v: unknown) => (typeof v === "number" ? `${v.toFixed(1)}%` : "n/a");
export const short = (s: string, n = 12) => (s.length > n ? s.slice(0, n) + "…" : s);
export const label = (s: string) => s.replaceAll("_", " ");
