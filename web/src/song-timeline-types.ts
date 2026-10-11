// The song timeline's data. The library's shapes come from the API schema
// (deadbot/experience.py, generated into ./generated/api); the stop, the view
// and the focus are shapes the client builds from a song card.

import type { components } from "./generated/api";

type Schemas = components["schemas"];
// Lists the server always fills (default_factory) are optional in the
// generated schema; Require restores the always-present guarantee, as types.ts does.
type Require<T, K extends keyof T> = Omit<T, K> & Required<Pick<T, K>>;

export type TimelineTrack = Schemas["PlayableTrack"];
export type YearPick = Schemas["SongYearPick"];
export type PickBasis = YearPick["basis"];
export type YearSummary = Schemas["SongYearSummary"];
export type LengthPoint = Schemas["SongLengthPoint"];

// The model's stop; a stop the library could not resolve has only its words.
export type TimelineStop = {
  performance_id: string;
  label: string | null;
  why: string | null;
  show_date?: string | null;
  venue_name?: string | null;
  seconds?: number | null;
  track?: TimelineTrack | null;
};

export type ChartView = "count" | "length";

export type SongTimelineData = {
  song_id: string;
  title: string;
  performance_count: number;
  year_summaries: YearSummary[];
  length_points: LengthPoint[];
  stops: TimelineStop[];
  open_year: number | null;
  chart_view: ChartView | null;
  year_questions: { year: number; question: string }[];
};

export type Neighbor = Schemas["SongNeighbor"];
export type YearPerformance = Require<Schemas["SongYearPerformance"], "releases" | "signals" | "guests">;
export type SongYearDetail = Omit<Schemas["SongYearDetail"], "performances"> & { performances: YearPerformance[] };

// What the visitor was pointing at when they asked; the song card sends it as AskFocus.
export type TimelineFocus = { label: string; song_id: string; year: number; ids: string[]; facts: string[] };
