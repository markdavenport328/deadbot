#!/usr/bin/env python3
"""Sharpen imprecise studio ``release_date`` values with Wikipedia evidence.

Input: ``data/raw/releases/wikipedia-album-dates.jsonl``, written by
``scripts/collect/fetch_wikipedia_album_dates.py``, one record per album that
collector could confidently match to a Wikipedia article and whose infobox
carried a ``Released`` field; and that collector's
``data/raw/releases/wikipedia-album-dates.run.json`` for the ``held`` list
(no confident article, or no ``Released`` field), so the review log below
covers every album the collector was asked to look at, not only the ones it
found.

Output: the ``release_date`` column only, on the studio rows named by the raw
records' ``release_id``, in ``data/canonical/official_releases.csv``; and a
decision log at ``data/raw/releases/wikipedia-album-date-review.jsonl``.

Rules, applied in order, per the governing spec:

1. **Year conflict wins over precision.** If the year Wikipedia's ``Released``
   field parses to disagrees with the year already in
   ``official_releases.csv``, the row is left untouched and the disagreement
   is logged as a ``conflict`` with both values. A conflict is a review item
   for a human, never something this script resolves by picking a side.
2. **Strictly more precise only.** A parsed Wikipedia date only overwrites the
   existing value when it is strictly more precise: year to year-month or
   full date, or year-month to full date. A same-precision or *less* precise
   Wikipedia value (this repository has one: Wikipedia's ``Run for the
   Roses`` infobox gives only ``1982``, a year, while the row already carries
   the year-month ``1982-11``) is held, never a downgrade.
3. **Unparseable or ambiguous, held.** A ``Released`` string this script
   cannot confidently reduce to a single year, year-month, or full date --
   because it holds more than one candidate date, or matches no known format
   after stripping ``<ref>...</ref>`` citations and HTML comments -- is
   logged and the row is left alone.
4. **Only the release_date column of studio rows changes.** No other column,
   no live row, and no row order is touched; ``official_releases.csv`` is
   rewritten in its existing row order with only some rows' ``release_date``
   values edited in place.
5. **Idempotent.** Two consecutive runs against the same raw file produce a
   byte-identical ``official_releases.csv``: nothing an earlier run already
   upgraded is touched again. The review log is *not* expected to be
   byte-identical across runs -- each run logs a fresh comparison against
   ``official_releases.csv`` as it stands when that run starts, so a row this
   script upgraded reads ``upgraded`` the first time and
   ``already_at_source_precision`` on every run after (the existing value now
   equals what Wikipedia gives), which is the correct comparison against the
   now-updated CSV, not drift.
"""

from __future__ import annotations

import csv
import json
import re
from datetime import date
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
RAW_DIR = ROOT / "data" / "raw" / "releases"
RAW_PATH = RAW_DIR / "wikipedia-album-dates.jsonl"
RUN_SUMMARY_PATH = RAW_DIR / "wikipedia-album-dates.run.json"
REVIEW_PATH = RAW_DIR / "wikipedia-album-date-review.jsonl"
RELEASES_CSV = ROOT / "data" / "canonical" / "official_releases.csv"
RELEASE_FIELDS = ["release_id", "title", "artist_name", "release_date", "release_type", "spotify_album_url", "source_url", "notes"]

_MONTHS = {
    name.casefold(): index
    for index, name in enumerate(
        [
            "January", "February", "March", "April", "May", "June",
            "July", "August", "September", "October", "November", "December",
        ],
        start=1,
    )
}

_REF_TAG = re.compile(r"<ref[^>]*>.*?</ref>", re.IGNORECASE | re.DOTALL)
_SELF_CLOSING_REF = re.compile(r"<ref[^>]*/\s*>", re.IGNORECASE)
_HTML_COMMENT = re.compile(r"<!--.*?-->", re.DOTALL)
_WIKILINK = re.compile(r"\[\[(?:[^\]|]*\|)?([^\]]*)\]\]")
_BR_TAG = re.compile(r"<br\s*/?>", re.IGNORECASE)

_START_DATE_TEMPLATE = re.compile(r"^\{\{\s*[Ss]tart[ _]date\s*\|(.*)\}\}$")
_ISO_DATE = re.compile(r"^(\d{4})-(\d{2})(?:-(\d{2}))?$")
_MONTH_DAY_YEAR = re.compile(r"^([A-Za-z]+)\s+(\d{1,2}),\s*(\d{4})$")
_DAY_MONTH_YEAR = re.compile(r"^(\d{1,2})\s+([A-Za-z]+)\s+(\d{4})$")
_MONTH_YEAR = re.compile(r"^([A-Za-z]+)\s+(\d{4})$")
_YEAR_ONLY = re.compile(r"^(\d{4})$")


def clean_wikitext(value: str) -> str:
    """Strip citations, comments, wikilink brackets, and line breaks.

    Deliberately does not strip anything else: a value that still has extra
    words or a second date after this cleanup is meant to fail every pattern
    below and be held, not coerced into a guess.
    """

    value = _REF_TAG.sub("", value)
    value = _SELF_CLOSING_REF.sub("", value)
    value = _HTML_COMMENT.sub("", value)
    value = _WIKILINK.sub(r"\1", value)
    value = _BR_TAG.sub(" ", value)
    return " ".join(value.split()).strip()


def _valid_ymd(year: int, month: int | None, day: int | None) -> bool:
    if month is not None and not (1 <= month <= 12):
        return False
    if day is not None:
        try:
            date(year, month, day)
        except ValueError:
            return False
    return True


def parse_released(raw: str) -> tuple[str, str] | None:
    """Parse a cleaned ``Released`` string to (iso_date, precision).

    ``precision`` is one of ``year``, ``year-month``, ``full``. Returns
    ``None`` when the string does not confidently reduce to exactly one date
    in a recognized format.
    """

    value = clean_wikitext(raw)
    if not value:
        return None

    template = _START_DATE_TEMPLATE.match(value)
    if template:
        # {{Start date|1972|5|1}}, optionally with a leading named df=yes/mf=yes
        # and/or a trailing |p=yes: keep only unnamed, purely numeric arguments,
        # in order, as year/month/day.
        args = [part.strip() for part in template.group(1).split("|")]
        numeric = [part for part in args if part.isdigit()]
        if not numeric or not (1 <= len(numeric) <= 3):
            return None
        year = int(numeric[0])
        month = int(numeric[1]) if len(numeric) >= 2 else None
        day = int(numeric[2]) if len(numeric) >= 3 else None
        if not _valid_ymd(year, month, day):
            return None
        if day is not None:
            return f"{year:04d}-{month:02d}-{day:02d}", "full"
        if month is not None:
            return f"{year:04d}-{month:02d}", "year-month"
        return f"{year:04d}", "year"

    iso = _ISO_DATE.match(value)
    if iso:
        year, month, day = int(iso.group(1)), int(iso.group(2)), iso.group(3)
        day_int = int(day) if day else None
        if not _valid_ymd(year, month, day_int):
            return None
        if day_int is not None:
            return f"{year:04d}-{month:02d}-{day_int:02d}", "full"
        return f"{year:04d}-{month:02d}", "year-month"

    month_day_year = _MONTH_DAY_YEAR.match(value)
    if month_day_year:
        month_name, day_str, year_str = month_day_year.groups()
        month = _MONTHS.get(month_name.casefold())
        if month is None:
            return None
        year, day = int(year_str), int(day_str)
        if not _valid_ymd(year, month, day):
            return None
        return f"{year:04d}-{month:02d}-{day:02d}", "full"

    day_month_year = _DAY_MONTH_YEAR.match(value)
    if day_month_year:
        day_str, month_name, year_str = day_month_year.groups()
        month = _MONTHS.get(month_name.casefold())
        if month is None:
            return None
        year, day = int(year_str), int(day_str)
        if not _valid_ymd(year, month, day):
            return None
        return f"{year:04d}-{month:02d}-{day:02d}", "full"

    month_year = _MONTH_YEAR.match(value)
    if month_year:
        month_name, year_str = month_year.groups()
        month = _MONTHS.get(month_name.casefold())
        if month is None:
            return None
        year = int(year_str)
        if not _valid_ymd(year, month, None):
            return None
        return f"{year:04d}-{month:02d}", "year-month"

    year_only = _YEAR_ONLY.match(value)
    if year_only:
        return f"{int(year_only.group(1)):04d}", "year"

    return None


_PRECISION_RANK = {"year": 0, "year-month": 1, "full": 2}


def precision_of(release_date: str) -> str:
    if len(release_date) == 4:
        return "year"
    if len(release_date) == 7:
        return "year-month"
    return "full"


def read_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def read_csv(path: Path) -> tuple[list[str], list[dict]]:
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        return list(reader.fieldnames or []), list(reader)


def write_csv(path: Path, fields: list[str], rows: list[dict]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows({field: row.get(field, "") for field in fields} for row in rows)


def main() -> None:
    header, rows = read_csv(RELEASES_CSV)
    if header != RELEASE_FIELDS:
        raise SystemExit("official_releases.csv header changed; refusing to write")
    by_release_id = {row["release_id"]: row for row in rows}

    raw_records = {record["source_record_id"]: record for record in read_jsonl(RAW_PATH)}
    run_summary = json.loads(RUN_SUMMARY_PATH.read_text(encoding="utf-8")) if RUN_SUMMARY_PATH.exists() else {}
    held_by_collector = {entry["release_id"]: entry for entry in run_summary.get("held", [])}

    decisions: list[dict] = []
    upgraded = conflicts = held = 0

    for release_id in sorted(set(raw_records) | set(held_by_collector)):
        row = by_release_id.get(release_id)
        if row is None:
            decisions.append(
                {
                    "release_id": release_id,
                    "status": "held",
                    "reason": "release_id_not_in_official_releases_csv",
                }
            )
            held += 1
            continue

        if release_id not in raw_records:
            collector_hold = held_by_collector[release_id]
            decisions.append(
                {
                    "release_id": release_id,
                    "title": row["title"],
                    "artist_name": row["artist_name"],
                    "existing_release_date": row["release_date"],
                    "status": "held",
                    "reason": collector_hold.get("reason", "no_article"),
                    "detail": collector_hold.get("detail", ""),
                }
            )
            held += 1
            continue

        record = raw_records[release_id]
        payload = record["raw_payload"]
        released_raw = payload["released_raw"]
        existing = row["release_date"]
        decision = {
            "release_id": release_id,
            "title": row["title"],
            "artist_name": row["artist_name"],
            "existing_release_date": existing,
            "article_title": payload["article_title"],
            "article_url": payload["article_url"],
            "revision_id": payload["revision_id"],
            "wikipedia_released_raw": released_raw,
        }

        parsed = parse_released(released_raw)
        if parsed is None:
            decision.update({"status": "held", "reason": "unparseable_or_ambiguous_released_field"})
            decisions.append(decision)
            held += 1
            continue

        parsed_date, parsed_precision = parsed
        decision["wikipedia_parsed_date"] = parsed_date
        parsed_year = parsed_date[:4]
        existing_year = existing[:4]
        if parsed_year != existing_year:
            decision.update(
                {
                    "status": "conflict",
                    "reason": "wikipedia_year_disagrees_with_existing_year",
                    "detail": f"existing {existing!r} (year {existing_year}) vs Wikipedia {parsed_date!r} (year {parsed_year})",
                }
            )
            decisions.append(decision)
            conflicts += 1
            continue

        existing_precision = precision_of(existing)
        if _PRECISION_RANK[parsed_precision] <= _PRECISION_RANK[existing_precision]:
            decision.update(
                {
                    "status": "held",
                    "reason": "already_at_source_precision"
                    if _PRECISION_RANK[parsed_precision] == _PRECISION_RANK[existing_precision]
                    else "wikipedia_less_precise_than_existing",
                }
            )
            decisions.append(decision)
            held += 1
            continue

        row["release_date"] = parsed_date
        decision.update({"status": "upgraded", "new_release_date": parsed_date})
        decisions.append(decision)
        upgraded += 1

    write_csv(RELEASES_CSV, RELEASE_FIELDS, rows)

    with REVIEW_PATH.open("w", encoding="utf-8") as handle:
        for decision in decisions:
            handle.write(json.dumps(decision, ensure_ascii=False, sort_keys=True) + "\n")

    print(
        json.dumps(
            {
                "albums_considered": len(decisions),
                "upgraded": upgraded,
                "conflicts": conflicts,
                "held": held,
                "review_path": str(REVIEW_PATH.relative_to(ROOT)),
            },
            indent=1,
        )
    )


if __name__ == "__main__":
    main()
