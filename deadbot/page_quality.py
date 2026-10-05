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
    }
    if expect:
        met, described = _expectation_met(expect, blocks)
        result["expected"] = {"met": met, "wanted": described}
    result["clean"] = not (result["repeats"] or result["catalog"] or result["narration"] or result["hedges"])
    return result
