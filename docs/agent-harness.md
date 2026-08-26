# Agent harness

Deadbot uses **LangGraph** as its permanent agent harness. The first graph is a bounded agent loop, not a fixed conversational workflow:

```text
user message → model chooses a read-only tool → tool result enters graph state
     ↑                                                    ↓
     └──────── model either chooses another tool or answers ┘
```

The loop is bounded by `DEADBOT_MAX_TOOL_ROUNDS`; a model cannot write to the repository, canonical graph, or external sources through this harness.

## Initial tool surface

- `search_entities` — resolve songs, shows, people, or venues to canonical IDs.
- `get_song` — song identity, writers, arrangements, performances, and resource links.
- `get_show` — show, venue, ordered performances, recording metadata, and show links.
- `get_performance` — one rendition plus performance-specific context and media links.
- `get_media_links` — stored YouTube, Spotify, Archive, or other link-out metadata.
- `get_historical_weather` — show-date weather for the venue area from Open-Meteo historical reanalysis, with the limitation clearly labeled.
- `get_astronomy` — local Sun and Moon rise/set, twilight, transit, and lunar-phase context from the U.S. Naval Observatory.
- `get_astrology` — date-based Western zodiac context, explicitly labeled as cultural/interpretive rather than scientific.

All tools are read only. The canonical-data tools do not fetch arbitrary web pages; the three contextual tools make narrowly scoped API calls for the requested show date and venue area. They return the source URL and retrieval metadata, while a later, sandboxed source-reader tool can retrieve only resources that are already present in `resources.csv`.

## Provider contract

`deadbot/models.py` defines the `ModelProvider` contract. The graph consumes a tool-capable chat model through that contract and does not import a provider directly. The initial `OllamaProvider` is selected by `DEADBOT_MODEL_PROVIDER=ollama` and its model is selected by `DEADBOT_OLLAMA_MODEL`.

To add a provider later, implement `create_chat_model()` and register it in `create_model_provider()`. That preserves the LangGraph agent, tools, prompts, state, evaluations, and canonical data contracts.

## Local model

The default is `qwen3:8b`, selected because it is a reasonably sized local model with Ollama tool-calling and thinking support. The harness starts it in non-thinking mode so that its tool-routing loop stays responsive; set `DEADBOT_OLLAMA_THINKING=true` only after evaluating the slower reasoning loop on real Deadbot questions. Use `qwen3:14b` on a machine with sufficient memory if answer quality needs improvement. The provider is local through Ollama; neither model choice affects the harness.

The initial graph uses non-streaming model requests because it waits for a full
tool-call or final-answer message at each node. This is also the reliable request
mode for the current local Ollama/LangChain combination.

```bash
ollama pull qwen3:8b
.venv/bin/deadbot chat
```

## Verification

Tests cover the local graph data contract: canonical-song coverage, entity resolution, song arrangements/resources, performance-specific provenance, and provider selection. They do not require a model download or a running Ollama process.
