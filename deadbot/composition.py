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
    AlbumCreditItem,
    AlbumTrackItem,
    AlbumUnitBlock,
    ArrangementBlock,
    ArrangementSearchBlock,
    ArrangementSearchItem,
    CreditItem,
    Emphasis,
    EquipmentItem,
    EquipmentListBlock,
    EraPerformanceItem,
    EraUnitBlock,
    GuestAppearanceItem,
    GuestAppearanceListBlock,
    ComparisonStripItem,
    ListenAction,
    MediaLinkBlock,
    PerformanceListItem,
    PerformanceSpineNeighbor,
    PerformanceUnitBlock,
    PerformerItem,
    RecordingItem,
    ResourceItem,
    SetlistSection,
    SetlistSong,
    ShowSelectionBlock,
    ShowSelectionItem,
    ShowUnitBlock,
    SongHistory,
    SongOverviewBlock,
    SongRepresentativePerformance,
    SongReleaseItem,
    SourceReference,
    UnitSource,
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
    # Every host a pathway link (deadbot/pathways.py) can carry: dead.net
    # research pages, the research-site blogs in data/research_sites.json,
    # the Grateful Dead Archive Online, archive.org, and Relix, the source of
    # cataloged interview resources. A pathway link the model cites must
    # survive here to reach the visible response.
    approved_hosts = {
        "dead.net",
        "www.dead.net",
        "deadheadhigh.com",
        "www.deadheadhigh.com",
        "deadessays.blogspot.com",
        "lostlivedead.blogspot.com",
        "hooterollin.blogspot.com",
        "deadsources.blogspot.com",
        "gratefulseconds.blogspot.com",
        "gdao.org",
        "www.gdao.org",
        "archive.org",
        "www.archive.org",
        "relix.com",
        "www.relix.com",
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
    # Fetch every show and venue in two queries. A song like Eyes of the World
    # has several hundred performances, and one lookup per row against the
    # remote database cost about thirty seconds per block.
    show_ids = [performance.get("show_id", "") for performance in performances if performance.get("show_id")]
    shows = {row["show_id"]: row for row in store.rows_in("shows", "show_id", show_ids)}
    venue_ids = [show.get("venue_id", "") for show in shows.values() if show.get("venue_id")]
    venues = {row["venue_id"]: row for row in store.rows_in("venues", "venue_id", venue_ids)}

    def sort_key(performance: dict[str, Any]) -> tuple[str, int]:
        show = shows.get(performance.get("show_id", ""), {})
        try:
            position = int(performance.get("position_in_set") or 0)
        except (TypeError, ValueError):
            position = 0
        return (show.get("show_date") or "9999-99-99", position)

    items = []
    for performance in sorted(performances, key=sort_key):
        show = shows.get(performance.get("show_id", ""), {})
        venue = venues.get(show.get("venue_id", "")) if show.get("venue_id") else None
        show_date = show.get("show_date") or None
        venue_name = venue.get("name") if venue else None
        show_label = " — ".join(part for part in [show_date, venue_name] if part) or show.get("show_id") or "Unknown show"
        items.append(
            PerformanceListItem(
                performance_id=performance["performance_id"],
                show_id=performance.get("show_id", ""),
                show_date=show_date,
                show_label=show_label,
                set_label=performance.get("set_label") or None,
                position_in_set=performance.get("position_in_set") or None,
                listen_url=_listen_url(performance),
            )
        )
    return items


def _song_history(performances: list[dict[str, Any]], store: CanonicalStore) -> SongHistory | None:
    """First and last renditions plus one representative per year, canonical dates only."""

    items = _performance_items(performances, store)
    if not items:
        return None
    first_per_year: dict[int, PerformanceListItem] = {}
    for item in items:
        if item.show_date and item.show_date[:4].isdigit():
            first_per_year.setdefault(int(item.show_date[:4]), item)
    years = sorted(first_per_year)
    if len(years) > 12:
        selected_positions = {round(step * (len(years) - 1) / 11) for step in range(12)}
        years = [year for position, year in enumerate(years) if position in selected_positions]
    by_year = [
        ComparisonStripItem(
            performance_id=first_per_year[year].performance_id,
            show_id=first_per_year[year].show_id,
            year=year,
            show_date=first_per_year[year].show_date,
            show_label=first_per_year[year].show_label,
            set_label=first_per_year[year].set_label,
            position_in_set=first_per_year[year].position_in_set,
            listen_url=first_per_year[year].listen_url,
        )
        for year in years
    ]
    dated = [item for item in items if item.show_date]
    first = dated[0] if dated else items[0]
    last = dated[-1] if dated else items[-1]
    return SongHistory(known_count=len(items), first=first, last=last, by_year=by_year)


def _set_neighbors(
    payload: dict[str, Any], store: CanonicalStore
) -> tuple[PerformanceSpineNeighbor | None, PerformanceSpineNeighbor | None]:
    """Return only the directly adjacent, canonical set neighbors for a rendition."""

    performance = payload.get("performance")
    song = payload.get("song")
    show = payload.get("show")
    if not isinstance(performance, dict) or not isinstance(song, dict) or not isinstance(show, dict):
        return None, None
    performance_id = performance.get("performance_id")
    song_id = song.get("song_id")
    show_id = show.get("show_id")
    if not performance_id or not song_id or not show_id:
        return None, None

    set_label = performance.get("set_label") or None
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
        return None, None

    def neighbor(item: dict[str, str] | None) -> PerformanceSpineNeighbor | None:
        if not item or not item.get("performance_id"):
            return None
        neighbor_song = store.one("songs", item.get("song_id", "")) or {}
        return PerformanceSpineNeighbor(performance_id=item["performance_id"], title=neighbor_song.get("title") or "Unknown song")

    return (
        neighbor(same_set[current_index - 1] if current_index > 0 else None),
        neighbor(same_set[current_index + 1] if current_index + 1 < len(same_set) else None),
    )


def _listen_url(performance: dict[str, Any]) -> str | None:
    """The best direct performance link the store attached, audio first."""

    listen = performance.get("listen")
    if not isinstance(listen, dict):
        return None
    for key in ("archive_track_url", "release_track_url", "video_url"):
        url = listen.get(key)
        if isinstance(url, str) and url:
            return url
    return None


def _setlist_sections(
    payload: dict[str, Any],
    store: CanonicalStore,
    highlighted: frozenset[str] = frozenset(),
) -> list[SetlistSection]:
    show = payload.get("show")
    performances = payload.get("performances")
    if not isinstance(show, dict) or not isinstance(performances, list):
        return []

    # One query for every song title in the show; a show unit inside an
    # explorer would otherwise cost one remote lookup per setlist entry.
    song_ids = [performance.get("song_id", "") for performance in performances if isinstance(performance, dict) and performance.get("song_id")]
    songs = {row["song_id"]: row for row in store.rows_in("songs", "song_id", song_ids)}

    grouped: dict[str, list[SetlistSong]] = {}
    for performance in performances:
        if not isinstance(performance, dict):
            continue
        song = songs.get(performance.get("song_id", ""), {})
        title = song.get("title")
        if not title or not performance.get("performance_id"):
            continue
        label = performance.get("set_label") or "Set"
        grouped.setdefault(label, []).append(
            SetlistSong(
                performance_id=performance["performance_id"],
                song_id=performance.get("song_id", ""),
                title=title,
                position_in_set=performance.get("position_in_set") or None,
                highlighted=performance["performance_id"] in highlighted,
                listen_url=_listen_url(performance),
            )
        )
    return [SetlistSection(label=label, songs=songs[:40]) for label, songs in list(grouped.items())[:4]]


# --- semantic units ---------------------------------------------------------


def _venue_location(venue: dict[str, Any] | None) -> str | None:
    if not isinstance(venue, dict):
        return None
    return ", ".join(part for part in (venue.get("city"), venue.get("state_region")) if part) or None


def _provider_for(url: str, platform: str | None = None) -> str:
    if platform:
        return platform
    host = urlparse(url).netloc.casefold().removeprefix("www.")
    if host.endswith("archive.org"):
        return "archive"
    if host.endswith("relisten.net"):
        return "relisten"
    if host.endswith("spotify.com"):
        return "spotify"
    if host.endswith(("youtube.com", "youtu.be")):
        return "youtube"
    return host or "web"


def _show_listen_actions(
    payload: dict[str, Any],
    store: CanonicalStore,
    preferred_recording_id: str | None,
) -> tuple[list[ListenAction], list[SourceReference]]:
    """Relevant listening actions that belong to a show.

    The composer may name a preferred recording; when it belongs to the show it
    leads. Otherwise the show's stored stream leads, and an official release
    follows. A generic recording index is source inventory rather than an
    editorial listening path, so it is not promoted here.
    """

    show = payload.get("show")
    if not isinstance(show, dict) or not show.get("show_id"):
        return [], []
    show_id = show["show_id"]
    actions: list[ListenAction] = []
    sources: list[SourceReference] = []
    seen: set[str] = set()

    def add(action: ListenAction) -> None:
        if action.url and action.url not in seen:
            seen.add(action.url)
            actions.append(action)

    if preferred_recording_id:
        for row in store.filtered_rows("recordings", show_id=show_id):
            if row.get("recording_id") != preferred_recording_id:
                continue
            url = row.get("source_url") or ""
            parsed = urlparse(url)
            if parsed.scheme not in {"http", "https"} or not parsed.netloc:
                break
            source_type = row.get("source_type") or "Recording"
            add(ListenAction(label=f"Listen to the show · {source_type}", url=url, provider=_provider_for(url)))
            sources.append(SourceReference(source_id=f"recording:{preferred_recording_id}", kind="contextual_resource", label=source_type, url=url))
            break

    show_links = payload.get("show_links") if isinstance(payload.get("show_links"), list) else []
    by_type: dict[str, dict[str, Any]] = {}
    for link in show_links:
        if isinstance(link, dict) and link.get("url"):
            by_type.setdefault(str(link.get("link_type") or ""), link)
    stream = by_type.get("streaming-show-page")
    if stream:
        add(ListenAction(label="Stream the show", url=stream["url"], provider=_provider_for(stream["url"], stream.get("platform"))))
    releases = payload.get("official_releases") if isinstance(payload.get("official_releases"), list) else []
    for release in releases:
        if not isinstance(release, dict):
            continue
        url = release.get("spotify_album_url") or release.get("source_url")
        if isinstance(url, str) and url:
            add(ListenAction(label=f"Hear it on {release.get('title') or 'the official release'}", url=url, provider=_provider_for(url), is_official=True))
            break
    video = by_type.get("full-show-video")
    if video:
        add(ListenAction(label="Watch the show", url=video["url"], provider=_provider_for(video["url"], video.get("platform"))))
    return actions[:4], sources


def _guest_items(payload: dict[str, Any], store: CanonicalStore) -> list[PerformerItem]:
    performers = _show_lineup(payload, store)
    return [item for item in performers if item.role == "guest"][:8]


def _show_unit(
    payload: dict[str, Any],
    store: CanonicalStore,
    *,
    emphasis: Emphasis = "supporting",
    judgments: list[str] | None = None,
    note: str | None = None,
    title: str | None = None,
    visible_facets: list[str] | None = None,
    setlist_disclosure: str = "expanded",
    highlighted_performance_ids: list[str] | None = None,
    preferred_recording_id: str | None = None,
    sources: list[UnitSource] | None = None,
    follow_up: str | None = None,
) -> tuple[ShowUnitBlock | None, list[SourceReference]]:
    """Hydrate one show unit from its show payload.

    Highlighted performances and the preferred recording are kept only when
    they belong to this show, so a slip in the plan cannot attach another
    night's song to this one.
    """

    show = payload.get("show")
    if not isinstance(show, dict) or not show.get("show_id") or not show.get("show_date"):
        return None, []
    own_performance_ids = {
        performance["performance_id"]
        for performance in payload.get("performances", [])
        if isinstance(performance, dict) and performance.get("performance_id")
    }
    facets = frozenset(
        ("guests", "listen", "setlist", "sources")
        if visible_facets is None
        else visible_facets
    )
    highlighted = frozenset(pid for pid in (highlighted_performance_ids or []) if pid in own_performance_ids)
    listen, listen_sources = _show_listen_actions(payload, store, preferred_recording_id)
    recordings = _show_recordings(payload, store) if "recordings" in facets else []
    venue = payload.get("venue")
    block = ShowUnitBlock(
        type="show_unit",
        show_id=show["show_id"],
        title=(title or "").strip() or None,
        show_date=show["show_date"],
        venue_name=venue.get("name") if isinstance(venue, dict) else None,
        location=_venue_location(venue),
        emphasis=emphasis,
        judgments=list(judgments or [])[:5],
        note=(note or "").strip() or None,
        visible_facets=sorted(facets, key=["guests", "listen", "setlist", "sources", "lineup", "recordings"].index),
        setlist_disclosure=setlist_disclosure,
        sets=_setlist_sections(payload, store, highlighted) if "setlist" in facets else [],
        setlist_note=(show.get("setlist_note") or None) if "setlist" in facets else None,
        guests=_guest_items(payload, store) if "guests" in facets else [],
        lineup=_show_lineup(payload, store) if "lineup" in facets else [],
        recordings=recordings,
        listen=listen if "listen" in facets else [],
        sources=(sources or [])[:4] if "sources" in facets else [],
        follow_up=(follow_up or "").strip() or None,
    )
    result_sources = list(listen_sources) if "listen" in facets else []
    result_sources.extend(
        SourceReference(source_id=item.source_id, kind="contextual_resource", label=item.source_type, url=item.url)
        for item in recordings
    )
    return block, result_sources


def _performance_listen_actions(context: dict[str, Any]) -> list[ListenAction]:
    """Link to this performance, then to the whole show."""

    song = context.get("song") if isinstance(context.get("song"), dict) else {}
    title = song.get("title") or "this performance"
    actions: list[ListenAction] = []
    seen: set[str] = set()

    def add(action: ListenAction) -> None:
        if action.url and action.url not in seen:
            seen.add(action.url)
            actions.append(action)

    listen = context.get("listen") if isinstance(context.get("listen"), dict) else {}
    archive_track = listen.get("archive_track_url")
    if isinstance(archive_track, str) and archive_track:
        add(ListenAction(label=f"Listen to {title}", url=archive_track, provider="archive"))
    release_track = listen.get("release_track_url")
    if isinstance(release_track, str) and release_track:
        add(ListenAction(label=f"Hear {title} on the official release", url=release_track, provider=_provider_for(release_track), is_official=True))
    video = listen.get("video_url")
    if isinstance(video, str) and video:
        add(ListenAction(label=f"Watch {title}", url=video, provider="youtube"))
    show_links = context.get("show_links") if isinstance(context.get("show_links"), list) else []
    for link_type, label in (("streaming-show-page", "Hear the full show"),):
        for link in show_links:
            if isinstance(link, dict) and link.get("link_type") == link_type and link.get("url"):
                add(ListenAction(label=label, url=link["url"], provider=_provider_for(link["url"], link.get("platform"))))
                break
        if len(actions) >= 3:
            break
    return actions[:3]


def _performance_unit(
    context: dict[str, Any],
    store: CanonicalStore,
    *,
    emphasis: Emphasis = "supporting",
    judgments: list[str] | None = None,
    note: str | None = None,
    sources: list[UnitSource] | None = None,
    follow_up: str | None = None,
) -> PerformanceUnitBlock | None:
    performance = context.get("performance")
    song = context.get("song")
    show = context.get("show")
    if not isinstance(performance, dict) or not isinstance(song, dict) or not isinstance(show, dict):
        return None
    if not performance.get("performance_id") or not song.get("song_id") or not show.get("show_id") or not song.get("title"):
        return None
    previous, next_ = _set_neighbors(context, store)
    venue = store.one("venues", show.get("venue_id", "")) if show.get("venue_id") else None
    show_label = " — ".join(part for part in [show.get("show_date"), venue.get("name") if venue else None] if part) or show["show_id"]
    return PerformanceUnitBlock(
        type="performance_unit",
        performance_id=performance["performance_id"],
        song_id=song["song_id"],
        song_title=song["title"],
        show_id=show["show_id"],
        show_date=show.get("show_date") or None,
        show_label=show_label,
        venue_name=venue.get("name") if venue else None,
        location=_venue_location(venue),
        set_label=performance.get("set_label") or None,
        position_in_set=performance.get("position_in_set") or None,
        emphasis=emphasis,
        judgments=list(judgments or [])[:5],
        note=(note or "").strip() or None,
        previous=previous,
        next=next_,
        listen=_performance_listen_actions(context),
        sources=(sources or [])[:4],
        follow_up=(follow_up or "").strip() or None,
    )


def _era_performance_item(context: dict[str, Any], store: CanonicalStore) -> EraPerformanceItem | None:
    performance = context.get("performance")
    song = context.get("song")
    show = context.get("show")
    if not isinstance(performance, dict) or not isinstance(song, dict) or not isinstance(show, dict):
        return None
    if not performance.get("performance_id") or not song.get("title") or not show.get("show_id"):
        return None
    venue = store.one("venues", show.get("venue_id", "")) if show.get("venue_id") else None
    show_date = show.get("show_date") or None
    show_label = " — ".join(part for part in [show_date, venue.get("name") if venue else None] if part) or show["show_id"]
    actions = _performance_listen_actions(context)
    play = next((action for action in actions if action.label.startswith(("Listen to ", "Hear "))), None)
    return EraPerformanceItem(
        performance_id=performance["performance_id"],
        song_id=song.get("song_id", ""),
        song_title=song["title"],
        show_id=show["show_id"],
        show_date=show_date,
        show_label=show_label,
        set_label=performance.get("set_label") or None,
        listen=play,
    )


def _era_unit(
    contexts: list[dict[str, Any]],
    store: CanonicalStore,
    *,
    title: str,
    span: str | None = None,
    note: str | None = None,
    sources: list[UnitSource] | None = None,
    follow_up: str | None = None,
) -> EraUnitBlock | None:
    items = [item for item in (_era_performance_item(context, store) for context in contexts) if item]
    if not items or not title.strip():
        return None
    return EraUnitBlock(
        type="era_unit",
        title=title.strip(),
        span=(span or "").strip() or None,
        note=(note or "").strip() or None,
        performances=items[:6],
        sources=(sources or [])[:4],
        follow_up=(follow_up or "").strip() or None,
    )


def _album_unit(
    payload: dict[str, Any],
    store: CanonicalStore,
    *,
    emphasis: Emphasis = "supporting",
    judgments: list[str] | None = None,
    note: str | None = None,
    title: str | None = None,
    visible_facets: list[str] | None = None,
    highlighted_song_ids: list[str] | None = None,
    sources: list[UnitSource] | None = None,
    follow_up: str | None = None,
) -> tuple[AlbumUnitBlock | None, list[SourceReference]]:
    """Hydrate one album unit from its release payload.

    Highlights are kept only for songs actually on this record, so a slip in
    the plan cannot mark a song that is not there. ``None`` preserves the full
    legacy projection for internal callers; a composer-supplied facet list is
    an explicit editorial selection, including an empty list.
    """

    release = payload.get("release")
    if not isinstance(release, dict) or not release.get("release_id"):
        return None, []

    payload_tracks = payload.get("tracks") if isinstance(payload.get("tracks"), list) else []
    own_song_ids = {track.get("song_id") for track in payload_tracks if isinstance(track, dict) and track.get("song_id")}
    highlighted = frozenset(sid for sid in (highlighted_song_ids or []) if sid in own_song_ids)
    facets = frozenset({"listen", "tracklist", "personnel", "sources"} if visible_facets is None else visible_facets)

    tracks = [
        AlbumTrackItem(
            track_number=track["track_number"],
            title=track.get("song_title") or track.get("title") or "",
            song_id=track.get("song_id"),
            performance_id=track.get("performance_id"),
            duration_seconds=track.get("duration_seconds"),
            highlighted=track.get("song_id") in highlighted,
            listen_url=track.get("spotify_track_url"),
        )
        for track in payload_tracks
        if isinstance(track, dict) and isinstance(track.get("track_number"), int)
    ][:30] if "tracklist" in facets else []

    personnel = [
        AlbumCreditItem(
            person_id=entry["person_id"],
            name=entry.get("name") or entry["person_id"],
            role=entry.get("role") or "performer",
            instrument=entry.get("instrument") or "",
        )
        for entry in (payload.get("personnel") or [])
        if isinstance(entry, dict) and entry.get("person_id")
    ][:20] if "personnel" in facets else []

    listen: list[ListenAction] = []
    album_url = release.get("spotify_album_url") or release.get("source_url")
    if "listen" in facets and isinstance(album_url, str) and album_url:
        listen.append(
            ListenAction(
                label=f"Listen to {release.get('title') or 'the record'}",
                url=album_url,
                provider=_provider_for(album_url),
                is_official=True,
            )
        )

    block = AlbumUnitBlock(
        type="album_unit",
        release_id=release["release_id"],
        title=(title or "").strip() or release.get("title") or "Untitled release",
        artist_name=release.get("artist_name") or None,
        release_date=release.get("release_date") or None,
        release_type=release.get("release_type") or "studio",
        emphasis=emphasis,
        judgments=list(judgments or [])[:5],
        note=(note or "").strip() or None,
        tracks=tracks,
        personnel=personnel,
        listen=listen,
        sources=(sources or [])[:4] if "sources" in facets else [],
        follow_up=(follow_up or "").strip() or None,
    )
    return block, []


def _url_index(payloads: list[dict[str, Any]]) -> dict[str, dict[str, str | None]]:
    """Map every URL the tools returned to the best label and source name near it.

    Stored resources, research records, site-search hits, read pages, archive
    reviews, links and releases all carry a URL beside a title-like field, so
    one walk over the turn's payloads is enough to name a source the composer
    cites by URL.
    """

    index: dict[str, dict[str, str | None]] = {}
    label_keys = ("title", "name", "source_description", "label")
    name_keys = ("source_name", "source", "site", "byline", "platform", "selector_name")
    url_keys = ("url", "source_url", "final_url", "spotify_album_url", "spotify_track_url")

    def visit(value: Any, inherited_name: str | None) -> None:
        if isinstance(value, dict):
            own_name = next((str(value[key]) for key in name_keys if isinstance(value.get(key), str) and value[key]), None)
            label = next((str(value[key]) for key in label_keys if isinstance(value.get(key), str) and value[key]), None)
            for key in url_keys:
                url = value.get(key)
                if isinstance(url, str) and url.startswith(("http://", "https://")) and url not in index:
                    index[url] = {"label": label, "source_name": own_name or inherited_name}
            for child in value.values():
                visit(child, own_name or inherited_name)
        elif isinstance(value, list):
            for child in value:
                visit(child, inherited_name)

    for payload in payloads:
        visit(payload, None)
    return index


def _unit_sources(
    requested: list[Any],
    grounded_urls: frozenset[str],
    payloads: list[dict[str, Any]],
) -> tuple[list[UnitSource], list[SourceReference]]:
    """Keep the composer's cited sources whose URLs the tools returned; name them from the payloads."""

    index = _url_index(payloads)
    items: list[UnitSource] = []
    sources: list[SourceReference] = []
    seen: set[str] = set()
    for entry in requested:
        url = getattr(entry, "url", None)
        if not isinstance(url, str) or url not in grounded_urls or url in seen:
            continue
        seen.add(url)
        named = index.get(url, {})
        host = urlparse(url).netloc.removeprefix("www.")
        label = (named.get("label") or host or url).strip()
        source_name = named.get("source_name")
        note = getattr(entry, "note", None)
        items.append(UnitSource(url=url, label=label[:200], source_name=source_name, note=(note or "").strip() or None))
        sources.append(SourceReference(source_id=f"url:{url}", kind="contextual_resource", label=label[:200], url=url))
    return items[:4], sources[:4]


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


def _show_lineup(payload: dict[str, Any], store: CanonicalStore) -> list[PerformerItem]:
    show = payload.get("show")
    assignments = payload.get("performers")
    if not isinstance(show, dict) or not isinstance(assignments, list):
        return []

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
            item = PerformerItem(person_id=person_id, name=person.get("name") or person_id, role=role, instruments=[instrument])
            grouped[key] = item
        elif instrument not in item.instruments:
            item.instruments.append(instrument)

    return list(grouped.values())[:24]


def _show_equipment(payload: dict[str, Any]) -> EquipmentListBlock | None:
    show = payload.get("show")
    equipment = payload.get("equipment")
    if not isinstance(show, dict) or not isinstance(equipment, list):
        return None

    items: list[EquipmentItem] = []
    seen: set[tuple[str, str, str]] = set()
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


def _show_recordings(payload: dict[str, Any], store: CanonicalStore) -> list[RecordingItem]:
    show = payload.get("show")
    recordings = (
        store.filtered_rows("recordings", show_id=show.get("show_id"))
        if isinstance(show, dict) and show.get("show_id")
        else payload.get("recordings")
    )
    if not isinstance(recordings, list):
        return []

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
    return items[:8]


def _song_overview(
    context: dict[str, Any],
    store: CanonicalStore,
    *,
    emphasis: Emphasis = "supporting",
    judgments: list[str] | None = None,
    note: str | None = None,
    visible_facets: list[str] | None = None,
    representative_performance_ids: list[str] | None = None,
    sources: list[UnitSource] | None = None,
    follow_up: str | None = None,
) -> SongOverviewBlock | None:
    song = context.get("song")
    if not isinstance(song, dict) or not song.get("song_id"):
        return None
    facets = frozenset(visible_facets) if visible_facets is not None else frozenset({"representatives"})
    performances = context.get("performances") if isinstance(context.get("performances"), list) else []

    credits: list[CreditItem] = []
    if "credits" in facets:
        for writer in context.get("writers", []) if isinstance(context.get("writers"), list) else []:
            person = store.one("people", writer.get("person_id", "")) if isinstance(writer, dict) else None
            credit_role = writer.get("writer_role", "") if isinstance(writer, dict) else ""
            if person and credit_role:
                credits.append(CreditItem(person_id=writer["person_id"], name=person.get("name") or writer["person_id"], role=credit_role))

    albums: list[SongReleaseItem] = []
    if "albums" in facets:
        all_albums = [
            SongReleaseItem(
                release_id=release["release_id"],
                title=release.get("title") or release["release_id"],
                release_date=release.get("release_date"),
                release_type=release.get("release_type") or "live",
            )
            for release in (context.get("releases") or [])
            if isinstance(release, dict) and release.get("release_id")
        ]
        # song_releases (data.py) orders releases earliest-first with undated
        # releases last, which is correct on its own terms. But truncating that
        # order to 6 can crowd a studio album out entirely behind live releases
        # that happen to carry a date. Present studio releases first so the
        # truncation never hides the studio record a user is most likely after.
        studio_albums = [album for album in all_albums if album.release_type == "studio"]
        other_albums = [album for album in all_albums if album.release_type != "studio"]
        albums = (studio_albums + other_albums)[:6]

    representatives: list[SongRepresentativePerformance] = []
    if "representatives" in facets:
        performance_items = {
            item.performance_id: item
            for item in _performance_items(performances, store)
        }
        representatives = [
            SongRepresentativePerformance(
                performance_id=item.performance_id,
                show_id=item.show_id,
                show_date=item.show_date,
                show_label=item.show_label,
                set_label=item.set_label,
                listen_url=item.listen_url,
            )
            for performance_id in (representative_performance_ids or [])
            if (item := performance_items.get(performance_id)) is not None
        ]

    history = _song_history(performances, store) if "history" in facets else None

    return SongOverviewBlock(
        type="song_overview",
        song_id=song["song_id"],
        title=song.get("title") or "Untitled song",
        original_artist=song.get("original_artist") or None,
        known_performance_count=len(performances),
        emphasis=emphasis,
        judgments=list(judgments or [])[:5],
        visible_facets=sorted(facets, key=["representatives", "history", "credits", "albums"].index),
        history=history,
        note=(note or "").strip() or None,
        representative_performances=representatives[:3],
        credits=credits[:12],
        source_ids=[f"canonical:{song['song_id']}"],
        albums=albums,
        sources=(sources or [])[:4],
        follow_up=(follow_up or "").strip() or None,
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
            )
        )
        sources.append(source)
    if not items:
        return None, []
    return (
        ArrangementSearchBlock(
            type="arrangement_search",
            title=f"Arrangements in {key_signature}",
            key_signature=key_signature,
            coverage_note=(
                search.get("coverage_note")
                if isinstance(search.get("coverage_note"), str)
                else "Each arrangement is one source's chart in this key."
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
                )
            )
        if not items:
            continue
        reported_count = guest.get("guest_show_count")
        count = reported_count if isinstance(reported_count, int) and reported_count == len(items) else len(items)
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
