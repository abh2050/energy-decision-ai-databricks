import type { Browser, BrowserContext } from "@playwright/test";

const remote = !!process.env.E2E_BASE_URL;

// Locally: the header the Databricks Apps proxy adds after OAuth sign-in.
// Remotely: a workspace OAuth token per role (E2E_OPERATOR_TOKEN, E2E_VIEWER_TOKEN).
export async function signedIn(browser: Browser, role: "operator" | "viewer" | "anonymous"): Promise<BrowserContext> {
  if (role === "anonymous") return browser.newContext();
  const headers: Record<string, string> = remote
    ? { Authorization: `Bearer ${process.env[role === "operator" ? "E2E_OPERATOR_TOKEN" : "E2E_VIEWER_TOKEN"] ?? ""}` }
    : { "X-Forwarded-Email": `${role}@example.com` };
  return browser.newContext({ extraHTTPHeaders: headers });
}
