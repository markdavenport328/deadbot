# Canonical data audit — 2026-08-27

This is a point-in-time audit of `data/canonical/*.csv`, the data the runtime
reads through `deadbot/data.py`. Every number below was computed directly from
the current CSVs (via `csv.DictReader`, not `wc -l`, so header rows are already
excluded); the queries are not reproduced here but are straightforward
group-bys and set-membership checks over the files named. Where a number in
this document could be read two ways, both readings are given rather than
picking one silently.

Row counts for every canonical table at audit time:

| Table | Rows |
| --- | ---: |
| shows | 2,358 |
| performances | 39,774 |
| show_performers | 26,265 |
| people | 277 |
| songs | 436 |
| venues | 595 |
| recordings | 17,977 |
| performance_recordings | 16,507 |
| resources | 293 |
| resource_songs | 299 |
| resource_shows | 5 |
| resource_performances | 11 |
| song_writers | 309 |
| song_arrangements | 1 |
| arrangement_chord_sections | 4 |
| equipment | 20 |
| show_equipment | 2,249 |
| official_releases | 1 |
| official_release_tracks | 21 |
| show_links | 1 |
| performance_links | 1 |

## Part 1 — Verified findings

### 1. Coverage shape

Shows, performances, and performer assignments (`show_performers` rows) by
year:

| Year | Shows | Performances | Shows with a performance | Shows with zero performances | show_performers rows | Shows with zero performer rows |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 1965 | 12 | 2 | 2 | 10 | 94 | 2 |
| 1966 | 113 | 228 | 32 | 81 | 1,114 | 3 |
| 1967 | 139 | 201 | 41 | 98 | 1,296 | 13 |
| 1968 | 126 | 529 | 69 | 57 | 1,252 | 22 |
| 1969 | 149 | 1,527 | 124 | 25 | 1,646 | 24 |
| 1970 | 145 | 2,078 | 135 | 10 | 1,478 | 26 |
| 1971 | 81 | 1,793 | 80 | 1 | 830 | 0 |
| 1972 | 86 | 2,229 | 86 | 0 | 938 | 0 |
| 1973 | 72 | 1,884 | 72 | 0 | 730 | 0 |
| 1974 | 40 | 1,059 | 40 | 0 | 447 | 0 |
| 1975 | 4 | 54 | 4 | 0 | 46 | 0 |
| 1976 | 41 | 941 | 41 | 0 | 452 | 0 |
| 1977 | 60 | 1,233 | 60 | 0 | 660 | 0 |
| 1978 | 81 | 1,584 | 81 | 0 | 910 | 0 |
| 1979 | 75 | 1,597 | 75 | 0 | 828 | 0 |
| 1980 | 87 | 2,103 | 87 | 0 | 979 | 0 |
| 1981 | 83 | 1,841 | 83 | 0 | 925 | 0 |
| 1982 | 61 | 1,312 | 61 | 0 | 692 | 0 |
| 1983 | 66 | 1,357 | 66 | 0 | 743 | 0 |
| 1984 | 64 | 1,281 | 64 | 0 | 747 | 0 |
| 1985 | 71 | 1,402 | 71 | 0 | 860 | 0 |
| 1986 | 46 | 879 | 46 | 0 | 591 | 0 |
| 1987 | 85 | 1,693 | 85 | 0 | 1,053 | 0 |
| 1988 | 80 | 1,563 | 80 | 0 | 1,000 | 0 |
| 1989 | 73 | 1,449 | 73 | 0 | 905 | 0 |
| 1990 | 74 | 1,489 | 74 | 0 | 948 | 0 |
| 1991 | 77 | 1,463 | 77 | 0 | 1,061 | 0 |
| 1992 | 55 | 1,011 | 55 | 0 | 672 | 0 |
| 1993 | 81 | 1,544 | 81 | 0 | 911 | 0 |
| 1994 | 84 | 1,584 | 84 | 0 | 933 | 0 |
| 1995 | 47 | 864 | 47 | 0 | 524 | 0 |

Setlist coverage has a clean break at 1971: from 1971 forward every show has
at least one performance row (1971 has exactly one holdout), and from 1972
forward every show also has at least one performer assignment. 1965–1970 is
where the gaps concentrate — 282 of 2,358 shows (12.0%) have zero performance
rows, and all but two of those are in 1965–1970. This lines up with
`docs/development-plan.md`'s account of gdshowsdb source records that
"contain no setlist entries" for the earliest years.

90 shows (3.8% of 2,358) have zero `show_performers` rows — the JerryBase
performer pass covered 2,268 of 2,358 shows, matching the development plan's
own figure. The 90 gaps are concentrated in 1966–1970 (13–26 per year) with a
couple in 1965; nothing later than 1970 is missing a performer assignment.

### 2. Depth asymmetry

293 resources exist. They connect to canonical entities through three link
tables:

| Link table | Rows | Distinct target entities linked |
| --- | ---: | ---: |
| resource_songs | 299 | 174 of 436 songs |
| resource_shows | 5 | 1 of 2,358 shows |
| resource_performances | 11 | 9 of 39,774 performances |

The one show in `resource_shows` and the concentration of `resource_performances`
rows are both Veneta (`gd-1972-08-27`). Counting resources by how directly
they touch Veneta:

- **6 of 293 resources** (2.0%) have a direct `resource_shows` or
  `resource_performances` link to the Veneta show or one of its performances.
- **57 of 293 resources** (19.5%) touch Veneta if a song-level resource
  counts whenever that song was played at Veneta — i.e., a resource attached
  to "Dark Star" also surfaces on the Veneta page because Dark Star was
  played there, even though the resource itself carries no Veneta-specific
  claim.

That gap between 6 and 57 matters for the next question: **how many of the
2,358 shows would compose into a page with any contextual resource or media
link at all?**

- **1 of 2,358 shows** (Veneta itself) has a direct show-level or
  performance-level resource/media link (`resource_shows`, `resource_performances`,
  `show_links`, or `performance_links`).
- **2,071 of 2,358 shows** (87.8%) would surface at least one resource card if
  the composition also pulls in resources attached to any song performed at
  that show — because 174 of 436 songs (39.9%) carry a song-level resource,
  and most shows contain at least one such song.

In other words: nearly every show can show *something*, but only because the
song layer is doing the work. Direct show- or performance-specific
context/media is present for exactly one show in the whole dataset.

`song_arrangements` has **1 row** (a B-key Sugaree arrangement sourced from
RUKIND tab material) with **4** linked `arrangement_chord_sections` rows. The
musician-mode ambition described in the development plan (source-specific
key, capo, tuning, chord sections per arrangement) currently rests on a
single arrangement covering a single song.

`performance_links` has **1 row** (a Promised Land YouTube clip, Veneta) and
`show_links` has **1 row** (the Veneta full-show YouTube upload). Media
linking exists only for the original hand-curated Veneta slice; none of the
86-show 1972 bulk pass or any other year has a show- or performance-level
media link yet.

`official_releases` has 1 row and `official_release_tracks` has 21 rows, all
21 of which map to Veneta performances — this is the Dick's Picks-style
release tied to the original pilot, not a general release catalog.

### 3. Ambiguous dates

`shows.csv` has 2,358 rows across **2,298 distinct `show_date` values**. **60
dates have 2 or more shows** (120 shows total, i.e. 5.1% of all shows). Every
one of those 60 dates falls in 1966–1970 (3 in 1966, 15 in 1967, 14 each in
1968–1970); no date from 1971 onward is ambiguous.

`CanonicalStore.resolve_show` (`deadbot/data.py:74`) tries an exact ID match,
then falls back to matching on `show_date`/`event_name`/`tour_name` and only
returns a row when exactly one match is found. A same-day double booking is
exactly this case, so any tool call that resolves a show by date alone
(`get_show`, `get_performance`, media-link lookup — see `deadbot/tools.py:69,
300, 326, 461`) silently returns "not found" for these 60 dates today, even
though the show(s) exist in canonical data.

Examples:

| Date | Shows | Venues |
| --- | --- | --- |
| 1966-03-03 | gd-1966-03-03-0, gd-1966-03-03-1 | American Institute of Aeronautics and Astronautics Hall, Los Angeles (both) |
| 1966-10-08 | gd-1966-10-08-0, gd-1966-10-08-1 | Mount Tamalpais / Cushing Memorial Amphitheatre, Marin County; Fillmore Auditorium, San Francisco |
| 1967-01-13 | gd-1967-01-13-0, gd-1967-01-13-1 | Berkeley Community Theater; Fillmore Auditorium, San Francisco |
| 1967-04-30 | gd-1967-04-30-0, gd-1967-04-30-1 | The Cheetah, Venice (both — an actual double-show day at one venue) |
| 1967-06-01 | gd-1967-06-01-0, gd-1967-06-01-1 | Tompkins Square Park, New York; Café Au Go Go, New York |

The 1966-03-03 and 1967-04-30 cases show the same venue twice (matinee/evening
or two distinct billed sets); the others are genuinely two different venues
on the same calendar date. Either way, `resolve_show` can't disambiguate by
date text alone.

### 4. Provenance-as-prose

Every canonical row already carries some source citation — the question is
whether it's machine-readable:

| Table | Rows | Rows with any source citation embedded in `notes`/`performance_notes` |
| --- | ---: | ---: |
| shows | 2,358 | 2,358 (100%) — `"Normalized from gdshowsdb show UUID … in github-blob:…"` |
| show_performers | 26,265 | 26,265 (100%) — `"JerryBase source event 19650505-01; raw snapshot jerrybase-1965.jsonl; …"` |
| performances | 39,774 | 39,754 (99.95%) — `"Source song UUID …; source label "…"."`. The 20 rows without it are exactly the 20 original Veneta performances, which predate this convention. |

So, functionally, every row that should have provenance has it — but only as
free text inside a `notes` column. There is no `source_id`, `source_record_id`,
`source_name`, or `retrieved_at` column anywhere in `shows`, `performances`,
or `show_performers`. The UUID, snapshot filename, and blob hash are only
recoverable by regexing prose, per row, per table, with a slightly different
format each time (gdshowsdb UUID + blob hash for shows; JerryBase event ID +
snapshot filename for show_performers; song UUID + source label for
performances). `resources.csv` is the one table that already has a real
column for this (`source_name`, filled for all 293 rows), which is the shape
the other tables should move toward.

This matters more as the corpus grows, for three concrete reasons:

- **The importer needs it.** `docs/development-plan.md` item 6 (CSV →
  PostgreSQL) and `docs/collection-methodology.md`'s validation checklist
  both assume a reviewable, queryable link back to source records. A prose
  blob can't be joined, filtered, or deduplicated by a SQL migration; it has
  to be re-parsed with a bespoke regex per table, and any format drift in a
  future collection pass (a new source, a renamed snapshot file) silently
  breaks that regex instead of raising a validation error.
- **Conflict review needs it.** `docs/provenance-policy.md` requires keeping
  raw values and reviewing a conflict before changing a canonical value. Doing
  that today means grepping notes text for a UUID and manually finding the
  matching raw JSONL line — there's no `source_record_id` to look up directly.
- **It doesn't scale past the current single-primary-source-per-year
  pattern.** Right now each year is dominated by one enumeration source
  (gdshowsdb) and one enrichment source (JerryBase), so a prose citation is
  merely inconvenient. Once a fact type accumulates multiple disagreeing
  sources (which the provenance policy explicitly anticipates), there's no
  column to hold "which source asserted this value and when" per claim.

### 5. Referential integrity

Checked every foreign-key-shaped relationship for orphans (a reference to an
ID that doesn't exist in the parent table). All are clean:

| Relationship | Orphan rows |
| --- | ---: |
| performances.show_id → shows | 0 |
| performances.song_id → songs | 0 |
| show_performers.show_id → shows | 0 |
| show_performers.person_id → people | 0 |
| shows.venue_id → venues | 0 |
| recordings.show_id → shows | 0 |
| performance_recordings.performance_id → performances | 0 |
| performance_recordings.recording_id → recordings | 0 |
| resource_songs.resource_id → resources | 0 |
| resource_songs.song_id → songs | 0 |
| resource_shows.resource_id → resources | 0 |
| resource_shows.show_id → shows | 0 |
| resource_performances.resource_id → resources | 0 |
| resource_performances.performance_id → performances | 0 |
| official_release_tracks.release_id → official_releases | 0 |
| official_release_tracks.performance_id → performances | 0 |
| song_writers.song_id → songs | 0 |
| song_writers.person_id → people | 0 |
| song_arrangements.song_id / performance_id / resource_id | 0 |
| arrangement_chord_sections.arrangement_id → song_arrangements | 0 |
| show_equipment.show_id → shows | 0 |
| show_equipment.equipment_id → equipment | 0 |
| show_links.show_id → shows | 0 |
| performance_links.performance_id → performances | 0 |

No orphans anywhere. This is consistent with a normalization process that
generates internal IDs from a bounded, already-validated show/song/person
baseline rather than free-typing foreign keys — worth confirming holds once a
PostgreSQL importer with real foreign-key constraints exists, but there's
nothing to fix today.

### 6. Songs layer

- 436 songs, all 436 of which have at least one performance (the song table
  is built from the performance baseline, so this is expected, not a finding).
- **303 of 436 songs (69.5%) have no `song_writers` row.** Some of that is
  legitimately outside scope (traditional numbers, jams, band-credited
  pieces per `docs/collection-methodology.md`'s guidance not to invent a
  writer role). But the gap also includes straightforward Hunter/Garcia
  originals with well-documented credits — e.g. "Alabama Getaway" and
  "Althea" have no `song_writers` row — so this isn't purely a "traditional
  works don't get a writer row by design" situation; it includes originals
  that simply haven't had a credit-enrichment pass yet.
- 309 `song_writers` rows cover the 133 songs that do have writer data —
  about 2.3 rows per credited song, split `music` (127), `lyrics` (96), and
  `writer` (86), i.e. the role-preserving convention from
  `docs/collection-methodology.md` is actually being followed where credits
  exist.
- **262 of 436 songs (60.1%) have performances but no `resource_songs`
  row** — no linked interview, article, tab, or media context of any kind.
- No duplicate or near-duplicate titles or slugs (checked exact
  case-insensitive match, and punctuation-insensitive normalization). The
  song catalog is clean on this axis.

### 7. Recordings layer

- 17,977 `recordings` rows, covering **1,910 of 2,358 shows (81.0%)** with at
  least one recording row.
- 16,507 `performance_recordings` rows, and — because every row in that table
  maps to a distinct `performance_id` — that's also the count of **distinct
  performances with a track mapping: 16,507 of 39,774 (41.5%)**. Put another
  way, well under half of documented performances currently have a specific
  track/timestamp on a specific recording.
- Recording notes split cleanly into two categories: **16,067 rows (89.4%)**
  carry a `"…search-index metadata only…"` note (an Internet Archive search
  hit, not yet reviewed in detail), and **1,910 rows (10.6%)** carry a
  `"Full Internet Archive item metadata preserved…"` note. That 1,910 figure
  is exactly the count of shows with any recording at all — i.e. the current
  convention is one fully reviewed representative recording per show, plus a
  long tail of unreviewed search-index stubs for the rest. So "recordings
  exist for a show" and "a recording has been reviewed in detail" are
  currently almost the same set, and neither implies a performance-level
  track mapping — track mappings (16,507) come from a smaller, separate
  effort layered on top.

## Part 2 — Prioritized next steps

Ordered by how much they block other work, not strictly by effort.

### 1. Add structured provenance columns

**Why:** Section 4 above — every canonical row already cites a source, but
only as prose. `source_name`, `source_record_id` (the gdshowsdb UUID /
JerryBase event ID / song UUID currently embedded in text), and ideally
`retrieved_at` should be real columns on `shows`, `performances`, and
`show_performers` (and eventually `recordings`, which has the same issue).
`resources.csv` already has the right shape (`source_name`, `source_url`) to
copy from.

**Effort:** Medium. It's a schema addition plus a one-time migration script
that regexes the existing notes into the new columns (three different regex
patterns, one per table/source convention) — not a re-collection. Freeform
`notes` can stay for anything that doesn't fit the structured fields.

**Unblocks:** The PostgreSQL importer's foreign-key/conflict validation
(item 7 below), any future multi-source conflict resolution
(`docs/provenance-policy.md`'s stated future need), and makes every
subsequent collection pass auditable by query instead of by grep. This is
cheapest to do now, before another 2,000+ rows of prose-only notes accumulate.

### 2. Expand source-specific chord arrangements

**Why:** The flagship musician-mode feature (`find_arrangements`,
source-specific key/capo/tuning cards) is described in the development plan
as a real capability, but it currently rests on **1** arrangement row
covering **1** song (Sugaree) with **4** chord sections. Any arrangement
query outside Sugaree returns nothing, which is a bigger gap than the
row-count table alone suggests, since it's not "thin coverage" but
"essentially no coverage."

**Effort:** Large, and inherently source-limited — this is a
collection/normalization pass against tab/chord sources (RUKIND and
similar), following the "review source, don't guess" rule in
`docs/collection-methodology.md`. Budget it per-song, not per-year; a
reasonable first target is full arrangement coverage for the 20 Veneta songs
before broadening.

**Unblocks:** Musician-mode actually being demonstrable beyond one song; a
credible answer to "does the app do more than setlist lookup."

### 3. Disambiguate ambiguous show dates in the resolve path

**Why:** Section 3 — 60 dates (120 shows, all 1966–1970) currently make
`resolve_show` return `None`, which is a dead end for any tool call that
takes a bare date. That's a real user-facing gap for exactly the years with
the thinnest other coverage.

**Effort:** Small–Medium. `resolve_show` (`deadbot/data.py:74`) needs either
(a) to return the full match list and let the caller disambiguate by venue or
set/matinee-evening, or (b) accept a secondary disambiguator (venue name or
`show_id` suffix) when the date is ambiguous, plus a tool-facing message that
says "N shows on this date" instead of silently returning nothing. No new
data collection required — this is purely retrieval-code and tool-response
work.

**Unblocks:** Correct answers for 1966–1970 questions, which is also where
performer/setlist coverage is already weakest — fixing this makes the
existing thin data actually reachable instead of doubly hidden.

### 4. Plan resource/media enrichment beyond Veneta

**Why:** Section 2 — only 1 of 2,358 shows has a direct show- or
performance-level resource or media link; the other 2,070 shows that surface
*any* resource card do so only via song-level attachment. The 86-show 1972
bulk pass added setlists and recordings but no contextual resources or media
links at all.

**Effort:** Large, ongoing — this is a genuine collection program, not a
script. Recommend sequencing by demonstrable impact: pick a small number of
heavily-played, well-documented shows per era (not necessarily
chronological) and build direct show/performance resource sets the way
Veneta's were built, rather than trying to backfill all 2,358 at once.

**Unblocks:** Any experience feature that depends on show-specific context
or media beyond Veneta — right now the "context beyond setlist" story is a
single-show demo, not a product capability.

### 5. Complete performance-level recording track mappings

**Why:** Section 7 — 41.5% of performances have a track mapping; the rest
have a show-level recording (81% of shows) but no way to jump to the specific
song within it. This is a smaller, more mechanical gap than resource
enrichment: the recordings mostly already exist, they just aren't broken down
by track/timestamp.

**Effort:** Medium. Track mapping is largely a matter of pulling per-track
listings from the already-identified Internet Archive items (the 1,910
reviewed recordings) rather than sourcing new recordings; the 16,067
search-index stubs are a separate, lower-priority tier (see item below).

**Unblocks:** "Play this specific song" from a canonical performance, which
is closer to the product's stated playback ambitions than show-level linking
alone.

### 6. Build the restricted source-reader tool

**Why:** `docs/development-plan.md` item 5. This is the named prerequisite
for any quote-card or attributed-source-context block in the experience
layer — the agent currently cannot read the content of a linked resource at
all, only cite its URL. Given how thin direct resource coverage still is
(item 4), this tool is what turns an existing `resources.csv` link into an
actual answer rather than a bare citation.

**Effort:** Medium, but scope-sensitive — the tool must fetch only URLs
already present in `resources.csv`, return concise metadata/excerpts, log
retrieval details, and never write a canonical claim automatically (per the
"current boundaries" list in the development plan). The sandboxing and
excerpt-length/rights guardrails are the real work, not the fetch itself.

**Unblocks:** The quote-card / attributed-source-context block described in
`docs/experience-architecture.md`; without it, the 293 existing resources
(and any added under item 4) stay link-only.

### 7. Build the CSV → PostgreSQL importer

**Why:** `docs/development-plan.md` item 6. The runtime is CSV-only today;
this is the last step before the data layer stops being "a directory of
files a script trusts" and becomes something with enforced constraints. It's
also the natural forcing function for cleaning up the gaps documented above
— a real foreign-key schema will surface anything Section 5's manual
orphan-checks missed, and structured provenance columns (item 1) are much
easier to add before this migration than after.

**Effort:** Large. Deterministic import, foreign-key validation, a rebuild
command, and refactoring `CanonicalStore` behind its existing read interface
so `deadbot/tools.py` doesn't change.

**Unblocks:** Everything downstream of "the data source is a set of CSV
files nothing validates on write" — concurrent collection passes, real
constraint enforcement, and eventually retiring the CSV-only boundary noted
in the development plan's "current boundaries" section.

**Sequencing note:** do item 1 (structured provenance columns) before this
one. Migrating prose-only provenance into a relational schema and then
adding structured columns afterward means writing the same regex-based
extraction twice.
