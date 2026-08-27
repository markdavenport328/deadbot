# Deadbot

Deadbot is an experimental Grateful Dead knowledge and music system. It has a reviewable canonical dataset, source-preserving raw-data conventions, a PostgreSQL schema that can be rebuilt from the canonical files, and a small read-only LangGraph agent harness.

## Current phase

The first agent harness reads the canonical CSV graph directly. It is deliberately read-only: it can find songs, shows, performances, contextual resources, and playback links, but it cannot collect source material or change canonical data.

## Why the model is separated

The same composition can be played at many shows, and a single show can have many independently captured sources. Deadbot therefore distinguishes:

- **Song** — the composition.
- **Show** — a dated event at a venue.
- **Performance** — one song played at one show, in set order.
- **Recording** — one captured source of a show.
- **Performance recording** — the track and timestamp where a performance appears on a recording.

That separation makes it possible to connect musical history, setlists, recording lineage, and eventual playback without conflating them.

## Architecture

```text
external sources → raw JSONL → normalization → canonical CSV → PostgreSQL
```

Canonical CSV files in `data/canonical/` are initially the source of truth. A future import process will validate and load them into the database described in `schema/postgres.sql`.

## Repository layout

- `data/raw/` — source-preserving, regenerable collected records.
- `data/canonical/` — normalized entities and relationships, tracked in Git.
- `schema/` — PostgreSQL definition and domain-model documentation.
- `scripts/` — collection, normalization, and import tooling.
- `deadbot/` — LangGraph agent loop, model-provider abstraction, and read-only canonical-data tools.
- `tests/` — harness and data-tool tests.
- `docs/` — architecture, source-evaluation notes, provenance policy, and decisions.

See `docs/graph-scope.md` for the boundary between structured graph data and externally hosted content.

## Project guide

- `docs/product-vision.md` — the intended user experience, system shape, and information boundaries.
- `docs/experience-brief.md` — visitor mindsets, response modes, source/claim policy, flagship response blueprints, and experience-quality rubric.
- `docs/experience-architecture.md` — the FastAPI/React experience layer, composition contract, block catalog, and media/provenance safeguards.
- `docs/development-plan.md` — current accomplishments, staged plan, and acceptance criteria.
- `docs/data-audit-2026-08-27.md` — a point-in-time, verified row-count and gap audit of the canonical CSV data, with prioritized next data-work steps.
- `docs/collection-methodology.md` — practical collection workflow, retry safety, title matching, rights boundaries, and validation checklist.
- `docs/collection-status-1965-1995.md` — full show/setlist baseline coverage and early-year gaps.
- `docs/agent-handoff.md` — concise onboarding guide for a collaborating agent.
- `docs/agent-harness.md` — LangGraph loop, tool surface, and local-model configuration.
- `docs/decisions.md` — architectural decisions that should not be casually revisited.

## Run the local agent

Create a virtual environment and install the project dependencies:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -e '.[dev]'
```

Install and start Ollama, then download the recommended starting model:

```bash
ollama pull qwen3:8b
```

Copy `.env.example` to `.env` if you want to change the model or local Ollama URL, then run:

```bash
.venv/bin/deadbot chat
```

See `docs/agent-harness.md` for the architecture, available tools, and model-provider contract.

## Run the web experience

Install the Python dependencies as above, then install and build the React
client:

```bash
cd web
npm install
npm run build
cd ..
.venv/bin/deadbot serve
```

Open `http://127.0.0.1:8000`. The web experience requires the configured local
model service when a question is submitted. For frontend development, run
`.venv/bin/deadbot serve --reload` and `npm run dev` from `web/`; Vite proxies
`/api` requests to FastAPI.

The browser receives a server-validated experience response made of allowlisted
cards, links, and media blocks. See `docs/experience-architecture.md` for the
composition and provenance contract.

## Evaluate canonical retrieval

Run the versioned Veneta tool-retrieval baseline without starting Ollama:

```bash
.venv/bin/deadbot evaluate
```

The command prints one pass/fail result per case. To preserve a run for comparison,
write the JSON report outside the tracked suite:

```bash
.venv/bin/deadbot evaluate --output eval-results/veneta-v1.json
```

See `docs/evaluation.md` for the boundary between deterministic tool checks and
separate model-response review.
