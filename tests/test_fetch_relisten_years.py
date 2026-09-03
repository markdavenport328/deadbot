"""Tests for the relisten-years collector's retry, merge, and force behaviour.

No network calls are made: ``urlopen`` and ``time.sleep`` are monkeypatched.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from urllib.error import HTTPError, URLError

sys.path.insert(0, str(Path(__file__).parents[1] / "scripts" / "collect"))
import fetch_relisten_years as fry  # noqa: E402


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
    return f"relisten:artists/grateful-dead/years/{year}"


# ---------------------------------------------------------------------------
# fetch_year: bounded retry with backoff and 429/503 handling (Important 2)
# ---------------------------------------------------------------------------


def test_fetch_year_retries_on_503_then_succeeds(monkeypatch):
    calls = {"n": 0}

    def fake_urlopen(request, timeout=60):
        calls["n"] += 1
        if calls["n"] == 1:
            raise HTTPError(request.full_url, 503, "Service Unavailable", None, None)
        return FakeResponse(200, {"shows": []})

    sleeps: list[float] = []
    monkeypatch.setattr(fry, "urlopen", fake_urlopen)
    monkeypatch.setattr(fry.time, "sleep", lambda seconds: sleeps.append(seconds))

    record = fry.fetch_year(1970)

    assert calls["n"] == 2
    assert record["status"] == 200
    assert record["error"] is None
    assert record["raw_payload"]["show_count_returned"] == 0
    assert sleeps == [2]


def test_fetch_year_retries_on_429_then_succeeds(monkeypatch):
    calls = {"n": 0}

    def fake_urlopen(request, timeout=60):
        calls["n"] += 1
        if calls["n"] == 1:
            raise HTTPError(request.full_url, 429, "Too Many Requests", None, None)
        return FakeResponse(200, {"shows": []})

    monkeypatch.setattr(fry, "urlopen", fake_urlopen)
    monkeypatch.setattr(fry.time, "sleep", lambda seconds: None)

    record = fry.fetch_year(1970)

    assert calls["n"] == 2
    assert record["status"] == 200


def test_fetch_year_does_not_retry_non_retryable_http_error(monkeypatch):
    calls = {"n": 0}

    def fake_urlopen(request, timeout=60):
        calls["n"] += 1
        raise HTTPError(request.full_url, 404, "Not Found", None, None)

    sleeps: list[float] = []
    monkeypatch.setattr(fry, "urlopen", fake_urlopen)
    monkeypatch.setattr(fry.time, "sleep", lambda seconds: sleeps.append(seconds))

    record = fry.fetch_year(1970)

    assert calls["n"] == 1
    assert record["status"] == 404
    assert record["raw_payload"] is None
    assert sleeps == []


def test_fetch_year_gives_up_after_max_attempts_on_persistent_503(monkeypatch):
    calls = {"n": 0}

    def fake_urlopen(request, timeout=60):
        calls["n"] += 1
        raise HTTPError(request.full_url, 503, "Service Unavailable", None, None)

    sleeps: list[float] = []
    monkeypatch.setattr(fry, "urlopen", fake_urlopen)
    monkeypatch.setattr(fry.time, "sleep", lambda seconds: sleeps.append(seconds))

    record = fry.fetch_year(1970)

    assert calls["n"] == fry.MAX_ATTEMPTS
    assert record["status"] == 503
    assert record["raw_payload"] is None
    # No sleep after the final attempt.
    assert len(sleeps) == fry.MAX_ATTEMPTS - 1


def test_fetch_year_retries_on_network_error(monkeypatch):
    calls = {"n": 0}

    def fake_urlopen(request, timeout=60):
        calls["n"] += 1
        if calls["n"] == 1:
            raise URLError("connection refused")
        return FakeResponse(200, {"shows": []})

    monkeypatch.setattr(fry, "urlopen", fake_urlopen)
    monkeypatch.setattr(fry.time, "sleep", lambda seconds: None)

    record = fry.fetch_year(1970)

    assert calls["n"] == 2
    assert record["status"] == 200


# ---------------------------------------------------------------------------
# merge_year_records: --force must never erase a successful earlier year
# (Important 1)
# ---------------------------------------------------------------------------


def test_merge_year_records_keeps_existing_success_when_new_fetch_fails():
    existing = [
        {"source_record_id": year_id(1970), "status": 200, "raw_payload": {"show_count_returned": 5}},
    ]
    new = [
        {"source_record_id": year_id(1970), "status": "error", "error": "network down", "raw_payload": None},
    ]

    merged = fry.merge_year_records(existing, new)

    assert merged == existing


def test_merge_year_records_upgrades_existing_failure_when_new_fetch_succeeds():
    existing = [
        {"source_record_id": year_id(1970), "status": 503, "error": "HTTP 503", "raw_payload": None},
    ]
    new = [
        {"source_record_id": year_id(1970), "status": 200, "error": None, "raw_payload": {"show_count_returned": 5}},
    ]

    merged = fry.merge_year_records(existing, new)

    assert merged == new


def test_merge_year_records_refreshes_a_repeated_success():
    existing = [
        {"source_record_id": year_id(1970), "status": 200, "raw_payload": {"show_count_returned": 5}},
    ]
    new = [
        {"source_record_id": year_id(1970), "status": 200, "raw_payload": {"show_count_returned": 6}},
    ]

    merged = fry.merge_year_records(existing, new)

    assert merged == new


def test_merge_year_records_leaves_years_outside_this_run_untouched():
    existing = [
        {"source_record_id": year_id(1970), "status": 200},
        {"source_record_id": year_id(1971), "status": 200},
    ]
    new = [
        {"source_record_id": year_id(1970), "status": "error", "raw_payload": None},
    ]

    merged = fry.merge_year_records(existing, new)
    by_id = {record["source_record_id"]: record for record in merged}

    assert by_id[year_id(1970)]["status"] == 200
    assert by_id[year_id(1971)]["status"] == 200


def test_merge_year_records_adds_a_new_year_and_sorts_by_year():
    existing = [{"source_record_id": year_id(1971), "status": 200}]
    new = [{"source_record_id": year_id(1970), "status": 200}]

    merged = fry.merge_year_records(existing, new)

    assert [record["source_record_id"] for record in merged] == [year_id(1970), year_id(1971)]


# ---------------------------------------------------------------------------
# collect(): --force writes via a .partial file and never destroys a
# preserved successful run when the rerun fails (Important 1, end to end).
# ---------------------------------------------------------------------------


def test_collect_with_force_preserves_success_when_rerun_fails(tmp_path, monkeypatch):
    output = tmp_path / "relisten-years.jsonl"
    monkeypatch.setattr(fry, "OUTPUT_DIR", tmp_path)
    monkeypatch.setattr(fry, "OUTPUT", output)
    monkeypatch.setattr(fry.time, "sleep", lambda seconds: None)

    existing_records = [
        {
            "source": "relisten",
            "source_record_id": year_id(1970),
            "retrieved_at": "2026-01-01T00:00:00Z",
            "source_url": "https://api.relisten.net/api/v2/artists/grateful-dead/years/1970",
            "status": 200,
            "error": None,
            "raw_payload": {"year": {"year": 1970}, "show_count_returned": 1, "shows": []},
        },
        {
            "source": "relisten",
            "source_record_id": year_id(1971),
            "retrieved_at": "2026-01-01T00:00:00Z",
            "source_url": "https://api.relisten.net/api/v2/artists/grateful-dead/years/1971",
            "status": 200,
            "error": None,
            "raw_payload": {"year": {"year": 1971}, "show_count_returned": 2, "shows": []},
        },
    ]
    output.write_text(
        "\n".join(json.dumps(record) for record in existing_records) + "\n", encoding="utf-8"
    )

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

    monkeypatch.setattr(fry, "fetch_year", failing_fetch_year)

    fry.collect([1970], force=True)

    assert not (tmp_path / "relisten-years.jsonl.partial").exists()
    result = [json.loads(line) for line in output.read_text(encoding="utf-8").splitlines() if line]
    by_id = {record["source_record_id"]: record for record in result}
    assert by_id[year_id(1970)]["status"] == 200
    assert by_id[year_id(1970)]["raw_payload"]["show_count_returned"] == 1
    assert by_id[year_id(1971)]["status"] == 200


def test_collect_without_force_refuses_to_overwrite_existing_output(tmp_path, monkeypatch):
    output = tmp_path / "relisten-years.jsonl"
    output.write_text("{}\n", encoding="utf-8")
    monkeypatch.setattr(fry, "OUTPUT_DIR", tmp_path)
    monkeypatch.setattr(fry, "OUTPUT", output)

    try:
        fry.collect([1970], force=False)
    except FileExistsError:
        pass
    else:
        raise AssertionError("expected FileExistsError")
