# Hamza El Din onstage with the Grateful Dead: research notes

Compiled 2026-09-18 for the guest song-credit pass. `show_performers.csv` already
credits Hamza El Din (percussion, role `guest`) at 15 distinct shows via
JerryBase. What it lacks is song-level detail and the story of how a Nubian
oud and tar player ended up sitting in with the Dead for fourteen years.

## Who he was

Hamza El Din (July 10, 1929 – May 22, 2006) grew up in Toshka, a Nubian
village on the Nile in southern Egypt that was flooded in the 1960s by the
Aswan High Dam, displacing tens of thousands of Nubians. He played oud
(a short-necked lute) and tar (a frame drum), and became known in the West
largely through Mickey Hart, who produced his landmark 1971 album *Escalay:
The Water Wheel* — one of the first "world music" records to get wide
release outside its home tradition. That relationship is the reason he was
on a Grateful Dead stage at all: when the band's Egypt trip came together in
1978, El Din was Hart's friend and collaborator, not a stranger act on the
bill.

## The catalog knows him at 15 shows (16 credit rows)

`show_performers.csv` lists Hamza El Din as a guest at:

| Show | Venue | Ollin Arageed performance row exists? |
|---|---|---|
| gd-1978-09-14 | Gizah Sound and Light Theater, Giza, Egypt | yes (set 1, opener) |
| gd-1978-09-15 | Gizah Sound and Light Theater, Giza, Egypt | yes (set 1, opener) |
| gd-1978-09-16 | Gizah Sound and Light Theater, Giza, Egypt | **no — missing, see below** |
| gd-1978-10-21 | Winterland, San Francisco | yes (set 1, opener) |
| gd-1978-10-22 | Winterland, San Francisco | yes (set 1, opener) |
| gd-1978-11-24 | Capitol Theatre, Passaic, NJ | yes (set 2, after Drums) |
| gd-1978-12-30 | Pauley Pavilion, UCLA | yes (set 2, after Drums) — no song-naming source found |
| gd-1979-08-05 | Oakland Auditorium | yes (set 2, after Drums) |
| gd-1985-03-13 | Berkeley Community Theater | yes (set 2, after Drums) |
| gd-1986-12-30 | Henry J. Kaiser Convention Center, Oakland | **no — missing, see below** |
| gd-1988-02-16 | Henry J. Kaiser Convention Center, Oakland | n/a — no song-naming source found |
| gd-1988-03-17 | Henry J. Kaiser Convention Center, Oakland | n/a (he played Drums, not Ollin Arageed, per source) |
| gd-1990-12-27 | Oakland-Alameda County Coliseum Arena | n/a (Drums only, per source) |
| gd-1990-12-31 | Oakland-Alameda County Coliseum Arena | n/a (Drums only, per source) |
| gd-1992-02-23 | Oakland-Alameda County Coliseum Arena | n/a (Drums only, per source) |

(`gd-1992-02-23` has two `show_performers.csv` rows for El Din — percussion
and vocals — from the same JerryBase event; see the note on that show below.)

## Egypt, September 1978: how the trip and the choir came together

The band played three nights at the Sound and Light Theatre on the Giza
plateau, September 14–16, 1978, released thirty years later as *Rocking the
Cradle: Egypt 1978* (2CD/DVD, September 30, 2008). Manager Richard Loren
organized the trip with Phil Lesh and Alan Trist after Jefferson Airplane's
Marty Balin planted the idea of playing Egypt; Mickey Hart's role was
bringing in the music, not the logistics.

Hart's contribution was Hamza El Din. El Din opened the first set on
September 14 and 15 with his own composition "Ollin Arageed," backed by
students of his Abu Simbel school and a group he arranged specially for the
trip — the Nubian Youth Choir, singers, dancers, and hand-clappers who gave
the piece its call-and-response, hand-clap texture. On the third night,
September 16, the piece moved to open the *second* set instead of the first
— that was also the night of a total lunar eclipse during the show, and the
night Bill Kreutzmann played with a broken wrist in a cast after a horseback
riding accident.

Scholar Nicholas G. Meriwether, quoted in a 2023 retrospective, frames the
choice to share a stage with El Din as the band "aligning themselves with
the most dispossessed" — a reference to the Nubian displacement from the
Aswan Dam flooding, including El Din's own home village.

**Data oddity:** `performances.csv` has an `ollin-arageed` row for
September 14 and 15 (both `-1-1`, the set-one opener) but **no `ollin-arageed`
performance row at all for September 16**, even though the Wikipedia article
for the release, the dead.net song-tag page for "Ollin Arageed," and The
National's 2023 retrospective all independently state he played it that
night too (as the set-two opener). This looks like a gap in the catalog's
normalized setlist for that show, not a case of him skipping the song. Held
out of `performance_performers.csv` because the contract requires an
existing `performance_id`, but flagged here since it's the one Egypt night
without a matching row.

## Winterland, October 1978: the homecoming

The Dead played a "From Egypt With Love" run at Winterland that October, and
dead.net's release-info page for the 2008 set says El Din "joined the Dead
for versions of 'Ollin Arageed'... at two of the concerts" — matching the
catalog's two Winterland guest credits, October 21 and 22. Both shows carry
an `ollin-arageed-1-1` performance row (again the set-one opener), and both
get a row here. A dead.net photo feature titled "Mickey Hart with Hamza
El-Din" is dated 10/22/1978, presumably from this run; it's caption-only, no
narrative text, so it's linked as show-level context rather than quoted.

## The recurring pattern, 1978–1992: Drums into Ollin Arageed

After Egypt and Winterland, El Din kept coming back — 11 more shows over 14
years, all clustered in the Bay Area or on the fall '78 tour, all playing
Ollin Arageed as an extension of the Drums segment rather than as a
stand-alone opener. Grateful Dead of the Day's guest-appearance page for
Hamza El Din is the best single source for which segment he played at each
date; it independently confirms 9 of the catalog's 15 dates and gives
song-level detail for most of them:

- **1978-11-24, Capitol Theatre:** Drums > Ollin Arageed > Fire on the
  Mountain. All three performance rows are written — this is the fullest
  documented sequence outside Egypt/Winterland.
- **1979-08-05, Oakland Auditorium:** Ollin Arageed (out of Drums).
- **1985-03-13, Berkeley Community Theater:** Drums > Ollin Arageed > Man
  Smart, Woman Smarter.
- **1986-12-30, Kaiser Convention Center:** Drums > Ollin Arageed per the
  source, but **`performances.csv` has no `ollin-arageed` row for this
  show** — only `drums-2-7` exists. Wrote the Drums row; held Ollin Arageed
  as a data gap, same shape as the September 16, 1978 gap above. Worth
  noting this was a night the Neville Brothers' rhythm section also sat in
  (Art Neville, Charles Neville, Brian Stoltz, Willie Green, Jose Lorenzo,
  all in the same JerryBase guest list) — a busy sit-in night, not unique to
  El Din.
- **1988-03-17, Kaiser Convention Center:** Drums only, per the source.
- **1990-12-27 and 1990-12-31, Oakland Coliseum Arena:** Drums only at both,
  per the source. Branford Marsalis also guested on 12/31, elsewhere in the
  set.
- **1992-02-23, Oakland Coliseum Arena:** Daily Dose Of The Dead's recap
  names "an inspired Drums featuring Hamza El-Din" following Playing in the
  Band into Terrapin Station — this appears to be one of his last sit-ins
  with the band. JerryBase's raw snapshot lists his instrument as "vocals,
  percussion" for this show, but no source names a song where he sang;
  wrote the Drums row as percussion only and left the vocal credit
  unconfirmed.

## Held out / unresolved

- **gd-1978-09-16 Ollin Arageed** — performance_id doesn't exist in
  `performances.csv` (see above). Show-level credit stands; song-level
  credit blocked on the missing row.
- **gd-1978-12-30, Pauley Pavilion (UCLA)** — JerryBase credits him as a
  guest, and the catalog's own setlist has a `drums-2-8` into
  `ollin-arageed-2-9` sequence that matches the pattern from every other
  1978 date, but no independent source was found that names a song for
  this specific show. Grateful Dead of the Day's guest log for El Din does
  not include this date at all. Held rather than inferred from pattern
  alone, per the contract's rule that a song-level row needs a source that
  names the song.
- **gd-1986-12-30 Ollin Arageed** — data gap, see above.
- **gd-1988-02-16, Kaiser Convention Center** — JerryBase-only guest credit;
  no independent source names a song, and Grateful Dead of the Day's guest
  log for El Din does not list this date either. Held entirely (show-level
  credit only).
- **gd-1992-02-23 vocals** — JerryBase's raw snapshot instrument field says
  "vocals, percussion," but the one narrative source found for this show
  names only Drums and doesn't mention singing. Left as a show-level detail
  rather than a song row.

## Data oddities noticed (not fixed, per contract)

- Two `performances.csv` shows in this slice are missing an `ollin-arageed`
  row that every available narrative source says happened:
  September 16, 1978, and December 30, 1986. Both are third-or-later dates
  in a run where the first date(s) do have the row, which suggests the
  normalization may have deduplicated or dropped a repeat performance_id
  rather than a real absence.
- `gd-1988-02-16`'s setlist has two separate `drums` performance rows
  (`drums-2-1` and `drums-2-6`), which is unusual — Drums normally appears
  once per show, later in the second set. Not investigated further; noted
  here in case it affects other guest-credit work on that show.

## Sources

- Wikipedia, ["Rocking the Cradle: Egypt
  1978"](https://en.wikipedia.org/wiki/Rocking_the_Cradle:_Egypt_1978)
- Wikipedia, ["Hamza El Din"](https://en.wikipedia.org/wiki/Hamza_El_Din)
- dead.net, ["Ollin Arageed" song tag page](https://www.dead.net/taxonomy/term/1873)
- dead.net, ["Rocking the Cradle: Grateful Dead, Egypt
  1978"](https://www.dead.net/features/release-info/rocking-cradle-grateful-dead-egypt-1978)
- dead.net, ["Mickey Hart with Hamza
  El-Din"](https://www.dead.net/features/mickey-hart-hamza-el-din) (photo
  feature, 10/22/1978)
- Grateful Dead of the Day, [guest page for Hamza El
  Din](https://gratefuldeadoftheday.com/guest/hamza-el-din/)
- Daily Dose Of The Dead, ["Today In Grateful Dead History: February 23,
  1992"](https://dailydoseofdead.wordpress.com/2016/02/23/today-in-grateful-dead-history-february-23-1992-oakland-alameda-county-coliseum-arena/)
- The National, ["At the foot of ancient power: The Grateful Dead's 1978
  Egypt shows
  revisited"](https://www.thenationalnews.com/weekend/2023/09/15/at-the-foot-of-ancient-power-the-grateful-deads-1978-egypt-shows-revisited/)
  (2023-09-15)
- `data/raw/performers/jerrybase-{1978,1979,1985,1986,1988,1990,1992}.jsonl`
  (existing snapshots, for show-level guest confirmation and instrument
  fields)
