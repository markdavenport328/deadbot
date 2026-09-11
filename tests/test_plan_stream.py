import json

from langchain_core.messages import AIMessageChunk

from deadbot.plan_stream import PlanEvent, PlanStreamer


def chunk(args: str, *, name: str | None = None, call_id: str = "f1", index: int = 0) -> AIMessageChunk:
    return AIMessageChunk(
        content="",
        tool_call_chunks=[{"name": name, "args": args, "id": call_id, "index": index, "type": "tool_call_chunk"}],
    )


PLAN = {
    "chat_answer": "Sugaree opened the \"second\" set, with a } brace and a \\ backslash.",
    "title": "Sugaree at Veneta",
    "lead": "A relaxed early version.",
    "groups": [
        {
            "title": "The night",
            "lead": None,
            "presentation": "comparison",
            "criteria": ["Pace", "Jam"],
            "items": [
                {"type": "show_unit", "show_id": "gd-1972-08-27", "emphasis": "primary", "judgments": ["Relaxed", "Long", "Extra"],
                 "supporting_sources": [{"url": "https://archive.org/details/x", "note": "A note with {braces} and [brackets]."}]},
                {"type": "editorial", "presentation": "narrative", "paragraphs": ["Text, with commas: and colons."], "items": []},
            ],
        },
        {"presentation": "collection", "items": [{"type": "song_overview", "song_id": "song-sugaree"}]},
    ],
}
PLAN_TEXT = json.dumps(PLAN)


def fake_resolve(items):
    item = items[0]
    return [{"type": item.type, "id": getattr(item, "show_id", None) or getattr(item, "song_id", None) or "editorial", "judgments": list(getattr(item, "judgments", []))}]


def drive(text: str, pieces: int) -> list[PlanEvent]:
    streamer = PlanStreamer(fake_resolve)
    events: list[PlanEvent] = []
    size = max(1, len(text) // pieces)
    for offset in range(0, len(text), size):
        fragment = text[offset : offset + size]
        events.extend(streamer.feed(chunk(fragment, name="finish_response" if offset == 0 else None)))
    return events


def test_events_arrive_in_reading_order_with_group_metadata():
    events = drive(PLAN_TEXT, 1)
    types = [event.type for event in events]
    assert types == ["page_head", "group_open", "block", "block", "group_close", "group_open", "block", "group_close"]
    assert events[0].payload == {"title": "Sugaree at Veneta", "lead": "A relaxed early version."}
    assert events[1].payload == {"index": 0, "title": "The night", "lead": None, "presentation": "comparison", "criteria": ["Pace", "Jam"]}
    assert events[2].payload["group_index"] == 0 and events[2].payload["block"]["id"] == "gd-1972-08-27"
    assert events[3].payload["block"]["type"] == "editorial"
    assert events[5].payload["presentation"] == "collection" and events[5].payload["criteria"] == []


def test_one_character_at_a_time_gives_identical_events():
    whole = drive(PLAN_TEXT, 1)
    by_char = drive(PLAN_TEXT, len(PLAN_TEXT))
    assert [(event.type, event.payload) for event in by_char] == [(event.type, event.payload) for event in whole]


def test_a_plan_with_no_groups_emits_the_head_when_the_call_completes():
    events = drive(json.dumps({"chat_answer": "Hi", "title": "Deadbot", "lead": None, "groups": []}), 3)
    assert [event.type for event in events] == ["page_head"]
    assert events[0].payload == {"title": "Deadbot", "lead": None}


def test_a_retried_call_resets_the_draft():
    streamer = PlanStreamer(fake_resolve)
    first = streamer.feed(chunk('{"chat_answer": "x", "title": "First", "groups": [{"presentation": "collection", "items": [', name="finish_response"))
    assert [event.type for event in first] == ["page_head", "group_open"]
    second = streamer.feed(chunk('{"chat_answer": "y", "title": "Second", "groups": []}', name="finish_response", call_id="f2", index=1))
    assert [event.type for event in second] == ["page_reset", "page_head"]
    assert second[1].payload["title"] == "Second"


def test_malformed_json_disables_events_without_raising():
    streamer = PlanStreamer(fake_resolve)
    events = streamer.feed(chunk('{"chat_answer": "x", "groups": ]]]', name="finish_response"))
    assert events == []
    assert streamer.disabled is True
    assert streamer.feed(chunk('{"title": "later"}')) == []


def test_chunks_from_other_tool_calls_are_ignored():
    streamer = PlanStreamer(fake_resolve)
    streamer.feed(chunk('{"query": "x"}', name="search_entities", call_id="s1", index=0))
    events = streamer.feed(chunk('{"chat_answer": "x", "title": "T", "groups": []}', name="finish_response", call_id="f1", index=1))
    assert [event.type for event in events] == ["page_head"]


def test_invalid_items_are_skipped_and_judgments_are_truncated_to_criteria():
    plan = {"chat_answer": "x", "title": "T", "groups": [{"presentation": "comparison", "criteria": ["A"], "items": [
        {"type": "not_a_block"},
        {"type": "show_unit", "show_id": "gd-1972-08-27", "judgments": ["one", "two"]},
    ]}]}

    class Block:
        def __init__(self, judgments):
            self.judgments = judgments
        def model_copy(self, update):
            return Block(update["judgments"])
        def model_dump(self, mode):
            return {"judgments": self.judgments}

    streamer = PlanStreamer(lambda items: [Block(list(items[0].judgments))])
    events = streamer.feed(chunk(json.dumps(plan), name="finish_response"))
    blocks = [event for event in events if event.type == "block"]
    assert len(blocks) == 1
    assert blocks[0].payload["block"] == {"judgments": ["one"]}


def test_group_leads_run_through_link_grounding():
    plan = {
        "chat_answer": "x",
        "title": "T",
        "lead": None,
        "groups": [
            {"presentation": "collection", "lead": "See [x](https://example.com/not-returned) for more.", "items": []},
            {"presentation": "collection", "lead": "See [ok](https://archive.org/ok) for more.", "items": []},
        ],
    }
    streamer = PlanStreamer(fake_resolve, grounded_urls=frozenset({"https://archive.org/ok"}))
    events = streamer.feed(chunk(json.dumps(plan), name="finish_response"))
    opens = [event for event in events if event.type == "group_open"]
    assert len(opens) == 2
    assert opens[0].payload["lead"] == "See x for more."
    assert opens[1].payload["lead"] == "See [ok](https://archive.org/ok) for more."


def test_a_failing_item_is_skipped_without_disabling_the_streamer():
    plan = {"chat_answer": "x", "title": "T", "groups": [{"presentation": "collection", "items": [
        {"type": "song_overview", "song_id": "bad-song"},
        {"type": "song_overview", "song_id": "good-song"},
    ]}]}

    def resolve(items):
        item = items[0]
        if item.song_id == "bad-song":
            raise RuntimeError("boom")
        return fake_resolve(items)

    streamer = PlanStreamer(resolve)
    events = streamer.feed(chunk(json.dumps(plan), name="finish_response"))
    blocks = [event for event in events if event.type == "block"]
    assert len(blocks) == 1
    assert blocks[0].payload["block"]["id"] == "good-song"
    assert streamer.disabled is False


def test_items_past_the_group_limit_are_not_streamed():
    items = [{"type": "show_unit", "show_id": f"gd-1990-03-{day:02d}"} for day in range(1, 24)]
    plan = {"chat_answer": "x", "title": "T", "groups": [{"presentation": "collection", "items": items}]}
    events = drive(json.dumps(plan), 7)
    blocks = [event for event in events if event.type == "block"]
    assert len(blocks) == 20
    assert blocks[-1].payload["block"]["id"] == "gd-1990-03-20"


def test_indented_json_gives_identical_events_to_compact_json():
    indented = json.dumps(PLAN, indent=2)
    compact_events = drive(PLAN_TEXT, 1)
    indented_events = drive(indented, 1)
    assert [(event.type, event.payload) for event in indented_events] == [(event.type, event.payload) for event in compact_events]


def test_criteria_listed_after_items_still_reach_group_close():
    plan = {"chat_answer": "x", "title": "T", "groups": [
        {"presentation": "comparison", "items": [
            {"type": "show_unit", "show_id": "gd-1972-08-27", "judgments": ["one"]},
        ], "criteria": ["Pace"]},
    ]}
    events = drive(json.dumps(plan), 1)
    opens = [event for event in events if event.type == "group_open"]
    closes = [event for event in events if event.type == "group_close"]
    assert opens[0].payload["criteria"] == []
    assert closes[0].payload["criteria"] == ["Pace"]
