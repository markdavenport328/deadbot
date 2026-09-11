#!/usr/bin/env python3
"""Build the canonical ``band_memberships`` table from reviewed sources.

Input:

* ``data/raw/people/wikidata-grateful-dead-members.jsonl`` and
  ``musicbrainz-grateful-dead-members.jsonl``, written by
  ``scripts/collect/fetch_band_membership_sources.py``.
* ``data/canonical/show_performers.csv`` and ``shows.csv``, read only to cross-
  check each source tenure against the band's own documented lineup evidence
  (``role == "performer"`` rows only; a ``guest`` row is a sit-in, not a
  membership fact).

Output: ``data/canonical/band_memberships.csv``, one row per person, act, and
tenure. ``act`` is always ``grateful-dead`` for this pass.

Scope: only the twelve core/officially-recognized members documented by both
sources -- the four/five original members (Garcia, Weir, Lesh, Kreutzmann,
Pigpen), the two additional drummers/percussionists across Mickey Hart's two
tenures, the four keyboardists after Pigpen (Constanten, Keith Godchaux,
Mydland, Welnick), Donna Jean Godchaux, and touring auxiliary member Bruce
Hornsby. MusicBrainz's "member of band" relation for the Grateful Dead also
names Robert Hunter (lyricist, never a performing member) and Rob Wasserman
(a solo/duo collaborator, not a Grateful Dead member); both are excluded here
because they are not officially recognized band members, matching the
exclusion already applied to every other guest musician left in
``show_performers.csv``.

Resolution policy, applied per person and documented in each row's ``notes``:

* When Wikidata, MusicBrainz, and the show-lineup evidence agree on the year
  (allowing for the lineup evidence's finer day precision), the lineup
  evidence's exact first/last ``performer``-role show date is used for
  ``start_date``/``end_date`` at day precision, and both source claims are
  named in ``notes``.
* A tenure that ended with the band's final show carries ``1995-07-09``
  (Chicago, Soldier Field) rather than a blank ``end_date``.
* Where a source's tenure date and the lineup evidence disagree by more than a
  few weeks, the row is held with both values recorded in ``notes`` rather
  than silently picking one; see ``docs/collection-status-band-membership.md``
  for the full comparison.
"""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
RAW_DIR = ROOT / "data" / "raw" / "people"
CANONICAL_DIR = ROOT / "data" / "canonical"

GRATEFUL_DEAD_WIKIDATA_QID = "Q212533"
GRATEFUL_DEAD_MUSICBRAINZ_MBID = "6faa7ca7-0d99-4a5e-bfa6-1fd5037520c6"


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    with path.open(encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def _wikidata_year(value: str | None) -> str | None:
    if not value:
        return None
    # Wikidata time values look like "+1965-00-00T00:00:00Z" at year precision.
    return value.lstrip("+")[:4]


def _performer_dates(show_performers_path: Path, shows_path: Path) -> dict[str, list[str]]:
    """First/last ``performer``-role show dates per person, from lineup evidence."""

    show_dates = {}
    with shows_path.open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            show_dates[row["show_id"]] = row["show_date"]

    dates_by_person: dict[str, list[str]] = {}
    with show_performers_path.open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            if row.get("role") != "performer":
                continue
            date = show_dates.get(row.get("show_id", ""))
            if not date:
                continue
            dates_by_person.setdefault(row["person_id"], []).append(date)
    for person_id, dates in dates_by_person.items():
        dates.sort()
    return dates_by_person


def build_rows(
    wikidata_records: list[dict[str, Any]],
    musicbrainz_records: list[dict[str, Any]],
    performer_dates: dict[str, list[str]],
) -> list[dict[str, str]]:
    wikidata_by_label = {record["label"]: record for record in wikidata_records}
    musicbrainz_by_name = {record["artist_name"]: record for record in musicbrainz_records}

    def first_last(person_id: str) -> tuple[str, str]:
        dates = performer_dates[person_id]
        return dates[0], dates[-1]

    def mb_note(name: str) -> str:
        record = musicbrainz_by_name[name]
        return f"MusicBrainz member-of-band relation on artist {GRATEFUL_DEAD_MUSICBRAINZ_MBID}: begin {record['begin']}, end {record['end']}."

    def wd_note(label: str) -> str:
        record = wikidata_by_label[label]
        spans = record["member_of_grateful_dead_spans"] or (
            [record["has_part_span_on_band_item"]] if record["has_part_span_on_band_item"] else []
        )
        rendered = "; ".join(
            f"{_wikidata_year(span['start'])}-{_wikidata_year(span['end'])}" for span in spans
        )
        return f"Wikidata {label} ({record['wikidata_qid']}) member-of statement(s) for the Grateful Dead ({GRATEFUL_DEAD_WIKIDATA_QID}): {rendered}."

    rows: list[dict[str, str]] = []

    def add(
        membership_id: str,
        person_id: str,
        role: str,
        start_date: str,
        start_precision: str,
        end_date: str,
        end_precision: str,
        notes: str,
    ) -> None:
        rows.append(
            {
                "membership_id": membership_id,
                "person_id": person_id,
                "act": "grateful-dead",
                "role": role,
                "start_date": start_date,
                "end_date": end_date,
                "start_precision": start_precision,
                "end_precision": end_precision,
                "source_key": "musicbrainz-api",
                "source_record_id": GRATEFUL_DEAD_MUSICBRAINZ_MBID,
                "notes": notes,
            }
        )

    # Original members whose lineup evidence spans the band's whole run.
    start, end = first_last("person-jerry-garcia")
    add(
        "membership-jerry-garcia-1965", "person-jerry-garcia", "guitar, vocals",
        start, "day", "1995-07-09", "day",
        "Founding member. show_performers shows performer-role shows from "
        f"{start} through the band's final show, 1995-07-09 (Soldier Field, "
        "Chicago); Garcia died 1995-08-09, one month after the last show. "
        + mb_note("Jerry Garcia") + " " + wd_note("Jerry Garcia"),
    )

    start, end = first_last("person-bob-weir")
    add(
        "membership-bob-weir-1965", "person-bob-weir", "guitar, vocals",
        start, "day", "1995-07-09", "day",
        f"Founding member. show_performers shows performer-role shows from {start} "
        "through the band's final show, 1995-07-09. " + mb_note("Bob Weir") + " " + wd_note("Bob Weir"),
    )

    start, end = first_last("person-bill-kreutzmann")
    add(
        "membership-bill-kreutzmann-1965", "person-bill-kreutzmann", "drums",
        start, "day", "1995-07-09", "day",
        f"Founding member. show_performers shows performer-role shows from {start} "
        "through the band's final show, 1995-07-09. " + mb_note("Bill Kreutzmann") + " " + wd_note("Bill Kreutzmann"),
    )

    start, end = first_last("person-phil-lesh")
    add(
        "membership-phil-lesh-1965", "person-phil-lesh", "bass, vocals",
        start, "day", "1995-07-09", "day",
        "Founding member of the band (formed 1965-05-05 as the Warlocks), though "
        f"show_performers' first performer-role row for Lesh is {start}, consistent "
        "with published accounts that original bassist Dana Morgan Jr. played the "
        "band's first several shows before Lesh joined; Wikidata/MusicBrainz record "
        "only year precision (1965) and do not distinguish this. Performer-role "
        "rows continue through the band's final show, 1995-07-09. "
        + mb_note("Phil Lesh") + " " + wd_note("Phil Lesh"),
    )

    # Pigpen: held disagreement between MusicBrainz's death-year end (1973)
    # and Wikidata/lineup evidence's last-performance end (1972).
    start, end = first_last("person-ron-pigpen-mckernan")
    add(
        "membership-ron-pigpen-mckernan-1965", "person-ron-pigpen-mckernan",
        "keyboards, harmonica, vocals", start, "day", end, "day",
        f"Founding member. show_performers' last performer-role row is {end}; "
        "Pigpen stopped touring in mid-1972 due to illness and died 1973-03-08. "
        "HELD DISAGREEMENT: MusicBrainz's member-of-band relation gives end "
        "1973 (his death year), while Wikidata's member-of statement and the "
        f"lineup evidence agree on {end}/1972. This row uses the last documented "
        "performance rather than the date of death; see "
        "docs/collection-status-band-membership.md. "
        + mb_note("Ron “Pigpen” McKernan") + " " + wd_note('Ron "Pigpen" McKernan'),
    )

    # Tom Constanten: single bounded tenure, MusicBrainz month precision.
    start, end = first_last("person-tom-constanten")
    add(
        "membership-tom-constanten-1968", "person-tom-constanten", "keyboards",
        start, "day", end, "day",
        f"show_performers performer-role rows run {start} to {end}, matching "
        "MusicBrainz's month-precision end (1970-01) and Wikidata's year-level "
        "1968-1970. " + mb_note("Tom Constanten") + " " + wd_note("Tom Constanten"),
    )

    # Keith Godchaux.
    start, end = first_last("person-keith-godchaux")
    add(
        "membership-keith-godchaux-1971", "person-keith-godchaux", "keyboards",
        start, "day", end, "day",
        f"show_performers performer-role rows run {start} to {end}, matching "
        "MusicBrainz and Wikidata (1971-1979). Keith Godchaux died 1980-07-23, "
        "after leaving the band. " + mb_note("Keith Godchaux") + " " + wd_note("Keith Godchaux"),
    )

    # Donna Jean Godchaux: guest debut 1971-12-31, performer-role member from 1972.
    start, end = first_last("person-donna-jean-godchaux")
    add(
        "membership-donna-jean-godchaux-1972", "person-donna-jean-godchaux", "vocals",
        start, "day", end, "day",
        f"show_performers performer-role rows run {start} to {end}; a single "
        "guest-role row on 1971-12-31 (New Year's Eve) precedes her formal "
        "membership and is not counted as tenure start. MusicBrainz gives begin "
        "1972 (matching); Wikidata gives 1971 (matching the guest debut, not "
        "the performer-role start). " + mb_note("Donna Jean Godchaux") + " " + wd_note("Donna Jean Godchaux"),
    )

    # Brent Mydland: minor (3-day) gap between last show and date of death.
    start, end = first_last("person-brent-mydland")
    add(
        "membership-brent-mydland-1979", "person-brent-mydland", "keyboards, vocals",
        start, "day", end, "day",
        f"show_performers performer-role rows run {start} to {end} (his last "
        "show); Mydland died 1990-07-26, three days later. MusicBrainz's "
        "member-of-band relation gives end 1990-07-26 (his date of death); this "
        "row uses the last documented performance instead, a few days apart "
        "rather than a substantive disagreement. " + mb_note("Brent Mydland") + " " + wd_note("Brent Mydland"),
    )

    # Vince Welnick: bounded to the band's own end.
    start, end = first_last("person-vince-welnick")
    add(
        "membership-vince-welnick-1990", "person-vince-welnick", "keyboards, vocals",
        start, "day", "1995-07-09", "day",
        f"show_performers performer-role rows run {start} through the band's "
        "final show, 1995-07-09, matching MusicBrainz and Wikidata (1990-1995). "
        + mb_note("Vince Welnick") + " " + wd_note("Vince Welnick"),
    )

    # Bruce Hornsby: touring auxiliary member, bounded by performer-role rows;
    # guest sit-ins before and after are excluded from the tenure.
    start, end = first_last("person-bruce-hornsby")
    guest_first, guest_last = "1988-06-25", "1994-08-04"
    add(
        "membership-bruce-hornsby-1990", "person-bruce-hornsby",
        "keyboards, accordion, vocals", start, "day", end, "day",
        f"Touring auxiliary member alongside Vince Welnick. show_performers "
        f"performer-role rows run {start} to {end}, matching Wikidata's "
        "has-part qualifier on the band's own item (1990-1992). MusicBrainz's "
        "member-of-band relation for Hornsby carries no begin/end. Separate "
        f"guest-role sit-ins from {guest_first} through {guest_last} (including "
        "under the JerryBase 'Bruce Hornsby (complete show)' identity, "
        "person-bruce-hornsby-complete-show) precede and follow this tenure "
        "and are not counted as membership. " + wd_note("Bruce Hornsby"),
    )

    # Mickey Hart: two tenures.
    all_dates = performer_dates["person-mickey-hart"]
    first_tenure = [d for d in all_dates if d < "1974-01-01"]
    second_tenure = [d for d in all_dates if d >= "1974-01-01"]
    add(
        "membership-mickey-hart-1967", "person-mickey-hart", "drums, percussion",
        first_tenure[0], "day", first_tenure[-1], "day",
        f"show_performers performer-role rows run {first_tenure[0]} to "
        f"{first_tenure[-1]}, matching MusicBrainz and Wikidata (1967-1971). "
        + mb_note("Mickey Hart") + " " + wd_note("Mickey Hart"),
    )
    add(
        "membership-mickey-hart-1975", "person-mickey-hart", "drums, percussion",
        second_tenure[0], "day", "1995-07-09", "day",
        f"show_performers performer-role rows resume {second_tenure[0]} (the "
        "SNACK benefit at Kezar Stadium) through the band's final show, "
        "1995-07-09, matching MusicBrainz's second relation (begin 1975). "
        "Wikidata's second member-of statement gives start 1974, matching a "
        "single guest-role sit-in on 1974-10-20 (during the band's final "
        "Winterland run before its 1974-1976 touring hiatus) that precedes "
        "full reinstatement; this row uses the performer-role return date. "
        "MusicBrainz relation: begin 1975, end 1995. " + wd_note("Mickey Hart"),
    )

    return rows


def write_csv(rows: list[dict[str, str]], path: Path) -> None:
    fieldnames = [
        "membership_id", "person_id", "act", "role", "start_date", "end_date",
        "start_precision", "end_precision", "source_key", "source_record_id", "notes",
    ]
    rows_sorted = sorted(rows, key=lambda row: (row["person_id"], row["start_date"]))
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows_sorted)


def main() -> None:
    wikidata_records = _load_jsonl(RAW_DIR / "wikidata-grateful-dead-members.jsonl")
    musicbrainz_records = _load_jsonl(RAW_DIR / "musicbrainz-grateful-dead-members.jsonl")
    performer_dates = _performer_dates(
        CANONICAL_DIR / "show_performers.csv", CANONICAL_DIR / "shows.csv"
    )
    rows = build_rows(wikidata_records, musicbrainz_records, performer_dates)
    write_csv(rows, CANONICAL_DIR / "band_memberships.csv")
    print(f"wrote {len(rows)} band_memberships rows")


if __name__ == "__main__":
    main()
