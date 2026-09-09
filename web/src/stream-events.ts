// The wire shape of the streaming endpoint's events. Shared by App.tsx (the
// live network reader and the replay effect) and visual-fixtures.ts (the
// replay fixture builder), so neither has to import the other.
import type { ExperienceBlock, ExperienceGroup, ExperienceResponse } from "./types";

export type PageEvent =
  | { type: "page_head"; title: string; lead: string | null }
  | { type: "group_open" | "group_close"; index: number; title: string | null; lead: string | null; presentation: ExperienceGroup["presentation"]; criteria: string[] }
  | { type: "block"; group_index: number; block: ExperienceBlock }
  | { type: "page_reset" };

export type StreamEvent =
  | { type: "status"; text: string }
  | { type: "answer"; text: string }
  | { type: "response"; response: ExperienceResponse }
  | { type: "error"; detail?: string }
  | PageEvent;
