# Updating the production catalog

Production serves one SQLite file, built from the CSVs in the deployed
commit. There is no production database to import into and nothing to back
up: the reviewed CSVs in Git are the data, and every deploy rebuilds the file
from them. Updating production means merging a CSV change to `main`.

## What the build does

`python -m deadbot.sqlite_build` reads every canonical CSV and the
selection-evidence review file and validates all of them before it writes
anything: column names, required values, dates, numbers and booleans. It then
loads them into a new file beside the old one, checks every foreign key,
and only then swaps the new file into place. A build that fails leaves the
previous file untouched and says which row or reference broke it.

Nothing is merged and nothing is left over from an earlier build. A row
removed from a CSV is gone from the next build; a corrected row is corrected.

## The procedure

1. **Build and check locally**, from the branch with the CSV change:

   ```bash
   .venv/bin/python -m deadbot.sqlite_build --output build/deadbot.sqlite
   .venv/bin/python -m pytest -q
   .venv/bin/deadbot evaluate
   ```

   The build prints the row count and the input fingerprint. The tests and
   the evaluation read the file it wrote.
2. **Open a pull request.** CI runs the same build, the tests and the
   evaluation against SQLite.
3. **Merge to `main`.** Vercel's build step runs the same build command
   (`vercel.json`) and bundles the file with the function. If the build
   fails, the deploy fails and the previous deployment keeps serving.
4. **Verify.**

   ```bash
   curl https://deadbot-ten.vercel.app/api/health
   ```

   It reports the deployed commit and the show count. Then ask one question
   that touches the new data.
5. **Roll back if needed.** Promote the previous deployment in the Vercel
   dashboard, or revert the commit on `main`. Either way the previous data
   comes back with the previous code, because both live in the commit.

## Stored answers

Answers to repeated questions are keyed by the catalog's input fingerprint
and the deployed commit, so a new build stops serving old answers by itself.
The opening questions are answered again during the Vercel build
(`scripts/warm_answers.py`) and shipped with the deploy.

## Environment

The store needs no configuration. `DEADBOT_SQLITE_PATH` moves the file and is
normally unset. Three variables from the PostgreSQL era are no longer read:
`DEADBOT_DATA_STORE`, `DEADBOT_DATABASE_URL` and `DATABASE_URL`. A value left
in a Vercel environment does no harm, and can be removed when convenient:

```bash
vercel env rm DEADBOT_DATA_STORE production
vercel env rm DEADBOT_DATABASE_URL production
vercel env rm DATABASE_URL production
```
