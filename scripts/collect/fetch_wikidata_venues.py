#!/usr/bin/env python3
"""Collect Wikidata candidates and location data for every canonical venue.

Follows the shape of ``fetch_wikipedia_album_dates.py``: one request per
second (plus backoff on 429/503, honoring ``Retry-After``), a durable raw
cache that makes a re-run resume rather than repeat completed requests, and
compact JSONL raw records that keep source identity and retrieval time.

This script only *collects*; it makes no matching or promotion decisions.
``scripts/normalize_wikidata_venues.py`` reads its output plus
``data/canonical/venues.csv`` and decides what is confident enough to
promote, what is held for review, and what is left unmatched.

Two passes, against the public Wikidata MediaWiki action API
(``www.wikidata.org/w/api.php``):

1. **Search** (``action=wbsearchentities``) once per venue, querying the
   venue's own name. A venue whose name contains a comma (e.g. "Activity
   Center, Arizona State University") is also searched on its first segment
   alone, since Wikidata often titles the item without the qualifier. Every
   candidate's id, label, description and matched alias (if any) is kept.
2. **Entity fetch** (``action=wbgetentities``) for every distinct QID surfaced
   by search, batched up to 50 ids per request (the API's documented limit),
   requesting English labels, English aliases, and a fixed set of claims:
   P625 (coordinate location), P31 (instance of), P131 (located in the
   administrative territorial entity), P17 (country), P1083 (capacity). Any
   QID referenced by a fetched entity's P31 or P131 is queued for another
   round of the same batched fetch, so the location and instance-of chain can
   be walked without a second script. This repeats until no new QIDs surface
   or ``MAX_HOPS`` rounds have run (a venue -> city -> state/province ->
   country chain is at most four links).

Raw output, both append-only caches keyed by stable id so a partial prior run
is preserved and only missing venues/entities are re-requested:

- ``data/raw/venues/wikidata-venue-search.jsonl`` -- one record per venue_id
  with the query strings tried, HTTP status, and the candidate list.
- ``data/raw/venues/wikidata-entities.jsonl`` -- one record per QID with its
  English label, English aliases, and the claim values listed above (decoded
  to plain ids/numbers/coordinates, not the full nested API envelope -- the
  same compaction ``fetch_wikipedia_album_dates.py`` applies to infobox
  fields).

Nothing else about a Wikidata item -- other-language labels, sitelinks,
statement references, images -- is retrieved or retained, matching the
metadata-only retention policy registered for ``wikidata-api`` in
``data/source_registry.json``.
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
RAW_DIR = ROOT / "data" / "raw" / "venues"
SEARCH_PATH = RAW_DIR / "wikidata-venue-search.jsonl"
ENTITIES_PATH = RAW_DIR / "wikidata-entities.jsonl"
CANONICAL_VENUES_CSV = ROOT / "data" / "canonical" / "venues.csv"

API = "https://www.wikidata.org/w/api.php"
USER_AGENT = "DeadbotVenueResearch/0.1 (metadata-only venue geography collection; contact mark@interactivestrategies.com)"
REQUEST_INTERVAL_SECONDS = 1.0
MAX_ATTEMPTS = 6
DEFAULT_BACKOFF_SECONDS = 20
MAX_BACKOFF_SECONDS = 90
SEARCH_LIMIT = 10
ENTITY_BATCH_SIZE = 50
MAX_HOPS = 4

CLAIM_PROPERTIES = ("P625", "P31", "P131", "P17", "P1083")


def now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


class Client:
    """Paced Wikidata MediaWiki API client with bounded retries."""

    def __init__(self) -> None:
        self.request_count = 0
        self._last_request_at = 0.0

    def get(self, params: dict[str, str]) -> tuple[int, str, dict]:
        query = dict(params)
        query["format"] = "json"
        url = API + "?" + urllib.parse.urlencode(query)
        status, payload = 0, {}
        for attempt in range(MAX_ATTEMPTS):
            wait = self._last_request_at + REQUEST_INTERVAL_SECONDS - time.monotonic()
            if wait > 0:
                time.sleep(wait)
            request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
            self._last_request_at = time.monotonic()
            self.request_count += 1
            try:
                with urllib.request.urlopen(request, timeout=60) as response:
                    status = response.status
                    payload = json.loads(response.read().decode("utf-8"))
                return status, url, payload
            except urllib.error.HTTPError as error:
                status = error.code
                retry_after = error.headers.get("Retry-After") if error.headers else None
                try:
                    payload = json.loads(error.read().decode("utf-8"))
                except (ValueError, OSError):
                    payload = {"error": str(error)}
                if status not in (429, 503):
                    return status, url, payload
                try:
                    backoff = min(int(retry_after), MAX_BACKOFF_SECONDS) if retry_after else DEFAULT_BACKOFF_SECONDS
                except ValueError:
                    backoff = DEFAULT_BACKOFF_SECONDS
            except (urllib.error.URLError, TimeoutError, OSError) as error:
                status, payload = 0, {"error": str(error)}
                backoff = min(2 ** (attempt + 1), MAX_BACKOFF_SECONDS)
            print(f"  retry {attempt + 1}/{MAX_ATTEMPTS} after HTTP {status} in {backoff}s", file=sys.stderr)
            time.sleep(backoff)
        return status, url, payload


def load_venues() -> list[dict]:
    with CANONICAL_VENUES_CSV.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def load_jsonl(path: Path) -> dict[str, dict]:
    if not path.exists():
        return {}
    records: dict[str, dict] = {}
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


def write_jsonl(path: Path, records: dict[str, dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for key in sorted(records):
            handle.write(json.dumps(records[key], sort_keys=True))
            handle.write("\n")


def search_candidates(client: Client, query: str, request_log: list[dict]) -> tuple[int, list[dict]]:
    status, url, payload = client.get(
        {"action": "wbsearchentities", "search": query, "language": "en", "type": "item", "limit": str(SEARCH_LIMIT)}
    )
    request_log.append({"query": query, "url": url, "http_status": status, "at": now_iso()})
    if status != 200:
        return status, []
    candidates = [
        {
            "id": item.get("id", ""),
            "label": (item.get("display", {}).get("label", {}) or {}).get("value", item.get("label", "")),
            "description": (item.get("display", {}).get("description", {}) or {}).get("value", item.get("description", "")),
            "match_type": (item.get("match", {}) or {}).get("type", ""),
            "match_text": (item.get("match", {}) or {}).get("text", ""),
        }
        for item in payload.get("search", [])
    ]
    return status, candidates


def fetch_venue_searches(client: Client, venues: list[dict], cache: dict[str, dict], refresh: bool) -> None:
    for venue in venues:
        venue_id = venue["venue_id"]
        if not refresh and venue_id in cache and cache[venue_id].get("status") == "ok":
            continue
        name = venue["name"].strip()
        queries = [name]
        if "," in name:
            first_segment = name.split(",", 1)[0].strip()
            if first_segment and first_segment != name:
                queries.append(first_segment)
        request_log: list[dict] = []
        all_candidates: dict[str, dict] = {}
        overall_status = "ok"
        for query in queries:
            status, candidates = search_candidates(client, query, request_log)
            if status != 200:
                overall_status = "search_failed"
            for candidate in candidates:
                all_candidates.setdefault(candidate["id"], candidate)
        cache[venue_id] = {
            "venue_id": venue_id,
            "name": name,
            "city": venue.get("city", ""),
            "country": venue.get("country", ""),
            "queries": queries,
            "requests": request_log,
            "candidates": list(all_candidates.values()),
            "status": overall_status,
            "retrieved_at": now_iso(),
        }
        print(f"searched {venue_id}: {len(all_candidates)} candidate(s)", file=sys.stderr)


def decode_claims(claims: dict) -> dict[str, Any]:
    decoded: dict[str, Any] = {}
    for prop in CLAIM_PROPERTIES:
        statements = claims.get(prop, [])
        values = []
        for statement in statements:
            snak = statement.get("mainsnak", {})
            if snak.get("snaktype") != "value":
                continue
            datavalue = snak.get("datavalue", {})
            value = datavalue.get("value")
            if datavalue.get("type") == "wikibase-entityid" and isinstance(value, dict):
                values.append(value.get("id"))
            elif datavalue.get("type") == "globecoordinate" and isinstance(value, dict):
                values.append({"latitude": value.get("latitude"), "longitude": value.get("longitude")})
            elif datavalue.get("type") == "quantity" and isinstance(value, dict):
                values.append(value.get("amount"))
            elif value is not None:
                values.append(value)
        if values:
            decoded[prop] = values
    return decoded


def fetch_entities(client: Client, qids: list[str]) -> dict[str, dict]:
    fetched: dict[str, dict] = {}
    for start in range(0, len(qids), ENTITY_BATCH_SIZE):
        batch = qids[start : start + ENTITY_BATCH_SIZE]
        status, url, payload = client.get(
            {
                "action": "wbgetentities",
                "ids": "|".join(batch),
                "props": "labels|aliases|claims",
                "languages": "en",
            }
        )
        if status != 200:
            print(f"  entity batch failed HTTP {status}: {url}", file=sys.stderr)
            continue
        entities = payload.get("entities", {})
        for qid, entity in entities.items():
            if entity.get("missing") is not None:
                fetched[qid] = {"qid": qid, "missing": True, "retrieved_at": now_iso()}
                continue
            label = (entity.get("labels", {}).get("en", {}) or {}).get("value", "")
            aliases = [alias.get("value", "") for alias in entity.get("aliases", {}).get("en", [])]
            claims = decode_claims(entity.get("claims", {}))
            fetched[qid] = {
                "qid": qid,
                "label": label,
                "aliases": aliases,
                "claims": claims,
                "retrieved_at": now_iso(),
            }
        print(f"fetched entity batch: {len(batch)} id(s)", file=sys.stderr)
    return fetched


def expand_entities(client: Client, entity_cache: dict[str, dict]) -> None:
    """Resolve P31 (instance of) labels one hop out, and walk P131 (located in)
    all the way up to a country.

    P31 stops after one hop: a venue's class ("concert hall", "stadium")
    only needs its own English label to classify indoor/outdoor, not its
    place in Wikidata's class hierarchy, which balloons quickly and unrelated
    to venue geography. P131 keeps climbing hop after hop, since the point is
    to reach the venue's city, state/province, and country.
    """

    seen = set(entity_cache)
    # First hop: resolve both P31 (class, one hop only) and P131 (start of
    # the location chain) from every already-fetched entity.
    referenced: set[str] = set()
    location_frontier: set[str] = set()
    for qid in list(entity_cache):
        claims = entity_cache[qid].get("claims", {})
        for value in claims.get("P31", []):
            if isinstance(value, str) and value.startswith("Q") and value not in seen:
                referenced.add(value)
        for value in claims.get("P131", []):
            if isinstance(value, str) and value.startswith("Q") and value not in seen:
                referenced.add(value)
                location_frontier.add(value)
    if referenced:
        print(f"hop 1: fetching {len(referenced)} new entit(y/ies)", file=sys.stderr)
        newly_fetched = fetch_entities(client, sorted(referenced))
        entity_cache.update(newly_fetched)
        seen |= referenced

    # Remaining hops: only continue climbing P131 from location-chain nodes.
    frontier = location_frontier
    for hop in range(MAX_HOPS - 1):
        referenced = set()
        for qid in frontier:
            claims = entity_cache.get(qid, {}).get("claims", {})
            for value in claims.get("P131", []):
                if isinstance(value, str) and value.startswith("Q") and value not in seen:
                    referenced.add(value)
        if not referenced:
            break
        print(f"hop {hop + 2}: fetching {len(referenced)} new entit(y/ies)", file=sys.stderr)
        newly_fetched = fetch_entities(client, sorted(referenced))
        entity_cache.update(newly_fetched)
        seen |= referenced
        frontier = referenced


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--refresh", action="store_true", help="Re-search every venue, ignoring the existing search cache.")
    parser.add_argument("--limit", type=int, default=None, help="Only process the first N venues (for testing).")
    args = parser.parse_args()

    venues = load_venues()
    if args.limit:
        venues = venues[: args.limit]

    search_cache = load_jsonl(SEARCH_PATH)
    entity_cache = load_jsonl(ENTITIES_PATH)

    client = Client()
    fetch_venue_searches(client, venues, search_cache, args.refresh)
    write_jsonl(SEARCH_PATH, search_cache)

    all_candidate_qids = sorted(
        {candidate["id"] for record in search_cache.values() for candidate in record.get("candidates", []) if candidate.get("id")}
    )
    missing_qids = [qid for qid in all_candidate_qids if qid not in entity_cache]
    if missing_qids:
        print(f"fetching {len(missing_qids)} venue-candidate entities", file=sys.stderr)
        entity_cache.update(fetch_entities(client, missing_qids))
        write_jsonl(ENTITIES_PATH, entity_cache)

    expand_entities(client, entity_cache)
    write_jsonl(ENTITIES_PATH, entity_cache)

    print(f"done: {client.request_count} HTTP requests this run", file=sys.stderr)
    print(f"search cache: {len(search_cache)} venues; entity cache: {len(entity_cache)} QIDs", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
