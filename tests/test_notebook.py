import base64
import json
import logging
import os
import zlib
from types import SimpleNamespace

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from deadbot import composition, notebook
from deadbot.experience import ConversationTurn
from deadbot.finish import build_experience_response
from notebook_support import LYCEUM, SECRET, finish_messages, record, store

MORNING_DEW = [("get_song", {"song_id_or_title": "Morning Dew"})]
PAGE = {
    "state": "ok",
    "url": "https://www.example.org/lyceum",
    "title": "Four nights at the Lyceum",
    "total_chars": 5000,
    "offset": 0,
    "text": "The band closed the tour in London.",
}


def _web_turn(payload):
    messages = [
        HumanMessage(content="What did the papers say?"),
        AIMessage(content="", tool_calls=[{"name": "read_page", "args": {"url": PAGE["url"]}, "id": "r1", "type": "tool_call"}]),
        ToolMessage(content=json.dumps(payload), tool_call_id="r1", name="read_page"),
        *finish_messages("Four nights."),
    ]
    response = build_experience_response("What did the papers say?", "t", messages, store())
    return notebook.record_turn(notebook.Notebook(), composition._latest_turn(messages), response)


def test_each_tool_call_becomes_one_entry_with_its_ids_and_a_fact_line():
    book, _ = record(notebook.Notebook(), "Tell me about May 26, 1972.", "The last Lyceum night.", LYCEUM + MORNING_DEW)
    assert book.turns == 1
    show, song = book.entries
    assert show.key == notebook.entry_key("get_show", {"show_id_or_date": "1972-05-26"})
    assert show.summary.startswith("get_show gd-1972-05-26 · Lyceum, London · 31 songs in 2 sets · 4 recordings · ~")
    assert song.summary.startswith("get_song song-morning-dew · Morning Dew · 282 performances, 1967–1995 · 79 releases · ~")
    assert {"gd-1972-05-26", "gd-1972-05-26-promised-land-1-1"} <= set(show.ids)
    assert "song-morning-dew" in song.ids
    assert (show.turn, show.last_read, show.payload) == (1, 1, None)


def test_a_web_result_keeps_its_payload_and_its_urls():
    (entry,) = _web_turn(PAGE).entries
    assert entry.payload == PAGE
    assert entry.summary.startswith('read_page example.org/lyceum · "Four nights at the Lyceum" · 35 of 5000 chars · ~')
    assert PAGE["url"] in entry.urls


def test_errors_and_the_finish_call_are_not_recorded():
    book, _ = record(notebook.Notebook(), "Tell me about 1972-13-45.", "No such night.", [("get_show", {"show_id_or_date": "1972-13-45"})])
    assert book.entries == []
    assert book.pages[0].turn == 1


def test_running_the_same_call_again_keeps_its_first_turn_and_line():
    first, _ = record(notebook.Notebook(), "Q1", "A1", LYCEUM, prefix="a")
    second, _ = record(first, "Q2", "A2", LYCEUM, prefix="b")
    (entry,) = second.entries
    assert (entry.turn, entry.last_read, entry.summary) == (1, 2, first.entries[0].summary)
    assert second.turns == 2


def test_reading_an_entry_back_marks_it_read_without_adding_an_entry():
    first, _ = record(notebook.Notebook(), "Q1", "A1", LYCEUM, prefix="a")
    key = first.entries[0].key
    messages = [
        HumanMessage(content="Q2"),
        AIMessage(content="", tool_calls=[{"name": "read_notebook", "args": {"keys_or_ids": [key]}, "id": "n1", "type": "tool_call"}]),
        ToolMessage(content=json.dumps({"notebook_entries": [{"key": key, "tool": "get_show", "args": {}, "result": {"show": {}}}]}), tool_call_id="n1", name="read_notebook"),
        *finish_messages("A2"),
    ]
    response = build_experience_response("Q2", "t", messages, store())
    second = notebook.record_turn(first, composition._latest_turn(messages), response)
    assert [(entry.key, entry.last_read) for entry in second.entries] == [(key, 2)]


def test_the_page_digest_names_each_block_and_the_chips():
    item = {
        "type": "show_unit",
        "show_id": "gd-1972-05-26",
        "title": "The last Lyceum night",
        "note": "Morning Dew out of The Other One.",
        "visible_facets": ["setlist"],
        "follow_ups": [{"label": "Lyceum Morning Dew", "question": "How does the Lyceum Morning Dew compare?"}],
    }
    book, response = record(notebook.Notebook(), "Tell me about May 26, 1972.", "The last Lyceum night.", LYCEUM, items=[item])
    (page,) = book.pages
    assert page.answer_key == notebook.answer_key(response.answer)
    assert page.blocks[0]["type"] == "show_unit" and page.blocks[0]["ids"] == ["gd-1972-05-26"]
    assert page.blocks[0]["note"] == "Morning Dew out of The Other One."
    assert page.chips == ["Lyceum Morning Dew"]


def test_each_turns_lines_follow_its_answer_in_the_transcript():
    book, _ = record(notebook.Notebook(), "Tell me about May 26, 1972.", "The last Lyceum night.", LYCEUM)
    conversation = [
        ConversationTurn(role="user", text="Tell me about May 26, 1972."),
        ConversationTurn(role="assistant", text="The last Lyceum night."),
    ]
    messages = notebook.transcript_with_notebook(book, conversation)
    assert [message.type for message in messages] == ["human", "ai", "human"]
    assert messages[2].name == composition.NOTEBOOK_MESSAGE_NAME
    assert messages[2].content.startswith("Research notebook, turn 1:")
    assert f"[{book.entries[0].key}] get_show gd-1972-05-26" in messages[2].content


def test_a_turn_whose_answer_is_not_in_the_transcript_goes_in_one_leading_message():
    book, _ = record(notebook.Notebook(), "Tell me about May 26, 1972.", "The last Lyceum night.", LYCEUM)
    conversation = [ConversationTurn(role="user", text="Hi"), ConversationTurn(role="assistant", text="Something else.")]
    messages = notebook.transcript_with_notebook(book, conversation)
    assert [message.type for message in messages] == ["human", "human", "ai"]
    assert messages[0].content.startswith("Research notebook from earlier in this conversation")
    assert "Turn 1:" in messages[0].content


def test_an_empty_notebook_leaves_the_transcript_as_it_was():
    conversation = [ConversationTurn(role="user", text="Hi"), ConversationTurn(role="assistant", text="Hello.")]
    messages = notebook.transcript_with_notebook(notebook.Notebook(), conversation)
    assert [(message.type, message.content) for message in messages] == [("human", "Hi"), ("ai", "Hello.")]


def test_find_matches_keys_then_arguments_then_ids():
    book, _ = record(notebook.Notebook(), "Q", "A", LYCEUM + MORNING_DEW)
    show, song = book.entries
    found, missing = notebook.find(book, [f"[{song.key}]", "1972-05-26", "gd-1972-05-26-promised-land-1-1", "nope"])
    assert [entry.key for entry in found] == [song.key, show.key]
    assert missing == ["nope"]


def test_grounding_and_focus_flags_cover_entries_and_pages():
    item = {"type": "show_unit", "show_id": "gd-1972-05-26", "visible_facets": ["setlist"]}
    book, _ = record(notebook.Notebook(), "Q", "A", LYCEUM, items=[item])
    ids, urls = notebook.grounding(book)
    assert "gd-1972-05-26-promised-land-1-1" in ids and "gd-1972-05-26" in ids
    assert isinstance(urls, frozenset)
    flagged = notebook.entries_mentioning(book, ["gd-1972-05-26", "gd-1999-01-01"])
    assert [entry.tool for entry in flagged] == ["get_show"]
    assert notebook.render_flags(flagged).startswith("Already in the research notebook for what the visitor clicked:")
    assert notebook.render_flags([]) == ""


def test_from_json_keeps_good_entries_and_skips_bad_ones():
    book, _ = record(notebook.Notebook(), "Q", "A", LYCEUM)
    data = book.to_json()
    data["entries"].append({"key": "only-a-key"})
    data["pages"].append("junk")
    restored = notebook.Notebook.from_json(data)
    assert [entry.key for entry in restored.entries] == [book.entries[0].key]
    assert len(restored.pages) == 1
    assert notebook.Notebook.from_json("junk") == notebook.Notebook()


def _messages_with(name, payload, call_id="x1", args=None):
    return [
        HumanMessage(content="Q"),
        AIMessage(content="", tool_calls=[{"name": name, "args": args or {}, "id": call_id, "type": "tool_call"}]),
        ToolMessage(content=payload if isinstance(payload, str) else json.dumps(payload), tool_call_id=call_id, name=name),
    ]


def test_a_failed_web_read_is_not_recorded_but_an_empty_one_is():
    for state in ("unavailable", "invalid"):
        assert notebook.tool_results(_messages_with("read_page", {"state": state, "url": PAGE["url"], "message": "x"})) == []
        assert notebook.tool_results(_messages_with("get_deadcast_metadata", {"research": {"state": state}})) == []
    kept = notebook.tool_results(_messages_with("read_page", {"state": "empty", "url": PAGE["url"], "text": ""}))
    assert [name for name, *_ in kept] == ["read_page"]


def test_a_failed_read_leaves_no_entry_in_the_notebook():
    messages = [*_messages_with("read_page", {"state": "unavailable", "url": PAGE["url"]}, "r1", {"url": PAGE["url"]}), *finish_messages("Could not fetch it.")]
    response = build_experience_response("Q", "t", messages, store())
    assert notebook.record_turn(notebook.Notebook(), composition._latest_turn(messages), response).entries == []


def test_tool_results_skips_non_json_list_and_error_payloads_without_raising():
    for payload in ("not json at all", json.dumps(["a", "list"]), json.dumps({"error": "boom"}), json.dumps("a string")):
        assert notebook.tool_results(_messages_with("get_show", payload)) == []


def test_the_finish_call_is_excluded_by_name_even_with_a_json_payload():
    messages = _messages_with(notebook.FINISH_TOOL_NAME, {"ok": True})
    assert notebook.tool_results(messages) == []
    assert notebook.tool_results(_messages_with("get_show", {"ok": True}))[0][0] == "get_show"


def test_entry_key_ignores_argument_order():
    assert notebook.entry_key("query_catalog", {"a": 1, "b": [2, 3]}) == notebook.entry_key("query_catalog", {"b": [2, 3], "a": 1})
    assert notebook.entry_key("get_show", {"a": 1}) != notebook.entry_key("get_song", {"a": 1})
    assert len(notebook.entry_key("get_show", {})) == 10


def test_an_unknown_tool_gets_the_generic_fact_line():
    line = notebook.summarize("get_mystery", {"q": "dew"}, {"rows": [1, 2, 3], "note": "x"}, 2500)
    assert line == "get_mystery dew · 3 rows · ~2.5k tok"


def test_a_failing_fact_line_falls_back_to_the_generic_one(monkeypatch):
    def boom(args, payload):
        raise ValueError("bad payload")

    monkeypatch.setitem(notebook._SUMMARIES, "get_show", boom)
    assert notebook.summarize("get_show", {"show_id_or_date": "1972-05-26"}, {"performances": [1]}, 10) == "get_show 1972-05-26 · 1 performances · ~10 tok"


def test_ids_and_urls_ceilings_trim_and_log(caplog):
    payload = {"rows": [{"show_id": f"gd-1972-{index:04d}"} for index in range(450)], "links": [f"https://example.org/{index}" for index in range(70)]}
    with caplog.at_level(logging.INFO, logger="deadbot.notebook"):
        ids, urls = notebook._ids_and_urls(payload)
    assert len(ids) == notebook.IDS_PER_ENTRY_CEILING and len(urls) == notebook.URLS_PER_ENTRY_CEILING
    assert "kept 400 of" in caplog.text


class _Block:
    def __init__(self, data):
        self.data = data

    def model_dump(self, mode="json"):
        return self.data


def test_the_digest_keeps_twelve_blocks_and_eight_chips():
    blocks = [
        _Block({"type": "show_unit", "show_id": f"gd-1972-{index:04d}", "title": f"T{index}", "follow_ups": [{"label": f"Chip {index}"}]})
        for index in range(20)
    ]
    response = SimpleNamespace(blocks=blocks, answer="A", title="Title")
    page = notebook.page_digest(response, 3)
    assert len(page.blocks) == notebook.DIGEST_BLOCK_CEILING == 12
    assert page.chips == [f"Chip {index}" for index in range(8)]
    assert page.blocks[0] == {"type": "show_unit", "ids": ["gd-1972-0000"], "title": "T0", "note": ""}


def test_identical_answers_on_two_turns_each_get_their_own_lines():
    first, _ = record(notebook.Notebook(), "Q1", "Same answer.", LYCEUM, prefix="a")
    second, _ = record(first, "Q2", "Same answer.", MORNING_DEW, prefix="b")
    conversation = [
        ConversationTurn(role="user", text="Q1"),
        ConversationTurn(role="assistant", text="Same answer."),
        ConversationTurn(role="user", text="Q2"),
        ConversationTurn(role="assistant", text="Same answer."),
    ]
    messages = notebook.transcript_with_notebook(second, conversation)
    assert [message.type for message in messages] == ["human", "ai", "human", "human", "ai", "human"]
    assert messages[2].content.startswith("Research notebook, turn 1:") and "get_show" in messages[2].content
    assert messages[5].content.startswith("Research notebook, turn 2:") and "get_song" in messages[5].content


def test_from_json_drops_entries_and_pages_with_malformed_fields():
    book, _ = record(notebook.Notebook(), "Q", "A", LYCEUM)
    data = book.to_json()
    data["entries"].append({**data["entries"][0], "key": "badids", "ids": None})
    data["entries"].append({**data["entries"][0], "key": "badurls", "urls": [1, 2]})
    data["entries"].append({**data["entries"][0], "key": "badpayload", "payload": "text"})
    data["pages"].append({**data["pages"][0], "turn": 2, "blocks": ["x"]})
    data["pages"].append({**data["pages"][0], "turn": 3, "chips": "chip"})
    restored = notebook.Notebook.from_json(data)
    assert [entry.key for entry in restored.entries] == [book.entries[0].key]
    assert [page.turn for page in restored.pages] == [1]


def test_entries_mentioning_returns_the_newest_matches():
    book, _ = record(
        notebook.Notebook(), "Q", "A",
        [("get_show", {"show_id_or_date": "1972-05-26"}), ("get_show", {"show_id_or_date": "gd-1972-05-26"})],
    )
    older, newer = book.entries
    assert notebook.entries_mentioning(book, ["gd-1972-05-26"], limit=1) == [newer]
    assert notebook.entries_mentioning(book, ["gd-1972-05-26"]) == [older, newer]


def _entry(index, *, last_read=1, summary=None, payload=None, tool="get_show"):
    return notebook.Entry(
        key=f"k{index:04d}", tool=tool, args={"n": index}, ids=[f"id-{index}"], urls=[],
        summary=summary or f"{tool} {index} · ~10 tok", tokens=10, turn=1, last_read=last_read, payload=payload,
    )


def test_a_notebook_survives_the_round_trip():
    book, _ = record(notebook.Notebook(), "Tell me about May 26, 1972.", "The last Lyceum night.", LYCEUM)
    token = notebook.encode(book, SECRET)
    assert token.startswith("v1.") and token.count(".") == 2
    assert notebook.decode(token, SECRET).to_json() == notebook.compact(book).to_json()


def test_a_changed_token_or_another_secret_reads_as_an_empty_notebook(caplog):
    book, _ = record(notebook.Notebook(), "Q", "A", LYCEUM)
    token = notebook.encode(book, SECRET)
    version, body, signature = token.split(".")
    swapped = "B" if body[20] == "A" else "A"
    tampered = f"{version}.{body[:20]}{swapped}{body[21:]}.{signature}"
    with caplog.at_level(logging.WARNING, logger="deadbot.notebook"):
        assert notebook.decode(tampered, SECRET).entries == []
        assert notebook.decode(token, "another-secret").entries == []
        assert notebook.decode("not a token", SECRET).entries == []
        assert notebook.decode("v1.\u00e9.\u00e9", SECRET).entries == []
    assert "signature" in caplog.text
    assert body[:40] not in caplog.text


def test_without_a_secret_turns_run_without_a_notebook_and_say_so_once(monkeypatch, caplog):
    monkeypatch.setattr(notebook, "_missing_secret_logged", False)
    with caplog.at_level(logging.WARNING, logger="deadbot.notebook"):
        assert notebook.encode(notebook.Notebook(turns=1), None) is None
        assert notebook.encode(notebook.Notebook(turns=1), "") is None
        assert notebook.decode("v1.x.y", None).entries == []
    assert caplog.text.count("DEADBOT_NOTEBOOK_SECRET is not set") == 1


def test_a_signed_token_that_inflates_past_the_ceiling_is_ignored():
    body = base64.urlsafe_b64encode(zlib.compress(b"[" + b"0," * 3_000_000 + b"0]", 9)).decode("ascii")
    token = f"{notebook.NOTEBOOK_VERSION}.{body}.{notebook._sign(body, SECRET)}"
    assert notebook.decode(token, SECRET).entries == []


def test_too_many_entries_compact_to_sixty_keeping_the_most_recently_read():
    book = notebook.Notebook(turns=1, entries=[_entry(index, last_read=index) for index in range(85)])
    compacted = notebook.compact(book)
    assert [entry.key for entry in compacted.entries] == [f"k{index:04d}" for index in range(25, 85)]


def test_long_index_lines_compact_below_the_token_target():
    book = notebook.Notebook(turns=1, entries=[_entry(index, last_read=index, summary="x" * 1000) for index in range(20)])
    compacted = notebook.compact(book)
    assert notebook.entry_tokens(compacted) <= notebook.INDEX_TOKEN_COMPACT_TO
    assert compacted.entries[-1].key == "k0019" and compacted.entries[0].key != "k0000"


def test_page_digests_keep_the_last_six_turns():
    book = notebook.Notebook(turns=9, pages=[notebook.PageDigest(turn=number, answer_key=f"a{number}", title="T") for number in range(1, 10)])
    assert [page.turn for page in notebook.compact(book).pages] == [4, 5, 6, 7, 8, 9]


def test_over_the_size_ceiling_web_payloads_go_first_least_recently_read():
    entries = [
        _entry(index, last_read=index + 1, tool="read_page", payload={"url": f"https://example.org/{index}", "text": os.urandom(30_000).hex()})
        for index in range(6)
    ]
    token = notebook.encode(notebook.Notebook(turns=6, entries=entries), SECRET)
    assert len(token) <= notebook.TOKEN_BYTE_CEILING
    kept = notebook.decode(token, SECRET)
    assert len(kept.entries) == 6
    assert kept.entries[0].payload is None
    assert kept.entries[-1].payload is not None
