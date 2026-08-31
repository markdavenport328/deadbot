# Critic-signal source findings (bounded pass)

Retrieved 2026-08-30. This pass stores metadata and dated show identifiers only; it does not retain article/review prose, lyrics, audio, scans, or poll tables.

## Rolling Stone Australia — suitable attributed selection list

- URL: https://au.rollingstone.com/music/music-features/grateful-dead-shows-david-fricke-15410/
- Page title: “20 Essential Grateful Dead Shows”
- Published: 2020-08-10; byline: David Fricke.
- The page visibly enumerates 20 venue/date entries from 1966-12-01 through 1991-09-14. It states that the story first appeared in the 2013 special edition *Grateful Dead: The Ultimate Guide* and that a version was originally published in April 2013.
- Access: public HTML page at retrieval. Rights: copyright-restricted. Retention decision: metadata-only (title, byline, date, URL, and list membership/show identifiers).
- Classification: critic/editorial selection, not a fan poll or consensus ranking. Suitable for an attributed selection list when labeled “David Fricke / Rolling Stone”; not evidence that the shows are objectively the best.
- The 20 show records are in `data/raw/critic-signals/rolling-stone-australia-20-essential-shows.jsonl`.

## DeadBase 50 — bibliographic lead, not an open list source

- Bibliographic metadata is corroborated by the public Dead.net feature https://www.dead.net/features/all-family/all-family-stu-nixon and a retail catalog record: *DeadBase 50: Celebrating 50 Years of the Grateful Dead*, John W. Scott, Mike Dolgushkin, and Stu Nixon; Watermark Press; July 2015; ISBN-13 9780692470930.
- Access: publication metadata is public; the book’s Favorite Tapes/Tapers’ Choice tables were not verified from an authorized open source in this pass. Internet Archive or other circulating scans should not be treated as rights-cleared merely because they are reachable.
- Classification: fan reference manual / poll-bearing source. Suitable as a provenance target only after authorized access or independently verified page-level evidence. Do not import list membership from Reddit or composite summaries.

## Grateful Dead Projects — archival pointer and secondary lead

- Original site is described as defunct in fan discussions. A Wayback snapshot pointer is available at https://web.archive.org/web/20170312110959/http://gratefuldeadprojects.com/.
- Access: original site unavailable; snapshot existence is confirmed by the secondary pointer, but snapshot contents/completeness were not verified in this pass. Rights status is unknown/restricted.
- Classification: fan-curated site, not critic/editorial and not a statistically documented poll. The Reddit composite at https://www.reddit.com/r/grateful_dead/comments/1ra1m3x/the_top_50_grateful_dead_shows_of_all_time_a/ describes GDP inclusion as one component of a weighted composite; this is secondary fan commentary and a lead only.
- Suitability: do not use GDP or the Reddit composite as a primary attributed selection list without opening and checking the archived source and preserving its exact provenance. Keep any future extraction separate from critic/editorial signals.

## Operational implications

The Rolling Stone rows can be promoted as attributed editorial signals after normal show/venue entity matching. DeadBase and GDP rows should remain source leads with explicit uncertainty and access/rights flags. Any future promotion must preserve source type (critic-editorial, fan-reference/poll, fan-curated, or secondary-composite) and must not merge these categories into one unqualified “best shows” score.
