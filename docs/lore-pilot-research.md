# Lore pilot: first source trails

This is a small research packet for designing the editorial layer. It is not a
canonical-data import and it does not declare any performance objectively best.
Each trail has a different job: a concrete history, a source's editorial frame,
or a listener/community signal. Any visitor-facing assertion still needs the
relevant retrieved record and a clearly scoped attribution.

## Song-evolution trails

| Topic | Useful question | Source trail | What it gives Deadbot |
| --- | --- | --- | --- |
| Friend of the Devil | “Why do early and later versions feel so different?” | [Official Deadcast episode](https://www.dead.net/deadcast/american-beauty-50-friend-devil), [official song history](https://www.dead.net/song/friend-devil), [Deadhead High guide](https://deadheadhigh.com/guides/how-grateful-dead-songs-changed-live) | The Deadcast supplies American Beauty writing/recording context; the official song page documents early lyric variants. Deadhead High is a secondary listening guide that proposes the well-known fast-to-slower-live arc and useful comparison dates. Keep its musical characterization attributed. |
| They Love Each Other | “Why are the early versions faster?” | [Official song essay](https://www.dead.net/features/greatest-stories-ever-told/greatest-stories-ever-told-they-love-each-other), [Blues for Allah 50 episode](https://www.dead.net/blues-allah-50-blues-allah), [Deadhead High guide](https://deadheadhigh.com/guides/how-grateful-dead-songs-changed-live) | The official essay gives debut/studio context; the Deadcast explicitly places the slower arrangement with the 1975 revival. The secondary guide offers a compact listening comparison. Pair these with our own dated performances rather than letting any source stand in for the chronology. |
| Sugaree | “How can the song support very different readings and performances?” | [Official song essay](https://www.dead.net/features/greatest-stories-ever-told/greatest-stories-ever-told-sugaree) | A strong official source for Hunter's recalled writing context, plural lyric interpretation, and an editorial observation that live tempos and instrumental intensity varied. It supports an exploration route, not a definitive reading or best-version list. |
| Dancin' in the Streets | “What changed after the hiatus?” | [Deadessays debut chronology](https://deadessays.blogspot.com/2009/09/dead-song-debuts.html), [Official Grateful Dead Hour](https://www.dead.net/features/gd-radio-hour/grateful-dead-hour-no-458) | Deadessays identifies the 1976 rearrangement alongside other returning songs; its account is independent editorial research, not canonical chronology. The Grateful Dead Hour provides a useful Phil Lesh framing of the song's cultural identity. Retrieve exact performance facts from the local graph. |

## Show-context trails

| Topic | Useful question | Source trail | What it gives Deadbot |
| --- | --- | --- | --- |
| Veneta, 8/27/72 | “Did the heat materially affect the show?” | [Deadcast part 1](https://www.dead.net/sunshine-daydream-veneta-82772-part-1), [Deadcast part 2](https://www.dead.net/sunshine-daydream-veneta-82772-part-2) | The official two-part account makes weather, the Springfield Creamery benefit, setting, and recording/afterlife central to the story. It also presents multiple reported temperature figures and recollections; Deadbot should present those as source-reported context, not flatten them into a single exact weather fact. The historical-weather tool remains a distinct nearby-grid corroboration. |
| Cornell, 5/8/77 | “Why does this show have such an afterlife?” | [Peter Conners interview](https://www.dead.net/features/all-family/all-family-peter-conners), [Dick Latvala collection](https://www.dead.net/features/blog/documenting-dead-dick-latvala-collection), [Barton Hall archive page](https://www.dead.net/show/may-8-1977) | These establish useful routes through tape circulation, archive/reception history, and eyewitness/community material. They are ideal for an answer that first gives a straightforward setlist or recording fact, then offers an optional “how the legend grew” trail. Comments on the archive page remain visitor recollections, not event facts. |

## How to turn these into data

For each source, create a reviewed resource record with entity links, source
kind, publication/episode date where known, access/rights state, and a short
question-oriented `why_open` note. If a concise claim is worth storing, it
should name the source, scope, and review state; if it is a listener's or
writer's assessment, store it as attributed editorial context or a selection
signal. Do not store long copied passages, lyrics, or transcripts.

The first user-facing pilot should support three paths:

1. a Friend of the Devil cross-era comparison: local performance endpoints and
   recordings plus an optional official/secondary evolution trail;
2. a Sugaree listening exploration: a small recording route plus the official
   writing/interpretation essay; and
3. a Veneta fact question: canonical answer first, then the Deadcast's
   heat/benefit/story trail when it makes the visit richer.
