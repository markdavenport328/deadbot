# Ornette Coleman and David Murray onstage with the Grateful Dead: research notes

Compiled 2026-09-18 for the jazz-horns slice of the guest song-credit pass. The
catalog already lists Ornette Coleman as a guest at two shows and David Murray
at two shows (JerryBase). What it lacked was song-level detail and the story
behind each sit-in. This file records what a web pass found, how well each
claim is sourced, and what went into `performance_performers.csv`.

## What the catalog knows today

`show_performers.csv` credits, all as guest/saxophone:

| Person | Show | Venue |
|---|---|---|
| Ornette Coleman | gd-1993-02-23 | Oakland-Alameda County Coliseum Arena |
| Ornette Coleman | gd-1993-12-09 | Los Angeles Sports Arena |
| David Murray | gd-1993-09-22 | Madison Square Garden |
| David Murray | gd-1995-02-26 | Oakland-Alameda County Coliseum Arena |

The JerryBase raw snapshots (`data/raw/performers/jerrybase-1993.jsonl`,
`jerrybase-1995.jsonl`) also list same-night guests outside this slice's
scope: Denardo Coleman (drums) and, per some sources, Graham Wiggins
(didgeridoo) and Sikiru Adepoju (percussion) on 1993-02-23; Airto Moreira
(drums) and Flora Purim (vocals) on 1993-12-09; James Cotton (harmonica) on
1993-09-22; Sikiru Adepoju (talking drum) on 1995-02-26. Those people already
have `person_id`s were they to get song-level rows, but the contract for this
slice is the two saxophonists, so no rows were added for them here — they
stay show-level.

Both `person-ornette-coleman` and `person-david-murray` already exist in
`people.csv` with plain, non-`-complete-show` ids. No `people.csv` staging
file was needed.

## The four nights, song by song

### 1993-02-23, Oakland-Alameda County Coliseum Arena (Mardi Gras)

Ornette Coleman and Prime Time opened the show. Coleman's set closed with
Garcia joining him for the last song, then Coleman stayed onstage as the Dead
took over.

- **Confirmed songs:** Space, The Other One, Stella Blue, Turn On Your
  Lovelight (set 2, positions 7-10). Two independent sources agree exactly:
  JamBase's "Throwback Thursday" recap and setlist.fm's setlist for the date.
  Catalog IDs: `gd-1993-02-23-space-2-7`, `gd-1993-02-23-the-other-one-2-8`,
  `gd-1993-02-23-stella-blue-2-9`, `gd-1993-02-23-turn-on-your-lovelight-2-10`.
- **Disputed: Brokedown Palace.** A 2009 Exile on Moan Street repost lists a
  fifth song, the Brokedown Palace encore, as part of Coleman's sit-in. No
  other source (JamBase, setlist.fm, Grateful Dead of the Day, Ultimate
  Classic Rock) credits him on it. Kept out per the two-sources-disagree
  rule; both claims are recorded here.
- **Story:** Grateful Dead of the Day's write-up for the date notes that
  Garcia played on Coleman's own closing song before the roles reversed and
  Coleman joined the Dead. This is the pass the Virgin Beauty relationship
  had been building toward for five years (see "How the collaboration
  happened" below).
- No official release.
- Sources: jambase.com/article/throwback-thursday-ornette-coleman-joins-grateful-dead;
  setlist.fm/setlist/grateful-dead/1993/oakland-alameda-county-coliseum-arena-oakland-ca-13d601a1.html;
  gratefuldeadoftheday.com/02-23-1993/; exileonmoanstreet.blogspot.com/2009/04/repost-ornette-coleman-grateful-dead.html;
  ultimateclassicrock.com/ornette-coleman-grateful-dead/.

### 1993-12-09, Los Angeles Sports Arena

Coleman's second and last sit-in of 1993, and his final appearance with the
Grateful Dead.

- **Confirmed songs:** Space, The Other One, Wharf Rat, Turn On Your Lovelight
  (set 2, positions 7-10). Again two independent sources agree exactly:
  JamBase and setlist.fm. Catalog IDs: `gd-1993-12-09-space-2-7`,
  `gd-1993-12-09-the-other-one-2-8`, `gd-1993-12-09-wharf-rat-2-9`,
  `gd-1993-12-09-turn-on-your-lovelight-2-10`.
- **Story:** Attendee comments on the dead.net show page describe a handoff:
  Airto Moreira and Flora Purim (not saxophonists, out of this slice's scope)
  sat in during Drums, then Coleman took over for the rest of the show
  starting with Space. One commenter, apparently disappointed to have missed
  a stronger show elsewhere in the run, allowed only "That counts!" about
  Coleman's participation.
- No official release.
- Sources: jambase.com/article/throwback-thursday-ornette-coleman-joins-grateful-dead;
  setlist.fm/setlist/grateful-dead/1993/los-angeles-sports-arena-los-angeles-ca-3bd60064.html;
  dead.net/show/december-9-1993.

### 1993-09-22, Madison Square Garden (final night of a six-night stand)

David Murray's only appearance with the Dead that year, and the one that led
to his tribute album.

- **Confirmed songs:** Bird Song (set 1, position 7, the set closer), then
  Easy Answers, Lazy River Road, Estimated Prophet, Dark Star, Space, Wharf
  Rat, Throwing Stones and Turn On Your Lovelight — essentially the entire
  second set. This is unusually well corroborated for a single night: JamBase
  names Bird Song and "Easy Answers and the rest of the set"; Grateful Dead
  of the Day's day-of review names Bird Song, Estimated Prophet, Dark Star and
  Wharf Rat by name with descriptive detail; the site's separate guest index
  for David Murray names Bird Song, Lazy River Road, Throwing Stones and Turn
  On Your Lovelight; and headyversion.com's fan version notes independently
  name Lazy River Road, Bird Song, Space, Dark Star, Throwing Stones, Wharf
  Rat and Turn On Your Lovelight. Between the four sources, every song from
  Bird Song through the second-set closer is named at least once, and no
  source contradicts any other. Catalog IDs: `gd-1993-09-22-bird-song-1-7`,
  `gd-1993-09-22-easy-answers-2-1`, `gd-1993-09-22-lazy-river-road-2-2`,
  `gd-1993-09-22-estimated-prophet-2-3`, `gd-1993-09-22-dark-star-2-4`,
  `gd-1993-09-22-space-2-6`, `gd-1993-09-22-wharf-rat-2-7`,
  `gd-1993-09-22-throwing-stones-2-8`,
  `gd-1993-09-22-turn-on-your-lovelight-2-9`.
- **Held out: Drums (set 2, position 5).** No source specifically names Murray
  on the drum duet itself; headyversion groups "Drums > Space" together but
  the descriptive language elsewhere in the same source attaches to Space,
  not Drums. Left as show-level for that performance.
- **The earpiece story.** Grateful Dead Hour no. 445 describes the band's
  in-ear monitor system, which let Weir, Garcia and Lesh cue Murray live
  during the set. Murray recalled it "laid it out for me like a blanket...
  opened it up for me and gave me all the room I wanted," and was struck by
  the crowd: "I could see bodies moving with my saxophone."
- **The Dark Star payoff.** Murray was "blown away" by the band and the
  audience's reaction that night (Music Box Online), and went on to record
  *Dark Star: The Music of the Grateful Dead* (1996) as a tribute to Garcia,
  featuring jazz arrangements of six Dead songs and a guest spot from Bob
  Weir on a track from a stage musical the two were developing together.
- No official release of this show, though a Charlie Miller soundboard
  circulates on archive.org.
- Sources: jambase.com/article/david-murray-joins-grateful-dead-at-msg-in-1993;
  gratefuldeadoftheday.com/09-22-1993/; gratefuldeadoftheday.com/guest/david-murray/;
  headyversion.com/show/234/grateful-dead/1993-09-22/;
  dead.net/features/gd-radio-hour/grateful-dead-hour-no-445;
  musicbox-online.com/dm-dark.html.

### 1995-02-26, Oakland-Alameda County Coliseum Arena (Mardi Gras run)

Murray's second and last sit-in with the Dead, at another Mardi Gras-themed
show, this time with his own group Octofunk opening.

- **Confirmed songs:** Estimated Prophet, Eyes of the World, Space, The Days
  Between, Not Fade Away (set 2, positions 5, 6, 8, 10, 11). setlist.fm tags
  each of these five individually "with David Murray." Catalog IDs:
  `gd-1995-02-26-estimated-prophet-2-5`, `gd-1995-02-26-eyes-of-the-world-2-6`,
  `gd-1995-02-26-space-2-8`, `gd-1995-02-26-the-days-between-2-10`,
  `gd-1995-02-26-not-fade-away-2-11`.
  - Eyes of the World is also tagged with Sikiru Adepoju on talking drum
    (out of scope here).
- **Held out: I Need A Miracle (set 2, position 9) and Drums (positions 1 and
  7).** Grateful Dead of the Day's guest index for David Murray lists "Eyes>
  Drums> I Need a Miracle" as one clause, which reads as a segue notation
  rather than an explicit credit, and setlist.fm does not tag either song
  "with David Murray" the way it tags the five confirmed songs (it tags the
  second Drums with Sikiru Adepoju only). Left as show-level; recorded here
  as an open question rather than guessed into a row.
- **Story:** Dead.net attendee comments describe a Mardi Gras parade and a
  dragon moving through the crowd during Drums, with Murray and Sikiru
  Adepoju on the talking drum for the parade. Reception was mixed: one
  commenter called it "completely 1 nutty crazy fun flippin show," while
  another called the saxophone "the worst sax I have ever heard" — the one
  dissenting voice across all four nights in this slice.
- No official release. Multiple soundboard sources are in the catalog's
  `recordings.csv` already.
- Sources: dead.net/show/february-26-1995; setlist.fm/setlist/grateful-dead/1995/oakland-alameda-county-coliseum-arena-oakland-ca-2bd60006.html;
  gratefuldeadoftheday.com/guest/david-murray/; gdao.org/items/show/377730
  (poster record only, no narrative).

## How the collaboration happened

- **Ornette Coleman and Garcia: Virgin Beauty is the through-line.** On
  1987-09-18, Coleman, his son Denardo, and Cecil Taylor attended a Dead show
  at Madison Square Garden at Phil Lesh's invitation. Afterward, Coleman
  invited Garcia to the recording sessions for *Virgin Beauty* (Portrait
  Records, 1988), the Coleman and Prime Time album. Garcia plays guitar on
  three tracks: "3 Wishes," "Singing in the Shower" and "Desert Players."
  Rolling Stone's David Fricke wrote that Deadheads who bought the album for
  Garcia's name "were pleasantly surprised by Prime Time's infectious
  propulsion and the emotive strength and striking warmth of Coleman's sax
  statements." Source: Wikipedia, "Virgin Beauty."
- **Garcia on Coleman, 1989:** "That's what Ornette always represented to me.
  No matter what direction you go in, there's always going to be other
  possibilities." Source: Ultimate Classic Rock, "The Night Ornette Coleman
  Joined the Grateful Dead."
- **The 1993 sit-ins as payback.** Five years after Virgin Beauty, Coleman's
  own band, Prime Time, opened two Dead shows in 1993 (Oakland 2/23 and Los
  Angeles 12/9), and both times Coleman crossed over into the Dead's set. No
  source found frames this explicitly as Garcia repaying the invitation, but
  every source that covers the backstory treats the two sit-ins as the
  continuation of the Virgin Beauty relationship rather than a new
  connection.
- **David Murray's connection came from the stage, not the studio.** Unlike
  Coleman, no source found describes a prior personal relationship between
  Murray and Garcia before 1993-09-22. Murray's own account (Grateful Dead
  Hour no. 445) describes being welcomed in live, through the band's earpiece
  monitor system, and being struck by the audience. That single night is
  what he says led him to make *Dark Star: The Music of the Grateful Dead*
  (Astor Place, 1996), his tribute album, which reframes six Dead
  compositions ("Shakedown Street," "China Doll," "Samson and Delilah," "Dark
  Star" among them) as full jazz explorations rather than covers, and
  includes a Bob Weir guest appearance recorded for a stage musical the two
  were separately developing. Murray returned to sit in with the Dead once
  more, at Oakland on 1995-02-26, and also guested with the Jerry Garcia Band
  at MSG on 1993-11-12 (that JGB date is outside this catalog's scope).
  Source: dead.net/features/gd-radio-hour/grateful-dead-hour-no-445;
  musicbox-online.com/dm-dark.html.

## Things to keep out of the answer

- Any claim that Coleman played Brokedown Palace on 1993-02-23 — one source
  only, contradicted by silence in four others.
- Any claim that Murray played Drums on 1993-09-22, or I Need A Miracle or
  either Drums segment on 1995-02-26 — no source names him on these
  specifically, even though the surrounding songs are well sourced.
- Denardo Coleman, Graham Wiggins, Sikiru Adepoju, Airto Moreira, Flora Purim
  and James Cotton all guested alongside the two saxophonists across these
  four nights, but adding their song-level credits is outside this slice's
  scope (two jazz saxophonists). They remain show-level guests in
  `show_performers.csv`.

## Catalog notes and possible follow-ups

- **gd-1993-09-22 has no `space-2-6` gap issue but the JerryBase snapshot
  for that event also lists James Cotton (harmonica)** as a guest not yet
  song-level. A future pass on 1993 MSG guests could add his rows using the
  same headyversion/Grateful Dead of the Day sourcing already gathered here
  (he is independently corroborated on Turn On Your Lovelight and Throwing
  Stones).
- **1995-02-26 has two `Drums` performances** (`gd-1995-02-26-drums-2-1` and
  `gd-1995-02-26-drums-2-7`), one before and one after the Mardi Gras parade.
  setlist.fm ties Sikiru Adepoju to the second one only; no source
  distinguishes them further.
- **The Grateful Dead of the Day guest index page** (gratefuldeadoftheday.com
  /guest/david-murray/) is a useful aggregator for any future guest-song pass
  — it lists songs per date for every guest the site has covered, in one
  place, though its terse phrasing sometimes needs cross-checking against a
  full setlist for segue versus credit ambiguity (as with I Need A Miracle
  above).
