import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import { resolve } from "node:path";
import { defineConfig } from "vite";

// Public site for GitHub Pages: the presentation (root page) and the app (browser sandbox), served under the
// repository path. Data files come from public/ (frozen JSON, ONNX models, traces, media).
export default defineConfig({
  base: process.env.PAGES_BASE ?? "/energy-decision-ai-databricks/",
  plugins: [react(), tailwindcss()],
  build: {
    outDir: "../site",
    emptyOutDir: true,
    rollupOptions: {
      input: {
        index: resolve(import.meta.dirname, "pages.html"),
        app: resolve(import.meta.dirname, "app/index.html"),
      },
    },
  },
  worker: { format: "es" },
  preview: { port: 4173, strictPort: true },
});
