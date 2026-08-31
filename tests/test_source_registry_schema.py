from pathlib import Path

from deadbot.postgres_import import SCHEMA_VERSION, _schema_sql


ROOT = Path(__file__).parents[1]


def test_source_registry_schema_contract_is_in_bootstrap_and_migration():
    bootstrap = (ROOT / "schema" / "postgres.sql").read_text(encoding="utf-8")
    migration = _schema_sql(ROOT / "schema/migrations/003_source_registry_snapshots.sql")

    assert SCHEMA_VERSION == 4
    for table in ("source_registry", "source_snapshots"):
        assert f"CREATE TABLE {table}" in bootstrap
        assert f"CREATE TABLE {table}" in migration
    for field in (
        "source_id",
        "host_allowlist",
        "authority_level",
        "access_state",
        "rights_state",
        "review_state",
        "allowed_operations",
        "retention_policy",
        "rate_policy",
        "adapter_version",
        "normalized_url",
        "retrieved_at",
        "retrieval_status",
        "content_hash",
        "metadata",
    ):
        assert field in bootstrap
        assert field in migration


def test_source_snapshot_integrity_guards_are_present():
    sql = (ROOT / "schema/migrations/003_source_registry_snapshots.sql").read_text(
        encoding="utf-8"
    )
    assert "REFERENCES source_registry (source_id) ON DELETE RESTRICT" in sql
    assert "normalized_url ~ '^https?://'" in sql
    assert "content_hash ~ '^sha256:[0-9a-f]{64}$'" in sql
    assert "jsonb_typeof(metadata) = 'object'" in sql
    assert "UPDATE deadbot_schema_metadata SET schema_version = 3" in sql


def test_selection_evidence_migration_advances_the_runtime_schema():
    sql = _schema_sql(ROOT / "schema/migrations/004_selection_evidence.sql")
    assert "CREATE TABLE selection_evidence" in sql
    assert "REFERENCES resources (resource_id)" in sql
    assert "UPDATE deadbot_schema_metadata SET schema_version = 4" in sql
