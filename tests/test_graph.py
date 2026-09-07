from langchain_core.language_models.fake_chat_models import FakeMessagesListChatModel
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langgraph.graph import END, START, MessagesState, StateGraph
from langgraph.prebuilt import ToolNode

from deadbot import graph
from deadbot.config import Settings
from deadbot.data import CanonicalStore
from deadbot.finish import FINISH_TOOL_NAME, build_finish_tool


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


def test_route_after_tools_returns_to_agent_when_finish_response_errored():
    calling = AIMessage(content="", tool_calls=[
        {"name": FINISH_TOOL_NAME, "args": {}, "id": "f1", "type": "tool_call"},
    ])
    errored = ToolMessage(
        content="Error invoking tool 'finish_response' with kwargs {} with error:\n chat_answer: Field required",
        tool_call_id="f1",
        name=FINISH_TOOL_NAME,
        status="error",
    )
    assert graph.route_after_tools({"messages": [HumanMessage(content="q"), calling, errored]}) == "agent"


def test_route_after_model_sends_tool_calls_to_tools_and_text_to_end():
    calling = AIMessage(content="", tool_calls=[{"name": "get_show", "args": {"show_id_or_date": "1972-08-27"}, "id": "t1", "type": "tool_call"}])
    assert graph.route_after_model({"messages": [calling]}) == "tools"
    assert graph.route_after_model({"messages": [AIMessage(content="plain text")]}) == graph.END


def test_agent_tools_include_finish_response():
    names = {tool.name for tool in graph.agent_tools(CanonicalStore())}
    assert FINISH_TOOL_NAME in names and "get_show" in names


def test_prompt_names_the_finish_tool():
    prompt = graph.SYSTEM_PROMPT.casefold()
    assert "finish_response" in prompt


def test_prompt_teaches_semantic_units_and_grouping_by_meaning():
    prompt = graph.SYSTEM_PROMPT
    unwrapped = " ".join(prompt.split())
    for unit in ("show_unit", "show_explorer", "performance_unit", "era_unit"):
        assert unit in prompt
    assert "Group by meaning and referent, not by tool, source or data type." in unwrapped
    assert "Tool boundaries and database tables are not presentation boundaries." in unwrapped
    assert '"Ask" chip' in unwrapped
    assert "Setlist songs, performances and semantic units retain the verified actions attached to them" in unwrapped
    # The research personality is preserved.
    for heading in ("## RESEARCH THE ACTUAL QUESTION", "# PRESERVE DISCOVERY", "# TRUST"):
        assert heading in prompt


def test_prompt_makes_chat_and_main_body_connected_independent_reading_paths():
    prompt = " ".join(graph.SYSTEM_PROMPT.split())
    assert "## ANSWER FIRST, THEN EARN THE REST" in graph.SYSTEM_PROMPT
    assert "chat_answer and the main body express one researched editorial judgment at different scales." in prompt
    assert "A visitor who begins with either reading path can understand the finding" in prompt
    assert "When you recommend or name a specific performance, provide its listening path" in prompt
    assert "Sugar Magnolia: the album's biggest live life" in prompt
    assert "Do not create one for every related song merely because its metadata is available." in prompt


def test_prompt_requires_priority_actions_and_proportionate_scope():
    prompt = " ".join(graph.SYSTEM_PROMPT.split())
    assert "## EDIT FOR THIS QUESTION" in graph.SYSTEM_PROMPT
    assert "A factual question can still deserve commentary and rich actions" in prompt
    assert "Build on a factual spine" in prompt
    assert "When you recommend or name a specific performance, provide its listening path" in prompt
    assert "prefer the venue or place name people recognize" in prompt
    assert "one or two across the whole page" not in prompt
    assert "perform an omission pass" not in prompt
    for job in ("unit formation", "grouping", "completion", "segregation", "global organization"):
        assert job in prompt.casefold()


def test_persona_tells_the_model_that_albums_are_held():
    from deadbot.graph import SYSTEM_PROMPT  # use the module's actual prompt constant

    assert "album" in SYSTEM_PROMPT.casefold()
    assert "get_album" in SYSTEM_PROMPT


def _run_tool_node(node: ToolNode, ai_message: AIMessage) -> list:
    """Invoke a ToolNode the way the real graph does: through a compiled graph,
    since ToolNode.invoke on its own raises for missing LangGraph runtime config.
    """

    builder = StateGraph(MessagesState)
    builder.add_node("tools", node)
    builder.add_edge(START, "tools")
    builder.add_edge("tools", END)
    compiled = builder.compile()
    return compiled.invoke({"messages": [ai_message]})["messages"]


def test_tool_node_finish_results_drive_the_router():
    node = ToolNode([build_finish_tool()])

    valid_call = AIMessage(content="", tool_calls=[{
        "name": FINISH_TOOL_NAME,
        "args": {"chat_answer": "Hi", "title": "T", "lead": None, "mode": "quick_fact", "body": []},
        "id": "f1",
        "type": "tool_call",
    }])
    valid_messages = [valid_call, *_run_tool_node(node, valid_call)]
    valid_result = valid_messages[-1]
    assert valid_result.name == FINISH_TOOL_NAME
    assert getattr(valid_result, "status", None) != "error"
    assert graph.route_after_tools({"messages": valid_messages}) == graph.END

    invalid_call = AIMessage(content="", tool_calls=[{
        "name": FINISH_TOOL_NAME,
        "args": {},
        "id": "f2",
        "type": "tool_call",
    }])
    try:
        invalid_messages = [invalid_call, *_run_tool_node(node, invalid_call)]
    except Exception as error:  # pragma: no cover - depends on installed langgraph
        # On some langgraph versions ToolNode raises for invalid args instead of
        # emitting an error ToolMessage; this installed version emits a
        # status="error" message instead (verified manually), but guard the
        # assumption so a version change reports clearly rather than failing
        # confusingly.
        raise AssertionError(
            f"ToolNode raised on invalid finish_response args instead of emitting an error message: {error!r}"
        ) from error
    invalid_result = invalid_messages[-1]
    assert getattr(invalid_result, "status", None) == "error"
    assert graph.route_after_tools({"messages": invalid_messages}) == "agent"


class _BindableFakeChatModel(FakeMessagesListChatModel):
    """FakeMessagesListChatModel has no bind_tools; build_agent calls it, so
    this subclass makes bind_tools a no-op returning self for the test.
    """

    def bind_tools(self, tools, **kwargs):
        return self


def test_build_agent_compiles_with_a_fake_provider():
    class FakeProvider:
        def create_chat_model(self):
            return _BindableFakeChatModel(responses=[AIMessage(content="hi")])

    compiled = graph.build_agent(Settings(), store=CanonicalStore(), provider=FakeProvider())
    assert compiled is not None
