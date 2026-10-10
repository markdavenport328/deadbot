"""A visitor who clicks in a grid and asks: what they clicked travels with the question."""

import json

import pytest
from fastapi.testclient import TestClient
from langchain_core.messages import AIMessage, ToolMessage

from deadbot import finish
from deadbot.api import create_app, focus_ids
from deadbot.config import Settings
from deadbot.experience import AskFocus, ExperienceRequest
from deadbot.sqlite_store import SqliteCanonicalStore

QUESTION = "Tell me about the Dark Star from May 11, 1972 in Rotterdam."
FOCUS = {
    "label": "Dark Star · May 11, 1972",
    "block_type": "grid",
    "block_id": "grid:abc",
    "ids": ["gd-1972-05-11", "gd-1972-05-11-dark-star-2-7", "song-dark-star"],
    "facts": ["Set 2, into Sugar Magnolia. 44 minutes in 2 passes."],
}


class FakeAgent:
    def __init__(self, messages=None):
        self.calls = []
        self.messages = messages

    def invoke(self, payload, config):
        self.calls.append((payload, config))
        plan = {"chat_answer": "Here is the night.", "title": "Dark Star", "lead": None, "groups": []}
        reply = [
            AIMessage(content="", tool_calls=[{"name": "finish_response", "args": plan, "id": "f1", "type": "tool_call"}]),
            ToolMessage(content="Response delivered to the visitor.", tool_call_id="f1", name="finish_response"),
        ]
        return {"messages": [*payload["messages"], *(self.messages or []), *reply]}


@pytest.fixture
def store(built_sqlite, tmp_path):
    return SqliteCanonicalStore(built_sqlite, response_cache_path=tmp_path / "cache.sqlite")


def client_for(store, agent, tmp_path):
    dist = tmp_path / "dist"
    dist.mkdir(exist_ok=True)
    (dist / "index.html").write_text("<!doctype html><title>shell</title>")
    return TestClient(create_app(settings=Settings(), store=store, agent=agent, client_dist=dist))


def test_focus_reaches_the_model_as_its_own_note_after_the_question(store, tmp_path):
    agent = FakeAgent()
    client = client_for(store, agent, tmp_path)
    result = client.post("/api/experience", json={"question": QUESTION, "focus": FOCUS})
    assert result.status_code == 200
    messages = agent.calls[0][0]["messages"]
    assert messages[0].content == QUESTION
    note = messages[-1]
    assert note is not messages[0]
    assert "The visitor asked from a grid on the page" in note.content
    assert "Dark Star · May 11, 1972" in note.content
    assert "44 minutes in 2 passes" in note.content
    assert "gd-1972-05-11-dark-star-2-7" in note.content
    # The note is separate, so the visitor's question stays exactly what they typed.
    assert "grid on the page" not in messages[0].content


def test_the_visitors_transcript_never_carries_the_focus_note(store, tmp_path):
    agent = FakeAgent()
    client = client_for(store, agent, tmp_path)
    body = client.post("/api/experience", json={"question": QUESTION, "focus": FOCUS}).json()
    assert body["conversation"] == [
        {"role": "user", "text": QUESTION},
        {"role": "assistant", "text": "Here is the night."},
    ]
    assert "grid on the page" not in json.dumps(body)


def test_the_stream_path_also_sends_the_note_and_keeps_the_transcript_clean(store, tmp_path):
    agent = FakeAgent()
    client = client_for(store, agent, tmp_path)
    text = client.post("/api/experience/stream", json={"question": QUESTION, "focus": FOCUS}).text
    events = [json.loads(line) for line in text.splitlines() if line.strip()]
    assert "grid on the page" in agent.calls[0][0]["messages"][-1].content
    assert events[-1]["type"] == "response"
    assert [turn["text"] for turn in events[-1]["response"]["conversation"]][0] == QUESTION
    assert "grid on the page" not in json.dumps(events)


def test_a_request_without_focus_sends_only_the_question(store, tmp_path):
    agent = FakeAgent()
    client = client_for(store, agent, tmp_path)
    client.post("/api/experience", json={"question": QUESTION})
    assert [message.content for message in agent.calls[0][0]["messages"]] == [QUESTION]


def test_focus_ids_that_exist_are_grounded_and_others_are_dropped(store):
    assert focus_ids(store, AskFocus.model_validate({**FOCUS, "ids": ["gd-1972-05-11", "gd-nope", "song-dark-star"]})) == {
        "gd-1972-05-11",
        "song-dark-star",
    }
    assert focus_ids(store, None) == set()


def test_a_clicked_night_can_be_placed_without_the_model_looking_it_up_again(store):
    ids = focus_ids(store, AskFocus.model_validate(FOCUS))
    assert {"gd-1972-05-11", "song-dark-star"} <= ids
    performance_ids = [i for i in ids if i.startswith("gd-1972-05-11-")]
    assert performance_ids, "the clicked performance resolves in the store"
    plan_item = {"type": "show_unit", "show_id": "gd-1972-05-11", "visible_facets": ["setlist"]}
    plan = {"chat_answer": "Rotterdam.", "title": "T", "lead": None, "groups": [{"presentation": "collection", "items": [plan_item]}]}
    messages = [
        AIMessage(content="", tool_calls=[{"name": "finish_response", "args": plan, "id": "f1", "type": "tool_call"}]),
        ToolMessage(content="ok", tool_call_id="f1", name="finish_response"),
    ]
    ungrounded = finish.build_experience_response(QUESTION, "t", messages, store)
    grounded = finish.build_experience_response(QUESTION, "t", messages, store, extra_ids=ids)
    assert [b.type for b in ungrounded.blocks] != ["show_unit"]
    assert [b.type for b in grounded.blocks] == ["show_unit"]


def test_a_focused_ask_neither_reads_nor_writes_the_response_cache(store, tmp_path):
    agent = FakeAgent()
    client = client_for(store, agent, tmp_path)
    # Two focused asks both reach the model, and neither is remembered.
    client.post("/api/experience", json={"question": QUESTION, "focus": FOCUS})
    client.post("/api/experience", json={"question": QUESTION, "focus": FOCUS})
    assert len(agent.calls) == 2
    client.post("/api/experience", json={"question": QUESTION})
    assert len(agent.calls) == 3  # nothing focused was stored for the plain question
    client.post("/api/experience", json={"question": QUESTION})
    assert len(agent.calls) == 3  # sanity: the plain question is cached
    client.post("/api/experience", json={"question": QUESTION, "focus": FOCUS})
    assert len(agent.calls) == 4  # a stored plain answer is never served to a focused ask


def test_the_stream_path_skips_the_cache_for_a_focused_ask(store, tmp_path):
    agent = FakeAgent()
    client = client_for(store, agent, tmp_path)
    client.post("/api/experience", json={"question": QUESTION})
    client.post("/api/experience/stream", json={"question": QUESTION, "focus": FOCUS})
    assert len(agent.calls) == 2


def test_overlong_focus_trims_instead_of_rejecting():
    request = ExperienceRequest.model_validate(
        {
            "question": "Q",
            "focus": {
                "label": "x" * 500,
                "block_type": "grid",
                "block_id": "g" * 500,
                "ids": [f"id-{n}" for n in range(100)],
                "facts": ["f" * 900 for _ in range(30)],
                "something_new": 1,
            },
        }
    )
    focus = request.focus
    assert len(focus.label) == 300 and len(focus.block_id) == 200
    assert len(focus.ids) == 40 and len(focus.facts) == 12
    assert all(len(fact) == 300 for fact in focus.facts)
