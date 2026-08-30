# Reviewed source registry

`data/source_registry.json` is the source-controlled seed for the schema-v3
`source_registry` contract. It defines the first two bounded adapters:

- `deadnet-editorial`: approved first-party editorial search/read metadata and
  links on `dead.net`.
- `deadcast-metadata`: approved first-party episode metadata and links under
  `/deadcast`; it does not retrieve or retain transcript or audio content.

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
No generic URL fetch is provided.
