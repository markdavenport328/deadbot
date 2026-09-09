// Keep the fixture packet out of production builds. The literal DEV branch is
// replaced at build time, so Rollup can omit the dynamic fixture module.
import type { ExperienceResponse } from "./types";
import type { StreamEvent } from "./stream-events";
import type { VisualFixtureName } from "./visual-fixtures";

export const requestedVisualFixture = import.meta.env.DEV
  ? new URLSearchParams(window.location.search).get("fixture")
  : null;

export async function loadRequestedVisualFixture(): Promise<ExperienceResponse | null> {
  if (!import.meta.env.DEV || !requestedVisualFixture) return null;
  const { visualFixtureFromLocation } = await import("./visual-fixtures");
  return visualFixtureFromLocation();
}

// A named `?stream=` fixture, replayed as a timed event sequence rather than
// dropped in whole (see `requestedVisualFixture` above for the static form).
export const requestedStreamFixture = import.meta.env.DEV
  ? new URLSearchParams(window.location.search).get("stream")
  : null;

export async function loadRequestedStreamEvents(): Promise<StreamEvent[] | null> {
  if (!import.meta.env.DEV || !requestedStreamFixture) return null;
  const { streamEventsFor, visualFixtureNames } = await import("./visual-fixtures");
  const name = requestedStreamFixture;
  const names: readonly string[] = visualFixtureNames;
  return names.includes(name) ? streamEventsFor(name as VisualFixtureName) : null;
}
