import json

from fastapi.testclient import TestClient
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from pydantic import ValidationError

from deadbot.api import create_app
from deadbot.composer import CompositionPlan, ModelGuidedComposer, apply_composition_plan
from deadbot.config import Settings
from deadbot.data import CanonicalStore
from deadbot.experience import ExperienceResponse, _embed_details, compose_experience_response


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
        question = payload["messages"][0].content
        self.messages.extend([HumanMessage(content=question), AIMessage(content=f"Reply to: {question}")])
        return {"messages": self.messages}


class SelectionStub:
    def __init__(self, plan):
        self.plan = plan
        self.inputs = []

    def invoke(self, messages):
        self.inputs.append(messages)
        return self.plan


def tool_message(payload):
    return ToolMessage(content=json.dumps(payload), tool_call_id="tool-call")


def test_composer_creates_grounded_cards_resources_and_media():
    store = CanonicalStore()
    song = store.resolve_song("Sugaree")
    performance = store.performance_context("gd-1972-08-27-sugaree")
    show = store.resolve_show("1972-08-27")
    assert song and performance and show
    response = compose_experience_response(
        question="Show me the Veneta Sugaree and its chord source.",
        thread_id="web-test",
        messages=[
            tool_message(store.song_context(song)),
            tool_message(performance),
            tool_message(store.show_context(show)),
            AIMessage(content="Sugaree has a source-specific chord resource and a Veneta performance link."),
        ],
        store=store,
    )
    assert response.thread_id == "web-test"
    assert {block.type for block in response.blocks} >= {"entity_card", "resource_list", "arrangement", "media_link"}
    assert any(source.kind == "contextual_resource" for source in response.sources)
    assert any(
        block.type == "media_link" and block.embed_kind == "youtube"
        for block in response.blocks
    )
    assert any(
        block.type == "media_link" and block.embed_kind == "spotify" and block.is_official
        for block in response.blocks
    )


def test_composer_returns_a_safe_gap_when_no_tools_return_data():
    response = compose_experience_response(
        question="Tell me about an unknown song.",
        thread_id="web-test",
        messages=[AIMessage(content="That song is not in the current library.")],
        store=CanonicalStore(),
    )
    assert response.blocks[0].type == "gap_state"
    assert response.sources == []


def test_composer_preserves_conversation_but_refreshes_blocks_for_the_latest_turn():
    store = CanonicalStore()
    song = store.resolve_song("Sugaree")
    show = store.resolve_show("1972-08-27")
    assert song and show
    response = compose_experience_response(
        question="And what about the show?",
        thread_id="web-test",
        messages=[
            HumanMessage(content="Tell me about Sugaree"),
            tool_message(store.song_context(song)),
            AIMessage(content="Sugaree is in the current library."),
            HumanMessage(content="And what about the show?"),
            tool_message(store.show_context(show)),
            AIMessage(content="The show was held on August 27, 1972."),
        ],
        store=store,
    )
    entity_blocks = [block for block in response.blocks if block.type == "entity_card"]
    assert response.answer == "The show was held on August 27, 1972."
    assert [turn.role for turn in response.conversation] == ["user", "assistant", "user", "assistant"]
    assert [block.entity_type for block in entity_blocks] == ["show"]


def test_only_recognized_provider_urls_receive_embed_identifiers():
    assert _embed_details("youtube", "https://www.youtube.com/watch?v=Ip48SfRx4ho") == ("youtube", "Ip48SfRx4ho")
    assert _embed_details("spotify", "https://open.spotify.com/album/1E4MXxSYoAMN5qpy1y6aBm") == ("spotify", "album/1E4MXxSYoAMN5qpy1y6aBm")
    assert _embed_details("youtube", "https://example.com/watch?v=Ip48SfRx4ho") == (None, None)


def test_composition_plan_can_only_reorder_existing_blocks_and_keeps_provenance():
    store = CanonicalStore()
    song = store.resolve_song("Sugaree")
    assert song
    response = compose_experience_response(
        question="Tell me about Sugaree.",
        thread_id="web-test",
        messages=[tool_message(store.song_context(song)), AIMessage(content="Sugaree is in the library.")],
        store=store,
    )
    provenance_index = next(index for index, block in enumerate(response.blocks) if block.type == "provenance_note")
    composed = apply_composition_plan(response, CompositionPlan(selected_block_indexes=[999, 0, 0]))
    assert [block.type for block in composed.blocks] == [response.blocks[0].type, "provenance_note"]
    assert composed.blocks[-1] == response.blocks[provenance_index]


def test_an_empty_composition_plan_uses_the_deterministic_candidate_order():
    store = CanonicalStore()
    song = store.resolve_song("Sugaree")
    assert song
    response = compose_experience_response(
        question="Tell me about Sugaree.",
        thread_id="web-test",
        messages=[tool_message(store.song_context(song)), AIMessage(content="Sugaree is in the library.")],
        store=store,
    )
    assert apply_composition_plan(response, CompositionPlan()) == response


def test_model_guided_composer_uses_a_structured_selection_without_creating_blocks():
    store = CanonicalStore()
    song = store.resolve_song("Sugaree")
    assert song
    response = compose_experience_response(
        question="Tell me about Sugaree.",
        thread_id="web-test",
        messages=[tool_message(store.song_context(song)), AIMessage(content="Sugaree is in the library.")],
        store=store,
    )
    stub = SelectionStub(CompositionPlan(selected_block_indexes=[1, 0, 999]))
    composer = ModelGuidedComposer(selector=stub)
    composed = composer.compose("Tell me about Sugaree.", response)
    assert [block.type for block in composed.blocks] == [response.blocks[1].type, response.blocks[0].type, "provenance_note"]
    assert len(stub.inputs) == 1


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


def test_api_returns_the_validated_experience_contract():
    store = CanonicalStore()
    show = store.resolve_show("1972-08-27")
    assert show
    agent = FakeAgent(
        [
            tool_message(store.show_context(show)),
            AIMessage(content="The Veneta show was held on August 27, 1972."),
        ]
    )
    client = TestClient(create_app(settings=Settings(), store=store, agent=agent))
    health = client.get("/api/health")
    result = client.post("/api/experience", json={"question": "Tell me about Veneta", "thread_id": "browser-1"})
    assert health.json() == {"status": "ok"}
    assert result.status_code == 200
    body = result.json()
    assert body["schema_version"] == "1"
    assert body["thread_id"] == "browser-1"
    assert body["blocks"][0]["type"] == "entity_card"
    assert agent.calls[0][1]["configurable"]["thread_id"] == "browser-1"


def test_api_uses_one_thread_for_follow_ups_and_returns_the_transcript():
    agent = ConversationFakeAgent()
    client = TestClient(create_app(settings=Settings(), agent=agent))
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


def test_api_serves_a_compiled_client_when_one_is_available(tmp_path):
    client_dist = tmp_path / "dist"
    client_dist.mkdir()
    (client_dist / "index.html").write_text("<main>Deadbot client</main>", encoding="utf-8")
    client = TestClient(create_app(agent=FakeAgent([]), client_dist=client_dist))
    page = client.get("/songs/sugaree")
    assert page.status_code == 200
    assert "Deadbot client" in page.text
