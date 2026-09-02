"""Block builders that project tool output into the browser schema.

This module holds the deterministic block builders used by
:mod:`deadbot.finish`, plus the small message helpers that find the current
turn and its tool payloads. Each builder turns one already-grounded tool
payload into a validated block from the allowlisted schema in
:mod:`deadbot.experience`, so nothing here can pass browser code, raw HTML, or
arbitrary embeds to the client. The agent chooses what to build; this module
only decides how a chosen component is shaped.
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
    CreditItem,
    EquipmentItem,
    EquipmentListBlock,
    GuestAppearanceItem,
    GuestAppearanceListBlock,
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


def _song_overview(context: dict[str, Any], store: CanonicalStore) -> SongOverviewBlock | None:
    song = context.get("song")
    if not isinstance(song, dict) or not song.get("song_id"):
        return None
    credits: list[CreditItem] = []
    for writer in context.get("writers", []) if isinstance(context.get("writers"), list) else []:
        person = store.one("people", writer.get("person_id", "")) if isinstance(writer, dict) else None
        role = writer.get("writer_role", "") if isinstance(writer, dict) else ""
        if person and role:
            credits.append(CreditItem(person_id=writer["person_id"], name=person.get("name") or writer["person_id"], role=role, follow_up=None))
    performances = context.get("performances") if isinstance(context.get("performances"), list) else []
    return SongOverviewBlock(
        type="song_overview",
        song_id=song["song_id"],
        title=song.get("title") or "Untitled song",
        original_artist=song.get("original_artist") or None,
        known_performance_count=len(performances),
        credits=credits[:12],
        source_ids=[f"canonical:{song['song_id']}"],
    )


def _arrangement_block(arrangement_id: str, store: CanonicalStore) -> ArrangementBlock | None:
    # ``store.one`` indexes tables by ``<singular>_id``; this table's key is
    # ``arrangement_id``, so look it up by filtering on that column instead.
    arrangement = next(iter(store.filtered_rows("song_arrangements", arrangement_id=arrangement_id)), None)
    if not arrangement:
        return None
    resource = store.one("resources", arrangement.get("resource_id", ""))
    source = _resource_source(resource) if resource else None
    if not resource or not source:
        return None
    sections = [
        section.get("progression", "")
        for section in store.filtered_rows("arrangement_chord_sections", arrangement_id=arrangement_id)
        if section.get("progression")
    ]
    return ArrangementBlock(
        type="arrangement",
        title=f"Source-specific arrangement: {resource.get('title', 'Chord resource')}",
        resource_id=resource["resource_id"],
        source_id=source.source_id,
        key_signature=arrangement.get("key_signature") or None,
        arrangement_scope=arrangement.get("arrangement_scope") or "source-specific arrangement",
        capo=arrangement.get("capo") or None,
        tuning=arrangement.get("tuning") or None,
        notes=arrangement.get("notes") or None,
        progressions=sections[:6],
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
