"""Versioned, validated experience schema for the browser client.

This module defines the allowlisted block schema Deadbot's server sends to the
browser: Pydantic block models, the discriminated ``ExperienceBlock`` union,
request/response envelopes, and layout/source references. Every browser-facing
payload is validated against these models, so neither the block builders in
:mod:`deadbot.composition` nor the response assembly in :mod:`deadbot.finish`
can pass browser code, raw HTML, or arbitrary embeds to the client.
"""

from __future__ import annotations

from typing import Annotated, Literal

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
    # The composer marks a performance as important; the renderer decides how
    # that looks. A listen URL is the library's per-performance track link.
    highlighted: bool = False
    listen_url: str | None = None


class SetlistSection(ExperienceModel):
    label: str
    songs: list[SetlistSong] = Field(min_length=1, max_length=40)


class ShowSetlistBlock(ExperienceModel):
    type: Literal["show_setlist"]
    show_id: str
    title: str
    sets: list[SetlistSection] = Field(min_length=1, max_length=4)


UnitRole = Literal[
    "anchor",
    "supporting",
    "contrast",
    "turning_point",
    "outlier",
    "culmination",
    "overlooked",
    "representative",
]

UnitOrganization = Literal["chronological", "curated", "comparative"]


class ListenAction(ExperienceModel):
    """A listening destination attached to the object it plays."""

    label: str
    url: str
    provider: str
    is_official: bool = False


class UnitSource(ExperienceModel):
    """Evidence the composer associated with one unit, resolved to a grounded URL."""

    url: str
    label: str
    source_name: str | None = None
    note: str | None = None


class PerformanceSpineNeighbor(ExperienceModel):
    performance_id: str
    title: str
    follow_up: str


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


class ShowUnitBlock(ExperienceModel):
    """One show as a primary object of the answer, hydrated from the store.

    The composer supplies the interpretive fields (role, note, highlights,
    preferred recording, sources, follow-up); date, venue, setlist, guests and
    listening actions come from canonical data.
    """

    type: Literal["show_unit"]
    show_id: str
    title: str | None = None
    show_date: str
    venue_name: str | None = None
    location: str | None = None
    role: UnitRole | None = None
    note: str | None = None
    sets: list[SetlistSection] = Field(default_factory=list, max_length=4)
    setlist_note: str | None = None
    guests: list[PerformerItem] = Field(default_factory=list, max_length=8)
    listen: list[ListenAction] = Field(default_factory=list, max_length=4)
    sources: list[UnitSource] = Field(default_factory=list, max_length=4)
    follow_up: str | None = None


class ShowExplorerBlock(ExperienceModel):
    """A collection-level experience for browsing several complete show units."""

    type: Literal["show_explorer"]
    title: str
    organization: UnitOrganization = "chronological"
    items: list[ShowUnitBlock] = Field(min_length=1, max_length=8)


class PerformanceUnitBlock(ExperienceModel):
    """One rendition as a primary object, with its set context and listening actions."""

    type: Literal["performance_unit"]
    performance_id: str
    song_id: str
    song_title: str
    show_id: str
    show_date: str | None = None
    show_label: str
    venue_name: str | None = None
    location: str | None = None
    set_label: str | None = None
    position_in_set: str | None = None
    role: UnitRole | None = None
    note: str | None = None
    previous: PerformanceSpineNeighbor | None = None
    next: PerformanceSpineNeighbor | None = None
    listen: list[ListenAction] = Field(default_factory=list, max_length=3)
    sources: list[UnitSource] = Field(default_factory=list, max_length=4)
    follow_up: str | None = None


class EraPerformanceItem(ExperienceModel):
    performance_id: str
    song_id: str
    song_title: str
    show_id: str
    show_date: str | None = None
    show_label: str
    set_label: str | None = None
    listen: ListenAction | None = None
    follow_up: str


class EraUnitBlock(ExperienceModel):
    """A stage of a development the composer names, with representative listening."""

    type: Literal["era_unit"]
    title: str
    span: str | None = None
    role: UnitRole | None = None
    note: str | None = None
    performances: list[EraPerformanceItem] = Field(min_length=1, max_length=6)
    sources: list[UnitSource] = Field(default_factory=list, max_length=4)
    follow_up: str | None = None


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
    # Everything but the title is optional with a default, because this model
    # doubles as the finish_response tool schema: when the optional fields were
    # required-but-nullable, the model's first finish call regularly omitted one
    # and had to be retried, costing a research round on every rich answer.
    marker: str | None = None
    title: str
    value: str | None = None
    detail: str | None = None
    follow_up: str | None = None
    link: EditorialLink | None = None


class EditorialBlock(ExperienceModel):
    """Flexible model-shaped material rendered in one of several visual forms."""

    type: Literal["editorial"]
    presentation: Literal["narrative", "fact_grid", "timeline"]
    eyebrow: str | None = None
    title: str | None = None
    paragraphs: list[str] = Field(default_factory=list, max_length=4)
    items: list[EditorialItem] = Field(default_factory=list, max_length=12)


ExperienceBlock = Annotated[
    EntityCardBlock
    | ShowUnitBlock
    | ShowExplorerBlock
    | PerformanceUnitBlock
    | EraUnitBlock
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
