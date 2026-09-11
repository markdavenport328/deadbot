import json

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from deadbot import composition, experience, finish
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


def test_finish_plan_accepts_editorial_blocks_and_unit_references_in_groups():
    plan = finish.FinishPlan.model_validate(
        {
            "chat_answer": "Sugaree opened the second set.",
            "title": "Sugaree at Veneta",
            "lead": "A relaxed early version.",
            "groups": [
                {
                    "presentation": "collection",
                    "items": [
                        {"type": "editorial", "presentation": "narrative", "title": "Why this one", "paragraphs": ["Garcia stretches the solo."], "items": []},
                        {"type": "show_unit", "show_id": "gd-1972-08-27", "emphasis": "primary", "visible_facets": ["setlist", "recordings"]},
                    ],
                }
            ],
        }
    )
    assert [item.type for item in plan.groups[0].items] == ["editorial", "show_unit"]
    assert plan.groups[0].items[1].emphasis == "primary"
    for field in ("mode", "body"):
        assert field not in finish.FinishPlan.model_fields


def test_finish_plan_rejects_removed_single_dimension_references():
    from pydantic import ValidationError

    for kind in ("show_setlist", "performer_list", "recording_list", "performance_list", "performance_extremes", "comparison_strip", "performance_spine", "show_explorer"):
        try:
            finish.GroupPlan.model_validate({"presentation": "collection", "items": [{"type": kind, "show_id": "x", "song_id": "y", "performance_id": "z", "items": []}]})
        except ValidationError:
            continue
        raise AssertionError(f"{kind} should no longer be accepted")


def test_role_maps_to_emphasis_when_emphasis_is_omitted():
    anchor = finish.ShowUnitRef(type="show_unit", show_id="gd-1972-08-27", role="anchor")
    contrast = finish.ShowUnitRef(type="show_unit", show_id="gd-1972-08-27", role="contrast")
    explicit = finish.ShowUnitRef(type="show_unit", show_id="gd-1972-08-27", role="anchor", emphasis="mention")
    assert finish._emphasis_for(anchor) == "primary"
    assert finish._emphasis_for(contrast) == "supporting"
    assert finish._emphasis_for(explicit) == "mention"
    assert finish._emphasis_for(finish.ShowUnitRef(type="show_unit", show_id="gd-1972-08-27")) == "supporting"


def test_finish_tool_uses_the_plan_schema_and_confirms_delivery():
    tool = finish.build_finish_tool()
    assert tool.name == finish.FINISH_TOOL_NAME
    assert tool.args_schema is finish.FinishPlan
    assert "finished" in tool.description.casefold() or "deliver" in tool.description.casefold()
    result = tool.invoke(
        {"chat_answer": "Hi", "title": "Deadbot", "lead": None, "groups": []}
    )
    assert "delivered" in result.casefold()


def _veneta_payloads(store):
    show = store.resolve_show("1972-08-27")
    song = store.resolve_song("Sugaree")
    return [store.show_context(show), store.song_context(song)]


def test_resolve_body_drops_references_the_tools_did_not_return():
    store = CanonicalStore()
    payloads = _veneta_payloads(store)
    grounded = finish.grounded_context(payloads)
    plan = finish.FinishPlan(
        chat_answer="x",
        title="t",
        lead=None,
        groups=[
            finish.GroupPlan(
                presentation="collection",
                items=[
                    finish.ShowUnitRef(type="show_unit", show_id="gd-1977-05-08", visible_facets=["setlist"]),
                    finish.MediaLinkRef(type="media_link", url="https://www.youtube.com/watch?v=notretrieved"),
                    finish.ShowUnitRef(type="show_unit", show_id="gd-1972-08-27", visible_facets=["setlist"]),
                ],
            )
        ],
    )
    blocks, _ = finish.resolve_items(plan.groups[0].items, grounded, payloads, store)
    assert [block.type for block in blocks] == ["show_unit"]
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
        groups=[
            finish.GroupPlan(
                presentation="collection",
                items=[
                    {
                        "type": "editorial",
                        "presentation": "fact_grid",
                        "eyebrow": None,
                        "title": "Ways in",
                        "paragraphs": [f"Start with the [soundboard]({good_url}) or [this](https://example.com/no)."],
                        "items": [
                            {"marker": "SBD", "title": "Soundboard", "value": None, "detail": None, "follow_ups": [], "link": {"url": good_url, "label": "Archive"}},
                            {"marker": "Bad", "title": "Nope", "value": None, "detail": None, "follow_ups": [], "link": {"url": "https://example.com/no", "label": "x"}},
                        ],
                    }
                ],
            )
        ],
    )
    blocks, _ = finish.resolve_items(plan.groups[0].items, grounded, payloads, store)
    block = blocks[0]
    assert block.paragraphs[0] == f"Start with the [soundboard]({good_url}) or this."
    assert block.items[0].link is not None and block.items[1].link is None


def test_resolve_body_keeps_a_song_payload_listening_link_and_strips_an_unreturned_one():
    store = CanonicalStore()
    song = store.resolve_song("Deal")
    payload = store.song_context(song)
    grounded = finish.grounded_context([payload])
    archive_url = next(
        performance["listen"]["archive_track_url"]
        for performance in payload["performances"]
        if "listen" in performance and "archive_track_url" in performance["listen"]
    )
    assert archive_url in grounded.urls
    plan = finish.FinishPlan(
        chat_answer="x",
        title="t",
        lead=None,
        groups=[
            finish.GroupPlan(
                presentation="collection",
                items=[
                    {
                        "type": "editorial",
                        "presentation": "narrative",
                        "eyebrow": None,
                        "title": "Hear it",
                        "paragraphs": [f"Listen on [Archive.org]({archive_url}) or [elsewhere](https://example.com/not-returned)."],
                        "items": [],
                    }
                ],
            )
        ],
    )
    blocks, _ = finish.resolve_items(plan.groups[0].items, grounded, [payload], store)
    assert blocks[0].paragraphs[0] == f"Listen on [Archive.org]({archive_url}) or elsewhere."


def test_resolve_body_resolves_guest_appearances_from_the_turn_payload():
    store = CanonicalStore()
    from deadbot.tools import build_tools

    guest_tool = next(tool for tool in build_tools(store) if tool.name == "search_guest_musicians")
    payload = json.loads(guest_tool.invoke({"query": "Branford"}))
    person_id = payload["guests"][0]["person_id"]
    grounded = finish.grounded_context([payload])
    plan = finish.FinishPlan(
        chat_answer="x", title="t", lead=None,
        groups=[finish.GroupPlan(presentation="collection", items=[finish.GuestAppearancesRef(type="guest_appearance_list", person_id=person_id)])],
    )
    blocks, _ = finish.resolve_items(plan.groups[0].items, grounded, [payload], store)
    assert blocks[0].type == "guest_appearance_list" and blocks[0].person_id == person_id


def test_resolve_body_hydrates_a_person_roster_from_the_turn_payload():
    store = CanonicalStore()
    from deadbot.tools import build_tools

    guest_tool = next(tool for tool in build_tools(store) if tool.name == "search_guest_musicians")
    payload = json.loads(guest_tool.invoke({"query": ""}))
    guests = payload["guests"]
    assert len(guests) > 12, "the roster exists for sets larger than an editorial grid"
    grounded = finish.grounded_context([payload])
    entries = [
        finish.PersonRosterEntry(person_id=guest["person_id"], note="cartwheels" if guest["name"] == "John Belushi" else None)
        for guest in guests
    ]
    entries.append(finish.PersonRosterEntry(person_id="person-nobody-mentioned-this-turn"))
    plan = finish.FinishPlan(
        chat_answer="x", title="t", lead=None,
        groups=[finish.GroupPlan(presentation="collection", items=[
            finish.PersonRosterRef(type="person_roster", title="Everyone who sat in", lead="One line.", entries=entries)
        ])],
    )
    blocks, _ = finish.resolve_items(plan.groups[0].items, grounded, [payload], store)
    block = blocks[0]
    assert block.type == "person_roster" and block.title == "Everyone who sat in" and block.lead == "One line."
    assert len(block.items) == len(guests), "every grounded person survives; the ungrounded one is dropped"
    first = block.items[0]
    assert first.name == guests[0]["name"] and first.show_count == guests[0]["guest_show_count"] and first.roles
    assert all(item.first_year and item.last_year for item in block.items)
    assert next(item for item in block.items if item.name == "John Belushi").note == "cartwheels"


def test_resolve_body_hydrates_a_person_roster_from_the_store_when_the_payload_has_no_guest_record():
    store = CanonicalStore()
    payload = {"lineup": [{"person_id": "person-bill-kreutzmann", "name": "Bill Kreutzmann"}]}
    grounded = finish.grounded_context([payload])
    plan = finish.FinishPlan(
        chat_answer="x", title="t", lead=None,
        groups=[finish.GroupPlan(presentation="collection", items=[
            finish.PersonRosterRef(type="person_roster", title="Drummers", entries=[finish.PersonRosterEntry(person_id="person-bill-kreutzmann")])
        ])],
    )
    blocks, _ = finish.resolve_items(plan.groups[0].items, grounded, [payload], store)
    item = blocks[0].items[0]
    assert item.name == "Bill Kreutzmann" and "drums" in item.roles and item.show_count > 1000 and item.first_year == "1965"


def test_resolve_body_resolves_research_and_canonical_resources_together():
    store = CanonicalStore()
    song = store.resolve_song("Sugaree")
    song_payload = store.song_context(song)
    canonical_resource_id = song_payload["resources"][0]["resource_id"]
    research_payload = {
        "research": {
            "state": "ok",
            "coverage": "metadata_only",
            "source": "dead.net",
            "records": [
                {
                    "entity_type": "song",
                    "identifier": "sugaree",
                    "title": "Sugaree | Dead.net",
                    "url": "https://www.dead.net/song/sugaree",
                    "description": "",
                    "published_at": "",
                    "source": "dead.net",
                }
            ],
        }
    }
    payloads = [song_payload, research_payload]
    grounded = finish.grounded_context(payloads)
    plan = finish.FinishPlan(
        chat_answer="x",
        title="t",
        lead=None,
        groups=[
            finish.GroupPlan(
                presentation="collection",
                items=[
                    finish.ResourceListRef(
                        type="resource_list",
                        resource_ids=[canonical_resource_id, "research:dead.net:sugaree", "research:dead.net:missing"],
                    )
                ],
            )
        ],
    )
    blocks, _ = finish.resolve_items(plan.groups[0].items, grounded, payloads, store)
    block = blocks[0]
    assert block.type == "resource_list"
    titles = [item.title for item in block.items]
    assert "Sugaree | Dead.net" in titles
    assert song_payload["resources"][0]["title"] in titles
    assert len(block.items) == 2


def test_resolve_body_resolves_song_overview():
    store = CanonicalStore()
    song = store.resolve_song("Sugaree")
    payload = store.song_context(song)
    grounded = finish.grounded_context([payload])
    plan = finish.FinishPlan(
        chat_answer="x", title="t", lead=None,
        groups=[finish.GroupPlan(presentation="collection", items=[finish.SongOverviewRef(type="song_overview", song_id=song["song_id"], visible_facets=["credits"])])],
    )
    blocks, _ = finish.resolve_items(plan.groups[0].items, grounded, [payload], store)
    block = blocks[0]
    assert block.type == "song_overview"
    assert block.title == song["title"]
    assert block.known_performance_count > 0
    assert block.credits and all(credit.name for credit in block.credits)


def test_song_overview_keeps_model_chosen_representative_performance_links():
    store = CanonicalStore()
    song = store.resolve_song("Sugaree")
    payload = store.song_context(song)
    chosen = next(performance for performance in payload["performances"] if performance.get("listen"))
    plan = finish.FinishPlan(
        chat_answer="x",
        title="t",
        lead=None,
        groups=[
            finish.GroupPlan(
                presentation="collection",
                items=[
                    finish.SongOverviewRef(
                        type="song_overview",
                        song_id=song["song_id"],
                        note="A song with a long onstage life.",
                        representative_performance_ids=[chosen["performance_id"]],
                    )
                ],
            )
        ],
    )
    blocks, _ = finish.resolve_items(plan.groups[0].items, finish.grounded_context([payload]), [payload], store)
    block = blocks[0]
    assert block.type == "song_overview"
    assert block.note == "A song with a long onstage life."
    assert [performance.performance_id for performance in block.representative_performances] == [chosen["performance_id"]]
    assert block.representative_performances[0].listen_url == chosen["listen"]["archive_track_url"]


def test_resolve_body_resolves_arrangement_from_song_arrangements_table():
    store = CanonicalStore()
    arrangement = next(iter(store.rows("song_arrangements")), None)
    assert arrangement is not None, "expected at least one row in song_arrangements for this test"
    song = store.one("songs", arrangement["song_id"])
    payload = store.song_context(song)
    grounded = finish.grounded_context([payload])
    plan = finish.FinishPlan(
        chat_answer="x", title="t", lead=None,
        groups=[finish.GroupPlan(presentation="collection", items=[finish.ArrangementRef(type="arrangement", arrangement_id=arrangement["arrangement_id"])])],
    )
    blocks, _ = finish.resolve_items(plan.groups[0].items, grounded, [payload], store)
    block = blocks[0]
    assert block.type == "arrangement"
    assert block.resource_id == arrangement["resource_id"]
    assert isinstance(block.progressions, list)


def test_resolve_body_rejects_research_resources_from_unapproved_hosts():
    """Only the reviewed research hosts, over https and without a fragment, reach the browser."""

    store = CanonicalStore()
    payload = {
        "research": {
            "state": "ok",
            "records": [
                {"entity_type": "song", "identifier": "evil", "title": "Evil", "url": "https://evil.example/x", "source": "dead.net"},
                {"entity_type": "song", "identifier": "insecure", "title": "Insecure", "url": "http://www.dead.net/song/sugaree", "source": "dead.net"},
                {"entity_type": "song", "identifier": "fragment", "title": "Fragment", "url": "https://www.dead.net/song/sugaree#frag", "source": "dead.net"},
                {"entity_type": "song", "identifier": "sugaree", "title": "Sugaree | Dead.net", "url": "https://www.dead.net/song/sugaree", "source": "dead.net"},
                {"entity_type": "song", "identifier": "essay", "title": "Jerry Garcia Instrument History", "url": "https://deadessays.blogspot.com/2019/08/jerry-garcia-instrument-history-guest.html", "source": "editorial"},
                {"entity_type": "song", "identifier": "trail", "title": "How Grateful Dead Songs Changed Live", "url": "https://deadheadhigh.com/guides/how-grateful-dead-songs-changed-live", "source": "editorial"},
            ],
        }
    }
    grounded = finish.grounded_context([payload])
    plan = finish.FinishPlan(
        chat_answer="x", title="t", lead=None,
        groups=[
            finish.GroupPlan(
                presentation="collection",
                items=[
                    finish.ResourceListRef(
                        type="resource_list",
                        resource_ids=[
                            "research:dead.net:evil",
                            "research:dead.net:insecure",
                            "research:dead.net:fragment",
                            "research:dead.net:sugaree",
                            "research:editorial:essay",
                            "research:editorial:trail",
                        ],
                    )
                ],
            )
        ],
    )
    blocks, sources = finish.resolve_items(plan.groups[0].items, grounded, [payload], store)
    block = blocks[0]
    assert block.type == "resource_list"
    # The unapproved host, the http URL, and the fragmented URL are all dropped.
    assert [item.resource_id for item in block.items] == [
        "research:dead.net:sugaree",
        "research:editorial:essay",
        "research:editorial:trail",
    ]
    assert all("evil.example" not in item.url for item in block.items)
    assert all(item.url.startswith("https://") and "#" not in item.url for item in block.items)
    # The reviewed lore hosts are accepted alongside dead.net.
    assert {item.url.split("/")[2] for item in block.items} == {
        "www.dead.net",
        "deadessays.blogspot.com",
        "deadheadhigh.com",
    }
    assert {source.source_id for source in sources} == {f"resource:{item.resource_id}" for item in block.items}


def test_resolve_body_resolves_performer_and_equipment_lists_for_a_show():
    store = CanonicalStore()
    payload = store.show_context(store.resolve_show("1972-08-27"))
    grounded = finish.grounded_context([payload])
    plan = finish.FinishPlan(
        chat_answer="x", title="t", lead=None,
        groups=[finish.GroupPlan(presentation="collection", items=[finish.EquipmentListRef(type="equipment_list", show_id="gd-1972-08-27")])],
    )
    blocks, sources = finish.resolve_items(plan.groups[0].items, grounded, [payload], store)
    (equipment,) = blocks
    assert [block.type for block in blocks] == ["equipment_list"]
    assert equipment.items and all(item.source_url.startswith("https://") for item in equipment.items)
    assert all(item.claim_type in {"show", "date_range"} for item in equipment.items)
    assert {item.source_id for item in equipment.items} <= {source.source_id for source in sources}


def _store_with_selection_evidence() -> CanonicalStore:
    """The reviewed selection rows the PostgreSQL runtime serves, read from their source file."""

    from pathlib import Path

    document = json.loads(
        (Path(__file__).parents[1] / "data" / "editorial" / "selection-evidence-review.json").read_text(encoding="utf-8")
    )
    entries = [
        {**entry, "review_packet": {"source_constraints": document["source_constraints"]}}
        for entry in document["entries"]
    ]

    class StoreWithSelectionEvidence(CanonicalStore):
        def selection_signal_rows(self):
            return entries

    return StoreWithSelectionEvidence()


def test_resolve_body_resolves_arrangement_search_and_show_selection_from_payloads():
    from deadbot.tools import build_tools

    plain_store = CanonicalStore()
    arrangement_payload = json.loads(
        next(tool for tool in build_tools(plain_store) if tool.name == "find_arrangements").invoke({"key_signature": "B"})
    )
    assert arrangement_payload["arrangements"], "expected a documented arrangement in B for this test"

    # get_show_selections reads selection signals, which the CSV store does not
    # serve; a reference to a selection it did not return must be dropped.
    empty_selection_payload = json.loads(
        next(tool for tool in build_tools(plain_store) if tool.name == "get_show_selections").invoke({})
    )
    assert empty_selection_payload["show_selections"] == []
    dropped, _ = finish.resolve_items(
        [finish.ShowSelectionRef(type="show_selection", selection_id="critic-show-selection-1")],
        finish.grounded_context([empty_selection_payload]),
        [empty_selection_payload],
        plain_store,
    )
    assert dropped == []

    # With the reviewed selection rows present, the same reference resolves.
    store = _store_with_selection_evidence()
    selection_payload = json.loads(
        next(tool for tool in build_tools(store) if tool.name == "get_show_selections").invoke({})
    )
    selection_id = selection_payload["show_selections"][0]["selection_id"]
    payloads = [arrangement_payload, selection_payload]
    grounded = finish.grounded_context(payloads)
    items = [
        finish.ArrangementSearchRef(type="arrangement_search", key_signature="B", title="Documented in B"),
        finish.ShowSelectionRef(type="show_selection", selection_id=selection_id),
    ]
    blocks, sources = finish.resolve_items(items, grounded, payloads, store)
    search, selection = blocks
    assert [block.type for block in blocks] == ["arrangement_search", "show_selection"]
    assert search.title == "Documented in B"
    assert search.key_signature == "B"
    assert search.items and all(item.key_signature == "B" and item.url for item in search.items)
    assert selection.source_id == f"selection:{selection_id}"
    assert selection.items and all(item.show_id and item.show_date and item.venue_name for item in selection.items)
    assert f"selection:{selection_id}" in {source.source_id for source in sources}


def test_finish_plan_accepts_semantic_units():
    plan = finish.FinishPlan.model_validate(
        {
            "chat_answer": "Five shows.",
            "title": "Branford with the Dead",
            "groups": [
                {
                    "presentation": "collection",
                    "items": [
                        {"type": "editorial", "presentation": "narrative", "paragraphs": ["Across the appearances he grew more integrated."]},
                        {"type": "show_unit", "show_id": "gd-1990-03-29", "emphasis": "primary", "note": "The debut.", "highlighted_performance_ids": ["p1"]},
                        {"type": "show_unit", "show_id": "gd-1990-12-31", "supporting_sources": [{"url": "https://example.org/x", "note": "A quote."}]},
                        {
                            "type": "performance_unit",
                            "performance_id": "p1",
                            "follow_ups": [{"label": "Another like this", "question": "Another like this?"}],
                        },
                        {"type": "era_unit", "title": "1973–74: spacious", "span": "1973–74", "representative_performance_ids": ["p2", "p3"]},
                    ],
                }
            ],
        }
    )
    assert [item.type for item in plan.groups[0].items] == ["editorial", "show_unit", "show_unit", "performance_unit", "era_unit"]
    assert plan.groups[0].items[1].emphasis == "primary"
    assert plan.groups[0].items[2].supporting_sources[0].url == "https://example.org/x"


def test_resolve_groups_preserves_order_criteria_and_truncates_judgments():
    store = CanonicalStore()
    payloads = _veneta_payloads(store)
    plan = finish.FinishPlan(
        chat_answer="x",
        title="Veneta",
        groups=[
            finish.GroupPlan(
                title="Two readings",
                lead="Judged on the same terms.",
                presentation="comparison",
                criteria=["Pace", "Jam"],
                items=[
                    finish.ShowUnitRef(type="show_unit", show_id="gd-1972-08-27", emphasis="primary", judgments=["Relaxed", "Long", "Extra"]),
                    finish.SongOverviewRef(type="song_overview", song_id="song-sugaree", judgments=["Steady"]),
                ],
            )
        ],
    )
    blocks, groups, _ = finish.resolve_groups(plan, finish.grounded_context(payloads), payloads, store)
    assert [block.type for block in blocks] == ["show_unit", "song_overview"]
    assert groups[0].presentation == "comparison" and groups[0].criteria == ["Pace", "Jam"]
    assert blocks[0].emphasis == "primary" and blocks[0].judgments == ["Relaxed", "Long"]
    assert blocks[1].emphasis == "supporting" and blocks[1].judgments == ["Steady"]


def test_finish_plan_rejects_an_unknown_role():
    from pydantic import ValidationError

    try:
        finish.ShowUnitRef.model_validate({"type": "show_unit", "show_id": "gd-1990-03-29", "role": "bold"})
    except ValidationError:
        pass
    else:
        raise AssertionError("roles are a closed vocabulary")


def test_a_plan_may_declare_an_album_unit():
    plan = finish.FinishPlan(
        chat_answer="Truckin' closes American Beauty.",
        title="American Beauty",
        groups=[
            finish.GroupPlan(
                presentation="collection",
                items=[{
                    "type": "album_unit",
                    "release_id": "release-american-beauty",
                    "visible_facets": ["listen", "tracklist"],
                    "highlighted_song_ids": ["song-truckin"],
                }],
            )
        ],
    )
    item = plan.groups[0].items[0]
    assert item.release_id == "release-american-beauty"
    assert item.visible_facets == ["listen", "tracklist"]


def test_an_ungrounded_release_id_is_dropped():
    items = [{"type": "album_unit", "release_id": "release-american-beauty"}]

    plan = finish.FinishPlan(
        chat_answer="x",
        title="x",
        groups=[finish.GroupPlan(presentation="collection", items=items)],
    )
    blocks, _ = finish.resolve_items(
        plan.groups[0].items, finish.GroundedContext(ids=frozenset(), urls=frozenset()), [], CanonicalStore()
    )
    assert blocks == []


def test_a_grounded_release_id_hydrates_into_an_album_unit():
    store = CanonicalStore()
    plan = finish.FinishPlan(
        chat_answer="x",
        title="x",
        groups=[
            finish.GroupPlan(
                presentation="collection",
                items=[{"type": "album_unit", "release_id": "release-american-beauty", "note": "The turn toward songs."}],
            )
        ],
    )
    grounded = finish.GroundedContext(ids=frozenset({"release-american-beauty"}), urls=frozenset())
    blocks, _ = finish.resolve_items(plan.groups[0].items, grounded, [], store)
    assert blocks[0].type == "album_unit"
    assert blocks[0].note == "The turn toward songs."
    assert blocks[0].tracks == [] and blocks[0].personnel == [] and blocks[0].listen == []


def test_album_unit_hydrates_only_the_facets_selected_by_the_composer():
    store = CanonicalStore()
    plan = finish.FinishPlan(
        chat_answer="x",
        title="x",
        groups=[
            finish.GroupPlan(
                presentation="collection",
                items=[{
                    "type": "album_unit",
                    "release_id": "release-american-beauty",
                    "visible_facets": ["listen", "tracklist"],
                    "highlighted_song_ids": ["song-truckin"],
                }],
            )
        ],
    )
    grounded = finish.GroundedContext(ids=frozenset({"release-american-beauty"}), urls=frozenset())
    blocks, _ = finish.resolve_items(plan.groups[0].items, grounded, [], store)
    block = blocks[0]
    assert block.tracks and block.listen
    assert block.personnel == [] and block.sources == []


def test_show_context_carries_per_performance_listening_paths():
    store = CanonicalStore()
    payload = store.show_context(store.resolve_show("1972-08-27"))
    with_listen = [performance for performance in payload["performances"] if "listen" in performance]
    assert with_listen, "the Veneta show has archive track links"
    assert all(performance["listen"]["archive_track_url"].startswith("https://archive.org/") for performance in with_listen)


def test_branford_debut_and_final_show_have_a_track_link_for_every_performance():
    store = CanonicalStore()
    for show_date in ("1990-03-29", "1994-12-16"):
        payload = store.show_context(store.resolve_show(show_date))
        assert len(payload["performances"]) == 17
        assert all(performance.get("listen", {}).get("archive_track_url") for performance in payload["performances"])


def test_franklins_tower_shortlist_hydrates_direct_song_links_from_archive_metadata():
    store = CanonicalStore()
    for show_date in ("1975-08-13", "1976-09-24", "1977-02-26", "1977-05-22", "1983-09-02"):
        payload = store.show_context(store.resolve_show(show_date))
        performance = next(item for item in payload["performances"] if item["song_id"] == "song-franklin-s-tower")
        assert performance.get("listen", {}).get("archive_track_url"), show_date


def test_performance_unit_offers_a_verified_youtube_video_alongside_audio():
    store = CanonicalStore()
    context = store.performance_context("gd-1990-03-29-eyes-of-the-world-2-1")
    assert context and context["listen"]["video_url"] == "https://www.youtube.com/watch?v=LEu6gCv8UPc"
    actions = composition._performance_listen_actions(context)
    assert any(action.provider == "youtube" and action.label == "Watch Eyes Of The World" for action in actions)


def test_resolve_body_hydrates_a_show_unit_from_the_composer_s_interpretation():
    store = CanonicalStore()
    show = store.resolve_show("1972-08-27")
    payload = store.show_context(show)
    grounded = finish.grounded_context([payload])
    highlighted = payload["performances"][3]["performance_id"]
    preferred = next(row["recording_id"] for row in store.filtered_rows("recordings", show_id=show["show_id"]) if row.get("source_url"))
    good_url = payload["resources"][0]["source_url"]
    plan = finish.FinishPlan(
        chat_answer="x", title="t", lead=None,
        groups=[
            finish.GroupPlan(
                presentation="collection",
                items=[
                    finish.ShowUnitRef(
                        type="show_unit",
                        show_id="gd-1972-08-27",
                        emphasis="primary",
                        note="The Sunshine Daydream show.",
                        visible_facets=["guests", "listen", "setlist", "sources"],
                        setlist_disclosure="expanded",
                        highlighted_performance_ids=[highlighted, "gd-1977-05-08-not-this-show"],
                        preferred_recording_id=preferred,
                        supporting_sources=[
                            finish.SupportingSource(url=good_url, note="A firsthand account."),
                            finish.SupportingSource(url="https://example.com/not-returned"),
                        ],
                        follow_ups=[finish.FollowUpTopic(label="Veneta lore", question="Why is Veneta so loved?")],
                    )
                ],
            )
        ],
    )
    blocks, sources = finish.resolve_items(plan.groups[0].items, grounded, [payload], store)
    unit = blocks[0]
    assert unit.type == "show_unit"
    # Identity is hydrated, not retyped by the model.
    assert unit.show_date == "1972-08-27"
    assert unit.venue_name == "Old Renaissance Faire Grounds"
    assert unit.location == "Veneta, OR"
    assert unit.emphasis == "primary" and unit.note == "The Sunshine Daydream show."
    assert unit.follow_ups == [experience.FollowUpTopic(label="Veneta lore", question="Why is Veneta so loved?")]
    # The setlist marks the composer's highlight and only performances of this show.
    songs = [song for section in unit.sets for song in section.songs]
    assert [song.performance_id for song in songs if song.highlighted] == [highlighted]
    assert any(song.listen_url for song in songs)
    # The preferred recording leads the listening actions; the release is offered too.
    assert unit.listen[0].label.startswith("Listen to the show")
    assert unit.listen[0].url == next(row["source_url"] for row in store.filtered_rows("recordings", show_id=show["show_id"]) if row["recording_id"] == preferred)
    assert any(action.is_official for action in unit.listen)
    assert not any("all recordings" in action.label.casefold() for action in unit.listen)
    # Only the grounded source survives, named from the payload that returned it.
    assert [source.url for source in unit.sources] == [good_url]
    assert unit.sources[0].label == payload["resources"][0]["title"]
    assert unit.sources[0].note == "A firsthand account."
    assert {source.source_id for source in sources} >= {f"recording:{preferred}", f"url:{good_url}"}


def test_show_unit_only_hydrates_the_facets_the_composer_selected():
    store = CanonicalStore()
    payload = store.show_context(store.resolve_show("1972-08-27"))
    plan = finish.FinishPlan(
        chat_answer="x",
        title="Veneta",
        groups=[
            finish.GroupPlan(
                presentation="collection",
                items=[
                    finish.ShowUnitRef(
                        type="show_unit",
                        show_id="gd-1972-08-27",
                        visible_facets=["setlist"],
                        setlist_disclosure="collapsed",
                    )
                ],
            )
        ],
    )
    blocks, _ = finish.resolve_items(plan.groups[0].items, finish.grounded_context([payload]), [payload], store)
    unit = blocks[0]
    assert unit.type == "show_unit"
    assert unit.visible_facets == ["setlist"] and unit.setlist_disclosure == "collapsed"
    assert unit.sets and not unit.guests and not unit.listen and not unit.sources


def test_show_unit_with_no_selected_facets_stays_compact():
    store = CanonicalStore()
    payload = store.show_context(store.resolve_show("1972-08-27"))
    plan = finish.FinishPlan(
        chat_answer="x",
        title="Veneta",
        groups=[finish.GroupPlan(presentation="collection", items=[finish.ShowUnitRef(type="show_unit", show_id="gd-1972-08-27")])],
    )
    blocks, sources = finish.resolve_items(
        plan.groups[0].items, finish.grounded_context([payload]), [payload], store
    )
    unit = blocks[0]
    assert unit.visible_facets == []
    assert not unit.sets and not unit.guests and not unit.listen and not unit.sources
    assert sources == []


def test_resolve_body_hydrates_a_performance_unit_with_set_context_and_play_action():
    store = CanonicalStore()
    show_payload = store.show_context(store.resolve_show("1972-08-27"))
    performance_id = show_payload["performances"][2]["performance_id"]
    context = store.performance_context(performance_id)
    assert context["listen"]["archive_track_url"]
    grounded = finish.grounded_context([show_payload])
    plan = finish.FinishPlan(
        chat_answer="x", title="t", lead=None,
        groups=[
            finish.GroupPlan(
                presentation="collection",
                items=[finish.PerformanceUnitRef(type="performance_unit", performance_id=performance_id, note="A relaxed version.")],
            )
        ],
    )
    blocks, _ = finish.resolve_items(plan.groups[0].items, grounded, [show_payload], store)
    unit = blocks[0]
    assert unit.type == "performance_unit"
    assert unit.song_title and unit.show_date == "1972-08-27" and unit.venue_name == "Old Renaissance Faire Grounds"
    assert unit.previous and unit.next, "a mid-set rendition has neighbours on both sides"
    assert unit.listen[0].label == f"Listen to {unit.song_title}"
    assert unit.listen[0].url == context["listen"]["archive_track_url"]
    assert any(action.label == "Hear the full show" for action in unit.listen)
    assert not any("all recordings" in action.label.casefold() for action in unit.listen)


def test_follow_up_contract_reserves_ask_for_exploration():
    description = finish.ShowUnitRef.model_fields["follow_ups"].description or ""
    assert "listening links already cover hearing it" in description
    assert "explanation, comparison, history, lore or evidence" in description


def test_show_unit_follow_ups_carry_label_and_question_and_drop_a_blank_label():
    store = CanonicalStore()
    payload = store.show_context(store.resolve_show("1972-08-27"))
    grounded = finish.grounded_context([payload])
    plan = finish.FinishPlan(
        chat_answer="x", title="t", lead=None,
        groups=[
            finish.GroupPlan(
                presentation="collection",
                items=[
                    finish.ShowUnitRef(
                        type="show_unit",
                        show_id="gd-1972-08-27",
                        follow_ups=[
                            finish.FollowUpTopic(label="Veneta lore", question="Why is Veneta so loved?"),
                            finish.FollowUpTopic(label="Sunshine Daydream", question="What is the Sunshine Daydream film?"),
                            finish.FollowUpTopic(label="   ", question="Dropped for its blank label"),
                        ],
                    )
                ],
            )
        ],
    )
    blocks, _ = finish.resolve_items(plan.groups[0].items, grounded, [payload], store)
    unit = blocks[0]
    assert [(topic.label, topic.question) for topic in unit.follow_ups] == [
        ("Veneta lore", "Why is Veneta so loved?"),
        ("Sunshine Daydream", "What is the Sunshine Daydream film?"),
    ]


def test_resolve_body_hydrates_an_era_unit_from_representative_performances():
    store = CanonicalStore()
    song = store.resolve_song("Sugaree")
    payload = store.song_context(song)
    grounded = finish.grounded_context([payload])
    with_listen = [performance for performance in payload["performances"] if "listen" in performance][:2]
    plan = finish.FinishPlan(
        chat_answer="x", title="t", lead=None,
        groups=[
            finish.GroupPlan(
                presentation="collection",
                items=[
                    finish.EraUnitRef(
                        type="era_unit",
                        title="Early Sugarees",
                        span="1971–72",
                        note="Loose and bluesy.",
                        representative_performance_ids=[*(performance["performance_id"] for performance in with_listen), "not-retrieved"],
                    ),
                    finish.EraUnitRef(type="era_unit", title="Nothing grounded", representative_performance_ids=["not-retrieved"]),
                ],
            )
        ],
    )
    blocks, _ = finish.resolve_items(plan.groups[0].items, grounded, [payload], store)
    assert [block.type for block in blocks] == ["era_unit"]
    era = blocks[0]
    assert era.title == "Early Sugarees" and era.span == "1971–72"
    assert [item.performance_id for item in era.performances] == [performance["performance_id"] for performance in with_listen]
    assert all(item.listen and item.listen.label == "Listen to Sugaree" for item in era.performances)
    assert all(item.show_date and item.show_label for item in era.performances)


def test_server_built_items_carry_no_generated_follow_ups():
    """Only the composer writes follow-ups; server projections never invent one."""

    for model in (
        experience.SetlistSong,
        experience.PerformerItem,
        experience.GuestAppearanceItem,
        experience.EquipmentItem,
        experience.PerformanceListItem,
        experience.ComparisonStripItem,
        experience.PerformanceSpineNeighbor,
        experience.ShowSelectionItem,
        experience.ArrangementSearchItem,
        experience.EraPerformanceItem,
        experience.CreditItem,
    ):
        assert "follow_ups" not in model.model_fields, model.__name__
    # The composer's own follow-ups survive on units and editorial items.
    for model in (experience.ShowUnitBlock, experience.PerformanceUnitBlock, experience.EraUnitBlock, experience.EditorialItem):
        assert "follow_ups" in model.model_fields, model.__name__


def finish_call(plan: dict):
    return AIMessage(content="", tool_calls=[{"name": finish.FINISH_TOOL_NAME, "args": plan, "id": "finish-1", "type": "tool_call"}])


def delivered():
    return ToolMessage(content="Response delivered to the visitor.", tool_call_id="finish-1", name=finish.FINISH_TOOL_NAME)


def test_build_experience_response_uses_the_finish_plan():
    store = CanonicalStore()
    show = store.resolve_show("1972-08-27")
    payload = store.show_context(show)
    good_url = next(url for url in sorted(finish.grounded_context([payload]).urls) if "archive.org" in url or "relisten.net" in url)
    plan = {
        "chat_answer": f"They opened with [Promised Land]({good_url}).",
        "title": "Veneta, 1972",
        "lead": "The Sunshine Daydream show.",
        "groups": [{"presentation": "collection", "items": [{"type": "show_unit", "show_id": "gd-1972-08-27", "visible_facets": ["setlist"]}]}],
    }
    messages = [
        HumanMessage(content="What opened Veneta?"),
        AIMessage(content="", tool_calls=[{"name": "get_show", "args": {"show_id_or_date": "1972-08-27"}, "id": "call-1", "type": "tool_call"}]),
        tool_message(payload),
        finish_call(plan),
        delivered(),
    ]
    response = finish.build_experience_response("What opened Veneta?", "web-1", messages, store)
    assert response.title == "Veneta, 1972"
    assert response.answer == f"They opened with [Promised Land]({good_url})."
    assert response.body_lead == "The Sunshine Daydream show."
    assert response.mode == "answer"
    assert [block.type for block in response.blocks] == ["show_unit"]
    assert response.groups[0].presentation == "collection" and response.groups[0].block_indexes == [0]
    assert response.conversation[-1].role == "assistant" and response.conversation[-1].text == response.answer
    assert response.conversation[0].text == "What opened Veneta?"


def test_build_experience_response_falls_back_when_no_plan_was_delivered(caplog):
    store = CanonicalStore()
    messages = [HumanMessage(content="Hi"), AIMessage(content="I could not find that show.")]
    with caplog.at_level("WARNING"):
        response = finish.build_experience_response("Hi", "web-1", messages, store)
    assert response.answer == "I could not find that show."
    assert response.mode == "gap"
    assert response.blocks[0].type == "gap_state"
    assert "finish_response" in caplog.text


def test_build_experience_response_only_uses_the_latest_turn():
    store = CanonicalStore()
    show = store.resolve_show("1972-08-27")
    earlier_plan = {
        "chat_answer": "Earlier.",
        "title": "Earlier",
        "lead": None,
        "groups": [{"presentation": "collection", "items": [{"type": "show_unit", "show_id": "gd-1972-08-27", "visible_facets": ["setlist"]}]}],
    }
    later_plan = {"chat_answer": "Later.", "title": "Later", "lead": None, "groups": []}
    messages = [
        HumanMessage(content="First"), tool_message(store.show_context(show)), finish_call(earlier_plan), delivered(),
        HumanMessage(content="Second"), finish_call(later_plan), delivered(),
    ]
    response = finish.build_experience_response("Second", "web-1", messages, store)
    assert response.title == "Later" and response.blocks == []
    assert [turn.text for turn in response.conversation] == ["First", "Earlier.", "Second", "Later."]


def test_build_experience_response_shows_one_assistant_turn_when_a_finish_call_is_retried():
    """A rejected finish call plus its retry is still one answer to the visitor."""

    store = CanonicalStore()
    partial_plan = {"chat_answer": "A first draft answer.", "lead": None, "groups": []}
    retry_plan = {"chat_answer": "The corrected answer.", "title": "Corrected", "lead": None, "groups": []}
    messages = [
        HumanMessage(content="Hi"),
        AIMessage(content="", tool_calls=[{"name": finish.FINISH_TOOL_NAME, "args": partial_plan, "id": "finish-0", "type": "tool_call"}]),
        ToolMessage(content="Error: title is required", tool_call_id="finish-0", name=finish.FINISH_TOOL_NAME, status="error"),
        finish_call(retry_plan),
        delivered(),
    ]
    response = finish.build_experience_response("Hi", "web-1", messages, store)
    assert response.title == "Corrected"
    assert [(turn.role, turn.text) for turn in response.conversation] == [
        ("user", "Hi"),
        ("assistant", "The corrected answer."),
    ]


def test_build_experience_response_substitutes_a_placeholder_for_a_blank_chat_answer(caplog):
    store = CanonicalStore()
    plan = {"chat_answer": "   ", "title": "t", "lead": None, "groups": []}
    messages = [HumanMessage(content="Hi"), finish_call(plan), delivered()]
    with caplog.at_level("WARNING"):
        response = finish.build_experience_response("Hi", "web-1", messages, store)
    assert response.answer == "Deadbot could not write a chat answer for this response."
    assert response.conversation[-1].text == response.answer
    assert "blank chat_answer" in caplog.text


def test_build_experience_response_substitutes_the_lead_for_a_blank_chat_answer():
    store = CanonicalStore()
    plan = {"chat_answer": "   ", "title": "t", "lead": "A short lead.", "groups": []}
    messages = [HumanMessage(content="Hi"), finish_call(plan), delivered()]
    response = finish.build_experience_response("Hi", "web-1", messages, store)
    assert response.answer == "A short lead."


def test_album_unit_hydrates_from_the_release_payload():
    store = CanonicalStore()
    payload = store.album_context(store.resolve_release("release-american-beauty"))
    block, sources = composition._album_unit(payload, store, note="The record that made them a band people bought.")

    assert block.type == "album_unit"
    assert block.title == "American Beauty"
    assert block.release_type == "studio"
    assert [track.track_number for track in block.tracks] == sorted(t.track_number for t in block.tracks)


def test_album_unit_keeps_the_record_title_beside_a_model_headline():
    store = CanonicalStore()
    payload = store.album_context(store.resolve_release("release-american-beauty"))
    block, _ = composition._album_unit(payload, store, title="Hear the source and trace the afterlife")

    assert block.title == "Hear the source and trace the afterlife"
    assert block.release_title == "American Beauty"


def test_album_unit_keeps_only_highlights_that_are_on_the_record():
    store = CanonicalStore()
    payload = store.album_context(store.resolve_release("release-american-beauty"))
    block, _ = composition._album_unit(payload, store, highlighted_song_ids=["song-truckin", "song-dark-star"])

    highlighted = {track.song_id for track in block.tracks if track.highlighted}
    assert highlighted == {"song-truckin"}


def test_album_unit_offers_the_record_as_a_listening_action():
    store = CanonicalStore()
    payload = store.album_context(store.resolve_release("release-american-beauty"))
    block, _ = composition._album_unit(payload, store)
    assert all(action.is_official for action in block.listen)
    assert block.listen[0].label == "Listen to American Beauty"


def test_song_overview_shows_the_records_that_held_the_song():
    store = CanonicalStore()
    context = store.song_context(store.resolve_song("Truckin'"))
    block = composition._song_overview(context, store, visible_facets=["albums"])
    assert any(album.release_type == "studio" for album in block.albums)


def test_song_overview_keeps_a_late_studio_album_ahead_of_the_truncation():
    """"Where I Come From" (2009-06-02) is the studio album carrying "Let It
    Grow", but six live releases dated earlier sort ahead of it in
    song_releases' earliest-first order. _song_overview truncates to 6
    albums; without prioritizing studio releases, "Where I Come From" falls
    off the list entirely."""

    store = CanonicalStore()
    context = store.song_context(store.resolve_song("Let It Grow"))
    block = composition._song_overview(context, store, visible_facets=["albums"])
    assert any(album.title == "Where I Come From" for album in block.albums)


def test_show_unit_hydrates_lineup_and_recordings_only_when_selected():
    store = CanonicalStore()
    payload = store.show_context(store.resolve_show("1972-08-27"))
    grounded = finish.grounded_context([payload])
    full = finish.ShowUnitRef(type="show_unit", show_id="gd-1972-08-27", visible_facets=["lineup", "recordings"])
    bare = finish.ShowUnitRef(type="show_unit", show_id="gd-1972-08-27", visible_facets=["setlist"])
    blocks, sources = finish.resolve_items([full, bare], grounded, [payload], store)
    assert blocks[0].lineup and all(item.role in {"performer", "guest"} for item in blocks[0].lineup)
    assert blocks[0].recordings and all(item.url.startswith("http") for item in blocks[0].recordings)
    assert any(source.url and "archive.org" in source.url for source in sources)
    assert blocks[1].lineup == [] and blocks[1].recordings == [] and blocks[1].sets


def test_song_overview_hydrates_history_and_omits_unselected_facets():
    store = CanonicalStore()
    payloads = _veneta_payloads(store)
    grounded = finish.grounded_context(payloads)
    ref = finish.SongOverviewRef(type="song_overview", song_id="song-sugaree", visible_facets=["history"])
    blocks, _ = finish.resolve_items([ref], grounded, payloads, store)
    song = blocks[0]
    assert song.visible_facets == ["history"]
    assert song.history is not None
    assert song.history.first.show_date <= song.history.last.show_date
    assert song.history.known_count == song.known_performance_count
    assert len({item.year for item in song.history.by_year}) == len(song.history.by_year)
    assert song.credits == [] and song.albums == [] and song.representative_performances == []


def test_performance_unit_still_carries_set_neighbors():
    store = CanonicalStore()
    payloads = _veneta_payloads(store)
    grounded = finish.grounded_context(payloads)
    performance_id = next(p["performance_id"] for p in payloads[0]["performances"] if p.get("performance_id"))
    blocks, _ = finish.resolve_items([finish.PerformanceUnitRef(type="performance_unit", performance_id=performance_id)], grounded, payloads, store)
    unit = blocks[0]
    assert unit.type == "performance_unit"
    assert unit.previous is not None or unit.next is not None
