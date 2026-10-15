import { defineConfig } from "@playwright/test";

// Public pages (Gate 7): served from the built site with the network blocked except the
// local static server, as after teardown.
const port = 4173;
export default defineConfig({
  testDir: "./e2e-public",
  timeout: 180_000,
  workers: 1,
  reporter: [["list"]],
  use: { baseURL: process.env.PUBLIC_BASE_URL ?? `http://127.0.0.1:${port}/energy-decision-ai-databricks/` },
  webServer: process.env.PUBLIC_BASE_URL
    ? undefined
    : {
        command: `npx vite preview --config vite.pages.config.ts --port ${port} --strictPort --host 127.0.0.1`,
        url: `http://127.0.0.1:${port}/energy-decision-ai-databricks/sandbox/`,
        reuseExistingServer: false,
        timeout: 60_000,
      },
});
