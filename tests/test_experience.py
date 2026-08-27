import json

from fastapi.testclient import TestClient
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from pydantic import ValidationError

from deadbot.api import create_app
from deadbot.composer import CompositionPlan, CompositionSection, ModelGuidedComposer, apply_composition_plan
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
    assert {block.type for block in response.blocks} >= {"entity_card", "resource_list", "song_overview", "arrangement", "media_link", "performance_extremes", "performance_spine"}
    overview = next(block for block in response.blocks if block.type == "song_overview")
    assert any(item.name == "Robert Hunter" and item.role == "lyrics" for item in overview.credits)
    assert overview.known_performance_count == len(store.song_context(song)["performances"])
    assert any(source.kind == "contextual_resource" for source in response.sources)
    assert any(
        block.type == "media_link" and block.embed_kind == "youtube"
        for block in response.blocks
    )
    assert any(
        block.type == "media_link" and block.embed_kind == "spotify" and block.is_official
        for block in response.blocks
    )
    arrangement = next(block for block in response.blocks if block.type == "arrangement")
    assert arrangement.key_signature == "B"
    assert arrangement.arrangement_scope == "recorded-song-interpretation"
    spine = next(block for block in response.blocks if block.type == "performance_spine")
    assert spine.previous and spine.previous.title == "Promised Land"
    assert spine.next and spine.next.title == "Me And My Uncle"


def test_song_credits_are_usable_in_the_experience_response():
    store = CanonicalStore()
    song = store.resolve_song("Sugaree")
    assert song
    response = compose_experience_response(
        question="Who wrote Sugaree?",
        thread_id="web-test",
        messages=[tool_message(store.song_context(song)), AIMessage(content="Sugaree credits are in the library.")],
        store=store,
    )
    overview = next(block for block in response.blocks if block.type == "song_overview")
    assert {item.name for item in overview.credits} == {"Jerry Garcia", "Robert Hunter"}
    assert "resource:resource-musicbrainz-work-search-sugaree" in overview.source_ids


def test_key_search_renders_only_documented_arrangements_with_a_coverage_note():
    store = CanonicalStore()
    response = compose_experience_response(
        question="What documented arrangements are in B?",
        thread_id="web-test",
        messages=[
            tool_message(store.arrangement_search("B")),
            AIMessage(content="The current library has one documented arrangement in B."),
        ],
        store=store,
    )
    search = next(block for block in response.blocks if block.type == "arrangement_search")
    assert response.mode == "musician"
    assert response.title == "Documented arrangements in B"
    assert search.items[0].title == "Sugaree"
    assert search.items[0].key_signature == "B"
    assert search.items[0].url.startswith("https://www.rukind.com/")
    assert "universal key" in search.coverage_note


def test_song_response_has_labeled_first_and_last_performances_with_follow_ups():
    store = CanonicalStore()
    song = store.resolve_song("Ripple")
    assert song
    response = compose_experience_response(
        question="When was Ripple first played? When last played?",
        thread_id="web-test",
        messages=[tool_message(store.song_context(song)), AIMessage(content="Ripple was first and last played on the dates below.")],
        store=store,
    )
    extremes = next(block for block in response.blocks if block.type == "performance_extremes")
    assert extremes.first.show_date == "1970-08-18"
    assert extremes.last.show_date == "1988-09-03"
    assert "show on 1970-08-18" in extremes.first.follow_up
    assert "—" in extremes.first.show_label


def test_show_response_uses_location_title_and_moves_setlist_and_recordings_to_body():
    store = CanonicalStore()
    show = store.resolve_show("1972-08-27")
    assert show
    response = compose_experience_response(
        question="Tell me about the 1972-08-27 show.",
        thread_id="web-test",
        messages=[
            tool_message(store.show_context(show)),
            AIMessage(content="The show was held at the Old Renaissance Faire Grounds.\n\n### Set 1:\n1. Truckin'"),
        ],
        store=store,
    )
    entity = next(block for block in response.blocks if block.type == "entity_card")
    setlist = next(block for block in response.blocks if block.type == "show_setlist")
    recordings = next(block for block in response.blocks if block.type == "recording_list")
    assert entity.title == "Old Renaissance Faire Grounds"
    assert entity.subtitle == "1972-08-27"
    assert len(setlist.sets) == 3
    assert len(recordings.items) == 7
    assert response.answer == "The show was held at the Old Renaissance Faire Grounds."
    assert "Set 1" not in response.conversation[-1].text


def test_show_response_exposes_source_reviewed_performers_and_instruments():
    store = CanonicalStore()
    show = store.resolve_show("1972-07-16")
    assert show
    response = compose_experience_response(
        question="Who played at the 1972-07-16 show?",
        thread_id="web-test",
        messages=[
            tool_message(store.show_context(show)),
            AIMessage(content="The show included the Grateful Dead and guest musicians."),
        ],
        store=store,
    )
    performers = next(block for block in response.blocks if block.type == "performer_list")
    berry = next(item for item in performers.items if item.name == "Berry Oakley")
    gregg = next(item for item in performers.items if item.name == "Gregg Allman")
    assert berry.role == "guest"
    assert berry.instruments == ["bass", "vocals"]
    assert gregg.instruments == ["Hammond B3"]


def test_show_response_exposes_named_guitars_with_evidence_scope():
    store = CanonicalStore()
    show = store.resolve_show("1995-07-09")
    assert show
    response = compose_experience_response(
        question="Which guitars did Jerry play at the final show?",
        thread_id="web-test",
        messages=[
            tool_message(store.show_context(show)),
            AIMessage(content="Jerry's documented guitars are shown below."),
        ],
        store=store,
    )
    equipment = next(block for block in response.blocks if block.type == "equipment_list")
    assert {item.name for item in equipment.items} >= {"Rosebud", "Tiger"}
    assert {item.claim_type for item in equipment.items} == {"show"}
    assert any(source.source_id == "source:jerry-garcia-instrument-history" for source in response.sources)


def test_equipment_first_show_lookup_can_expand_into_a_show_with_context_and_listening():
    store = CanonicalStore()
    tiger = store.resolve_equipment("Tiger")
    show = store.resolve_show("1979-08-04")
    assert tiger and show
    response = compose_experience_response(
        question="What was the first show Jerry played Tiger in?",
        thread_id="web-test",
        messages=[
            tool_message(store.equipment_history(tiger)),
            AIMessage(content="The first documented Tiger assignment is the Oakland show on August 4, 1979."),
        ],
        store=store,
    )
    entity = next(block for block in response.blocks if block.type == "entity_card")
    assert entity.title == "Oakland Auditorium"
    assert "Oakland, CA" in entity.details
    assert any(block.type == "show_setlist" for block in response.blocks)
    assert any(block.type == "recording_list" for block in response.blocks)
    equipment = next(block for block in response.blocks if block.type == "equipment_list")
    assert any(item.name == "Tiger" for item in equipment.items)


def test_composer_returns_a_safe_gap_when_no_tools_return_data():
    response = compose_experience_response(
        question="Tell me about an unknown song.",
        thread_id="web-test",
        messages=[AIMessage(content="That song is not in the current library.")],
        store=CanonicalStore(),
    )
    assert response.blocks[0].type == "gap_state"
    assert response.mode == "gap"
    assert response.sources == []


def test_title_only_song_cards_do_not_repeat_the_page_title():
    store = CanonicalStore()
    song = store.resolve_song("Ripple")
    assert song
    response = compose_experience_response(
        question="When was Ripple first performed?",
        thread_id="web-test",
        messages=[tool_message(store.song_context(song)), AIMessage(content="Ripple was first performed on August 18, 1970.")],
        store=store,
    )
    assert response.title == "Ripple"
    assert not any(block.type == "entity_card" for block in response.blocks)
    assert all(block.type != "coverage" for section in response.layout for index in section.block_indexes for block in [response.blocks[index]])


def test_coverage_block_describes_the_full_current_library_range():
    store = CanonicalStore()
    response = compose_experience_response(
        question="What does the library cover?",
        thread_id="web-test",
        messages=[AIMessage(content="The library covers the available canonical data.")],
        store=store,
    )
    coverage = next(block for block in response.blocks if block.type == "coverage")
    dated_shows = [show for show in store.rows("shows") if show.get("show_date")]
    years = sorted({show["show_date"][:4] for show in dated_shows})
    song_ids = {performance["song_id"] for performance in store.rows("performances")}

    assert coverage.title == "Current library coverage"
    assert f"{len(dated_shows)} dated shows" in coverage.message
    assert f"{len(store.rows('performances'))} ordered performances" in coverage.message
    assert f"{len(song_ids)} song labels spanning {years[0]}–{years[-1]}" in coverage.message
    assert "1972 library" not in coverage.message


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


def test_composition_plan_can_only_reorder_existing_blocks_without_forcing_provenance():
    store = CanonicalStore()
    song = store.resolve_song("Sugaree")
    assert song
    response = compose_experience_response(
        question="Tell me about Sugaree.",
        thread_id="web-test",
        messages=[tool_message(store.song_context(song)), AIMessage(content="Sugaree is in the library.")],
        store=store,
    )
    resource_index = next(index for index, block in enumerate(response.blocks) if block.type == "resource_list")
    composed = apply_composition_plan(
        response,
        CompositionPlan(sections=[CompositionSection(region="primary", candidate_indexes=[999, resource_index, 0, 0])]),
    )
    assert [block.type for block in composed.blocks] == [response.blocks[resource_index].type, response.blocks[0].type]
    assert all(block.type != "provenance_note" for block in composed.blocks)
    assert [section.region for section in composed.layout] == ["primary"]


def test_composition_cannot_show_coverage_as_a_normal_result_instead_of_grounded_content():
    store = CanonicalStore()
    song = store.resolve_song("Sugaree")
    assert song
    response = compose_experience_response(
        question="Tell me about Sugaree.",
        thread_id="web-test",
        messages=[tool_message(store.song_context(song)), AIMessage(content="Sugaree is in the library.")],
        store=store,
    )
    coverage_index = next(index for index, block in enumerate(response.blocks) if block.type == "coverage")
    composed = apply_composition_plan(
        response,
        CompositionPlan(mode="quick_fact", sections=[CompositionSection(region="primary", candidate_indexes=[coverage_index])]),
    )
    assert composed == response
    assert all(
        response.blocks[index].type != "coverage"
        for section in composed.layout
        for index in section.block_indexes
    )


def test_composition_preserves_the_model_selected_show_order_and_regions():
    store = CanonicalStore()
    show = store.resolve_show("1972-08-27")
    assert show
    response = compose_experience_response(
        question="Tell me about the show.",
        thread_id="web-test",
        messages=[tool_message(store.show_context(show)), AIMessage(content="The show is in the library.")],
        store=store,
    )
    recording_index = next(index for index, block in enumerate(response.blocks) if block.type == "recording_list")
    setlist_index = next(index for index, block in enumerate(response.blocks) if block.type == "show_setlist")
    composed = apply_composition_plan(
        response,
        CompositionPlan(
            mode="show",
            sections=[
                CompositionSection(region="context", candidate_indexes=[setlist_index]),
                CompositionSection(region="media", candidate_indexes=[recording_index]),
            ],
        ),
    )
    assert [section.region for section in composed.layout] == ["context", "media"]
    assert [block.type for block in composed.blocks] == ["show_setlist", "recording_list"]
    assert composed.layout[0].block_indexes == [0]
    assert composed.layout[1].block_indexes == [1]


def test_an_invalid_composition_plan_uses_the_deterministic_candidate_order():
    store = CanonicalStore()
    song = store.resolve_song("Sugaree")
    assert song
    response = compose_experience_response(
        question="Tell me about Sugaree.",
        thread_id="web-test",
        messages=[tool_message(store.song_context(song)), AIMessage(content="Sugaree is in the library.")],
        store=store,
    )
    invalid = CompositionPlan(sections=[CompositionSection(region="primary", candidate_indexes=[999])])
    assert apply_composition_plan(response, invalid) == response


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
    resource_index = next(index for index, block in enumerate(response.blocks) if block.type == "resource_list")
    stub = SelectionStub(
        CompositionPlan(mode="musician", sections=[CompositionSection(region="supporting", candidate_indexes=[resource_index, 0, 999])])
    )
    composer = ModelGuidedComposer(selector=stub)
    composed = composer.compose("Tell me about Sugaree.", response)
    assert [block.type for block in composed.blocks] == [response.blocks[resource_index].type, response.blocks[0].type]
    assert composed.mode == "musician"
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
    assert health.json()["status"] == "ok"
    assert health.json()["canonical_shows"] == "2358"
    assert health.json()["performer_assignments"] == "26265"
    assert health.json()["show_equipment_links"] == "2249"
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


def test_api_replays_browser_conversation_for_stateless_follow_up():
    agent = FakeAgent([AIMessage(content="The grounded follow-up answer.")])
    client = TestClient(create_app(settings=Settings(), agent=agent))
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


def test_api_serves_a_compiled_client_when_one_is_available(tmp_path):
    client_dist = tmp_path / "dist"
    client_dist.mkdir()
    (client_dist / "index.html").write_text("<main>Deadbot client</main>", encoding="utf-8")
    client = TestClient(create_app(agent=FakeAgent([]), client_dist=client_dist))
    page = client.get("/songs/sugaree")
    assert page.status_code == 200
    assert "Deadbot client" in page.text
