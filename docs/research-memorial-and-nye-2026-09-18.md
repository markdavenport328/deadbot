# Three famous guest nights: research notes

Compiled 2026-09-18 for the same "songs, not shows" pass that PR #49 did for
Carlos Santana. This slice covers three well-known guest nights: the Bill
Graham memorial free concert (1991-11-03), the two Etta James/Tower of Power
nights at Oakland's New Year's run (1982-12-30 and 12-31), and the Joan Baez
benefit and NYE nights (1981-12-12 and 12-31, with a look at 1980-01-13).

## What the catalog knew before this pass

`show_performers.csv` already credited these guests at these shows (all from
JerryBase, show-level only):

| Show | Venue | Guests already on the show row |
|---|---|---|
| gd-1991-11-03 | Polo Field, Golden Gate Park | John Fogerty, Neil Young, John Popper |
| gd-1982-12-30 | Oakland Auditorium | Etta James, Emilio Castillo, Greg Adams, Marc Russo, Stephen Kupka |
| gd-1982-12-31 | Oakland Auditorium | Etta James, Emilio Castillo, Greg Adams, Marc Russo, Stephen Kupka, Mic Gillette, John Cipollina, Matthew Kelly |
| gd-1981-12-12 | Fiesta Hall, San Mateo | Joan Baez, Matthew Kelly |
| gd-1981-12-31 | Oakland Auditorium | Joan Baez, John Cipollina, Matthew Kelly |
| gd-1980-01-13 | Oakland Coliseum Arena | Joan Baez (plus Santana, Cipollina, Errico — covered in the 2026-09-14 pass) |
| gd-1966-07-16 | (Jefferson Airplane sit-in show) | Joan Baez, Jorma Kaukonen, Marty Balin, Paul Kantner, Grace Slick, Jack Casady |

This pass turned the first six rows into song-level credits (66 rows across
five shows, plus one row at 1980-01-13). 1966-07-16 was skipped per the
contract; no source surfaced with per-song evidence for it either, so that
call held.

## 1991-11-03, Polo Field, Golden Gate Park: the Bill Graham memorial

Bill Graham, his companion Melissa Gold, and pilot Steve Kahn died in a
helicopter crash on 1991-10-25, returning from a Huey Lewis show at Concord
Pavilion. Bill Graham Presents staff put together a free tribute, "Laughter,
Love and Music," at the Polo Field in Golden Gate Park eight days later.
Estimates run as high as 300,000 people; dead.net commenters describe the
field already holding roughly 10,000 people at the start of the day and
filling continuously after that. The bill also included Santana, Journey (a
reunion), Crosby Stills Nash & Young, John Fogerty, Los Lobos and Jackson
Browne — most of them artists Graham had discovered or promoted early.

The Grateful Dead's own set: Hell In A Bucket, China Cat Sunflower > I Know
You Rider, Wang Dang Doodle, Born On The Bayou, Green River, Bad Moon Rising,
Proud Mary, Truckin' > The Other One > Wharf Rat > Sunshine Daydream, encore
Forever Young > Touch Of Grey.

- **John Fogerty** sang and played guitar on his four old Creedence
  Clearwater Revival songs: **Born On The Bayou**, **Green River**, **Bad
  Moon Rising** and **Proud Mary**. Catalog IDs: `gd-1991-11-03-born-on-the-
  bayou-1-5` through `-proud-mary-1-8`.
- **Neil Young** joined for the encore, his own **Forever Young**, on guitar
  and vocal. Catalog ID: `gd-1991-11-03-forever-young-2-1`. No source
  supports him on anything else that day — the "and others" in some fan
  shorthand for this show refers to the day's lineup of guests generally
  (Fogerty, Popper, Young), not additional songs for Young himself. Treat
  Forever Young as his only sourced song.
- **John Popper** (Blues Traveler) sat in on harmonica for **Wang Dang
  Doodle** only. Catalog ID: `gd-1991-11-03-wang-dang-doodle-1-4`.
- Sources agree closely: setlist.fm's footnotes, JamBase's "Grateful Dead
  Legends Team For Bill Graham Tribute" (which also covers the 1991-10-27
  Oakland show, already a resource in the catalog), and Live For Live Music's
  recap all give the same four Fogerty songs and the same one Young song.

Keep this show distinct from 1991-10-27 (Oakland Coliseum, two days after
Graham died, Santana and Gary Duncan sitting in) — the existing JamBase
resource covers both events and is now linked to both shows.

## 1982-12-30 and 12-31, Oakland Auditorium: Etta James and the Tower of Power horns

Both nights were part of the Dead's New Year's run at the Oakland
Auditorium. Etta James and the Tower of Power horn section (Emilio Castillo,
Greg Adams, Marc Russo, Stephen Kupka, and on 12-31 also Mic Gillette) sat in
on both nights, but for different amounts of the show.

### 12-30: a two-song encore

The Hard To Handle > Tell Mama encore was Pigpen's old Hard To Handle sung
live for the first time since 1971, and Etta James's own Tell Mama making
its live debut with the band. Grateful Dead of the Day calls Hard To Handle
"funk-filled with the horns just killing it" and Tell Mama a "smoking
version" with Tower of Power blowing — naming the horns on both songs.
Catalog IDs: `gd-1982-12-30-hard-to-handle-3-1`, `gd-1982-12-30-tell-mama-3-2`.
No Cipollina or Kelly guest row exists for this night; the show_performers
guest list for 12-30 has only Etta James and four of the five horn players
(no Mic Gillette that night).

### 12-31: a full five-song third set, plus Cipollina and Kelly earlier

The third set was a dedicated Pigpen-tribute run: **Turn On Your Lovelight**,
**Tell Mama**, **Baby What You Want Me To Do**, **Hard To Handle**, **In The
Midnight Hour**. setlist.fm footnotes all five to Etta James. A Hooterollin'
Around post about an unidentified extra percussionist that night says
directly that the horns "performed five R&B songs" — the same five — so the
Tower of Power credits ride on that post plus the JerryBase show-level list,
rather than a per-song setlist.fm footnote (setlist.fm doesn't footnote the
horns by name, only Etta). Catalog IDs: `gd-1982-12-31-turn-on-your-
lovelight-3-1`, `-tell-mama-3-2`, `-baby-what-you-want-me-to-do-3-3`, `-hard-
to-handle-3-4`, `-midnight-hour-3-5`.

Earlier in the show, two other guests already on the show-level row got
song-level credits from the same setlist.fm footnotes:
- **John Cipollina** (guitar) on **Not Fade Away**, **Deal** and **Sunshine
  Daydream**, closing the second set.
- **Matthew Kelly** (harmonica) on **C.C. Rider**, opening the first set.

### The mystery percussionist

The Hooterollin' post spends most of its length on an unidentified musician
playing timbale-style percussion alongside the horns all five songs —
described as "a wiry white guy, about 40ish, long sideburns but losing his
hair on top" — and never resolves who he was, though a commenter suggests
David Garibaldi, Tower of Power's regular drummer. No row was added for him;
the identification is a guess, not a source.

## 1981-12-12 and 12-31: Joan Baez, and the aborted Baez/Dead album

Joan Baez and Mickey Hart were a couple through 1981, and the relationship
put Baez in front of the Dead twice that December — first at a small benefit
in San Mateo, then during the New Year's run in Oakland. The band had also
been recording an album of Baez's original material behind the scenes.
Sometime in 1982, Baez and Hart broke up, the album was shelved, and by all
accounts everyone let the collaboration drop; it was never released.

### 1981-12-12, Fiesta Hall, San Mateo: Dance For Disarmament

Billed as "Joan Baez & Friends — Dance For Disarmament," this was a nuclear-
disarmament benefit at a hall holding about 2,000 people — tiny by the
Dead's standards. Opening act High Noon (Merl Saunders, Mickey Hart, Michael
Hinton, Jim McPherson, Chuck Rainey) was joined by Bill Kreutzmann on
percussion and later by Baez on vocals.

**The Dead backed Baez for an entire acoustic set** — eleven songs by
setlist.fm's count: Me And Bobby McGee, (For The) Children Of The Eighties,
Lucifer's Eyes, Warriors Of The Sun, Bye Bye Love, Barbara Allen, Marriott
USA, Where Have All Our Heroes Gone, All My Love (Oh Boy), Lady Di And I,
and The Boxer. Most are her originals, several were show debuts, and Lost
Live Dead calls the set "a true musical low point for the band," blaming
Baez's overtly political new songs: "didactic politics do not often make for
good songs." Garcia reportedly walked off partway through Lady Di And I.

**None of these eleven songs exist as rows in the catalog's
`performances.csv` for this show** — see the data note below. The one Baez
song this pass could credit is her return for the closing encore, **It's All
Over Now, Baby Blue**, which the catalog does have. Catalog ID:
`gd-1981-12-12-it-s-all-over-now-baby-blue-2-1`.

### 1981-12-31, Oakland Auditorium: New Year's Eve

Baez, Matthew Kelly and John Cipollina all sat in, but on different parts of
the show. As at San Mateo, Baez opened with an acoustic set (Me And Bobby
McGee, Bye Bye Love, Lucifer's Eyes, Children Of The Eighties, Banks Of The
Ohio) that again has no rows in `performances.csv` — same gap, see below.
What the catalog does have, and setlist.fm footnotes to her:
- **It Must Have Been The Roses**, in the electric second set. Catalog ID:
  `gd-1981-12-31-it-must-have-been-the-roses-1-6`.
- **It's All Over Now, Baby Blue**, the closing encore — the same song she'd
  closed San Mateo with nineteen days earlier. Catalog ID: `gd-1981-12-31-
  it-s-all-over-now-baby-blue-3-4`.

The other two guests that night, both already on the show-level row, get
song-level credit from the same setlist.fm footnotes:
- **Matthew Kelly** (harmonica): C.C. Rider, Big Boss Man, Minglewood Blues,
  Iko Iko.
- **John Cipollina** (guitar): The Other One, Not Fade Away, Goin' Down The
  Road Feelin' Bad — a three-song run out of Drums/Space.

### 1980-01-13, Oakland Coliseum Arena: the Cambodian refugee benefit

The 2026-09-14 Santana pass already covered this Bill Graham benefit in
detail for Not Fade Away, Sugar Magnolia and the U.S. Blues encore. Joan
Baez also has a guest row here, and this pass found one specific credit for
her: after the Dead closed their own set with U.S. Blues, **Baez brought
every performer from the day back onstage to sing her song "Bridging The
Gap"** together — Lost Live Dead names this directly. That resolves a data
oddity the Santana doc flagged: `song-bridging-the-gap` looked like it might
be "a benefit-jam placeholder rather than a song" imported from gdshowsdb.
It is a real, named song, and the catalog's `gd-1980-01-13-bridging-the-gap-
2-2` slot is exactly that all-cast finale. Catalog ID for Baez's credit:
the same performance, `gd-1980-01-13-bridging-the-gap-2-2`.

No other song is sourced to Baez specifically at this show — she is one
voice among many on Bridging The Gap, and Amazing Grace (sung with the Beach
Boys and others) isn't in the catalog's performances table for this show at
all.

## What was deliberately left out

- **The entire acoustic Baez sets at 1981-12-12 and 1981-12-31** (eleven and
  five songs respectively) — no rows exist in `performances.csv` for these
  songs, so no performance_performers row can point at them. See the data
  note below; this is the single biggest gap this pass ran into.
- **1966-07-16.** Skipped per the contract; a quick check found nothing
  beyond the existing JerryBase show-level credit for any of the six guests
  (Baez, Kaukonen, Balin, Kantner, Slick, Casady) naming specific songs.
- **The Oakland 12-31-1982 mystery percussionist.** Plausibly David
  Garibaldi, not confirmed; no row added.
- **"Good Night Irene"** — a dead.net commenter recalls Etta James singing
  this on 12-31-1982, but it isn't in the catalog's setlist for that show and
  no second source corroborates it. Left out.
- **Neil Young on anything beyond Forever Young** at the 1991-11-03 memorial.
  No source names a second song for him.
- **CSNY's own performance** at the 1991-11-03 memorial (they played a
  separate set, per Live For Live Music) is out of scope — this catalog only
  tracks the Grateful Dead's own set.

## Data oddities noticed (not fixed here)

- **`performances.csv` is missing whole acoustic sets on two of the three
  Baez nights.** For `gd-1981-12-12`, the catalog has exactly the electric
  second set plus the closing encore (10 performances) and nothing from the
  acoustic first set where Baez actually sang eleven songs. For
  `gd-1981-12-31`, the catalog starts at Shakedown Street (the electric set)
  and has nothing from Baez's five-song acoustic opener. Both shows'
  gdshowsdb import apparently only captured the electric portion of the
  night. This caps how much of "which songs Baez sang with the band" this
  pass could actually attach to performance rows — most of her singing that
  winter isn't reachable until those acoustic sets get performance rows of
  their own.
- **`song-bridging-the-gap` is confirmed real**, not a placeholder — see the
  1980-01-13 section above. Worth removing the old hedge in the Santana
  research doc if anyone revisits it.
- **1982-12-30 has no Mic Gillette guest row** while 1982-12-31 does; both
  nights otherwise share the same four other Tower of Power horn players.
  Consistent with JerryBase and not something to "fix," just noted.

## Sources

setlist.fm (per-show setlist pages, footnoted to guests) for all five shows;
Lost Live Dead ("January 13, 1980 Oakland Coliseum Arena," "December 12,
1981 Fiesta Hall, San Mateo") for the Baez/Cambodia benefit story and the
Bridging The Gap finale; Grateful Dead of the Day (12-30-1982) and
Hooterollin' Around ("Unknown Percussionist, 3rd Set: December 31, 1982")
for the Etta James/Tower of Power nights; JamBase ("Grateful Dead Legends
Team For Bill Graham Tribute") and Live For Live Music for the 1991-11-03
memorial; dead.net community pages for crowd-size and reception color on
1991-11-03 and 1981-12-31.
