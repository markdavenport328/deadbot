"""Contract-version tests for `deadbot.experience` in isolation.

These import only `deadbot.experience`, not `deadbot.composition` or
`deadbot.finish`. Those two modules still reference names this task deletes
(`role`, `UnitRole`, etc.) and are fixed in Task 3; importing them here would
make these tests fail to collect for a reason unrelated to what they check.
"""

from deadbot import experience


def test_contract_version_two_uses_emphasis_and_server_set_mode():
    assert experience.ExperienceResponse.model_fields["schema_version"].default == "2"
    assert experience.ExperienceResponse.model_fields["mode"].default == "answer"
    assert "layout" not in experience.ExperienceResponse.model_fields
    for name in ("ShowUnitBlock", "PerformanceUnitBlock", "AlbumUnitBlock", "SongOverviewBlock"):
        fields = getattr(experience, name).model_fields
        assert fields["emphasis"].default == "supporting"
        assert "role" not in fields
        assert "judgments" in fields
    assert "role" not in experience.EraUnitBlock.model_fields
    assert "criteria" in experience.ExperienceGroup.model_fields
    for removed in ("ShowExplorerBlock", "ShowSetlistBlock", "RecordingListBlock", "PerformerListBlock",
                    "PerformanceListBlock", "PerformanceExtremesBlock", "PerformanceSpineBlock",
                    "ComparisonStripBlock", "LayoutSection", "UnitRole", "UnitOrganization"):
        assert not hasattr(experience, removed), removed


def test_show_unit_accepts_lineup_and_recordings_facets_and_song_overview_accepts_history():
    unit = experience.ShowUnitBlock(
        type="show_unit", show_id="gd-1972-08-27", show_date="1972-08-27",
        visible_facets=["lineup", "recordings"],
        lineup=[experience.PerformerItem(person_id="jerry", name="Jerry Garcia", role="performer", instruments=["guitar"])],
        recordings=[experience.RecordingItem(recording_id="r1", title="SBD", source_type="soundboard", url="https://archive.org/details/x", source_id="recording:r1")],
    )
    assert unit.emphasis == "supporting" and unit.lineup[0].name == "Jerry Garcia"
    item = experience.PerformanceListItem(performance_id="p1", show_id="gd-1972-08-27", show_date="1972-08-27", show_label="1972-08-27 — Veneta")
    song = experience.SongOverviewBlock(
        type="song_overview", song_id="song-sugaree", title="Sugaree", known_performance_count=1,
        emphasis="primary", visible_facets=["history"],
        history=experience.SongHistory(known_count=1, first=item, last=item, by_year=[]),
    )
    assert song.history.first.performance_id == "p1"
