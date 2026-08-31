# Development plan

This document is the current implementation plan for Deadbot. It should be updated as work finishes, priorities change, or a decision becomes durable enough to add to `docs/decisions.md`.

## Product direction

Deadbot is a provenance-aware Grateful Dead knowledge and music assistant. It should answer questions using structured, reviewable data; clearly distinguish canonical facts from interviews, editorial analysis, and personal recollections; and provide external media and reading links instead of copying protected material.

The first vertical slice is the Grateful Dead's 1972-08-27 Veneta, Oregon performance. It is intentionally small enough to validate the whole path from canonical data to a local tool-calling agent.

## Accomplished

### Data and provenance

- Established source → raw JSONL → normalization → canonical CSV → PostgreSQL architecture.
- Chose fact-type-specific provenance rather than a single universal canonical source.
- Created the relational schema for songs, shows, performances, recordings, people, resources, source-specific arrangements, and external links.
- Modeled interviews, articles, oral histories, memoirs, tabs, and media as generic resources with typed song/show/performance relationships.
- Preserved raw source records for the initial JerryBase, gdshowsdb, Internet Archive, Spotify, YouTube, RUKIND, and contextual-resource collection passes.

### Veneta vertical slice

The original Veneta vertical slice contains:

| Entity or relationship | Current count |
| --- | ---: |
| Shows / venues | 1 / 1 |
| Songs / Veneta performances | 20 / 20 |
| People / show-performer assignments | 7 / 10 |
| Recordings / performance-recording mappings | 1 / 20 |
| Generic resources | 22 |
| Song / show / performance resource links | 24 / 5 / 11 |
| Official releases / release tracks | 1 / 21 |
| Show / performance media links | 1 / 1 |
| Source-specific chord arrangements / sections | 1 / 4 |

These counts describe the original pilot slice only and predate the full
collection, which now spans 1965-1995. See `docs/data-audit-2026-08-27.md`
for the current, verified row counts and coverage gaps across every
canonical table.

The subsequent 1972 bulk pass expanded the canonical show/performance layer to
86 shows, 51 venue instances, 80 songs, and 2,229 performances. It also added
362 Internet Archive recording-index rows across all 86 shows. The year-level
coverage and remaining gaps are tracked in `docs/collection-status-1972.md`.

The current resource set gives every one of the 20 Veneta songs at least one contextual link. It includes official Dead.net/Deadcast material, independent reporting, a clearly labeled eyewitness memoir, an archival interview, tab/chord material, and playback/video links. See `docs/veneta-song-dossiers.md`.

### Agent harness

- Selected **LangGraph** as the permanent harness.
- Implemented a bounded read-only tool loop: model → selected tool(s) → model → answer.
- Added a provider contract so models are swappable without changing the graph or tools.
- Added the initial local Ollama provider and downloaded `qwen3:8b` on the development machine.
- Added five local canonical-data tools: entity search, song lookup, show lookup, performance lookup, and media-link lookup.
- Added a terminal chat command, in-memory session checkpoints, environment-based configuration, and seven automated tests.

### Experience architecture

- Chose FastAPI as the HTTP application layer and React + TypeScript as the interactive client.
- Defined a schema-driven composition approach: grounded retrieval produces a validated response made of an answer, provenance metadata, and allowlisted content blocks; the client renders those blocks deterministically.
- Defined the initial block catalog and safety rules for cards, resource lists, Spotify/YouTube media embeds, source-specific chord resources, short permitted quotes, and explicit coverage gaps.
- Documented the durable architecture in `docs/experience-architecture.md` and ADR-011.

### Experience foundation

- Added a FastAPI application with health and experience endpoints, injectable
  runtime dependencies, stable browser-to-agent thread IDs, and production
  static-client delivery.
- Added versioned Pydantic experience models and a deterministic adapter that
  transforms grounded tool results into only allowlisted cards, resource lists,
  media links/embeds, source-specific arrangement summaries, provenance notes,
  and gap states.
- Added a React + TypeScript client with an accessible question flow and
  deterministic renderers for every initial block type.
- Added trusted Spotify and YouTube embed adapters that derive only provider
  identifiers from stored canonical links. Official-release summaries are now
  returned by show and performance lookup, making approved Spotify playback
  available to the experience layer.
- Added API, schema, media-validation, static-client, and composition tests.
- Added a two-column workspace: the left conversation thread keeps the current
  browser session's turn-by-turn context and shows short inline replies; the
  right content column refreshes to the latest turn's grounded composition.
- The browser reuses one opaque thread ID, which maps to LangGraph's in-memory
  checkpoint. Conversation context lasts for the current server process only;
  durable user history remains a separate future decision.
- Added a model-guided composer that receives an enriched decision brief:
  grounded answer, recent conversation, candidate scope/purpose/provenance,
  known performance evidence, and current library coverage. It returns
  model-selected primary, supporting, context, and media regions using only
  server-owned candidate indexes; invalid or unavailable-model results fall
  back to the deterministic candidate order.
- Added a main-panel mode label and title so the composed result does not
  begin as an unexplained card grid. The browser labels the model-selected
  experience mode while the conversation column retains the direct
  conversational answer. (The main panel's own answer-lead paragraph came
  later; see "Experience refinements" below.)
- Added canonical performance-spine blocks for the immediately adjacent songs
  in a rendition's documented set, plus musician-facing arrangement cards that
  preserve source-specific key, scope, capo, tuning, and note fields.
- Added `find_arrangements`, a read-only key-search tool that returns only
  documented source-specific arrangements and explicitly does not claim a
  universal song key or complete transposition coverage.

### Experience refinements

- The main panel now opens with the composed answer text — `response.answer`
  rendered as an answer-lead paragraph directly under the content heading —
  so the panel leads with the direct answer instead of an unexplained card
  grid or bare mode label.
- Follow-up clicks now continue the same conversation thread instead of
  resetting it; a separate "New chat" control starts a fresh thread with a
  fresh thread ID.
- Added a quiet sources footer that lists the response's deduplicated
  provenance registry with canonical/external-source chips and outbound
  links.
- Moved every block's composer guidance out of the shared system prompt and
  into a structured `usage_guidance` field on each candidate's brief entry.
  The system prompt itself shrank from roughly 677 words to roughly 206
  words of durable principles.
- Added `comparison_strip`, a block that places one representative rendition
  of a song per known year with an explicit coverage note, making
  `comparison` mode expressible for the first time.
- Ambiguous show dates (60 dates in 1966-1970 carry two shows apiece) now
  return the concrete candidate shows — show_id, venue, city, event — from
  `get_show`, `get_media_links`, and the weather/astronomy/astrology tools
  instead of a silent not-found. The system prompt tells the model to pick a
  candidate or ask the visitor; a date with no show at all still reports a
  plain not-found without any external fetch.
- Added `docs/data-audit-2026-08-27.md`, a from-source, verified row-count
  and gap audit of every canonical table, with a prioritized list of next
  data work. It is the current reference for coverage numbers; see "Veneta
  vertical slice" below.
- Added immutable content-addressed canonical snapshot manifests and an
  append-only PostgreSQL import ledger. Each successful import now reports a
  `sha256:...` input revision, distinguishes bootstrap/rebuild from a
  non-destructive merge, and gives future derived observations a
  foreign-keyed revision reference. Schema v2 includes the explicit v1 → v2
  migration; live import/restart/rollback verification remains outstanding.

## Current boundaries

These boundaries are intentional and should not be bypassed casually:

- Canonical CSV remains the source of truth and zero-setup runtime. PostgreSQL
  is now an optional, rebuildable operational read store selected by
  configuration.
- Agent tools are read only. The agent cannot edit canonical data, download media, or collect arbitrary web content.
- A resource URL is a link-out reference. It does not turn an interview statement, memoir, or editorial interpretation into a canonical fact.
- Do not copy full lyrics, tabs, transcriptions, audio, or video into the repository.
- The local model is useful for harness development, but its answer quality has not yet been evaluated against a Deadbot-specific test set.
- The model-guided composer is selection-only: it cannot write visible facts,
  URLs, iframe markup, HTML, or new block types. It requires an available local
  model to improve layout; model failure returns the deterministic layout.
- `AGENTS.md` records the project-wide model-first principle: favor richer
  grounded context and instructions for ordinary product judgment; reserve
  deterministic code for validation and narrow safety guardrails.
- A model may not generate browser code, iframe markup, arbitrary embeds, or arbitrary external URLs. The future client must render only server-validated, allowlisted blocks.

## Next work

### 1. Evaluate the agent against the Veneta slice

Implemented the model-independent retrieval baseline at `evals/veneta-v1.json`.
It contains 30 versioned cases, a deterministic local runner (`deadbot evaluate`),
and optional JSON reports. It also exposed and closed a show-lookup gap: performer
role assignments are now included in the `get_show` tool result.

The next part of this milestone is a separately scored model-response pass using
the failure conditions in each case. Include:

- direct structured lookups (date, set order, performer roles);
- source discovery (for example, Bird Song and China Cat context);
- media-link requests;
- provenance distinctions (canonical fact vs. source-attributed claim);
- negative cases where the library does not yet know the answer.

**Done when:** the local harness runs the tool set reproducibly, records pass/fail results, and a model-response pass exposes the most important routing, citation, and provenance weaknesses.

### First local model-response findings (qwen3:8b)

A complete 30-case local run is now reproducible with `deadbot evaluate --model`.
It found the following priority weaknesses:

- The model handles straightforward show facts, eyewitness attribution, and a
  full-show media link when the tool accepts an unambiguous show date.
- It often stops after `search_entities` or calls `get_show` when a question needs
  `get_performance`, so performance-specific sources and recording-track details
  are frequently missed.
- Missing-song and missing-performance questions can still produce an irrelevant
  show or venue summary. The system prompt now explicitly forbids this, but the
  negative cases remain failing model evaluations.
- One run produced incorrect non-canonical claims (for example, a France venue
  for the Veneta China Cat > Rider context), confirming that a returned resource
  must not be treated as support for invented prose.

The next retrieval-improvement iteration should add focused tool guidance and
compact performance lookup paths, then rerun the targeted failing model cases
before repeating the full suite.

### 2. Improve local retrieval and response quality

Use evaluation failures to refine tool descriptions, entity resolution, result sizes, system instructions, and the local-model configuration. Do not add a multi-agent swarm or broad web browsing as a substitute for fixing local retrieval.

**Done when:** routine Veneta questions resolve the right graph entities, return relevant links, and preserve attribution reliably.

### 3. Harden the baseline experience

Exercise the web experience against a running local model, and against the
deployed OpenAI-compatible provider configuration (`DEADBOT_OPENAI_MODEL`,
`gpt-4o-mini` by default), with representative Veneta questions, and tighten
the adapter where real tool traces expose missing or redundant cards. Add
browser-level automated checks once a suitable local test runner is selected.
Keep the existing schema, source restrictions, and safe fallbacks intact
while improving visual hierarchy, responsive behavior, and source
presentation.

**Done when:** a browser user can ask representative Veneta questions and see
a validated response that makes canonical data, contextual sources, and media
paths visibly distinct; the full flow is checked with both API and browser-level
tests.

### 4. Evaluate and tune the bounded model-guided composer

The first composer now reasons over an enriched decision brief and selects
server-validated blocks into primary, supporting, context, and media regions.
Each candidate in the brief now carries a structured `usage_guidance` field
in place of block-specific rules that used to live only in the shared system
prompt, which shrank to durable principles as a result. Run the composer
against the configured local model and against the deployed OpenAI-compatible
provider configuration with representative Veneta questions, and compare its
selections to the deterministic candidate order. Tune the model's grounded
brief, instructions, and candidate metadata before adding deterministic
intent routing.

Add example-based evaluations for questions that should emphasize a song card,
show/performance card, media option, chord-resource list, provenance note, or
gap state. Record schema version, candidate count, selected indexes, and safe
fallback category, without logging protected text or private model reasoning.

**Done when:** local-model composition reliably makes a smaller, more relevant
main-column layout while preserving provenance, factual content, and the
deterministic fallback.

### 5. Add curated source research and a restricted source-reader

Build a reviewed source registry plus source-specific, sandboxed research tools.
Start with metadata-only Dead.net/Deadcast adapters, then add restricted
readers that return concise permitted excerpts from returned or stored
resources. The agent answers the question directly and uses research when it
can add a worthwhile connection. Source tools operate through reviewed
source-specific paths; canonical writes remain a reviewed data workflow, and
source accounts stay attributed context.

**Status:** the schema-v3 registry/snapshot contract, a reviewed local
Dead.net/Deadcast registry seed, and a bounded metadata-only Dead.net song
reader are in place. The reader starts from a canonical song, follows the
registry's approved host/path rules, returns explicit `ok`/`empty`/`partial`/
`blocked`/`unavailable` states, and contributes only a vetted resource link to
the model's decision brief and main-column candidate inventory. The same path
has a deterministic resource-list fallback. It retains neither article body nor
lyrics. Source discovery/search, show/performance routes, snapshot persistence,
and any source-specific permitted excerpts remain future work.

The first practical exploration layer now also includes a bounded Deadcast
metadata reader and a six-entity, source-controlled lore-trail catalog for
Friend of the Devil, Sugaree, They Love Each Other, Dancin' in the Streets,
Veneta, and Cornell. These tools return only links, source kind, and a
question-oriented reason to open the source. The response composer can render
reviewed Dead.net, Deadhead High, and Deadessays links as main-column resources;
none of their text becomes a canonical fact. See
`docs/lore-source-trails.md` and `docs/lore-pilot-research.md`.

**Next:** run live-model traces for factual-plus-exploratory answers, then use
the results to improve research invocation, source discovery, main-column
selection, and safe fallback behavior. Add source-specific excerpts only after
rights review. See `docs/serendipity-research-plan.md`.

### 6. Build the canonical CSV → PostgreSQL importer

Implemented a strict, transactional importer for all 21 canonical CSV tables,
a safe explicit rebuild command, an optional PostgreSQL read store behind the
existing tool interface, environment-based store selection, and parity tests.
The schema now also reserves normalized tables for release/show coverage,
curator and fan selections, attributed claims, and recomputable structured
observations. Every successful import records a content-addressed canonical
snapshot and table-result ledger; schema v2 links future observations to that
immutable input revision and upgrades v1 through a checked-in migration.

**Status:** implementation and driver-independent parity tests are complete.
A local Docker PostgreSQL 16 smoke check is complete: a clean schema-v2
bootstrap imported all 107,404 canonical source rows in one transaction,
recorded snapshot
`sha256:524b5c16865ef59bf56174ea4f5eee5e8e7c47985fe874d0af72089e799e4218`,
and served a PostgreSQL-backed Veneta show lookup with the expected 2,358-show
and 39,774-performance coverage summary. The full suite passed with that local
configuration (111 tests). Reconnect, rebuild of an already populated database,
deliberately-invalid-import rollback, and CSV/PostgreSQL parity have since
passed locally. Measured query plans and a production-like deployment
validation remain cutover work.

### 7. Expand the 1972 collection responsibly

Use gdshowsdb as the bulk baseline, JerryBase for review, Internet Archive for recordings, and selected sources by fact type. Add data in reviewable batches; preserve raw records and source-specific identifiers. The first bulk pass is complete: 86 shows, 2,229 performances, and 362 recording rows are now canonical; one full Internet Archive metadata record is preserved for each show. The JerryBase performer pass now adds source-reviewed musicians, guests, and instrument strings for 2,268 of 2,358 canonical shows across 1965–1995. The remaining work is track mappings, additional recording detail, named guitar/equipment history, unresolved song credits, held-date review, and cross-source review.

The year-level pass also established the collection playbook in
`docs/collection-methodology.md`: enumerate the bounded universe first, run
typed enrichment passes, keep compact raw evidence separate from canonical
conclusions, fail closed on transport errors, resolve title aliases in stages,
and hold ambiguous matches rather than guessing. These rules should be used
for every subsequent year and enrichment batch.

**Done when:** a documented 1972 ingestion/reconciliation pass produces validated show/performance/recording coverage beyond the Veneta pilot.

The next 1972 milestone is a deep enrichment pass, not another undifferentiated
scrape. Prioritize recording-to-performance track mappings, release/show/track
coverage, Dick's Picks and other sourced critic or fan selections, attributed
claims and lore, show/performance-specific resources, and supported
equipment/personnel details. Define expected coverage before each pass and keep
claims and selections distinct from canonical event facts.

In parallel, preserve and correct the broad 1965–1995 show/performance spine.
1972 is a proving ground for typed relationships, retrieval, and coverage
language—not the natural scope of cross-decade questions such as how a song
evolved. Any 1972 observation needs a named source universe, input revision,
and supporting entity/resource IDs; it must not imply a career-wide denominator.
See `docs/question-driven-enrichment.md` and
`docs/data-and-retrieval-roadmap.md` for the selection and rollout rules.

### 8. Add bounded PostgreSQL graph retrieval and observations

Replace whole-table or whole-history context with typed, parameterized traversal
plans. Resolve a question to seed entities and scope, then use SQL to follow
only the relevant one-to-three-hop relationships, aggregate large result sets,
rank representative evidence, and paginate detail. Return a compact retrieval
packet containing graph paths, provenance, coverage, gaps, and approved expansion
references.

Start with representative 1972 show, release, selection, lore, and pattern
questions, then run the same plans against sparse early and later eras before
claiming cross-timeline applicability. Compute a small library of versioned
structured observations from the imported graph. Recompute an observation
whenever its calculation version or canonical input revision changes; continue
composing visitor-facing prose at request time.

**Done when:** representative 1972 questions select the correct traversal,
remain within measured context budgets, cite their coverage and provenance, and
produce materially useful connections with drill-down paths. The initial packet
targets are p95 below 10,000 tokens and a 20,000-token hard ceiling.

### 9. Establish the cross-decade song and show-context cohort

Select a stratified, evidence-backed 50–100-song cohort for enrichment beyond
the canonical spine. This is internal collection planning; it does not enter
the model's tool instructions or appear as a global song ranking. Choose the
cohort from recorded question utility—recurring version/recommendation signals,
cross-era comparison potential, transition/suite centrality, lyric/history
sources, recording and release coverage, and a reserved long-tail share. Store
recommendations as attributed selection signals.

For outdoor shows, collect contextual weather, benefit, production, and crowd
conditions only where sources make them material. Preserve direct observations,
nearby station or grid data, and reported recollections as distinct scopes. The
historical-weather tool may corroborate a notable-weather question with
nearby-grid reanalysis; it must not be presented as an exact station or
concert-site observation.

**Done when:** the cohort and its question-family matrix have documented
rationales, source inventory, coverage states, and representative cross-era
evaluations. See `docs/question-driven-enrichment.md`.

**Current first pass:** `data/editorial/song-cohort-candidates.csv` provides a
72-song reproducible factual coverage queue. Its 32-entry priority-review
overlay preserves factual coverage/risk fields while recording data,
transition, long-tail, discovery-guide, lore-trail, and explicit editorial-
override reasons. Dark Star, Dancin' in the Streets, and They Love Each Other
show how a fertile editorial question can join factual coverage in the review
queue. The queue directs review work and preserves each entry's rationale and
coverage risk. See `docs/priority-review-queue.md`.

The companion `data/editorial/featured-show-candidates.json` provides 20
cross-era show anchors with canonical coverage counts and explicit relationship
gaps. It is an internal enhancement queue, not a best-show ranking or runtime
retrieval input. See `docs/featured-show-candidates.md`.

### 10. Add the document/RAG layer

After rights and access review, ingest or retrieve permissible interviews, liner notes, books, reviews, and essays as documents separate from canonical entities. Index them with source, date, rights, and entity links.

**Done when:** document retrieval complements structured graph lookup without obscuring provenance or redistributing protected text.

## Deferred

- Dedicated graph database.
- Full-text/vector indexing before a document corpus exists.
- Audio/video hosting or downloading.
- Automatic canonical writes by an agent.
- Multi-agent orchestration before single-agent retrieval is measured and dependable.
- Model-generated interface code, arbitrary browser embeds, and arbitrary client-side external fetching.
