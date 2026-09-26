"""Versioned, validated experience schema for the browser client.

This module defines the allowlisted block schema Deadbot's server sends to the
browser: Pydantic block models, the discriminated ``ExperienceBlock`` union,
request/response envelopes, and layout/source references. Every browser-facing
payload is validated against these models, so neither the block builders in
:mod:`deadbot.composition` nor the response assembly in :mod:`deadbot.finish`
can pass browser code, raw HTML, or arbitrary embeds to the client.
"""

from __future__ import annotations

import logging
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


logger = logging.getLogger(__name__)


ExperienceMode = Literal["answer", "gap"]

# Transport ceilings. They sit far above any real answer and exist only so a
# runaway plan or record cannot produce an unbounded payload; code that fills a
# list truncates to them with a log line (see ``fit``). They are not editorial
# limits on how much the model may show.
LIST_CEILING = 1000
PAGE_BLOCK_CEILING = 200


def fit(items: list[Any], what: str) -> list[Any]:
    """``items`` within ``LIST_CEILING``, logging when anything is cut."""

    if len(items) <= LIST_CEILING:
        return items
    logger.warning("Truncated %d %s to the transport ceiling of %d", len(items), what, LIST_CEILING)
    return items[:LIST_CEILING]


class ExperienceModel(BaseModel):
    """Base model that rejects unrecognized browser-facing fields."""

    model_config = ConfigDict(extra="forbid")


class ModelAuthored(ExperienceModel):
    """A browser model the finish plan also uses as written by the model.

    A key the schema does not name is ignored rather than failing the item,
    so an extra field the model adds never costs the visitor its content.
    """

    model_config = ConfigDict(extra="ignore")


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
    details: list[str] = Field(default_factory=list, max_length=LIST_CEILING)
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
    # The playable Internet Archive track for the in-page player, when the
    # library has one; distinct from listen_url, which may point to a
    # Spotify or YouTube destination instead of an audio file the browser
    # can play directly.
    audio_url: str | None = None
    duration_seconds: int | None = Field(default=None, ge=0)
    segue_into_next: bool = False


class SetlistSection(ExperienceModel):
    label: str
    songs: list[SetlistSong] = Field(min_length=1, max_length=LIST_CEILING)


Emphasis = Literal["primary", "supporting", "mention"]
ShowFacet = Literal["guests", "listen", "setlist", "sources", "lineup", "recordings"]
SongFacet = Literal["credits", "albums", "history", "representatives", "by_year"]
PerformanceFacet = Literal["setlist", "listen", "sources"]
SetlistDisclosure = Literal["expanded", "collapsed", "hidden"]
# How a record card starts: expanded is the full card; collapsed is one
# compact row the server fills in, which opens into the full card in place.
CardDisclosure = Literal["collapsed", "expanded"]
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


class FollowUpTopic(ModelAuthored):
    """A short topic chip the visitor can press, and the full question it stands for.

    The chip shows only the label under "More about"; pressing it sends the
    question, in the visitor's voice, to start a new turn. Only the composer
    writes these; the server never generates one.
    """

    label: str
    question: str


class PlayableTrack(ExperienceModel):
    """One Internet Archive track the in-page player can play, in show order."""

    performance_id: str
    title: str
    audio_url: str
    duration_seconds: int | None = Field(default=None, ge=0)
    set_label: str | None = None


class PerformanceSpineNeighbor(ExperienceModel):
    performance_id: str
    title: str


class ShowSelectionItem(ExperienceModel):
    show_id: str
    show_date: str
    venue_name: str
    location: str | None = None
    # One tape's playable tracks for the show, in show order, so the row can
    # play the show in-page. Empty when the library has no archive track.
    tracks: list[PlayableTrack] = Field(default_factory=list, max_length=LIST_CEILING)
    recording_identifier: str | None = None


class ShowSelectionBlock(ExperienceModel):
    """A clearly attributed selection of shows from one reviewed source."""

    type: Literal["show_selection"]
    title: str
    selection_type: str
    selector_name: str
    coverage_note: str
    source_id: str
    items: list[ShowSelectionItem] = Field(min_length=1, max_length=LIST_CEILING)


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
    instruments: list[str] = Field(min_length=1, max_length=LIST_CEILING)


class PerformanceListItem(ExperienceModel):
    performance_id: str
    show_id: str
    show_date: str | None = None
    show_label: str
    set_label: str | None = None
    position_in_set: str | None = None
    venue_name: str | None = None
    # The library's track link for this rendition, when it has one; the
    # performance's label links there.
    listen_url: str | None = None
    # The Internet Archive track the in-page player plays for this rendition,
    # when the library has one, and its length.
    audio_url: str | None = None
    duration_seconds: int | None = Field(default=None, ge=0)


class ComparisonStripItem(ExperienceModel):
    performance_id: str
    show_id: str
    year: int
    show_date: str | None = None
    show_label: str
    set_label: str | None = None
    position_in_set: str | None = None
    venue_name: str | None = None
    listen_url: str | None = None
    # The Internet Archive track the in-page player plays for this rendition,
    # when the library has one, and its length.
    audio_url: str | None = None
    duration_seconds: int | None = Field(default=None, ge=0)


class SongHistory(ExperienceModel):
    """A song's stage life: first, last, and one performance per year."""

    known_count: int = Field(ge=1)
    first: PerformanceListItem
    last: PerformanceListItem
    by_year: list[ComparisonStripItem] = Field(default_factory=list, max_length=LIST_CEILING)


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
    disclosure: CardDisclosure = "expanded"
    # The show's playable tape, in show order, for the collapsed row's one
    # play control. Filled only when the card starts collapsed.
    tracks: list[PlayableTrack] = Field(default_factory=list, max_length=LIST_CEILING)
    note: str | None = None
    visible_facets: list[ShowFacet] = Field(default_factory=list, max_length=LIST_CEILING)
    setlist_disclosure: SetlistDisclosure = "expanded"
    sets: list[SetlistSection] = Field(default_factory=list, max_length=LIST_CEILING)
    setlist_note: str | None = None
    # The Internet Archive item behind this setlist's playable tracks, once
    # per show rather than repeated on every song: the in-page player's
    # thumbnail and its "Tape on the Internet Archive" link are both derived
    # from this identifier.
    recording_identifier: str | None = None
    recording_details_url: str | None = None
    guests: list[PerformerItem] = Field(default_factory=list, max_length=LIST_CEILING)
    lineup: list[PerformerItem] = Field(default_factory=list, max_length=LIST_CEILING)
    recordings: list[RecordingItem] = Field(default_factory=list, max_length=LIST_CEILING)
    judgments: list[str] = Field(default_factory=list, max_length=LIST_CEILING)
    listen: list[ListenAction] = Field(default_factory=list, max_length=LIST_CEILING)
    sources: list[UnitSource] = Field(default_factory=list, max_length=LIST_CEILING)
    follow_ups: list[FollowUpTopic] = Field(default_factory=list, max_length=LIST_CEILING)


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
    disclosure: CardDisclosure = "expanded"
    # This rendition's own Internet Archive track and length, when the library has one.
    audio_url: str | None = None
    duration_seconds: int | None = Field(default=None, ge=0)
    judgments: list[str] = Field(default_factory=list, max_length=LIST_CEILING)
    note: str | None = None
    visible_facets: list[PerformanceFacet] = Field(default_factory=lambda: ["setlist", "listen", "sources"], max_length=LIST_CEILING)
    previous: PerformanceSpineNeighbor | None = None
    next: PerformanceSpineNeighbor | None = None
    listen: list[ListenAction] = Field(default_factory=list, max_length=LIST_CEILING)
    # The show's playable tracks from the same tape as this rendition, in show
    # order, so a full-show action on the Internet Archive can play in-page.
    # Empty when the library has no archive track for this performance.
    show_tracks: list[PlayableTrack] = Field(default_factory=list, max_length=LIST_CEILING)
    sources: list[UnitSource] = Field(default_factory=list, max_length=LIST_CEILING)
    follow_ups: list[FollowUpTopic] = Field(default_factory=list, max_length=LIST_CEILING)


class EraPerformanceItem(ExperienceModel):
    performance_id: str
    song_id: str
    song_title: str
    show_id: str
    show_date: str | None = None
    show_label: str
    set_label: str | None = None
    venue_name: str | None = None
    listen: ListenAction | None = None
    # The Internet Archive track the in-page player plays for this rendition,
    # when the library has one, and its length.
    audio_url: str | None = None
    duration_seconds: int | None = Field(default=None, ge=0)


class EraUnitBlock(ExperienceModel):
    """A stage of a development the composer names, with representative listening."""

    type: Literal["era_unit"]
    title: str
    span: str | None = None
    note: str | None = None
    performances: list[EraPerformanceItem] = Field(min_length=1, max_length=LIST_CEILING)
    sources: list[UnitSource] = Field(default_factory=list, max_length=LIST_CEILING)
    follow_ups: list[FollowUpTopic] = Field(default_factory=list, max_length=LIST_CEILING)


class AlbumTrackItem(ExperienceModel):
    track_number: int = Field(ge=1)
    title: str
    song_id: str | None = None
    performance_id: str | None = None
    duration_seconds: int | None = Field(default=None, ge=0)
    highlighted: bool = False
    listen_url: str | None = None
    # A live record's track, when its performance has an Internet Archive
    # track: what the in-page player plays, its length, and the show it is from.
    audio_url: str | None = None
    audio_duration_seconds: int | None = Field(default=None, ge=0)
    show_date: str | None = None
    venue_name: str | None = None


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
    # The record's own name from the library, kept apart from ``title`` so the
    # card can name the record even when the model wrote the headline.
    release_title: str | None = None
    artist_name: str | None = None
    release_date: str | None = None
    release_type: str
    emphasis: Emphasis = "supporting"
    disclosure: CardDisclosure = "expanded"
    cover_url: str | None = None
    # The shows the record draws on: one show names its venue and date; more
    # give their count and span. Zero for a studio record.
    show_count: int = Field(default=0, ge=0)
    first_show_date: str | None = None
    last_show_date: str | None = None
    show_venue_name: str | None = None
    show_location: str | None = None
    judgments: list[str] = Field(default_factory=list, max_length=LIST_CEILING)
    note: str | None = None
    tracks: list[AlbumTrackItem] = Field(default_factory=list, max_length=LIST_CEILING)
    personnel: list[AlbumCreditItem] = Field(default_factory=list, max_length=LIST_CEILING)
    listen: list[ListenAction] = Field(default_factory=list, max_length=LIST_CEILING)
    sources: list[UnitSource] = Field(default_factory=list, max_length=LIST_CEILING)
    follow_ups: list[FollowUpTopic] = Field(default_factory=list, max_length=LIST_CEILING)


class GuestAppearanceSong(ExperienceModel):
    """One song a guest is credited on, from performance_performers."""

    performance_id: str
    song_title: str
    note: str | None = None
    # The Internet Archive track the in-page player plays for this rendition,
    # when the library has one, and its length.
    audio_url: str | None = None
    duration_seconds: int | None = Field(default=None, ge=0)


class GuestAppearanceItem(ExperienceModel):
    show_id: str
    show_date: str
    venue_name: str | None = None
    location: str | None = None
    instruments: list[str] = Field(min_length=1, max_length=LIST_CEILING)
    participation_scope: str | None = None
    # Empty when the credit is known only at the show level.
    songs: list[GuestAppearanceSong] = Field(default_factory=list, max_length=LIST_CEILING)


class GuestAppearanceListBlock(ExperienceModel):
    """Canonical guest-show relationships for one resolved person."""

    type: Literal["guest_appearance_list"]
    person_id: str
    person_name: str
    known_show_count: int = Field(ge=1)
    items: list[GuestAppearanceItem] = Field(min_length=1, max_length=LIST_CEILING)


class PersonRosterItem(ExperienceModel):
    """One person in a roster: identity and appearance facts from the store, one note from the model."""

    person_id: str
    name: str
    roles: list[str] = Field(default_factory=list, max_length=LIST_CEILING)
    show_count: int = Field(ge=0)
    first_year: str | None = None
    last_year: str | None = None
    note: str | None = None


class PersonRosterBlock(ExperienceModel):
    """A complete set of people, organized under one model-chosen heading.

    The inventory component for questions that ask for everyone: the model
    names the section and chooses who belongs in it; the server supplies each
    person's name, roles, show count and span.
    """

    type: Literal["person_roster"]
    title: str
    lead: str | None = None
    items: list[PersonRosterItem] = Field(min_length=1, max_length=LIST_CEILING)


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
    items: list[EquipmentItem] = Field(min_length=1, max_length=LIST_CEILING)


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
    items: list[ResourceItem] = Field(min_length=1, max_length=LIST_CEILING)


class CreditItem(ExperienceModel):
    person_id: str
    name: str
    role: str


class CreditListBlock(ExperienceModel):
    type: Literal["credit_list"]
    title: str
    items: list[CreditItem] = Field(min_length=1, max_length=LIST_CEILING)
    source_ids: list[str] = Field(min_length=1, max_length=LIST_CEILING)


class SongReleaseItem(ExperienceModel):
    release_id: str
    title: str
    release_date: str | None = None
    release_type: str
    # Where to hear the release, when the library has a link for it.
    listen_url: str | None = None


class SongRepresentativePerformance(ExperienceModel):
    """A model-chosen rendition that gives a song unit an immediate listening path."""

    performance_id: str
    show_id: str
    show_date: str | None = None
    show_label: str
    set_label: str | None = None
    venue_name: str | None = None
    listen_url: str | None = None
    # The Internet Archive track the in-page player plays for this rendition,
    # when the library has one, and its length.
    audio_url: str | None = None
    duration_seconds: int | None = Field(default=None, ge=0)


class SongYearCount(ExperienceModel):
    """How many times a song was played in one year; a year with none is zero."""

    year: int
    count: int = Field(ge=0)


class SongOverviewBlock(ExperienceModel):
    type: Literal["song_overview"]
    song_id: str
    title: str
    original_artist: str | None = None
    known_performance_count: int
    first_year: int | None = None
    last_year: int | None = None
    emphasis: Emphasis = "supporting"
    disclosure: CardDisclosure = "expanded"
    judgments: list[str] = Field(default_factory=list, max_length=LIST_CEILING)
    visible_facets: list[SongFacet] = Field(default_factory=lambda: ["representatives"], max_length=LIST_CEILING)
    history: SongHistory | None = None
    # Every year from the song's first performance to its last, zero years included.
    year_counts: list[SongYearCount] = Field(default_factory=list, max_length=LIST_CEILING)
    note: str | None = None
    representative_performances: list[SongRepresentativePerformance] = Field(default_factory=list, max_length=LIST_CEILING)
    credits: list[CreditItem] = Field(default_factory=list, max_length=LIST_CEILING)
    source_ids: list[str] = Field(default_factory=list, max_length=LIST_CEILING)
    albums: list[SongReleaseItem] = Field(default_factory=list, max_length=LIST_CEILING)
    sources: list[UnitSource] = Field(default_factory=list, max_length=LIST_CEILING)
    follow_ups: list[FollowUpTopic] = Field(default_factory=list, max_length=LIST_CEILING)


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
    progressions: list[str] = Field(default_factory=list, max_length=LIST_CEILING)


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
    items: list[ArrangementSearchItem] = Field(min_length=1, max_length=LIST_CEILING)


class DataChartColumn(ExperienceModel):
    key: str
    label: str
    type: Literal["temporal", "categorical", "quantitative"]


class DataChartBlock(ExperienceModel):
    """A model-selected chart, hydrated entirely from one verified
    aggregate_data result.

    Every number here is server-computed from that exact result; the
    model chose only which aggregation to reference and how to frame it
    (title/note). The server derives orientation from the dimension
    column's type (temporal -> vertical, else horizontal) and finds the
    dimension column itself (the one whose key isn't "value") at render
    time, so no field mapping travels through this block at all.
    """

    type: Literal["data_chart"]
    aggregation_id: str
    title: str
    note: str | None = None
    chart: Literal["bar"]
    orientation: Literal["vertical", "horizontal"]
    columns: list[DataChartColumn] = Field(min_length=2, max_length=2)
    rows: list[dict[str, object]] = Field(default_factory=list, max_length=200)
    metric_label: str
    total: int
    excluded_count: int
    date_range: dict[str, int] | None = None
    empty_reason: str | None = None


class VersionStripSong(ExperienceModel):
    song_id: str
    title: str


class VersionStripRow(ExperienceModel):
    """One night's pairing: the two tape tracks the row plays in turn."""

    pair_id: str
    show_id: str
    show_date: str
    # A show is named by its venue and date together.
    venue_name: str
    location: str | None = None
    segue: bool
    first_performance_id: str
    second_performance_id: str
    first_seconds: int | None = Field(default=None, ge=0)
    second_seconds: int | None = Field(default=None, ge=0)
    first_track: PlayableTrack | None = None
    second_track: PlayableTrack | None = None


class VersionStripYear(ExperienceModel):
    year: int
    count: int = Field(ge=0)


class VersionStripBlock(ExperienceModel):
    """Chosen nights of one song pairing, drawn to one clock.

    The model chose the pairing, the nights, their order and the framing; the
    server hydrated each night's venue, date, tape-track lengths and playable
    tracks from the library, and the per-year counts when the model asked for
    them.
    """

    type: Literal["version_strip"]
    pairing_id: str
    title: str | None = None
    note: str | None = None
    first_song: VersionStripSong
    second_song: VersionStripSong
    total_count: int = Field(ge=0)
    rows: list[VersionStripRow] = Field(min_length=1, max_length=LIST_CEILING)
    year_counts: list[VersionStripYear] = Field(default_factory=list, max_length=LIST_CEILING)


class ProvenanceNoteBlock(ExperienceModel):
    type: Literal["provenance_note"]
    text: str
    source_ids: list[str] = Field(min_length=1, max_length=LIST_CEILING)


class GapStateBlock(ExperienceModel):
    type: Literal["gap_state"]
    message: str


class EditorialLink(ModelAuthored):
    """An outbound link the model attaches to something it wrote.

    The server keeps a link only when its URL appeared in material the tools
    returned during the same turn; anything else is dropped before rendering.
    """

    url: str
    label: str


class ListeningHeroBlock(ExperienceModel):
    """The page's lead when the answer is best heard: a cover, a name and one Play.

    The model chooses the show or record, writes the line and the Play words,
    and says where playback starts; the server hydrates identity, the image,
    and the playable queue from the library.
    """

    type: Literal["listening_hero"]
    show_id: str | None = None
    release_id: str | None = None
    # A show is named by its venue and date together; a record by its title.
    venue_name: str | None = None
    location: str | None = None
    show_date: str | None = None
    release_title: str | None = None
    release_date: str | None = None
    line: str | None = None
    play_label: str | None = None
    # The in-page queue, in listening order, and where playback starts in it.
    queue: list[PlayableTrack] = Field(default_factory=list, max_length=LIST_CEILING)
    start_index: int = Field(default=0, ge=0)
    # Where Play goes when nothing is playable in-page: the official release
    # or the show's stream.
    play_url: str | None = None
    recording_identifier: str | None = None
    recording_details_url: str | None = None
    image_url: str | None = None
    image_alt: str | None = None
    link: EditorialLink | None = None


class PullQuoteBlock(ModelAuthored):
    """One sentence the model sets apart, large, as the page's pulled line."""

    type: Literal["pull_quote"]
    text: str = Field(
        min_length=1,
        description="One sentence, in your voice, that states the idea the visitor should carry away.",
    )


class EditorialItemText(ModelAuthored):
    """The words of one editorial item, as the model writes them."""

    # Everything but the title is optional with a default, because this model
    # doubles as the finish_response tool schema: when the optional fields were
    # required-but-nullable, the model's first finish call regularly omitted one
    # and had to be retried, costing a research round on every rich answer.
    marker: str | None = Field(
        default=None,
        description="A short label that classifies or indexes this item and renders as small type above the subject: a year, a date, a set position, or a category such as 'The skeptical view'. Never the subject itself.",
    )
    title: str = Field(
        description="The specific subject of this item, rendered as its heading: a claim, a viewpoint, a place, a person, or a record you name. Put your assessment in value or detail."
    )
    value: str | None = Field(
        default=None,
        description="Your concise assessment of the subject, such as 'The high-water mark' or 'Looser, faster'. A short value renders as display type; a sentence renders as text.",
    )
    detail: str | None = Field(
        default=None,
        description="One or two sentences of context or evidence for this item.",
    )
    # Short topic chips under "More about", each carrying the full question it
    # sends. Only the composer writes these; the server never generates one.
    follow_ups: list[FollowUpTopic] = Field(
        default_factory=list,
        max_length=LIST_CEILING,
        description=(
            "Up to three topics the visitor might want more about, each a short label plus the specific question it "
            "opens when pressed, rendered as chips under 'More about'."
        ),
    )
    link: EditorialLink | None = Field(
        default=None,
        description="A link to an outside article or page this item draws on. For a show, performance or record, name it by ID instead and the server links it.",
    )


class EditorialItem(EditorialItemText):
    """One editorial item as the browser receives it."""

    # A show's or performance's playable tape tracks, when the item names one
    # and the library has them; the item's title plays them in-page.
    tracks: list[PlayableTrack] = Field(default_factory=list, max_length=LIST_CEILING)


def read_editorial_shape(data: Any) -> Any:
    """A fact-grid row written as a whole block becomes that block's one item,
    and a block without a presentation gets one from its shape.

    In a comparison the model sometimes writes each row as its own editorial
    block, with the item fields (value, detail, marker) beside the title. The
    row's fields move into one item, so the material the model meant survives
    in both the streamed and the delivered page.
    """

    if not isinstance(data, dict):
        return data
    row_keys = [key for key in ("value", "detail", "marker") if key in data]
    title = data.get("title")
    if row_keys and not data.get("items") and isinstance(title, str) and title.strip():
        item = {"title": title, **{key: data[key] for key in row_keys}}
        data = {key: value for key, value in data.items() if key not in row_keys}
        data["items"] = [item]
        data.setdefault("presentation", "fact_grid")
    if not data.get("presentation"):
        # Items alone read as a fact grid; anything else as a narrative.
        data = {**data, "presentation": "fact_grid" if data.get("items") and not data.get("paragraphs") else "narrative"}
    return data


class EditorialBlock(ModelAuthored):
    """Prose, viewpoints and comparisons in the model's own words, rendered in one of several forms."""

    @model_validator(mode="before")
    @classmethod
    def _read_shape(cls, data: Any) -> Any:
        return read_editorial_shape(data)

    type: Literal["editorial"]
    presentation: Literal["narrative", "fact_grid", "timeline"] = Field(
        default="narrative",
        description="narrative for prose; fact_grid for a compact set judged on shared terms, including attributed viewpoints; timeline for a sequence."
    )
    eyebrow: str | None = None
    title: str | None = None
    paragraphs: list[str] = Field(default_factory=list, max_length=LIST_CEILING)
    items: list[EditorialItem] = Field(default_factory=list, max_length=LIST_CEILING)


class RankedListRow(ExperienceModel):
    rank: int = Field(ge=1)
    # The row's record ID (a song, venue or guest), when the result has one.
    id: str | None = None
    label: str
    value: int
    note: str | None = None


class RankedListBlock(ExperienceModel):
    """The top rows of one aggregate_data result, ranked, with the model's notes on the rows it chose."""

    type: Literal["ranked_list"]
    aggregation_id: str
    title: str
    note: str | None = None
    dimension_label: str
    metric_label: str
    rows: list[RankedListRow] = Field(min_length=1, max_length=LIST_CEILING)
    # Rows of the result not shown.
    more_count: int = Field(default=0, ge=0)


ExperienceBlock = Annotated[
    EntityCardBlock
    | ShowUnitBlock
    | PerformanceUnitBlock
    | EraUnitBlock
    | AlbumUnitBlock
    | ShowSelectionBlock
    | GuestAppearanceListBlock
    | PersonRosterBlock
    | EquipmentListBlock
    | ResourceListBlock
    | CreditListBlock
    | SongOverviewBlock
    | MediaLinkBlock
    | CoverageBlock
    | ArrangementBlock
    | ArrangementSearchBlock
    | DataChartBlock
    | VersionStripBlock
    | ProvenanceNoteBlock
    | GapStateBlock
    | EditorialBlock
    | ListeningHeroBlock
    | PullQuoteBlock
    | RankedListBlock,
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
    criteria: list[str] = Field(default_factory=list, max_length=LIST_CEILING)
    block_indexes: list[int] = Field(min_length=1, max_length=PAGE_BLOCK_CEILING)


class ExperienceResponse(ExperienceModel):
    schema_version: Literal["2"] = "2"
    thread_id: str
    title: str
    answer: str
    body_lead: str | None = None
    mode: ExperienceMode = "answer"
    conversation: list[ConversationTurn] = Field(default_factory=list, max_length=50)
    blocks: list[ExperienceBlock] = Field(default_factory=list, max_length=PAGE_BLOCK_CEILING)
    groups: list[ExperienceGroup] = Field(default_factory=list, max_length=LIST_CEILING)
    # A 32-block exploratory response can legitimately reference more than one
    # source per block (for example, show identity plus a recording path).
    sources: list[SourceReference] = Field(default_factory=list, max_length=LIST_CEILING)
