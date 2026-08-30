"""Runtime selection for the canonical read store.

CSV remains the portable source-of-truth representation while PostgreSQL can
serve the same read contract in deployed or larger local environments.
"""

from __future__ import annotations

from typing import Any

from deadbot.config import Settings
from deadbot.data import CanonicalStore


def create_canonical_store(settings: Settings | None = None) -> Any:
    """Create the configured canonical store without eagerly requiring Postgres."""

    settings = settings or Settings.from_env()
    if settings.data_store == "csv":
        return CanonicalStore()
    if settings.data_store == "postgres":
        if not settings.database_url:
            raise ValueError(
                "DEADBOT_DATA_STORE=postgres requires DEADBOT_DATABASE_URL "
                "(or DATABASE_URL)."
            )
        from deadbot.postgres import PostgresStore

        return PostgresStore.from_dsn(settings.database_url)
    raise ValueError(
        f"Unsupported DEADBOT_DATA_STORE={settings.data_store!r}; expected 'csv' or 'postgres'."
    )
