-- The metro area a fan names a venue by: Red Rocks is Denver, Rosemont and
-- Alpine Valley are Chicago, Nassau and the Meadowlands are New York. Any other
-- venue's metro area is its own city. Assigned by scripts/assign_metro_areas.py.
BEGIN;

ALTER TABLE venues ADD COLUMN metro_area TEXT;

UPDATE deadbot_schema_metadata SET schema_version = 11;

COMMIT;
