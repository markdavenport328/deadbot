"""Versioned, validated experience schema for the browser client.

This module defines the allowlisted block schema Deadbot's server sends to the
browser: Pydantic block models, the discriminated ``ExperienceBlock`` union,
request/response envelopes, and layout/source references. Every browser-facing
payload is validated against these models, so neither the deterministic
adapter in :mod:`deadbot.composition` nor the model-guided composer in
:mod:`deadbot.composer` can pass browser code, raw HTML, or arbitrary embeds
to the client.

For backward compatibility, the deterministic adapter's names (for example
``compose_experience_response``) remain importable from this module; they are
re-exported lazily from :mod:`deadbot.composition` at the bottom of this file.
"""

from __future__ import annotations

from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field


ExperienceMode = Literal[
    "quick_fact",
    "performance",
    "show",
    "listening",
    "comparison",
    "research",
    "musician",
    "gap",
]


class ExperienceModel(BaseModel):
    """Base model that rejects unrecognized browser-facing fields."""

    model_config = ConfigDict(extra="forbid")


class SourceReference(ExperienceModel):
    source_id: str
    kind: Literal["canonical", "contextual_resource"]
    label: str
    url: str | None = None


class EntityCardBlock(ExperienceModel):
    type: Literal["entity_card"]
    entity_type: Literal["song", "show", "performance"]
    entity_id: str
    title: str
    subtitle: str | None = None
    details: list[str] = Field(default_factory=list, max_length=6)
    source_id: str
    follow_up: str | None = None


class SetlistSong(ExperienceModel):
    performance_id: str
    song_id: str
    title: str
    position_in_set: str | None = None
    follow_up: str


class SetlistSection(ExperienceModel):
    label: str
    songs: list[SetlistSong] = Field(min_length=1, max_length=40)


class ShowSetlistBlock(ExperienceModel):
    type: Literal["show_setlist"]
    show_id: str
    title: str
    sets: list[SetlistSection] = Field(min_length=1, max_length=4)


class ShowSelectionItem(ExperienceModel):
    show_id: str
    show_date: str
    venue_name: str
    location: str | None = None
    follow_up: str


class ShowSelectionBlock(ExperienceModel):
    """A clearly attributed selection of shows from one reviewed source."""

    type: Literal["show_selection"]
    title: str
    selection_type: str
    selector_name: str
    coverage_note: str
    source_id: str
    items: list[ShowSelectionItem] = Field(min_length=1, max_length=24)


class RecordingItem(ExperienceModel):
    recording_id: str
    title: str
    source_type: str
    archive_identifier: str | None = None
    url: str
    source_id: str


class RecordingListBlock(ExperienceModel):
    type: Literal["recording_list"]
    show_id: str | None = None
    title: str
    items: list[RecordingItem] = Field(min_length=1, max_length=8)


class PerformerItem(ExperienceModel):
    person_id: str
    name: str
    role: Literal["performer", "guest"]
    instruments: list[str] = Field(min_length=1, max_length=8)
    follow_up: str


class PerformerListBlock(ExperienceModel):
    type: Literal["performer_list"]
    show_id: str
    title: str
    items: list[PerformerItem] = Field(min_length=1, max_length=24)


class GuestAppearanceItem(ExperienceModel):
    show_id: str
    show_date: str
    venue_name: str | None = None
    location: str | None = None
    instruments: list[str] = Field(min_length=1, max_length=8)
    participation_scope: str | None = None
    follow_up: str


class GuestAppearanceListBlock(ExperienceModel):
    """Canonical guest-show relationships for one resolved person."""

    type: Literal["guest_appearance_list"]
    person_id: str
    person_name: str
    known_show_count: int = Field(ge=1)
    items: list[GuestAppearanceItem] = Field(min_length=1, max_length=24)


class EquipmentItem(ExperienceModel):
    equipment_id: str
    name: str
    manufacturer: str
    model: str
    usage_context: str
    claim_type: Literal["show", "date_range"]
    evidence: str
    source_id: str
    source_url: str
    follow_up: str


class EquipmentListBlock(ExperienceModel):
    type: Literal["equipment_list"]
    show_id: str
    title: str
    items: list[EquipmentItem] = Field(min_length=1, max_length=16)


class ResourceItem(ExperienceModel):
    resource_id: str
    title: str
    resource_type: str
    source_name: str
    url: str
    source_id: str
    context_note: str | None = None


class ResourceListBlock(ExperienceModel):
    type: Literal["resource_list"]
    title: str
    items: list[ResourceItem] = Field(min_length=1, max_length=8)


class CreditItem(ExperienceModel):
    person_id: str
    name: str
    role: str
    follow_up: str | None = None


class CreditListBlock(ExperienceModel):
    type: Literal["credit_list"]
    title: str
    items: list[CreditItem] = Field(min_length=1, max_length=12)
    source_ids: list[str] = Field(min_length=1, max_length=8)


class SongOverviewBlock(ExperienceModel):
    type: Literal["song_overview"]
    song_id: str
    title: str
    original_artist: str | None = None
    known_performance_count: int
    credits: list[CreditItem] = Field(default_factory=list, max_length=12)
    source_ids: list[str] = Field(default_factory=list, max_length=8)


class MediaLinkBlock(ExperienceModel):
    type: Literal["media_link"]
    title: str
    provider: str
    url: str
    link_type: str
    is_official: bool
    embed_kind: Literal["spotify", "youtube"] | None = None
    embed_id: str | None = None


class PerformanceListItem(ExperienceModel):
    performance_id: str
    show_id: str
    show_date: str | None = None
    show_label: str
    set_label: str | None = None
    position_in_set: str | None = None
    follow_up: str


class PerformanceExtremesBlock(ExperienceModel):
    type: Literal["performance_extremes"]
    song_id: str
    title: str
    first: PerformanceListItem
    last: PerformanceListItem


class PerformanceListBlock(ExperienceModel):
    type: Literal["performance_list"]
    title: str
    song_id: str
    known_count: int
    items: list[PerformanceListItem] = Field(min_length=1, max_length=20)


class ComparisonStripItem(ExperienceModel):
    performance_id: str
    show_id: str
    year: int
    show_date: str | None = None
    show_label: str
    set_label: str | None = None
    position_in_set: str | None = None
    follow_up: str


class ComparisonStripBlock(ExperienceModel):
    """Selected grounded performances of one song over time.

    Entries are representative selections from current library coverage —
    canonical dates and set placement only, never musical analysis.
    """

    type: Literal["comparison_strip"]
    song_id: str
    title: str
    known_count: int
    coverage_note: str
    items: list[ComparisonStripItem] = Field(min_length=2, max_length=12)


class PerformanceSpineNeighbor(ExperienceModel):
    performance_id: str
    title: str
    follow_up: str


class PerformanceSpineBlock(ExperienceModel):
    """Place one rendition back into its documented set sequence."""

    type: Literal["performance_spine"]
    performance_id: str
    song_id: str
    title: str
    show_label: str
    set_label: str | None = None
    position_in_set: str | None = None
    previous: PerformanceSpineNeighbor | None = None
    next: PerformanceSpineNeighbor | None = None


class CoverageBlock(ExperienceModel):
    type: Literal["coverage"]
    title: str
    message: str


class ArrangementBlock(ExperienceModel):
    type: Literal["arrangement"]
    title: str
    resource_id: str
    source_id: str
    key_signature: str | None = None
    arrangement_scope: str
    capo: str | None = None
    tuning: str | None = None
    notes: str | None = None
    progressions: list[str] = Field(default_factory=list, max_length=6)


class ArrangementSearchItem(ExperienceModel):
    arrangement_id: str
    song_id: str
    title: str
    resource_id: str
    resource_title: str
    source_name: str
    url: str
    key_signature: str
    arrangement_scope: str
    follow_up: str


class ArrangementSearchBlock(ExperienceModel):
    type: Literal["arrangement_search"]
    title: str
    key_signature: str
    coverage_note: str
    items: list[ArrangementSearchItem] = Field(min_length=1, max_length=20)


class ProvenanceNoteBlock(ExperienceModel):
    type: Literal["provenance_note"]
    text: str
    source_ids: list[str] = Field(min_length=1, max_length=8)


class GapStateBlock(ExperienceModel):
    type: Literal["gap_state"]
    message: str


class EditorialLink(ExperienceModel):
    """An outbound link the model attaches to something it wrote.

    The server keeps a link only when its URL appeared in material the tools
    returned during the same turn; anything else is dropped before rendering.
    """

    url: str
    label: str


class EditorialItem(ExperienceModel):
    marker: str | None
    title: str
    value: str | None
    detail: str | None
    follow_up: str | None
    link: EditorialLink | None = None


class EditorialBlock(ExperienceModel):
    """Flexible model-shaped material rendered in one of several visual forms."""

    type: Literal["editorial"]
    presentation: Literal["narrative", "fact_grid", "timeline"]
    eyebrow: str | None
    title: str | None
    paragraphs: list[str] = Field(max_length=4)
    items: list[EditorialItem] = Field(max_length=12)


ExperienceBlock = Annotated[
    EntityCardBlock
    | ShowSetlistBlock
    | ShowSelectionBlock
    | RecordingListBlock
    | PerformerListBlock
    | GuestAppearanceListBlock
    | EquipmentListBlock
    | ResourceListBlock
    | CreditListBlock
    | SongOverviewBlock
    | MediaLinkBlock
    | PerformanceListBlock
    | PerformanceExtremesBlock
    | PerformanceSpineBlock
    | ComparisonStripBlock
    | CoverageBlock
    | ArrangementBlock
    | ArrangementSearchBlock
    | ProvenanceNoteBlock
    | GapStateBlock
    | EditorialBlock,
    Field(discriminator="type"),
]


class ConversationTurn(ExperienceModel):
    """A browser-safe projection of one human or final assistant message."""

    role: Literal["user", "assistant"]
    text: str = Field(min_length=1, max_length=8_000)


class ExperienceRequest(ExperienceModel):
    question: str = Field(min_length=1, max_length=2_000)
    thread_id: str | None = Field(default=None, min_length=1, max_length=200)
    conversation: list[ConversationTurn] = Field(default_factory=list, max_length=50)


class LayoutSection(ExperienceModel):
    """A server-validated region in the composed main column."""

    region: Literal["primary", "supporting", "context", "media"]
    block_indexes: list[int] = Field(min_length=1, max_length=8)


class ExperienceResponse(ExperienceModel):
    schema_version: Literal["1"] = "1"
    thread_id: str
    title: str
    answer: str
    body_lead: str | None = None
    mode: ExperienceMode = "quick_fact"
    conversation: list[ConversationTurn] = Field(default_factory=list, max_length=50)
    # Four layout regions can each carry up to eight blocks. Keep the response
    # envelope aligned with that 32-block layout capacity so a deeply researched
    # candidate packet can be edited without a schema failure.
    blocks: list[ExperienceBlock] = Field(default_factory=list, max_length=32)
    layout: list[LayoutSection] = Field(default_factory=list, max_length=4)
    # A 32-block exploratory response can legitimately reference more than one
    # source per block (for example, show identity plus a recording path).
    sources: list[SourceReference] = Field(default_factory=list, max_length=64)


# ---------------------------------------------------------------------------
# Backward-compatible re-exports from the deterministic adapter.
#
# The adapter in deadbot.composition imports this schema module, so importing
# it eagerly here would be circular when deadbot.composition is imported
# first. A module-level __getattr__ (PEP 562) resolves the moved names lazily,
# keeping ``from deadbot.experience import compose_experience_response`` (and
# helper access such as ``experience._comparison_strip``) working regardless
# of which module is imported first.
# ---------------------------------------------------------------------------

_COMPOSITION_EXPORTS = frozenset(
    {
        "compose_experience_response",
        "_content_text",
        "_tool_payloads",
        "_final_answer",
        "_latest_turn",
        "_conversation_turns",
        "_canonical_source",
        "_resource_source",
        "_embed_details",
        "_resource_item",
        "_media_block",
        "_entity_card_from_song",
        "_entity_card_from_show",
        "_entity_card_from_performance",
        "_performance_items",
        "_performance_list",
        "_performance_extremes",
        "_comparison_strip",
        "_performance_spine",
        "_show_setlist",
        "_show_performers",
        "_show_equipment",
        "_recording_list",
        "_coverage_block",
        "_arrangement_search_block",
    }
)


def __getattr__(name: str) -> Any:
    if name in _COMPOSITION_EXPORTS:
        from deadbot import composition

        return getattr(composition, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
