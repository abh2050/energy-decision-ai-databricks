import { test, type Page } from "@playwright/test";

const SHOTS = "../docs/gates/gate7_screens";

async function caption(page: Page, text: string, ms: number) {
  await page.evaluate((t) => {
    let el = document.getElementById("demo-caption");
    if (!el) {
      el = document.createElement("div");
      el.id = "demo-caption";
      el.style.cssText =
        "position:fixed;left:50%;bottom:24px;transform:translateX(-50%);max-width:1100px;z-index:9999;" +
        "background:rgba(15,23,42,.92);color:#fff;padding:12px 18px;border-radius:10px;font:500 18px/1.4 system-ui";
      document.body.appendChild(el);
    }
    el.textContent = t;
  }, text);
  await page.waitForTimeout(ms);
}

async function hideCaption(page: Page) {
  await page.evaluate(() => document.getElementById("demo-caption")?.remove());
}

test("demo walkthrough", async ({ page }) => {
  await page.goto("/");
  await page.getByTestId("forecast-chart").waitFor({ timeout: 120_000 });
  await caption(page, "Energy Decision Intelligence Platform: should a facility run a forecast-driven battery schedule? Live app on Databricks Apps.", 9000);
  await caption(page, "Every view shows its provenance: Delta source and version, evaluation period, model version, units, and measured versus assumed values.", 8000);
  await caption(page, "Operating workspace: day-ahead forecast with the P10 to P90 band, and the planned and settled battery schedule for the busiest day.", 9000);
  await hideCaption(page);
  await page.screenshot({ path: `${SHOTS}/operating_workspace.png` });
  await page.getByTestId("cell").selectOption("1/4");
  await caption(page, "Change the battery: full site peak, 4 hours. All results are the persisted 2014 replay (revised strategy, corrected guard).", 8000);

  await page.getByTestId("nav-strategies").click();
  await caption(page, "Strategy comparison: bills, billed peaks, throughput, degradation, regret against hindsight, and constraint violations for all six strategies.", 10000);
  await hideCaption(page);
  await page.screenshot({ path: `${SHOTS}/strategy_comparison.png`, fullPage: true });
  await page.mouse.wheel(0, 700);
  await caption(page, "On PG&E B-19, robust dispatch beats no battery at every size; on PGE Schedule 85, nothing forecast-driven does.", 8000);

  await page.getByTestId("nav-business").click();
  await page.getByTestId("cell").selectOption("0.5/2");
  await caption(page, "Pilot business case: two deterministic verdicts, side by side. Frozen rule: revise. With amendment A1 (stricter): revise.", 10000);
  await hideCaption(page);
  await page.screenshot({ path: `${SHOTS}/pilot_business_case.png`, fullPage: true });
  await page.mouse.wheel(0, 650);
  await caption(page, "Sensitivity map: net benefit against no battery by battery size and tariff spread, with the flip boundaries.", 9000);
  await page.mouse.wheel(0, 700);
  await caption(page, "Stress tests: forecast error, heat week, reserve floor. Every battery size breaches at least one limit, so no size reaches proceed.", 9000);
  await page.mouse.wheel(0, 900);
  await caption(page, "Capital layer: at the mid NREL ATB cost nothing pays back within 15 years. Recommendation: do not buy a battery for this load profile.", 10000);

  await page.getByTestId("nav-operating").click();
  await page.getByTestId("decision-panel").scrollIntoViewIfNeeded();
  await page.getByTestId("new-scenario").click();
  await page.getByTestId("objective").fill("Evaluate a battery sized to the full site peak with 4 hours of storage.");
  await caption(page, "A decision run. The operator states an objective in plain language; the planning agent proposes a typed change, quoting the request.", 9000);
  await page.getByTestId("start-run").click();
  await page.getByTestId("interpretation").waitFor({ timeout: 120_000 });
  await caption(page, "The proposal waits for the operator. Hard constraints are never on the allowlist, and every number must match its evidence row.", 9000);
  await page.getByTestId("confirm").click();
  await caption(page, "After confirmation: persisted forecast, optimization and settlement, then the risk agent picks stress tests and the business agent drafts the brief.", 6000);
  await page.getByTestId("recommendation").waitFor({ timeout: 180_000 });
  await page.getByTestId("recommendation").scrollIntoViewIfNeeded();
  await caption(page, "Business prompt v3 restates the A1 verdict; it may only explain it. The deterministic verdicts sit beside the agent's text.", 10000);
  await hideCaption(page);
  await page.screenshot({ path: `${SHOTS}/decision_run.png` });
  await page.getByTestId("comment").fill("demo");
  await page.getByTestId("decide-revise").click();
  await caption(page, "Only the operator decides: approve, revise, or reject. The decision is stored in Lakebase with a hashed identity.", 8000);

  await page.getByTestId("nav-brief").click();
  await page.getByTestId("brief-planning").waitFor();
  await caption(page, "Agent decision brief: planning interpretation, risk findings, and the recommendation, each claim linked to its evidence row.", 10000);
  await hideCaption(page);
  await page.screenshot({ path: `${SHOTS}/agent_decision_brief.png`, fullPage: true });
  await page.mouse.wheel(0, 1200);
  await caption(page, "One model call per agent, with prompt version, latency, tokens, and an MLflow trace for each. A failed or invalid answer falls back to a template.", 10000);
  await caption(page, "Viewers can read everything but cannot start, confirm, or decide: roles are enforced on the server.", 8000);
  await caption(page, "The public sandbox runs the same forecaster (onnxruntime web) and optimizer (highs js) in your browser, with recorded agent traces.", 9000);
  await hideCaption(page);
});
