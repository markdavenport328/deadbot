"""Runtime selection for the canonical read store.

SQLite is the default: a file built from the checked-in CSVs. PostgreSQL
remains selectable until it is retired. The CSVs themselves are build inputs,
never a serving fallback.
"""

from __future__ import annotations

import os
from typing import Any

from deadbot.config import Settings


def create_canonical_store(settings: Settings | None = None) -> Any:
    """Create the configured runtime store."""

    settings = settings or Settings.from_env()
    if settings.data_store == "sqlite":
        from deadbot.sqlite_build import DEFAULT_SQLITE_PATH, ensure_current
        from deadbot.sqlite_store import SqliteCanonicalStore

        path = settings.sqlite_path or DEFAULT_SQLITE_PATH
        # A local run rebuilds whenever the checked-out data changed. A Vercel
        # deployment built its file from the same commit and cannot write one.
        if not os.environ.get("VERCEL"):
            ensure_current(path)
        return SqliteCanonicalStore(path)
    if settings.data_store == "postgres":
        if not settings.database_url:
            raise ValueError(
                "DEADBOT_DATA_STORE=postgres requires DEADBOT_DATABASE_URL "
                "(or DATABASE_URL)."
            )
        from deadbot.postgres import PostgresStore

        return PostgresStore.from_dsn(settings.database_url)
    raise ValueError(
        "DEADBOT_DATA_STORE must be sqlite or postgres; "
        "CSV files are build inputs, not a runtime store."
    )
