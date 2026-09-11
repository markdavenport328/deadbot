"""Turn the agent's final ``finish_response`` tool call into a browser response.

The model does its research with read-only tools and then delivers the
experience by calling ``finish_response`` with a :class:`FinishPlan`. This
module owns the model-facing plan schema, collects what the tools actually
returned this turn, resolves the plan's references against the store, and
produces the validated :class:`ExperienceResponse`. Deterministic code here is
transport and structural integrity only: it never chooses content and never
vetoes an editorial decision. An ungrounded reference or link is dropped; a
missing plan is a logged, diagnosable failure.
"""

from __future__ import annotations

import logging
import re
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Annotated, Any, Literal

from langchain_core.tools import BaseTool, StructuredTool
from pydantic import BaseModel, ConfigDict, Field, TypeAdapter, ValidationError, model_validator

from deadbot import composition
from deadbot.data import CanonicalStore
from deadbot.experience import (
    ConversationTurn,
    EditorialBlock,
    Emphasis,
    ExperienceGroup,
    ExperienceBlock,
    ExperienceResponse,
    GapStateBlock,
    PersonRosterBlock,
    PersonRosterItem,
    ResourceListBlock,
    ShowFacet,
    ShowUnitBlock,
    SongFacet,
    SourceReference,
)


logger = logging.getLogger(__name__)

FINISH_TOOL_NAME = "finish_response"

# The most items one group carries. Applied identically by the finish tool's
# plan validation and by the progressive streamer, so the page the visitor
# watches compose is the page that is delivered.
GROUP_ITEM_LIMIT = 20

# The ways a group can relate its items. An unknown value reads as a
# collection in both paths rather than failing the plan.
PRESENTATIONS = frozenset({"collection", "sequence", "comparison", "argument"})

# Deprecated plan vocabulary, accepted for one release and mapped to emphasis.
UnitRole = Literal["anchor", "supporting", "contrast", "turning_point", "outlier", "culmination", "overlooked", "representative"]

_MARKDOWN_LINK = re.compile(r"\[([^\]]+)\]\((https?://[^\s)]+)\)")


@dataclass(frozen=True)
class GroundedContext:
    """Identifiers and URLs the tools returned during the current turn."""

    ids: frozenset[str]
    urls: frozenset[str]


def _walk(value: Any, ids: set[str], urls: set[str], key: str | None = None) -> None:
    if isinstance(value, dict):
        for child_key, child in value.items():
            _walk(child, ids, urls, child_key)
    elif isinstance(value, list):
        for child in value:
            _walk(child, ids, urls, key)
    elif isinstance(value, str):
        if value.startswith(("http://", "https://")):
            urls.add(value)
        elif key and (key == "id" or key.endswith("_id") or key == "archive_identifier" or key == "key_signature"):
            ids.add(value)


def grounded_context(payloads: list[dict[str, Any]]) -> GroundedContext:
    """Collect every identifier and URL present in this turn's tool output."""

    ids: set[str] = set()
    urls: set[str] = set()
    for payload in payloads:
        _walk(payload, ids, urls)
    return GroundedContext(ids=frozenset(ids), urls=frozenset(urls))


def keep_grounded_links(text: str, urls: frozenset[str]) -> str:
    """Keep markdown links whose URL the tools returned; unwrap the others to plain text."""

    def replace(match: re.Match[str]) -> str:
        label, url = match.group(1), match.group(2)
        return match.group(0) if url in urls else label

    return _MARKDOWN_LINK.sub(replace, text)


class _Ref(BaseModel):
    """A library component referenced by canonical ID, optionally retitled."""

    model_config = ConfigDict(extra="forbid")
    title: str | None = None


class EquipmentListRef(_Ref):
    type: Literal["equipment_list"]
    show_id: str


class GuestAppearancesRef(_Ref):
    type: Literal["guest_appearance_list"]
    person_id: str


class PersonRosterEntry(BaseModel):
    """One person in a roster, by ID, with an optional phrase from the model."""

    model_config = ConfigDict(extra="forbid")
    person_id: str = Field(description="A person_id that appeared in a tool result this turn.")
    note: str | None = Field(
        default=None,
        description="A short phrase on what makes this person worth knowing here, when you have one grounded in the research. The server supplies name, roles, show count and years.",
    )


class PersonRosterRef(_Ref):
    """One section of people under a heading you choose.

    The inventory component for questions that ask for everyone. A page that
    lists everyone uses several rosters, one per section, so that together they
    hold the complete set; a section is a scene, an instrument, an era or a
    pattern such as the people who kept coming back. The server hydrates each
    person's name, roles, show count and span from the library.
    """

    type: Literal["person_roster"]
    title: str = Field(description="The heading that names this section of people: a scene, role, era or pattern, in a few words.")
    lead: str | None = Field(default=None, description="One sentence on what unites these people, when the heading alone does not say it.")
    entries: list[PersonRosterEntry] = Field(
        min_length=1,
        max_length=200,
        description="Everyone who belongs in this section, in the order you want them read. Across the page's rosters, every person appears once.",
    )


class ShowSelectionRef(_Ref):
    type: Literal["show_selection"]
    selection_id: str


class ArrangementRef(_Ref):
    type: Literal["arrangement"]
    arrangement_id: str


class ArrangementSearchRef(_Ref):
    type: Literal["arrangement_search"]
    key_signature: str


class MediaLinkRef(_Ref):
    type: Literal["media_link"]
    url: str


class ResourceListRef(_Ref):
    type: Literal["resource_list"]
    resource_ids: list[str] = Field(min_length=1, max_length=8)


# --- semantic units ---------------------------------------------------------
#
# A unit declares what the visitor should perceive as one meaningful object in
# this answer. The model supplies interpretation (emphasis, note,
# preferred listening, evidence, next question); the server hydrates the
# object's own facts from the store.


class SupportingSource(BaseModel):
    """Evidence the composer attaches to a unit, cited by a URL a tool returned this turn."""

    model_config = ConfigDict(extra="forbid")
    url: str = Field(description="A URL that appeared in a tool result this turn: a resource, research record, search hit, read page or archive review.")
    note: str | None = Field(default=None, description="What this source says about the unit, in a sentence, with attribution.")


class FollowUpTopic(BaseModel):
    """A short topic chip the visitor can press, and the full question it stands for.

    The chip shows only the label under "More about"; pressing it sends the
    question, in the visitor's voice, to start a new turn.
    """

    model_config = ConfigDict(extra="forbid")
    label: str = Field(
        max_length=40,
        description="Two or three words naming the topic as it will appear on the chip, e.g. 'Guest musicians', 'Spring 1990', 'Jazz and the Dead'.",
    )
    question: str = Field(description="The full question, in the visitor's voice, that the chip sends when pressed.")


_EMPHASIS_DESCRIPTION = (
    "How much of the page this object earns. primary: the object the answer is about; renders full width with its "
    "selected facets open. supporting: a peer or piece of evidence; renders as a compact card with its note, listening "
    "and highlights. mention: a name the visitor may want to follow; renders as one line with a listen link."
)
_ROLE_DESCRIPTION = "Deprecated. Use emphasis. anchor maps to primary; every other value maps to supporting."
_JUDGMENTS_DESCRIPTION = (
    "For a unit inside a comparison group: your one-line judgment for each of the group's criteria, in the same order. "
    "Leave an entry empty when you have nothing grounded to say."
)
_NOTE_DESCRIPTION = "Why this object matters here, stated briefly. Interpretation, not the facts the server already shows."
_SOURCES_DESCRIPTION = "Sources whose evidence is about this object specifically (a quote about this show, a review of this recording)."
_FOLLOW_UPS_DESCRIPTION = (
    "Up to three topics the visitor might want more about, each a short label plus the specific question it opens. "
    "Draw them from relationships or implications found in this research: explanation, comparison, history, lore or "
    "evidence. This object's listening links already cover hearing it, so topics open understanding rather than "
    "playback. Include only topics that create a worthwhile continuation."
)


class ShowUnitRef(_Ref):
    """One show as a primary object of the answer. The server supplies date, venue, setlist, guests and listening."""

    title: str | None = Field(
        default=None,
        description=(
            "Your headline for this show: its familiar nickname ('Cornell \'77', 'The Field Trip') or the phrase that says what "
            "it means in this answer ('A remarkably complete night'). The card names the venue, city and date above your headline, "
            "and your note is the text beneath it, so the headline is free to interpret. Omit it and the venue name is the headline."
        ),
    )
    type: Literal["show_unit"]
    show_id: str
    role: UnitRole | None = Field(default=None, description=_ROLE_DESCRIPTION)
    emphasis: Emphasis | None = Field(default=None, description=_EMPHASIS_DESCRIPTION)
    judgments: list[str] = Field(default_factory=list, max_length=5, description=_JUDGMENTS_DESCRIPTION)
    note: str | None = Field(default=None, description=_NOTE_DESCRIPTION)
    visible_facets: list[ShowFacet] = Field(
        default_factory=list,
        max_length=6,
        description=(
            "The facets worth showing for this show. guests, listen, setlist and sources as before; lineup is the full "
            "performer list; recordings is the complete recording inventory. Identity and your note are always shown."
        ),
    )
    setlist_disclosure: Literal["expanded", "collapsed", "hidden"] = Field(
        default="collapsed",
        description="How a selected setlist starts: expanded only when it is the immediate point, otherwise collapsed or hidden.",
    )
    highlighted_performance_ids: list[str] = Field(
        default_factory=list,
        max_length=12,
        description="Performances in this show that deserve attention; the setlist marks them and offers them first.",
    )
    preferred_recording_id: str | None = Field(default=None, description="The recording of this show to lead with, when you have a reason to prefer one.")
    supporting_sources: list[SupportingSource] = Field(default_factory=list, max_length=4, description=_SOURCES_DESCRIPTION)
    follow_ups: list[FollowUpTopic] = Field(default_factory=list, max_length=3, description=_FOLLOW_UPS_DESCRIPTION)


class PerformanceUnitRef(_Ref):
    """One rendition as a primary object. The server supplies song, show, set context and listening."""

    type: Literal["performance_unit"]
    performance_id: str
    role: UnitRole | None = Field(default=None, description=_ROLE_DESCRIPTION)
    emphasis: Emphasis | None = Field(default=None, description=_EMPHASIS_DESCRIPTION)
    judgments: list[str] = Field(default_factory=list, max_length=5, description=_JUDGMENTS_DESCRIPTION)
    note: str | None = Field(default=None, description=_NOTE_DESCRIPTION)
    supporting_sources: list[SupportingSource] = Field(default_factory=list, max_length=4, description=_SOURCES_DESCRIPTION)
    follow_ups: list[FollowUpTopic] = Field(default_factory=list, max_length=3, description=_FOLLOW_UPS_DESCRIPTION)


class EraUnitRef(_Ref):
    """A stage of a development you name, with representative performances as evidence and listening."""

    type: Literal["era_unit"]
    title: str = Field(description="The stage, in your words: '1973–74: spacious and exploratory'.")
    span: str | None = Field(default=None, description="The years or dates this stage covers.")
    note: str | None = Field(default=None, description="What changed in this stage and how you know.")
    representative_performance_ids: list[str] = Field(min_length=1, max_length=6, description="Performances that show this stage; each becomes a listening path.")
    supporting_sources: list[SupportingSource] = Field(default_factory=list, max_length=4, description=_SOURCES_DESCRIPTION)
    follow_ups: list[FollowUpTopic] = Field(default_factory=list, max_length=3, description=_FOLLOW_UPS_DESCRIPTION)


class AlbumUnitRef(_Ref):
    """One official record as a primary object, with model-selected facets."""

    title: str | None = Field(
        default=None,
        description=(
            "Your headline for this record: the phrase that says what it means in this answer ('Hear the source and trace the afterlife'). "
            "The card names the record, its kind and release date above your headline, and your note is the text beneath it, so the "
            "headline is free to interpret. Omit it and the record's own title is the headline."
        ),
    )
    type: Literal["album_unit"]
    release_id: str
    role: UnitRole | None = Field(default=None, description=_ROLE_DESCRIPTION)
    emphasis: Emphasis | None = Field(default=None, description=_EMPHASIS_DESCRIPTION)
    judgments: list[str] = Field(default_factory=list, max_length=5, description=_JUDGMENTS_DESCRIPTION)
    note: str | None = Field(default=None, description="Why this record matters to the question, in your voice.")
    visible_facets: list[Literal["listen", "tracklist", "personnel", "sources"]] = Field(
        default_factory=list,
        max_length=4,
        description=(
            "The record details that materially advance this answer. Select deliberately: tracklist and personnel hydrate the complete available lists, "
            "so omit them when the record is only context. Identity and your note are always shown."
        ),
    )
    highlighted_song_ids: list[str] = Field(default_factory=list, max_length=12)
    supporting_sources: list[SupportingSource] = Field(default_factory=list, max_length=4, description=_SOURCES_DESCRIPTION)
    follow_ups: list[FollowUpTopic] = Field(default_factory=list, max_length=3, description=_FOLLOW_UPS_DESCRIPTION)


class SongOverviewRef(_Ref):
    """One song as a primary object, with model-chosen representative performances."""

    type: Literal["song_overview"]
    song_id: str
    role: UnitRole | None = Field(default=None, description=_ROLE_DESCRIPTION)
    emphasis: Emphasis | None = Field(default=None, description=_EMPHASIS_DESCRIPTION)
    judgments: list[str] = Field(default_factory=list, max_length=5, description=_JUDGMENTS_DESCRIPTION)
    note: str | None = Field(default=None, description=_NOTE_DESCRIPTION)
    visible_facets: list[SongFacet] = Field(
        default_factory=lambda: ["representatives"],
        max_length=4,
        description=(
            "The song facets worth showing: representatives (your chosen renditions), credits, albums, history (first "
            "and last performances, the count, and one rendition per year with listening links)."
        ),
    )
    representative_performance_ids: list[str] = Field(
        default_factory=list,
        max_length=3,
        description="Representative performances for this song, in the listening order you chose. Retrieve concrete rendition IDs first; each known direct recording link remains attached.",
    )
    supporting_sources: list[SupportingSource] = Field(default_factory=list, max_length=4, description=_SOURCES_DESCRIPTION)
    follow_ups: list[FollowUpTopic] = Field(default_factory=list, max_length=3, description=_FOLLOW_UPS_DESCRIPTION)


def _emphasis_for(ref: Any) -> Emphasis:
    """The rendered emphasis for a unit ref: explicit emphasis, else the deprecated role mapped."""

    explicit = getattr(ref, "emphasis", None)
    if explicit:
        return explicit
    return "primary" if getattr(ref, "role", None) == "anchor" else "supporting"


BodyItem = Annotated[
    EditorialBlock
    | ShowUnitRef
    | PerformanceUnitRef
    | EraUnitRef
    | AlbumUnitRef
    | SongOverviewRef
    | EquipmentListRef
    | GuestAppearancesRef
    | PersonRosterRef
    | ShowSelectionRef
    | ArrangementRef
    | ArrangementSearchRef
    | MediaLinkRef
    | ResourceListRef,
    Field(discriminator="type"),
]

_BODY_ITEM_ADAPTER = TypeAdapter(BodyItem)


def _describe_validation_error(error: ValidationError) -> str:
    """The first problem in a validation error, as one short line for a log."""

    problems = error.errors()
    if not problems:
        return str(error)
    first = problems[0]
    location = ".".join(str(part) for part in first.get("loc", ()))
    return f"{location or 'item'}: {first.get('msg', 'invalid')}"


def validate_body_item(raw: Any, *, where: str) -> Any | None:
    """One body item, or ``None`` when it does not fit its schema.

    The one rule for a body item, shared by the finish tool's plan validation
    and the progressive streamer: an item that does not fit is dropped and
    logged, never a reason to reject the plan around it. Both paths apply it
    to the same text, so the draft page and the delivered page agree.
    """

    if isinstance(raw, BaseModel):
        return raw
    try:
        return _BODY_ITEM_ADAPTER.validate_python(raw)
    except ValidationError as error:
        kind = raw.get("type") if isinstance(raw, dict) else type(raw).__name__
        keys = sorted(raw.keys()) if isinstance(raw, dict) else []
        logger.warning(
            "Dropped a %s %s item that did not fit its schema (%s); it carried keys %s", where, kind, _describe_validation_error(error), keys
        )
        return None


class GroupPlan(BaseModel):
    """A model-selected editorial relationship among body items."""

    # A key the schema does not name is ignored, as the streamer ignores it;
    # the items inside keep their own strict schemas (see validate_body_item).
    model_config = ConfigDict(extra="ignore")
    title: str | None = Field(
        default=None,
        description=(
            "A concise heading that names this group's subject. Omit it when the page title already does that job, and when the "
            "group holds one item that carries its own title: that title is the heading."
        ),
    )
    lead: str | None = Field(default=None, description="A brief relationship, claim, or shared basis that adds to the page lead. Omit it rather than restating the same framing.")
    presentation: Literal["collection", "sequence", "comparison", "argument"] = Field(
        description="collection for peers, sequence for a development or route, comparison for items judged on shared terms, argument for evidence supporting a claim."
    )
    criteria: list[str] = Field(
        default_factory=list,
        max_length=5,
        description="For a comparison only: the shared terms the items are judged on, in order, as short labels such as 'Tempo' or 'Second-set jam'.",
    )
    items: list[BodyItem] = Field(
        min_length=1,
        max_length=GROUP_ITEM_LIMIT,
        description=(
            "Only the items that earn a place in the answer, in exact reading order, up to twenty. "
            "Retrieved or related does not mean included."
        ),
    )


class FinishPlan(BaseModel):
    """The model's finished response: chat answer plus the main-body plan."""

    model_config = ConfigDict(extra="ignore")

    @model_validator(mode="before")
    @classmethod
    def _apply_body_rules(cls, data: Any) -> Any:
        """Body rules the streamer applies too, so both paths deliver one page.

        A group keeps its first ``GROUP_ITEM_LIMIT`` items; an item that does
        not fit its schema is dropped; a group left with no items is dropped;
        the page keeps its first eight groups; an unknown presentation reads
        as a collection and criteria keep only their strings. Sizes truncate
        and bad values fall back instead of failing the whole plan, because a
        failed plan makes the model retry with a different plan after the
        visitor has already watched the first one compose. What the plan must
        still get right is the answer and the title.
        """

        if not isinstance(data, dict) or not isinstance(data.get("groups"), list):
            return data
        raw_groups = data["groups"]
        if len(raw_groups) > 8:
            logger.warning("finish_response planned %d groups; keeping the first 8", len(raw_groups))
            raw_groups = raw_groups[:8]
        groups: list[Any] = []
        for group in raw_groups:
            if not isinstance(group, dict) or not isinstance(group.get("items"), list):
                groups.append(group)  # Ordinary validation reports what is wrong with it.
                continue
            raw_items = group["items"]
            if len(raw_items) > GROUP_ITEM_LIMIT:
                logger.warning("finish_response planned %d items in one group; keeping the first %d", len(raw_items), GROUP_ITEM_LIMIT)
                raw_items = raw_items[:GROUP_ITEM_LIMIT]
            items = [item for item in (validate_body_item(raw, where="planned") for raw in raw_items) if item is not None]
            if not items:
                logger.warning("finish_response planned a group with no usable items (title=%r); dropping it", group.get("title"))
                continue
            presentation = group.get("presentation")
            if presentation not in PRESENTATIONS:
                logger.warning("finish_response planned a group with presentation %r; reading it as a collection", presentation)
                presentation = "collection"
            criteria = group.get("criteria")
            criteria = [entry for entry in criteria if isinstance(entry, str)][:5] if isinstance(criteria, list) else []
            groups.append({**group, "presentation": presentation, "criteria": criteria, "items": items})
        return {**data, "groups": groups}
    chat_answer: str = Field(
        description="The direct standalone answer shown in the conversation. Lead with the conclusion and keep it proportionate to the question. May use markdown links to URLs the tools returned this turn."
    )
    title: str = Field(description="Concise main-body title that states the central finding, not merely the topic.")
    lead: str | None = Field(default=None, description="A short expansion of the central finding. Omit it if the title and first item already establish the answer. Markdown links allowed.")
    groups: list[GroupPlan] = Field(
        default_factory=list,
        max_length=8,
        description=(
            "The edited main body as groups, each one a distinct relationship: collection for peers, sequence for a development or route, "
            "comparison for items judged on shared criteria, argument for evidence under a claim. Inside a group, semantic units declare the "
            "objects of the answer and the server hydrates their facts: show_unit, performance_unit, album_unit, song_overview, era_unit. "
            "Give each object an emphasis. Editorial blocks you write (narrative, fact_grid, timeline) carry what spans the units. "
            "Standalone components for objects without a parent unit: equipment_list, guest_appearance_list, person_roster (a complete set of "
            "people under a heading you choose), show_selection, arrangement, arrangement_search, media_link, resource_list. An answer that "
            "needs no main body leaves groups empty."
        ),
    )


def _retitle(block: Any, title: str | None) -> Any:
    if title and hasattr(block, "title"):
        return block.model_copy(update={"title": title.strip()})
    return block


def _sanitize_editorial(block: EditorialBlock, urls: frozenset[str]) -> EditorialBlock:
    items = [
        item.model_copy(update={"link": item.link if item.link and item.link.url in urls else None})
        for item in block.items
    ]
    return block.model_copy(
        update={
            "paragraphs": [keep_grounded_links(paragraph, urls) for paragraph in block.paragraphs],
            "items": items,
        }
    )


def _find_in_payloads(payloads: list[dict[str, Any]], key: str, match_key: str, match_value: str) -> dict[str, Any] | None:
    for payload in payloads:
        for record in payload.get(key, []) if isinstance(payload.get(key), list) else []:
            if isinstance(record, dict) and record.get(match_key) == match_value:
                return record
    return None


def _find_research_resource(payloads: list[dict[str, Any]], resource_id: str) -> dict[str, Any] | None:
    """Locate a research-sourced resource by its projected id.

    ``composition._research_resource`` synthesizes ``research:<source>:<identifier>``
    from a raw research record, so that id never appears verbatim in tool output for
    ``grounded.ids`` to have captured. It is grounded by construction instead: this
    scans the turn's research payloads and re-projects each record to find the match.
    """

    for payload in payloads:
        for key in ("research", "research_result", "research_results"):
            value = payload.get(key)
            if isinstance(value, dict):
                records = value.get("records")
            elif isinstance(value, list):
                records = value
            else:
                records = None
            for candidate in records or []:
                if not isinstance(candidate, dict):
                    continue
                projected = composition._research_resource(candidate)
                if projected and projected["resource_id"] == resource_id:
                    return projected
    return None


def _resolve_show_unit(
    item: ShowUnitRef,
    grounded: GroundedContext,
    payloads: list[dict[str, Any]],
    store: CanonicalStore,
) -> tuple[ShowUnitBlock | None, list[SourceReference]]:
    if item.show_id not in grounded.ids:
        return None, []
    show = store.resolve_show(item.show_id)
    if not show:
        return None, []
    selected_facets = frozenset(item.visible_facets)
    unit_sources, source_refs = composition._unit_sources(
        item.supporting_sources if "sources" in selected_facets else [], grounded.urls, payloads
    )
    block, listen_sources = composition._show_unit(
        store.show_context(show),
        store,
        emphasis=_emphasis_for(item),
        judgments=item.judgments,
        note=item.note,
        title=item.title,
        visible_facets=item.visible_facets,
        setlist_disclosure=item.setlist_disclosure,
        highlighted_performance_ids=item.highlighted_performance_ids,
        preferred_recording_id=item.preferred_recording_id,
        sources=unit_sources,
        follow_ups=item.follow_ups,
    )
    return block, [*listen_sources, *source_refs]


def _person_facts_from_store(person_ids: list[str], store: CanonicalStore) -> dict[str, dict[str, Any]]:
    """Name, roles, show count and span for each person, from the library in three bounded queries."""

    people = {row["person_id"]: row for row in store.rows_in("people", "person_id", person_ids)}
    assignments = store.rows_in("show_performers", "person_id", person_ids)
    shows = {row["show_id"]: row for row in store.rows_in("shows", "show_id", {row.get("show_id", "") for row in assignments})}
    facts: dict[str, dict[str, Any]] = {}
    for person_id, person in people.items():
        facts[person_id] = {"name": person.get("name") or person_id, "roles": [], "show_ids": set(), "years": []}
    for row in assignments:
        person_facts = facts.get(row.get("person_id", ""))
        if person_facts is None:
            continue
        instrument = row.get("instrument") or ""
        if instrument and instrument not in person_facts["roles"]:
            person_facts["roles"].append(instrument)
        show = shows.get(row.get("show_id", ""))
        if show:
            person_facts["show_ids"].add(show["show_id"])
            date = show.get("show_date") or ""
            if len(date) >= 4:
                person_facts["years"].append(date[:4])
    return facts


def _person_facts_from_payloads(person_id: str, payloads: list[dict[str, Any]]) -> dict[str, Any] | None:
    """A guest record from search_guest_musicians already carries canonical appearances."""

    guest = _find_in_payloads(payloads, "guests", "person_id", person_id)
    if not guest or not isinstance(guest.get("appearances"), list):
        return None
    roles: list[str] = []
    years: list[str] = []
    show_ids: set[str] = set()
    for appearance in guest["appearances"]:
        if not isinstance(appearance, dict):
            continue
        for instrument in appearance.get("instruments") or []:
            if isinstance(instrument, str) and instrument and instrument not in roles:
                roles.append(instrument)
        date = appearance.get("show_date") or ""
        if isinstance(date, str) and len(date) >= 4:
            years.append(date[:4])
        if isinstance(appearance.get("show_id"), str):
            show_ids.add(appearance["show_id"])
    name = guest.get("name")
    return {"name": name if isinstance(name, str) and name else person_id, "roles": roles, "show_ids": show_ids, "years": years}


def _resolve_person_roster(
    item: Any,
    grounded: GroundedContext,
    payloads: list[dict[str, Any]],
    store: CanonicalStore,
) -> PersonRosterBlock | None:
    """Hydrate a roster: the model chose who and in what order; the server supplies each person's facts."""

    wanted = [entry for entry in item.entries if entry.person_id in grounded.ids]
    if not wanted:
        return None
    from_store = _person_facts_from_store([entry.person_id for entry in wanted], store)
    items: list[PersonRosterItem] = []
    seen: set[str] = set()
    for entry in wanted:
        if entry.person_id in seen:
            continue
        facts = _person_facts_from_payloads(entry.person_id, payloads) or from_store.get(entry.person_id)
        if not facts:
            continue
        seen.add(entry.person_id)
        years = sorted(facts["years"])
        items.append(
            PersonRosterItem(
                person_id=entry.person_id,
                name=facts["name"],
                roles=facts["roles"][:6],
                show_count=len(facts["show_ids"]),
                first_year=years[0] if years else None,
                last_year=years[-1] if years else None,
                note=entry.note.strip() if entry.note and entry.note.strip() else None,
            )
        )
    if not items:
        return None
    return PersonRosterBlock(
        type="person_roster",
        title=item.title.strip() or "People",
        lead=keep_grounded_links(item.lead.strip(), grounded.urls) if item.lead and item.lead.strip() else None,
        items=items[:200],
    )


def _resolve_reference(
    item: Any,
    grounded: GroundedContext,
    payloads: list[dict[str, Any]],
    store: CanonicalStore,
) -> tuple[ExperienceBlock | None, list[SourceReference]]:
    sources: list[SourceReference] = []
    kind = item.type

    if kind == "show_unit":
        return _resolve_show_unit(item, grounded, payloads, store)

    if kind == "performance_unit":
        if item.performance_id not in grounded.ids:
            return None, []
        context = store.performance_context(item.performance_id)
        if not context:
            return None, []
        unit_sources, sources = composition._unit_sources(item.supporting_sources, grounded.urls, payloads)
        block = composition._performance_unit(
            context, store, emphasis=_emphasis_for(item), judgments=item.judgments, note=item.note, sources=unit_sources, follow_ups=item.follow_ups
        )
        return block, sources

    if kind == "era_unit":
        contexts = []
        for performance_id in item.representative_performance_ids:
            if performance_id not in grounded.ids:
                continue
            context = store.performance_context(performance_id)
            if context:
                contexts.append(context)
        if not contexts:
            return None, []
        unit_sources, sources = composition._unit_sources(item.supporting_sources, grounded.urls, payloads)
        block = composition._era_unit(contexts, store, title=item.title, span=item.span, note=item.note, sources=unit_sources, follow_ups=item.follow_ups)
        return block, sources

    if kind == "album_unit":
        if item.release_id not in grounded.ids:
            return None, []
        release = store.resolve_release(item.release_id)
        if not release:
            return None, []
        selected_facets = frozenset(item.visible_facets)
        unit_sources, sources = composition._unit_sources(
            item.supporting_sources if "sources" in selected_facets else [], grounded.urls, payloads
        )
        block, listen_sources = composition._album_unit(
            store.album_context(release),
            store,
            emphasis=_emphasis_for(item),
            judgments=item.judgments,
            note=item.note,
            title=item.title,
            visible_facets=item.visible_facets,
            highlighted_song_ids=item.highlighted_song_ids,
            sources=unit_sources,
            follow_ups=item.follow_ups,
        )
        return block, [*listen_sources, *sources]

    if kind == "equipment_list":
        if item.show_id not in grounded.ids:
            return None, []
        show = store.resolve_show(item.show_id)
        if not show:
            return None, []
        payload = store.show_context(show)
        block = composition._show_equipment(payload)
        if block:
            sources = [
                SourceReference(source_id=entry.source_id, kind="contextual_resource", label="Jerry Garcia Instrument History", url=entry.source_url)
                for entry in block.items
            ]
        return _retitle(block, item.title), sources

    if kind == "song_overview":
        if item.song_id not in grounded.ids:
            return None, []
        song = store.one("songs", item.song_id)
        if not song:
            return None, []
        context = store.song_context(song)
        unit_sources, sources = composition._unit_sources(item.supporting_sources, grounded.urls, payloads)
        return _retitle(
            composition._song_overview(
                context,
                store,
                emphasis=_emphasis_for(item),
                judgments=item.judgments,
                note=item.note,
                visible_facets=item.visible_facets,
                representative_performance_ids=[
                    performance_id
                    for performance_id in item.representative_performance_ids
                    if performance_id in grounded.ids
                ],
                sources=unit_sources,
                follow_ups=item.follow_ups,
            ),
            item.title,
        ), sources

    if kind == "guest_appearance_list":
        guest = _find_in_payloads(payloads, "guests", "person_id", item.person_id)
        blocks = composition._guest_appearance_blocks({"guests": [guest]}) if guest else []
        return (blocks[0], []) if blocks else (None, [])

    if kind == "person_roster":
        return _resolve_person_roster(item, grounded, payloads, store), []

    if kind == "show_selection":
        selection = _find_in_payloads(payloads, "show_selections", "selection_id", item.selection_id)
        blocks, selection_sources = composition._show_selection_blocks({"show_selections": [selection]}) if selection else ([], [])
        return (_retitle(blocks[0], item.title), selection_sources) if blocks else (None, [])

    if kind == "arrangement_search":
        for payload in payloads:
            search = payload.get("arrangement_search")
            if isinstance(search, dict) and search.get("key_signature") == item.key_signature:
                block, search_sources = composition._arrangement_search_block(payload, store)
                return _retitle(block, item.title), search_sources
        return None, []

    if kind == "arrangement":
        if item.arrangement_id not in grounded.ids:
            return None, []
        block = composition._arrangement_block(item.arrangement_id, store)
        if block:
            resource = store.one("resources", block.resource_id) or {}
            source = composition._resource_source(resource)
            sources = [source] if source else []
        return _retitle(block, item.title), sources

    if kind == "media_link":
        if item.url not in grounded.urls:
            return None, []
        for payload in payloads:
            for key in ("links", "show_links"):
                for link in payload.get(key, []) if isinstance(payload.get(key), list) else []:
                    if isinstance(link, dict) and link.get("url") == item.url:
                        return _retitle(composition._media_block(link), item.title), []
            for release in payload.get("official_releases", []) if isinstance(payload.get("official_releases"), list) else []:
                if isinstance(release, dict) and release.get("spotify_album_url") == item.url:
                    link = {"platform": "spotify", "link_type": "official-release", "url": item.url, "title": release.get("title", "Official release"), "is_official": True}
                    return _retitle(composition._media_block(link), item.title), []
        return None, []

    if kind == "resource_list":
        rows: list[Any] = []
        for resource_id in item.resource_ids:
            resource: dict[str, Any] | None
            if resource_id.startswith("research:"):
                # A research resource's id is synthesized by the projection, not
                # copied from tool output, so it cannot appear in grounded.ids.
                # It is grounded by construction: only ids re-derivable from this
                # turn's own research payloads can match.
                resource = _find_research_resource(payloads, resource_id)
            else:
                if resource_id not in grounded.ids:
                    continue
                resource = store.one("resources", resource_id)
                if not resource:
                    resource = _find_in_payloads(payloads, "resources", "resource_id", resource_id)
            entry = composition._resource_item(resource) if resource else None
            if entry:
                rows.append(entry)
                source = composition._resource_source(resource)
                if source:
                    sources.append(source)
        if not rows:
            return None, []
        return ResourceListBlock(type="resource_list", title=(item.title or "Reading and listening").strip(), items=rows[:8]), sources

    return None, []


def resolve_items(
    items: list[Any],
    grounded: GroundedContext,
    payloads: list[dict[str, Any]],
    store: CanonicalStore,
) -> tuple[list[ExperienceBlock], list[SourceReference]]:
    """Resolve a list of body items into validated blocks, dropping what was not retrieved."""

    blocks: list[ExperienceBlock] = []
    sources: list[SourceReference] = []
    for item in items:
        if isinstance(item, EditorialBlock):
            blocks.append(_sanitize_editorial(item, grounded.urls))
            continue
        block, block_sources = _resolve_reference(item, grounded, payloads, store)
        if block is None:
            logger.info("Dropped ungrounded or unresolvable reference: %s", item.model_dump())
            continue
        blocks.append(block)
        for source in block_sources:
            if source.source_id not in {existing.source_id for existing in sources}:
                sources.append(source)
    return blocks[:32], sources[:64]


def resolve_groups(
    plan: FinishPlan,
    grounded: GroundedContext,
    payloads: list[dict[str, Any]],
    store: CanonicalStore,
) -> tuple[list[ExperienceBlock], list[ExperienceGroup], list[SourceReference]]:
    """Resolve model-selected groups while preserving their order and relationship."""

    blocks: list[ExperienceBlock] = []
    groups: list[ExperienceGroup] = []
    sources: list[SourceReference] = []

    for group in plan.groups:
        group_blocks, group_sources = resolve_items(group.items, grounded, payloads, store)
        if not group_blocks:
            continue
        remaining = 32 - len(blocks)
        if remaining <= 0:
            break
        group_blocks = group_blocks[:remaining]
        criteria = [c.strip() for c in group.criteria if c.strip()][:5]
        criteria_count = len(criteria)
        group_blocks = [
            block.model_copy(update={"judgments": list(block.judgments)[:criteria_count]}) if hasattr(block, "judgments") else block
            for block in group_blocks
        ]
        start = len(blocks)
        blocks.extend(group_blocks)
        groups.append(
            ExperienceGroup(
                title=(group.title or "").strip() or None,
                lead=keep_grounded_links(group.lead.strip(), grounded.urls) if group.lead and group.lead.strip() else None,
                presentation=group.presentation,
                criteria=criteria,
                block_indexes=list(range(start, len(blocks))),
            )
        )
        for source in group_sources:
            if source.source_id not in {existing.source_id for existing in sources}:
                sources.append(source)
    return blocks, groups, sources[:64]


def _deliver(**_: Any) -> str:
    return "Response delivered to the visitor."


def build_finish_tool() -> BaseTool:
    """The one tool that ends a turn: its arguments are the finished response."""

    return StructuredTool.from_function(
        func=_deliver,
        name=FINISH_TOOL_NAME,
        description=(
            "Deliver the finished response to the visitor. Call this once, when your research is done. "
            "chat_answer gives the conclusion immediately; the main body adds the evidence, story or context that makes the answer worth opening, with "
            "listening and source actions attached to the objects they belong to. Compose groups (collection, sequence, comparison, argument) of semantic "
            "units with an emphasis, a note, selected facets, highlights and sources, plus your own narrative, fact grids or timelines for what spans the "
            "units. IDs must have appeared in a tool result this turn; links you write are kept only when their URL came from a tool result this turn."
        ),
        args_schema=FinishPlan,
    )


def finish_plan_from_messages(messages: list[Any]) -> FinishPlan | None:
    """Return the validated plan from the latest ``finish_response`` call, if any."""

    for message in reversed(messages):
        if getattr(message, "type", None) != "ai":
            continue
        # The last finish call in the message is the one the streamer followed,
        # so it is the one the delivered page is built from.
        for call in reversed(getattr(message, "tool_calls", None) or []):
            if call.get("name") == FINISH_TOOL_NAME:
                try:
                    return FinishPlan.model_validate(call.get("args") or {})
                except ValidationError as error:
                    logger.warning("finish_response arguments failed validation: %s", error)
                    return None
    return None


def _conversation(all_messages: list[Any], chat_answer: str) -> list[ConversationTurn]:
    """Visible turns: user text, earlier assistant answers, and this turn's chat answer.

    A single turn can carry more than one ``finish_response`` call: when the
    first one's arguments fail ``FinishPlan`` validation the model sees the tool
    error and retries. The visitor asked one question and must see one answer,
    so only the last finish call after each human message becomes an assistant
    turn — a later call overwrites the turn an earlier one produced.
    """

    turns: list[ConversationTurn] = []
    answer_index: int | None = None
    for message in all_messages:
        message_type = getattr(message, "type", None)
        text = composition._content_text(getattr(message, "content", "")).strip()
        if message_type == "human" and text:
            turns.append(ConversationTurn(role="user", text=text[:8_000]))
            answer_index = None
        elif message_type == "ai":
            for call in getattr(message, "tool_calls", None) or []:
                if call.get("name") == FINISH_TOOL_NAME and isinstance(call.get("args"), dict):
                    answer = str(call["args"].get("chat_answer") or "").strip()
                    if not answer:
                        continue
                    turn = ConversationTurn(role="assistant", text=answer[:8_000])
                    if answer_index is None:
                        turns.append(turn)
                        answer_index = len(turns) - 1
                    else:
                        turns[answer_index] = turn
            if text and not getattr(message, "tool_calls", None):
                turns.append(ConversationTurn(role="assistant", text=text[:8_000]))
    final = ConversationTurn(role="assistant", text=chat_answer[:8_000])
    if turns and turns[-1].role == "assistant":
        turns[-1] = final
    else:
        turns.append(final)
    return turns[-50:]


def build_experience_response(question: str, thread_id: str, messages: Iterable[Any], store: CanonicalStore) -> ExperienceResponse:
    """Assemble the browser response from the agent's latest turn."""

    all_messages = list(messages)
    turn = composition._latest_turn(all_messages)
    payloads = composition._tool_payloads(turn)
    plan = finish_plan_from_messages(turn)

    if plan is None:
        last_text = next(
            (composition._content_text(m.content).strip() for m in reversed(turn) if getattr(m, "type", None) == "ai" and composition._content_text(m.content).strip()),
            "",
        )
        logger.warning("The agent ended the turn without calling finish_response (question=%r, tool_payloads=%s)", question, len(payloads))
        answer = last_text or "Deadbot could not finish shaping this answer. Please try again."
        return ExperienceResponse(
            thread_id=thread_id,
            title="Deadbot",
            answer=answer,
            mode="gap",
            conversation=_conversation(all_messages, answer),
            blocks=[GapStateBlock(type="gap_state", message="The main body was not delivered for this answer.")],
            sources=[],
        )

    grounded = grounded_context(payloads)
    blocks, groups, sources = resolve_groups(plan, grounded, payloads, store)
    chat_answer = keep_grounded_links(plan.chat_answer.strip(), grounded.urls)
    lead = keep_grounded_links(plan.lead.strip(), grounded.urls) if plan.lead and plan.lead.strip() else None
    if not chat_answer.strip():
        logger.warning("finish_response delivered a blank chat_answer (question=%r); substituting the lead or a placeholder", question)
        chat_answer = lead if lead else "Deadbot could not write a chat answer for this response."
    return ExperienceResponse(
        thread_id=thread_id,
        title=plan.title.strip() or "Deadbot",
        answer=chat_answer,
        body_lead=lead,
        mode="answer",
        conversation=_conversation(all_messages, chat_answer),
        blocks=blocks,
        groups=groups,
        sources=sources,
    )
