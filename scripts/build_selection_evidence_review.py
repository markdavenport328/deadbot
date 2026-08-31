#!/usr/bin/env python3
"""Resolve collected selection signals conservatively against canonical IDs."""
from __future__ import annotations

import csv
import json
from collections import Counter
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CANONICAL = ROOT / "data" / "canonical"
RAW = ROOT / "data" / "raw"
OUTPUT = ROOT / "data" / "editorial" / "selection-evidence-review.json"


def csv_rows(name: str) -> list[dict[str, str]]:
    with (CANONICAL / name).open(newline="", encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def jsonl(path: Path) -> list[dict[str, object]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def document() -> dict[str, object]:
    shows = csv_rows("shows.csv")
    performances = csv_rows("performances.csv")
    shows_by_date: dict[str, list[dict[str, str]]] = {}
    for show in shows:
        shows_by_date.setdefault(show["show_date"], []).append(show)

    entries: list[dict[str, object]] = []
    critic_records = jsonl(RAW / "critic-signals" / "rolling-stone-australia-20-essential-shows.jsonl")
    for record in critic_records:
        payload = record["raw_payload"]
        if not isinstance(payload, dict) or "show_date" not in payload:
            continue
        date = str(payload["show_date"])
        candidates = shows_by_date.get(date, [])
        entries.append({
            "source": "rolling-stone-australia",
            "signal_type": "critic_editorial_show_selection",
            "source_record_id": record["source_record_id"],
            "source_url": record["source_url"],
            "show_date": date,
            "candidate_show_ids": [show["show_id"] for show in candidates],
            "resolution_state": "resolved_unique_show" if len(candidates) == 1 else "held_ambiguous_show_date",
            "selection_label": "David Fricke / Rolling Stone: 20 Essential Grateful Dead Shows",
        })

    fan_records = jsonl(RAW / "fan-signals" / "headyversion-best-versions.jsonl")
    for record in fan_records:
        date = str(record["performance_date"])
        song_id = str(record["song_id"])
        date_show_candidates = shows_by_date.get(date, [])
        performance_candidates = [
            performance for performance in performances
            if performance["song_id"] == song_id and performance["show_id"] in {show["show_id"] for show in date_show_candidates}
        ]
        if len(date_show_candidates) != 1:
            state = "held_ambiguous_show_date"
        elif len(performance_candidates) == 1:
            state = "resolved_unique_performance"
        elif not performance_candidates:
            state = "held_missing_canonical_performance"
        else:
            state = "held_multiple_canonical_performances"
        entries.append({
            "source": "headyversion",
            "signal_type": "fan_ranked_version",
            "source_url": record["source_url"],
            "song_id": song_id,
            "show_date": date,
            "candidate_show_ids": [show["show_id"] for show in date_show_candidates],
            "candidate_performance_ids": [performance["performance_id"] for performance in performance_candidates],
            "resolution_state": state,
            "collection_state": record["collection_state"],
            "recommendation_rank": record.get("recommendation_rank"),
            "fan_vote_count": record.get("fan_vote_count"),
        })

    release_records = jsonl(RAW / "releases" / "deadnet-featured-release-pass-2026-08-30.jsonl")
    for record in release_records:
        if record.get("record_type") != "release_candidate" or not record.get("release_id"):
            continue
        show_id = str(record["release_show_id"])
        entries.append({
            "source": "deadnet-official-release-pass",
            "signal_type": "official_release_candidate",
            "source_url": record["source_url"],
            "release_candidate_id": record["release_id"],
            "candidate_show_ids": [show_id] if show_id in {show["show_id"] for show in shows} else [],
            "resolution_state": "resolved_show_pending_release_review" if record["status"] in {"confirmed", "confirmed_collection_only"} else "held_source_detail_needed",
            "release_status": record["status"],
            "title": record["title"],
        })

    screenshot_records = jsonl(
        RAW / "individual-curators" / "charlie-miller-user-provided-threads-screenshot-2026-08-30.jsonl"
    )
    for record in screenshot_records:
        payload = record.get("raw_payload", {})
        if not isinstance(payload, dict):
            continue
        for item in payload.get("entries", []):
            if not isinstance(item, dict):
                continue
            date = str(item["performance_date"])
            song_id = str(item["song_id_candidate"])
            date_show_candidates = shows_by_date.get(date, [])
            performance_candidates = [
                performance for performance in performances
                if performance["song_id"] == song_id
                and performance["show_id"] in {show["show_id"] for show in date_show_candidates}
            ]
            if len(date_show_candidates) != 1:
                state = "held_ambiguous_show_date"
            elif len(performance_candidates) == 1:
                state = "resolved_unique_performance"
            elif not performance_candidates:
                state = "held_missing_canonical_performance"
            else:
                state = "held_multiple_canonical_performances"
            entries.append({
                "source": "charlie-miller-user-provided-threads",
                "signal_type": "individual_curator_song_selection",
                "source_handle": record["source_handle"],
                "source_provenance": "user_provided_screenshot",
                "identity_state": record["identity_state"],
                "song_id": song_id,
                "show_date": date,
                "candidate_show_ids": [show["show_id"] for show in date_show_candidates],
                "candidate_performance_ids": [performance["performance_id"] for performance in performance_candidates],
                "resolution_state": state,
                "source_label": item["source_label"],
                "source_context": item.get("source_context"),
            })

    reddit_records = jsonl(RAW / "individual-curators" / "charlie-miller-reddit-recommendations-2026-08-30.jsonl")
    for record in reddit_records:
        if "performance_date" not in record:
            entries.append({
                "source": "charlie-miller-reddit",
                "signal_type": str(record["selection_type"]),
                "source_handle": record["source_handle"],
                "source_url": record["source_url"],
                "resolution_state": "held_era_scope",
                "era_label": record.get("era_label"),
                "source_context": record["source_context"],
            })
            continue
        date = str(record["performance_date"])
        candidates = shows_by_date.get(date, [])
        entries.append({
            "source": "charlie-miller-reddit",
            "signal_type": str(record["selection_type"]),
            "source_handle": record["source_handle"],
            "source_url": record["source_url"],
            "show_date": date,
            "candidate_show_ids": [show["show_id"] for show in candidates],
            "resolution_state": "resolved_unique_show" if len(candidates) == 1 else "held_ambiguous_show_date",
            "source_context": record["source_context"],
        })

    state_counts = Counter(entry["resolution_state"] for entry in entries)
    source_counts = Counter(entry["source"] for entry in entries)
    return {
        "schema_version": 1,
        "kind": "selection_evidence_review",
        "status": "staging_only",
        "purpose": (
            "Conservatively resolved source-attributed selection evidence. It is "
            "not runtime input or a best-version score; unresolved or access-limited "
            "signals remain held for review."
        ),
        "source_constraints": {
            "headyversion": "indexed excerpts only; direct origin access was blocked and terms were not verified",
            "rolling_stone_australia": "copyright-restricted metadata-only critic list",
            "deadnet_store": "official metadata candidate; store host needs registry/adapter review before promotion",
            "charlie_miller_threads": "user-provided screenshot; project owner identifies the account as Charlie Miller",
            "charlie_miller_reddit": "self-identified account replies; retain as individual-curator selections, not a consensus signal",
        },
        "summary": {"entry_count": len(entries), "by_source": dict(sorted(source_counts.items())), "by_resolution_state": dict(sorted(state_counts.items()))},
        "entries": entries,
    }


def main() -> None:
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(document(), indent=2) + "\n", encoding="utf-8")
    print(f"wrote selection evidence review to {OUTPUT}")


if __name__ == "__main__":
    main()
