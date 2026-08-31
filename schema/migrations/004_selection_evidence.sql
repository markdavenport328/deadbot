-- Store the complete reviewed selection packet in PostgreSQL so held and
-- ambiguous evidence remains available without pretending it is resolved.
BEGIN;

CREATE TABLE selection_evidence (
    selection_evidence_id TEXT PRIMARY KEY,
    source_resource_id TEXT NOT NULL REFERENCES resources (resource_id)
        DEFERRABLE INITIALLY DEFERRED,
    selection_list_id TEXT REFERENCES selection_lists (selection_list_id)
        DEFERRABLE INITIALLY DEFERRED,
    signal_type TEXT NOT NULL,
    resolution_state TEXT NOT NULL,
    payload JSONB NOT NULL,
    CHECK (jsonb_typeof(payload) = 'object')
);

CREATE INDEX selection_evidence_source_resource_idx
    ON selection_evidence (source_resource_id);
CREATE INDEX selection_evidence_list_idx
    ON selection_evidence (selection_list_id);

UPDATE deadbot_schema_metadata SET schema_version = 4 WHERE schema_version = 3;

COMMIT;
