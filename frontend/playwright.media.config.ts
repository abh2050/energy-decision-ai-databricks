import { defineConfig } from "@playwright/test";

// Records the demo video and screenshots from the deployed live app (run once, before
// teardown). E2E_BASE_URL and E2E_OPERATOR_TOKEN are read from the environment.
export default defineConfig({
  testDir: "./e2e-media",
  timeout: 600_000,
  workers: 1,
  use: {
    baseURL: process.env.E2E_BASE_URL,
    viewport: { width: 1280, height: 720 },
    video: { mode: "on", size: { width: 1280, height: 720 } },
    extraHTTPHeaders: { Authorization: `Bearer ${process.env.E2E_OPERATOR_TOKEN ?? ""}` },
  },
  outputDir: "media-output",
});
