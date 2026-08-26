"""Validated, deterministic experience responses for the browser client.

The experience layer intentionally receives only tool outputs that have already
passed through Deadbot's read-only agent. It builds an allowlisted block schema;
neither this adapter nor a future model-guided composer can pass browser code,
raw HTML, or arbitrary embeds to the client.
"""

from __future__ import annotations

import json
from collections.abc import Iterable
from typing import Annotated, Any, Literal
from urllib.parse import parse_qs, urlparse

from pydantic import BaseModel, ConfigDict, Field

from deadbot.data import CanonicalStore


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


class ResourceItem(ExperienceModel):
    resource_id: str
    title: str
    resource_type: str
    source_name: str
    url: str
    source_id: str


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
    show_date: str | None = None
    set_label: str | None = None
    position_in_set: str | None = None


class PerformanceListBlock(ExperienceModel):
    type: Literal["performance_list"]
    title: str
    song_id: str
    known_count: int
    items: list[PerformanceListItem] = Field(min_length=1, max_length=20)


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
    progressions: list[str] = Field(default_factory=list, max_length=6)


class ProvenanceNoteBlock(ExperienceModel):
    type: Literal["provenance_note"]
    text: str
    source_ids: list[str] = Field(min_length=1, max_length=8)


class GapStateBlock(ExperienceModel):
    type: Literal["gap_state"]
    message: str


ExperienceBlock = Annotated[
    EntityCardBlock
    | ResourceListBlock
    | CreditListBlock
    | MediaLinkBlock
    | PerformanceListBlock
    | CoverageBlock
    | ArrangementBlock
    | ProvenanceNoteBlock
    | GapStateBlock,
    Field(discriminator="type"),
]


class ExperienceRequest(ExperienceModel):
    question: str = Field(min_length=1, max_length=2_000)
    thread_id: str | None = Field(default=None, min_length=1, max_length=200)


class ConversationTurn(ExperienceModel):
    """A browser-safe projection of one human or final assistant message."""

    role: Literal["user", "assistant"]
    text: str = Field(min_length=1, max_length=8_000)


class LayoutSection(ExperienceModel):
    """A server-validated region in the composed main column."""

    region: Literal["primary", "supporting", "context", "media"]
    block_indexes: list[int] = Field(min_length=1, max_length=8)


class ExperienceResponse(ExperienceModel):
    schema_version: Literal["1"] = "1"
    thread_id: str
    title: str
    answer: str
    conversation: list[ConversationTurn] = Field(default_factory=list, max_length=50)
    blocks: list[ExperienceBlock] = Field(default_factory=list, max_length=16)
    layout: list[LayoutSection] = Field(default_factory=list, max_length=4)
    sources: list[SourceReference] = Field(default_factory=list, max_length=32)


def _content_text(content: Any) -> str:
    """Normalize LangChain message content without exposing rich message data."""

    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "".join(item.get("text", "") for item in content if isinstance(item, dict))
    return ""


def _tool_payloads(messages: Iterable[Any]) -> list[dict[str, Any]]:
    payloads = []
    for message in messages:
        if getattr(message, "type", None) != "tool":
            continue
        try:
            payload = json.loads(_content_text(getattr(message, "content", "")))
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict):
            payloads.append(payload)
    return payloads


def _final_answer(messages: Iterable[Any]) -> str:
    for message in reversed(list(messages)):
        if getattr(message, "type", None) == "ai":
            answer = _content_text(getattr(message, "content", "")).strip()
            if answer:
                return answer
    return "I could not produce a grounded answer from the current library."


def _latest_turn(messages: list[Any]) -> list[Any]:
    """Return only the most recent user turn and its tool/answer messages.

    LangGraph's checkpoint contains the full conversation for model context. The
    main panel should refresh to the current request, rather than accumulating
    cards and links from earlier turns.
    """

    for index in range(len(messages) - 1, -1, -1):
        if getattr(messages[index], "type", None) == "human":
            return messages[index:]
    return messages


def _conversation_turns(messages: Iterable[Any]) -> list[ConversationTurn]:
    turns: list[ConversationTurn] = []
    for message in messages:
        message_type = getattr(message, "type", None)
        role = "user" if message_type == "human" else "assistant" if message_type == "ai" else None
        if not role:
            continue
        text = _content_text(getattr(message, "content", "")).strip()
        # Tool-call AI messages normally have no visible content. The browser
        # should never show the tool request itself in the conversation thread.
        if text:
            turns.append(ConversationTurn(role=role, text=text))
    return turns[-50:]


def _canonical_source(entity_id: str) -> SourceReference:
    return SourceReference(
        source_id=f"canonical:{entity_id}",
        kind="canonical",
        label="Deadbot canonical data",
    )


def _resource_source(resource: dict[str, Any]) -> SourceReference | None:
    url = resource.get("source_url", "")
    if not url:
        return None
    return SourceReference(
        source_id=f"resource:{resource['resource_id']}",
        kind="contextual_resource",
        label=resource.get("source_name") or resource.get("title") or "Contextual resource",
        url=url,
    )


def _embed_details(platform: str, url: str) -> tuple[Literal["spotify", "youtube"] | None, str | None]:
    """Return an embed identifier only for recognized, trusted provider URLs."""

    parsed = urlparse(url)
    host = parsed.netloc.casefold().removeprefix("www.")
    if platform.casefold() == "youtube" and host in {"youtube.com", "youtu.be", "music.youtube.com"}:
        video_id = parse_qs(parsed.query).get("v", [""])[0]
        if host == "youtu.be":
            video_id = parsed.path.strip("/").split("/")[0]
        if parsed.path.startswith("/embed/"):
            video_id = parsed.path.removeprefix("/embed/").split("/")[0]
        if video_id and all(character.isalnum() or character in "-_" for character in video_id):
            return "youtube", video_id
    if platform.casefold() == "spotify" and host == "open.spotify.com":
        parts = [part for part in parsed.path.split("/") if part]
        if len(parts) >= 2 and parts[0] in {"album", "track", "playlist", "episode", "show"}:
            identifier = parts[1]
            if identifier.isalnum():
                return "spotify", f"{parts[0]}/{identifier}"
    return None, None


def _resource_item(resource: dict[str, Any]) -> ResourceItem | None:
    source = _resource_source(resource)
    if not source:
        return None
    return ResourceItem(
        resource_id=resource["resource_id"],
        title=resource.get("title") or "Untitled resource",
        resource_type=resource.get("resource_type") or "resource",
        source_name=source.label,
        url=source.url or "",
        source_id=source.source_id,
    )


def _media_block(link: dict[str, Any]) -> MediaLinkBlock | None:
    url = link.get("url", "")
    platform = link.get("platform", "")
    if not url or not platform:
        return None
    embed_kind, embed_id = _embed_details(platform, url)
    return MediaLinkBlock(
        type="media_link",
        title=link.get("title") or "Listen or watch",
        provider=platform,
        url=url,
        link_type=link.get("link_type") or "media",
        is_official=link.get("is_official", "").casefold() == "true" if isinstance(link.get("is_official"), str) else bool(link.get("is_official")),
        embed_kind=embed_kind,
        embed_id=embed_id,
    )


def _entity_card_from_song(song: dict[str, Any]) -> EntityCardBlock | None:
    source_id = f"canonical:{song['song_id']}"
    details = [f"Original artist: {song['original_artist']}"] if song.get("original_artist") else []
    # The page already carries the song title. A title-only card adds no useful
    # information, so keep it out of the composed page while retaining the
    # canonical entity in the retrieval result.
    if not details:
        return None
    return EntityCardBlock(
        type="entity_card",
        entity_type="song",
        entity_id=song["song_id"],
        title=song.get("title") or "Untitled song",
        details=details,
        source_id=source_id,
    )


def _entity_card_from_show(payload: dict[str, Any]) -> EntityCardBlock:
    show = payload["show"]
    venue = payload.get("venue") or {}
    source_id = f"canonical:{show['show_id']}"
    venue_label = ", ".join(part for part in [venue.get("name"), venue.get("city"), venue.get("state_region")] if part)
    details = [venue_label] if venue_label else []
    if show.get("event_name"):
        details.append(show["event_name"])
    return EntityCardBlock(
        type="entity_card",
        entity_type="show",
        entity_id=show["show_id"],
        title=show.get("show_date") or "Undated show",
        subtitle=venue.get("name") or None,
        details=details,
        source_id=source_id,
    )


def _entity_card_from_performance(payload: dict[str, Any]) -> EntityCardBlock:
    performance = payload["performance"]
    song = payload.get("song") or {}
    show = payload.get("show") or {}
    source_id = f"canonical:{performance['performance_id']}"
    details = []
    if show.get("show_date"):
        details.append(show["show_date"])
    if performance.get("set_label"):
        details.append(f"{performance['set_label']} · #{performance.get('position_in_set', '?')}")
    return EntityCardBlock(
        type="entity_card",
        entity_type="performance",
        entity_id=performance["performance_id"],
        title=song.get("title") or "Untitled performance",
        subtitle="Performance",
        details=details,
        source_id=source_id,
    )


def _performance_list(song: dict[str, Any], performances: list[dict[str, Any]], store: CanonicalStore) -> PerformanceListBlock | None:
    items = []
    for performance in performances:
        show = store.one("shows", performance.get("show_id", "")) or {}
        items.append(
            PerformanceListItem(
                performance_id=performance["performance_id"],
                show_date=show.get("show_date") or None,
                set_label=performance.get("set_label") or None,
                position_in_set=performance.get("position_in_set") or None,
            )
        )
    if not items:
        return None
    return PerformanceListBlock(
        type="performance_list",
        title="Known performances",
        song_id=song["song_id"],
        known_count=len(items),
        items=items[:20],
    )


def _coverage_block(store: CanonicalStore) -> CoverageBlock:
    dated_shows = [show for show in store.rows("shows") if show.get("show_date", "")]
    years = sorted({show["show_date"][:4] for show in dated_shows})
    performance_song_ids = {
        performance.get("song_id")
        for performance in store.rows("performances")
        if performance.get("song_id")
    }
    if years:
        year_range = f"{years[0]}–{years[-1]}"
    else:
        year_range = "no dated years"
    return CoverageBlock(
        type="coverage",
        title="Current library coverage",
        message=(
            f"The current canonical library contains {len(dated_shows)} dated shows, "
            f"{len(store.rows('performances'))} ordered performances, and "
            f"{len(performance_song_ids)} song labels spanning {year_range}. "
            "This is a source-derived baseline with uneven enrichment; it is not a complete record "
            "of every historical performance or song-related fact."
        ),
    )


def compose_experience_response(
    question: str,
    thread_id: str,
    messages: Iterable[Any],
    store: CanonicalStore,
) -> ExperienceResponse:
    """Create a safe, deterministic response from already-grounded tool output."""

    message_list = list(messages)
    latest_turn_messages = _latest_turn(message_list)
    blocks: list[ExperienceBlock] = []
    sources: list[SourceReference] = []
    seen_entities: set[str] = set()
    seen_resources: set[str] = set()
    seen_media: set[str] = set()
    resource_items: list[ResourceItem] = []
    chord_items: list[ResourceItem] = []
    credit_items: list[CreditItem] = []
    credit_source_ids: list[str] = []
    arrangements: list[ArrangementBlock] = []
    title = "Deadbot"

    def add_source(source: SourceReference | None) -> None:
        if source and source.source_id not in {item.source_id for item in sources}:
            sources.append(source)

    def add_entity(block: EntityCardBlock) -> None:
        nonlocal title
        if block.entity_id not in seen_entities:
            seen_entities.add(block.entity_id)
            blocks.append(block)
            add_source(_canonical_source(block.entity_id))
            if title == "Deadbot":
                title = block.title

    def add_resources(resources: Iterable[dict[str, Any]]) -> None:
        for resource in resources:
            resource_id = resource.get("resource_id")
            if not resource_id or resource_id in seen_resources:
                continue
            item = _resource_item(resource)
            if not item:
                continue
            seen_resources.add(resource_id)
            add_source(_resource_source(resource))
            if resource.get("resource_type") in {"tab", "chord_chart"}:
                chord_items.append(item)
            else:
                resource_items.append(item)

    def add_media(links: Iterable[dict[str, Any]]) -> None:
        for link in links:
            url = link.get("url")
            if not url or url in seen_media:
                continue
            block = _media_block(link)
            if block:
                seen_media.add(url)
                blocks.append(block)

    def add_credits(payload: dict[str, Any]) -> None:
        writers = payload.get("writers")
        song = payload.get("song") or {}
        if not isinstance(writers, list) or not isinstance(song, dict):
            return
        for writer in writers:
            if not isinstance(writer, dict):
                continue
            person_id = writer.get("person_id", "")
            person = store.one("people", person_id)
            role = writer.get("writer_role", "")
            if not person or not role:
                continue
            credit = CreditItem(person_id=person_id, name=person.get("name") or person_id, role=role)
            if (credit.person_id, credit.role) not in {(item.person_id, item.role) for item in credit_items}:
                credit_items.append(credit)
            if not credit_source_ids:
                credit_source_ids.append(f"canonical:{song.get('song_id', '')}")
        for resource in payload.get("resources", []) if isinstance(payload.get("resources"), list) else []:
            if not isinstance(resource, dict):
                continue
            if resource.get("resource_type") not in {"catalog-work-search", "lyrics-and-credits", "catalog-song-page"}:
                continue
            source = _resource_source(resource)
            if source and source.source_id not in credit_source_ids:
                credit_source_ids.append(source.source_id)

    for payload in _tool_payloads(latest_turn_messages):
        if "song" in payload and isinstance(payload["song"], dict):
            if title == "Deadbot":
                title = payload["song"].get("title") or title
            song_card = _entity_card_from_song(payload["song"])
            if song_card:
                add_entity(song_card)
            add_credits(payload)
            performances = payload.get("performances")
            if isinstance(performances, list):
                performance_list = _performance_list(
                    payload["song"],
                    [item for item in performances if isinstance(item, dict)],
                    store,
                )
                if performance_list:
                    blocks.append(performance_list)
        if "show" in payload and isinstance(payload["show"], dict):
            add_entity(_entity_card_from_show(payload))
        if "performance" in payload and isinstance(payload["performance"], dict):
            add_entity(_entity_card_from_performance(payload))
        resources = payload.get("resources")
        if isinstance(resources, list):
            add_resources(item for item in resources if isinstance(item, dict))
        links = payload.get("links")
        if isinstance(links, list):
            add_media(item for item in links if isinstance(item, dict))
        show_links = payload.get("show_links")
        if isinstance(show_links, list):
            add_media(item for item in show_links if isinstance(item, dict))
        official_releases = payload.get("official_releases")
        if isinstance(official_releases, list):
            add_media(
                {
                    "platform": "spotify",
                    "link_type": "official-release",
                    "url": release.get("spotify_album_url", ""),
                    "title": release.get("title", "Official release"),
                    "is_official": True,
                }
                for release in official_releases
                if isinstance(release, dict) and release.get("spotify_album_url")
            )
        for arrangement in payload.get("arrangements", []) if isinstance(payload.get("arrangements"), list) else []:
            if not isinstance(arrangement, dict):
                continue
            resource = store.one("resources", arrangement.get("resource_id", ""))
            if not resource:
                continue
            source = _resource_source(resource)
            if not source:
                continue
            sections = [
                section.get("progression", "")
                for section in store.rows("arrangement_chord_sections")
                if section.get("arrangement_id") == arrangement.get("arrangement_id") and section.get("progression")
            ]
            arrangements.append(
                ArrangementBlock(
                    type="arrangement",
                    title=f"Source-specific arrangement: {resource.get('title', 'Chord resource')}",
                    resource_id=resource["resource_id"],
                    source_id=source.source_id,
                    key_signature=arrangement.get("key_signature") or None,
                    progressions=sections,
                )
            )
            add_source(source)

    if credit_items:
        blocks.append(
            CreditListBlock(
                type="credit_list",
                title="Known composition credits",
                items=credit_items[:12],
                source_ids=credit_source_ids[:8] or ["canonical:unknown"],
            )
        )
    if resource_items:
        blocks.append(ResourceListBlock(type="resource_list", title="Further reading and listening", items=resource_items[:8]))
    if chord_items:
        blocks.append(ResourceListBlock(type="resource_list", title="Chord charts and arrangements", items=chord_items[:8]))
    blocks.extend(arrangements[:3])
    if not blocks:
        blocks.append(
            GapStateBlock(
                type="gap_state",
                message="The current experience did not receive a matching grounded result. Try a song, show, or performance that appears in the current library.",
            )
        )
    blocks.append(_coverage_block(store))

    # This is the conservative fallback used when model composition is
    # disabled or unavailable. Coverage is still a validated candidate for a
    # question that asks about scope, but it should not fill ordinary pages.
    visible_indexes = [
        index
        for index, block in enumerate(blocks)
        if block.type not in {"coverage", "provenance_note"}
    ]

    return ExperienceResponse(
        thread_id=thread_id,
        title=title,
        answer=_final_answer(latest_turn_messages),
        conversation=_conversation_turns(message_list),
        blocks=blocks,
        layout=[
            LayoutSection(
                region="primary" if start == 0 else "supporting",
                block_indexes=visible_indexes[start : start + 8],
            )
            for start in range(0, len(visible_indexes), 8)
        ],
        sources=sources,
    )
