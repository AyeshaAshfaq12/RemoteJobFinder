import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// M5 replaces this with a per-view build that inlines JS/CSS into dist/<view>.html.
export default defineConfig({
  plugins: [react()],
  build: { outDir: "dist", emptyOutDir: true },
});
