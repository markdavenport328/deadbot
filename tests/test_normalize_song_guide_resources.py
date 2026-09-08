"""Tests for the song-guide normalizer's mapping rules and idempotency.

Every test builds its own tiny canonical set and raw index in ``tmp_path``;
nothing reads the repository's data files and nothing touches the network.
"""

from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1] / "scripts" / "normalize"))
import normalize_song_guide_resources as nsg  # noqa: E402


SONGS = [
    ("song-candyman", "Candyman", "candyman"),
    ("song-attics-of-my-life", "Attics Of My Life", "attics-of-my-life"),
    ("song-box-of-rain", "Box Of Rain", "box-of-rain"),
    ("song-he-s-gone", "He's Gone", "he-s-gone"),
    ("song-slipknot", "Slipknot!", "slipknot"),
    ("song-help-on-the-way", "Help On The Way", "help-on-the-way"),
    ("song-they-love-each-other", "They Love Each Other", "they-love-each-other"),
    ("song-goin-down-the-road-feelin-bad", "Goin' Down The Road Feelin' Bad", "goin-down-the-road-feelin-bad"),
    ("song-the-eleven", "The Eleven", "the-eleven"),
    ("song-eleven", "Eleven", "eleven"),
]
SHOWS = [
    ("gd-1982-07-27", "1982-07-27"),
    ("gd-1969-02-27-early", "1969-02-27"),
    ("gd-1969-02-27-late", "1969-02-27"),
]

RESOURCE_FIELDS = ["resource_id", "resource_type", "title", "creator", "source_name", "source_url", "published_date", "notes"]
EXISTING_RESOURCE = {
    "resource_id": "resource-deadnet-song-candyman",
    "resource_type": "lyrics-and-credits",
    "title": "Candyman | Grateful Dead",
    "creator": "",
    "source_name": "Grateful Dead / Dead.net",
    "source_url": "https://www.dead.net/song/candyman",
    "published_date": "",
    "notes": "Official song page.",
}


def _write_csv(path: Path, fieldnames: list[str], rows: list[dict[str, str]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def canonical(tmp_path: Path) -> Path:
    directory = tmp_path / "canonical"
    directory.mkdir(exist_ok=True)
    _write_csv(
        directory / "songs.csv",
        ["song_id", "title", "slug", "original_artist", "first_known_dead_performance", "last_known_dead_performance", "notes"],
        [
            {"song_id": song_id, "title": title, "slug": slug, "original_artist": "", "first_known_dead_performance": "", "last_known_dead_performance": "", "notes": ""}
            for song_id, title, slug in SONGS
        ],
    )
    _write_csv(
        directory / "shows.csv",
        ["show_id", "show_date", "venue_id", "tour_name", "event_name", "notes", "source_key", "source_record_id"],
        [
            {"show_id": show_id, "show_date": date, "venue_id": "venue-x", "tour_name": "", "event_name": "", "notes": "", "source_key": "gdshowsdb", "source_record_id": show_id}
            for show_id, date in SHOWS
        ],
    )
    _write_csv(directory / "resources.csv", RESOURCE_FIELDS, [EXISTING_RESOURCE])
    _write_csv(
        directory / "resource_songs.csv",
        ["resource_id", "song_id", "relationship_type", "notes"],
        [{"resource_id": "resource-deadnet-song-candyman", "song_id": "song-candyman", "relationship_type": "lyrics-source", "notes": "Existing row."}],
    )
    _write_csv(directory / "resource_shows.csv", ["resource_id", "show_id", "relationship_type", "notes"], [])
    return directory


def deadnet_raw(tmp_path: Path, essays: list[dict], song_pages: list[dict] | None = None) -> Path:
    directory = tmp_path / "raw"
    directory.mkdir(exist_ok=True)
    lines: list[dict] = [
        {
            "source": "deadnet-editorial",
            "source_record_id": "deadnet-greatest-stories:www.dead.net",
            "retrieved_at": "2026-09-08T00:00:00Z",
            "source_url": "https://www.dead.net/features/greatest-stories-ever-told",
            "raw_payload": {"record_type": "pass_metadata", "status": "ok", "host": "www.dead.net", "source_name": "Grateful Dead / Dead.net", "essay_count": len(essays)},
        }
    ]
    for essay in essays:
        slug = essay["slug"]
        lines.append(
            {
                "source": "deadnet-editorial",
                "source_record_id": f"greatest-stories-ever-told-{slug}",
                "retrieved_at": "2026-09-08T00:00:00Z",
                "source_url": f"https://www.dead.net/features/greatest-stories-ever-told/greatest-stories-ever-told-{slug}",
                "raw_payload": {
                    "record_type": "essay",
                    "host": "www.dead.net",
                    "resource_type": "song-history-essay",
                    "source_name": "Grateful Dead / Dead.net",
                    "url_slug": slug,
                    "title": essay.get("title", f'Greatest Stories Ever Told - "{slug}"'),
                    "description": essay.get("description", "Official Site Of The Grateful Dead"),
                    "byline": essay.get("byline", "David Dodd"),
                    "published_date": essay.get("published_date", "2013-12-12"),
                    "http_status": 200,
                    "discovered_via": "series index",
                },
            }
        )
    for page in song_pages or []:
        lines.append(
            {
                "source": "deadnet-editorial",
                "source_record_id": f"song/{page['slug']}",
                "retrieved_at": "2026-09-08T00:00:00Z",
                "source_url": f"https://www.dead.net/song/{page['slug']}",
                "raw_payload": {
                    "record_type": "song_page",
                    "host": "www.dead.net",
                    "resource_type": "catalog-song-page",
                    "source_name": "Grateful Dead / Dead.net",
                    "url_slug": page["slug"],
                    "song_id": page["song_id"],
                    "title": page.get("title", "Song | Grateful Dead"),
                    "description": page.get("description", ""),
                    "byline": "",
                    "published_date": "",
                    "http_status": 200,
                    "discovered_via": "target slug",
                },
            }
        )
    path = directory / "deadnet-greatest-stories.jsonl"
    path.write_text("\n".join(json.dumps(line) for line in lines) + "\n", encoding="utf-8")
    return directory


def deadheadhigh_raw(tmp_path: Path, pages: list[dict]) -> Path:
    directory = tmp_path / "raw"
    directory.mkdir(exist_ok=True)
    lines: list[dict] = [
        {
            "source": "deadheadhigh",
            "source_record_id": "deadheadhigh-index:deadheadhigh.com",
            "retrieved_at": "2026-09-08T00:00:00Z",
            "source_url": "https://deadheadhigh.com/sitemap.xml",
            "raw_payload": {"record_type": "pass_metadata", "status": "ok", "host": "deadheadhigh.com", "source_name": "Deadhead High", "page_count": len(pages)},
        }
    ]
    for page in pages:
        path_value = page["path"]
        lines.append(
            {
                "source": "deadheadhigh",
                "source_record_id": path_value.strip("/"),
                "retrieved_at": "2026-09-08T00:00:00Z",
                "source_url": f"https://deadheadhigh.com{path_value}",
                "raw_payload": {
                    "record_type": "page",
                    "host": "deadheadhigh.com",
                    "source_name": "Deadhead High",
                    "resource_type": page.get("resource_type", "listening-guide" if path_value.startswith("/songs/") else "listener-guide"),
                    "url_slug": path_value.strip("/").split("/")[-1],
                    "url_path": path_value,
                    "section": path_value.strip("/").split("/")[0],
                    "title": page.get("title", "A page | Deadhead High"),
                    "description": page.get("description", ""),
                    "byline": "",
                    "published_date": "",
                    "http_status": 200,
                    "kept_because": page.get("kept_because", "song page"),
                },
            }
        )
    path = directory / "deadheadhigh-index.jsonl"
    path.write_text("\n".join(json.dumps(line) for line in lines) + "\n", encoding="utf-8")
    return directory


def run(tmp_path: Path, raw_dir: Path, canonical_dir: Path, out_name: str = "out") -> tuple[dict, Path]:
    out_dir = tmp_path / out_name
    held_dir = tmp_path / "held"
    summary = nsg.normalize(raw_dir, canonical_dir, out_dir, held_dir)
    return summary, out_dir


def rows(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def held(tmp_path: Path, source: str) -> list[dict]:
    path = tmp_path / "held" / f"lore-mapping-held-{source}.jsonl"
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


# --- the match key -----------------------------------------------------------


def test_the_match_key_reads_apostrophes_stopwords_and_punctuation_alike():
    assert nsg.match_key("He's Gone") == nsg.match_key("hes-gone") == ("hes", "gone")
    assert nsg.match_key("Attics Of My Life") == nsg.match_key("attics-my-life") == ("attics", "my", "life")
    assert nsg.match_key("Slipknot!") == nsg.match_key("slipknot") == ("slipknot",)
    assert nsg.match_key("Goin' Down The Road Feelin' Bad") == nsg.match_key("goin-down-road-feeling-bad")
    assert nsg.match_key("They Love Each Other") == nsg.match_key("love-each-other")
    assert nsg.match_key("It's All Over Now, Baby Blue") == nsg.match_key("it-s-all-over-now-baby-blue")


# --- Dead.net essays ---------------------------------------------------------


def test_an_essay_becomes_a_resource_mapped_to_its_song(tmp_path):
    raw = deadnet_raw(tmp_path, [{"slug": "attics-my-life", "title": 'Greatest Stories Ever Told - "Attics of My Life"'}])
    canonical_dir = canonical(tmp_path)
    summary, out_dir = run(tmp_path, raw, canonical_dir)
    resource = [row for row in rows(out_dir / "resources.csv") if row["resource_id"] == "resource-deadnet-gset-attics-my-life"]
    assert len(resource) == 1
    assert resource[0]["resource_type"] == "song-history-essay"
    assert resource[0]["creator"] == "David Dodd"
    assert resource[0]["source_name"] == "Grateful Dead / Dead.net"
    assert resource[0]["source_url"] == "https://www.dead.net/features/greatest-stories-ever-told/greatest-stories-ever-told-attics-my-life"
    assert resource[0]["published_date"] == "2013-12-12"
    link = [row for row in rows(out_dir / "resource_songs.csv") if row["resource_id"] == "resource-deadnet-gset-attics-my-life"]
    assert link == [{"resource_id": "resource-deadnet-gset-attics-my-life", "song_id": "song-attics-of-my-life", "relationship_type": "about", "notes": link[0]["notes"]}]
    assert "slug" in link[0]["notes"].casefold()
    assert summary["by_source"]["deadnet"]["songs_mapped"] == 1


def test_a_slug_matching_two_songs_is_held_and_the_resource_is_still_written(tmp_path):
    raw = deadnet_raw(tmp_path, [{"slug": "eleven", "title": 'Greatest Stories Ever Told - "The Eleven"'}])
    canonical_dir = canonical(tmp_path)
    summary, out_dir = run(tmp_path, raw, canonical_dir)
    assert any(row["resource_id"] == "resource-deadnet-gset-eleven" for row in rows(out_dir / "resources.csv"))
    assert not any(row["resource_id"] == "resource-deadnet-gset-eleven" for row in rows(out_dir / "resource_songs.csv"))
    entries = held(tmp_path, "deadnet")
    assert len(entries) == 1
    assert entries[0]["resource_id"] == "resource-deadnet-gset-eleven"
    assert sorted(entries[0]["candidates"]) == ["song-eleven", "song-the-eleven"]
    assert "more than one" in entries[0]["reason"]
    assert summary["by_source"]["deadnet"]["held"] == 1


def test_an_unmatched_slug_is_held_with_candidates(tmp_path):
    raw = deadnet_raw(tmp_path, [{"slug": "the-wheel-of-fortune", "title": 'Greatest Stories Ever Told - "The Wheel of Fortune"'}])
    canonical_dir = canonical(tmp_path)
    summary, out_dir = run(tmp_path, raw, canonical_dir)
    entries = held(tmp_path, "deadnet")
    assert len(entries) == 1
    assert "no canonical song" in entries[0]["reason"].casefold()
    assert any(row["resource_id"] == "resource-deadnet-gset-the-wheel-of-fortune" for row in rows(out_dir / "resources.csv"))
    assert summary["by_source"]["deadnet"]["held"] == 1


def test_a_song_page_whose_url_is_already_cataloged_is_left_alone(tmp_path):
    raw = deadnet_raw(
        tmp_path,
        [],
        song_pages=[{"slug": "candyman", "song_id": "song-candyman"}, {"slug": "box-of-rain", "song_id": "song-box-of-rain"}],
    )
    canonical_dir = canonical(tmp_path)
    summary, out_dir = run(tmp_path, raw, canonical_dir)
    ids = [row["resource_id"] for row in rows(out_dir / "resources.csv")]
    assert ids.count("resource-deadnet-song-candyman") == 1
    assert "resource-deadnet-song-box-of-rain" in ids
    assert summary["by_source"]["deadnet"]["urls_already_cataloged"] == 1
    # The existing row keeps its own type, creator and notes.
    existing = [row for row in rows(out_dir / "resources.csv") if row["resource_id"] == "resource-deadnet-song-candyman"][0]
    assert existing == EXISTING_RESOURCE


def test_the_drupal_path_counter_is_not_part_of_the_song_name(tmp_path):
    raw = deadnet_raw(tmp_path, [{"slug": "box-rain-0", "title": 'Greatest Stories Ever Told - "Box Of Rain"'}])
    canonical_dir = canonical(tmp_path)
    summary, out_dir = run(tmp_path, raw, canonical_dir)
    link = [row for row in rows(out_dir / "resource_songs.csv") if row["resource_id"] == "resource-deadnet-gset-box-rain-0"]
    assert link[0]["song_id"] == "song-box-of-rain"
    assert held(tmp_path, "deadnet") == []


def test_a_paired_essay_maps_to_both_songs_it_names(tmp_path):
    raw = deadnet_raw(tmp_path, [{"slug": "help-wayslipknot", "title": 'Greatest Stories Ever Told - "Help on the Way"/"Slipknot"'}])
    canonical_dir = canonical(tmp_path)
    summary, out_dir = run(tmp_path, raw, canonical_dir)
    links = sorted(row["song_id"] for row in rows(out_dir / "resource_songs.csv") if row["resource_id"] == "resource-deadnet-gset-help-wayslipknot")
    assert links == ["song-help-on-the-way", "song-slipknot"]
    assert "title" in [row for row in rows(out_dir / "resource_songs.csv") if row["resource_id"] == "resource-deadnet-gset-help-wayslipknot"][0]["notes"].casefold()
    assert held(tmp_path, "deadnet") == []
    assert summary["by_source"]["deadnet"]["songs_mapped"] == 2


def test_a_target_whose_page_was_already_cataloged_says_so(tmp_path):
    raw = deadnet_raw(tmp_path, [], song_pages=[{"slug": "candyman", "song_id": "song-candyman"}])
    canonical_dir = canonical(tmp_path)
    targets = {"songs": [{"song_id": "song-candyman", "title": "Candyman", "slug": "candyman"}]}
    summary = nsg.normalize(raw, canonical_dir, tmp_path / "out", tmp_path / "held", targets)
    assert summary["targets"]["song-candyman"]["deadnet-song_page"] == "already cataloged"


# --- Deadhead High -----------------------------------------------------------


def test_a_deadhead_high_song_page_maps_by_slug(tmp_path):
    raw = deadheadhigh_raw(tmp_path, [{"path": "/songs/box-of-rain", "title": "Grateful Dead Box of Rain live versions | Deadhead High", "description": "Explore 156 performances."}])
    canonical_dir = canonical(tmp_path)
    summary, out_dir = run(tmp_path, raw, canonical_dir)
    resource = [row for row in rows(out_dir / "resources.csv") if row["resource_id"] == "resource-deadheadhigh-songs-box-of-rain"][0]
    assert resource["resource_type"] == "listening-guide"
    assert resource["source_name"] == "Deadhead High"
    assert resource["creator"] == ""
    assert "Explore 156 performances." in resource["notes"]
    link = [row for row in rows(out_dir / "resource_songs.csv") if row["resource_id"] == "resource-deadheadhigh-songs-box-of-rain"]
    assert link[0]["song_id"] == "song-box-of-rain"
    assert link[0]["relationship_type"] == "about"
    assert summary["by_source"]["deadheadhigh"]["songs_mapped"] == 1


def test_a_deadhead_high_show_page_maps_to_the_one_show_on_that_date(tmp_path):
    raw = deadheadhigh_raw(tmp_path, [{"path": "/shows/1982-07-27", "title": "Grateful Dead 7/27/82 | Deadhead High", "kept_because": "target show date"}])
    canonical_dir = canonical(tmp_path)
    summary, out_dir = run(tmp_path, raw, canonical_dir)
    resource = [row for row in rows(out_dir / "resources.csv") if row["resource_id"] == "resource-deadheadhigh-shows-1982-07-27"][0]
    assert resource["resource_type"] == "listener-guide"
    link = [row for row in rows(out_dir / "resource_shows.csv") if row["resource_id"] == "resource-deadheadhigh-shows-1982-07-27"]
    assert link[0]["show_id"] == "gd-1982-07-27"
    assert link[0]["relationship_type"] == "about"
    assert summary["by_source"]["deadheadhigh"]["shows_mapped"] == 1
    assert held(tmp_path, "deadheadhigh") == []


def test_a_date_carrying_two_shows_is_held(tmp_path):
    raw = deadheadhigh_raw(tmp_path, [{"path": "/shows/1969-02-27", "title": "Grateful Dead 2/27/69 | Deadhead High"}])
    canonical_dir = canonical(tmp_path)
    summary, out_dir = run(tmp_path, raw, canonical_dir)
    entries = held(tmp_path, "deadheadhigh")
    assert len(entries) == 1
    assert sorted(entries[0]["candidates"]) == ["gd-1969-02-27-early", "gd-1969-02-27-late"]
    assert not rows(out_dir / "resource_shows.csv")
    assert summary["by_source"]["deadheadhigh"]["held"] == 1


def test_a_guide_page_with_no_song_or_date_is_unmapped_not_held(tmp_path):
    raw = deadheadhigh_raw(tmp_path, [{"path": "/guides/how-to-get-into-the-grateful-dead", "title": "How to get into the Grateful Dead", "kept_because": "guide"}])
    canonical_dir = canonical(tmp_path)
    summary, out_dir = run(tmp_path, raw, canonical_dir)
    assert any(row["resource_id"] == "resource-deadheadhigh-guides-how-to-get-into-the-grateful-dead" for row in rows(out_dir / "resources.csv"))
    assert held(tmp_path, "deadheadhigh") == []
    assert summary["by_source"]["deadheadhigh"]["unmapped"] == 1


# --- idempotency and existing rows ------------------------------------------


def test_a_rerun_reproduces_byte_identical_files(tmp_path):
    raw = deadnet_raw(tmp_path, [{"slug": "candyman"}, {"slug": "box-rain"}], song_pages=[{"slug": "box-of-rain", "song_id": "song-box-of-rain"}])
    canonical_dir = canonical(tmp_path)
    _, first = run(tmp_path, raw, canonical_dir, out_name="first")
    _, second = run(tmp_path, raw, canonical_dir, out_name="second")
    for name in ("resources.csv", "resource_songs.csv", "resource_shows.csv"):
        assert (first / name).read_bytes() == (second / name).read_bytes()
    # And normalizing in place a second time adds nothing.
    for name in ("songs.csv", "shows.csv"):
        (first / name).write_bytes((canonical_dir / name).read_bytes())
    nsg.normalize(raw, first, first, tmp_path / "held")
    assert (first / "resources.csv").read_bytes() == (second / "resources.csv").read_bytes()


def test_existing_rows_are_preserved_exactly(tmp_path):
    raw = deadnet_raw(tmp_path, [{"slug": "candyman"}])
    canonical_dir = canonical(tmp_path)
    before = (canonical_dir / "resources.csv").read_bytes()
    _, out_dir = run(tmp_path, raw, canonical_dir)
    assert (canonical_dir / "resources.csv").read_bytes() == before
    assert (out_dir / "resources.csv").read_bytes().startswith(before)
    assert rows(out_dir / "resource_songs.csv")[0] == {
        "resource_id": "resource-deadnet-song-candyman",
        "song_id": "song-candyman",
        "relationship_type": "lyrics-source",
        "notes": "Existing row.",
    }


def test_both_raw_files_are_read_in_one_pass(tmp_path):
    raw = deadnet_raw(tmp_path, [{"slug": "candyman"}])
    deadheadhigh_raw(tmp_path, [{"path": "/songs/he-s-gone", "title": "He's Gone | Deadhead High"}])
    canonical_dir = canonical(tmp_path)
    summary, out_dir = run(tmp_path, raw, canonical_dir)
    assert set(summary["by_source"]) == {"deadnet", "deadheadhigh"}
    ids = {row["resource_id"] for row in rows(out_dir / "resources.csv")}
    assert {"resource-deadnet-gset-candyman", "resource-deadheadhigh-songs-he-s-gone"} <= ids
    songs = {row["song_id"] for row in rows(out_dir / "resource_songs.csv")}
    assert {"song-candyman", "song-he-s-gone"} <= songs


def test_an_incomplete_raw_pass_is_skipped(tmp_path):
    raw = deadnet_raw(tmp_path, [{"slug": "candyman"}])
    path = raw / "deadnet-greatest-stories.jsonl"
    lines = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
    lines[0]["raw_payload"]["status"] = "aborted"
    path.write_text("\n".join(json.dumps(line) for line in lines) + "\n", encoding="utf-8")
    canonical_dir = canonical(tmp_path)
    summary, out_dir = run(tmp_path, raw, canonical_dir)
    assert "deadnet" not in summary["by_source"]
    assert not any(row["resource_id"].startswith("resource-deadnet-gset-") for row in rows(out_dir / "resources.csv"))
