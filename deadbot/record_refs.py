"""Facts the server looks up for records the model names by reference.

The model chooses which records to show, in what order, and writes its own
words about them; everything here comes from the store or from a tool result
this turn: the IDs in a result the model points at, a record's cover, the
shows a release draws on, a ranking's rows and counts, and the link or
playable tracks for a record an editorial item names.
"""

from __future__ import annotations

from typing import Any

from deadbot import composition
from deadbot.data import CanonicalStore
from deadbot.experience import EditorialLink, PlayableTrack, RankedListBlock, RankedListRow, fit
from deadbot.listening import musicbrainz_release_id, playable_show_tracks

# The ID column an aggregate_data result's rows carry, by what it grouped.
_AGGREGATION_ID_COLUMNS = {"song": "song_id", "venue": "venue_id", "guest": "person_id"}


def result_ids(payloads: list[dict[str, Any]], result_id: str, column: str) -> list[str]:
    """The ``column`` IDs in one tool result this turn, in its row order, without repeats.

    ``result_id`` names a query_catalog result (its ``result_id``) or an
    aggregate_data result (its ``aggregation_id``).
    """

    for payload in payloads:
        if payload.get("result_id") == result_id:
            columns, rows = payload.get("columns"), payload.get("rows")
            if not isinstance(columns, list) or not isinstance(rows, list) or column not in columns:
                return []
            position = columns.index(column)
            values = [row[position] for row in rows if isinstance(row, list) and len(row) > position]
        elif payload.get("aggregation_id") == result_id:
            query = payload.get("query") if isinstance(payload.get("query"), dict) else {}
            if _AGGREGATION_ID_COLUMNS.get(str(query.get("group_by"))) != column:
                return []
            values = [row.get("id") for row in payload.get("rows") or [] if isinstance(row, dict)]
        else:
            continue
        return list(dict.fromkeys(value for value in values if isinstance(value, str) and value))
    return []


def cover_thumbnail(release: dict[str, Any]) -> str | None:
    mbid = musicbrainz_release_id(release)
    return f"https://coverartarchive.org/release/{mbid}/front-250" if mbid else None


def release_shows(release_id: str, store: CanonicalStore) -> list[dict[str, Any]]:
    """The shows a release draws on, earliest first, each with its venue row, in four queries."""

    tracks = store.filtered_rows("official_release_tracks", release_id=release_id)
    performances = store.rows_in("performances", "performance_id", {row.get("performance_id", "") for row in tracks if row.get("performance_id")})
    shows = store.rows_in("shows", "show_id", {row.get("show_id", "") for row in performances})
    venues = {row["venue_id"]: row for row in store.rows_in("venues", "venue_id", {row.get("venue_id", "") for row in shows if row.get("venue_id")})}
    return sorted(({**show, "venue": venues.get(show.get("venue_id", ""))} for show in shows), key=lambda show: show.get("show_date") or "")


def ranked_list_block(
    payload: dict[str, Any],
    *,
    count: int | None,
    title: str | None,
    note: str | None,
    row_notes: dict[str, str],
) -> RankedListBlock | None:
    """The top ``count`` rows of one aggregate_data payload, exactly as the tool counted them."""

    columns = payload.get("columns")
    rows = payload.get("rows")
    if not isinstance(columns, list) or not isinstance(rows, list):
        return None
    dimension = next((column for column in columns if isinstance(column, dict) and column.get("key") != "value"), None)
    if dimension is None:
        return None
    key = dimension.get("key")
    shown = rows if count is None or count < 1 else rows[:count]
    ranked: list[RankedListRow] = []
    for position, row in enumerate(shown, start=1):
        if not isinstance(row, dict) or not isinstance(row.get("value"), int) or row.get(key) is None:
            continue
        row_id = row.get("id") if isinstance(row.get("id"), str) else None
        label = str(row[key])
        ranked.append(RankedListRow(rank=position, id=row_id, label=label, value=row["value"], note=row_notes.get(row_id or "") or row_notes.get(label)))
    if not ranked:
        return None
    excluded = payload.get("excluded_count") if isinstance(payload.get("excluded_count"), int) else 0
    return RankedListBlock(
        type="ranked_list",
        aggregation_id=str(payload.get("aggregation_id")),
        title=(title or "").strip() or str(payload.get("metric_label") or "Ranking"),
        note=(note or "").strip() or None,
        dimension_label=str(dimension.get("label") or "Item"),
        metric_label=str(payload.get("metric_label") or "Count"),
        rows=fit(ranked, "ranked list rows"),
        more_count=max(0, len(rows) - len(shown)) + excluded,
    )


def record_link(kind: str, record_id: str, store: CanonicalStore) -> tuple[EditorialLink | None, list[PlayableTrack]]:
    """The link and playable tracks for a show, performance or release an editorial item names."""

    if kind == "release":
        release = store.resolve_release(record_id)
        url = (release or {}).get("spotify_album_url") or (release or {}).get("source_url")
        if not release or not url:
            return None, []
        return EditorialLink(url=url, label=f"Listen to {release.get('title') or 'the record'}"), []
    if kind == "show":
        show = store.resolve_show(record_id)
        return None, (playable_show_tracks(show["show_id"], store)[0] if show else [])
    if kind == "performance":
        context = store.performance_context(record_id)
        if not context:
            return None, []
        audio = composition._audio(context.get("listen"))
        song = context.get("song") or {}
        if audio["audio_url"]:
            performance = context.get("performance") or {}
            return None, [
                PlayableTrack(
                    performance_id=record_id,
                    title=song.get("title") or "Performance",
                    audio_url=audio["audio_url"],
                    duration_seconds=audio["duration_seconds"],
                    set_label=performance.get("set_label") or None,
                )
            ]
        url = composition._listen_url(context)
        return (EditorialLink(url=url, label=f"Listen to {song.get('title') or 'this performance'}") if url else None), []
    return None, []
