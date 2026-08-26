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

## Current boundaries

These boundaries are intentional and should not be bypassed casually:

- Canonical CSV is the current runtime data source; PostgreSQL import is not implemented yet.
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

Exercise the web experience against a running local model with representative
Veneta questions and tighten the adapter where real tool traces expose missing
or redundant cards. Add browser-level automated checks once a suitable local
test runner is selected. Keep the existing schema, source restrictions, and
safe fallbacks intact while improving visual hierarchy, responsive behavior,
and source presentation.

**Done when:** a browser user can ask representative Veneta questions and see
a validated response that makes canonical data, contextual sources, and media
paths visibly distinct; the full flow is checked with both API and browser-level
tests.

### 4. Evaluate and tune the bounded model-guided composer

The first composer now reasons over an enriched decision brief and selects
server-validated blocks into primary, supporting, context, and media regions.
Run it against the configured local model with representative Veneta questions
and compare its selections to the deterministic candidate order. Tune the
model's grounded brief, instructions, and candidate metadata before adding
deterministic intent routing.

Add example-based evaluations for questions that should emphasize a song card,
show/performance card, media option, chord-resource list, provenance note, or
gap state. Record schema version, candidate count, selected indexes, and safe
fallback category, without logging protected text or private model reasoning.

**Done when:** local-model composition reliably makes a smaller, more relevant
main-column layout while preserving provenance, factual content, and the
deterministic fallback.

### 5. Add a restricted source-reader tool

Build a sandboxed tool that may fetch only URLs already present in `resources.csv`, returns concise source metadata/excerpts, records retrieval details, and never writes canonical claims automatically.

**Done when:** the agent can answer a question using a linked interview or article while naming the source and retaining the URL.

### 6. Build the canonical CSV → PostgreSQL importer

Implement deterministic import, foreign-key validation, and a rebuild command. Refactor `CanonicalStore` behind the existing read interface so the agent can move from CSV to PostgreSQL without changing its tools.

**Done when:** a clean database can be rebuilt from canonical CSV and the same agent tests pass against it.

### 7. Expand the 1972 collection responsibly

Use gdshowsdb as the bulk baseline, JerryBase for review, Internet Archive for recordings, and selected sources by fact type. Add data in reviewable batches; preserve raw records and source-specific identifiers. The first bulk pass is complete: 86 shows, 2,229 performances, and 362 recording rows are now canonical; one full Internet Archive metadata record is preserved for each show. The JerryBase performer pass now adds source-reviewed musicians, guests, and instrument strings for 2,268 of 2,358 canonical shows across 1965–1995. The remaining work is track mappings, additional recording detail, named guitar/equipment history, unresolved song credits, held-date review, and cross-source review.

The year-level pass also established the collection playbook in
`docs/collection-methodology.md`: enumerate the bounded universe first, run
typed enrichment passes, keep compact raw evidence separate from canonical
conclusions, fail closed on transport errors, resolve title aliases in stages,
and hold ambiguous matches rather than guessing. These rules should be used
for every subsequent year and enrichment batch.

**Done when:** a documented 1972 ingestion/reconciliation pass produces validated show/performance/recording coverage beyond the Veneta pilot.

### 8. Add the document/RAG layer

After rights and access review, ingest or retrieve permissible interviews, liner notes, books, reviews, and essays as documents separate from canonical entities. Index them with source, date, rights, and entity links.

**Done when:** document retrieval complements structured graph lookup without obscuring provenance or redistributing protected text.

## Deferred

- Dedicated graph database.
- Full-text/vector indexing before a document corpus exists.
- Audio/video hosting or downloading.
- Automatic canonical writes by an agent.
- Multi-agent orchestration before single-agent retrieval is measured and dependable.
- Model-generated interface code, arbitrary browser embeds, and arbitrary client-side external fetching.
