from langchain_core.messages import AIMessageChunk

from deadbot.answer_stream import AnswerAccumulator, extract_chat_answer


def test_empty_string_has_no_answer_yet():
    assert extract_chat_answer("") == ("", False)


def test_text_before_the_key_appears_has_no_answer_yet():
    assert extract_chat_answer('{"title": "Ve') == ("", False)


def test_key_present_but_no_opening_quote_yet():
    assert extract_chat_answer('{"chat_answer"') == ("", False)
    assert extract_chat_answer('{"chat_answer" : ') == ("", False)


def test_a_partial_value_streams_as_far_as_generated():
    assert extract_chat_answer('{"chat_answer": "Veneta opened wi') == ("Veneta opened wi", False)


def test_escaped_quote_and_newline_are_resolved():
    raw = '{"chat_answer": "He said \\"hi\\" and\\nleft"'
    assert extract_chat_answer(raw) == ('He said "hi" and\nleft', True)


def test_unicode_escape_and_surrogate_pair_emoji():
    # U+1F600 (grinning face emoji) encoded as a UTF-16 surrogate pair.
    raw = '{"chat_answer": "Hi \\ud83d\\ude00"'
    assert extract_chat_answer(raw) == ("Hi \U0001F600", True)


def test_trailing_lone_backslash_is_held_back():
    raw = '{"chat_answer": "Veneta\\'
    assert extract_chat_answer(raw) == ("Veneta", False)


def test_trailing_partial_unicode_escape_is_held_back_then_completed():
    raw = '{"chat_answer": "Veneta \\u00'
    assert extract_chat_answer(raw) == ("Veneta ", False)
    completed = '{"chat_answer": "Veneta \\u00e9"'
    assert extract_chat_answer(completed) == ("Veneta é", True)


def test_completed_value_reports_complete_and_ignores_later_fields():
    raw = '{"chat_answer": "Veneta opened with Promised Land.", "title": "Veneta, 1972"'
    assert extract_chat_answer(raw) == ("Veneta opened with Promised Land.", True)


def test_chat_answer_as_the_second_key():
    raw = '{"title": "Veneta, 1972", "chat_answer": "Veneta opened wi'
    assert extract_chat_answer(raw) == ("Veneta opened wi", False)


def _chunk(*, name=None, args="", call_id="f1", index=0):
    tool_call_chunk = {"args": args, "id": call_id, "index": index}
    if name is not None:
        tool_call_chunk["name"] = name
    tool_call_chunk["type"] = "tool_call_chunk"
    return AIMessageChunk(content="", tool_call_chunks=[tool_call_chunk])


def test_accumulator_feeds_the_growing_answer_across_chunks():
    accumulator = AnswerAccumulator()
    first = accumulator.feed(_chunk(name="finish_response", args='{"chat_answer": "Ven'))
    assert first == "Ven"
    assert accumulator.complete is False

    second = accumulator.feed(_chunk(args="eta opened wi"))
    assert second == "Veneta opened wi"

    third = accumulator.feed(_chunk(args='th Promised Land."'))
    assert third == "Veneta opened with Promised Land."
    assert accumulator.complete is True


def test_accumulator_ignores_a_different_tool():
    accumulator = AnswerAccumulator()
    result = accumulator.feed(_chunk(name="get_show", args='{"show_id_or_date": "1972-08-27"'))
    assert result is None
    assert accumulator.complete is False


def test_accumulator_returns_none_when_nothing_grew():
    accumulator = AnswerAccumulator()
    accumulator.feed(_chunk(name="finish_response", args='{"chat_answer": "Ven'))
    result = accumulator.feed(_chunk(args=""))
    assert result is None
