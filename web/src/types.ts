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
// `conversation`) — and a few nested block fields (`details`, `progressions`,
// `credits`, `source_ids`) — are declared in deadbot/experience.py with a
// Pydantic default_factory (e.g. `Field(default_factory=list)`). FastAPI's
// OpenAPI schema marks those as not required, because a *request* using this
// same model could omit them. But every browser-facing response is built
// through ExperienceResponse's own constructor, which always populates them
// (with `[]` when empty) — the server never omits the key. `Require` restores
// that always-present guarantee in the client's types without touching the
// generated file or the components that consume these fields.
type Require<T, K extends keyof T> = Omit<T, K> & Required<Pick<T, K>>;

export type SourceReference = components["schemas"]["SourceReference"];

type FixedEntityCardBlock = Require<components["schemas"]["EntityCardBlock"], "details">;
type FixedArrangementBlock = Require<components["schemas"]["ArrangementBlock"], "progressions">;
type FixedSongOverviewBlock = Require<
  components["schemas"]["SongOverviewBlock"],
  "credits" | "source_ids"
>;

export type ExperienceBlock =
  | FixedEntityCardBlock
  | components["schemas"]["ShowSetlistBlock"]
  | components["schemas"]["RecordingListBlock"]
  | components["schemas"]["PerformerListBlock"]
  | components["schemas"]["EquipmentListBlock"]
  | components["schemas"]["ResourceListBlock"]
  | components["schemas"]["CreditListBlock"]
  | FixedSongOverviewBlock
  | components["schemas"]["MediaLinkBlock"]
  | components["schemas"]["PerformanceListBlock"]
  | components["schemas"]["PerformanceExtremesBlock"]
  | components["schemas"]["PerformanceSpineBlock"]
  | components["schemas"]["ComparisonStripBlock"]
  | components["schemas"]["CoverageBlock"]
  | FixedArrangementBlock
  | components["schemas"]["ArrangementSearchBlock"]
  | components["schemas"]["ProvenanceNoteBlock"]
  | components["schemas"]["GapStateBlock"];

export type ExperienceResponse = Omit<
  components["schemas"]["ExperienceResponse"],
  "blocks" | "layout" | "sources" | "conversation"
> &
  Required<
    Pick<components["schemas"]["ExperienceResponse"], "layout" | "sources" | "conversation">
  > & {
    blocks: ExperienceBlock[];
  };
