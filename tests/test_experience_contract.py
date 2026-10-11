"""Contract-version tests for `deadbot.experience` in isolation.

These are the contract's standalone tests: they import only
`deadbot.experience`, not `deadbot.composition` or `deadbot.finish`, so a
change in those two modules cannot make these tests fail to collect for a
reason unrelated to what they check.
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


def test_show_unit_accepts_lineup_and_recordings_facets_and_song_overview_accepts_the_timeline():
    unit = experience.ShowUnitBlock(
        type="show_unit", show_id="gd-1972-08-27", show_date="1972-08-27",
        visible_facets=["lineup", "recordings"],
        lineup=[experience.PerformerItem(person_id="jerry", name="Jerry Garcia", role="performer", instruments=["guitar"])],
        recordings=[experience.RecordingItem(recording_id="r1", title="SBD", source_type="soundboard", url="https://archive.org/details/x", source_id="recording:r1")],
    )
    assert unit.emphasis == "supporting" and unit.lineup[0].name == "Jerry Garcia"
    song = experience.SongOverviewBlock(
        type="song_overview", song_id="song-sugaree", title="Sugaree", known_performance_count=1,
        emphasis="primary", visible_facets=["by_year"], open_year=1972,
        year_summaries=[experience.SongYearSummary(year=1972, count=1)],
        length_points=[experience.SongLengthPoint(performance_id="p1", show_date="1972-08-27", seconds=600)],
    )
    assert song.year_summaries[0].count == 1 and song.open_year == 1972
