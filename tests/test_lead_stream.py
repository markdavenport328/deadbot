from langchain_core.messages import AIMessageChunk

from deadbot.lead_stream import LeadAccumulator, extract_lead


def test_empty_string_has_no_answer_yet():
    assert extract_lead("") == ("", False)


def test_text_before_the_key_appears_has_no_answer_yet():
    assert extract_lead('{"headline": "Ve') == ("", False)


def test_key_present_but_no_opening_quote_yet():
    assert extract_lead('{"lead"') == ("", False)
    assert extract_lead('{"lead" : ') == ("", False)


def test_a_partial_value_streams_as_far_as_generated():
    assert extract_lead('{"lead": "Veneta opened wi') == ("Veneta opened wi", False)


def test_escaped_quote_and_newline_are_resolved():
    raw = '{"lead": "He said \\"hi\\" and\\nleft"'
    assert extract_lead(raw) == ('He said "hi" and\nleft', True)


def test_unicode_escape_and_surrogate_pair_emoji():
    # U+1F600 (grinning face emoji) encoded as a UTF-16 surrogate pair.
    raw = '{"lead": "Hi \\ud83d\\ude00"'
    assert extract_lead(raw) == ("Hi \U0001F600", True)


def test_trailing_lone_backslash_is_held_back():
    raw = '{"lead": "Veneta\\'
    assert extract_lead(raw) == ("Veneta", False)


def test_trailing_partial_unicode_escape_is_held_back_then_completed():
    raw = '{"lead": "Veneta \\u00'
    assert extract_lead(raw) == ("Veneta ", False)
    completed = '{"lead": "Veneta \\u00e9"'
    assert extract_lead(completed) == ("Veneta é", True)


def test_bare_low_surrogate_is_replaced_rather_than_left_unpaired():
    raw = '{"lead": "Hi \\udc00 there"'
    answer, complete = extract_lead(raw)
    assert answer == "Hi � there"
    assert complete is True
    assert not any(0xD800 <= ord(char) <= 0xDFFF for char in answer)


def test_high_surrogate_without_a_matching_low_surrogate_is_replaced():
    raw = '{"lead": "Hi \\ud83dA"'
    answer, complete = extract_lead(raw)
    assert answer == "Hi �A"
    assert complete is True
    assert not any(0xD800 <= ord(char) <= 0xDFFF for char in answer)


def test_completed_value_reports_complete_and_ignores_later_fields():
    raw = '{"lead": "Veneta opened with Promised Land.", "headline": "Veneta, 1972"'
    assert extract_lead(raw) == ("Veneta opened with Promised Land.", True)


def test_lead_as_the_second_key():
    raw = '{"headline": "Veneta, 1972", "lead": "Veneta opened wi'
    assert extract_lead(raw) == ("Veneta opened wi", False)


def _chunk(*, name=None, args="", call_id="f1", index=0):
    tool_call_chunk = {"args": args, "id": call_id, "index": index}
    if name is not None:
        tool_call_chunk["name"] = name
    tool_call_chunk["type"] = "tool_call_chunk"
    return AIMessageChunk(content="", tool_call_chunks=[tool_call_chunk])


def test_accumulator_feeds_the_growing_answer_across_chunks():
    accumulator = LeadAccumulator()
    first = accumulator.feed(_chunk(name="finish_response", args='{"lead": "Ven'))
    assert first == "Ven"
    assert accumulator.complete is False

    second = accumulator.feed(_chunk(args="eta opened wi"))
    assert second == "Veneta opened wi"

    third = accumulator.feed(_chunk(args='th Promised Land."'))
    assert third == "Veneta opened with Promised Land."
    assert accumulator.complete is True


def test_accumulator_ignores_a_different_tool():
    accumulator = LeadAccumulator()
    result = accumulator.feed(_chunk(name="get_show", args='{"show_id_or_date": "1972-08-27"'))
    assert result is None
    assert accumulator.complete is False


def test_accumulator_returns_none_when_nothing_grew():
    accumulator = LeadAccumulator()
    accumulator.feed(_chunk(name="finish_response", args='{"lead": "Ven'))
    result = accumulator.feed(_chunk(args=""))
    assert result is None


def test_a_group_lead_is_not_mistaken_for_the_top_level_lead():
    groups_first = '{"groups": [{"lead": "A group intro", "items": []}], "lead": "The page lead"'
    assert extract_lead(groups_first) == ("The page lead", True)
    only_group = '{"initial_tab": "read", "headline": "H", "groups": [{"title": "T", "lead": "A group intro'
    assert extract_lead(only_group) == ("", False)
    after = '{"lead": "The page lead", "groups": [{"lead": "A group intro", "items": []}]}'
    assert extract_lead(after) == ("The page lead", True)


def test_a_value_that_reads_like_a_key_does_not_start_the_lead():
    raw = '{"headline": "\\"lead\\": \\"fake", "lead": "Real'
    assert extract_lead(raw) == ("Real", False)


def test_the_accumulator_streams_only_the_top_level_lead():
    accumulator = LeadAccumulator()
    pieces = ['{"lead": "Ven', 'eta.", "groups": [{"lead": "Intro', ' text", "items": []}]}']
    seen = [accumulator.feed(_chunk(name="finish_response" if i == 0 else None, args=piece)) for i, piece in enumerate(pieces)]
    assert seen == ["Ven", "Veneta.", None]
    assert accumulator.complete
