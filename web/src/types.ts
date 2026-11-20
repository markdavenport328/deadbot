// Derived from web/openapi.json — do not hand-edit.
//
// The browser contract is defined once, in Python, as the Pydantic models in
// deadbot/experience.py. This file re-exports typed aliases over the
// TypeScript generated from that schema (web/src/generated/api.ts) so the two
// never drift. To pick up a schema change, regenerate both files:
//
//   .venv/bin/python scripts/export_openapi.py
//   npm run gen:types --prefix web
//
// CI fails the build if either regeneration step would change a committed
// file (see .github/workflows/ci.yml).
import type { components } from "./generated/api";

// A handful of ExperienceResponse fields (`blocks`, `layout`, `sources`,
// `conversation`) — and a few nested block fields (`details`,
// `credits`, `source_ids`, `representative_performances`, `sources`) — are declared in deadbot/experience.py with a
// Pydantic default_factory (e.g. `Field(default_factory=list)`). FastAPI's
// OpenAPI schema marks those as not required, because a *request* using this
// same model could omit them. But every browser-facing response is built
// through ExperienceResponse's own constructor, which always populates them
// (with `[]` when empty) — the server never omits the key. `Require` restores
// that always-present guarantee in the client's types without touching the
// generated file or the components that consume these fields.
type Require<T, K extends keyof T> = Omit<T, K> & Required<Pick<T, K>>;

export type SourceReference = components["schemas"]["SourceReference"];
export type AskFocus = components["schemas"]["AskFocus"];
export type ExperienceGroup = Require<components["schemas"]["ExperienceGroup"], "criteria">;

type FixedEntityCardBlock = Require<components["schemas"]["EntityCardBlock"], "details">;
type FixedEditorialBlock = Require<components["schemas"]["EditorialBlock"], "paragraphs" | "items">;
type FixedSongOverviewBlock = Require<
  components["schemas"]["SongOverviewBlock"],
  "credits" | "source_ids" | "albums" | "representative_performances" | "sources" | "visible_facets" | "judgments"
>;

// Semantic units. Their hydrated lists are always present in a server
// response (see the note on Require above).
export type ShowUnitBlock = Require<components["schemas"]["ShowUnitBlock"], "sets" | "guests" | "listen" | "sources" | "visible_facets" | "lineup" | "recordings" | "judgments">;
export type AlbumUnitBlock = Require<
  components["schemas"]["AlbumUnitBlock"],
  "tracks" | "personnel" | "listen" | "sources" | "judgments"
>;
type FixedDataChartBlock = Require<components["schemas"]["DataChartBlock"], "rows">;

export type ExperienceBlock =
  | FixedEntityCardBlock
  | ShowUnitBlock
  | AlbumUnitBlock
  | components["schemas"]["PeopleTimelineBlock"]
  | components["schemas"]["ResourceListBlock"]
  | components["schemas"]["CreditListBlock"]
  | FixedSongOverviewBlock
  | components["schemas"]["MediaLinkBlock"]
  | components["schemas"]["CoverageBlock"]
  | components["schemas"]["ProvenanceNoteBlock"]
  | components["schemas"]["GapStateBlock"]
  | FixedEditorialBlock
  | Require<components["schemas"]["ListeningHeroBlock"], "queue">
  | components["schemas"]["PullQuoteBlock"]
  | FixedDataChartBlock
  | Require<components["schemas"]["VersionStripBlock"], "year_counts">
  | components["schemas"]["SongVersionsBlock"]
  | Require<components["schemas"]["GridBlock"], "suggestions" | "follow_ups">
  | components["schemas"]["RankedListBlock"];

export type GridBlock = Extract<ExperienceBlock, { type: "grid" }>;

// `schema_version` is the server's current version on a fresh response, but a
// page the browser saved earlier carries the version it was made under, so the
// client's type is any string; the saved-page reader compares it.
export type ExperienceResponse = Omit<
  components["schemas"]["ExperienceResponse"],
  "blocks" | "sources" | "conversation" | "schema_version"
> &
  Required<
    Pick<components["schemas"]["ExperienceResponse"], "groups" | "sources" | "conversation">
  > & {
    schema_version?: string;
    blocks: ExperienceBlock[];
  };
