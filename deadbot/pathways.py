"""Compact lore pathways attached to entity results.

A pathway is not source text: it is a small, always-present inventory of the
lore already cataloged for one song, show or release (resources, a reviewed
source trail, selection-signal counts) or, when nothing is cataloged, the
research sites worth searching instead. Every read here is batched across the
whole call -- one ``rows_in`` per relation table regardless of how many
entities were requested -- so attaching pathways to a list of search results
never costs a lookup per entity.
"""

from __future__ import annotations

import json
from typing import Any, Iterable

from deadbot.data import CanonicalStore
from deadbot.lore_source_trails import source_trails_for_entity
from deadbot.selection_signals import SelectionSignalError, stored_selection_entries

# Inventory rows, not lore: a catalog/lyrics page names a song but carries no
# musical or historical commentary a visitor would open as a pathway.
_EXCLUDED_RESOURCE_TYPES = {"catalog-work-search", "lyrics-and-credits", "catalog-song-page"}
_MAX_TOP_RESOURCES = 3
# A little under the ~900-character target so real-world long titles and URLs
# still leave headroom once cataloged/research_routes overhead is added.
_CHAR_BUDGET = 860

# The Global constraints' research-site names for a cataloged-nothing entity,
# in the order to suggest them.
_RESEARCH_ROUTES: dict[str, tuple[str, ...]] = {
    "song": ("Grateful Dead Guide (Deadessays)", "Deadhead High", "Dead.net"),
    "show": (
        "Lost Live Dead",
        "Dead Sources",
        "Grateful Dead Archive Online",
        "Internet Archive Grateful Dead collection",
    ),
    "release": ("Dead.net", "Dead Sources"),
}


def _selection_entries(store: CanonicalStore) -> list[dict[str, Any]] | None:
    """The reviewed selection evidence, or None when this store cannot serve it."""

    try:
        return stored_selection_entries(store)
    except SelectionSignalError:
        return None


def _dedupe(values: Iterable[str]) -> list[str]:
    return list(dict.fromkeys(value for value in values if value))


def _resource_summary(resource_rows: list[dict[str, str]]) -> dict[str, Any] | None:
    """Project cataloged resource rows into a compact, source-attributed count.

    Catalog/lyrics rows are inventory, not lore, and never reach this summary
    or its ``top`` picks.
    """

    lore = [row for row in resource_rows if row.get("resource_type") not in _EXCLUDED_RESOURCE_TYPES]
    if not lore:
        return None
    by_type: dict[str, int] = {}
    for row in lore:
        kind = row.get("resource_type") or "resource"
        by_type[kind] = by_type.get(kind, 0) + 1
    top = []
    for row in lore[:_MAX_TOP_RESOURCES]:
        item = {
            "title": row.get("title") or "",
            "source_name": row.get("source_name") or "",
            "resource_type": row.get("resource_type") or "",
            "url": row.get("source_url") or "",
        }
        top.append({key: value for key, value in item.items() if value})
    return {"count": len(lore), "by_type": by_type, "top": top}


def _trail_summary(entity_type: str, entity_id: str) -> dict[str, Any] | None:
    """A compact summary of the reviewed source trail: a count and one why-open note."""

    trail = source_trails_for_entity(entity_type, entity_id)
    records = trail.get("records") or []
    if not records:
        return None
    return {"link_count": len(records), "why_open": records[0].get("why_open") or ""}


def _selection_summary(
    entries: list[dict[str, Any]],
    *,
    performance_ids: frozenset[str],
    matching_show_ids: frozenset[str],
    entity_show_id: str | None,
) -> dict[str, Any] | None:
    """Count reviewed selection entries naming this song's performances/shows or this show.

    Signals stay source-attributed: a count and the distinct sources that
    named it, never a combined score.
    """

    count = 0
    sources: list[str] = []
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        matched = False
        if entity_show_id is not None:
            candidate_shows = entry.get("candidate_show_ids")
            matched = isinstance(candidate_shows, list) and entity_show_id in candidate_shows
        else:
            candidate_performances = entry.get("candidate_performance_ids")
            if isinstance(candidate_performances, list) and any(
                pid in performance_ids for pid in candidate_performances if isinstance(pid, str)
            ):
                matched = True
            if not matched:
                candidate_shows = entry.get("candidate_show_ids")
                if isinstance(candidate_shows, list) and any(
                    sid in matching_show_ids for sid in candidate_shows if isinstance(sid, str)
                ):
                    matched = True
        if not matched:
            continue
        count += 1
        source = entry.get("source")
        if isinstance(source, str) and source not in sources:
            sources.append(source)
    if count == 0:
        return None
    return {"count": count, "sources": sources}


def _notable_versions(
    release_track_performance_ids: Iterable[str],
    performance_ids: frozenset[str],
    entries: list[dict[str, Any]] | None,
) -> dict[str, Any] | None:
    """Counts of the song's performances an official release or a fan vote singled out."""

    official = {pid for pid in release_track_performance_ids if pid in performance_ids}
    fan_voted: set[str] = set()
    for entry in entries or ():
        if not isinstance(entry, dict) or entry.get("signal_type") != "fan_ranked_version":
            continue
        candidates = entry.get("candidate_performance_ids")
        if isinstance(candidates, list):
            fan_voted.update(pid for pid in candidates if isinstance(pid, str) and pid in performance_ids)
    if not official and not fan_voted:
        return None
    return {"official_release_versions": len(official), "fan_vote_versions": len(fan_voted)}


def _size(payload: dict[str, Any]) -> int:
    return len(json.dumps(payload, ensure_ascii=False, separators=(",", ":")))


def _fit_budget(payload: dict[str, Any]) -> dict[str, Any]:
    """Keep one pathways object under the compactness budget.

    A song or show with unusually long titles, source names, or URLs can
    still push three ``top`` resources over budget; drop the least-recently
    added one first, then shorten the source-trail note, rather than let the
    payload grow unbounded.
    """

    if _size(payload) <= _CHAR_BUDGET:
        return payload
    resources = payload.get("resources")
    if isinstance(resources, dict) and resources.get("top"):
        top = resources["top"]
        while top and _size(payload) > _CHAR_BUDGET:
            top.pop()
        if not top:
            resources.pop("top", None)
    song_lore = payload.get("song_lore")
    if isinstance(song_lore, list):
        while len(song_lore) > 1 and _size(payload) > _CHAR_BUDGET:
            song_lore.pop()
    trail = payload.get("source_trail")
    if isinstance(trail, dict) and isinstance(trail.get("why_open"), str) and _size(payload) > _CHAR_BUDGET:
        why_open = trail["why_open"]
        if len(why_open) > 40:
            trail["why_open"] = why_open[:57].rstrip() + "…"
    return payload


def pathways_for(store: CanonicalStore, entities: list[tuple[str, str]]) -> dict[str, dict[str, Any]]:
    """Return the compact pathways object for each ``(entity_type, entity_id)``.

    ``entity_type`` is ``"song"``, ``"show"`` or ``"release"``. Every relation
    table this needs is read once per call across every entity, never once
    per entity, so attaching pathways to a batch of search results costs a
    handful of ``rows_in`` calls regardless of how many entities were passed.
    """

    song_ids = {entity_id for kind, entity_id in entities if kind == "song"}
    show_ids = {entity_id for kind, entity_id in entities if kind == "show"}
    release_ids = {entity_id for kind, entity_id in entities if kind == "release"}

    resource_ids_needed: set[str] = set()
    resource_songs_by_song: dict[str, list[str]] = {}
    resource_performances_by_song: dict[str, list[str]] = {}
    performance_ids_by_song: dict[str, frozenset[str]] = {}
    show_ids_by_song: dict[str, frozenset[str]] = {}
    release_track_performance_ids_by_song: dict[str, list[str]] = {}

    if song_ids:
        performances = store.rows_in("performances", "song_id", song_ids)
        performance_ids_by_song = {
            song_id: frozenset(
                row.get("performance_id", "") for row in performances if row.get("song_id") == song_id
            )
            for song_id in song_ids
        }
        show_ids_by_song = {
            song_id: frozenset(row.get("show_id", "") for row in performances if row.get("song_id") == song_id)
            for song_id in song_ids
        }
        all_performance_ids = {row.get("performance_id", "") for row in performances}

        for row in store.rows_in("resource_songs", "song_id", song_ids):
            song_id, resource_id = row.get("song_id", ""), row.get("resource_id", "")
            if song_id and resource_id:
                resource_songs_by_song.setdefault(song_id, []).append(resource_id)
                resource_ids_needed.add(resource_id)

        performance_resources = store.rows_in("resource_performances", "performance_id", all_performance_ids)
        performance_id_to_songs: dict[str, list[str]] = {}
        for song_id, performance_ids in performance_ids_by_song.items():
            for performance_id in performance_ids:
                performance_id_to_songs.setdefault(performance_id, []).append(song_id)
        for row in performance_resources:
            performance_id, resource_id = row.get("performance_id", ""), row.get("resource_id", "")
            if not resource_id:
                continue
            resource_ids_needed.add(resource_id)
            for song_id in performance_id_to_songs.get(performance_id, []):
                resource_performances_by_song.setdefault(song_id, []).append(resource_id)

        release_tracks = store.rows_in("official_release_tracks", "performance_id", all_performance_ids)
        for row in release_tracks:
            performance_id = row.get("performance_id", "")
            for song_id in performance_id_to_songs.get(performance_id, []):
                release_track_performance_ids_by_song.setdefault(song_id, []).append(performance_id)

    resource_shows_by_show: dict[str, list[str]] = {}
    if show_ids:
        for row in store.rows_in("resource_shows", "show_id", show_ids):
            show_id, resource_id = row.get("show_id", ""), row.get("resource_id", "")
            if show_id and resource_id:
                resource_shows_by_show.setdefault(show_id, []).append(resource_id)
                resource_ids_needed.add(resource_id)

    resource_releases_by_release: dict[str, list[str]] = {}
    if release_ids:
        try:
            release_resource_rows = store.rows_in("resource_releases", "release_id", release_ids)
        except Exception:
            # A store without a resource_releases table (every store today)
            # has no release-level resources cataloged; treat that as none
            # rather than failing the whole pathways attachment.
            release_resource_rows = []
        for row in release_resource_rows:
            release_id, resource_id = row.get("release_id", ""), row.get("resource_id", "")
            if release_id and resource_id:
                resource_releases_by_release.setdefault(release_id, []).append(resource_id)
                resource_ids_needed.add(resource_id)

    lore_songs_by_release: dict[str, list[tuple[str, str]]] = {}
    track_resources_by_song: dict[str, list[str]] = {}
    if release_ids:
        track_song_ids_by_release: dict[str, list[str]] = {}
        for row in store.rows_in("official_release_tracks", "release_id", release_ids):
            release_id, song_id = row.get("release_id", ""), row.get("song_id", "")
            if release_id and song_id:
                track_song_ids_by_release.setdefault(release_id, []).append(song_id)
        track_song_ids = {song_id for song_ids in track_song_ids_by_release.values() for song_id in song_ids}
        for row in store.rows_in("resource_songs", "song_id", track_song_ids):
            song_id, resource_id = row.get("song_id", ""), row.get("resource_id", "")
            if song_id and resource_id:
                track_resources_by_song.setdefault(song_id, []).append(resource_id)
                resource_ids_needed.add(resource_id)
        titles = {row["song_id"]: row.get("title") or row["song_id"] for row in store.rows_in("songs", "song_id", track_song_ids)}
        for release_id, song_ids in track_song_ids_by_release.items():
            lore_songs_by_release[release_id] = [(song_id, titles.get(song_id, song_id)) for song_id in _dedupe(song_ids) if song_id in track_resources_by_song]

    resources_by_id: dict[str, dict[str, str]] = {}
    if resource_ids_needed:
        resources_by_id = {
            row["resource_id"]: row for row in store.rows_in("resources", "resource_id", resource_ids_needed)
        }

    entries = _selection_entries(store) if (song_ids or show_ids) else None

    result: dict[str, dict[str, Any]] = {}
    for kind, entity_id in entities:
        if entity_id in result or kind not in _RESEARCH_ROUTES:
            continue
        payload: dict[str, Any] = {}
        cataloged = False

        if kind == "song":
            resource_ids = _dedupe(
                [*resource_songs_by_song.get(entity_id, []), *resource_performances_by_song.get(entity_id, [])]
            )
            resources = _resource_summary([resources_by_id[rid] for rid in resource_ids if rid in resources_by_id])
            if resources:
                payload["resources"] = resources
                cataloged = True

            trail = _trail_summary("song", entity_id)
            if trail:
                payload["source_trail"] = trail
                cataloged = True

            if entries is not None:
                selections = _selection_summary(
                    entries,
                    performance_ids=performance_ids_by_song.get(entity_id, frozenset()),
                    matching_show_ids=show_ids_by_song.get(entity_id, frozenset()),
                    entity_show_id=None,
                )
                if selections:
                    payload["selections"] = selections
                    cataloged = True

            notable = _notable_versions(
                release_track_performance_ids_by_song.get(entity_id, []),
                performance_ids_by_song.get(entity_id, frozenset()),
                entries,
            )
            if notable:
                payload["notable_versions"] = notable

        elif kind == "show":
            resource_ids = _dedupe(resource_shows_by_show.get(entity_id, []))
            resources = _resource_summary([resources_by_id[rid] for rid in resource_ids if rid in resources_by_id])
            if resources:
                payload["resources"] = resources
                cataloged = True

            trail = _trail_summary("show", entity_id)
            if trail:
                payload["source_trail"] = trail
                cataloged = True

            if entries is not None:
                selections = _selection_summary(
                    entries,
                    performance_ids=frozenset(),
                    matching_show_ids=frozenset(),
                    entity_show_id=entity_id,
                )
                if selections:
                    payload["selections"] = selections
                    cataloged = True

        else:  # release
            resource_ids = _dedupe(resource_releases_by_release.get(entity_id, []))
            resources = _resource_summary([resources_by_id[rid] for rid in resource_ids if rid in resources_by_id])
            if resources:
                payload["resources"] = resources
                cataloged = True

            song_lore = [
                {"song_id": song_id, "title": title}
                for song_id, title in lore_songs_by_release.get(entity_id, [])
                if _resource_summary([resources_by_id[rid] for rid in track_resources_by_song.get(song_id, []) if rid in resources_by_id])
            ][:6]
            if song_lore:
                payload["song_lore"] = song_lore

        entity_payload = {"cataloged": cataloged, **payload, "research_routes": list(_RESEARCH_ROUTES[kind])}
        result[entity_id] = _fit_budget(entity_payload)

    return result
