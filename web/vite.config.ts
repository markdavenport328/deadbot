import { readFileSync } from "node:fs";
import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";

// The page contract's version, from the same file the client's types are
// generated from, so the client knows which saved pages it can still draw.
const openapi = JSON.parse(readFileSync(new URL("./openapi.json", import.meta.url), "utf8"));
const schemaVersion: string = openapi.components.schemas.ExperienceResponse.properties.schema_version.const;

export default defineConfig({
  plugins: [react()],
  define: {
    __DEADBOT_SCHEMA_VERSION__: JSON.stringify(schemaVersion)
  },
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
