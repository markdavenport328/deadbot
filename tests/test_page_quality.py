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
