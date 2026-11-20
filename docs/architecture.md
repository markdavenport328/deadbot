# Architecture

Deadbot is organized as a sequence of separable layers:

1. **Source layer** — external catalogs, archives, reference sites, and official sources.
2. **Raw collection layer** — source-preserving records, normally JSONL/NDJSON.
3. **Normalization layer** — matching, deduplication, validation, stable-ID assignment, and reconciliation.
4. **Canonical domain layer** — reviewable CSV entities and relationships that represent Deadbot's current normalized understanding.
5. **SQLite operational layer** — a read-only database file rebuilt from canonical data on every deploy.
6. **Retrieval/tool layer** — future interfaces for structured queries, semantic retrieval, and external calls.
7. **Agent runtime** — future orchestration and reasoning that combines retrieval and tools.
8. **Experience/UI layer** — a FastAPI application and React + TypeScript client that render validated, provenance-aware exploration responses.

The repository includes the read-only agent runtime at layer 7 and a
deterministic CSV-to-SQLite build at layer 5 (`deadbot/sqlite_build.py`). Every
build validates all of its input first and records a fingerprint of the exact
reviewed files it was built from. CSV remains the reviewable source of truth;
the SQLite file is the only store the application serves, and an in-memory
reading of the same CSVs (`deadbot/data.py`) shapes its responses and backs
the tests. The runtime does not modify canonical data.

The data sequence is intentional:

```text
source evidence
  → reviewed raw records
  → normalized canonical entities and relationships
  → SQLite operational projection
  → versioned structured observations
  → request-time model explanation and layout
```

This does not require completing every source collection before useful product
work begins. It requires completing the relevant base facts and coverage
metadata before deriving an observation from them. When base data or a
calculation changes, the observation is recomputed with a new input revision;
visitor-facing prose is composed from the current retrieval packet rather than
left behind as a stale database fact.

`data-and-retrieval-roadmap.md` turns this sequence into concrete collection
stages, bounded graph traversal plans, context budgets, and a
1972-to-full-timeline rollout. It was written when PostgreSQL was the planned
operational store; ADR-015 in `decisions.md` records the move to SQLite.

## Retrieval evolution

Retrieval can progressively combine:

- SQL for deterministic structured questions;
- full-text and vector retrieval for prose and unstructured material;
- external APIs and tools for live or outside information; and
- agent reasoning to combine those capabilities.

The relational core is designed to support that expansion. Semantic-search content and embeddings should be added in separate retrieval-oriented tables rather than embedded into the canonical model prematurely.

Full-timeline scale does not imply full-timeline model context. Retrieval first
resolves typed seed entities, applies an explicit time/entity scope, and follows
only the relationships needed for the question. SQL performs filtering,
aggregation, ranking, and pagination; the model receives a compact evidence
packet containing the answer candidates, relevant graph paths, provenance,
coverage limits, and expansion references. Initial packet targets are a
measured p95 below 10,000 tokens and a hard ceiling of 20,000 tokens.

Resource metadata and source-specific chord arrangements remain in the canonical domain layer because they are structured, attributable relationships. A generic resource can be linked to a song, show, or performance. Long-form lesson text, complete transcriptions, reviews, and other prose belong in a future document/retrieval layer and should be stored or indexed according to their rights and usage terms.

## Experience composition

The experience layer receives a grounded retrieval result and returns a versioned response composed of an answer, source/provenance metadata, and typed content blocks. The model decides which blocks appear and how they are ordered and grouped. A block can represent a song or performance card, an approved media player, a resource list, a quote from a permitted source-reader result, or a gap state. The client renders these blocks deterministically.

Composition is deliberately distinct from retrieval and rendering:

```text
retrieval/tools → composition plan → validated experience response → UI renderer
```

The model composes the page from a palette of typed components and its own editorial writing, naming records by ID; code fills in their facts from the store and builds players and links from stored or tool-returned URLs, so the model never writes interface code or embed markup. Code reads the plan leniently and keeps the model's work on the page (ADR-014). See `docs/experience-architecture.md`.
