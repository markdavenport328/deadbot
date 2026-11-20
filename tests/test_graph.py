import datetime
import json
import os
import subprocess
import sys
import time

import pytest
from langchain_core.language_models.fake_chat_models import FakeMessagesListChatModel
from langchain_core.messages import AIMessage, AIMessageChunk, HumanMessage, ToolMessage
from langchain_core.outputs import ChatGenerationChunk
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


PALETTE = ("performances", "pairing", "show", "shows", "release", "releases", "song_years", "chart", "grid", "people", "links")
ROUTES = (
    "search_entities", "get_song", "get_song_life", "get_song_notable_versions", "list_song_performances",
    "get_show", "get_performance", "get_album", "get_segue_pairing", "get_grid", "look_up", "aggregate_data",
    "search_guest_musicians", "get_picks", "get_recording_reviews", "search_stories", "read_page", "search_site",
    "get_historical_weather", "get_equipment_history", "find_arrangements", "read_notebook",
)


def _prompt() -> str:
    return " ".join(graph.SYSTEM_PROMPT.split())


def test_prompt_gives_the_visitors_the_goal_the_writer_and_the_tools():
    for heading in ("## THE VISITORS", "## THE GOAL", "## THE WRITER", "## TOOLS", "## THE PAGE"):
        assert heading in graph.SYSTEM_PROMPT


def test_prompt_names_the_finish_tool_and_the_page_fields():
    prompt = _prompt()
    assert "call finish_response once" in prompt
    for field in ("headline", "the answer", "sections"):
        assert field in prompt


def test_prompt_names_every_component_and_research_tool():
    prompt = _prompt()
    for name in (*PALETTE, *ROUTES):
        assert f"- {name}" in prompt, name


def test_prompt_tools_are_the_agent_tools():
    # look_up needs the SQLite store; the CSV store builds every other tool.
    names = {tool.name for tool in graph.agent_tools(CanonicalStore())} - {FINISH_TOOL_NAME}
    assert names == set(ROUTES) - {"look_up"}


def test_prompt_components_are_the_page_items():
    from typing import get_args

    from deadbot.page_plan import PageItem

    union = get_args(PageItem)[0]
    kinds = {get_args(model.model_fields["type"].annotation)[0] for model in get_args(union)}
    assert kinds == set(PALETTE)


def test_prompt_grounds_ids_in_this_turn_or_the_notebook():
    prompt = _prompt()
    assert "IDs from a tool result in this turn or from the notebook" in prompt
    assert "Quote counts exactly as the tools return them" in prompt


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
        "args": {"answer": "Hi", "sections": []},
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

    def _stream(self, messages, stop=None, run_manager=None, **kwargs):
        _SEEN_KWARGS.append(dict(kwargs))
        yield ChatGenerationChunk(message=AIMessageChunk(content="hi"))


def _model_kwargs_for_one_call(settings, **config):
    class FakeProvider:
        def create_chat_model(self):
            return _RecordingFakeChatModel(responses=[AIMessage(content="hi")])

    compiled = graph.build_agent(settings, store=CanonicalStore(), provider=FakeProvider())
    _SEEN_KWARGS.clear()
    compiled.invoke(
        {"messages": [HumanMessage(content="hello")]},
        graph.run_config("web-1:request:x", settings, conversation_id="web-1", **config),
    )
    return _SEEN_KWARGS[-1]


def test_openai_calls_carry_the_shared_prompt_cache_key():
    assert _model_kwargs_for_one_call(Settings(model_provider="openai"))["prompt_cache_key"] == "deadbot"


def test_other_providers_get_no_prompt_cache_key():
    assert "prompt_cache_key" not in _model_kwargs_for_one_call(Settings())


def test_every_visitor_gets_the_same_prompt_cache_key():
    settings = Settings()
    keys = {graph.prompt_cache_key(f"web-{number}", settings) for number in range(50)}
    assert keys == {"deadbot"}


def test_sharded_keys_keep_a_conversation_on_one_key_and_spread_conversations():
    settings = Settings(prompt_cache_shards=4)
    keys = {graph.prompt_cache_key(f"web-{number}", settings) for number in range(200)}
    assert keys == {"deadbot-0", "deadbot-1", "deadbot-2", "deadbot-3"}
    # The request's throwaway thread never picks the key; the conversation does.
    first = graph.run_config("web-7:request:a", settings, conversation_id="web-7")
    second = graph.run_config("web-7:request:b", settings, conversation_id="web-7")
    assert first["configurable"]["prompt_cache_key"] == second["configurable"]["prompt_cache_key"]


def _openai_request(question, conversation_id, settings=None):
    """The request body langchain-openai would send for one visitor's first call. Nothing is sent."""

    langchain_openai = pytest.importorskip("langchain_openai")
    settings = settings or Settings(model_provider="openai", openai_model="gpt-5.6-luna", openai_reasoning_effort="low")
    model = langchain_openai.ChatOpenAI(
        model=settings.openai_model, use_responses_api=True, api_key="not-a-real-key",
        reasoning={"effort": settings.openai_reasoning_effort},
    )
    bound = model.bind_tools(graph.agent_tools(CanonicalStore()))
    config = graph.run_config(f"{conversation_id}:request:x", settings, conversation_id=conversation_id)
    system = graph.system_message(explicit_breakpoint=settings.prompt_cache_breakpoint)
    return model._get_request_payload(
        [system, HumanMessage(content=question)], **bound.kwargs, **graph._cache_options(config)
    )


def test_two_visitors_first_calls_share_a_byte_identical_static_prefix():
    one = _openai_request("How many times did they play Madison Square Garden?", "web-visitor-one")
    two = _openai_request("Find me an overlooked Sugaree", "web-visitor-two")

    def static(payload):
        # Everything ahead of the visitor's own words: settings, tool schemas in order, the system prompt.
        body = {key: value for key, value in payload.items() if key != "input"}
        return json.dumps([body, payload["input"][0]], ensure_ascii=False)

    assert static(one) == static(two)
    assert one["prompt_cache_key"] == two["prompt_cache_key"] == "deadbot"
    assert one["input"][1:] != two["input"][1:]
    assert [tool["name"] for tool in one["tools"]][-1] == FINISH_TOOL_NAME
    # No date, request id or thread id rides in the prefix.
    for needle in ("web-visitor", "request:", str(datetime.date.today().year)):
        assert needle not in static(one)


def test_the_static_prefix_does_not_depend_on_the_process():
    # Set and dict ordering change with the hash seed; the prefix must not.
    pytest.importorskip("langchain_openai")
    script = (
        "import hashlib, json;"
        "from tests.test_graph import _openai_request;"
        "p = _openai_request('q', 'web-1');"
        "print(hashlib.sha256(json.dumps([p['tools'], p['input'][0]], ensure_ascii=False).encode()).hexdigest())"
    )
    digests = set()
    for seed in ("1", "2"):
        env = {**os.environ, "PYTHONHASHSEED": seed, "PYTHONPATH": os.getcwd()}
        digests.add(subprocess.run([sys.executable, "-c", script], env=env, capture_output=True, text=True, check=True).stdout.strip())
    assert len(digests) == 1


def test_the_explicit_breakpoint_marks_the_end_of_the_system_prompt_only_when_asked():
    plain = _openai_request("q", "web-1")
    assert plain["input"][0]["content"] == graph.SYSTEM_PROMPT
    marked = _openai_request("q", "web-1", Settings(
        model_provider="openai", openai_model="gpt-5.6-luna", openai_reasoning_effort="low", prompt_cache_breakpoint=True,
    ))
    block = marked["input"][0]["content"][-1]
    assert block["text"] == graph.SYSTEM_PROMPT
    assert block["prompt_cache_breakpoint"] == {"mode": "explicit"}


def test_a_late_model_call_waits_no_longer_than_the_turn_has_left():
    settings = Settings(model_provider="openai", model_timeout_seconds=25)
    assert "timeout" not in _model_kwargs_for_one_call(settings)
    streaming = Settings(model_provider="openai", model_timeout_seconds=25, model_streaming=True)
    plenty = _model_kwargs_for_one_call(streaming, deadline=time.monotonic() + 500)
    assert plenty["timeout"] == 25
    short = _model_kwargs_for_one_call(streaming, deadline=time.monotonic() + 10)
    assert 0 < short["timeout"] <= 10


def test_a_turn_out_of_time_stops_before_paying_for_another_model_call():
    settings = Settings(model_provider="openai", model_streaming=True)
    _SEEN_KWARGS.clear()
    with pytest.raises(graph.TurnBudgetExceeded):
        _model_kwargs_for_one_call(settings, deadline=time.monotonic() + 1)
    assert _SEEN_KWARGS == []


def test_run_config_carries_the_notebook_only_when_given():
    assert "notebook" not in graph.run_config("t", Settings())["configurable"]
    assert graph.run_config("t", Settings(), notebook="book")["configurable"]["notebook"] == "book"
