from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from deadbot import progress


def test_tool_calls_become_visitor_facing_status_lines():
    assert progress.describe_tool_call("search_entities", {"query": "Branford Marsalis"}) == "Searching the library for “Branford Marsalis”"
    assert progress.describe_tool_call("get_show", {"show_id_or_date": "1990-03-29"}) == "Reading the show on 1990-03-29"
    assert progress.describe_tool_call("search_site", {"site": "Dead Essays", "query": "Branford"}) == "Searching Dead Essays for “Branford”"
    assert progress.describe_tool_call("read_page", {"url": "https://www.dead.net/features/x"}) == "Reading dead.net"
    assert progress.describe_tool_call("get_recording_reviews", {"recording": "1977-05-08"}) == "Checking listener reviews of the recordings"
    assert progress.describe_tool_call("finish_response", {}) == "Composing the answer"
    # Unknown tools still read as words, never as identifiers.
    assert progress.describe_tool_call("get_something_new", None) == "Get something new"


def test_status_lines_cover_only_new_tool_calls():
    messages = [
        HumanMessage(content="q"),
        AIMessage(content="", tool_calls=[{"name": "get_show", "args": {"show_id_or_date": "1972-08-27"}, "id": "t1", "type": "tool_call"}]),
        ToolMessage(content="{}", tool_call_id="t1", name="get_show"),
        AIMessage(content="", tool_calls=[
            {"name": "read_page", "args": {"url": "https://deadessays.blogspot.com/x"}, "id": "t2", "type": "tool_call"},
            {"name": "finish_response", "args": {}, "id": "f1", "type": "tool_call"},
        ]),
    ]
    assert list(progress.status_lines(messages, 0)) == ["Reading the show on 1972-08-27", "Reading deadessays.blogspot.com", "Composing the answer"]
    assert list(progress.status_lines(messages, 3)) == ["Reading deadessays.blogspot.com", "Composing the answer"]
    assert list(progress.status_lines(messages, len(messages))) == []
