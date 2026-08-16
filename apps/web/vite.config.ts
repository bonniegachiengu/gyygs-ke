import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    // `host: true` binds every interface so a real Android phone on the same
    // Wi-Fi can hit http://<lan-ip>:5173 — DISPATCH_BRIEF M3 requires phone QA.
    host: true,
    port: 5173,
    proxy: {
      // Mirrors what nginx does in production, so the app calls the API
      // same-origin in both worlds and there is no API base URL to configure.
      "/api": { target: "http://127.0.0.1:8000", changeOrigin: false },
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
