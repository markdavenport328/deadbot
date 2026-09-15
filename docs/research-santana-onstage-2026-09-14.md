# Carlos Santana onstage with the Grateful Dead: research notes

Compiled 2026-09-14 for the "Best songs with Santana" question. The catalog
already lists Santana as a guest at seven shows (JerryBase). What it lacks is
song-level detail and any story. This file records what a web pass found, how
well each claim is sourced, and what could be added to the catalog.

## What the catalog knows today

`show_performers.csv` credits Carlos Santana (guitar, role `guest`) at:

| Show | Venue | Catalog setlist has the songs he played? |
|---|---|---|
| gd-1976-12-31 | Cow Palace, Daly City | yes, but which ones he played is unresolved (see below) |
| gd-1980-01-13 | Oakland Coliseum Arena | setlist incomplete in catalog (see data note) |
| gd-1987-08-22 | Calaveras County Fairgrounds | yes |
| gd-1987-08-23 | Calaveras County Fairgrounds | yes |
| gd-1991-04-28 | Sam Boyd Silver Bowl, Las Vegas | yes |
| gd-1991-10-27 | Oakland Coliseum Arena | yes |
| gd-1993-01-26 | Oakland Coliseum Arena | yes |

Guest credits are show-level, so the current answer can only name shows. The
performance IDs below are the ones a song-level credit would attach to.

## The seven nights, song by song

### 1976-12-31, Cow Palace (New Year's Eve)

- Santana's band opened (78-minute set, broadcast live on KSAN along with the
  Dead's sets). Santanamigos has the opening set.
- **Which Dead songs he played on: unresolved.** JerryBase credits him as a
  guest, and a dead.net attendee comment says Garcia and Santana "played at
  the same time on many songs," but setlist.fm, dead.net, the archive.org
  item notes, and the Wikipedia page for *Live at the Cow Palace* carry no
  per-song credit. The official release's personnel list names only the seven
  band members. Treat any per-song claim for this night as unconfirmed until
  someone listens to the release or checks DeadBase / Deadlists comments.
- Official release: *Live at the Cow Palace: New Year's Eve 1976* (Rhino,
  2007), the complete show. This is the only Santana night with an official
  release.
- Reception: widely called one of the strongest-played nights of 1976; the
  Slipknot! jam and Morning Dew get singled out.
- Sources: dead.net show page; setlist.fm; Wikipedia *Live at the Cow Palace*;
  ArchiveGrid (KSAN broadcast reel); santanamigos.com/19761231.htm.

### 1980-01-13, Oakland Coliseum Arena (Cambodian refugee benefit)

- Bill Graham benefit prompted by Joan Baez. Bill: Grateful Dead, Beach Boys,
  Jefferson Starship, Joan Baez, Santana. KSAN broadcast, the station's last
  Dead broadcast before it flipped to country later that year. The Dead's set
  ran about 90 minutes, unusually short for an indoor headline.
- **Songs:** Santana and John Cipollina (Quicksilver) both joined on
  **Not Fade Away** and **Sugar Magnolia**. Greg Errico (Sly and the Family
  Stone) sat in on the U.S. Blues encore. Sourcing: Lost Live Dead (Corry
  Arnold), corroborated by JerryBase's guest list and a Discogs bootleg titled
  "Grateful Dead Featuring Carlos Santana."
- Catalog performance IDs: `gd-1980-01-13-not-fade-away-*` and
  `gd-1980-01-13-sugar-magnolia-*` (set 1, positions 9 and 10).
- No official release.
- Sources: lostlivedead.blogspot.com/2014/12/january-13-1980-oakland-coliseum-arena.html;
  discogs.com/release/4691474.

### 1987-08-22 and 08-23, Calaveras County Fairgrounds (Mountain Aire II)

- Santana's band and David Lindley and El Rayo-X opened both days.
- **8/22 songs:** **Good Morning Little School Girl** and **In the Midnight
  Hour**, closing the first set. School Girl was a bust-out: first time played
  since 1970-09-19. Catalog IDs: set 1 positions 9 and 10.
- **8/23 songs:** **Iko Iko** and **All Along the Watchtower**, closing the
  first set. Catalog IDs: set 1 positions 8 and 9. The Grateful Dead's
  official account described him "cranking solos right alongside Jerry Garcia."
- A clip of the 8/22 School Girl circulates on YouTube and is the usual visual
  reference for this pairing.
- Santana has since said Calaveras 1987 was the first time he performed
  *with* the Dead, which conflicts with the 1976 and 1980 credits above. His
  recollection is probably counting the shows where he was clearly featured;
  JerryBase's earlier credits stand.
- No official release. Charlie Miller UltraMatrix soundboards for both nights
  are in the catalog's `recordings.csv`.
- Sources: setlist.fm pages for both dates; x.com/GratefulDead/status/1827045150960603175;
  dailydoseofdead.wordpress.com (2019-08-23 entry).

### 1991-04-28, Sam Boyd Silver Bowl, Las Vegas

- Santana's band opened. Two sold-out nights (4/27, 4/28) at 39,000 each, the
  first time the stadium hit capacity for anyone.
- **Song:** an extended **Bird Song** closing the first set, around 17 to 18
  minutes. Catalog ID: `gd-1991-04-28-bird-song` (set 1 position 7).
- Anecdote: an attendee on dead.net recalls Santana standing center stage,
  head bowed and hands clasped as if praying, through the first verses before
  he played a note.
- Reception is split. Grateful Dead of the Day calls it "matching Garcia and
  then raising him"; dead.net commenters say "nice but he could have opened it
  up a little more" and "it seemed a bit forced"; a gratefuldeadoftheday
  commenter says he "didn't add much." Worth saying honestly in an answer:
  fans disagree about this one.
- Did he play the Box of Rain encore? No source credits him; treat as no.
- No official release (the 1991 pick in *30 Trips Around the Sun* is 9/10/91
  MSG).
- Sources: dead.net/show/april-28-1991; gratefuldeadoftheday.com/04-28-1991/;
  jerrygarcia.com show page.

### 1991-10-27, Oakland Coliseum Arena (two days after Bill Graham died)

- Graham died in a helicopter crash on 1991-10-25. This was the Dead's first
  show afterward. David Graham spoke to the crowd before the show; lighters
  came out.
- **Songs:** Santana and **Gary Duncan** (Quicksilver, his first Dead sit-in
  since 1972) joined for **Iko Iko > Mona**, four San Francisco guitarists
  trading off. Catalog IDs: set 2 positions 5 and 6 (`iko-iko`, `mona`), and
  plausibly the `jam` at position 7 that follows.
- Keep this distinct from the formal Graham memorial, "Laughter, Love and
  Music," Polo Fields, Golden Gate Park, 1991-11-03, where Santana, the Dead,
  CSNY, Journey, John Fogerty and others played to roughly 300,000. That
  event is not a Grateful Dead show in the catalog.
- No official release.
- Sources: jambase.com "Grateful Dead legends team for Bill Graham tribute";
  dead.net/show/october-27-1991; setlist.fm.

### 1993-01-26, Oakland Coliseum Arena (Chinese New Year run)

- The best-storied of the seven. A dragon parade moved through the crowd
  during Drums for the Year of the Rooster.
- **Songs:** Santana came out after Space and stayed for the rest of the set:
  **The Other One > Stella Blue > Turn On Your Lovelight**, then the
  **Gloria** encore. Catalog IDs: set 2 positions 8, 9, 10 and set 3 position 1.
- Anecdote: Santana did not know Stella Blue. Video shows Bob Weir leaning in
  repeatedly during the song to walk him through what was coming. He plays
  tentatively at first, then finds his footing by the end. JamBase: he
  "gained his bearings towards the end of 'Stella Blue' and unleashed a flurry
  of potent riffs." That Stella Blue is the moment most often cited from the
  night.
- This was Santana's last sit-in with the Grateful Dead.
- No official release.
- Sources: jambase.com/article/grateful-dead-carlos-santana-oakland-1993;
  jambase.com/article/grateful-dead-carlos-santana-stella-blue-1993-video
  (video via the LoloYodel channel); dead.net/show/january-26-1993.

## Listening shortlist for the answer

Ranked by how much Santana is actually audible and how good the tape is.

1. **1993-01-26 The Other One > Stella Blue > Lovelight, Gloria.** Longest
   stretch, best story, Weir coaching him live.
2. **1987-08-23 Iko Iko, All Along the Watchtower.** Clear, featured, good
   Miller soundboard.
3. **1987-08-22 Good Morning Little School Girl, Midnight Hour.** The
   bust-out. Video exists.
4. **1991-10-27 Iko Iko > Mona.** Four-guitar front line with Gary Duncan, in
   the shadow of Graham's death.
5. **1991-04-28 Bird Song.** Long and contested; say so.
6. **1980-01-13 Not Fade Away, Sugar Magnolia.** Santana plus Cipollina;
   good FM and Miller sources exist.
7. **1976-12-31.** Only official release, but where he plays is not pinned
   down.

## How the collaboration happened

- **Bill Graham is the through-line.** Graham met Garcia at the Acid Tests in
  1965. He met Santana in 1967 when Santana and a friend climbed a drainpipe
  to get into the Fillmore for Paul Butterfield. Graham became Santana's
  manager and put the unrecorded band on Dead bills: Fillmore West late
  August 1968 (the Lee Conklin poster art later became the cover of Santana's
  debut), Winterland New Year's Eve 1968, Robertson Gym UC Santa Barbara
  1969-01-17, Family Dog on the Great Highway 1970-02-04 (filmed for PBS as
  "A Night at the Family Dog"). Santana, 1976: "Fortunately, I have Bill
  Graham at my side. He's like an older brother." Graham also produced the
  1980 benefit, and the 1991-10-27 sit-in came two days after his death.
  Source: Harvey Kubernik, "San Francisco Nights" (Cave Hollywood, 1976
  interviews republished 2012); rrauction poster lot notes; Lost Live Dead.
- **Woodstock, August 1969.** Santana's own account, in *The Universal Tone*
  and many interviews: Garcia handed him mescaline (some retellings say LSD)
  backstage, the set got moved up, and he played "Soul Sacrifice" while the
  guitar neck felt like a snake. He tells it fondly. Source: JamBase
  "Carlos Santana Reveals Favorite Woodstock Memory"; MusicRadar excerpt.
- **1969-05-11, Aztec Bowl, San Diego State.** Garcia announced "Santana's
  drummers want to sit in," and Santana's percussionists joined the Dead for
  a percussion jam into Lovelight. Contemporary *Daily Aztec* review (Bob
  Melton, 1969-05-13). This is the band's percussion section, not Carlos on
  guitar; do not count it as a Carlos Santana appearance. The shared bills in
  1968 and 1969 show no evidence of a sit-in.
- **Garcia on Santana, 1976:** "Carlos has developed himself into a spiritual
  being from a completely different kind of person." (Kubernik.)
- **Santana on playing with Garcia:** "He'd go up and down; I'd go left and
  right. And I could tell he enjoyed it because the Dead always invited me
  back." (Newsweek, "Come Along, or Go Alone: Jerry Garcia's Collaborations,"
  2015.) And: "Jerry was the Sun of the Grateful Dead – the music they played
  was like planets orbiting around him." (Rolling Stone essay, via Far Out.)
- **The reverse direction.** 1988-01-23, Henry J. Kaiser, Oakland: "Carlos
  Santana and Friends," a benefit for Medical Aid to El Salvador. Garcia and
  Weir joined Santana, Tower of Power, Wayne Shorter, Armando Peraza, Bonnie
  Raitt and Boz Scaggs. Corry Arnold calls Garcia and Weir "great foils" for
  Santana. 1989-08-02, Hollywood Roosevelt Hotel: Garcia joined Santana and
  Rubén Blades for a taped "Latino Session." Both are Garcia side
  appearances, not Dead shows; the Kaiser show is already a resource in the
  catalog (Lost Live Dead post).
- **Mickey Hart link.** Hart and Santana share the Babatunde Olatunji circle
  (Santana's "Jingo" is an Olatunji tune; Hart recorded with Olatunji). A
  GDAO photo from 1987-02-15 shows Santana, Garcia, Olatunji and Hart
  together. Source: gdao.org/items/show/835481.
- **After Garcia.** On 1995-08-09 Santana called Garcia "a profound talent"
  and offered "To live is to dream. To die is to awaken." (Seattle Times
  roundup.) Santana sat in with Phil Lesh and Friends at Lockn' on 2015-09-12
  (Fire on the Mountain with Warren Haynes). He did not play Fare Thee Well.
  In 2021 he jammed with Bill Kreutzmann and said "I just close my eyes and
  imagine Jerry Garcia next to me." (Ft. Myers Magazine, Sept/Oct 2021.)

## Things to keep out of the answer

- A JamBase all-guests compilation lists Santana on Drums 1989-02-12 (Great
  Western Forum). That night's drum guest was Yoshikazu Fujimoto of Kodo, with
  Bob Dylan and Spencer Davis as the other guests. Confirmed wrong.
- Any claim that Santana jammed with the Dead at UC Santa Barbara 1969 or
  Winterland 1968. Shared bills only.
- Conflating 1991-10-27 (Dead show, Santana sat in) with 1991-11-03 (Graham
  memorial in the park).

## Catalog notes and possible follow-ups

- **Song-level guest credits now have a home.** Schema version 10 added
  `performance_performers` (2026-09-14) and the songs above were entered for
  six of the seven nights, with the anecdotes as `resource_performances`
  rows. See `docs/collection-status-guest-song-credits.md` for what went in
  and what was left out.
- **gd-1980-01-13 setlist looks incomplete.** The catalog has ten set 1 songs
  plus a set 2 of `u-s-blues` and `bridging-the-gap`. Sources describe one
  90-minute set plus a U.S. Blues encore. "Bridging the Gap" may be a
  benefit-jam label imported from gdshowsdb and is worth checking.
- **Resources worth adding:** the two JamBase 1993 pieces, the Grateful Dead
  of the Day 1991-04-28 page, and the Kubernik "San Francisco Nights" piece
  as a person-level resource. The Lost Live Dead posts for 1980-01-13 and the
  1988 Kaiser show are already resources; the 1980 one is linked to its show
  row, but neither is linked to Santana as a person, and there is no
  person-level resource table to do it with.
- **Santana's own opening sets** are outside the catalog's scope but the
  santanamigos.com date pages are a clean source if "who opened" ever becomes
  a field.
