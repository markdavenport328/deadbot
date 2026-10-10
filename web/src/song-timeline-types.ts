// The song timeline's data, mirroring deadbot/song_life.py's JSON. Phase 2
// replaces these with types generated from the API schema.

export type TimelineTrack = {
  performance_id: string;
  title: string;
  audio_url: string;
  duration_seconds: number | null;
  set_label: string | null;
};

export type PickBasis = "picked" | "show_picked" | "released" | "first";

export type YearPick = {
  performance_id: string;
  show_date: string;
  venue_name: string | null;
  set_label: string | null;
  seconds: number | null;
  basis: PickBasis;
  basis_detail: string | null;
  track: TimelineTrack | null;
};

export type YearSummary = {
  year: number;
  count: number;
  median_seconds: number | null;
  longest: { performance_id: string; seconds: number } | null;
  top_next: { title: string; count: number } | null;
  pick: YearPick | null;
};

export type LengthPoint = { performance_id: string; show_date: string; seconds: number };

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

export type Neighbor = { song_id: string; title: string; segued: boolean };

export type YearPerformance = {
  performance_id: string;
  show_id: string;
  show_date: string;
  venue_name: string | null;
  city: string | null;
  set_label: string | null;
  position_in_set: number;
  encore: boolean;
  previous: Neighbor | null;
  next: Neighbor | null;
  seconds: number | null;
  length_source: "release" | "tape" | null;
  track: TimelineTrack | null;
  releases: string[];
  signals: { voice: string; scope: "performance" | "show" }[];
  guests: { name: string; instrument: string | null }[];
};

export type SongYearDetail = { song_id: string; title: string; year: number; performances: YearPerformance[] };

// What the visitor was pointing at when they asked; phase 2 sends it as AskFocus.
export type TimelineFocus = { label: string; song_id: string; year: number; ids: string[]; facts: string[] };
