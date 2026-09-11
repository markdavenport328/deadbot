-- A small canonical answer to "who was in the band, in what role, and when."
-- Previously this was only derivable by scanning all of show_performers.
-- One row per person's role and tenure in a named act; act is a stable text
-- identifier ('grateful-dead' for this pass), not a foreign key, because the
-- catalog does not yet model bands as entities in their own right. A
-- non-contiguous tenure (Mickey Hart leaving and rejoining) carries one row
-- per contiguous span.
BEGIN;

CREATE TABLE band_memberships (
    membership_id TEXT PRIMARY KEY,
    person_id TEXT NOT NULL REFERENCES people (person_id) ON DELETE CASCADE,
    act TEXT NOT NULL,
    role TEXT NOT NULL,
    start_date DATE NOT NULL,
    end_date DATE,
    start_precision TEXT NOT NULL,
    end_precision TEXT,
    source_key TEXT,
    source_record_id TEXT,
    notes TEXT,
    UNIQUE (person_id, act, start_date),
    CHECK (end_date IS NULL OR end_date >= start_date),
    CHECK (start_precision IN ('day', 'month', 'year')),
    CHECK (end_precision IS NULL OR end_precision IN ('day', 'month', 'year')),
    CHECK (end_date IS NOT NULL OR end_precision IS NULL)
);

CREATE INDEX band_memberships_person_id_idx ON band_memberships (person_id);
CREATE INDEX band_memberships_act_dates_idx ON band_memberships (act, start_date, end_date);

UPDATE deadbot_schema_metadata SET schema_version = 9;

COMMIT;
