import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _load(name: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / f"{name}.py")
    loaded = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(loaded)
    return loaded


module = _load("normalize_musicbrainz_studio_releases")
live = _load("normalize_musicbrainz_live_releases")

# Notes copied from real rows of data/canonical/official_releases.csv, one of
# each kind the two normalizers have to tell apart.
STUDIO_NOTES = (
    "MusicBrainz release feb9cb7f-cf75-4bcc-a0bd-29ccadac931f; "
    "release group 474a9145-4c41-41b6-86b9-7dc060b20227; studio release-group pass; "
    "0/12 tracks resolved to a canonical song."
)
LIVE_NOTES = (
    "MusicBrainz release 6ecd7bfc-ea33-4edd-8a9b-629487f6949e; "
    "release group 4fbae9ee-09d7-4135-9d85-284cadcc3019; "
    "show resolution: single date 1970-03-01 from 1/30 track-level dates."
)
CURATED_NOTES = "Official Spotify release containing one intro and the 20 canonical performances."

ROWS = [
    {"release_id": "release-17-pine-avenue", "notes": STUDIO_NOTES},
    {"release_id": "release-30-days-of-dead-1970-03-01", "notes": LIVE_NOTES},
    {"release_id": "release-veneta-or-1972-08-27-complete-sunshine-daydream-concert", "notes": CURATED_NOTES},
]


def _kept(pass_module) -> set[str]:
    """The release_ids a rerun of this pass leaves alone.

    Both normalizers rebuild their own rows and keep everything else, so this
    mirrors the `kept_releases` filter in each script's main().  Track rows
    follow their release in both scripts (they are filtered by release_id
    membership), so a release kept here keeps its tracks.
    """

    return {row["release_id"] for row in ROWS if not pass_module.owns_row(row)}

SONGS = {
    "sugaree": "song-sugaree",
    "truckin": "song-truckin",
    "china cat sunflower": "song-china-cat-sunflower",
}


def test_an_exact_title_resolves_to_its_song():
    assert module.resolve_song_id("Sugaree", SONGS) == "song-sugaree"


def test_punctuation_and_case_do_not_block_a_match():
    assert module.resolve_song_id("Truckin'", SONGS) == "song-truckin"
    assert module.resolve_song_id("CHINA CAT SUNFLOWER", SONGS) == "song-china-cat-sunflower"


def test_an_unresolved_title_is_held_rather_than_guessed():
    assert module.resolve_song_id("Untitled Studio Jam", SONGS) is None


def test_release_ids_are_stable_kebab_case():
    assert module.release_id_for("American Beauty") == "release-american-beauty"
    assert module.release_id_for("Ace") == "release-ace"


def test_only_a_performing_credit_naming_an_instrument_becomes_a_row():
    """`instrument` is part of the primary key, so it can never be improvised.

    MusicBrainz hangs attributes on non-performing relations too -- `producer`
    carries `executive`, `additional`, `assistant` -- and reading those as
    instruments would file "Bob Weir, producer, executive" in the column that
    says what he played.  Everything that is not a performing credit with a
    named instrument is held, and an unknown person is never invented.
    """

    people = {"jerry garcia": "person-jerry-garcia", "bob weir": "person-bob-weir"}
    release = {
        "id": "release-mbid",
        "artist_relations": [
            {"type": "instrument", "artist_name": "Jerry Garcia", "attributes": ["guitar"]},
            {"type": "producer", "artist_name": "Bob Weir", "attributes": ["executive"]},
            {"type": "engineer", "artist_name": "Bob Weir", "attributes": []},
            {"type": "instrument", "artist_name": "Betty Cantor-Jackson", "attributes": ["tambourine"]},
        ],
        "media": [
            {
                "tracks": [
                    {
                        "recording": {
                            "id": "rec-1",
                            "artist_relations": [
                                {"type": "vocal", "artist_name": "Jerry Garcia", "attributes": ["lead vocals"]},
                                # The same person and instrument again: one row, not a key clash.
                                {"type": "instrument", "artist_name": "Jerry Garcia", "attributes": ["guitar"]},
                            ],
                        }
                    }
                ]
            }
        ],
    }

    rows, held = module.resolve_personnel("release-test", release, people)

    assert [(row["person_id"], row["role"], row["instrument"]) for row in rows] == [
        ("person-jerry-garcia", "performer", "guitar"),
        ("person-jerry-garcia", "performer", "lead vocals"),
    ]
    assert all(row["instrument"] for row in rows)
    assert "on 2 credits" in rows[0]["notes"]

    reasons = {(record["name"], record["reason"]) for record in held}
    assert reasons == {
        ("Bob Weir", "no_instrument"),
        ("Betty Cantor-Jackson", "person_not_in_people_csv"),
    }


def test_each_pass_replaces_only_its_own_rows():
    """Neither pass may delete the other's rows, in either running order.

    Regression test for the live pass claiming every studio row: its filter used
    to keep only rows whose notes lacked "MusicBrainz release ", which every
    studio row's notes begins with, so a live run after a studio run deleted all
    49 studio releases and their track rows.  Ownership needs the narrow marker.
    """

    studio, live_row, curated = (row["release_id"] for row in ROWS)

    # The studio pass rebuilds the studio row and leaves the other two alone.
    assert _kept(module) == {live_row, curated}
    # The live pass rebuilds the live row and leaves the other two alone.
    assert _kept(live) == {studio, curated}

    # No row is owned by both passes, whichever runs second.
    assert not [row for row in ROWS if module.owns_row(row) and live.owns_row(row)]
    # And the MBID marker alone is not ownership: it is on both managed rows.
    assert all(live.MANAGED_MARKER in row["notes"] for row in ROWS[:2])


def test_a_previously_assigned_release_id_is_reused_rather_than_renumbered():
    """The same MBID keeps its id across runs, from either the release or group.

    Ids are public: renumbering one silently repoints anything that referenced
    it.  `release-american-beauty-2009` is deliberately not what
    `release_id_for("American Beauty")` would produce, so a reuse failure shows
    up as the derived id rather than passing by luck.
    """

    existing = [
        {
            "release_id": "release-american-beauty-2009",
            "notes": (
                "MusicBrainz release aaaaaaaa-1111-2222-3333-444444444444; "
                "release group bbbbbbbb-1111-2222-3333-444444444444; studio release-group pass."
            ),
        },
        {"release_id": "release-a-live-record", "notes": LIVE_NOTES},
    ]
    id_by_mbid = module.previous_studio_ids(existing)
    assert id_by_mbid["aaaaaaaa-1111-2222-3333-444444444444"] == "release-american-beauty-2009"
    # The live row's MBIDs are not this pass's to reuse.
    assert "6ecd7bfc-ea33-4edd-8a9b-629487f6949e" not in id_by_mbid

    by_release_mbid = {
        "release_group_id": "bbbbbbbb-1111-2222-3333-444444444444",
        "release_group_title": "American Beauty",
        "release_mbid": "aaaaaaaa-1111-2222-3333-444444444444",
        "artist_name": "Grateful Dead",
        "first_release_date": "1970-11-01",
    }
    assigned = module.assign_release_ids([by_release_mbid], set(), dict(id_by_mbid))
    assert assigned["bbbbbbbb-1111-2222-3333-444444444444"] == "release-american-beauty-2009"

    # A re-issued album whose chosen edition changed still keeps its id, because
    # the release-group MBID is recorded too.
    new_edition = {**by_release_mbid, "release_mbid": "cccccccc-1111-2222-3333-444444444444"}
    assigned = module.assign_release_ids([new_edition], set(), dict(id_by_mbid))
    assert assigned["bbbbbbbb-1111-2222-3333-444444444444"] == "release-american-beauty-2009"

    # A genuinely new group gets a fresh derived id.
    fresh = {
        "release_group_id": "dddddddd-1111-2222-3333-444444444444",
        "release_group_title": "Wake of the Flood",
        "release_mbid": "eeeeeeee-1111-2222-3333-444444444444",
        "artist_name": "Grateful Dead",
        "first_release_date": "1973-10-15",
    }
    assigned = module.assign_release_ids([fresh], set(), dict(id_by_mbid))
    assert assigned["dddddddd-1111-2222-3333-444444444444"] == "release-wake-of-the-flood"
