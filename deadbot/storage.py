"""Runtime selection for the required PostgreSQL read store.

The checked-in CSVs are import inputs. They are never a serving fallback.
"""

from __future__ import annotations

from typing import Any

from deadbot.config import Settings


def create_canonical_store(settings: Settings | None = None) -> Any:
    """Create and verify the sole supported runtime store."""

    settings = settings or Settings.from_env()
    if settings.data_store != "postgres":
        raise ValueError(
            "Deadbot serves only PostgreSQL. Set DEADBOT_DATA_STORE=postgres; "
            "CSV files are import inputs, not a runtime fallback."
        )
    if not settings.database_url:
        raise ValueError(
            "DEADBOT_DATA_STORE=postgres requires DEADBOT_DATABASE_URL "
            "(or DATABASE_URL)."
        )
    from deadbot.postgres import PostgresStore

    return PostgresStore.from_dsn(settings.database_url)
