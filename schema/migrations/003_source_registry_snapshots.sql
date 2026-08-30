-- Add reviewed source acquisition contracts and immutable retrieval evidence.
BEGIN;

CREATE TABLE source_registry (
    source_id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    host_allowlist TEXT[] NOT NULL DEFAULT '{}',
    authority_level TEXT NOT NULL DEFAULT 'unknown',
    access_state TEXT NOT NULL DEFAULT 'unknown',
    rights_state TEXT NOT NULL DEFAULT 'unknown',
    review_state TEXT NOT NULL DEFAULT 'unreviewed',
    allowed_operations TEXT[] NOT NULL DEFAULT '{}',
    retention_policy JSONB NOT NULL DEFAULT '{}'::jsonb,
    rate_policy JSONB NOT NULL DEFAULT '{}'::jsonb,
    adapter_version TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    notes TEXT,
    CHECK (btrim(source_id) <> ''), CHECK (btrim(name) <> ''),
    CHECK (authority_level IN ('primary', 'official', 'curated', 'community', 'discovery', 'unknown')),
    CHECK (access_state IN ('allowed', 'restricted', 'prohibited', 'unknown')),
    CHECK (rights_state IN ('cleared', 'restricted', 'prohibited', 'unknown')),
    CHECK (review_state IN ('unreviewed', 'approved', 'rejected', 'deprecated')),
    CHECK (jsonb_typeof(retention_policy) = 'object'),
    CHECK (jsonb_typeof(rate_policy) = 'object')
);

CREATE TABLE source_snapshots (
    source_snapshot_id TEXT PRIMARY KEY,
    source_id TEXT NOT NULL REFERENCES source_registry (source_id) ON DELETE RESTRICT,
    normalized_url TEXT NOT NULL,
    retrieved_at TIMESTAMPTZ NOT NULL,
    retrieval_status TEXT NOT NULL,
    content_hash TEXT,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    http_status INTEGER,
    mime_type TEXT,
    adapter_version TEXT NOT NULL,
    CHECK (btrim(source_snapshot_id) <> ''), CHECK (normalized_url ~ '^https?://'),
    CHECK (retrieval_status IN ('retrieved', 'not_modified', 'failed', 'blocked', 'not_found')),
    CHECK (content_hash IS NULL OR content_hash ~ '^sha256:[0-9a-f]{64}$'),
    CHECK (jsonb_typeof(metadata) = 'object'),
    CHECK (http_status IS NULL OR http_status BETWEEN 100 AND 599),
    UNIQUE (source_id, normalized_url, retrieved_at, content_hash)
);

CREATE INDEX source_snapshots_source_id_idx ON source_snapshots (source_id);
CREATE INDEX source_snapshots_url_retrieved_idx
    ON source_snapshots (normalized_url, retrieved_at DESC);

UPDATE deadbot_schema_metadata SET schema_version = 3 WHERE schema_version = 2;

COMMIT;
