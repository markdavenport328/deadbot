"""The page keeps the model's work: lenient reading, one shared path, reference-based records."""

import json

import pytest
from langchain_core.messages import AIMessage, AIMessageChunk, HumanMessage, ToolMessage

from deadbot import finish
from deadbot.data import CanonicalStore
from deadbot.plan_stream import PlanStreamer
from deadbot.sqlite_store import SqliteCanonicalStore
from deadbot.tools import build_tools


@pytest.fixture
def sqlite_store(built_sqlite, tmp_path):
    result = SqliteCanonicalStore(built_sqlite, response_cache_path=tmp_path / "cache.sqlite")
    yield result
    result.close()


def _tool(store, name):
    return next(tool for tool in build_tools(store) if tool.name == name)


def _turn(payloads: list[tuple[str, dict]], plan: dict) -> list:
    messages: list = [HumanMessage(content="q")]
    for index, (name, payload) in enumerate(payloads):
        call_id = f"call-{index}"
        messages.append(AIMessage(content="", tool_calls=[{"name": name, "args": {}, "id": call_id, "type": "tool_call"}]))
        messages.append(ToolMessage(content=json.dumps(payload), tool_call_id=call_id, name=name))
    messages.append(AIMessage(content="", tool_calls=[{"name": finish.FINISH_TOOL_NAME, "args": plan, "id": "finish-1", "type": "tool_call"}]))
    messages.append(ToolMessage(content="Response delivered to the visitor.", tool_call_id="finish-1", name=finish.FINISH_TOOL_NAME))
    return messages


def _streamed_blocks(plan: dict, payloads: list[dict], store) -> list[dict]:
    grounded = finish.grounded_context(payloads)
    streamer = PlanStreamer(lambda items: finish.resolve_items(items, grounded, payloads, store)[0], grounded_urls=grounded.urls)
    text = json.dumps(plan)
    events = []
    for offset in range(0, len(text), 97):
        chunk = AIMessageChunk(
            content="",
            tool_call_chunks=[{"name": finish.FINISH_TOOL_NAME if offset == 0 else None, "args": text[offset : offset + 97], "id": "finish-1", "index": 0, "type": "tool_call_chunk"}],
        )
        events.extend(streamer.feed(chunk))
    assert not streamer.disabled
    return [event.payload["block"] for event in events if event.type == "block"]


def test_the_streamed_page_and_the_delivered_page_have_the_same_blocks():
    store = CanonicalStore()
    show = store.show_context(store.resolve_show("1972-08-27"))
    song = store.song_context(store.resolve_song("Sugaree"))
    shows = [row["show_id"] for row in store.filtered_rows("shows") if row.get("show_date", "").startswith("1977")]
    listing = {"shows": [{"show_id": show_id} for show_id in shows]}
    performance_id = show["performances"][0]["performance_id"]
    follow_ups = [{"label": f"Topic {n}", "question": f"What about topic {n}?", "why": "extra key"} for n in range(6)]
    plan = {
        "chat_answer": "Veneta was hot.",
        "title": "Veneta and May 1977",
        "groups": [
            {
                "title": "The night",
                "presentation": "comparison",
                "criteria": ["Pace", "Jam"],
                "mood": "an extra group key",
                "items": [
                    {
                        "type": "show_unit",
                        "show_id": "gd-1972-08-27",
                        "emphasis": "primary",
                        "judgments": ["Relaxed", "Long", "Extra", "Beyond", "the", "old", "cap"],
                        "visible_facets": ["setlist", "not_a_facet", "listen"],
                        "follow_ups": follow_ups,
                        "confidence": "an extra item key",
                    },
                    {"type": "song_overview", "song_id": "song-sugaree", "visible_facets": ["by_year"], "representative_performance_ids": [performance_id] * 5},
                    {"type": "show_unit", "show_id": "gd-2099-01-01", "note": "A night the tools never returned."},
                    {"title": "Heat", "value": "Over 100°F", "detail": "A row without its type."},
                    {"type": "editorial", "items": [{"title": "Kept"}, {"detail": "no title"}], "paragraphs": ["p"] * 7},
                    {"type": "pull_quote", "text": "x" * 600},
                    {"type": "no_such_block"},
                ],
            },
            {"presentation": "collection", "items": [{"type": "show_unit", "show_id": show_id, "disclosure": "collapsed"} for show_id in shows]},
        ]
        + [{"presentation": "collection", "items": [{"type": "editorial", "paragraphs": [f"Group {n}"]}]} for n in range(9)],
    }
    payloads = [show, song, listing]
    response = finish.build_experience_response("q", "t", _turn([("get_show", show), ("get_song", song), ("query_catalog", listing)], plan), store)
    final = [block.model_dump(mode="json") for block in response.blocks]
    streamed = _streamed_blocks(plan, payloads, store)
    assert streamed == final

    types = [block["type"] for block in final]
    assert types[:6] == ["show_unit", "song_overview", "editorial", "editorial", "editorial", "pull_quote"]
    assert final[0]["judgments"] == ["Relaxed", "Long", "Extra", "Beyond", "the", "old", "cap"]
    assert final[0]["visible_facets"] == ["listen", "setlist"]
    assert len(final[0]["follow_ups"]) == 6
    assert final[2]["paragraphs"] == ["A night the tools never returned."]
    assert final[3]["items"][0]["title"] == "Heat"
    assert [item["title"] for item in final[4]["items"]] == ["Kept"] and len(final[4]["paragraphs"]) == 7
    assert len(final[5]["text"]) == 600
    collapsed = [block for block in final if block["type"] == "show_unit" and block["disclosure"] == "collapsed"]
    assert len(collapsed) == len(shows) > 20
    assert len(response.groups) == 11


def test_song_overview_by_year_counts_every_year_from_first_to_last():
    store = CanonicalStore()
    context = store.song_context(store.resolve_song("Dark Star"))
    blocks, _ = finish.resolve_items(
        [finish.validate_body_item({"type": "song_overview", "song_id": context["song"]["song_id"], "visible_facets": ["by_year"]}, where="planned")],
        finish.grounded_context([context]),
        [context],
        store,
    )
    counts = blocks[0].year_counts
    years = [entry.year for entry in counts]
    assert years == list(range(years[0], years[-1] + 1))
    assert sum(entry.count for entry in counts) == len([p for p in context["performances"]])
    assert any(entry.count == 0 for entry in counts)
    assert blocks[0].first_year == years[0] and blocks[0].last_year == years[-1]


def test_album_units_from_a_catalog_result_list_every_release_collapsed(sqlite_store):
    result = json.loads(_tool(sqlite_store, "query_catalog").invoke({"name": "releases_covering_years", "year_from": 1972}))
    assert result["result_id"].startswith("query:")
    release_ids = [row[result["columns"].index("release_id")] for row in result["rows"]]
    item = finish.validate_body_item({"type": "album_unit", "from_result": result["result_id"], "disclosure": "collapsed", "visible_facets": ["listen", "tracklist"]}, where="planned")
    blocks, _ = finish.resolve_items([item], finish.grounded_context([result]), [result], sqlite_store)
    assert [block.release_id for block in blocks] == release_ids
    assert all(block.disclosure == "collapsed" for block in blocks)
    with_one_show = [block for block in blocks if block.show_count == 1]
    assert with_one_show and all(block.show_venue_name and block.first_show_date for block in with_one_show)
    assert any(block.cover_url and block.cover_url.endswith("/front-250") for block in blocks)


def test_a_ranked_list_takes_its_rows_and_counts_from_the_aggregation():
    store = CanonicalStore()
    payload = json.loads(_tool(store, "aggregate_data").invoke({"dataset": "performances", "group_by": "song", "measure": "count", "limit": 10}))
    first = payload["rows"][0]
    item = finish.validate_body_item(
        {"type": "ranked_list", "aggregation_id": payload["aggregation_id"], "count": 5, "notes": [{"key": first["id"], "note": "The workhorse."}]},
        where="planned",
    )
    (block,), _ = finish.resolve_items([item], finish.grounded_context([payload]), [payload], store)
    assert [row.label for row in block.rows] == [row["label"] for row in payload["rows"][:5]]
    assert [row.value for row in block.rows] == [row["value"] for row in payload["rows"][:5]]
    assert block.rows[0].note == "The workhorse." and block.more_count >= 5


def test_an_editorial_item_that_names_a_performance_plays_it():
    store = CanonicalStore()
    show = store.show_context(store.resolve_show("1977-05-08"))
    playable = next(p for p in show["performances"] if (p.get("listen") or {}).get("archive_track_url"))
    item = finish.validate_body_item(
        {"type": "editorial", "presentation": "fact_grid", "items": [{"title": "The one", "performance_id": playable["performance_id"]}]},
        where="planned",
    )
    (block,), _ = finish.resolve_items([item], finish.grounded_context([show]), [show], store)
    assert block.items[0].tracks and block.items[0].tracks[0].performance_id == playable["performance_id"]
