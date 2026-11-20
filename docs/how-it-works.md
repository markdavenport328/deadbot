# How Deadbot works

This document walks through the three layers that make Deadbot go: what's in the database, how a question turns into tool calls against it, and how the results become a composed page in the browser. It's written at a moderate technical level — enough to see the mechanisms, not a code tour.

For the product goals and design philosophy, see [product-vision.md](product-vision.md) and [experience-brief.md](experience-brief.md).

## The database

### What it holds

The SQLite database holds the **canonical catalog** — every fact Deadbot can draw on when answering a question. It's organized around five core entities and the relationships between them.

**Shows** are the backbone. There are roughly 2,300 of them, each with a date, venue, tour, and full setlist. A **performance** is one song played at one show: it carries the set number, position, segue information, and links to recordings and streaming audio. This is the key join table — it's how "Scarlet Begonias" at Cornell '77 is a different record from "Scarlet Begonias" at Veneta '72.

**Songs** are compositions: title, writers, arrangements, first and last known Dead performance. **People** are musicians — band members, guest performers, songwriters — with band membership records that track roles, instruments, and date ranges. **Venues** carry location, capacity, and indoor/outdoor setting. **Equipment** tracks specific instruments (Tiger, Wolf, Rosebud) and their show assignments.

Around these core entities sit several supporting layers:

| Layer | What it holds | Example |
| --- | --- | --- |
| **Recordings** | Audience tapes, soundboards, archive.org identifiers, tapers and transferers | Charlie Miller SBD of 5/8/77 |
| **Official releases** | Albums with track-level mappings back to specific performances, personnel, Spotify links | *Dick's Picks Vol. 36* |
| **Resources** | External links to articles, interviews, oral histories, reviews, tabs, videos | A Dead.net oral history of "Dark Star" |
| **Selections** | Curated picks from critics, fans, and official sources, with source attribution | A "best Estimated Prophet" list from a published book |

The whole schema is about **30 tables** with strict foreign keys, check constraints, and referential-integrity triggers, defined in one file (`schema/sqlite.sql`). There are no migrations: the database is rebuilt from scratch on every deploy, so a schema change is an edit to that file. There are no embeddings or vector columns — all text matching is done with SQL `LIKE` queries.

### How data gets in

The database is populated from **24 reviewed CSV files** (~48 MB total) that live in the repo under `data/canonical/`. These CSVs are the version-controlled source of truth. The pipeline looks like this:

```
External sources → collection scripts → raw JSON in data/raw/
                                            ↓
                                    normalization scripts
                                            ↓
                                    canonical CSVs in data/canonical/
                                            ↓
                                    deadbot db-build → SQLite file (build/deadbot.sqlite)
```

**Collection** scripts in `scripts/collect/` pull raw data from external sources: Jerrybase for setlists, MusicBrainz for release metadata, Internet Archive for recording indexes, Relisten for streaming links, Wikidata and Wikipedia for biographical facts, dead.net for official material, and several others. These produce raw JSON files preserved in `data/raw/`.

**Normalization** scripts transform that raw data into the canonical CSV format — resolving entity identities, deduplicating, and fitting everything to the strict column-and-type contracts defined in the import code.

**The build** (`deadbot db-build`, or `python3 -m deadbot.sqlite_build`) turns the CSVs into the SQLite file. Before writing anything, it validates every CSV against its table contract (column names, types, nullable rules). It then loads them into a new file beside the old one, checks every foreign key, and only then swaps the new file into place. If anything fails, the previous file is left as it was. The build records a SHA-256 fingerprint of the exact inputs, so a local run knows when the checked-out CSVs have changed and rebuilds.

There is one mode: every build starts from an empty database and loads everything. A row removed from a CSV is gone from the next build.

After the CSV data loads, the build adds selection evidence from a reviewed editorial JSON file, generating the `resources`, `selection_lists`, `selection_entries`, and `selection_evidence` rows that power the curated-picks tools.

### At runtime

The database is **read-only at runtime**. The only write the application ever makes is caching its own answers for repeat questions, in a separate small file. All catalog data enters through the build.

The app runs on Vercel as a serverless function. The deploy's build step builds the SQLite file from the CSVs (`python3 -m deadbot.sqlite_build`), and the function opens it read-only. The response cache lives in its own small SQLite file in the function's temporary directory. SQLite is the only store; CI builds the same file and runs the tests and the evaluation against it.

There's a **per-request query cache** at the data layer: since the data is read-only, the same SQL query within one request returns the same rows without hitting the database again. This matters because the composition step often re-fetches entities the model already looked up during research.

The entire data layer is **hand-written parameterized SQL** through Python's standard `sqlite3` module (`deadbot/sqlite_store.py`). No ORM, no SQLAlchemy. Table and column identifiers are validated against a strict pattern and double-quoted. User input never enters identifiers.

## How retrieval works

When a user asks a question, the system runs a **LangGraph agent loop** — a language model that decides what to look up, executes the lookups, reviews the results, and repeats until it has enough material to compose an answer.

### The full path

```
User question
    ↓
POST /api/experience/stream
    ↓
Response cache check (normalized question + data version + code commit)
    ↓  cache miss
LangGraph agent loop (up to 8 research rounds)
    ↓
    ├─→ Agent node: LLM decides what to look up
    │       ↓
    ├─→ Tools node: executes tool calls
    │       ├─→ Catalog tools → SQLite queries
    │       └─→ External tools → web fetches
    │       ↓
    └─→ Results return to model for next round
    ↓
Model calls finish_response (terminal tool)
    ↓
Composition: resolve references → SQLite catalog
    ↓
Grounding check: records not in tool output keep only the model's words
    ↓
Validated ExperienceResponse → browser
```

### Cache layer

Before the model runs at all, the system checks whether this exact question (normalized to lowercase, punctuation-stripped) has been answered before with the current data version and code commit. If so, the cached response is returned instantly. Only first-turn questions are cached — follow-ups in a conversation aren't. Failed or gap answers are never stored. A stored answer is read back through the current response schema, so one written under an older page vocabulary is discarded and answered live. The deploy's build step also answers the opening questions once and ships those answers (`scripts/warm_answers.py`); they seed the cache under the same data version and commit.

### The agent loop

On a cache miss, the question enters a LangGraph state graph with two nodes that alternate:

1. **Agent node** — the language model receives the question, a system prompt describing how to research Grateful Dead topics, and results from any prior tool calls. It decides what to look up next.
2. **Tools node** — executes whatever tool calls the model requested and returns the results.

The routing logic is simple: if the model made tool calls, go to the tools node; if a successful `finish_response` result is in the messages, end the loop; otherwise, return to the agent node for another round. The recursion limit is 8 tool rounds (20 LangGraph steps).

### The 22 research tools

The model has 22 read-only research tools, all defined in `deadbot/tools.py`, plus `finish_response`, which delivers the answer.

**Finding and reading records**

| Tool | What it does |
| --- | --- |
| `search_entities` | Fuzzy search across songs, shows, people, venues, equipment, and releases |
| `search_guest_musicians` | Guest musicians and the shows they played |
| `get_show` | A show: venue, setlist, lineup, recordings, equipment, links |
| `get_song` | A song: writers, performance summary, arrangements, releases, resources |
| `get_song_life` | A song's life on stage year by year: how often and how long it was played |
| `list_song_performances` | A song's performances in order, a page at a time |
| `get_song_notable_versions` | Renditions with official releases and critic, curator and fan picks |
| `get_performance` | One rendition: its show, set position, recordings and links |
| `get_album` | An official release: tracklist mapped to performances, personnel, listening links |
| `get_picks` | The nights and versions critics, tapers and fans picked, for a song, a show, or a span of years or a venue |
| `find_arrangements` | Song arrangements by key signature |
| `get_equipment_history` | The first and last shows a named instrument was played at |
| `look_up` | Listed queries or read-only SQL over curated views, for lists by year, venue or tour (registered when the store runs catalog queries) |

**Counting and comparing**

| Tool | What it does |
| --- | --- |
| `aggregate_data` | Verified counts and rankings across shows, performances or guests; the source of every chart |
| `get_segue_pairing` | How a two-song pairing (China Cat > Rider) changed across the nights it was played |
| `get_grid` | Two lists against each other (songs by year, shows by song), every cell playable |

**Stories and outside sources**

| Tool | What it does |
| --- | --- |
| `search_stories` | Interviews, articles, podcasts and videos the library holds on a topic, song or show |
| `search_site` | Search one outside research site (Lost Live Dead, archive.org and others) |
| `read_page` | Read a web page's text |
| `get_recording_reviews` | Archive.org listener reviews and star ratings for a tape |
| `get_historical_weather` | The weather at a show's venue on its date |

**The conversation's own research**

| Tool | What it does |
| --- | --- |
| `read_notebook` | Results from earlier turns of this conversation, brought back whole or sliced, so a follow-up does not repeat the research |

### How search works at the SQL level

When the model calls `search_entities` with a phrase like "dark star 1972", the system:

1. Splits the phrase into word n-grams (1–3 words).
2. Searches **six entity types** in parallel: songs, shows, people, venues, equipment, and official releases.
3. For each entity type, runs two passes:
   - **Exact match:** `LOWER(column) = LOWER(needle)`
   - **Substring match:** `LIKE '%needle%'` with escaped wildcards
4. Ranks exact matches above fuzzy ones using a `CASE WHEN exact THEN 0 ELSE 1 END` ordering.
5. Attaches "pathways" (cataloged lore routes) to the top results.

Show search is slightly different — it joins `shows` with `venues`, concatenates searchable text from multiple columns (show ID, date, event name, tour name, venue name, city, state), and runs substring matching against the combined text.

This is straightforward text matching — no embeddings, no semantic similarity. It works well because the Dead domain has bounded vocabulary (song titles, venue names, dates) and the model formulates specific search terms.

### Context methods

When a tool like `get_show` is called, the database layer doesn't just return a single row. The store's **context methods** join multiple tables to produce rich payloads:

- `show_context()` fetches the show + venue + all performances + performers + recordings + show links + equipment + resources. One show becomes a full payload.
- `song_context()` fetches the song + writers + all performances + arrangements + resources + release tracks + performance links.
- `performance_context()` fetches the performance + show + venue + song + recordings + links + resources + set neighbors (previous and next songs in the same set).
- `album_context()` fetches the release + tracks + personnel + song lookups.

These are the building blocks the model works with. Each tool call returns a rich, pre-joined payload that the model reads before deciding what to do next.

## What the experience looks like

The browser shows one page for each question: the answer at the top, then sections of things to hear and see. The model decides what the page says and holds; the application fills in every fact and renders it.

### The model's page

When the model has gathered enough material, it calls `finish_response`, a terminal tool whose arguments *are* the page. Those arguments are a `PagePlan` (`deadbot/page_plan.py`):

- **`headline`** — an optional short line above the answer.
- **`answer`** — the answer to the question, in markdown: paragraphs, lists or a table.
- **`sections`** — the rest of the page in reading order. Each section has an optional `heading`, optional `text` (the model's own words, in markdown) and `items`.

The model writes IDs and its own words; it never writes a date, a setlist or a link's target. Every ID must come from a tool result in this conversation (or its research notebook).

### The eleven items

A section's items are the page's components. Each one names records by ID and the server supplies their facts and players.

| Item | What it shows |
| --- | --- |
| `performances` | Performances to play in order: one song across nights, or several songs from one night. A note per performance. |
| `pairing` | Chosen nights of two songs played back to back, from a `get_segue_pairing` result, drawn to one clock. |
| `show` | One show: its setlist, lineup and player. With `play`, it becomes the page's opening player, starting at a set or a song. |
| `shows` | Many shows as rows that open and play, by ID or every show in a `look_up` result. |
| `release` | One official release: play button, tracklist and personnel. |
| `releases` | Many official releases as rows that open and play. |
| `song_years` | A song's life year by year: times played or typical length, each year opening to its performances. |
| `chart` | An `aggregate_data` result as bars or as a ranked list with the model's notes on rows. |
| `grid` | A `get_grid` result as a table, every cell playable. |
| `people` | Band members and guests as bars across the years they played, with show counts. |
| `links` | Interviews, articles, podcasts and videos the tools returned. |

`show`, `release` and `song_years` start open by default and can start as one closed row.

### From the page to the response

The server reads the page into an internal plan (`deadbot/finish.py`: a lead and groups of body items) that hydration, streaming and stored pages share. Each section becomes a group; each item becomes one or more body items (`page_plan.body_items`), which resolve to the blocks the browser renders:

| Item | Block in the response |
| --- | --- |
| `performances` | `song_versions` |
| `pairing` | `version_strip` |
| `show` | `show_unit`, or `listening_hero` when it names where to start playing |
| `shows` | one collapsed `show_unit` per show |
| `release`, `releases` | `album_unit` |
| `song_years` | `song_overview` |
| `chart` | `data_chart` or `ranked_list` |
| `grid` | `grid` |
| `people` | `people_timeline` |
| `links` | `media_link` for a URL, `resource_list` for stored resources |

One more block carries the model's own words: `editorial`, a block of prose. The server writes it in three cases, so the model's work always stays on the page:

- A section with a heading or text and no cards (none planned, or none resolved) shows its text as prose under its heading.
- An item that does not fit any component keeps its title and text as prose.
- A reference that does not resolve to a record from this turn keeps the model's note as prose, without the record.

A turn that ends without a page returns a `gap_state` block and an honest message. The response carries `schema_version` (`"4"`); the browser uses it to set aside pages it saved under an older vocabulary.

### Follow-ups

A follow-up is a new question in the same conversation. The browser sends it with the conversation so far and the signed research notebook the previous response returned, so the model starts from what it already found (`read_notebook`). Three places on a page start one:

- **The question box**, for anything the visitor types.
- **An opened row** on a chart or ranked list. The row opens in place to that record's facts and one recording, from `GET /api/rows/{id}` with no model call, and offers one question the server writes from the record ("The story of Playing In The Band on stage").
- **A grid cell or a year on a song's timeline.** The question carries what the visitor was pointing at (`focus`: the block, the IDs, a few facts), which the model reads as a note and may place on the page without looking it up again.

The model's page schema has no follow-up field: the model does not write suggested questions.

### Streaming

The page renders as the model writes it. A character-by-character scanner (`PlanStreamer`, `deadbot/plan_stream.py`) reads the `finish_response` arguments as they arrive and emits events:

1. **`page_head`** — headline and answer, as the sections begin.
2. **`group_open`** — a section's heading and text as its items begin.
3. **`block`** — each item, resolved and hydrated, as it closes in the text.
4. **`group_close`** — when a section closes. A section that closes with no blocks sends its words as a prose block first.

The answer also streams on its own as it grows (`lead` events, from `LeadAccumulator`), and `status` events say what the model is doing. When the plan is complete the server builds the whole response and the browser replaces the draft with it.

If the model's call is rejected and it writes another, the streamer emits `page_reset` and the draft starts over. If the model restates its sections inside one call, `groups_reset` starts the sections over.

### Grounding and validation

`deadbot/finish.py` builds a `GroundedContext` from every tool result in the turn: every ID and every URL that appeared in tool output, plus the research notebook's and the visitor's click. During resolution:

- Every referenced ID is checked against this set and then read from the store. The card's facts come from the store, never from the model.
- A markdown link in the model's words is kept only when its URL came from a tool result; otherwise it is unwrapped to its words.
- The plan is read leniently: extra keys are ignored, a bad list entry or optional field is removed and the rest kept, an older key (`lead` for `answer`, `title` for a section's `heading`) reads as the key it meant, and an item written straight into `sections` stands as a section of its own. Nothing caps how many sections or items the model plans; only transport ceilings far above normal use (1,000 entries per list, 200 blocks per page) truncate, with a log line.
- The streamer and the final response read every key and resolve every item through the same functions (`page_plan.finish_args` and `body_items`, `validate_body_item`, `resolve_items`, `group_words`, `words_alone`), so the draft the visitor watched and the delivered page hold the same sections. `tests/test_stream_final_parity.py` runs one plan through both.

The result is a validated `ExperienceResponse` that the React client renders as deterministic application code. The model chose what to show and how to frame it. The system guarantees that everything it chose is real.
