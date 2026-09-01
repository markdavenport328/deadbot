"""Grounded candidate projection from tool output.

This module is the deterministic adapter between Deadbot's read-only agent and
the versioned browser schema in :mod:`deadbot.experience`. It turns already-
grounded agent/tool messages into a validated ``ExperienceResponse`` full of
candidate blocks — the model-guided composer in :mod:`deadbot.composer` then
selects and arranges from these candidates. Because the adapter only ever
receives tool outputs that passed through the read-only agent, and only emits
the allowlisted block schema, it cannot pass browser code, raw HTML, or
arbitrary embeds to the client.
"""

from __future__ import annotations

import json
from collections.abc import Iterable
from typing import Any, Literal
from urllib.parse import parse_qs, urlparse

from deadbot.data import CanonicalStore
from deadbot.experience import (
    ArrangementBlock,
    ArrangementSearchBlock,
    ArrangementSearchItem,
    ComparisonStripBlock,
    ComparisonStripItem,
    ConversationTurn,
    CoverageBlock,
    CreditItem,
    EntityCardBlock,
    EquipmentItem,
    EquipmentListBlock,
    ExperienceBlock,
    ExperienceMode,
    ExperienceResponse,
    GapStateBlock,
    GuestAppearanceItem,
    GuestAppearanceListBlock,
    LayoutSection,
    MediaLinkBlock,
    PerformanceExtremesBlock,
    PerformanceListBlock,
    PerformanceListItem,
    PerformanceSpineBlock,
    PerformanceSpineNeighbor,
    PerformerItem,
    PerformerListBlock,
    RecordingItem,
    RecordingListBlock,
    ResourceItem,
    ResourceListBlock,
    SetlistSection,
    SetlistSong,
    ShowSelectionBlock,
    ShowSelectionItem,
    ShowSetlistBlock,
    SongOverviewBlock,
    SourceReference,
)


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
    notes = str(resource.get("notes") or "").strip()
    visitor_prefix = "Visitor context:"
    context_note = notes[len(visitor_prefix) :].strip() if notes.startswith(visitor_prefix) else None
    return ResourceItem(
        resource_id=resource["resource_id"],
        title=resource.get("title") or "Untitled resource",
        resource_type=resource.get("resource_type") or "resource",
        source_name=source.label,
        url=source.url or "",
        source_id=source.source_id,
        context_note=context_note or None,
    )


def _research_resource(resource: dict[str, Any]) -> dict[str, Any] | None:
    """Project a metadata-only research record into a trusted resource row.

    Research adapters own the source and URL validation.  The composition
    layer deliberately accepts only a small, explicit record shape and never
    turns descriptions or excerpts into canonical claims.
    """

    identifier = str(resource.get("resource_id") or resource.get("identifier") or "").strip()
    title = resource.get("title")
    url = resource.get("url")
    parsed_url = urlparse(url) if isinstance(url, str) else None
    approved_hosts = {
        "dead.net",
        "www.dead.net",
        "deadheadhigh.com",
        "www.deadheadhigh.com",
        "deadessays.blogspot.com",
    }
    if (
        not identifier
        or not isinstance(title, str)
        or not title.strip()
        or parsed_url is None
        or parsed_url.scheme != "https"
        or parsed_url.hostname not in approved_hosts
        or parsed_url.username is not None
        or parsed_url.password is not None
        or parsed_url.fragment
    ):
        return None
    source = str(resource.get("source") or resource.get("source_name") or "research").strip()
    return {
        "resource_id": f"research:{source}:{identifier}",
        "title": title.strip(),
        "resource_type": str(resource.get("resource_type") or resource.get("entity_type") or "research").strip(),
        "source_name": source,
        "source_url": url,
    }


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
        follow_up=f"Tell me about {song.get('title') or 'this song'}." if song.get("title") else None,
    )


def _entity_card_from_show(payload: dict[str, Any]) -> EntityCardBlock:
    show = payload["show"]
    venue = payload.get("venue") or {}
    source_id = f"canonical:{show['show_id']}"
    location = ", ".join(part for part in [venue.get("city"), venue.get("state_region")] if part)
    details = [location] if location else []
    if show.get("event_name"):
        details.append(show["event_name"])
    venue_name = venue.get("name") or show.get("show_date") or "Undated show"
    return EntityCardBlock(
        type="entity_card",
        entity_type="show",
        entity_id=show["show_id"],
        title=venue_name,
        subtitle=show.get("show_date") or None,
        details=details,
        source_id=source_id,
        follow_up=f"Tell me about the show on {show.get('show_date')}." if show.get("show_date") else None,
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
        follow_up=(
            f"Tell me about the performance of {song.get('title')} on {show.get('show_date')}."
            if song.get("title") and show.get("show_date")
            else None
        ),
    )


def _performance_items(performances: list[dict[str, Any]], store: CanonicalStore) -> list[PerformanceListItem]:
    def sort_key(performance: dict[str, Any]) -> tuple[str, int]:
        show = store.one("shows", performance.get("show_id", "")) or {}
        try:
            position = int(performance.get("position_in_set") or 0)
        except (TypeError, ValueError):
            position = 0
        return (show.get("show_date") or "9999-99-99", position)

    items = []
    for performance in sorted(performances, key=sort_key):
        show = store.one("shows", performance.get("show_id", "")) or {}
        venue = store.one("venues", show.get("venue_id", "")) if show.get("venue_id") else None
        show_date = show.get("show_date") or None
        venue_name = venue.get("name") if venue else None
        show_label = " — ".join(part for part in [show_date, venue_name] if part) or show.get("show_id") or "Unknown show"
        follow_up = f"Tell me about the show on {show_date}." if show_date else f"Tell me about the show {show_label}."
        items.append(
            PerformanceListItem(
                performance_id=performance["performance_id"],
                show_id=performance.get("show_id", ""),
                show_date=show_date,
                show_label=show_label,
                set_label=performance.get("set_label") or None,
                position_in_set=performance.get("position_in_set") or None,
                follow_up=follow_up,
            )
        )
    return items


def _performance_list(song: dict[str, Any], performances: list[dict[str, Any]], store: CanonicalStore) -> PerformanceListBlock | None:
    items = _performance_items(performances, store)
    if not items:
        return None
    return PerformanceListBlock(
        type="performance_list",
        title="Known performances",
        song_id=song["song_id"],
        known_count=len(items),
        items=items[:20],
    )


def _performance_extremes(song: dict[str, Any], performances: list[dict[str, Any]], store: CanonicalStore) -> PerformanceExtremesBlock | None:
    items = _performance_items(performances, store)
    if not items:
        return None
    return PerformanceExtremesBlock(
        type="performance_extremes",
        song_id=song["song_id"],
        title="First and last performances",
        first=items[0],
        last=items[-1],
    )


def _comparison_strip(song: dict[str, Any], performances: list[dict[str, Any]], store: CanonicalStore) -> ComparisonStripBlock | None:
    """Place one representative rendition per known year on a chronological strip.

    The strip is a comparison-mode candidate built only from canonical dates and
    set placement. It is skipped entirely when the library's coverage of the
    song does not span at least two distinct years.
    """

    items = _performance_items(performances, store)
    first_per_year: dict[int, PerformanceListItem] = {}
    for item in items:
        if not item.show_date or not item.show_date[:4].isdigit():
            continue
        year = int(item.show_date[:4])
        first_per_year.setdefault(year, item)
    years = sorted(first_per_year)
    if len(years) < 2:
        return None
    if len(years) > 12:
        # An evenly spread selection that always keeps the first and last year.
        selected_positions = {round(step * (len(years) - 1) / 11) for step in range(12)}
        years = [year for position, year in enumerate(years) if position in selected_positions]

    title = song.get("title") or "this song"
    strip_items = [
        ComparisonStripItem(
            performance_id=first_per_year[year].performance_id,
            show_id=first_per_year[year].show_id,
            year=year,
            show_date=first_per_year[year].show_date,
            show_label=first_per_year[year].show_label,
            set_label=first_per_year[year].set_label,
            position_in_set=first_per_year[year].position_in_set,
            follow_up=f"Tell me about the performance of {title} on {first_per_year[year].show_date}.",
        )
        for year in years
    ]
    return ComparisonStripBlock(
        type="comparison_strip",
        song_id=song["song_id"],
        title="Performances over time",
        known_count=len(items),
        coverage_note=(
            "Each stop is one representative performance from that year, selected "
            "from current library coverage. This strip is not a complete "
            "performance history of the song."
        ),
        items=strip_items,
    )


def _performance_spine(payload: dict[str, Any], store: CanonicalStore) -> PerformanceSpineBlock | None:
    """Return only the directly adjacent, canonical set context for a rendition."""

    performance = payload.get("performance")
    song = payload.get("song")
    show = payload.get("show")
    if not isinstance(performance, dict) or not isinstance(song, dict) or not isinstance(show, dict):
        return None
    performance_id = performance.get("performance_id")
    song_id = song.get("song_id")
    show_id = show.get("show_id")
    if not performance_id or not song_id or not show_id:
        return None

    set_label = performance.get("set_label") or None
    try:
        current_position = int(performance.get("position_in_set") or 0)
    except (TypeError, ValueError):
        current_position = 0
    same_set = [
        item
        for item in store.filtered_rows("performances", show_id=show_id)
        if (item.get("set_label") or None) == set_label
    ]
    def position(item: dict[str, str]) -> int:
        try:
            return int(item.get("position_in_set") or 0)
        except (TypeError, ValueError):
            return 0

    same_set.sort(key=position)
    current_index = next((index for index, item in enumerate(same_set) if item.get("performance_id") == performance_id), None)
    if current_index is None:
        return None

    def neighbor(item: dict[str, str] | None) -> PerformanceSpineNeighbor | None:
        if not item or not item.get("performance_id"):
            return None
        neighbor_song = store.one("songs", item.get("song_id", "")) or {}
        title = neighbor_song.get("title") or "Unknown song"
        return PerformanceSpineNeighbor(
            performance_id=item["performance_id"],
            title=title,
            follow_up=(
                f"Tell me about the performance of {title} on {show.get('show_date')}."
                if show.get("show_date")
                else f"Tell me about the performance of {title}."
            ),
        )

    venue = store.one("venues", show.get("venue_id", "")) or {}
    show_label = " — ".join(
        part for part in [show.get("show_date"), venue.get("name")] if part
    ) or show_id
    return PerformanceSpineBlock(
        type="performance_spine",
        performance_id=performance_id,
        song_id=song_id,
        title="Set context",
        show_label=show_label,
        set_label=set_label,
        position_in_set=str(current_position) if current_position else performance.get("position_in_set") or None,
        previous=neighbor(same_set[current_index - 1] if current_index > 0 else None),
        next=neighbor(same_set[current_index + 1] if current_index + 1 < len(same_set) else None),
    )


def _show_setlist(payload: dict[str, Any], store: CanonicalStore) -> ShowSetlistBlock | None:
    show = payload.get("show")
    performances = payload.get("performances")
    if not isinstance(show, dict) or not isinstance(performances, list):
        return None

    grouped: dict[str, list[SetlistSong]] = {}
    for performance in performances:
        if not isinstance(performance, dict):
            continue
        song = store.one("songs", performance.get("song_id", "")) or {}
        title = song.get("title")
        if not title or not performance.get("performance_id"):
            continue
        label = performance.get("set_label") or "Set"
        show_date = show.get("show_date") or ""
        grouped.setdefault(label, []).append(
            SetlistSong(
                performance_id=performance["performance_id"],
                song_id=performance.get("song_id", ""),
                title=title,
                position_in_set=performance.get("position_in_set") or None,
                follow_up=(
                    f"Tell me about the performance of {title} on {show_date}."
                    if show_date
                    else f"Tell me about the performance of {title}."
                ),
            )
        )

    if not grouped:
        return None
    return ShowSetlistBlock(
        type="show_setlist",
        show_id=show["show_id"],
        title="Setlist",
        sets=[SetlistSection(label=label, songs=songs) for label, songs in grouped.items()],
    )


def _show_selection_blocks(payload: dict[str, Any]) -> tuple[list[ShowSelectionBlock], list[SourceReference]]:
    """Project source-attributed show selections into safe browser blocks."""

    selections = payload.get("show_selections")
    if not isinstance(selections, list):
        return [], []
    blocks: list[ShowSelectionBlock] = []
    sources: list[SourceReference] = []
    for selection in selections:
        if not isinstance(selection, dict):
            continue
        selection_id = selection.get("selection_id")
        title = selection.get("title")
        source_url = selection.get("source_url")
        raw_items = selection.get("items")
        if not isinstance(selection_id, str) or not isinstance(title, str) or not isinstance(source_url, str) or not isinstance(raw_items, list):
            continue
        parsed = urlparse(source_url)
        if parsed.scheme != "https" or not parsed.netloc or parsed.username or parsed.password:
            continue
        items = []
        for item in raw_items:
            if not isinstance(item, dict):
                continue
            show_id, show_date, venue_name = item.get("show_id"), item.get("show_date"), item.get("venue_name")
            if not all(isinstance(value, str) and value for value in (show_id, show_date, venue_name)):
                continue
            items.append(
                ShowSelectionItem(
                    show_id=show_id,
                    show_date=show_date,
                    venue_name=venue_name,
                    location=item.get("location") if isinstance(item.get("location"), str) and item.get("location") else None,
                    follow_up=f"Tell me about the Grateful Dead show on {show_date}.",
                )
            )
        if not items:
            continue
        source_id = f"selection:{selection_id}"
        blocks.append(
            ShowSelectionBlock(
                type="show_selection",
                title=title,
                selection_type=selection.get("selection_type") if isinstance(selection.get("selection_type"), str) else "source-attributed selection",
                selector_name=selection.get("selector_name") if isinstance(selection.get("selector_name"), str) else "Editorial source",
                coverage_note=selection.get("coverage_note") if isinstance(selection.get("coverage_note"), str) else "This is a source-attributed selection, not a ranking.",
                source_id=source_id,
                items=items[:24],
            )
        )
        sources.append(SourceReference(source_id=source_id, kind="contextual_resource", label=title, url=source_url))
    return blocks, sources


def _show_performers(payload: dict[str, Any], store: CanonicalStore) -> PerformerListBlock | None:
    show = payload.get("show")
    assignments = payload.get("performers")
    if not isinstance(show, dict) or not isinstance(assignments, list):
        return None

    grouped: dict[tuple[str, str], PerformerItem] = {}
    for assignment in assignments:
        if not isinstance(assignment, dict):
            continue
        person_id = assignment.get("person_id")
        role = assignment.get("role")
        person = store.one("people", person_id or "")
        instrument = assignment.get("instrument")
        if not person_id or role not in {"performer", "guest"} or not person or not instrument:
            continue
        key = (person_id, role)
        item = grouped.get(key)
        if item is None:
            name = person.get("name") or person_id
            show_date = show.get("show_date") or ""
            item = PerformerItem(
                person_id=person_id,
                name=name,
                role=role,
                instruments=[instrument],
                follow_up=(
                    f"Tell me more about {name} and their role at the {show_date} show."
                    if show_date
                    else f"Tell me more about {name} and their role at this show."
                ),
            )
            grouped[key] = item
        elif instrument not in item.instruments:
            item.instruments.append(instrument)

    if not grouped:
        return None
    return PerformerListBlock(
        type="performer_list",
        show_id=show["show_id"],
        title="Performers",
        items=list(grouped.values())[:24],
    )


def _show_equipment(payload: dict[str, Any]) -> EquipmentListBlock | None:
    show = payload.get("show")
    equipment = payload.get("equipment")
    if not isinstance(show, dict) or not isinstance(equipment, list):
        return None

    items: list[EquipmentItem] = []
    seen: set[tuple[str, str, str]] = set()
    show_date = show.get("show_date") or ""
    for assignment in equipment:
        if not isinstance(assignment, dict):
            continue
        equipment_id = assignment.get("equipment_id")
        name = assignment.get("name")
        source_id = assignment.get("source_id")
        source_url = assignment.get("source_url")
        usage_context = assignment.get("usage_context") or "stage guitar"
        claim_type = assignment.get("claim_type")
        if (
            not equipment_id
            or not name
            or not source_id
            or not isinstance(source_url, str)
            or not source_url
            or claim_type not in {"show", "date_range"}
        ):
            continue
        key = (equipment_id, usage_context, claim_type)
        if key in seen:
            continue
        seen.add(key)
        items.append(
            EquipmentItem(
                equipment_id=equipment_id,
                name=name,
                manufacturer=assignment.get("manufacturer") or "",
                model=assignment.get("model") or "",
                usage_context=usage_context,
                claim_type=claim_type,
                evidence=(
                    "Specific-show evidence from the cited instrument history."
                    if claim_type == "show"
                    else "Dated-range evidence from the cited instrument history."
                ),
                source_id=source_id,
                source_url=source_url,
                follow_up=(
                    f"Tell me more about {name} at the {show_date} show."
                    if show_date
                    else f"Tell me more about {name}."
                ),
            )
        )
    if not items:
        return None
    return EquipmentListBlock(
        type="equipment_list",
        show_id=show["show_id"],
        title="Jerry's guitars",
        items=items[:16],
    )


def _recording_list(payload: dict[str, Any], store: CanonicalStore) -> RecordingListBlock | None:
    show = payload.get("show")
    recordings = (
        store.filtered_rows("recordings", show_id=show.get("show_id"))
        if isinstance(show, dict) and show.get("show_id")
        else payload.get("recordings")
    )
    if not isinstance(recordings, list):
        return None

    items: list[RecordingItem] = []
    seen_ids: set[str] = set()
    for recording in recordings:
        if not isinstance(recording, dict):
            continue
        recording_id = recording.get("recording_id")
        url = recording.get("source_url")
        if not recording_id or recording_id in seen_ids or not isinstance(url, str):
            continue
        parsed = urlparse(url)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            continue
        seen_ids.add(recording_id)
        archive_identifier = recording.get("archive_identifier") or None
        title = recording.get("source_description") or f"{recording.get('source_type', 'Audio')} recording"
        items.append(
            RecordingItem(
                recording_id=recording_id,
                title=title,
                source_type=recording.get("source_type") or "Recording",
                archive_identifier=archive_identifier,
                url=url,
                source_id=f"recording:{recording_id}",
            )
        )
    if not items:
        return None
    return RecordingListBlock(
        type="recording_list",
        show_id=show.get("show_id") if isinstance(show, dict) else None,
        title="Recordings",
        items=items[:8],
    )


def _coverage_block(store: CanonicalStore) -> CoverageBlock:
    coverage = store.coverage_summary()
    if coverage["first_year"] and coverage["last_year"]:
        year_range = f"{coverage['first_year']}–{coverage['last_year']}"
    else:
        year_range = "no dated years"
    return CoverageBlock(
        type="coverage",
        title="Current library coverage",
        message=(
            f"The current canonical library contains {coverage['dated_show_count']} dated shows, "
            f"{coverage['performance_count']} ordered performances, and "
            f"{coverage['performance_song_count']} song labels spanning {year_range}. "
            "This is a source-derived baseline with uneven enrichment; it is not a complete record "
            "of every historical performance or song-related fact."
        ),
    )


def _arrangement_search_block(payload: dict[str, Any], store: CanonicalStore) -> tuple[ArrangementSearchBlock | None, list[SourceReference]]:
    """Turn a key-search tool result into an explicitly source-limited list."""

    search = payload.get("arrangement_search")
    arrangements = payload.get("arrangements")
    if not isinstance(search, dict) or not isinstance(arrangements, list):
        return None, []
    key_signature = search.get("key_signature")
    if not isinstance(key_signature, str) or not key_signature:
        return None, []
    items: list[ArrangementSearchItem] = []
    sources: list[SourceReference] = []
    for arrangement in arrangements:
        if not isinstance(arrangement, dict):
            continue
        arrangement_id = arrangement.get("arrangement_id")
        song = store.one("songs", arrangement.get("song_id", "")) or {}
        resource = store.one("resources", arrangement.get("resource_id", "")) or {}
        source = _resource_source(resource)
        if not arrangement_id or not song.get("song_id") or not song.get("title") or not resource.get("resource_id") or not source:
            continue
        items.append(
            ArrangementSearchItem(
                arrangement_id=arrangement_id,
                song_id=song["song_id"],
                title=song["title"],
                resource_id=resource["resource_id"],
                resource_title=resource.get("title") or "Chord resource",
                source_name=source.label,
                url=source.url or "",
                key_signature=arrangement.get("key_signature") or key_signature,
                arrangement_scope=arrangement.get("arrangement_scope") or "source-specific arrangement",
                follow_up=f"Show me the documented arrangement for {song['title']}.",
            )
        )
        sources.append(source)
    if not items:
        return None, []
    return (
        ArrangementSearchBlock(
            type="arrangement_search",
            title=f"Documented arrangements in {key_signature}",
            key_signature=key_signature,
            coverage_note=(
                search.get("coverage_note")
                if isinstance(search.get("coverage_note"), str)
                else "Results include only documented arrangements in the current library."
            ),
            items=items[:20],
        ),
        sources,
    )


def _guest_appearance_blocks(payload: dict[str, Any]) -> list[GuestAppearanceListBlock]:
    """Project resolved guest-credit relationships into browser-safe blocks."""

    raw_guests = payload.get("guests")
    if not isinstance(raw_guests, list):
        return []
    blocks: list[GuestAppearanceListBlock] = []
    # Keep the candidate packet within the response's global block budget even
    # if the model asks for the full guest directory. A named-person query
    # normally produces one block; broad directory exploration stays bounded.
    for guest in raw_guests[:8]:
        if not isinstance(guest, dict):
            continue
        person_id = guest.get("person_id")
        person_name = guest.get("name")
        raw_appearances = guest.get("appearances")
        if not isinstance(person_id, str) or not isinstance(person_name, str) or not isinstance(raw_appearances, list):
            continue
        items: list[GuestAppearanceItem] = []
        for appearance in raw_appearances:
            if not isinstance(appearance, dict):
                continue
            show_id = appearance.get("show_id")
            show_date = appearance.get("show_date")
            venue_name = appearance.get("venue_name")
            location = appearance.get("location")
            raw_instruments = appearance.get("instruments")
            if not isinstance(raw_instruments, list):
                legacy_instrument = appearance.get("instrument")
                raw_instruments = [legacy_instrument] if isinstance(legacy_instrument, str) else []
            instruments = [item for item in raw_instruments if isinstance(item, str) and item]
            if not isinstance(show_id, str) or not isinstance(show_date, str) or not instruments:
                continue
            scope = appearance.get("participation_scope")
            items.append(
                GuestAppearanceItem(
                    show_id=show_id,
                    show_date=show_date,
                    venue_name=venue_name if isinstance(venue_name, str) and venue_name else None,
                    location=location if isinstance(location, str) and location else None,
                    instruments=instruments[:8],
                    participation_scope=scope if isinstance(scope, str) and scope else None,
                    follow_up=f"Tell me about the Grateful Dead show on {show_date}.",
                )
            )
        if not items:
            continue
        documented_count = guest.get("guest_show_count")
        count = documented_count if isinstance(documented_count, int) and documented_count == len(items) else len(items)
        blocks.append(
            GuestAppearanceListBlock(
                type="guest_appearance_list",
                person_id=person_id,
                person_name=person_name,
                known_show_count=count,
                items=items[:24],
            )
        )
    return blocks


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
    seen_arrangements: set[str] = set()
    processed_show_ids: set[str] = set()
    resource_items: list[ResourceItem] = []
    chord_items: list[ResourceItem] = []
    credit_items: list[CreditItem] = []
    credit_source_ids: list[str] = []
    arrangements: list[ArrangementBlock] = []
    song_summary: dict[str, Any] | None = None
    song_performance_count = 0
    mode: ExperienceMode = "quick_fact"
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
            credit_name = person.get("name") or person_id
            song_title = song.get("title") or "this song"
            credit = CreditItem(
                person_id=person_id,
                name=credit_name,
                role=role,
                follow_up=f"Tell me more about {credit_name}'s {role} role on {song_title}.",
            )
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

    tool_payloads = _tool_payloads(latest_turn_messages)
    for payload in tool_payloads:
        guest_blocks = _guest_appearance_blocks(payload)
        if guest_blocks:
            blocks.extend(guest_blocks)
            mode = "musician"
            if title == "Deadbot" and len(guest_blocks) == 1:
                title = guest_blocks[0].person_name
            for block in guest_blocks:
                add_source(_canonical_source(block.person_id))
        show_selection_blocks, show_selection_sources = _show_selection_blocks(payload)
        if show_selection_blocks:
            blocks.extend(show_selection_blocks)
            for source in show_selection_sources:
                add_source(source)
            if title == "Deadbot":
                title = show_selection_blocks[0].title
            mode = "research"
        arrangement_search, arrangement_search_sources = _arrangement_search_block(payload, store)
        if arrangement_search:
            blocks.append(arrangement_search)
            mode = "musician"
            if title == "Deadbot":
                title = arrangement_search.title
            for source in arrangement_search_sources:
                add_source(source)
        if "song" in payload and isinstance(payload["song"], dict):
            if song_summary is None:
                song_summary = payload["song"]
            if title == "Deadbot":
                title = payload["song"].get("title") or title
            song_card = _entity_card_from_song(payload["song"])
            if song_card:
                add_entity(song_card)
            add_credits(payload)
            performances = payload.get("performances")
            if isinstance(performances, list):
                song_performance_count = len([item for item in performances if isinstance(item, dict)])
                performance_items = [item for item in performances if isinstance(item, dict)]
                performance_extremes = _performance_extremes(
                    payload["song"],
                    performance_items,
                    store,
                )
                if performance_extremes:
                    blocks.append(performance_extremes)
                comparison_strip = _comparison_strip(
                    payload["song"],
                    performance_items,
                    store,
                )
                if comparison_strip:
                    blocks.append(comparison_strip)
                performance_list = _performance_list(
                    payload["song"],
                    performance_items,
                    store,
                )
                if performance_list:
                    blocks.append(performance_list)
        if "show" in payload and isinstance(payload["show"], dict):
            show_id = payload["show"].get("show_id")
            if show_id and show_id not in processed_show_ids:
                processed_show_ids.add(show_id)
                add_entity(_entity_card_from_show(payload))
                performer_list = _show_performers(payload, store)
                if performer_list:
                    blocks.append(performer_list)
                equipment_list = _show_equipment(payload)
                if equipment_list:
                    blocks.append(equipment_list)
                    for item in equipment_list.items:
                        add_source(
                            SourceReference(
                                source_id=item.source_id,
                                kind="contextual_resource",
                                label="Jerry Garcia Instrument History",
                                url=item.source_url,
                            )
                        )
                show_setlist = _show_setlist(payload, store)
                if show_setlist:
                    blocks.append(show_setlist)
                recording_list = _recording_list(payload, store)
                if recording_list:
                    for item in recording_list.items:
                        add_source(
                            SourceReference(
                                source_id=item.source_id,
                                kind="contextual_resource",
                                label=item.source_type,
                                url=item.url,
                            )
                        )
                    blocks.append(recording_list)
        if "performance" in payload and isinstance(payload["performance"], dict):
            # A performance spine is a richer, non-redundant identifier for a
            # rendition than a generic entity card. Keep the page title useful
            # even when this is the only retrieved payload.
            performance_song = payload.get("song")
            if title == "Deadbot" and isinstance(performance_song, dict):
                title = performance_song.get("title") or title
            performance_spine = _performance_spine(payload, store)
            if performance_spine:
                blocks.append(performance_spine)
            else:
                add_entity(_entity_card_from_performance(payload))
        resources = payload.get("resources")
        if isinstance(resources, list):
            add_resources(item for item in resources if isinstance(item, dict))
        # Metadata-only source research is returned as a server-owned packet.
        # Normalize records into the same resource_list path as canonical
        # resources so the main column and its safe fallback stay identical.
        research_packets: list[Any] = []
        for key in ("research", "research_result", "research_results"):
            value = payload.get(key)
            if isinstance(value, dict):
                records = value.get("records")
                if isinstance(records, list):
                    research_packets.extend(records)
            elif isinstance(value, list):
                research_packets.extend(value)
        research_resources = []
        for record in research_packets:
            if isinstance(record, dict):
                resource = _research_resource(record)
                if resource:
                    research_resources.append(resource)
        if research_resources:
            add_resources(research_resources)
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
        for arrangement in (
            []
            if arrangement_search
            else payload.get("arrangements", []) if isinstance(payload.get("arrangements"), list) else []
        ):
            if not isinstance(arrangement, dict):
                continue
            arrangement_id = arrangement.get("arrangement_id")
            if not arrangement_id or arrangement_id in seen_arrangements:
                continue
            resource = store.one("resources", arrangement.get("resource_id", ""))
            if not resource:
                continue
            source = _resource_source(resource)
            if not source:
                continue
            sections = [
                section.get("progression", "")
                for section in store.filtered_rows(
                    "arrangement_chord_sections", arrangement_id=arrangement_id
                )
                if section.get("progression")
            ]
            arrangements.append(
                ArrangementBlock(
                    type="arrangement",
                    title=f"Source-specific arrangement: {resource.get('title', 'Chord resource')}",
                    resource_id=resource["resource_id"],
                    source_id=source.source_id,
                    key_signature=arrangement.get("key_signature") or None,
                    arrangement_scope=arrangement.get("arrangement_scope") or "source-specific arrangement",
                    capo=arrangement.get("capo") or None,
                    tuning=arrangement.get("tuning") or None,
                    notes=arrangement.get("notes") or None,
                    progressions=sections,
                )
            )
            seen_arrangements.add(arrangement_id)
            add_source(source)

    if song_summary is not None:
        blocks.insert(
            0,
            SongOverviewBlock(
                type="song_overview",
                song_id=song_summary["song_id"],
                title=song_summary.get("title") or "Untitled song",
                original_artist=song_summary.get("original_artist") or None,
                known_performance_count=song_performance_count,
                credits=credit_items[:12],
                source_ids=(
                    [f"canonical:{song_summary['song_id']}"]
                    + [source_id for source_id in credit_source_ids if source_id != f"canonical:{song_summary['song_id']}"]
                )[:8],
            ),
        )
    if resource_items:
        blocks.append(ResourceListBlock(type="resource_list", title="Further reading and listening", items=resource_items[:8]))
    if chord_items:
        blocks.append(ResourceListBlock(type="resource_list", title="Chord charts and arrangements", items=chord_items[:8]))
    blocks.extend(arrangements[:3])
    if not blocks:
        mode = "gap"
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

    answer = _final_answer(latest_turn_messages)
    conversation = _conversation_turns(message_list)

    return ExperienceResponse(
        thread_id=thread_id,
        title=title,
        answer=answer,
        mode=mode,
        conversation=conversation,
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
