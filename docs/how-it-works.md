# How Deadbot works

This document walks through the three layers that make Deadbot go: what's in the database, how a question turns into tool calls against it, and how the results become a composed page in the browser. It's written at a moderate technical level — enough to see the mechanisms, not a code tour.

For the product goals and design philosophy, see [product-vision.md](product-vision.md) and [experience-brief.md](experience-brief.md).

## The database

### What it holds

The PostgreSQL database holds the **canonical catalog** — every fact Deadbot can draw on when answering a question. It's organized around five core entities and the relationships between them.

**Shows** are the backbone. There are roughly 2,300 of them, each with a date, venue, tour, and full setlist. A **performance** is one song played at one show: it carries the set number, position, segue information, and links to recordings and streaming audio. This is the key join table — it's how "Scarlet Begonias" at Cornell '77 is a different record from "Scarlet Begonias" at Veneta '72.

**Songs** are compositions: title, writers, arrangements, first and last known Dead performance. **People** are musicians — band members, guest performers, songwriters — with band membership records that track roles, instruments, and date ranges. **Venues** carry location, capacity, and indoor/outdoor setting. **Equipment** tracks specific instruments (Tiger, Wolf, Rosebud) and their show assignments.

Around these core entities sit several supporting layers:

| Layer | What it holds | Example |
| --- | --- | --- |
| **Recordings** | Audience tapes, soundboards, archive.org identifiers, tapers and transferers | Charlie Miller SBD of 5/8/77 |
| **Official releases** | Albums with track-level mappings back to specific performances, personnel, Spotify links | *Dick's Picks Vol. 36* |
| **Resources** | External links to articles, interviews, oral histories, reviews, tabs, videos | A Dead.net oral history of "Dark Star" |
| **Selections** | Curated picks from critics, fans, and official sources, with source attribution | A "best Estimated Prophet" list from a published book |
| **Claims** | Sourced factual statements tied to one or more entities | "Jerry used Tiger for the first time on 8/4/79" |
| **Observations** | Derived stats computed from the data, versioned against the import that produced them | Song performance counts, first/last dates, set-neighbor frequency |

The whole schema is about **30 tables** with strict foreign keys, check constraints, and referential-integrity triggers. It's at schema version 9, with migrations applied as plain SQL files in sequence. There are no embeddings or vector columns — all text matching is done with SQL `LIKE` queries.

### How data gets in

The database is populated from **23 reviewed CSV files** (~48 MB total) that live in the repo under `data/canonical/`. These CSVs are the version-controlled source of truth. The pipeline looks like this:

```
External sources → collection scripts → raw JSON in data/raw/
                                            ↓
                                    normalization scripts
                                            ↓
                                    canonical CSVs in data/canonical/
                                            ↓
                                    deadbot db-import → PostgreSQL
```

**Collection** scripts in `scripts/collect/` pull raw data from external sources: Jerrybase for setlists, MusicBrainz for release metadata, Internet Archive for recording indexes, Relisten for streaming links, Wikidata and Wikipedia for biographical facts, dead.net for official material, and several others. These produce raw JSON files preserved in `data/raw/`.

**Normalization** scripts transform that raw data into the canonical CSV format — resolving entity identities, deduplicating, and fitting everything to the strict column-and-type contracts defined in the import code.

**Import** is a CLI command (`deadbot db-import`) that runs in a single database transaction. Before writing anything, it validates every CSV against its table contract (column names, types, nullable rules). It then creates a SHA-256 content manifest of the exact files used, so we know precisely which data produced which database state. If validation fails, nothing is written.

There are two import modes:
- **Merge** (the default) — `INSERT ... ON CONFLICT DO NOTHING`. New rows are added; existing rows are left alone.
- **Rebuild** (`--rebuild`) — clears canonical tables in reverse dependency order, then reloads everything. Does not drop the schema itself.

After the CSV data loads, a separate step atomically replaces selection evidence from a reviewed editorial JSON file, generating the `resources`, `selection_lists`, `selection_entries`, and `selection_evidence` rows that power the curated-picks tools.

Every import records a ledger row in `canonical_imports` for auditability.

### At runtime

The database is **read-only at runtime**. The only write the application ever makes is caching its own answers for repeat questions (in `deadbot_response_cache`). All catalog data enters through the import pipeline.

The app runs on Vercel as a serverless function. A single Postgres connection is created lazily on first query, transparently reopened if it drops (important for serverless cold starts), and shared across requests in that function instance. The database URL comes from Vercel environment variables.

There's a **per-request query cache** at the data layer: since the data is read-only, the same SQL query within one request returns the same rows without hitting the database again. This matters because the composition step often re-fetches entities the model already looked up during research.

The entire data layer is **hand-written parameterized SQL** through Python's standard DB-API interface. No ORM, no SQLAlchemy. Table and column identifiers are validated against a strict pattern and double-quoted. User input never enters identifiers.

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
LangGraph agent loop (up to 8 rounds)
    ↓
    ├─→ Agent node: LLM decides what to look up
    │       ↓
    ├─→ Tools node: executes tool calls
    │       ├─→ Catalog tools → PostgreSQL queries
    │       └─→ External tools → web fetches
    │       ↓
    └─→ Results return to model for next round
    ↓
Model calls finish_response (terminal tool)
    ↓
Composition: resolve references → PostgreSQL
    ↓
Grounding check: drop anything not in tool output
    ↓
Validated ExperienceResponse → browser
```

### Cache layer

Before the model runs at all, the system checks whether this exact question (normalized to lowercase, punctuation-stripped) has been answered before with the current data version and code commit. If so, the cached response is returned instantly. Only first-turn questions are cached — follow-ups in a conversation aren't. Failed or gap answers are never stored.

### The agent loop

On a cache miss, the question enters a LangGraph state graph with two nodes that alternate:

1. **Agent node** — the language model receives the question, a system prompt describing how to research Grateful Dead topics, and results from any prior tool calls. It decides what to look up next.
2. **Tools node** — executes whatever tool calls the model requested and returns the results.

The routing logic is simple: if the model made tool calls, go to the tools node; if a successful `finish_response` result is in the messages, end the loop; otherwise, return to the agent node for another round. The recursion limit is 8 tool rounds (20 LangGraph steps).

### The 26 tools

The model has access to 26 read-only tools, all defined in `deadbot/tools.py`. They fall into three groups:

**Catalog tools** query the PostgreSQL database:

| Tool | What it does |
| --- | --- |
| `search_entities` | Fuzzy search across songs, shows, people, venues, equipment, and releases |
| `get_show` | Full show context: venue, setlist, performers, recordings, equipment, links |
| `get_song` | Song overview: writers, performance summary, arrangements, releases, resources |
| `get_performance` | One rendition's context: show, venue, set neighbors, recordings, links |
| `get_album` | Official release: tracklist mapped to performances, personnel, listening links |
| `list_song_performances` | Paginated chronological list of a song's performances |
| `get_song_performance_profile` | Derived counts, first/last/neighbor stats for a song |
| `get_song_notable_versions` | Renditions with official releases and critic/curator/fan signals |
| `get_selections_for` | Reviewed selection signals for one song or show |
| `get_show_selections` | Reviewed show selections for discovery questions |
| `get_selection_signals` | Complete reviewed critic/fan/curator selection inventory |
| `search_guest_musicians` | Find guest musicians and the shows they played |
| `get_equipment_history` | First/last show assignments for a named instrument |
| `get_media_links` | Listening/viewing links for a show or performance |
| `find_arrangements` | Song arrangements by key signature |
| `get_recording_reviews` | Archive.org listener reviews and star ratings |

**External research tools** fetch from the web:

| Tool | What it does |
| --- | --- |
| `search_stored_resources` | Search the cataloged resource inventory by keyword |
| `get_deadnet_song_context` | Dead.net metadata page for a canonical song |
| `get_deadcast_metadata` | Metadata for an official Deadcast episode |
| `get_lore_source_trails` | Reviewed lore links for a song or show |
| `get_research_source_directory` | List of research sites with what each is good for |
| `search_site` | Search one external research site (Lost Live Dead, archive.org, etc.) |
| `read_page` | Read any web page's text |

**Context tools** provide supplementary information:

| Tool | What it does |
| --- | --- |
| `get_historical_weather` | Historical weather for a show's venue and date |
| `get_astronomy` | Sun and moon data for a show's venue and date |
| `get_astrology` | Western zodiac sign for a show's date |

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

The browser presents two surfaces that complement each other instead of repeating each other:

- **The chat pane** holds the direct conversational answer — a few sentences that address the question.
- **The composed page** holds the broader payoff: entity cards, listening paths, editorial context, and follow-up routes, organized by the model's editorial judgment about what matters and how it relates.

The page isn't a chat transcript with cards bolted on. The model produces a structured plan that decides what to emphasize, how to group it, and what presentation fits. The application renders that plan as a composed layout.

### The model's plan

When the model has gathered enough material, it calls `finish_response` — a terminal tool whose arguments *are* the answer. Those arguments are a `FinishPlan` containing:

- **`chat_answer`** — the direct text answer for the conversation pane.
- **`title`** — the page headline.
- **`lead`** — optional expansion of the central finding.
- **`groups`** — up to 8 groups, each containing items (semantic unit references and editorial blocks).

The model writes this plan from what it retrieved. Every reference (a show ID, a song ID, a performance ID) must trace to a tool result from the same conversation. References that don't are silently dropped during resolution — the answer can only contain things the model actually looked up.

### Semantic units

The building blocks of a page are **semantic units** — typed, data-rich components that the model references by ID and the server hydrates from the database. Five primary unit types carry the weight:

**Show unit** — a full show card. The model provides a `show_id` and chooses which facets to display (setlist, guests, lineup, recordings, listen actions). The server hydrates it with the venue, date, full setlist with set labels and positions, performer names and instruments, recording identifiers, and streaming links. The setlist can be expanded, collapsed, or hidden. The model can highlight specific performances and prefer a specific recording.

**Song overview** — a composition across its entire life. The server provides the performance count, a history strip (first performance, last performance, by-year counts), representative versions the model selected, writing credits, and official releases the song appears on. The model chooses which facets to show and which performances best represent the song.

**Performance unit** — one rendition of one song at one show. The server provides the song, venue, date, set label, position in set, the previous and next songs in the same set (so you see the flow), and listening links. This is where a specific version lives — not the song in general, but this version on this night.

**Album unit** — an official release. The tracklist maps each track back to its specific live performance (show, date, venue), with personnel, duration, and streaming links. The model can highlight specific songs.

**Era unit** — a named stage in a song's development (e.g., "1972–1974: the exploratory years"), with representative performances that illustrate it. The model defines the era's title, span, and interpretive note; the server fills in the performance details.

### Emphasis

Each unit carries an **emphasis** level that controls its rendering scale:

- **Primary** — full width, facet tabs start open. Used for the main subject of the answer.
- **Supporting** — compact card. Used for context or comparison items.
- **Mention** — collapses to a single line with a listening link. Used when an entity deserves a reference but not a full card.

The model chooses emphasis based on how central each entity is to the answer. A question about Cornell '77 might render that show as primary, with supporting cards for the songs the model wants to highlight and mentions for others referenced in passing.

### Groups and editorial structure

Units don't just stack in a list. The model organizes them into **groups**, each with a presentation mode:

- **Collection** — a grid of peers. Five notable Dark Stars, shown side by side.
- **Sequence** — a development or route on a numbered spine. How a song evolved across decades.
- **Comparison** — items judged on shared criteria, rendered in aligned columns. The model names the criteria (e.g., "energy," "improvisation," "recording quality") and writes a judgment for each unit on each axis.
- **Argument** — a claim as the group heading, with evidence beneath.

Groups can carry titles, leads, and up to 20 items. A page can hold up to eight groups. This gives the model a real editorial vocabulary — it's choosing structure, not just listing results.

### Editorial blocks

Alongside the data-hydrated units, the model can write its own material as **editorial blocks** in three forms:

- **Narrative** — prose paragraphs for interpretation, argument, or synthesis.
- **Fact grid** — compact label-value pairs for cross-comparison, including attributed viewpoints from critics or fans.
- **Timeline** — chronological entries with markers, titles, and detail text.

These are where the model's synthesis and voice live. But every link in an editorial block must trace to a URL the tools actually returned, or it's stripped before rendering. The model can write; it can't invent sources.

### Other block types

The block catalog also includes focused components that appear when the question calls for them:

- **Equipment list** — which guitars Jerry played at a show, with manufacturer, model, and evidence.
- **Guest appearance list** — a guest musician's canonical show appearances with dates, venues, and instruments.
- **Person roster** — a complete section of people under a heading (the '77 touring lineup, or every drummer who sat in).
- **Arrangement** — chord progressions from a specific source, with key signature, capo, and tuning.
- **Show selection** — source-attributed lists from critics, fans, and official publications.
- **Media link** — an embeddable YouTube or Spotify player.
- **Resource list** — external reading and listening links with publication details.
- **Coverage note** — an acknowledgment of gaps in the catalog, so the model can say what it doesn't know.

### Follow-ups

Every semantic unit and editorial item can carry **follow-up topics** — short labels that render as chips beneath the content. Pressing one sends a new question into the conversation. The reader moves naturally from a show card to a deeper question about one of its songs, or from a song overview into a specific era. These are how the experience creates pathways through the catalog rather than dead-ending at an answer.

### Streaming

The page renders progressively as the model writes. A character-by-character JSON scanner (`PlanStreamer`) parses the `finish_response` arguments as they stream token by token, emitting events:

1. **`page_head`** — title and lead, as soon as they're known.
2. **`group_open`** — a group's metadata (title, presentation mode, criteria) as its items array begins.
3. **`block`** — each item, resolved and hydrated, as it closes in the JSON stream.
4. **`group_close`** — when a group object closes.

The chat answer streams separately into the conversation pane at the same time (extracted by `AnswerAccumulator`). The browser lays out the page progressively as blocks arrive. When the full plan is complete, the server validates the entire response and the draft is replaced with the final grounded version.

If the model's plan fails validation, it can retry — the streamer emits a `page_reset` event that clears the draft, and the model writes a new plan.

### Grounding and validation

The composition layer (`deadbot/finish.py`) builds a `GroundedContext` from every tool result in the conversation — a frozen set of every entity ID and every URL that appeared in tool output. During resolution:

- Every entity reference (show ID, song ID, performance ID) is checked against this set. Ungrounded references are silently dropped.
- Every URL in an editorial block or supporting source is checked. Ungrounded links are stripped.
- The finish plan's own validators enforce structural limits: max 8 groups, max 20 items per group, valid presentation modes.
- Items that fail schema validation are dropped individually — they don't reject the whole response.

The result is a validated `ExperienceResponse` that the React client renders as deterministic application code. The model chose what to show and how to frame it. The system guarantees that everything it chose is real.
