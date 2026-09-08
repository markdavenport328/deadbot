import json

from deadbot.data import CanonicalStore
from deadbot.pathways import pathways_for
from deadbot.postgres import PostgresCanonicalStore
from deadbot.tools import build_tools
from test_data import store_with_selection_evidence, tool_by_name
from test_postgres_store import Connection


def test_sugaree_is_cataloged_with_a_source_trail_and_a_non_catalog_resource():
    store = CanonicalStore()
    song = store.resolve_song("Sugaree")
    pathways = pathways_for(store, [("song", song["song_id"])])[song["song_id"]]

    assert pathways["cataloged"] is True
    assert "source_trail" in pathways
    assert pathways["source_trail"]["link_count"] >= 1
    assert pathways["resources"]["count"] >= 1
    assert all(item["resource_type"] not in {"catalog-work-search", "lyrics-and-credits"} for item in pathways["resources"]["top"])


def test_a_song_with_only_catalog_resources_is_not_cataloged():
    store = CanonicalStore()
    # A song whose only resources are catalog rows (MusicBrainz work, lyric
    # page). The targeted lore passes reach most of the repertoire now, so the
    # example is a one-off cover rather than a repertoire staple.
    song = store.resolve_song("Ballad Of Casey Jones")
    assert song is not None
    pathways = pathways_for(store, [("song", song["song_id"])])[song["song_id"]]

    assert pathways == {
        "cataloged": False,
        "research_routes": ["Grateful Dead Guide (Deadessays)", "Deadhead High", "Dead.net"],
    }


def test_veneta_show_has_a_source_trail_and_resources():
    store = CanonicalStore()
    show = store.resolve_show("gd-1972-08-27")
    pathways = pathways_for(store, [("show", show["show_id"])])[show["show_id"]]

    assert pathways["cataloged"] is True
    assert pathways["source_trail"]["link_count"] >= 1
    assert pathways["resources"]["count"] >= 1
    assert pathways["research_routes"] == [
        "Lost Live Dead",
        "Dead Sources",
        "Grateful Dead Archive Online",
        "Internet Archive Grateful Dead collection",
    ]


def test_every_pathways_object_is_compact():
    store = CanonicalStore()
    entities = [
        ("song", store.resolve_song("Sugaree")["song_id"]),
        ("song", store.resolve_song("Dark Star")["song_id"]),
        ("song", store.resolve_song("A Voice From On High")["song_id"]),
        ("show", store.resolve_show("gd-1972-08-27")["show_id"]),
        ("release", store.rows("official_releases")[0]["release_id"]),
    ]
    pathways = pathways_for(store, entities)
    for entity_id, payload in pathways.items():
        size = len(json.dumps(payload, ensure_ascii=False, separators=(",", ":")))
        assert size < 900, f"{entity_id} pathways is {size} characters: {payload}"


def test_search_entities_carries_pathways_for_the_show_and_the_song():
    store = CanonicalStore()
    result = json.loads(tool_by_name(store, "search_entities").invoke({"query": "Veneta Bird Song"}))

    pathways = result["pathways"]
    assert "gd-1972-08-27" in pathways
    assert "song-bird-song" in pathways
    assert pathways["gd-1972-08-27"]["cataloged"] is True


def test_dark_star_selections_include_headyversion():
    store = store_with_selection_evidence()
    song = store.resolve_song("Dark Star")
    pathways = pathways_for(store, [("song", song["song_id"])])[song["song_id"]]

    assert "selections" in pathways
    assert pathways["selections"]["count"] > 0
    assert "headyversion" in pathways["selections"]["sources"]


def test_get_show_issues_a_bounded_number_of_statements_on_the_postgres_toy_fixture():
    connection = Connection()
    store = PostgresCanonicalStore(connection, schema="canonical")
    tools = {tool.name: tool for tool in build_tools(store)}

    before = len(connection.statements)
    payload = json.loads(tools["get_show"].invoke({"show_id_or_date": "show-1972-08-27"}))
    issued = connection.statements[before:]

    assert len(issued) < 25
    assert "pathways" in payload
    assert isinstance(payload["pathways"], dict)
