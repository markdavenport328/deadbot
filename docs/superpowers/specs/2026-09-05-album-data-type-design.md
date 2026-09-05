# Albums as a data type — design

Date: 2026-09-05. Owner brief: Deadbot has no album data type and does not
say which album a song appeared on. Add both. See `AGENTS.md` for the working
principles this follows.

## What exists today

`official_releases` (`schema/postgres.sql:261`) holds release_id, title,
artist_name, release_date, release_type, spotify_album_url, source_url and
notes. It has 294 rows and **every row is `release_type='live'`**. The
2026-09-01 MusicBrainz pass deliberately enumerated only release groups with
primary type Album and secondary type Live
(`docs/collection-status-official-releases.md`). No studio record — *The
Grateful Dead*, *Anthem of the Sun*, *Workingman's Dead*, *American Beauty*,
*Terrapin Station* — exists as a row.

`official_release_tracks` holds 10,045 rows keyed `(release_id,
track_number)`. A track's only entity reference is a nullable
`performance_id`: one song played at one show. 7,046 tracks resolve to a
canonical performance; 2,999 do not, and those carry a `track_title` and
nothing else.

`songs.csv` has song_id, title, slug, original_artist,
first_known_dead_performance, last_known_dead_performance and notes. There is
no album column. `original_artist` is empty for all 436 rows.
`song_writers.csv` covers 133 of the 436 songs.

## The gap

A song reaches a release only sideways. `CanonicalStore._listen_paths`
(`deadbot/data.py:226`) walks `official_release_tracks` for a performance ID
and returns a release *track URL* as a listening path. There is no
song-to-release relationship, so "what record is Sugaree on" is unanswerable
and always has been.

The gap is visible at every layer above the store. `song_context`
(`deadbot/data.py:204`) returns song, writers, performances, resources and
arrangements — the model never sees album information for a song.
`SongOverviewBlock` (`deadbot/experience.py:318`) has no album field.
`search_entities` (`deadbot/tools.py:307`) resolves songs, people, venues,
equipment and shows, so an album title resolves to nothing.

## Goals

1. A song knows which official records carried it, with dates.
2. An album is a browsable object: tracklist, release date, personnel, links.
3. The studio-versus-live relationship is expressible — how long a song lived
   on stage before or after the record.
4. Live and studio releases are one catalog, not two parallel models.

Catalog scope: the Grateful Dead studio albums plus the solo and side-project
records that first carried songs the band played — Garcia, Ace, New Riders of
the Purple Sage, Old & In the Way, Kingfish, Jerry Garcia Band. Roughly 30–45
albums. Cover songs link only to Dead-family releases; their non-Dead origin
is recorded as `original_artist` and writer credits, not as an imported
discography of other artists.

## Decisions

1. **Extend `official_releases`; do not add a parallel album table.** The
   table is already an album table that has only been fed live records. Studio
   albums enter as rows with `release_type='studio'`. This keeps one answer to
   "what did they officially release", reuses the importer specs, the
   `release_shows` coverage guard, `official_release_summaries` and the
   listen-action builder, and avoids splitting hybrid records — *Europe '72*,
   *Reckoning* and *Dead Set* are live recordings that functioned as album
   releases.

   Rejected: separate `albums` / `album_tracks` tables. Conceptually tidier,
   but it duplicates release plumbing, splits the catalog, and forces a
   judgment call on every hybrid release. Rejected: an `original_album` column
   on `songs`. Cheapest, but a song sits on several records and the column
   yields no tracklist, no personnel and nothing to browse — it fails goals 2
   and 4 outright.

2. **A release track gains a nullable `song_id`.** A studio track has no
   performance, because a performance is a song played at a show. Giving
   tracks an optional composition reference makes song-to-album a plain join
   through `official_release_tracks`. Live tracks keep pointing at
   performances; a track may carry both, one, or neither (an intro, tuning or
   banter segment carries neither, as today).

3. **Backfill `song_id` on unmapped live tracks.** 2,999 existing live tracks
   have a title and no performance. Where the title resolves to a canonical
   song, the backfill makes "which official releases carry this song at all"
   answerable across the live catalog. This repairs data already held and is
   in scope for this pass.

4. **`release_type` becomes a checked vocabulary**: `studio`, `live`,
   `compilation`, `single`. The column is currently free text with one value
   in practice. `compilation` and `single` are declared now and left unused;
   the catalog scope excludes them from this collection pass.

5. **Album personnel is a new table, `release_personnel`**, shaped like
   `show_performers`: one row per person's role-and-instrument assignment on a
   release. MusicBrainz artist-credit and recording-level relationship data
   for these records is uneven, so this table is expected to land partial.
   Partial personnel does not block the rest of the pass.

6. **Studio-versus-live comparison is the model's to make, not the store's.**
   The release date is on `official_releases` and every performance is dated,
   and after this change `song_context` returns both in one payload. "Played
   live for fourteen months before the record" therefore needs no new column
   and no new store method — it needs the model to have the two dates
   together, which it now does. Per `AGENTS.md`, giving the model the facts
   comes before adding deterministic code to compute the observation for it.

7. **One new semantic unit, `album_unit`**, alongside `show_unit`,
   `performance_unit` and `era_unit`. An album is a meaningful object a
   visitor perceives whole — title, year, tracklist, who played on it, where
   to hear it, and the model's note about why it matters here. Following the
   semantic-units design, composition is fixed by adding a unit, not by adding
   prose rules.

8. **Cover origin is recorded on the song, not modeled as foreign
   discography.** `original_artist` gets populated; writer credits extend
   where a source supports them. Deadbot says "Morning Dew is Bonnie Dobson's
   song; the Dead put their version on *The Grateful Dead* in 1967" without
   holding Bonnie Dobson's discography.

## Schema changes

Schema version 4 → 5. New forward migration
`schema/migrations/005_studio_releases.sql`; `SCHEMA_VERSION` in
`deadbot/postgres_import.py:26` and the seed insert at `schema/postgres.sql:14`
both move to 5.

```
official_release_tracks
  + song_id TEXT REFERENCES songs (song_id) ON DELETE SET NULL

official_releases
  + CHECK (release_type IN ('studio', 'live', 'compilation', 'single'))

release_personnel                                          (new)
    release_id TEXT NOT NULL REFERENCES official_releases (release_id)
        ON DELETE CASCADE
    person_id  TEXT NOT NULL REFERENCES people (person_id)
        ON DELETE CASCADE
    role       TEXT NOT NULL
    instrument TEXT NOT NULL
    notes      TEXT
    PRIMARY KEY (release_id, person_id, role, instrument)
```

`instrument` is `NOT NULL` because it is part of the primary key, matching
`show_performers` exactly. Every one of that table's 26,265 rows carries a
real instrument, so no placeholder convention exists to copy. A MusicBrainz
credit that names a person and a role but no instrument therefore cannot be
stored as-is; the normalizer holds it in the review log rather than inventing
a value. If held credits turn out to be common, the fix is to drop
`instrument` from the primary key in a later migration, not to fill the column
with a sentinel.

The migration adds the column and table without rewriting existing rows; the
check constraint is added after normalizing the 294 existing `live` values,
which already conform.

Canonical CSVs follow the same shape, since every canonical file has a
same-named table whose columns match the header: `official_release_tracks.csv`
gains a `song_id` column, and `data/canonical/release_personnel.csv` is new.
Import order places `release_personnel` after both `people` and
`official_releases`.

## Collection

`scripts/collect/fetch_musicbrainz_studio_releases.py` mirrors the live
fetcher: resolve each artist MBID by search, enumerate Album release groups
*without* the Live secondary type, browse official releases with
`inc=recordings+url-rels+release-groups+artist-credits`, checkpoint per page,
one request per second with a descriptive User-Agent. Artists: Grateful Dead,
Jerry Garcia, Bob Weir, New Riders of the Purple Sage, Old & In the Way,
Kingfish, Jerry Garcia Band. Raw records land in `data/raw/releases/` beside
the existing live JSONL files.

The MusicBrainz entry in `data/source_registry.json` is verified to cover
these operations before the pass runs; a new host or operation requires a
registry review, not an ad-hoc call.

`scripts/normalize_musicbrainz_studio_releases.py` writes the canonical rows.
It resolves each track title to a canonical `song_id` with the same matching
discipline the live normalizer uses, logs every decision to a review JSONL,
manages only rows whose notes identify them as its own, reuses previously
assigned release IDs, and produces byte-identical output on a rerun. Following
`docs/collection-methodology.md`, an unresolved title match is recorded and
held, never promoted with a guessed value.

The live-track `song_id` backfill is a separate normalizer pass over the
existing 2,998 unmapped tracks, with the same fail-closed rule: a title that
does not resolve stays empty and appears in the review log.

Cover origin is a reviewed curation pass, not a script. `original_artist` is
empty for all 436 songs, and writer data covers 133, so this is authoring
rather than gap-filling. Where writer credits exist and name no Dead-family
member, that is evidence a song is a cover, but it does not name the original
artist by itself. This pass is sequenced last and is independently reviewable;
the album work does not depend on it.

## Store

`CanonicalStore` (`deadbot/data.py`) and `PostgresCanonicalStore`
(`deadbot/postgres.py`) must change together. The Postgres store mirrors the
CSV store by narrowing rows into a projection (`deadbot/postgres.py:434`); a
one-sided change makes the two modes disagree silently.

- `song_context` gains a `releases` list: release ID, title, artist, date,
  type, track number and album URL for each record carrying the song, sorted
  by release date, studio before live at equal dates.
- New `album_context(release)`: the release row, its tracklist with each
  track's resolved song and performance, personnel with resolved names, and
  its links.
- New `resolve_release(identifier)`, matching on release ID and title, in both
  stores.
- `official_release_summaries` is unchanged in shape and gains studio rows for
  free.

## Model-facing changes

- `get_song` (`deadbot/tools.py:535`) returns the richer payload; its
  docstring names albums as available.
- New `get_album(release_id_or_title)` tool returning `album_context`.
- `search_entities` (`deadbot/tools.py:307`) adds releases to its resolution
  set, so "American Beauty" returns an ID.
- The persona's "Structured library" paragraph (`deadbot/graph.py:47`) lists
  official releases already; it is extended to say that studio and solo
  albums, their tracklists and their personnel are held, and that a song's
  record and its live history can be compared.

## Composition and browser schema

```
AlbumUnitRef   type=album_unit   release_id, role?, note?,
                                 highlighted_song_ids[≤12],
                                 supporting_sources[≤4], follow_up?, title?

AlbumUnitBlock release_id, title, artist_name?, release_date?, release_type,
               role?, note?, tracks[AlbumTrackItem ≤30],
               personnel[PerformerItem ≤20], listen[ListenAction ≤3],
               sources[UnitSource ≤4], follow_up?

AlbumTrackItem track_number, title, song_id?, performance_id?,
               duration_seconds?, highlighted: bool, listen_url?
```

Grounding follows the existing rule: the release ID must appear in this turn's
tool output, highlighted song IDs must belong to the release, and a supporting
source URL must have come from this turn.

`SongOverviewBlock` (`deadbot/experience.py:318`) gains an `albums` list of
`{release_id, title, release_date, release_type}`, capped at six. Both blocks
join the `ExperienceBlock` union (`deadbot/experience.py:491`), and
`AlbumUnitRef` joins the `FinishPlan` body vocabulary and the palette
description the model reads (`deadbot/finish.py`).

`_song_overview` (`deadbot/composition.py:994`) populates the album list. A
new `_album_unit` builder hydrates the unit from `album_context`.

## Renderer

Regenerate `web/openapi.json` via `scripts/export_openapi.py`, then
`web/src/generated/api.ts`. Add `AlbumUnitBlock` to the union in
`web/src/types.ts:44` and a render case in `web/src/App.tsx`. An album unit is
one card: title and year as the heading, artist when it is not the Grateful
Dead, a role chip when present, the note, the tracklist with highlighted songs
marked and each track linking to its song, personnel, listen actions, sources
and follow-up. The `song_overview` case (`web/src/App.tsx:557`) shows the
song's records inline.

## Tests

Store: song context includes releases in the specified order; album context
resolves tracklist, personnel and links; release resolution by ID and title;
CSV and Postgres stores return equal payloads for the same fixture. Importer:
the new column and table load, the release-type constraint rejects an unknown
value, and the version-4 database migrates to 5. Composition: album unit
hydration, highlight filtering, source grounding, song overview albums. Plan
validation for `AlbumUnitRef`. Normalizer: title-to-song resolution, held
unresolved rows, byte-identical rerun. Schema export and type generation are
regenerated as part of the change, not after it.

New evaluation cases in `evals/`: which record a song is on, an album asked
about directly, and a song's stage life measured against its release date.

## Limitations accepted in this pass

Compilations and singles are declared in the vocabulary and not collected. No
non-Dead-family discography, so a cover's original record is named in prose
rather than modeled. `release_personnel` may be partial where MusicBrainz
credit data is thin. The cover-origin curation pass covers songs the review
can support and leaves the rest empty rather than guessing. Multiple editions
of one album collapse to one row, as the live pass already does by picking one
release per release group.
