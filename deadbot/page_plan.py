"""The page the model writes in ``finish_response``: an answer, then sections.

This is the shape the model sees. The server reads it into the plan the rest
of the pipeline already knows (:class:`deadbot.finish.FinishPlan`: a lead and
groups of body items), so validation, hydration, streaming and stored pages
share one path. Each section becomes a group; each item becomes one or more
body items. Code here is transport: it renames and reshapes, and it never
chooses content.
"""

from __future__ import annotations

import logging
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter, ValidationError, model_validator

logger = logging.getLogger(__name__)


def _without_null_branch(schema: dict[str, Any]) -> dict[str, Any]:
    """An optional field written as its type alone: it is optional because it may be left out."""

    branches = schema.get("anyOf")
    if not (isinstance(branches, list) and len(branches) == 2 and {"type": "null"} in branches):
        return schema
    other = next(branch for branch in branches if branch != {"type": "null"})
    rest = {key: value for key, value in schema.items() if key != "anyOf" and not (key == "default" and value is None)}
    return {**other, **rest}


class _Compact(BaseModel):
    """A model whose schema leaves out the null branch on each optional field; null still reads."""

    @classmethod
    def __get_pydantic_json_schema__(cls, core_schema: Any, handler: Any) -> dict[str, Any]:
        schema = handler(core_schema)
        target = handler.resolve_ref_schema(schema)
        properties = target.get("properties")
        if isinstance(properties, dict):
            for name, value in list(properties.items()):
                if isinstance(value, dict):
                    properties[name] = _without_null_branch(value)
        return schema


class _Item(_Compact):
    model_config = ConfigDict(extra="ignore")
    title: str | None = Field(default=None, description="A heading for this item, when the section's heading does not cover it.")


_OPEN = "True (the default) starts it open. False starts it as one row the visitor can open."


class PerformancesItem(_Item):
    """Performances to play in order: one song across nights, or several songs from one night."""

    type: Literal["performances"]
    performance_ids: list[str] = Field(description="The performances, in the order to hear them.")
    notes: dict[str, str] | None = Field(default=None, description="Your line under a performance, keyed by performance_id.")


class PairingItem(_Item):
    """Nights of two songs played back to back, from a get_segue_pairing result."""

    type: Literal["pairing"]
    pairing_id: str
    pair_ids: list[str] = Field(description="The nights to play, as pair_ids from that result, in order.")
    note: str | None = None


class ShowItem(_Item):
    """One show: its setlist, lineup and player."""

    type: Literal["show"]
    show_id: str
    note: str | None = None
    open: bool = Field(default=True, description=_OPEN)
    play: str | None = Field(
        default=None,
        description="Start the player here and make it the page's opening player: a set label such as 'Set 2', or a performance_id.",
    )


class ShowsItem(_Item):
    """Many shows as rows that open and play."""

    type: Literal["shows"]
    show_ids: list[str] = Field(default_factory=list, description="The shows, in order.")
    from_result: str | None = Field(default=None, description="A look_up result_id: every show in it, in its order.")
    notes: dict[str, str] | None = Field(default=None, description="Your line on a show, keyed by show_id.")


class ReleaseItem(_Item):
    """One official release."""

    type: Literal["release"]
    release_id: str
    note: str | None = None
    open: bool = Field(default=True, description=_OPEN)


class SongYearsItem(_Item):
    """A song's life year by year: times played or typical length, with each year's performances."""

    type: Literal["song_years"]
    song_id: str
    view: Literal["count", "length"] = "count"
    open_year: int | None = Field(default=None, description="The year whose performances open first.")
    note: str | None = None
    open: bool = Field(default=True, description=_OPEN)


class ChartItem(_Item):
    """An aggregate_data result as bars or a ranked list."""

    type: Literal["chart"]
    aggregation_id: str
    view: Literal["bars", "ranked"] = "bars"
    rows: int | None = Field(default=None, description="For ranked: how many rows from the top.")
    notes: dict[str, str] | None = Field(default=None, description="Your line on a row, keyed by its id, label or year.")
    note: str | None = None


class GridItem(_Item):
    """A get_grid result as a table, every cell playable."""

    type: Literal["grid"]
    grid_id: str
    row_ids: list[str] | None = Field(default=None, description="The rows to draw, in order; omit for all.")
    note: str | None = None


class PeopleItem(_Item):
    """Band members as bars across the years they played, with their show counts."""

    type: Literal["people"]
    person_ids: list[str] = Field(description="The people, in order.")
    note: str | None = None


class LinksItem(_Item):
    """Interviews, articles, podcasts and videos from the tools."""

    type: Literal["links"]
    urls: list[str] = Field(default_factory=list, description="URLs from this turn's tool results.")
    resource_ids: list[str] = Field(default_factory=list, description="resource_ids from search_stories.")


PageItem = Annotated[
    PerformancesItem
    | PairingItem
    | ShowItem
    | ShowsItem
    | ReleaseItem
    | SongYearsItem
    | ChartItem
    | GridItem
    | PeopleItem
    | LinksItem,
    Field(discriminator="type"),
]

_ITEM = TypeAdapter(PageItem)


class Section(_Compact):
    model_config = ConfigDict(extra="ignore")
    heading: str | None = None
    text: str | None = Field(default=None, description="Your words for this section, in markdown: paragraphs, lists or a table.")
    items: list[PageItem] = Field(default_factory=list, description="What to hear and see in this section, in order.")

    @model_validator(mode="before")
    @classmethod
    def _keep_good_items(cls, value: Any) -> Any:
        # One bad item never fails the page: the server reads the raw call and
        # keeps what it can of it, so the tool call itself only needs the rest.
        if not isinstance(value, dict) or not isinstance(value.get("items"), list):
            return value
        kept = []
        for item in value["items"]:
            try:
                _ITEM.validate_python(item)
            except ValidationError as error:
                logger.info("finish_response: an item did not fit its component: %s", str(error)[:300])
                continue
            kept.append(item)
        return {**value, "items": kept}


class PagePlan(_Compact):
    """The finished page: the answer, then sections in reading order."""

    model_config = ConfigDict(extra="ignore")
    headline: str | None = Field(default=None, description="A short line above the answer.")
    answer: str = Field(description="The answer to the question, in markdown: paragraphs, lists or a table.")
    sections: list[Section] = Field(default_factory=list, description="The rest of the page, in reading order.")


# --- reading the page into the pipeline's plan ------------------------------


def _text(value: Any) -> str | None:
    return value.strip() if isinstance(value, str) and value.strip() else None


def _strings(value: Any) -> list[str]:
    return [item for item in value if isinstance(item, str) and item.strip()] if isinstance(value, list) else []


def _string_map(value: Any) -> dict[str, str]:
    return {k: v for k, v in value.items() if isinstance(k, str) and isinstance(v, str) and v.strip()} if isinstance(value, dict) else {}


def _set_label(play: str) -> str:
    """'2', 'set 2' or 'Set 2' as the setlist labels it."""

    words = play.strip()
    if words.isdigit():
        return f"Set {words}"
    if words.lower().startswith("set "):
        return "Set " + words[4:].strip()
    return words


def _closed(item: dict[str, Any]) -> bool:
    return item.get("open") is False or str(item.get("open")).lower() == "false"


def body_items(item: Any) -> list[dict[str, Any]]:
    """One page item as the body items the pipeline hydrates. Unknown shapes pass through."""

    if not isinstance(item, dict):
        return []
    kind = item.get("type")
    disclosure = "collapsed" if _closed(item) else "expanded"
    title = _text(item.get("title"))
    note = _text(item.get("note"))
    if kind == "performances":
        return [{
            "type": "song_versions",
            "title": title,
            "performance_ids": _strings(item.get("performance_ids")),
            "notes": _string_map(item.get("notes")) or None,
        }]
    if kind == "pairing":
        return [{"type": "version_strip", "pairing_id": item.get("pairing_id"), "pair_ids": item.get("pair_ids"), "title": title, "note": note}]
    if kind == "show":
        play = _text(item.get("play"))
        if play:
            hero: dict[str, Any] = {"type": "listening_hero", "show_id": item.get("show_id"), "line": note or title}
            if play.startswith("gd-") and play != item.get("show_id"):
                hero["start_performance_id"] = play
            else:
                hero["start_set"] = _set_label(play)
                hero["play_label"] = f"Play {_set_label(play).lower()}"
            return [hero]
        return [{
            "type": "show_unit",
            "show_id": item.get("show_id"),
            "title": title,
            "note": note,
            "disclosure": disclosure,
            "visible_facets": ["listen", "setlist"] if disclosure == "collapsed" else ["listen", "setlist", "guests"],
        }]
    if kind == "shows":
        notes = _string_map(item.get("notes"))
        if _text(item.get("from_result")):
            return [{"type": "show_unit", "from_result": item["from_result"], "title": title, "disclosure": "collapsed", "visible_facets": ["listen", "setlist"]}]
        return [
            {"type": "show_unit", "show_id": show_id, "note": notes.get(show_id), "disclosure": "collapsed", "visible_facets": ["listen", "setlist"]}
            for show_id in _strings(item.get("show_ids"))
        ]
    if kind == "release":
        return [{"type": "album_unit", "release_id": item.get("release_id"), "title": title, "note": note, "disclosure": disclosure}]
    if kind == "song_years":
        view = item.get("view") if item.get("view") in ("count", "length") else "count"
        return [{
            "type": "song_overview",
            "song_id": item.get("song_id"),
            "title": title,
            "note": note,
            "disclosure": disclosure,
            "visible_facets": ["by_year"],
            "chart_view": view,
            "open_year": item.get("open_year"),
        }]
    if kind == "chart":
        if item.get("view") == "ranked":
            notes = [{"key": key, "note": value} for key, value in _string_map(item.get("notes")).items()]
            return [{"type": "ranked_list", "aggregation_id": item.get("aggregation_id"), "count": item.get("rows"), "title": title, "note": note, "notes": notes}]
        return [{"type": "data_chart", "aggregation_id": item.get("aggregation_id"), "title": title, "note": note}]
    if kind == "grid":
        return [{"type": "grid", "grid_id": item.get("grid_id"), "row_ids": item.get("row_ids"), "title": title, "note": note}]
    if kind == "people":
        return [{"type": "people_timeline", "person_ids": _strings(item.get("person_ids")), "title": title, "note": note}]
    if kind == "links":
        out: list[dict[str, Any]] = [{"type": "media_link", "url": url} for url in _strings(item.get("urls"))]
        if resource_ids := _strings(item.get("resource_ids")):
            out.append({"type": "resource_list", "resource_ids": resource_ids, "title": title})
        return out
    return [item]


def is_page_plan(data: Any) -> bool:
    return isinstance(data, dict) and ("answer" in data or "sections" in data)


def finish_args(data: dict[str, Any]) -> dict[str, Any]:
    """The page as the pipeline's plan: answer as lead, each section a group."""

    groups = []
    for section in data.get("sections") or []:
        if not isinstance(section, dict):
            continue
        items = [body for item in section.get("items") or [] for body in body_items(item)]
        groups.append({"title": _text(section.get("heading")), "lead": _text(section.get("text")), "presentation": "collection", "items": items})
    return {"headline": data.get("headline"), "lead": data.get("answer") or "", "groups": groups}


# The streamer reads the raw text key by key; these are the page's keys in the plan's terms.
TOP_KEYS = {"answer": "lead", "sections": "groups"}
SECTION_KEYS = {"heading": "title", "text": "lead"}
