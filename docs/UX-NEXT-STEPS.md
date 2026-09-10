# Deadbot UX continuation — September 7, 2026

## Start here

Read `AGENTS.md` and this file before continuing UX work. The user approved the
prioritized plan below and asked for implementation in reviewable batches.
Preserve model ownership of selection, interpretation, ordering, grouping, and
omission. One model delivers the whole turn through `finish_response`.

## Repository reconciliation

There are two separate clones of the same GitHub repository:

- `/Users/markdavenport/Development/Deadbot`: was already at `079f4cb` (PR #13).
  Two generated TypeScript build-info files were modified. This clone was not changed.
- `/Users/markdavenport/Documents/Claude/Personal/DeadBot`: this task's workspace.
  As of September 7 it is aligned with `main` at `a42b62b` (merged PR #17).
  Its previous work was rebased onto the merged album work (PR #15); no hard reset
  was used.

The earlier reviews saying semantic units were absent described the stale mirror.
They DO exist in current main: show_unit, performance_unit, era_unit, show_explorer
(retired in the palette cut), attached listening, highlighted songs, Ask chips, and
peer-show setlist disclosure.
Do not rebuild these. Check branch/status in the exact working folder first;
changes to one clone do not update the other automatically.

## First batch implemented

- Generated titles widened from 12ch to 26ch, capped at 40px, with balanced wrapping.
- Opening padding/lead spacing reduced; shared spacing tokens introduced.
- Peer semantic units separated more strongly while internal details stay close.
- Mobile conversation's 36rem minimum height removed; textarea fills available width.
- Mobile View answer anchor is inside the composer and targets the answer heading.
- Streaming autoscroll is confined to the conversation's own overflow container,
  with reduced-motion support, instead of scrolling the entire document.
- Song/performance identity separated from a visible Listen link with an external
  destination cue and descriptive accessible label. Missing links leave plain identity.
- Show recording actions moved before full setlists, within the same show unit.
- Outbound recording actions no longer use misleading playback icons. Backend
  performance action copy now says Listen to rather than Play; era action selection
  and existing label assertions were updated consistently.
- Setlist numbering restored; narrow heading/role wrapping improved.

Main files: `web/src/App.tsx`, `web/src/styles.css`, `deadbot/composition.py`,
`tests/test_finish.py`. No schema or model editorial changes in this batch.

## Listening pathways and album reconciliation completed

- Song titles with verified recording URLs are the listening links; a compact play
  mark communicates the destination without appending repeated `Listen` text.
  Unlinked songs remain plain identity.
- Positional `Start here` and `Culmination` annotations remain non-interactive.
  Generic Internet Archive recording indexes are not promoted as show or
  performance actions, and follow-up chips invite interpretation rather than
  duplicate listening controls.
- A conservative candidate-selection bug no longer suppresses an entire show when
  one of several possible paths is invalid. `1990-03-29` now has verified Archive
  links for all 17 performances.
- The partial `1994-12-16` representative is supplemented by verified metadata
  from an existing complete SBD recording. Ten targeted mappings fill the former
  gaps, including `Estimated Prophet` and `The Other One`; never replace a missing
  song mapping with a whole-show URL.
- The album semantic unit from merged PR #15 was reconciled with this interaction:
  album track highlights correctly emphasize linked titles, and its recording
  action, tracklist, credits, and relationship labels use the same listening
  vocabulary.

## Editorial scope and prioritization completed

- The system prompt now makes orientation precede discovery: answer directly,
  decide how much depth the question earns, build a factual spine, distinguish
  sourced interpretation and synthesis, and perform an omission pass before
  composing.
- Chat, page, group and unit layers have distinct jobs instead of each restating
  the thesis. One group is the default; more groups must introduce a genuinely
  distinct movement.
- The Five Jobs of Gestalt are explicit, including segregation and global
  organization: the direct answer, support and optional exploration must be
  recognizable at first glance.
- Follow-ups are optional and limited to one or two unusually valuable paths.
  Discovery is no longer a mandatory completion criterion.
- `show_unit` no longer defaults to every facet or an expanded setlist.
  `album_unit` now accepts model-selected listening, tracklist, personnel and
  source facets; full album inventory appears only when the composer selects it.
- `evals/editorial-scope-v1.json` adds manual model-review cases for a compact
  fact, American Beauty's live legacy, an Eyes development, and subjective best
  shows. These test meaningfully different earned depths without deterministic
  question routing.

Validation: 296 Python tests passed. No browser response schema or frontend
source changed; generated API types therefore did not require regeneration.

## Remaining work, in priority order

### 1. Broaden visual acceptance coverage

Use fixed validated responses (not live model generation) for visual comparisons:
Branford collection, Eyes development, Cornell argument, three Shakedown
recommendations, and a compact fact. Include long titles/venues, missing links,
multiple recordings, highlights, sources, and expanded setlists. First batch used
temporary local-only fixture entries with the actual App and mocked API; these
were removed before delivery. A reusable development-only fixture harness would
make subsequent review repeatable without adding product UI or calling an LLM.

The reusable harness is now available in `web/src/visual-fixtures.ts`. Run
`npm run dev --prefix web` and add `?fixture=branford`, `eyes`, `cornell`,
`shakedown`, `fact`, or `songs` to the local URL. It loads through the actual App
renderers, skips server health and model requests, exposes no visitor-facing
fixture control, and is excluded from production bundles. Initial review covered
the fixture set at 1440px, 600px, 390px, and 320px, including a local expanded
setlist disclosure. Keyboard navigation, enlarged text, coarse pointers,
reduced motion, and loading-scroll behavior still need a dedicated pass.

Check 1440px, 600px, 390px, and 320px widths, enlarged text, keyboard navigation,
coarse pointer targets, and reduced motion. Verify loading doesn't move the main
document, disclosures remain local, and Ask initiates research. Existing automated
suite is Python-focused; there is no established browser test runner.

### 2. Reduce card framing and refine nesting

Start with era units as open editorial chapters; use heading, date range, alignment,
and whitespace for boundaries. Keep show/performance identities, notes, listening,
and evidence attached. Avoid nested boxes for era > show > performance. Existing
semantic cards intentionally remain in the first batch to keep the change focused.

Era units now render without the shared card frame. Consecutive stages use an
open heading, their model-supplied span, and a restrained divider with generous
whitespace; listening and evidence remain in their respective stage. Shows,
performances, and records keep their identity frames because they are discrete
objects rather than editorial chapters. Reviewed with the Eyes fixture at desktop
and phone widths.

Acceptance: chronology looks like progression and collections like peers before
reading the prose. Do not infer a timeline from adjacent dates; render relationships
chosen by the model. Retain enclosure for distinct asides and bounded interactions.

### 3. Model-selected disclosure and semantic relationships

Current ShowUnit disclosure is still chosen in the renderer from item count and
anchor role. Extend the contract to let the model choose relevant facets and initial
disclosure. Keep user expansion state stable and important qualifications visible.
Do not hydrate every known fact into a mandatory visible panel.

`show_explorer.organization` (retired in the palette cut) currently changes a label, not the spatial arrangement.
Add a small group grammar for collection, sequence, comparison, and argument/evidence.
Model controls group title, membership, reading order, emphasis and presentation;
runtime validates references and renders supported layouts. Comparison should align
shared criteria; evidence should stay attached to the claim it supports.

Remove `deadbot/finish.py`'s first-eight-primary/later-supporting assignment. Block
count is a transport concern and must not give content secondary editorial meaning.
Avoid keyword routing, automatic duplicate suppression, forced coverage copy, or
another model handoff. Diagnose weak choices through context/prompt/evaluation.

Initial implementation: `finish_response` now accepts model-selected groups
with collection, sequence, comparison, or argument presentation; a group owns
its title, lead, membership, and reading order. Resolution validates references
but preserves that ordering, and the browser renders the selected relationship
without re-grouping it. Comparison groups use aligned peer cards at wide sizes;
argument groups visually keep their lead with the evidence. The former automatic
first-eight/later-supporting layout has been removed.

Show units now accept `visible_facets` and `setlist_disclosure`. The composer
can retain only guests, listening, setlist, and/or source evidence that help the
answer, and chooses whether the selected setlist begins expanded, collapsed, or
hidden. Native disclosure state stays with the visitor after they open it.
`show_explorer` (retired in the palette cut) remains compatible for older calls, but new composition guidance
uses groups with directly selected units so the model controls the relationship
and ordering.

Song overviews can now be primary units as well: the composer supplies each
song's local interpretation and selected representative performance IDs, while
the runtime preserves their ordering and attaches the verified direct recording
path for each. This lets a song-centered comparison use distinct, explorable
song units rather than compressing several live stories into one fact grid.

Acceptance: one schema supports genuinely different collection, development, and
argument compositions; reference resolution preserves model-selected order/grouping.

### 4. Opening outline and editorial roles

Add optional model-selected group outline with stable local anchors. Derive navigation
from the same group structure; do not generate a second interpretation or duplicate
the answer. Encourage concise titles and leads via composer context, without rejecting
long titles. Express anchor/contrast roles through emphasis/relationships rather than
relying on visitor-facing internal badges such as Supporting.

### 5. Preserve exploration across turns

Current App stores only one response; follow-ups replace it. Add experience history
with presentation identifiers, originating question/object, scroll position and
disclosure state. Same canonical performance may appear in different editorial
contexts. Keep conversation state separate from the historical page being viewed,
so asking from an old page doesn't submit a stale transcript. Provide a clear return
path and verify restoration after a contextual follow-up.

## Validation and delivery

For schema changes, export OpenAPI with `scripts/export_openapi.py`, regenerate
frontend types with `npm run gen:types --prefix web`, and check for drift.
For this batch: run `pytest tests/test_finish.py tests/test_experience.py`, frontend
build, and browser review. GitHub CI additionally runs the complete Python suite,
database import/evaluations, schema drift, and web build. Record any remaining CI
or deployment failures rather than assuming a merge means deployment succeeded.

The user explicitly requested commit, push, PR and merge for this batch. Future agents
should follow the current user's authorization and the repository instructions for
subsequent delivery. Avoid overwriting modifications in the separate Development clone.

## Validation completed for the first batch

- 52 targeted Python tests passed (`tests/test_finish.py`, `tests/test_experience.py`).
- Production frontend build passed; whitespace/diff checks passed.
- Browser reviewed the actual App with temporary illustrative fixtures at desktop
  1440px and phone 390px. Confirmed title/first-unit visibility, show recording
  placement, missing-link identity, numbered setlist, and mobile View answer focus.
- Intermediate-width and full keyboard/streaming-position verification remain in
  the broader visual acceptance task above. No claim of a complete accessibility audit.
- Independent review caught metadata CSS applying to the new identity wrappers;
  those selectors were narrowed before delivery.

## Validation completed for listening pathways and album reconciliation

- 132 focused Python tests passed across canonical data, composition/finish,
  research tools, Postgres ordering, and recording normalization. A follow-up
  priority-queue snapshot refresh passed 49 relevant tests.
- OpenAPI export and frontend type generation had no drift; the production web
  build passed.
- GitHub CI passed Python (including database import and `deadbot evaluate`), web,
  and preview checks before PR #17 merged. The Dark Star coverage snapshot now
  reflects 71 distinct recordings and 72 linked performances.

## Batch: answer card fixes (September 8, 2026)

- Role badges and group presentation eyebrows are no longer rendered; a visitor
  sees the content, not an internal label naming its role.
- `EditorialItem` slots in `deadbot/experience.py` are named and documented by
  what the visitor sees on the page, not by internal composition mechanics.
- The fact grid renders the subject as a serif heading in both the marker and
  no-marker case, and gives a value display type only when that value is 20
  characters or fewer.
- The album unit leads with the model's own note, then listen actions and
  "Listen for" highlights, with a compact two-column body: tracklist on the
  left, personnel grouped per person in one collapsed disclosure on the right.
- The content pane shows a working panel while a question is pending, and the
  API now emits a "Composing the page" status the moment the chat answer
  completes; the finish tool's own status changed to "Assembling the page" so
  the two no longer collide.

## Next: knob audit and emphasis

Diagnosis (Wake of the Flood, local canonical store, no database): `get_album`
attaches a `pathways` object to every release, but a release can only ever
report `cataloged: false` plus two generic `research_routes` ("Dead.net",
"Dead Sources"). No `resource_releases.csv` exists in `data/canonical`, and
`pathways_for` never builds a `source_trail` or `selections` summary for
releases the way it does for songs and shows. Separately, `search_entities`
caps pathway attachment at the first six matches overall, and songs from the
record's own tracklist filled that cap before the release match got a
`pathways` key at all. So a release can lose its pathway entirely in search,
and even read directly through `get_album` it only ever offers the same two
research routes, never a cataloged one. The prompt says a research-routes-only
pathway should still become a follow_up; nothing enforces that if skipped.

Agreed direction: every field in `FinishPlan` must change what the visitor sees
or be removed. Roles become an emphasis axis (lead, supporting, mention) instead
of a labeled badge. Group presentations gain distinct layouts instead of one
shared list style. Add progressive page streaming so later units arrive without
blocking the first read. Design fixtures first for four question shapes (song,
show, album, person) before touching the schema again.

Completed by the emphasis and palette cut batch: `role` on a unit is deprecated
in favor of a three-level `emphasis` (primary, supporting, mention); comparison
groups carry `criteria` and units carry per-criterion `judgments`; `mode`,
`body`, `layout` and `show_explorer` are removed, and seven former
single-dimension components are folded into unit facets instead (show:
lineup, recordings; song: history); the renderer has emphasis anatomy and
relationship layouts; the prompt was rewritten around emphasis and facets;
releases gained `song_lore` pathways.

What remains: removing `role` from the plan entirely after one release now that
callers have had a chance to move to `emphasis`; a manual rerun of
`evals/editorial-scope-v1.json` judged against the experience brief.

## Batch: progressive page streaming (September 9, 2026)

- `/api/experience/stream` now scans the model's `finish_response` call as it
  is written and emits `page_head`, then per group `group_open`, hydrated
  `block` events (each resolved through `finish.resolve_items` as it streams),
  and `group_close`, ahead of the final `response` event.
- The browser builds the page from these events instead of waiting for
  `response`; a development-only `?stream=<fixture>` mode replays a visual
  fixture as a timed event sequence for review without a model call.
- `scripts/trace_stream.py` times a live request: seconds to first answer
  text, answer complete, first block, last block, and final response.

Live trace run: conditions are local API against the production database, OpenAI gpt-5.6-luna, 12 tool rounds, response cache off, one run per question on 2026-09-09. Seconds from request start.

| Question | First answer text | Answer complete | First block | Last block | Response |
| --- | --- | --- | --- | --- | --- |
| Branford | 10.1 | 10.8 | 11.7 | 13.6 | 14.2 |
| Franklin's Tower best versions | 20.9 | 22.6 | 25.8 | 33.5 | 33.9 |
| American Beauty live legacy | 15.4 | 36.8 | 19.5 | 42.7 | 42.9 |

The first block reaches the browser 1 to 4 seconds after the chat answer completes, and the page fills over the following 2 to 23 seconds instead of appearing all at once when the response lands. In the American Beauty run the answer-complete mark was recorded after the first block, which is consistent with a finish retry resetting the draft partway through.

## Batch: post-launch frontend fixes (September 9, 2026)

Owner feedback after the streaming launch, frontend half. The prompt and tool
half (plain facts without coverage caveats, guest questions answered with show
units and insight) is the next batch.

- The end-of-stream flash was not a remount. When the final `response` landed,
  `composing` flipped false in the same commit, and a sole primary unit's facet
  disclosures (setlist, lineup, recordings, tracklist, credits, history) were
  controlled by that flag, so they snapped open together. Facets now decide
  once, when they first appear, whether to start open (`Facet` in `App.tsx`);
  later renders leave them alone. Trade-off: a sole-unit answer that streamed
  in keeps its facets collapsed, one click to open. Plain, cached and fixture
  responses still open them, as before.
- Blocks are keyed by unit identity rather than position, so a streamed block
  and its final counterpart are the same element even if the two passes ever
  diverge. Verified with a mutation observer over a `?stream=album` replay: the
  card was added once, never removed, and no `open` attribute changed.
- Criteria groups (Texture, Band interaction, and so on) are separated by the
  1rem token while label and text stay 0.25rem apart. The four duplicated
  small-caps label rules share one rule.
- The before / this performance / after strip uses three equal columns in the
  first/last endpoint pattern, one typeface and size, titles aligned at the
  top, the current song in the highlight color.
- The renderer no longer prints "documented" ("N shows", "N performances",
  "key of B").
- New `?fixture=performance`: one primary performance unit judged on four
  criteria with set neighbors, for reviewing the card at full width.

## Measurements

| Date | Change | finish_response schema (chars / approx tokens) |
| --- | --- | --- |
| 2026-09-09 | baseline before the emphasis and palette cut | 28022 / 7005 |
| 2026-09-09 | after the emphasis and palette cut | 24418 / 6104 |

Live finish-call timing, 2026-09-09: three questions run once each against this
worktree's code, provider openai, model gpt-5.6-luna, using the main checkout's
`.env` for `OPENAI_API_KEY` and `DEADBOT_DATABASE_URL` (this shell has neither
on its own).

| Question | Finish call wall time since the last tool result (s) | Finish call output tokens | Total wall time (s) |
| --- | --- | --- | --- |
| Was Branford on the whole 1991-09-10 Madison Square Garden show, and where should I listen for him? | 16.93 | 1514 | 37.43 |
| What are the best versions of Franklin's Tower? | 20.47 | 1697 | 53.70 |
| What was the live legacy of American Beauty? | 19.21 | 1871 | 36.50 |

The finish-call time did not fall with the smaller schema; plan output length
(about 1500 to 1900 tokens per call) is the dominant cost, so the next latency
lever is shorter plans or progressive page streaming.
