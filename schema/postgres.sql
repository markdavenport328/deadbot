-- Deadbot canonical domain schema.
-- This file is designed to be rebuilt entirely from data/canonical CSV files.
-- Future semantic-search tables (for example, text chunks and embeddings using
-- pgvector) belong alongside this core model, not in the canonical entity tables.

BEGIN;

CREATE TABLE deadbot_schema_metadata (
    schema_version INTEGER PRIMARY KEY,
    applied_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CHECK (schema_version > 0)
);

INSERT INTO deadbot_schema_metadata (schema_version) VALUES (3);

-- Reviewed acquisition contracts. These describe adapter boundaries and
-- policy; they do not themselves perform network access.
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

-- Immutable retrieval evidence, including failed or blocked attempts.
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

-- A snapshot is a content-addressed manifest of the exact reviewed CSV files
-- used for an import. It is the canonical input revision cited by derived
-- observations; importing a later snapshot never mutates this record.
CREATE TABLE canonical_snapshots (
    snapshot_id TEXT PRIMARY KEY,
    manifest JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CHECK (snapshot_id ~ '^sha256:[0-9a-f]{64}$'),
    CHECK (jsonb_typeof(manifest) = 'object'),
    CHECK (manifest ? 'format'),
    CHECK (manifest ? 'files')
);

-- This append-only ledger records each successful import attempt and whether
-- it was a clean bootstrap/rebuild or a non-destructive merge. A merge must
-- not be interpreted as proof that the operational projection is an exact
-- mirror of its listed snapshot.
CREATE TABLE canonical_imports (
    import_id UUID PRIMARY KEY,
    snapshot_id TEXT NOT NULL REFERENCES canonical_snapshots (snapshot_id) ON DELETE RESTRICT,
    import_mode TEXT NOT NULL,
    imported_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    table_results JSONB NOT NULL,
    CHECK (import_mode IN ('bootstrap', 'rebuild', 'merge')),
    CHECK (jsonb_typeof(table_results) = 'object')
);

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
    show_date DATE NOT NULL,
    venue_id TEXT NOT NULL REFERENCES venues (venue_id),
    tour_name TEXT,
    event_name TEXT,
    notes TEXT,
    source_key TEXT,
    source_record_id TEXT
);

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

-- Forward-looking enrichment tables. These are operational PostgreSQL tables,
-- not additional canonical CSVs yet. They keep collected evidence separate
-- from reproducible calculations and model-written presentation.

-- A release can contain a complete show, part of a show, or only one or more
-- represented performances. Keep this relationship explicit instead of
-- inferring complete-show coverage from the presence of a release track.
CREATE TABLE release_shows (
    release_id TEXT NOT NULL REFERENCES official_releases (release_id)
        DEFERRABLE INITIALLY DEFERRED,
    show_id TEXT NOT NULL REFERENCES shows (show_id)
        DEFERRABLE INITIALLY DEFERRED,
    coverage_type TEXT NOT NULL,
    evidence_resource_id TEXT REFERENCES resources (resource_id)
        DEFERRABLE INITIALLY DEFERRED,
    notes TEXT,
    PRIMARY KEY (release_id, show_id),
    CHECK (coverage_type IN ('complete', 'partial', 'represented', 'unknown'))
);

-- The legacy performance_id on official_release_tracks preserves the current
-- CSV shape. New imports should use this bridge when a track contains several
-- performances or one performance spans several tracks.
CREATE TABLE official_release_track_performances (
    release_id TEXT NOT NULL,
    track_number INTEGER NOT NULL,
    segment_position INTEGER NOT NULL,
    performance_id TEXT NOT NULL REFERENCES performances (performance_id)
        DEFERRABLE INITIALLY DEFERRED,
    start_seconds INTEGER,
    duration_seconds INTEGER,
    notes TEXT,
    PRIMARY KEY (release_id, track_number, segment_position),
    FOREIGN KEY (release_id, track_number)
        REFERENCES official_release_tracks (release_id, track_number)
        DEFERRABLE INITIALLY DEFERRED,
    UNIQUE (release_id, track_number, performance_id),
    CHECK (segment_position > 0),
    CHECK (start_seconds IS NULL OR start_seconds >= 0),
    CHECK (duration_seconds IS NULL OR duration_seconds >= 0)
);

-- A mapped release segment must be covered by an explicit release/show row.
-- This prevents a partial track mapping from being presented as an unqualified
-- release relationship and ensures the coverage label is available to queries.
CREATE FUNCTION check_release_track_performance_show()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM performances p
        JOIN release_shows rs
          ON rs.release_id = NEW.release_id
         AND rs.show_id = p.show_id
        WHERE p.performance_id = NEW.performance_id
    ) THEN
        RAISE EXCEPTION 'release % has no show-coverage row for performance %',
            NEW.release_id, NEW.performance_id;
    END IF;
    RETURN NEW;
END;
$$;

CREATE TRIGGER official_release_track_performances_covered_show
BEFORE INSERT OR UPDATE OF release_id, performance_id
ON official_release_track_performances
FOR EACH ROW EXECUTE FUNCTION check_release_track_performance_show();

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
    published_date DATE,
    retrieved_at TIMESTAMPTZ,
    notes TEXT
);

CREATE TABLE selection_entries (
    selection_entry_id TEXT PRIMARY KEY,
    selection_list_id TEXT NOT NULL REFERENCES selection_lists (selection_list_id) ON DELETE CASCADE,
    entry_position INTEGER,
    rank INTEGER,
    vote_count INTEGER,
    score NUMERIC,
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
    CHECK (num_nonnulls(show_id, performance_id, song_id, release_id, recording_id) = 1)
);

-- Claims are concise, attributed source assertions. They are not promoted to
-- canonical facts merely because they have been collected.
CREATE TABLE claims (
    claim_id TEXT PRIMARY KEY,
    claim_type TEXT NOT NULL,
    claim_text TEXT NOT NULL,
    source_resource_id TEXT NOT NULL REFERENCES resources (resource_id)
        DEFERRABLE INITIALLY DEFERRED,
    attributed_to TEXT,
    evidence_locator TEXT,
    claim_scope TEXT,
    review_status TEXT NOT NULL DEFAULT 'unreviewed',
    reviewed_at TIMESTAMPTZ,
    notes TEXT,
    CHECK (review_status IN ('unreviewed', 'reviewed', 'rejected')),
    CHECK (reviewed_at IS NULL OR review_status <> 'unreviewed')
);

-- Typed nullable foreign keys retain referential integrity for a relationship
-- that may point at any major domain entity. Exactly one target is required.
CREATE TABLE claim_entities (
    claim_entity_id TEXT PRIMARY KEY,
    claim_id TEXT NOT NULL REFERENCES claims (claim_id) ON DELETE CASCADE,
    relationship_type TEXT NOT NULL,
    person_id TEXT REFERENCES people (person_id) DEFERRABLE INITIALLY DEFERRED,
    song_id TEXT REFERENCES songs (song_id) DEFERRABLE INITIALLY DEFERRED,
    venue_id TEXT REFERENCES venues (venue_id) DEFERRABLE INITIALLY DEFERRED,
    show_id TEXT REFERENCES shows (show_id) DEFERRABLE INITIALLY DEFERRED,
    performance_id TEXT REFERENCES performances (performance_id) DEFERRABLE INITIALLY DEFERRED,
    recording_id TEXT REFERENCES recordings (recording_id) DEFERRABLE INITIALLY DEFERRED,
    release_id TEXT REFERENCES official_releases (release_id) DEFERRABLE INITIALLY DEFERRED,
    equipment_id TEXT REFERENCES equipment (equipment_id) DEFERRABLE INITIALLY DEFERRED,
    CHECK (
        num_nonnulls(
            person_id,
            song_id,
            venue_id,
            show_id,
            performance_id,
            recording_id,
            release_id,
            equipment_id
        ) = 1
    )
);

-- Derived observations contain structured, reproducible calculation output;
-- the model turns that output into prose at request time. observation_key is
-- the stable logical observation, while each row is a version tied to both a
-- calculation version and a canonical input revision.
CREATE TABLE derived_observations (
    observation_id TEXT PRIMARY KEY,
    observation_key TEXT NOT NULL,
    observation_type TEXT NOT NULL,
    calculation_version TEXT NOT NULL,
    input_revision TEXT NOT NULL,
    computed_at TIMESTAMPTZ NOT NULL,
    coverage_start_date DATE,
    coverage_end_date DATE,
    coverage_description TEXT NOT NULL,
    result JSONB NOT NULL,
    is_current BOOLEAN NOT NULL DEFAULT TRUE,
    supersedes_observation_id TEXT REFERENCES derived_observations (observation_id) ON DELETE SET NULL,
    notes TEXT,
    UNIQUE (observation_key, calculation_version, input_revision),
    CHECK (coverage_end_date IS NULL OR coverage_start_date IS NULL OR coverage_end_date >= coverage_start_date),
    CHECK (jsonb_typeof(result) = 'object'),
    CHECK (btrim(observation_key) <> ''),
    CHECK (btrim(calculation_version) <> ''),
    CHECK (btrim(input_revision) <> ''),
    CHECK (btrim(coverage_description) <> ''),
    CHECK (supersedes_observation_id IS NULL OR supersedes_observation_id <> observation_id)
);

-- New installations require every observation input revision to name an
-- immutable canonical snapshot. The v1 → v2 migration installs this same
-- constraint as NOT VALID so historical rows remain readable.
ALTER TABLE derived_observations
    ADD CONSTRAINT derived_observations_input_revision_snapshot_fkey
    FOREIGN KEY (input_revision) REFERENCES canonical_snapshots (snapshot_id)
    DEFERRABLE INITIALLY DEFERRED;

CREATE FUNCTION check_observation_supersedes_same_key()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
    IF NEW.supersedes_observation_id IS NOT NULL AND NOT EXISTS (
        SELECT 1
        FROM derived_observations previous
        WHERE previous.observation_id = NEW.supersedes_observation_id
          AND previous.observation_key = NEW.observation_key
    ) THEN
        RAISE EXCEPTION 'observation % supersedes a different observation key',
            NEW.observation_id;
    END IF;
    RETURN NEW;
END;
$$;

CREATE TRIGGER derived_observations_same_superseded_key
BEFORE INSERT OR UPDATE OF observation_key, supersedes_observation_id
ON derived_observations
FOR EACH ROW EXECUTE FUNCTION check_observation_supersedes_same_key();

CREATE TABLE observation_entities (
    observation_entity_id TEXT PRIMARY KEY,
    observation_id TEXT NOT NULL REFERENCES derived_observations (observation_id) ON DELETE CASCADE,
    relationship_type TEXT NOT NULL,
    person_id TEXT REFERENCES people (person_id) DEFERRABLE INITIALLY DEFERRED,
    song_id TEXT REFERENCES songs (song_id) DEFERRABLE INITIALLY DEFERRED,
    venue_id TEXT REFERENCES venues (venue_id) DEFERRABLE INITIALLY DEFERRED,
    show_id TEXT REFERENCES shows (show_id) DEFERRABLE INITIALLY DEFERRED,
    performance_id TEXT REFERENCES performances (performance_id) DEFERRABLE INITIALLY DEFERRED,
    recording_id TEXT REFERENCES recordings (recording_id) DEFERRABLE INITIALLY DEFERRED,
    release_id TEXT REFERENCES official_releases (release_id) DEFERRABLE INITIALLY DEFERRED,
    equipment_id TEXT REFERENCES equipment (equipment_id) DEFERRABLE INITIALLY DEFERRED,
    claim_id TEXT REFERENCES claims (claim_id) ON DELETE CASCADE,
    CHECK (
        num_nonnulls(
            person_id,
            song_id,
            venue_id,
            show_id,
            performance_id,
            recording_id,
            release_id,
            equipment_id,
            claim_id
        ) = 1
    )
);

CREATE TABLE observation_resources (
    observation_id TEXT NOT NULL REFERENCES derived_observations (observation_id) ON DELETE CASCADE,
    resource_id TEXT NOT NULL REFERENCES resources (resource_id)
        DEFERRABLE INITIALLY DEFERRED,
    relationship_type TEXT NOT NULL,
    notes TEXT,
    PRIMARY KEY (observation_id, resource_id, relationship_type)
);

CREATE UNIQUE INDEX recordings_shnid_unique
    ON recordings (shnid)
    WHERE shnid IS NOT NULL;

CREATE UNIQUE INDEX recordings_archive_identifier_unique
    ON recordings (archive_identifier)
    WHERE archive_identifier IS NOT NULL;

CREATE INDEX shows_venue_id_idx ON shows (venue_id);
CREATE INDEX shows_show_date_idx ON shows (show_date);
CREATE INDEX shows_source_record_idx ON shows (source_key, source_record_id);
CREATE INDEX performances_show_order_idx
    ON performances (show_id, set_number, position_in_set);
CREATE INDEX performances_song_id_idx ON performances (song_id);
CREATE INDEX performances_song_show_idx ON performances (song_id, show_id);
CREATE INDEX performances_source_record_idx
    ON performances (source_key, source_record_id);
CREATE INDEX show_equipment_equipment_id_idx ON show_equipment (equipment_id);
CREATE INDEX show_equipment_claim_id_idx ON show_equipment (claim_id);
CREATE INDEX show_links_show_id_idx ON show_links (show_id);
CREATE INDEX performance_links_performance_id_idx ON performance_links (performance_id);
CREATE INDEX official_release_tracks_performance_id_idx ON official_release_tracks (performance_id);
CREATE INDEX recordings_show_id_idx ON recordings (show_id);
CREATE INDEX recordings_source_type_idx ON recordings (source_type);
CREATE INDEX recordings_show_source_type_idx ON recordings (show_id, source_type);
CREATE INDEX performance_recordings_recording_track_idx
    ON performance_recordings (recording_id, track_number);
CREATE INDEX song_writers_person_id_idx ON song_writers (person_id);
CREATE INDEX resource_songs_song_id_idx ON resource_songs (song_id);
CREATE INDEX resource_shows_show_id_idx ON resource_shows (show_id);
CREATE INDEX resource_performances_performance_id_idx ON resource_performances (performance_id);
CREATE INDEX song_arrangements_song_id_idx ON song_arrangements (song_id);
CREATE INDEX song_arrangements_performance_id_idx ON song_arrangements (performance_id);
CREATE INDEX show_performers_person_id_idx ON show_performers (person_id);
CREATE INDEX show_performers_source_record_idx
    ON show_performers (source_key, source_record_id);
CREATE INDEX release_shows_show_id_idx ON release_shows (show_id);
CREATE INDEX release_shows_coverage_type_idx ON release_shows (coverage_type);
CREATE INDEX official_release_track_performances_performance_idx
    ON official_release_track_performances (performance_id);
CREATE INDEX selection_lists_source_resource_idx
    ON selection_lists (source_resource_id);
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
CREATE INDEX claims_source_resource_idx ON claims (source_resource_id);
CREATE INDEX claims_type_review_status_idx ON claims (claim_type, review_status);
CREATE INDEX claim_entities_claim_id_idx ON claim_entities (claim_id);
CREATE UNIQUE INDEX claim_entities_person_unique
    ON claim_entities (person_id, claim_id, relationship_type) WHERE person_id IS NOT NULL;
CREATE UNIQUE INDEX claim_entities_song_unique
    ON claim_entities (song_id, claim_id, relationship_type) WHERE song_id IS NOT NULL;
CREATE UNIQUE INDEX claim_entities_venue_unique
    ON claim_entities (venue_id, claim_id, relationship_type) WHERE venue_id IS NOT NULL;
CREATE UNIQUE INDEX claim_entities_show_unique
    ON claim_entities (show_id, claim_id, relationship_type) WHERE show_id IS NOT NULL;
CREATE UNIQUE INDEX claim_entities_performance_unique
    ON claim_entities (performance_id, claim_id, relationship_type) WHERE performance_id IS NOT NULL;
CREATE UNIQUE INDEX claim_entities_recording_unique
    ON claim_entities (recording_id, claim_id, relationship_type) WHERE recording_id IS NOT NULL;
CREATE UNIQUE INDEX claim_entities_release_unique
    ON claim_entities (release_id, claim_id, relationship_type) WHERE release_id IS NOT NULL;
CREATE UNIQUE INDEX claim_entities_equipment_unique
    ON claim_entities (equipment_id, claim_id, relationship_type) WHERE equipment_id IS NOT NULL;
CREATE UNIQUE INDEX derived_observations_one_current_per_key
    ON derived_observations (observation_key) WHERE is_current;
CREATE INDEX derived_observations_type_current_idx
    ON derived_observations (observation_type, is_current);
CREATE INDEX observation_entities_observation_id_idx
    ON observation_entities (observation_id);
CREATE UNIQUE INDEX observation_entities_person_unique
    ON observation_entities (person_id, observation_id, relationship_type) WHERE person_id IS NOT NULL;
CREATE UNIQUE INDEX observation_entities_song_unique
    ON observation_entities (song_id, observation_id, relationship_type) WHERE song_id IS NOT NULL;
CREATE UNIQUE INDEX observation_entities_venue_unique
    ON observation_entities (venue_id, observation_id, relationship_type) WHERE venue_id IS NOT NULL;
CREATE UNIQUE INDEX observation_entities_show_unique
    ON observation_entities (show_id, observation_id, relationship_type) WHERE show_id IS NOT NULL;
CREATE UNIQUE INDEX observation_entities_performance_unique
    ON observation_entities (performance_id, observation_id, relationship_type) WHERE performance_id IS NOT NULL;
CREATE UNIQUE INDEX observation_entities_recording_unique
    ON observation_entities (recording_id, observation_id, relationship_type) WHERE recording_id IS NOT NULL;
CREATE UNIQUE INDEX observation_entities_release_unique
    ON observation_entities (release_id, observation_id, relationship_type) WHERE release_id IS NOT NULL;
CREATE UNIQUE INDEX observation_entities_equipment_unique
    ON observation_entities (equipment_id, observation_id, relationship_type) WHERE equipment_id IS NOT NULL;
CREATE UNIQUE INDEX observation_entities_claim_unique
    ON observation_entities (claim_id, observation_id, relationship_type) WHERE claim_id IS NOT NULL;
CREATE INDEX observation_resources_resource_id_idx
    ON observation_resources (resource_id);
CREATE INDEX canonical_imports_snapshot_id_idx ON canonical_imports (snapshot_id);
CREATE INDEX source_snapshots_source_id_idx ON source_snapshots (source_id);
CREATE INDEX source_snapshots_url_retrieved_idx
    ON source_snapshots (normalized_url, retrieved_at DESC);

COMMIT;
