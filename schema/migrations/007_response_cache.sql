-- Cached composed answers for repeated questions (the opening suggestion
-- chips above all). A row is keyed by the normalized question text and
-- stamped with the data version and deployed commit that produced it, so a
-- data import or a code deploy invalidates it without deleting anything.
-- The application also creates this table lazily with IF NOT EXISTS, so a
-- deploy ahead of this migration still serves answers; the migration keeps
-- the checked-in schema authoritative.
BEGIN;

CREATE TABLE IF NOT EXISTS deadbot_response_cache (
    question_key TEXT PRIMARY KEY,
    data_version TEXT NOT NULL,
    question TEXT NOT NULL,
    response TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

UPDATE deadbot_schema_metadata SET schema_version = 7;

COMMIT;
