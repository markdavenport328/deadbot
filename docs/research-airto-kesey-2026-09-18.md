# Airto Moreira, Flora Purim, and Ken Kesey onstage with the Grateful Dead: research notes

Compiled 2026-09-18, following the shape of `research-santana-onstage-2026-09-14.md`. This
pass takes two recurring non-rock guests — Brazilian percussionist Airto Moreira (often with
his wife, vocalist Flora Purim) and novelist Ken Kesey — from show-level credits in
`show_performers.csv` to song-level credits in `performance_performers.csv`.

## What the catalog knows today

`show_performers.csv` credits guest rows at more shows than the contract's seed list named; a
grep for `airto|flora-purim|ken-kesey` turned up all of the following. Note `person-airto-moreira-complete-show`
is a JerryBase duplicate of `person-airto-moreira` for `gd-1982-05-28`, handled per the
contract by using the plain id.

**Ken Kesey** (5 shows): 1978-12-31, 1981-05-08, 1983-08-31, 1984-05-08, 1991-10-31.

**Airto Moreira** (12 shows): 1980-12-13, 1980-12-14, 1982-05-28, 1983-05-15, 1983-10-31,
1989-02-11, 1989-12-30, 1989-12-31, 1991-02-21, 1991-12-30, 1991-12-31, 1993-12-09.

**Flora Purim** (7 shows, all overlapping Airto's except one): 1980-12-13, 1980-12-14,
1981-08-27 (alone), 1982-05-28, 1983-05-15, 1989-02-11, 1993-12-09.

All rows are `source_key=jerrybase`, drawn from the `data/raw/performers/jerrybase-<year>.jsonl`
snapshots (JerryBase itself 403s from this sandbox). JerryBase's `instrument` field turned out
to be a rough guide rather than a per-show fact — see Data notes below.

## Ken Kesey, show by show

### 1978-12-31, Winterland (closing night)

Kesey rolled out the **Thunder Machine** — Mickey Hart's clanging percussion sculpture — during
**Drums**. Wikipedia's *Closing of Winterland* article and a LiveForLiveMusic feature both name
the instrument; JerryBase's guest list calls his instrument "harmonica," which does not match
either independent source for this night. Catalog id: `gd-1978-12-31-drums-2-6`. This show has
no separate `space` performance in the catalog (see Data notes) so the row stops at Drums.
Sources: en.wikipedia.org/wiki/The_Closing_of_Winterland; liveforlivemusic.com feature.

### 1981-05-08, Nassau Coliseum

Kesey played **harmonica** during **Drums**, per the JerryGarcia.com show page's own note ("*w/
Ken Kesey on harmonica"). Catalog id: `gd-1981-05-08-drums-2-5`. No source extends this to
Space or the U.S. Blues encore that closed the show, so it stops at Drums.
Source: jerrygarcia.com/show/1981-05-08-nassau-coliseum-uniondale-ny-usa/.

### 1983-08-31, Hult Center, Eugene (Kesey's home turf)

Kesey again played **harmonica**, this time "standing behind drums" during Drums into Space,
per Grateful Dead of the Day's show notes. Eugene is Kesey country — Pleasant Hill and the
Springfield Creamery, of the 1972 Field Trip benefits, are minutes away. Catalog id:
`gd-1983-08-31-drums-2-5`. Source: gratefuldeadoftheday.com/08-31-1983/.

### 1984-05-08, Hult Center, Eugene (same room, second visit)

Kesey brought the **Thunder Machine** back for **Drums**, per the JerryGarcia.com show note
("* w/ Ken Kesey and the Thunder Machine"). Catalog id: `gd-1984-05-08-drums-2-5`.
Source: jerrygarcia.com/show/1984-05-08-silva-hall-hult-center-eugene-or-usa/.

### 1991-10-31, Oakland Coliseum Arena (Halloween, the Bill Graham eulogy)

Six days after Bill Graham died in a helicopter crash on 1991-10-25, this was the band's first
show since. Mid-way through **Dark Star** — after the first verse — Kesey walked out in a black
suit and a black-plumed hat and delivered an impromptu spoken eulogy over the jam: memories of
Graham's kindness after Kesey's own son's death, building to a recitation of e.e. cummings'
"Buffalo Bill" poem, before the band moved on into Drums. Catalog id:
`gd-1991-10-31-dark-star-2-5`. The full transcript is archived at Speakola; Far Out Magazine
and dead.net's show comments corroborate the staging and timing. This is the best-documented
of the five Kesey appearances.
Sources: speakola.com/eulogy/for-bill-graham-promoter-grateful-dead-ken-kesey-1991;
faroutmagazine.co.uk/the-grateful-dead-eulogized-bill-graham-dark-star/;
dead.net/show/october-31-1991.

## Airto Moreira and Flora Purim, show by show

### 1980-12-13 and 1980-12-14, Long Beach Arena (back-to-back nights)

Both nights, Moreira and Purim sat in for **Drums**; the 12/13 show continues into **Space**
per Grateful Dead of the Day's guest index for both performers. A dead.net attendee, at their
first Dead show, called the Drums with Airto and Flora "mind blowing," alongside that night's
Not Fade Away. Catalog ids: `gd-1980-12-13-drums-2-4` and `-space-2-5`;
`gd-1980-12-14-drums-2-6`. Sources: gratefuldeadoftheday.com/guest/airto-moreira/ and
/guest/flora-purim/; dead.net/show/december-13-1980.

### 1982-05-28, Moscone Convention Center (Vietnam Veterans benefit)

A benefit that raised $175,000; Moreira, per contemporary coverage, "played the whole show,"
with Purim, John Cipollina, and Boz Scaggs joining for select songs. The only segment named by
a specific source is **Drums**, so only that row is entered; the "whole show" claim is recorded
here rather than turned into a row for every song, since no source names them individually.
Catalog id: `gd-1982-05-28-drums-1-7`. Purim's row uses `vocals` (per the catalog's existing
show-level instrument for her that night); Moreira's uses `drums`.
Sources: gratefuldeadoftheday.com/guest/airto-moreira/; dead.net/show/may-28-1982.

### 1983-05-15, Greek Theatre, UC Berkeley

Moreira and Purim both sat in for **Drums**. Catalog id: `gd-1983-05-15-drums-2-6`.
Source: gratefuldeadoftheday.com/guest/airto-moreira/ and /guest/flora-purim/.

### 1983-10-31, Marin Veterans Memorial Auditorium (Halloween)

Moreira joined for **Drums**. The same show carried the last Saint Stephen the band ever
played (after a 352-show hiatus, revived twice that October, closed out here); dead.net's show
page subtitle names both facts together ("With Airto Moreira - final 'St. Stephen'"), but no
source ties Moreira to Saint Stephen itself, so the row stops at Drums. Catalog id:
`gd-1983-10-31-drums-2-6`. Source: dead.net/show/october-31-1983.

### 1989-02-11, Great Western Forum

Moreira, Purim, and Diana Moreira (Airto and Flora's daughter, not in the catalog's people
table and out of this pass's scope) all sat in for **Drums**. Catalog id:
`gd-1989-02-11-drums-2-8`. This show's second set has an unusual Space > "I Will Take You
Home" > Drums > Space shape (see Data notes); the guest credit is for Drums specifically.
Sources: gratefuldeadoftheday.com/guest/airto-moreira/, /guest/flora-purim/;
dead.net/show/february-11-1989.

### 1989-12-30, Oakland Coliseum Arena — the biggest sit-in of the pass

A dead.net comment from Forrest George names the exact songs: Moreira sat in starting with
**Sugaree** and stayed through **Walkin' Blues, Jack-A-Roe, When I Paint My Masterpiece, West
L.A. Fadeaway,** and **The Music Never Stopped** to close set one, then rejoined for most of
set two, **China Cat Sunflower** through **One More Saturday Night** (including Drums and
Space). Grateful Dead of the Day's recording notes corroborate the same range and add an
honest caveat: he was "sometimes audible and often not." Sixteen performance rows are entered
for this show, one per named song, each carrying the same two citations. Catalog ids:
`gd-1989-12-30-sugaree-1-3` through `-the-music-never-stopped-1-8`, then
`-china-cat-sunflower-2-2` through `-one-more-saturday-night-2-11`.
Sources: dead.net/show/december-30-1989 (Forrest George comment);
gratefuldeadoftheday.com/12-30-1989/.

### 1989-12-31, Oakland Coliseum Arena (the very next night, New Year's Eve)

Grateful Dead of the Day's guest index names **Victim or the Crime, Dark Star, Drums** for
this show — a second, separate sit-in the night after the one above. Catalog ids:
`gd-1989-12-31-victim-or-the-crime-2-2`, `-dark-star-2-3`, `-drums-2-4`.
Source: gratefuldeadoftheday.com/guest/airto-moreira/.

### 1991-02-21, Oakland Coliseum Arena

The guest index names an unusually long run: **Uncle John's Band, Terrapin Station, Drums,
Eyes of the World, Throwing Stones, Not Fade Away** — most of set two around the Drums/Space
break. Catalog ids: `gd-1991-02-21-uncle-john-s-band-2-2`, `-terrapin-station-2-3`,
`-drums-2-5`, `-eyes-of-the-world-2-7`, `-throwing-stones-2-8`, `-not-fade-away-2-9`.
Source: gratefuldeadoftheday.com/guest/airto-moreira/.

### 1991-12-30, Oakland Coliseum Arena

Tape notes on Grateful Dead of the Day tag the jam before Drums as a **Dear Prudence** tease
(the catalog's setlist just calls it `song-jam`; see Data notes) and credit "Airto Moreira on
Drums and Vocals" through both it and Drums itself. Catalog ids: `gd-1991-12-30-jam-2-6`,
`-drums-2-7`. Source: gratefuldeadoftheday.com/12-30-1991/.

### 1991-12-31, Oakland Coliseum Arena

The guest index names **Not Fade Away** — the rare set-two opener that show — as Moreira's
credit. This is the thinnest citation in the pass: the show's own dead.net page carries no
supporting detail, and no second source was found. Entered because the index does name a
specific song, but flagged here as the weakest-sourced row. Catalog id:
`gd-1991-12-31-not-fade-away-2-1`. Source: gratefuldeadoftheday.com/guest/airto-moreira/.

### 1993-12-09, Los Angeles Sports Arena

Moreira and Purim sat in for **Drums**, and Ornette Coleman (out of this pass's scope) took
over for the rest of the show, per a dead.net attendee comment: "Airto and Flora Purim sat in
on Drums and then Ornette Coleman sat in for the remainder of the show." The guest index lists
this as "Drums> Space" for Moreira, but the eyewitness account only credits Drums before
Coleman's entrance; where the two disagree on scope, the narrower, corroborated claim (Drums
only) is what's entered. Catalog id: `gd-1993-12-09-drums-2-6`.
Sources: dead.net/show/december-9-1993; gratefuldeadoftheday.com/guest/airto-moreira/ and
/guest/flora-purim/.

### 1981-08-27, Long Beach Arena — Flora Purim alone

JerryBase credits Flora Purim (vocals) and a Michael Hinton (percussion, not in this catalog's
people table) as guests, with no Airto Moreira. No source found names a song or segment for
Purim that night — Grateful Dead of the Day's guest index for her does not include this date at
all. **Left out; unresolved.**

## What was deliberately left out

- **1981-08-27 Flora Purim.** No song-level source found; see above.
- **1982-05-28 Airto Moreira, "the whole show."** Sourced only in general terms; only the
  Drums row is entered (see above).
- **1983-10-31 Saint Stephen.** A dead.net page subtitle links Airto Moreira and the final
  Saint Stephen in the same sentence, but does not credit him on the song itself.
- **1993-12-09 Space.** Grateful Dead of the Day's guest index says "Drums> Space" but a
  first-hand dead.net account only places Moreira and Purim on Drums before Ornette Coleman
  arrives; kept out per the two-sources-disagree rule.
- **1991-12-31 Not Fade Away.** Entered despite thin sourcing (see above) since a specific
  source does name the song; flagged rather than held out, since the rule for holding a row out
  is either no song-naming source or disagreeing sources, neither of which quite applies here.
- **Ornette Coleman, Diana Moreira, Michael Hinton, John Cipollina, Boz Scaggs.** All appear in
  the same guest lists as this pass's two subjects but are out of scope for this slug.

## Data notes surfaced by the pass

- **JerryBase's `instrument` field for Kesey is inconsistent with independent sources at two of
  five shows.** It says "harmonica" for all four non-Halloween appearances (1978-12-31,
  1981-05-08, 1983-08-31, 1984-05-08), but two independent sources (Wikipedia, LiveForLiveMusic
  for 1978-12-31; JerryGarcia.com for 1984-05-08) say he played Mickey Hart's Thunder Machine,
  a percussion sculpture, at those two. The other two (1981-05-08, 1983-08-31) are
  independently confirmed as harmonica. JerryBase looks like it defaulted to Kesey's most
  common prop rather than checking each show.
- **`gd-1978-12-31` has no separate `space` performance** — only `song-drums` in set 2 — even
  though period sources describe a Drums/Space-style jam that night. Not changed here; noted
  as a possible gap in the imported setlist, same category as the 1980-01-13 gap noted in the
  Santana research doc.
- **`gd-1989-02-11` set 2 has an unusual shape**: `song-space` (2-6), then "I Will Take You
  Home" (2-7), then `song-drums` (2-8), then `song-space` again (2-9) — Space appears to
  bracket a song rather than the usual single Drums > Space block. Not changed here.
- **`gd-1982-05-28` has Drums and Space in set 1** (positions 7 and 8 of ten), not the usual
  second-set placement — this was a short single-set-plus-encore Vietnam Veterans benefit show,
  not a truncated import. Not changed here.
- **A second Moreira duplicate pattern.** Like Santana's plain-vs-`-complete-show` ids, JerryBase
  qualified Moreira's 1982-05-28 id with "(complete show)" specifically because period sources
  say he played essentially the entire first set that night — the qualifier tracks something
  real, not noise, even though the contract (correctly) says to fold it onto the plain id.
- **1991-12-30's "jam" performance is unlabeled** in the catalog (`song-jam`) but tape notes
  identify it as a Dear Prudence tease. Not renamed here; worth a follow-up pass across all
  `song-jam` performances to see how many carry an identifiable quote.
- **Diana Moreira and Michael Hinton** appear as guests in the JerryBase raw snapshots
  (1989-02-11 and 1981-08-27 respectively) but have no row in `people.csv` and are not
  addressed by this pass.

## Report-back summary

- Shows examined: 17 (5 Kesey, 12 Airto/Flora, counting 1980-12-13/14 and 1989-12-30/31 as
  separate nights).
- Performance rows written: 48 (5 Kesey, 36 Airto Moreira, 7 Flora Purim).
- Resources written: 17 new; 34 resource_performances links; 2 resource_shows links.
- Rows held out / unresolved: 1981-08-27 Flora Purim (no song source); 1982-05-28 Airto's
  "whole show" claim beyond Drums; 1983-10-31 Saint Stephen; 1993-12-09 Space (disagreement).
