# Emphasis and Palette Cut Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make every choice in `finish_response` change what the visitor sees, give pages legible hierarchy through a three-level emphasis axis and four distinct relationship layouts, shrink the finish schema, and let releases carry lore pathways.

**Architecture:** The model composes meaning (finding, objects with emphasis and notes, relationships, prose) through the `finish_response` Pydantic schema in `deadbot/finish.py`; the server resolves references and hydrates facts in `deadbot/finish.py` and `deadbot/composition.py` into the browser contract in `deadbot/experience.py`; the React renderer in `web/src/App.tsx` owns all form. This batch removes plan fields with no visible effect, replaces `role` with `emphasis`, adds comparison `criteria`/`judgments`, folds seven table-shaped components into unit facets, gives each relationship a layout, and fixes release pathways in `deadbot/pathways.py` and `deadbot/tools.py`.

**Tech Stack:** Python 3.11, Pydantic v2, FastAPI, LangGraph; React 18 + TypeScript + Vite; pytest; `openapi-typescript` for the generated contract.

**Spec:** `docs/superpowers/specs/2026-09-08-emphasis-and-palette-cut-design.md`

## Global Constraints

- Deterministic code is transport, structural integrity and form. It never chooses content, adds copy the model did not write, or routes on keywords (`AGENTS.md`).
- Emphasis values are exactly `primary`, `supporting`, `mention`; default `supporting`. `role` stays accepted on the plan for one release and maps `anchor` to `primary`, everything else to `supporting`; response blocks carry `emphasis` and no `role`.
- `schema_version` becomes `"2"`. `ExperienceResponse.mode` becomes `Literal["answer", "gap"]`, server-set. `FinishPlan` loses `mode` and `body`. `layout`, `LayoutSection`, `ShowExplorerBlock`/`ShowExplorerRef`, `UnitOrganization`, and the refs/blocks `show_setlist`, `performer_list`, `recording_list`, `performance_list`, `performance_extremes`, `comparison_strip`, `performance_spine` are removed.
- Show facets: `guests`, `listen`, `setlist`, `sources`, `lineup`, `recordings`. Song facets: `credits`, `albums`, `history`, `representatives`, default `["representatives"]`.
- `GroupPlan.criteria` max 5; unit `judgments` max 5, truncated to `len(criteria)`, gaps never filled.
- Python: `PY=/Users/markdavenport/Development/DeadBot/.venv/bin/python`, run from the worktree root. Tests: `$PY -m pytest <files> -q`.
- Whenever `deadbot/experience.py` or `deadbot/finish.py` schema changes: `$PY scripts/export_openapi.py` then `npm run gen:types --prefix web`; commit `web/openapi.json` and `web/src/generated/api.ts`. CI fails on drift.
- Web: `npm run build --prefix web` must pass at the end of every frontend task. Fixtures in `web/src/visual-fixtures.ts` are the review surface (`?fixture=<name>` in Vite dev).
- Palette and spacing tokens in `web/src/styles.css` are the design system; no new colors. User-facing copy: plain words, no em-dashes.
- Do not push. Commit locally; every commit message ends with `Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>`.
- Sequence note: the spec's fixture-first check runs as Task 6, immediately after the contract exists, and gates Tasks 7 to 11. If a fixture cannot be expressed, the implementer reports BLOCKED and the controller revises the schema before continuing.

---

### Task 1: Measurement script and baseline

**Files:**
- Create: `scripts/measure_finish_schema.py`
- Modify: `docs/UX-NEXT-STEPS.md` (append a "Measurements" section)
- Test: `tests/test_measure_finish_schema.py`

**Interfaces:**
- Produces: `measure_finish_schema.schema_size() -> dict[str, int]` with keys `chars` and `approx_tokens` (`chars // 4`).

- [ ] **Step 1: Write the failing test**

```python
# tests/test_measure_finish_schema.py
from scripts.measure_finish_schema import schema_size


def test_schema_size_reports_chars_and_tokens_for_the_finish_tool():
    size = schema_size()
    assert size["chars"] > 1000
    assert size["approx_tokens"] == size["chars"] // 4
```

- [ ] **Step 2: Run it to verify it fails**

Run: `$PY -m pytest tests/test_measure_finish_schema.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'scripts.measure_finish_schema'` (add an empty `scripts/__init__.py` if `scripts` is not importable; check with `ls scripts/__init__.py` first).

- [ ] **Step 3: Write the script**

```python
# scripts/measure_finish_schema.py
"""Report the size of the finish_response tool schema the model sees each call."""

from __future__ import annotations

import json

from deadbot.finish import build_finish_tool


def schema_size() -> dict[str, int]:
    tool = build_finish_tool()
    schema = tool.args_schema.model_json_schema()
    text = json.dumps({"name": tool.name, "description": tool.description, "parameters": schema}, separators=(",", ":"))
    chars = len(text)
    return {"chars": chars, "approx_tokens": chars // 4}


if __name__ == "__main__":
    size = schema_size()
    print(f"finish_response schema: {size['chars']} chars, about {size['approx_tokens']} tokens")
```

- [ ] **Step 4: Run the test and the script**

Run: `$PY -m pytest tests/test_measure_finish_schema.py -q && $PY scripts/measure_finish_schema.py`
Expected: PASS, and one line with the baseline numbers.

- [ ] **Step 5: Record the baseline**

Append to `docs/UX-NEXT-STEPS.md`:

```markdown
## Measurements

| Date | Change | finish_response schema (chars / approx tokens) |
| --- | --- | --- |
| 2026-09-09 | baseline before the emphasis and palette cut | <chars> / <tokens> |
```

Replace the placeholders with the script's output.

- [ ] **Step 6: Commit**

```bash
git add scripts/measure_finish_schema.py scripts/__init__.py tests/test_measure_finish_schema.py docs/UX-NEXT-STEPS.md
git commit -m "Measure the finish_response schema size and record the baseline"
```

---

### Task 2: Browser contract version 2

**Files:**
- Modify: `deadbot/experience.py`
- Test: `tests/test_experience.py` (new tests appended)

**Interfaces:**
- Produces, in `deadbot/experience.py`:
  - `Emphasis = Literal["primary", "supporting", "mention"]`
  - `ShowFacet = Literal["guests", "listen", "setlist", "sources", "lineup", "recordings"]`
  - `SongFacet = Literal["credits", "albums", "history", "representatives"]`
  - `ExperienceMode = Literal["answer", "gap"]`
  - `class SongHistory(ExperienceModel)`: `known_count: int`, `first: PerformanceListItem`, `last: PerformanceListItem`, `by_year: list[ComparisonStripItem]` (max 12)
  - `ShowUnitBlock`: `emphasis: Emphasis = "supporting"`, `lineup: list[PerformerItem]` (max 24), `recordings: list[RecordingItem]` (max 8), `judgments: list[str]` (max 5); `role` removed; `visible_facets` max 6
  - `PerformanceUnitBlock`, `AlbumUnitBlock`: `emphasis`, `judgments`; `role` removed
  - `SongOverviewBlock`: `emphasis`, `judgments`, `visible_facets: list[SongFacet]`, `history: SongHistory | None`; `role` removed
  - `EraUnitBlock`: `role` removed (no emphasis)
  - `ExperienceGroup.criteria: list[str]` (max 5)
  - `ExperienceResponse.schema_version: Literal["2"] = "2"`, `mode: ExperienceMode = "answer"`, no `layout`
- Removed: `UnitRole`, `UnitOrganization`, `LayoutSection`, `ShowExplorerBlock`, `ShowSetlistBlock`, `RecordingListBlock`, `PerformerListBlock`, `PerformanceListBlock`, `PerformanceExtremesBlock`, `PerformanceSpineBlock`, `ComparisonStripBlock`. Kept: `SetlistSection`, `PerformerItem`, `RecordingItem`, `PerformanceListItem`, `ComparisonStripItem`, `PerformanceSpineNeighbor`, `CoverageBlock`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_experience.py`:

```python
def test_contract_version_two_uses_emphasis_and_server_set_mode():
    from deadbot import experience

    assert experience.ExperienceResponse.model_fields["schema_version"].default == "2"
    assert experience.ExperienceResponse.model_fields["mode"].default == "answer"
    assert "layout" not in experience.ExperienceResponse.model_fields
    for name in ("ShowUnitBlock", "PerformanceUnitBlock", "AlbumUnitBlock", "SongOverviewBlock"):
        fields = getattr(experience, name).model_fields
        assert fields["emphasis"].default == "supporting"
        assert "role" not in fields
        assert "judgments" in fields
    assert "role" not in experience.EraUnitBlock.model_fields
    assert "criteria" in experience.ExperienceGroup.model_fields
    for removed in ("ShowExplorerBlock", "ShowSetlistBlock", "RecordingListBlock", "PerformerListBlock",
                    "PerformanceListBlock", "PerformanceExtremesBlock", "PerformanceSpineBlock",
                    "ComparisonStripBlock", "LayoutSection", "UnitRole", "UnitOrganization"):
        assert not hasattr(experience, removed), removed


def test_show_unit_accepts_lineup_and_recordings_facets_and_song_overview_accepts_history():
    from deadbot import experience

    unit = experience.ShowUnitBlock(
        type="show_unit", show_id="gd-1972-08-27", show_date="1972-08-27",
        visible_facets=["lineup", "recordings"],
        lineup=[experience.PerformerItem(person_id="jerry", name="Jerry Garcia", role="performer", instruments=["guitar"])],
        recordings=[experience.RecordingItem(recording_id="r1", title="SBD", source_type="soundboard", url="https://archive.org/details/x", source_id="recording:r1")],
    )
    assert unit.emphasis == "supporting" and unit.lineup[0].name == "Jerry Garcia"
    item = experience.PerformanceListItem(performance_id="p1", show_id="gd-1972-08-27", show_date="1972-08-27", show_label="1972-08-27 — Veneta")
    song = experience.SongOverviewBlock(
        type="song_overview", song_id="song-sugaree", title="Sugaree", known_performance_count=1,
        emphasis="primary", visible_facets=["history"],
        history=experience.SongHistory(known_count=1, first=item, last=item, by_year=[]),
    )
    assert song.history.first.performance_id == "p1"
```

- [ ] **Step 2: Run them to verify they fail**

Run: `$PY -m pytest tests/test_experience.py -q -k "version_two or lineup_and_recordings"`
Expected: FAIL (`schema_version` default is `"1"`; `emphasis` missing).

- [ ] **Step 3: Edit `deadbot/experience.py`**

Replace the `ExperienceMode` literal (lines 18 to 27) with:

```python
ExperienceMode = Literal["answer", "gap"]
```

Replace the `UnitRole` literal and `UnitOrganization`/`ShowFacet` lines (lines 78 to 92) with:

```python
Emphasis = Literal["primary", "supporting", "mention"]
ShowFacet = Literal["guests", "listen", "setlist", "sources", "lineup", "recordings"]
SongFacet = Literal["credits", "albums", "history", "representatives"]
SetlistDisclosure = Literal["expanded", "collapsed", "hidden"]
GroupPresentation = Literal["collection", "sequence", "comparison", "argument"]
```

Delete the classes `ShowSetlistBlock`, `RecordingListBlock`, `PerformerListBlock`, `ShowExplorerBlock`, `PerformanceExtremesBlock`, `PerformanceListBlock`, `ComparisonStripBlock`, `PerformanceSpineBlock`, `LayoutSection`. Keep their item models (`SetlistSection`, `RecordingItem`, `PerformerItem`, `PerformanceListItem`, `ComparisonStripItem`, `PerformanceSpineNeighbor`). Move `PerformanceListItem` and `ComparisonStripItem` above `ShowUnitBlock` if they are defined later than where `SongHistory` needs them.

Add after `ComparisonStripItem`:

```python
class SongHistory(ExperienceModel):
    """A song's documented stage life: first, last, and one performance per year."""

    known_count: int = Field(ge=1)
    first: PerformanceListItem
    last: PerformanceListItem
    by_year: list[ComparisonStripItem] = Field(default_factory=list, max_length=12)
```

In `ShowUnitBlock` replace `role: UnitRole | None = None` with `emphasis: Emphasis = "supporting"`, change `visible_facets` to `Field(default_factory=list, max_length=6)`, and add after `guests`:

```python
    lineup: list[PerformerItem] = Field(default_factory=list, max_length=24)
    recordings: list[RecordingItem] = Field(default_factory=list, max_length=8)
    judgments: list[str] = Field(default_factory=list, max_length=5)
```

Update its docstring to say "emphasis" instead of "role".

In `PerformanceUnitBlock` and `AlbumUnitBlock` replace `role: UnitRole | None = None` with:

```python
    emphasis: Emphasis = "supporting"
    judgments: list[str] = Field(default_factory=list, max_length=5)
```

In `EraUnitBlock` delete the `role` line.

In `SongOverviewBlock` replace `role: UnitRole | None = None` with:

```python
    emphasis: Emphasis = "supporting"
    judgments: list[str] = Field(default_factory=list, max_length=5)
    visible_facets: list[SongFacet] = Field(default_factory=lambda: ["representatives"], max_length=4)
    history: SongHistory | None = None
```

In `ExperienceGroup` add `criteria: list[str] = Field(default_factory=list, max_length=5)` after `presentation`.

In `ExperienceResponse`: `schema_version: Literal["2"] = "2"`, `mode: ExperienceMode = "answer"`, delete `layout` and the three comment lines above `blocks` about layout regions (keep `max_length=32`).

Remove the deleted blocks from the `ExperienceBlock` union.

- [ ] **Step 4: Run the new tests**

Run: `$PY -m pytest tests/test_experience.py -q -k "version_two or lineup_and_recordings"`
Expected: PASS. Other tests in the repo will now fail because `finish.py` still imports removed names; that is expected until Task 3.

- [ ] **Step 5: Commit**

```bash
git add deadbot/experience.py tests/test_experience.py
git commit -m "Version the browser contract: emphasis, facets, criteria, server-set mode"
```

---

### Task 3: Plan schema and resolution

**Files:**
- Modify: `deadbot/finish.py`
- Modify: `deadbot/composition.py` (function signatures only: `role` parameter becomes `emphasis`)
- Modify: `deadbot/response_cache.py` (no logic change; confirm `mode == "gap"` still compiles)
- Test: `tests/test_finish.py`, `tests/test_experience.py`

**Interfaces:**
- Consumes: Task 2 names.
- Produces, in `deadbot/finish.py`:
  - `UnitRole = Literal["anchor", "supporting", "contrast", "turning_point", "outlier", "culmination", "overlooked", "representative"]` (plan-only, deprecated)
  - `_emphasis_for(ref) -> Emphasis`
  - Unit refs gain `emphasis: Emphasis | None`, `judgments: list[str]`; keep `role: UnitRole | None`
  - `GroupPlan.criteria: list[str]`
  - `FinishPlan` has `chat_answer`, `title`, `lead`, `groups` only
  - `resolve_items(items, grounded, payloads, store) -> tuple[list[ExperienceBlock], list[SourceReference]]` replaces `resolve_body`
  - `resolve_groups(plan, grounded, payloads, store)` unchanged signature; applies `criteria` and truncates `judgments`
  - `build_experience_response` sets `mode="answer"` or `"gap"`, no `layout`
- Composition hydrators take `emphasis: Emphasis = "supporting"` and `judgments: list[str] | None = None` instead of `role`: `_show_unit`, `_performance_unit`, `_album_unit`, `_song_overview`; `_era_unit` loses `role`.

- [ ] **Step 1: Update the tests first**

In `tests/test_finish.py`:

Replace `test_finish_plan_accepts_editorial_blocks_and_library_references` with:

```python
def test_finish_plan_accepts_editorial_blocks_and_unit_references_in_groups():
    plan = finish.FinishPlan.model_validate(
        {
            "chat_answer": "Sugaree opened the second set.",
            "title": "Sugaree at Veneta",
            "lead": "A relaxed early version.",
            "groups": [
                {
                    "presentation": "collection",
                    "items": [
                        {"type": "editorial", "presentation": "narrative", "title": "Why this one", "paragraphs": ["Garcia stretches the solo."], "items": []},
                        {"type": "show_unit", "show_id": "gd-1972-08-27", "emphasis": "primary", "visible_facets": ["setlist", "recordings"]},
                    ],
                }
            ],
        }
    )
    assert [item.type for item in plan.groups[0].items] == ["editorial", "show_unit"]
    assert plan.groups[0].items[1].emphasis == "primary"
    for field in ("mode", "body"):
        assert field not in finish.FinishPlan.model_fields


def test_finish_plan_rejects_removed_single_dimension_references():
    from pydantic import ValidationError

    for kind in ("show_setlist", "performer_list", "recording_list", "performance_list", "performance_extremes", "comparison_strip", "performance_spine", "show_explorer"):
        try:
            finish.GroupPlan.model_validate({"presentation": "collection", "items": [{"type": kind, "show_id": "x", "song_id": "y", "performance_id": "z", "items": []}]})
        except ValidationError:
            continue
        raise AssertionError(f"{kind} should no longer be accepted")


def test_role_maps_to_emphasis_when_emphasis_is_omitted():
    anchor = finish.ShowUnitRef(type="show_unit", show_id="gd-1972-08-27", role="anchor")
    contrast = finish.ShowUnitRef(type="show_unit", show_id="gd-1972-08-27", role="contrast")
    explicit = finish.ShowUnitRef(type="show_unit", show_id="gd-1972-08-27", role="anchor", emphasis="mention")
    assert finish._emphasis_for(anchor) == "primary"
    assert finish._emphasis_for(contrast) == "supporting"
    assert finish._emphasis_for(explicit) == "mention"
    assert finish._emphasis_for(finish.ShowUnitRef(type="show_unit", show_id="gd-1972-08-27")) == "supporting"
```

Replace `test_finish_tool_uses_the_plan_schema_and_confirms_delivery`'s invoke argument with `{"chat_answer": "Hi", "title": "Deadbot", "lead": None, "groups": []}`.

Replace `test_resolve_groups_preserves_the_models_relationship_and_order` with:

```python
def test_resolve_groups_preserves_order_criteria_and_truncates_judgments():
    store = CanonicalStore()
    payloads = _veneta_payloads(store)
    plan = finish.FinishPlan(
        chat_answer="x",
        title="Veneta",
        groups=[
            finish.GroupPlan(
                title="Two readings",
                lead="Judged on the same terms.",
                presentation="comparison",
                criteria=["Pace", "Jam"],
                items=[
                    finish.ShowUnitRef(type="show_unit", show_id="gd-1972-08-27", emphasis="primary", judgments=["Relaxed", "Long", "Extra"]),
                    finish.SongOverviewRef(type="song_overview", song_id="song-sugaree", judgments=["Steady"]),
                ],
            )
        ],
    )
    blocks, groups, _ = finish.resolve_groups(plan, finish.grounded_context(payloads), payloads, store)
    assert [block.type for block in blocks] == ["show_unit", "song_overview"]
    assert groups[0].presentation == "comparison" and groups[0].criteria == ["Pace", "Jam"]
    assert blocks[0].emphasis == "primary" and blocks[0].judgments == ["Relaxed", "Long"]
    assert blocks[1].emphasis == "supporting" and blocks[1].judgments == ["Steady"]
```

Delete `test_resolve_body_builds_referenced_components_with_model_titles`, `test_resolve_body_builds_the_default_recording_list_when_no_recordings_are_named`, `test_resolve_body_nests_show_units_in_an_explorer_and_drops_unretrieved_shows`, `test_resolve_body_resolves_performance_extremes_and_spine`, `test_performance_lists_and_comparison_strips_link_to_recordings`, `test_show_setlist_songs_carry_listen_links`, and the performer half of `test_resolve_body_resolves_performer_and_equipment_lists_for_a_show` (keep the equipment assertions). Task 4 adds facet tests that cover the same behavior.

Every remaining test that builds a `FinishPlan` with `mode=` or `body=[...]` changes to `groups=[finish.GroupPlan(presentation="collection", items=[...])]`, and every call to `finish.resolve_body(plan, ...)` becomes `finish.resolve_items(plan.groups[0].items, ...)`. Every `role="anchor"` in a ref becomes `emphasis="primary"`; other roles are dropped. Where a test asserts `response.layout[...]`, delete that assertion. Where a test asserts `response.mode == "show"`, assert `response.mode == "answer"`.

In `tests/test_experience.py`, change `finish_call` to:

```python
def finish_call(chat_answer, *, title="Deadbot", lead=None, groups=None):
    """The two messages a finished agent turn ends with: the call and its result."""

    plan = {"chat_answer": chat_answer, "title": title, "lead": lead, "groups": groups or []}
```

and update every inline `plan = {...}` dict in that file to drop `"mode"` and replace `"body": [...]` with `"groups": [{"presentation": "collection", "items": [...]}]` (or `"groups": []` when the body was empty). Any removed ref types used there become `show_unit` refs with `visible_facets=["setlist"]`.

- [ ] **Step 2: Run to verify failure**

Run: `$PY -m pytest tests/test_finish.py tests/test_experience.py -q 2>&1 | tail -5`
Expected: import errors (`finish.py` still imports removed names).

- [ ] **Step 3: Edit `deadbot/finish.py`**

Imports: drop `LayoutSection`, `ShowExplorerBlock`, `UnitOrganization`, `UnitRole`; add `Emphasis`, `SongFacet`, `ShowFacet`.

After the imports add the deprecated plan-only role vocabulary:

```python
# Deprecated plan vocabulary, accepted for one release and mapped to emphasis.
UnitRole = Literal["anchor", "supporting", "contrast", "turning_point", "outlier", "culmination", "overlooked", "representative"]
```

Delete `ShowSetlistRef`, `RecordingListRef`, `PerformerListRef`, `PerformanceSpineRef`, `ComparisonStripRef`, `PerformanceListRef`, `PerformanceExtremesRef`, `ShowExplorerRef`.

Replace `_ROLE_DESCRIPTION` with:

```python
_EMPHASIS_DESCRIPTION = (
    "How much of the page this object earns. primary: the object the answer is about; renders full width with its "
    "selected facets open. supporting: a peer or piece of evidence; renders as a compact card with its note, listening "
    "and highlights. mention: a name the visitor may want to follow; renders as one line with a listen link."
)
_ROLE_DESCRIPTION = "Deprecated. Use emphasis. anchor maps to primary; every other value maps to supporting."
_JUDGMENTS_DESCRIPTION = (
    "For a unit inside a comparison group: your one-line judgment for each of the group's criteria, in the same order. "
    "Leave an entry empty when you have nothing grounded to say."
)
```

In `ShowUnitRef`, `PerformanceUnitRef`, `AlbumUnitRef`, `SongOverviewRef` add, next to the existing `role` field:

```python
    emphasis: Emphasis | None = Field(default=None, description=_EMPHASIS_DESCRIPTION)
    judgments: list[str] = Field(default_factory=list, max_length=5, description=_JUDGMENTS_DESCRIPTION)
```

and change each `role` field description to `_ROLE_DESCRIPTION`. In `EraUnitRef` delete `role`. In `ShowUnitRef` change `visible_facets` to `list[ShowFacet]` with `max_length=6` and description: "The facets worth showing for this show. guests, listen, setlist and sources as before; lineup is the full performer list; recordings is the complete recording inventory. Identity and your note are always shown." In `SongOverviewRef` add:

```python
    visible_facets: list[SongFacet] = Field(
        default_factory=lambda: ["representatives"],
        max_length=4,
        description="The song facets worth showing: representatives (your chosen renditions), credits, albums, history (first and last documented performances, the count, and one rendition per year with listening links).",
    )
```

Add the mapping helper after the unit refs:

```python
def _emphasis_for(ref: Any) -> Emphasis:
    """The rendered emphasis for a unit ref: explicit emphasis, else the deprecated role mapped."""

    explicit = getattr(ref, "emphasis", None)
    if explicit:
        return explicit
    return "primary" if getattr(ref, "role", None) == "anchor" else "supporting"
```

Update `BodyItem` to the remaining union: `EditorialBlock | ShowUnitRef | PerformanceUnitRef | EraUnitRef | AlbumUnitRef | SongOverviewRef | EquipmentListRef | GuestAppearancesRef | ShowSelectionRef | ArrangementRef | ArrangementSearchRef | MediaLinkRef | ResourceListRef`.

In `GroupPlan` add after `presentation`:

```python
    criteria: list[str] = Field(
        default_factory=list,
        max_length=5,
        description="For a comparison only: the shared terms the items are judged on, in order, as short labels such as 'Tempo' or 'Second-set jam'.",
    )
```

Replace `FinishPlan` with:

```python
class FinishPlan(BaseModel):
    """The model's finished response: chat answer plus the main-body plan."""

    model_config = ConfigDict(extra="forbid")
    chat_answer: str = Field(
        description="The direct standalone answer shown in the conversation. Lead with the conclusion and keep it proportionate to the question. May use markdown links to URLs the tools returned this turn."
    )
    title: str = Field(description="Concise main-body title that states the central finding, not merely the topic.")
    lead: str | None = Field(default=None, description="A short expansion of the central finding. Omit it if the title and first item already establish the answer. Markdown links allowed.")
    groups: list[GroupPlan] = Field(
        default_factory=list,
        max_length=8,
        description=(
            "The edited main body as groups, each one a distinct relationship: collection for peers, sequence for a development or route, "
            "comparison for items judged on shared criteria, argument for evidence under a claim. Inside a group, semantic units declare the "
            "objects of the answer and the server hydrates their facts: show_unit, performance_unit, album_unit, song_overview, era_unit. "
            "Give each object an emphasis. Editorial blocks you write (narrative, fact_grid, timeline) carry what spans the units. "
            "Standalone components for objects without a parent unit: equipment_list, guest_appearance_list, show_selection, arrangement, "
            "arrangement_search, media_link, resource_list. An answer that needs no main body leaves groups empty."
        ),
    )
```

Rename `resolve_body(plan, ...)` to `resolve_items(items: list[Any], grounded, payloads, store)` iterating `items`; in `resolve_groups` call `resolve_items(group.items, ...)`, remove the `if not group_plans and plan.body` fallback, and build `ExperienceGroup(..., criteria=[c.strip() for c in group.criteria if c.strip()][:5], ...)`. After resolving each group's blocks, truncate judgments:

```python
        criteria_count = len(group.criteria)
        group_blocks = [
            block.model_copy(update={"judgments": list(block.judgments)[:criteria_count]}) if hasattr(block, "judgments") else block
            for block in group_blocks
        ]
```

In `_resolve_reference` delete the branches for `show_explorer`, the `show_setlist`/`performer_list`/`recording_list` trio (keep `equipment_list`, now on its own: `if kind == "equipment_list":` with the same body), the `comparison_strip`/`performance_list`/`performance_extremes` cases (keep `song_overview` on its own), and `performance_spine`. Pass `emphasis=_emphasis_for(item)` and `judgments=item.judgments` instead of `role=item.role` to `_show_unit`, `_performance_unit`, `_album_unit`, `_song_overview`; pass `visible_facets=item.visible_facets` to `_song_overview`; drop `role=` from `_era_unit`.

Delete `_layout`. In `build_experience_response`: the no-plan branch uses `mode="gap"` and no `layout`; the normal branch uses `mode="answer"` and no `layout`.

Update `build_finish_tool`'s description to: "Deliver the finished response to the visitor. Call this once, when your research is done. chat_answer gives the conclusion immediately; the main body adds the evidence, story or context that makes the answer worth opening, with listening and source actions attached to the objects they belong to. Compose groups (collection, sequence, comparison, argument) of semantic units with an emphasis, a note, selected facets, highlights and sources, plus your own narrative, fact grids or timelines for what spans the units. IDs must have appeared in a tool result this turn; links you write are kept only when their URL came from a tool result this turn."

- [ ] **Step 4: Edit `deadbot/composition.py` signatures**

In `_show_unit`, `_performance_unit`, `_album_unit`, `_song_overview`: replace the `role: UnitRole | None = None` keyword with `emphasis: Emphasis = "supporting", judgments: list[str] | None = None`, and set `emphasis=emphasis, judgments=list(judgments or [])[:5]` on the built block instead of `role=role`. In `_song_overview` add `visible_facets: list[str] | None = None` (used in Task 4; for now pass `visible_facets=list(visible_facets) if visible_facets is not None else ["representatives"]` to the block). In `_era_unit` delete the `role` parameter and argument. Fix imports (`Emphasis` in, `UnitRole` out).

- [ ] **Step 5: Run the tests**

Run: `$PY -m pytest tests/test_finish.py tests/test_experience.py tests/test_progress.py tests/test_answer_stream.py -q 2>&1 | tail -5`
Expected: PASS. Tests referencing composition functions deleted in Task 4 are not yet touched; if any fail only because of the `emphasis` rename, fix the call.

- [ ] **Step 6: Commit**

```bash
git add deadbot/finish.py deadbot/composition.py tests/test_finish.py tests/test_experience.py
git commit -m "Compose with emphasis and criteria; remove mode, body, explorer and single-dimension refs"
```

---

### Task 4: Facets absorb the single-dimension components

**Files:**
- Modify: `deadbot/composition.py`
- Modify: `deadbot/finish.py` (`_resolve_show_unit`, `song_overview` branch)
- Test: `tests/test_finish.py`

**Interfaces:**
- Produces, in `deadbot/composition.py`:
  - `_show_lineup(payload, store) -> list[PerformerItem]` (was `_show_performers`; returns items, not a block)
  - `_show_recordings(payload, store) -> list[RecordingItem]` (was `_recording_list`)
  - `_song_history(performances, store) -> SongHistory | None` (merges `_performance_extremes` and `_comparison_strip`)
  - `_set_neighbors(context, store) -> tuple[PerformanceSpineNeighbor | None, PerformanceSpineNeighbor | None]` (was `_performance_spine`)
  - `_show_unit(...)` hydrates `lineup` when `"lineup"` selected and `recordings` when `"recordings"` selected; returns recording sources as `SourceReference`s alongside listen sources
  - `_song_overview(..., visible_facets=...)` hydrates `credits`, `albums`, `history`, `representatives` only when selected
- Deleted: `_show_setlist`, `_performance_list`, `_performance_extremes`, `_comparison_strip`, `_performance_spine`, `_show_performers`, `_recording_list`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_finish.py`:

```python
def test_show_unit_hydrates_lineup_and_recordings_only_when_selected():
    store = CanonicalStore()
    payload = store.show_context(store.resolve_show("1972-08-27"))
    grounded = finish.grounded_context([payload])
    full = finish.ShowUnitRef(type="show_unit", show_id="gd-1972-08-27", visible_facets=["lineup", "recordings"])
    bare = finish.ShowUnitRef(type="show_unit", show_id="gd-1972-08-27", visible_facets=["setlist"])
    blocks, sources = finish.resolve_items([full, bare], grounded, [payload], store)
    assert blocks[0].lineup and all(item.role in {"performer", "guest"} for item in blocks[0].lineup)
    assert blocks[0].recordings and all(item.url.startswith("http") for item in blocks[0].recordings)
    assert any(source.url and "archive.org" in source.url for source in sources)
    assert blocks[1].lineup == [] and blocks[1].recordings == [] and blocks[1].sets


def test_song_overview_hydrates_history_and_omits_unselected_facets():
    store = CanonicalStore()
    payloads = _veneta_payloads(store)
    grounded = finish.grounded_context(payloads)
    ref = finish.SongOverviewRef(type="song_overview", song_id="song-sugaree", visible_facets=["history"])
    blocks, _ = finish.resolve_items([ref], grounded, payloads, store)
    song = blocks[0]
    assert song.visible_facets == ["history"]
    assert song.history is not None
    assert song.history.first.show_date <= song.history.last.show_date
    assert song.history.known_count == song.known_performance_count
    assert len({item.year for item in song.history.by_year}) == len(song.history.by_year)
    assert song.credits == [] and song.albums == [] and song.representative_performances == []


def test_performance_unit_still_carries_set_neighbors():
    store = CanonicalStore()
    payloads = _veneta_payloads(store)
    grounded = finish.grounded_context(payloads)
    performance_id = next(p["performance_id"] for p in payloads[0]["performances"] if p.get("performance_id"))
    blocks, _ = finish.resolve_items([finish.PerformanceUnitRef(type="performance_unit", performance_id=performance_id)], grounded, payloads, store)
    unit = blocks[0]
    assert unit.type == "performance_unit"
    assert unit.previous is not None or unit.next is not None
```

- [ ] **Step 2: Run to verify failure**

Run: `$PY -m pytest tests/test_finish.py -q -k "lineup_and_recordings or hydrates_history or set_neighbors"`
Expected: FAIL (`lineup` empty, `history` None).

- [ ] **Step 3: Refactor `deadbot/composition.py`**

Rename `_show_performers` to `_show_lineup` and make it return `list(grouped.values())[:24]` (an empty list instead of `None`); update `_guest_items` (line 544) to call `_show_lineup` and filter `role == "guest"` as it does now.

Rename `_recording_list` to `_show_recordings` returning `items[:8]` (empty list instead of `None`); delete the `RecordingListBlock` construction.

Replace `_performance_list`, `_performance_extremes`, `_comparison_strip` with:

```python
def _song_history(performances: list[dict[str, Any]], store: CanonicalStore) -> SongHistory | None:
    """First and last documented renditions plus one representative per year, canonical dates only."""

    items = _performance_items(performances, store)
    if not items:
        return None
    first_per_year: dict[int, PerformanceListItem] = {}
    for item in items:
        if item.show_date and item.show_date[:4].isdigit():
            first_per_year.setdefault(int(item.show_date[:4]), item)
    years = sorted(first_per_year)
    if len(years) > 12:
        selected_positions = {round(step * (len(years) - 1) / 11) for step in range(12)}
        years = [year for position, year in enumerate(years) if position in selected_positions]
    by_year = [
        ComparisonStripItem(
            performance_id=first_per_year[year].performance_id,
            show_id=first_per_year[year].show_id,
            year=year,
            show_date=first_per_year[year].show_date,
            show_label=first_per_year[year].show_label,
            set_label=first_per_year[year].set_label,
            position_in_set=first_per_year[year].position_in_set,
            listen_url=first_per_year[year].listen_url,
        )
        for year in years
    ]
    return SongHistory(known_count=len(items), first=items[0], last=items[-1], by_year=by_year)
```

Rename `_performance_spine` to `_set_neighbors` returning `(previous, next)` neighbors and delete the `PerformanceSpineBlock` construction; update `_performance_unit` (line 658) to unpack the tuple. Delete `_show_setlist`.

In `_show_unit`: compute `lineup = _show_lineup(payload, store) if "lineup" in facets else []` and `recordings = _show_recordings(payload, store) if "recordings" in facets else []`; set both on the block; extend the returned sources with `SourceReference(source_id=item.source_id, kind="contextual_resource", label=item.source_type, url=item.url)` for each recording.

In `_song_overview`: `facets = frozenset(visible_facets) if visible_facets is not None else frozenset({"representatives"})`; build `credits` only if `"credits" in facets`, `albums` only if `"albums" in facets`, `representatives` only if `"representatives" in facets`, `history=_song_history(performances, store) if "history" in facets else None`; set `visible_facets=sorted(facets, key=["representatives", "history", "credits", "albums"].index)`.

Fix imports: add `SongHistory`, remove the deleted block classes.

- [ ] **Step 4: Wire `deadbot/finish.py`**

`_resolve_show_unit` already passes `visible_facets`; ensure the recording sources returned by `_show_unit` are included (they are, through `listen_sources`). In the `song_overview` branch pass `visible_facets=item.visible_facets`. Remove any remaining reference to the deleted composition functions.

- [ ] **Step 5: Run the tests**

Run: `$PY -m pytest tests/test_finish.py tests/test_experience.py -q 2>&1 | tail -5`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add deadbot/composition.py deadbot/finish.py tests/test_finish.py
git commit -m "Fold setlist, lineup, recording and performance history components into unit facets"
```

---

### Task 5: Regenerate the contract and make the frontend compile

**Files:**
- Modify: `web/openapi.json`, `web/src/generated/api.ts` (generated)
- Modify: `web/src/types.ts`, `web/src/App.tsx`, `web/src/visual-fixtures.ts`
- Modify: `evals/exploration-v1.json`, `tests/test_exploration_evaluation.py`, `tests/test_evaluations.py` (if it asserts `mode`)
- Test: `npm run build --prefix web`; `$PY -m pytest tests/test_exploration_evaluation.py tests/test_evaluations.py -q`

**Interfaces:**
- Consumes: version 2 contract.
- Produces: `web/src/types.ts` without `ShowExplorer`, `ShowSetlist`, `RecordingList`, `PerformerList`, `PerformanceList`, `PerformanceExtremes`, `PerformanceSpine`, `ComparisonStrip` types; `ShowUnitBlock` `Require` list gains `"lineup" | "recordings" | "judgments"`; `FixedSongOverviewBlock` `Require` gains `"visible_facets" | "judgments"`; `ExperienceResponse` type no longer picks `layout`.

- [ ] **Step 1: Regenerate**

Run: `$PY scripts/export_openapi.py && npm run gen:types --prefix web && git diff --stat web/openapi.json web/src/generated/api.ts`
Expected: both files change; no manual edits.

- [ ] **Step 2: Update `web/src/types.ts`**

Remove the union members for the deleted blocks. Change:

```ts
export type ShowUnitBlock = Require<components["schemas"]["ShowUnitBlock"], "sets" | "guests" | "listen" | "sources" | "visible_facets" | "lineup" | "recordings" | "judgments">;
type FixedPerformanceUnitBlock = Require<components["schemas"]["PerformanceUnitBlock"], "listen" | "sources" | "judgments">;
export type AlbumUnitBlock = Require<components["schemas"]["AlbumUnitBlock"], "tracks" | "personnel" | "listen" | "sources" | "judgments">;
type FixedSongOverviewBlock = Require<components["schemas"]["SongOverviewBlock"], "credits" | "source_ids" | "albums" | "representative_performances" | "sources" | "visible_facets" | "judgments">;
export type ExperienceGroup = Require<components["schemas"]["ExperienceGroup"], "criteria">;
```

Delete `FixedShowExplorerBlock`. In `ExperienceResponse`, remove `"layout"` from both the `Omit` and the `Required<Pick<...>>` lists.

- [ ] **Step 3: Make `web/src/App.tsx` compile**

Delete the `show_explorer`, `show_setlist`, `recording_list`, `performer_list`, `performance_list`, `performance_extremes`, `comparison_strip`, and `performance_spine` cases from `Block`. Delete `modeLabels` and the `<p className="eyebrow">{modeLabels[response.mode]}</p>` line in the content heading. Replace every `${block.role ? \` role-${block.role}\` : ""}` / `${unit.role ? ...}` class fragment with ` emphasis-${block.emphasis}` (or `unit.emphasis`). Remove the `ShowUnit` role class the same way. Do not add new rendering yet; Task 7 does.

- [ ] **Step 4: Update `web/src/visual-fixtures.ts`**

In the `fixture()` helper remove the `mode` parameter and the `layout` line; set `schema_version: "2"`, `mode: "answer"`, and pass `criteria: []` on the group. In the `show()` helper replace `role: role ?? null` with `emphasis: emphasis ?? "supporting"`, `lineup: []`, `recordings: []`, `judgments: []`. Convert every fixture: `role: "anchor"` becomes `emphasis: "primary"`, other roles become `emphasis: "supporting"` on object units and are deleted on era units. The `branford` fixture's `show_explorer` becomes three `show_unit` blocks in one `collection` group. The `views` fixture drops its `mode` and `layout` lines and gains `criteria: []` on each group. Song overview fixtures gain `visible_facets: ["representatives"]`, `judgments: []`, `history: null`. Album fixtures gain `judgments: []`.

- [ ] **Step 5: Update evals**

In `evals/exploration-v1.json` delete every `"mode": "..."` line inside `expected` except `"mode": "gap"`, and remove `recording_list` and `comparison_strip` from `allowed_block_types`, adding `show_unit` and `song_overview`. In `tests/test_exploration_evaluation.py` replace `assert case["expected"]["mode"]` with `assert case["expected"].get("mode", "answer") in {"answer", "gap"}`. If `tests/test_evaluations.py` line 67's `"mode": "research"` is a case's expected mode, remove it; if it is a suite header, leave it.

- [ ] **Step 6: Build and test**

Run: `npm run build --prefix web && $PY -m pytest tests/test_exploration_evaluation.py tests/test_evaluations.py -q 2>&1 | tail -3`
Expected: build passes; tests pass (the known pre-existing `DEADBOT_DATABASE_URL` failure in `test_evaluations.py` is not caused by this task; report it if it appears).

- [ ] **Step 7: Commit**

```bash
git add web/openapi.json web/src/generated/api.ts web/src/types.ts web/src/App.tsx web/src/visual-fixtures.ts evals/exploration-v1.json tests/test_exploration_evaluation.py tests/test_evaluations.py
git commit -m "Regenerate the version 2 contract and remove retired blocks from the renderer"
```

---

### Task 6: Fixture-first check for four question shapes

**Files:**
- Modify: `web/src/visual-fixtures.ts`
- Test: `npm run build --prefix web` (type-checking the fixtures against the generated contract is the check)

**Interfaces:**
- Produces fixtures named `fact`, `legacy`, `evolution`, `views` in `visualFixtureNames`; `eyes` and `songs` are removed if their content is covered by `evolution` and `legacy`. Keep `branford`, `cornell`, `shakedown`, `album`.

- [ ] **Step 1: Write the four fixtures**

Each fixture is the ideal page, hand-written, using only version 2 fields.

`fact` ("When was American Beauty released?"): title "American Beauty came out in November 1970", no lead, one `collection` group with one `album_unit` at `emphasis: "primary"`, `visible_facets: ["listen"]`, tracks `[]`, personnel `[]`, note one sentence, follow_up "How did these songs settle into the live repertoire?". Nothing else.

`legacy` ("What was the live legacy of American Beauty?"): title stating the finding; one `collection` group titled "The durable songs" with four `song_overview` blocks at `emphasis: "supporting"`, each with `visible_facets: ["representatives"]`, one representative performance with a listen URL, and a note; then a second `collection` group titled "The ones that faded" with two `song_overview` blocks at `emphasis: "mention"` (note only, `representative_performances: []`); then an `argument` group whose `lead` is the claim and whose single item is a narrative editorial block.

`evolution` ("How did Eyes of the World evolve?"): one `sequence` group with three `era_unit` blocks (title, span, note, two performances each with listen links) followed by one `song_overview` at `emphasis: "primary"` with `visible_facets: ["history"]` and a populated `history` (first, last, `by_year` of four entries).

`views` (existing): keep the two groups; convert the first group into a `comparison` with `criteria: ["Musical quality", "Emotional weight", "Worth hearing"]` and three `performance_unit` blocks (Soldier Field "So Many Roads", "Black Muddy River", "Box of Rain") at `emphasis: "supporting"` each with three `judgments`; keep the second group as the fact grid.

Use the existing `fixture()`/`show()`/`songs()` helpers where they fit; hand-build otherwise, mirroring their shape.

- [ ] **Step 2: Build**

Run: `npm run build --prefix web`
Expected: PASS. If any fixture cannot be typed because the contract lacks a field the ideal page needs, stop and report BLOCKED naming the field and the fixture.

- [ ] **Step 3: Commit**

```bash
git add web/src/visual-fixtures.ts
git commit -m "Hand-write the four target pages as version 2 fixtures"
```

---

### Task 7: Emphasis anatomy, facets, and criteria in the renderer

**Files:**
- Modify: `web/src/App.tsx`, `web/src/styles.css`
- Test: `npm run build --prefix web`; browser review of `?fixture=legacy`, `?fixture=evolution`, `?fixture=views`, `?fixture=branford` at 1440px and 375px

**Interfaces:**
- Consumes: Task 5 types.
- Produces in `App.tsx`:
  - `type UnitBlock = Extract<ExperienceBlock, { type: "show_unit" | "performance_unit" | "album_unit" | "song_overview" }>`
  - `function isUnit(block: ExperienceBlock): block is UnitBlock`
  - `function MentionRow({ block }: { block: UnitBlock })`
  - `function CriteriaTable({ criteria, judgments }: { criteria: string[]; judgments: string[] })`
  - `Block` gains props `criteria: string[]` and `soleUnit: boolean`
  - `function unitKey(block: UnitBlock): string`
  - `function chunkMentions(blocks: (ExperienceBlock | undefined)[]): Array<{ kind: "mentions"; blocks: UnitBlock[] } | { kind: "block"; block: ExperienceBlock }>`

- [ ] **Step 1: Add the helpers**

```tsx
type UnitBlock = Extract<ExperienceBlock, { type: "show_unit" | "performance_unit" | "album_unit" | "song_overview" }>;

function isUnit(block: ExperienceBlock): block is UnitBlock {
  return block.type === "show_unit" || block.type === "performance_unit" || block.type === "album_unit" || block.type === "song_overview";
}

function unitIdentity(block: UnitBlock): { title: string; url?: string | null } {
  switch (block.type) {
    case "show_unit":
      return { title: block.venue_name ? `${block.venue_name} (${formatShowDate(block.show_date)})` : formatShowDate(block.show_date), url: block.listen[0]?.url };
    case "performance_unit":
      return { title: `${block.song_title}, ${venueFirstShowLabel(block.show_date, block.venue_name, block.show_label)}`, url: block.listen[0]?.url };
    case "album_unit":
      return { title: block.release_date ? `${block.title} (${block.release_date.slice(0, 4)})` : block.title, url: block.listen[0]?.url };
    case "song_overview":
      return { title: block.title, url: block.representative_performances[0]?.listen_url };
  }
}

// A mention is one line: the object, the model's note, a way to hear it.
function MentionRow({ block }: { block: UnitBlock }) {
  const identity = unitIdentity(block);
  return (
    <li className={`mention emphasis-mention ${block.type}`}>
      <ListeningLabel title={identity.title} url={identity.url} className="list-item-label" />
      {block.note && <span className="mention-note">{renderInline(block.note)}</span>}
    </li>
  );
}

function CriteriaTable({ criteria, judgments }: { criteria: string[]; judgments: string[] }) {
  if (criteria.length === 0) return null;
  return (
    <dl className="criteria">
      {criteria.map((criterion, index) => (
        <div key={criterion}>
          <dt>{criterion}</dt>
          <dd>{judgments[index] ? renderInline(judgments[index]) : null}</dd>
        </div>
      ))}
    </dl>
  );
}

function unitKey(block: UnitBlock): string {
  switch (block.type) {
    case "show_unit": return block.show_id;
    case "performance_unit": return block.performance_id;
    case "album_unit": return block.release_id;
    case "song_overview": return block.song_id;
  }
}

function chunkMentions(blocks: (ExperienceBlock | undefined)[]) {
  const out: Array<{ kind: "mentions"; blocks: UnitBlock[] } | { kind: "block"; block: ExperienceBlock }> = [];
  for (const block of blocks) {
    if (!block) continue;
    if (isUnit(block) && block.emphasis === "mention") {
      const last = out[out.length - 1];
      if (last && last.kind === "mentions") last.blocks.push(block);
      else out.push({ kind: "mentions", blocks: [block] });
    } else {
      out.push({ kind: "block", block });
    }
  }
  return out;
}
```

- [ ] **Step 2: Thread `criteria` and `soleUnit` through rendering**

In the group render loop replace the `group.block_indexes.map(...)` body with:

```tsx
{chunkMentions(group.block_indexes.map((index) => response.blocks[index])).map((entry, position) =>
  entry.kind === "mentions" ? (
    <ul className="mention-list" key={`mentions-${groupIndex}-${position}`}>
      {entry.blocks.map((block) => <MentionRow key={`${block.type}-${unitKey(block)}`} block={block} />)}
    </ul>
  ) : (
    <Block
      key={`${entry.block.type}-${position}`}
      block={entry.block}
      sources={response.sources}
      criteria={group.presentation === "comparison" ? group.criteria : []}
      soleUnit={unitCount === 1}
      onFollowUp={chooseFollowUp}
    />
  )
)}
```

where `const unitCount = response.blocks.filter(isUnit).length;` is computed once above the groups and `unitKey` returns the unit's id field (`show_id`, `performance_id`, `release_id`, or `song_id`). `Block` accepts `criteria: string[]` and `soleUnit: boolean` and passes them to `ShowUnit`, `AlbumUnit`, and the performance and song cases.

- [ ] **Step 3: Emphasis anatomy in each unit**

In `ShowUnit`, `AlbumUnit`, and the `performance_unit` and `song_overview` cases:

- Render `<CriteriaTable criteria={criteria} judgments={block.judgments} />` immediately after the note.
- Compute `const compact = block.emphasis === "supporting";` and `const openFacets = block.emphasis === "primary" && soleUnit;`.
- `ShowUnit`: when `compact`, force the setlist into the collapsed `<details>` form regardless of `setlist_disclosure` unless it is `hidden`. Render new facets after the setlist:

```tsx
{shows("lineup") && unit.lineup.length > 0 && (
  <details className="unit-facet unit-setlist" open={openFacets}>
    <summary>Lineup</summary>
    <ul className="facet-list">
      {unit.lineup.map((person) => (
        <li key={`${person.person_id}-${person.role}`}>
          <strong>{person.name}</strong>
          <span>{person.instruments.join(", ")}{person.role === "guest" ? " · Guest" : ""}</span>
        </li>
      ))}
    </ul>
  </details>
)}
{shows("recordings") && unit.recordings.length > 0 && (
  <details className="unit-facet unit-setlist" open={openFacets}>
    <summary>Recordings</summary>
    <ul className="facet-list">
      {unit.recordings.map((recording) => (
        <li key={recording.recording_id}>
          <ExternalLink href={recording.url}>{recording.title}</ExternalLink>
          <span>{recording.source_type}{recording.archive_identifier ? ` · ${recording.archive_identifier}` : ""}</span>
        </li>
      ))}
    </ul>
  </details>
)}
```

- `AlbumUnit`: the personnel `<details>` gets `open={openFacets}`; when `compact`, wrap the tracklist in `<details className="unit-facet unit-setlist"><summary>Tracklist</summary>…</details>` instead of the open section.
- `song_overview`: the `song-facts` `<dl>` is removed (the count lives in the history facet; the original artist moves into the subtitle line under the heading as `<p className="subtitle">Originally by {block.original_artist}</p>` when present). Render facets in `block.visible_facets` order using a `switch`: `representatives` as today; `credits` as today; `albums` as today; `history` as:

```tsx
{block.history && (
  <section className="song-history">
    <p className="fact-label">Performance history</p>
    <p className="subtitle">{block.history.known_count} documented performance{block.history.known_count === 1 ? "" : "s"}</p>
    <div className="performance-endpoints">
      <div className="performance-endpoint"><p className="fact-label">First</p><ListeningLabel title={block.history.first.show_label} url={block.history.first.listen_url} className="list-item-label" /></div>
      <div className="performance-endpoint"><p className="fact-label">Last</p><ListeningLabel title={block.history.last.show_label} url={block.history.last.listen_url} className="list-item-label" /></div>
    </div>
    {block.history.by_year.length > 1 && (
      <ol className="comparison-track" aria-label="One performance per year">
        {block.history.by_year.map((item) => (
          <li className="comparison-stop" key={item.performance_id}>
            <p className="comparison-year">{item.year}</p>
            <ListeningLabel title={item.show_label} url={item.listen_url} className="list-item-label" />
          </li>
        ))}
      </ol>
    )}
  </section>
)}
```

When `compact`, `credits`, `albums` and `history` render inside `<details className="unit-facet unit-setlist">` with summaries "Credits", "On record", "Performance history".

- [ ] **Step 4: CSS**

Append to `web/src/styles.css`:

```css
/* Emphasis: how much of the page one object earns. */
.card.emphasis-primary { grid-column: 1 / -1; border-color: #7d6a35; }
.card.emphasis-supporting { grid-column: span 12; padding: var(--space-part) 1.1rem; }
.card.emphasis-supporting .unit-note { font-size: 0.96rem; }
@media (min-width: 861px) { .card.emphasis-supporting { grid-column: span 6; } }
.mention-list { grid-column: 1 / -1; margin: 0; padding: 0; list-style: none; }
.mention { display: flex; flex-wrap: wrap; align-items: baseline; gap: 0.35rem 0.75rem; border-top: 1px solid #3e5544; padding: 0.6rem 0; }
.mention:last-child { border-bottom: 1px solid #3e5544; }
.mention-note { color: #bdc9bb; font-size: 0.92rem; line-height: 1.45; }
.mention-note::before { content: "· "; color: #7f9582; }
.criteria { display: grid; gap: var(--space-identity); margin: var(--space-part) 0 0; border-top: 1px solid #3e5544; padding-top: var(--space-identity); }
.criteria > div { display: grid; grid-template-columns: minmax(6rem, 9rem) 1fr; gap: 0.5rem; }
.criteria dt { color: #aebbac; font-size: 0.76rem; font-weight: 750; letter-spacing: 0.08em; text-transform: uppercase; }
.criteria dd { margin: 0; color: #f1efdf; font-size: 0.95rem; line-height: 1.45; min-height: 1.45em; }
.unit-facet { margin-top: var(--space-part); }
.facet-list { margin: var(--space-identity) 0 0; padding: 0; list-style: none; }
.facet-list li + li { border-top: 1px solid #3e5544; margin-top: 0.5rem; padding-top: 0.5rem; }
.facet-list li span { display: block; margin-top: 0.2rem; color: #aebbac; font-size: 0.86rem; }
.song-history .performance-endpoints { margin-top: var(--space-identity); }
```

Remove the now-unused `.role-anchor` selectors and the `.song-facts` rules if no element uses them.

- [ ] **Step 5: Build and review**

Run: `npm run build --prefix web`; then in Vite dev open `?fixture=legacy` (supporting cards pair up, mentions list), `?fixture=evolution` (primary song with history open because it is the sole unit), `?fixture=views` (criteria rows align across three columns), at 1440px and 375px.
Expected: build passes; each check holds.

- [ ] **Step 6: Commit**

```bash
git add web/src/App.tsx web/src/styles.css
git commit -m "Render emphasis levels, unit facets, and comparison criteria"
```

---

### Task 8: Relationship layouts

**Files:**
- Modify: `web/src/styles.css`, `web/src/App.tsx` (group header for argument)
- Test: `npm run build --prefix web`; browser review of all four fixtures from Task 6

**Interfaces:**
- Consumes: group class names `group-collection`, `group-sequence`, `group-comparison`, `group-argument` already on each `<section className="experience-group ...">`.

- [ ] **Step 1: Argument header markup**

In the group render, when `group.presentation === "argument"` render the header as:

```tsx
<header className="group-heading claim">
  {group.title && <h2>{group.title}</h2>}
  {group.lead && <p className="claim-text">{renderInline(group.lead)}</p>}
</header>
```

(Other presentations keep the existing header.)

- [ ] **Step 2: CSS**

Replace the existing `.group-sequence .group-blocks`, `.group-argument .group-heading`, and the `@media (min-width: 861px) { .group-comparison ... }` rules with:

```css
/* Relationships: peers, order, contrast, claim and evidence each have a shape. */
.group-sequence .group-blocks { position: relative; counter-reset: step; gap: var(--space-unit); padding-left: 3.25rem; }
.group-sequence .group-blocks::before { content: ""; position: absolute; top: 0.4rem; bottom: 0.4rem; left: 1rem; border-left: 1px solid #506757; }
.group-sequence .group-blocks > * { position: relative; grid-column: 1 / -1; }
.group-sequence .group-blocks > *::before { counter-increment: step; content: counter(step); position: absolute; left: -3.25rem; top: 0; width: 2rem; height: 2rem; border: 1px solid #c49e48; border-radius: 999px; color: #f1d684; font-family: Georgia, "Times New Roman", serif; font-size: 0.95rem; font-weight: 700; line-height: 2rem; text-align: center; background: #14221b; }
@media (min-width: 861px) {
  .group-comparison .group-blocks { grid-template-columns: repeat(auto-fit, minmax(18rem, 1fr)); }
  .group-comparison .group-blocks > .card { grid-column: auto; }
  .group-comparison .group-blocks > .typography-block, .group-comparison .group-blocks > .mention-list { grid-column: 1 / -1; }
}
.group-argument .group-heading.claim { border-left: 3px solid #c49e48; padding-left: var(--space-part); }
.group-argument .claim-text { max-width: 58rem; margin: var(--space-identity) 0 0; color: #f1efdf; font-family: Georgia, "Times New Roman", serif; font-size: 1.25rem; line-height: 1.45; }
.group-argument .group-blocks { border-left: 1px solid #3e5544; margin-left: 1px; padding-left: var(--space-part); }
@media (max-width: 520px) {
  .group-sequence .group-blocks { padding-left: 2.5rem; }
  .group-sequence .group-blocks > *::before { left: -2.5rem; width: 1.6rem; height: 1.6rem; line-height: 1.6rem; font-size: 0.85rem; }
}
```

- [ ] **Step 3: Build and review**

Run: `npm run build --prefix web`; open `?fixture=evolution` (numbered spine), `?fixture=views` (three aligned columns), `?fixture=legacy` (paired supporting cards, then mention list, then claim callout) at 1440px and 375px.
Expected: build passes; each relationship reads differently before the prose is read.

- [ ] **Step 4: Commit**

```bash
git add web/src/App.tsx web/src/styles.css
git commit -m "Give collection, sequence, comparison and argument groups distinct layouts"
```

---

### Task 9: Prompt

**Files:**
- Modify: `deadbot/graph.py` (SYSTEM_PROMPT, "COMPOSING THE EXPERIENCE" section)
- Test: `tests/test_graph.py`

- [ ] **Step 1: Update the tests**

In `test_prompt_teaches_semantic_units_and_grouping_by_meaning` change the units tuple to `("show_unit", "performance_unit", "era_unit", "album_unit", "song_overview")` and add:

```python
    assert "show_explorer" not in prompt
    assert "quick_fact" not in prompt
    for word in ("primary", "supporting", "mention"):
        assert word in unwrapped
    assert "criteria" in unwrapped
```

- [ ] **Step 2: Run to verify failure**

Run: `$PY -m pytest tests/test_graph.py -q`
Expected: FAIL on `show_explorer` still present.

- [ ] **Step 3: Rewrite the composing section**

Replace the text from "The model declares semantic units; the server hydrates their facts and URLs:" through "Use the simplest component that makes the important relationship obvious." with:

```text
The model declares semantic units; the server hydrates their facts and URLs:

- show_unit: one show. Select the facets that advance the answer from guests,
  listen, setlist, sources, lineup (the full performer list) and recordings
  (the complete recording inventory). Highlight performances worth attention.
  A show_unit needs only a show_id that appeared in this turn's tool output;
  call get_show when its setlist or guests inform what you write.
- performance_unit: one rendition. The server adds its song, venue, set
  neighbors and play actions.
- album_unit: a record. Choose listen, tracklist, personnel or sources only
  when that inventory advances the answer.
- song_overview: a song. Choose representatives (your chosen renditions, in
  listening order, from list_song_performances), credits, albums, or history
  (first and last documented performances, the count, and one rendition per
  year with listening links).
- era_unit: a stage in a musical development, with representative performances
  that let the visitor hear the change.

Give each show, performance, album and song an emphasis. primary is the object
the answer is about; it renders full width with its facets open. supporting is
a peer or a piece of evidence; it renders as a compact card with your note,
listening and highlights. mention is a name worth following; it renders as one
line with a listen link. One or two primary objects is the norm.

Groups are relationships. collection presents peers in an equal grid. sequence
presents a development or route on a numbered spine. comparison presents items
judged on the same terms in aligned columns: name the shared criteria on the
group and give each unit one judgment per criterion, in order, leaving an entry
empty when nothing grounded supports it. argument presents your claim as the
group lead with the evidence attached beneath it.

Editorial blocks are narrative, fact_grid and timeline. Narrative makes an
argument; a timeline makes sequence visible; a fact_grid compares a concise
set on shared terms, including attributed viewpoints. In a fact_grid, each
item title names its subject and the value or detail carries the assessment.

Give each idea one clear home. Song_overview units are the home for individual
song stories and listening actions. A fact_grid is the home for a compact
cross-song pattern. When both appear, the grid states the pattern and the song
units develop different evidence, interpretation and actions.

Standalone components serve objects without a parent unit: equipment_list,
guest_appearance_list, show_selection, arrangement, arrangement_search,
media_link and resource_list.
```

Also delete the sentence beginning "Roles such as anchor, supporting, contrast" and its continuation. Search the whole prompt for "mode" used in the schema sense and remove it; leave ordinary English uses.

- [ ] **Step 4: Run the tests**

Run: `$PY -m pytest tests/test_graph.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add deadbot/graph.py tests/test_graph.py
git commit -m "Teach the composer emphasis, facets and relationship criteria"
```

---

### Task 10: Release pathways

**Files:**
- Modify: `deadbot/tools.py` (`search_entities` pathway selection), `deadbot/pathways.py` (release branch, budget fit)
- Test: `tests/test_pathways.py`

**Interfaces:**
- Produces: release pathways may carry `song_lore: list[{"song_id": str, "title": str}]` (max 6); `search_entities` attaches pathways to at most two entities per type, six total.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_pathways.py`:

```python
def test_search_entities_gives_a_release_pathways_even_when_its_tracks_match_first():
    store = CanonicalStore()
    release = store.resolve_release("Wake of the Flood")
    result = json.loads(tool_by_name(store, "search_entities").invoke({"query": "Wake of the Flood"}))
    pathways = result["pathways"]
    assert release["release_id"] in pathways
    by_type = {}
    for match in result["matches"]:
        if match["id"] in pathways:
            by_type[match["entity_type"]] = by_type.get(match["entity_type"], 0) + 1
    assert all(count <= 2 for count in by_type.values())
    assert len(pathways) <= 6


def test_release_pathways_point_to_tracks_with_cataloged_lore():
    store = CanonicalStore()
    sugaree = store.resolve_song("Sugaree")["song_id"]
    release_id = next(row["release_id"] for row in store.rows("official_release_tracks") if row.get("song_id") == sugaree)
    pathways = pathways_for(store, [("release", release_id)])[release_id]
    assert any(entry["song_id"] == sugaree for entry in pathways["song_lore"])
    assert all(set(entry) == {"song_id", "title"} for entry in pathways["song_lore"])
    assert len(pathways["song_lore"]) <= 6
```

- [ ] **Step 2: Run to verify failure**

Run: `$PY -m pytest tests/test_pathways.py -q -k "release"`
Expected: FAIL (`release_id` not in pathways; `song_lore` KeyError). If `resolve_release("Wake of the Flood")` returns `None` in the local store, use `"American Beauty"` in the first test instead and note it in the report.

- [ ] **Step 3: Edit `deadbot/tools.py`**

Replace the `pathway_entities = [...]` list comprehension in `search_entities` with:

```python
        # At most two entities per type so a record's own tracks do not crowd
        # the record (or a show) out of the six pathway slots.
        pathway_entities: list[tuple[str, str]] = []
        per_type: dict[str, int] = {}
        for match in limited:
            kind = match["entity_type"]
            if kind not in {"song", "show", "release"} or per_type.get(kind, 0) >= 2:
                continue
            per_type[kind] = per_type.get(kind, 0) + 1
            pathway_entities.append((kind, match["id"]))
            if len(pathway_entities) == 6:
                break
```

- [ ] **Step 4: Edit `deadbot/pathways.py`**

After the `resource_releases_by_release` block add:

```python
    lore_songs_by_release: dict[str, list[tuple[str, str]]] = {}
    if release_ids:
        track_song_ids_by_release: dict[str, list[str]] = {}
        for row in store.rows_in("official_release_tracks", "release_id", release_ids):
            release_id, song_id = row.get("release_id", ""), row.get("song_id", "")
            if release_id and song_id:
                track_song_ids_by_release.setdefault(release_id, []).append(song_id)
        track_song_ids = {song_id for song_ids in track_song_ids_by_release.values() for song_id in song_ids}
        track_resources_by_song: dict[str, list[str]] = {}
        for row in store.rows_in("resource_songs", "song_id", track_song_ids):
            song_id, resource_id = row.get("song_id", ""), row.get("resource_id", "")
            if song_id and resource_id:
                track_resources_by_song.setdefault(song_id, []).append(resource_id)
                resource_ids_needed.add(resource_id)
        titles = {row["song_id"]: row.get("title") or row["song_id"] for row in store.rows_in("songs", "song_id", track_song_ids)}
        for release_id, song_ids in track_song_ids_by_release.items():
            lore_songs_by_release[release_id] = [(song_id, titles.get(song_id, song_id)) for song_id in _dedupe(song_ids) if song_id in track_resources_by_song]
```

This block must run before `resources_by_id` is loaded (it adds to `resource_ids_needed`). In the release branch, after the `resources` check, add:

```python
            song_lore = [
                {"song_id": song_id, "title": title}
                for song_id, title in lore_songs_by_release.get(entity_id, [])
                if _resource_summary([resources_by_id[rid] for rid in track_resources_by_song.get(song_id, []) if rid in resources_by_id])
            ][:6]
            if song_lore:
                payload["song_lore"] = song_lore
```

(`track_resources_by_song` must be defined outside the `if release_ids` block as an empty dict first so the release branch can reference it.) In `_fit_budget`, before the `source_trail` trim, add:

```python
    song_lore = payload.get("song_lore")
    if isinstance(song_lore, list):
        while len(song_lore) > 1 and _size(payload) > _CHAR_BUDGET:
            song_lore.pop()
```

- [ ] **Step 5: Run the tests**

Run: `$PY -m pytest tests/test_pathways.py tests/test_research_tools.py -q`
Expected: PASS, including the compactness test.

- [ ] **Step 6: Commit**

```bash
git add deadbot/tools.py deadbot/pathways.py tests/test_pathways.py
git commit -m "Give releases lore pathways and keep search pathways diverse by entity type"
```

---

### Task 11: Measure, document, and full validation

**Files:**
- Modify: `docs/UX-NEXT-STEPS.md`, `docs/experience-architecture.md` (semantic units table and block catalog rows for removed components)
- Test: full targeted suite and web build

- [ ] **Step 1: Measure the schema after the cut**

Run: `$PY scripts/measure_finish_schema.py`
Add a row to the Measurements table in `docs/UX-NEXT-STEPS.md`: `| <today> | after the emphasis and palette cut | <chars> / <tokens> |`.

- [ ] **Step 2: Live finish-call timing (only if the environment has `OPENAI_API_KEY` and `DEADBOT_DATABASE_URL`)**

If both are present in the environment, run the three questions (Branford; Franklin's Tower best versions; American Beauty live legacy) with the trace pattern from the latency work and record plan output tokens and finish-call wall time in the same table. If either variable is missing, add one line under the table: "Live finish-call timing not run in this environment; run before merge with the trace script and record here." Do not invent numbers.

- [ ] **Step 3: Documentation**

In `docs/experience-architecture.md`: remove `show_explorer` from the semantic units table; add `album_unit` and `song_overview` rows; in the block catalog remove the rows for the setlist, performance spine, comparison strip, and card components that are now facets, and add one sentence under the table: "Facets of a unit (setlist, lineup, recordings, performance history, credits, albums) render inside the unit; they are not separate blocks." In `docs/UX-NEXT-STEPS.md` under "## Next: knob audit and emphasis" mark the items completed by this batch and list what remains: removing `role` from the plan after one release; progressive page streaming.

- [ ] **Step 4: Full validation**

Run:

```bash
$PY -m pytest tests/test_finish.py tests/test_experience.py tests/test_progress.py tests/test_answer_stream.py tests/test_graph.py tests/test_pathways.py tests/test_research_tools.py tests/test_exploration_evaluation.py tests/test_measure_finish_schema.py -q
npm run build --prefix web
$PY scripts/export_openapi.py && npm run gen:types --prefix web && git status --short web/openapi.json web/src/generated/api.ts
```

Expected: all pass; the last command prints nothing (no drift).

- [ ] **Step 5: Commit**

```bash
git add docs/UX-NEXT-STEPS.md docs/experience-architecture.md
git commit -m "Record the palette cut measurements and update the architecture notes"
```
