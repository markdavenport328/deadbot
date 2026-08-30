# Agent handoff guide

Use this guide when joining the Deadbot project midstream.

## Read first

1. `README.md` for setup and repository layout.
2. `docs/product-vision.md` for the intended app and its boundaries.
3. `docs/development-plan.md` for current status and next work.
4. `docs/data-and-retrieval-roadmap.md` for collection order, PostgreSQL
   cutover gates, bounded context, and the 1972-to-full-timeline rollout.
5. `docs/decisions.md` for durable architectural choices.
6. `docs/provenance-policy.md`, `docs/graph-scope.md`, and `docs/model-retrieval.md` before changing data or retrieval behavior.
7. `docs/agent-harness.md` before changing the LangGraph runtime.
8. `docs/experience-architecture.md` before changing the FastAPI API, composer, or frontend blocks.

## Current state

- Veneta, 1972-08-27 remains the vertical-slice experience; all of 1972 is the
  first planned deep enrichment slice. It validates typed enrichment and
  retrieval mechanics, but it is not the natural scope for career-evolution
  questions about songs.
- Canonical data lives in `data/canonical/*.csv`; raw collected records live in `data/raw/`.
- The broad canonical spine currently spans 1965–1995 with 2,358 shows and
  39,774 ordered performances. Enrichment depth is intentionally uneven and
  must be described with coverage metadata.
- CSV remains the reviewed source of truth. `deadbot/postgres_import.py` imports
  all 21 canonical tables into the versioned PostgreSQL schema and records an
  immutable `sha256:...` canonical snapshot plus append-only import ledger;
  `deadbot/postgres.py` supplies the interchangeable read store.
- `DEADBOT_DATA_STORE=csv` is the code default. This local checkout has an
  ignored `.env` that selects its Docker PostgreSQL database; process
  environment values still take precedence. PostgreSQL configuration and the
  `deadbot db-import` command are documented in `README.md`.
- Driver-independent importer, store-parity, CLI, API, and retrieval tests are
  implemented. The local Docker PostgreSQL 16 smoke check cleanly bootstrapped
  schema v2, imported 107,404 canonical rows, recorded snapshot
  `sha256:524b5c16865ef59bf56174ea4f5eee5e8e7c47985fe874d0af72089e799e4218`,
  and verified a PostgreSQL-backed Veneta lookup; 142 tests passed. Reconnect,
  populated-database rebuild, invalid-import rollback, and CSV/PostgreSQL
  result parity also passed locally. Deployment-like query measurements and a
  production-like deployment validation remain cutover work, so do not call the
  database path deployment-verified yet.
- `deadbot/` contains the current read-only LangGraph harness.
- `.venv/` is local and ignored. The project is installed there in editable mode.
- The development machine has Ollama and `qwen3:8b` installed. The default model configuration is in `.env.example`; no secrets belong in Git.
- The repository contains uncommitted project work. Preserve unrelated changes and do not reset, overwrite, or discard files merely to obtain a clean tree.

## Run and verify

```bash
PYTHONPATH=. .venv/bin/python -m pytest -q
.venv/bin/deadbot chat
```

The tests do not require Ollama. The chat command requires a running local Ollama service and the configured model. Start with `qwen3:8b` in non-thinking mode; use real evaluation questions before changing model parameters.

## How the agent works

The agent loop is:

```text
user message → model chooses local read-only tool(s) → model answers
```

The tools resolve entities and return canonical facts, typed relationships,
arrangements, equipment history, contextual data, and external media links.
They do not change canonical data. Tool outputs are JSON so they can be tested
independently of any model.

## Non-negotiable data rules

- Preserve raw source data. Normalize into canonical CSV; do not overwrite source-shaped records.
- Use stable lowercase kebab-case IDs. Match spelling variants to an existing canonical entity where appropriate.
- Treat external resource material as source-attributed context. Do not silently promote a recollection or editorial interpretation to a canonical fact.
- Keep chords tied to a source-specific arrangement, never directly to the abstract song.
- Store links and concise metadata, not audio, full lyrics, complete tabs, or copied long-form source text.
- Do not add agent write tools without an explicit review/approval workflow and tests.

## Immediate next sequence

1. Run live-model evaluations of the fact-plus-exploration experience: a direct
   show fact, a Cornell fact with optional source trail, “best Sugar Magnolia
   recordings,” Friend of the Devil across decades, Veneta's notable weather,
   source unavailability, and a quick fact that should stay compact.
2. Use the traces to improve the decision brief, tool descriptions, composition
   inventory, and model configuration. The model chooses relevance, ordering,
   omission, and column placement; validation stays focused on allowed blocks,
   supplied references, provider links, provenance, and safe fallback.
3. Review and enrich the existing priority queue. It is internal planning only:
   the model receives the discovery guide, source trails, factual tools, and
   coverage for a current question, never a cohort-size target or global rank.
4. Complete the 1972 typed passes for release/show/track mappings, recording
   tracks, selections, claims/resources, equipment/personnel, and notable
   outdoor-show context. Preserve direct, proxy, and reported weather scopes.
5. Add bounded show/performance research paths and source snapshots after
   source-specific access and rights review; extend the same pattern across the
   cross-decade priority work.

Do not wait for globally complete collection. Base facts must precede the
observations that depend on them within a bounded slice; ready slices may ship
while collection continues elsewhere.

## Useful file map

| Need | Primary location |
| --- | --- |
| Domain schema | `schema/postgres.sql` |
| Data/retrieval rollout | `docs/data-and-retrieval-roadmap.md` |
| Question-driven enrichment | `docs/question-driven-enrichment.md` |
| PostgreSQL importer/store | `deadbot/postgres_import.py`, `deadbot/postgres.py` |
| Canonical-data conventions | `data/canonical/README.md` |
| Source policy | `docs/provenance-policy.md` |
| Data sources | `docs/data-sources.md` |
| Veneta song-resource guide | `docs/veneta-song-dossiers.md` |
| Agent loop | `deadbot/graph.py` |
| Model providers | `deadbot/models.py` |
| Read-only tools | `deadbot/tools.py` |
| Harness tests | `tests/` |
