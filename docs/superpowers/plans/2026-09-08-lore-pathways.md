# Lore pathways attached to entity results

## Context

Deadbot's model decides per question whether to look for lore (interviews,
essays, source trails, fan and critic selections). A plain question ("What
came before Dark Star at Veneta?") therefore often gets a plain answer with no
pathways outward, while a question that does prompt lore research pays for an
extra model round. Traces on 2026-09-08 showed the model's first research
round already reaches for lore when it can; the fix is to make the lore
inventory arrive with the entities themselves so no extra round or decision is
needed. The owner's direction: always see whether good lore exists; answer
plainly, then offer pathways.

Spec authority: `docs/model-retrieval.md` (resources are first-class,
queryable graph records; the model discovers them through structured lookup),
`docs/agent-harness.md` (tools are read-only; grounding is turn-scoped),
`docs/provenance-policy.md`, and this file.

## Global constraints

- Tools stay read-only and never touch the network for pathways; everything
  comes from the canonical store (resources and their relationship tables,
  `data/lore-source-trails.json` via `deadbot.lore_source_trails`, selection
  evidence via `store.selection_signal_rows` when the store has it, official
  release tracks) plus `data/research_sites.json` for suggested search routes.
- Pathways are metadata: title, source, type, URL, counts, and a short
  "why open" note. Never page text.
- Batched reads only: one `rows_in` per table for all entities in the call,
  never a lookup per entity. Both stores (`CanonicalStore`, Postgres).
- Compact: at most 3 titled links per category per entity, and each entity's
  pathways object stays under about 900 characters of JSON.
- An empty inventory says so and offers search routes rather than implying
  coverage: `"cataloged": false` plus `research_routes` naming the research
  sites suited to that entity type (songs: Grateful Dead Guide (Deadessays),
  Deadhead High, Dead.net; shows: Lost Live Dead, Dead Sources, Grateful Dead
  Archive Online, Internet Archive Grateful Dead collection; albums: Dead.net,
  Dead Sources).
- Selection signals stay source-attributed voices: counts and labels, never a
  combined score.
- Prompt guidance is written affirmatively (repo rule: no "do not").
- Tests: `PYTHONPATH=. /Users/markdavenport/Development/DeadBot/.venv/bin/python -m pytest -q`.
  The pre-existing failure `tests/test_evaluations.py::test_evaluate_cli_exits_non_zero_when_a_case_fails`
  is expected; everything else passes. Commit trailer:
  `Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>`. Never push; never bare `git stash`.

## Task 1 — `deadbot/pathways.py` and tool attachment

1. New module `deadbot/pathways.py` with
   `pathways_for(store, entities: list[tuple[str, str]]) -> dict[str, dict]`
   where each entity is `("song" | "show" | "release", entity_id)` and the
   result maps `entity_id` to a pathways object:
   ```json
   {
     "cataloged": true,
     "resources": {"count": 4, "by_type": {"article": 2, "interview": 1, "podcast-transcript": 1},
                   "top": [{"title": "...", "source_name": "...", "resource_type": "article", "url": "https://..."}]},
     "source_trail": {"link_count": 4, "why_open": "..."},
     "selections": {"count": 3, "sources": ["rolling-stone-australia", "headyversion"]},
     "notable_versions": {"official_release_versions": 12, "fan_vote_versions": 0},
     "research_routes": ["Grateful Dead Guide (Deadessays)", "Deadhead High"]
   }
   ```
   Omit a category key entirely when it has nothing (no empty objects).
   `resources` excludes catalog rows: resource types `catalog-work-search`,
   `lyrics-and-credits` and `catalog-song-page` are inventory, not lore, and
   are left out of both the count and `top`. `source_trail` comes from
   `deadbot.lore_source_trails.source_trails_for_entity` (read it to learn the
   record shape; songs and shows only). `selections` counts selection entries
   whose candidate performances belong to the song (or whose candidate shows
   include the show), grouped by `source`; when the store lacks
   `selection_signal_rows`, omit the key. `notable_versions` (songs only):
   count of the song's performances that appear on an official release track,
   and count with a `fan_ranked_version` entry. `research_routes` is present
   always, listing the site names for the entity type from the Global
   constraints; `cataloged` is true when any of resources, source_trail or
   selections is present.
   Reads: `resource_songs` / `resource_shows` / `resource_performances`
   (by entity ids in one `rows_in` each), `resources` (one `rows_in`),
   `performances` for the songs (one `rows_in` by `song_id`),
   `official_release_tracks` (one `rows_in` by `performance_id`), selection
   rows once. A release's pathways use `resources` linked through
   `official_release_tracks`? No: for releases use only resources whose
   `notes` or `title` name the release id is unreliable, so releases get
   `resources` from a `resource_releases` table only if one exists in the
   store (`store.rows("resource_releases")` inside a try/except KeyError →
   treat as none) plus `research_routes`.
2. Attach in `deadbot/tools.py`:
   - `search_entities`: add `"pathways": {entity_id: {...}}` for the first
     6 song/show/release matches.
   - `get_song`: add `"pathways"` for the song.
   - `get_show`: add `"pathways"` for the show.
   - `get_album`: add `"pathways"` for the release.
   - `search_guest_musicians`: add `"pathways"` keyed by show id for the shows
     in the returned appearances (first 8 shows).
   Each tool's docstring gains one sentence: "pathways lists the cataloged
   lore for each result (resources, source trail, selections) or the research
   sites to search when nothing is cataloged."
3. Confirm the browser link host allowlist in `deadbot/composition.py`
   accepts the hosts that pathway URLs will carry (dead.net, blogspot.com
   blogs in `data/research_sites.json`, gdao.org, archive.org, relix.com);
   add any research-site host that is missing so a pathway link the model
   cites survives into the response. Name what you checked in the report.
4. Tests (`tests/test_pathways.py`): with the real CSV store, Sugaree has
   `cataloged: true` with a source trail and at least one non-catalog
   resource; a song with only lyric/catalog rows (find one) has
   `cataloged: false` with `research_routes`; Veneta (`gd-1972-08-27`) has a
   source trail and resources; every pathways object serializes under 900
   characters; `search_entities("Veneta Bird Song")` carries pathways for the
   show and the song; with the toy Postgres fixture
   (`tests/test_postgres_store.py` `Connection`, `TABLES`) `get_show` issues a
   bounded number of statements and the pathways object is present. Use
   `tests/test_data.py::store_with_selection_evidence` for a selections case
   (Dark Star has selections with `headyversion` among sources).
5. `docs/agent-harness.md`: one paragraph under the tool list describing
   pathways and the empty-inventory behaviour. Commit.

## Task 2 — Prompt guidance and a lighter `get_show`

1. `deadbot/graph.py` `SYSTEM_PROMPT`, in "## RESEARCH THE ACTUAL QUESTION"
   after the "Well-worn routes" paragraph, add:
   "Every entity result carries pathways: the lore already cataloged for it,
   or the research sites worth searching when nothing is. Answer the question
   directly, then offer the pathways that fit as links or Ask chips. When a
   pathway looks likely to change the answer, open it; otherwise offer it."
   And in "# COMPOSING THE EXPERIENCE" after the show_unit bullet: "A
   show_unit needs only a show_id that appeared in this turn's tool output;
   the server hydrates its setlist, guests and listening. Call get_show when
   its setlist or guests inform what you write."
2. `deadbot/tools.py` `get_show`: compact two sections of the payload.
   `recordings` becomes `{"count": N, "recording_ids": [first 5 ids in the
   existing order]}` with a note "full recording metadata: get_performance or
   the recording_list component". `performers` keeps one entry per person:
   `{"person_id", "name", "role", "instruments": [..]}` merging multiple
   instrument rows for the same person. Measure before/after on
   `gd-1990-03-29` with the CSV store and put the character counts in the
   report (target: at least 20% smaller). Update
   `tests/test_data.py`/`tests/test_research_tools.py` expectations that read
   these sections; keep `show_context` (used by composition) unchanged, the
   compaction happens in the tool only.
3. Tests: prompt tests in `tests/test_graph.py` asserting the two new
   sentences are present and `"do not"` still absent; a `get_show` shape test.
   Commit.
