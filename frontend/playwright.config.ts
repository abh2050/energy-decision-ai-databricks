import { createHash } from "node:crypto";
import { defineConfig } from "@playwright/test";

// Local runs simulate the Databricks Apps proxy by sending its X-Forwarded-Email header.
// E2E_BASE_URL runs the same specs against the deployed app with a bearer token instead.
const OPERATOR = "operator@example.com";
const hash = (s: string) => createHash("sha256").update(`edip:${s}`).digest("hex");
const remote = process.env.E2E_BASE_URL;
const port = 8791;

export default defineConfig({
  testDir: "./e2e",
  timeout: 180_000,
  workers: 1,
  reporter: [["list"]],
  use: { baseURL: remote ?? `http://127.0.0.1:${port}`, screenshot: "only-on-failure" },
  webServer: remote
    ? undefined
    : {
        command: `cd .. && uv run uvicorn edip.api.main:app --port ${port}`,
        url: `http://127.0.0.1:${port}/healthz`,
        reuseExistingServer: false,
        timeout: 60_000,
        env: {
          EDIP_DATA_DIR: process.env.EDIP_DATA_DIR ?? "",
          EDIP_STORE: process.env.EDIP_STORE ?? "memory",
          EDIP_MODEL: process.env.EDIP_MODEL ?? "none",
          EDIP_TRACING: process.env.EDIP_TRACING ?? "off",
          EDIP_OPERATOR_HASHES: hash(OPERATOR),
          DATABRICKS_CONFIG_PROFILE: process.env.DATABRICKS_CONFIG_PROFILE ?? "",
        },
      },
});
