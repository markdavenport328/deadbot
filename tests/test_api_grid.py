"""POST /api/grid: the visitor's reshape of a grid, built from the library alone."""

import pytest
from fastapi.testclient import TestClient

from deadbot.api import create_app
from deadbot.config import Settings
from deadbot.sqlite_store import SqliteCanonicalStore

SHOWS = ["gd-1972-05-11", "gd-1972-05-07"]


def make_client(built_sqlite, tmp_path, settings):
    store = SqliteCanonicalStore(built_sqlite, response_cache_path=tmp_path / "cache.sqlite")
    dist = tmp_path / "dist"
    dist.mkdir()
    (dist / "index.html").write_text("<!doctype html><title>shell</title>")
    app = create_app(settings=settings, store=store, agent=object(), client_dist=dist)
    return TestClient(app)


@pytest.fixture
def client(built_sqlite, tmp_path):
    with make_client(built_sqlite, tmp_path, Settings()) as test_client:
        yield test_client


def spec(columns, rows=SHOWS):
    return {"row_kind": "show", "row_ids": rows, "column_kind": "song", "column_ids": columns}


def test_grid_endpoint_adds_a_column(client):
    response = client.post(
        "/api/grid", json={"spec": spec(["song-dark-star", "song-morning-dew"]), "title": "T"}
    )
    assert response.status_code == 200
    body = response.json()
    assert body["type"] == "grid"
    assert [c["id"] for c in body["columns"]] == ["song-dark-star", "song-morning-dew"]
    assert body["rows"][0]["cells"][1]["state"] == "value"  # Morning Dew in Rotterdam
    assert body["grid_id"].startswith("grid:")


def test_grid_endpoint_keeps_the_original_words_and_drops_the_models_picks(client):
    response = client.post(
        "/api/grid",
        json={
            "spec": spec(["song-dark-star"]),
            "title": "One big jam a night",
            "note": "Written for the first grid.",
            "open_rows": 1,
        },
    )
    body = response.json()
    assert body["title"] == "One big jam a night"
    assert body["note"] == "Written for the first grid."
    assert body["open_rows"] == 1
    assert body["follow_ups"] == []
    assert body["coverage"] is None
    assert not any(cell["highlight"] for row in body["rows"] for cell in row["cells"])
    assert body["suggestions"]


def test_grid_endpoint_keeps_the_row_order_the_visitor_sees(client):
    body = client.post("/api/grid", json={"spec": spec(["song-dark-star"], SHOWS)}).json()
    assert [row["id"] for row in body["rows"]] == SHOWS


def test_grid_endpoint_rejects_unsupported_pairs_cleanly(client):
    response = client.post(
        "/api/grid",
        json={
            "spec": {
                "row_kind": "song",
                "row_ids": ["song-dark-star"],
                "column_kind": "song",
                "column_ids": ["song-dark-star"],
            }
        },
    )
    assert response.status_code == 422


def test_grid_endpoint_answers_404_when_the_library_has_nothing_to_draw(client):
    response = client.post("/api/grid", json={"spec": spec(["song-dark-star"], ["gd-0000-00-00"])})
    assert response.status_code == 404


def test_grid_endpoint_is_served_by_the_api_not_the_client_shell(client):
    response = client.post("/api/grid", json={"spec": spec(["song-dark-star"])})
    assert response.headers["content-type"].startswith("application/json")


def test_grid_endpoint_reshapes_a_song_by_year_grid(client):
    years = [f"year:{year}" for year in (1971, 1972, 1973)]
    request_spec = {"row_kind": "song", "row_ids": ["song-dark-star"], "column_kind": "year", "column_ids": years}
    full = client.post("/api/grid", json={"spec": request_spec}).json()
    assert [c["id"] for c in full["columns"]] == years
    # The client sends back the ids the block carried, minus the removed year.
    reduced_spec = {**full["spec"], "column_ids": [c["id"] for c in full["columns"] if c["id"] != "year:1972"]}
    response = client.post("/api/grid", json={"spec": reduced_spec})
    assert response.status_code == 200
    body = response.json()
    assert [c["id"] for c in body["columns"]] == ["year:1971", "year:1973"]
    assert [c["sub"] for c in body["columns"]] == ["1971", "1973"]
    assert body["suggestions"] == []


def test_a_long_note_still_reshapes_and_comes_back_intact(client):
    note = "A long note. " * 400  # 5,200 characters
    response = client.post("/api/grid", json={"spec": spec(["song-dark-star"]), "note": note})
    assert response.status_code == 200
    assert response.json()["note"] == note.strip()


def test_a_note_past_the_ceiling_is_cut_not_refused(client):
    response = client.post(
        "/api/grid", json={"spec": spec(["song-dark-star"]), "note": "x" * 15_000, "coverage": "y" * 15_000}
    )
    assert response.status_code == 200
    body = response.json()
    assert len(body["note"]) == 10_000
    assert len(body["coverage"]) == 10_000


def test_grid_endpoint_hands_the_coverage_back(client):
    body = client.post(
        "/api/grid", json={"spec": spec(["song-dark-star"]), "coverage": "Setlists are thin before 1971."}
    ).json()
    assert body["coverage"] == "Setlists are thin before 1971."


def test_reshapes_have_their_own_rate_limit_bucket(built_sqlite, tmp_path):
    settings = Settings(rate_limit_per_minute=1, grid_rate_limit_per_minute=2)
    with make_client(built_sqlite, tmp_path, settings) as tight:
        body = {"spec": spec(["song-dark-star"])}
        assert [tight.post("/api/grid", json=body).status_code for _ in range(3)] == [200, 200, 429]


def test_reshapes_do_not_spend_the_question_budget(built_sqlite, tmp_path):
    settings = Settings(rate_limit_per_minute=1, grid_rate_limit_per_minute=60)
    with make_client(built_sqlite, tmp_path, settings) as roomy:
        body = {"spec": spec(["song-dark-star"])}
        assert all(roomy.post("/api/grid", json=body).status_code == 200 for _ in range(5))
        # The question bucket is still untouched: its one request is not a 429.
        assert roomy.post("/api/experience", json={"question": ""}).status_code == 422
