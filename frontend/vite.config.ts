import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// The live app is served by FastAPI from src/edip/api/static (Databricks Apps).
export default defineConfig({
  plugins: [react(), tailwindcss()],
  publicDir: false,
  build: { outDir: "../src/edip/api/static", emptyOutDir: true },
  server: { proxy: { "/api": "http://127.0.0.1:8000" } },
});
