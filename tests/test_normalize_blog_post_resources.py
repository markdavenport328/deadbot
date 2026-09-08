"""Tests for the blog-post-index normalizer's mapping rules and idempotency.

Every test builds its own tiny canonical set and raw feed index in ``tmp_path``;
nothing reads the repository's data files and nothing touches the network.
"""

from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1] / "scripts" / "normalize"))
import normalize_blog_post_resources as nbp  # noqa: E402


SONGS = [
    ("song-dark-star", "Dark Star"),
    ("song-me-and-my-uncle", "Me And My Uncle"),
    ("song-china-cat-sunflower", "China Cat Sunflower"),
    ("song-i-know-you-rider", "I Know You Rider"),
    ("song-truckin", "Truckin'"),
    ("song-deal", "Deal"),
    ("song-playing-in-the-band", "Playing In The Band"),
    ("song-playing-in-the-band-reprise", "Playing In The Band Reprise"),
    ("song-not-fade-away", "Not Fade Away"),
    ("song-goin-down-the-road-feeling-bad", "Goin' Down The Road Feeling Bad"),
    ("song-morning-dew", "Morning Dew"),
    ("song-it-s-all-over-now", "It's All Over Now"),
    ("song-it-s-all-over-now-baby-blue", "It's All Over Now Baby Blue"),
    ("song-new-orleans", "New Orleans"),
]
SHOWS = [
    ("gd-1972-08-27", "1972-08-27"),
    ("gd-1970-02-13", "1970-02-13"),
    ("gd-1977-05-08", "1977-05-08"),
    ("gd-1969-02-27-early", "1969-02-27"),
    ("gd-1969-02-27-late", "1969-02-27"),
    ("gd-1969-09-26", "1969-09-26"),
    ("gd-1969-09-27", "1969-09-27"),
]

RESOURCE_FIELDS = ["resource_id", "resource_type", "title", "creator", "source_name", "source_url", "published_date", "notes"]
EXISTING_RESOURCE = {
    "resource_id": "resource-deadnet-tiger-rose-50",
    "resource_type": "article",
    "title": "Tiger Rose 50",
    "creator": "Jesse Jarnow",
    "source_name": "Grateful Dead / Dead.net",
    "source_url": "https://www.dead.net/tiger-rose-50",
    "published_date": "",
    "notes": "Official editorial feature.",
}


def _write_csv(path: Path, fieldnames: list[str], rows: list[dict[str, str]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def canonical(tmp_path: Path) -> Path:
    directory = tmp_path / "canonical"
    directory.mkdir()
    _write_csv(
        directory / "songs.csv",
        ["song_id", "title", "slug", "original_artist", "first_known_dead_performance", "last_known_dead_performance", "notes"],
        [
            {"song_id": song_id, "title": title, "slug": song_id.removeprefix("song-"), "original_artist": "", "first_known_dead_performance": "", "last_known_dead_performance": "", "notes": ""}
            for song_id, title in SONGS
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
        [{"resource_id": "resource-deadnet-tiger-rose-50", "song_id": "song-dark-star", "relationship_type": "song-origin", "notes": "Existing row."}],
    )
    _write_csv(
        directory / "resource_shows.csv",
        ["resource_id", "show_id", "relationship_type", "notes"],
        [{"resource_id": "resource-deadnet-tiger-rose-50", "show_id": "gd-1972-08-27", "relationship_type": "show-oral-history", "notes": "Existing row."}],
    )
    return directory


def raw_index(
    tmp_path: Path,
    posts: list[dict],
    *,
    host: str = "lostlivedead.blogspot.com",
    site_id: str = "lost-live-dead",
    site_name: str = "Lost Live Dead",
    resource_type: str = "show-history-post",
    slug: str = "lostlivedead",
) -> Path:
    directory = tmp_path / "raw"
    directory.mkdir(exist_ok=True)
    lines = [
        {
            "source": site_id,
            "source_record_id": f"blog-post-index:{host}",
            "retrieved_at": "2026-09-08T00:00:00Z",
            "source_url": f"https://{host}/feeds/posts/summary",
            "raw_payload": {
                "record_type": "pass_metadata",
                "host": host,
                "site_name": site_name,
                "resource_type": resource_type,
                "page_count": 1,
                "entry_count": len(posts),
                "post_count": len(posts),
                "status": "ok",
            },
        }
    ]
    for index, post in enumerate(posts):
        post_slug = post.get("slug", f"post-{index}")
        lines.append(
            {
                "source": site_id,
                "source_record_id": f"tag:blogger.com,1999:blog-1.post-{index}",
                "retrieved_at": "2026-09-08T00:00:00Z",
                "source_url": post.get("url", f"https://{host}/2012/08/{post_slug}.html"),
                "raw_payload": {
                    "record_type": "post",
                    "host": host,
                    "site_name": site_name,
                    "resource_type": resource_type,
                    "title": post["title"],
                    "published": post.get("published", "2012-08-27T09:00:00.000-07:00"),
                    "updated": post.get("updated", "2012-08-28T09:00:00.000-07:00"),
                    "labels": post.get("labels", []),
                    "author": post.get("author", "Corry342"),
                    "request_url": f"https://{host}/feeds/posts/summary?alt=json&max-results=150&start-index=1",
                    "http_status": 200,
                },
            }
        )
    path = directory / f"blog-post-index-{slug}.jsonl"
    with path.open("w", encoding="utf-8") as handle:
        for line in lines:
            handle.write(json.dumps(line, ensure_ascii=False, separators=(",", ":")) + "\n")
    return path


def run(tmp_path: Path, posts: list[dict], **kwargs) -> dict:
    directory = canonical(tmp_path)
    raw_index(tmp_path, posts, **kwargs)
    return nbp.normalize(tmp_path / "raw", directory, tmp_path / "held.jsonl")


def rows(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def held(tmp_path: Path) -> list[dict]:
    text = (tmp_path / "held.jsonl").read_text(encoding="utf-8")
    return [json.loads(line) for line in text.splitlines() if line]


# ---------------------------------------------------------------------------
# Show dates
# ---------------------------------------------------------------------------


def test_each_supported_date_format_maps_its_show(tmp_path):
    summary = run(
        tmp_path,
        [
            {"title": "1972-08-27: Veneta, Oregon", "slug": "iso"},
            {"title": "The Dead at the Fillmore East 2/13/70", "slug": "short-year"},
            {"title": "Cornell 5/8/1977 reconsidered", "slug": "long-year"},
            {"title": "August 27, 1972 Old Renaissance Faire Grounds", "slug": "long-month"},
            {"title": "Feb. 13, 1970 Fillmore East", "slug": "abbreviated-month"},
        ],
    )

    mapped = {row["resource_id"]: row for row in rows(tmp_path / "canonical" / "resource_shows.csv")}
    assert mapped["resource-lostlivedead-2012-08-iso"]["show_id"] == "gd-1972-08-27"
    assert mapped["resource-lostlivedead-2012-08-short-year"]["show_id"] == "gd-1970-02-13"
    assert mapped["resource-lostlivedead-2012-08-long-year"]["show_id"] == "gd-1977-05-08"
    assert mapped["resource-lostlivedead-2012-08-long-month"]["show_id"] == "gd-1972-08-27"
    assert mapped["resource-lostlivedead-2012-08-abbreviated-month"]["show_id"] == "gd-1970-02-13"
    assert mapped["resource-lostlivedead-2012-08-iso"]["relationship_type"] == "about"
    assert mapped["resource-lostlivedead-2012-08-iso"]["notes"] == "Title names the show date."
    assert summary["shows_mapped"] == 3
    assert summary["show_rows_written"] == 5


def test_a_date_only_in_the_labels_maps_and_says_so(tmp_path):
    run(tmp_path, [{"title": "New Year's Eve at Winterland", "labels": ["1977", "1977-05-08"], "slug": "labelled"}])

    row = rows(tmp_path / "canonical" / "resource_shows.csv")[-1]
    assert row["resource_id"] == "resource-lostlivedead-2012-08-labelled"
    assert row["show_id"] == "gd-1977-05-08"
    assert row["notes"] == "A post label names the show date."


def test_a_title_date_wins_over_a_different_label_date(tmp_path):
    run(tmp_path, [{"title": "August 27, 1972 in Veneta", "labels": ["1977-05-08"], "slug": "both"}])

    row = rows(tmp_path / "canonical" / "resource_shows.csv")[-1]
    assert row["show_id"] == "gd-1972-08-27"


def test_a_date_matching_two_shows_is_held_not_guessed(tmp_path):
    summary = run(tmp_path, [{"title": "February 27, 1969 Fillmore West", "slug": "two-shows"}])

    assert rows(tmp_path / "canonical" / "resource_shows.csv") == [
        {"resource_id": "resource-deadnet-tiger-rose-50", "show_id": "gd-1972-08-27", "relationship_type": "show-oral-history", "notes": "Existing row."}
    ]
    entry = held(tmp_path)[0]
    assert entry["resource_id"] == "resource-lostlivedead-2012-08-two-shows"
    assert entry["url"].endswith("two-shows.html")
    assert entry["title"] == "February 27, 1969 Fillmore West"
    assert entry["reason"] == "1969-02-27 matches more than one canonical show."
    assert entry["candidates"] == ["gd-1969-02-27-early", "gd-1969-02-27-late"]
    assert summary["held"] == 1


def test_two_dates_in_a_title_are_held_with_both_candidates(tmp_path):
    run(tmp_path, [{"title": "September 26-27, 1969 Fillmore East", "slug": "range"}])

    entry = held(tmp_path)[0]
    assert entry["reason"] == "The title names more than one date."
    assert entry["candidates"] == ["1969-09-26 (gd-1969-09-26)", "1969-09-27 (gd-1969-09-27)"]


def test_several_dates_that_match_no_canonical_show_stay_unmapped(tmp_path):
    summary = run(tmp_path, [{"title": "April 1-2, 1996 at the Fillmore", "slug": "no-show"}])

    assert held(tmp_path) == []
    assert summary["dates_without_a_canonical_show"] == 1
    assert summary["unmapped"] == 1


def test_a_date_with_no_canonical_show_still_stores_the_resource(tmp_path):
    summary = run(tmp_path, [{"title": "March 12, 1978 Yale University: Bob Weir Band", "slug": "weir"}])

    assert [row["resource_id"] for row in rows(tmp_path / "canonical" / "resources.csv")][-1] == "resource-lostlivedead-2012-08-weir"
    assert summary["dates_without_a_canonical_show"] == 1
    assert summary["show_rows_written"] == 0


def test_an_impossible_date_is_not_read_as_a_date(tmp_path):
    summary = run(tmp_path, [{"title": "The 13/45/72 nonsense and 2/30/70 too", "slug": "junk"}])

    assert summary["show_rows_written"] == 0
    assert summary["dates_without_a_canonical_show"] == 0


# ---------------------------------------------------------------------------
# Song titles
# ---------------------------------------------------------------------------


def test_a_multi_word_song_title_maps(tmp_path):
    summary = run(tmp_path, [{"title": "The road to China Cat Sunflower", "slug": "china-cat"}])

    row = rows(tmp_path / "canonical" / "resource_songs.csv")[-1]
    assert row == {
        "resource_id": "resource-lostlivedead-2012-08-china-cat",
        "song_id": "song-china-cat-sunflower",
        "relationship_type": "about",
        "notes": "Title names the song.",
    }
    assert summary["songs_mapped"] == 1


def test_song_matching_ignores_case_and_apostrophe_style(tmp_path):
    run(
        tmp_path,
        [
            {"title": "GOIN’ DOWN THE ROAD FEELING BAD, again", "slug": "curly"},
            {"title": "a few words on me & my uncle", "slug": "ampersand"},
        ],
    )

    mapped = {row["resource_id"]: row["song_id"] for row in rows(tmp_path / "canonical" / "resource_songs.csv")}
    assert mapped["resource-lostlivedead-2012-08-curly"] == "song-goin-down-the-road-feeling-bad"
    assert mapped["resource-lostlivedead-2012-08-ampersand"] == "song-me-and-my-uncle"


def test_a_song_title_inside_a_longer_word_does_not_match(tmp_path):
    summary = run(tmp_path, [{"title": "Morning Dewdrops, Dark Starlight and Dealerships", "slug": "inside"}])

    assert summary["song_rows_written"] == 0


def test_the_longer_of_two_overlapping_song_titles_wins(tmp_path):
    run(tmp_path, [{"title": "Playing In The Band Reprise as an idea", "slug": "reprise"}])

    mapped = [row["song_id"] for row in rows(tmp_path / "canonical" / "resource_songs.csv") if row["resource_id"].startswith("resource-lostlivedead")]
    assert mapped == ["song-playing-in-the-band-reprise"]


def test_a_short_song_title_alone_in_a_title_stays_unmapped(tmp_path):
    summary = run(tmp_path, [{"title": "Deal me in: the 1978 tour", "slug": "short"}])

    assert summary["song_rows_written"] == 0
    assert summary["unmapped"] == 1
    assert held(tmp_path) == []


def test_a_short_song_title_maps_when_a_label_names_it(tmp_path):
    run(tmp_path, [{"title": "Deal me in: the 1978 tour", "labels": ["1978", "Deal"], "slug": "short-labelled"}])

    row = rows(tmp_path / "canonical" / "resource_songs.csv")[-1]
    assert row["song_id"] == "song-deal"
    assert row["notes"] == "Title names the song and a post label names it too."


def test_a_short_song_title_maps_on_deadessays_when_the_title_starts_with_it(tmp_path):
    directory = canonical(tmp_path)
    raw_index(
        tmp_path,
        [{"title": "Truckin' 1970-74", "slug": "truckin"}, {"title": "A word about Truckin' in 1970", "slug": "mid-title"}],
        host="deadessays.blogspot.com",
        site_id="dead-essays",
        site_name="Grateful Dead Guide (Deadessays)",
        resource_type="editorial-blog-post",
        slug="deadessays",
    )

    nbp.normalize(tmp_path / "raw", directory, tmp_path / "held.jsonl")

    mapped = {row["resource_id"]: row for row in rows(directory / "resource_songs.csv")}
    assert mapped["resource-deadessays-2012-08-truckin"]["song_id"] == "song-truckin"
    assert mapped["resource-deadessays-2012-08-truckin"]["notes"] == "Title begins with the song title."
    assert "resource-deadessays-2012-08-mid-title" not in mapped


def test_a_comma_inside_a_song_title_still_matches_the_longer_song(tmp_path):
    run(tmp_path, [{"title": 'February 24, 1974: "It\'s All Over Now, Baby Blue" encore', "slug": "baby-blue"}])

    mapped = [row["song_id"] for row in rows(tmp_path / "canonical" / "resource_songs.csv") if row["resource_id"].startswith("resource-lostlivedead")]
    assert mapped == ["song-it-s-all-over-now-baby-blue"]


def test_a_song_named_after_a_city_is_not_mapped_by_a_city_label(tmp_path):
    # These blogs label a post with its venue's city, so the label is no
    # evidence that the post is about the song of the same name.
    summary = run(
        tmp_path,
        [
            {"title": "January 30, 1970: The Warehouse, New Orleans", "slug": "venue"},
            {"title": "June 30, 1972: Memorial Auditorium, New Orleans", "labels": ["1972", "New Orleans"], "slug": "labelled"},
        ],
    )

    assert summary["song_rows_written"] == 0


def test_a_city_named_song_maps_when_a_deadessays_title_starts_with_it(tmp_path):
    directory = canonical(tmp_path)
    raw_index(
        tmp_path,
        [{"title": "New Orleans 1970-1990", "slug": "no"}],
        host="deadessays.blogspot.com",
        site_id="dead-essays",
        site_name="Grateful Dead Guide (Deadessays)",
        resource_type="editorial-blog-post",
        slug="deadessays",
    )

    nbp.normalize(tmp_path / "raw", directory, tmp_path / "held.jsonl")

    assert rows(directory / "resource_songs.csv")[-1]["song_id"] == "song-new-orleans"


def test_a_label_that_merely_contains_a_short_song_title_does_not_support_it(tmp_path):
    summary = run(tmp_path, [{"title": "Deal me in: the 1978 tour", "labels": ["Top-31 Deal Segment"], "slug": "loose"}])

    assert summary["song_rows_written"] == 0


def test_more_than_three_song_matches_is_held(tmp_path):
    summary = run(
        tmp_path,
        [{"title": "Dark Star, China Cat Sunflower, I Know You Rider, Not Fade Away and Morning Dew", "slug": "many"}],
    )

    assert summary["song_rows_written"] == 0
    entry = held(tmp_path)[0]
    assert entry["reason"] == "The title names more than three songs."
    assert entry["candidates"] == [
        "song-china-cat-sunflower",
        "song-dark-star",
        "song-i-know-you-rider",
        "song-morning-dew",
        "song-not-fade-away",
    ]
    assert summary["held"] == 1


def test_three_song_matches_all_map(tmp_path):
    summary = run(tmp_path, [{"title": "Dark Star into China Cat Sunflower and I Know You Rider", "slug": "three"}])

    assert summary["song_rows_written"] == 3
    assert held(tmp_path) == []


def test_a_post_can_map_to_both_a_song_and_a_show(tmp_path):
    run(tmp_path, [{"title": "Dark Star, 1972-08-27", "slug": "both-kinds"}])

    assert [row["song_id"] for row in rows(tmp_path / "canonical" / "resource_songs.csv")][-1] == "song-dark-star"
    assert [row["show_id"] for row in rows(tmp_path / "canonical" / "resource_shows.csv")][-1] == "gd-1972-08-27"


def test_a_held_show_date_does_not_block_a_song_mapping(tmp_path):
    run(tmp_path, [{"title": "Morning Dew on February 27, 1969", "slug": "mixed"}])

    assert [row["song_id"] for row in rows(tmp_path / "canonical" / "resource_songs.csv")][-1] == "song-morning-dew"
    assert held(tmp_path)[0]["reason"] == "1969-02-27 matches more than one canonical show."


# ---------------------------------------------------------------------------
# Resource rows
# ---------------------------------------------------------------------------


def test_every_post_becomes_a_resource_row_shaped_by_its_host(tmp_path):
    summary = run(
        tmp_path,
        [{"title": "Vintage Dead reviewed", "labels": ["1966", "reviews"], "author": "LIA", "published": "2011-04-03T07:12:00.000-07:00", "slug": "vintage"}],
        host="deadsources.blogspot.com",
        site_id="dead-sources",
        site_name="Dead Sources",
        resource_type="press-transcription",
        slug="deadsources",
    )

    row = rows(tmp_path / "canonical" / "resources.csv")[-1]
    assert row["resource_id"] == "resource-deadsources-2012-08-vintage"
    assert row["resource_type"] == "press-transcription"
    assert row["title"] == "Vintage Dead reviewed"
    assert row["creator"] == "LIA"
    assert row["source_name"] == "Dead Sources"
    assert row["source_url"] == "https://deadsources.blogspot.com/2012/08/vintage.html"
    assert row["published_date"] == "2011-04-03"
    assert "Post labels: 1966, reviews" in row["notes"]
    assert "no post text is stored" in row["notes"]
    assert summary["resources_written"] == 1
    assert summary["unmapped"] == 1


def test_a_post_on_an_http_only_custom_domain_is_stored_over_https(tmp_path):
    # Grateful Seconds publishes on gratefulseconds.com, which offers no TLS,
    # so the stored link uses the blog's own https address instead.
    directory = canonical(tmp_path)
    raw_index(
        tmp_path,
        [{"title": "Dark Star, 1972-08-27", "url": "http://www.gratefulseconds.com/2015/01/hi-im-dave.html"}],
        host="gratefulseconds.blogspot.com",
        site_id="grateful-seconds",
        site_name="Grateful Seconds",
        resource_type="statistics-post",
        slug="gratefulseconds",
    )

    summary = nbp.normalize(tmp_path / "raw", directory, tmp_path / "held.jsonl")

    row = rows(directory / "resources.csv")[-1]
    assert row["source_url"] == "https://gratefulseconds.blogspot.com/2015/01/hi-im-dave.html"
    assert row["resource_id"] == "resource-gratefulseconds-2015-01-hi-im-dave"
    assert "gratefulseconds.com" in row["notes"]
    assert summary["songs_mapped"] == 1 and summary["shows_mapped"] == 1


def test_a_post_without_an_author_leaves_the_creator_blank(tmp_path):
    run(tmp_path, [{"title": "Anonymous post", "author": "", "slug": "anon"}])

    assert rows(tmp_path / "canonical" / "resources.csv")[-1]["creator"] == ""


# ---------------------------------------------------------------------------
# Idempotency and existing rows
# ---------------------------------------------------------------------------


def test_a_rerun_changes_nothing_and_writes_no_duplicate_rows(tmp_path):
    directory = canonical(tmp_path)
    raw_index(
        tmp_path,
        [
            {"title": "Dark Star, 1972-08-27", "slug": "a"},
            {"title": "February 27, 1969 Fillmore West", "slug": "b"},
            {"title": "Nothing to map here", "slug": "c"},
        ],
    )
    first = nbp.normalize(tmp_path / "raw", directory, tmp_path / "held.jsonl")
    before = {name: (directory / name).read_bytes() for name in ("resources.csv", "resource_songs.csv", "resource_shows.csv")}
    before_held = (tmp_path / "held.jsonl").read_bytes()

    second = nbp.normalize(tmp_path / "raw", directory, tmp_path / "held.jsonl")

    assert {name: (directory / name).read_bytes() for name in before} == before
    assert (tmp_path / "held.jsonl").read_bytes() == before_held
    assert first["resources_written"] == 3 and second["resources_written"] == 0
    assert second["resources_already_present"] == 3
    assert first["held"] == second["held"] == 1


def test_existing_rows_keep_their_place_and_their_values(tmp_path):
    run(tmp_path, [{"title": "Dark Star, 1972-08-27", "slug": "a"}])

    resources = rows(tmp_path / "canonical" / "resources.csv")
    assert resources[0] == EXISTING_RESOURCE
    assert rows(tmp_path / "canonical" / "resource_songs.csv")[0]["notes"] == "Existing row."
    assert rows(tmp_path / "canonical" / "resource_shows.csv")[0]["notes"] == "Existing row."


def test_an_existing_rows_own_quoting_survives_the_pass(tmp_path):
    directory = canonical(tmp_path)
    path = directory / "resources.csv"
    quoted = 'resource-hand-quoted,article,"A title needing no quotes",,Somewhere,https://example.org/a,,"A note needing no quotes."\n'
    with path.open("a", encoding="utf-8", newline="") as handle:
        handle.write(quoted)
    raw_index(tmp_path, [{"title": "Dark Star, 1972-08-27", "slug": "a"}])

    nbp.normalize(tmp_path / "raw", directory, tmp_path / "held.jsonl")

    assert quoted in path.read_text(encoding="utf-8")


def test_new_rows_are_sorted_by_resource_id(tmp_path):
    run(
        tmp_path,
        [
            {"title": "Zeta: Dark Star", "slug": "zeta"},
            {"title": "Alpha: Morning Dew", "slug": "alpha"},
            {"title": "Mid: Not Fade Away", "slug": "mid"},
        ],
    )

    added = [row["resource_id"] for row in rows(tmp_path / "canonical" / "resources.csv")][1:]
    assert added == sorted(added)
    song_rows = [row["resource_id"] for row in rows(tmp_path / "canonical" / "resource_songs.csv")][1:]
    assert song_rows == sorted(song_rows)


def test_a_post_url_already_cataloged_under_another_id_is_not_added_twice(tmp_path):
    directory = canonical(tmp_path)
    with (directory / "resources.csv").open("a", newline="", encoding="utf-8") as handle:
        csv.DictWriter(handle, fieldnames=RESOURCE_FIELDS, lineterminator="\n").writerow(
            {
                "resource_id": "resource-hand-written-veneta",
                "resource_type": "editorial-blog-post",
                "title": "Veneta",
                "creator": "",
                "source_name": "Lost Live Dead",
                "source_url": "https://lostlivedead.blogspot.com/2012/08/dupe.html",
                "published_date": "",
                "notes": "Cataloged by hand earlier.",
            }
        )
    raw_index(tmp_path, [{"title": "Dark Star, 1972-08-27", "slug": "dupe"}])

    summary = nbp.normalize(tmp_path / "raw", directory, tmp_path / "held.jsonl")

    assert summary["resources_written"] == 0
    assert summary["urls_already_cataloged"] == 1
    assert [row["resource_id"] for row in rows(directory / "resources.csv")] == [
        "resource-deadnet-tiger-rose-50",
        "resource-hand-written-veneta",
    ]
    assert len(rows(directory / "resource_songs.csv")) == 1


def test_an_aborted_or_empty_raw_directory_writes_nothing(tmp_path):
    directory = canonical(tmp_path)
    (tmp_path / "raw").mkdir()
    before = (directory / "resources.csv").read_bytes()

    summary = nbp.normalize(tmp_path / "raw", directory, tmp_path / "held.jsonl")

    assert summary["posts_read"] == 0
    assert (directory / "resources.csv").read_bytes() == before
    assert (tmp_path / "held.jsonl").read_text(encoding="utf-8") == ""


def test_the_summary_counts_hosts_and_posts(tmp_path):
    summary = run(tmp_path, [{"title": "Dark Star, 1972-08-27", "slug": "a"}, {"title": "Nothing here", "slug": "b"}])

    assert summary["hosts"] == 1
    assert summary["posts_read"] == 2
    assert summary["by_host"]["lostlivedead.blogspot.com"]["posts"] == 2
    assert summary["by_host"]["lostlivedead.blogspot.com"]["resources_written"] == 2


# ---------------------------------------------------------------------------
# Pure helpers
# ---------------------------------------------------------------------------


def test_a_run_spanning_two_months_names_both_of_its_ends(tmp_path):
    assert nbp.find_dates("Fillmore West February 27-March 2, 1969") == ["1969-02-27", "1969-03-02"]
    assert nbp.find_dates("January 31 - February 1, 1970: The Warehouse") == ["1970-01-31", "1970-02-01"]
    assert nbp.find_dates("December 31 - January 1, 1972 at Winterland") == ["1971-12-31", "1972-01-01"]

    run(tmp_path, [{"title": "Fillmore West September 26 to September 27, 1969", "slug": "run"}])

    assert held(tmp_path)[0]["reason"] == "The title names more than one date."


def test_find_dates_reads_each_format_once(tmp_path):
    assert nbp.find_dates("1972-08-27 and 8/27/72 and August 27, 1972") == ["1972-08-27"]
    assert nbp.find_dates("5/8/1977 then 5/9/77") == ["1977-05-08", "1977-05-09"]
    assert nbp.find_dates("Sept. 3, 1972") == ["1972-09-03"]
    assert nbp.find_dates("no dates at all") == []
    assert nbp.find_dates("2/29/1972") == ["1972-02-29"]
    assert nbp.find_dates("2/29/1971") == []


def test_resource_ids_come_from_the_post_url(tmp_path):
    assert nbp.resource_id_for("https://lostlivedead.blogspot.com/2012/08/veneta-1972.html") == "resource-lostlivedead-2012-08-veneta-1972"
    assert nbp.resource_id_for("https://www.deadessays.blogspot.com/2011/12/dark-star.html") == "resource-deadessays-2011-12-dark-star"
