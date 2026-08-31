"""Runtime access to reviewed, source-attributed selection signals."""

from __future__ import annotations

from typing import Any
from urllib.parse import urlparse

from deadbot.data import CanonicalStore


class SelectionSignalError(ValueError):
    """Raised when a reviewed selection packet cannot be used safely."""


def _https_url(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    parsed = urlparse(value)
    if parsed.scheme != "https" or not parsed.netloc or parsed.username or parsed.password:
        return None
    return value


def _stored_entries(store: CanonicalStore) -> list[dict[str, Any]]:
    reader = getattr(store, "selection_signal_rows", None)
    if not callable(reader):
        raise SelectionSignalError("Selection signals require the PostgreSQL runtime store.")
    try:
        entries = reader()
    except Exception as error:
        raise SelectionSignalError("The PostgreSQL selection-signal store is unavailable.") from error
    if not isinstance(entries, list) or not all(isinstance(entry, dict) for entry in entries):
        raise SelectionSignalError("The PostgreSQL selection-signal store is invalid.")
    return entries


def selection_signal_summary(store: CanonicalStore) -> dict[str, Any]:
    """Return a compact factual summary from PostgreSQL, never a local file."""

    entries = _stored_entries(store)
    by_source: dict[str, int] = {}
    by_resolution_state: dict[str, int] = {}
    source_constraints: dict[str, str] = {}
    for entry in entries:
        source = entry.get("source")
        state = entry.get("resolution_state")
        if isinstance(source, str):
            by_source[source] = by_source.get(source, 0) + 1
        if isinstance(state, str):
            by_resolution_state[state] = by_resolution_state.get(state, 0) + 1
        packet = entry.get("review_packet")
        if isinstance(packet, dict) and isinstance(packet.get("source_constraints"), dict):
            source_constraints = {
                key: value for key, value in packet["source_constraints"].items()
                if isinstance(key, str) and isinstance(value, str)
            }
    return {
        "entry_count": len(entries),
        "by_source": by_source,
        "by_resolution_state": by_resolution_state,
        "source_constraints": source_constraints,
    }


def load_selection_signals(store: CanonicalStore) -> dict[str, Any]:
    """Return the complete reviewed signal inventory with canonical resolution state.

    This deliberately preserves distinctions between editorial selections, fan
    rankings, official-release candidates, and individual curator picks. A
    held row remains visible as held rather than being silently transformed
    into a recommendation.
    """

    entries = _stored_entries(store)
    signals: list[dict[str, Any]] = []
    for index, entry in enumerate(entries, start=1):
        if not isinstance(entry, dict):
            continue
        source = entry.get("source")
        signal_type = entry.get("signal_type")
        resolution_state = entry.get("resolution_state")
        if not all(isinstance(value, str) and value for value in (source, signal_type, resolution_state)):
            continue
        result: dict[str, Any] = {
            "signal_id": str(entry.get("source_record_id") or f"{source}:{index}"),
            "source": source,
            "signal_type": signal_type,
            "resolution_state": resolution_state,
        }
        for field in (
            "selection_label", "source_label", "source_handle", "source_context",
            "source_provenance", "identity_state", "collection_state", "recommendation_rank",
            "fan_vote_count", "release_candidate_id", "release_status", "title", "era_label",
        ):
            value = entry.get(field)
            if isinstance(value, (str, int)) and value != "":
                result[field] = value
        source_url = _https_url(entry.get("source_url"))
        if source_url:
            result["source_url"] = source_url
        show_ids = entry.get("candidate_show_ids")
        if isinstance(show_ids, list) and all(isinstance(value, str) for value in show_ids):
            shows = []
            for show_id in show_ids:
                show = store.one("shows", show_id)
                if not show:
                    continue
                venue = store.one("venues", show.get("venue_id", ""))
                shows.append(
                    {
                        "show_id": show_id,
                        "show_date": show.get("show_date"),
                        "venue_name": venue.get("name") if venue else None,
                    }
                )
            result["candidate_shows"] = shows
        performance_ids = entry.get("candidate_performance_ids")
        if isinstance(performance_ids, list) and all(isinstance(value, str) for value in performance_ids):
            performances = []
            for performance_id in performance_ids:
                performance = store.one("performances", performance_id)
                if not performance:
                    continue
                song = store.one("songs", performance.get("song_id", ""))
                performances.append(
                    {
                        "performance_id": performance_id,
                        "show_id": performance.get("show_id"),
                        "song_id": performance.get("song_id"),
                        "song_title": song.get("title") if song else None,
                    }
                )
            result["candidate_performances"] = performances
        signals.append(result)
    return {
        "selection_signals": signals,
        "source_constraints": selection_signal_summary(store)["source_constraints"],
        "coverage_note": (
            "These are source-attributed signals with explicit resolution and access states, "
            "not one combined score or an objective best-of ranking."
        ),
    }


def load_show_selections(store: CanonicalStore) -> list[dict[str, Any]]:
    """Return each fully resolved, source-attributed show selection.

    A returned selection is a source's point of view. Held rows stay absent so
    the model cannot turn an ambiguous signal into a definite recommendation.
    """

    entries = _stored_entries(store)

    selections: dict[tuple[str, str], dict[str, Any]] = {}
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        label = entry.get("selection_label")
        source_url = _https_url(entry.get("source_url"))
        show_ids = entry.get("candidate_show_ids")
        if (
            entry.get("signal_type") != "critic_editorial_show_selection"
            or entry.get("resolution_state") != "resolved_unique_show"
            or not isinstance(label, str)
            or not source_url
            or not isinstance(show_ids, list)
            or len(show_ids) != 1
        ):
            continue
        show = store.one("shows", show_ids[0])
        venue = store.one("venues", show.get("venue_id", "")) if show else None
        if not show or not venue or show.get("show_date") != entry.get("show_date"):
            continue
        key = (label, source_url)
        selection = selections.setdefault(
            key,
            {
                "selection_id": f"critic-show-selection-{len(selections) + 1}",
                "title": label,
                "selection_type": "critic/editorial selection",
                "selector_name": "David Fricke / Rolling Stone",
                "source_url": source_url,
                "coverage_note": (
                    "This is one source-attributed editorial selection, not a Deadbot ranking, "
                    "listener consensus, or a complete map of notable Grateful Dead shows."
                ),
                "items": [],
            },
        )
        selection["items"].append(
            {
                "show_id": show["show_id"],
                "show_date": show["show_date"],
                "venue_name": venue.get("name") or "Unknown venue",
                "location": ", ".join(
                    value for value in (venue.get("city"), venue.get("state_region"), venue.get("country")) if value
                ),
            }
        )
    return [selection for selection in selections.values() if selection["items"]]
