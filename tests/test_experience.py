import json
from typing import get_args

from fastapi.testclient import TestClient
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from pydantic import ValidationError

from deadbot import experience
from deadbot.api import create_app
from deadbot.composer import CompositionPlan, CompositionSection, ModelGuidedComposer, _block_brief, _composer_brief, apply_composition_plan
from deadbot.config import Settings
from deadbot.data import CanonicalStore
from deadbot.experience import ExperienceResponse, _embed_details, compose_experience_response
from deadbot.tools import build_tools


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


class FakeCheckpointer:
    """Stand-in for LangGraph's MemorySaver that records delete_thread calls."""

    def __init__(self):
        self.deleted_threads = []

    def delete_thread(self, thread_id):
        self.deleted_threads.append(thread_id)


class SelectionStub:
    def __init__(self, plan):
        self.plan = plan
        self.inputs = []

    def invoke(self, messages):
        self.inputs.append(messages)
        return self.plan


class SelectionSequenceStub:
    def __init__(self, plans):
        self.plans = iter(plans)
        self.inputs = []

    def invoke(self, messages):
        self.inputs.append(messages)
        return next(self.plans)


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


def test_guest_count_question_keeps_model_selected_show_and_listening_paths():
    """A guest directory plus chosen show contexts must never collapse to a gap."""

    store = CanonicalStore()
    guest_tool = next(tool for tool in build_tools(store) if tool.name == "search_guest_musicians")
    guest_payload = json.loads(guest_tool.invoke({"query": "Branford"}))
    selected_show_ids = ["gd-1990-03-29", "gd-1991-09-10", "gd-1993-12-10"]
    response = compose_experience_response(
        question="How many shows did Branford play with the Dead?",
        thread_id="guest-count-test",
        messages=[
            tool_message(guest_payload),
            *[
                tool_message(store.show_context(store.one("shows", show_id)))
                for show_id in selected_show_ids
            ],
            AIMessage(
                content=(
                    "The current canonical guest-credit directory documents five Branford Marsalis "
                    "show appearances. I pulled three grounded show and listening paths below."
                )
            ),
        ],
        store=store,
    )

    assert response.answer.startswith("The current canonical guest-credit directory documents five")
    assert response.mode == "quick_fact"
    assert {block.show_id for block in response.blocks if block.type == "recording_list"} == set(selected_show_ids)
    assert {block.show_id for block in response.blocks if block.type == "show_setlist"} == set(selected_show_ids)
    assert not any(block.type == "gap_state" for block in response.blocks)


def test_metadata_only_research_records_join_the_main_column_resource_path():
    store = CanonicalStore()
    song = store.resolve_song("Sugaree")
    assert song
    response = compose_experience_response(
        question="Find some Dead.net context for Sugaree.",
        thread_id="research-test",
        messages=[
            tool_message(
                {
                    "song": song,
                    "research": {
                        "state": "ok",
                        "records": [
                            {
                                "entity_type": "song",
                                "identifier": "sugaree",
                                "title": "Sugaree | Dead.net",
                                "url": "https://www.dead.net/song/sugaree",
                                "source": "dead.net",
                            }
                        ],
                    },
                }
            ),
            AIMessage(content="I found a Dead.net source for additional context."),
        ],
        store=store,
    )
    resource_blocks = [block for block in response.blocks if block.type == "resource_list"]
    assert resource_blocks
    assert any(item.title == "Sugaree | Dead.net" for block in resource_blocks for item in block.items)
    assert any(item.source_id == "resource:research:dead.net:sugaree" for block in resource_blocks for item in block.items)
    assert any(section.block_indexes for section in response.layout)


def test_research_candidates_in_brief_are_server_owned_and_provenanced():
    store = CanonicalStore()
    song = store.resolve_song("Sugaree")
    assert song
    response = compose_experience_response(
        question="Find context for Sugaree.",
        thread_id="research-brief-test",
        messages=[
            tool_message(
                {
                    "song": song,
                    "research_results": [
                        {"identifier": "sugaree", "title": "Sugaree", "url": "https://www.dead.net/song/sugaree", "source": "dead.net"}
                    ],
                }
            ),
            AIMessage(content="Context is available."),
        ],
        store=store,
    )
    brief = json.loads(_composer_brief("Find context for Sugaree.", response))
    candidate = next(item for item in brief["research_candidates"] if item["title"] == "Sugaree")
    assert candidate["provenance"] == "contextual resource metadata"
    assert candidate["candidate_index"] < len(response.blocks)


def test_research_resource_rejects_non_deadnet_urls():
    store = CanonicalStore()
    response = compose_experience_response(
        question="Find context.",
        thread_id="research-safe-test",
        messages=[
            tool_message({"research": {"records": [{"identifier": "x", "title": "X", "url": "https://evil.example/x", "source": "dead.net"}]}}),
            AIMessage(content="No trusted source was returned."),
        ],
        store=store,
    )
    assert not any(block.type == "resource_list" for block in response.blocks)


def test_reviewed_lore_catalog_hosts_can_reach_main_column_resources():
    store = CanonicalStore()
    response = compose_experience_response(
        question="How did Friend of the Devil change?",
        thread_id="lore-catalog-test",
        messages=[
            tool_message(
                {
                    "research": {
                        "records": [
                            {
                                "resource_id": "lore:friend:deadhead-high",
                                "title": "How Grateful Dead Songs Changed Live",
                                "url": "https://deadheadhigh.com/guides/how-grateful-dead-songs-changed-live",
                                "source": "editorial",
                                "resource_type": "lore_source_trail",
                            }
                        ]
                    }
                }
            ),
            AIMessage(content="I found a useful listening trail."),
        ],
        store=store,
    )
    resources = [block for block in response.blocks if block.type == "resource_list"]
    assert any(item.title == "How Grateful Dead Songs Changed Live" for block in resources for item in block.items)


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


def test_multi_year_song_produces_a_chronological_comparison_strip_with_one_stop_per_year():
    store = CanonicalStore()
    song = store.resolve_song("Ripple")
    assert song
    context = store.song_context(song)
    response = compose_experience_response(
        question="How did Ripple change over the years?",
        thread_id="web-test",
        messages=[tool_message(context), AIMessage(content="Ripple appears across several years of the current library.")],
        store=store,
    )
    strip = next(block for block in response.blocks if block.type == "comparison_strip")

    def show_date(performance):
        return (store.one("shows", performance["show_id"]) or {}).get("show_date") or ""

    dated = sorted(context["performances"], key=lambda performance: (show_date(performance), int(performance.get("position_in_set") or 0)))
    expected_years = sorted({int(show_date(performance)[:4]) for performance in dated if show_date(performance)})
    assert [item.year for item in strip.items] == expected_years
    # Each stop is the chronologically first known performance of its year.
    for item in strip.items:
        first_of_year = next(performance for performance in dated if show_date(performance).startswith(str(item.year)))
        assert item.performance_id == first_of_year["performance_id"]
        assert item.show_date == show_date(first_of_year)
        assert f"Tell me about the performance of Ripple on {item.show_date}." == item.follow_up
    assert strip.known_count == len(context["performances"])
    assert "not a complete" in strip.coverage_note
    assert "current library coverage" in strip.coverage_note
    # The strip is a candidate alongside the existing performance evidence, not a replacement.
    assert any(block.type == "performance_list" for block in response.blocks)
    assert any(block.type == "performance_extremes" for block in response.blocks)


def test_single_year_song_produces_no_comparison_strip():
    stub_store, performances = _stub_performances(["1972-08-27", "1972-08-21", "1972-11-13"])
    strip = experience._comparison_strip({"song_id": "song:1", "title": "Sugaree"}, performances, stub_store)
    assert strip is None


def test_comparison_strip_spreads_more_than_twelve_years_and_keeps_the_endpoints():
    store = CanonicalStore()
    song = store.resolve_song("Sugaree")
    assert song
    context = store.song_context(song)
    response = compose_experience_response(
        question="Compare Sugaree across eras.",
        thread_id="web-test",
        messages=[tool_message(context), AIMessage(content="Sugaree spans decades of the current library.")],
        store=store,
    )
    strip = next(block for block in response.blocks if block.type == "comparison_strip")

    all_years = sorted(
        {
            int((store.one("shows", performance["show_id"]) or {}).get("show_date", "")[:4])
            for performance in context["performances"]
            if (store.one("shows", performance["show_id"]) or {}).get("show_date")
        }
    )
    assert len(all_years) > 12
    strip_years = [item.year for item in strip.items]
    assert len(strip_years) <= 12
    assert strip_years == sorted(strip_years)
    assert strip_years[0] == all_years[0]
    assert strip_years[-1] == all_years[-1]
    assert set(strip_years) <= set(all_years)


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


def test_model_guided_composer_revises_an_overfull_layout_instead_of_dumping_candidates():
    store = CanonicalStore()
    show = store.resolve_show("1972-08-27")
    assert show
    response = compose_experience_response(
        question="Tell me about the show.",
        thread_id="web-test",
        messages=[tool_message(store.show_context(show)), AIMessage(content="The show is in the library.")],
        store=store,
    )
    setlist_index = next(index for index, block in enumerate(response.blocks) if block.type == "show_setlist")
    recording_index = next(index for index, block in enumerate(response.blocks) if block.type == "recording_list")
    first_plan = CompositionPlan(
        mode="show",
        sections=[CompositionSection(region="primary", candidate_indexes=list(range(min(8, len(response.blocks)))))],
    )
    revised_plan = CompositionPlan(
        mode="show",
        sections=[CompositionSection(region="primary", candidate_indexes=[setlist_index, recording_index])],
    )
    stub = SelectionSequenceStub([first_plan, revised_plan])

    composed = ModelGuidedComposer(selector=stub, max_blocks=2).compose("Tell me about the show.", response)

    assert [block.type for block in composed.blocks] == ["show_setlist", "recording_list"]
    assert composed.layout[0].block_indexes == [0, 1]
    assert len(stub.inputs) == 2


def _one_block_of_every_type():
    performance = experience.PerformanceListItem(
        performance_id="p1", show_id="s1", show_date="1972-08-27", show_label="Veneta — 1972-08-27", follow_up="Show me this performance"
    )
    return [
        experience.EntityCardBlock(type="entity_card", entity_type="song", entity_id="song:1", title="Sugaree", source_id="src:1"),
        experience.ShowSetlistBlock(
            type="show_setlist",
            show_id="s1",
            title="Setlist",
            sets=[
                experience.SetlistSection(
                    label="Set 1",
                    songs=[experience.SetlistSong(performance_id="p1", song_id="song:1", title="Sugaree", follow_up="Show me this song")],
                )
            ],
        ),
        experience.ShowSelectionBlock(
            type="show_selection",
            title="20 Essential Grateful Dead Shows",
            selection_type="critic/editorial selection",
            selector_name="David Fricke / Rolling Stone",
            coverage_note="One source selection, not a ranking.",
            source_id="selection:critic-show-selection-1",
            items=[
                experience.ShowSelectionItem(
                    show_id="s1",
                    show_date="1972-08-27",
                    venue_name="Old Renaissance Faire Grounds",
                    follow_up="Tell me about the show.",
                )
            ],
        ),
        experience.RecordingListBlock(
            type="recording_list",
            show_id="s1",
            title="Recordings",
            items=[experience.RecordingItem(recording_id="r1", title="SBD", source_type="soundboard", url="https://archive.org/details/x", source_id="src:1")],
        ),
        experience.PerformerListBlock(
            type="performer_list",
            show_id="s1",
            title="Performers",
            items=[experience.PerformerItem(person_id="pe1", name="Jerry Garcia", role="performer", instruments=["guitar"], follow_up="Who played")],
        ),
        experience.EquipmentListBlock(
            type="equipment_list",
            show_id="s1",
            title="Guitars",
            items=[
                experience.EquipmentItem(
                    equipment_id="e1",
                    name="Tiger",
                    manufacturer="Doug Irwin",
                    model="Tiger",
                    usage_context="primary electric",
                    claim_type="show",
                    evidence="photograph",
                    source_id="src:1",
                    source_url="https://example.com/evidence",
                    follow_up="Tell me about Tiger",
                )
            ],
        ),
        experience.ResourceListBlock(
            type="resource_list",
            title="Resources",
            items=[experience.ResourceItem(resource_id="res1", title="Essay", resource_type="article", source_name="Site", url="https://example.com", source_id="src:1")],
        ),
        experience.CreditListBlock(
            type="credit_list",
            title="Credits",
            items=[experience.CreditItem(person_id="pe2", name="Robert Hunter", role="lyrics")],
            source_ids=["src:1"],
        ),
        experience.SongOverviewBlock(type="song_overview", song_id="song:1", title="Sugaree", known_performance_count=1),
        experience.MediaLinkBlock(type="media_link", title="Listen", provider="youtube", url="https://www.youtube.com/watch?v=x", link_type="video", is_official=False),
        experience.PerformanceListBlock(type="performance_list", title="Performances", song_id="song:1", known_count=1, items=[performance]),
        experience.PerformanceExtremesBlock(type="performance_extremes", song_id="song:1", title="First and last", first=performance, last=performance),
        experience.PerformanceSpineBlock(type="performance_spine", performance_id="p1", song_id="song:1", title="Sugaree", show_label="Veneta — 1972-08-27"),
        experience.ComparisonStripBlock(
            type="comparison_strip",
            song_id="song:1",
            title="Performances over time",
            known_count=2,
            coverage_note="Representative selections from current library coverage, not a complete performance history.",
            items=[
                experience.ComparisonStripItem(
                    performance_id="p1",
                    show_id="s1",
                    year=1972,
                    show_date="1972-08-27",
                    show_label="Veneta — 1972-08-27",
                    follow_up="Tell me about the performance of Sugaree on 1972-08-27.",
                ),
                experience.ComparisonStripItem(
                    performance_id="p2",
                    show_id="s2",
                    year=1977,
                    show_date="1977-05-08",
                    show_label="Barton Hall — 1977-05-08",
                    follow_up="Tell me about the performance of Sugaree on 1977-05-08.",
                ),
            ],
        ),
        experience.CoverageBlock(type="coverage", title="Current library coverage", message="Coverage is partial."),
        experience.ArrangementBlock(type="arrangement", title="Arrangement", resource_id="res1", source_id="src:1", arrangement_scope="recorded-song-interpretation"),
        experience.ArrangementSearchBlock(
            type="arrangement_search",
            title="Documented arrangements in B",
            key_signature="B",
            coverage_note="Documented arrangements only, not a universal key.",
            items=[
                experience.ArrangementSearchItem(
                    arrangement_id="a1",
                    song_id="song:1",
                    title="Sugaree",
                    resource_id="res1",
                    resource_title="Chords",
                    source_name="Site",
                    url="https://example.com",
                    key_signature="B",
                    arrangement_scope="recorded-song-interpretation",
                    follow_up="Play Sugaree",
                )
            ],
        ),
        experience.ProvenanceNoteBlock(type="provenance_note", text="Contextual material differs from canonical facts.", source_ids=["src:1"]),
        experience.GapStateBlock(type="gap_state", message="Not in the current library."),
    ]


def test_every_block_type_brief_carries_structured_usage_guidance():
    blocks = _one_block_of_every_type()
    union_members = get_args(get_args(experience.ExperienceBlock)[0])
    all_block_types = {get_args(member.model_fields["type"].annotation)[0] for member in union_members}
    assert {block.type for block in blocks} == all_block_types
    for index, block in enumerate(blocks):
        brief = _block_brief(index, block)
        assert brief["index"] == index
        assert brief["type"] == block.type
        for field in ("scope", "helps_with", "usage_guidance", "provenance"):
            assert isinstance(brief.get(field), str) and brief[field].strip(), f"{block.type} brief is missing {field}"
        assert "decision_tradeoff" not in brief


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
    agent = FakeAgent([AIMessage(content="The grounded follow-up answer.")])
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
            tool_message(store.show_context(show)),
            AIMessage(content="The Veneta show was held on August 27, 1972."),
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
    agent = FakeAgent([AIMessage(content="The grounded follow-up answer.")])
    settings = Settings(rate_limit_per_minute=0)
    client = TestClient(create_app(settings=settings, store=CanonicalStore(), agent=agent))

    for _ in range(5):
        assert client.post("/api/experience", json={"question": "Tell me about Veneta"}).status_code == 200


def test_agent_receives_only_the_most_recent_conversation_window_turns():
    long_conversation = []
    for index in range(20):
        long_conversation.append({"role": "user", "text": f"Question {index}"})
        long_conversation.append({"role": "assistant", "text": f"Answer {index}"})
    agent = FakeAgent([AIMessage(content="The grounded follow-up answer.")])
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
    agent = FakeAgent([AIMessage(content="The grounded follow-up answer.")])
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
    client = TestClient(create_app(agent=FakeAgent([]), client_dist=client_dist))
    page = client.get("/songs/sugaree")
    assert page.status_code == 200
    assert "Deadbot client" in page.text
