"""Score the writing on a finished answer page.

The page-quality suite (evals/page-quality-v1.json, run by
scripts/page_eval.py) asks real questions and scores each delivered page so
that a change to the persona or tools is measured rather than judged one
answer at a time. Only words the model wrote are scored; names, dates and
venues the server fills in are not.

Every check counts something a reader would notice:

- repeats: a page layer that restates the chat answer
- catalog: talk about the catalog, library or documentation instead of the band
- narration: describing the page itself ("below", "open any card")
- hedges: stock caveats such as "not popularity ratings"

Three more checks look at what the visitor can do with the page rather than
its words:

- silent: a card with nothing to play on the page, only links that leave it
- empty_rows: a collapsed show row whose "More" opens to nothing
- restated: a text block whose rows retell cards already on the page
"""

from __future__ import annotations

import re
from typing import Any

CATALOG = re.compile(
    r"\b(catalog(?:ed|ue|s)?|documented|library|verified|surviving|qualifying|on record|in the data(?:base)?)\b",
    re.IGNORECASE,
)
NARRATION = re.compile(
    r"\b(below|above|the cards?|compact (?:rows?|cards?)|scannable|open (?:any|a|each|one)\b|"
    r"listed (?:chronologically|below|by)|ordered (?:by|chronologically)|in (?:release|chronological) order|"
    r"the (?:full |complete )?list (?:is|includes|below|shows)|click)\b",
    re.IGNORECASE,
)
HEDGES = re.compile(
    r"(not (?:a )?popularity|not necessarily|should not be (?:treated|read)|it should be noted|"
    r"not (?:objectively|definitively)|keep in mind|with that limitation)",
    re.IGNORECASE,
)
_WORD = re.compile(r"[A-Za-z0-9’']+")
_STOP = frozenset(
    "a an and are as at be but by for from had has have in into is it its of on or that the their them they this "
    "to was were which with while who whose than then there these those also its it’s dead grateful".split()
)


def _words(text: str) -> list[str]:
    return [word.lower() for word in _WORD.findall(text)]


def _content(text: str) -> set[str]:
    return {word for word in _words(text) if word not in _STOP and len(word) > 2}


def model_layers(response: dict[str, Any]) -> list[tuple[str, str]]:
    """(where, text) for every piece of the page the model wrote, chat answer excluded."""

    layers: list[tuple[str, str]] = []

    def add(where: str, value: Any) -> None:
        if isinstance(value, str) and value.strip():
            layers.append((where, value.strip()))

    add("title", response.get("title"))
    add("lead", response.get("body_lead"))
    for index, group in enumerate(response.get("groups") or []):
        add(f"group[{index}].title", group.get("title"))
        add(f"group[{index}].lead", group.get("lead"))
    for index, block in enumerate(response.get("blocks") or []):
        kind = block.get("type", "block")
        where = f"{kind}[{index}]"
        add(f"{where}.note", block.get("note"))
        if kind in {"editorial", "pull_quote"}:
            add(f"{where}.title", block.get("title"))
            add(f"{where}.text", block.get("text"))
            for p_index, paragraph in enumerate(block.get("paragraphs") or []):
                add(f"{where}.paragraph[{p_index}]", paragraph)
            for i_index, item in enumerate(block.get("items") or []):
                for key in ("title", "value", "detail"):
                    add(f"{where}.item[{i_index}].{key}", item.get(key))
        for r_index, row in enumerate(block.get("rows") or []):
            if isinstance(row, dict):
                add(f"{where}.row[{r_index}].note", row.get("note"))
        for j_index, judgment in enumerate(block.get("judgments") or []):
            add(f"{where}.judgment[{j_index}]", judgment)
    return layers


def _hits(pattern: re.Pattern[str], layers: list[tuple[str, str]], chat: str) -> list[str]:
    found: list[str] = []
    for where, text in [("chat", chat), *layers]:
        for match in pattern.finditer(text):
            found.append(f"{where}: “{match.group(0)}”")
    return found


def repeats(chat: str, layers: list[tuple[str, str]], threshold: float = 0.5) -> list[str]:
    """Layers whose content words mostly restate one sentence of the chat answer."""

    sentences = [_content(sentence) for sentence in re.split(r"(?<=[.!?])\s+", chat) if sentence.strip()]
    flagged: list[str] = []
    for where, text in layers:
        # A title naturally names what the answer names; repeats are sentences.
        if where == "title" or where.endswith(".title"):
            continue
        words = _content(text)
        if len(words) < 5:
            continue
        for sentence in sentences:
            if len(sentence) < 4:
                continue
            overlap = len(words & sentence) / min(len(words), len(sentence))
            if overlap >= threshold:
                flagged.append(f"{where} ({overlap:.0%} of a chat sentence)")
                break
    return flagged


def _expectation_met(expect: dict[str, Any], blocks: list[dict[str, Any]]) -> tuple[bool, str]:
    """``any_of``: one of these must hold. Each option names a block type and optional facet, disclosure, minimum count."""

    for option in expect.get("any_of", []):
        matching = [block for block in blocks if block.get("type") == option["type"]]
        if facet := option.get("facet"):
            matching = [block for block in matching if facet in (block.get("visible_facets") or [])]
        if disclosure := option.get("disclosure"):
            matching = [block for block in matching if block.get("disclosure", "expanded") == disclosure]
        if len(matching) >= option.get("min", 1):
            return True, _describe(option)
    return False, " or ".join(_describe(option) for option in expect.get("any_of", []))


def _describe(option: dict[str, Any]) -> str:
    bits = [option["type"]]
    if option.get("facet"):
        bits.append(f"+{option['facet']}")
    if option.get("disclosure"):
        bits.append(option["disclosure"])
    if option.get("min", 1) > 1:
        bits.append(f"×{option['min']}+")
    return " ".join(bits)


CARD_TYPES = frozenset({"show_unit", "performance_unit", "album_unit", "song_overview"})


def _has_audio(rows: Any, key: str = "audio_url") -> bool:
    return any(isinstance(row, dict) and row.get(key) for row in rows or [])


def playable(block: dict[str, Any]) -> bool:
    """Whether a card offers listening that stays on the page."""

    kind = block.get("type")
    if kind == "show_unit":
        songs = [song for set_ in block.get("sets") or [] for song in set_.get("songs") or []]
        return _has_audio(block.get("tracks")) or _has_audio(songs)
    if kind == "performance_unit":
        return bool(block.get("audio_url")) or bool(block.get("show_tracks"))
    if kind == "album_unit":
        # Spotify plays in the card's embed; anything else official leaves the site.
        spotify = any(isinstance(item, dict) and item.get("provider") == "spotify" for item in block.get("listen") or [])
        return spotify or _has_audio(block.get("tracks"))
    if kind == "song_overview":
        return _has_audio(block.get("representative_performances")) or _has_audio(
            block.get("representative_performances"), "track"
        )
    return True


def _card_label(index: int, block: dict[str, Any]) -> str:
    name = block.get("release_title") or block.get("song_title") or block.get("title") or block.get("show_id") or ""
    return f"{block.get('type')}[{index}] {name}".strip()


def silent_cards(blocks: list[dict[str, Any]]) -> list[str]:
    return [_card_label(index, block) for index, block in enumerate(blocks) if block.get("type") in CARD_TYPES and not playable(block)]


def empty_rows(blocks: list[dict[str, Any]]) -> list[str]:
    """Collapsed show rows that carry nothing for "More" to open."""

    found = []
    for index, block in enumerate(blocks):
        if block.get("type") != "show_unit" or block.get("disclosure") != "collapsed":
            continue
        if not any(block.get(key) for key in ("sets", "lineup", "guests", "recordings", "listen", "sources")):
            found.append(_card_label(index, block))
    return found


_TOKEN = re.compile(r"[a-z0-9]+")


def _tokens(text: str) -> set[str]:
    text = text.lower().replace("’", "'").replace("'s", "").replace("vol.", "volume ")
    return {token for token in _TOKEN.findall(text) if token not in _STOP and (token.isdigit() or len(token) > 2)}


def _card_names(blocks: list[dict[str, Any]]) -> tuple[list[set[str]], set[str]]:
    """Token sets naming each card or row on the page, and the years a song card already counts."""

    names: list[set[str]] = []
    years: set[str] = set()
    for block in blocks:
        for key in ("release_title", "song_title", "venue_name"):
            if isinstance(block.get(key), str):
                names.append(_tokens(block[key]))
        for row in (block.get("items") if block.get("type") == "person_roster" else None) or []:
            if isinstance(row, dict) and row.get("name"):
                names.append(_tokens(row["name"]))
        for row in block.get("rows") or [] if block.get("type") in {"data_chart", "ranked_list"} else []:
            if isinstance(row, dict) and isinstance(row.get("label"), str):
                names.append(_tokens(row["label"]))
        if block.get("type") == "song_overview" and "by_year" in (block.get("visible_facets") or []):
            years |= {str(row.get("year")) for row in block.get("year_counts") or [] if isinstance(row, dict)}
    return [name for name in names if name], years


def _names_a_card(text: str, names: list[set[str]], years: set[str]) -> bool:
    if text.strip() in years:
        return True
    words = _tokens(text)
    numbers = {word for word in words if word.isdigit()}
    for name in names:
        shared = words & name
        # Every number must agree, so Dick's Picks 4 never matches Vol. 11.
        if len(shared - numbers) >= min(2, len(name)) and numbers <= name:
            return True
    return False


def restated_cards(blocks: list[dict[str, Any]]) -> list[str]:
    """Editorial blocks whose rows mostly name cards the page already shows."""

    names, years = _card_names(blocks)
    if not names and not years:
        return []
    found = []
    for index, block in enumerate(blocks):
        if block.get("type") != "editorial":
            continue
        items = [item for item in block.get("items") or [] if isinstance(item, dict)]
        hits = sum(
            1 for item in items if any(_names_a_card(str(item.get(key) or ""), names, years) for key in ("marker", "title") if item.get(key))
        )
        if hits >= 2 and hits * 2 >= len(items):
            found.append(f"editorial[{index}] {block.get('title') or ''} ({hits} of {len(items)} rows retell cards)".strip())
    return found


def score_page(response: dict[str, Any], expect: dict[str, Any] | None = None) -> dict[str, Any]:
    """Counts and examples for one delivered page."""

    chat = response.get("answer") or ""
    layers = model_layers(response)
    blocks = response.get("blocks") or []
    result: dict[str, Any] = {
        "repeats": repeats(chat, layers),
        "catalog": _hits(CATALOG, layers, chat),
        "narration": _hits(NARRATION, layers, chat),
        "hedges": _hits(HEDGES, layers, chat),
        "page_words": sum(len(_words(text)) for _, text in layers),
        "chat_words": len(_words(chat)),
        "blocks": [block.get("type") for block in blocks],
        "silent": silent_cards(blocks),
        "empty_rows": empty_rows(blocks),
        "restated": restated_cards(blocks),
    }
    if expect:
        met, described = _expectation_met(expect, blocks)
        result["expected"] = {"met": met, "wanted": described}
    result["clean"] = not (result["repeats"] or result["catalog"] or result["narration"] or result["hedges"])
    result["usable"] = not (result["silent"] or result["empty_rows"] or result["restated"])
    return result
