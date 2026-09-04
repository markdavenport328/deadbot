# Semantic experience units — design

Date: 2026-09-04. Owner brief: refactor page composition so the model
declares the meaningful objects of an answer and the application hydrates
and renders them. See `AGENTS.md` for the working principles this follows.

## How composition works today

One model owns the turn (`deadbot/graph.py`). It researches with read-only
tools and ends by calling `finish_response`, whose arguments are a
`FinishPlan` (`deadbot/finish.py`): chat answer, title, lead, mode, and a
`body` of up to twelve items. A body item is either an `EditorialBlock` the
model writes (narrative, fact grid, timeline) or a thin reference to a
library component by canonical ID (`show_setlist`, `recording_list`,
`media_link`, `performance_spine`, `comparison_strip`, ...).

`finish.resolve_body` turns each reference into a browser block by projecting
the store through the builders in `deadbot/composition.py`. The browser
schema (`deadbot/experience.py`) is flat: no block contains another block,
and the model does not control layout. `_layout` chunks blocks into groups
of eight.

## Why it groups by data type

The model never authors a library block, so there is no place inside a
setlist, recording list or media link for "why this show matters here". The
only prose slot is a separate editorial block. With a flat vocabulary of
single-dimension components, the rational composition of "five Branford
shows" is one list of shows, one run of setlists, one run of recordings: the
schema makes the perceptual unit "one show, with everything about it"
inexpressible. The prompt's instruction "everything about one object goes in
one block" cannot be followed for any object richer than a paragraph.

Two smaller gaps compound it: the setlist projection cannot mark which songs
matter, and songs in a setlist have no listening action even though the
library has per-performance archive track links.

## Decisions

1. **Add semantic units as body items** the model can declare. Four, chosen
   from what the current data can hydrate and what the representative
   questions need:
   - `show_unit` — one show is a primary object of this answer.
   - `performance_unit` — one rendition is a primary object.
   - `era_unit` — a stage of a development the model names, with
     representative performances as evidence and listening.
   - `show_explorer` — a collection of show units with an organization.
   Not added: `comparison_unit` (fact_grid and comparison_strip already
   serve it), `argument_unit` (narrative plus units and evidence serve it),
   `musician_unit` (guest_appearance_list serves it). These can be added
   later if real answers show the need.
2. **The model supplies interpretation, the server supplies facts.** A unit
   reference carries an ID, an optional `role`, a `note`, highlighted
   performance IDs, a preferred recording, supporting sources and a
   follow-up. Date, venue, location, setlist, song titles, listening URLs,
   release metadata and set neighbors are hydrated from the store.
3. **Roles are a small closed vocabulary**: anchor, supporting, contrast,
   turning_point, outlier, culmination, overlooked, representative. The
   renderer may use them; the model never specifies styling.
4. **Evidence is referenced by URL.** Every evidence-bearing tool (stored
   resources, research records, site search hits, read pages, archive
   reviews) returns a URL, and URL grounding already exists. A supporting
   source is `{url, note?}`; the server keeps it only when the URL came from
   this turn's tool output and hydrates its label from the payload that
   returned it.
5. **Actions attach to objects.** A show unit carries listen actions
   (preferred recording, full-show stream or archive listing, official
   release). Setlist songs carry a per-performance listen URL where the
   library has one, in both `show_unit` and the standalone `show_setlist`.
   A performance unit carries "play this performance" and "hear the show".
6. **Show payloads gain per-performance listening paths**, as song payloads
   already have, so the model sees them and the show unit can hydrate them.
7. **Nesting is typed and one level deep.** `show_explorer` contains
   `show_unit` blocks; nothing else nests. No generic container block.
8. **Existing components stay.** `show_setlist`, `recording_list`,
   `media_link`, `performance_spine` and the rest remain available for
   answers where a single dimension is the answer. The prompt demotes them
   to that role.
9. **Prompt changes are confined to COMPOSING THE EXPERIENCE and ANSWER
   FIRST.** The research, interpretation, organizing-idea, Gestalt,
   discovery and trust sections are preserved.

## Model-facing schema (finish.py)

```
ShowUnitRef        type=show_unit        show_id, role?, note?, highlighted_performance_ids[≤12],
                                         preferred_recording_id?, supporting_sources[≤4], follow_up?, title?
PerformanceUnitRef type=performance_unit performance_id, role?, note?, supporting_sources[≤4], follow_up?
EraUnitRef         type=era_unit         title, span?, note?, representative_performance_ids[1..6],
                                         supporting_sources[≤4], follow_up?
ShowExplorerRef    type=show_explorer    title?, organization ∈ {chronological, curated, comparative},
                                         items: ShowUnitRef[1..8]
SupportingSource   url, note?
```

Grounding rules: a show or performance ID must appear in this turn's tool
output (the existing rule). Highlighted performance IDs and the preferred
recording must belong to the unit's show; others are dropped. A supporting
source URL must appear in this turn's tool output.

## Browser-facing schema (experience.py)

```
ListenAction     label, url, provider, is_official
UnitSource       url, label, source_name?, note?
SetlistSong      + highlighted: bool = False, listen_url: str | None
ShowUnitBlock    show_id, show_date, venue_name?, location?, role?, note?, sets[], setlist_note?,
                 guests[PerformerItem], listen[ListenAction ≤4], sources[UnitSource ≤4], follow_up?, title?
PerformanceUnitBlock
                 performance_id, song_id, song_title, show_id, show_date, show_label, venue_name?, location?,
                 set_label?, position_in_set?, role?, note?, previous?, next? (PerformanceSpineNeighbor),
                 listen[ListenAction ≤3], sources, follow_up?
EraUnitBlock     title, span?, role?, note?, performances[EraPerformanceItem 1..6], sources, follow_up?
EraPerformanceItem performance_id, song_title, show_id, show_date, show_label, set_label?, listen?: ListenAction, follow_up
ShowExplorerBlock title, organization, items: ShowUnitBlock[1..8]
```

## Renderer (web/src/App.tsx)

`ShowUnit`, `PerformanceUnit`, `EraUnit` and `ShowExplorer` components.
A show unit is one card: date and venue as the heading, location, a role
chip when present, the note, guests, the setlist with highlighted songs
marked and every song with a listen URL playable, the listen actions, the
sources, and the follow-up. Inside an explorer, an anchor's setlist is open
and other units' setlists are collapsed behind a disclosure, with
highlighted songs always visible. The standalone setlist renderer gains the
per-song listen link.

## Prompt

COMPOSING THE EXPERIENCE is rewritten around: first decide the major units
of this answer; group by meaning and referent, not by tool or data type;
declare units and their significance and let the renderer hydrate them; use
single-dimension components only when one dimension is the answer; keep
page-level synthesis (patterns across units) in editorial blocks and
unit-level information inside units. ANSWER FIRST stops asking for the list
in chat when the body presents the same objects as units.

## Tests

Plan validation for each unit; hydration of a show unit (identity, sets,
highlights, listen order with preferred recording first, guest lineup,
source grounding); explorer nesting and dropping; performance unit spine and
play action; era unit representative performances; setlist listen URLs;
show payload listen paths; prompt content; nested schema validation through
the API. Schema export and type generation must be regenerated.

## Limitations accepted in this pass

No comparison, argument or musician units. No per-highlight notes. Layout
regions still chunk mechanically. Real-model evaluation of the five
representative prompts depends on a configured provider and is reported
separately from the deterministic tests.
