import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

// In development the SPA runs on Vite's own server and forwards API
// calls to the docker-compose gateway, so the browser still sees a
// single origin — the same shape as production, where the gateway
// serves both (ADR-0006: the refresh cookie is SameSite=Strict).
const gateway = process.env.FINCORE_GATEWAY_URL ?? "http://localhost:8180";

export default defineConfig({
  plugins: [react()],
  build: {
    // Phones keep old browsers for years (and every browser on an iPhone is
    // Safari underneath): compile down to what iOS 14 Safari understands
    // rather than the toolchain's newer default.
    target: ["es2020", "safari14", "chrome90", "firefox90"],
  },
  server: {
    port: 5173,
    proxy: {
      "/api": { target: gateway, changeOrigin: false },
    },
  },
  test: {
    globals: true,
    environment: "jsdom",
    setupFiles: ["./src/test/setup.ts"],
    css: false,
  },
});
