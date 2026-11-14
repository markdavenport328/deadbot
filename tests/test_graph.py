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
        content="Error invoking tool 'finish_response' with kwargs {} with error:\n lead: Field required",
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


PALETTE = (
    "song_versions", "version_strip", "show_unit", "performance_unit", "album_unit", "song_overview",
    "era_unit", "data_chart", "ranked_list", "grid", "listening_hero", "editorial", "pull_quote",
    "person_roster", "guest_appearance_list", "equipment_list", "show_selection", "arrangement",
    "arrangement_search", "media_link", "resource_list",
)
ROUTES = (
    "search_entities", "get_song", "get_song_life", "get_song_notable_versions", "list_song_performances",
    "get_show", "get_performance", "get_album", "get_segue_pairing", "get_grid", "look_up", "aggregate_data",
    "search_guest_musicians", "get_recording_reviews", "search_site", "read_page", "read_notebook",
)


def _prompt() -> str:
    return " ".join(graph.SYSTEM_PROMPT.split())


def test_prompt_gives_the_visitors_the_goal_the_writer_and_the_tools():
    for heading in ("## THE VISITORS", "## THE GOAL", "## THE WRITER", "## RESEARCH TOOLS", "## PAGE COMPONENTS"):
        assert heading in graph.SYSTEM_PROMPT


def test_prompt_names_the_finish_tool_and_the_page_fields():
    prompt = _prompt()
    assert "call finish_response once" in prompt
    for field in ("headline", "lead", "initial_tab"):
        assert field in prompt


def test_prompt_names_every_component_and_research_tool():
    prompt = _prompt()
    for name in (*PALETTE, *ROUTES):
        assert name in prompt, name


def test_prompt_grounds_ids_in_this_turn_or_the_notebook():
    prompt = _prompt()
    assert "IDs from a tool result in this turn or from the research notebook" in prompt
    assert "Quote aggregate_data numbers exactly as returned" in prompt


def test_prompt_is_written_affirmatively():
    folded = graph.SYSTEM_PROMPT.casefold()
    for phrase in ("do not", "don't", "never", "avoid"):
        assert phrase not in folded, phrase


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
        "args": {"lead": "Hi", "groups": []},
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


def test_a_streamed_finish_call_keeps_both_groups_lists():
    from langchain_core.messages import AIMessageChunk

    from deadbot.graph import repair_finish_arguments

    first = AIMessageChunk(content="", tool_call_chunks=[{"name": "finish_response", "args": '{"title": "t", "groups": [{"title": "One"}],', "id": "c1", "index": 0}])
    rest = AIMessageChunk(content="", tool_call_chunks=[{"name": None, "args": ' "groups": [{"title": "Two"}]}', "id": None, "index": 0}])
    message = repair_finish_arguments(first + rest)
    assert [group["title"] for group in message.tool_calls[0]["args"]["groups"]] == ["One", "Two"]
    assert message.tool_calls[0]["id"] == "c1"


_SEEN_KWARGS: list[dict] = []


class _RecordingFakeChatModel(_BindableFakeChatModel):
    def _generate(self, messages, stop=None, run_manager=None, **kwargs):
        _SEEN_KWARGS.append(dict(kwargs))
        return super()._generate(messages, stop=stop, run_manager=run_manager, **kwargs)


def _model_kwargs_for_one_call(settings):
    class FakeProvider:
        def create_chat_model(self):
            return _RecordingFakeChatModel(responses=[AIMessage(content="hi")])

    compiled = graph.build_agent(settings, store=CanonicalStore(), provider=FakeProvider())
    _SEEN_KWARGS.clear()
    compiled.invoke(
        {"messages": [HumanMessage(content="hello")]},
        graph.run_config("web-1:request:x", settings, prompt_cache_key="web-1"),
    )
    return _SEEN_KWARGS[-1]


def test_openai_calls_carry_the_conversation_as_the_prompt_cache_key():
    assert _model_kwargs_for_one_call(Settings(model_provider="openai"))["prompt_cache_key"] == "web-1"


def test_other_providers_get_no_prompt_cache_key():
    assert "prompt_cache_key" not in _model_kwargs_for_one_call(Settings())


def test_run_config_carries_the_notebook_only_when_given():
    assert "notebook" not in graph.run_config("t", Settings())["configurable"]
    assert graph.run_config("t", Settings(), notebook="book")["configurable"]["notebook"] == "book"
