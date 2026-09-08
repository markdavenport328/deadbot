# Lore collection: index the research blogs as stored resources

## Context

Deadbot's stored lore is thin: of 300 resources, 267 are catalog rows
(MusicBrainz work entries, Dead.net lyric pages); six shows of 2,358 have any
resource; source trails cover six entities. The pathways feature (see
`2026-09-08-lore-pathways.md`) will say "nothing cataloged" for most
questions until the inventory grows. The five Blogger research sites in
`data/research_sites.json` (Lost Live Dead, Hooterollin' Around, Grateful Dead
Guide (Deadessays), Dead Sources, Grateful Seconds) publish public Atom feeds
listing every post with title, URL, dates and labels. Indexing those feeds as
metadata-only resource records, mapped to canonical songs and shows, is the
fastest honest way to give hundreds of entities a pathway.

Spec authority: `docs/collection-methodology.md` (raw → normalizer →
canonical CSV → status doc; hold, never guess; rerunnable and idempotent),
`docs/provenance-policy.md`, `docs/data-sources.md`, `docs/model-retrieval.md`
(store link, author, date, source, relationship, scope note; never a copied
transcript).

## Global constraints

- Metadata only. A raw record keeps: post title, URL, published and updated
  timestamps, labels, author name if the feed gives one, retrieval time,
  request URL and HTTP status. Never store post content, summaries or
  excerpts.
- Respect each host. Fetch `https://{host}/robots.txt` first and record what
  it says in the status doc; if it disallows the feed path, skip that host and
  say so. One request at a time, at least two seconds apart, a plain
  `User-Agent: Deadbot/0.1 (metadata index; contact via repository)`. Blogger
  feeds paginate with `?alt=json&max-results=150&start-index=N`; stop when a
  page returns fewer than 150 entries. Expect on the order of 5 to 10 pages
  per host.
- Raw records are retry-safe: rerunning the collector rewrites the raw file
  from a complete successful pass and never turns a previously collected
  entry into an apparent absence because of a transient failure (abort the
  host's file on any non-200 page).
- Mapping is conservative and explained. Auto-map only when one of these
  holds; otherwise write the post to the held queue with a reason:
  - Show: the title (or a label) contains one unambiguous date — ISO
    `YYYY-MM-DD`, `M/D/YY`, `M/D/YYYY`, or `Month D, YYYY` — that matches
    exactly one row in `data/canonical/shows.csv`. Two shows on that date, or
    two different dates in the title, is a hold.
  - Song: the title contains a canonical song title from
    `data/canonical/songs.csv` as a whole phrase (word boundaries, case
    insensitive, straight/curly apostrophes equivalent) where the song title
    is at least two words or at least six letters; single short titles
    (`Deal`, `Ripple`, `Truckin'`, `Bertha`, `Cassidy`) map only when the
    label set also names the song or the host is Deadessays and the title
    starts with the song title. Any title matching more than three songs is a
    hold.
  - Neither: the post is still stored as a resource (a blog post about the
    band is a resource) with no relationship rows, and counted as
    "unmapped" in the status doc; it never enters the held queue.
- Canonical output follows the existing schemas exactly:
  `data/canonical/resources.csv` columns
  `resource_id,resource_type,title,creator,source_name,source_url,published_date,notes`
  and `resource_songs.csv` / `resource_shows.csv` columns
  `resource_id,{song_id|show_id},relationship_type,notes`. Resource ids are
  stable: `resource-{host-slug}-{post-slug}` from the URL. `relationship_type`
  is `about`. `notes` states the match basis ("Title names the show date"
  / "Title names the song"). `resource_type` by host: Deadessays and
  Hooterollin' → `editorial-blog-post`; Lost Live Dead → `show-history-post`;
  Dead Sources → `press-transcription`; Grateful Seconds → `statistics-post`.
  `creator` is the blog's byline when the feed carries an author, else blank.
  `source_name` is the site name from `data/research_sites.json`.
- Idempotent: rerunning the normalizer produces byte-identical CSV output
  for unchanged raw input, preserves every existing row that did not come
  from this pass, and sorts its own rows deterministically. Existing
  `resources.csv` rows are never modified.
- Tests use fixture feed entries, never the network. Full suite must stay
  green except the known database-bound eval test. Commit trailer:
  `Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>`. Never push;
  never bare `git stash`.
- Production PostgreSQL is loaded by the owner's import step
  (`deadbot/postgres_import.py`); this pass changes CSVs and docs only. Say so
  in the status doc.

## Task 1 — Collector

`scripts/collect/collect_blog_post_index.py` (look at the existing
`scripts/collect/` and `scripts/normalize/` directories and follow their
conventions for arguments, logging and output paths). Arguments: one or more
site names or hosts (default: all five Blogger sites), `--out data/raw/resources/`.
Output: one JSONL file per host, `blog-post-index-{host-slug}.jsonl`, one
line per post plus a first line with the pass metadata (host, retrieved_at,
robots findings, page count, entry count). Unit tests for pagination logic
and record shaping with a fake transport (see `PageTransport` in
`deadbot/source_reader.py` and how `tests/test_site_search.py` fakes it).
Then run it once for real against the five hosts and commit the raw files.

## Task 2 — Normalizer

`scripts/normalize/normalize_blog_post_resources.py`: reads every
`blog-post-index-*.jsonl`, applies the mapping rules, appends new rows to the
three canonical CSVs, writes the held queue to
`data/editorial/blog-post-mapping-held.jsonl` (one line per held post with
`resource_id`, `url`, `title`, `reason`, `candidates`), and prints counts.
Tests (`tests/test_normalize_blog_post_resources.py`) cover: each date format;
a date shared by two shows → hold; a two-word song title maps; a short song
title without label support → unmapped, with label support → maps; more than
three song matches → hold; idempotent rerun; existing rows untouched. Run it
for real, spot-check twenty random mappings by reading only the post titles
(never the pages), fix rules if a check fails, rerun, commit.

## Task 3 — Status doc and registry

`docs/collection-status-lore-blog-index.md`: per host, robots findings, pages
fetched, entries, resources written, songs and shows mapped (distinct
counts), unmapped, held, and the twenty spot checks with outcome. Update
`docs/data-sources.md` with the five sources and their retention boundary,
and add the five hosts to the source registry
(`data/source_registry.json`, following the existing entry shape and
`docs/source-registry.md`) as reviewed metadata-only sources with
`allowed_operations` `["search", "read"]`. Run the full test suite. Commit.
Report: the per-host counts and the before/after totals of songs and shows
with at least one non-catalog resource (before: 174 songs counting catalog
rows, 6 shows).
