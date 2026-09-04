# Agent harness

Deadbot uses **LangGraph** as its permanent agent harness. The first graph is a bounded agent loop, not a fixed conversational workflow:

```text
user message → model chooses a read-only tool → tool result enters graph state
     ↑                                                    ↓
     └──── model chooses another tool, or calls finish_response ┘
```

The loop is bounded by `DEADBOT_MAX_TOOL_ROUNDS`; a model cannot write to the repository, canonical graph, or external sources through this harness. A turn ends only when a `finish_response` call validates, and the application handles three distinct outcomes short of that:

- If `finish_response`'s arguments fail validation, the tool result carries an error and the loop returns to the model so it can correct the call, still bounded by the round budget.
- If the model ends a turn without calling `finish_response` at all, the application logs a warning and shows the last assistant text, or a short placeholder, with a gap-state body.
- If a validated `finish_response` call delivers a blank chat answer, the application logs a warning and shows the lead, or a short placeholder, in its place; the plan's body still renders normally.

Exhausting the round budget is not a graceful fallback: LangGraph raises a recursion error at the limit, and the request fails with an HTTP 503 rather than returning a partial response.

## Initial tool surface

- `search_entities` — resolve songs, shows, people, or venues to canonical IDs.
- `get_song` — song identity, writers, arrangements, performances, and resource links.
- `get_show` — show, venue, ordered performances, recording metadata, and show links.
- `get_performance` — one rendition plus performance-specific context and media links.
- `get_song_performance_profile` — on-demand derived performance totals, dated
  endpoints, and frequent immediate set neighbors for one song. This describes
  only the current documented library (with explicit transition denominators),
  not complete band history, editorial lore, or a “best” score.
- `get_deadnet_song_context` — an optional reviewed Dead.net song-page title,
  short metadata, and link; it never returns page body or lyrics.
- `get_deadcast_metadata` — an optional reviewed Deadcast episode title, short
  metadata, and link for a supplied official episode slug; it never returns a
  transcript or audio.
- `get_lore_source_trails` — a selective, source-controlled set of links and
  “why open” notes for the first song/show lore pilot. It supplies no source
  text and does not turn editorial context into canonical fact.
- `get_research_source_directory` — the suggested research sites
  (`data/research_sites.json`) with what each is good for and how it can be
  searched, plus the stored link catalogs and reviewed metadata adapters.
- `search_site` — search one site through its own mechanism (Blogger post
  feeds, GDAO's Omeka API, archive.org advanced search, WordPress search, or a
  sitemap match). Accepts a directory name or any host.
- `read_page` — read any public page's text at request time: title, byline,
  date and the article body with navigation, comments and footers removed.
  Long pages page by offset; a focus phrase returns the relevant passages
  first. Nothing is stored beyond a short in-process cache.
- `get_recording_reviews` — archive.org listener reviews and star ratings for
  a canonical recording, an archive identifier, or a show.
- `get_media_links` — stored YouTube, Spotify, Archive, or other link-out metadata.
- `get_historical_weather` — show-date weather for the venue area from Open-Meteo historical reanalysis, with the limitation clearly labeled. Use it when a question or a stored source makes weather material (for example heat, rain, lightning, or snow), not to infer an event context for every outdoor show.
- `get_astronomy` — local Sun and Moon rise/set, twilight, transit, and lunar-phase context from the U.S. Naval Observatory.
- `get_astrology` — date-based Western zodiac context, explicitly labeled as cultural/interpretive rather than scientific.
- `finish_response` — the only way a turn ends: the model's chat answer and main-body plan, resolved by `deadbot/finish.py`.

All tools are read only. The canonical-data tools never touch the network; the three contextual tools make narrowly scoped API calls for the requested show date and venue area. The research tools (`search_site`, `read_page`, `get_recording_reviews`) read public web pages and public JSON endpoints at request time so the model can work from what a source actually says. They keep nothing: no page text is stored, and the site directory is a suggestion of where to look, not a boundary. See `docs/superpowers/specs/2026-09-03-source-reading-design.md`.

Historical weather is nearby-grid-cell reanalysis, not an exact NWS station or
concert-site measurement. Keep it distinct from direct weather observations and
from attributed interview or memoir claims about conditions at a show.

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
