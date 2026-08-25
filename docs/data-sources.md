# Candidate data sources

The 1972 pilot has collected three low-volume raw records from JerryBase and Internet Archive. Details not yet independently researched remain **TBD**.

For each candidate, assess data quality, terms, attribution requirements, access stability, and whether records can be preserved and regenerated responsibly.

## JerryBase

- What it provides: Public event pages with show context, venue/location, musicians, setlists, releases, tours, recording references, and notes.
- Access method: Public web pages; no collection API has been adopted for this project.
- Structured fields: Event date, venue, location, performer names/instruments, ordered sets, tour, releases, and recording references are visible on event pages.
- Coverage: The 1972 pilot confirms a Grateful Dead event record for 1972-08-27.
- Authority / reliability: Primary source for the 1972 pilot's show, setlist, and performer assertions; corrections and conflicts remain reviewable.
- Licensing / usage considerations: TBD. Use low-volume, source-attributed collection only until terms and an appropriate access method are reviewed.
- Potential canonical entities populated: Shows, venues, performances, people, show performers, and recording cross-references.
- Known limitations: Public page data is not yet a bulk-import interface; source-specific title, instrument, and setlist notation require normalization.

## gdshowsdb

- What it provides: A public relational Grateful Dead show database with committed, year-specific YAML files, normalized song references, show sets, positions, and segue indicators.
- Access method: Public Git repository and GitHub Contents API.
- Structured fields: Year YAML files, song-reference data, show details, set segmentation, ordered song occurrences, and segue markers.
- Coverage: A committed `1972.yaml` file is available in the repository.
- Authority / reliability: Primary bulk baseline for 1972 show and performance ingestion. JerryBase remains a review source for corrections and disputed records.
- Licensing / usage considerations: Repository is published under the MIT License. Pin each retrieved raw file by its GitHub blob SHA.
- Potential canonical entities populated: Shows, venues, songs, performances, and segues.
- Known limitations: The source must still be reconciled against the canonical model and independently reviewed where it conflicts with other evidence.

## Internet Archive Grateful Dead collection

- What it provides: Recording-item metadata, identifiers, source descriptions, lineage, taper/transfer information, collection status, and file/track metadata.
- Access method: Read-only item metadata endpoint and collection search endpoint.
- Structured fields: Archive identifier, date, title, venue, coverage, source, lineage, taper, transferer, and supplied track/file fields.
- Coverage: The pilot query returned 364 1972 collection items and preserved one item-metadata record for 1972-08-27.
- Authority / reliability: Primary source for the 1972 pilot's recording-source metadata.
- Licensing / usage considerations: Audio availability varies by item and collection policy. This pilot retrieved metadata only; it did not download or store audio.
- Potential canonical entities populated: Recordings and performance-recording locations, with supporting show/venue values for reconciliation.
- Known limitations: Values are item-supplied metadata and can vary between sources; one show can have many items and a track title can use source-specific notation.

## Relisten

- What it provides: Public browsing of shows, recording sources, source types, taper/transfer details, SHNIDs, lineages, and track-level presentation.
- Access method: Public web pages were confirmed; an API and its usage policy remain to be evaluated before automated collection.
- Structured fields: Show date/location, source type, recording duration, taper, transferer, SHNID, lineage, and track information are visible on source pages.
- Coverage: 1972 is the chosen pilot year, but no Relisten record has yet been collected.
- Authority / reliability: Secondary enrichment and reconciliation candidate for recording and timing data; not yet selected as a 1972 primary source.
- Licensing / usage considerations: TBD.
- Potential canonical entities populated: Recordings, performance recordings, and source cross-references.
- Known limitations: Its source records may represent, link to, or derive from external archive material; preserve identifiers and compare against the underlying item metadata.

## setlist.fm

- What it provides: TBD
- Access method: TBD
- Structured fields: TBD
- Coverage: TBD
- Authority / reliability: TBD
- Licensing / usage considerations: TBD
- Potential canonical entities populated: TBD
- Known limitations: TBD

## Grateful Dead Family Discography / DeadDisc

- What it provides: Discography, live and studio releases, release-by-recording-date pages, cover relationships, and Grateful Dead–related discographic research.
- Access method: Public web pages.
- Structured fields: Release titles, release categories, recording-date references, and artist/discography relationships are visible on the site.
- Coverage: The site provides both a general discography and releases organized by recording date.
- Authority / reliability: Research and reconciliation candidate for future official-release data; not a 1972 primary source yet.
- Licensing / usage considerations: TBD.
- Potential canonical entities populated: Future official-release, release-track, composition, and cover relationships.
- Known limitations: The current canonical schema has no release/release-track tables; do not force release data into `recordings`.

## RUKIND

- What it provides: Song, tab, chord, title, show, and venue browsing.
- Access method: Public tab pages can be discovered and inspected; the broad title endpoint returned HTTP 403 during this evaluation.
- Structured fields: The sampled Sugaree page provides title, writer display, update date, source-specific key, and chord display.
- Coverage: TBD.
- Authority / reliability: Source-specific tab/chord reference. It is not a universal chord authority or a 1972 show/setlist source.
- Licensing / usage considerations: TBD; do not automate collection without an access/usage review.
- Potential canonical entities populated: Song resources, source-specific arrangements, and chord sections.
- Known limitations: Access controls block the evaluated broad title endpoint. Preserve attribution and scope; do not copy full tablature or treat an interpretation as a universal chart.

## MusicBrainz

- What it provides: TBD
- Access method: TBD
- Structured fields: TBD
- Coverage: TBD
- Authority / reliability: TBD
- Licensing / usage considerations: TBD
- Potential canonical entities populated: TBD
- Known limitations: TBD

## Official Grateful Dead releases / catalog

- What it provides: TBD
- Access method: TBD
- Structured fields: TBD
- Coverage: TBD
- Authority / reliability: TBD
- Licensing / usage considerations: TBD
- Potential canonical entities populated: TBD
- Known limitations: TBD

## YouTube

- What it provides: External full-show and performance-specific videos, lessons, interviews, and demonstrations.
- Access method: Public page links and provider-hosted playback.
- Structured fields: Video URL, title, channel, publication date, and explicit song/show scope where a source identifies them.
- Coverage: The Veneta pilot includes one full-show SBD upload and one Promised Land performance-video link.
- Authority / reliability: Link-out/provider source. Treat uploader identity, title, and stated scope as source metadata; do not treat a video alone as the canonical setlist authority.
- Licensing / usage considerations: Store links and concise metadata only; do not download or redistribute video/audio without a separately verified right.
- Potential canonical entities populated: Show links, performance links, and future tutorial/resource references.
- Known limitations: A full-show upload does not establish verified timestamps for each performance; record timestamps only when directly sourced or independently checked.

## Spotify

- What it provides: Official catalog and release/track links for streaming and playback where available.
- Access method: Public album and track pages; any API use is TBD.
- Structured fields: Release/track titles, artist, release date, duration, and provider URLs.
- Coverage: The Veneta pilot includes the 2013 complete-concert album and maps its 20 song tracks to canonical performances.
- Authority / reliability: Primary link-out source for the provider's own catalog metadata; cross-check release identity and performance mapping against other evidence where needed.
- Licensing / usage considerations: Store links and metadata only. Playback is governed by Spotify's service and the user's access.
- Potential canonical entities populated: Official releases, official release tracks, and provider links.
- Known limitations: Availability and URL behavior can change by market; a release can include intros, banter, or edits that do not map one-to-one to song performances.

## Dead.net / Good Ol’ Grateful Deadcast

- What it provides: Official editorial articles, podcast episodes and transcripts, archival interview excerpts, song histories, show oral histories, and release context.
- Access method: Public web pages; retain links and concise metadata rather than copying articles or transcripts.
- Structured fields: Title, author or host, source URL, publication date where displayed, resource type, and song/show/performance relationship.
- Coverage: The Veneta pilot now links two official oral-history episodes and selected song-context pieces for Sugaree, Deal, Bird Song, China Cat Sunflower, I Know You Rider, Playing in the Band, He’s Gone, Dark Star, and Sugar Magnolia.
- Authority / reliability: First-party editorial context and a strong starting point for the retrieval layer. Statements from interview subjects, especially recollections of origins or events, stay attributed to that source.
- Licensing / usage considerations: Store metadata, short editorial scope notes, and links only; do not copy or redistribute transcripts/audio absent a separately reviewed right.
- Potential canonical entities populated: Generic resources and resource-to-song/show/performance relationships; occasionally a reviewed supporting source for a future canonical fact.
- Known limitations: Editorial accounts are not automatically a canonical authority for all historical claims, and podcast pages may not show a publication date.

## Independent reporting and archive-hosted memoirs

- What it provides: Local reporting based on participant interviews and firsthand retrospective accounts.
- Access method: Public article and archive-item pages; link out to the original material.
- Structured fields: Byline, publisher, date where displayed, resource URL, resource type, and show/performance relationship.
- Coverage: The Veneta pilot links an OPB/KLCC report built on Kesey-family interviews and a Grateful Dead Archive Online attendee memoir.
- Authority / reliability: Useful contextual evidence. Reporting and first-person testimony should be identified by source and treated separately from canonical show facts.
- Licensing / usage considerations: Store links, metadata, and concise notes only. Archive-hosted memoirs may have separate reuse restrictions.
- Potential canonical entities populated: Generic contextual resources and source-attributed anecdotal evidence.
- Known limitations: A memoir's impressions and remembered details are subjective; reported figures and claims need corroboration before use as canonical data.

## Apple Music

- What it provides: Official catalog resolution and external playback links.
- Access method: TBD.
- Structured fields: TBD.
- Coverage: TBD.
- Authority / reliability: Provider metadata/link-out candidate.
- Licensing / usage considerations: TBD.
- Potential canonical entities populated: Additional official-release provider links.
- Known limitations: TBD.

## Other sources discovered later

- What it provides: TBD
- Access method: TBD
- Structured fields: TBD
- Coverage: TBD
- Authority / reliability: TBD
- Licensing / usage considerations: TBD
- Potential canonical entities populated: TBD
- Known limitations: TBD
