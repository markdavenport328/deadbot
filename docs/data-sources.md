# Candidate data sources

The 1972 pilot began with low-volume JerryBase and Internet Archive records and
now includes the pinned gdshowsdb year baseline plus targeted song-source
enrichment. Details not yet independently researched remain **TBD**.

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
- Coverage: Committed year files are available in the repository; this project
  has collected the 1965–1995 show/setlist baseline.
- Authority / reliability: Primary bulk baseline for 1972 show and performance ingestion. JerryBase remains a review source for corrections and disputed records.
- Licensing / usage considerations: Repository is published under the MIT License. Pin each retrieved raw file by its GitHub blob SHA.
- Potential canonical entities populated: Shows, venues, songs, performances, and segues.
- Known limitations: The source must still be reconciled against the canonical model and independently reviewed where it conflicts with other evidence.

## JerryBase performer enrichment

- What it provides: Event-level musicians, guest musicians, source instrument strings, and event identifiers for Grateful Dead shows.
- Access method: Public event index and event pages; the collector stores compact JSONL evidence and does not copy full page contents.
- Structured fields: Event date, venue, billed act, musician/guest display name, and instrument description.
- Coverage: Snapshots now cover 2,268 of 2,358 canonical shows across 1965–1995. The 90 held shows are recorded in year-specific coverage reports; the collector accepts the full range through its `--all` option.
- Authority / reliability: Source-reviewed enrichment for who and what instrument the event page lists; it is not used to infer a standing band roster or a named guitar when the page does not say one.
- Licensing / usage considerations: Preserve concise metadata and source URLs only; review site terms before broader redistribution.
- Potential canonical entities populated: People and show-performer role/instrument assignments; future source-specific instrument details when explicitly tied to an event.
- Known limitations: Same-date event selection requires venue reconciliation; unidentified and question-marked source names stay raw and are not promoted. JerryBase's standard musician field generally gives musical roles rather than named guitar models, so show-specific Wolf/Tiger/Rosebud assignments require a separate equipment-history source.

## Jerry Garcia guitar-history enrichment

- What it provides: Named guitar identities and dated range or specific-show claims for instruments Jerry Garcia played.
- Access method: Public instrument-history article, preserved as compact claim metadata with a content hash rather than copied full page text.
- Structured fields: Equipment entity, manufacturer/model, show link, usage context, evidence scope, source note, and source URL.
- Coverage: 2,249 links across the canonical 1965–1995 show set from 31 explicit source claims.
- Authority / reliability: Secondary research source that states its claims are confirmed through photographic and video evidence; it is distinct from JerryBase's event-level lineup data.
- Licensing / usage considerations: Store concise attributed metadata and source URLs only; do not reproduce the source article or images.
- Potential canonical entities populated: Named equipment entities and show-equipment relationships.
- Known limitations: Date ranges do not imply exclusivity, and the source is not a complete song-by-song or set-by-set equipment log. Ambiguous or non-Grateful Dead side-project claims remain out of the canonical show links.

## Internet Archive Grateful Dead collection

- What it provides: Recording-item metadata, identifiers, source descriptions, lineage, taper/transfer information, collection status, and file/track metadata.
- Access method: Read-only item metadata endpoint and collection search endpoint.
- Structured fields: Archive identifier, date, title, venue, coverage, source, lineage, taper, transferer, and supplied track/file fields.
- Coverage: Metadata-only recording indexes now cover the 1965–1995 baseline
  with 18,325 unique items; one representative item per 1,910 safely linked
  canonical shows has also been preserved with full item metadata.
- Track enrichment: 16,487 additional performance-recording links were
  promoted from representative file metadata when source track order aligned
  uniquely with the canonical setlist; source durations were retained, while
  playback start times were left blank.
- Per-track playback links (2026-09-01): 16,505 `performance_links` rows
  (`platform=archive`, `link_type=recording-track`) were derived offline from
  the preserved representative file names as
  `https://archive.org/details/{identifier}/{file}`, which opens the
  archive.org player on that track. Two Veneta encore rows are held because
  their source titles carry an `E1:`/`E2:` prefix. See
  `docs/collection-status-performance-track-links.md`.
- Show listing links (2026-09-01): 1,910 `show_links` rows
  (`platform=archive`, `link_type=recording-index`) point at the collection
  search page for the show date, written only for shows that already have
  recording rows because the listing page returns HTTP 200 even for dates
  with no items. See `docs/collection-status-show-listening-links.md`.
- Authority / reliability: Primary source for the 1972 pilot's recording-source metadata.
- Licensing / usage considerations: Audio availability varies by item and collection policy. This pilot retrieved metadata only; it did not download or store audio.
- Potential canonical entities populated: Recordings and performance-recording locations, with supporting show/venue values for reconciliation.
- Known limitations: Values are item-supplied metadata and can vary between sources; one show can have many items, a track title can use source-specific notation, and same-day shows without a distinguishing source field remain unmapped rather than guessed.

## Relisten

- What it provides: Public browsing of shows, recording sources, source types, taper/transfer details, SHNIDs, lineages, and track-level presentation.
- Access method: Public JSON API (`https://api.relisten.net/api/v2/artists/grateful-dead/years/<year>` and `/years/<year>/<date>`), confirmed working 2026-09-01. `scripts/collect/fetch_relisten_years.py` fetches one year listing per request at one request per second with a descriptive User-Agent and stores compact metadata only.
- Structured fields: Per show, display date, source count, average rating, soundboard/FLAC flags, venue name and location; per source, source type, taper, transferer, SHNID, lineage, and per-track archive.org stream URLs.
- Coverage: 31 year listings (1965–1995) preserved in `data/raw/recordings/relisten-years.jsonl`; 2,080 Relisten show dates, 1,963 of which match canonical shows. Those shows now carry a `show_links` row (`platform=relisten`, `link_type=streaming-show-page`) pointing at `https://relisten.net/grateful-dead/YYYY/MM/DD`. 144 Relisten dates have no canonical show and are reconciliation candidates. See `docs/collection-status-show-listening-links.md`.
- Authority / reliability: Secondary. Relisten is a player over the Internet Archive's Grateful Dead collection; its ratings and review counts are archive.org community signals surfaced through the API. Preserve identifiers and compare against the underlying item metadata.
- Licensing / usage considerations: The about page describes a free, non-commercial, open-source project (API server MIT, web client AGPL-3.0) that complies with Archive.org policy and posts the band's taping and distribution stipulations. No written API terms, rate limits, or usage policy were found; the API docs endpoint is not public. Current use is 31 metadata requests and link-outs to Relisten's own pages. Ask the Relisten team (GitHub or Discord) before higher-volume or scheduled collection, and add a source-registry entry before the runtime agent reads Relisten directly. Name Relisten as the player and the Internet Archive as the recording source in any user-facing surface.
- Potential canonical entities populated: Show links today; recordings, performance recordings, and source cross-references later.
- Known limitations: Relisten lists one show per date, so early and late shows on the same date share a URL (54 rows, noted on each row). Shows with no known tape (nearly all 1965–1970 gaps) do not appear.

## Research blogs (Lost Live Dead, Hooterollin' Around, Grateful Dead Guide / Deadessays, Dead Sources, Grateful Seconds)

- What it provides: Long-form independent research on the band. Lost Live Dead
  reconstructs individual shows, venues, tours and the band's business,
  strongest on 1965–1975. Hooterollin' Around covers side projects, guests,
  personnel and the wider Bay Area scene. Grateful Dead Guide (Deadessays)
  analyses songs, jams and arrangements era by era. Dead Sources transcribes
  contemporary press — reviews, interviews and news items from the years the
  shows happened. Grateful Seconds counts things: song placements, firsts and
  lasts, streaks and oddities, plus one Deadhead's show diary.
- Access method: Each site is a public Blogger blog with an Atom post feed.
  `scripts/collect/collect_blog_post_index.py` reads `robots.txt` first, then
  walks `/feeds/posts/summary?alt=json&max-results=150&start-index=N`, one
  request at a time at least two seconds apart, with
  `User-Agent: Deadbot/0.1 (metadata index; contact via repository)`. 29
  requests indexed all five sites on 2026-09-08. Post pages themselves are not
  fetched by the collector; the runtime research tools (`read_page`,
  `search_site`) read them at request time without storing them.
- Structured fields: Post title, post URL, published and updated timestamps,
  post labels, and the feed's author byline. Nothing else.
- Retention boundary: **Metadata only.** No post body, summary or excerpt is
  stored in raw, canonical or editorial files, and none may be added. Canonical
  `notes` carries the post's own labels plus the retention sentence. These are
  independent authors' copyrighted essays: the catalog holds a link and a
  title, which is what makes the post findable, and the reader goes to the
  author's page for the writing.
- Coverage (2026-09-08): 1,740 posts indexed — 298 Lost Live Dead, 133
  Hooterollin', 184 Deadessays, 575 Dead Sources, 550 Grateful Seconds — each
  host's count equal to the total its own feed reports. 133 `resource_songs`
  rows cover 63 songs and 566 `resource_shows` rows cover 419 shows, all
  `relationship_type` `about`; 896 posts are stored with no relationship and
  211 are held for review. See `docs/collection-status-lore-blog-index.md`.
- Authority / reliability: Independent research and criticism, cited as such.
  Lost Live Dead and Dead Sources document their evidence carefully and are
  strong review sources for show history, but none of the five is a setlist or
  show authority for this project; gdshowsdb remains the canonical baseline. A
  mapped row says a post's title names a song or a date, not that the post's
  claims are canonical.
- Licensing / usage considerations: Public blogs with no stated reuse licence.
  Store links, titles and the sites' own labels only, name the site and its
  author wherever a row is shown, and keep collection to the feed at low
  volume. A pass that wanted post text would need the authors' permission
  first.
- Potential canonical entities populated: Generic resources and typed
  resource-to-song / resource-to-show relationships. Never a show, song, date
  or setlist value.
- Known limitations: A title-based mapping is a pointer, not a reading. A date
  in a title can belong to an interview or a side-project set on a Dead show
  day; a run of shows or a date carrying two shows is held rather than guessed;
  and these sites title posts by date and venue far more often than by song, so
  song coverage stays thin. Grateful Seconds' custom domain is http-only, so
  its rows store the blog's own https address for the same post.

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

- What it provides: Work-level title, composer, lyricist, and writer relationships, with stable work and artist identifiers.
- Access method: Official JSON web service at `musicbrainz.org/ws/2/work`; the collection script spaces requests and preserves the query/result summary.
- Structured fields: Work ID, title, score, ISWC values where supplied, and source-reported composer/lyricist/writer relationships.
- Coverage: 80 title queries for the 1972 song set; 60 responses were available in the collected run, with 52 exact-title matches and 51 exact matches carrying credit relations.
- Authority / reliability: Secondary structured catalog for composition-credit reconciliation. Exact-title results are not automatically authoritative for a Dead performance when a title is shared by unrelated works.
- Licensing / usage considerations: Preserve identifiers, concise metadata, and source URLs; review MusicBrainz attribution/database terms before redistributing a larger derived dataset.
- Potential canonical entities populated: Songs, people, and role-level song-writer relationships.
- Known limitations: Title-only search can return unrelated works, traditional works may not map to a person, and a work's role model may differ from a source's display convention. Ambiguous matches remain in raw records and are not canonicalized.

## Band membership (MusicBrainz + Wikidata)

- What it provides: Who was a core or officially recognized Grateful Dead
  member, in what role, and over what dates, plus each member's date of birth
  and (where applicable) date of death.
- Access method: `scripts/collect/fetch_band_membership_sources.py` makes two
  requests, one second apart, both read-only and unauthenticated: MusicBrainz
  `GET /ws/2/artist/6faa7ca7-0d99-4a5e-bfa6-1fd5037520c6?inc=artist-rels` for
  the Grateful Dead artist's `member of band` relations (`begin`/`end`/
  `ended`, plus role attributes such as `keyboard`); and Wikidata
  `wbgetclaims` for the band item (`Q212533`) property `P527` ("has part(s)")
  to enumerate members, followed by `wbgetentities` on each member QID for
  their label, date of birth (`P569`), date of death (`P570`), and their own
  `P463` ("member of") statement for the band with its `P580`/`P582` start/end
  qualifiers. `scripts/normalize_band_membership.py` reads those raw records
  plus `show_performers.csv`'s `role == "performer"` rows (never `guest`) to
  cross-check each source tenure against the band's own documented lineup and
  writes `data/canonical/band_memberships.csv`.
- Structured fields: MusicBrainz artist MBID, relation begin/end/ended and
  attributes; Wikidata QID, birth/death dates, and member-of start/end
  qualifiers at whatever precision (year, sometimes month) Wikidata records.
- Coverage (2026-09-11): 13 tenure rows for 12 people -- the five
  1965-founding members (Garcia, Weir, Lesh, Kreutzmann, Pigpen), Mickey Hart
  across two tenures (1967-1971 and 1975-1995), the post-Pigpen keyboardists
  (Constanten, Keith Godchaux, Mydland, Welnick), Donna Jean Godchaux, and
  touring auxiliary member Bruce Hornsby. `people.csv` `birth_date`/
  `death_date` were filled for the same 12 people (plus their two
  JerryBase `(complete show)` duplicate rows) from Wikidata. See
  `docs/collection-status-band-membership.md` for the full comparison,
  including where MusicBrainz, Wikidata, and the lineup evidence disagree.
- Authority / reliability: Both are secondary structured catalogs, cross-checked
  against the band's own canonical performance ledger rather than trusted
  alone; `show_performers` evidence is preferred for exact dates, with the
  source claims retained in `notes` for comparison.
- Licensing / usage considerations: MusicBrainz core data and Wikidata
  statements are both CC0. Rows cite the MusicBrainz artist MBID (all rows
  in this pass) and name the corroborating Wikidata QID in `notes`.
- Potential canonical entities populated: `band_memberships`, and the
  `birth_date`/`death_date` columns of `people`.
- Known limitations: This pass covers only the twelve core/officially
  recognized members documented by both sources; MusicBrainz's relation also
  names Robert Hunter (lyricist, never a performing member) and Rob Wasserman
  (a solo/duo collaborator), both excluded as not band members. A held
  disagreement remains for Pigpen's end date (MusicBrainz gives his death
  year 1973; Wikidata and the lineup evidence agree on his last performance,
  1972-06-17) -- see the status doc rather than treating either as settled
  without review.

## Official Grateful Dead releases / catalog

- What it provides: Official live release identities, release dates, track lists, per-track recording dates where MusicBrainz editors recorded them, and streaming URL relationships.
- Access method: MusicBrainz web service (JSON, one request per second, descriptive User-Agent, backoff on 429/503). `scripts/collect/fetch_musicbrainz_live_releases.py` resolves the artist MBID by search, enumerates Album+Live release groups, and browses official releases with recordings and URL relationships; `scripts/normalize_musicbrainz_live_releases.py` resolves releases to canonical shows and aligns tracks with setlists. `scripts/collect/fetch_musicbrainz_studio_releases.py` browses Album (non-Live) release groups across the Dead and its solo/side-project artists and, with `--artist-relations`, looks up per-person instrument credits on the promoted releases; `scripts/normalize_musicbrainz_studio_releases.py` promotes studio albums, resolves each track title to a canonical `song_id`, and writes `release_personnel`.
- Structured fields: Release-group and release MBIDs, titles, disambiguations, dates, medium and track titles and lengths, recording disambiguations (often `live, YYYY-MM-DD: venue`), `streaming` URL relationships, and artist-relation instrument/vocal credits.
- Coverage (2026-09-01): 991 live release groups enumerated; 293 promoted to `official_releases.csv` (157 single-show, 136 spanning several shows); 10,024 tracks written, 6,993 mapped to a canonical performance; 65 releases and 399 tracks carry Spotify URLs from MusicBrainz. 33 release groups and 3,031 tracks are held with reasons. See `docs/collection-status-official-releases.md`. The 2026-09-05/06 studio pass added the Dead-family studio catalog — 46 studio albums across the Grateful Dead, Jerry Garcia, Jerry Garcia Band, Bob Weir, New Riders of the Purple Sage, Old & In the Way and Kingfish — with 447 tracklist rows, 133 resolved to a canonical song, and 205 `release_personnel` rows. A separate backfill (`scripts/normalize_release_track_songs.py`) then extended `song_id` resolution to live-release tracks as well, bringing tracks carrying a `song_id` to 9,380 of 10,492 catalog-wide. See `docs/collection-status-studio-releases.md`.
- Authority / reliability: Secondary structured catalog. Titles, order, and dates are contributor-entered; recording dates were used as attribution evidence for existing canonical shows, never to create shows.
- Licensing / usage considerations: MusicBrainz core data is CC0. Rows cite the release MBID in `source_url` and `notes`; keep a "source: MusicBrainz" credit where these fields are shown. Spotify and Apple Music URL coverage needs a credentialed API pass with a rights review; it is deferred until credentials exist.
- Potential canonical entities populated: Official releases, official release tracks, and later a release-to-show coverage table and a track-segment bridge for suites and medleys.
- Known limitations: Two-show releases without per-track dates, early/late show dates, and undated bonus tracks remain unmapped pending per-track evidence. `Rhythm Devils` is treated as an alias of `Drums`, the setlist spine's name for the drummers' segment.

## Wikipedia (English)

- What it provides: Album infobox metadata, most usefully a `Released` field that is frequently more precise (a full date, or a year-month) than MusicBrainz's release-group `first_release_date` for the same studio album.
- Access method: The public MediaWiki action API at `en.wikipedia.org/w/api.php` (JSON, one request per 1.5 seconds, descriptive User-Agent, backoff honoring a numeric `Retry-After` on 429/503). `scripts/collect/fetch_wikipedia_album_dates.py` reads `official_releases.csv` for every `studio` row whose `release_date` is a bare year or year-month, resolves each to a Wikipedia article with `action=query&list=search` (a curated title table for the 25 albums in the 2026-09-06 pass, verified present in live search results before use; a generic fold-and-disambiguator heuristic for anything added later), fetches that article's current wikitext with `action=query&prop=revisions`, and extracts the infobox `Released` field verbatim with a regex anchored on `| released =`. `scripts/normalize_wikipedia_album_dates.py` parses that raw string (`{{Start date|...}}`, `Month D, YYYY`, `Month YYYY`, or a bare year, after stripping `<ref>` citations and wikilink brackets) and upgrades `release_date` only when the parsed year agrees with the existing value and the parsed precision is strictly finer.
- Structured fields: Article title, page id, revision id, article URL, and the raw infobox `Released` string. No other article text, images, or full wikitext is retained, matching the `wikipedia-api` source-registry entry's `metadata_only` / `store_content: false` policy.
- Coverage (2026-09-06): 25 of 46 studio albums had a year-only or year-month `release_date`; all 25 were matched to a confident Wikipedia article and yielded a parseable `Released` field. 11 were sharpened (`Ace` 1972-05 → 1972-05-01; `17 Pine Avenue` 2012-03 → 2012-03-06; `Cats Under the Stars`, `Compliments of Garcia`, `Heaven Help the Fool`, `Jerry Garcia / David Grisman` all year → full date; `Gypsy Cowboy`, `New Riders of the Purple Sage`, `Powerglide`, `The Adventures of Panama Red` year → year-month; `Reflections` 1976-02 → 1976-02-03). 4 disagreed with the existing year and were held as conflicts rather than resolved one way (`Hooteroll?` 1970 vs Wikipedia 1971; `Feelin' All Right` 1980 vs 1981; `Marin County Line` 1993 vs 1977; `Midnight Moonlight` 1993 vs 1992). 10 were already at Wikipedia's own precision (9) or more precise than Wikipedia offers (`Run for the Roses`, whose Wikipedia infobox gives only `1982` against the existing `1982-11`). See `docs/collection-status-studio-releases.md`.
- Authority / reliability: Tertiary, crowd-edited encyclopedia. Treated here strictly as a precision-sharpening cross-check against MusicBrainz's already-promoted date, never as a source that can introduce a new album, override a disagreeing year, or add a date where none exists.
- Licensing / usage considerations: Wikipedia article text is CC BY-SA (share-alike, attribution required), not CC0. Only a short, verbatim infobox field is extracted and stored — never article prose, images, or full wikitext — and rows cite the article URL and revision id in the raw record for attribution.
- Potential canonical entities populated: `official_releases.release_date` only, at finer precision.
- Known limitations: A conflicting year is a review item for a human, not something this pass resolves; the four conflicts above are open questions. The search step's confidence rule is curated per-album for the 2026-09-06 catalog; an album added to the target set later falls back to a generic title-fold heuristic that may need its own curated entry if the fallback cannot find a unique match.

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
- Coverage: The Veneta pilot includes the 2013 complete-concert album and maps its 20 song tracks to canonical performances. The 2026-09-01 MusicBrainz pass added 65 album URLs and 399 track URLs from MusicBrainz streaming relationships; most Dick's Picks, Dave's Picks, Road Trips, and Download Series entries still lack one.
- Authority / reliability: Primary link-out source for the provider's own catalog metadata; cross-check release identity and performance mapping against other evidence where needed.
- Licensing / usage considerations: Store links and metadata only. Playback is governed by Spotify's service and the user's access.
- Potential canonical entities populated: Official releases, official release tracks, and provider links.
- Known limitations: Availability and URL behavior can change by market; a release can include intros, banter, or edits that do not map one-to-one to song performances.

## Dead.net / Good Ol’ Grateful Deadcast

- What it provides: Official editorial articles, podcast episodes and transcripts, archival interview excerpts, song histories, show oral histories, and release context.
- Access method: Public web pages; retain links and concise metadata rather than copying articles or transcripts.
- Structured fields: Title, author or host, source URL, publication date where displayed, resource type, and song/show/performance relationship.
- Coverage: The 1972 song pass resolved 54 Dead.net song pages for the 80-title set; 51 expose lyric-page content and 52 expose credit fields. The canonical layer stores source links and concise metadata, not full lyrics.
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
