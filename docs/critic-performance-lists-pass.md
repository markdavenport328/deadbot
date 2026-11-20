# Critic performance-list pass (2026-11-19)

Two attributed critic lists that name a specific performance (song, date,
venue), added as `critic_editorial_performance_selection` evidence. Same
retention as the Rolling Stone pass: song, date and venue as listed, the pick's
role ("main pick", "Eighties pick", "key later version") and, for Guitar World,
the list position. No prose is kept.

| Source | Selector | Raw file | Records |
| --- | --- | --- | --- |
| Guitar World, "The Grateful Dead's 50 best live performances" (2018-10-16) | Blair Jackson | `data/raw/critic-signals/guitar-world-50-best-live-performances-2018.jsonl` | 81 picks, 96 song entries |
| Pitchfork, "The Grateful Dead: A Guide to Their Essential Live Songs" (2017-05-23) | Pitchfork | `data/raw/critic-signals/pitchfork-essential-live-songs-2017.jsonl` | 69 picks, 79 song entries |

Pitchfork's guide was read through the Pocket mirror of the same page
(`getpocket.com/explore`), whose robots.txt allows it; the source URL kept is
Pitchfork's own. Guitar World's robots.txt allows the article path.

`scripts/build_selection_evidence_review.py` resolves each song a pick names
(a pick of "Scarlet Begonias > Fire on the Mountain" is two entries). An entry
resolves only when its date holds one show and that show one performance of the
song. Otherwise it stays held: a date with no show in the catalog, a song not
played that night, or two renditions that night (`held_multiple_canonical_performances`).
A list's own typo (Guitar World's "Nassau 3-27-90", "Hamilton 4-22-90") is held,
not corrected.

## Sources not used

- **Headyversion** serves a Cloudflare 403 to automated requests for its pages
  (its robots.txt allows `*` but reserves AI training). Collection stopped there;
  the 2026-08-30 indexed-excerpt records remain the only Headyversion evidence.
- **Rolling Stone** (US) robots.txt disallows AI crawlers by name; its
  "20 Best Versions of Dark Star" list was not read.
- **Deadhead High** is crawlable, but its terms ask visitors not to scrape or
  republish its material, and its song pages rank shows, not performances.

## How the tool weighs this evidence

`get_song_notable_versions` counts a release family once (the album, its box,
its per-show volumes and its complete recordings; or several editions of one
night), then adds each source that names the very performance. A pick that names
the song on a night with two renditions is labelled "this song that night"; a
pick of the night is labelled "the whole show". A vote or pick for one song never
appears on another song played the same night. Versions are ordered by that
count, then by picks naming the performance, then fan votes.
