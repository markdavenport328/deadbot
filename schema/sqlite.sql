-- Deadbot canonical schema for the SQLite read store.
--
-- A port of the serving tables in schema/postgres.sql. The file is rebuilt
-- from data/canonical on every deploy (deadbot/sqlite_build.py) and opened
-- read-only at runtime, so triggers only guard inserts. Audit and enrichment
-- tables that nothing reads at runtime (source registry, snapshots, import
-- ledger, claims, observations, release/show coverage) are not ported.

CREATE TABLE deadbot_schema_metadata (
    schema_version INTEGER PRIMARY KEY,
    input_fingerprint TEXT NOT NULL,
    built_at TEXT NOT NULL
);

CREATE TABLE people (
    person_id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    birth_date TEXT,
    death_date TEXT,
    notes TEXT,
    CHECK (death_date IS NULL OR birth_date IS NULL OR death_date >= birth_date)
);

CREATE TABLE songs (
    song_id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    slug TEXT NOT NULL UNIQUE,
    original_artist TEXT,
    first_known_dead_performance TEXT,
    last_known_dead_performance TEXT,
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
    latitude REAL,
    longitude REAL,
    notes TEXT,
    -- Scope the notable-weather question family: 'indoor'/'outdoor' only when
    -- Wikidata's instance-of (or an explicit source statement) makes the
    -- class unambiguous; capacity only where Wikidata states it. A blank is
    -- deliberate -- see docs/collection-status-venue-geography.md.
    setting TEXT,
    capacity INTEGER,
    CHECK (latitude IS NULL OR latitude BETWEEN -90 AND 90),
    CHECK (longitude IS NULL OR longitude BETWEEN -180 AND 180),
    CHECK (setting IS NULL OR setting IN ('indoor', 'outdoor')),
    CHECK (capacity IS NULL OR capacity > 0)
);

CREATE TABLE equipment (
    equipment_id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    category TEXT NOT NULL,
    manufacturer TEXT,
    model TEXT,
    notes TEXT
);

CREATE TABLE shows (
    show_id TEXT PRIMARY KEY,
    show_date TEXT NOT NULL,
    venue_id TEXT NOT NULL REFERENCES venues (venue_id),
    tour_name TEXT,
    event_name TEXT,
    notes TEXT,
    source_key TEXT,
    source_record_id TEXT
);

CREATE INDEX shows_venue_id_idx ON shows (venue_id);
CREATE INDEX shows_show_date_idx ON shows (show_date);
CREATE INDEX shows_source_record_idx ON shows (source_key, source_record_id);

-- These columns deliberately mirror show_equipment.csv. source_id is an
-- external evidence identifier, not a resources.resource_id, so it remains
-- text until that collected source has been promoted to the resource catalog.
CREATE TABLE show_equipment (
    show_id TEXT NOT NULL REFERENCES shows (show_id) ON DELETE CASCADE,
    equipment_id TEXT NOT NULL REFERENCES equipment (equipment_id) ON DELETE CASCADE,
    usage_context TEXT NOT NULL,
    claim_type TEXT NOT NULL,
    claim_id TEXT NOT NULL,
    source_id TEXT NOT NULL,
    source_url TEXT NOT NULL,
    source_note TEXT,
    PRIMARY KEY (show_id, equipment_id, usage_context, claim_id, source_id)
);

CREATE INDEX show_equipment_equipment_id_idx ON show_equipment (equipment_id);
CREATE INDEX show_equipment_claim_id_idx ON show_equipment (claim_id);

CREATE TABLE song_writers (
    song_id TEXT NOT NULL REFERENCES songs (song_id) ON DELETE CASCADE,
    person_id TEXT NOT NULL REFERENCES people (person_id) ON DELETE CASCADE,
    writer_role TEXT NOT NULL,
    notes TEXT,
    PRIMARY KEY (song_id, person_id, writer_role)
);

CREATE INDEX song_writers_person_id_idx ON song_writers (person_id);

-- One row per person's role and tenure in a named act. act is a stable text
-- identifier ('grateful-dead' for this pass), not a foreign key to a band
-- table, because the catalog does not yet model bands as entities in their
-- own right. A person with a non-contiguous tenure (for example, Mickey Hart
-- leaving and rejoining) carries one row per contiguous span. end_date is
-- nullable so a currently active tenure in a future act need not invent an
-- end, but every Grateful Dead row in this pass carries an explicit end date
-- -- 1995-07-09 for a tenure that ran to the band's last show -- rather than
-- leaving it blank.
CREATE TABLE band_memberships (
    membership_id TEXT PRIMARY KEY,
    person_id TEXT NOT NULL REFERENCES people (person_id) ON DELETE CASCADE,
    act TEXT NOT NULL,
    role TEXT NOT NULL,
    start_date TEXT NOT NULL,
    end_date TEXT,
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

CREATE TABLE resources (
    resource_id TEXT PRIMARY KEY,
    resource_type TEXT NOT NULL,
    title TEXT NOT NULL,
    creator TEXT,
    source_name TEXT NOT NULL,
    source_url TEXT NOT NULL,
    published_date TEXT,
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

CREATE INDEX resource_songs_song_id_idx ON resource_songs (song_id);

CREATE TABLE resource_shows (
    resource_id TEXT NOT NULL REFERENCES resources (resource_id) ON DELETE CASCADE,
    show_id TEXT NOT NULL REFERENCES shows (show_id) ON DELETE CASCADE,
    relationship_type TEXT NOT NULL,
    notes TEXT,
    PRIMARY KEY (resource_id, show_id, relationship_type)
);

CREATE INDEX resource_shows_show_id_idx ON resource_shows (show_id);

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

CREATE INDEX show_performers_person_id_idx ON show_performers (person_id);
CREATE INDEX show_performers_source_record_idx
    ON show_performers (source_key, source_record_id);

CREATE TABLE performances (
    performance_id TEXT PRIMARY KEY,
    show_id TEXT NOT NULL REFERENCES shows (show_id) ON DELETE CASCADE,
    song_id TEXT NOT NULL REFERENCES songs (song_id),
    set_number INTEGER,
    set_label TEXT,
    position_in_set INTEGER NOT NULL,
    encore TEXT NOT NULL CHECK (encore IN ('true', 'false')) DEFAULT 'false',
    segue_into_next TEXT NOT NULL CHECK (segue_into_next IN ('true', 'false')) DEFAULT 'false',
    performance_notes TEXT,
    source_key TEXT,
    source_record_id TEXT,
    CHECK (set_number IS NULL OR set_number > 0),
    CHECK (position_in_set > 0),
    UNIQUE (show_id, set_number, position_in_set)
);

CREATE INDEX performances_show_order_idx
    ON performances (show_id, set_number, position_in_set);
CREATE INDEX performances_song_id_idx ON performances (song_id);
CREATE INDEX performances_song_show_idx ON performances (song_id, show_id);
CREATE INDEX performances_source_record_idx
    ON performances (source_key, source_record_id);

-- Song-level performer credits, sparse: a row exists only where a source pins
-- a person to one performance. show_performers still carries the show-level
-- credit; an appearance with no rows here is known at the show level only.
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

CREATE TABLE resource_performances (
    resource_id TEXT NOT NULL REFERENCES resources (resource_id) ON DELETE CASCADE,
    performance_id TEXT NOT NULL REFERENCES performances (performance_id) ON DELETE CASCADE,
    relationship_type TEXT NOT NULL,
    notes TEXT,
    PRIMARY KEY (resource_id, performance_id, relationship_type)
);

CREATE INDEX resource_performances_performance_id_idx ON resource_performances (performance_id);

CREATE TABLE show_links (
    show_link_id TEXT PRIMARY KEY,
    show_id TEXT NOT NULL REFERENCES shows (show_id) ON DELETE CASCADE,
    platform TEXT NOT NULL,
    link_type TEXT NOT NULL,
    url TEXT NOT NULL,
    title TEXT,
    is_official TEXT NOT NULL CHECK (is_official IN ('true', 'false')) DEFAULT 'false',
    notes TEXT,
    UNIQUE (show_id, platform, url)
);

CREATE INDEX show_links_show_id_idx ON show_links (show_id);

CREATE TABLE performance_links (
    performance_link_id TEXT PRIMARY KEY,
    performance_id TEXT NOT NULL REFERENCES performances (performance_id) ON DELETE CASCADE,
    platform TEXT NOT NULL,
    link_type TEXT NOT NULL,
    url TEXT NOT NULL,
    title TEXT,
    start_seconds INTEGER,
    duration_seconds INTEGER,
    is_official TEXT NOT NULL CHECK (is_official IN ('true', 'false')) DEFAULT 'false',
    notes TEXT,
    UNIQUE (performance_id, platform, url),
    CHECK (start_seconds IS NULL OR start_seconds >= 0),
    CHECK (duration_seconds IS NULL OR duration_seconds >= 0)
);

CREATE INDEX performance_links_performance_id_idx ON performance_links (performance_id);

CREATE TABLE official_releases (
    release_id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    artist_name TEXT,
    -- Text, not DATE: MusicBrainz sometimes knows only a year ("1972") or a
    -- year-month ("1972-05"), and a SQL date column cannot hold a partial
    -- value without inventing a day. release_date stores exactly what is
    -- known, at whatever precision that is; a full day is a plain ISO date
    -- ("1970-11-01"). ISO 8601 strings of any of these precisions still sort
    -- and compare correctly as plain text.
    release_date TEXT,
    release_type TEXT,
    spotify_album_url TEXT,
    source_url TEXT NOT NULL,
    notes TEXT,
    CHECK (release_type IN ('studio', 'live', 'compilation', 'single'))
);

CREATE TABLE official_release_tracks (
    release_id TEXT NOT NULL REFERENCES official_releases (release_id) ON DELETE CASCADE,
    track_number INTEGER NOT NULL,
    performance_id TEXT REFERENCES performances (performance_id) ON DELETE SET NULL,
    song_id TEXT REFERENCES songs (song_id) ON DELETE SET NULL,
    track_title TEXT NOT NULL,
    duration_seconds INTEGER,
    spotify_track_url TEXT,
    notes TEXT,
    PRIMARY KEY (release_id, track_number),
    CHECK (track_number > 0),
    CHECK (duration_seconds IS NULL OR duration_seconds >= 0)
);

CREATE INDEX official_release_tracks_song_id_idx
    ON official_release_tracks (song_id);
CREATE INDEX official_release_tracks_performance_id_idx ON official_release_tracks (performance_id);

CREATE TABLE release_personnel (
    release_id TEXT NOT NULL REFERENCES official_releases (release_id) ON DELETE CASCADE,
    person_id TEXT NOT NULL REFERENCES people (person_id) ON DELETE CASCADE,
    role TEXT NOT NULL,
    instrument TEXT NOT NULL,
    notes TEXT,
    PRIMARY KEY (release_id, person_id, role, instrument)
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

CREATE INDEX song_arrangements_song_id_idx ON song_arrangements (song_id);
CREATE INDEX song_arrangements_performance_id_idx ON song_arrangements (performance_id);

-- An arrangement must describe the same song as its source resource and,
-- when present, its performance-specific context.
CREATE TRIGGER song_arrangements_same_song
BEFORE INSERT ON song_arrangements
FOR EACH ROW
WHEN NOT EXISTS (
        SELECT 1 FROM resource_songs rs
        WHERE rs.resource_id = NEW.resource_id AND rs.song_id = NEW.song_id
    )
    OR (
        NEW.performance_id IS NOT NULL AND NOT EXISTS (
            SELECT 1 FROM performances p
            WHERE p.performance_id = NEW.performance_id AND p.song_id = NEW.song_id
        )
    )
BEGIN
    SELECT RAISE(ABORT, 'arrangement has a resource or performance for a different song');
END;

CREATE TABLE arrangement_chord_sections (
    arrangement_id TEXT NOT NULL REFERENCES song_arrangements (arrangement_id) ON DELETE CASCADE,
    section_position INTEGER NOT NULL,
    section_label TEXT NOT NULL,
    progression TEXT NOT NULL,
    notes TEXT,
    PRIMARY KEY (arrangement_id, section_position),
    CHECK (section_position > 0)
);

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

CREATE UNIQUE INDEX recordings_shnid_unique
    ON recordings (shnid)
    WHERE shnid IS NOT NULL;

CREATE UNIQUE INDEX recordings_archive_identifier_unique
    ON recordings (archive_identifier)
    WHERE archive_identifier IS NOT NULL;

CREATE INDEX recordings_show_id_idx ON recordings (show_id);
CREATE INDEX recordings_source_type_idx ON recordings (source_type);
CREATE INDEX recordings_show_source_type_idx ON recordings (show_id, source_type);

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

CREATE INDEX performance_recordings_recording_track_idx
    ON performance_recordings (recording_id, track_number);

-- A recording source belongs to one show, so its mapped performances must too.
CREATE TRIGGER performance_recordings_same_show
BEFORE INSERT ON performance_recordings
FOR EACH ROW
WHEN NOT EXISTS (
    SELECT 1 FROM performances p
    JOIN recordings r ON r.recording_id = NEW.recording_id
    WHERE p.performance_id = NEW.performance_id AND p.show_id = r.show_id
)
BEGIN
    SELECT RAISE(ABORT, 'performance and recording belong to different shows');
END;

-- Selection lists preserve distinct recognition signals (for example, an
-- official curator's choices, a critic list, or a dated fan vote) rather than
-- collapsing them into one opaque score. Every list is backed by a resource.
CREATE TABLE selection_lists (
    selection_list_id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    selection_type TEXT NOT NULL,
    selector_name TEXT,
    source_resource_id TEXT NOT NULL REFERENCES resources (resource_id)
        DEFERRABLE INITIALLY DEFERRED,
    published_date TEXT,
    retrieved_at TEXT,
    notes TEXT
);

CREATE INDEX selection_lists_source_resource_idx
    ON selection_lists (source_resource_id);

CREATE TABLE selection_entries (
    selection_entry_id TEXT PRIMARY KEY,
    selection_list_id TEXT NOT NULL REFERENCES selection_lists (selection_list_id) ON DELETE CASCADE,
    entry_position INTEGER,
    rank INTEGER,
    vote_count INTEGER,
    score REAL,
    show_id TEXT REFERENCES shows (show_id) DEFERRABLE INITIALLY DEFERRED,
    performance_id TEXT REFERENCES performances (performance_id) DEFERRABLE INITIALLY DEFERRED,
    song_id TEXT REFERENCES songs (song_id) DEFERRABLE INITIALLY DEFERRED,
    release_id TEXT REFERENCES official_releases (release_id) DEFERRABLE INITIALLY DEFERRED,
    recording_id TEXT REFERENCES recordings (recording_id) DEFERRABLE INITIALLY DEFERRED,
    source_label TEXT,
    notes TEXT,
    CHECK (entry_position IS NULL OR entry_position > 0),
    CHECK (rank IS NULL OR rank > 0),
    CHECK (vote_count IS NULL OR vote_count >= 0),
    CHECK (((show_id IS NOT NULL) + (performance_id IS NOT NULL) + (song_id IS NOT NULL) + (release_id IS NOT NULL) + (recording_id IS NOT NULL)) = 1)
);

CREATE INDEX selection_entries_list_order_idx
    ON selection_entries (selection_list_id, entry_position);
CREATE UNIQUE INDEX selection_entries_list_show_unique
    ON selection_entries (show_id, selection_list_id) WHERE show_id IS NOT NULL;
CREATE UNIQUE INDEX selection_entries_list_performance_unique
    ON selection_entries (performance_id, selection_list_id) WHERE performance_id IS NOT NULL;
CREATE UNIQUE INDEX selection_entries_list_song_unique
    ON selection_entries (song_id, selection_list_id) WHERE song_id IS NOT NULL;
CREATE UNIQUE INDEX selection_entries_list_release_unique
    ON selection_entries (release_id, selection_list_id) WHERE release_id IS NOT NULL;
CREATE UNIQUE INDEX selection_entries_list_recording_unique
    ON selection_entries (recording_id, selection_list_id) WHERE recording_id IS NOT NULL;

-- The full reviewed evidence packet is stored separately from normalized list
-- entries so held or ambiguous signals remain available to the model without
-- forcing an unsafe single-entity resolution.
CREATE TABLE selection_evidence (
    selection_evidence_id TEXT PRIMARY KEY,
    source_resource_id TEXT NOT NULL REFERENCES resources (resource_id)
        DEFERRABLE INITIALLY DEFERRED,
    selection_list_id TEXT REFERENCES selection_lists (selection_list_id)
        DEFERRABLE INITIALLY DEFERRED,
    signal_type TEXT NOT NULL,
    resolution_state TEXT NOT NULL,
    payload TEXT NOT NULL,
    CHECK (json_type(payload) = 'object')
);

CREATE INDEX selection_evidence_source_resource_idx
    ON selection_evidence (source_resource_id);
CREATE INDEX selection_evidence_list_idx
    ON selection_evidence (selection_list_id);

-- Catalog views for query_catalog: each pre-joins what set questions usually
-- need, so most queries are one table with WHERE, GROUP BY and ORDER BY.
-- year is the integer year of show_date.

CREATE VIEW show_facts AS
SELECT s.show_id, s.show_date, CAST(substr(s.show_date, 1, 4) AS INTEGER) AS year,
       s.venue_id, v.name AS venue_name, v.city, v.state_region, v.country,
       s.tour_name, s.event_name,
       (SELECT COUNT(*) FROM performances p WHERE p.show_id = s.show_id) AS performance_count
FROM shows s
LEFT JOIN venues v ON v.venue_id = s.venue_id;

CREATE VIEW performance_facts AS
SELECT p.performance_id, p.song_id, so.title AS song_title, p.show_id, s.show_date,
       CAST(substr(s.show_date, 1, 4) AS INTEGER) AS year,
       s.venue_id, v.name AS venue_name, v.city, s.tour_name,
       p.set_number, p.set_label, p.position_in_set, p.encore, p.segue_into_next
FROM performances p
JOIN shows s ON s.show_id = p.show_id
LEFT JOIN songs so ON so.song_id = p.song_id
LEFT JOIN venues v ON v.venue_id = s.venue_id;

CREATE VIEW release_track_facts AS
SELECT t.release_id, r.title AS release_title, r.release_type, r.release_date,
       t.track_number, t.track_title,
       COALESCE(t.song_id, p.song_id) AS song_id, so.title AS song_title,
       t.performance_id, p.show_id, s.show_date,
       CAST(substr(s.show_date, 1, 4) AS INTEGER) AS year,
       s.venue_id, v.name AS venue_name, v.city
FROM official_release_tracks t
JOIN official_releases r ON r.release_id = t.release_id
LEFT JOIN performances p ON p.performance_id = t.performance_id
LEFT JOIN songs so ON so.song_id = COALESCE(t.song_id, p.song_id)
LEFT JOIN shows s ON s.show_id = p.show_id
LEFT JOIN venues v ON v.venue_id = s.venue_id;

CREATE VIEW guest_appearances AS
SELECT sp.show_id, s.show_date, CAST(substr(s.show_date, 1, 4) AS INTEGER) AS year,
       sp.person_id, pe.name AS person_name, sp.instrument, v.name AS venue_name, v.city
FROM show_performers sp
JOIN shows s ON s.show_id = sp.show_id
LEFT JOIN people pe ON pe.person_id = sp.person_id
LEFT JOIN venues v ON v.venue_id = s.venue_id
WHERE sp.role = 'guest';
