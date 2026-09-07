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
They DO exist in current main: show_unit, performance_unit, era_unit, show_explorer,
attached listening, highlighted songs, Ask chips, and peer-show setlist disclosure.
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
`shakedown`, or `fact` to the local URL. It loads through the actual App
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

`show_explorer.organization` currently changes a label, not the spatial arrangement.
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
`show_explorer` remains compatible for older calls, but new composition guidance
uses groups with directly selected units so the model controls the relationship
and ordering.

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
