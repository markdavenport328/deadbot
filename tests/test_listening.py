import json

from langchain_core.messages import AIMessageChunk

from deadbot import composition, finish, listening
from deadbot.data import CanonicalStore
from deadbot.plan_stream import PlanStreamer
from deadbot.sqlite_store import SqliteCanonicalStore

CORNELL = "gd-1977-05-08"
CORNELL_TAPE = "gd1977-05-08.148737.SBD.Betty.Anon.Noel.t-flac2448"
CORNELL_SPOTIFY = "https://open.spotify.com/album/3T9UKU0jMIyrRD0PtKXqPJ"
TERRAPIN = "gd-1977-06-09-terrapin-station-2-10"


def _hero_plan(**hero):
    return finish.FinishPlan.model_validate(
        {
            "chat_answer": "Cornell earns it.",
            "title": "Cornell's case is coherence",
            "groups": [
                {
                    "presentation": "collection",
                    "items": [
                        {"type": "listening_hero", **hero},
                        {"type": "pull_quote", "text": "The case is that the [second set](https://example.com/x) never lets go."},
                    ],
                }
            ],
        }
    )


def test_listening_hero_hydrates_a_show_with_its_release_cover_and_the_queue_from_the_named_set():
    store = CanonicalStore()
    payload = store.show_context(store.resolve_show("1977-05-08"))
    grounded = finish.grounded_context([payload])
    assert CORNELL_SPOTIFY in grounded.urls
    plan = _hero_plan(
        show_id=CORNELL,
        line="Betty Board soundboard",
        play_label="Play the second set",
        start_set="set 2",
        link={"url": CORNELL_SPOTIFY, "label": "Official 2017 release on Spotify"},
    )
    blocks, _ = finish.resolve_items(plan.groups[0].items, grounded, [payload], store)
    hero, quote = blocks
    assert hero.type == "listening_hero"
    # Identity comes from the library: the venue and date name the show.
    assert hero.venue_name == "Barton Hall, Cornell University" and hero.location == "Ithaca, NY" and hero.show_date == "1977-05-08"
    # The show maps to the single-show release, not the box set that also holds it.
    assert hero.release_id == "release-cornell-1977-05-08"
    assert hero.image_url == "https://coverartarchive.org/release/3e4aecfb-bfcc-49fb-abf6-7afae378c3a0/front-500"
    assert hero.image_alt and "Cornell 5/8/77" in hero.image_alt and "May 8, 1977" in hero.image_alt
    # The queue is one tape in show order, starting where the model said.
    assert hero.recording_identifier == CORNELL_TAPE
    assert all(CORNELL_TAPE in track.audio_url for track in hero.queue)
    assert hero.queue[hero.start_index].title == "Scarlet Begonias" and hero.queue[hero.start_index].set_label == "Set 2"
    assert hero.queue[0].set_label == "Set 1"
    assert hero.play_label == "Play the second set" and hero.line == "Betty Board soundboard"
    assert hero.link and hero.link.url == CORNELL_SPOTIFY
    assert hero.play_url is None, "a playable queue plays in-page"
    # A pulled line keeps its words and loses link markup.
    assert quote.type == "pull_quote" and quote.text == "The case is that the second set never lets go."


def test_listening_hero_drops_an_ungrounded_link_and_an_ungrounded_show():
    store = CanonicalStore()
    payload = store.show_context(store.resolve_show("1977-05-08"))
    grounded = finish.grounded_context([payload])
    plan = _hero_plan(show_id=CORNELL, link={"url": "https://example.com/not-returned", "label": "Elsewhere"})
    blocks, _ = finish.resolve_items(plan.groups[0].items[:1], grounded, [payload], store)
    assert blocks[0].link is None
    plan = _hero_plan(show_id="gd-1972-08-27")
    blocks, _ = finish.resolve_items(plan.groups[0].items[:1], grounded, [payload], store)
    assert blocks == []


def test_listening_hero_for_a_record_shows_its_cover_and_plays_it_on_spotify():
    store = CanonicalStore()
    release = store.resolve_release("release-cornell-1977-05-08")
    payload = {"release": release}
    plan = _hero_plan(release_id="release-cornell-1977-05-08", play_label="Play the record")
    blocks, _ = finish.resolve_items(plan.groups[0].items[:1], finish.grounded_context([payload]), [payload], store)
    hero = blocks[0]
    assert hero.show_id is None and hero.release_title == "Cornell 5/8/77" and hero.release_date == "2017-05-05"
    assert hero.image_url and hero.image_url.startswith("https://coverartarchive.org/release/")
    assert hero.queue == [] and hero.play_url == CORNELL_SPOTIFY


def test_a_show_without_a_release_cover_falls_back_to_the_tape_image(built_sqlite, tmp_path):
    store = SqliteCanonicalStore(built_sqlite, response_cache_path=tmp_path / "cache.sqlite")
    tracks, tape = listening.playable_show_tracks("gd-1977-06-09", store)
    assert tape and tracks
    hero = listening.listening_hero(store, show_id="gd-1977-06-09", release_id=None)
    assert hero is not None and hero.venue_name == "Winterland"
    if not (hero.image_url or "").startswith("https://coverartarchive.org/"):
        assert hero.image_url == listening.archive_thumbnail(tape)
    # The SQLite store and the CSV store agree on the tape and its order.
    csv_tracks, csv_tape = listening.playable_show_tracks("gd-1977-06-09", CanonicalStore())
    assert csv_tape == tape and [track.audio_url for track in csv_tracks] == [track.audio_url for track in tracks]


def test_a_performance_with_an_archive_track_offers_its_tape_as_the_full_show_with_playable_tracks():
    store = CanonicalStore()
    context = store.performance_context(TERRAPIN)
    block = composition._performance_unit(context, store)
    track_action, show_action = block.listen[:2]
    assert track_action.label == "Listen to Terrapin Station"
    assert track_action.url.startswith("https://archive.org/download/gd1977-06-09.sbd.dauria.3372.shnf/")
    assert show_action.label == "Hear the full show"
    assert show_action.url == "https://archive.org/details/gd1977-06-09.sbd.dauria.3372.shnf"
    assert block.show_tracks and all("gd1977-06-09.sbd.dauria.3372.shnf" in track.audio_url for track in block.show_tracks)
    assert any(track.performance_id == TERRAPIN and track.audio_url == track_action.url for track in block.show_tracks)


def test_the_streamer_and_the_plan_accept_the_same_hero_and_pulled_line():
    store = CanonicalStore()
    payload = store.show_context(store.resolve_show("1977-05-08"))
    grounded = finish.grounded_context([payload])
    raw = {
        "chat_answer": "Cornell earns it.",
        "title": "Cornell",
        "groups": [
            {
                "presentation": "collection",
                "items": [
                    {"type": "listening_hero", "show_id": CORNELL, "play_label": "Play the second set", "start_set": "Set 2"},
                    {"type": "pull_quote", "text": "The second set never lets go."},
                ],
            }
        ],
    }
    plan = finish.FinishPlan.model_validate(raw)
    delivered, _, _ = finish.resolve_groups(plan, grounded, [payload], store)

    streamer = PlanStreamer(lambda items: finish.resolve_items(items, grounded, [payload], store)[0], grounded.urls)
    events = streamer.feed(
        AIMessageChunk(
            content="",
            tool_call_chunks=[{"name": finish.FINISH_TOOL_NAME, "args": json.dumps(raw), "id": "f1", "index": 0, "type": "tool_call_chunk"}],
        )
    )
    streamed = [event.payload["block"] for event in events if event.type == "block"]
    assert [block["type"] for block in streamed] == ["listening_hero", "pull_quote"]
    assert streamed == [block.model_dump(mode="json") for block in delivered]
