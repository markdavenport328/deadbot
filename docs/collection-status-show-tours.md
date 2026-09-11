# Show tour collection status (2026-09-10/11)

## Task

Fill `shows.csv` `tour_name`. Before this pass, 1 of 2,358 canonical shows
carried a tour name (`gd-1972-08-27`, hand-curated from JerryBase in an
earlier pass). Deadheads navigate by tour (Europe '72, Spring '77, Egypt '78,
Fall '73, Festival Express), so this is a first-class grouping the model
needs and the catalog was almost entirely missing it.

## Source evaluation

### JerryBase — blocked (access state, not absence of data)

JerryBase event pages show a tour field and were the planned source
(`scripts/collect/fetch_jerrybase_performers.py` already collects performer
data from the same pages). Verified 2026-09-10/11 from this environment:
every request to `jerrybase.com`, including `GET /events?year=1972` with the
exact `User-Agent: Deadbot/0.1 (performer-enrichment)` string the existing
performer collector used successfully on 2026-08-26, returns **HTTP 403**.
No browser user agent or proxy was tried, per instruction. This is recorded
as an **access state** (`blocked`), not as JerryBase lacking tour data —
JerryBase's own pages likely still carry a tour field per show; this project
simply cannot reach it right now. Revisit later; see "Held for later" below.

### Relisten — reachable, explicit, and adopted as primary

Relisten's public API (`api.relisten.net`, already an approved collection
source for `relisten-years.jsonl`) carries a `tour` object on every show
record returned by `GET /api/v2/artists/grateful-dead/years/<year>`, which
`data/raw/recordings/relisten-years.jsonl` (the existing raw file) does not
retain — the existing collector's `compact_show()` only keeps
`SHOW_FIELDS`, which excludes `tour`. A one-request test of
`GET /api/v2/artists/grateful-dead/years/1972` with a descriptive User-Agent
(one request, well under the established 1/second pace) confirmed the field
is present: each show carries `tour: {name, slug, uuid, start_date,
end_date}` or `tour: null`.

A second, separate endpoint, `GET /api/v2/artists/grateful-dead/tours`,
returns the complete, closed list backing that field — confirmed with one
request. As of 2026-09-11 it holds exactly **nine** entries: a catch-all
`"Not Part of a Tour"` (2,161 shows) plus eight named touring runs:

| Source tour name | Start | End | Shows on tour |
| --- | --- | --- | --- |
| Spring 1970 | 1970-04-26 | 1970-05-17 | 14 |
| Europe 1972 | 1972-04-07 | 1972-05-26 | 22 |
| Summer 1974 | 1974-06-08 | 1974-08-06 | 18 |
| Summer 1976 | 1976-06-03 | 1976-07-18 | 25 |
| Spring 1977 | 1977-04-22 | 1977-06-09 | 30 |
| Summer 1988 | 1988-06-17 | 1988-07-03 | 11 |
| Spring 1990 | 1990-03-14 | 1990-04-03 | 16 |
| Fall 1993 | 1993-09-08 | 1993-09-30 | 18 |

This tour tagging is itself sourced upstream from jerrygarcia.com (per the
artist endpoint's `upstream_sources`), independent of Relisten's own
editorial judgment, and confirmed to be a small, closed, source-maintained
list via `features.tours: true` on the artist endpoint plus the `/tours`
enumeration above — it is not an artifact of a partial or failing request.
The important limitation: this source tags **very few** of the band's
touring years as a distinct "tour." Egypt '78, Fall '73, and most other runs
Deadheads would readily name are inside the "Not Part of a Tour" catch-all
in this dataset. Relisten is explicit and structured for what it covers, but
its coverage of "named tour" as a concept is narrow — see "Held for later."

### Wikipedia — no tour list, isolated tour articles only

`action=query&list=search` for "Grateful Dead concert tours" returns no
tour-list or tour-index article (results were albums, films, and reunion
pages). `action=query&list=categorymembers` for
`Category:Grateful Dead concert tours` returned zero members — the category
does not exist. A search for `"Europe '72" Grateful Dead` does confirm the
one tour-specific article the task anticipated (`Europe '72`, plus several
related release articles), but that is an isolated case, not a bounded
enumeration source: extracting tour date ranges would mean discovering and
curating one Wikipedia article per tour by hand, with no index to drive it
and no guarantee of coverage or a parseable date range in the infobox. Given
Relisten already supplies eight explicit, dated, per-show tour assignments
structurally, Wikipedia was not pursued further for this pass. The
`wikipedia-api` registry entry's `operation_policies` and `notes` were
therefore **not extended** — nothing here used it beyond the two read-only
search queries reported above, which are within its already-approved
`search` operation.

### Dead.net — no tour field on the reachable pages

The task's assumed URL shape, `https://www.dead.net/show/<date>`, returns
HTTP 404 (Dead.net's show URLs are not date-keyed in this simple form). The
site does expose `/archives/tour` (a "Show Archive" page, linked from a
site-wide `href="/archives/tour"`), which sounded promising, but its filter
controls are keyed by **year** (`<option value="1978">1978</option>`, etc.),
not by tour name, and its internal JS state only distinguishes a `"tour"`
content-type flag from `"news"` — there is no per-show or per-range tour
label anywhere in the fetched HTML. Dead.net was not pursued further; it
does not carry the fact type this task needs on any page this evaluation
could reach. (`/archives/tour` is outside the current `deadnet-editorial`
registry allowlist in any case, so nothing was collected from it.)

### Decision

**Primary source: Relisten**, via a new raw file,
`data/raw/recordings/relisten-tours.jsonl`, fetched by
`scripts/collect/fetch_relisten_tours.py`. Rule: **promote `tour_name` only
for a show whose Relisten record carries a non-null `tour` whose `name` is
not `"Not Part of a Tour"`, and only when that source name is in the
normalizer's reviewed alias table.** Every other show — no named tour, no
Relisten record for the date, or (should it ever occur) an unrecognized new
tour name — stays blank. JerryBase's tour field remains held until the
403 clears.

## Collection

`scripts/collect/fetch_relisten_tours.py` fetches the same
`/api/v2/artists/grateful-dead/years/<year>` endpoint `fetch_relisten_years.py`
already uses (one request per year, one request per second, descriptive
`User-Agent: Deadbot/0.1 (tour-research; contact via repository)`), for all
31 years (1965–1995), and writes a compact `{display_date, uuid, tour}` raw
record per show into a dedicated raw file so its retry/merge behavior does
not depend on `relisten-years.jsonl`'s existing compact field set. It
follows the same retry-safe, `--force`-mergeable, never-erase-a-prior-success
pattern as `fetch_relisten_years.py`.

Run 2026-09-11: all 31 years returned HTTP 200. 150 shows carried a named
tour across the per-year listings. This is 4 short of the `/tours`
endpoint's own total of 154 (`shows_on_tour` summed across the eight named
tours); the gap is Spring 1970, where the per-year listing returns 10 of
that tour's shows rather than 14. Checked directly: two Spring-1970-window
canonical dates (1970-04-26 and 1970-05-10) do not appear in Relisten's
per-year show listing at all — consistent with Relisten's documented
behavior of listing a date only when it has a known tape (see
`docs/data-sources.md`'s Relisten entry) — which accounts for 2 of the 4;
the remaining 2 were not tracked further since every date the per-year
listing did return resolved cleanly to a canonical show (0 unmatched
dates). Net effect: this is a coverage gap in which shows the source's
per-date listing surfaces, not a mismatch in what it says about the dates
it does surface.

## Normalization

`scripts/normalize_show_tours.py`:

- Matches by `show_date` (Relisten has one record per calendar date).
- Never overwrites a `tour_name` that is already non-blank from another
  source (verified: the existing `gd-1972-08-27` JerryBase row was
  untouched — 1972-08-27 is outside Relisten's Europe 1972 window in any
  case, so there was no conflict to arbitrate).
- Promotes only a source tour name present in `TOUR_NAME_ALIASES`, an
  explicit table mapping each of Relisten's eight names to one canonical
  spelling (currently identity, since Relisten's names are already plain —
  the table exists so a future source's variant spelling can be reconciled
  to the same eight canonical values without touching what is already on
  disk). Any unrecognized name is held for review rather than promoted
  under an unreviewed spelling; none occurred in this run.
- Cites the source in `notes`, appended to whatever citation was already
  there (matching the existing `gd-1972-08-27` row's convention of
  semicolon-joined facts), e.g.:

  > Normalized from gdshowsdb show UUID 4d893edd-…; Tour sourced from
  > Relisten tour listing (https://api.relisten.net/api/v2/artists/grateful-dead/years/1970,
  > retrieved 2026-09-11): "Spring 1970" (1970-04-26 to 1970-05-17).

- Is idempotent: a previously-written row is identified by a fixed marker
  in `notes` and recomputed from scratch on rerun (verified: rerunning
  produced a byte-identical `shows.csv`).
- Handles the one case where a named-tour date has two canonical shows
  (`gd-1970-05-15-0`/`-1`, an early/late Fillmore East show both inside the
  Spring 1970 window): both rows get the tour, and each row's note names
  the sibling it shares the date-level source record with.

## Result

| Metric | Count |
| --- | --- |
| Canonical shows | 2,358 |
| `tour_name` filled before this pass | 1 |
| `tour_name` filled after this pass | 152 |
| — from this pass (Relisten) | 151 |
| — pre-existing (JerryBase, `gd-1972-08-27`) | 1 |
| Unrecognized tour names held for review | 0 |

Tour name | Canonical shows filled
--- | ---
Europe 1972 | 22
Fall 1993 | 18
Spring 1970 | 11
Spring 1977 | 30
Spring 1990 | 16
Summer 1974 | 18
Summer 1976 | 25
Summer 1988 | 11
(pre-existing, JerryBase) Grateful Dead Summer 1972 West Coast/Mountain | 1

2,206 shows have no named-tour source record for their date and remain
blank, including every 1965–1969, 1971, 1973, 1975, 1978–1987, 1989,
1991–1992, and 1994–1995 show, most shows within years that do have a named
tour, and the two Spring-1970-window dates (1970-04-26, 1970-05-10) absent
from Relisten's per-year listing (see above).

## Held for later (human decision / future source)

- **JerryBase is the biggest gap.** Its event pages reportedly show a tour
  field per the task brief; once the 403 clears, that source should be
  re-evaluated against the same alias table — JerryBase may use different
  spellings for the same tours (needing new alias entries) and, more
  importantly, may name additional tours Relisten's eight-entry list does
  not cover (Egypt '78, Fall '73, Wake of the Flood/Fall '73, the 1970
  Festival Express run — none of these produced a Relisten tour tag in this
  pass). Do not treat Relisten's 8-tour list as exhaustive; it should be
  supplemented, not replaced, once JerryBase is reachable.
- **A human should decide** whether any additional, currently-"Not Part of a
  Tour" run deserves a project-defined tour_name from another explicit
  source (a research blog, a published tour itinerary) even though
  Relisten does not tag it — this pass deliberately does not infer a tour
  from a month/year grouping, per instruction, so a well-known but
  Relisten-untagged run (Egypt '78 being the clearest example) stays blank
  rather than guessed.
- No conflicting tour-name evidence was found between Relisten and the one
  pre-existing JerryBase-sourced row, so no override rule was needed this
  pass; one should be written (source priority, and what to do on a
  disagreeing date range) before JerryBase enrichment resumes.
