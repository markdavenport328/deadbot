# Collection methodology

This is the practical playbook learned from the 1972 expansion. It applies to
future years and to future enrichment of 1972.

## Start with a coverage matrix

Before collecting, list the target entities and the fact types to be filled:

| Fact type | Example | Preferred collection shape |
| --- | --- | --- |
| Show and setlist baseline | date, venue, ordered songs, segues | Bulk source, one pinned raw snapshot |
| Recording inventory | archive item IDs, lineage, source descriptions | Search index followed by selected item metadata |
| Song catalog | stable title/slug, aliases, performance counts | Normalize from the show baseline before enrichment |
| Composition credits | lyricist, composer, writer | Work/catalog lookup plus source-page review |
| Lyric availability | page URL, page status, lyrics-present flag | External source link and compact metadata only |
| Context | interview, article, memoir, lesson | Generic resource with typed entity relationships |
| Performance detail | lineup, recording track, timestamp | Targeted source review; never infer from a show-level record |

Record the expected coverage and known gaps before the pass begins. A missing
fact should remain visibly missing; it should not be silently replaced with a
plausible value from a neighboring source.

## Use different sources for different jobs

The 1972 pass showed that sources fall into three useful classes:

1. **Enumeration sources** establish the bounded universe. The pinned gdshowsdb
   year file supplied the 86 shows, 2,229 ordered performances, and 80 song
   labels.
2. **Enrichment sources** add a specific fact type. Internet Archive supplied
   recording identifiers and metadata; MusicBrainz supplied work-level credit
   candidates; Dead.net supplied official song-page links and displayed credits.
3. **Review/context sources** explain or challenge a fact. JerryBase, interviews,
   oral histories, memoirs, and editorial pages should remain attributed
   evidence unless the project explicitly promotes a claim to canonical status.

Do not use a convenient source as a universal authority. Select a primary and
fallback source by fact type, and define the override rule before resolving a
conflict.

## Keep the four layers separate

The reliable path is:

```text
source request → compact raw record → normalization decision → canonical row → validation
```

- **Raw records** preserve source identity, URL, retrieval time, request
  status, stable external IDs, and the concise fields needed to reproduce the
  decision. They may contain source-specific spellings and failed attempts.
- **Normalization scripts** perform matching, alias handling, role mapping,
  deduplication, and explicit exclusions. They should be rerunnable and
  deterministic.
- **Canonical files** contain only reviewed conclusions and stable internal
  IDs. They should not become a second unmarked web cache.
- **Resources** retain external links and typed relationships. A resource link
  is evidence or a path to the source; it is not automatically a canonical
  claim.

For each pass, keep a short status document with counts for requested,
successful, unresolved, promoted, and held-for-review records.

## Make collection retry-safe

Network collection can fail after a successful earlier run. A failed retry
must never turn a previously collected page into an apparent 404 or empty
record.

Collection scripts should therefore:

- preserve the prior raw snapshot or write a new run-specific file;
- record HTTP status, error text, resolved URL, and attempted aliases;
- abort normalization when a broad request unexpectedly returns zero or an
  abnormally low success rate;
- normalize only the successful run selected by the operator;
- keep output sorted by stable canonical ID; and
- make reruns idempotent by matching resources on source URL and relationships
  on `(resource_id, entity_id, relationship_type)`.

Never interpret a transport failure as source absence. “Not collected,” “page
not found,” “page resolved without the requested field,” and “source reviewed
and absent” are different states and should remain distinguishable.

## Resolve titles in stages

Song titles are not reliable keys across sources. Use this order:

1. Start with the stable canonical song ID created from the bounded show
   baseline.
2. Try the source's documented slug and a small, explicit alias list for
   punctuation and contractions.
3. If a catalog search is needed, compare normalized title keys but inspect the
   returned work/artist context.
4. Promote a result only when the title, artist/composition context, and role
   relationships agree with the Dead repertoire.
5. Preserve plausible but ambiguous matches in raw data and mark them for
   review.

Exact title is necessary but not sufficient. The 1972 MusicBrainz pass returned
unrelated works for shared titles such as `Caution`, `Space`, and `Nobody's
Fault But Mine`; those candidates were retained as evidence but not promoted.

## Normalize credits conservatively

Preserve the source's role distinctions where available:

- `lyricist` → `lyrics`
- `composer` → `music`
- `writer` → `writer`

Do not collapse all roles into one generic writer value when the source gives
more detail. Conversely, do not invent a role when a source only displays a
combined credit. Traditional works, instrumental jams, and band-level credits
need explicit handling; they are not automatically people rows. A source that
reports `Traditional` or `Grateful Dead` should remain source evidence unless
the schema has an appropriate non-person entity.

Keep `original_artist`, authorship, and first/last-known performance as
separate facts. A cover's original artist is not necessarily identical to the
work's registered writer, and a song's presence in one year does not establish
its full performance history.

## Treat lyrics as linked knowledge, not copied text

For lyric-bearing sources, store:

- the external page URL;
- source name and page title;
- retrieval status and `has_lyrics` / `has_credits` metadata;
- a typed `lyrics-source` relationship to the song; and
- concise notes about scope or limitations.

Do not store full lyrics, large page captures, or reconstructed lyric text in
raw or canonical files. Short quotations belong only in a separately reviewed,
rights-aware retrieval path. The same boundary applies to complete tabs,
transcriptions, audio, and video.

## Validate every pass at three levels

1. **Source validation:** count requests, successes, errors, resolved aliases,
   exact matches, and held cases. Spot-check representative raw records.
2. **Relational validation:** check stable-ID uniqueness, foreign keys, resource
   URLs, relationship uniqueness, and expected coverage counts.
3. **Behavior validation:** run the repository tests and deterministic retrieval
   evaluation. Add a regression case whenever a collection pass changes what a
   user can retrieve.

Finish with a short handoff containing what was added, what remains unresolved,
which source decisions were made, and which facts were intentionally not
promoted.
