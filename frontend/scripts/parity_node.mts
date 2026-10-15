// Node check of the browser optimizer against the 20 saved Python cases (dev aid; the
// gate test runs the same comparison in the browser with Playwright).
import { readFileSync } from "node:fs";
import highsLoader from "highs";
import { solveDay } from "../src/wasm/optimizer.ts";

const highs = await highsLoader();
const { cases } = JSON.parse(readFileSync("public/data/sandbox/parity_cases.json", "utf8"));
let worst = 0;
for (const c of cases) {
  const plan = solveDay(highs, c);
  const rel = Math.abs(plan.objective_usd - c.python_objective_usd) / Math.max(1, Math.abs(c.python_objective_usd));
  worst = Math.max(worst, rel);
  console.log(c.case, c.tariff_id.slice(0, 4), c.strategy.slice(0, 6), c.python_objective_usd.toFixed(3), plan.objective_usd.toFixed(3), (rel * 100).toFixed(4) + "%");
}
console.log("worst", (worst * 100).toFixed(5) + "%");
