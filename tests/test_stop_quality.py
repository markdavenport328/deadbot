from deadbot.song_life import LifePerformance
from deadbot.stop_quality import score_stops


def perf(pid, date, venue, seconds):
    return LifePerformance(
        performance_id=pid, show_id=f"gd-{date}", show_date=date, venue_name=venue, city=None, set_number=2,
        set_label="Set 2", position_in_set=4, encore=False, previous=None, next=None, seconds=seconds,
        length_source="tape" if seconds else None, audio_url=None, tape_seconds=seconds, releases=(), signals=(), guests=(),
    )


LIFE = [
    perf("p77", "1977-02-26", "Swing Auditorium", 668),
    perf("p79", "1979-01-08", "Madison Square Garden", 735),
    perf("p79b", "1979-11-06", "Spectrum", 937),
    perf("p86", "1986-04-22", "Berkeley Community Theater", 1078),
    perf("p93", "1993-09-29", "Boston Garden", 1514),
    perf("p95", "1995-07-08", "Soldier Field", 1022),
]
CASE = {"id": "t", "song_id": "song-t", "year": 1979}


def page(stops, **card):
    return {"blocks": [{"type": "song_overview", "song_id": "song-t", "visible_facets": ["by_year"], "year_summaries": [{"year": 1977}],
                        "representative_performances": stops, **card}, {"type": "editorial"}]}


def test_a_page_without_a_song_card_says_so():
    score = score_stops({"blocks": [{"type": "era_unit"}]}, CASE, LIFE, tools=["get_song"], seconds=9.5)
    assert score["song_card"] is False and score["other_blocks"] == ["era_unit"]
    assert score["used_song_life"] is False and score["seconds"] == 9.5
    assert score_stops(None, CASE, LIFE)["song_card"] is False


def test_stops_are_counted_spread_and_compared_with_the_calendar():
    score = score_stops(page([
        {"performance_id": "p77", "label": "The debut", "why": "First time out at Swing Auditorium."},
        {"performance_id": "p79", "label": "Charlie Miller's pick", "why": "The 1979 one, 12:15."},
        {"performance_id": "p86", "label": "Berkeley", "why": None},
        {"performance_id": "lost", "label": "A lost night", "why": "Not in the library."},
    ], open_year=1979, year_questions=[{"year": 1979, "question": "Q?"}]), CASE, LIFE)
    assert (score["song_card"], score["timeline"]) == (True, True)
    assert (score["stops_total"], score["stops_resolved"], score["labeled"], score["with_why"]) == (4, 3, 4, 3)
    assert score["years_spanned"] == 3 and score["span_share"] == 0.5 and score["thirds"] == 2
    assert score["beyond_calendar"] == 2
    assert score["open_year_ok"] is True and score["year_questions"] == 1
    assert score["fact_issues"] == []


def test_wrong_facts_in_a_stops_words_are_caught():
    score = score_stops(page([
        {"performance_id": "p79", "label": "The debut at the Spectrum", "why": "Debuted here, the longest ever at 25:14."},
        {"performance_id": "p86", "label": "The last one, 1985", "why": "A 30-minute reading."},
    ], open_year=1977), CASE, LIFE)
    issues = " | ".join(score["fact_issues"])
    assert "says first/debut but the debut is 1977-02-26" in issues
    assert "names Spectrum but the performance was at Madison Square Garden" in issues
    assert "says longest but it is the longest neither overall nor in its year" in issues
    assert "says 25:14 but the library has 12:15" in issues
    assert "says last but the last is 1995-07-08" in issues
    assert "says 30 minutes but the library has 18" in issues
    assert "names 1985 but the performance is from 1986" in issues
    assert score["open_year_ok"] is False


def test_the_longest_of_its_year_is_a_true_longest():
    score = score_stops(page([{"performance_id": "p79b", "label": "Longest of 1979", "why": "The longest 1979 version, about 15 minutes."}]), CASE, LIFE)
    assert score["fact_issues"] == []


def test_context_in_a_why_is_not_a_claim_about_the_stop():
    score = score_stops(page([
        {"performance_id": "p95", "label": "The last one", "why": "Closing a stage life that began at Swing Auditorium, nearly 18 years after its debut in 1977."},
    ]), CASE, LIFE)
    assert score["fact_issues"] == []


def test_qualified_and_contextual_phrases_are_not_claims():
    score = score_stops(page([
        {"performance_id": "p86", "label": "Berkeley", "why": "The longest among the released versions; the year's typical versions ran about 30 minutes, years after the debut."},
    ]), CASE, LIFE)
    assert score["fact_issues"] == []
