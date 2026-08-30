#!/usr/bin/env python3
"""Build the canonical cross-decade song review queue.

This is deliberately a derived artifact: it reads only data/canonical CSVs and
does not assign popularity or interestingness.  Re-running it replaces the
queue with the same deterministic, stratified selection for the current
canonical snapshot.
"""
from __future__ import annotations

import csv
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CANONICAL = ROOT / "data" / "canonical"
OUTPUT = ROOT / "data" / "editorial" / "song-cohort-candidates.csv"


def rows(name: str) -> list[dict[str, str]]:
    with (CANONICAL / name).open(newline="", encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def risk(perf_count: int, linked_count: int, resource_count: int, writer_count: int) -> str:
    ratio = linked_count / perf_count if perf_count else 0.0
    if ratio < 0.25 or (resource_count == 0 and writer_count == 0):
        return "high"
    if ratio < 0.60 or resource_count == 0 or writer_count == 0:
        return "medium"
    return "low"


def make_candidates() -> list[dict[str, object]]:
    songs = rows("songs.csv")
    performances = rows("performances.csv")
    performance_by_id = {r["performance_id"]: r for r in performances}
    by_song: dict[str, list[dict[str, str]]] = defaultdict(list)
    for p in performances:
        by_song[p["song_id"]].append(p)

    linked_performances: dict[str, set[str]] = defaultdict(set)
    linked_recordings: dict[str, set[str]] = defaultdict(set)
    for link in rows("performance_recordings.csv"):
        performance = performance_by_id.get(link["performance_id"])
        if performance:
            linked_performances[performance["song_id"]].add(link["performance_id"])
            linked_recordings[performance["song_id"]].add(link["recording_id"])

    resource_ids: dict[str, set[str]] = defaultdict(set)
    for link in rows("resource_songs.csv"):
        resource_ids[link["song_id"]].add(link["resource_id"])
    writer_ids: dict[str, set[str]] = defaultdict(set)
    for link in rows("song_writers.csv"):
        writer_ids[link["song_id"]].add(link["person_id"])

    all_candidates = []
    for song in songs:
        ps = by_song.get(song["song_id"], [])
        years = sorted(int(p["show_id"].split("-")[1]) for p in ps if "-" in p["show_id"])
        if not years:
            continue
        first, last = years[0], years[-1]
        span = last - first
        decades = len({year // 10 for year in years})
        if span < 10 or decades < 2:
            continue
        perf_count = len(ps)
        linked_count = len(linked_performances[song["song_id"]])
        resource_count = len(resource_ids[song["song_id"]])
        writer_count = len(writer_ids[song["song_id"]])
        ratio = linked_count / perf_count
        debut_era = f"{(first // 5) * 5}-{(first // 5) * 5 + 4}"
        span_band = "10-14" if span < 15 else "15-19" if span < 20 else "20+"
        all_candidates.append({
            "song_id": song["song_id"], "title": song["title"],
            "debut_era": debut_era, "span_band": span_band,
            "first_year": first, "last_year": last, "span_years": span,
            "performance_count": perf_count,
            "distinct_recording_count": len(linked_recordings[song["song_id"]]),
            "recording_linked_performance_count": linked_count,
            "recording_linked_performance_ratio": f"{ratio:.4f}",
            "resource_count": resource_count, "writer_count": writer_count,
            "coverage_risk": risk(perf_count, linked_count, resource_count, writer_count),
        })

    # Quotas intentionally preserve debut eras and include a long-tail share.
    era_quota = {"1965-1969": 24, "1970-1974": 28, "1975-1979": 10,
                 "1980-1984": 8, "1985-1989": 2, "1990-1994": 0}
    selected = []
    for era, quota in era_quota.items():
        pool = [c for c in all_candidates if c["debut_era"] == era]
        # Coverage breadth is a selection key, not a quality/popularity score.
        # The final song_id tie-break makes the output reproducible.
        breadth_key = lambda c: (-int(c["span_years"]), -int(c["resource_count"]),
                                 -int(c["writer_count"]), c["song_id"])
        pool.sort(key=breadth_key)
        # Keep roughly one-fifth for low-frequency/long-tail review, rather
        # than letting the broadest, best-linked songs crowd out rarer ones.
        tail_count = min(max(1, round(quota * 0.2)), quota, len(pool))
        tail = sorted(pool, key=lambda c: (int(c["performance_count"]),
                                           -int(c["span_years"]), c["song_id"]))[:tail_count]
        tail_ids = {c["song_id"] for c in tail}
        breadth = [c for c in pool if c["song_id"] not in tail_ids]
        selected.extend(tail + breadth[: quota - len(tail)])
    selected.sort(key=lambda c: (str(c["debut_era"]), str(c["span_band"]), str(c["song_id"])))
    for i, c in enumerate(selected, 1):
        c["queue_position"] = i
    return selected


def main() -> None:
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    candidates = make_candidates()
    fields = ["queue_position", "song_id", "title", "debut_era", "span_band",
              "first_year", "last_year", "span_years", "performance_count",
              "distinct_recording_count", "recording_linked_performance_count",
              "recording_linked_performance_ratio", "resource_count", "writer_count",
              "coverage_risk"]
    with OUTPUT.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(candidates)
    print(f"wrote {len(candidates)} candidates to {OUTPUT}")


if __name__ == "__main__":
    main()
