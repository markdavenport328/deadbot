import json

from deadbot.tools import TOOL_RESULT_CEILING_CHARS, _json


def test_small_payloads_are_unchanged():
    payload = {"a": 1, "items": [{"x": "y"}] * 3, "empty": None}
    assert _json(payload) == json.dumps({"a": 1, "items": [{"x": "y"}] * 3}, separators=(",", ":"))


def test_oversized_payload_trims_its_largest_list_and_says_so():
    payload = {"release": {"title": "Box"}, "tracks": [{"n": i, "title": "x" * 200} for i in range(2000)], "notes": ["short"]}
    result = json.loads(_json(payload))
    assert len(_json(payload)) <= TOOL_RESULT_CEILING_CHARS
    assert result["release"] == {"title": "Box"} and result["notes"] == ["short"]
    entry = result["_truncated"][0]
    assert entry["path"] == "tracks" and entry["total"] == 2000 and 0 < entry["kept"] < 2000
    assert len(result["tracks"]) == entry["kept"]
    assert "narrow" in result["_truncated_note"]


def test_nested_lists_are_found_by_path():
    payload = {"live_legacy": {"song-a": {"versions": ["v" * 100] * 3000}}}
    result = json.loads(_json(payload))
    assert result["_truncated"][0]["path"] == "live_legacy.song-a.versions"
