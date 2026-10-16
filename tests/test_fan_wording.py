"""Tool output reads like a fan talking: no catalog, record-keeping or import words.

The model copies the words it is handed. Keys, notes and tool descriptions the
code itself writes stay free of database and import vocabulary. Text that comes
from the data (titles, source names such as "UC Santa Cruz Library", free-text
notes) is the data's own wording and is left alone.
"""

import json
import re

import pytest

from deadbot.sqlite_store import SqliteCanonicalStore
from deadbot.tools import build_tools

BOX = "release-europe-72-the-complete-recordings-2011"
BANNED = re.compile(
    r"catalog|canonical|metadata|mapped|on record|unattributed|provenance|database",
    re.IGNORECASE,
)

# Fields that carry the data's own words.
DATA_FIELDS = {
    "title", "name", "source_name", "source", "creator", "summary", "text", "description", "label",
    "venue_name", "release_title", "song_title", "track_title", "selector_name", "why_open", "notes",
    "note_text", "city", "quote", "excerpt", "headline", "instrument", "role", "source_title", "resource_type",
}


@pytest.fixture(scope="module")
def tools(built_sqlite, tmp_path_factory):
    store = SqliteCanonicalStore(built_sqlite, response_cache_path=tmp_path_factory.mktemp("c") / "cache.sqlite")
    yield {t.name: t for t in build_tools(store)}
    store.close()


def tool_wording(node, field=""):
    """Every key and every string the tool wrote, skipping the data's own text fields."""

    if isinstance(node, dict):
        for key, value in node.items():
            yield key
            yield from tool_wording(value, key)
    elif isinstance(node, list):
        for value in node:
            yield from tool_wording(value, field)
    elif isinstance(node, str) and field not in DATA_FIELDS and not field.endswith(("_url", "_id")):
        yield node


def offenders(payload):
    return [text[:140] for text in tool_wording(payload) if BANNED.search(text)]


def call(tools, tool_name, args):
    return json.loads(tools[tool_name].invoke(args))


@pytest.mark.parametrize(
    "name,args",
    [
        ("get_album", {"release_id_or_title": BOX}),
        ("get_album", {"release_id_or_title": BOX, "include": ["live_legacy"]}),
        ("get_album", {"release_id_or_title": "American Beauty"}),
        ("get_song", {"song_id_or_title": "Terrapin Station"}),
        ("get_song_life", {"song_id_or_title": "Terrapin Station"}),
        ("get_song_notable_versions", {"song_id_or_title": "Dark Star"}),
        ("get_show", {"show_id_or_date": "1977-05-08"}),
        ("aggregate_data", {"dataset": "performances", "group_by": "year", "measure": "count", "song_id": "song-dark-star"}),
        ("look_up", {"name": "releases_covering_years", "year_from": 1972}),
    ],
)
def test_tool_output_has_no_catalog_words(tools, name, args):
    assert offenders(call(tools, name, args)) == []


def test_tool_descriptions_have_no_catalog_words(tools):
    bad = {name: BANNED.findall(tool.description) for name, tool in tools.items() if BANNED.search(tool.description)}
    assert bad == {}
