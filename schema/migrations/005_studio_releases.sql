-- Studio albums join the release catalog rather than forming a parallel one.
-- A studio track has no performance, because a performance is a song played
-- at a show, so a track may name its composition directly.
BEGIN;

ALTER TABLE official_release_tracks
    ADD COLUMN song_id TEXT REFERENCES songs (song_id) ON DELETE SET NULL;

CREATE INDEX official_release_tracks_song_id_idx
    ON official_release_tracks (song_id);

-- The 294 existing rows are all 'live' and already conform.
ALTER TABLE official_releases
    ADD CONSTRAINT official_releases_release_type_check
    CHECK (release_type IN ('studio', 'live', 'compilation', 'single'));

-- One row per person's role-and-instrument credit on a release, shaped like
-- show_performers.  instrument is NOT NULL because it is part of the key.
CREATE TABLE release_personnel (
    release_id TEXT NOT NULL REFERENCES official_releases (release_id) ON DELETE CASCADE,
    person_id TEXT NOT NULL REFERENCES people (person_id) ON DELETE CASCADE,
    role TEXT NOT NULL,
    instrument TEXT NOT NULL,
    notes TEXT,
    PRIMARY KEY (release_id, person_id, role, instrument)
);

UPDATE deadbot_schema_metadata SET schema_version = 5;

COMMIT;
