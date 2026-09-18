# Branford Marsalis onstage with the Grateful Dead: research notes

Compiled 2026-09-18, in the shape of `research-santana-onstage-2026-09-14.md`.
The catalog already lists Branford Marsalis as a show-level guest (saxophone)
at five shows, from JerryBase. This pass adds song-level credits and the
stories behind them.

## What the catalog knows today

`show_performers.csv` credits Branford Marsalis (saxophone, role `guest`) at:

| Show | Venue | Songs resolved this pass |
|---|---|---|
| gd-1990-03-29 | Nassau Veterans Memorial Coliseum, Uniondale, NY | yes, 9 of 17 performances |
| gd-1990-12-31 | Oakland-Alameda County Coliseum Arena | yes, 10 of 18 performances |
| gd-1991-09-10 | Madison Square Garden | yes, 19 of 20 performances |
| gd-1993-12-10 | Los Angeles Sports Arena | yes, 3 of 18 performances |
| gd-1994-12-16 | Los Angeles Sports Arena | yes, 8 of 17 performances |

The JerryBase raw snapshots (`data/raw/performers/jerrybase-{1990,1991,1993,1994}.jsonl`)
carry only the show-level guest list (name plus instrument); they have no
song-level detail, so every song credit below comes from the web pass.

## The five nights, song by song

### 1990-03-29, Nassau Coliseum, Uniondale, NY

Marsalis's debut. Phil Lesh invited him backstage; the band "auditioned" him
on **Bird Song**, the penultimate song of the first set, and within a verse
Jerry Garcia and Marsalis were trading licks. Afterward Marsalis thanked the
band for letting him play, and they told him to stay for the whole second
set. He opened it with **Eyes of the World**, then **Estimated Prophet**,
then a **Dark Star** he'd never played — he asked the band "What is it?"
before going on. After Drums and Space he played a second **Dark Star**;
fans called his private number afterward to thank him for reviving a song
the Dead hadn't played in six months. He closed the set with **The Wheel**,
**Throwing Stones**, and **Turn On Your Lovelight**, then returned for the
**Knockin' On Heaven's Door** encore. Marsalis called it "the best time I've
had in my entire life." The show was later released as the three-disc
official album *Wake Up to Find Out*.

Catalog performance IDs: `gd-1990-03-29-bird-song-1-6`,
`eyes-of-the-world-2-1`, `estimated-prophet-2-2`, `dark-star-2-3`,
`dark-star-2-6`, `the-wheel-2-7`, `throwing-stones-2-8`,
`turn-on-your-lovelight-2-9`, `knockin-on-heaven-s-door-3-1`.

Not included: `jack-straw-1-1` through `when-i-paint-my-masterpiece-1-5`
(before he came out) and `promised-land-1-7` (the last song of the first
set; every source has him leaving the stage after Bird Song and returning
for the second set, not staying for Promised Land). `drums-2-4` and
`space-2-5` are held out — no source names Marsalis playing through them,
only that the two Dark Stars bracket them.

Sources: en.wikipedia.org/wiki/Wake_Up_to_Find_Out; JamBase, "Watch Branford
Marsalis Make Grateful Dead Debut At Nassau Coliseum"; the artist-hosted
retrospective at branfordmarsalis.com (already cataloged as
`resource-branford-history-with-the-dead`).

### 1990-12-31, Oakland-Alameda County Coliseum Arena (New Year's Eve)

Marsalis's second sit-in. He joined late in the first set for **Bird Song**
and closed it with **Promised Land**. The second set opened and closed with
**Not Fade Away** — a bookend the Dead used only four times in their
history — with **Eyes of the World**, **Dark Star**, **The Other One**, and
**Wharf Rat** in between. Percussionist Hamza El-Din joined separately for
the Drums segment; no source credits Marsalis on Drums or Space that night.
Marsalis stayed through the two-song encore, **The Weight** and **Johnny B.
Goode**.

Catalog performance IDs: `bird-song-1-7`, `promised-land-1-8`,
`not-fade-away-2-1`, `eyes-of-the-world-2-2`, `dark-star-2-3`,
`the-other-one-2-6`, `wharf-rat-2-7`, `not-fade-away-2-8`, `the-weight-3-1`,
`johnny-b-goode-3-2`.

Not included: `hell-in-a-bucket-1-1` through `mexicali-blues-1-5` (before he
came out), `drums-2-4`, `space-2-5` (credited to El-Din / undocumented for
Marsalis).

Sources: setlist.fm, "Grateful Dead Setlist at Oakland-Alameda County
Coliseum Arena... December 31, 1990" (per-song annotation); the
branfordmarsalis.com retrospective for the Not Fade Away bookend detail.

### 1991-09-10, Madison Square Garden

Marsalis's third sit-in, and the one every source frames as full-show, not
partial: JamBase's article on the date says he "augmented the band for the
entire concert" from the opening **Shakedown Street** (Phil Lesh playing
funk-style bass under him) through the encore, **It's All Over Now, Baby
Blue**; Deadhead High's listener guide says he "sits in for the full Madison
Square Garden show" and specifically calls out him getting room right away
in **Shakedown Street > C.C. Rider**; Grateful Dead of the Day's guest index
lists this appearance as "entire show." JamBase also singles out his
soprano-and-tenor work on **Dark Star**, played twice around Drums and
Space. Because three independent sources converge on full-show rather than
a partial or vague claim, this pass credits him on every performance in the
show except Drums, where no source places a horn.

Catalog performance IDs: `shakedown-street-1-1`, `c-c-rider-1-2`,
`it-takes-a-lot-to-laugh-it-takes-a-train-to-cry-1-3`,
`black-throated-wind-1-4`, `high-time-1-5`, `cassidy-1-6`, `deal-1-7`,
`help-on-the-way-2-1`, `slipknot-2-2`, `franklin-s-tower-2-3`,
`estimated-prophet-2-4`, `dark-star-2-5`, `space-2-7`, `dark-star-2-8`,
`space-2-9`, `i-need-a-miracle-2-10`, `standing-on-the-moon-2-11`,
`turn-on-your-lovelight-2-12`, `it-s-all-over-now-baby-blue-3-1`.

Not included: `drums-2-6`.

Sources: JamBase, "Branford Marsalis Guests With Grateful Dead At Madison
Square Garden On This Date In 1991"; Deadhead High listener guide (already
cataloged as `resource-deadheadhigh-shows-1991-09-10`); Grateful Dead of the
Day's guest index.

### 1993-12-10, Los Angeles Sports Arena

The thinnest sourcing of the five. Grateful Dead of the Day's guest index —
the only source in this pass that breaks this appearance down by song —
names three: **Bertha**, closing the first set, then **Scarlet Begonias**
into **Fire on the Mountain**, opening the second. Marsalis had been
managing time away from his Tonight Show band duties to make the show. Two
other sources describe it more broadly as a full-show appearance —
JerryGarcia.com's show page says he "played saxophones throughout the
entire show" — but neither names songs, and that broader claim isn't
consistent with the narrower three-song list. Per the evidence rule, the row
count stays at the three named songs; the broader claim is recorded here
rather than turned into rows.

Catalog performance IDs: `bertha-1-7`, `scarlet-begonias-2-1`,
`fire-on-the-mountain-2-2`.

Held out as unresolved: `hell-in-a-bucket-1-1`, `loser-1-2`,
`little-red-rooster-1-3`, `so-many-roads-1-4`,
`just-like-tom-thumb-s-blues-1-5`, `eternity-1-6`, `corrina-2-3`,
`terrapin-station-2-4`, `jam-2-5`, `i-need-a-miracle-2-8`,
`standing-on-the-moon-2-9`, `not-fade-away-2-10`, `brokedown-palace-3-1` —
plausible if the "entire show" framing is right, but not named by any
source found in this pass.

Sources: Grateful Dead of the Day guest index for Branford Marsalis;
JerryGarcia.com show page for 1993-12-10 (held out, see above).

### 1994-12-16, Los Angeles Sports Arena

Marsalis's fifth and last known sit-in with the band. Set 1 is not his — no
source places him before the second set. He opened set two with **Eyes of
the World**, then **Samba In The Rain**, **Estimated Prophet**, and **He's
Gone**, sat out Drums, returned for **Space**, then **The Other One**,
**Wharf Rat**, and closed the set with **Good Lovin'**. He did not return
for the **Lucy In The Sky With Diamonds** encore — setlist.fm's per-song
breakdown stops at Good Lovin', and no other source places him on the
Beatles cover.

Catalog performance IDs: `eyes-of-the-world-2-1`, `samba-in-the-rain-2-2`,
`estimated-prophet-2-3`, `hes-gone-2-4`, `space-2-6`, `the-other-one-2-7`,
`wharf-rat-2-8`, `good-lovin-2-9`.

Not included: `hell-in-a-bucket-1-1` through `don-t-ease-me-in-1-7` (set 1),
`drums-2-5`, `lucy-in-the-sky-with-diamonds-3-1` (encore, confirmed absent).

Sources: setlist.fm, "Grateful Dead Setlist at Los Angeles Sports Arena...
December 16, 1994" (per-song annotation); Grateful Seconds blog, "30 Trips
Listening Hint #1," which independently names Eyes of the World, Samba In
The Rain, and Estimated Prophet for this date (already cataloged as
`resource-gratefulseconds-2015-10-30-trips-listening-hint-1-every-single`).

## How the collaboration happened

Unlike Santana's decades-long Bill Graham connection, Marsalis's five sit-ins
all trace to one night: Phil Lesh invited him backstage before the March 29,
1990 Nassau Coliseum show, and the band tried him out on a single song,
Bird Song, before deciding to keep him on for the rest of the night. Bassist
Phil Lesh again features prominently in the third appearance, playing
funk-style bass under Marsalis's opening solo at Madison Square Garden in
September 1991. The five shows run March 1990 through December 1994, with
Marsalis reportedly juggling his Tonight Show band-leading duties (which
began in 1992) to make the December 1993 date. No appearance after
1994-12-16 has turned up in this pass; treat it as his last known sit-in
with the Grateful Dead until a later date surfaces.

## What was deliberately left out

- **1993-12-10 beyond Bertha, Scarlet Begonias, and Fire on the Mountain.**
  JerryGarcia.com's "entire show" framing conflicts with Grateful Dead of the
  Day's specific three-song list; kept at three rows, both claims recorded
  above.
- **Drums at every show.** No source anywhere in this pass places Marsalis's
  saxophone in a Drums segment; where a specific percussion guest is named
  (Hamza El-Din, 1990-12-31) it is a different person, out of scope for this
  pass.
- **Space at 1990-03-29 and 1990-12-31.** No source names Marsalis playing
  through these segments even though he plays on both sides of them.
- **1994-12-16 encore, Lucy In The Sky With Diamonds.** Explicitly excluded
  by the source that breaks the show down song by song.
- **Any sixth appearance.** Nothing found in this pass suggests Marsalis
  played with the Dead outside these five shows (his 2009 sit-in with The
  Dead spinoff band at the Izod Center is a different band, out of scope).

## Data notes surfaced by this pass

- Canonical `resources.csv` already carried eleven Marsalis-related resources
  from an earlier pass (dead.net community pages for all five shows, the
  Deadhead High listener guides, the branfordmarsalis.com retrospective, two
  Grateful Seconds posts, and a rukind.com forum thread about his Dark Star
  turns) with `resource_shows.csv` rows already linking them to all five
  shows. None of those had song-level `resource_performances` links or any
  `performance_performers` rows yet; this pass is the first to add either.
- The branfordmarsalis.com article (an artist-hosted reprint of a Live For
  Live Music feature covering all five shows in one narrative) places the
  1993-12-10 and 1994-12-16 shows at "Long Beach Arena, Los Angeles" and
  attributes "Samba In The Rain," "The Other One," and "Scarlet Begonias >
  Fire On The Mountain" all to the December 1993 date. The catalog's own
  `performances.csv` shows both shows at Los Angeles Sports Arena, and
  "Samba In The Rain" and "The Other One" only appear in the 1994-12-16
  setlist, not 1993-12-10. This pass follows the catalog's show/song
  assignments and the narrower, per-show Grateful Dead of the Day list
  instead of that article's account for song attribution, though the
  article remains a good source for the invitation story and quotes.
