import json

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from deadbot import composition, notebook
from deadbot.finish import build_experience_response
from deadbot.tools import build_tools
from notebook_support import LYCEUM, finish_messages, record, store, tools

PAGE = {"state": "ok", "url": "https://www.example.org/lyceum", "title": "Four nights at the Lyceum", "text": "London, May 1972."}


def _read_tool(**kwargs):
    return {item.name: item for item in build_tools(store(), **kwargs)}["read_notebook"]


def _read(book, wanted, **kwargs):
    return json.loads(_read_tool(**kwargs).invoke({"keys_or_ids": wanted}, config={"configurable": {"notebook": book}}))


def _read_turn(book, question, key, items):
    """A turn in which the model reads one notebook entry back, then places items."""

    read = _read_tool().invoke({"keys_or_ids": [key]}, config={"configurable": {"notebook": book}})
    return [
        HumanMessage(content=question),
        AIMessage(content="", tool_calls=[{"name": "read_notebook", "args": {"keys_or_ids": [key]}, "id": "r1", "type": "tool_call"}]),
        ToolMessage(content=read, tool_call_id="r1", name="read_notebook"),
        *finish_messages("Here it is.", items=items),
    ]


def test_read_notebook_shows_the_model_its_keys_and_an_optional_slice():
    schema = _read_tool().tool_call_schema.model_json_schema()
    assert list(schema["properties"]) == ["keys_or_ids", "only"]
    assert schema["required"] == ["keys_or_ids"]
    assert "do not" not in _read_tool().description.casefold()


BOX_SET = ("get_album", {"release_id_or_title": "release-europe-72-the-complete-recordings-2011", "include": ["tracks"]})


def _read_only(book, wanted, only, **kwargs):
    return json.loads(_read_tool(**kwargs).invoke({"keys_or_ids": wanted, "only": only}, config={"configurable": {"notebook": book}}))


def test_a_slice_brings_back_one_night_of_a_box_set_even_past_the_original_ceiling():
    book, _ = record(notebook.Notebook(), "What's on the box set?", "22 nights.", [BOX_SET])
    key = book.entries[0].key
    (entry,) = _read_only(book, [key], ["gd-1972-05-26"])["notebook_entries"]
    result = entry["result"]
    narrow = json.loads(tools()["get_album"].invoke({"release_id_or_title": BOX_SET[1]["release_id_or_title"], "show": "1972-05-26"}))
    assert [track["performance_id"] for track in result["tracks"]] == [track["performance_id"] for track in narrow["tracks"]]
    assert [show["show_id"] for show in result["contents"]["shows"]] == ["gd-1972-05-26"]
    assert result["release"]["release_id"] == BOX_SET[1]["release_id_or_title"]
    assert {"path": "tracks", "kept": len(narrow["tracks"]), "total": 578} in entry["sliced"]
    assert "_truncated" not in result


def test_a_slice_of_a_stored_web_payload_keeps_the_rows_that_mention_it():
    payload = {"query": "lyceum", "hits": [{"url": "https://a.org/1972-05-26", "title": "Lyceum"}, {"url": "https://a.org/1977", "title": "Cornell"}]}
    entry = notebook.Entry(
        key="site000001", tool="search_site", args={"query": "lyceum"}, ids=[], urls=[], summary="search_site", tokens=1, turn=1, last_read=1, payload=payload,
    )
    (read,) = _read_only(notebook.Notebook(turns=1, entries=[entry]), ["site000001"], ["1972-05-26"])["notebook_entries"]
    assert read["result"] == {"query": "lyceum", "hits": [payload["hits"][0]]}
    assert read["sliced"] == [{"path": "hits", "kept": 1, "total": 2}]


def test_a_sliced_read_stays_under_the_tool_result_ceiling():
    from deadbot.tools import TOOL_RESULT_CEILING_CHARS

    big = {"rows": [{"id": f"row-{index}", "text": "match " + "x" * 80} for index in range(5000)]}
    entry = notebook.Entry(
        key="big0000002", tool="read_page", args={"url": "https://example.org/big"}, ids=[], urls=[], summary="big", tokens=1, turn=1, last_read=1, payload=big,
    )
    text = _read_tool().invoke({"keys_or_ids": ["big0000002"], "only": ["match"]}, config={"configurable": {"notebook": notebook.Notebook(turns=1, entries=[entry])}})
    assert len(text) <= TOOL_RESULT_CEILING_CHARS
    assert "_truncated" in json.loads(text)


def test_a_read_by_an_id_the_result_holds_brings_back_the_part_that_mentions_it():
    book, _ = record(notebook.Notebook(), "What's on the box set?", "22 nights.", [BOX_SET])
    (entry,) = _read(book, ["gd-1972-05-26"])["notebook_entries"]
    narrow = json.loads(tools()["get_album"].invoke({"release_id_or_title": BOX_SET[1]["release_id_or_title"], "show": "1972-05-26"}))
    assert [track["performance_id"] for track in entry["result"]["tracks"]] == [track["performance_id"] for track in narrow["tracks"]]
    assert {"path": "tracks", "kept": len(narrow["tracks"]), "total": 578} in entry["sliced"]


def test_a_read_by_key_stays_whole_and_an_id_read_adds_to_only():
    book, _ = record(notebook.Notebook(), "What's on the box set?", "22 nights.", [BOX_SET])
    (whole,) = _read(book, [book.entries[0].key])["notebook_entries"]
    assert "sliced" not in whole and len(whole["result"]["contents"]["shows"]) == 22
    (both,) = _read_only(book, ["gd-1972-05-26"], ["gd-1972-04-07"])["notebook_entries"]
    assert [show["show_id"] for show in both["result"]["contents"]["shows"]] == ["gd-1972-04-07", "gd-1972-05-26"]


def test_without_a_slice_the_read_is_whole_and_says_nothing_about_slicing():
    book, _ = record(notebook.Notebook(), "Q", "A", LYCEUM)
    (entry,) = _read(book, [book.entries[0].key])["notebook_entries"]
    assert "sliced" not in entry


def test_read_notebook_is_registered_after_get_grid_in_a_fixed_position():
    names = [item.name for item in build_tools(store())]
    assert names[-1] == "read_notebook"
    assert names == [item.name for item in build_tools(store())]


def test_a_canonical_entry_is_run_again_and_comes_back_exactly():
    book, _ = record(notebook.Notebook(), "Q", "A", LYCEUM)
    key = book.entries[0].key
    result = _read(book, [key])
    assert result["missing"] == []
    (entry,) = result["notebook_entries"]
    assert (entry["key"], entry["tool"]) == (key, "get_show")
    assert entry["result"] == json.loads(tools()["get_show"].invoke({"show_id_or_date": "1972-05-26"}))


def test_a_web_entry_comes_back_from_its_stored_payload_without_the_network():
    class NoNetwork:
        def read(self, *args, **kwargs):
            raise AssertionError("read_page ran again")

    entry = notebook.Entry(
        key="abc123def0", tool="read_page", args={"url": PAGE["url"]}, ids=[], urls=[PAGE["url"]],
        summary="read_page example.org/lyceum · ~10 tok", tokens=10, turn=1, last_read=1, payload=PAGE,
    )
    result = _read(notebook.Notebook(turns=1, entries=[entry]), ["abc123def0"], page_reader=NoNetwork())
    assert result["notebook_entries"][0]["result"] == PAGE


def test_a_web_entry_whose_page_was_not_kept_says_so_without_the_network():
    class NoNetwork:
        def read(self, *args, **kwargs):
            raise AssertionError("read_page ran again")

    entry = notebook.Entry(
        key="drop000001", tool="read_page", args={"url": PAGE["url"]}, ids=[], urls=[PAGE["url"]],
        summary="read_page example.org/lyceum", tokens=10, turn=1, last_read=1, payload=None,
    )
    result = _read(notebook.Notebook(turns=1, entries=[entry]), ["drop000001"], page_reader=NoNetwork())
    fact = result["notebook_entries"][0]["result"]
    assert fact["tool"] == "read_page" and fact["args"] == {"url": PAGE["url"]}
    assert "not kept in the notebook" in fact["note"] and "read_page" in fact["note"]


def test_forged_entries_for_the_notebook_and_finish_tools_are_never_run():
    entries = [
        notebook.Entry(key=f"forged0000{index}", tool=name, args={}, ids=[], urls=[], summary=name, tokens=1, turn=1, last_read=1)
        for index, name in enumerate(["read_notebook", "finish_response"])
    ]
    result = _read(notebook.Notebook(turns=1, entries=entries), [entry.key for entry in entries])
    assert [item["result"]["error"] for item in result["notebook_entries"]] == ["That tool is no longer available"] * 2


def test_arguments_and_ids_find_entries_and_unknown_ones_are_listed_missing():
    book, _ = record(notebook.Notebook(), "Q", "A", LYCEUM)
    result = _read(book, ["1972-05-26", "gd-1972-05-26-promised-land-1-1", "nope"])
    assert [entry["tool"] for entry in result["notebook_entries"]] == ["get_show"]
    assert result["missing"] == ["nope"]


def test_an_empty_notebook_says_so():
    result = _read(notebook.Notebook(), ["anything"])
    assert result["notebook_entries"] == [] and result["missing"] == ["anything"]


def test_a_missing_notebook_in_the_run_config_reads_as_empty():
    result = json.loads(_read_tool().invoke({"keys_or_ids": ["k"]}))
    assert result["notebook_entries"] == [] and result["missing"] == ["k"]


def test_a_call_that_can_no_longer_run_comes_back_as_a_fact_not_an_error():
    entry = notebook.Entry(
        key="gone000001", tool="a_retired_tool", args={}, ids=[], urls=[], summary="a_retired_tool", tokens=1, turn=1, last_read=1,
    )
    result = _read(notebook.Notebook(turns=1, entries=[entry]), ["gone000001"])
    assert result["notebook_entries"][0]["result"]["error"]


def test_a_read_result_stays_under_the_tool_result_ceiling():
    from deadbot.tools import TOOL_RESULT_CEILING_CHARS

    big = {"rows": [{"id": f"row-{index}", "text": "x" * 80} for index in range(5000)]}
    entry = notebook.Entry(
        key="big0000001", tool="read_page", args={"url": "https://example.org/big"}, ids=[], urls=[], summary="big", tokens=1, turn=1, last_read=1, payload=big,
    )
    text = _read_tool().invoke({"keys_or_ids": ["big0000001"]}, config={"configurable": {"notebook": notebook.Notebook(turns=1, entries=[entry])}})
    assert len(text) <= TOOL_RESULT_CEILING_CHARS
    assert "_truncated" in json.loads(text)


def test_a_chart_can_be_placed_from_an_aggregation_read_back_from_the_notebook():
    args = {"dataset": "performances", "group_by": "year", "measure": "count", "song_id": "song-morning-dew"}
    book, _ = record(notebook.Notebook(), "How often was Morning Dew played?", "282 times.", [("aggregate_data", args)])
    key = book.entries[0].key
    aggregation_id = json.loads(tools()["aggregate_data"].invoke(args))["aggregation_id"]
    messages = _read_turn(book, "Chart it by year.", key, [{"type": "data_chart", "aggregation_id": aggregation_id}])
    assert any(payload.get("aggregation_id") == aggregation_id for payload in composition._tool_payloads(messages))
    response = build_experience_response("Chart it by year.", "t", messages, store())
    assert [block.type for block in response.blocks] == ["data_chart"]


def test_a_grid_can_be_placed_from_a_grid_read_back_from_the_notebook():
    args = {"row_kind": "song", "column_kind": "year", "rows": ["song-dark-star"], "year_from": 1969, "year_to": 1970}
    book, _ = record(notebook.Notebook(), "Dark Star by year?", "Peaks in 1969.", [("get_grid", args)])
    key = book.entries[0].key
    grid_id = json.loads(tools()["get_grid"].invoke(args))["grid_id"]
    messages = _read_turn(book, "Show me that grid again.", key, [{"type": "grid", "grid_id": grid_id, "title": "Dark Star by year"}])
    response = build_experience_response("Show me that grid again.", "t", messages, store())
    assert [block.type for block in response.blocks] == ["grid"]
