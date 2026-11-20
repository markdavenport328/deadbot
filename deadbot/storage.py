"""The canonical read store: one SQLite file built from the checked-in CSVs.

There is nothing to select. The CSVs are build inputs, never a serving
fallback, and no environment variable chooses a store: a ``DEADBOT_DATA_STORE``
left over from an older deployment is not read.
"""

from __future__ import annotations

import os

from deadbot import sqlite_build
from deadbot.config import Settings
from deadbot.sqlite_store import SqliteCanonicalStore


def create_canonical_store(settings: Settings | None = None) -> SqliteCanonicalStore:
    """Open the SQLite store, building it first on a local run if the data changed."""

    settings = settings or Settings.from_env()
    path = settings.sqlite_path or sqlite_build.DEFAULT_SQLITE_PATH
    # A local run rebuilds whenever the checked-out data changed. A Vercel
    # deployment built its file from the same commit and cannot write one.
    if not os.environ.get("VERCEL"):
        sqlite_build.ensure_current(path)
    return SqliteCanonicalStore(path)
