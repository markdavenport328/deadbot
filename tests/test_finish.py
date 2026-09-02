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


def _veneta_payloads(store):
    show = store.resolve_show("1972-08-27")
    song = store.resolve_song("Sugaree")
    return [store.show_context(show), store.song_context(song)]


def test_resolve_body_builds_referenced_components_with_model_titles():
    store = CanonicalStore()
    payloads = _veneta_payloads(store)
    grounded = finish.grounded_context(payloads)
    plan = finish.FinishPlan(
        chat_answer="x",
        title="Veneta",
        lead=None,
        mode="show",
        body=[
            finish.ShowSetlistRef(type="show_setlist", show_id="gd-1972-08-27", title="The whole night"),
            finish.RecordingListRef(type="recording_list", show_id="gd-1972-08-27", recording_ids=["recording-gd-1972-08-27-sbd-4682"]),
            finish.ComparisonStripRef(type="comparison_strip", song_id="song-sugaree"),
        ],
    )
    blocks, sources = finish.resolve_body(plan, grounded, payloads, store)
    assert [block.type for block in blocks] == ["show_setlist", "recording_list", "comparison_strip"]
    assert blocks[0].title == "The whole night"
    assert [item.recording_id for item in blocks[1].items] == ["recording-gd-1972-08-27-sbd-4682"]
    assert any(source.url and "archive.org" in source.url for source in sources)


def test_resolve_body_drops_references_the_tools_did_not_return():
    store = CanonicalStore()
    payloads = _veneta_payloads(store)
    grounded = finish.grounded_context(payloads)
    plan = finish.FinishPlan(
        chat_answer="x",
        title="t",
        lead=None,
        mode="show",
        body=[
            finish.ShowSetlistRef(type="show_setlist", show_id="gd-1977-05-08"),
            finish.MediaLinkRef(type="media_link", url="https://www.youtube.com/watch?v=notretrieved"),
            finish.ShowSetlistRef(type="show_setlist", show_id="gd-1972-08-27"),
        ],
    )
    blocks, _ = finish.resolve_body(plan, grounded, payloads, store)
    assert [block.type for block in blocks] == ["show_setlist"]
    assert blocks[0].show_id == "gd-1972-08-27"


def test_resolve_body_keeps_editorial_blocks_and_strips_ungrounded_links():
    store = CanonicalStore()
    payloads = _veneta_payloads(store)
    grounded = finish.grounded_context(payloads)
    good_url = next(url for url in grounded.urls if "archive.org" in url)
    plan = finish.FinishPlan(
        chat_answer="x",
        title="t",
        lead=None,
        mode="show",
        body=[
            {
                "type": "editorial",
                "presentation": "fact_grid",
                "eyebrow": None,
                "title": "Ways in",
                "paragraphs": [f"Start with the [soundboard]({good_url}) or [this](https://example.com/no)."],
                "items": [
                    {"marker": "SBD", "title": "Soundboard", "value": None, "detail": None, "follow_up": None, "link": {"url": good_url, "label": "Archive"}},
                    {"marker": "Bad", "title": "Nope", "value": None, "detail": None, "follow_up": None, "link": {"url": "https://example.com/no", "label": "x"}},
                ],
            }
        ],
    )
    blocks, _ = finish.resolve_body(plan, grounded, payloads, store)
    block = blocks[0]
    assert block.paragraphs[0] == f"Start with the [soundboard]({good_url}) or this."
    assert block.items[0].link is not None and block.items[1].link is None


def test_resolve_body_resolves_guest_appearances_from_the_turn_payload():
    store = CanonicalStore()
    from deadbot.tools import build_tools

    guest_tool = next(tool for tool in build_tools(store) if tool.name == "search_guest_musicians")
    payload = json.loads(guest_tool.invoke({"query": "Branford"}))
    person_id = payload["guests"][0]["person_id"]
    grounded = finish.grounded_context([payload])
    plan = finish.FinishPlan(
        chat_answer="x", title="t", lead=None, mode="musician",
        body=[finish.GuestAppearancesRef(type="guest_appearance_list", person_id=person_id)],
    )
    blocks, _ = finish.resolve_body(plan, grounded, [payload], store)
    assert blocks[0].type == "guest_appearance_list" and blocks[0].person_id == person_id
