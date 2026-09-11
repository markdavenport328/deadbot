# Collection status: catalog-wide song writer credits and cover origins

Pass date: 2026-09-11. Sources: Dead.net song pages (JSON-in-HTML editorial
credit fields) and MusicBrainz's `/ws/2/work` search (JSON web service).

## What was done

Before this pass, `data/canonical/song_writers.csv` covered only the 174 songs
performed in 1970-1972 (`data/raw/songs/{deadnet-song-credits,musicbrainz-song-works}-19{70,71,72}.jsonl`).
The other 262 of the 436 canonical songs had never been attempted against
either source.

1. **Generalized both collectors** (`scripts/collect/fetch_deadnet_song_credits.py`,
   `scripts/collect/fetch_musicbrainz_song_works.py`) from a `year` positional
   argument to a catalog-wide default: each now scans every existing
   `deadnet-song-credits-*.jsonl` / `musicbrainz-song-works-*.jsonl` raw file
   (any year or a prior catalog run) to find songs never attempted, and
   writes new run-specific `*-catalog.jsonl` output. `--year YEAR` reproduces
   the original year-scoped behavior. A prior HTTP 200 is never overwritten
   by a later failure; both scripts flush to a `.partial` file after every
   song so an interrupted run resumes without re-requesting completed work.
   The Dead.net collector was also changed from an 8-way concurrent thread
   pool (which did not respect any rate limit) to serial requests spaced at
   `data/source_registry.json`'s `deadnet-editorial` rate policy
   (`requests_per_minute: 10`, i.e. one request per six seconds).
2. **Verified both hosts were reachable** with one request each
   (`dead.net/song/truckin` → 200, `musicbrainz.org/ws/2/work` → 200) before
   the long run.
3. **Added the MusicBrainz `/ws/2/work` path** to the `musicbrainz-api`
   entry's `search` operation policy in `data/source_registry.json`. It had
   been used by the collector since the 1970-1972 pass but was flagged in
   the registry's own notes as "a separate, unverified gap tracked outside
   this entry"; this pass confirmed the path, method, and existing rate
   policy match the entry and folded it in.
4. **Ran both collectors catalog-wide** against the 262 uncovered songs.
   MusicBrainz's first pass returned many `503`s under sustained load (its
   documented `requests_per_minute: 55` / `min_interval_seconds: 1` evidently
   assumes a longer sustained window than this run's burst); `fetch.py` was
   extended with a bounded retry (up to 3 attempts, backing off
   `retry_after_seconds: 30` from the registry on a 503, immediately on a
   timeout) and a `--retry-errors` mode that re-fetches only the non-200
   entries already recorded in the catalog file, in place. Two retry passes
   brought MusicBrainz to 262/262 resolved.
5. **Wrote `scripts/normalize_song_sources_catalog.py`**, a companion to the
   existing `scripts/normalize_song_sources_1972.py`, to normalize the new
   catalog-wide raw records under the same staged-resolution rules (see
   `docs/collection-methodology.md`):
   - A MusicBrainz work is promoted only when there is exactly one exact
     title-key match, or every exact match agrees on the same credit set;
     exact matches that disagree (a shared title across unrelated works —
     confirmed for "A Day In the Life", whose exact matches split between
     Lennon/McCartney and an unrelated Todd Terry work) are held, never
     promoted.
   - Dead.net's Lyrics By / Music By credit is used as a fallback only when
     MusicBrainz produced no promotable credit.
   - Role mapping: `lyricist`/Lyrics By → `lyrics`, `composer`/Music By →
     `music`, `writer` → `writer`. "Traditional" and "Grateful Dead" credits
     are held as source evidence, not turned into people rows.
   - `people.csv` and `song_writers.csv` are written sorted by their ID
     columns (`person_id`; `song_id, writer_role, person_id`) so a concurrent
     agent's appends merge cleanly. No existing row was reordered in a way
     that lost data — every prior row from both files is still present
     (verified by set comparison against the pre-pass files).
6. **Checked whether any source states an explicit "original artist"** fact
   distinct from a writer/composer credit. A live fetch of the Dead.net
   "Morning Dew" page was inspected field-by-field: it exposes
   `field--name-field-lyrics-by` and `field--name-field-music-by` (both
   "Bonnie Dobson") but no field naming an originating artist or recording
   separately from the writer credit — the closest text is a fan comment
   ("It certainly sounds as if Jerry sings 'mourn' even though the Bonnie
   Dobson original is 'moan'"), which is attributed visitor commentary, not
   structured source metadata, and is not retrieved by the collector.
   Because neither source in this pass names an original artist as a fact
   separate from its writer credit, `songs.csv`'s `original_artist` column
   was left untouched (still blank catalog-wide); promoting a writer credit
   into that field would conflate two facts the methodology keeps separate
   ("a cover's original artist is not necessarily identical to the work's
   registered writer").
7. **Rebuilt `data/editorial/cover-origin-review.csv`** with
   `scripts/build_cover_origin_review.py` now that `song_writers.csv` has
   grown. No row in the file had a human-entered `original_artist`,
   `evidence_url`, or non-"held" `decision` before the rebuild (checked
   first), so nothing was overwritten.
8. **Regenerated two stale derived snapshots** that pytest caught as
   out of sync with the new canonical data: `data/coverage/canonical-spine-baseline.json`
   (`scripts/build_baseline_coverage.py`) and `data/editorial/priority-review-queue.json`'s
   factual `candidate` snapshots (`scripts/refresh_priority_review_coverage.py`).
   Neither script's own selections or editorial priorities changed; only
   their materialized coverage numbers were refreshed to match the current
   `song_writers.csv`. `data/editorial/song-cohort-candidates.csv` was left
   untouched: regenerating it could shift which songs are selected into the
   stratified cohort (`writer_count` is a tie-break key in that script's
   selection, not just a label), which is a larger, separate editorial
   decision outside this pass's scope; the full test suite passes against
   the existing file, so nothing requires touching it now.

## Counts

| Source | Requested | Successful (HTTP 200) | Error | Exact/usable match |
| --- | --- | --- | --- | --- |
| Dead.net (catalog pass) | 262 | 107 | 155 | 105 pages expose a credit field |
| MusicBrainz (catalog pass, after retries) | 262 | 262 | 0 | 233 have at least one exact title-key match |

| Item | Count |
| --- | --- |
| Songs promoted with new canonical writer credit(s) | 162 |
| New `song_writers.csv` rows | 367 |
| New `people.csv` rows (writers not previously in the catalog) | 77 |
| New `resources.csv` rows (Dead.net song pages + MusicBrainz work-search pages) | 365 |
| New `resource_songs.csv` relationship rows | 369 |
| Songs held (no credit promoted) | 100 |
| Songs with a canonical writer credit, catalog-wide (133 pre-existing + 162 new) | 295 of 436 |
| Songs with no writer credit at all, catalog-wide | 141 of 436 |
| `original_artist` values promoted | 0 (no source in this pass states one explicitly; see above) |

Held reasons (this pass's 262 songs only):

| Reason | Count | Meaning |
| --- | --- | --- |
| `ambiguous_musicbrainz_matches` | 68 | More than one exact title-key match on MusicBrainz, disagreeing on credits, and no usable Dead.net fallback; held per the methodology's shared-title rule. |
| `no_deadnet_page_and_no_musicbrainz_exact_match` | 24 | Dead.net page did not resolve (404/no page) and MusicBrainz returned no exact title-key match. Nothing to review yet. |
| `traditional_or_band_credit_only` | 5 | The only named credit available was "Traditional" or "Grateful Dead"; held as source evidence rather than turned into a people row. |
| `no_named_credit_in_either_source` | 2 | At least one source resolved but named no individual (e.g. a role type outside lyricist/composer/writer, or a resolved Dead.net page with `has_credits: false`). |
| `no_deadnet_page` | 1 | Dead.net page did not resolve, but this one had other held evidence (see script output) rather than a clean MusicBrainz miss. |

## Cover-origin review

`data/editorial/cover-origin-review.csv` was rebuilt (not duplicated) from
the current `song_writers.csv`: 305 candidates (164 `non_family_writer`, 141
`no_writer_data`), down from 386 before this pass, since 81 titles that
previously had no writer data (or were not yet distinguishable from a
Dead-family composition) now carry a resolved credit. All rows are still
`decision: held` pending human review — this pass adds writer-credit
evidence, not an `original_artist` determination, per the methodology's rule
that a cover's original artist is a separate fact from its writer credit.

## Validation

- `PYTHONPATH=. pytest -q`: 517 passed, 1 pre-existing failure unrelated to
  this pass (`test_evaluate_cli_exits_non_zero_when_a_case_fails` requires
  `DEADBOT_DATABASE_URL`/a live Postgres connection that isn't part of this
  data pass).
- Row-level set comparison confirmed every pre-existing row in
  `songs.csv`, `song_writers.csv`, `people.csv`, `resources.csv`, and
  `resource_songs.csv` survived the pass unchanged; only new rows were
  added, and `people.csv`/`song_writers.csv` are sorted by ID.
- `people.csv` person_ids and names are unique after the pass (no
  duplicate person created for an existing writer).

## Remaining gaps

- 141 of 436 songs still have no canonical writer credit (`no_writer_data`
  in the review file): either the Dead.net page never resolved or neither
  source named a usable credit.
- 68 songs have MusicBrainz evidence retained but held as ambiguous
  (disagreeing exact-title-key matches); a human with music-catalog
  knowledge could resolve some of these by picking the correct work, but
  that is a review decision, not something this pass automates.
- `original_artist` remains blank for all 436 songs. Filling it needs either
  a source that states an explicit "originally recorded by" fact (not
  currently exposed by either collector) or a human decision recorded in
  `cover-origin-review.csv`.
- `data/editorial/song-cohort-candidates.csv` was intentionally left
  unregenerated (see above); a human may want to decide whether to refresh
  it now that more songs carry writer credits.
