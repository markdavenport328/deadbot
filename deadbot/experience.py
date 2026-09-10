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


ExperienceMode = Literal["answer", "gap"]


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
    # The composer marks a performance as important; the renderer decides how
    # that looks. A listen URL is the library's per-performance track link, and
    # it is the song's link: a setlist entry leads to its recording.
    highlighted: bool = False
    listen_url: str | None = None


class SetlistSection(ExperienceModel):
    label: str
    songs: list[SetlistSong] = Field(min_length=1, max_length=40)


Emphasis = Literal["primary", "supporting", "mention"]
ShowFacet = Literal["guests", "listen", "setlist", "sources", "lineup", "recordings"]
SongFacet = Literal["credits", "albums", "history", "representatives"]
SetlistDisclosure = Literal["expanded", "collapsed", "hidden"]
GroupPresentation = Literal["collection", "sequence", "comparison", "argument"]


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


class FollowUpTopic(ExperienceModel):
    """A short topic chip the visitor can press, and the full question it stands for.

    The chip shows only the label under "More about"; pressing it sends the
    question, in the visitor's voice, to start a new turn. Only the composer
    writes these; the server never generates one.
    """

    label: str
    question: str


class PerformanceSpineNeighbor(ExperienceModel):
    performance_id: str
    title: str


class ShowSelectionItem(ExperienceModel):
    show_id: str
    show_date: str
    venue_name: str
    location: str | None = None


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


class PerformerItem(ExperienceModel):
    person_id: str
    name: str
    role: Literal["performer", "guest"]
    instruments: list[str] = Field(min_length=1, max_length=8)


class PerformanceListItem(ExperienceModel):
    performance_id: str
    show_id: str
    show_date: str | None = None
    show_label: str
    set_label: str | None = None
    position_in_set: str | None = None
    # The library's track link for this rendition, when it has one; the
    # performance's label links there.
    listen_url: str | None = None


class ComparisonStripItem(ExperienceModel):
    performance_id: str
    show_id: str
    year: int
    show_date: str | None = None
    show_label: str
    set_label: str | None = None
    position_in_set: str | None = None
    listen_url: str | None = None


class SongHistory(ExperienceModel):
    """A song's stage life: first, last, and one performance per year."""

    known_count: int = Field(ge=1)
    first: PerformanceListItem
    last: PerformanceListItem
    by_year: list[ComparisonStripItem] = Field(default_factory=list, max_length=12)


class ShowUnitBlock(ExperienceModel):
    """One show as a primary object of the answer, hydrated from the store.

    The composer supplies the interpretive fields (emphasis, note, highlights,
    preferred recording, sources, follow-up topics); date, venue, setlist, guests and
    listening actions come from canonical data.
    """

    type: Literal["show_unit"]
    show_id: str
    title: str | None = None
    show_date: str
    venue_name: str | None = None
    location: str | None = None
    emphasis: Emphasis = "supporting"
    note: str | None = None
    visible_facets: list[ShowFacet] = Field(default_factory=list, max_length=6)
    setlist_disclosure: SetlistDisclosure = "expanded"
    sets: list[SetlistSection] = Field(default_factory=list, max_length=4)
    setlist_note: str | None = None
    guests: list[PerformerItem] = Field(default_factory=list, max_length=8)
    lineup: list[PerformerItem] = Field(default_factory=list, max_length=24)
    recordings: list[RecordingItem] = Field(default_factory=list, max_length=8)
    judgments: list[str] = Field(default_factory=list, max_length=5)
    listen: list[ListenAction] = Field(default_factory=list, max_length=4)
    sources: list[UnitSource] = Field(default_factory=list, max_length=4)
    follow_ups: list[FollowUpTopic] = Field(default_factory=list, max_length=3)


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
    emphasis: Emphasis = "supporting"
    judgments: list[str] = Field(default_factory=list, max_length=5)
    note: str | None = None
    previous: PerformanceSpineNeighbor | None = None
    next: PerformanceSpineNeighbor | None = None
    listen: list[ListenAction] = Field(default_factory=list, max_length=3)
    sources: list[UnitSource] = Field(default_factory=list, max_length=4)
    follow_ups: list[FollowUpTopic] = Field(default_factory=list, max_length=3)


class EraPerformanceItem(ExperienceModel):
    performance_id: str
    song_id: str
    song_title: str
    show_id: str
    show_date: str | None = None
    show_label: str
    set_label: str | None = None
    listen: ListenAction | None = None


class EraUnitBlock(ExperienceModel):
    """A stage of a development the composer names, with representative listening."""

    type: Literal["era_unit"]
    title: str
    span: str | None = None
    note: str | None = None
    performances: list[EraPerformanceItem] = Field(min_length=1, max_length=6)
    sources: list[UnitSource] = Field(default_factory=list, max_length=4)
    follow_ups: list[FollowUpTopic] = Field(default_factory=list, max_length=3)


class AlbumTrackItem(ExperienceModel):
    track_number: int = Field(ge=1)
    title: str
    song_id: str | None = None
    performance_id: str | None = None
    duration_seconds: int | None = Field(default=None, ge=0)
    highlighted: bool = False
    listen_url: str | None = None


class AlbumCreditItem(ExperienceModel):
    """One person's credit on a record, mirroring `release_personnel`."""

    person_id: str
    name: str
    role: str
    instrument: str


class AlbumUnitBlock(ExperienceModel):
    """One official record as a whole object: what is on it and who made it."""

    type: Literal["album_unit"]
    release_id: str
    title: str
    artist_name: str | None = None
    release_date: str | None = None
    release_type: str
    emphasis: Emphasis = "supporting"
    judgments: list[str] = Field(default_factory=list, max_length=5)
    note: str | None = None
    tracks: list[AlbumTrackItem] = Field(default_factory=list, max_length=30)
    personnel: list[AlbumCreditItem] = Field(default_factory=list, max_length=20)
    listen: list[ListenAction] = Field(default_factory=list, max_length=3)
    sources: list[UnitSource] = Field(default_factory=list, max_length=4)
    follow_ups: list[FollowUpTopic] = Field(default_factory=list, max_length=3)


class GuestAppearanceItem(ExperienceModel):
    show_id: str
    show_date: str
    venue_name: str | None = None
    location: str | None = None
    instruments: list[str] = Field(min_length=1, max_length=8)
    participation_scope: str | None = None


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


class CreditListBlock(ExperienceModel):
    type: Literal["credit_list"]
    title: str
    items: list[CreditItem] = Field(min_length=1, max_length=12)
    source_ids: list[str] = Field(min_length=1, max_length=8)


class SongReleaseItem(ExperienceModel):
    release_id: str
    title: str
    release_date: str | None = None
    release_type: str


class SongRepresentativePerformance(ExperienceModel):
    """A model-chosen rendition that gives a song unit an immediate listening path."""

    performance_id: str
    show_id: str
    show_date: str | None = None
    show_label: str
    set_label: str | None = None
    listen_url: str | None = None


class SongOverviewBlock(ExperienceModel):
    type: Literal["song_overview"]
    song_id: str
    title: str
    original_artist: str | None = None
    known_performance_count: int
    emphasis: Emphasis = "supporting"
    judgments: list[str] = Field(default_factory=list, max_length=5)
    visible_facets: list[SongFacet] = Field(default_factory=lambda: ["representatives"], max_length=4)
    history: SongHistory | None = None
    note: str | None = None
    representative_performances: list[SongRepresentativePerformance] = Field(default_factory=list, max_length=3)
    credits: list[CreditItem] = Field(default_factory=list, max_length=12)
    source_ids: list[str] = Field(default_factory=list, max_length=8)
    albums: list[SongReleaseItem] = Field(default_factory=list, max_length=6)
    sources: list[UnitSource] = Field(default_factory=list, max_length=4)
    follow_ups: list[FollowUpTopic] = Field(default_factory=list, max_length=3)


class MediaLinkBlock(ExperienceModel):
    type: Literal["media_link"]
    title: str
    provider: str
    url: str
    link_type: str
    is_official: bool
    embed_kind: Literal["spotify", "youtube"] | None = None
    embed_id: str | None = None


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
    marker: str | None = Field(
        default=None,
        description="A short label that classifies or indexes this item and renders as small type above the subject: a year, a date, a set position, or a category such as 'The skeptical view'. Never the subject itself.",
    )
    title: str = Field(
        description="The specific subject of this item, rendered as its heading: a song, show, person, place, fact, or claim. Put measurements and assessments in value or detail."
    )
    value: str | None = Field(
        default=None,
        description="The concise measurement or assessment for the subject, such as '330 performances, 1972–1995' or 'Track six'. A short value renders as display type; a sentence renders as text.",
    )
    detail: str | None = Field(
        default=None,
        description="One or two sentences of context or evidence for this item.",
    )
    # Short topic chips under "More about", each carrying the full question it
    # sends. Only the composer writes these; the server never generates one.
    follow_ups: list[FollowUpTopic] = Field(
        default_factory=list,
        max_length=3,
        description=(
            "Up to three topics the visitor might want more about, each a short label plus the specific question it "
            "opens when pressed, rendered as chips under 'More about'."
        ),
    )
    link: EditorialLink | None = Field(
        default=None,
        description="An outbound link for this item; kept only when its URL appeared in a tool result this turn.",
    )


class EditorialBlock(ExperienceModel):
    """Flexible model-shaped material rendered in one of several visual forms."""

    type: Literal["editorial"]
    presentation: Literal["narrative", "fact_grid", "timeline"] = Field(
        description="narrative for prose; fact_grid for a compact set judged on shared terms, including attributed viewpoints; timeline for a sequence."
    )
    eyebrow: str | None = None
    title: str | None = None
    paragraphs: list[str] = Field(default_factory=list, max_length=4)
    items: list[EditorialItem] = Field(default_factory=list, max_length=12)


ExperienceBlock = Annotated[
    EntityCardBlock
    | ShowUnitBlock
    | PerformanceUnitBlock
    | EraUnitBlock
    | AlbumUnitBlock
    | ShowSelectionBlock
    | GuestAppearanceListBlock
    | EquipmentListBlock
    | ResourceListBlock
    | CreditListBlock
    | SongOverviewBlock
    | MediaLinkBlock
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


class ExperienceGroup(ExperienceModel):
    """A model-selected relationship between one or more body blocks.

    ``block_indexes`` preserves the composer's reading order after references
    have been resolved. The browser only renders this supported presentation;
    it never re-groups or re-orders the material.
    """

    title: str | None = None
    lead: str | None = None
    presentation: GroupPresentation
    criteria: list[str] = Field(default_factory=list, max_length=5)
    block_indexes: list[int] = Field(min_length=1, max_length=12)


class ExperienceResponse(ExperienceModel):
    schema_version: Literal["2"] = "2"
    thread_id: str
    title: str
    answer: str
    body_lead: str | None = None
    mode: ExperienceMode = "answer"
    conversation: list[ConversationTurn] = Field(default_factory=list, max_length=50)
    blocks: list[ExperienceBlock] = Field(default_factory=list, max_length=32)
    groups: list[ExperienceGroup] = Field(default_factory=list, max_length=8)
    # A 32-block exploratory response can legitimately reference more than one
    # source per block (for example, show identity plus a recording path).
    sources: list[SourceReference] = Field(default_factory=list, max_length=64)
