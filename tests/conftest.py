import pytest


@pytest.fixture(scope="session")
def built_sqlite(tmp_path_factory):
    """The real canonical CSVs built once per session into a SQLite file."""

    from deadbot.sqlite_build import build_database

    return build_database(tmp_path_factory.mktemp("sqlite") / "deadbot.sqlite").path
