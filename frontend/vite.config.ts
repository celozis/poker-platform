/// <reference types="vitest/config" />
import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    proxy: {
      // ws: the hall board's WebSocket goes through the same proxy.
      "/api": { target: process.env.API_URL ?? "http://localhost:8000", ws: true },
    },
  },
  test: {
    environment: "jsdom",
    setupFiles: ["./src/test-setup.ts"],
    // Dates in tests are written for Novosibirsk time (UTC+7).
    env: { TZ: "Asia/Novosibirsk" },
  },
});
