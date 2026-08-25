# Future scripts

This directory reserves a deliberately small pipeline surface:

```text
collect/
    source-specific ingestion

normalize/
    entity matching
    stable ID creation
    cleanup and reconciliation

import/
    validation
    canonical CSV → PostgreSQL
```

No collectors or importers are implemented in this phase. When they are added, collectors should preserve raw source records; normalizers should make matching and corrections reviewable; and importers should validate all canonical CSV headers, data types, IDs, foreign keys, and cross-show recording mappings before loading PostgreSQL.

## 1972 pilot collector

`collect/fetch_gdshowsdb_year.py` is the first small collector. It retrieves one public, committed year file from the MIT-licensed `jefmsmit/gdshowsdb` repository through GitHub's Contents API and stores the unparsed API response as one JSONL raw record. It fetches metadata only, never audio, and refuses to overwrite an existing record without `--force`.
