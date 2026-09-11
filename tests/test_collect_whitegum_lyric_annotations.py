"""Tests for the whitegum.com site-index parser and song lookup.

Fixture-only: ``parse_longlist`` and ``build_lookup`` are pure functions over
a small HTML fixture shaped like the site's real ``/longlist.htm``, and no
network call is made.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1] / "scripts" / "collect"))
sys.path.insert(0, str(Path(__file__).parents[1] / "scripts" / "normalize"))
import collect_whitegum_lyric_annotations as cwl  # noqa: E402
from normalize_song_guide_resources import match_key  # noqa: E402


FIXTURE = """
<H3>Originals</H3>
<A HREF="/~acsa/songfile/UNCLEJB.HTM"><B>Uncle John's Band </B></A><BR>
<A HREF="/~acsa/songfile/COMESTIM.HTM"><B>Comes A Time </B></A><BR>
<H3>Covers</H3>
Aiko, Aiko <I>see</I> <A HREF="/~acsa/songfile/IKOIKO.HTM"><B>Iko Iko </B></A><BR>
<H3>Phil &amp; Friends</H3>
<A HREF="/~acsa/songfile/COMESTI2.HTM"><B>Comes A Time </B></A><BR>
"""


def test_parse_longlist_reads_section_alias_href_and_title():
    entries = cwl.parse_longlist(FIXTURE)
    assert {"section": "Originals", "alias": "", "href": "/~acsa/songfile/UNCLEJB.HTM", "title": "Uncle John's Band"} in entries
    assert {"section": "Covers", "alias": "Aiko, Aiko", "href": "/~acsa/songfile/IKOIKO.HTM", "title": "Iko Iko"} in entries


def test_build_lookup_keys_by_both_title_and_alias():
    entries = cwl.parse_longlist(FIXTURE)
    lookup = cwl.build_lookup(entries)
    assert lookup[match_key("Uncle John's Band")][0]["href"] == "/~acsa/songfile/UNCLEJB.HTM"
    # The alias "Aiko, Aiko" resolves to the same page as its own title "Iko Iko".
    assert lookup[match_key("Aiko, Aiko")][0]["href"] == "/~acsa/songfile/IKOIKO.HTM"


def test_build_lookup_surfaces_two_distinct_pages_for_one_ambiguous_title():
    entries = cwl.parse_longlist(FIXTURE)
    lookup = cwl.build_lookup(entries)
    candidates = lookup[match_key("Comes A Time")]
    hrefs = sorted({candidate["href"] for candidate in candidates})
    assert hrefs == ["/~acsa/songfile/COMESTI2.HTM", "/~acsa/songfile/COMESTIM.HTM"]
