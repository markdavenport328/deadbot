-- official_releases.release_date was a SQL date, so a MusicBrainz release
-- group that gives only a year ("1972") or a year-month ("1972-05") could
-- not be stored as-is; the importer blanked those 24 studio albums rather
-- than invent a day. release_date now holds exactly what is known, at
-- whatever precision that is. Nothing else changes: ISO 8601 date strings
-- of mixed precision still sort and compare correctly as plain text, and
-- the 294 existing rows already carry full dates or are already blank, so
-- this widens the column without rewriting any of their values.
BEGIN;

ALTER TABLE official_releases
    ALTER COLUMN release_date TYPE TEXT;

UPDATE deadbot_schema_metadata SET schema_version = 6;

COMMIT;
