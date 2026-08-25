# Data directories

`raw/` holds collected records exactly enough to preserve what a source supplied. `canonical/` holds the normalized, stable entities and relationships that Deadbot uses as its initial source of truth.

The path between them is intentional:

```text
source record → raw JSONL → normalization → canonical CSV → PostgreSQL
```

No audio belongs here. Recordings are represented by source metadata, lineage, identifiers, and resolvable URLs.
