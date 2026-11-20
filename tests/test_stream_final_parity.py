"""One plan through both paths: the page the browser drafts from the stream is the page delivered.

The streamed path is :class:`deadbot.plan_stream.PlanStreamer` fed the raw
``finish_response`` text and reduced the way the browser reduces its events
(web/src/core/page-draft.ts). The delivered path is
:func:`deadbot.finish.build_experience_response` over the same call. Both use
the real store and the real resolution.
"""

import json

import pytest
from langchain_core.messages import AIMessage, AIMessageChunk, HumanMessage, ToolMessage

from deadbot import finish
from deadbot.data import CanonicalStore
from deadbot.plan_stream import PlanStreamer

SHOW = "gd-1972-08-27"
PAYLOADS = [{"show": {"show_id": SHOW}}]


@pytest.fixture(scope="module")
def store():
    return CanonicalStore()


def streamed_page(text: str, store, pieces: int) -> list[dict]:
    """The sections a browser holds once the stream ends, as page-draft.ts builds them."""

    grounded = finish.grounded_context(PAYLOADS)
    streamer = PlanStreamer(lambda items: finish.resolve_items(items, grounded, PAYLOADS, store)[0], grounded_urls=grounded.urls)
    events = []
    size = max(1, len(text) // pieces)
    for offset in range(0, len(text), size):
        chunk = AIMessageChunk(
            content="",
            tool_call_chunks=[{
                "name": finish.FINISH_TOOL_NAME if offset == 0 else None,
                "args": text[offset : offset + size],
                "id": "f1",
                "index": 0,
                "type": "tool_call_chunk",
            }],
        )
        events.extend(streamer.feed(chunk))
    assert not streamer.disabled
    groups: list[dict] = []
    for event in events:
        if event.type in ("page_reset", "groups_reset"):
            groups = []
        if event.type not in ("group_open", "group_close", "block"):
            continue
        index = event.payload["group_index" if event.type == "block" else "index"]
        while len(groups) <= index:
            groups.append({"title": None, "lead": None, "blocks": []})
        if event.type == "block":
            groups[index]["blocks"].append(event.payload["block"])
        else:
            groups[index].update(title=event.payload["title"], lead=event.payload["lead"])
    # A section with no heading, no text and no blocks draws nothing.
    return [group for group in groups if group["title"] or group["lead"] or group["blocks"]]


def delivered_page(text: str, store) -> list[dict]:
    """The sections of the finished response, in the same shape."""

    messages = [
        HumanMessage(content="Q"),
        AIMessage(content="", tool_calls=[{"name": "get_show", "args": {}, "id": "c1"}]),
        ToolMessage(content=json.dumps(PAYLOADS[0]), tool_call_id="c1", name="get_show"),
        AIMessage(content="", tool_calls=[{"name": finish.FINISH_TOOL_NAME, "args": finish.read_joining_repeats(text), "id": "f1"}]),
    ]
    response = finish.build_experience_response("Q", "t", messages, store).model_dump(mode="json")
    assert response["mode"] == "answer"
    return [
        {"title": group["title"], "lead": group["lead"], "blocks": [response["blocks"][index] for index in group["block_indexes"]]}
        for group in response["groups"]
    ]


def both(page: dict | str, store) -> list[dict]:
    """The page from both paths, asserted equal however the text is cut into chunks."""

    text = page if isinstance(page, str) else json.dumps(page)
    delivered = delivered_page(text, store)
    for pieces in (1, 7, len(text)):
        assert streamed_page(text, store, pieces) == delivered, pieces
    return delivered


def words(group: dict) -> str:
    """Everything a section says, heading to last block, as one string."""

    return json.dumps(group)


def test_two_sections_of_words_alone_are_delivered(store):
    """Reported: a plan of two sections with a heading and text and no cards came back with no groups."""

    page = {
        "answer": "They played it 52 times.",
        "sections": [
            {"heading": "Why it mattered", "text": "The Garden was home turf by 1987."},
            {"heading": "What to hear", "text": "- The 1990 run\n- The 1991 run", "items": []},
        ],
    }
    delivered = both(page, store)
    assert len(delivered) == 2
    assert "Why it mattered" in words(delivered[0]) and "home turf" in words(delivered[0])
    assert "What to hear" in words(delivered[1]) and "The 1991 run" in words(delivered[1])
    # A section of words alone is a block of prose, so every shell draws it.
    assert all(group["blocks"] for group in delivered)


def test_every_section_the_stream_showed_is_delivered(store):
    page = {
        "headline": "Veneta",
        "answer": "A benefit in a hot Oregon field.",
        "sections": [
            {"heading": "No items key", "text": "Words one."},
            {"heading": "Empty items", "text": "Words two.", "items": []},
            {"heading": "Nothing resolves", "text": "Words three.", "items": [{"type": "show", "show_id": "gd-1999-01-01"}]},
            {"text": "Words four, with no heading."},
            {"heading": "A heading alone"},
            {"heading": "The night", "text": "Words six.", "items": [{"type": "show", "show_id": SHOW}]},
            {"heading": "Unresolved with a note", "items": [{"type": "show", "show_id": "gd-1999-01-01", "note": "The note stays."}]},
            {"heading": "  ", "text": " ", "items": []},
        ],
    }
    delivered = both(page, store)
    assert len(delivered) == 7  # the last section is blank, so it draws nothing in either path
    told = "\n".join(words(group) for group in delivered)
    for text in ("No items key", "Words one.", "Empty items", "Words two.", "Nothing resolves", "Words three.", "Words four", "A heading alone", "The night", "Words six.", "The note stays."):
        assert text in told, text
    night = next(group for group in delivered if group["title"] == "The night")
    assert night["lead"] == "Words six." and [block["type"] for block in night["blocks"]] == ["show_unit"]


def test_a_section_heading_written_as_title_and_text_as_lead_is_delivered(store):
    page = {"answer": "A.", "sections": [{"title": "Old key heading", "lead": "Old key text.", "items": [{"type": "show", "show_id": SHOW}]}]}
    delivered = both(page, store)
    assert [(group["title"], group["lead"]) for group in delivered] == [("Old key heading", "Old key text.")]


def test_an_item_written_straight_into_sections_is_delivered(store):
    page = {"answer": "A.", "sections": [{"type": "show", "show_id": SHOW, "note": "Straight in."}, {"heading": "After", "text": "Words."}]}
    delivered = both(page, store)
    assert [block["type"] for block in delivered[0]["blocks"]] == ["show_unit"]
    assert "After" in words(delivered[1])


def test_items_beside_sections_are_delivered(store):
    for page in (
        '{"answer": "A.", "sections": [{"heading": "One", "text": "Words."}], "items": [{"type": "show", "show_id": "%s"}]}' % SHOW,
        '{"answer": "A.", "items": [{"type": "show", "show_id": "%s"}], "sections": [{"heading": "One", "text": "Words."}]}' % SHOW,
    ):
        delivered = both(page, store)
        assert sorted(len(group["blocks"]) for group in delivered) == [1, 1]
        assert any(block["type"] == "show_unit" for group in delivered for block in group["blocks"])


def test_a_page_that_mixes_the_older_keys_is_delivered(store):
    section = {"heading": "One", "text": "Words.", "items": [{"type": "show", "show_id": SHOW}]}
    for page in ({"answer": "A.", "groups": [section]}, {"lead": "A.", "sections": [section]}):
        delivered = both(page, store)
        assert [(group["title"], group["lead"], len(group["blocks"])) for group in delivered] == [("One", "Words.", 1)]


def test_words_alone_survive_a_second_sections_list(store):
    """The model sometimes writes "sections" twice: a continuation, or the page restated."""

    night = json.dumps({"heading": "The night", "items": [{"type": "show", "show_id": SHOW}]})
    said = json.dumps({"heading": "What was said", "text": "Words alone."})
    for text, headings in (
        ('{"answer": "A.", "sections": [' + night + '], "sections": [' + said + "]}", ["The night", "What was said"]),
        ('{"answer": "A.", "sections": [' + night + '], "sections": [' + night + ", " + said + "]}", ["The night", "What was said"]),
        ('{"answer": "A.", "sections": [' + said + '], "sections": [' + said + ", " + night + "]}", ["What was said", "The night"]),
        ('{"answer": "A.", "sections": [' + night + '], "groups": [' + said + "]}", ["The night", "What was said"]),
    ):
        delivered = both(text, store)
        assert [group["title"] for group in delivered] == headings, text
        assert "Words alone." in "".join(words(group) for group in delivered)


def test_an_older_plan_group_of_words_alone_is_delivered(store):
    page = {"lead": "A.", "groups": [{"title": "Words alone", "lead": "No items key."}, {"title": "Empty", "lead": "No items.", "items": []}]}
    delivered = both(page, store)
    assert len(delivered) == 2 and "No items key." in words(delivered[0]) and "No items." in words(delivered[1])


def test_an_item_of_a_type_the_page_does_not_have_is_delivered_as_its_words(store):
    """Its words are the model's work: prose in the draft and in the delivered page, never a failed plan."""

    page = {
        "answer": "A.",
        "sections": [{
            "heading": "One night",
            "items": [
                {"type": "performance_unit", "performance_id": "gd-1972-08-27-dark-star", "note": "The retired card's note."},
                {"type": "no_such_component", "title": "A title", "text": "Some text."},
                {"type": "show", "show_id": SHOW},
            ],
        }],
    }
    (section,) = both(page, store)
    assert [block["type"] for block in section["blocks"]] == ["editorial", "editorial", "show_unit"]
    assert section["blocks"][0]["paragraphs"] == ["The retired card's note."]
    assert section["blocks"][1]["title"] == "A title" and section["blocks"][1]["paragraphs"] == ["Some text."]
