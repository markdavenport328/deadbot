import json

from fastapi.testclient import TestClient
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from pydantic import ValidationError

from deadbot import experience
from deadbot.api import create_app
from deadbot.composition import _comparison_strip, _embed_details
from deadbot.config import Settings
from deadbot.data import CanonicalStore
from deadbot.experience import ExperienceResponse


def finish_call(chat_answer, *, title="Deadbot", lead=None, mode="quick_fact", body=None):
    """The two messages a finished agent turn ends with: the call and its result."""

    plan = {"chat_answer": chat_answer, "title": title, "lead": lead, "mode": mode, "body": body or []}
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
        plan = {"chat_answer": f"Reply to: {question}", "title": "Deadbot", "lead": None, "mode": "quick_fact", "body": []}
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


class StubComparisonStore:
    """Minimal store stand-in so comparison-strip selection can be exercised directly."""

    def __init__(self, shows):
        self.shows = shows

    def one(self, table, entity_id):
        if table == "shows":
            return self.shows.get(entity_id)
        return None

    def rows(self, table):
        return []


def _stub_performances(dates):
    shows = {}
    performances = []
    for index, date in enumerate(dates):
        show_id = f"show-{index}"
        shows[show_id] = {"show_id": show_id, "show_date": date}
        performances.append(
            {"performance_id": f"perf-{index}", "show_id": show_id, "song_id": "song:1", "set_label": "Set 1", "position_in_set": "1"}
        )
    return StubComparisonStore(shows), performances


def test_single_year_song_produces_no_comparison_strip():
    stub_store, performances = _stub_performances(["1972-08-27", "1972-08-21", "1972-11-13"])
    strip = _comparison_strip({"song_id": "song:1", "title": "Sugaree"}, performances, stub_store)
    assert strip is None


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
    plan = {"chat_answer": "Veneta opened with Promised Land.", "title": "Veneta, 1972", "lead": None, "mode": "show",
            "body": [{"type": "show_setlist", "show_id": "gd-1972-08-27", "title": "The whole night"}]}
    agent = FakeAgent([
        HumanMessage(content="What opened Veneta?"),
        tool_message(store.show_context(show)),
        AIMessage(content="", tool_calls=[{"name": "finish_response", "args": plan, "id": "f1", "type": "tool_call"}]),
        ToolMessage(content="Response delivered to the visitor.", tool_call_id="f1", name="finish_response"),
    ])
    client = TestClient(create_app(settings=Settings(), store=store, agent=agent))
    body = client.post("/api/experience", json={"question": "What opened Veneta?"}).json()
    assert body["title"] == "Veneta, 1972"
    assert body["blocks"][0]["type"] == "show_setlist" and body["blocks"][0]["title"] == "The whole night"
    assert body["conversation"][-1] == {"role": "assistant", "text": "Veneta opened with Promised Land."}


def test_experience_endpoint_renders_a_nested_show_explorer():
    store = CanonicalStore()
    show = store.resolve_show("1972-08-27")
    payload = store.show_context(show)
    plan = {
        "chat_answer": "One show, as a unit.",
        "title": "Veneta as a unit",
        "lead": None,
        "mode": "show",
        "body": [
            {
                "type": "show_explorer",
                "title": "The show",
                "organization": "curated",
                "items": [{"type": "show_unit", "show_id": "gd-1972-08-27", "role": "anchor", "note": "One frame, everything about it."}],
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
    explorer = body["blocks"][0]
    assert explorer["type"] == "show_explorer" and explorer["organization"] == "curated"
    unit = explorer["items"][0]
    assert unit["type"] == "show_unit" and unit["show_date"] == "1972-08-27" and unit["role"] == "anchor"
    assert unit["sets"] and unit["listen"]
    # The nested response still validates against the browser contract.
    ExperienceResponse.model_validate(body)


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
                mode="show",
                body=[{"type": "show_setlist", "show_id": "gd-1972-08-27"}],
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
    assert body["schema_version"] == "1"
    assert body["thread_id"] == "browser-1"
    assert body["blocks"][0]["type"] == "show_setlist"
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
            *finish_call("The Veneta show was held on August 27, 1972.", title="Veneta, 1972", mode="show"),
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
