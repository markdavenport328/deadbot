-- Venue geography: canonical latitude/longitude (backed by a reviewed
-- Wikidata match, QID recorded in notes) so get_historical_weather and
-- get_astronomy stop geocoding live on every call for a venue this pass
-- resolved. setting and capacity scope the notable-weather question family
-- to venues where Wikidata states them plainly; see
-- docs/collection-status-venue-geography.md for requested/confident/held
-- counts and docs/collection-methodology.md for why an unmatched venue is
-- left blank rather than backed by a city centroid or a guess.
BEGIN;

ALTER TABLE venues
    ADD COLUMN setting TEXT,
    ADD COLUMN capacity INTEGER,
    ADD CONSTRAINT venues_setting_check CHECK (setting IS NULL OR setting IN ('indoor', 'outdoor')),
    ADD CONSTRAINT venues_capacity_check CHECK (capacity IS NULL OR capacity > 0);

UPDATE deadbot_schema_metadata SET schema_version = 8;

COMMIT;
