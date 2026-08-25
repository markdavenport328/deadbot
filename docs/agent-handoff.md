# Agent handoff guide

Use this guide when joining the Deadbot project midstream.

## Read first

1. `README.md` for setup and repository layout.
2. `docs/product-vision.md` for the intended app and its boundaries.
3. `docs/development-plan.md` for current status and next work.
4. `docs/decisions.md` for durable architectural choices.
5. `docs/provenance-policy.md`, `docs/graph-scope.md`, and `docs/model-retrieval.md` before changing data or retrieval behavior.
6. `docs/agent-harness.md` before changing the LangGraph runtime.
7. `docs/experience-architecture.md` before changing the FastAPI API, composer, or frontend blocks.

## Current state

- The active pilot is **Grateful Dead, Veneta, Oregon — 1972-08-27**.
- Canonical data lives in `data/canonical/*.csv`; raw collected records live in `data/raw/`.
- The canonical layer includes 20 songs and 20 ordered performances for the Veneta show, with linkable contextual resources for every song.
- `deadbot/` contains the current read-only LangGraph harness.
- `.venv/` is local and ignored. The project is installed there in editable mode.
- The development machine has Ollama and `qwen3:8b` installed. The default model configuration is in `.env.example`; no secrets belong in Git.
- The repository contains uncommitted project work. Preserve unrelated changes and do not reset, overwrite, or discard files merely to obtain a clean tree.

## Run and verify

```bash
.venv/bin/python -m pytest -q
.venv/bin/deadbot chat
```

The tests do not require Ollama. The chat command requires a running local Ollama service and the configured model. Start with `qwen3:8b` in non-thinking mode; use real evaluation questions before changing model parameters.

## How the agent works

The agent loop is:

```text
user message → model chooses local read-only tool(s) → model answers
```

The five existing tools resolve entities and return canonical facts, typed resource relationships, and external media links. They do not fetch web pages or make changes. Tool outputs are JSON so they can be tested independently of any model.

## Non-negotiable data rules

- Preserve raw source data. Normalize into canonical CSV; do not overwrite source-shaped records.
- Use stable lowercase kebab-case IDs. Match spelling variants to an existing canonical entity where appropriate.
- Treat external resource material as source-attributed context. Do not silently promote a recollection or editorial interpretation to a canonical fact.
- Keep chords tied to a source-specific arrangement, never directly to the abstract song.
- Store links and concise metadata, not audio, full lyrics, complete tabs, or copied long-form source text.
- Do not add agent write tools without an explicit review/approval workflow and tests.

## Safe next contribution

The highest-value next task is to create the Veneta evaluation set described in `docs/development-plan.md`. It should exercise entity resolution, source selection, media links, and provenance language. Keep it model-independent where possible: validate tool results directly, then separately score model responses.

## Useful file map

| Need | Primary location |
| --- | --- |
| Domain schema | `schema/postgres.sql` |
| Canonical-data conventions | `data/canonical/README.md` |
| Source policy | `docs/provenance-policy.md` |
| Data sources | `docs/data-sources.md` |
| Veneta song-resource guide | `docs/veneta-song-dossiers.md` |
| Agent loop | `deadbot/graph.py` |
| Model providers | `deadbot/models.py` |
| Read-only tools | `deadbot/tools.py` |
| Harness tests | `tests/` |
