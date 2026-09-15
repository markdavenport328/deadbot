-- Who played on one particular song, when a source says so.
-- show_performers answers "who was onstage at this show"; a guest credit
-- there says Santana was at the Cow Palace, not which songs he played. This
-- table carries the song-level claim, one row per person's role-and-instrument
-- assignment on one performance, shaped like show_performers. It is sparse by
-- design: a row exists only where a source pins the guest to the song, so an
-- appearance with no rows here stays show-level rather than guessed.
BEGIN;

CREATE TABLE performance_performers (
    performance_id TEXT NOT NULL REFERENCES performances (performance_id) ON DELETE CASCADE,
    person_id TEXT NOT NULL REFERENCES people (person_id) ON DELETE CASCADE,
    role TEXT NOT NULL,
    instrument TEXT NOT NULL,
    notes TEXT,
    source_key TEXT,
    source_record_id TEXT,
    PRIMARY KEY (performance_id, person_id, role, instrument)
);

CREATE INDEX performance_performers_person_id_idx ON performance_performers (person_id);

UPDATE deadbot_schema_metadata SET schema_version = 10;

COMMIT;
