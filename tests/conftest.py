import pytest


@pytest.fixture(scope="session")
def built_sqlite(tmp_path_factory):
    """The real canonical CSVs built once per session into a SQLite file."""

    from deadbot.sqlite_build import build_database

    return build_database(tmp_path_factory.mktemp("sqlite") / "deadbot.sqlite").path


@pytest.fixture(autouse=True)
def _no_listener_remarks_from_the_network(monkeypatch):
    """Tools fetch archive.org listener remarks live; tests stay offline (a test may restore the method)."""

    from deadbot.site_search import SiteSearcher

    monkeypatch.setattr(SiteSearcher, "listener_remarks", lambda self, identifier, song_title, limit=3: [])
