#!/usr/bin/env python3
"""Add structured provenance columns to the canonical CSVs.

`shows.csv`, `performances.csv`, and `show_performers.csv` each carry a
per-row source citation, but only as free text inside `notes` /
`performance_notes`, in a small number of ad-hoc prose formats. This script
adds two real columns to the end of each file:

    source_key         -- short identifier for the source system
                           ("gdshowsdb", "jerrybase", or "manual")
    source_record_id    -- the stable identifier from that source (a
                           gdshowsdb show UUID, a gdshowsdb song UUID, or a
                           JerryBase event id), empty for "manual" rows

This is a deterministic, rerunnable migration, not a one-off patch:

  * Parsing is done with strict, anchored regexes against the known note
    formats (see the *_RE constants below). A row that doesn't match any
    known format is left with empty source_key/source_record_id -- it is
    never guessed -- and is printed in the report at the end of the run.
  * Idempotent: if `source_key`/`source_record_id` columns already exist
    (from a previous run), they are dropped and recomputed from `notes`
    rather than trusted, so rerunning after a notes fix or a schema tweak
    always reflects the current file contents.
  * `notes` / `performance_notes` and every other existing column are
    copied through unchanged. Row order and row count are preserved
    exactly. Output uses the same CSV dialect as the input (comma
    delimiter, minimal quoting, "\n" line endings).

Background (see docs/data-audit-2026-08-27.md, section "Provenance as
prose", and docs/collection-methodology.md / docs/provenance-policy.md for
the project's source conventions):

  * shows.csv: 2,357 of 2,358 rows were normalized from a pinned gdshowsdb
    year-file blob and cite a gdshowsdb show UUID plus a github-blob hash.
    The single exception is the original hand-curated Veneta show
    (`gd-1972-08-27`), which predates the gdshowsdb bulk pass and instead
    cites a JerryBase event id directly in its `notes`.
  * performances.csv: 39,754 of 39,774 rows cite a gdshowsdb song UUID (the
    per-row identifier available for performances, since performances were
    normalized from the same gdshowsdb show records as `shows.csv`). The
    remaining 20 rows are the original hand-curated Veneta performances,
    which predate this citation convention and have an empty
    `performance_notes` field -- these get `source_key = "manual"` and an
    empty `source_record_id`.
  * show_performers.csv: 26,255 of 26,265 rows were normalized from a
    JerryBase per-year event snapshot and cite a JerryBase event id plus
    the raw snapshot filename. The remaining 10 rows are the JerryBase
    performer assignments for the same hand-curated Veneta show, entered
    before the event-id convention existed -- they cite JerryBase as the
    source but do not repeat the event id inline. Since every one of those
    10 rows' `show_id` is `gd-1972-08-27`, and `shows.csv`'s own citation
    for that show resolves to JerryBase event id "19720827-01", these rows
    get `source_key = "jerrybase"` and that same event id as
    `source_record_id` -- not a guess, but the identical event record their
    own note text already names, recovered via a documented, deterministic
    join instead of duplicated prose.

Usage:
    .venv/bin/python scripts/add_provenance_columns.py
"""
from __future__ import annotations

import csv
import re
import sys
from pathlib import Path

CANON_DIR = Path(__file__).resolve().parent.parent / "data" / "canonical"

NEW_COLUMNS = ["source_key", "source_record_id"]

UUID_RE = r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}"

# The one show that predates the gdshowsdb bulk pass and is cited
# differently in all three files.
VENETA_SHOW_ID = "gd-1972-08-27"

# --- shows.csv -------------------------------------------------------------
# "Normalized from gdshowsdb show UUID <uuid> in github-blob:<hash>."
# optionally followed by "; Source record contains no setlist entries."
SHOWS_GDSHOWSDB_RE = re.compile(
    r"^Normalized from gdshowsdb show UUID (" + UUID_RE + r") in github-blob:[0-9a-fA-F]+\."
)
# "Normalized from JerryBase event <event-id>; recording metadata
# reconciled from Internet Archive item <item-id>." (Veneta only)
SHOWS_JERRYBASE_RE = re.compile(r"^Normalized from JerryBase event ([0-9A-Za-z-]+);")

# --- performances.csv -------------------------------------------------------
# "Source song UUID <uuid>; source label '<label>'." or with double quotes
# around the label -- both quoting styles occur; it doesn't change parsing.
PERFORMANCES_SONG_RE = re.compile(
    r"^Source song UUID (" + UUID_RE + r"); source label [\"'].*[\"']\.$"
)

# --- show_performers.csv ----------------------------------------------------
# "JerryBase source event <event-id>; raw snapshot <file>; JerryBase source
# instrument: <instrument list>[.]"
SHOW_PERFORMERS_EVENT_RE = re.compile(
    r"^JerryBase source event ([0-9A-Za-z-]+); raw snapshot [^;]+;"
)
# "JerryBase source instrument: <instrument list>[.]" (Veneta only, no
# event id inline -- resolved via the parent show's own citation instead).
SHOW_PERFORMERS_NO_EVENT_RE = re.compile(r"^JerryBase source instrument:")


def read_rows(path: Path):
    with path.open(newline="", encoding="utf-8") as fh:
        reader = csv.reader(fh)
        header = next(reader)
        rows = [row for row in reader]
    return header, rows


def write_rows(path: Path, header, rows) -> None:
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh, quoting=csv.QUOTE_MINIMAL, lineterminator="\n")
        writer.writerow(header)
        writer.writerows(rows)


def strip_existing_new_columns(header, rows):
    """Idempotency: drop source_key/source_record_id if already present,
    so they get recomputed from notes rather than carried over stale."""
    idxs = [header.index(c) for c in NEW_COLUMNS if c in header]
    if not idxs:
        return header, rows
    keep = [i for i in range(len(header)) if i not in idxs]
    new_header = [header[i] for i in keep]
    new_rows = [[row[i] for i in keep] for row in rows]
    return new_header, new_rows


def parse_shows_note(note: str):
    m = SHOWS_GDSHOWSDB_RE.match(note)
    if m:
        return "gdshowsdb", m.group(1)
    m = SHOWS_JERRYBASE_RE.match(note)
    if m:
        return "jerrybase", m.group(1)
    return "", ""


def build_shows_source_map():
    """Parse shows.csv's own notes into {show_id: (source_key, source_record_id)}.

    Used both to migrate shows.csv itself and to resolve the show_performers
    rows that cite JerryBase without repeating the event id inline.
    """
    header, rows = read_rows(CANON_DIR / "shows.csv")
    header, rows = strip_existing_new_columns(header, rows)
    show_id_idx = header.index("show_id")
    notes_idx = header.index("notes")
    mapping = {}
    for row in rows:
        mapping[row[show_id_idx]] = parse_shows_note(row[notes_idx])
    return mapping


def migrate_shows():
    path = CANON_DIR / "shows.csv"
    header, rows = read_rows(path)
    header, rows = strip_existing_new_columns(header, rows)
    show_id_idx = header.index("show_id")
    notes_idx = header.index("notes")

    unparsed = []
    new_rows = []
    for row in rows:
        key, rec_id = parse_shows_note(row[notes_idx])
        if not key:
            unparsed.append(row[show_id_idx])
        new_rows.append(row + [key, rec_id])

    write_rows(path, header + NEW_COLUMNS, new_rows)
    return len(rows), unparsed


def migrate_performances():
    path = CANON_DIR / "performances.csv"
    header, rows = read_rows(path)
    header, rows = strip_existing_new_columns(header, rows)
    pid_idx = header.index("performance_id")
    show_id_idx = header.index("show_id")
    notes_idx = header.index("performance_notes")

    unparsed = []
    new_rows = []
    for row in rows:
        note = row[notes_idx]
        show_id = row[show_id_idx]
        m = PERFORMANCES_SONG_RE.match(note)
        if m:
            key, rec_id = "gdshowsdb", m.group(1)
        elif note == "" and show_id == VENETA_SHOW_ID:
            key, rec_id = "manual", ""
        else:
            key, rec_id = "", ""
            unparsed.append(row[pid_idx])
        new_rows.append(row + [key, rec_id])

    write_rows(path, header + NEW_COLUMNS, new_rows)
    return len(rows), unparsed


def migrate_show_performers(shows_map):
    path = CANON_DIR / "show_performers.csv"
    header, rows = read_rows(path)
    header, rows = strip_existing_new_columns(header, rows)
    show_id_idx = header.index("show_id")
    person_id_idx = header.index("person_id")
    notes_idx = header.index("notes")

    unparsed = []
    new_rows = []
    for row in rows:
        note = row[notes_idx]
        show_id = row[show_id_idx]
        m = SHOW_PERFORMERS_EVENT_RE.match(note)
        if m:
            key, rec_id = "jerrybase", m.group(1)
        elif SHOW_PERFORMERS_NO_EVENT_RE.match(note):
            parent_key, parent_id = shows_map.get(show_id, ("", ""))
            if parent_key == "jerrybase" and parent_id:
                key, rec_id = "jerrybase", parent_id
            else:
                key, rec_id = "", ""
                unparsed.append(f"{show_id}/{row[person_id_idx]}")
        else:
            key, rec_id = "", ""
            unparsed.append(f"{show_id}/{row[person_id_idx]}")
        new_rows.append(row + [key, rec_id])

    write_rows(path, header + NEW_COLUMNS, new_rows)
    return len(rows), unparsed


def main() -> int:
    shows_map = build_shows_source_map()

    shows_total, shows_unparsed = migrate_shows()
    perf_total, perf_unparsed = migrate_performances()
    sp_total, sp_unparsed = migrate_show_performers(shows_map)

    print("Provenance migration report")
    print("=" * 60)
    for name, total, unparsed in (
        ("shows.csv", shows_total, shows_unparsed),
        ("performances.csv", perf_total, perf_unparsed),
        ("show_performers.csv", sp_total, sp_unparsed),
    ):
        parsed = total - len(unparsed)
        pct = 100.0 * parsed / total if total else 0.0
        print(f"{name}: {parsed}/{total} parsed ({pct:.2f}%)")
        if unparsed:
            print(f"  {len(unparsed)} row(s) failed closed (empty source_key/source_record_id):")
            for row_id in unparsed:
                print(f"    - {row_id}")
    print("=" * 60)

    total_unparsed = len(shows_unparsed) + len(perf_unparsed) + len(sp_unparsed)
    if total_unparsed:
        print(
            f"{total_unparsed} row(s) failed closed. Review the report above; "
            "known hand-curated exceptions are expected to be zero after this "
            "script's cross-referencing, so any row listed here is unexpected "
            "and should be investigated before trusting the new columns."
        )
    else:
        print("All rows parsed. No unexplained unparseable rows.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
