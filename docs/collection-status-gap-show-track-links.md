# Track audio for shows with none (Internet Archive gap pass)

Updated 2026-10-12. Roadmap item 12 in `docs/OPENING-QUESTIONS-ROADMAP.md`.

Goal: give track-level archive.org audio to canonical shows that have a
setlist but no `archive` / `recording-track` link, starting with the shows that
have only a Relisten page (for example `gd-1969-09-30-0`, the Cafe au Go-Go
early show with the first China Cat Sunflower into I Know You Rider).

Relisten was not contacted. The owner agreed that bulk Relisten access waits
for a note to the Relisten team, and Relisten's tapes come from Archive
anyway, so this pass used only the Internet Archive search and metadata
endpoints.

## Why these shows had no tracks

The earlier index pass (`normalize_internet_archive_1972_index.py`) attaches an
Archive item to a show by date and deliberately skips any date shared by two
canonical shows, because a date does not say which show a tape holds. Of the
195 shows with a setlist and no track audio, 64 sit on such a date (early/late
pairs from 1967 on, mostly 1969–1970). The year indexes also never saw items
whose date field was missing or off by a day, and the alternates collector
stopped at three items per show, which for 1987-07-12 meant three tapes of the
third set only.

## Method

1. **Targets.** Every canonical show with performances and no archive
   track link: 195 shows on 171 distinct dates. (The other 282 shows without
   tracks have no setlist, so a track cannot be tied to a performance; see
   "What is still missing".)
2. **Search.** `scripts/collect/fetch_internet_archive_gap_shows.py` ran one
   advanced search per date against the GratefulDead collection, matching the
   `date` field or an identifier that starts `gd1969-09-30` / `gd69-09-30`.
   Results are preserved as one record per date in
   `data/raw/recordings/internet-archive-gap-search.jsonl`.
3. **Item metadata.** For each item found (and each item already attached to a
   target show), the same script fetched `https://archive.org/metadata/<id>`
   when it was not preserved yet and appended it to
   `internet-archive-alternate-items.jsonl`, the file the track normalizers
   already read. Items go in the pipeline's representative order (soundboard,
   then audience, then identifier). On a single-show date the script stops at
   the first item that aligns every performance; on a shared date it fetches
   all of them, because a tape that aligns to two shows settles neither.
4. **Pick the show.** `scripts/normalize_internet_archive_gap_shows.py`
   evaluates each item against every canonical show on its date with the
   existing aligners (`evaluate_item`: the strict aligner, then the tolerant
   one) and adds a `recordings.csv` row for an item only when it passes every
   one of these checks. Anything else is held, with the reason, in
   `data/raw/recordings/internet-archive-gap-review.jsonl`.
   - The item's track titles align to exactly one show's setlist.
   - On a shared date, the alignment is complete or settles at least 3 tracks
     (one or two shared song titles do not say which show a tape holds).
   - On a shared date, the venue the item names is not another show's venue
     and not this one's. (This caught `gd67-01-14.sbd.vernon.9108`: its title
     says Fillmore Auditorium, while the canonical show with a setlist that day
     is the Polo Field Human Be-In.)
   - The item's own `early` or `late` label does not name the opposite end of
     the date's show order.
   - The show has no track audio from a different tape.
   For each show the one item the track pass would choose is kept (the first
   that aligns every performance, in representative order; otherwise the one
   with the most settled tracks).
5. **Map and link with the existing scripts.** `normalize_internet_archive_tracks.py`
   (its fallback pass) mapped the new recordings to performances, and
   `normalize_internet_archive_track_links.py` wrote the download-route links.
   Titles come from the source, durations from archive.org's own `length`
   field (blank when it gives none), and no audio was downloaded.
6. **Verify.** Every new link was requested once, one per second.

## Counts

| Measure | Before | After |
| --- | ---: | ---: |
| Canonical shows | 2,358 | 2,358 |
| Shows with a setlist | 2,076 | 2,076 |
| Shows with at least one archive track link | 1,881 | 1,907 |
| `archive` / `recording-track` rows in `performance_links.csv` | 32,642 | 32,935 |
| `recordings.csv` rows | 17,977 | 18,002 |
| `performance_recordings.csv` rows | 32,652 | 32,945 |
| Relisten-linked shows with no track audio | 82 | 57 |
| of those, with a setlist (could take tracks) | 61 | 36 |

Of the 195 target shows, 26 gained audio (25 of them Relisten-linked, 290 new
links); 169 are still without. Requests: 171 searches and 130 item-metadata
fetches. 43 of the 171 dates have at least one Archive item; 128 have none.
The 26 shows: 25 from a tape newly attached by this pass, and 1987-07-12 from
a tape that was already in `recordings.csv`, which the old three-item limit
had never reached.

Three further rows are not from new shows. The rerun of
`normalize_internet_archive_tracks.py` found "We Bid You Goodnight" rows for
`gd-1969-02-15`, `gd-1969-12-30` and `gd-1971-04-29` that the unchanged
normalizer produces today (the title alias arrived after the last run) and
that the committed file lacked, so those shows each gained one track.

Derived files refreshed because the counts changed:
`data/editorial/priority-review-queue.json` (coverage snapshots, via
`scripts/refresh_priority_review_coverage.py`) and the home screen's recording
count in `web/src/App.tsx` (via `scripts/home_stats.py`).

## Shows that gained audio

| Show | Tracks linked | Source | Tape | Relisten link |
| --- | ---: | --- | --- | --- |
| gd-1967-08-05-1 | 6 of 6 | SBD | `gd1967-08-05.176008.sbd.flegel.miller.flac1648` | yes |
| gd-1968-05-18-0 | 5 of 5 | AUD | `gd1968-05-18.aud.dad.82515.flac16` | yes |
| gd-1968-06-14-1 | 9 of 11 | AUD | `gd1968-06-14.140953.late.aud.dalton.miller.sirmick.flac1644` | yes |
| gd-1969-02-07-0 | 3 of 6 | SBD | `gd69-02-07.early.sbd.wiley.14472.sbeok.shnf` | yes |
| gd-1969-02-12-1 | 7 of 10 | SBD | `gd1969-02-12.sbd-late.cotsman.6285.sbeok.shnf` | yes |
| gd-1969-03-22-0 | 4 of 9 | SBD | `gd69-03-22.sbd.cotsman.8994.sbeok.shnf` | yes |
| gd-1969-05-03-1 | 7 of 14 | AUD | `gd69-05-03.aud.phunk1.73.sbeok.shnf` | yes |
| gd-1969-06-21-0 | 10 of 12 | AUD | `gd1969-06-21.aud-early.cotsman.8995.sbeok.shnf` | yes |
| gd-1969-09-26-1 | 4 of 6 | AUD | `gd69-09-26.aud.hanno.14856.sbeok.shnf` | yes |
| gd-1969-09-27-0 | 8 of 10 | AUD | `gd1969-09-27.early.aud.warner-jupillej.12064.sbeok.shnf` | yes |
| **gd-1969-09-30-0** | 5 of 5 | AUD | `gd69-09-30.aud.early.hollister.80.sbeok.shnf` | yes |
| gd-1970-01-03-1 | 16 of 20 | SBD | `gd1970-01-03.sbd.gmb.97743.flac16` | yes |
| gd-1970-02-11-1 | 7 of 9 | AUD | `gd1970-02-11.late-set2.aud.smith.99152.sbeok.flac16` | yes |
| gd-1970-02-13-0 | 10 of 11 | SBD | `gd1970-02-13.early.sbd.murphy.31636.sbeok.flac16` | yes |
| gd-1970-02-13-1 | 16 of 18 | AUD | `gd1970-02-13.123814.aud.cooper.flac16` | yes |
| gd-1970-02-14-1 | 23 of 23 | SBD | `gd1970-02-14.141007.late.show.sbd.pcm.dalton.miller.clugston.fixed.flac1644` | yes |
| gd-1970-03-20-1 | 17 of 21 | SBD | `gd70-03-20.sbd.late.hamilton.14287.sbeok.shnf` | yes |
| gd-1970-03-21-0 | 9 of 12 | AUD | `gd70-03-21.early.aud.5315.sbeok.shnf` | yes |
| gd-1970-03-21-1 | 15 of 16 | AUD | `gd1970-03-21.late.aud.lee.pcrp.21779.shnf` | yes |
| gd-1970-05-15-1 | 21 of 26 | SBD | `gd70-05-15.early-late.sbd.97.sbeok.shnf` | yes |
| gd-1970-06-24-1 | 21 of 22 | | `gd1970-06-24.145261.late.SonyF95.lee.hance.sirmick.flac1644` | yes |
| gd-1970-10-30-1 | 15 of 15 | SBD | `gd1970-10-30.121125.sbd.deluca.digitalrbb.miller.flac1648` | yes |
| gd-1970-10-31-0 | 13 of 13 | SBD | `gd1970-10-31.122042.sbd.deluca.Digitalrbb.miller.flac1648` | yes |
| gd-1970-10-31-1 | 18 of 19 | SBD | `gd1970-10-31.early-late.sbd.serafin.33566.flac16` | yes |
| gd-1970-11-14 | 3 of 5 | SBD | `gd1970-11-14.179272.sbd.cassidy.minches.miller.t.flac2496` | no |
| gd-1987-07-12 | 18 of 18 | | `gd1987-07-12.142137.fob.schoeps.dalton.miller.clugston.flac1644` | yes |

Each linked track is a title match to the show's setlist; a partial count means
the tape lacks, or the aligner could not settle, the other songs.

## Held for review

Nothing below was guessed. Every row has the evidence in
`data/raw/recordings/internet-archive-gap-review.jsonl` (per-show alignment
status and matched-track counts for each tape).

### Relisten-linked shows with a setlist where the tape does not match (13)

The only tapes Archive holds for the date have track titles that do not match
the canonical setlist. The tape may be another show's material, a composite, or
the canonical setlist may need checking against it.

| Show | What the tapes hold |
| --- | --- |
| gd-1966-02-12 | One track, "Who Cares Rap"; setlist is Twist And Shout |
| gd-1966-10-31 | One track, "Jam Session (musicians unknown)"; setlist is Viola Lee Blues, Alice D. Millionaire |
| gd-1967-04-08 | TV-broadcast composite with announcer and interview tracks; the two Dead titles carry a band or "composite" prefix the title rules do not strip |
| gd-1967-07-23 | Neal Cassady rap tapes and a flexi-disc; none is a setlist song |
| gd-1967-10-31 | Alligator, Caution, Cryptical Envelopment, The Other One; setlist is Viola Lee Blues |
| gd-1968-12-31 | A 41-track item dated `68-xx-xx` mixing several nights; 1 of 35 song tracks aligns |
| gd-1969-09-07 | 1950s rock and roll covers; setlist is Me And My Uncle, China Cat Sunflower, and others |
| gd-1970-04-24 | Four audience tapes of a different set (I Know You Rider, Dire Wolf, Dark Star...); setlist is three songs |
| gd-1970-07-11 | 35 tracks, 4 of 24 song tracks align |
| gd-1970-08-17 | Three tracks (Let Me In, Attics Of My Life, Friend Of The Devil), none in the setlist |
| gd-1970-11-09 | Attics Of My Life, Mama Tried, Walkin' The Dog...; setlist is Not Fade Away, The Other One. A second item has no track titles |
| gd-1970-11-12 | China Cat Sunflower, I Know You Rider, Mama Tried, Good Lovin'; setlist is Candyman, Lovelight, Saint Stephen, It's A Man's World |
| gd-1971-11-06 | The item's file metadata gives conflicting titles for one track, so no title list could be read |

### Relisten-linked shows on a shared date where a tape cannot be pinned to one show (23)

| Show | Tapes held and why |
| --- | --- |
| gd-1967-01-14-0 | `gd1967-01-14.sbd.vernon.9108` aligns 2 tracks, but the item names Fillmore Auditorium and the other canonical show of the date is at the Fillmore; this show is the Polo Field Human Be-In. Its duplicate identifier `gd67-01-14...` matches fewer than 3 tracks |
| gd-1967-08-05-0 | Three tapes match fewer than 3 tracks of either show |
| gd-1968-06-14-0 | Tapes found match only the other show |
| gd-1969-02-07-1 | Two tapes match this show (8 tracks each) but also match the other show (3 and 1 tracks), so both shows align and the tape is held |
| gd-1969-04-12-0, -1 | One tape aligns to both shows (6 and 5 tracks, the second complete) |
| gd-1969-05-03-0 | Tapes found match only the other show |
| gd-1969-06-20-0, -1 | One Aoxomoxoa-related item matches 1 track of -1 and none of -0 |
| gd-1969-06-21-1 | A late tape matches no track; an early-and-late tape aligns to both shows |
| gd-1969-09-26-0 | Tapes found match only the other show |
| gd-1969-09-27-1 | Tapes found match only the other show |
| gd-1969-09-29-1 | Two tapes labeled early match this show (4 and 7 tracks), but this is the second show of the pair (the first has no setlist), so the label disagrees with the show order |
| gd-1970-01-02-0, -1 | Two tapes align to both shows (9 and 12 tracks; and an early-and-late tape, 11 complete and 12); a third matches no track; `partial-early` matches 3 tracks of -1 but is labeled early |
| gd-1970-01-03-0 | A late tape aligns to both shows (1 and 13 tracks) |
| gd-1970-02-11-0 | Four tapes align to both shows (4 tracks of -0, 7 or 8 of -1); one fragment matches fewer than 3 tracks |
| gd-1970-02-14-0 | `sbd.miller.97644` aligns to both shows (5 complete and 22); an early-and-late tape aligns to both |
| gd-1970-05-15-0 | The early-and-late tape matches only the other show; a second item matches no track |
| gd-1970-06-24-0 | Five audience tapes align to both shows |
| gd-1970-10-11-0, -1 | One tape aligns to both shows (7 and 6 tracks) |
| gd-1970-10-30-0 | Two tapes labeled early match this show (10 and 9 tracks) and the other show by 1 track; held because both shows align |

The cheapest next gains are in this table. A rule that places a tape on the
show it matches overwhelmingly (for example 10 tracks against 1, as for
`gd1970-10-30.early.sbd.cousinit.17359` and `gd69-02-07` late) would add
`gd-1970-10-30-0` and `gd-1969-02-07-1` at least. That is a judgment about how
strong a match must be to settle a shared date, so it was not applied here.

### Shows without a Relisten link

132 of the 133 target shows with a setlist and no Relisten link have no Archive
item for their date at all (the 1965–1968 spine shows and many 1970 dates).
The 133rd, `gd-1970-11-13`, has two soundboard items that the tolerant aligner
could not settle against its setlist.

## What is still missing

- **169 shows with a setlist still have no track audio:** the 36 and 133 above.
- **282 shows have no setlist** in `performances.csv` (21 of them Relisten
  linked, for example the Fillmore pair `gd-1967-01-14-1`). A track cannot be
  tied to a performance that is not in the data. If a tape exists for one of
  these dates, it needs a setlist first.
- **Combined tapes.** A recording belongs to exactly one show in the schema, so
  an early-and-late tape cannot serve both shows of a pair. Tapes that align to
  both are held rather than assigned to one.
- **Item metadata not fetched (12 items, all `gd-1987-07-12`).** The single-show
  stop fetched no more once one tape aligned every performance.

## Validation

- `tests/test_data.py` guard tests (converters, uniqueness, foreign keys) and
  the rest of the suite pass; the deploy SQLite build succeeds.
- Every new `performance_link_id` and `url` is unique, and each new row's
  `performance_id` and `recording_id` resolve.
- New links were requested one per second with GET (headers only), 293 in
  total; the result is below.
- No Relisten request was made. Requests to archive.org used the User-Agent
  `Deadbot/0.1 (historical-show-context)`, sequentially at one per second, with
  retries and backoff.

### Link check

293 new links, requested 2026-10-12 with up to three attempts each: 269 returned
HTTP 200 on the first pass and 24 returned HTTP 500 from an archive.org
datanode. A recheck of those 24 recovered 6 to 7 (the answer varies from one
attempt to the next); the persistent failures are 17 of the 21 links for
`gd-1970-06-24-1` (`gd1970-06-24.145261.late.SonyF95...`), whose files are all
listed in the item's metadata. The same check on the older, unrelated link
sample that `--verify-samples` draws returned 500 for 3 of 10 links that
answered 200 in September, so the 500s are archive.org's current state, not
bad rows. The links stay because every file name comes from the item's own
metadata; recheck `gd-1970-06-24-1` later, and note that the existing
playback code already recovers broken archive.org copies.

## Source and rights notes

Item metadata and the audio files are Internet Archive community uploads under
the band's taping and stream-only policies; rows are `is_official = false` and
each note names the item and file. A track link identifies one version of the
performance on one source. The identifier or description of some items says
"early", "late" or "partial", and a tape may hold only part of a show.
