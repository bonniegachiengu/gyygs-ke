import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

export default defineConfig({
  plugins: [react(), tailwindcss()],
  // npm workspaces hoist react to the repo root while this config lives in
  // apps/web. Without an explicit dedupe the dev server can serve a pre-bundled
  // React to some modules and the raw one to others, which surfaces as
  // "Invalid hook call … more than one copy of React" and a blank screen on the
  // first state change. Harmless in the production build; fatal in dev.
  resolve: { dedupe: ["react", "react-dom"] },
  optimizeDeps: { include: ["react", "react-dom", "react/jsx-runtime", "zustand"] },
  server: {
    // `host: true` binds every interface so a real Android phone on the same
    // Wi-Fi can hit http://<lan-ip>:5173 — DISPATCH_BRIEF M3 requires phone QA.
    host: true,
    port: 5173,
    proxy: {
      // Mirrors what nginx does in production, so the app calls the API
      // same-origin in both worlds and there is no API base URL to configure.
      // Port 8010, not 8000: on Bonnie's machine WSL forwards localhost:8000 to
      // the VOS III backend, which is live and must not be disturbed.
      "/api": { target: "http://127.0.0.1:8010", changeOrigin: false },
    },
  },
  build: {
    target: "es2020",
    cssCodeSplit: false,
    rollupOptions: {
      output: {
        // React changes far less often than app code; a stable vendor chunk
        // keeps it cached across deploys on slow mobile connections.
        // Vite 8 bundles with rolldown, which only accepts the function form —
        // the object form fails with "manualChunks is not a function".
        manualChunks(id: string) {
          if (/node_modules[\\/](react|react-dom|scheduler)[\\/]/.test(id)) return "react";
          return undefined;
        },
      },
    },
  },
});
