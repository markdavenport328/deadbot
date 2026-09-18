# Guest song credits status

Updated 2026-09-18.

Goal: let "Best songs with Santana" name songs instead of shows. Before this
pass every guest credit lived in `show_performers.csv`, so the catalog knew
Carlos Santana was onstage at seven shows and nothing about which songs he
played. Schema version 10 adds `performance_performers.csv`, one row per
person's role-and-instrument credit on one performance, shaped like
`show_performers`.

## What was done

1. A web research pass, written up in
   `docs/research-santana-onstage-2026-09-14.md`, established the songs for
   six of Santana's seven sit-ins from setlist.fm, JerryBase, dead.net show
   pages, Lost Live Dead, JamBase, Daily Dose of the Dead and Grateful Dead
   of the Day. JerryBase itself is not reachable from the sandbox (403), so
   its guest lists were read from the raw snapshots already in
   `data/raw/performers/`.
2. `data/canonical/performance_performers.csv` gained 18 rows:
   - Carlos Santana, guitar, on 14 performances across six shows
     (1980-01-13, 1987-08-22, 1987-08-23, 1991-04-28, 1991-10-27,
     1993-01-26).
   - John Cipollina, guitar, on the same two 1980-01-13 songs.
   - Gary Duncan, guitar, on the same two 1991-10-27 songs.
   - Greg Errico, drums, on the 1980-01-13 U.S. Blues encore.
   Each row's `notes` carries a one-line account and the citation;
   `source_key` is `manual` and `source_record_id` is
   `research-santana-onstage-2026-09-14`.
3. Ten resources were added to `resources.csv` (JamBase, dead.net community
   pages, Grateful Dead of the Day, Daily Dose of the Dead, Newsweek, Cave
   Hollywood, Far Out Magazine), with eleven `resource_performances` rows of
   type `performance-anecdote` or `performance-listening-note` and five
   `resource_shows` rows, so the anecdotes reach the model with a source.
4. `search_guest_musicians` now attaches `songs` to an appearance when the
   catalog has rows for that person and show, in set order, each with the
   note. An appearance without `songs` is show-level only. The
   `guest_appearance_list` block carries the same list and the web card
   prints the song titles under each show.
5. `performance_context` (the CSV and Postgres stores) now returns
   `performers`, the song-level credits with the person's name.

## What was deliberately left out

- **1976-12-31 Cow Palace.** JerryBase credits Santana as a guest and one
  attendee says he and Garcia played together on many songs, but no source
  names the songs and the official release credits only the band. No rows;
  the appearance stays show-level.
- **1991-04-28 Box of Rain encore.** No source credits Santana on it.
- **1991-10-27 the jam after Mona.** Plausible, not sourced.
- **1969-05-11 San Diego.** Santana's percussionists sat in, not Carlos.
- **1989-02-12 Drums.** A JamBase guest compilation lists Santana; the drum
  guest that night was Yoshikazu Fujimoto of Kodo. Confirmed wrong.

## Data notes surfaced by the pass

- `gd-1980-01-13` has ten set 1 songs and a set 2 of `u-s-blues` then
  `bridging-the-gap`. Sources describe one 90-minute set plus a U.S. Blues
  encore. `song-bridging-the-gap` was normalized from a gdshowsdb label and
  may be a benefit-jam placeholder rather than a song. Not changed here.
- Santana has said Calaveras 1987 was the first time he played with the
  Dead, which conflicts with the 1976 and 1980 JerryBase credits. The
  credits stand; the remark is noted in the research document.

## Second pass, 2026-09-18: eight guest slices in parallel

Eight research agents ran at once, one per guest slice, each writing its own
research document and a staged set of rows that were validated (every
performance_id, person_id and resource_id resolves; no collisions; one row per
person, role and instrument on a performance) and appended to the canonical
tables in one step. The table went from 18 rows on 6 shows to 325 rows on 69
shows, covering 26 people. Resources gained 93 rows, resource_performances
264 and resource_shows 59. The featured-show queue was regenerated because
two of its shows gained show-linked resources.

| Slice | Research document | Song rows | Shows |
| --- | --- | --- | --- |
| Branford Marsalis | `docs/research-branford-marsalis-2026-09-18.md` | 49 | 5 |
| Bruce Hornsby as a guest | `docs/research-bruce-hornsby-2026-09-18.md` | 30 | 7 |
| Bob Dylan | `docs/research-bob-dylan-2026-09-18.md` | 14 | 4 |
| Ornette Coleman, David Murray | `docs/research-jazz-horns-2026-09-18.md` | 22 | 4 |
| Clarence Clemons, Steve Miller | `docs/research-clemons-miller-2026-09-18.md` | 61 | 11 |
| Hamza El Din | `docs/research-hamza-el-din-2026-09-18.md` | 16 | 12 |
| Bill Graham memorial, NYE 1982 (Etta James, Tower of Power horns), Joan Baez 1981 | `docs/research-memorial-and-nye-2026-09-18.md` | 67 | 6 |
| Airto Moreira, Flora Purim, Ken Kesey | `docs/research-airto-kesey-2026-09-18.md` | 48 | 17 |

Conventions settled by this pass:

- A person who plays and sings gets two rows, one per instrument; the primary
  key is (performance, person, role, instrument), matching `show_performers`.
- Instrument labels follow the `show_performers` guest vocabulary
  (`vocals`, `keyboards`, `acoustic guitar`, `rap` for spoken word).
- "Played the whole show" stays show-level unless several independent sources
  say so for a named set of songs. Marsalis at gd-1991-09-10 (three sources,
  every song but Drums) got rows; Hornsby's 1993-95 whole-set returns did not.
- Where two sources disagree on a song, the row is left out and both claims
  are written in the research document.

Held out, with reasons in the research documents: Dylan's 1987 co-headline
sets (not representable as Dead performances); Purim's 1981-08-27 sit-in;
Airto's whole-set claim at the 1982-05-28 Moscone benefit; Marsalis beyond
three named songs at gd-1993-12-10; Hornsby's 1992-06-20 closing songs and
his 1994-03-23 JerryBase-only credit; Miller's contested gd-1992-06-20 songs;
Clemons on two songs at gd-1989-12-27; Brokedown Palace for Ornette Coleman
at gd-1993-02-23; El Din at gd-1978-12-30 and gd-1988-02-16.

Catalog gaps the pass surfaced (not changed here):

- `performances.csv` has no `ollin-arageed` row at gd-1978-09-16 or
  gd-1986-12-30 though sources place El Din's piece at both.
- The acoustic Joan Baez sets at gd-1981-12-12 and gd-1981-12-31 are missing
  from `performances.csv`; only the electric sets were imported.
- `song-bridging-the-gap` at gd-1980-01-13 is a real Baez song, the all-cast
  finale of the benefit, not a placeholder.
- JerryBase's Kesey instrument field says harmonica at four shows; sources
  show the Thunder Machine at two of them.
- Guests seen at these shows with no song rows yet: James Cotton
  (gd-1993-09-22, corroborated on two songs), Denardo Coleman, Graham Wiggins
  and Sikiru Adepoju (gd-1993-02-23), Spencer Davis and Yoshikazu Fujimoto
  (gd-1989-02-12), Diana Moreira and Michael Hinton (no people rows).
- gd-1994-08-04 carries a Hornsby accordion guest credit not in this pass.

## Next candidates

Remaining recurring guests at show level only: Matthew Kelly's other eleven
harmonica nights, Ned Lagin's 57 credits (1970-75, mostly Seastones sets),
John Cipollina's remaining shows, the Neville Brothers and Baba Olatunji
percussion sit-ins, Huey Lewis, Spencer Davis, James Cotton, and the
Egypt-era Nubian choir. The 1987 Dylan tour and the missing acoustic Baez
sets need new performance rows first.
