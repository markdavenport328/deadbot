"""The client shell must not answer for hashed bundles or self-hosted fonts."""

from fastapi.testclient import TestClient

from deadbot.api import create_app
from deadbot.config import Settings
from deadbot.data import CanonicalStore


def _fake_dist(tmp_path):
    dist = tmp_path / "dist"
    (dist / "assets").mkdir(parents=True)
    (dist / "fonts").mkdir()
    (dist / "index.html").write_text("<!doctype html><title>shell</title>")
    (dist / "assets" / "app-abc123.js").write_text("console.log('bundle')")
    # A woff2 starts with the ASCII signature "wOF2".
    (dist / "fonts" / "fraunces-latin.woff2").write_bytes(b"wOF2" + b"\0" * 12)
    return dist


def _client(tmp_path) -> TestClient:
    app = create_app(
        settings=Settings(),
        store=CanonicalStore(),
        agent=object(),
        client_dist=_fake_dist(tmp_path),
    )
    return TestClient(app)


def test_hashed_assets_are_served_as_files(tmp_path):
    response = _client(tmp_path).get("/assets/app-abc123.js")

    assert response.status_code == 200
    assert response.text == "console.log('bundle')"


def test_fonts_are_served_as_files_not_the_shell(tmp_path):
    response = _client(tmp_path).get("/fonts/fraunces-latin.woff2")

    assert response.status_code == 200
    assert response.content.startswith(b"wOF2")
    assert response.headers["content-type"] == "font/woff2"


def test_browser_routes_still_get_the_shell(tmp_path):
    response = _client(tmp_path).get("/songs/dark-star")

    assert response.status_code == 200
    assert "<title>shell</title>" in response.text
