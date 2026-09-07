-- official_releases.release_date is a SQL date, so a MusicBrainz release
-- group that only gives a year or a year-month cannot be stored as-is.
-- release_date now holds the earliest date consistent with what MusicBrainz
-- knows, and release_date_precision records how much of it is real: 'day'
-- for a full date, 'month' when only year-month was known, 'year' when only
-- the year was known.  A release with no date at all keeps both columns
-- null; nothing is fabricated because the precision travels with the value.
BEGIN;

ALTER TABLE official_releases
    ADD COLUMN release_date_precision TEXT;

ALTER TABLE official_releases
    ADD CONSTRAINT official_releases_release_date_precision_check
    CHECK (release_date_precision IN ('day', 'month', 'year'));

UPDATE deadbot_schema_metadata SET schema_version = 6;

COMMIT;
