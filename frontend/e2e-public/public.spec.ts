import { expect, test, type Page } from "@playwright/test";
import { readFileSync } from "node:fs";

const BANNER =
  "Sandbox mode: model and optimizer run locally in your browser; agent responses are recorded from the live system.";

// Block everything except the static site itself (as after the cloud is torn down).
async function offline(page: Page, baseURL: string) {
  const origin = new URL(baseURL).origin;
  const blocked: string[] = [];
  await page.route("**/*", (route) => {
    const url = route.request().url();
    if (url.startsWith(origin) || url.startsWith("data:") || url.startsWith("blob:")) return route.continue();
    blocked.push(url);
    return route.abort();
  });
  return blocked;
}

test("sandbox: banner, live forecast and schedule in the browser, network blocked", async ({ page, baseURL }) => {
  const blocked = await offline(page, baseURL!);
  await page.goto("sandbox/");
  await expect(page.getByTestId("sandbox-banner")).toHaveText(BANNER);
  await expect(page.getByTestId("mode-label")).toContainText("Sandbox");
  await expect(page.getByTestId("schedule-chart")).toContainText("solved in your browser", { timeout: 120_000 });
  await expect(page.getByTestId("forecast-chart")).toContainText("computed in your browser");
  await expect(page.getByTestId("sandbox-settlement-note")).toContainText("without 15 minute billing demand or the charge guard");
  // Change battery size, tariff, and reserve: the schedule is re-solved locally.
  await page.getByTestId("cell").first().selectOption("1/4");
  await page.getByTestId("reserve").fill("0.3");
  await expect(page.getByTestId("schedule-chart")).toContainText("objective", { timeout: 120_000 });
  // A synthetic day is labelled synthetic.
  const days = await page.getByTestId("day").locator("option").allTextContents();
  await page.getByTestId("day").selectOption(days.find((d) => d.startsWith("synthetic"))!);
  await expect(page.getByTestId("synthetic-note")).toBeVisible({ timeout: 120_000 });
  expect(blocked).toEqual([]);
});

test("sandbox: recorded agent traces by scenario; template when no recording", async ({ page, baseURL }) => {
  await offline(page, baseURL!);
  await page.goto("sandbox/");
  await page.getByTestId("scenario").selectOption("s09");
  await page.getByTestId("start-run").click();
  await expect(page.getByTestId("interpretation")).not.toBeEmpty();
  await page.getByTestId("confirm").click();
  await expect(page.getByTestId("recommendation")).toBeVisible();
  await expect(page.getByTestId("verdict-display")).toContainText("Frozen rule:");
  await page.getByTestId("decide-approve").click();
  await expect(page.getByTestId("approval")).toContainText("this browser only");
  // A new scenario has no recording: the template answers, labelled as a template.
  await page.getByTestId("new-scenario").click();
  await page.getByTestId("start-run").click();
  await page.getByTestId("confirm").click();
  await expect(page.getByTestId("recommendation")).toContainText("template");
});

test("sandbox: every view shows provenance and labels", async ({ page, baseURL }) => {
  await offline(page, baseURL!);
  await page.goto("sandbox/");
  for (const v of ["strategies", "business", "brief", "operating"]) {
    await page.getByTestId(`nav-${v}`).click();
    await expect(page.getByTestId("provenance")).toContainText("Evaluation period");
  }
  await page.getByTestId("nav-business").click();
  await expect(page.getByTestId("sensitivity-map")).toContainText("USD");
  await expect(page.getByTestId("verdict-display")).toContainText("With amendment A1");
});

test("parity: browser optimizer matches Python on 20 saved cases within 0.5 percent", async ({ page, baseURL }) => {
  await offline(page, baseURL!);
  await page.goto("sandbox/");
  const { cases } = JSON.parse(readFileSync("public/data/sandbox/parity_cases.json", "utf8"));
  expect(cases.length).toBe(20);
  for (const c of cases) {
    const plan = await page.evaluate((p) => window.edipSolve!(p), c);
    const rel = Math.abs(plan.objective_usd - c.python_objective_usd) / Math.max(1, Math.abs(c.python_objective_usd));
    expect(rel, `case ${c.case}`).toBeLessThanOrEqual(0.005);
  }
});

test("parity: browser ONNX forecast matches the pinned Python forecast", async ({ page, baseURL }) => {
  await offline(page, baseURL!);
  await page.goto("sandbox/");
  const slice = JSON.parse(readFileSync("public/data/sandbox/slice.json", "utf8"));
  const got = await page.evaluate(() => window.edipForecastDay1!());
  for (const q of ["point", "p10", "p50", "p90"] as const) {
    const ref = (slice.reference_forecasts[q] as number[]).slice(0, 24);
    const worst = Math.max(...ref.map((v, i) => Math.abs(v - got[q][i])));
    expect(worst, q).toBeLessThan(0.5); // kW
  }
});

test("explainer: video, clickable architecture, walkthrough, screenshots, traces, results", async ({ page, baseURL }) => {
  const blocked = await offline(page, baseURL!);
  await page.goto("explainer/");
  await expect(page.getByTestId("video")).toHaveAttribute("src", /demo\.webm$/);
  const ok = await page.evaluate(async () => {
    const v = document.querySelector("video")!;
    return (await fetch(v.src, { method: "HEAD" })).ok;
  });
  expect(ok).toBe(true);
  await page.getByTestId("layer-forecast").click();
  await expect(page.getByTestId("layer-detail")).toContainText("ONNX");
  await expect(page.getByTestId("walkthrough")).toContainText("Operator request");
  await page.getByTestId("step-6").click();
  await expect(page.getByTestId("step-6")).toContainText("Tests chosen");
  await expect(page.getByTestId("screenshots").locator("img")).toHaveCount(5);
  await expect(page.getByTestId("trace-table")).toContainText("agent.business");
  await expect(page.getByTestId("results-table")).toContainText("robust quantile");
  await expect(page.getByTestId("sensitivity-map")).toContainText("USD");
  await expect(page.getByTestId("evaluation-table")).toContainText("Held-out");
  await expect(page.getByTestId("recommendation-text")).toContainText("Do not buy a battery");
  expect(blocked).toEqual([]);
});

test("landing page links both public pages", async ({ page, baseURL }) => {
  await offline(page, baseURL!);
  await page.goto("./");
  await expect(page.locator('a[href="./sandbox/"]')).toBeVisible();
  await expect(page.locator('a[href="./explainer/"]')).toBeVisible();
  // All six architecture diagrams load from the site itself.
  const imgs = page.locator("figure img");
  await expect(imgs).toHaveCount(6);
  for (let i = 0; i < 6; i++) {
    await imgs.nth(i).scrollIntoViewIfNeeded();
    await expect.poll(() => imgs.nth(i).evaluate((el: HTMLImageElement) => el.naturalWidth)).toBeGreaterThan(0);
  }
});
