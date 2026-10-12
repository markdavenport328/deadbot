"""A record is found however its name's quotes and dashes are typed."""

from deadbot.sqlite_store import SqliteCanonicalStore, _like


def test_like_folds_curly_quotes_dashes_and_case():
    assert _like("dick's picks%", "Dick’s Picks, Volume 4: Fillmore East 2/13–14/70") == 1
    assert _like("%2/13-14/70", "Dick’s Picks, Volume 4: Fillmore East 2/13–14/70") == 1
    assert _like("%100\\%%", "a 100% sure thing", "\\") == 1
    assert _like("dave's picks%", "Dick’s Picks") == 0
    assert _like(None, "x") is None


def test_a_straight_apostrophe_finds_dicks_picks(built_sqlite, tmp_path):
    store = SqliteCanonicalStore(built_sqlite, response_cache_path=tmp_path / "cache.sqlite")
    rows = store.matching_rows_any("official_releases", ["Dick's Picks"], ("title",))
    assert rows and all(row["release_id"].startswith("release-dicks-picks-") for row in rows)


def test_model_sql_matches_curly_titles(built_sqlite, tmp_path):
    store = SqliteCanonicalStore(built_sqlite, response_cache_path=tmp_path / "cache.sqlite")
    result = store.run_catalog_query(
        "SELECT DISTINCT release_id FROM release_track_facts WHERE release_title LIKE 'Dick''s Picks%'"
    )
    assert ["release-dicks-picks-volume-4-fillmore-east-1996"] in result["rows"]
