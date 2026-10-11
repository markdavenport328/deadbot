# Research Notebook Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Keep what each turn's tools found, carry it to the next turn in a signed token the browser holds, and let the model answer a follow-up from that record, read entries back in full, or research what is new.

**Architecture:** A new `deadbot/notebook.py` turns a finished turn's tool calls into entries (the call, every ID and URL its result held, a one-line fact digest written by code, and the payload only for web results) plus a digest of the page shown. `deadbot/api.py` decodes the token from `ExperienceRequest.notebook`, places each earlier turn's lines right after that turn's answer in the replayed transcript (append-only, so the provider's prompt cache keeps the prefix), and returns an updated token on `ExperienceResponse.notebook`. A new `read_notebook` tool replays canonical calls from the store and returns stored web payloads, reading the notebook from `config["configurable"]["notebook"]` so the tool schema stays static. Notebook IDs and URLs join the turn's grounding, so the server hydrates every fact from the store as before.

**Tech Stack:** Python 3.14 / FastAPI / Pydantic / LangGraph 1.2 / langchain-openai 1.6 (Responses API, `prompt_cache_key`); hmac + zlib + base64 from the standard library; React + TypeScript + Vite; vitest + jsdom.

**Spec:** `docs/superpowers/specs/2026-10-09-research-notebook-design.md` (approved). Its open questions are answered: the notebook is a server-signed token in the browser, and it lasts as long as the tab's session. Read `AGENTS.md` and the grid plan `docs/superpowers/plans/2026-10-09-grid-block.md` (Task 7 defines `AskFocus` and `ExperienceRequest.focus`, consumed here unchanged).

## Global Constraints

- Read `AGENTS.md` first. Code guards facts and transport; the model owns judgment. Code writes the notebook's fact lines and keeps the record exact; the model decides whether to answer from the index, call `read_notebook`, or research. No keyword routes, no forced reads, no second model step.
- **Order with the grid plan.** Tasks 1–3 touch only new files, `deadbot/composition.py` (one constant), `deadbot/config.py`, `.env.example`, `deadbot/turn_metrics.py` and `scripts/measure_turns.py`, none of which grid Tasks 1–7 change; they may start now. Tasks 4–9 start **after grid Tasks 1–7 have merged to `main`** and build on the grid version of `_prepare`, `_Invocation`, `_respond`, `ExperienceRequest`, `build_tools`, `describe_tool_call`, `SYSTEM_PROMPT`, `build_experience_response` and `askQuestion`. Where a step shows a whole function from those files, keep every grid line as it is and add only the lines marked `# NEW`.
- `AskFocus` and `ExperienceRequest.focus` are consumed exactly as grid Task 7 defines them: `label`, `block_type`, `block_id`, `ids`, `facts`.
- Secret: `DEADBOT_NOTEBOOK_SECRET`. When it is unset, every turn runs without a notebook and the server logs `DEADBOT_NOTEBOOK_SECRET is not set; turns run without a research notebook` once per process. Never log the secret or a token's contents.
- A missing, unsigned, tampered or oversized-when-inflated token means the turn runs without a notebook and a warning is logged. The visitor still gets an answer.
- Ceilings trim and log; they never refuse or police the model: 80 entries (compact to 60), about 4,000 index tokens of entry lines (compact to 3,000), page digests for the last 6 turns, 12 blocks per digest, 400 IDs and 60 URLs per entry, 150,000 characters per token (`TOKEN_BYTE_CEILING`), 4,000,000 bytes inflated, and the existing 80,000-character tool-result ceiling for each `read_notebook` result. Over the token ceiling, drop stored web payloads least recently read first, keeping the entry; then drop the least recently read entries.
- Prompt-cache shape: `SYSTEM_PROMPT` and every tool schema stay byte-identical across turns and requests; nothing per-conversation goes there. Notebook text reaches the model only as messages in the replayed history, and a new turn only appends. `prompt_cache_key` is the conversation's stable `thread_id`, sent only to the OpenAI provider.
- Prompt and tool-description text says what to do. No "do not" sentences (`tests/test_graph.py` asserts `"do not" not in prompt.casefold()` and `prompt.count("this turn") == 1`).
- After any `deadbot/experience.py` change: `PYTHONPATH=. /Users/markdavenport/Development/DeadBot/.venv/bin/python scripts/export_openapi.py` then `npm run gen:types --prefix web`. CI fails on drift in `web/openapi.json` or `web/src/generated/api.ts`.
- Python tests: `PYTHONPATH=. /Users/markdavenport/Development/DeadBot/.venv/bin/python -m pytest -q` (full suite before each task's commit). Web: `npm ci --prefix web` once if the worktree has no `node_modules`, then `npm test --prefix web` and `npm run build --prefix web`.
- Stage files by name. Never `git add -A` or `git add .`. Never bare `git stash`. Never push: when work is ready, give the owner the `git push` command on its own line and wait.
- Commit trailer: `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>` (or the model actually doing the work).
- Fixtures prove the plumbing; only live runs prove follow-ups got faster and stayed good. Task 3 records the "before" numbers; Task 9 runs the same sequences after.

## File Structure

| File | Responsibility |
|---|---|
| `deadbot/notebook.py` (new) | `Entry`, `PageDigest`, `Notebook`; entry keys; fact lines per tool with a generic fallback; harvesting a finished turn; page digest; rendering turn lines, deltas and focus flags; placing deltas in the transcript; `find`, `grounding`, `entries_mentioning`; compaction; HMAC sign, encode, verify, decode. |
| `deadbot/composition.py` | `NOTEBOOK_MESSAGE_NAME`; `_tool_payloads` unwraps `read_notebook` results so each read result counts as a payload. |
| `deadbot/config.py`, `.env.example` | `Settings.notebook_secret` from `DEADBOT_NOTEBOOK_SECRET` (kept out of `repr`). |
| `deadbot/turn_metrics.py`, `scripts/measure_turns.py` | `notebook_reads`, `notebook_index_chars`; multi-turn sequences; cached share; with/without-notebook comparison. |
| `deadbot/experience.py` | `NOTEBOOK_TOKEN_MAX_CHARS`, `ExperienceRequest.notebook`, `ExperienceResponse.notebook`. |
| `deadbot/api.py` | Decode in `_prepare`; transcript with notebook deltas and focus flags; isolated invocation thread; `_run_config`; harvest and encode in `_respond`; notebook-carrying requests skip the response cache; `_turn_grounding`. |
| `deadbot/finish.py` | `_conversation` skips notebook messages; `merge_grounding`; `build_experience_response(..., extra_grounding=...)`; finish tool description names the notebook. |
| `deadbot/graph.py` | `run_config(..., notebook=, prompt_cache_key=)`; `call_model` passes `prompt_cache_key` to OpenAI; the notebook paragraph and the grounding sentence in `SYSTEM_PROMPT`. |
| `deadbot/tools.py` | `read_notebook`. |
| `deadbot/progress.py` | Status line for `read_notebook`. |
| `scripts/warm_answers.py` | Reports how many bundled starter answers carry a notebook; says so when the secret is missing. |
| `web/src/research-notebook.ts` (new) | `readStoredNotebook`, `storeNotebook`, `clearStoredNotebook` (sessionStorage, every access in try/catch). |
| `web/src/App.tsx` | Hold the token in state, send it with follow-ups, store it, clear it on a fresh start. |
| `tests/notebook_support.py` (new) | Shared builders: real tool output, real turns, a test secret. |
| `tests/test_notebook.py`, `tests/test_api_notebook.py`, `tests/test_read_notebook.py` (new) | Backend tests. |
| `tests/test_config.py`, `tests/test_graph.py`, `tests/test_progress.py`, `tests/test_turn_metrics.py`, `tests/test_measure_turns.py`, `tests/test_response_cache.py` | Additions. |
| `web/src/research-notebook.test.ts`, `web/src/App.notebook.test.tsx` (new) | Frontend tests. |
| `docs/measurements/<date>-notebook-before.md`, `docs/measurements/<date>-notebook-after.md` (new) | Live numbers before and after. |

---

### Task 1: Notebook entries, fact lines, page digests and the transcript

**Files:**
- Create: `deadbot/notebook.py`
- Modify: `deadbot/composition.py` (one constant next to `_latest_turn`, ~line 91)
- Create: `tests/notebook_support.py`
- Test: `tests/test_notebook.py`

**Interfaces:**
- Consumes: `finish._walk(value, ids, urls, key=None)`, `finish.FINISH_TOOL_NAME`, `finish.build_experience_response(question, thread_id, messages, store)`, `composition._content_text`, `composition._latest_turn`, `experience.ConversationTurn`, `experience.ExperienceResponse`.
- Produces (in `deadbot/notebook.py`):
  - `READ_TOOL_NAME = "read_notebook"`, `WEB_TOOLS: frozenset[str]`, `UNRECORDED_TOOLS: frozenset[str]`
  - `@dataclass Entry(key: str, tool: str, args: dict, ids: list[str], urls: list[str], summary: str, tokens: int, turn: int, last_read: int, payload: dict | None = None)`
  - `@dataclass PageDigest(turn: int, answer_key: str, title: str, blocks: list[dict] = [], chips: list[str] = [])` (each block dict: `type`, `ids`, `title`, `note`)
  - `@dataclass Notebook(turns: int = 0, entries: list[Entry] = [], pages: list[PageDigest] = [])` with `to_json() -> dict` and `Notebook.from_json(data) -> Notebook` (lenient)
  - `entry_key(tool: str, args: dict) -> str` (10 hex chars), `answer_key(text: str) -> str` (12 hex chars)
  - `summarize(tool: str, args: dict, payload: dict, tokens: int) -> str`
  - `tool_results(turn_messages: list) -> list[tuple[str, dict, dict, int]]` (name, args, payload, chars), `keys_read(turn_messages: list) -> list[str]`
  - `page_digest(response: ExperienceResponse, turn: int) -> PageDigest`
  - `record_turn(book: Notebook, turn_messages: list, response: ExperienceResponse) -> Notebook` (returns a new notebook)
  - `turn_numbers(book) -> list[int]`, `turn_lines(book, number) -> list[str]`, `entry_tokens(book) -> int`
  - `render_turn(book, number) -> str`, `render_earlier(book, numbers) -> str`, `render_flags(entries: list[Entry]) -> str`
  - `notebook_message(text: str) -> HumanMessage` (named `NOTEBOOK_MESSAGE_NAME`)
  - `transcript_with_notebook(book, conversation: list[ConversationTurn]) -> list[BaseMessage]`
  - `find(book, wanted: Iterable[str], *, per_id: int = 3) -> tuple[list[Entry], list[str]]`
  - `entries_mentioning(book, ids: Iterable[str], *, limit: int = 8) -> list[Entry]`
  - `grounding(book) -> tuple[frozenset[str], frozenset[str]]` (ids, urls)
- Produces (in `deadbot/composition.py`): `NOTEBOOK_MESSAGE_NAME = "research_notebook"`.
- Produces (in `tests/notebook_support.py`): `SECRET`, `LYCEUM`, `store()`, `tools()`, `call_messages(calls, *, prefix)`, `plan_for(answer, items=None)`, `finish_messages(answer, *, items=None, call_id="f1")`, `turn(question, answer, calls, *, items=None, prefix="c")`, `record(book, question, answer, calls, *, items=None, prefix="c") -> (Notebook, ExperienceResponse)`.

- [ ] **Step 1: Add the message-name constant**

In `deadbot/composition.py`, directly above `def _latest_turn`:

```python
# Research-notebook lines travel to the model as human messages with this
# name. The Responses API drops message names, so the model reads only the
# text; Deadbot uses the name to keep them out of the visible conversation.
NOTEBOOK_MESSAGE_NAME = "research_notebook"
```

- [ ] **Step 2: Write the shared test builders**

Create `tests/notebook_support.py`:

```python
"""Shared builders for research-notebook tests: real tool output, real turns."""

from __future__ import annotations

from functools import lru_cache
from typing import Any

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from deadbot import composition, notebook
from deadbot.data import CanonicalStore
from deadbot.finish import build_experience_response
from deadbot.tools import build_tools

SECRET = "test-notebook-secret"
LYCEUM = [("get_show", {"show_id_or_date": "1972-05-26"})]


@lru_cache(maxsize=1)
def store() -> CanonicalStore:
    return CanonicalStore()


@lru_cache(maxsize=1)
def tools() -> dict[str, Any]:
    return {item.name: item for item in build_tools(store())}


def call_messages(calls: list[tuple[str, dict]], *, prefix: str = "c") -> list[Any]:
    messages: list[Any] = []
    for index, (name, args) in enumerate(calls):
        call_id = f"{prefix}{index}"
        messages.append(AIMessage(content="", tool_calls=[{"name": name, "args": args, "id": call_id, "type": "tool_call"}]))
        messages.append(ToolMessage(content=tools()[name].invoke(args), tool_call_id=call_id, name=name))
    return messages


def plan_for(answer: str, items: list[dict] | None = None) -> dict[str, Any]:
    groups = [{"presentation": "collection", "items": items}] if items else []
    return {"chat_answer": answer, "title": answer[:40], "lead": None, "groups": groups}


def finish_messages(answer: str, *, items: list[dict] | None = None, call_id: str = "f1") -> list[Any]:
    return [
        AIMessage(content="", tool_calls=[{"name": "finish_response", "args": plan_for(answer, items), "id": call_id, "type": "tool_call"}]),
        ToolMessage(content="Response delivered to the visitor.", tool_call_id=call_id, name="finish_response"),
    ]


def turn(question: str, answer: str, calls: list[tuple[str, dict]], *, items: list[dict] | None = None, prefix: str = "c") -> list[Any]:
    return [HumanMessage(content=question), *call_messages(calls, prefix=prefix), *finish_messages(answer, items=items, call_id=f"{prefix}f")]


def record(book, question, answer, calls, *, items=None, prefix="c"):
    messages = turn(question, answer, calls, items=items, prefix=prefix)
    response = build_experience_response(question, "t", messages, store())
    return notebook.record_turn(book, composition._latest_turn(messages), response), response
```

- [ ] **Step 3: Write the failing tests**

Create `tests/test_notebook.py`:

```python
import json

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from deadbot import composition, notebook
from deadbot.experience import ConversationTurn
from deadbot.finish import build_experience_response
from notebook_support import LYCEUM, finish_messages, record, store

MORNING_DEW = [("get_song", {"song_id_or_title": "Morning Dew"})]
PAGE = {
    "state": "ok",
    "url": "https://www.example.org/lyceum",
    "title": "Four nights at the Lyceum",
    "total_chars": 5000,
    "offset": 0,
    "text": "The band closed the tour in London.",
}


def _web_turn(payload):
    messages = [
        HumanMessage(content="What did the papers say?"),
        AIMessage(content="", tool_calls=[{"name": "read_page", "args": {"url": PAGE["url"]}, "id": "r1", "type": "tool_call"}]),
        ToolMessage(content=json.dumps(payload), tool_call_id="r1", name="read_page"),
        *finish_messages("Four nights."),
    ]
    response = build_experience_response("What did the papers say?", "t", messages, store())
    return notebook.record_turn(notebook.Notebook(), composition._latest_turn(messages), response)


def test_each_tool_call_becomes_one_entry_with_its_ids_and_a_fact_line():
    book, _ = record(notebook.Notebook(), "Tell me about May 26, 1972.", "The last Lyceum night.", LYCEUM + MORNING_DEW)
    assert book.turns == 1
    show, song = book.entries
    assert show.key == notebook.entry_key("get_show", {"show_id_or_date": "1972-05-26"})
    assert show.summary.startswith("get_show gd-1972-05-26 · Lyceum, London · 31 songs in 2 sets · 4 recordings · ~")
    assert song.summary.startswith("get_song song-morning-dew · Morning Dew · 282 performances, 1967–1995 · 79 releases · ~")
    assert {"gd-1972-05-26", "gd-1972-05-26-promised-land-1-1"} <= set(show.ids)
    assert "song-morning-dew" in song.ids
    assert (show.turn, show.last_read, show.payload) == (1, 1, None)


def test_a_web_result_keeps_its_payload_and_its_urls():
    (entry,) = _web_turn(PAGE).entries
    assert entry.payload == PAGE
    assert entry.summary.startswith('read_page example.org/lyceum · "Four nights at the Lyceum" · 35 of 5000 chars · ~')
    assert PAGE["url"] in entry.urls


def test_errors_and_the_finish_call_are_not_recorded():
    book, _ = record(notebook.Notebook(), "Tell me about 1972-13-45.", "No such night.", [("get_show", {"show_id_or_date": "1972-13-45"})])
    assert book.entries == []
    assert book.pages[0].turn == 1


def test_running_the_same_call_again_keeps_its_first_turn_and_line():
    first, _ = record(notebook.Notebook(), "Q1", "A1", LYCEUM, prefix="a")
    second, _ = record(first, "Q2", "A2", LYCEUM, prefix="b")
    (entry,) = second.entries
    assert (entry.turn, entry.last_read, entry.summary) == (1, 2, first.entries[0].summary)
    assert second.turns == 2


def test_reading_an_entry_back_marks_it_read_without_adding_an_entry():
    first, _ = record(notebook.Notebook(), "Q1", "A1", LYCEUM, prefix="a")
    key = first.entries[0].key
    messages = [
        HumanMessage(content="Q2"),
        AIMessage(content="", tool_calls=[{"name": "read_notebook", "args": {"keys_or_ids": [key]}, "id": "n1", "type": "tool_call"}]),
        ToolMessage(content=json.dumps({"notebook_entries": [{"key": key, "tool": "get_show", "args": {}, "result": {"show": {}}}]}), tool_call_id="n1", name="read_notebook"),
        *finish_messages("A2"),
    ]
    response = build_experience_response("Q2", "t", messages, store())
    second = notebook.record_turn(first, composition._latest_turn(messages), response)
    assert [(entry.key, entry.last_read) for entry in second.entries] == [(key, 2)]


def test_the_page_digest_names_each_block_and_the_chips():
    item = {
        "type": "show_unit",
        "show_id": "gd-1972-05-26",
        "title": "The last Lyceum night",
        "note": "Morning Dew out of The Other One.",
        "visible_facets": ["setlist"],
        "follow_ups": [{"label": "Lyceum Morning Dew", "question": "How does the Lyceum Morning Dew compare?"}],
    }
    book, response = record(notebook.Notebook(), "Tell me about May 26, 1972.", "The last Lyceum night.", LYCEUM, items=[item])
    (page,) = book.pages
    assert page.answer_key == notebook.answer_key(response.answer)
    assert page.blocks[0]["type"] == "show_unit" and page.blocks[0]["ids"] == ["gd-1972-05-26"]
    assert page.blocks[0]["note"] == "Morning Dew out of The Other One."
    assert page.chips == ["Lyceum Morning Dew"]


def test_each_turns_lines_follow_its_answer_in_the_transcript():
    book, _ = record(notebook.Notebook(), "Tell me about May 26, 1972.", "The last Lyceum night.", LYCEUM)
    conversation = [
        ConversationTurn(role="user", text="Tell me about May 26, 1972."),
        ConversationTurn(role="assistant", text="The last Lyceum night."),
    ]
    messages = notebook.transcript_with_notebook(book, conversation)
    assert [message.type for message in messages] == ["human", "ai", "human"]
    assert messages[2].name == composition.NOTEBOOK_MESSAGE_NAME
    assert messages[2].content.startswith("Research notebook, turn 1:")
    assert f"[{book.entries[0].key}] get_show gd-1972-05-26" in messages[2].content


def test_a_turn_whose_answer_is_not_in_the_transcript_goes_in_one_leading_message():
    book, _ = record(notebook.Notebook(), "Tell me about May 26, 1972.", "The last Lyceum night.", LYCEUM)
    conversation = [ConversationTurn(role="user", text="Hi"), ConversationTurn(role="assistant", text="Something else.")]
    messages = notebook.transcript_with_notebook(book, conversation)
    assert [message.type for message in messages] == ["human", "human", "ai"]
    assert messages[0].content.startswith("Research notebook from earlier in this conversation")
    assert "Turn 1:" in messages[0].content


def test_an_empty_notebook_leaves_the_transcript_as_it_was():
    conversation = [ConversationTurn(role="user", text="Hi"), ConversationTurn(role="assistant", text="Hello.")]
    messages = notebook.transcript_with_notebook(notebook.Notebook(), conversation)
    assert [(message.type, message.content) for message in messages] == [("human", "Hi"), ("ai", "Hello.")]


def test_find_matches_keys_then_arguments_then_ids():
    book, _ = record(notebook.Notebook(), "Q", "A", LYCEUM + MORNING_DEW)
    show, song = book.entries
    found, missing = notebook.find(book, [f"[{song.key}]", "1972-05-26", "gd-1972-05-26-promised-land-1-1", "nope"])
    assert [entry.key for entry in found] == [song.key, show.key]
    assert missing == ["nope"]


def test_grounding_and_focus_flags_cover_entries_and_pages():
    item = {"type": "show_unit", "show_id": "gd-1972-05-26", "visible_facets": ["setlist"]}
    book, _ = record(notebook.Notebook(), "Q", "A", LYCEUM, items=[item])
    ids, urls = notebook.grounding(book)
    assert "gd-1972-05-26-promised-land-1-1" in ids and "gd-1972-05-26" in ids
    assert isinstance(urls, frozenset)
    flagged = notebook.entries_mentioning(book, ["gd-1972-05-26", "gd-1999-01-01"])
    assert [entry.tool for entry in flagged] == ["get_show"]
    assert notebook.render_flags(flagged).startswith("Already in the research notebook for what the visitor clicked:")
    assert notebook.render_flags([]) == ""


def test_from_json_keeps_good_entries_and_skips_bad_ones():
    book, _ = record(notebook.Notebook(), "Q", "A", LYCEUM)
    data = book.to_json()
    data["entries"].append({"key": "only-a-key"})
    data["pages"].append("junk")
    restored = notebook.Notebook.from_json(data)
    assert [entry.key for entry in restored.entries] == [book.entries[0].key]
    assert len(restored.pages) == 1
    assert notebook.Notebook.from_json("junk") == notebook.Notebook()
```

- [ ] **Step 4: Run the tests to verify they fail**

Run: `PYTHONPATH=. /Users/markdavenport/Development/DeadBot/.venv/bin/python -m pytest -q tests/test_notebook.py`
Expected: FAIL at import with `ImportError: cannot import name 'notebook' from 'deadbot'`.

- [ ] **Step 5: Write `deadbot/notebook.py`**

```python
"""The research notebook: what earlier turns of one conversation found.

Each tool call a turn makes becomes one entry: the call itself (tool and
arguments), every library ID and URL its result held, and a one-line fact
digest written by code. A canonical result is not stored, because the same
call against the same library returns the same payload and read_notebook can
run it again; a web result costs seconds and may change, so its payload is
kept. Each turn also leaves a digest of the page the visitor saw.

Code keeps this record exact and carries it between requests. The model
decides what in it matters and what to read again.
"""

from __future__ import annotations

import copy
import hashlib
import json
import logging
from collections.abc import Iterable
from dataclasses import asdict, dataclass, field, fields
from typing import Any
from urllib.parse import urlparse

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage

from deadbot.composition import NOTEBOOK_MESSAGE_NAME, _content_text
from deadbot.experience import ConversationTurn, ExperienceResponse
from deadbot.finish import FINISH_TOOL_NAME, _walk


logger = logging.getLogger(__name__)

READ_TOOL_NAME = "read_notebook"
UNRECORDED_TOOLS = frozenset({FINISH_TOOL_NAME, READ_TOOL_NAME})
# Results fetched from outside the library: slow, and not guaranteed to come
# back the same, so the notebook keeps their payloads.
WEB_TOOLS = frozenset({
    "read_page",
    "search_site",
    "get_recording_reviews",
    "get_historical_weather",
    "get_astronomy",
    "get_deadnet_song_context",
    "get_deadcast_metadata",
})
IDS_PER_ENTRY_CEILING = 400
URLS_PER_ENTRY_CEILING = 60
DIGEST_BLOCK_CEILING = 12
CHIP_CEILING = 8

TURN_HEADING = (
    "Research notebook, turn {number}: what the tools returned for the answer above, one line per call. "
    "read_notebook brings any entry back in full."
)
EARLIER_HEADING = (
    "Research notebook from earlier in this conversation, one line per call. "
    "read_notebook brings any entry back in full."
)
FLAGS_HEADING = "Already in the research notebook for what the visitor clicked:"


@dataclass
class Entry:
    key: str
    tool: str
    args: dict[str, Any]
    ids: list[str]
    urls: list[str]
    summary: str
    tokens: int
    turn: int
    last_read: int
    payload: dict[str, Any] | None = None


@dataclass
class PageDigest:
    turn: int
    answer_key: str
    title: str
    blocks: list[dict[str, Any]] = field(default_factory=list)
    chips: list[str] = field(default_factory=list)


@dataclass
class Notebook:
    turns: int = 0
    entries: list[Entry] = field(default_factory=list)
    pages: list[PageDigest] = field(default_factory=list)

    def to_json(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_json(cls, data: Any) -> "Notebook":
        """Read a stored notebook leniently: a malformed entry or page is skipped."""

        if not isinstance(data, dict):
            return cls()
        entries = [entry for raw in _list(data.get("entries")) if (entry := _entry_from(raw)) is not None]
        pages = [page for raw in _list(data.get("pages")) if (page := _page_from(raw)) is not None]
        turns = data.get("turns")
        if not isinstance(turns, int):
            turns = max([entry.turn for entry in entries] + [page.turn for page in pages] + [0])
        return cls(turns=turns, entries=entries, pages=pages)


_ENTRY_FIELDS = tuple(item.name for item in fields(Entry))
_PAGE_FIELDS = tuple(item.name for item in fields(PageDigest))


def _list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _entry_from(raw: Any) -> Entry | None:
    if not isinstance(raw, dict):
        return None
    try:
        entry = Entry(**{name: raw[name] for name in _ENTRY_FIELDS if name in raw})
    except TypeError:
        return None
    if not (isinstance(entry.key, str) and isinstance(entry.tool, str) and isinstance(entry.args, dict)):
        return None
    if not (isinstance(entry.turn, int) and isinstance(entry.last_read, int)):
        return None
    return entry


def _page_from(raw: Any) -> PageDigest | None:
    if not isinstance(raw, dict):
        return None
    try:
        page = PageDigest(**{name: raw[name] for name in _PAGE_FIELDS if name in raw})
    except TypeError:
        return None
    return page if isinstance(page.turn, int) and isinstance(page.answer_key, str) else None


def entry_key(tool: str, args: dict[str, Any]) -> str:
    """The same call with the same arguments has the same key."""

    text = json.dumps([tool, args], sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:10]


def answer_key(text: str) -> str:
    """Matches a turn's page digest to that turn's answer in the browser's transcript."""

    return hashlib.sha256(text.strip()[:8_000].encode("utf-8")).hexdigest()[:12]


# --- fact lines --------------------------------------------------------------


def _count(number: Any, singular: str, plural: str | None = None) -> str:
    return f"{number} {singular if number == 1 else plural or singular + 's'}"


def _args_text(args: dict[str, Any]) -> str:
    values = []
    for value in args.values():
        if value in (None, "", [], {}):
            continue
        values.append(json.dumps(value, ensure_ascii=False) if isinstance(value, (list, dict)) else str(value))
    return " ".join(values)[:80]


def _tokens_text(tokens: int) -> str:
    return f"~{tokens / 1000:.1f}k tok" if tokens >= 1000 else f"~{tokens} tok"


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _show_parts(args: dict[str, Any], payload: dict[str, Any]) -> list[str]:
    show, venue = _dict(payload.get("show")), _dict(payload.get("venue"))
    songs = [row for row in _list(payload.get("performances")) if isinstance(row, dict)]
    sets = {row.get("set_number") for row in songs if row.get("set_number")}
    recordings = _dict(payload.get("recordings")).get("count")
    parts = [show.get("show_id") or _args_text(args), ", ".join(str(part) for part in (venue.get("name"), venue.get("city")) if part)]
    parts.append(f"{_count(len(songs), 'song')} in {_count(len(sets), 'set')}" if songs else "no setlist")
    if recordings:
        parts.append(_count(recordings, "recording"))
    return parts


def _song_parts(args: dict[str, Any], payload: dict[str, Any]) -> list[str]:
    song, summary = _dict(payload.get("song")), _dict(payload.get("performance_summary"))
    first = _dict(summary.get("first_performance")).get("show_date")
    last = _dict(summary.get("last_performance")).get("show_date")
    parts = [song.get("song_id") or _args_text(args), song.get("title") or ""]
    if summary.get("performance_count") is not None:
        span = f", {str(first)[:4]}–{str(last)[:4]}" if first and last else ""
        parts.append(_count(summary["performance_count"], "performance") + span)
    if payload.get("release_count") is not None:
        parts.append(_count(payload["release_count"], "release"))
    return parts


def _song_performances_parts(args: dict[str, Any], payload: dict[str, Any]) -> list[str]:
    song = _dict(payload.get("song"))
    rows = _list(payload.get("performances"))
    total = payload.get("performance_count", len(rows))
    return [song.get("song_id") or _args_text(args), song.get("title") or "", f"{len(rows)} of {_count(total, 'performance')} from offset {payload.get('offset', 0)}"]


def _search_parts(args: dict[str, Any], payload: dict[str, Any]) -> list[str]:
    matches = [match for match in _list(payload.get("matches")) if isinstance(match, dict)]
    labels = ", ".join(str(match.get("label") or match.get("id")) for match in matches[:3])
    query = payload.get("query") or args.get("query") or ""
    return [f'"{query}"', _count(len(matches), "match", "matches") + (f": {labels}" if labels else "")]


def _catalog_parts(args: dict[str, Any], payload: dict[str, Any]) -> list[str]:
    columns = [str(column) for column in _list(payload.get("columns"))][:5]
    return [
        str(payload.get("query") or "sql"),
        str(payload.get("result_id") or ""),
        _count(len(_list(payload.get("rows"))), "row"),
        ("columns " + ", ".join(columns)) if columns else "",
    ]


def _aggregate_parts(args: dict[str, Any], payload: dict[str, Any]) -> list[str]:
    query = _dict(payload.get("query"))
    filters = ", ".join(f"{key} {value}" for key, value in _dict(query.get("filters")).items() if value not in (None, "", []))
    return [
        str(payload.get("aggregation_id") or ""),
        f"{query.get('dataset')} by {query.get('group_by')}, {query.get('measure')}",
        filters,
        _count(len(_list(payload.get("rows"))), "row"),
    ]


def _read_page_parts(args: dict[str, Any], payload: dict[str, Any]) -> list[str]:
    parsed = urlparse(str(payload.get("final_url") or payload.get("url") or args.get("url") or ""))
    text = str(payload.get("text") or "")
    parts = [(parsed.netloc.removeprefix("www.") + parsed.path)[:80]]
    if payload.get("title"):
        parts.append(f'"{str(payload["title"])[:80]}"')
    parts.append(f"{len(text)} of {payload.get('total_chars') or len(text)} chars")
    if args.get("focus"):
        parts.append(f'focus "{args["focus"]}"')
    return parts


def _search_site_parts(args: dict[str, Any], payload: dict[str, Any]) -> list[str]:
    hits = [hit for hit in _list(payload.get("hits")) if isinstance(hit, dict)]
    site = payload.get("site") or args.get("site") or ""
    query = payload.get("query") or args.get("query") or ""
    return [f'{site} "{query}"', _count(len(hits), "hit")]


def _generic_parts(args: dict[str, Any], payload: dict[str, Any]) -> list[str]:
    parts = [_args_text(args) or "(no arguments)"]
    for key, value in payload.items():
        if isinstance(value, list) and len(parts) < 5:
            parts.append(f"{len(value)} {key}")
    return parts


_SUMMARIES = {
    "get_show": _show_parts,
    "get_song": _song_parts,
    "list_song_performances": _song_performances_parts,
    "search_entities": _search_parts,
    "query_catalog": _catalog_parts,
    "aggregate_data": _aggregate_parts,
    "read_page": _read_page_parts,
    "search_site": _search_site_parts,
}


def summarize(tool: str, args: dict[str, Any], payload: dict[str, Any], tokens: int) -> str:
    """One line of facts about a result, for the index the model browses."""

    try:
        parts = _SUMMARIES.get(tool, _generic_parts)(args, payload)
    except Exception:  # A fact line must never cost the turn its notebook.
        logger.info("The notebook line for %s fell back to the generic one", tool, exc_info=True)
        parts = _generic_parts(args, payload)
    head, *rest = [str(part) for part in parts] or [""]
    return " · ".join([f"{tool} {head}".strip(), *(part for part in rest if part), _tokens_text(tokens)])


# --- harvesting a turn ---------------------------------------------------------


def tool_results(turn_messages: list[Any]) -> list[tuple[str, dict[str, Any], dict[str, Any], int]]:
    """Each successful research call this turn: name, arguments, parsed payload, size in characters."""

    calls: dict[str, dict[str, Any]] = {}
    for message in turn_messages:
        if getattr(message, "type", None) == "ai":
            for call in getattr(message, "tool_calls", None) or []:
                if call.get("id"):
                    calls[call["id"]] = call
    results = []
    for message in turn_messages:
        if getattr(message, "type", None) != "tool" or getattr(message, "status", None) == "error":
            continue
        call = calls.get(getattr(message, "tool_call_id", None) or "")
        name = (call or {}).get("name") or getattr(message, "name", None)
        if call is None or not name or name in UNRECORDED_TOOLS:
            continue
        text = _content_text(getattr(message, "content", ""))
        try:
            payload = json.loads(text)
        except (TypeError, ValueError):
            continue
        if not isinstance(payload, dict) or "error" in payload:
            continue
        results.append((name, dict(call.get("args") or {}), payload, len(text)))
    return results


def keys_read(turn_messages: list[Any]) -> list[str]:
    """Entry keys the model read back with read_notebook this turn."""

    keys = []
    for message in turn_messages:
        if getattr(message, "type", None) != "tool" or getattr(message, "name", None) != READ_TOOL_NAME:
            continue
        try:
            payload = json.loads(_content_text(getattr(message, "content", "")))
        except (TypeError, ValueError):
            continue
        for item in _list(payload.get("notebook_entries")) if isinstance(payload, dict) else []:
            if isinstance(item, dict) and isinstance(item.get("key"), str):
                keys.append(item["key"])
    return keys


def _ids_and_urls(payload: dict[str, Any]) -> tuple[list[str], list[str]]:
    ids: set[str] = set()
    urls: set[str] = set()
    _walk(payload, ids, urls)
    id_list, url_list = sorted(ids), sorted(urls)
    if len(id_list) > IDS_PER_ENTRY_CEILING or len(url_list) > URLS_PER_ENTRY_CEILING:
        logger.info(
            "A notebook entry kept %d of %d IDs and %d of %d URLs",
            min(len(id_list), IDS_PER_ENTRY_CEILING), len(id_list), min(len(url_list), URLS_PER_ENTRY_CEILING), len(url_list),
        )
    return id_list[:IDS_PER_ENTRY_CEILING], url_list[:URLS_PER_ENTRY_CEILING]


def page_digest(response: ExperienceResponse, turn: int) -> PageDigest:
    """What the visitor saw: each block's type, IDs, title and note, and the follow-up chips."""

    blocks: list[dict[str, Any]] = []
    chips: list[str] = []
    for block in response.blocks[:DIGEST_BLOCK_CEILING]:
        data = block.model_dump(mode="json")
        ids = [value for key, value in data.items() if isinstance(value, str) and value and (key == "id" or key.endswith("_id"))][:6]
        title = next((str(data[key]) for key in ("title", "song_title", "release_title") if data.get(key)), "")
        blocks.append({"type": str(data.get("type") or ""), "ids": ids, "title": title[:120], "note": str(data.get("note") or "")[:120]})
        for chip in _list(data.get("follow_ups")):
            label = str(chip.get("label") or "").strip() if isinstance(chip, dict) else ""
            if label and label not in chips:
                chips.append(label)
    return PageDigest(turn=turn, answer_key=answer_key(response.answer), title=response.title[:120], blocks=blocks, chips=chips[:CHIP_CEILING])


def record_turn(book: Notebook, turn_messages: list[Any], response: ExperienceResponse) -> Notebook:
    """A new notebook with this turn's calls and page added."""

    book = copy.deepcopy(book)
    number = book.turns + 1
    book.turns = number
    by_key = {entry.key: entry for entry in book.entries}
    for key in keys_read(turn_messages):
        if key in by_key:
            by_key[key].last_read = number
    for name, args, payload, chars in tool_results(turn_messages):
        key = entry_key(name, args)
        stored = payload if name in WEB_TOOLS else None
        existing = by_key.get(key)
        if existing is not None:
            # The entry keeps its turn and its line, so the notebook messages
            # already sent stay byte-identical for the provider's prompt cache.
            existing.last_read = number
            if stored is not None:
                existing.payload = stored
            continue
        ids, urls = _ids_and_urls(payload)
        entry = Entry(
            key=key, tool=name, args=args, ids=ids, urls=urls,
            summary=summarize(name, args, payload, chars // 4), tokens=chars // 4,
            turn=number, last_read=number, payload=stored,
        )
        book.entries.append(entry)
        by_key[key] = entry
    book.pages = [page for page in book.pages if page.turn != number] + [page_digest(response, number)]
    return book


# --- what the model reads ------------------------------------------------------


def turn_numbers(book: Notebook) -> list[int]:
    return sorted({entry.turn for entry in book.entries} | {page.turn for page in book.pages})


def _entry_line(entry: Entry) -> str:
    return f"[{entry.key}] {entry.summary}"


def _page_lines(page: PageDigest) -> list[str]:
    lines = []
    if page.blocks:
        described = []
        for block in page.blocks:
            text = " ".join(part for part in (str(block.get("type") or ""), " ".join(block.get("ids") or [])) if part)
            if block.get("title"):
                text += f' "{block["title"]}"'
            if block.get("note"):
                text += f": {block['note']}"
            described.append(text)
        lines.append(f'Page shown ("{page.title}"): ' + "; ".join(described))
    if page.chips:
        lines.append("Follow-up chips offered: " + " · ".join(page.chips))
    return lines


def turn_lines(book: Notebook, number: int) -> list[str]:
    lines = [_entry_line(entry) for entry in book.entries if entry.turn == number]
    page = next((page for page in book.pages if page.turn == number), None)
    if page is not None:
        lines.extend(_page_lines(page))
    return lines


def entry_tokens(book: Notebook) -> int:
    """About how many tokens the entry lines cost the model."""

    return sum(len(_entry_line(entry)) + 1 for entry in book.entries) // 4


def render_turn(book: Notebook, number: int) -> str:
    lines = turn_lines(book, number)
    return "\n".join([TURN_HEADING.format(number=number), *lines]) if lines else ""


def render_earlier(book: Notebook, numbers: Iterable[int]) -> str:
    sections: list[str] = []
    for number in numbers:
        lines = turn_lines(book, number)
        if lines:
            sections.extend([f"Turn {number}:", *lines])
    return "\n".join([EARLIER_HEADING, *sections]) if sections else ""


def render_flags(entries: list[Entry]) -> str:
    return "\n".join([FLAGS_HEADING, *(_entry_line(entry) for entry in entries)]) if entries else ""


def notebook_message(text: str) -> HumanMessage:
    return HumanMessage(content=text, name=NOTEBOOK_MESSAGE_NAME)


def transcript_with_notebook(book: Notebook, conversation: list[ConversationTurn]) -> list[BaseMessage]:
    """The browser's transcript with each turn's notebook lines right after that turn's answer.

    A new turn only appends, so everything already sent stays byte-identical
    and the provider's prompt cache keeps it. Turns whose answers are no
    longer in the transcript (trimmed, or never matched) go in one message
    before it.
    """

    by_answer = {page.answer_key: page.turn for page in book.pages}
    placed: set[int] = set()
    body: list[BaseMessage] = []
    for item in conversation:
        if item.role == "user":
            body.append(HumanMessage(content=item.text))
            continue
        body.append(AIMessage(content=item.text))
        number = by_answer.get(answer_key(item.text))
        if number is None or number in placed:
            continue
        placed.add(number)
        text = render_turn(book, number)
        if text:
            body.append(notebook_message(text))
    earlier = render_earlier(book, [number for number in turn_numbers(book) if number not in placed])
    return ([notebook_message(earlier)] if earlier else []) + body


# --- lookups -------------------------------------------------------------------


def _arg_values(args: dict[str, Any]) -> set[str]:
    values: set[str] = set()
    for value in args.values():
        if isinstance(value, str):
            values.add(value)
        elif isinstance(value, list):
            values.update(item for item in value if isinstance(item, str))
    return values


def find(book: Notebook, wanted: Iterable[str], *, per_id: int = 3) -> tuple[list[Entry], list[str]]:
    """Entries by key, else by an argument they were called with, else by an ID they returned (newest first)."""

    found: list[Entry] = []
    seen: set[str] = set()
    missing: list[str] = []
    for raw in wanted:
        value = str(raw).strip().strip("[]")
        if not value:
            continue
        matches = [entry for entry in book.entries if entry.key == value]
        if not matches:
            matches = [entry for entry in book.entries if value in _arg_values(entry.args)]
        if not matches:
            matches = [entry for entry in reversed(book.entries) if value in entry.ids][:per_id]
        if not matches:
            missing.append(value)
            continue
        for entry in matches:
            if entry.key not in seen:
                seen.add(entry.key)
                found.append(entry)
    return found, missing


def entries_mentioning(book: Notebook, ids: Iterable[str], *, limit: int = 8) -> list[Entry]:
    wanted = {str(value) for value in ids if value}
    return [entry for entry in book.entries if wanted & set(entry.ids) or wanted & _arg_values(entry.args)][:limit]


def grounding(book: Notebook) -> tuple[frozenset[str], frozenset[str]]:
    """Every ID and URL the notebook holds, so the page can place them without a new lookup."""

    ids: set[str] = set()
    urls: set[str] = set()
    for entry in book.entries:
        ids.update(entry.ids)
        urls.update(entry.urls)
    for page in book.pages:
        for block in page.blocks:
            ids.update(value for value in block.get("ids") or [] if isinstance(value, str))
    return frozenset(ids), frozenset(urls)
```

- [ ] **Step 6: Run the tests to verify they pass**

Run: `PYTHONPATH=. /Users/markdavenport/Development/DeadBot/.venv/bin/python -m pytest -q tests/test_notebook.py`
Expected: PASS (12 tests). If a measured fact in the two `startswith` lines differs on the day (song counts, recordings), re-measure with the real tool and update the expected text; the shape of the line is what the test protects.

- [ ] **Step 7: Run the full suite**

Run: `PYTHONPATH=. /Users/markdavenport/Development/DeadBot/.venv/bin/python -m pytest -q`
Expected: all pass.

- [ ] **Step 8: Commit**

```bash
git add deadbot/notebook.py deadbot/composition.py tests/notebook_support.py tests/test_notebook.py
git commit -m "Record each turn's research as notebook entries with fact lines and a page digest

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 2: Signing, size ceilings and the secret

**Files:**
- Modify: `deadbot/notebook.py` (append the codec and compaction; `record_turn` returns `compact(book)`)
- Modify: `deadbot/config.py` (`Settings.notebook_secret`)
- Modify: `.env.example`
- Test: `tests/test_notebook.py`, `tests/test_config.py`

**Interfaces:**
- Consumes: everything Task 1 produced in `deadbot/notebook.py`.
- Produces:
  - Constants `NOTEBOOK_VERSION = "v1"`, `ENTRY_CEILING = 80`, `ENTRY_COMPACT_TO = 60`, `INDEX_TOKEN_CEILING = 4_000`, `INDEX_TOKEN_COMPACT_TO = 3_000`, `PAGE_TURN_CEILING = 6`, `TOKEN_BYTE_CEILING = 150_000`, `DECOMPRESSED_CEILING = 4_000_000`
  - `compact(book: Notebook) -> Notebook`
  - `encode(book: Notebook, secret: str | None) -> str | None` (`"v1.<base64url zlib json>.<base64url hmac-sha256>"`)
  - `decode(token: str | None, secret: str | None) -> Notebook` (empty on any problem)
  - `note_missing_secret() -> None` (logs once per process)
  - `_sign(body: str, secret: str) -> str` (tests use it)
  - `Settings.notebook_secret: str | None` (not in `repr`)

- [ ] **Step 1: Write the failing tests**

Add to the imports at the top of `tests/test_notebook.py`:

```python
import base64
import logging
import os
import zlib

from notebook_support import SECRET
```

Then append:

```python
def _entry(index, *, last_read=1, summary=None, payload=None, tool="get_show"):
    return notebook.Entry(
        key=f"k{index:04d}", tool=tool, args={"n": index}, ids=[f"id-{index}"], urls=[],
        summary=summary or f"{tool} {index} · ~10 tok", tokens=10, turn=1, last_read=last_read, payload=payload,
    )


def test_a_notebook_survives_the_round_trip():
    book, _ = record(notebook.Notebook(), "Tell me about May 26, 1972.", "The last Lyceum night.", LYCEUM)
    token = notebook.encode(book, SECRET)
    assert token.startswith("v1.") and token.count(".") == 2
    assert notebook.decode(token, SECRET).to_json() == notebook.compact(book).to_json()


def test_a_changed_token_or_another_secret_reads_as_an_empty_notebook(caplog):
    book, _ = record(notebook.Notebook(), "Q", "A", LYCEUM)
    token = notebook.encode(book, SECRET)
    version, body, signature = token.split(".")
    swapped = "B" if body[20] == "A" else "A"
    tampered = f"{version}.{body[:20]}{swapped}{body[21:]}.{signature}"
    with caplog.at_level(logging.WARNING, logger="deadbot.notebook"):
        assert notebook.decode(tampered, SECRET).entries == []
        assert notebook.decode(token, "another-secret").entries == []
        assert notebook.decode("not a token", SECRET).entries == []
        assert notebook.decode("v1.é.é", SECRET).entries == []
    assert "signature" in caplog.text
    assert body[:40] not in caplog.text


def test_without_a_secret_turns_run_without_a_notebook_and_say_so_once(monkeypatch, caplog):
    monkeypatch.setattr(notebook, "_missing_secret_logged", False)
    with caplog.at_level(logging.WARNING, logger="deadbot.notebook"):
        assert notebook.encode(notebook.Notebook(turns=1), None) is None
        assert notebook.encode(notebook.Notebook(turns=1), "") is None
        assert notebook.decode("v1.x.y", None).entries == []
    assert caplog.text.count("DEADBOT_NOTEBOOK_SECRET is not set") == 1


def test_a_signed_token_that_inflates_past_the_ceiling_is_ignored():
    body = base64.urlsafe_b64encode(zlib.compress(b"[" + b"0," * 3_000_000 + b"0]", 9)).decode("ascii")
    token = f"{notebook.NOTEBOOK_VERSION}.{body}.{notebook._sign(body, SECRET)}"
    assert notebook.decode(token, SECRET).entries == []


def test_too_many_entries_compact_to_sixty_keeping_the_most_recently_read():
    book = notebook.Notebook(turns=1, entries=[_entry(index, last_read=index) for index in range(85)])
    compacted = notebook.compact(book)
    assert [entry.key for entry in compacted.entries] == [f"k{index:04d}" for index in range(25, 85)]


def test_long_index_lines_compact_below_the_token_target():
    book = notebook.Notebook(turns=1, entries=[_entry(index, last_read=index, summary="x" * 1000) for index in range(20)])
    compacted = notebook.compact(book)
    assert notebook.entry_tokens(compacted) <= notebook.INDEX_TOKEN_COMPACT_TO
    assert compacted.entries[-1].key == "k0019" and compacted.entries[0].key != "k0000"


def test_page_digests_keep_the_last_six_turns():
    book = notebook.Notebook(turns=9, pages=[notebook.PageDigest(turn=number, answer_key=f"a{number}", title="T") for number in range(1, 10)])
    assert [page.turn for page in notebook.compact(book).pages] == [4, 5, 6, 7, 8, 9]


def test_over_the_size_ceiling_web_payloads_go_first_least_recently_read():
    entries = [
        _entry(index, last_read=index + 1, tool="read_page", payload={"url": f"https://example.org/{index}", "text": os.urandom(30_000).hex()})
        for index in range(6)
    ]
    token = notebook.encode(notebook.Notebook(turns=6, entries=entries), SECRET)
    assert len(token) <= notebook.TOKEN_BYTE_CEILING
    kept = notebook.decode(token, SECRET)
    assert len(kept.entries) == 6
    assert kept.entries[0].payload is None
    assert kept.entries[-1].payload is not None
```

Append to `tests/test_config.py`:

```python
def test_the_notebook_secret_is_read_from_the_environment_and_kept_out_of_repr(monkeypatch, tmp_path):
    monkeypatch.setenv("DEADBOT_NOTEBOOK_SECRET", "  s3cret-value  ")
    settings = Settings.from_env(env_path=tmp_path / "absent.env")
    assert settings.notebook_secret == "s3cret-value"
    assert "s3cret-value" not in repr(settings)


def test_a_blank_notebook_secret_means_no_notebook(monkeypatch, tmp_path):
    monkeypatch.setenv("DEADBOT_NOTEBOOK_SECRET", " ")
    assert Settings.from_env(env_path=tmp_path / "absent.env").notebook_secret is None
    assert Settings().notebook_secret is None
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `PYTHONPATH=. /Users/markdavenport/Development/DeadBot/.venv/bin/python -m pytest -q tests/test_notebook.py tests/test_config.py`
Expected: FAIL with `AttributeError: module 'deadbot.notebook' has no attribute 'encode'` and `TypeError`/`AttributeError` on `notebook_secret`.

- [ ] **Step 3: Add the secret to `Settings`**

In `deadbot/config.py`, change the import to `from dataclasses import dataclass, field`, add after `response_cache_ttl_seconds`:

```python
    # Signs the research notebook the browser carries between turns. Unset
    # means turns run without a notebook. Kept out of repr so it never lands
    # in a log line.
    notebook_secret: str | None = field(default=None, repr=False)
```

and in `from_env`, after `response_cache_ttl_seconds=...`:

```python
            notebook_secret=(value("DEADBOT_NOTEBOOK_SECRET") or "").strip() or None,
```

Append to `.env.example`:

```
# Signs the research notebook that carries each turn's research to the next
# turn. Any long random string; the same value in every environment that
# serves or builds answers (Vercel: Production and Preview, build and
# runtime). Make one with:
#   python -c "import secrets; print(secrets.token_urlsafe(32))"
# Unset means follow-ups start from the transcript alone.
# DEADBOT_NOTEBOOK_SECRET=
```

- [ ] **Step 4: Add the codec and compaction to `deadbot/notebook.py`**

Add `import base64`, `import hmac` and `import zlib` to the imports. Append:

```python
# --- ceilings, signing, transport ------------------------------------------------

NOTEBOOK_VERSION = "v1"
ENTRY_CEILING = 80
ENTRY_COMPACT_TO = 60
INDEX_TOKEN_CEILING = 4_000
INDEX_TOKEN_COMPACT_TO = 3_000
PAGE_TURN_CEILING = 6
# The whole token as the browser holds it. ExperienceRequest accepts up to
# experience.NOTEBOOK_TOKEN_MAX_CHARS, which is larger.
TOKEN_BYTE_CEILING = 150_000
DECOMPRESSED_CEILING = 4_000_000
_SIGNATURE_ROOM = 64

_missing_secret_logged = False


def note_missing_secret() -> None:
    global _missing_secret_logged
    if not _missing_secret_logged:
        _missing_secret_logged = True
        logger.warning("DEADBOT_NOTEBOOK_SECRET is not set; turns run without a research notebook")


def _least_read(entry: Entry) -> tuple[int, int]:
    return (entry.last_read, entry.turn)


def compact(book: Notebook) -> Notebook:
    """The notebook within its entry, index and page ceilings.

    Over a ceiling, entries go in one batch, least recently read first, down
    to the lower target, so the lines the model has already seen change
    rarely and the provider's prompt cache keeps them.
    """

    book = copy.deepcopy(book)
    book.pages = sorted(book.pages, key=lambda page: page.turn)[-PAGE_TURN_CEILING:]
    if len(book.entries) <= ENTRY_CEILING and entry_tokens(book) <= INDEX_TOKEN_CEILING:
        return book
    before = len(book.entries)
    for victim in sorted(book.entries, key=_least_read):
        if len(book.entries) <= ENTRY_COMPACT_TO and entry_tokens(book) <= INDEX_TOKEN_COMPACT_TO:
            break
        book.entries = [entry for entry in book.entries if entry.key != victim.key]
    logger.info("Research notebook compacted from %d to %d entries", before, len(book.entries))
    return book


def _pack(book: Notebook) -> str:
    text = json.dumps(book.to_json(), ensure_ascii=False, separators=(",", ":"))
    return base64.urlsafe_b64encode(zlib.compress(text.encode("utf-8"), 9)).decode("ascii")


def _sign(body: str, secret: str) -> str:
    digest = hmac.new(secret.encode("utf-8"), f"{NOTEBOOK_VERSION}.{body}".encode("ascii"), hashlib.sha256).digest()
    return base64.urlsafe_b64encode(digest).decode("ascii")


def _drop_one_payload(book: Notebook) -> bool:
    stored = [entry for entry in book.entries if entry.payload is not None]
    if not stored:
        return False
    min(stored, key=_least_read).payload = None
    return True


def _drop_one_entry(book: Notebook) -> bool:
    if not book.entries:
        return False
    victim = min(book.entries, key=_least_read)
    book.entries = [entry for entry in book.entries if entry is not victim]
    return True


def encode(book: Notebook, secret: str | None) -> str | None:
    """The signed token the browser carries to the next turn, or None without a secret."""

    if not secret:
        note_missing_secret()
        return None
    book = compact(book)
    body = _pack(book)
    if len(body) > TOKEN_BYTE_CEILING - _SIGNATURE_ROOM:
        before = len(body)
        while len(body) > TOKEN_BYTE_CEILING - _SIGNATURE_ROOM and (_drop_one_payload(book) or _drop_one_entry(book)):
            body = _pack(book)
        logger.info("Research notebook trimmed from %d to %d characters (%d entries)", before, len(body), len(book.entries))
    return f"{NOTEBOOK_VERSION}.{body}.{_sign(body, secret)}"


def decode(token: str | None, secret: str | None) -> Notebook:
    """The notebook a request carried, or an empty one when it is missing or cannot be trusted."""

    if not token:
        return Notebook()
    if not secret:
        note_missing_secret()
        return Notebook()
    parts = token.split(".")
    if len(parts) != 3 or parts[0] != NOTEBOOK_VERSION:
        logger.warning("Ignoring a research notebook that is not a v1 token")
        return Notebook()
    _, body, signature = parts
    try:
        expected = _sign(body, secret)
    except UnicodeEncodeError:
        logger.warning("Ignoring a research notebook whose signature does not match")
        return Notebook()
    if not hmac.compare_digest(signature.encode("utf-8"), expected.encode("ascii")):
        logger.warning("Ignoring a research notebook whose signature does not match")
        return Notebook()
    try:
        inflater = zlib.decompressobj()
        raw = inflater.decompress(base64.urlsafe_b64decode(body.encode("ascii")), DECOMPRESSED_CEILING)
        if inflater.unconsumed_tail:
            logger.warning("Ignoring a research notebook that inflates past %d bytes", DECOMPRESSED_CEILING)
            return Notebook()
        return Notebook.from_json(json.loads(raw.decode("utf-8")))
    except (ValueError, zlib.error):
        logger.warning("Ignoring a research notebook that could not be read")
        return Notebook()
```

Then change the last line of `record_turn` from `return book` to:

```python
    return compact(book)
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `PYTHONPATH=. /Users/markdavenport/Development/DeadBot/.venv/bin/python -m pytest -q tests/test_notebook.py tests/test_config.py`
Expected: PASS.

- [ ] **Step 6: Full suite, then commit**

Run: `PYTHONPATH=. /Users/markdavenport/Development/DeadBot/.venv/bin/python -m pytest -q`
Expected: all pass.

```bash
git add deadbot/notebook.py deadbot/config.py .env.example tests/test_notebook.py tests/test_config.py
git commit -m "Sign and size the research notebook, and read its secret from the environment

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 3: Measure conversations, not just questions, and record the baseline

**Files:**
- Modify: `deadbot/turn_metrics.py`
- Modify: `scripts/measure_turns.py`
- Test: `tests/test_turn_metrics.py`, `tests/test_measure_turns.py`
- Create (live run): `docs/measurements/<today>-notebook-before.md`

**Interfaces:**
- Consumes: `composition.NOTEBOOK_MESSAGE_NAME` (Task 1).
- Produces:
  - `turn_metrics(...)` adds `"notebook_reads": int` (count of `read_notebook` results this turn) and `"notebook_index_chars": int` (characters of notebook messages in the input).
  - `scripts.measure_turns.SEQUENCES: dict[str, list[str]]`
  - `measure_sequence(questions: list[str], *, app, use_notebook: bool = True, pause_seconds: float = 0.0) -> list[dict]`; each row adds `turn` and `notebook_bytes` (size of the token sent with that question).
  - `table(rows)` gains `Cached share`, `Notebook reads`, `Notebook index (chars)`, `Notebook sent (bytes)` columns.
  - CLI: `--sequence NAME` (repeatable), `--compare` (each sequence without, then with, the notebook), `--without-notebook`.

This task runs **before** the notebook reaches the API, so its live run is the honest "before": the grid plan merged, no notebook. Run the code part now; run Step 7 after grid Tasks 1–7 merge and before Task 4 merges.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_turn_metrics.py`:

```python
def test_metrics_count_notebook_reads_and_the_notebook_index_size():
    index = HumanMessage(content="Research notebook, turn 1: one line", name="research_notebook")
    messages = [
        HumanMessage(content="earlier"), AIMessage(content="answer"), index,
        HumanMessage(content="Compare the Lyceum nights."),
        AIMessage(content="", tool_calls=[{"name": "read_notebook", "args": {"keys_or_ids": ["k"]}, "id": "n", "type": "tool_call"}],
                  usage_metadata={"input_tokens": 900, "output_tokens": 10, "total_tokens": 910}),
        ToolMessage(content='{"notebook_entries":[]}', tool_call_id="n", name="read_notebook"),
    ]
    metrics = turn_metrics("Compare the Lyceum nights.", messages, started=0.0, first_answer_at=None, finished_at=1.0, error=None)
    assert metrics["notebook_reads"] == 1
    assert metrics["notebook_index_chars"] == len(index.content)
```

In `tests/test_measure_turns.py`, change the import to `from scripts.measure_turns import DEFAULT_QUESTIONS, SEQUENCES, measure, measure_sequence, table`, then append:

```python
class _RecordingAgent(_Agent):
    def __init__(self):
        self.sent = []

    def stream(self, payload, config, stream_mode="values"):
        self.sent.append([message.content for message in payload["messages"]])
        yield from super().stream(payload, config, stream_mode)


def test_a_sequence_is_asked_as_one_conversation():
    agent = _RecordingAgent()
    app = create_app(settings=Settings(response_cache=False), store=CanonicalStore(), agent=agent)
    rows = measure_sequence(["one", "two"], app=app)
    assert [row["turn"] for row in rows] == [1, 2]
    assert agent.sent[1] == ["one", "About one", "two"]
    assert [row["notebook_bytes"] for row in rows] == [0, 0]
    rendered = table(rows)
    assert "Cached share" in rendered.splitlines()[0] and "Notebook reads" in rendered.splitlines()[0]


def test_the_sequences_cover_the_owners_follow_up_path():
    assert SEQUENCES["europe72"][0] == "What's on Europe '72: The Complete Recordings?"
    assert "Lyceum" in SEQUENCES["europe72"][1] and "Morning Dew" in SEQUENCES["europe72"][2]
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `PYTHONPATH=. /Users/markdavenport/Development/DeadBot/.venv/bin/python -m pytest -q tests/test_turn_metrics.py tests/test_measure_turns.py`
Expected: FAIL with `KeyError: 'notebook_reads'` and `ImportError: cannot import name 'SEQUENCES'`.

- [ ] **Step 3: Extend `turn_metrics`**

In `deadbot/turn_metrics.py`, add `from deadbot.composition import NOTEBOOK_MESSAGE_NAME, _content_text`. In `turn_metrics`, before the `return`:

```python
    notebook_chars = sum(
        len(_content_text(message.content))
        for message in messages
        if isinstance(message, HumanMessage) and getattr(message, "name", None) == NOTEBOOK_MESSAGE_NAME
    )
```

and add these keys to the returned dict, after `"largest_tool_result_chars"`:

```python
        "notebook_reads": sum(1 for tool in tools if tool["name"] == "read_notebook"),
        "notebook_index_chars": notebook_chars,
```

Also add one sentence to the module docstring: `Per turn it also counts read_notebook calls and how large the notebook lines in the input were.`

- [ ] **Step 4: Add sequences to `scripts/measure_turns.py`**

Add `import uuid` to the imports. After `DEFAULT_QUESTIONS`:

```python
# Follow-up paths the research notebook is meant to speed up. Each runs as one
# conversation, the way the browser asks it.
SEQUENCES = {
    "europe72": [
        "What's on Europe '72: The Complete Recordings?",
        "Tell me about the last Lyceum night, May 26, 1972.",
        "How does that night's Morning Dew compare with other Morning Dews?",
    ],
    "1979": [
        "Best shows of 1979",
        "Compare the first two shows you picked.",
        "Which songs from those nights would you play someone new to 1979?",
    ],
}
```

After `measure`:

```python
def measure_sequence(
    questions: list[str], *, app: Any, use_notebook: bool = True, pause_seconds: float = 0.0
) -> list[dict[str, Any]]:
    """Ask questions in order as one conversation, sending back what each answer returned."""

    collector = _Collector()
    metrics_logger = logging.getLogger("deadbot.turn_metrics")
    metrics_logger.addHandler(collector)
    client = TestClient(app)
    thread_id = f"measure-{uuid.uuid4()}"
    conversation: list[dict[str, Any]] = []
    token: str | None = None
    rows = []
    try:
        for index, question in enumerate(questions):
            if index and pause_seconds:
                time.sleep(pause_seconds)
            sent = token if use_notebook and token else None
            body: dict[str, Any] = {"question": question, "thread_id": thread_id, "conversation": conversation}
            if sent:
                body["notebook"] = sent
            before = len(collector.lines)
            delivered = None
            with client.stream("POST", "/api/experience/stream", json=body) as response:
                for line in response.iter_lines():
                    if line.strip():
                        event = json.loads(line)
                        if event.get("type") == "response":
                            delivered = event["response"]
            logged = collector.lines[before:]
            row = dict(logged[-1]) if logged else {"question": question, "error": "no metrics logged"}
            row.update(turn=index + 1, notebook_bytes=len(sent or ""))
            rows.append(row)
            if delivered is None:
                break
            conversation = delivered.get("conversation") or []
            token = delivered.get("notebook")
    finally:
        metrics_logger.removeHandler(collector)
    return rows
```

Replace `table`:

```python
def table(rows: list[dict[str, Any]]) -> str:
    header = (
        "| Question | Calls | Research rounds | Peak input | Total input | Cached input | Cached share | Total output | Reasoning | "
        "Notebook reads | Notebook index (chars) | Notebook sent (bytes) | Largest tool result | First answer (s) | Total (s) | Truncated | Error |"
    )
    lines = [header, "|" + "---|" * 17]
    for row in rows:
        truncated = sum(1 for tool in row.get("tools", []) if tool.get("truncated"))
        lines.append(
            f"| {row.get('question', '')} | {row.get('model_calls', '')} | {_cell(row.get('research_rounds'))} | "
            f"{row.get('peak_input_tokens', '')} | {row.get('total_input_tokens', '')} | {_cell(row.get('total_cached_input_tokens'))} | "
            f"{_cell(row.get('cached_input_share'))} | {_cell(row.get('total_output_tokens'))} | {_cell(row.get('total_reasoning_tokens'))} | "
            f"{_cell(row.get('notebook_reads'))} | {_cell(row.get('notebook_index_chars'))} | {_cell(row.get('notebook_bytes'))} | "
            f"{row.get('largest_tool_result_chars', '')} | {row.get('seconds_to_first_answer', '')} | {row.get('seconds_total', '')} | "
            f"{truncated} | {row.get('error') or ''} |"
        )
    return "\n".join(lines)
```

Replace `main`:

```python
def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("questions", nargs="*")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--pause", type=float, default=20.0)
    parser.add_argument("--sequence", action="append", choices=sorted(SEQUENCES), help="ask a follow-up path as one conversation")
    parser.add_argument("--compare", action="store_true", help="run each sequence without, then with, the research notebook")
    parser.add_argument("--without-notebook", action="store_true", help="send no notebook back with follow-ups")
    args = parser.parse_args(argv)

    from deadbot.api import create_app
    from deadbot.config import Settings

    settings = dataclasses.replace(Settings.from_env(), response_cache=False, rate_limit_per_minute=0)
    app = create_app(settings=settings)
    if args.sequence:
        sections = []
        rows = []
        for name in args.sequence:
            for use_notebook in ([False, True] if args.compare else [not args.without_notebook]):
                label = f"{name}, {'with' if use_notebook else 'without'} the notebook"
                found = measure_sequence(SEQUENCES[name], app=app, use_notebook=use_notebook, pause_seconds=args.pause)
                sections.append(f"## {label}\n\n{table(found)}")
                rows.extend({**row, "sequence": label} for row in found)
        rendered = "\n\n".join(sections)
    else:
        rows = measure(args.questions or DEFAULT_QUESTIONS, app=app, pause_seconds=args.pause)
        rendered = table(rows)
    print(rendered)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(
            f"# Turn measurements\n\nModel: {settings.openai_model if settings.model_provider == 'openai' else settings.ollama_model}"
            f" (reasoning effort: {settings.openai_reasoning_effort or 'default'})\n\n{rendered}\n\n"
            "Raw metrics, one JSON object per question:\n\n```json\n" + "\n".join(json.dumps(row) for row in rows) + "\n```\n",
            encoding="utf-8",
        )
```

Update the module docstring with the new usage line:

```
    PYTHONPATH=. .venv/bin/python scripts/measure_turns.py --sequence europe72 --sequence 1979 --compare --output docs/measurements/<date>-notebook-after.md
```

- [ ] **Step 5: Run the tests to verify they pass, then the full suite**

Run: `PYTHONPATH=. /Users/markdavenport/Development/DeadBot/.venv/bin/python -m pytest -q tests/test_turn_metrics.py tests/test_measure_turns.py && PYTHONPATH=. /Users/markdavenport/Development/DeadBot/.venv/bin/python -m pytest -q`
Expected: all pass.

- [ ] **Step 6: Commit the code**

```bash
git add deadbot/turn_metrics.py scripts/measure_turns.py tests/test_turn_metrics.py tests/test_measure_turns.py
git commit -m "Measure follow-up conversations turn by turn, with cache share and notebook use

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

- [ ] **Step 7: Record the live baseline (after grid Tasks 1–7 merge, before Task 4 merges)**

This costs real tokens. The worktree needs the owner's `.env` (gitignored); if it has none, copy it from the main checkout. Use the production model and reasoning effort `low` (see the project memory on reasoning effort).

```bash
test -f .env || cp /Users/markdavenport/Development/DeadBot/.env .env
PYTHONPATH=. DEADBOT_MODEL_PROVIDER=openai DEADBOT_OPENAI_REASONING_EFFORT=low \
  /Users/markdavenport/Development/DeadBot/.venv/bin/python scripts/measure_turns.py \
  --sequence europe72 --sequence 1979 --pause 20 \
  --output docs/measurements/$(date +%F)-notebook-before.md
```

Expected: two tables of three rows each, no `Error` cells. Turns 2 and 3 should show the problem the spec measured: 3–4 calls, tens of thousands of input tokens, 13–20 s to the first answer.

```bash
git add docs/measurements/*-notebook-before.md
git commit -m "Record follow-up cost before the research notebook

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 4: The notebook travels: request, response, response cache and starter answers

Start after grid Tasks 1–7 merge.

**Files:**
- Modify: `deadbot/experience.py` (`NOTEBOOK_TOKEN_MAX_CHARS`, `ExperienceRequest.notebook`, `ExperienceResponse.notebook`)
- Modify: `deadbot/api.py` (`_Invocation`, `_prepare`, `_respond`, `_with_notebook`, `_cached`, `_remember`)
- Modify: `scripts/warm_answers.py`
- Regenerate: `web/openapi.json`, `web/src/generated/api.ts`
- Test: `tests/test_api_notebook.py` (new), `tests/test_response_cache.py`, `tests/test_measure_turns.py`

**Interfaces:**
- Consumes: `notebook.decode`, `notebook.encode`, `notebook.record_turn`, `notebook.note_missing_secret`, `notebook.TOKEN_BYTE_CEILING` (Tasks 1–2); `Settings.notebook_secret`; the grid version of `_prepare`/`_respond`.
- Produces:
  - `experience.NOTEBOOK_TOKEN_MAX_CHARS = 200_000`
  - `ExperienceRequest.notebook: str | None` (max 200,000 chars)
  - `ExperienceResponse.notebook: str | None`
  - `_Invocation.notebook: notebook.Notebook` (default empty)
  - `_with_notebook(invocation, messages, response) -> ExperienceResponse` inside `create_app`
  - Requests that carry a notebook neither read nor fill the response cache.
  - TS: `ExperienceResponse["notebook"]?: string | null` via `gen:types`.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_api_notebook.py`:

```python
import logging

from fastapi.testclient import TestClient

from deadbot import experience, notebook
from deadbot.api import create_app
from deadbot.config import Settings
from notebook_support import LYCEUM, SECRET, record, store, turn
from test_experience import FakeAgent, StreamingFakeAgent, _CachingStore, _ndjson

EUROPE = "What's on Europe '72: The Complete Recordings?"
EUROPE_ANSWER = "Twenty-two nights, every one released."
FIRST_EXCHANGE = [{"role": "user", "text": EUROPE}, {"role": "assistant", "text": EUROPE_ANSWER}]


def _client(agent, *, secret=SECRET, data=None, **settings):
    return TestClient(create_app(settings=Settings(notebook_secret=secret, **settings), store=data or store(), agent=agent))


def _token(*turns):
    book = notebook.Notebook()
    for index, (question, answer, calls) in enumerate(turns):
        book, _ = record(book, question, answer, calls, prefix=f"t{index}")
    return book, notebook.encode(book, SECRET)


def test_an_answer_carries_a_signed_notebook_of_its_research():
    agent = FakeAgent(turn("Tell me about May 26, 1972.", "The last Lyceum night.", LYCEUM))
    body = _client(agent).post("/api/experience", json={"question": "Tell me about May 26, 1972."}).json()
    assert body["notebook"].startswith("v1.")
    book = notebook.decode(body["notebook"], SECRET)
    assert book.turns == 1
    assert [(entry.tool, entry.turn) for entry in book.entries] == [("get_show", 1)]
    assert "gd-1972-05-26" in book.entries[0].ids
    assert book.pages[0].answer_key == notebook.answer_key("The last Lyceum night.")


def test_the_streamed_response_event_carries_the_notebook_too():
    agent = StreamingFakeAgent(turn("Tell me about May 26, 1972.", "The last Lyceum night.", LYCEUM))
    events = _ndjson(_client(agent).post("/api/experience/stream", json={"question": "Tell me about May 26, 1972."}).text)
    assert events[-1]["type"] == "response"
    assert notebook.decode(events[-1]["response"]["notebook"], SECRET).turns == 1


def test_a_follow_up_adds_its_turn_to_the_notebook_it_was_sent():
    first, token = _token((EUROPE, EUROPE_ANSWER, LYCEUM))
    agent = FakeAgent(turn("And Morning Dew?", "It closed the Lyceum run.", [("get_song", {"song_id_or_title": "Morning Dew"})]))
    body = _client(agent).post("/api/experience", json={
        "question": "And Morning Dew?", "thread_id": "browser-1", "conversation": FIRST_EXCHANGE, "notebook": token,
    }).json()
    book = notebook.decode(body["notebook"], SECRET)
    assert book.turns == 2
    assert [(entry.tool, entry.turn) for entry in book.entries] == [("get_show", 1), ("get_song", 2)]


def test_a_tampered_notebook_is_ignored_and_the_visitor_still_gets_an_answer(caplog):
    _, token = _token((EUROPE, EUROPE_ANSWER, LYCEUM))
    tampered = token[:-4] + ("AAAA" if not token.endswith("AAAA") else "BBBB")
    agent = FakeAgent(turn("And Morning Dew?", "It closed the run.", []))
    with caplog.at_level(logging.WARNING, logger="deadbot.notebook"):
        response = _client(agent).post("/api/experience", json={"question": "And Morning Dew?", "conversation": FIRST_EXCHANGE, "notebook": tampered})
    assert response.status_code == 200
    assert notebook.decode(response.json()["notebook"], SECRET).turns == 1
    assert "signature" in caplog.text


def test_without_a_secret_there_is_no_notebook_and_one_log_line(monkeypatch, caplog):
    monkeypatch.setattr(notebook, "_missing_secret_logged", False)
    client = _client(FakeAgent(turn("Q", "A", LYCEUM)), secret=None)
    with caplog.at_level(logging.WARNING, logger="deadbot.notebook"):
        first = client.post("/api/experience", json={"question": "Q"}).json()
        second = client.post("/api/experience", json={"question": "Q"}).json()
    assert first["notebook"] is None and second["notebook"] is None
    assert caplog.text.count("DEADBOT_NOTEBOOK_SECRET is not set") == 1


def test_the_request_ceiling_sits_above_the_token_ceiling():
    assert notebook.TOKEN_BYTE_CEILING < experience.NOTEBOOK_TOKEN_MAX_CHARS
    response = _client(FakeAgent(turn("Q", "A", []))).post("/api/experience", json={"question": "Q", "notebook": "x" * (experience.NOTEBOOK_TOKEN_MAX_CHARS + 1)})
    assert response.status_code == 422


def test_a_cached_starter_answer_carries_its_notebook_and_notebook_requests_skip_the_cache():
    data = _CachingStore()
    agent = FakeAgent(turn(EUROPE, EUROPE_ANSWER, LYCEUM))
    client = _client(agent, data=data)
    live = client.post("/api/experience", json={"question": EUROPE}).json()
    cached = client.post("/api/experience", json={"question": EUROPE}).json()
    assert len(agent.calls) == 1
    assert cached["notebook"] == live["notebook"]
    client.post("/api/experience", json={"question": EUROPE, "notebook": live["notebook"]})
    assert len(agent.calls) == 2
```

Append to `tests/test_response_cache.py`:

```python
def test_an_exported_answer_keeps_its_notebook_through_the_bundle():
    _, cache = _postgres_cache()
    question = "What's on Europe '72: The Complete Recordings?"
    cache.remember(question, ExperienceResponse(thread_id="original", title="Europe '72", answer="Twenty-two nights.", notebook="v1.body.sig"))
    (entry,) = cache.export([question])
    assert entry["response"]["notebook"] == "v1.body.sig"
    _, fresh = _postgres_cache()
    assert fresh.seed([entry]) == 1
    assert fresh.lookup(question, thread_id="new").notebook == "v1.body.sig"
```

(If `_postgres_cache()` builds two caches over separate in-memory databases, as it does today, the seed test proves the bundle path end to end. If the version string differs between the two because of the fixture, set `entry["data_version"] = fresh._version()` before seeding and keep the assertion.)

Append to `tests/test_measure_turns.py`:

```python
def test_a_sequence_sends_back_the_notebook_each_answer_carried():
    app = create_app(settings=Settings(response_cache=False, notebook_secret="s"), store=CanonicalStore(), agent=_Agent())
    rows = measure_sequence(["one", "two"], app=app)
    assert rows[0]["notebook_bytes"] == 0 and rows[1]["notebook_bytes"] > 0
    assert measure_sequence(["one", "two"], app=app, use_notebook=False)[1]["notebook_bytes"] == 0
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `PYTHONPATH=. /Users/markdavenport/Development/DeadBot/.venv/bin/python -m pytest -q tests/test_api_notebook.py tests/test_response_cache.py tests/test_measure_turns.py`
Expected: FAIL (`KeyError: 'notebook'`, 422 on the `notebook` request field, `AttributeError: NOTEBOOK_TOKEN_MAX_CHARS`).

- [ ] **Step 3: Add the fields to `deadbot/experience.py`**

Above `class ExperienceRequest`:

```python
# The longest research-notebook token a request may carry. The server makes
# tokens up to notebook.TOKEN_BYTE_CEILING, which is smaller.
NOTEBOOK_TOKEN_MAX_CHARS = 200_000
```

In `ExperienceRequest`, after the grid's `focus` field:

```python
    notebook: str | None = Field(
        default=None,
        max_length=NOTEBOOK_TOKEN_MAX_CHARS,
        description="The research notebook the previous response returned, sent back unchanged.",
    )
```

In `ExperienceResponse`, after `sources`:

```python
    notebook: str | None = Field(
        default=None,
        description="Signed research notebook: what this conversation's tools found so far. Send it back with the next question.",
    )
```

- [ ] **Step 4: Decode, harvest and encode in `deadbot/api.py`**

Add `from dataclasses import dataclass, field` (replacing the plain `dataclass` import) and `from deadbot import composition, finish, notebook`.

In `_Invocation`, after the last field the grid version has:

```python
    notebook: notebook.Notebook = field(default_factory=notebook.Notebook)  # NEW
```

In `_prepare` (grid version), add the decode as the second line and change the isolated-thread condition and the return:

```python
    def _prepare(request: ExperienceRequest) -> _Invocation:
        thread_id = request.thread_id or f"web-{uuid.uuid4()}"
        book = notebook.decode(request.notebook, app.state.settings.notebook_secret)  # NEW
        # ... the grid version's transcript, question and focus lines, unchanged ...
        invocation_thread_id = (
            f"{thread_id}:request:{uuid.uuid4()}" if request.conversation or book.entries else thread_id  # NEW: `or book.entries`
        )
        return _Invocation(thread_id=thread_id, invocation_thread_id=invocation_thread_id, messages=messages, notebook=book)  # NEW: notebook=book
```

Keep every other argument the grid version passes to `_Invocation`.

Replace `_respond` so it ends through `_with_notebook` (keep the grid version's arguments to `build_experience_response` exactly):

```python
    def _with_notebook(invocation: _Invocation, messages: list[Any], response: ExperienceResponse) -> ExperienceResponse:
        """The response plus the signed notebook the browser sends back with the next question."""

        secret = app.state.settings.notebook_secret
        if not secret:
            notebook.note_missing_secret()
            return response
        try:
            book = notebook.record_turn(invocation.notebook, composition._latest_turn(list(messages)), response)
            token = notebook.encode(book, secret)
        except Exception:  # The answer matters more than its notebook.
            logger.exception("The research notebook could not be saved; the answer goes out without it")
            return response
        return response.model_copy(update={"notebook": token})

    def _respond(request: ExperienceRequest, invocation: _Invocation, messages: list[Any]) -> ExperienceResponse:
        response = build_experience_response(
            question=request.question,
            thread_id=invocation.thread_id,
            messages=messages,
            store=app.state.store,
            # ... plus any argument the grid version added ...
        )
        return _with_notebook(invocation, messages, response)  # NEW
```

Change `_cached` and `_remember` so a request carrying a notebook is a follow-up in a session (its answer may lean on earlier research, so it is neither served from nor stored as a fresh answer):

```python
    def _cached(request: ExperienceRequest, invocation: _Invocation) -> ExperienceResponse | None:
        """A stored answer for a fresh (no-conversation, no-notebook) repeat of a question."""

        if request.conversation or request.notebook:
            return None
        return app.state.response_cache.lookup(request.question, thread_id=invocation.thread_id)

    def _remember(request: ExperienceRequest, response: ExperienceResponse) -> None:
        if not request.conversation and not request.notebook:
            app.state.response_cache.remember(request.question, response)
```

A cached starter answer already carries its notebook: the cache stores the whole `response.model_dump`, and `lookup` revalidates it. Nothing else is needed for warm answers to bring their research.

- [ ] **Step 5: Report notebooks in `scripts/warm_answers.py`**

In `build_bundle`, after the `OPENAI_API_KEY` check:

```python
    if not settings.notebook_secret:
        print("warm answers: DEADBOT_NOTEBOOK_SECRET is not set; the answers ship without research notebooks")
```

Replace the final `print` with:

```python
    carried = sum(1 for entry in entries if isinstance(entry.get("response"), dict) and entry["response"].get("notebook"))
    print(f"warm answers: wrote {len(entries)} of {len(questions)} to {path} ({sum(done)} answered, {carried} with a research notebook)")
```

Update the module docstring's first paragraph with one sentence: `Each answer carries its research notebook when DEADBOT_NOTEBOOK_SECRET is set at build time, so the first follow-up starts from that research.`

- [ ] **Step 6: Regenerate the browser types**

```bash
PYTHONPATH=. /Users/markdavenport/Development/DeadBot/.venv/bin/python scripts/export_openapi.py
npm run gen:types --prefix web
```

Expected: `web/openapi.json` and `web/src/generated/api.ts` gain `notebook` on both `ExperienceRequest` and `ExperienceResponse`.

- [ ] **Step 7: Run the tests, the full suites and the build**

```bash
PYTHONPATH=. /Users/markdavenport/Development/DeadBot/.venv/bin/python -m pytest -q tests/test_api_notebook.py tests/test_response_cache.py tests/test_measure_turns.py
PYTHONPATH=. /Users/markdavenport/Development/DeadBot/.venv/bin/python -m pytest -q
npm test --prefix web
npm run build --prefix web
```

Expected: all pass.

- [ ] **Step 8: Commit**

```bash
git add deadbot/experience.py deadbot/api.py scripts/warm_answers.py web/openapi.json web/src/generated/api.ts tests/test_api_notebook.py tests/test_response_cache.py tests/test_measure_turns.py
git commit -m "Carry a signed research notebook on each response and accept it on the next request

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

- [ ] **Step 9: Ask the owner to set the secret on Vercel**

Tell the owner, in plain words: the notebook needs one secret value in Vercel for Production and Preview (it must be present at build time too, so starter answers ship with their notebooks). Give the commands to run from the repository root:

```bash
python3 -c "import secrets; print(secrets.token_urlsafe(32))"
vercel env add DEADBOT_NOTEBOOK_SECRET production
vercel env add DEADBOT_NOTEBOOK_SECRET preview
```

Until it is set, deploys behave exactly as today and log the missing-secret line once per instance.

---

### Task 5: What the model sees: notebook lines in the transcript, focus flags, and the cache key

**Files:**
- Modify: `deadbot/api.py` (`_prepare`, `_run_config`, both `run_config` call sites)
- Modify: `deadbot/finish.py` (`_conversation`)
- Modify: `deadbot/graph.py` (`run_config`, `_cache_options`, `call_model`)
- Test: `tests/test_api_notebook.py`, `tests/test_graph.py`

**Interfaces:**
- Consumes: `notebook.transcript_with_notebook`, `notebook.entries_mentioning`, `notebook.render_flags`, `notebook.notebook_message`, `composition.NOTEBOOK_MESSAGE_NAME`; grid `request.focus.ids`.
- Produces:
  - `graph.run_config(thread_id: str, settings: Settings, *, notebook: Any = None, prompt_cache_key: str | None = None) -> dict`; `configurable` carries `notebook` and `prompt_cache_key` when given.
  - `graph._cache_options(config) -> dict[str, str]`
  - `_run_config(invocation: _Invocation) -> dict` inside `create_app`.
  - Model input order: `[earlier-turns message?] [user, assistant, turn-N notebook message]... [focus flags message?] [question]`.

- [ ] **Step 1: Write the failing tests**

Add to the imports at the top of `tests/test_api_notebook.py`:

```python
from langchain_core.messages import AIMessage, HumanMessage

from deadbot import composition
from deadbot.finish import build_experience_response
```

Then append:

```python
def test_each_turns_research_follows_its_answer_and_the_question_comes_last():
    book, token = _token((EUROPE, EUROPE_ANSWER, LYCEUM))
    agent = FakeAgent(turn("Compare the Lyceum nights.", "Four nights.", []))
    _client(agent).post("/api/experience", json={
        "question": "Compare the Lyceum nights.", "thread_id": "browser-1", "conversation": FIRST_EXCHANGE, "notebook": token,
    })
    sent = agent.calls[0][0]["messages"]
    assert [message.type for message in sent] == ["human", "ai", "human", "human"]
    assert sent[2].name == composition.NOTEBOOK_MESSAGE_NAME
    assert sent[2].content.startswith("Research notebook, turn 1:")
    assert f"[{book.entries[0].key}] get_show gd-1972-05-26" in sent[2].content
    assert sent[3].content == "Compare the Lyceum nights."


def test_a_new_turn_leaves_every_earlier_message_byte_identical():
    first, first_token = _token((EUROPE, EUROPE_ANSWER, LYCEUM))
    second, _ = record(first, "Tell me about May 26.", "The last Lyceum night.", [("get_song", {"song_id_or_title": "Morning Dew"})], prefix="t1")
    second_token = notebook.encode(second, SECRET)
    agent_one = FakeAgent(turn("Tell me about May 26.", "The last Lyceum night.", []))
    _client(agent_one).post("/api/experience", json={"question": "Tell me about May 26.", "conversation": FIRST_EXCHANGE, "notebook": first_token})
    agent_two = FakeAgent(turn("And its Morning Dew?", "Out of The Other One.", []))
    two_exchanges = FIRST_EXCHANGE + [{"role": "user", "text": "Tell me about May 26."}, {"role": "assistant", "text": "The last Lyceum night."}]
    _client(agent_two).post("/api/experience", json={"question": "And its Morning Dew?", "conversation": two_exchanges, "notebook": second_token})
    one = [message.content for message in agent_one.calls[0][0]["messages"]][:-1]
    two = [message.content for message in agent_two.calls[0][0]["messages"]]
    assert two[: len(one)] == one
    assert two[len(one) + 2].startswith("Research notebook, turn 2:")


def test_a_click_on_something_already_researched_is_flagged_before_the_question():
    book, token = _token((EUROPE, EUROPE_ANSWER, LYCEUM))
    agent = FakeAgent(turn("Tell me about the Morning Dew from May 26, 1972.", "Out of The Other One.", []))
    _client(agent).post("/api/experience", json={
        "question": "Tell me about the Morning Dew from May 26, 1972.",
        "conversation": FIRST_EXCHANGE,
        "notebook": token,
        "focus": {"label": "Morning Dew · May 26, 1972", "block_type": "grid", "block_id": "grid:abc",
                  "ids": ["gd-1972-05-26", "song-morning-dew"], "facts": []},
    })
    sent = agent.calls[0][0]["messages"]
    assert sent[-2].name == composition.NOTEBOOK_MESSAGE_NAME
    assert sent[-2].content.startswith("Already in the research notebook for what the visitor clicked:")
    assert book.entries[0].key in sent[-2].content
    assert sent[-1].content.startswith("Tell me about the Morning Dew from May 26, 1972.")


def test_a_notebook_without_a_transcript_still_gets_its_own_invocation_thread_and_the_cache_key():
    _, token = _token((EUROPE, EUROPE_ANSWER, LYCEUM))
    agent = FakeAgent(turn("Q", "A", []))
    _client(agent).post("/api/experience", json={"question": "Q", "thread_id": "browser-1", "notebook": token})
    config = agent.calls[0][1]
    assert config["configurable"]["thread_id"].startswith("browser-1:request:")
    assert config["configurable"]["prompt_cache_key"] == "browser-1"
    assert isinstance(config["configurable"]["notebook"], notebook.Notebook)


def test_notebook_messages_stay_out_of_the_visible_conversation():
    messages = [
        HumanMessage(content="q1"), AIMessage(content="a1"),
        notebook.notebook_message("Research notebook, turn 1: what the tools returned"),
        *turn("q2", "a2", []),
    ]
    response = build_experience_response("q2", "t", messages, store())
    assert [item.text for item in response.conversation] == ["q1", "a1", "q2", "a2"]
```

Append to `tests/test_graph.py` (add `HumanMessage` is already imported there):

```python
_SEEN_KWARGS: list[dict] = []


class _RecordingFakeChatModel(_BindableFakeChatModel):
    def _generate(self, messages, stop=None, run_manager=None, **kwargs):
        _SEEN_KWARGS.append(dict(kwargs))
        return super()._generate(messages, stop=stop, run_manager=run_manager, **kwargs)


def _model_kwargs_for_one_call(settings):
    class FakeProvider:
        def create_chat_model(self):
            return _RecordingFakeChatModel(responses=[AIMessage(content="hi")])

    compiled = graph.build_agent(settings, store=CanonicalStore(), provider=FakeProvider())
    _SEEN_KWARGS.clear()
    compiled.invoke(
        {"messages": [HumanMessage(content="hello")]},
        graph.run_config("web-1:request:x", settings, prompt_cache_key="web-1"),
    )
    return _SEEN_KWARGS[-1]


def test_openai_calls_carry_the_conversation_as_the_prompt_cache_key():
    assert _model_kwargs_for_one_call(Settings(model_provider="openai"))["prompt_cache_key"] == "web-1"


def test_other_providers_get_no_prompt_cache_key():
    assert "prompt_cache_key" not in _model_kwargs_for_one_call(Settings())


def test_run_config_carries_the_notebook_only_when_given():
    assert "notebook" not in graph.run_config("t", Settings())["configurable"]
    assert graph.run_config("t", Settings(), notebook="book")["configurable"]["notebook"] == "book"
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `PYTHONPATH=. /Users/markdavenport/Development/DeadBot/.venv/bin/python -m pytest -q tests/test_api_notebook.py tests/test_graph.py`
Expected: FAIL (message types are `["human", "ai", "human"]`; `run_config()` got an unexpected keyword argument).

- [ ] **Step 3: `run_config` and the cache key in `deadbot/graph.py`**

Add `from typing import Any` and `from langchain_core.runnables import RunnableConfig`. Replace `run_config`:

```python
def run_config(thread_id: str, settings: Settings, *, notebook: Any = None, prompt_cache_key: str | None = None) -> dict:
    """The session's checkpoint thread, its research notebook and cache key, and a bound on agent iterations."""

    configurable: dict[str, Any] = {"thread_id": thread_id}
    if notebook is not None:
        # read_notebook finds it here, so its schema stays the same on every call.
        configurable["notebook"] = notebook
    if prompt_cache_key:
        configurable["prompt_cache_key"] = prompt_cache_key
    # Each research round costs two graph steps (agent, tools). The extra pair
    # beyond the rounds themselves reserves room to finish: one for the
    # ``finish_response`` call, and one more so a call whose arguments failed
    # validation can be corrected instead of the turn dying mid-answer.
    return {"configurable": configurable, "recursion_limit": settings.max_tool_rounds * 2 + 4}
```

Above `build_agent`:

```python
def _cache_options(config: RunnableConfig | None) -> dict[str, str]:
    """Route a conversation's calls to the same provider cache (OpenAI's prompt_cache_key)."""

    key = ((config or {}).get("configurable") or {}).get("prompt_cache_key")
    return {"prompt_cache_key": str(key)[:64]} if key else {}
```

In `build_agent`, before `def call_model`, add `routes_cache = settings.model_provider == "openai"`, and change `call_model` to:

```python
    def call_model(state: MessagesState, config: RunnableConfig):
        prompt = [SystemMessage(content=SYSTEM_PROMPT), *state["messages"]]
        options = _cache_options(config) if routes_cache else {}
        if not settings.model_streaming:
            return {"messages": [model.invoke(prompt, **options)]}
        # Streamed, the finish_response arguments arrive as raw JSON text. The
        # model sometimes writes the "groups" key twice; a plain JSON parse
        # keeps only the last one and the page loses everything before it,
        # while the visitor already watched it stream. Read the raw text so
        # repeated lists join, the way the streamed draft shows them.
        full: AIMessageChunk | None = None
        for chunk in model.stream(prompt, **options):
            full = chunk if full is None else full + chunk
        if full is None:
            return {"messages": [model.invoke(prompt, **options)]}
        return {"messages": [repair_finish_arguments(full)]}
```

- [ ] **Step 4: Notebook lines and flags in `_prepare`; one `_run_config`**

In `deadbot/api.py`, replace the grid version's transcript construction with the notebook transcript, and add the flags message before the final question. The final question message (the question plus the grid's focus block) stays exactly as the grid version builds it; below it is called `question_message`:

```python
    def _prepare(request: ExperienceRequest) -> _Invocation:
        thread_id = request.thread_id or f"web-{uuid.uuid4()}"
        book = notebook.decode(request.notebook, app.state.settings.notebook_secret)
        conversation = _trimmed_conversation(request.conversation, app.state.settings.conversation_window)
        # NEW: each earlier turn's notebook lines sit right after that turn's
        # answer, so a new turn only appends and the provider's prompt cache
        # keeps everything before the new question.
        messages = notebook.transcript_with_notebook(book, conversation)
        if request.focus is not None:  # NEW
            flags = notebook.render_flags(notebook.entries_mentioning(book, request.focus.ids))
            if flags:
                messages.append(notebook.notebook_message(flags))
        messages.append(question_message)  # the grid version's final HumanMessage, unchanged
        # ... the grid version's invocation thread and return, as changed in Task 4 ...
```

Inside `create_app`, after `_release`:

```python
    def _run_config(invocation: _Invocation) -> dict:
        return run_config(
            invocation.invocation_thread_id,
            app.state.settings,
            notebook=invocation.notebook,
            prompt_cache_key=invocation.thread_id,
        )
```

Replace both `run_config(invocation.invocation_thread_id, app.state.settings)` calls (in `experience` and in `_stream_events`) with `_run_config(invocation)`.

- [ ] **Step 5: Keep notebook messages out of the visible conversation**

In `deadbot/finish.py` `_conversation`, first line inside the `for message in all_messages:` loop:

```python
        if getattr(message, "type", None) == "human" and getattr(message, "name", None) == composition.NOTEBOOK_MESSAGE_NAME:
            continue
```

- [ ] **Step 6: Run the tests and the full suite**

```bash
PYTHONPATH=. /Users/markdavenport/Development/DeadBot/.venv/bin/python -m pytest -q tests/test_api_notebook.py tests/test_graph.py
PYTHONPATH=. /Users/markdavenport/Development/DeadBot/.venv/bin/python -m pytest -q
```

Expected: all pass, including `test_api_replays_browser_conversation_for_stateless_follow_up` (no notebook means the same three messages as before).

- [ ] **Step 7: Commit**

```bash
git add deadbot/api.py deadbot/finish.py deadbot/graph.py tests/test_api_notebook.py tests/test_graph.py
git commit -m "Show the model each earlier turn's research after that turn's answer, and route a conversation to one prompt cache

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 6: `read_notebook`: earlier results back in full

**Files:**
- Modify: `deadbot/tools.py` (end of `build_tools`)
- Modify: `deadbot/composition.py` (`_tool_payloads`)
- Modify: `deadbot/progress.py` (`describe_tool_call`)
- Test: `tests/test_read_notebook.py` (new), `tests/test_progress.py`

**Interfaces:**
- Consumes: `notebook.Notebook`, `notebook.Entry`, `notebook.find` (Task 1); `config["configurable"]["notebook"]` (Task 5).
- Produces:
  - Tool `read_notebook(keys_or_ids: list[str])`; its model-facing schema has only `keys_or_ids`. Result: `{"notebook_entries": [{"key", "tool", "args", "result"}], "missing": [...]}` through `_json` (80,000-character ceiling).
  - `composition._tool_payloads` returns each `notebook_entries[].result` dict as a payload after the wrapper, so grounding, `from_result`, `aggregation_id`, `selection_id` and source naming work unchanged.
  - `describe_tool_call("read_notebook", ...) == "Going back over earlier research"`.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_read_notebook.py`:

```python
import json

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from deadbot import composition, notebook
from deadbot.finish import build_experience_response
from deadbot.tools import build_tools
from notebook_support import LYCEUM, finish_messages, record, store, tools

PAGE = {"state": "ok", "url": "https://www.example.org/lyceum", "title": "Four nights at the Lyceum", "text": "London, May 1972."}


def _read_tool(**kwargs):
    return {item.name: item for item in build_tools(store(), **kwargs)}["read_notebook"]


def _read(book, wanted, **kwargs):
    return json.loads(_read_tool(**kwargs).invoke({"keys_or_ids": wanted}, config={"configurable": {"notebook": book}}))


def test_read_notebook_shows_the_model_only_its_keys():
    assert list(_read_tool().tool_call_schema.model_json_schema()["properties"]) == ["keys_or_ids"]


def test_a_canonical_entry_is_run_again_and_comes_back_exactly():
    book, _ = record(notebook.Notebook(), "Q", "A", LYCEUM)
    key = book.entries[0].key
    result = _read(book, [key])
    assert result["missing"] == []
    (entry,) = result["notebook_entries"]
    assert (entry["key"], entry["tool"]) == (key, "get_show")
    assert entry["result"] == json.loads(tools()["get_show"].invoke({"show_id_or_date": "1972-05-26"}))


def test_a_web_entry_comes_back_from_its_stored_payload_without_the_network():
    class NoNetwork:
        def read(self, *args, **kwargs):
            raise AssertionError("read_page ran again")

    entry = notebook.Entry(
        key="abc123def0", tool="read_page", args={"url": PAGE["url"]}, ids=[], urls=[PAGE["url"]],
        summary="read_page example.org/lyceum · ~10 tok", tokens=10, turn=1, last_read=1, payload=PAGE,
    )
    result = _read(notebook.Notebook(turns=1, entries=[entry]), ["abc123def0"], page_reader=NoNetwork())
    assert result["notebook_entries"][0]["result"] == PAGE


def test_arguments_and_ids_find_entries_and_unknown_ones_are_listed_missing():
    book, _ = record(notebook.Notebook(), "Q", "A", LYCEUM)
    result = _read(book, ["1972-05-26", "gd-1972-05-26-promised-land-1-1", "nope"])
    assert [entry["tool"] for entry in result["notebook_entries"]] == ["get_show"]
    assert result["missing"] == ["nope"]


def test_an_empty_notebook_says_so():
    result = _read(notebook.Notebook(), ["anything"])
    assert result["notebook_entries"] == [] and result["missing"] == ["anything"]


def test_a_chart_can_be_placed_from_an_aggregation_read_back_from_the_notebook():
    args = {"dataset": "performances", "group_by": "year", "measure": "count", "song_id": "song-morning-dew"}
    book, _ = record(notebook.Notebook(), "How often was Morning Dew played?", "282 times.", [("aggregate_data", args)])
    key = book.entries[0].key
    aggregation_id = json.loads(tools()["aggregate_data"].invoke(args))["aggregation_id"]
    read = _read_tool().invoke({"keys_or_ids": [key]}, config={"configurable": {"notebook": book}})
    messages = [
        HumanMessage(content="Chart it by year."),
        AIMessage(content="", tool_calls=[{"name": "read_notebook", "args": {"keys_or_ids": [key]}, "id": "r1", "type": "tool_call"}]),
        ToolMessage(content=read, tool_call_id="r1", name="read_notebook"),
        *finish_messages("By year.", items=[{"type": "data_chart", "aggregation_id": aggregation_id}]),
    ]
    assert any(payload.get("aggregation_id") == aggregation_id for payload in composition._tool_payloads(messages))
    response = build_experience_response("Chart it by year.", "t", messages, store())
    assert [block.type for block in response.blocks] == ["data_chart"]
```

Append to `tests/test_progress.py`:

```python
def test_reading_the_notebook_has_a_status_line():
    assert progress.describe_tool_call("read_notebook", {"keys_or_ids": ["k"]}) == "Going back over earlier research"
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `PYTHONPATH=. /Users/markdavenport/Development/DeadBot/.venv/bin/python -m pytest -q tests/test_read_notebook.py tests/test_progress.py`
Expected: FAIL with `KeyError: 'read_notebook'` and the status line reading `Read notebook`.

- [ ] **Step 3: Add the tool**

In `deadbot/tools.py`, add `from langchain_core.runnables import RunnableConfig` and change `from deadbot import aggregation, sequences` to `from deadbot import aggregation, notebook, sequences`. At the end of `build_tools`, after the `query_catalog` block and before `return tools`:

```python
    replayable = {item.name: item for item in tools}

    def _notebook_result(entry: notebook.Entry) -> dict[str, Any]:
        """A stored web payload, or the canonical call run again against the library."""

        if entry.payload is not None:
            return entry.payload
        original = replayable.get(entry.tool)
        if original is None:
            return {"error": "That tool is no longer available", "tool": entry.tool}
        try:
            result = json.loads(original.invoke(entry.args))
        except Exception as error:  # A replay that fails must not end the turn.
            return {"error": "Could not run that call again", "detail": str(error)[:300]}
        return result if isinstance(result, dict) else {"result": result}

    @tool
    def read_notebook(keys_or_ids: list[str], config: RunnableConfig) -> str:
        """Bring earlier research back in full: the results of calls listed in the research notebook.

        Pass the bracketed keys from the notebook's lines, or library IDs and
        arguments (a show_id, song_id, performance_id, aggregation_id,
        result_id or date) to get the entries that hold them. Several keys in
        one call come back together. Each result is what the original call
        returned, run again against the library, so its IDs, aggregation_id
        and result_id can go on the page.
        """
        book = ((config or {}).get("configurable") or {}).get("notebook")
        if not isinstance(book, notebook.Notebook) or not book.entries:
            return _json({"notebook_entries": [], "missing": list(keys_or_ids), "note": "The research notebook is empty for this conversation."})
        found, missing = notebook.find(book, keys_or_ids)
        return _json({
            "notebook_entries": [
                {"key": entry.key, "tool": entry.tool, "args": entry.args, "result": _notebook_result(entry)} for entry in found
            ],
            "missing": missing,
        })

    tools.append(read_notebook)
```

- [ ] **Step 4: Count read results as payloads**

In `deadbot/composition.py` `_tool_payloads`, replace:

```python
        if isinstance(payload, dict):
            payloads.append(payload)
```

with:

```python
        if isinstance(payload, dict):
            payloads.append(payload)
            # read_notebook brings earlier results back inside one message;
            # each result counts as if its tool had run this turn.
            entries = payload.get("notebook_entries")
            for entry in entries if isinstance(entries, list) else []:
                result = entry.get("result") if isinstance(entry, dict) else None
                if isinstance(result, dict):
                    payloads.append(result)
```

- [ ] **Step 5: Status line**

In `deadbot/progress.py` `describe_tool_call`, after the `FINISH_TOOL_NAME` branch:

```python
    if name == "read_notebook":
        return "Going back over earlier research"
```

- [ ] **Step 6: Run the tests and the full suite**

```bash
PYTHONPATH=. /Users/markdavenport/Development/DeadBot/.venv/bin/python -m pytest -q tests/test_read_notebook.py tests/test_progress.py
PYTHONPATH=. /Users/markdavenport/Development/DeadBot/.venv/bin/python -m pytest -q
```

Expected: all pass. If a test counts the registered tools (for example in `tests/test_research_tools.py`), add `read_notebook` to its expected list.

- [ ] **Step 7: Commit**

```bash
git add deadbot/tools.py deadbot/composition.py deadbot/progress.py tests/test_read_notebook.py tests/test_progress.py
git commit -m "Add read_notebook, which brings earlier results back by replaying canonical calls and returning stored web pages

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 7: Ground notebook IDs, and tell the model about the notebook

**Files:**
- Modify: `deadbot/finish.py` (`merge_grounding`, `build_experience_response(..., extra_grounding=)`, finish tool description)
- Modify: `deadbot/api.py` (`_turn_grounding`; `_respond`; the PlanStreamer grounding in `_stream_events`)
- Modify: `deadbot/graph.py` (`SYSTEM_PROMPT`)
- Test: `tests/test_api_notebook.py`, `tests/test_graph.py`

**Interfaces:**
- Consumes: `notebook.grounding(book) -> (ids, urls)`; grid Task 7's focus-ID helper (`api_focus_ids(store, ids) -> set[str]`).
- Produces:
  - `finish.merge_grounding(*contexts: GroundedContext) -> GroundedContext`
  - `finish.build_experience_response(question, thread_id, messages, store, *, extra_grounding: GroundedContext | None = None)`
  - `_turn_grounding(request, invocation) -> finish.GroundedContext` in `create_app`: notebook IDs and URLs plus the grid's resolved focus IDs. This is the one place extra grounding is assembled; grid Task 7's direct focus-ID union in `_respond` and `_stream_events` moves into it.

- [ ] **Step 1: Write the failing tests**

Add to the imports at the top of `tests/test_api_notebook.py` (merge with the existing `deadbot.finish`, `notebook_support` and `test_experience` imports):

```python
from deadbot.finish import build_finish_tool
from notebook_support import plan_for
from test_experience import PlanStreamingFakeAgent
```

Then append:

```python
SHOW_ITEM = {"type": "show_unit", "show_id": "gd-1972-05-26", "visible_facets": ["setlist"]}


def test_a_show_researched_in_an_earlier_turn_can_go_on_the_page_by_its_id():
    _, token = _token((EUROPE, EUROPE_ANSWER, LYCEUM))
    request = {"question": "Show me the last Lyceum night.", "conversation": FIRST_EXCHANGE}
    with_notebook = _client(FakeAgent(turn(request["question"], "Here it is.", [], items=[SHOW_ITEM]))).post(
        "/api/experience", json={**request, "notebook": token}).json()
    assert [block["type"] for block in with_notebook["blocks"]] == ["show_unit"]
    assert with_notebook["blocks"][0]["sets"]
    without = _client(FakeAgent(turn(request["question"], "Here it is.", [], items=[SHOW_ITEM]))).post(
        "/api/experience", json=request).json()
    assert "show_unit" not in [block["type"] for block in without["blocks"]]


def test_the_streamed_page_grounds_notebook_ids_the_same_way():
    _, token = _token((EUROPE, EUROPE_ANSWER, LYCEUM))
    question = "Show me the last Lyceum night."
    agent = PlanStreamingFakeAgent(turn(question, "Here it is.", [], items=[SHOW_ITEM]), plan_for("Here it is.", [SHOW_ITEM]))
    events = _ndjson(_client(agent).post("/api/experience/stream", json={"question": question, "conversation": FIRST_EXCHANGE, "notebook": token}).text)
    assert [event["block"]["type"] for event in events if event["type"] == "block"] == ["show_unit"]
    assert events[-1]["response"]["blocks"][0]["type"] == "show_unit"


def test_the_finish_tool_names_the_notebook_as_a_source_of_ids():
    assert "research notebook" in build_finish_tool().description
```

Append to `tests/test_graph.py`:

```python
def test_prompt_teaches_the_research_notebook():
    prompt = " ".join(graph.SYSTEM_PROMPT.split())
    assert "research notebook" in prompt
    assert "read_notebook" in prompt
    assert "tool results of this turn or the research notebook" in prompt
    assert "do not" not in prompt.casefold()
    assert prompt.count("this turn") == 1
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `PYTHONPATH=. /Users/markdavenport/Development/DeadBot/.venv/bin/python -m pytest -q tests/test_api_notebook.py tests/test_graph.py`
Expected: FAIL (the show_unit is not placed; the prompt has no notebook paragraph).

- [ ] **Step 3: `merge_grounding` and `extra_grounding` in `deadbot/finish.py`**

After `grounded_context`:

```python
def merge_grounding(*contexts: GroundedContext) -> GroundedContext:
    """IDs and URLs from several sources: this turn's tools, the research notebook, what the visitor clicked."""

    return GroundedContext(
        ids=frozenset().union(*(context.ids for context in contexts)),
        urls=frozenset().union(*(context.urls for context in contexts)),
    )
```

Change the signature of `build_experience_response` to add a keyword-only parameter (fold in any focus parameter grid Task 7 added, so there is one):

```python
def build_experience_response(
    question: str,
    thread_id: str,
    messages: Iterable[Any],
    store: CanonicalStore,
    *,
    extra_grounding: GroundedContext | None = None,
) -> ExperienceResponse:
```

and replace `grounded = grounded_context(payloads)` with:

```python
    grounded = grounded_context(payloads)
    if extra_grounding is not None:
        grounded = merge_grounding(grounded, extra_grounding)
```

In `build_finish_tool`'s description, change `Every ID and URL in the plan must have appeared in a tool result this turn:` to `Every ID and URL in the plan must have appeared in a tool result this turn or in the research notebook:`.

- [ ] **Step 4: `_turn_grounding` in `deadbot/api.py`**

Inside `create_app`, after `_run_config`:

```python
    def _turn_grounding(request: ExperienceRequest, invocation: _Invocation) -> finish.GroundedContext:
        """IDs and URLs this turn may use beyond its own tool results: the notebook and what was clicked."""

        ids, urls = notebook.grounding(invocation.notebook)
        if request.focus is not None:
            ids = ids | frozenset(api_focus_ids(app.state.store, request.focus.ids))
        return finish.GroundedContext(ids=frozenset(ids), urls=urls)
```

(`api_focus_ids` is grid Task 7's helper; call it by the name and location that task gave it.)

In `_respond`, pass `extra_grounding=_turn_grounding(request, invocation)` to `build_experience_response` (replacing the grid's focus argument if it added one). In `_stream_events`, replace the PlanStreamer grounding line:

```python
                                grounded = finish.merge_grounding(
                                    finish.grounded_context(payloads), _turn_grounding(request, invocation)
                                )
```

(removing the grid's separate focus union there, which `_turn_grounding` now covers).

- [ ] **Step 5: The prompt**

In `deadbot/graph.py` `SYSTEM_PROMPT`, after the paragraph that begins `Work like a researcher.` and before `Well-worn routes.`, add:

```
Follow-ups build on what earlier turns found. When the conversation has a
research notebook, it lists every call earlier turns made, one line each
with its key, and the page the visitor saw. Answer from those lines when they
hold what the answer needs. Call read_notebook with the keys or IDs this
answer will use to bring those results back in full, alongside any new
lookups in the same round. Research what is new or missing as you would for
a first question. A show, song, performance or release listed in the notebook
can go on the page by its ID.
```

In `# TRUST AND VOICE`, change the first sentence to:

```
Ground every fact, ID and URL in the tool results of this turn or the research
notebook; the server checks every ID and link against them.
```

- [ ] **Step 6: Run the tests and the full suite**

```bash
PYTHONPATH=. /Users/markdavenport/Development/DeadBot/.venv/bin/python -m pytest -q tests/test_api_notebook.py tests/test_graph.py
PYTHONPATH=. /Users/markdavenport/Development/DeadBot/.venv/bin/python -m pytest -q
```

Expected: all pass, including the grid's focus-grounding test (it now runs through `_turn_grounding`).

- [ ] **Step 7: Commit**

```bash
git add deadbot/finish.py deadbot/api.py deadbot/graph.py tests/test_api_notebook.py tests/test_graph.py
git commit -m "Let notebook IDs ground the page, and tell the model to look in the notebook first

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 8: The browser holds the notebook

**Files:**
- Create: `web/src/research-notebook.ts`
- Modify: `web/src/App.tsx` (state next to `activeThreadId` ~line 1994; `askQuestion` ~2142, its request body ~2176 in the grid version; `startNewChat` ~2293)
- Test: `web/src/research-notebook.test.ts` (new), `web/src/App.notebook.test.tsx` (new)

**Interfaces:**
- Consumes: `ExperienceResponse.notebook?: string | null` (generated in Task 4); the grid version's `askQuestion(nextQuestion?, { fresh }, focus?)` signature and body.
- Produces: `readStoredNotebook(): string | null`, `storeNotebook(token: string | null | undefined): void`, `clearStoredNotebook(): void`; sessionStorage key `deadbot-research-notebook`.

Behavior: the token lives in React state and in sessionStorage, so it lasts as long as the tab's session (a reload keeps it). A follow-up sends it; a fresh start (starter chip with `fresh: true`, or "New chat") clears it and sends none. Each successful answer replaces it; a failed turn keeps the last one.

- [ ] **Step 1: Write the failing tests**

Create `web/src/research-notebook.test.ts`:

```ts
import { afterEach, expect, test, vi } from "vitest";
import { clearStoredNotebook, readStoredNotebook, storeNotebook } from "./research-notebook";

afterEach(() => {
  vi.restoreAllMocks();
  window.sessionStorage.clear();
});

test("a stored notebook comes back for the tab, and clearing it forgets it", () => {
  storeNotebook("v1.body.sig");
  expect(readStoredNotebook()).toBe("v1.body.sig");
  clearStoredNotebook();
  expect(readStoredNotebook()).toBeNull();
});

test("an answer without a notebook clears the stored one", () => {
  storeNotebook("v1.body.sig");
  storeNotebook(undefined);
  expect(readStoredNotebook()).toBeNull();
});

test("blocked or full storage is ignored", () => {
  vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => {
    throw new DOMException("blocked", "SecurityError");
  });
  vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {
    throw new DOMException("full", "QuotaExceededError");
  });
  expect(() => storeNotebook("v1.body.sig")).not.toThrow();
  expect(() => clearStoredNotebook()).not.toThrow();
  expect(readStoredNotebook()).toBeNull();
});
```

Create `web/src/App.notebook.test.tsx`:

```tsx
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeAll, beforeEach, expect, test, vi } from "vitest";

type Turn = { role: "user" | "assistant"; text: string };

function reply(title: string, notebook: string, conversation: Turn[]) {
  return {
    schema_version: "2", thread_id: "web-test", title, answer: conversation[conversation.length - 1].text,
    body_lead: null, mode: "answer", conversation, blocks: [], groups: [], sources: [], notebook
  };
}

const sent: Record<string, unknown>[] = [];

beforeAll(() => {
  window.matchMedia = ((query: string) => ({
    matches: false, media: query, onchange: null,
    addListener() {}, removeListener() {}, addEventListener() {}, removeEventListener() {}, dispatchEvent: () => false
  })) as typeof window.matchMedia;
  Element.prototype.scrollIntoView = function scrollIntoView() {};
  Element.prototype.scrollTo = function scrollTo() {} as typeof Element.prototype.scrollTo;
  window.scrollTo = (() => {}) as typeof window.scrollTo;
});

beforeEach(() => {
  sent.length = 0;
  window.sessionStorage.clear();
  window.history.replaceState({}, "", "/");
  const replies = [
    reply("Europe '72", "v1.first.sig", [
      { role: "user", text: "What's on Europe '72?" }, { role: "assistant", text: "Twenty-two nights." }
    ]),
    reply("The Lyceum", "v1.second.sig", [
      { role: "user", text: "What's on Europe '72?" }, { role: "assistant", text: "Twenty-two nights." },
      { role: "user", text: "Tell me about the last Lyceum night." }, { role: "assistant", text: "May 26, 1972." }
    ])
  ];
  vi.stubGlobal("fetch", vi.fn(async (url: RequestInfo | URL, init?: RequestInit) => {
    const path = String(url);
    if (path.endsWith("/api/experience/stream")) return new Response(null, { status: 404 });
    if (path.endsWith("/api/experience")) {
      sent.push(JSON.parse(String(init?.body)));
      return new Response(JSON.stringify(replies.shift()), { status: 200, headers: { "Content-Type": "application/json" } });
    }
    return new Response(null, { status: 404 });
  }));
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

function ask(text: string) {
  const box = screen.getAllByLabelText("Question").find((element) => !(element as HTMLTextAreaElement).disabled) as HTMLTextAreaElement;
  fireEvent.change(box, { target: { value: text } });
  fireEvent.keyDown(box, { key: "Enter" });
}

test("a follow-up sends back the notebook the last answer carried, and the tab keeps the newest", async () => {
  vi.resetModules();
  const { default: App } = await import("./App");
  render(<App />);
  ask("What's on Europe '72?");
  await screen.findByRole("heading", { level: 1, name: "Europe '72" });
  expect(sent[0].notebook).toBeUndefined();
  expect(window.sessionStorage.getItem("deadbot-research-notebook")).toBe("v1.first.sig");
  ask("Tell me about the last Lyceum night.");
  await screen.findByRole("heading", { level: 1, name: "The Lyceum" });
  expect(sent[1].notebook).toBe("v1.first.sig");
  expect(window.sessionStorage.getItem("deadbot-research-notebook")).toBe("v1.second.sig");
});
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `npm test --prefix web -- research-notebook App.notebook`
Expected: FAIL (`Failed to resolve import "./research-notebook"`).

- [ ] **Step 3: Write `web/src/research-notebook.ts`**

```ts
// The research notebook is a signed token the server returns with each
// answer: what this conversation's research has found so far. The browser
// keeps it for the tab's session and sends it back with the next question,
// so a follow-up starts from that research instead of from nothing. Storage
// can be blocked or full; then the token lives only in memory for this page.
const STORAGE_KEY = "deadbot-research-notebook";

export function readStoredNotebook(): string | null {
  try {
    const value = window.sessionStorage.getItem(STORAGE_KEY);
    return value && value.trim() ? value : null;
  } catch {
    return null;
  }
}

export function storeNotebook(token: string | null | undefined): void {
  try {
    if (token) window.sessionStorage.setItem(STORAGE_KEY, token);
    else window.sessionStorage.removeItem(STORAGE_KEY);
  } catch {
    // Blocked or full storage: the token still travels from React state.
  }
}

export function clearStoredNotebook(): void {
  storeNotebook(null);
}
```

- [ ] **Step 4: Hold, send and replace the token in `web/src/App.tsx`**

Import:

```tsx
import { clearStoredNotebook, readStoredNotebook, storeNotebook } from "./research-notebook";
```

Next to `const [activeThreadId, setActiveThreadId] = useState(createThreadId);`:

```tsx
  // What this conversation's research has found so far, signed by the
  // server. It goes back with each follow-up and is replaced by each answer.
  const [notebook, setNotebook] = useState<string | null>(readStoredNotebook);
```

In `askQuestion` (grid version), right after `const conversation = fresh ? [] : response?.conversation ?? [];`:

```tsx
    const sentNotebook = fresh ? null : notebook;
    if (fresh) {
      setNotebook(null);
      clearStoredNotebook();
    }
```

In the request body object the grid version builds (`{ question: trimmed, thread_id: requestThreadId, conversation, ...focus }`), add the notebook only when there is one:

```tsx
      ...(sentNotebook ? { notebook: sentNotebook } : {}),
```

After `const finalResponse = streamed ?? await askPlain(body);`:

```tsx
      setNotebook(finalResponse.notebook ?? null);
      storeNotebook(finalResponse.notebook);
```

In `startNewChat`, after `setActiveThreadId(createThreadId());`:

```tsx
    setNotebook(null);
    clearStoredNotebook();
```

- [ ] **Step 5: Run the web tests and build**

```bash
npm test --prefix web
npm run build --prefix web
```

Expected: all pass; the build type-checks `finalResponse.notebook`.

- [ ] **Step 6: Commit**

```bash
git add web/src/research-notebook.ts web/src/research-notebook.test.ts web/src/App.tsx web/src/App.notebook.test.tsx
git commit -m "Keep the research notebook for the tab and send it back with each follow-up

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 9: Live multi-turn evals, before and after

**Files:**
- Create: `docs/measurements/<today>-notebook-after.md`
- Modify: `docs/UX-NEXT-STEPS.md` (one status entry)
- Modify only if the evidence calls for it: `deadbot/notebook.py` (fact lines), `deadbot/graph.py` (the notebook paragraph), `deadbot/tools.py` (`read_notebook` description)

**Interfaces:**
- Consumes: everything above; `scripts/measure_turns.py --sequence ... --compare` (Task 3); the "before" file from Task 3 Step 7.

- [ ] **Step 1: Run the sequences with and without the notebook**

```bash
test -f .env || cp /Users/markdavenport/Development/DeadBot/.env .env
grep -q '^DEADBOT_NOTEBOOK_SECRET=' .env || echo "DEADBOT_NOTEBOOK_SECRET=$(python3 -c 'import secrets; print(secrets.token_urlsafe(32))')" >> .env
PYTHONPATH=. DEADBOT_MODEL_PROVIDER=openai DEADBOT_OPENAI_REASONING_EFFORT=low \
  /Users/markdavenport/Development/DeadBot/.venv/bin/python scripts/measure_turns.py \
  --sequence europe72 --sequence 1979 --compare --pause 20 \
  --output docs/measurements/$(date +%F)-notebook-after.md
```

Expected: four tables (each sequence without, then with, the notebook), three rows each, no `Error` cells, `Notebook sent (bytes)` above zero on turns 2–3 of the "with" runs.

- [ ] **Step 2: Compare against the spec's targets**

For turns 2 and 3 of each "with" run, against the Task 3 "before" file and the "without" run of the same session:

| Measure | Target from the spec |
|---|---|
| Model calls on a follow-up about material already researched (europe72 turn 2, 1979 turn 2) | 1–2 (today 3–4) |
| Total input tokens on those turns | 15–35k (today 50–90k) |
| Seconds to first answer on those turns | about 7–9 s (today 13–20 s) |
| Follow-ups needing new research (europe72 turn 3) | no search round; 3–6 s and 12–25k tokens saved |
| Cached share on turns 2–3 | well above the "without" run; record the value |
| Notebook index (chars) | under about 12,000 characters (3k tokens) at turn 3 |

Write a short section at the top of the "after" file: one line per sequence and turn with calls, input tokens, cached share and seconds before → after, and which targets were met.

- [ ] **Step 3: Read every page**

Start the worktree API with the same `.env` and ask both sequences in the browser (follow the project memory's local-replay notes: `deadbot serve`, OpenAI key, reasoning effort `low`). For each turn, read the chat answer and the page: did the follow-up use the earlier night without re-searching, are the cards hydrated (setlists, players), did any card vanish between the streamed draft and the delivered page, and is the answer as good as the "without" run's? Also click a grid cell's "Ask about this" (grid Task 7) after the Europe '72 answer and check the flags message led to a one- or two-call turn. Record findings in the "after" file in the visitor's terms.

- [ ] **Step 4: Fix the family, not the example**

If the model re-searches what the notebook already holds, or reads everything back, change what it was missing: a fact line that hides the fact it needed (Task 1 `_SUMMARIES`), the notebook paragraph in `SYSTEM_PROMPT`, or the `read_notebook` description. No keyword routes, no forced reads. Re-run both sequences after any change and keep both result tables in the file. Add a measured line for any change to the "after" file.

- [ ] **Step 5: Status note**

Add an entry to `docs/UX-NEXT-STEPS.md`: the research notebook shipped (token in the browser, `read_notebook`, notebook grounding, prompt-cache key), the measured before/after for the two sequences, the Vercel secret's status, and any open item from Step 3.

- [ ] **Step 6: Run everything, commit, and hand the push to the owner**

```bash
PYTHONPATH=. /Users/markdavenport/Development/DeadBot/.venv/bin/python -m pytest -q
npm test --prefix web
npm run build --prefix web
git add docs/measurements/*-notebook-after.md docs/UX-NEXT-STEPS.md
git commit -m "Measure follow-ups with the research notebook against the baseline

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

Stage any Step 4 code changes by name in the same or a preceding commit. Then give the owner the push command for the branch on its own line, and after they confirm, open the pull request with `gh pr create` and a body that ends with the attribution line. After it merges and deploys with `DEADBOT_NOTEBOOK_SECRET` set, ask the Europe '72 starter on production and one follow-up, and confirm in the preview or production logs that the turn read the notebook (`notebook_reads` or a short call count in the turn-metrics line) and that no "signature does not match" warnings appear.

---

## Self-review notes

- Spec coverage: entries with key/tool/args/ids/summary/tokens/turn/last_read/payload and page digests (Task 1); signed token, `DEADBOT_NOTEBOOK_SECRET`, bad signature logged, size and eviction rules (Task 2); `ExperienceResponse.notebook` in both the JSON and the final NDJSON event, `ExperienceRequest.notebook`, OpenAPI and types (Task 4); index as append-only deltas after each answer, focus flags from `AskFocus` (Task 5); `prompt_cache_key=thread_id` (Task 5); `read_notebook` through `config["configurable"]["notebook"]` with replay and stored web payloads (Task 6); grounding extended at both `build_experience_response` and the stream path (Task 7); prompt sentences (Task 7); notebooks in the warm-answers bundle (Task 4); frontend state plus sessionStorage (Task 8); `cached_input_tokens` already logged per call, now shown with cached share and notebook columns, and multi-turn evals before (Task 3) and after (Task 9).
- Decisions this plan made where the spec was open:
  - Notebook text is a `HumanMessage` named `research_notebook` (the Responses API drops names), skipped by `_conversation`, so it never reaches the visitor's transcript. Focus flags are their own named message before the question rather than appended to it, for the same reason.
  - Deltas are placed by a hash of each turn's chat answer, not by position, because the browser's transcript is trimmed to the conversation window; turns that no longer match go in one leading message.
  - Re-running a call keeps the entry's first turn and line (refreshing only `last_read` and a web payload), so bytes already sent never change. The spec said "replaces its entry"; this keeps the prompt cache warm.
  - The 4k-token index ceiling counts entry lines only; page digests are bounded separately (6 turns, 12 blocks), so a long page can never force every entry out.
  - Requests that carry a notebook neither read nor fill the response cache: their answers may lean on earlier research.
  - A reload keeps the token in sessionStorage and sends it with the next typed question; starter chips and "New chat" clear it.
- Type consistency: `Entry`, `PageDigest`, `Notebook`, `record_turn`, `encode`/`decode`, `transcript_with_notebook`, `find`, `grounding`, `entries_mentioning`, `render_flags`, `notebook_message`, `NOTEBOOK_MESSAGE_NAME` (composition), `run_config(..., notebook=, prompt_cache_key=)`, `_run_config`, `_turn_grounding`, `merge_grounding`, `extra_grounding` are named the same in every task that uses them.
