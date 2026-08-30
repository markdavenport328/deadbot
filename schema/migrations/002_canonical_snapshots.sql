-- Upgrade schema version 1 to version 2 without dropping canonical or
-- enrichment data. Existing observations remain readable; the NOT VALID
-- constraint below still enforces snapshot references on future writes.
BEGIN;

CREATE TABLE canonical_snapshots (
    snapshot_id TEXT PRIMARY KEY,
    manifest JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CHECK (snapshot_id ~ '^sha256:[0-9a-f]{64}$'),
    CHECK (jsonb_typeof(manifest) = 'object'),
    CHECK (manifest ? 'format'),
    CHECK (manifest ? 'files')
);

CREATE TABLE canonical_imports (
    import_id UUID PRIMARY KEY,
    snapshot_id TEXT NOT NULL REFERENCES canonical_snapshots (snapshot_id) ON DELETE RESTRICT,
    import_mode TEXT NOT NULL,
    imported_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    table_results JSONB NOT NULL,
    CHECK (import_mode IN ('bootstrap', 'rebuild', 'merge')),
    CHECK (jsonb_typeof(table_results) = 'object')
);

ALTER TABLE derived_observations
    ADD CONSTRAINT derived_observations_input_revision_snapshot_fkey
    FOREIGN KEY (input_revision) REFERENCES canonical_snapshots (snapshot_id)
    DEFERRABLE INITIALLY DEFERRED NOT VALID;

CREATE INDEX canonical_imports_snapshot_id_idx ON canonical_imports (snapshot_id);

UPDATE deadbot_schema_metadata SET schema_version = 2 WHERE schema_version = 1;

COMMIT;
