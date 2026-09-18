# Bob Dylan onstage with the Grateful Dead: research notes

Compiled 2026-09-18 for the guest song-credit pass. The catalog already lists
Bob Dylan as a show-level guest (JerryBase) at four shows: two 1986 stadium
dates shared with Tom Petty and the Heartbreakers, the February 12, 1989
Forum sit-in, and the October 17, 1994 Madison Square Garden appearance. What
it lacked was which songs he actually played or sang on, and the story of
each. This file records what a web pass found, split the same way the
Santana research did: what the catalog knows, each show song by song, what
was left out and why, and data notes.

## What the catalog knows today

`show_performers.csv` credits Bob Dylan (guest, guitar and vocals, or
acoustic and vocals in 1994) at:

| Show | Venue | Catalog setlist has the songs he played? |
|---|---|---|
| gd-1986-07-02 | Rubber Bowl, University of Akron | yes |
| gd-1986-07-07 | Robert F. Kennedy Stadium, Washington DC | yes |
| gd-1989-02-12 | Great Western Forum, Inglewood | yes |
| gd-1994-10-17 | Madison Square Garden, New York | yes |

Guest credits were show-level only, so the catalog could name shows but not
songs. The performance IDs below are the ones the song-level credits now
attach to.

## 1987 "Dylan & the Dead": not a fit for this pass

The contract asked me to check whether the 1987 joint tour dates exist in
the catalog as Dead shows. They do: `gd-1987-07-02`, `-07-04`, `-07-06`,
`-07-07`, `-07-08`, `-07-10`, `-07-12`, `-07-19`, `-07-24`, `-07-26` are all
in `shows.csv`, normalized from gdshowsdb. I checked `performances.csv` for
each of the six co-headline dates (07-04, 07-10, 07-12, 07-19, 07-24,
07-26); every one is the Grateful Dead's own set, with no Dylan-fronted song
titles (no "Gotta Serve Somebody," "Man of Peace," "Ballad of a Thin Man,"
etc.) and no Dylan credit in `show_performers.csv`. This matches how the
real 1987 tour worked: at each date the Dead played their own set, then
Dylan came out fronting a separate set with the Dead as his backing band.
The catalog holds the Dead's own sets, not Dylan's fronted sets, so there is
nothing to add here. "When I Paint My Masterpiece," which the Dead played at
three of these shows (07-12, 07-19, 07-26), is a Dylan song but was part of
the Dead's own long-standing repertoire, not a credited Dylan sit-in — no
row added for it.

`resource-gratefulseconds-2016-10-nobel-prize-winner-bob-dylan-rocks-with`
and `resource-gratefulseconds-2018-12-we-will-survive-economics-of-1987s`,
already in `resources.csv`, cover this tour at a show level; neither is
linked to a performance and none should be, per the above.

## The four shows, song by song

### 1986-07-02, Rubber Bowl, University of Akron

Dylan and Tom Petty and the Heartbreakers opened the show on their own
stadium tour; this was the first time Dylan and the Grateful Dead ever
played together live. Dylan joined for three songs in set one:

- **Little Red Rooster** (Willie Dixon), set 1 position 4.
- **Don't Think Twice, It's Alright**, set 1 position 5, Dylan on lead
  vocals — the only time the Grateful Dead ever played this song.
- **It's All Over Now, Baby Blue**, set 1 position 6, Dylan and Garcia on
  shared vocals.

A dead.net attendee, checking the show against handwritten notes, wrote:
"Dylan joining them for Little Red Rooster, Don't Think Twice and Baby
Blue." Setlist.fm annotates the same three songs "with Bob Dylan."

**Desolation Row** (set 2 position 4) is not counted as a Dylan song here.
setlist.fm annotates it "without Garcia," and a dead.net commenter wrote "I
looked at my old handwritten setlist from this show and had written 'no
Jerry' next to Desolation Row" — both point to Garcia stepping out, not to
Dylan stepping in, and no source names Dylan on this song at Akron
(contrast with RFK five days later, where he is explicitly credited on it).
Held out; see "What was left out" below.

Sources: setlist.fm (Grateful Dead and Bob Dylan/Tom Petty setlists for the
date); dead.net/show/july-2-1986 attendee comments.

### 1986-07-07, Robert F. Kennedy Memorial Stadium, Washington, DC

Second stop of the same run. Dylan joined for two songs in set one:

- **It's All Over Now, Baby Blue**, set 1 position 4. His guitar was not
  working at the start of the song and he finished it on a borrowed Bob Weir
  guitar; a dead.net attendee called his playing, once switched, "really
  nice touch, very cool fills."
- **Desolation Row**, set 1 position 5. Both setlist.fm and a dead.net
  commenter agree Dylan sang here: "the Desolation Row with the two Bobs
  trading lyrics."

Attendees noted the formality of the moment — the band did not usually take
a bow or make introductions "unless Bill Graham was present," and this night
they did.

Sources: setlist.fm; dead.net/show/july-7-1986 attendee comments.

### 1989-02-12, Great Western Forum, Inglewood (the famous sit-in)

This is the night usually pointed to as "the" Dylan/Dead sit-in, and the
richest sourced of the four. Dylan came out at the start of the second set
and stayed, on and off, through the encore. Spencer Davis (vocals/guitar,
"How Long Blues" and "Gimme Some Lovin'" in set one) and Yoshikazu Fujimoto
of Kodo (drums, during Drums) also sat in that night — both are outside this
slice (Dylan only) and are not touched here. The Santana research doc
already flagged and corrected a JamBase compilation error that had wrongly
listed Santana, not Fujimoto, as this show's drum guest; that correction
stands.

**Dylan's run**, JamBase and Grateful Dead of the Day agree, covered
"everything pre-Drums" in the second set:

- **Iko Iko** (set 2 position 1) — opened the second set with Dylan onstage.
- **Monkey and the Engineer** (set 2 position 2) — a bust-out, first
  performance since 1981. Grateful Dead of the Day: "some people who were
  there claim that Dylan was calling the setlist," which would explain why
  this rarity came out.
- **Alabama Getaway** (set 2 position 3).
- **Dire Wolf** (set 2 position 4).
- **Cassidy** (set 2 position 5) — a dead.net attendee wrote Dylan "clearly
  looked baffled during the jam in Cassidy," adding that he seemed more
  comfortable with structured songs than open jamming.
- **Stuck Inside of Mobile with the Memphis Blues Again** (set 2 position
  6) — the night's centerpiece. Weir sang lead on Dylan's own song and
  stalled mid-verse; one attendee recalled "Bobby kept trying to get Dylan
  to sing during Stuck Inside of Mobile... but he didn't want to," until
  Weir "pretended to forget the lyrics," at which point Dylan finished the
  line himself.

Dylan then left the stage for Drums, Space, The Other One, Stella Blue and
Foolish Heart, and came back for the two-song encore:

- **Not Fade Away** (set 3 position 1).
- **Knockin' on Heaven's Door** (set 3 position 2) — JamBase says Dylan
  "took the band through" the song; a dead.net commenter instead recalls
  "Dylan didn't sing, he let Bobby sing Heaven's Door." Both agree Dylan was
  onstage for the song; only who sang lead is disputed, so the row stays and
  the disagreement is noted once here rather than in the row.

**Why it mattered.** This was the sit-in, not the six 1987 co-headline
dates, that is usually cited as having planted the idea of a real Dylan/Dead
tour in Dylan's own head — he had, of course, already toured with the Dead
in 1987, so the causal story sometimes told (that this night "led to" that
tour) has the chronology backwards; more accurately, this was the pair's
first time playing together again since that tour, and it came at a moment,
per Garcia interviews from the era, when the band had "always wanted to do"
more with Dylan and kept the door open whenever he was in town. No source
found in this pass carries a direct quote from Garcia or Weir made
specifically after this show; the closest is Garcia's general remark from
around the 1987 tour's genesis that pairing with Dylan was "something we
always wanted to do." That quote belongs to 1987, not February 1989, and is
not attached to any 1989 row.

Sources: JamBase, "Bob Dylan, Spencer Davis & Kitaro Join Grateful Dead In
1989"; dead.net/show/february-12-1989 attendee comments; Grateful Dead of
the Day, 02-12-1989; setlist.fm.

### 1994-10-17, Madison Square Garden, New York

Dylan's only song this night was the encore:

- **Rainy Day Women #12 and 35** (set 3 position 1) — the Grateful Dead's
  only performance of the song, ever, and Dylan's first sit-in with the band
  since the 1989 Forum show. His microphone failed; one attendee wrote "we
  couldn't hear a word of it, and I don't think anyone on stage knew the
  words," while the crowd sang the refrain anyway. Weir stopped playing
  mid-song to adjust Dylan's mic stand.

**All Along the Watchtower**, earlier in the same second set (position 8),
is not a Dylan row. JamBase is explicit that the Dead played "a Dylan-less
version of Bob's own 'All Along the Watchtower'" — the Dead had long since
made the song their own and played it without him that night, same set,
same show. This is the clearest possible source-named exclusion in this
pass and is called out so nobody re-adds it later from the title alone.

Sources: JamBase, "Bob Dylan Performs With Grateful Dead At Madison Square
Garden On This Date In 1994"; dead.net/show/october-17-1994 attendee
comments.

## What was left out and why

- **1986-07-02 Desolation Row.** setlist.fm marks it "without Garcia," and a
  dead.net commenter's handwritten notes say "no Jerry" — both describe
  Garcia sitting out, not Dylan sitting in, and no source names Dylan on
  this song at Akron. Contrast with 1986-07-07, five days later, where two
  sources independently name him on Desolation Row. Held out.
- **1989-02-12 who sang Knockin' on Heaven's Door.** JamBase credits Dylan
  with leading the song; a dead.net attendee recalls Weir singing it while
  Dylan stood by. Both sources place Dylan onstage for the song, so the row
  stays; the vocal-lead disagreement is recorded once above rather than
  guessed at in the row's notes.
- **1994-10-17 All Along the Watchtower.** Explicitly Dylan-less per
  JamBase; not a row.
- **1987 co-headline dates.** The catalog's setlists for these shows are the
  Dead's own sets, with no Dylan-fronted songs and no existing Dylan credit
  in `show_performers.csv`. Nothing to add; see the section above.
- **Spencer Davis and Yoshikazu Fujimoto, 1989-02-12.** Both are credited
  guests the same night as Dylan but are outside this slice's scope (Bob
  Dylan only) and were not researched or added here.

## Catalog notes and possible follow-ups

- **`gd-1994-10-17` performances confirm the JerryBase instrument note.**
  JerryBase lists Dylan's instrument at this show as "acoustic, vocals,"
  which matches Rainy Day Women being an acoustic-flavored encore singalong
  rather than a plugged-in jam.
- **Two more Dylan/Dead crossings are outside this slice's four shows** and
  worth a future pass if the same treatment is wanted: the six-date 1987
  "Dylan & the Dead" tour (Dylan's own fronted sets, not currently in the
  catalog as separate performances — would need new performance rows keyed
  to Dylan-fronted setlists, a bigger lift than a guest-credit pass) and any
  Dylan covers played by the Dead without him present (routine repertoire,
  not sit-ins).
- **Resources already in the catalog before this pass** —
  `resource-gratefulseconds-2016-06-30-years-ago-jerry-garcia-and-i-both`
  (Garcia and Dylan/Petty at the Greek, June 1986, a different show),
  `resource-hooterollin-2011-04-on-tour-1986-david-nelson-and-bob-dylan`, and
  the two Grateful Seconds 1987-tour posts — were read for context but
  carry no song-level detail for the four shows in this slice, so none were
  linked to performances.
