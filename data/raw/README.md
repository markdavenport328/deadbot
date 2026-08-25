# Raw data

Raw data preserves source records before entity matching and cleanup. Files should normally use JSON Lines (NDJSON): one source record per line, allowing a source-specific payload to be retained without forcing every source into one shape.

Example only (not collected data):

```json
{"source":"example-source","retrieved_at":"2026-08-24T12:00:00Z","show_date":"1973-11-11","venue":"Example venue","raw_payload":{"example":"value"}}
```

Raw records should:

- preserve source values and source identifiers;
- include retrieval timestamps where practical;
- retain source-specific fields in the payload;
- not silently normalize names or identifiers;
- preserve enough provenance to trace a canonical assertion back to its source; and
- be regenerable from collection scripts where source terms allow it.

Subdirectories group records by their primary subject. A source record may contain information relevant to more than one canonical entity; preserve it where it was collected rather than splitting or rewriting it prematurely.
