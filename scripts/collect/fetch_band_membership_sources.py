#!/usr/bin/env python3
"""Collect compact Wikidata and MusicBrainz records for Grateful Dead band membership.

This is the collection step for the canonical ``band_memberships`` table and
the ``people.birth_date`` / ``people.death_date`` fill described in
``docs/collection-status-band-membership.md``. It follows the project's
standard raw-record conventions: one request per second, a descriptive
User-Agent, and compact JSONL output that preserves source identifiers so a
later normalization pass can re-derive every canonical decision.

Two requests, run one second apart:

1. Wikidata: ``wbgetclaims`` for the Grateful Dead item (Q212533), property
   P527 ("has part(s)", used here for band members), to get each member's
   QID and any start/end (P580/P582) qualifiers on that statement. A second
   ``wbgetentities`` call resolves each member QID's label, date of birth
   (P569), date of death (P570), and that person's own P463 ("member of")
   statement for the band with its own start/end qualifiers -- kept separate
   from the band-item qualifiers because the two do not always agree (Bruce
   Hornsby's P463 statement carries no dates even though the band's P527
   statement does).
2. MusicBrainz: the Grateful Dead artist entity
   (6faa7ca7-0d99-4a5e-bfa6-1fd5037520c6) with ``inc=artist-rels``, which
   carries "member of band" relations with ``begin``/``end``/``ended`` and
   optional attributes (for example ``keyboard``) for artists related to the
   band.

Both are read-only public JSON web services; no authentication is used or
required. Only the fields named above are retained -- no Wikidata sitelinks,
statements about unrelated properties, or MusicBrainz release/recording data
are written to the raw files.
"""

from __future__ import annotations

import json
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
RAW_DIR = ROOT / "data" / "raw" / "people"

USER_AGENT = "Deadbot/0.1 (band membership research; contact via repository)"
GRATEFUL_DEAD_WIKIDATA_QID = "Q212533"
GRATEFUL_DEAD_MUSICBRAINZ_MBID = "6faa7ca7-0d99-4a5e-bfa6-1fd5037520c6"
MIN_INTERVAL_SECONDS = 1.0


def _get_json(url: str) -> dict[str, Any]:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.loads(response.read().decode("utf-8"))


def _throttled(urls: list[str]) -> list[dict[str, Any]]:
    results = []
    for index, url in enumerate(urls):
        if index:
            time.sleep(MIN_INTERVAL_SECONDS)
        results.append(_get_json(url))
    return results


def fetch_wikidata_band_members() -> list[dict[str, Any]]:
    """One record per Grateful Dead member statement on the band's own item."""

    claims_url = (
        "https://www.wikidata.org/w/api.php?action=wbgetclaims"
        f"&entity={GRATEFUL_DEAD_WIKIDATA_QID}&property=P527&format=json"
    )
    claims_doc = _get_json(claims_url)
    time.sleep(MIN_INTERVAL_SECONDS)
    claims = claims_doc.get("claims", {}).get("P527", [])
    member_qids = [
        claim["mainsnak"]["datavalue"]["value"]["id"]
        for claim in claims
        if claim.get("mainsnak", {}).get("datavalue")
    ]

    def _has_part_span(claim: dict[str, Any]) -> dict[str, str | None]:
        qualifiers = claim.get("qualifiers", {})

        def _time(prop: str) -> str | None:
            for qualifier in qualifiers.get(prop, []):
                value = qualifier.get("datavalue", {}).get("value", {})
                return value.get("time")
            return None

        return {"start": _time("P580"), "end": _time("P582")}

    # The band's own P527 ("has part(s)") statement sometimes carries a
    # start/end qualifier the member's own P463 statement does not mirror
    # (observed for Bruce Hornsby), so both qualifier locations are preserved.
    has_part_span_by_qid = {
        claim["mainsnak"]["datavalue"]["value"]["id"]: _has_part_span(claim)
        for claim in claims
        if claim.get("mainsnak", {}).get("datavalue")
    }

    # Wikidata's own qualifiers only carry P463 (member of) start/end on the
    # *person's* statement, not always mirrored on the band's P527 statement,
    # so member-level start/end come from each person's own P463 claim.
    entities_url = (
        "https://www.wikidata.org/w/api.php?action=wbgetentities"
        f"&ids={'|'.join(member_qids)}&props=labels|claims&languages=en&format=json"
    )
    entities_doc = _get_json(entities_url)
    entities = entities_doc.get("entities", {})

    def _p463_spans(entity: dict[str, Any]) -> list[dict[str, str | None]]:
        spans = []
        for claim in entity.get("claims", {}).get("P463", []):
            value = claim.get("mainsnak", {}).get("datavalue", {}).get("value", {})
            if value.get("id") != GRATEFUL_DEAD_WIKIDATA_QID:
                continue
            qualifiers = claim.get("qualifiers", {})

            def _time(prop: str) -> str | None:
                for qualifier in qualifiers.get(prop, []):
                    value = qualifier.get("datavalue", {}).get("value", {})
                    return value.get("time")
                return None

            spans.append({"start": _time("P580"), "end": _time("P582")})
        return spans

    def _date(entity: dict[str, Any], prop: str) -> str | None:
        for claim in entity.get("claims", {}).get(prop, []):
            value = claim.get("mainsnak", {}).get("datavalue", {}).get("value", {})
            return value.get("time")
        return None

    records = []
    for qid in member_qids:
        entity = entities.get(qid, {})
        records.append(
            {
                "source": "wikidata",
                "wikidata_qid": qid,
                "label": entity.get("labels", {}).get("en", {}).get("value"),
                "date_of_birth_raw": _date(entity, "P569"),
                "date_of_death_raw": _date(entity, "P570"),
                "member_of_grateful_dead_spans": _p463_spans(entity),
                "has_part_span_on_band_item": has_part_span_by_qid.get(qid),
            }
        )
    return records


def fetch_musicbrainz_member_relations() -> list[dict[str, Any]]:
    """One record per 'member of band' relation on the Grateful Dead artist."""

    url = (
        f"https://musicbrainz.org/ws/2/artist/{GRATEFUL_DEAD_MUSICBRAINZ_MBID}"
        "?inc=artist-rels&fmt=json"
    )
    document = _get_json(url)
    records = []
    for relation in document.get("relations", []):
        if relation.get("type") != "member of band":
            continue
        artist = relation.get("artist", {})
        records.append(
            {
                "source": "musicbrainz-api",
                "grateful_dead_mbid": GRATEFUL_DEAD_MUSICBRAINZ_MBID,
                "artist_mbid": artist.get("id"),
                "artist_name": artist.get("name"),
                "begin": relation.get("begin"),
                "end": relation.get("end"),
                "ended": relation.get("ended"),
                "attributes": relation.get("attributes", []),
            }
        )
    return records


def _write_jsonl(path: Path, records: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(record, ensure_ascii=False, sort_keys=True))
            handle.write("\n")


def main() -> None:
    retrieved_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    wikidata_records = fetch_wikidata_band_members()
    time.sleep(MIN_INTERVAL_SECONDS)
    musicbrainz_records = fetch_musicbrainz_member_relations()
    for record in (*wikidata_records, *musicbrainz_records):
        record["retrieved_at"] = retrieved_at

    _write_jsonl(RAW_DIR / "wikidata-grateful-dead-members.jsonl", wikidata_records)
    _write_jsonl(RAW_DIR / "musicbrainz-grateful-dead-members.jsonl", musicbrainz_records)
    print(f"wrote {len(wikidata_records)} Wikidata member records")
    print(f"wrote {len(musicbrainz_records)} MusicBrainz member relation records")


if __name__ == "__main__":
    main()
