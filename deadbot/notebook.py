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
