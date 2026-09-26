# Decisions

## ADR-001 — PostgreSQL as initial operational database

**Decision:** PostgreSQL is the initial operational database.

**Reasoning:** It provides strong relational querying, straightforward hosting, a mature ecosystem, JSONB when source-shaped data is needed, a future pgvector option, and enough graph-like relationship support for the initial domain.

## ADR-002 — Canonical CSV + raw JSONL

**Decision:** Use canonical CSV for normalized data and raw JSONL/NDJSON for collected source records.

**Reasoning:** The formats are inspectable, Git-friendly, portable, easy to generate and import, and preserve separation between source data and normalized data.

## ADR-003 — Relational graph before dedicated graph database

**Decision:** Model the graph-shaped domain in PostgreSQL before considering a dedicated graph database.

**Reasoning:** Current relationships are represented cleanly in PostgreSQL. This avoids premature Neo4j or comparable infrastructure. Reassess only if multi-hop graph traversal becomes a real limitation.

## ADR-004 — No audio stored in Git

**Decision:** Do not store audio in this repository.

**Reasoning:** Recordings remain externally hosted; the repository stores metadata and resolvable identifiers. This avoids large binary files and rights complications.

## ADR-005 — Primary source by fact type, with preserved evidence

**Decision:** Select a primary source for each fact type before populating canonical data. Do not designate one source as universally authoritative for every entity and relationship.

**Reasoning:** Different sources may be strongest for different claims: show and setlist information, venue details, songwriting credits, recording lineage, and official-release metadata are distinct fact types. Raw records will preserve every source value and identifier. Canonical records will initially follow the chosen primary source for their fact type, while documented corrections and later conflicting-source reconciliation remain possible.

**Implementation note:** The specific primary sources are intentionally `TBD` until the candidate-source review is completed. Before collection begins, document the selected primary source, fallback source, and override rule for each fact type.

## ADR-006 — Source-specific song arrangements and chord charts

**Decision:** Model chords as ordered sections of a source-specific song arrangement, linked to a resource, rather than as one universal chord chart on a song.

**Reasoning:** Chord charts can differ by key, transposition, performance, instrument, and transcriber's interpretation. Separating resources, arrangements, and chord sections preserves attribution and allows multiple valid versions without overwriting one another. The repository stores structured chord symbols and links; it does not copy full tablature, lyrics, notation, or audio.

## ADR-007 — External media links; structured release relationships

**Decision:** Keep audio, video, streaming, and detailed instructional content externally hosted. Store resolvable link metadata in the graph. Model official releases and their performance-track mappings as structured data.

**Reasoning:** External providers own delivery, rights, playback, and availability. Deadbot needs to answer what a link represents and how an official release track relates to a performance, but it does not need to duplicate the media. Official release-track mappings are durable domain relationships; provider URLs remain links that can be updated independently.

## ADR-008 — Generic resources with typed entity relationships

**Decision:** Represent interviews, essays, reviews, lessons, tabs, videos, and other external references as generic resources attached through typed song, show, and performance relationship tables.

**Reasoning:** One interview can concern a song and a specific show; one article can discuss several performances. Typed relationship tables retain relational integrity and give the future model a direct, structured route to relevant links before it invokes browsing or document retrieval.

## ADR-009 — LangGraph as the permanent agent harness

**Decision:** Use LangGraph as Deadbot's permanent agent harness.

**Reasoning:** Deadbot needs a bounded agent loop with explicit state, inspectable tool calls, durable sessions, and clear approval points for future writes. The conversational agent is not a fixed workflow: it loops between a model and selected tools until it can answer. Deterministic ingestion, validation, and publication jobs may use fixed subgraphs within the same harness.

**Implementation note:** The initial graph is read only and bounded by `DEADBOT_MAX_TOOL_ROUNDS`. It is deliberately small: entity resolution, graph lookup, resource retrieval, and media links only.

## ADR-010 — Model-provider abstraction; local Ollama pilot

**Decision:** Keep model providers behind a small Deadbot adapter contract. Start the local pilot with Ollama and `qwen3:8b` in non-thinking mode.

**Reasoning:** The LangGraph harness, tool contracts, prompts, state, tests, and canonical data must not depend on one model service. A provider may change later without changing the harness. The initial local model supports tool calling while keeping development private and self-contained.

**Implementation note:** The initial provider configuration is in `.env.example`; provider adapters live in `deadbot/models.py`. Enable thinking mode only after evaluation demonstrates a benefit for real Deadbot questions.

## ADR-011 — FastAPI experience layer and schema-driven composition

**Status:** The FastAPI + React decision stands. Its composition rules (the
allowlist framing, the deterministic adapter first, validation that rejects
model output) are superseded by ADR-014.

**Decision:** Build Deadbot's user-facing application with FastAPI and a React + TypeScript client. The agent's grounded retrieval output is transformed into a versioned, validated response containing an answer, source metadata, and a sequence of allowlisted content blocks. The client renders those blocks with deterministic application code.

**Reasoning:** Deadbot needs an explorable music-and-research experience, not a plain chat transcript. Reusable cards, source lists, media players, and provenance notes allow the application to present different kinds of grounded information clearly. FastAPI fits the current Python and LangGraph runtime, keeps model and data access server-side, and can serve the compiled client in one deployable application. React is a suitable client for composing and testing these interactive reusable patterns.

The model may select and order approved blocks; it must not generate HTML, CSS, JavaScript, iframe markup, or arbitrary URLs. Server-side Pydantic validation ensures that every entity, resource, media link, and quote refers only to data present in the approved retrieval packet. This retains model flexibility without allowing it to bypass provenance, rights, or media safety rules.

**Implementation note:** Begin with a deterministic adapter that produces the same response contract from agent/tool results. Add a separate model-guided composer only after the contract, renderers, and evaluation examples are in place. Spotify and YouTube embeds, when supported, are built by trusted provider adapters from approved stored media links; all other links remain normal outbound links. See `docs/experience-architecture.md`.

**2026-09 update:** The separate model-guided composer described above was
built, then merged back into the single research model: one model now ends
its turn by calling `finish_response` with the chat answer and body plan in
one step, and `deadbot/finish.py` resolves that plan into the same validated
response contract. Do not reintroduce a second model step or a handoff
between models; see `docs/agent-harness.md` and `docs/experience-architecture.md`.

## ADR-012 — Bounded, retry-safe collection passes

**Decision:** Organize collection as bounded enumeration and typed enrichment
passes. Preserve compact raw evidence separately from canonical conclusions,
and fail closed when a retry returns broad transport errors or unexpectedly
empty results.

**Reasoning:** The 1972 pass showed that no single source is best for shows,
recordings, composition credits, lyric availability, and historical context.
Title-only catalog searches also produce plausible but unrelated works, and a
network failure can otherwise look like a real source absence. Reviewable
passes with explicit held cases preserve progress without turning uncertainty
into false certainty.

**Implementation note:** Each pass records requested/successful/unresolved/
promoted/held counts, uses stable IDs and idempotent relationships, and ends
with source, relational, and behavior validation. Full lyrics, tabs,
transcriptions, audio, and video remain external links or compact metadata.
See `docs/collection-methodology.md`.

## ADR-013 — Base facts before derived observations; prose at request time

**Decision:** Build each insight in dependency order: preserve source evidence,
review canonical entities and relationships, import that snapshot into
PostgreSQL, then compute versioned structured observations. Store an
observation's calculation version, input revision, coverage boundary, and
supporting entities/resources. Compose visitor-facing prose at request time.

**Reasoning:** Derived insight is trustworthy only when its inputs and coverage
are inspectable. Versioning makes a result reproducible and replaceable when
the collection improves, while request-time prose prevents an old narrative
from surviving after the underlying graph changes. This order applies per
dataset slice or question family; it does not require collecting the band's
entire history before shipping useful, clearly bounded insights.

**Implementation note:** CSV remains the reviewed source of truth during the
transition. PostgreSQL is the operational projection and query surface. A
dedicated graph database is still deferred until measured traversals show that
relational joins and indexes are insufficient.

## ADR-014 — Code guards facts; the model owns judgment

**Decision:** Divide the experience layer's work in two. Code guards facts and
transport: it resolves referenced IDs to stored records, fills cards' facts
from the store, builds players and links from stored or tool-returned URLs,
parses the streamed plan, and renders it. The model owns every editorial
choice: what to say, what to show and omit, depth, order, grouping, disclosure,
and the split between chat and page. Code reads the model's plan leniently and
keeps its work on the page; it does not reject or strip output for editorial
reasons.

**Reasoning:** Deadbot's quality comes from the model's judgment. The earlier
safety-first framing (an allowlist the model "may select from," validation
that rejects a call, caps on list and group sizes) accumulated checks that
silently removed the model's work: whole lists dropped over an item cap, cards
dropped over one extra key, and components that streamed and then vanished from
the finished page. Each check was written to fix one example and broke the
next. The same principle governs the CFP and AKF assistants.

**Components as freedom:** Deadbot is a software interface over a structured
music library, not an open-ended knowledge base, so it leans into components
more than a general assistant would. The right component for a task gives the
model freedom: a show, a performance, a song's stage life, an era, a version
strip, a ranked list, a chart. The model names records and chooses
facets and disclosure; code supplies the facts. A new component is added when
the model has a relationship or pattern to express that the palette cannot
hold, and it is designed for the family of questions that need it.

**Implementation note:** Plan items ignore unknown keys; a bad field is removed
and the item kept; a reference that does not resolve renders the model's own
text; an item that fits no component becomes prose; size ceilings sit far above
normal use and truncate with a log. Streamed and final pages share one path.
Before adding a check, ask whether it protects a fact or the transport; if it
only polices the model, leave it out. See `AGENTS.md`.
