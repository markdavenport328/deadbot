# Research notebook: keep what each turn found

Status: design, 2026-10-09. Recommended option chosen; awaiting owner approval before a build plan.

## The problem

A follow-up starts from nothing. The browser sends `{question, thread_id, conversation}`, and `conversation` holds only the visitor's questions and the chat answers (`finish.py:1542-1580`, `api.py:149-162`). No tool results, IDs or page plan reach the next turn, and grounding only accepts IDs from the current turn's tool output (`finish.py:94-101`, `composition.py:91-102`). So after a Europe '72 answer, "compare the two Lyceum nights" searches again, fetches the shows again, then finishes: 3–4 model calls, 50–90k input tokens, 13–20 s to the first words.

Grid clicks (`docs/superpowers/plans/2026-10-09-grid-block.md`, Task 7) will make follow-ups about material already on the page common. Each should feel like turning a page, not starting over.

The owner's goal: keep the research from earlier turns, let the model look there first and decide whether it needs more, let the context grow richer each turn, and never send the model 100,000 tokens to do it.

## What we measured (2026-10-09, offline)

- The static prefix (system prompt plus 31 tool schemas) is about 11,900 tokens and identical on every call, so it is already shaped for OpenAI's automatic prefix caching. No run has recorded `cached_input_tokens` yet.
- Canonical tools take 2–123 ms against SQLite. Re-running a canonical query costs almost nothing; model rounds cost 3–6 s each.
- Web tools (`read_page`, `search_site`, `get_recording_reviews`) cost seconds, and their cache is per serverless instance.
- Every canonical result is keyed by stable IDs, and `query_catalog` and `aggregate_data` IDs are deterministic hashes. A canonical result can be replayed exactly instead of stored.
- Vercel runs each request on any instance. In-memory session state (`MemorySaver`) can't be relied on, and the SQLite file is read-only.

## Design

### What the notebook holds

One entry per tool call:

| Field | Example |
|---|---|
| `key` | hash of tool name + canonical args |
| `tool`, `args` | `get_show`, `{"show_id": "gd-1972-05-26"}` |
| `ids` | every show, song, performance, release, person, result and aggregation ID and URL in the payload (reuse `finish._walk`) |
| `summary` | one line written by code: `get_show gd-1972-05-26 · Lyceum Theatre, London · 3 sets, 28 songs · 2 recordings · ~2.3k tok` |
| `tokens`, `turn`, `last_read` | for ceilings and eviction |
| `payload` | only for web results that can't be replayed; canonical calls store nothing but the call |

Plus a **page digest** per turn: each block's type, IDs, title and note, and the follow-up chips, so the model knows what the visitor is looking at.

The summary is a fact digest, so code writes it. Judgment about what matters stays with the model.

### Where it lives (recommended): a signed token the browser holds

- The server returns `ExperienceResponse.notebook`, a string: zlib, then base64, then HMAC-signed with `DEADBOT_NOTEBOOK_SECRET`. It also goes out in the final NDJSON `response` event.
- The browser keeps it with `conversation` (and in `sessionStorage`) and sends it back as `ExperienceRequest.notebook`.
- Any instance can serve the next turn, and nothing new needs to be set up.
- A missing or bad signature means the turn runs without a notebook, and that is logged. The visitor still gets an answer.
- Size: about 150 bytes per index entry, with web excerpts compressed. A rich five-turn conversation stays well under 100 KB.

**Alternative: a shared key-value store** (Upstash Redis through the Vercel Marketplace) keyed by `thread_id`, with a 24-hour TTL.
- For: tiny requests, no size pressure, the browser can't alter it, and shareable sessions become possible later.
- Against: new infrastructure, a secret and a bill; 10–30 ms per read and write; a decision about keeping visitors' sessions; and one more thing that can fail.
- The same `notebook.py` interface can sit behind either backend, so starting with the token and moving later is cheap.

**Rejected: provider-side conversation state** (`previous_response_id`). It keeps resending the full history, which is the 100k-token problem, and it ties Deadbot to one provider.

### How the model browses it cheaply

1. **An index, not the payloads.** `_prepare` adds one "Research notebook" message after the transcript: the entries' one-line summaries plus the page digests. About 40 tokens per entry. A Europe '72 opener with 10–15 calls indexes in about 600 tokens; five turns in about 2–3k.
2. **`read_notebook(keys_or_ids)`.** One batched call returns stored or replayed payloads. Its output is an ordinary tool message, so grounding, `from_result` and `aggregation_id` all work unchanged. The notebook reaches the tool through `config["configurable"]["notebook"]`, so the tool schema stays static and inside the cached prefix.
3. **Index IDs are grounded.** IDs and URLs listed in the notebook join this turn's grounded IDs (`finish.py:1597`, `api.py:294`). The model can place a `show_unit` for a night researched two turns ago without looking it up; the server still hydrates every fact from the store.
4. **Prompt.** A few sentences, written as what to do: the notebook lists what earlier turns found; read what this answer will use; research what is new or missing. There is no forced read and no keyword routing. The model chooses between answering from the index, `read_notebook`, or new research.

### Ceilings and eviction

These trim and log; they never police the model's choices.
- At most 80 entries and about 4k index tokens. Each `read_notebook` result is capped at the existing 80k characters.
- Over the cap: first drop stored web payloads, least recently read first, keeping the entry so the call can be re-run. Then drop the oldest unread entries.
- Evict in batches (compact to 60 when 80 is reached) so the replayed prefix changes rarely.
- Re-running the same tool with the same args replaces its entry.

### Keeping the provider's prompt cache warm

- `SYSTEM_PROMPT` and the tool schemas stay byte-identical. The notebook never goes there.
- History is append-only: after each turn's chat answer in the replayed transcript, insert that turn's notebook delta, not a freshly rendered full index. Earlier bytes stay identical, so the cached prefix grows turn by turn.
- Set `prompt_cache_key=thread_id`.
- Add `cached_input_tokens` to the `scripts/measure_turns.py` table so cache hits are measured, not assumed.

### Grid clicks and other focused asks

The grid plan's `AskFocus` (`label`, `block_type`, `block_id`, `ids`, `facts`) is used unchanged. With a notebook, `_prepare` also flags the index entries that mention the focus IDs ("already in the notebook: get_show gd-1972-05-11 …"). The model decides whether that is enough.

### Ready-made starter answers

`scripts/warm_answers.py` saves each starter question's notebook with its cached response. The first follow-up after a ready-made Europe '72 answer then starts with that research already done.

## Expected effect

| Follow-up | Today | With the notebook |
|---|---|---|
| About material already researched ("compare the two Lyceum nights") | 3–4 calls, 50–90k input tokens, 13–20 s to first words | 1–2 calls, 15–35k input, about 7–9 s (the measured two-call floor) |
| Needing new research | search round + detail round + finish | the search round disappears (IDs are in the index): about 3–6 s and 12–25k tokens saved |
| Web pages already read | re-fetched on a cold instance | replayed from the token |

The index costs 0.6–3k tokens per call, mostly served from the prompt cache after the first turn.

## Build order (for the plan that follows approval)

1. `deadbot/notebook.py`: entries, per-tool summaries with a generic fallback, encode/sign/verify, replay.
2. Harvest entries after each turn in `_respond` and the stream path.
3. `notebook` on the request and response; OpenAPI export and `gen:types`.
4. Index and delta messages in `_prepare`.
5. The `read_notebook` tool.
6. Grounding extended with notebook IDs.
7. Prompt sentences.
8. Notebooks in the warm-answers bundle.
9. Frontend: hold the token, send it back, send `focus` on grid clicks (already defined by the grid plan).
10. Live multi-turn evals: extend `scripts/measure_turns.py` to question sequences (Europe '72 → a Lyceum night → Morning Dew) and compare calls, tokens, cache hits and seconds before and after.

## Open questions for the owner

- **Token in the browser or a shared store?** Recommendation: the signed token now. It needs no new service, and the interface lets us move to a store if sessions ever need to be shared or the token grows too large.
- **How long should a conversation's research last?** With the token it lasts as long as the tab. With a store, a TTL has to be chosen (24 hours suggested).
