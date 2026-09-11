#!/usr/bin/env python3
"""Promote confident Wikidata venue matches into ``data/canonical/venues.csv``.

Reads ``data/raw/venues/wikidata-venue-search.jsonl`` (search candidates) and
``data/raw/venues/wikidata-entities.jsonl`` (entity claims), both written by
``scripts/collect/fetch_wikidata_venues.py``, and makes every matching
decision this pass promotes. Nothing here performs network access.

A candidate is promoted only when both hold:

- **Name agreement**: the candidate's English label, or one of its English
  aliases, equals the venue's name after normalization (casefolded,
  diacritics stripped, punctuation collapsed to spaces, a leading "the "
  dropped) -- either the full venue name or, for a compound name such as
  "Activity Center, Arizona State University", the text before the first
  comma.
- **City agreement**: walking the candidate's P131 ("located in the
  administrative territorial entity") chain up through its own P131 parents
  reaches an entity whose normalized label equals the venue's canonical
  city.

Exactly one promoted candidate is required. Zero, or more than one, is held
for review rather than guessed. A held or unmatched venue's latitude,
longitude, setting and capacity are left untouched (they start and stay
blank); state_region is likewise left untouched unless the venue was one of
the 56 rows with a blank state_region going in.

For a promoted candidate:

- **latitude/longitude** come from P625, and the QID is appended to
  ``notes`` so the match stays reviewable.
- **setting** is set only when a P31 (instance of) label contains one of the
  five outdoor terms (stadium, amphitheatre/amphitheater, fairground, park,
  racetrack) or one of the five indoor terms (arena, theatre/theater,
  auditorium, ballroom, club) named in the collection brief. Any other class
  (a university building, a generic "hall" or "pavilion", a convention
  center) is left blank rather than guessed.
- **capacity** is set only when P1083 (maximum capacity) is stated.
- **state_region** is filled, only for a venue that started blank, by
  finding the chain node whose own P31 marks it a country (Wikidata Q6256)
  and taking the chain's next-closer node's label as the state/region name.
  This is skipped if that label would just repeat the venue's existing
  ``country`` field (already true, for this dataset, of the constituent
  countries of the UK).

Output:

- Rewrites ``data/canonical/venues.csv`` with ``setting`` and ``capacity``
  columns added, latitude/longitude/state_region filled for confident
  matches.
- Writes ``data/raw/venues/venue-geography-review.jsonl``: one record per
  venue that was NOT promoted (no candidates, no name match, name match but
  no city agreement, or more than one qualifying candidate), with every
  candidate this pass actually saw, so a human reviewer does not have to
  re-run the search.
- Writes ``data/raw/venues/venue-geography-run.json``: a run summary with
  requested/confident/held/unmatched counts and setting/capacity coverage,
  the source for ``docs/collection-status-venue-geography.md``.
"""

from __future__ import annotations

import csv
import json
import re
import sys
import unicodedata
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
RAW_DIR = ROOT / "data" / "raw" / "venues"
SEARCH_PATH = RAW_DIR / "wikidata-venue-search.jsonl"
ENTITIES_PATH = RAW_DIR / "wikidata-entities.jsonl"
REVIEW_PATH = RAW_DIR / "venue-geography-review.jsonl"
RUN_SUMMARY_PATH = RAW_DIR / "venue-geography-run.json"
CANONICAL_VENUES_CSV = ROOT / "data" / "canonical" / "venues.csv"

VENUE_COLUMNS = ["venue_id", "name", "city", "state_region", "country", "latitude", "longitude", "notes", "setting", "capacity"]

OUTDOOR_TERMS = ("stadium", "amphitheatre", "amphitheater", "fairground", "park", "racetrack")
INDOOR_TERMS = ("arena", "theatre", "theater", "auditorium", "ballroom", "club")

# Wikidata QIDs for the modern country the *current* countries in
# venues.csv's own "country" column, by exact (case-sensitive) column value.
# Using a fixed, verified QID -- rather than "is this chain node's own P31
# 'country' (Q6256)?" -- matters here: several defunct polities (the Grand
# Duchy of Frankfurt, the Kingdom of Bavaria, the historical province of
# Upper Canada) are *also* instance-of country in Wikidata, and a P131 chain
# through a former capital or a redevelopment authority can pass through one
# of those before reaching the modern country. Stopping generically at the
# first "country"-typed node found several of those instead of Germany or
# Canada. Every distinct value venues.csv's country column holds is listed
# here (verified against the fetched entity cache); a country not listed
# here yields no state_region fill rather than a guess.
COUNTRY_QID_BY_NAME = {
    "US": "Q30",
    "Canada": "Q16",
    "England": "Q21",
    "Scotland": "Q22",
    "Germany": "Q183",
    "France": "Q142",
    "Netherlands": "Q55",
    "Denmark": "Q35",
    "Sweden": "Q34",
    "Spain": "Q29",
    "Luxembourg": "Q32",
    "Egypt": "Q79",
    "Jamaica": "Q766",
}

# Current (not defunct/historical) first-level subdivisions for the
# countries above, used as an allowlist by resolve_state_region so a stale
# or off-level P131 chain node is dropped rather than promoted.
ALLOWED_STATE_REGIONS = {
    # Canadian provinces and territories.
    "Ontario", "Quebec", "British Columbia", "Alberta", "Manitoba",
    "Saskatchewan", "Nova Scotia", "New Brunswick",
    "Newfoundland and Labrador", "Prince Edward Island", "Yukon",
    "Northwest Territories", "Nunavut",
    # Dutch provinces.
    "North Holland", "South Holland", "Utrecht", "Gelderland",
    "North Brabant", "Limburg", "Zeeland", "Overijssel", "Groningen",
    "Friesland", "Drenthe", "Flevoland",
    # German Länder.
    "Bavaria", "Hesse", "North Rhine-Westphalia", "Baden-Württemberg",
    "Lower Saxony", "Saxony", "Rhineland-Palatinate", "Berlin",
    "Schleswig-Holstein", "Brandenburg", "Saxony-Anhalt", "Thuringia",
    "Hamburg", "Mecklenburg-Vorpommern", "Saarland", "Bremen",
    # French administrative regions (2016 reform).
    "Auvergne-Rhone-Alpes", "Auvergne-Rhône-Alpes",
    "Bourgogne-Franche-Comte", "Bourgogne-Franche-Comté", "Brittany",
    "Bretagne", "Centre-Val de Loire", "Corsica", "Corse", "Grand Est",
    "Hauts-de-France", "Ile-de-France", "Île-de-France", "Normandy",
    "Normandie", "Nouvelle-Aquitaine", "Occitanie", "Pays de la Loire",
    "Provence-Alpes-Cote d'Azur", "Provence-Alpes-Côte d'Azur",
    # Danish and Swedish first-level regions/counties.
    "Capital Region of Denmark", "Stockholm County",
}

_DIACRITICS = re.compile(r"[̀-ͯ]")
_PUNCTUATION = re.compile(r"[^a-z0-9]+")
_LEADING_THE = re.compile(r"^the\s+")
_WIKIDATA_NOTE = re.compile(r"\s*Wikidata: Q\d+ \(name\+city matched\)\.")


def fold(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value or "")
    stripped = _DIACRITICS.sub("", normalized)
    spaced = _PUNCTUATION.sub(" ", stripped.casefold()).strip()
    spaced = re.sub(r"\s+", " ", spaced)
    return _LEADING_THE.sub("", spaced).strip()


def load_jsonl(path: Path) -> dict[str, dict]:
    records: dict[str, dict] = {}
    if not path.exists():
        return records
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            record = json.loads(line)
            key = record.get("venue_id") or record.get("qid")
            if key:
                records[key] = record
    return records


def venue_name_keys(name: str) -> set[str]:
    keys = {fold(name)}
    if "," in name:
        first = name.split(",", 1)[0].strip()
        if first:
            keys.add(fold(first))
    keys.discard("")
    return keys


def name_matches(entity: dict, name_keys: set[str]) -> bool:
    label_key = fold(entity.get("label", ""))
    if label_key and label_key in name_keys:
        return True
    for alias in entity.get("aliases", []):
        if fold(alias) in name_keys:
            return True
    return False


def location_chain(qid_list: list[str], entities: dict[str, dict], max_hops: int = 6) -> list[tuple[str, dict]]:
    """Walk P131 parents starting from qid_list, returning (qid, entity) pairs, nearest first."""

    chain: list[tuple[str, dict]] = []
    visited: set[str] = set()
    frontier = list(qid_list)
    for _ in range(max_hops):
        next_frontier: list[str] = []
        for qid in frontier:
            if qid in visited:
                continue
            visited.add(qid)
            entity = entities.get(qid)
            if not entity or entity.get("missing"):
                continue
            chain.append((qid, entity))
            next_frontier.extend(entity.get("claims", {}).get("P131", []))
        frontier = next_frontier
        if not frontier:
            break
    return chain


def city_agrees(chain: list[tuple[str, dict]], city: str) -> bool:
    city_key = fold(city)
    if not city_key:
        return False
    return any(fold(entity.get("label", "")) == city_key for _, entity in chain)


def classify_setting(instance_qids: list[str], entities: dict[str, dict], venue_label: str = "") -> str:
    # A "dome" venue (JMA Wireless Dome, the former Carrier Dome; the Hubert
    # H. Humphrey Metrodome) is instance-of "stadium" in Wikidata like any
    # open-air stadium, but the name itself says it is enclosed. Since
    # setting exists to scope the notable-weather question family, an
    # explicit "dome" in the matched entity's own label overrides the
    # generic stadium->outdoor rule.
    if "dome" in fold(venue_label):
        return "indoor"
    labels = [fold(entities.get(qid, {}).get("label", "")) for qid in instance_qids]
    for label in labels:
        if any(term in label for term in OUTDOOR_TERMS):
            return "outdoor"
    for label in labels:
        if any(term in label for term in INDOOR_TERMS):
            return "indoor"
    return ""


def parse_capacity(values: list) -> str:
    for value in values:
        try:
            amount = float(str(value).lstrip("+"))
        except (TypeError, ValueError):
            continue
        if amount > 0:
            return str(int(round(amount)))
    return ""


def resolve_state_region(chain: list[tuple[str, dict]], existing_country: str) -> str:
    """The chain entry immediately below the modern country -- but only if
    it names a real, current first-level subdivision.

    Wikidata's P131 chain is not reliably clean above the city: Munich's
    chain reaches a "Kingdom of Bavaria" node (a defunct pre-1918 state, also
    instance-of country in its own right) before reaching modern Germany;
    Toronto's reaches "Upper Canada" (defunct 1841) before modern Canada; a
    Paris venue's reaches "metropolitan France" (a France-minus-overseas
    grouping, not a region) before France. Rather than try to detect and
    reject every such defunct or off-level node from its own claims (a
    second round of entity fetches this pass did not make), the resolved
    label is only accepted when it is on ``ALLOWED_STATE_REGIONS`` --
    current provinces/territories/states/regions for the countries this
    catalog actually has. Anything else is left blank rather than risk a
    defunct-polity value like "Kingdom of Bavaria" in canonical data.
    """

    target_qid = COUNTRY_QID_BY_NAME.get(existing_country.strip())
    if not target_qid:
        return ""
    previous_label = ""
    for qid, entity in chain:
        if qid == target_qid:
            if previous_label and previous_label in ALLOWED_STATE_REGIONS:
                return previous_label
            return ""
        previous_label = entity.get("label", "")
    return ""


def first_coordinate(claims: dict) -> tuple[float, float] | None:
    for value in claims.get("P625", []):
        if isinstance(value, dict) and value.get("latitude") is not None and value.get("longitude") is not None:
            return float(value["latitude"]), float(value["longitude"])
    return None


def evaluate_venue(venue: dict, search_record: dict, entities: dict[str, dict]) -> dict:
    candidates = search_record.get("candidates", []) if search_record else []
    name_keys = venue_name_keys(venue["name"])
    seen_candidates = []
    qualifying: list[dict] = []
    for candidate in candidates:
        qid = candidate.get("id", "")
        entity = entities.get(qid)
        seen = {**candidate, "wikidata_label": entity.get("label") if entity else None}
        if not entity or entity.get("missing"):
            seen["reject_reason"] = "entity_not_found"
            seen_candidates.append(seen)
            continue
        if not name_matches(entity, name_keys):
            seen["reject_reason"] = "name_mismatch"
            seen_candidates.append(seen)
            continue
        claims = entity.get("claims", {})
        chain = location_chain(claims.get("P131", []), entities)
        if not city_agrees(chain, venue.get("city", "")):
            seen["reject_reason"] = "city_mismatch"
            seen["location_chain"] = [ent.get("label", "") for _, ent in chain]
            seen_candidates.append(seen)
            continue
        coordinate = first_coordinate(claims)
        if coordinate is None:
            seen["reject_reason"] = "no_coordinates"
            seen_candidates.append(seen)
            continue
        seen["reject_reason"] = None
        seen_candidates.append(seen)
        qualifying.append({"qid": qid, "entity": entity, "chain": chain, "coordinate": coordinate})

    if len(qualifying) == 1:
        return {"status": "confident", "match": qualifying[0], "candidates": seen_candidates}
    if len(qualifying) > 1:
        return {"status": "held", "reason": "multiple_qualifying_candidates", "candidates": seen_candidates}
    if not candidates:
        return {"status": "unmatched", "reason": "no_search_candidates", "candidates": seen_candidates}
    return {"status": "held", "reason": "no_qualifying_candidate", "candidates": seen_candidates}


def main() -> int:
    with CANONICAL_VENUES_CSV.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        existing_columns = reader.fieldnames or []
        venues = list(reader)

    search_cache = load_jsonl(SEARCH_PATH)
    entities = load_jsonl(ENTITIES_PATH)

    counts = {"requested": len(venues), "confident": 0, "held": 0, "unmatched": 0}
    setting_counts = {"indoor": 0, "outdoor": 0, "blank": 0}
    capacity_counts = {"filled": 0, "blank": 0}
    state_region_filled = 0
    state_region_targets = 0
    review_records = []

    for venue in venues:
        # Preserve any column already on this row and add the two new ones.
        for column in ("setting", "capacity"):
            venue.setdefault(column, "")

        was_blank_state_region = not venue.get("state_region", "").strip()
        if was_blank_state_region:
            state_region_targets += 1

        search_record = search_cache.get(venue["venue_id"])
        result = evaluate_venue(venue, search_record, entities)

        if result["status"] == "confident":
            counts["confident"] += 1
            match = result["match"]
            lat, lon = match["coordinate"]
            venue["latitude"] = str(lat)
            venue["longitude"] = str(lon)
            qid = match["qid"]
            # Strip any Wikidata note a prior run of this script already
            # appended, so a rerun replaces rather than duplicates it.
            note = _WIKIDATA_NOTE.sub("", venue.get("notes", "")).strip()
            venue["notes"] = (note + " " if note else "") + f"Wikidata: {qid} (name+city matched)."

            instance_qids = [v for v in match["entity"].get("claims", {}).get("P31", []) if isinstance(v, str)]
            setting = classify_setting(instance_qids, entities, match["entity"].get("label", ""))
            venue["setting"] = setting
            setting_counts[setting or "blank"] += 1

            capacity = parse_capacity(match["entity"].get("claims", {}).get("P1083", []))
            venue["capacity"] = capacity
            capacity_counts["filled" if capacity else "blank"] += 1

            if was_blank_state_region:
                state_region = resolve_state_region(match["chain"], venue.get("country", ""))
                if state_region:
                    venue["state_region"] = state_region
                    state_region_filled += 1
        else:
            if result["status"] == "held":
                counts["held"] += 1
            else:
                counts["unmatched"] += 1
            setting_counts["blank"] += 1
            capacity_counts["blank"] += 1
            review_records.append(
                {
                    "venue_id": venue["venue_id"],
                    "name": venue["name"],
                    "city": venue.get("city", ""),
                    "state_region": venue.get("state_region", ""),
                    "country": venue.get("country", ""),
                    "status": result["status"],
                    "reason": result.get("reason", ""),
                    "candidates_seen": result["candidates"],
                }
            )

    # Column order: existing columns, plus setting/capacity if not already present.
    output_columns = list(existing_columns)
    for column in ("setting", "capacity"):
        if column not in output_columns:
            output_columns.append(column)

    with CANONICAL_VENUES_CSV.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=output_columns)
        writer.writeheader()
        for venue in venues:
            writer.writerow({column: venue.get(column, "") for column in output_columns})

    RAW_DIR.mkdir(parents=True, exist_ok=True)
    with REVIEW_PATH.open("w", encoding="utf-8") as handle:
        for record in sorted(review_records, key=lambda r: r["venue_id"]):
            handle.write(json.dumps(record, sort_keys=True))
            handle.write("\n")

    summary = {
        "requested": counts["requested"],
        "confident": counts["confident"],
        "held": counts["held"],
        "unmatched": counts["unmatched"],
        "setting_coverage": setting_counts,
        "capacity_coverage": capacity_counts,
        "state_region": {
            "blank_going_in": state_region_targets,
            "filled_this_pass": state_region_filled,
        },
    }
    RUN_SUMMARY_PATH.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2, sort_keys=True), file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
