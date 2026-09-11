"""Tests for the relisten-tours collector's retry, merge, and compaction behaviour.

No network calls are made: ``urlopen`` and ``time.sleep`` are monkeypatched.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from urllib.error import HTTPError, URLError

sys.path.insert(0, str(Path(__file__).parents[1] / "scripts" / "collect"))
import fetch_relisten_tours as frt  # noqa: E402


class FakeResponse:
    def __init__(self, status: int, payload: dict):
        self.status = status
        self._payload = payload

    def read(self) -> bytes:
        return json.dumps(self._payload).encode("utf-8")

    def __enter__(self) -> "FakeResponse":
        return self

    def __exit__(self, *exc_info) -> bool:
        return False


def year_id(year: int) -> str:
    return f"relisten:artists/grateful-dead/years/{year}/tours"


# ---------------------------------------------------------------------------
# compact_payload / compact_show: keep only the tour field this collector needs
# ---------------------------------------------------------------------------


def test_compact_show_keeps_null_tour():
    show = {"display_date": "1965-11-01", "uuid": "abc", "tour": None, "avg_rating": 9.0}
    assert frt.compact_show(show) == {"display_date": "1965-11-01", "uuid": "abc", "tour": None}


def test_compact_show_keeps_only_named_tour_fields():
    show = {
        "display_date": "1972-04-07",
        "uuid": "xyz",
        "tour": {
            "name": "Europe 1972",
            "slug": "europe-1972",
            "uuid": "tour-uuid",
            "start_date": "1972-04-07T00:00:00Z",
            "end_date": "1972-05-26T00:00:00Z",
            "id": 1361,
            "shows_on_tour": 22,
        },
    }
    compacted = frt.compact_show(show)
    assert compacted["tour"] == {
        "name": "Europe 1972",
        "slug": "europe-1972",
        "uuid": "tour-uuid",
        "start_date": "1972-04-07T00:00:00Z",
        "end_date": "1972-05-26T00:00:00Z",
    }


def test_compact_payload_sorts_by_display_date():
    payload = {
        "shows": [
            {"display_date": "1972-05-01", "uuid": "b", "tour": None},
            {"display_date": "1972-04-01", "uuid": "a", "tour": None},
        ]
    }
    compacted = frt.compact_payload(payload)
    assert [show["display_date"] for show in compacted["shows"]] == ["1972-04-01", "1972-05-01"]
    assert compacted["show_count"] == 2


# ---------------------------------------------------------------------------
# fetch_year: bounded retry with backoff, mirroring fetch_relisten_years.py
# ---------------------------------------------------------------------------


def test_fetch_year_retries_on_503_then_succeeds(monkeypatch):
    calls = {"n": 0}

    def fake_urlopen(request, timeout=60):
        calls["n"] += 1
        if calls["n"] == 1:
            raise HTTPError(request.full_url, 503, "Service Unavailable", None, None)
        return FakeResponse(200, {"shows": []})

    sleeps: list[float] = []
    monkeypatch.setattr(frt, "urlopen", fake_urlopen)
    monkeypatch.setattr(frt.time, "sleep", lambda seconds: sleeps.append(seconds))

    record = frt.fetch_year(1970)

    assert calls["n"] == 2
    assert record["status"] == 200
    assert record["error"] is None
    assert record["raw_payload"]["show_count"] == 0
    assert sleeps == [2]


def test_fetch_year_does_not_retry_non_retryable_http_error(monkeypatch):
    calls = {"n": 0}

    def fake_urlopen(request, timeout=60):
        calls["n"] += 1
        raise HTTPError(request.full_url, 403, "Forbidden", None, None)

    monkeypatch.setattr(frt, "urlopen", fake_urlopen)
    monkeypatch.setattr(frt.time, "sleep", lambda seconds: None)

    record = frt.fetch_year(1970)

    assert calls["n"] == 1
    assert record["status"] == 403
    assert record["raw_payload"] is None


def test_fetch_year_retries_on_network_error(monkeypatch):
    calls = {"n": 0}

    def fake_urlopen(request, timeout=60):
        calls["n"] += 1
        if calls["n"] == 1:
            raise URLError("connection refused")
        return FakeResponse(200, {"shows": []})

    monkeypatch.setattr(frt, "urlopen", fake_urlopen)
    monkeypatch.setattr(frt.time, "sleep", lambda seconds: None)

    record = frt.fetch_year(1970)

    assert calls["n"] == 2
    assert record["status"] == 200


# ---------------------------------------------------------------------------
# merge_year_records: --force must never erase a successful earlier year
# ---------------------------------------------------------------------------


def test_merge_year_records_keeps_existing_success_when_new_fetch_fails():
    existing = [{"source_record_id": year_id(1970), "status": 200, "raw_payload": {"show_count": 5}}]
    new = [{"source_record_id": year_id(1970), "status": "error", "error": "network down", "raw_payload": None}]

    merged = frt.merge_year_records(existing, new)

    assert merged == existing


def test_merge_year_records_upgrades_existing_failure_when_new_fetch_succeeds():
    existing = [{"source_record_id": year_id(1970), "status": 503, "error": "HTTP 503", "raw_payload": None}]
    new = [{"source_record_id": year_id(1970), "status": 200, "error": None, "raw_payload": {"show_count": 5}}]

    merged = frt.merge_year_records(existing, new)

    assert merged == new


def test_merge_year_records_sorts_by_year():
    existing = [{"source_record_id": year_id(1971), "status": 200}]
    new = [{"source_record_id": year_id(1970), "status": 200}]

    merged = frt.merge_year_records(existing, new)

    assert [record["source_record_id"] for record in merged] == [year_id(1970), year_id(1971)]


# ---------------------------------------------------------------------------
# collect(): writes via a .partial file and never destroys a preserved
# successful run when the rerun fails.
# ---------------------------------------------------------------------------


def test_collect_with_force_preserves_success_when_rerun_fails(tmp_path, monkeypatch):
    output = tmp_path / "relisten-tours.jsonl"
    monkeypatch.setattr(frt, "OUTPUT_DIR", tmp_path)
    monkeypatch.setattr(frt, "OUTPUT", output)
    monkeypatch.setattr(frt.time, "sleep", lambda seconds: None)

    existing_records = [
        {
            "source": "relisten",
            "source_record_id": year_id(1970),
            "retrieved_at": "2026-01-01T00:00:00Z",
            "source_url": "https://api.relisten.net/api/v2/artists/grateful-dead/years/1970",
            "status": 200,
            "error": None,
            "raw_payload": {"show_count": 1, "shows": []},
        }
    ]
    output.write_text("\n".join(json.dumps(record) for record in existing_records) + "\n", encoding="utf-8")

    def failing_fetch_year(year: int) -> dict:
        return {
            "source": "relisten",
            "source_record_id": year_id(year),
            "retrieved_at": "2026-01-02T00:00:00Z",
            "source_url": f"https://api.relisten.net/api/v2/artists/grateful-dead/years/{year}",
            "status": "error",
            "error": "URLError: network down",
            "raw_payload": None,
        }

    monkeypatch.setattr(frt, "fetch_year", failing_fetch_year)

    frt.collect([1970], force=True)

    assert not (tmp_path / "relisten-tours.jsonl.partial").exists()
    result = [json.loads(line) for line in output.read_text(encoding="utf-8").splitlines() if line]
    assert result[0]["status"] == 200
    assert result[0]["raw_payload"]["show_count"] == 1


def test_collect_without_force_refuses_to_overwrite_existing_output(tmp_path, monkeypatch):
    output = tmp_path / "relisten-tours.jsonl"
    output.write_text("{}\n", encoding="utf-8")
    monkeypatch.setattr(frt, "OUTPUT_DIR", tmp_path)
    monkeypatch.setattr(frt, "OUTPUT", output)

    try:
        frt.collect([1970], force=False)
    except FileExistsError:
        pass
    else:
        raise AssertionError("expected FileExistsError")
