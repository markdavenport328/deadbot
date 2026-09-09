import json

import pytest
from fastapi.testclient import TestClient
from langchain_core.messages import AIMessage, AIMessageChunk, HumanMessage, ToolMessage
from pydantic import ValidationError

from deadbot import experience
from deadbot.api import create_app
from deadbot.composition import _embed_details
from deadbot.config import Settings
from deadbot.data import CanonicalStore
from deadbot.experience import ExperienceResponse


def finish_call(chat_answer, *, title="Deadbot", lead=None, groups=None):
    """The two messages a finished agent turn ends with: the call and its result."""

    plan = {"chat_answer": chat_answer, "title": title, "lead": lead, "groups": groups or []}
    return [
        AIMessage(content="", tool_calls=[{"name": "finish_response", "args": plan, "id": "f1", "type": "tool_call"}]),
        ToolMessage(content="Response delivered to the visitor.", tool_call_id="f1", name="finish_response"),
    ]


class FakeAgent:
    def __init__(self, messages):
        self.messages = messages
        self.calls = []

    def invoke(self, payload, config):
        self.calls.append((payload, config))
        return {"messages": self.messages}


class ConversationFakeAgent:
    """Small stateful stand-in for LangGraph's checkpointed agent in API tests."""

    def __init__(self):
        self.messages = []
        self.calls = []

    def invoke(self, payload, config):
        self.calls.append((payload, config))
        question = payload["messages"][-1].content
        plan = {"chat_answer": f"Reply to: {question}", "title": "Deadbot", "lead": None, "groups": []}
        self.messages.extend([
            HumanMessage(content=question),
            AIMessage(content="", tool_calls=[{"name": "finish_response", "args": plan, "id": "f1", "type": "tool_call"}]),
            ToolMessage(content="Response delivered to the visitor.", tool_call_id="f1", name="finish_response"),
        ])
        return {"messages": self.messages}


class FakeCheckpointer:
    """Stand-in for LangGraph's MemorySaver that records delete_thread calls."""

    def __init__(self):
        self.deleted_threads = []

    def delete_thread(self, thread_id):
        self.deleted_threads.append(thread_id)


def tool_message(payload):
    return ToolMessage(content=json.dumps(payload), tool_call_id="tool-call")


def test_only_recognized_provider_urls_receive_embed_identifiers():
    assert _embed_details("youtube", "https://www.youtube.com/watch?v=Ip48SfRx4ho") == ("youtube", "Ip48SfRx4ho")
    assert _embed_details("spotify", "https://open.spotify.com/album/1E4MXxSYoAMN5qpy1y6aBm") == ("spotify", "album/1E4MXxSYoAMN5qpy1y6aBm")
    assert _embed_details("youtube", "https://example.com/watch?v=Ip48SfRx4ho") == (None, None)


def test_schema_rejects_an_unrecognized_browser_block():
    try:
        ExperienceResponse.model_validate(
            {
                "thread_id": "web-test",
                "title": "Test",
                "answer": "Test",
                "blocks": [{"type": "raw_html", "html": "<script>bad()</script>"}],
            }
        )
    except ValidationError:
        pass
    else:
        raise AssertionError("Unknown experience blocks must be rejected")


def test_experience_endpoint_renders_the_finish_plan():
    store = CanonicalStore()
    show = store.resolve_show("1972-08-27")
    plan = {
        "chat_answer": "Veneta opened with Promised Land.",
        "title": "Veneta, 1972",
        "lead": None,
        "groups": [{"presentation": "collection", "items": [{"type": "show_unit", "show_id": "gd-1972-08-27", "title": "The whole night", "visible_facets": ["setlist"]}]}],
    }
    agent = FakeAgent([
        HumanMessage(content="What opened Veneta?"),
        tool_message(store.show_context(show)),
        AIMessage(content="", tool_calls=[{"name": "finish_response", "args": plan, "id": "f1", "type": "tool_call"}]),
        ToolMessage(content="Response delivered to the visitor.", tool_call_id="f1", name="finish_response"),
    ])
    client = TestClient(create_app(settings=Settings(), store=store, agent=agent))
    body = client.post("/api/experience", json={"question": "What opened Veneta?"}).json()
    assert body["title"] == "Veneta, 1972"
    assert body["blocks"][0]["type"] == "show_unit" and body["blocks"][0]["title"] == "The whole night"
    assert body["conversation"][-1] == {"role": "assistant", "text": "Veneta opened with Promised Land."}


def test_experience_endpoint_renders_a_show_unit_through_a_group():
    store = CanonicalStore()
    show = store.resolve_show("1972-08-27")
    payload = store.show_context(show)
    plan = {
        "chat_answer": "One show, as a unit.",
        "title": "Veneta as a unit",
        "lead": None,
        "groups": [
            {
                "presentation": "collection",
                "title": "The show",
                "items": [{
                    "type": "show_unit",
                    "show_id": "gd-1972-08-27",
                    "emphasis": "primary",
                    "note": "One frame, everything about it.",
                    "visible_facets": ["setlist", "listen"],
                }],
            }
        ],
    }
    agent = FakeAgent([
        HumanMessage(content="Tell me about Veneta"),
        tool_message(payload),
        AIMessage(content="", tool_calls=[{"name": "finish_response", "args": plan, "id": "f1", "type": "tool_call"}]),
        ToolMessage(content="Response delivered to the visitor.", tool_call_id="f1", name="finish_response"),
    ])
    client = TestClient(create_app(settings=Settings(), store=store, agent=agent))
    body = client.post("/api/experience", json={"question": "Tell me about Veneta"}).json()
    unit = body["blocks"][0]
    assert unit["type"] == "show_unit" and unit["show_date"] == "1972-08-27" and unit["emphasis"] == "primary"
    assert unit["sets"] and unit["listen"]
    assert body["groups"][0]["title"] == "The show"
    # The response still validates against the browser contract.
    ExperienceResponse.model_validate(body)


class StreamingFakeAgent(FakeAgent):
    """Yields the growing message list the way LangGraph's ``stream`` does with
    stream_mode="values", ignoring the ``["values", "messages"]`` mode list the
    application now requests -- exactly like an agent with no ``messages``
    support, which ``_stream_events`` must still treat as a stream of ``values``
    states.
    """

    def stream(self, payload, config, stream_mode="values"):
        self.calls.append((payload, config))
        assert stream_mode == ["values", "messages"]
        for end in range(1, len(self.messages) + 1):
            yield {"messages": self.messages[:end]}


class AnswerStreamingFakeAgent(FakeAgent):
    """Interleaves ``("messages", (AIMessageChunk, metadata))`` tool-call-argument
    fragments for ``finish_response`` with ``("values", state)`` steps, the way
    LangGraph's ``stream`` does for ``stream_mode=["values", "messages"]``.
    """

    def stream(self, payload, config, stream_mode="values"):
        self.calls.append((payload, config))
        assert stream_mode == ["values", "messages"]
        yield ("values", {"messages": self.messages[:2]})
        fragments = [
            '{"chat_answer": "Veneta ',
            'opened with ',
            'Promised Land."',
            ', "title": "Veneta, 1972"}',
        ]
        for index, fragment in enumerate(fragments):
            chunk = AIMessageChunk(
                content="",
                tool_call_chunks=[
                    {
                        "name": "finish_response" if index == 0 else None,
                        "args": fragment,
                        "id": "f1",
                        "index": 0,
                        "type": "tool_call_chunk",
                    }
                ],
            )
            yield ("messages", (chunk, {}))
        yield ("values", {"messages": self.messages})


class SurrogateStreamingFakeAgent(FakeAgent):
    """Streams a ``finish_response`` tool-call-argument fragment carrying an
    actual lone low surrogate character (not a ``\\u`` escape sequence, so
    ``extract_chat_answer`` passes it straight through unmodified) so the
    ``answer`` event reaching ``line()`` in ``api.py`` is the one holding
    the unpaired surrogate -- this exercises that layer's own defense
    (``.encode("utf-8", "replace")``) independent of the extractor's.
    """

    def stream(self, payload, config, stream_mode="values"):
        self.calls.append((payload, config))
        assert stream_mode == ["values", "messages"]
        yield ("values", {"messages": self.messages[:1]})
        chunk = AIMessageChunk(
            content="",
            tool_call_chunks=[
                {
                    "name": "finish_response",
                    "args": '{"chat_answer": "Hi \udc00 there", "title": "Deadbot"}',
                    "id": "f1",
                    "index": 0,
                    "type": "tool_call_chunk",
                }
            ],
        )
        yield ("messages", (chunk, {}))
        yield ("values", {"messages": self.messages})


def _ndjson(text):
    return [json.loads(line) for line in text.splitlines() if line.strip()]


def test_streaming_endpoint_reports_each_tool_call_then_the_response():
    store = CanonicalStore()
    show = store.resolve_show("1972-08-27")
    plan = {"chat_answer": "Veneta opened with Promised Land.", "title": "Veneta, 1972", "lead": None,
            "groups": [{"presentation": "collection", "items": [{"type": "show_unit", "show_id": "gd-1972-08-27", "visible_facets": ["setlist"]}]}]}
    agent = StreamingFakeAgent([
        HumanMessage(content="What opened Veneta?"),
        AIMessage(content="", tool_calls=[{"name": "get_show", "args": {"show_id_or_date": "1972-08-27"}, "id": "t1", "type": "tool_call"}]),
        ToolMessage(content=json.dumps(store.show_context(show)), tool_call_id="t1", name="get_show"),
        AIMessage(content="", tool_calls=[{"name": "finish_response", "args": plan, "id": "f1", "type": "tool_call"}]),
        ToolMessage(content="Response delivered to the visitor.", tool_call_id="f1", name="finish_response"),
    ])
    client = TestClient(create_app(settings=Settings(), store=store, agent=agent))
    result = client.post("/api/experience/stream", json={"question": "What opened Veneta?", "thread_id": "browser-1"})
    assert result.status_code == 200
    assert result.headers["content-type"].startswith("application/x-ndjson")
    events = _ndjson(result.text)
    assert [event["type"] for event in events] == ["status", "status", "response"]
    assert [event["text"] for event in events[:2]] == ["Reading the show on 1972-08-27", "Assembling the page"]
    response = ExperienceResponse.model_validate(events[-1]["response"])
    assert response.title == "Veneta, 1972" and response.blocks[0].type == "show_unit"
    assert agent.calls[0][1]["configurable"]["thread_id"] == "browser-1"


def test_streaming_endpoint_streams_the_chat_answer_as_it_is_generated():
    store = CanonicalStore()
    plan = {"chat_answer": "Veneta opened with Promised Land.", "title": "Veneta, 1972", "lead": None,
            "groups": [{"presentation": "collection", "items": [{"type": "show_unit", "show_id": "gd-1972-08-27", "visible_facets": ["setlist"]}]}]}
    agent = AnswerStreamingFakeAgent([
        HumanMessage(content="What opened Veneta?"),
        AIMessage(content="", tool_calls=[{"name": "finish_response", "args": plan, "id": "f1", "type": "tool_call"}]),
        ToolMessage(content="Response delivered to the visitor.", tool_call_id="f1", name="finish_response"),
    ])
    client = TestClient(create_app(settings=Settings(), store=store, agent=agent))
    result = client.post("/api/experience/stream", json={"question": "What opened Veneta?", "thread_id": "browser-1"})
    assert result.status_code == 200
    events = _ndjson(result.text)

    answer_events = [event for event in events if event["type"] == "answer"]
    response_index = next(index for index, event in enumerate(events) if event["type"] == "response")
    assert len(answer_events) >= 2
    assert all(events.index(event) < response_index for event in answer_events)

    answer_texts = [event["text"] for event in answer_events]
    for earlier, later in zip(answer_texts, answer_texts[1:]):
        assert later.startswith(earlier)

    response = ExperienceResponse.model_validate(events[response_index]["response"])
    assert answer_texts[-1] == response.answer


def test_streaming_endpoint_announces_page_composition_once_the_chat_answer_completes():
    """Once the chat answer has fully streamed, the browser should learn the
    rest of the page (blocks, links, etc.) is still being put together, once
    and only once, before the final response arrives.
    """
    store = CanonicalStore()
    plan = {"chat_answer": "Veneta opened with Promised Land.", "title": "Veneta, 1972", "lead": None,
            "groups": [{"presentation": "collection", "items": [{"type": "show_unit", "show_id": "gd-1972-08-27", "visible_facets": ["setlist"]}]}]}
    agent = AnswerStreamingFakeAgent([
        HumanMessage(content="What opened Veneta?"),
        AIMessage(content="", tool_calls=[{"name": "finish_response", "args": plan, "id": "f1", "type": "tool_call"}]),
        ToolMessage(content="Response delivered to the visitor.", tool_call_id="f1", name="finish_response"),
    ])
    client = TestClient(create_app(settings=Settings(), store=store, agent=agent))
    result = client.post("/api/experience/stream", json={"question": "What opened Veneta?", "thread_id": "browser-1"})
    assert result.status_code == 200
    events = _ndjson(result.text)

    composing_page_events = [event for event in events if event == {"type": "status", "text": "Composing the page"}]
    assert len(composing_page_events) == 1

    last_answer_index = max(index for index, event in enumerate(events) if event["type"] == "answer")
    composing_index = next(index for index, event in enumerate(events) if event == {"type": "status", "text": "Composing the page"})
    response_index = next(index for index, event in enumerate(events) if event["type"] == "response")
    assert last_answer_index < composing_index < response_index


def test_streaming_endpoint_delivers_a_lone_surrogate_answer_as_a_valid_line():
    plan = {"chat_answer": "Hi there", "title": "Deadbot", "lead": None, "groups": []}
    agent = SurrogateStreamingFakeAgent([
        HumanMessage(content="Hi"),
        AIMessage(content="", tool_calls=[{"name": "finish_response", "args": plan, "id": "f1", "type": "tool_call"}]),
        ToolMessage(content="Response delivered to the visitor.", tool_call_id="f1", name="finish_response"),
    ])
    client = TestClient(create_app(settings=Settings(), store=CanonicalStore(), agent=agent))
    result = client.post("/api/experience/stream", json={"question": "Hi"})
    assert result.status_code == 200
    # Before the api.py fix, line()'s json.dumps(..., ensure_ascii=False) left
    # the lone surrogate embedded in the text, and Starlette's own UTF-8
    # encode of that body -- outside this generator's try/except -- raised
    # UnicodeEncodeError, so the stream produced no usable "answer" line at
    # all; parsing every line here, with the surrogate gone, is the check.
    events = _ndjson(result.text)
    answer_events = [event for event in events if event["type"] == "answer"]
    assert answer_events
    assert any("Hi" in event["text"] and "there" in event["text"] for event in answer_events)
    assert not any(0xD800 <= ord(char) <= 0xDFFF for event in answer_events for char in event["text"])
    assert events[-1]["type"] == "response"


class PlanStreamingFakeAgent(FakeAgent):
    """Streams a complete finish_response plan with one group in fragments, after a tool step."""

    def __init__(self, messages, plan):
        super().__init__(messages)
        self.plan_text = json.dumps(plan)

    def stream(self, payload, config, stream_mode="values"):
        self.calls.append((payload, config))
        yield ("values", {"messages": self.messages[:3]})  # human, tool-calling ai, tool result
        size = 7
        for offset in range(0, len(self.plan_text), size):
            chunk = AIMessageChunk(
                content="",
                tool_call_chunks=[{"name": "finish_response" if offset == 0 else None, "args": self.plan_text[offset : offset + size], "id": "f1", "index": 0, "type": "tool_call_chunk"}],
            )
            yield ("messages", (chunk, {}))
        yield ("values", {"messages": self.messages})


def test_streaming_endpoint_builds_the_page_progressively_then_delivers_the_response():
    store = CanonicalStore()
    show_payload = store.show_context(store.resolve_show("1972-08-27"))
    plan = {
        "chat_answer": "Veneta opened with Promised Land.",
        "title": "Veneta, 1972",
        "lead": None,
        "groups": [{"title": "The show", "presentation": "collection", "items": [
            {"type": "show_unit", "show_id": "gd-1972-08-27", "emphasis": "primary", "visible_facets": ["setlist"]},
            {"type": "editorial", "presentation": "narrative", "paragraphs": ["A benefit in the heat."], "items": []},
        ]}],
    }
    messages = [
        HumanMessage(content="What opened Veneta?"),
        AIMessage(content="", tool_calls=[{"name": "get_show", "args": {"show_id_or_date": "1972-08-27"}, "id": "t1", "type": "tool_call"}]),
        ToolMessage(content=json.dumps(show_payload), tool_call_id="t1", name="get_show"),
        AIMessage(content="", tool_calls=[{"name": "finish_response", "args": plan, "id": "f1", "type": "tool_call"}]),
        ToolMessage(content="Response delivered to the visitor.", tool_call_id="f1", name="finish_response"),
    ]
    client = TestClient(create_app(settings=Settings(), store=store, agent=PlanStreamingFakeAgent(messages, plan)))
    events = _ndjson(client.post("/api/experience/stream", json={"question": "What opened Veneta?", "thread_id": "b1"}).text)
    types = [event["type"] for event in events]
    last_answer = max(index for index, event in enumerate(events) if event["type"] == "answer")
    assert types.index("page_head") > last_answer
    assert types[types.index("page_head") :] == ["page_head", "group_open", "block", "block", "group_close", "response"]
    head = events[types.index("page_head")]
    assert head["title"] == "Veneta, 1972" and head["lead"] is None
    streamed_blocks = [event["block"] for event in events if event["type"] == "block"]
    final = events[-1]["response"]
    assert [block["type"] for block in streamed_blocks] == [block["type"] for block in final["blocks"]] == ["show_unit", "editorial"]
    assert streamed_blocks[0]["show_id"] == final["blocks"][0]["show_id"] == "gd-1972-08-27"
    assert all(event["group_index"] == 0 for event in events if event["type"] == "block")


class _CachingStore(CanonicalStore):
    """An in-memory response cache for testing the cached-answer path.

    ``CanonicalStore`` (the in-memory test double) does not implement the
    response cache interface at all, so ``ResponseCache`` disables itself
    for it (see ``test_a_store_without_cache_methods_disables_the_cache_quietly``
    in tests/test_response_cache.py). This subclass adds a tiny in-memory
    implementation of that interface, the same way ``CloseableStore`` above
    adds a ``close`` method, so the cached-answer path can be exercised here.
    """

    def __init__(self):
        super().__init__()
        self._cached: dict[tuple[str, str], dict] = {}

    def data_version(self) -> str:
        return "test-version"

    def ensure_response_cache(self) -> None:
        pass

    def cached_response(self, question_key, data_version, max_age_seconds):
        return self._cached.get((question_key, data_version))

    def store_response(self, question_key, data_version, question, response) -> None:
        self._cached[(question_key, data_version)] = response


def test_streaming_endpoint_sends_no_page_events_for_a_cached_answer():
    # CanonicalStore() (used elsewhere in this file) has no cache methods, so
    # ResponseCache disables itself for it; _CachingStore above adds a tiny
    # in-memory implementation of that interface so the same fresh question
    # asked twice hits the cache the second time.
    store = _CachingStore()
    plan = {
        "chat_answer": "Veneta opened with Promised Land.",
        "title": "Veneta, 1972",
        "lead": None,
        "groups": [{"title": "The show", "presentation": "collection", "items": [
            {"type": "show_unit", "show_id": "gd-1972-08-27", "emphasis": "primary", "visible_facets": ["setlist"]},
        ]}],
    }
    show_payload = store.show_context(store.resolve_show("1972-08-27"))
    messages = [
        HumanMessage(content="What opened Veneta?"),
        AIMessage(content="", tool_calls=[{"name": "get_show", "args": {"show_id_or_date": "1972-08-27"}, "id": "t1", "type": "tool_call"}]),
        ToolMessage(content=json.dumps(show_payload), tool_call_id="t1", name="get_show"),
        AIMessage(content="", tool_calls=[{"name": "finish_response", "args": plan, "id": "f1", "type": "tool_call"}]),
        ToolMessage(content="Response delivered to the visitor.", tool_call_id="f1", name="finish_response"),
    ]
    client = TestClient(create_app(settings=Settings(), store=store, agent=PlanStreamingFakeAgent(messages, plan)))
    first = client.post("/api/experience/stream", json={"question": "What opened Veneta?", "thread_id": "b1"})
    assert first.status_code == 200
    _ndjson(first.text)  # drain the first (live) stream so the answer is remembered

    second = client.post("/api/experience/stream", json={"question": "What opened Veneta?", "thread_id": "b2"})
    events = _ndjson(second.text)
    assert [event["type"] for event in events] == ["status", "response"]


def test_streaming_endpoint_falls_back_to_invoke_for_an_agent_without_stream():
    agent = FakeAgent(finish_call("A plain answer."))
    client = TestClient(create_app(settings=Settings(), store=CanonicalStore(), agent=agent))
    events = _ndjson(client.post("/api/experience/stream", json={"question": "Hi"}).text)
    assert [event["type"] for event in events] == ["status", "response"]
    assert events[-1]["response"]["answer"] == "A plain answer."


def test_streaming_endpoint_reports_a_failure_as_an_error_event():
    class FailingAgent:
        def invoke(self, payload, config):
            raise RuntimeError("model down")

    client = TestClient(create_app(settings=Settings(), store=CanonicalStore(), agent=FailingAgent()))
    events = _ndjson(client.post("/api/experience/stream", json={"question": "Hi"}).text)
    assert events[-1]["type"] == "error" and "unavailable" in events[-1]["detail"]
    assert "model down" not in json.dumps(events)


def test_api_returns_the_validated_experience_contract():
    store = CanonicalStore()
    show = store.resolve_show("1972-08-27")
    assert show
    agent = FakeAgent(
        [
            HumanMessage(content="Tell me about Veneta"),
            tool_message(store.show_context(show)),
            *finish_call(
                "The Veneta show was held on August 27, 1972.",
                title="Veneta, 1972",
                groups=[{"presentation": "collection", "items": [{"type": "show_unit", "show_id": "gd-1972-08-27", "visible_facets": ["setlist"]}]}],
            ),
        ]
    )
    client = TestClient(create_app(settings=Settings(), store=store, agent=agent))
    health = client.get("/api/health")
    result = client.post("/api/experience", json={"question": "Tell me about Veneta", "thread_id": "browser-1"})
    assert health.json()["status"] == "ok"
    assert health.json()["canonical_shows"] == "2358"
    assert health.json()["performer_assignments"] == "26265"
    assert health.json()["show_equipment_links"] == "2249"
    assert set(health.json()) == {"status", "git_commit", "canonical_shows", "performer_assignments", "show_equipment_links"}
    assert result.status_code == 200
    body = result.json()
    assert body["schema_version"] == "2"
    assert body["thread_id"] == "browser-1"
    assert body["blocks"][0]["type"] == "show_unit"
    assert agent.calls[0][1]["configurable"]["thread_id"] == "browser-1"


def test_api_closes_a_closeable_store_on_shutdown():
    class CloseableStore(CanonicalStore):
        closed = False

        def close(self):
            self.closed = True

    store = CloseableStore()
    with TestClient(create_app(settings=Settings(), store=store, agent=FakeAgent([]))) as client:
        assert client.get("/api/health").status_code == 200

    assert store.closed is True


def test_api_uses_one_thread_for_follow_ups_and_returns_the_transcript():
    agent = ConversationFakeAgent()
    client = TestClient(create_app(settings=Settings(), store=CanonicalStore(), agent=agent))
    first = client.post("/api/experience", json={"question": "Tell me about Veneta", "thread_id": "browser-1"})
    second = client.post("/api/experience", json={"question": "What came next?", "thread_id": "browser-1"})
    assert first.status_code == 200
    assert second.status_code == 200
    assert second.json()["answer"] == "Reply to: What came next?"
    assert second.json()["conversation"] == [
        {"role": "user", "text": "Tell me about Veneta"},
        {"role": "assistant", "text": "Reply to: Tell me about Veneta"},
        {"role": "user", "text": "What came next?"},
        {"role": "assistant", "text": "Reply to: What came next?"},
    ]
    assert {call[1]["configurable"]["thread_id"] for call in agent.calls} == {"browser-1"}


def test_api_replays_browser_conversation_for_stateless_follow_up():
    agent = FakeAgent(finish_call("The grounded follow-up answer."))
    client = TestClient(create_app(settings=Settings(), store=CanonicalStore(), agent=agent))
    result = client.post(
        "/api/experience",
        json={
            "question": "What guitar did Jerry play?",
            "thread_id": "browser-1",
            "conversation": [
                {"role": "user", "text": "When did the Dead play RFK in the early 90s?"},
                {"role": "assistant", "text": "They played RFK on June 14 and 15, 1991."},
            ],
        },
    )
    assert result.status_code == 200
    sent_messages = agent.calls[0][0]["messages"]
    assert [message.content for message in sent_messages] == [
        "When did the Dead play RFK in the early 90s?",
        "They played RFK on June 14 and 15, 1991.",
        "What guitar did Jerry play?",
    ]
    assert agent.calls[0][1]["configurable"]["thread_id"].startswith("browser-1:request:")


def test_requests_beyond_the_per_minute_limit_get_429_while_earlier_ones_succeed():
    store = CanonicalStore()
    show = store.resolve_show("1972-08-27")
    assert show
    agent = FakeAgent(
        [
            HumanMessage(content="Tell me about Veneta"),
            tool_message(store.show_context(show)),
            *finish_call("The Veneta show was held on August 27, 1972.", title="Veneta, 1972"),
        ]
    )
    settings = Settings(rate_limit_per_minute=2)
    client = TestClient(create_app(settings=settings, store=store, agent=agent))

    first = client.post("/api/experience", json={"question": "Tell me about Veneta"})
    second = client.post("/api/experience", json={"question": "Tell me about Veneta"})
    third = client.post("/api/experience", json={"question": "Tell me about Veneta"})

    assert first.status_code == 200
    assert second.status_code == 200
    assert third.status_code == 429
    assert third.json()["detail"]

    # The health endpoint is never rate limited.
    for _ in range(5):
        assert client.get("/api/health").status_code == 200


def test_a_nonpositive_rate_limit_disables_the_limiter():
    agent = FakeAgent(finish_call("The grounded follow-up answer."))
    settings = Settings(rate_limit_per_minute=0)
    client = TestClient(create_app(settings=settings, store=CanonicalStore(), agent=agent))

    for _ in range(5):
        assert client.post("/api/experience", json={"question": "Tell me about Veneta"}).status_code == 200


def test_agent_receives_only_the_most_recent_conversation_window_turns():
    long_conversation = []
    for index in range(20):
        long_conversation.append({"role": "user", "text": f"Question {index}"})
        long_conversation.append({"role": "assistant", "text": f"Answer {index}"})
    agent = FakeAgent(finish_call("The grounded follow-up answer."))
    settings = Settings(conversation_window=4)
    client = TestClient(create_app(settings=settings, store=CanonicalStore(), agent=agent))

    result = client.post(
        "/api/experience",
        json={"question": "What guitar did Jerry play?", "conversation": long_conversation},
    )

    assert result.status_code == 200
    sent_messages = agent.calls[0][0]["messages"]
    assert [message.content for message in sent_messages] == [
        "Question 18",
        "Answer 18",
        "Question 19",
        "Answer 19",
        "What guitar did Jerry play?",
    ]


def test_the_per_request_checkpoint_is_deleted_after_a_conversation_replay():
    checkpointer = FakeCheckpointer()
    agent = FakeAgent(finish_call("The grounded follow-up answer."))
    agent.checkpointer = checkpointer
    client = TestClient(create_app(settings=Settings(), store=CanonicalStore(), agent=agent))

    result = client.post(
        "/api/experience",
        json={
            "question": "What guitar did Jerry play?",
            "thread_id": "browser-1",
            "conversation": [
                {"role": "user", "text": "When did the Dead play RFK in the early 90s?"},
                {"role": "assistant", "text": "They played RFK on June 14 and 15, 1991."},
            ],
        },
    )

    assert result.status_code == 200
    invocation_thread_id = agent.calls[0][1]["configurable"]["thread_id"]
    assert invocation_thread_id.startswith("browser-1:request:")
    assert checkpointer.deleted_threads == [invocation_thread_id]


def test_the_stable_thread_checkpoint_is_never_deleted_across_follow_ups():
    checkpointer = FakeCheckpointer()
    agent = ConversationFakeAgent()
    agent.checkpointer = checkpointer
    client = TestClient(create_app(settings=Settings(), store=CanonicalStore(), agent=agent))

    first = client.post("/api/experience", json={"question": "Tell me about Veneta", "thread_id": "browser-1"})
    second = client.post("/api/experience", json={"question": "What came next?", "thread_id": "browser-1"})

    assert first.status_code == 200
    assert second.status_code == 200
    assert checkpointer.deleted_threads == []


def test_api_serves_a_compiled_client_when_one_is_available(tmp_path):
    client_dist = tmp_path / "dist"
    client_dist.mkdir()
    (client_dist / "index.html").write_text("<main>Deadbot client</main>", encoding="utf-8")
    client = TestClient(
        create_app(settings=Settings(), store=CanonicalStore(), agent=FakeAgent([]), client_dist=client_dist)
    )
    page = client.get("/songs/sugaree")
    assert page.status_code == 200
    assert "Deadbot client" in page.text
    assert page.headers["cache-control"] == "no-cache, no-store, must-revalidate"


def test_album_unit_block_validates_a_full_record():
    block = experience.AlbumUnitBlock(
        type="album_unit",
        release_id="release-american-beauty",
        title="American Beauty",
        artist_name="Grateful Dead",
        release_date="1970-11-01",
        release_type="studio",
        tracks=[
            experience.AlbumTrackItem(
                track_number=10,
                title="Truckin'",
                song_id="song-truckin",
                performance_id=None,
                duration_seconds=311,
                highlighted=True,
                listen_url=None,
            )
        ],
    )
    assert block.tracks[0].highlighted is True
    assert block.personnel == []


def test_album_credits_take_a_free_text_role_and_one_instrument():
    credit = experience.AlbumCreditItem(
        person_id="person-jerry-garcia", name="Jerry Garcia", role="performer", instrument="lead guitar"
    )
    assert credit.instrument == "lead guitar"


def test_album_unit_caps_its_tracklist():
    with pytest.raises(ValidationError):
        experience.AlbumUnitBlock(
            type="album_unit",
            release_id="release-x",
            title="X",
            release_type="studio",
            tracks=[
                experience.AlbumTrackItem(track_number=n, title=f"t{n}", highlighted=False)
                for n in range(1, 32)
            ],
        )


def test_song_overview_carries_the_records_that_held_the_song():
    block = experience.SongOverviewBlock(
        type="song_overview",
        song_id="song-truckin",
        title="Truckin'",
        known_performance_count=520,
        albums=[
            experience.SongReleaseItem(
                release_id="release-american-beauty",
                title="American Beauty",
                release_date="1970-11-01",
                release_type="studio",
            )
        ],
    )
    assert block.albums[0].release_type == "studio"


def test_song_overview_albums_default_to_empty():
    block = experience.SongOverviewBlock(
        type="song_overview", song_id="s", title="S", known_performance_count=0
    )
    assert block.albums == []


def test_editorial_items_can_carry_an_outbound_link():
    item = experience.EditorialItem(
        marker="1972-08-27",
        title="Veneta",
        value=None,
        detail="The Sunshine Daydream show.",
        follow_up=None,
        link=experience.EditorialLink(url="https://archive.org/details/gd1972-08-27.sbd.latvala-eaton-lutch-dankseed.4682.shnf", label="Listen on Archive.org"),
    )
    assert item.link.label == "Listen on Archive.org"
    legacy = experience.EditorialItem(marker=None, title="Appearances", value="5", detail=None, follow_up=None)
    assert legacy.link is None
