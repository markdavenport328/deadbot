"""POST /api/grid: the visitor's reshape of a grid, built from the library alone."""

import pytest
from fastapi.testclient import TestClient

from deadbot.api import create_app
from deadbot.config import Settings
from deadbot.sqlite_store import SqliteCanonicalStore

SHOWS = ["gd-1972-05-11", "gd-1972-05-07"]


@pytest.fixture
def client(built_sqlite, tmp_path):
    store = SqliteCanonicalStore(built_sqlite, response_cache_path=tmp_path / "cache.sqlite")
    dist = tmp_path / "dist"
    dist.mkdir()
    (dist / "index.html").write_text("<!doctype html><title>shell</title>")
    app = create_app(settings=Settings(), store=store, agent=object(), client_dist=dist)
    with TestClient(app) as test_client:
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
