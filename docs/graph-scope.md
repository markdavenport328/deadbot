# What belongs in the Deadbot graph

Deadbot should keep the **identity, relationship, ordering, provenance, and access metadata** needed to answer questions reliably. It should link out to large, rights-sensitive, or source-owned content.

## Keep as structured graph data

| Information | Why it belongs in the graph |
| --- | --- |
| Songs, people, writers, venues, shows, performances, sets, and segues | These are the stable entities and relationships that support deterministic questions and exploration. |
| Actual performer/instrument assignments | A show-level relationship answers lineup and guest questions without assuming a fixed band roster. |
| Recording-source metadata, SHNIDs, Archive identifiers, lineage, and track mappings | Identifies a specific tape/source and connects it to a canonical performance without storing media. |
| Official releases and release-track-to-performance mappings | Makes questions such as “what official releases contain this performance?” answerable. |
| External link and resource metadata | Platform, URL, scope, source, relationship type, official status, title, and verified timestamp make media and reference links retrievable. |
| Song resources, source-specific arrangements, and concise chord progressions | These are structured, attributable music facts. Multiple arrangements can coexist. |
| Provenance and normalization decisions | They make source disagreements and manual corrections auditable. |

## Link out; do not copy into the repository

| Content | Stored graph metadata | External destination |
| --- | --- | --- |
| Audio and video | Show/performance ID, platform, URL, title, official status, optional timestamp | Internet Archive, YouTube, Spotify, Apple Music, Nugs, or another host |
| Full tabs, notation, lyrics, lesson text, and PDFs | Resource record, author/source, URL, arrangement summary | RUKIND, Weeping Willow Guitar, YouTube, publishers, or other original host |
| Full reviews, interviews, books, essays, liner notes, and fan commentary | Bibliographic/resource metadata, provenance, future text-index pointer | Original publisher, archive, or licensed document store |
| Maps, routing, weather, sunrise, and astronomy results | Query parameters, source, retrieval date, optional cached derived fact | External API or source record |

## Future retrieval layers

- **SQL / graph-like traversal:** factual questions about shows, songs, performances, recordings, releases, musicians, and links.
- **Document retrieval:** indexed excerpts and metadata for licensed or permitted prose such as interviews, liner notes, reviews, and analysis.
- **Live tools:** playback providers, weather, maps, astronomy, and current web research.

The rule of thumb: retain enough structured metadata to discover, explain, and link to something; retain the content itself only when its rights, licensing, and product value clearly justify it.
