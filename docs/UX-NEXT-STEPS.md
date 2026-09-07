# Deadbot UX continuation — September 6, 2026

## Start here

Read `AGENTS.md` and this file before continuing UX work. The user approved the
prioritized plan below and asked for implementation in reviewable batches.
Preserve model ownership of selection, interpretation, ordering, grouping, and
omission. One model delivers the whole turn through `finish_response`.

## Repository reconciliation

There are two separate clones of the same GitHub repository:

- `/Users/markdavenport/Development/Deadbot`: was already at `079f4cb` (PR #13).
  Two generated TypeScript build-info files were modified. This clone was not changed.
- `/Users/markdavenport/Documents/Claude/Personal/DeadBot`: this task's workspace,
  initially at `94c1d44` (PR #10), clean. Safely fast-forwarded to `079f4cb`, then
  created `codex/experience-readability`. No hard reset was used.

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

## Remaining work, in priority order

### 1. Broaden visual acceptance coverage

Use fixed validated responses (not live model generation) for visual comparisons:
Branford collection, Eyes development, Cornell argument, three Shakedown
recommendations, and a compact fact. Include long titles/venues, missing links,
multiple recordings, highlights, sources, and expanded setlists. First batch used
temporary local-only fixture entries with the actual App and mocked API; these
were removed before delivery. A reusable development-only fixture harness would
make subsequent review repeatable without adding product UI or calling an LLM.

Check 1440px, 600px, 390px, and 320px widths, enlarged text, keyboard navigation,
coarse pointer targets, and reduced motion. Verify loading doesn't move the main
document, disclosures remain local, and Ask initiates research. Existing automated
suite is Python-focused; there is no established browser test runner.

### 2. Reduce card framing and refine nesting

Start with era units as open editorial chapters; use heading, date range, alignment,
and whitespace for boundaries. Keep show/performance identities, notes, listening,
and evidence attached. Avoid nested boxes for era > show > performance. Existing
semantic cards intentionally remain in the first batch to keep the change focused.

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
