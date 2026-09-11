# Updating the production database

How to move reviewed canonical data into the production PostgreSQL database
without losing anything. Written 2026-09-08 after reading `deadbot/postgres_import.py`
and the production ledger; update it when the importer changes.

## What the importer actually does

`deadbot db-import` reads every canonical CSV and the selection-evidence
review file, validates all of them **before** opening a database transaction,
computes a content-addressed snapshot id for that exact file set, and then in
**one transaction**:

1. applies any pending schema migrations (`schema/migrations/NNN_*.sql`) when
   the database's `deadbot_schema_metadata.schema_version` is behind the
   importer's `SCHEMA_VERSION`;
2. records the snapshot in `canonical_snapshots`;
3. loads the canonical tables;
4. **replaces** the selection-evidence tables (`selection_evidence`,
   `selection_entries`, `selection_lists`) from
   `data/editorial/selection-evidence-review.json`, every time, in every mode;
5. appends a row to the `canonical_imports` ledger and commits.

Any failure rolls the whole transaction back; the database is left exactly as
it was.

There are two modes, and the difference is the whole safety story:

| Mode | Command | Canonical tables | Use when |
|---|---|---|---|
| **Merge** (default) | `deadbot db-import` | `INSERT … ON CONFLICT DO NOTHING`: new rows are added, existing rows are left as they are, nothing is deleted | Every change in the CSVs is an **addition** (new resources, new relationships, new shows) |
| **Rebuild** | `deadbot db-import --rebuild` | `DELETE FROM` every canonical table (reverse dependency order), then reload from the CSVs | Rows were **changed or removed** in the CSVs and the database must mirror the files |

Merge cannot delete anything, but it also cannot correct a row: a changed
venue name or a fixed date stays wrong in the database until a rebuild.

## What can be deleted, precisely

- **Rebuild deletes every canonical row and reloads from your checkout.** If
  your checkout's CSVs are older than what was last imported, the rebuild
  silently removes whatever the newer import had added. This is the failure
  earlier agents warned about. The guard is the ledger check below: the last
  imported snapshot must be one your checkout descends from.
- **Selection evidence is replaced on every import**, merge or rebuild, from
  the review JSON in your checkout. Same guard applies.
- **Nothing else is touched.** Tables outside the importer's list
  (`claims`, `derived_observations`, `release_shows`,
  `official_release_track_performances`, `source_registry`, the
  `deadbot_response_cache`, the ledgers) are never deleted by the importer.
  Their foreign keys to canonical tables are `NO ACTION`, so if they ever hold
  rows, a rebuild **fails and rolls back** rather than cascading. As of
  2026-09-08 they are all empty.
- The response cache keys on row counts, so an import invalidates cached
  answers by itself; no manual flush.

## Connection

Use the **unpooled** database URL for imports (`DATABASE_URL_UNPOOLED` in
`.env`). The pooled URL goes through a connection pooler that can interfere
with a long single transaction and prepared statements; reads from the app are
fine on it, a 40,000-row import is not.

## The procedure

Run from a checkout of `main` at the commit that is deployed (Vercel deploys
`main`). Never import from a feature branch or a worktree with different CSVs.

1. **Back up.** Neon: create a branch of the production database in the Neon
   console (instant, point-in-time) and name it for the date. Anywhere else:
   `pg_dump "$DATABASE_URL_UNPOOLED" --format=custom --file=deadbot-$(date +%F).dump`.
2. **Preflight, read-only.**
   ```bash
   .venv/bin/deadbot db-import --check --database-url "$DATABASE_URL_UNPOOLED"
   ```
   It prints the installed schema version and pending migrations, the last
   ledger entries, this checkout's snapshot id, and per-table row counts
   (database vs CSV). Read three things:
   - *Pending migrations* are the ones that will run. A table one of them
     creates shows `database_rows: null` and is listed under
     `tables_created_by_pending_migrations`; the check does not try to count
     it. Open each file and
     confirm it is additive (`CREATE TABLE IF NOT EXISTS`, `ADD COLUMN`,
     `ALTER … TYPE`) or that you understand what it changes.
   - *Last import snapshot* should match the snapshot of the `main` commit
     you imported last time. If it is a snapshot you cannot account for,
     stop: someone imported something newer than your checkout, and a
     rebuild would delete it.
   - *Tables where the database has more rows than the CSV* are the rows a
     rebuild would delete. Zero such tables means a rebuild is safe as far
     as row counts can tell. Merge never deletes regardless.
3. **Choose the mode.** `git diff --stat <last-imported-commit>..HEAD -- data/canonical`
   shows only insertions → merge. Any deletions or modifications → rebuild,
   after step 1 and a clean step 2.
4. **Import.**
   ```bash
   .venv/bin/deadbot db-import --database-url "$DATABASE_URL_UNPOOLED"
   ```
   (add `--rebuild` only when step 3 said so). The command prints the
   snapshot id; it must equal the one from step 2.
5. **Verify.** Re-run the `--check`; the database counts now match the CSV
   counts for every table the import touched, and the ledger's newest row is
   yours. Then `curl https://deadbot-ten.vercel.app/api/health` (it reports
   show counts), ask one question that touches the new data, and warm the
   opening questions: `python scripts/warm_answers.py https://deadbot-ten.vercel.app`.
6. **Roll back if needed.** Neon: restore the production branch from the
   branch you made in step 1. Elsewhere: `pg_restore --clean --if-exists
   --dbname "$DATABASE_URL_UNPOOLED" deadbot-<date>.dump`.

## The 2026-09-08 release specifically

- Production ledger before this release: last import was a **rebuild on
  2026-09-08 02:35 UTC** from snapshot `sha256:ce08c7d0…`, which is exactly
  the snapshot of `main` at `cef0c09`. Production therefore holds nothing the
  repository does not.
- Schema: production is at version 6; this release's importer is version 7.
  Migration `007_response_cache.sql` runs inside the import transaction and is
  additive (`CREATE TABLE IF NOT EXISTS deadbot_response_cache`). The app also
  creates that table lazily on its first request, so deploy order does not
  matter.
- Canonical changes on the branch are **insertions only**: `resources.csv`
  +2,397, `resource_shows.csv` +613, `resource_songs.csv` +580 (the blog
  index plus the targeted Dead.net, Deadhead High and GDAO passes). The
  importer's reader validates the branch CSVs (snapshot `sha256:f5a0efe2…`),
  and the selection-evidence file is unchanged. **Use merge.** Expected
  result: resources 311 → 2,708 (the 11 extra rows in production are the
  selection-evidence source rows the importer creates), resource_shows 17 →
  630, resource_songs 299 → 879. Confirm with `db-import --check` before and
  after.
