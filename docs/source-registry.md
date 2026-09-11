# Reviewed source registry

`data/source_registry.json` is the source-controlled seed for the schema-v3
`source_registry` contract. It defines the first two bounded adapters:

- `deadnet-editorial`: approved first-party editorial search/read metadata and
  links on `dead.net`.
- `deadcast-metadata`: approved first-party episode metadata and links under
  `/deadcast`; it does not retrieve or retain transcript or audio content.

It also defines `wikidata-api`: the public Wikidata JSON web service at
`www.wikidata.org/w/api.php`, one request per second with a descriptive
User-Agent, metadata-only retention. `scripts/collect/fetch_band_membership_sources.py`
uses it to read the Grateful Dead item's member list (`P527`) and each
member's own `member of` statement (`P463`) with their start/end (`P580`/
`P582`) qualifiers, plus date of birth (`P569`) and date of death (`P570`) --
feeding `data/canonical/band_memberships.csv` and the `birth_date`/
`death_date` fill in `data/canonical/people.csv`. The same script's second
request extends `musicbrainz-api`'s existing `search`/`browse` operations
with a new `lookup` operation (`GET /ws/2/artist/<mbid>?inc=artist-rels`) for
the band's own "member of band" relations.

Each entry includes the schema-v3 authority, access, rights, and review states,
adapter version, retention and rate policies, and an operation policy that
combines an HTTP method allowlist with path prefixes. The JSON seed is
declarative: it does not itself permit network access. Validate it with
`deadbot.source_registry.load_registry()` before importing/promoting rows into
the operational table. Changes to hosts, paths, operations, rights, or policy
require review and a new adapter version where behavior changes.

The `get_deadnet_song_context` tool consults the approved `deadnet-editorial`
entry before creating its metadata-only reader. The `get_deadcast_metadata`
tool similarly consults `deadcast-metadata` and reads only an episode route
under `/deadcast/<slug>`. A missing, unapproved, or invalid local entry
disables that optional tool path. The runtime reader returns only a page title,
optional page metadata, and an allowlisted link; it never retains page body,
lyrics, transcripts, or audio.

The adapter accepts only HTTPS requests to registry hosts and configured path
prefixes. Identifiers are slug-shaped and returned title/description fields
are bounded short metadata. The reviewed endpoints are `GET
https://www.dead.net/search` for editorial entity search,
`GET https://www.dead.net/song/<slug>` (plus other registry-approved entity
paths), and `GET https://www.dead.net/deadcast/<slug>` for episode metadata.
These two adapters remain metadata-only. Since 2026-09-03 the separate
research tools (`read_page`, `search_site`, `get_recording_reviews`) read
public pages at request time without storing them; they are governed by
`data/research_sites.json` as a suggestion list, not by this registry. See
`docs/superpowers/specs/2026-09-03-source-reading-design.md`.
