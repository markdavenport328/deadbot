# Opening questions roadmap — October 12, 2026

The splash-screen chips are the first page most visitors see, and today they
lead to uneven results. This roadmap comes from the cached production answers
for the chips (fetched October 12 at commit `9154bf4`), checked against the
code and the canonical data. Items are in priority order: each one names what
the visitor sees, why it happens, the fix, which side of the model/code split
the fix belongs on (see `AGENTS.md`), its rough size, and the chips it helps.

The chips are cached answers built at deploy (`scripts/warm_answers.py`), so
every fix reaches the splash screen on the next deploy.

## What the answers showed

| Chip | What the visitor gets | Why |
|---|---|---|
| Most played songs | A flat bar chart, nothing to click | `data_chart` bars ignore their row IDs; hover is the only interaction |
| Best shows of 1979 | Two of three show cards lead with a Relisten link | The songs inside those setlists play in our player (19 and 16 tracks), but the card's main listen button is the Relisten link, and our player can't play a Relisten page |
| Veneta | Show card and playlist are great; the top is a jumble | Up to six labels stack before any prose: group title, group lead, eyebrow, block title, an item title repeating the block title, and a tagline |
| China-Rider | No way to hear the first China-Rider | The 9/30/69 Café au Go-Go tape exists only on Relisten; we never imported its tracks |
| Albums that shaped the repertoire | Spotify links that leave the site | Album cards show Spotify as an outbound link; an embed exists only on `media_link` blocks |
| Dark Star by year | A chart with no listening | It *is* the life-of-a-song timeline, but the model gave it no stops, so there are no gold pins and no listening path. The plays are hidden behind choosing a year or switching to Length. A fact grid then repeats the year counts |
| Dick's Picks | Five album cards, then the same five again as text | The prompt's "say it once" rule names songs, not records |
| Europe '72 box | Three text timelines; no grid, no tour outline | `get_album` returns the box's 22 shows, but nothing points the model to the grid, and `get_grid` matches tour names exactly ("Europe '72" misses "Europe 1972") |
| Reckoning | Play buttons but no setlists | The model left `visible_facets` empty, so the cards carry no setlist and "More" opens an empty drawer. Album rows always get their tracklist; show rows don't |
| Branford | Show rows with full setlists in the drawer | Works; this is the model listing its facets |
| Who sat in | Text and a roster with no way in | `person_roster` names are plain text: no expander, no follow-up |

One problem runs across several chips: catalog vocabulary leaks into the page
("The catalog maps 'Oh Babe, It Ain't No Lie' here", "570 tracks mapped to
canonical performances and eight additional unattributed tracks", "cataloged
setlist performances"). It comes from words in the tool output, such as
`unattributed_track_count` and "cataloged" in tool descriptions.

## Roadmap

### Tier 1: small fixes in code, shipped together

**1. Every show card with tape plays in our player.** When a show card has a
playable queue, its main listen control plays that queue ("Play the show"),
and Relisten moves to a secondary link. Today `inPagePlay`
(`web/src/listen-control.tsx`) turns a card's queue into the main action only
for archive.org links. This is transport: code builds players from stored URLs.
*Size: small. Helps: 1979, Madison Square Garden, any expanded show card.*

**2. A show row's "More" always opens to its setlist and listening.** Collapsed
show rows get the same floor album rows already get (`finish.py` forces
`listen` and `tracklist` on collapsed albums): the setlist and listen data come
with the row, so its drawer is never empty. The model still decides which
facets an expanded card opens with. A setlist is a stored fact, and an
expander that opens to nothing is broken transport. *Size: small. Helps:
Reckoning, every `from_result` list of shows.*

**3. One heading per idea.** The renderer drops an editorial item's title when
it repeats its block's title (the same rule `App.tsx` already applies to group
headings), and the `editorial` schema description tells the model that a
narrative is paragraphs, with items reserved for fact grids and timelines.
*Size: small. Helps: Veneta and any narrative editorial.*

**4. Make the chips an eval.** Add `evals/opening-v1.json` with all fifteen
chips, scored by `scripts/page_eval.py` on things a visitor notices: the page
offers in-app listening where audio exists; no card's content is repeated as
text; no catalog vocabulary appears in page copy; a show card's "More" has
something in it. Run it live before and after each item below. *Size: small to
medium. Helps: measuring every item after this one.*

### Tier 2: steering the model through tool output and the persona

These need live runs (item 4) to prove they work.

**5. Speak like a fan, not a database.** Rename the tool-output fields and
phrasing that leak (`unattributed_track_count`, "cataloged", "mapped"). Give
counts in plain terms ("750 times") and drop the meta-commentary ("that
enthusiasm is subjective"). Tool wording steers page wording more reliably than
a prompt rule. *Size: small to medium. Helps: Reckoning, Europe '72, most
played, Veneta.*

**6. Say each thing once, for every kind of card.** Change the prompt's "a
fact_grid of the same songs already given their own units" to cover anything
that already has a card: records, shows, years. Also say plainly that the song
timeline already shows the yearly counts. *Size: small. Helps: Dick's Picks,
Dark Star. Prove it with item 4's duplication check.*

**7. Tours and live boxes get their nights and their grid.** When `get_album`
returns a live release with several shows, its output names the tour and says
`get_grid` can lay out that tour's songs across its nights. `get_grid` also
matches tour names loosely ("Europe '72" finds "Europe 1972"), and
`query_catalog` `shows` with `tour` gives the night-by-night outline as
collapsed show rows. This is the open experiment in `UX-NEXT-STEPS.md` (around
line 422). It needs no new component, because collapsed show rows are the tour
outline once item 2 lands. *Size: medium. Helps: Europe '72, Reckoning, any
"what's on this box" or "tell me about this tour" question.*

**8. Song timelines come with a listening path.** For a counting question, the
model treats the card as a chart and skips stops. Two changes: the
`get_song_life` description and the timeline's palette entry say the stops are
how the visitor hears the song's life, so a counting answer still gets three
or four stops; and when there are no stops, the timeline says how to listen
(each year opens to its performances with play buttons) instead of hiding it.
The model still chooses the stops; code never picks them. *Size: small to
medium. Helps: Dark Star, Morning Dew, any song-by-year question.*

### Tier 3: new component capability

**9. Ranked bars you can open.** One shared row behavior for `data_chart`,
`ranked_list` and `person_roster`: each bar or row opens in place to its key
facts, a play button for a representative performance, and a follow-up ask
("More on Ned Lagin with the Dead"). The rows already carry entity IDs
(`song-playing-in-the-band`, `person-ned-lagin`), so code can fill the opened
row from the store. The panel pattern already exists in the grid
(`grid-actions.ts`, `GridFacts.tsx`); this is the "play / see all / ask panel
on other charts and lists" item in `UX-NEXT-STEPS.md`. The sat-in answer then
becomes a guests-by-shows bar chart where every bar opens to that guest's
nights. Design it for the whole family of ranked questions (songs, guests,
venues, records, years), not just these two chips. *Size: large. Helps: most
played, sat-in, albums, Santana, MSG.*

**10. Spotify plays on the page.** Album cards render the Spotify embed
(`MediaEmbed` in `App.tsx` already builds it for `media_link` blocks) in the
card or its opened row. Spotify's iframe API tells us when it starts, so we
pause our player and the two never play at once. Visitors who aren't signed in
to Spotify hear 30-second previews, which is Spotify's rule, not ours. No
content-security headers block the embed. *Size: medium. Helps: albums, Dick's
Picks, Europe '72, any record answer.*

**11. The life of a pairing.** Yes, a song-life timeline for China-Rider is
straightforward with our data. Setlists mark segues, and counting China Cat →
Rider gives 544 segues from 9/30/69 to 1995 (25 in 1969, 64 in 1970, none in
1975–76 or 1978, back in 1979). `sequences.py` already returns every dated
version with both halves' lengths and tracks, plus per-year counts and median
lengths. The work is to let `song_overview` (or `version_strip`) take a
`pairing_id` and feed the same `SongTimeline`, with the model's stops as gold
pins. New code: the pairing's standouts and the year-detail lookup. *Size:
medium to large. Helps: China-Rider, Scarlet-Fire, Help-Slip-Franklin's, Lost
Sailor-Saint, and every "when did X → Y start" question.*

### Tier 4: data passes

**12. Relisten source tracks.** Import track-level audio for shows where
Relisten has a tape and we have none: 82 shows today have only a Relisten
page, including the first China-Rider. This is already first on the data-pass
list. *Helps: China-Rider, late-'60s questions.*

**13. Fill Spotify gaps on records.** Dick's Picks Vol. 4 came back with no
listen link. A sweep through the Spotify API, the next step in the Spotify
notes, fills these so item 10 has something to embed.

## Recommended order

Ship items 1–3 as one small PR. Build item 4 before anything in Tier 2, so
each change is measured live. Then work through 5–8; they are prompt and
tool-output work, and each is small. Item 9 is the biggest visible gain and
deserves its own design pass, because it shapes every ranked answer. Items 10
and 11 can run in parallel with it. Items 12 and 13 are independent data work
that can run at any time.
