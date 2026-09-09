# Emphasis and palette cut

Design for the batch after PR #28. Agreed direction: insight leads, inventory
follows; every choice the model makes must change what the visitor sees; the
model composes meaning and the runtime owns form; a smaller plan is a faster
plan.

## Problem

`finish_response` gives the model roughly fifteen kinds of choice. After PR #28
only about half of them alter the page:

| Choice | Visible effect today |
| --- | --- |
| `role` (8 values) on each unit | `anchor` changes a border color. Nothing else. |
| `mode` (8 values) | One eyebrow word above the page title. |
| Group `presentation` (4 values) | Comparison splits units into two columns; argument adds a gold rule to the heading; sequence widens a gap; collection is the default. |
| `show_explorer.organization` | Nothing (its label was removed). |
| Legacy `body` | Same as one untitled collection group. |
| `layout` in the response | Ignored by the renderer. |
| `show_setlist`, `performer_list`, `recording_list`, `performance_list`, `performance_extremes`, `comparison_strip`, `performance_spine` | Table-shaped duplicates of facets that `show_unit` and `song_overview` already carry or could carry. |

Three costs follow. The model spends output tokens on decisions with no
consequence, and the finish call is already the largest single latency cost at
17 to 20 seconds. Pages come out with little hierarchy because nothing in the
schema says which object is the point. And the palette promises variety the
renderer cannot deliver, which misleads both the model and us.

## Goals

1. Every field in `FinishPlan` changes what the visitor sees, or it is removed.
2. A page has legible hierarchy: the lead object is unmistakable, supporting
   objects are compact, mentions are a line. (The values are primary, supporting
   and mention; "lead" is avoided because the page and group `lead` fields are
   prose.)
3. The four relationships (peers, order, contrast, claim and evidence) look
   different from each other without the model choosing layout.
4. The finish schema and a typical rich plan both shrink measurably.
5. Releases carry pathways so an album answer can offer a follow-up.

Non-goals for this batch: progressive page streaming (separate spec),
conversation history across turns, any new data collection.

## The model's job after this change

For each answer the model decides:

- **The finding**: `chat_answer`, `title`, optional `lead`. Unchanged.
- **The objects**: which shows, performances, records, songs and eras earn a
  place; for each, an `emphasis`, a `note`, the facets worth showing,
  highlights, sources, and an optional `follow_up`.
- **The relationships**: one or more groups, each with a `presentation`, an
  optional `title` and `lead`, and membership in reading order. A comparison
  group may name shared `criteria`, and each unit in it may supply a short
  `judgments` list aligned to those criteria.
- **Prose**: narrative, fact grid, and timeline blocks as today.

The model never chooses layout, disclosure defaults beyond a setlist, labels,
or a page mode.

## The runtime's job

Resolve references and drop ungrounded ones (unchanged). Hydrate each unit's
facts. Render each emphasis level, each relationship, and each facet with one
fixed anatomy. Degrade gracefully when a choice does not fit the space. Set the
response's `mode` itself (`answer` or `gap`). Never add copy the model did not
write.

## Schema changes

All changes are in `deadbot/finish.py` (model-facing plan) and
`deadbot/experience.py` (browser-facing response). `schema_version` becomes
`"2"`. OpenAPI and TypeScript types are regenerated.

### Emphasis replaces role

On `ShowUnitRef`, `PerformanceUnitRef`, `AlbumUnitRef`, and `SongOverviewRef`:

```python
emphasis: Literal["primary", "supporting", "mention"] = Field(
    default="supporting",
    description=(
        "How much of the page this object earns. primary: the object the answer is about; "
        "renders full width with its selected facets open. supporting: a peer or piece of "
        "evidence; renders as a compact card with its note, listening and highlights. "
        "mention: a name the visitor may want to follow; renders as one line with a listen link."
    ),
)
```

`EraUnitRef` keeps no emphasis; eras are chapters, not objects.

`role` stays accepted on the plan for one release so in-flight prompts and
cached plans still validate. Resolution maps `anchor` to `primary` and every other
role to `supporting` when `emphasis` is omitted, then drops `role`. The
response blocks carry `emphasis` and no `role`. The prompt stops describing
roles. A follow-up release removes `role` from the plan schema.

### Groups gain form

`GroupPlan.presentation` keeps its four values. Two additions:

```python
criteria: list[str] = Field(default_factory=list, max_length=5,
    description="For a comparison only: the shared terms the items are judged on, in order, as short labels such as 'Tempo' or 'Second-set jam'.")
```

On the four object unit refs:

```python
judgments: list[str] = Field(default_factory=list, max_length=5,
    description="For a unit inside a comparison group: your one-line judgment for each of the group's criteria, in the same order. Leave an entry empty when you have nothing grounded to say.")
```

`ExperienceGroup` carries `criteria`; unit blocks carry `judgments`. Resolution
truncates `judgments` to `len(criteria)` and never fills gaps.

### Removals

- `FinishPlan.mode` is removed. `ExperienceResponse.mode` becomes
  `Literal["answer", "gap"]`, set by the server. The response cache continues to
  skip `gap`. Eval case files drop `expected.mode` except where it is `gap`.
- `FinishPlan.body` is removed. `groups` is the only body. An answer with no
  main body is an empty `groups` list.
- `ShowExplorerRef`, `ShowExplorerBlock`, and `UnitOrganization` are removed.
- `ExperienceResponse.layout` and `LayoutSection` are removed.
- These refs and blocks are removed: `show_setlist`, `performer_list`,
  `recording_list`, `performance_list`, `performance_extremes`,
  `comparison_strip`, `performance_spine`. Their content becomes facets below.
- `UnitRole` is removed from the response; it remains in the plan only for the
  compatibility mapping.

### Facets absorb the single-dimension components

`ShowUnitRef.visible_facets` accepts `guests`, `listen`, `setlist`, `sources`,
`lineup`, `recordings`. `lineup` hydrates the full performer list with
instruments; `recordings` hydrates the complete recording inventory with source
type and archive identifier. Both render inside the unit, collapsed by default,
under the same disclosure styling as a collapsed setlist. `ShowUnitBlock` gains
`lineup` and `recordings` lists.

`SongOverviewRef` gains `visible_facets` accepting `credits`, `albums`,
`history`, `representatives`, default `["representatives"]`. `history`
hydrates what `performance_extremes` and `comparison_strip` produced: first and
last documented performances, the count, and one representative per year with
listen links, rendered as one facet. `SongOverviewBlock` gains `history`.

`PerformanceUnit` already renders set neighbors, which is what
`performance_spine` did.

`equipment_list`, `guest_appearance_list`, `show_selection`, `arrangement`,
`arrangement_search`, `media_link`, and `resource_list` stay. They describe
objects that have no parent unit.

## Rendering

`web/src/App.tsx` and `web/src/styles.css`. The palette and spacing tokens are
unchanged.

### Emphasis anatomy

- **primary**: spans the full grid. Heading, note, listen actions, highlights, then
  selected facets. A setlist follows its `setlist_disclosure`. Other facets
  start collapsed except when the unit is the only unit on the page, in which
  case selected facets start open. Border uses the current anchor color.
- **supporting**: spans six columns at 861px and wider, twelve below. Heading,
  note, compact listen actions, highlights. Any selected facet renders
  collapsed. Personnel and tracklist on an album collapse.
- **mention**: no card frame. One row: identity as a listening label when a
  direct link exists, the note after a middle dot, and a compact listen action.
  Consecutive mentions in a group render as one list with hairline separators.

### Relationship layouts

- **collection**: an equal-weight grid. Lead units span twelve columns;
  supporting units pair up; mentions list. No ordinals.
- **sequence**: a numbered spine. Each item gets an ordinal in the left gutter
  and a vertical rule connects them; items span twelve columns. Eras inside a
  sequence keep their open chapter styling and take the ordinal.
- **comparison**: aligned columns. Units share one row at 861px and wider, up
  to three across, then wrap. When `criteria` exist, every unit renders a
  criteria table in the same order directly under its note, so rows line up
  across columns. Empty judgments render an empty cell.
- **argument**: the group `lead` renders as the claim in a callout with the
  existing gold rule, in the large lead type. Evidence units render beneath,
  indented under the rule, so the claim and its support read as one shape.

Group headings render title and lead only; there are still no presentation
labels.

### Content pane header

The mode eyebrow above the page title goes away. The title stands alone.

## Prompt

`deadbot/graph.py`, section "Composing the experience". Replace the role
sentence and the `show_explorer` mention with the emphasis vocabulary and the
four relationships. Describe facets by what the visitor sees. Keep the
affirmative voice. Remove every mention of `mode`. The single-dimension
paragraph shrinks to the standalone components that remain.

## Release pathways

`deadbot/tools.py` and `deadbot/pathways.py`.

- `search_entities` caps pathway attachment at six entities but fills the cap
  in match order, so a record's own tracks crowd out the record. Change the cap
  to at most two entities per type, six total, so a release, a show and a song
  each get pathways when they appear.
- `pathways_for` returns `cataloged: false` for every release because no
  release resources exist. Add a `song_lore` list to a release's pathways: up
  to six track titles that have cataloged resources, with their song ids, so
  the model can point a follow-up at the track that has a story. Releases keep
  their research routes.

## Measurement

Before and after, using the trace script pattern from the latency work:

| Measure | Method |
| --- | --- |
| Finish tool schema size | Token count of the bound tool definition |
| Plan size | Output tokens of the `finish_response` call |
| Finish call time | Wall clock from last tool result to finish call complete |

Questions: Branford, Franklin's Tower best versions, American Beauty live
legacy. Record the numbers in `docs/UX-NEXT-STEPS.md`.

## Fixture-first check

Before implementation, hand-write the ideal page as fixture JSON for four
shapes: a compact fact (release date of American Beauty), a record's live
legacy, a song's evolution across eras, and "what do people say about the last
show." Each must be expressible in the new schema. Where it is not, the schema
changes here are revised before code is written. After implementation these
four become permanent fixtures in `web/src/visual-fixtures.ts`, replacing
overlapping ones.

## Testing

- `tests/test_finish.py`: role to emphasis mapping; `judgments` truncation to
  `criteria`; removed refs rejected by validation; `mode` set to `gap` when no
  plan; new facets hydrate and are dropped when unselected.
- `tests/test_experience.py`: schema version 2; streaming endpoint unchanged.
- `tests/test_graph.py`: prompt mentions emphasis and no longer mentions roles
  or mode, if the file tests prompt content.
- Evals: rerun `evals/editorial-scope-v1.json` manually and judge the four
  cases against the brief's six questions.
- Web: `npm run build --prefix web`; fixtures reviewed at 1440px and 375px.
- OpenAPI export and type generation with no drift.

## Compatibility and rollout

One release with `role` accepted and mapped. The response cache key includes
the deployment commit, so cached version 1 responses are not served after
deploy. No database change. Vercel `maxDuration` is untouched; the measured
finish time is the signal for whether the cut is paying off.

## Sequence

1. Fixture-first check and any schema revision.
2. Schema: emphasis, criteria and judgments, removals, facets; regenerate types.
3. Resolution: mapping, truncation, new facet hydration; tests.
4. Renderer: emphasis anatomy, relationship layouts, facets, header.
5. Prompt.
6. Release pathways.
7. Measurement and docs.
