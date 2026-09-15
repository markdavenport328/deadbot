# Guest song credits status

Updated 2026-09-14.

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

## Next candidates

The same shape fits any recurring guest whose songs are known: Branford
Marsalis (1990-03-29 is fully documented on the official release), Bruce
Hornsby's pre-membership sit-ins, Bob Dylan 1989-02-12, the Ornette Coleman
1993-02-23 second set.
