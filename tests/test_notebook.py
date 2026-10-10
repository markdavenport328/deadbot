import json

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from deadbot import composition, notebook
from deadbot.experience import ConversationTurn
from deadbot.finish import build_experience_response
from notebook_support import LYCEUM, finish_messages, record, store

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
