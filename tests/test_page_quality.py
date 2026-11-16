from deadbot.page_quality import model_layers, score_page


def _page(**overrides):
    page = {
        "lead": "The Dead played Harrisburg twice, both at City Island: June 22, 1983, and June 23, 1984.",
        "headline": "Two summers at City Island",
        "groups": [],
        "blocks": [
            {"type": "show_unit", "disclosure": "expanded", "visible_facets": ["listen"], "note": "A rare Bobby-sung Lovelight closes the first night."},
            {"type": "show_unit", "disclosure": "expanded", "visible_facets": ["listen"], "note": "Brent's keyboards lead a long Terrapin in 1984."},
        ],
    }
    page.update(overrides)
    return page


def test_a_lean_page_is_clean_and_meets_its_shape():
    expect = {"any_of": [{"type": "show_unit", "disclosure": "expanded", "min": 2}]}
    scored = score_page(_page(), expect)
    assert scored["clean"]
    assert scored["expected"] == {"met": True, "wanted": "show_unit expanded ×2+"}


def test_a_group_lead_that_restates_the_lead_is_a_repeat():
    scored = score_page(_page(groups=[{"title": None, "lead": "Harrisburg was a two-night stop: the Dead played City Island in June 1983 and June 1984."}]))
    assert scored["repeats"] and scored["repeats"][0].startswith("group[0].lead")
    assert not scored["clean"]


def test_catalog_talk_narration_and_hedges_are_counted():
    page = _page(
        headline="The catalog lists every show below, ordered by date.",
        groups=[{"title": None, "lead": "These are performance counts, not popularity ratings."}],
    )
    scored = score_page(page)
    assert any("catalog" in hit for hit in scored["catalog"])
    assert any("below" in hit for hit in scored["narration"])
    assert any("ordered by" in hit for hit in scored["narration"])
    assert any("not popularity" in hit for hit in scored["hedges"])


def test_server_filled_fields_are_not_scored():
    # Venue names and setlists come from the store; only the model's words count.
    page = _page(blocks=[{"type": "show_unit", "venue_name": "Library Hall", "note": None, "sets": [{"songs": [{"title": "Below the Line"}]}]}])
    assert model_layers(page) == [("headline", "Two summers at City Island")]
    assert score_page(page)["clean"]


def test_a_missing_shape_names_what_was_wanted():
    expect = {"any_of": [{"type": "version_strip"}, {"type": "song_overview", "facet": "by_year"}]}
    scored = score_page(_page(), expect)
    assert scored["expected"] == {"met": False, "wanted": "version_strip or song_overview +by_year"}


def _show_row(**overrides):
    row = {"type": "show_unit", "show_id": "gd-1980-09-26", "disclosure": "collapsed", "visible_facets": [], "sets": [], "tracks": [], "lineup": [], "guests": [], "recordings": [], "listen": [], "sources": []}
    row.update(overrides)
    return row


def test_a_show_row_with_nothing_to_open_is_an_empty_row():
    scored = score_page(_page(blocks=[_show_row(), _show_row(sets=[{"label": "Set 1", "songs": [{"title": "Ripple"}]}])]))
    assert scored["empty_rows"] == ["show_unit[0] gd-1980-09-26"]
    assert not scored["usable"]


def test_a_card_with_only_outbound_listening_is_silent():
    relisten = [{"label": "Stream the show", "url": "https://relisten.net/grateful-dead/1969/09/30", "provider": "relisten"}]
    tape = {"label": "Set 1", "songs": [{"title": "China Cat Sunflower", "audio_url": "https://archive.org/download/x/t01.mp3"}]}
    album = {"type": "album_unit", "release_title": "Ace", "embed_kind": "album", "embed_id": "album/x", "tracks": []}
    blocks = [_show_row(disclosure="expanded", listen=relisten), _show_row(disclosure="expanded", sets=[tape]), album]
    assert score_page(_page(blocks=blocks))["silent"] == ["show_unit[0] gd-1980-09-26"]


def test_a_fact_grid_retelling_the_album_cards_is_restated():
    albums = [
        {"type": "album_unit", "release_title": "Dick’s Picks, Volume 4: Fillmore East 2/13–14/70", "tracks": [{"audio_url": "x"}]},
        {"type": "album_unit", "release_title": "Dick’s Picks, Volume 11: Stanley Theater 9/27/72", "tracks": [{"audio_url": "x"}]},
    ]
    grid = {"type": "editorial", "presentation": "fact_grid", "title": "The quick route", "items": [
        {"marker": "Want space", "title": "Dick’s Picks 4", "value": "Start here"},
        {"marker": "Want 1972", "title": "Dick’s Picks 11", "value": "Start here"},
    ]}
    assert score_page(_page(blocks=[*albums, grid]))["restated"] == ["editorial[2] The quick route (2 of 2 rows retell cards)"]
    # A grid about other records is new material, not a retelling.
    other = {**grid, "items": [{"title": "Dick’s Picks 8"}, {"title": "Dick’s Picks 3"}]}
    assert score_page(_page(blocks=[*albums, other]))["restated"] == []


def test_year_rows_beside_a_song_timeline_are_restated():
    song = {"type": "song_overview", "visible_facets": ["by_year"], "year_counts": [{"year": 1968, "count": 37}, {"year": 1969, "count": 70}]}
    grid = {"type": "editorial", "title": "Year by year", "items": [{"marker": "1968", "title": "1968"}, {"marker": "1969", "title": "1969"}]}
    assert score_page(_page(blocks=[song, grid]))["restated"]


def test_the_opening_suite_asks_the_splash_questions():
    import json
    from pathlib import Path

    from scripts.warm_answers import OPENING_QUESTIONS

    suite = json.loads((Path(__file__).resolve().parents[1] / "evals" / "opening-v1.json").read_text(encoding="utf-8"))
    assert [case["question"] for case in suite["cases"]] == OPENING_QUESTIONS


def test_a_song_life_told_by_year_is_not_a_retelling():
    song = {"type": "song_overview", "visible_facets": ["by_year"], "year_counts": [{"year": 1968, "count": 37}, {"year": 1973, "count": 22}]}
    story = {"type": "editorial", "title": "Its life", "items": [
        {"marker": "1968", "title": "First single", "detail": "Released as a single before it ever stretched out."},
        {"marker": "1973", "title": "The last long ones", "detail": "Fall '73 brought the final half-hour versions."},
    ]}
    assert score_page(_page(blocks=[song, story]))["restated"] == []


def test_a_one_word_venue_needs_the_whole_row_to_match():
    shows = [{"type": "show_unit", "venue_name": "Winterland", "tracks": [{"audio_url": "x"}]}]
    grid = {"type": "editorial", "title": "Bay Area nights", "items": [{"title": "Winterland opens"}, {"title": "Winterland closes"}]}
    assert score_page(_page(blocks=[*shows, grid]))["restated"] == []


def _show_section(lead, row_note):
    sets = [{"songs": [{"title": title} for title in ("Eyes of the World", "Estimated Prophet", "Dark Star", "The Wheel", "Throwing Stones")]}]
    row = {"show_date": "1990-03-29", "venue_name": "Nassau Veterans Memorial Coliseum", "length_seconds": 789, "note": row_note}
    return _page(
        groups=[{"title": "The debut", "lead": lead, "block_indexes": [0, 1]}],
        blocks=[
            {"type": "show_unit", "sets": sets},
            {"type": "song_versions", "rows": [row]},
        ],
    )


def test_words_that_tell_what_the_cards_show_are_retold():
    scored = score_page(_show_section(
        "The second set ran Eyes of the World > Estimated Prophet > Dark Star > The Wheel.",
        "March 29 at Nassau Veterans Memorial Coliseum, 13:09 long.",
    ))
    assert scored["retold"] == [
        "group[0].lead: walks the setlist (4 songs on its show card)",
        "song_versions[1].row[0].note: gives its row's march 29, Nassau Veterans Memorial Coliseum, 13:09",
    ]
    assert not scored["clean"]


def test_words_about_what_happens_in_the_music_are_not_retold():
    scored = score_page(_show_section(
        "Phil invited him backstage; the band tried him on Bird Song, then kept him for Dark Star.",
        "Listen for the sax answering Jerry in the second verse.",
    ))
    assert scored["retold"] == []
