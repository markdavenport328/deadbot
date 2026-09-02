import json

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from deadbot import finish
from deadbot.data import CanonicalStore


def tool_message(payload, name="get_show"):
    return ToolMessage(content=json.dumps(payload), tool_call_id="call-1", name=name)


def test_grounded_context_collects_ids_and_urls_from_tool_payloads():
    payloads = [
        {"show": {"show_id": "gd-1972-08-27"}, "performances": [{"performance_id": "gd-1972-08-27-sugaree"}]},
        {"matches": [{"entity_type": "song", "id": "song-sugaree", "label": "Sugaree"}]},
        {"resources": [{"resource_id": "resource-1", "source_url": "https://www.dead.net/song/sugaree"}]},
        {"recordings": [{"recording_id": "recording-1", "archive_identifier": "gd1972-08-27.sbd.4682.shnf"}]},
    ]
    grounded = finish.grounded_context(payloads)
    assert {"gd-1972-08-27", "gd-1972-08-27-sugaree", "song-sugaree", "resource-1", "recording-1", "gd1972-08-27.sbd.4682.shnf"} <= grounded.ids
    assert "https://www.dead.net/song/sugaree" in grounded.urls


def test_keep_grounded_links_strips_urls_the_tools_did_not_return():
    urls = frozenset({"https://archive.org/details/gd1972-08-27"})
    text = "Hear it on [Archive.org](https://archive.org/details/gd1972-08-27) or [elsewhere](https://example.com/x)."
    assert finish.keep_grounded_links(text, urls) == "Hear it on [Archive.org](https://archive.org/details/gd1972-08-27) or elsewhere."


def test_finish_plan_accepts_editorial_blocks_and_library_references():
    plan = finish.FinishPlan.model_validate(
        {
            "chat_answer": "Sugaree opened the second set.",
            "title": "Sugaree at Veneta",
            "lead": "A relaxed early version.",
            "mode": "performance",
            "body": [
                {
                    "type": "editorial",
                    "presentation": "narrative",
                    "eyebrow": None,
                    "title": "Why this one",
                    "paragraphs": ["Garcia stretches the solo."],
                    "items": [],
                },
                {"type": "show_setlist", "show_id": "gd-1972-08-27", "title": "The whole night"},
                {"type": "recording_list", "show_id": "gd-1972-08-27", "recording_ids": ["recording-gd-1972-08-27-sbd-4682"], "title": None},
            ],
        }
    )
    assert [item.type for item in plan.body] == ["editorial", "show_setlist", "recording_list"]
    assert plan.body[1].title == "The whole night"


def test_finish_tool_uses_the_plan_schema_and_confirms_delivery():
    tool = finish.build_finish_tool()
    assert tool.name == finish.FINISH_TOOL_NAME
    assert tool.args_schema is finish.FinishPlan
    assert "finished" in tool.description.casefold() or "deliver" in tool.description.casefold()
    result = tool.invoke(
        {"chat_answer": "Hi", "title": "Deadbot", "lead": None, "mode": "quick_fact", "body": []}
    )
    assert "delivered" in result.casefold()
