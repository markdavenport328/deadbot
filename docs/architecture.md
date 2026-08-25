# Architecture

Deadbot is organized as a sequence of separable layers:

1. **Source layer** — external catalogs, archives, reference sites, and official sources.
2. **Raw collection layer** — source-preserving records, normally JSONL/NDJSON.
3. **Normalization layer** — matching, deduplication, validation, stable-ID assignment, and reconciliation.
4. **Canonical domain layer** — reviewable CSV entities and relationships that represent Deadbot's current normalized understanding.
5. **PostgreSQL operational layer** — a rebuildable relational database imported from canonical data.
6. **Retrieval/tool layer** — future interfaces for structured queries, semantic retrieval, and external calls.
7. **Agent runtime** — future orchestration and reasoning that combines retrieval and tools.
8. **Experience/UI layer** — a FastAPI application and React + TypeScript client that render validated, provenance-aware exploration responses.

The repository now includes the initial read-only agent runtime at layer 7. It reads canonical CSV data directly while the PostgreSQL import layer remains future work. It does not yet collect external documents, modify canonical data, or run an operational database.

## Future retrieval

Later, retrieval will likely combine:

- SQL for deterministic structured questions;
- full-text and vector retrieval for prose and unstructured material;
- external APIs and tools for live or outside information; and
- agent reasoning to combine those capabilities.

The relational core is designed to support that expansion. Semantic-search content and embeddings should be added in separate retrieval-oriented tables rather than embedded into the canonical model prematurely.

Resource metadata and source-specific chord arrangements remain in the canonical domain layer because they are structured, attributable relationships. A generic resource can be linked to a song, show, or performance. Long-form lesson text, complete transcriptions, reviews, and other prose belong in a future document/retrieval layer and should be stored or indexed according to their rights and usage terms.

## Experience composition

The experience layer receives a grounded retrieval result and returns a versioned response composed of an answer, source/provenance metadata, and typed content blocks. A block can represent a song or performance card, an approved media player, a resource list, a quote from a permitted source-reader result, or a gap state. The client renders these blocks deterministically.

Composition is deliberately distinct from retrieval and rendering:

```text
retrieval/tools → composition plan → validated experience response → UI renderer
```

The model may select and order blocks from a small allowlist but cannot generate interface code, iframe markup, or untrusted URLs. The backend validates all references and provider-specific media identifiers. This maintains the existing read-only, provenance-aware architecture while allowing answers to become useful listening and research paths. See `docs/experience-architecture.md`.
