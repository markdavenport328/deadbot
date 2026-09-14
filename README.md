# Deadbot

Deadbot is a conversational Grateful Dead knowledge and music companion — an experiment in what happens when you give a language model a structured catalog of live music history and let it compose experiences, not just answers.

Ask it a question like *"What did they play after Dark Star at Veneta?"* and you get a quick factual answer. Ask *"Show me a strong Bird Song recording with the players' roles, chords, and something worth reading about it"* and you get a composed page: setlist cards, performer lineups, listening links, sourced editorial context, and pathways into recordings — all assembled from grounded data and validated before it reaches the browser.

The project explores how model-driven editorial choices and a defined interface system can produce useful, coherent web experiences from structured data. It's built on a knowledge graph of 2,300+ shows, 500 songs, and 40,000 song performances spanning 1965–1995.

**[Live →](https://deadbot-ten.vercel.app/)**

## The question behind the project

Most AI chat interfaces produce transcripts. Deadbot asks a different question: can the model act as an editorial layer — choosing what to emphasize, how to group it, and what paths to offer the reader — while the system guarantees that everything rendered is grounded in real data?

The model researches, synthesizes, and composes. But it doesn't generate HTML or invent URLs. It produces a structured plan that the server validates and resolves against the database before anything reaches the browser. Every entity reference must trace to a tool result from the same conversation. Hallucinated references are silently dropped, not rendered.

This separation — model as editorial judgment, application as rendering and verification — is the core architectural idea.

## How it works

For the full technical walkthrough, see **[How Deadbot works](docs/how-it-works.md)**. Here's the short version.

### Data model

The same composition can be played at many shows, and a single show can have many independently captured sources. The data model makes these distinctions explicit:

- **Song** — the composition itself (writers, arrangements, first/last performance dates).
- **Show** — a dated event at a venue, with a tour, setlist, and performer lineup.
- **Performance** — one song played at one show, in set order. This is the key join: it's how "Dark Star" at Veneta is a different record from "Dark Star" at Cornell.
- **Recording** — one captured source of a show (audience tape, soundboard, matrix blend).
- **Official release** — an album, with track-level mappings back to specific performances.

Around these sit recordings, external resources, curated selection signals, sourced claims, and derived observations — about 30 PostgreSQL tables with strict foreign keys and referential-integrity triggers. The database is populated from 23 reviewed CSV files that are the version-controlled source of truth, loaded in a single validated transaction.

### Retrieval

A user's question enters a **LangGraph agent loop** where the language model alternates between deciding what to look up and executing the lookups — up to eight rounds. It has 26 read-only tools: catalog tools that query PostgreSQL (search, show lookup, song lookup, performance context, album details, recording reviews, selection signals) and external tools that fetch articles, interviews, and lore from the web. Search is structured SQL text matching, not vector/semantic — the Dead domain has bounded vocabulary and the model formulates specific terms.

### Experience composition

When the model has enough material, it calls `finish_response` — a terminal tool whose arguments *are* the answer. It delivers a chat reply, a page title, and groups of **semantic units** (show cards, song overviews, performance units, album units, era units) referenced by ID, plus editorial blocks (narrative, fact grid, timeline) for the model's own synthesis.

The server resolves each reference against the database — hydrating shows with venues, setlists, performers, recordings, and listening links — and validates that every entity appeared in a tool result. The model organizes units into groups with presentation modes (collection, sequence, comparison, argument) and controls emphasis (primary, supporting, mention) to shape the page layout. The browser renders the validated result as deterministic React components.

The page streams progressively as the model writes: a token-by-token JSON parser emits blocks as they complete, so the browser lays out the page before the full plan arrives. Every unit carries follow-up topic chips that send new questions into the conversation, creating pathways through the catalog rather than dead-ending at an answer.

## Architecture

```
external sources → raw JSON → normalization → canonical CSV → PostgreSQL
                                                                  ↑
                                                          reviewed, versioned,
                                                          rebuildable from CSVs
```

The system has four layers:

1. **Canonical knowledge graph** — reviewed, normalized data for factual relationships. CSV files are the source of truth; PostgreSQL is the operational store rebuilt from them.
2. **Tool-using agent** — a bounded LangGraph loop that combines catalog retrieval with approved external-source reading.
3. **Composition and validation** — resolves the model's editorial plan into grounded, typed blocks with provenance tracking.
4. **React experience** — renders validated blocks as an interactive exploration interface.

### Repository layout

| Directory | Contents |
| --- | --- |
| `data/canonical/` | Normalized entities and relationships, tracked in Git |
| `data/raw/` | Source-preserving collected records |
| `schema/` | PostgreSQL definition and migrations |
| `scripts/` | Collection, normalization, and import tooling |
| `deadbot/` | LangGraph agent, tools, composition, FastAPI endpoints |
| `web/` | React + TypeScript client |
| `tests/` | Harness and data-tool tests |
| `docs/` | Architecture, decisions, data audits, and design documents |

## Running locally

### Prerequisites

Python 3.11+, Node.js 18+, PostgreSQL, and either [Ollama](https://ollama.ai) (local) or an OpenAI API key.

### Setup

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -e '.[dev,postgres]'
```

### Import the catalog

```bash
export DEADBOT_DATABASE_URL='postgresql://deadbot:deadbot@localhost:5432/deadbot'
.venv/bin/deadbot db-import --rebuild
```

The importer validates every CSV, creates a content-addressed manifest, and commits the schema and data as one transaction. Without `--rebuild`, existing rows win and new rows merge in.

### Run the web experience

```bash
cd web && npm install && npm run build && cd ..
.venv/bin/deadbot serve
```

Open `http://127.0.0.1:8000`. For frontend development, run `deadbot serve --reload` alongside `npm run dev` from `web/`; Vite proxies `/api` requests to FastAPI.

### Run the CLI agent

```bash
ollama pull qwen3:8b
.venv/bin/deadbot chat
```

### Evaluate retrieval

Run the versioned tool-retrieval baseline without a model:

```bash
.venv/bin/deadbot evaluate
```

## Design documents

- **[How Deadbot works](docs/how-it-works.md)** — the database, retrieval loop, and experience system in detail
- [`docs/product-vision.md`](docs/product-vision.md) — the intended experience, system shape, and information boundaries
- [`docs/experience-brief.md`](docs/experience-brief.md) — persona, response goals, presentation palette, and review criteria
- [`docs/experience-architecture.md`](docs/experience-architecture.md) — composition contract, block catalog, and provenance safeguards
- [`docs/development-plan.md`](docs/development-plan.md) — accomplishments, staged plan, and acceptance criteria
- [`docs/decisions.md`](docs/decisions.md) — architectural decisions that should not be casually revisited
- [`docs/agent-harness.md`](docs/agent-harness.md) — LangGraph loop, tool surface, and model-provider contract
