import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      // DEADBOT_API_URL points the dev server at an API on another port.
      "/api": process.env.DEADBOT_API_URL ?? "http://127.0.0.1:8000"
    }
  },
  test: {
    environment: "jsdom",
    setupFiles: ["./src/setupTests.ts"],
    globals: true,
    css: false
  }
});
