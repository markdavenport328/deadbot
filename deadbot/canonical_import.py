"""The reviewed canonical CSVs as a database-neutral contract.

Every database writer (the SQLite builder, and the PostgreSQL importer while
it remains) reads and validates input through this module, so a CSV that one
accepts the other accepts too. Standard library only: Vercel's build step
imports this before any dependency is installed.
"""

from __future__ import annotations

import csv
import hashlib
import json
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping, Sequence


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CANONICAL_DIR = ROOT / "data" / "canonical"
DEFAULT_SELECTION_EVIDENCE_PATH = ROOT / "data" / "editorial" / "selection-evidence-review.json"


Converter = Callable[[str], Any]


def _as_date(value: str) -> date:
    return date.fromisoformat(value)


def _as_int(value: str) -> int:
    return int(value)


def _as_float(value: str) -> float:
    return float(value)


def _as_bool(value: str) -> bool:
    normalized = value.strip().lower()
    if normalized in {"true", "t", "1", "yes"}:
        return True
    if normalized in {"false", "f", "0", "no"}:
        return False
    raise ValueError(f"expected a boolean, got {value!r}")


@dataclass(frozen=True)
class TableSpec:
    """The exact CSV/database contract for one canonical table."""

    name: str
    columns: tuple[str, ...]
    nullable: frozenset[str] = frozenset()
    converters: Mapping[str, Converter] = field(default_factory=dict)

    @property
    def csv_name(self) -> str:
        return f"{self.name}.csv"


def _spec(
    name: str,
    columns: str,
    *,
    nullable: Iterable[str] = (),
    dates: Iterable[str] = (),
    integers: Iterable[str] = (),
    floats: Iterable[str] = (),
    booleans: Iterable[str] = (),
) -> TableSpec:
    converters: dict[str, Converter] = {}
    converters.update((column, _as_date) for column in dates)
    converters.update((column, _as_int) for column in integers)
    converters.update((column, _as_float) for column in floats)
    converters.update((column, _as_bool) for column in booleans)
    return TableSpec(
        name=name,
        columns=tuple(columns.split()),
        nullable=frozenset(nullable),
        converters=converters,
    )


# This order is part of the import contract: every referenced parent precedes
# its children.  It also gives rebuild mode a safe deletion order when reversed.
TABLE_SPECS: tuple[TableSpec, ...] = (
    _spec("people", "person_id name birth_date death_date notes", nullable=("birth_date", "death_date", "notes"), dates=("birth_date", "death_date")),
    _spec("band_memberships", "membership_id person_id act role start_date end_date start_precision end_precision source_key source_record_id notes", nullable=("end_date", "end_precision", "source_key", "source_record_id", "notes"), dates=("start_date", "end_date")),
    _spec("songs", "song_id title slug original_artist first_known_dead_performance last_known_dead_performance notes", nullable=("original_artist", "first_known_dead_performance", "last_known_dead_performance", "notes"), dates=("first_known_dead_performance", "last_known_dead_performance")),
    _spec("venues", "venue_id name city state_region country latitude longitude notes setting capacity", nullable=("city", "state_region", "country", "latitude", "longitude", "notes", "setting", "capacity"), floats=("latitude", "longitude"), integers=("capacity",)),
    _spec("equipment", "equipment_id name category manufacturer model notes", nullable=("manufacturer", "model", "notes")),
    _spec("shows", "show_id show_date venue_id tour_name event_name notes source_key source_record_id", nullable=("tour_name", "event_name", "notes", "source_key", "source_record_id"), dates=("show_date",)),
    _spec("song_writers", "song_id person_id writer_role notes", nullable=("notes",)),
    _spec("resources", "resource_id resource_type title creator source_name source_url published_date notes", nullable=("creator", "published_date", "notes"), dates=("published_date",)),
    _spec("resource_songs", "resource_id song_id relationship_type notes", nullable=("notes",)),
    _spec("resource_shows", "resource_id show_id relationship_type notes", nullable=("notes",)),
    _spec("show_performers", "show_id person_id role instrument notes source_key source_record_id", nullable=("notes", "source_key", "source_record_id")),
    _spec("performances", "performance_id show_id song_id set_number set_label position_in_set encore segue_into_next performance_notes source_key source_record_id", nullable=("set_number", "set_label", "performance_notes", "source_key", "source_record_id"), integers=("set_number", "position_in_set"), booleans=("encore", "segue_into_next")),
    _spec("performance_performers", "performance_id person_id role instrument notes source_key source_record_id", nullable=("notes", "source_key", "source_record_id")),
    _spec("resource_performances", "resource_id performance_id relationship_type notes", nullable=("notes",)),
    _spec("show_links", "show_link_id show_id platform link_type url title is_official notes", nullable=("title", "notes"), booleans=("is_official",)),
    _spec("performance_links", "performance_link_id performance_id platform link_type url title start_seconds duration_seconds is_official notes", nullable=("title", "start_seconds", "duration_seconds", "notes"), integers=("start_seconds", "duration_seconds"), booleans=("is_official",)),
    # release_date is TEXT, not a date converter: it may hold a partial value
    # ("1972", "1972-05") as well as a full ISO date, so it passes through as
    # the plain string the CSV already carries.
    _spec("official_releases", "release_id title artist_name release_date release_type spotify_album_url source_url notes", nullable=("artist_name", "release_date", "release_type", "spotify_album_url", "notes")),
    _spec("official_release_tracks", "release_id track_number performance_id song_id track_title duration_seconds spotify_track_url notes", nullable=("performance_id", "song_id", "duration_seconds", "spotify_track_url", "notes"), integers=("track_number", "duration_seconds")),
    _spec("release_personnel", "release_id person_id role instrument notes", nullable=("notes",)),
    _spec("song_arrangements", "arrangement_id song_id performance_id resource_id arrangement_scope key_signature capo tuning notes", nullable=("performance_id", "key_signature", "capo", "tuning", "notes")),
    _spec("arrangement_chord_sections", "arrangement_id section_position section_label progression notes", nullable=("notes",), integers=("section_position",)),
    _spec("recordings", "recording_id show_id source_type taper transferer shnid archive_identifier source_description lineage source_url notes", nullable=("source_type", "taper", "transferer", "shnid", "archive_identifier", "source_description", "lineage", "source_url", "notes")),
    _spec("performance_recordings", "performance_id recording_id track_number start_seconds duration_seconds track_title notes", nullable=("start_seconds", "duration_seconds", "track_title", "notes"), integers=("track_number", "start_seconds", "duration_seconds")),
    _spec("show_equipment", "show_id equipment_id usage_context claim_type claim_id source_id source_url source_note", nullable=("source_note",)),
)


@dataclass(frozen=True)
class CanonicalSnapshot:
    """An immutable content manifest for one reviewed canonical input set."""

    snapshot_id: str
    manifest: Mapping[str, Any]


class CanonicalImportError(ValueError):
    """Raised when canonical input violates its explicit import contract."""


def read_selection_evidence(path: Path | str = DEFAULT_SELECTION_EVIDENCE_PATH) -> dict[str, Any]:
    """Read the reviewed selection packet that must accompany every database import."""

    source = Path(path)
    try:
        document = json.loads(source.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise CanonicalImportError(f"selection evidence is unavailable or invalid: {source}") from exc
    entries = document.get("entries") if isinstance(document, dict) else None
    if document.get("kind") != "selection_evidence_review" or not isinstance(entries, list):
        raise CanonicalImportError("selection evidence must be a selection_evidence_review with entries")
    for position, entry in enumerate(entries, start=1):
        if not isinstance(entry, dict):
            raise CanonicalImportError(f"selection evidence entry {position} must be an object")
        if not isinstance(entry.get("source"), str) or not entry["source"]:
            raise CanonicalImportError(f"selection evidence entry {position} is missing source")
        if not isinstance(entry.get("signal_type"), str) or not entry["signal_type"]:
            raise CanonicalImportError(f"selection evidence entry {position} is missing signal_type")
        if not isinstance(entry.get("resolution_state"), str) or not entry["resolution_state"]:
            raise CanonicalImportError(f"selection evidence entry {position} is missing resolution_state")
    return document


def _stable_selection_id(prefix: str, *parts: str) -> str:
    digest = hashlib.sha256("\0".join(parts).encode("utf-8")).hexdigest()[:24]
    return f"{prefix}-{digest}"


def _selection_source_url(entry: Mapping[str, Any]) -> str:
    value = entry.get("source_url")
    if isinstance(value, str) and value.startswith("https://"):
        return value
    if entry.get("source") == "charlie-miller-user-provided-threads":
        return "https://www.threads.com/@charliedmiller87"
    raise CanonicalImportError(
        f"selection source {entry.get('source')!r} has no usable source URL"
    )


def _selector_name(entry: Mapping[str, Any]) -> str | None:
    source = entry.get("source")
    if source in {"charlie-miller-user-provided-threads", "charlie-miller-reddit"}:
        return "Charlie Miller"
    if source == "rolling-stone-australia":
        return "David Fricke / Rolling Stone"
    return None


@dataclass(frozen=True)
class SelectionRows:
    """Insert-ready rows generated solely from the reviewed selection packet."""

    resources: list[tuple[Any, ...]]
    lists: list[tuple[Any, ...]]
    entries: list[tuple[Any, ...]]
    evidence: list[tuple[Any, ...]]


def selection_evidence_rows(document: Mapping[str, Any]) -> SelectionRows:
    """Project the reviewed packet into resource, list, entry and evidence rows."""

    entries = document["entries"]
    resources: dict[str, tuple[Any, ...]] = {}
    lists: dict[str, tuple[Any, ...]] = {}
    evidence_rows: list[tuple[Any, ...]] = []
    entry_rows: list[tuple[Any, ...]] = []
    review_packet = {
        "purpose": document.get("purpose"),
        "source_constraints": document.get("source_constraints", {}),
        "summary": document.get("summary", {}),
    }
    for position, raw_entry in enumerate(entries, start=1):
        entry = dict(raw_entry)
        source = entry["source"]
        source_url = _selection_source_url(entry)
        resource_id = _stable_selection_id("resource-selection", source, source_url)
        title = entry.get("selection_label") or f"{source} selection evidence"
        resources[resource_id] = (
            resource_id,
            "selection-evidence",
            title,
            _selector_name(entry),
            source,
            source_url,
            None,
            "Reviewed source-attributed selection evidence.",
        )
        list_key = str(entry.get("selection_label") or entry["signal_type"])
        list_id = _stable_selection_id("selection-list", source, list_key, source_url)
        lists[list_id] = (
            list_id,
            list_key,
            entry["signal_type"],
            _selector_name(entry),
            resource_id,
            None,
            None,
            "Generated from the reviewed selection-evidence packet.",
        )
        evidence_id = _stable_selection_id(
            "selection-evidence", source, str(entry.get("source_record_id") or ""), str(position)
        )
        entry["review_packet"] = review_packet
        evidence_rows.append(
            (
                evidence_id,
                resource_id,
                list_id,
                entry["signal_type"],
                entry["resolution_state"],
                json.dumps(entry, ensure_ascii=False, sort_keys=True, separators=(",", ":")),
            )
        )
        show_ids = entry.get("candidate_show_ids")
        performance_ids = entry.get("candidate_performance_ids")
        target_column = target_id = None
        if entry["resolution_state"] in {"resolved_unique_show", "resolved_show_pending_release_review"} and isinstance(show_ids, list) and len(show_ids) == 1:
            target_column, target_id = "show_id", show_ids[0]
        elif entry["resolution_state"] == "resolved_unique_performance" and isinstance(performance_ids, list) and len(performance_ids) == 1:
            target_column, target_id = "performance_id", performance_ids[0]
        if target_column and isinstance(target_id, str):
            targets = {"show_id": None, "performance_id": None, "song_id": None, "release_id": None, "recording_id": None}
            targets[target_column] = target_id
            entry_rows.append(
                (
                    _stable_selection_id("selection-entry", evidence_id),
                    list_id,
                    position,
                    entry.get("recommendation_rank") if isinstance(entry.get("recommendation_rank"), int) else None,
                    entry.get("fan_vote_count") if isinstance(entry.get("fan_vote_count"), int) else None,
                    None,
                    targets["show_id"],
                    targets["performance_id"],
                    targets["song_id"],
                    targets["release_id"],
                    targets["recording_id"],
                    entry.get("source_label") if isinstance(entry.get("source_label"), str) else None,
                    f"resolution_state={entry['resolution_state']}",
                )
            )
    return SelectionRows(
        resources=list(resources.values()),
        lists=list(lists.values()),
        entries=entry_rows,
        evidence=evidence_rows,
    )


def _convert_row(spec: TableSpec, row: Mapping[str, str], line_number: int) -> tuple[Any, ...]:
    converted: list[Any] = []
    for column in spec.columns:
        value = row[column]
        if value == "" and column in spec.nullable:
            converted.append(None)
            continue
        if value == "":
            raise CanonicalImportError(
                f"{spec.csv_name}:{line_number}: required {column} is empty"
            )
        converter = spec.converters.get(column)
        if converter is None:
            converted.append(value)
            continue
        try:
            converted.append(converter(value))
        except (TypeError, ValueError) as exc:
            raise CanonicalImportError(
                f"{spec.csv_name}:{line_number}: invalid {column}: {exc}"
            ) from exc
    return tuple(converted)


def read_canonical_table(canonical_dir: Path | str, spec: TableSpec) -> list[tuple[Any, ...]]:
    """Read and strictly validate one canonical CSV."""

    path = Path(canonical_dir) / spec.csv_name
    try:
        handle = path.open("r", encoding="utf-8-sig", newline="")
    except FileNotFoundError as exc:
        raise CanonicalImportError(f"missing canonical file: {path}") from exc

    with handle:
        reader = csv.DictReader(handle)
        actual = tuple(reader.fieldnames or ())
        if actual != spec.columns:
            raise CanonicalImportError(
                f"{spec.csv_name}: expected header {spec.columns!r}, got {actual!r}"
            )
        rows: list[tuple[Any, ...]] = []
        for line_number, row in enumerate(reader, start=2):
            if None in row:
                raise CanonicalImportError(
                    f"{spec.csv_name}:{line_number}: row has more fields than its header"
                )
            rows.append(_convert_row(spec, row, line_number))
        return rows


def read_canonical_tables(
    canonical_dir: Path | str = DEFAULT_CANONICAL_DIR,
    specs: Sequence[TableSpec] = TABLE_SPECS,
) -> dict[str, list[tuple[Any, ...]]]:
    """Validate all input before opening a database transaction."""

    return {spec.name: read_canonical_table(canonical_dir, spec) for spec in specs}


def canonical_snapshot(
    canonical_dir: Path | str,
    rows_by_table: Mapping[str, Sequence[tuple[Any, ...]]],
    specs: Sequence[TableSpec] = TABLE_SPECS,
) -> CanonicalSnapshot:
    """Create a content-addressed manifest for already validated CSV input.

    Per-file digests preserve the exact reviewed files used by an import. The
    combined digest is deliberately independent of filesystem paths and gives
    observations a stable, portable input revision identifier.
    """

    root = Path(canonical_dir)
    combined = hashlib.sha256()
    files: list[dict[str, Any]] = []
    for spec in specs:
        payload = (root / spec.csv_name).read_bytes()
        digest = hashlib.sha256(payload).hexdigest()
        combined.update(spec.csv_name.encode("utf-8"))
        combined.update(b"\0")
        combined.update(bytes.fromhex(digest))
        combined.update(b"\0")
        files.append(
            {
                "name": spec.csv_name,
                "sha256": digest,
                "row_count": len(rows_by_table[spec.name]),
            }
        )
    return CanonicalSnapshot(
        snapshot_id=f"sha256:{combined.hexdigest()}",
        manifest={"format": "deadbot-canonical-snapshot/v1", "files": files},
    )
