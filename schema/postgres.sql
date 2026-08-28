-- Deadbot canonical domain schema.
-- This file is designed to be rebuilt entirely from data/canonical CSV files.
-- Future semantic-search tables (for example, text chunks and embeddings using
-- pgvector) belong alongside this core model, not in the canonical entity tables.

BEGIN;

CREATE TABLE people (
    person_id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    birth_date DATE,
    death_date DATE,
    notes TEXT,
    CHECK (death_date IS NULL OR birth_date IS NULL OR death_date >= birth_date)
);

CREATE TABLE songs (
    song_id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    slug TEXT NOT NULL UNIQUE,
    original_artist TEXT,
    first_known_dead_performance DATE,
    last_known_dead_performance DATE,
    notes TEXT,
    CHECK (
        last_known_dead_performance IS NULL
        OR first_known_dead_performance IS NULL
        OR last_known_dead_performance >= first_known_dead_performance
    )
);

CREATE TABLE venues (
    venue_id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    city TEXT,
    state_region TEXT,
    country TEXT,
    latitude DOUBLE PRECISION,
    longitude DOUBLE PRECISION,
    notes TEXT,
    CHECK (latitude IS NULL OR latitude BETWEEN -90 AND 90),
    CHECK (longitude IS NULL OR longitude BETWEEN -180 AND 180)
);

CREATE TABLE shows (
    show_id TEXT PRIMARY KEY,
    show_date DATE NOT NULL,
    venue_id TEXT NOT NULL REFERENCES venues (venue_id),
    tour_name TEXT,
    event_name TEXT,
    notes TEXT,
    source_key TEXT,
    source_record_id TEXT
);

CREATE TABLE song_writers (
    song_id TEXT NOT NULL REFERENCES songs (song_id) ON DELETE CASCADE,
    person_id TEXT NOT NULL REFERENCES people (person_id) ON DELETE CASCADE,
    writer_role TEXT NOT NULL,
    notes TEXT,
    PRIMARY KEY (song_id, person_id, writer_role)
);

CREATE TABLE resources (
    resource_id TEXT PRIMARY KEY,
    resource_type TEXT NOT NULL,
    title TEXT NOT NULL,
    creator TEXT,
    source_name TEXT NOT NULL,
    source_url TEXT NOT NULL,
    published_date DATE,
    notes TEXT,
    UNIQUE (source_url)
);

CREATE TABLE resource_songs (
    resource_id TEXT NOT NULL REFERENCES resources (resource_id) ON DELETE CASCADE,
    song_id TEXT NOT NULL REFERENCES songs (song_id) ON DELETE CASCADE,
    relationship_type TEXT NOT NULL,
    notes TEXT,
    PRIMARY KEY (resource_id, song_id, relationship_type)
);

CREATE TABLE resource_shows (
    resource_id TEXT NOT NULL REFERENCES resources (resource_id) ON DELETE CASCADE,
    show_id TEXT NOT NULL REFERENCES shows (show_id) ON DELETE CASCADE,
    relationship_type TEXT NOT NULL,
    notes TEXT,
    PRIMARY KEY (resource_id, show_id, relationship_type)
);

CREATE TABLE show_performers (
    show_id TEXT NOT NULL REFERENCES shows (show_id) ON DELETE CASCADE,
    person_id TEXT NOT NULL REFERENCES people (person_id) ON DELETE CASCADE,
    role TEXT NOT NULL,
    instrument TEXT NOT NULL,
    notes TEXT,
    source_key TEXT,
    source_record_id TEXT,
    PRIMARY KEY (show_id, person_id, role, instrument)
);

CREATE TABLE performances (
    performance_id TEXT PRIMARY KEY,
    show_id TEXT NOT NULL REFERENCES shows (show_id) ON DELETE CASCADE,
    song_id TEXT NOT NULL REFERENCES songs (song_id),
    set_number INTEGER,
    set_label TEXT,
    position_in_set INTEGER NOT NULL,
    encore BOOLEAN NOT NULL DEFAULT FALSE,
    segue_into_next BOOLEAN NOT NULL DEFAULT FALSE,
    performance_notes TEXT,
    source_key TEXT,
    source_record_id TEXT,
    CHECK (set_number IS NULL OR set_number > 0),
    CHECK (position_in_set > 0),
    UNIQUE (show_id, set_number, position_in_set)
);

CREATE TABLE resource_performances (
    resource_id TEXT NOT NULL REFERENCES resources (resource_id) ON DELETE CASCADE,
    performance_id TEXT NOT NULL REFERENCES performances (performance_id) ON DELETE CASCADE,
    relationship_type TEXT NOT NULL,
    notes TEXT,
    PRIMARY KEY (resource_id, performance_id, relationship_type)
);

CREATE TABLE show_links (
    show_link_id TEXT PRIMARY KEY,
    show_id TEXT NOT NULL REFERENCES shows (show_id) ON DELETE CASCADE,
    platform TEXT NOT NULL,
    link_type TEXT NOT NULL,
    url TEXT NOT NULL,
    title TEXT,
    is_official BOOLEAN NOT NULL DEFAULT FALSE,
    notes TEXT,
    UNIQUE (show_id, platform, url)
);

CREATE TABLE performance_links (
    performance_link_id TEXT PRIMARY KEY,
    performance_id TEXT NOT NULL REFERENCES performances (performance_id) ON DELETE CASCADE,
    platform TEXT NOT NULL,
    link_type TEXT NOT NULL,
    url TEXT NOT NULL,
    title TEXT,
    start_seconds INTEGER,
    duration_seconds INTEGER,
    is_official BOOLEAN NOT NULL DEFAULT FALSE,
    notes TEXT,
    UNIQUE (performance_id, platform, url),
    CHECK (start_seconds IS NULL OR start_seconds >= 0),
    CHECK (duration_seconds IS NULL OR duration_seconds >= 0)
);

CREATE TABLE official_releases (
    release_id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    artist_name TEXT,
    release_date DATE,
    release_type TEXT,
    spotify_album_url TEXT,
    source_url TEXT NOT NULL,
    notes TEXT
);

CREATE TABLE official_release_tracks (
    release_id TEXT NOT NULL REFERENCES official_releases (release_id) ON DELETE CASCADE,
    track_number INTEGER NOT NULL,
    performance_id TEXT REFERENCES performances (performance_id) ON DELETE SET NULL,
    track_title TEXT NOT NULL,
    duration_seconds INTEGER,
    spotify_track_url TEXT,
    notes TEXT,
    PRIMARY KEY (release_id, track_number),
    CHECK (track_number > 0),
    CHECK (duration_seconds IS NULL OR duration_seconds >= 0)
);

CREATE TABLE song_arrangements (
    arrangement_id TEXT PRIMARY KEY,
    song_id TEXT NOT NULL REFERENCES songs (song_id) ON DELETE CASCADE,
    performance_id TEXT REFERENCES performances (performance_id) ON DELETE CASCADE,
    resource_id TEXT NOT NULL REFERENCES resources (resource_id) ON DELETE RESTRICT,
    arrangement_scope TEXT NOT NULL,
    key_signature TEXT,
    capo TEXT,
    tuning TEXT,
    notes TEXT
);

CREATE TABLE arrangement_chord_sections (
    arrangement_id TEXT NOT NULL REFERENCES song_arrangements (arrangement_id) ON DELETE CASCADE,
    section_position INTEGER NOT NULL,
    section_label TEXT NOT NULL,
    progression TEXT NOT NULL,
    notes TEXT,
    PRIMARY KEY (arrangement_id, section_position),
    CHECK (section_position > 0)
);

-- An arrangement must describe the same song as its source resource and,
-- when present, its performance-specific context.
CREATE FUNCTION check_song_arrangement_context()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM resource_songs rs
        WHERE rs.resource_id = NEW.resource_id
          AND rs.song_id = NEW.song_id
    ) THEN
        RAISE EXCEPTION 'arrangement % has a resource for a different song', NEW.arrangement_id;
    END IF;

    IF NEW.performance_id IS NOT NULL AND NOT EXISTS (
        SELECT 1
        FROM performances p
        WHERE p.performance_id = NEW.performance_id
          AND p.song_id = NEW.song_id
    ) THEN
        RAISE EXCEPTION 'arrangement % has a performance for a different song', NEW.arrangement_id;
    END IF;

    RETURN NEW;
END;
$$;

CREATE TRIGGER song_arrangements_same_song
BEFORE INSERT OR UPDATE OF song_id, performance_id, resource_id ON song_arrangements
FOR EACH ROW EXECUTE FUNCTION check_song_arrangement_context();

CREATE TABLE recordings (
    recording_id TEXT PRIMARY KEY,
    show_id TEXT NOT NULL REFERENCES shows (show_id) ON DELETE CASCADE,
    source_type TEXT,
    taper TEXT,
    transferer TEXT,
    shnid TEXT,
    archive_identifier TEXT,
    source_description TEXT,
    lineage TEXT,
    source_url TEXT,
    notes TEXT
);

CREATE TABLE performance_recordings (
    performance_id TEXT NOT NULL REFERENCES performances (performance_id) ON DELETE CASCADE,
    recording_id TEXT NOT NULL REFERENCES recordings (recording_id) ON DELETE CASCADE,
    track_number INTEGER NOT NULL,
    start_seconds INTEGER,
    duration_seconds INTEGER,
    track_title TEXT,
    notes TEXT,
    PRIMARY KEY (performance_id, recording_id, track_number),
    CHECK (track_number > 0),
    CHECK (start_seconds IS NULL OR start_seconds >= 0),
    CHECK (duration_seconds IS NULL OR duration_seconds >= 0)
);

-- A recording source belongs to one show, so its mapped performances must too.
CREATE FUNCTION check_performance_recording_show()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM performances p
        JOIN recordings r ON r.recording_id = NEW.recording_id
        WHERE p.performance_id = NEW.performance_id
          AND p.show_id = r.show_id
    ) THEN
        RAISE EXCEPTION 'performance % and recording % belong to different shows',
            NEW.performance_id, NEW.recording_id;
    END IF;
    RETURN NEW;
END;
$$;

CREATE TRIGGER performance_recordings_same_show
BEFORE INSERT OR UPDATE OF performance_id, recording_id ON performance_recordings
FOR EACH ROW EXECUTE FUNCTION check_performance_recording_show();

CREATE UNIQUE INDEX recordings_shnid_unique
    ON recordings (shnid)
    WHERE shnid IS NOT NULL;

CREATE UNIQUE INDEX recordings_archive_identifier_unique
    ON recordings (archive_identifier)
    WHERE archive_identifier IS NOT NULL;

CREATE INDEX shows_venue_id_idx ON shows (venue_id);
CREATE INDEX shows_show_date_idx ON shows (show_date);
CREATE INDEX performances_show_order_idx
    ON performances (show_id, set_number, position_in_set);
CREATE INDEX performances_song_id_idx ON performances (song_id);
CREATE INDEX show_links_show_id_idx ON show_links (show_id);
CREATE INDEX performance_links_performance_id_idx ON performance_links (performance_id);
CREATE INDEX official_release_tracks_performance_id_idx ON official_release_tracks (performance_id);
CREATE INDEX recordings_show_id_idx ON recordings (show_id);
CREATE INDEX recordings_source_type_idx ON recordings (source_type);
CREATE INDEX performance_recordings_recording_track_idx
    ON performance_recordings (recording_id, track_number);
CREATE INDEX song_writers_person_id_idx ON song_writers (person_id);
CREATE INDEX resource_songs_song_id_idx ON resource_songs (song_id);
CREATE INDEX resource_shows_show_id_idx ON resource_shows (show_id);
CREATE INDEX resource_performances_performance_id_idx ON resource_performances (performance_id);
CREATE INDEX song_arrangements_song_id_idx ON song_arrangements (song_id);
CREATE INDEX song_arrangements_performance_id_idx ON song_arrangements (performance_id);
CREATE INDEX show_performers_person_id_idx ON show_performers (person_id);

COMMIT;
