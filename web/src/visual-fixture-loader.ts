// Keep the fixture packet out of production builds. The literal DEV branch is
// replaced at build time, so Rollup can omit the dynamic fixture module.
import type { ExperienceResponse } from "./types";

export const requestedVisualFixture = import.meta.env.DEV
  ? new URLSearchParams(window.location.search).get("fixture")
  : null;

export async function loadRequestedVisualFixture(): Promise<ExperienceResponse | null> {
  if (!import.meta.env.DEV || !requestedVisualFixture) return null;
  const { visualFixtureFromLocation } = await import("./visual-fixtures");
  return visualFixtureFromLocation();
}
