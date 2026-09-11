"""Tests for the Deadcast episode-index parser.

No network calls: ``parse_index`` is a pure function over the archive
listing's HTML, fixture-only.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1] / "scripts" / "collect"))
import collect_deadcast_episode_index as cdi  # noqa: E402


FIXTURE = """
<h3>Season 1</h3>
    <div class="views-row"><div class="views-field views-field-nothing"><span class="field-content"><span><a href="/deadcast/workingmans-dead-50-uncle-johns-band" target="_blank">Workingman’s Dead 50: Uncle John’s Band</a>&nbsp;</span>
<span>(<time datetime="2020-05-20T00:10:36-07:00" class="datetime">5/20/20</time>)&nbsp;</span>
<span></span></span></div></div>
    <div class="views-row"><div class="views-field views-field-nothing"><span class="field-content"><span><a href="/deadcast/bonus-tiger-rose-50" target="_blank">BONUS: Tiger Rose 50</a>&nbsp;</span>
<span>(<time datetime="2025-04-03T00:23:06-07:00" class="datetime">4/3/25</time>)&nbsp;</span>
<span>[<a href="/tiger-rose-50" target="_blank">transcript</a>]</span></span></div></div>
<h3>Season 2</h3>
    <div class="views-row"><div class="views-field views-field-nothing"><span class="field-content"><span><a href="/deadcast/american-beauty-50-box-rain" target="_blank">American Beauty 50: Box of Rain</a>&nbsp;</span>
<span>(<time datetime="2020-11-12T02:00:00-08:00" class="datetime">11/12/20</time>)&nbsp;</span>
<span>[<a href="/american-beauty-50-box-rain" target="_blank">transcript</a>]</span></span></div></div>
"""


def test_parse_index_reads_title_url_season_and_date_with_and_without_a_transcript_link():
    episodes, note = cdi.parse_index(FIXTURE)
    assert note == "3 episode row(s) parsed from the archive listing."
    assert episodes == [
        {
            "season": "1",
            "url_path": "/deadcast/workingmans-dead-50-uncle-johns-band",
            "title": "Workingman’s Dead 50: Uncle John’s Band",
            "published_date": "2020-05-20",
        },
        {
            "season": "1",
            "url_path": "/deadcast/bonus-tiger-rose-50",
            "title": "BONUS: Tiger Rose 50",
            "published_date": "2025-04-03",
        },
        {
            "season": "2",
            "url_path": "/deadcast/american-beauty-50-box-rain",
            "title": "American Beauty 50: Box of Rain",
            "published_date": "2020-11-12",
        },
    ]


def test_parse_index_returns_nothing_for_a_page_with_no_rows():
    episodes, note = cdi.parse_index("<p>nothing here</p>")
    assert episodes == []
    assert note == "0 episode row(s) parsed from the archive listing."
