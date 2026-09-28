/// <reference types="vitest/config" />
import { defineConfig, type ProxyOptions } from "vite";
import react from "@vitejs/plugin-react";

const apiProxy: ProxyOptions = {
  target: "http://127.0.0.1:8000",
  bypass(req) {
    if (req.method === "GET" && (req.headers.accept ?? "").includes("text/html")) {
      return "/index.html";
    }
  },
};

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      "/reviews": apiProxy,
      "/repositories": apiProxy,
      "/health": apiProxy,
      "/analytics": apiProxy,
    },
  },
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: "./src/test/setup.ts",
  },
});

