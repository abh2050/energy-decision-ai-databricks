import { expect, test, type Page } from "@playwright/test";
import { signedIn } from "./helpers";

const remote = !!process.env.E2E_BASE_URL;

async function runToRecommendation(page: Page) {
  await page.goto("/");
  await expect(page.getByTestId("role")).toContainText("operator", { timeout: 60_000 });
  await page.getByTestId("new-scenario").click();
  await expect(page.getByTestId("scenario")).not.toHaveValue("");
  await page.getByTestId("start-run").click();
  await expect(page.getByTestId("run-status")).toHaveText("planning_proposed", { timeout: 120_000 });
  await expect(page.getByTestId("interpretation")).not.toBeEmpty();
  await page.getByTestId("confirm").click();
  await expect(page.getByTestId("run-status")).toHaveText("recommended", { timeout: 150_000 });
  await expect(page.getByTestId("verdict-display")).toContainText("Frozen rule:");
  await expect(page.getByTestId("verdict-display")).toContainText("With amendment A1 (dated, stricter):");
}

test("login: no forwarded identity is rejected; a signed-in user gets a role", async ({ browser }) => {
  test.skip(remote, "on Databricks the Apps proxy redirects to OAuth sign-in before the app");
  const anon = await signedIn(browser, "anonymous");
  const res = await anon.request.get("/api/meta");
  expect(res.status()).toBe(401);
  const op = await signedIn(browser, "operator");
  const page = await op.newPage();
  await page.goto("/");
  await expect(page.getByTestId("mode-label")).toContainText("Live", { timeout: 60_000 }); // first load reads the snapshot
  await expect(page.getByTestId("role")).toContainText("operator");
});

test("view recommendation, full decision flow, approval persists", async ({ browser }) => {
  const ctx = await signedIn(browser, "operator");
  const page = await ctx.newPage();
  await runToRecommendation(page);
  await page.getByTestId("comment").fill("e2e approve");
  await page.getByTestId("decide-approve").click();
  await expect(page.getByTestId("run-status")).toHaveText("decided");
  await expect(page.getByTestId("approval")).toContainText("approve");
  // Persistence: a fresh page load reads the approval back from the store.
  await page.reload();
  await page.getByTestId("nav-brief").click();
  await expect(page.getByTestId("brief-calls")).toContainText("approve");
  await expect(page.getByTestId("brief-calls").locator("tbody tr")).toHaveCount(3);
  const runs = await (await ctx.request.get("/api/runs")).json();
  const detail = await (await ctx.request.get(`/api/runs/${runs[0].run_id}`)).json();
  expect(detail.approvals[0].decision).toBe("approve");
  expect(detail.approvals[0].comment).toBe("e2e approve");
});

for (const decision of ["revise", "reject"] as const) {
  test(`operator can ${decision} a recommendation`, async ({ browser }) => {
    const page = await (await signedIn(browser, "operator")).newPage();
    await runToRecommendation(page);
    await page.getByTestId(`decide-${decision}`).click();
    await expect(page.getByTestId("approval")).toContainText(decision);
  });
}

test("viewer is blocked from approving, in the UI and on the server", async ({ browser }) => {
  test.skip(remote && !process.env.E2E_VIEWER_TOKEN, "needs a second, viewer identity on Databricks");
  const viewer = await signedIn(browser, "viewer");
  const page = await viewer.newPage();
  await page.goto("/");
  await expect(page.getByTestId("role")).toContainText("viewer", { timeout: 60_000 });
  await expect(page.getByTestId("viewer-note")).toBeVisible();
  await expect(page.getByTestId("start-run")).toBeDisabled();
  await expect(page.getByTestId("new-scenario")).toBeDisabled();
  const runs = await (await viewer.request.get("/api/runs")).json();
  const target = runs.length ? runs[0].run_id : "none";
  const res = await viewer.request.post(`/api/runs/${target}/decision`, { data: { decision: "approve" } });
  expect(res.status()).toBe(403);
  const sc = await viewer.request.post("/api/scenarios", {
    data: { name: "x", tariff_id: "pge_b19_secondary", strategy: "robust_quantile", power_fraction: 0.5, duration_hours: 2 },
  });
  expect(sc.status()).toBe(403);
});

test("every view shows provenance, units, and measured versus assumed labels", async ({ browser }) => {
  const page = await (await signedIn(browser, remote && !process.env.E2E_VIEWER_TOKEN ? "operator" : "viewer")).newPage();
  await page.goto("/");
  for (const view of ["operating", "strategies", "brief", "business"]) {
    await page.getByTestId(`nav-${view}`).click();
    await expect(page.getByTestId("provenance")).toContainText("Evaluation period");
    await expect(page.getByTestId("provenance")).toContainText("Results:");
  }
  await page.getByTestId("nav-strategies").click();
  await expect(page.getByTestId("strategy-table").first()).toContainText("measured");
  await expect(page.getByTestId("strategy-table").first().getByTestId("source")).toContainText("Delta version");
  await page.getByTestId("nav-business").click();
  await expect(page.getByTestId("verdict-display")).toContainText("Frozen rule:");
  await expect(page.getByTestId("a1-link")).toHaveAttribute("href", /amendment-a1/);
  await expect(page.getByTestId("assumptions")).toContainText("assumed");
});
