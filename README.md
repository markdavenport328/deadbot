# Deadbot

Deadbot is an experimental Grateful Dead knowledge and music system. It has a reviewable canonical dataset, source-preserving raw-data conventions, a PostgreSQL schema that can be rebuilt from the canonical files, and a small read-only LangGraph agent harness.

## Current phase

The agent harness can read the canonical graph from CSV (the zero-setup
default) or from PostgreSQL. It is deliberately read-only: it can find songs,
shows, performances, contextual resources, and playback links. Its first
reviewed external reader can also retrieve Dead.net page metadata and links for
a resolved song; it cannot collect article bodies, lyrics, audio, or change
canonical data.

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

Canonical CSV files in `data/canonical/` remain the reviewable source of truth.
The deterministic importer validates and loads all of them into the rebuildable
operational database described in `schema/postgres.sql`. Structured observations
are computed from that grounded layer and versioned separately; generated prose
is not stored as canonical fact.

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
- `docs/data-and-retrieval-roadmap.md` — optimal collection order, PostgreSQL cutover gates, bounded graph retrieval, and the 1972-to-full-timeline rollout.
- `docs/question-driven-enrichment.md` — question-first selection of the cross-decade song cohort, the role of the 1972 pilot, and source-qualified notable-show context.
- `docs/serendipity-research-plan.md` — flexible two-column answers, model-guided exploration, and source-specific research-tool rollout.
- `docs/editorial-discovery-guide.md` — the discretionary, non-factual lore-path inventory available to the answering model.
- `docs/lore-pilot-research.md` — first source trails for song evolution and Veneta/Cornell context.
- `docs/lore-source-trails.md` — the initial model-callable catalog of those source links and their question-specific purpose.
- `docs/song-cohort-candidates.md` — reproducible 72-song factual coverage queue for cross-decade enrichment review.
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

## Use PostgreSQL

Install the optional driver, create an empty PostgreSQL database, and import the
canonical snapshot:

```bash
.venv/bin/python -m pip install -e '.[dev,postgres]'
export DEADBOT_DATABASE_URL='postgresql://deadbot:deadbot@localhost:5432/deadbot'
.venv/bin/deadbot db-import --rebuild
```

The importer validates every CSV before touching the database, creates a
content-addressed manifest for that exact file set, and commits the schema,
snapshot ledger, and data as one transaction. The command prints the canonical
snapshot ID; use it as the `input_revision` for any derived observation.
Without `--rebuild`, existing rows win and conflicts are skipped, so that
non-destructive merge is not proof that the database is an exact mirror of the
listed snapshot. Use the explicit rebuild after canonical corrections when the
operational projection must match the files.

To run the app against the imported database:

```bash
export DEADBOT_DATA_STORE=postgres
.venv/bin/deadbot serve
```

Leave `DEADBOT_DATA_STORE=csv` for the portable, zero-setup path. See
`schema/README.md` for load order and the forward enrichment tables.

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
