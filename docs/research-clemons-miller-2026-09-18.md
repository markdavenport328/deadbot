# Clarence Clemons and Steve Miller onstage with the Grateful Dead: research notes

Compiled 2026-09-18, in the shape of `docs/research-santana-onstage-2026-09-14.md`. The
catalog already lists both guests at show level (`show_performers.csv`, JerryBase source).
This file records what a web pass found song by song, how well each claim is sourced, and
the stories worth carrying into `performance_performers.csv`.

## What the catalog knows today

Clarence Clemons (saxophone, role `guest`) at five 1988-89 shows:

| Show | Venue |
|---|---|
| gd-1988-12-31 | Oakland-Alameda County Coliseum Arena |
| gd-1989-05-27 | Oakland-Alameda County Coliseum Stadium |
| gd-1989-06-21 | Shoreline Amphitheatre, Mountain View |
| gd-1989-12-06 | Oakland-Alameda County Coliseum Arena |
| gd-1989-12-27 | Oakland-Alameda County Coliseum Arena |

Steve Miller (guitar, and vocals+guitar on 7/1, role `guest`) at six summer-1992 shows:

| Show | Venue |
|---|---|
| gd-1992-05-31 | Sam Boyd Silver Bowl, Las Vegas |
| gd-1992-06-14 | Giants Stadium, East Rutherford |
| gd-1992-06-15 | Giants Stadium, East Rutherford |
| gd-1992-06-20 | Robert F. Kennedy Stadium, Washington |
| gd-1992-06-25 | Soldier Field, Chicago |
| gd-1992-07-01 | Buckeye Lake Music Center, Thornville, OH |

**Data note:** the task brief for this pass described gd-1989-12-06 as "Los Angeles Forum"
and gd-1992-07-01 as "Deer Creek." Both are wrong in the catalog's own `shows.csv`: 12/6/89
is Oakland-Alameda County Coliseum Arena (part of a five-night Oakland run that December,
confirmed by dead.net, setlist.fm and gratefuldeadoftheday), and 7/1/92 is Buckeye Lake
Music Center in Thornville, Ohio (confirmed the same way, and by JerryBase's own raw
snapshot). The catalog's venues are followed here; the brief's venue names are not used.

## Clarence Clemons, song by song

### 1988-12-31, Oakland (New Year's Eve) — his first sit-in

Setlist.fm marks eight songs "with Clarence Clemons": **Wang Dang Doodle**, **West L.A.
Fadeaway** (set 1); **Sugar Magnolia**, **Touch of Grey**, **Man Smart (Woman Smarter)**,
**Terrapin Station** (set 2); **Goin' Down the Road Feelin' Bad**, **One More Saturday
Night** (encore). This was the first time Clemons ever sat in with the Dead. He was
newly free after Bruce Springsteen put the E Street Band on hiatus and was living nearby
in Marin — the beginning of a year-long association.

### 1989-05-27, Oakland Stadium — In Concert Against AIDS benefit

The Dead headlined a benefit bill with John Fogerty, Tower of Power, Los Lobos, Tracy
Chapman and Joe Satriani (dead.net show page); Garcia and Weir also backed Fogerty's own
set. Two songs have strong, specific sourcing beyond the setlist:

- **Bird Song** — JamBase: "the Big Man contributing mightily to this mighty fine 'Bird
  Song'"; calls this the first time Clemons played in an actual Grateful Dead concert
  (he'd sat in with the Jerry Garcia Band earlier that year).
- **Fire on the Mountain** — JamBase: grew out of the Hell in a Bucket transition, "Big
  Man would fuel the flames of 'Fire,' egged on by guitarist Jerry Garcia." Notes this
  segue pairing happened only three times total, otherwise in 1987.

A single blog, Albums That Should Exist (a detailed per-song recap of the full In Concert
Against AIDS set), names eight more songs with Clemons on saxophone: **Iko Iko**, **Stuck
Inside of Mobile with the Memphis Blues Again**, **Promised Land**, **Hell in a Bucket**,
**Blow Away**, **Truckin'**, **Turn On Your Lovelight**, **Brokedown Palace** — more than
half the set. This is the only source naming that many songs for this show; it agrees
exactly with JamBase on Bird Song and Fire on the Mountain, which is why it's trusted for
the rest. Dead.net's own comments only say he played "in the first set and most of the
second and encore," which is too vague on its own — the blog is what turns that into
song-level rows.

### 1989-06-21, Shoreline Amphitheatre

Glide Magazine and Live for Live Music (via search) agree: Clemons walked on during the
transition into **Hell in a Bucket** and stayed for the rest of the second set except
Drums and Space — **Ship of Fools**, **Estimated Prophet**, **Eyes of the World**,
**Truckin'**, **The Other One**, **Morning Dew**, **Turn On Your Lovelight**. The show was
broadcast live via pay-per-view, which is likely why it's well documented; Glide calls it
one of the best shows of Summer Tour '89.

### 1989-12-06, Oakland Coliseum Arena — earthquake relief benefit

Two sources, complementary rather than conflicting: Grateful Dead of the Day's recording
notes say Clemons "sits in on tenor saxophone" starting with **Ship of Fools**, and comes
in "very soft and restrained" during **Space**. Albums That Should Exist names six songs
running from Ship of Fools through the encore: Ship of Fools, **Terrapin Station**, **All
Along the Watchtower**, **Standing on the Moon**, **Sunshine Daydream**, **Black Muddy
River** — it doesn't mention Space, but Grateful Dead of the Day's specific description of
him playing during Space (rather than sitting out) reads as additional detail, not a
conflicting claim, so Space is included. The Dead played this date because they were
already booked elsewhere on the benefit's original November 26, 1989 date.

### 1989-12-27, Oakland — his fifth and final sit-in

Live for Live Music: Clemons joined for **Iko Iko** (a "powerful" opener to the second
set), **Playing In The Band**, **The Wheel**, **I Need a Miracle**. The article, citing
David Browne's book *So Many Roads*, tells the backstage story: Clemons found mushrooms
being passed around, ate a substantial amount, and "a large, confused smile" came over his
face partway through the set. This was Clemons' fifth Grateful Dead sit-in in just under a
year and his last.

**Left out:** dead.net attendee comments for this show also credit Clemons on **Just Like
Tom Thumb's Blues** ("came in early with some cool unique horn effects") and **Promised
Land**, both in the first set. No formal source names these songs; per the evidence rule,
attendee recollections alone don't clear the bar. Left as show-level only.

## Steve Miller, song by song

Miller's own band opened all six shows on this stretch of the Dead's summer 1992 tour —
the Bay Area's two biggest rock exports of their generation sharing a bill. He played
guitar throughout, adding vocals for the vocal number at Buckeye Lake.

### 1992-05-31, Sam Boyd Silver Bowl, Las Vegas

Closing night of a three-show Vegas run. Dead.net comments and Daily Dose of the Dead
agree: Miller joined for **Spoonful** through **Morning Dew**, then the **Baba O'Riley**
and **Tomorrow Never Knows** covers that closed the show. One dead.net commenter: Bobby
and Miller were "feigning Pete Townshend windmills and leaps" during Baba O'Riley.

### 1992-06-14, Giants Stadium

Setlist.fm marks **Spoonful**, **The Other One**, **Baba O'Riley** and **Tomorrow Never
Knows** "with Steve Miller." A dead.net attendee adds that Miller "came out and played
with the Dead for Spoonful and stayed the rest of the show" and had earlier dedicated
"Take the Money and Run" to the Dead from his own set — corroboration for the stretch, but
not itself a source naming Morning Dew, so Morning Dew (the last song of that set, between
The Other One and the encore) is left out.

### 1992-06-15, Giants Stadium

Setlist.fm marks **I Need a Miracle**, **Standing on the Moon**, **Not Fade Away** and the
**Knockin' On Heaven's Door** encore "with Steve Miller." (An earlier web search summary
also suggested Throwing Stones for this date; the setlist.fm page itself does not tag it,
so it's left out.)

### 1992-06-20, RFK Stadium

Two sources disagree here. Setlist.fm tags **Throwing Stones**, **One More Saturday
Night** and **Baba O'Riley** "with Steve Miller." But Grateful Dead of the Day and a
circulating YouTube clip ("Grateful Dead & Steve Miller - Baba O'Riley / Tomorrow Never
Knows 6/20/1992") name only **Baba O'Riley** and **Tomorrow Never Knows**, and a
dead.net comment thread for this date doesn't mention Miller joining the band at all
(only that his own set was well liked). Per the evidence rule, only the songs multiple
sources converge on are kept: Baba O'Riley and Tomorrow Never Knows. Throwing Stones and
One More Saturday Night are left out as single-source and contradicted by the more
detailed accounts.

### 1992-06-25, Soldier Field

Setlist.fm tags five songs: **Iko Iko**, **Good Morning Little Schoolgirl**, **All Along
the Watchtower**, **Turn On Your Lovelight**, **Gloria**. Harmonica player James Cotton
shared three of the five (Good Morning Little Schoolgirl, Lovelight, Gloria) — Cotton is
out of scope for this slice and isn't given a row. Good Morning Little Schoolgirl was the
Sonny Boy Williamson cover's first outing since August 22, 1987.

### 1992-07-01, Buckeye Lake Music Center

Setlist.fm tags **In the Midnight Hour** and **West L.A. Fadeaway** "with Steve Miller"
(and Norton Buffalo on harmonica for the second). JamBase's writeup of West L.A. Fadeaway
notes it was the last time that song ever closed a second set. JerryBase's own guest
listing for this date credits Miller "vocals, guitar" rather than guitar alone, which is
why both performance rows carry `instrument = vocals, guitar` (one row per performance,
matching the catalog's one-guest-one-role convention; see data note below). Reception was
mixed even from Miller himself — a JamBase aside quotes him later saying of the Dead, "I
couldn't stand that band."

## Data notes and possible follow-ups

- **Venue mismatches in the task brief**, not the catalog: see above for gd-1989-12-06
  (Oakland, not LA Forum) and gd-1992-07-01 (Buckeye Lake, not Deer Creek). Not changed
  here; the catalog's `shows.csv` values are correct as far as this pass could verify.
- **`performance_performers` is one row per person per performance.** The pilot Santana
  pass didn't need multi-instrument rows; this slice did (Miller vocals+guitar at
  Buckeye Lake), so this pass folds multiple instruments into one comma-joined
  `instrument` value rather than two rows, to avoid a duplicate `(performance_id,
  person_id)` key. Future passes with a similar case should do the same.
- **James Cotton and Norton Buffalo** both sat in alongside Miller on some of these
  songs (6/25 and 7/1) but are out of scope for this slice per the contract; no rows
  were added for them. They're worth their own pass — Cotton in particular is a
  recurring guest across multiple Dead shows.
- **The 1992-06-20 RFK disagreement** (Throwing Stones and One More Saturday Night,
  setlist.fm only vs. Baba O'Riley/Tomorrow Never Knows, multiple sources) is the one
  real source conflict in this slice; see above. Worth a second look if someone can
  listen to the RFK soundboard directly.
- **Clemons' 1989-12-27 comment-only songs** (Tom Thumb's Blues, Promised Land) are a
  good candidate if a firmer source turns up — a JamBase or Relisten piece specifically
  on that show would settle it.

## Summary of what was added

- Clarence Clemons: 37 performance rows across the five 1988-89 shows (8 at 12/31/88, 10
  at 5/27/89, 8 at 6/21/89, 7 at 12/6/89, 4 at 12/27/89).
- Steve Miller: 22 performance rows across the six summer-1992 shows (5 at 5/31, 4 at
  6/14, 4 at 6/15, 2 at 6/20, 5 at 6/25, 2 at 7/1 — 22 rows total).
- 19 new resources (JamBase, setlist.fm, dead.net community pages, Grateful Dead of the
  Day, Daily Dose of the Dead, Glide Magazine, Live for Live Music, Albums That Should
  Exist), 64 `resource_performances` rows and 5 `resource_shows` rows.
