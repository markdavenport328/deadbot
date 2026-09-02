from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from deadbot import graph
from deadbot.finish import FINISH_TOOL_NAME


def test_route_after_tools_ends_the_turn_once_the_response_is_delivered():
    calling = AIMessage(content="", tool_calls=[
        {"name": FINISH_TOOL_NAME, "args": {}, "id": "f1", "type": "tool_call"},
        {"name": "get_show", "args": {"show_id_or_date": "1972-08-27"}, "id": "t1", "type": "tool_call"},
    ])
    delivered = ToolMessage(content="Response delivered to the visitor.", tool_call_id="f1", name=FINISH_TOOL_NAME)
    other = ToolMessage(content="{}", tool_call_id="t1", name="get_show")
    # The finish result may not be the last message when the model issued
    # parallel tool calls; any finish result in the latest batch ends the turn.
    assert graph.route_after_tools({"messages": [HumanMessage(content="q"), calling, delivered, other]}) == graph.END
    assert graph.route_after_tools({"messages": [HumanMessage(content="q"), calling, other]}) == "agent"


def test_route_after_model_sends_tool_calls_to_tools_and_text_to_end():
    calling = AIMessage(content="", tool_calls=[{"name": "get_show", "args": {"show_id_or_date": "1972-08-27"}, "id": "t1", "type": "tool_call"}])
    assert graph.route_after_model({"messages": [calling]}) == "tools"
    assert graph.route_after_model({"messages": [AIMessage(content="plain text")]}) == graph.END


def test_agent_tools_include_finish_response():
    from deadbot.data import CanonicalStore

    names = {tool.name for tool in graph.agent_tools(CanonicalStore())}
    assert FINISH_TOOL_NAME in names and "get_show" in names


def test_prompt_is_one_persona_without_a_handoff():
    prompt = graph.SYSTEM_PROMPT.casefold()
    assert "finish_response" in prompt
    assert "editor" not in prompt and "handoff" not in prompt
