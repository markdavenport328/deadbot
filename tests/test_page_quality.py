from deadbot.page_quality import model_layers, score_page


def _page(**overrides):
    page = {
        "answer": "The Dead played Harrisburg twice, both at City Island: June 22, 1983, and June 23, 1984.",
        "title": "Two summers at City Island",
        "body_lead": None,
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


def test_a_lead_that_restates_the_chat_answer_is_a_repeat():
    scored = score_page(_page(body_lead="Harrisburg was a two-night stop: the Dead played City Island in June 1983 and June 1984."))
    assert scored["repeats"] and scored["repeats"][0].startswith("lead")
    assert not scored["clean"]


def test_catalog_talk_narration_and_hedges_are_counted():
    page = _page(
        body_lead="The catalog lists every show below, ordered by date.",
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
    assert model_layers(page) == [("title", "Two summers at City Island")]
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
    album = {"type": "album_unit", "release_title": "Ace", "listen": [{"provider": "spotify", "url": "https://open.spotify.com/album/x"}], "tracks": []}
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
