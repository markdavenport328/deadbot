"""Listening paths the in-page player can use: a show's tape and a listening hero.

The model decides that a page leads with listening and which show or record
it is; this module hydrates what that needs from the library: the playable
Internet Archive tracks of one tape in show order, a cover image, and the
identity a hero names. It reads the store only through its query layer
(``one``, ``filtered_rows``, ``rows_in``), never ``tables`` directly, so the
CSV, PostgreSQL and SQLite stores behave the same. Store values are strings.
"""

from __future__ import annotations

import re
from collections import Counter
from typing import Any

from deadbot.data import CanonicalStore, _archive_identifier
from deadbot.experience import EditorialLink, ListeningHeroBlock, PlayableTrack

_MUSICBRAINZ_RELEASE = re.compile(r"musicbrainz\.org/release/([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})", re.IGNORECASE)

TRACK_LIMIT = 60


def _number(value: Any, missing: int = 10**6) -> int:
    text = str(value or "").strip()
    return int(text) if text.isdigit() else missing


_MONTHS = ("January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December")


def _long_date(iso: str) -> str:
    """'1977-05-08' as 'May 8, 1977'; anything else unchanged."""

    match = re.fullmatch(r"(\d{4})-(\d{2})-(\d{2})", iso or "")
    if not match or not 1 <= int(match.group(2)) <= 12:
        return iso or ""
    return f"{_MONTHS[int(match.group(2)) - 1]} {int(match.group(3))}, {match.group(1)}"


def archive_thumbnail(identifier: str | None) -> str | None:
    return f"https://archive.org/services/img/{identifier}" if identifier else None


def archive_details(identifier: str | None) -> str | None:
    return f"https://archive.org/details/{identifier}" if identifier else None


def musicbrainz_release_id(release: dict[str, Any] | None) -> str | None:
    """The MusicBrainz release ID in an official release's source URL, when it has one."""

    if not isinstance(release, dict):
        return None
    match = _MUSICBRAINZ_RELEASE.search(str(release.get("source_url") or ""))
    return match.group(1).lower() if match else None


def cover_art_url(release: dict[str, Any] | None) -> str | None:
    mbid = musicbrainz_release_id(release)
    return f"https://coverartarchive.org/release/{mbid}/front-500" if mbid else None


def playable_show_tracks(show_id: str, store: CanonicalStore, identifier: str | None = None) -> tuple[list[PlayableTrack], str | None]:
    """One tape's playable tracks for a show, in show order, and that tape's identifier.

    With ``identifier`` the tracks come from that Internet Archive item;
    without it, from the item that covers the most of the show. Each
    performance keeps one track, chosen by link ID the way the store's
    listening paths choose, so the same URL plays everywhere on the page.
    """

    performances = [row for row in store.filtered_rows("performances", show_id=show_id) if row.get("performance_id")]
    if not performances:
        return [], None
    performance_ids = [row["performance_id"] for row in performances]
    by_tape: dict[str, dict[str, tuple[str, str, str]]] = {}
    for link in store.rows_in("performance_links", "performance_id", performance_ids):
        if link.get("platform") != "archive" or link.get("link_type") != "recording-track":
            continue
        url = link.get("url") or ""
        tape = _archive_identifier(url)
        if not tape:
            continue
        candidate = (link.get("performance_link_id") or "", url, link.get("duration_seconds") or "")
        chosen = by_tape.setdefault(tape, {})
        performance_id = link.get("performance_id") or ""
        if performance_id not in chosen or candidate < chosen[performance_id]:
            chosen[performance_id] = candidate
    if not by_tape:
        return [], None
    if identifier not in by_tape:
        # The tape that covers the most of the show; ties go to the lower identifier.
        identifier = min(by_tape, key=lambda tape: (-len(by_tape[tape]), tape))
    chosen = by_tape[identifier]
    songs = {row["song_id"]: row for row in store.rows_in("songs", "song_id", {row.get("song_id", "") for row in performances})}
    ordered = sorted(performances, key=lambda row: (_number(row.get("set_number")), _number(row.get("position_in_set")), row["performance_id"]))
    tracks: list[PlayableTrack] = []
    for row in ordered:
        link = chosen.get(row["performance_id"])
        title = (songs.get(row.get("song_id", "")) or {}).get("title")
        if not link or not title:
            continue
        duration = str(link[2]).strip()
        tracks.append(
            PlayableTrack(
                performance_id=row["performance_id"],
                title=title,
                audio_url=link[1],
                duration_seconds=int(duration) if duration.isdigit() else None,
                set_label=row.get("set_label") or None,
            )
        )
    return tracks[:TRACK_LIMIT], identifier


def _show_release(show_id: str, store: CanonicalStore, performance_ids: list[str]) -> dict[str, Any] | None:
    """The official release most devoted to this show that has cover art.

    The release carrying the most of the show's performances wins; a tie
    goes to the release with the fewest tracks overall, the one that is this
    show rather than a box set that contains it.
    """

    if not performance_ids:
        return None
    counts = Counter(row.get("release_id", "") for row in store.rows_in("official_release_tracks", "performance_id", performance_ids))
    counts.pop("", None)
    if not counts:
        return None
    releases = [row for row in store.rows_in("official_releases", "release_id", set(counts)) if musicbrainz_release_id(row)]
    if not releases:
        return None
    sizes = Counter(row.get("release_id", "") for row in store.rows_in("official_release_tracks", "release_id", {row["release_id"] for row in releases}))
    return min(releases, key=lambda row: (-counts[row["release_id"]], sizes[row["release_id"]], row["release_id"]))


def _start_index(tracks: list[PlayableTrack], start_set: str | None, start_performance_id: str | None) -> int:
    if start_performance_id:
        for index, track in enumerate(tracks):
            if track.performance_id == start_performance_id:
                return index
    wanted = (start_set or "").strip().casefold()
    if wanted:
        for index, track in enumerate(tracks):
            if (track.set_label or "").strip().casefold() == wanted:
                return index
    return 0


def listening_hero(
    store: CanonicalStore,
    *,
    show_id: str | None,
    release_id: str | None,
    line: str | None = None,
    play_label: str | None = None,
    start_set: str | None = None,
    start_performance_id: str | None = None,
    link: EditorialLink | None = None,
) -> ListeningHeroBlock | None:
    """Hydrate a listening hero for one show or one record.

    A show hero plays the show's tape in-page from the set or song the model
    named, and shows the cover of the official release most devoted to the
    show, else the tape's own image. A record hero shows its cover and plays
    it where the library links it.
    """

    show = store.one("shows", show_id) if show_id else None
    release = store.one("official_releases", release_id) if release_id else None
    if not show and not release:
        return None

    common = {
        "line": (line or "").strip() or None,
        "play_label": (play_label or "").strip() or None,
        "link": link,
    }
    if show:
        venue = store.one("venues", show.get("venue_id", "")) if show.get("venue_id") else None
        venue_name = (venue or {}).get("name") or None
        location = ", ".join(part for part in ((venue or {}).get("city"), (venue or {}).get("state_region")) if part) or None
        tracks, identifier = playable_show_tracks(show["show_id"], store)
        performance_ids = [row["performance_id"] for row in store.filtered_rows("performances", show_id=show["show_id"]) if row.get("performance_id")]
        cover_release = release if cover_art_url(release) else _show_release(show["show_id"], store, performance_ids)
        image_url = cover_art_url(cover_release) or archive_thumbnail(identifier)
        date = show.get("show_date") or ""
        place = ", ".join(part for part in (venue_name or "this show", _long_date(date)) if part)
        if cover_art_url(cover_release):
            image_alt = f"Cover of {cover_release.get('title') or 'the official release'}, the official release of {place}"
        elif image_url:
            image_alt = f"Internet Archive image for the tape of {place}"
        else:
            image_alt = None
        play_url = None
        if not tracks:
            spotify = (cover_release or {}).get("spotify_album_url") or ""
            stream = next(
                (row.get("url") for row in store.filtered_rows("show_links", show_id=show["show_id"]) if row.get("link_type") == "streaming-show-page" and row.get("url")),
                None,
            )
            play_url = spotify or stream or None
        return ListeningHeroBlock(
            type="listening_hero",
            show_id=show["show_id"],
            release_id=(cover_release or {}).get("release_id") or None,
            venue_name=venue_name,
            location=location,
            show_date=date or None,
            queue=tracks,
            start_index=_start_index(tracks, start_set, start_performance_id),
            play_url=play_url,
            recording_identifier=identifier,
            recording_details_url=archive_details(identifier),
            image_url=image_url,
            image_alt=image_alt,
            **common,
        )

    image_url = cover_art_url(release)
    return ListeningHeroBlock(
        type="listening_hero",
        release_id=release["release_id"],
        release_title=release.get("title") or None,
        release_date=release.get("release_date") or None,
        play_url=release.get("spotify_album_url") or None,
        image_url=image_url,
        image_alt=f"Cover of {release.get('title') or 'this record'}" if image_url else None,
        **common,
    )
