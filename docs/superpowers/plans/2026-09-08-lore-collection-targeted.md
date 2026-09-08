# Lore collection, targeted pass: Dead.net song essays, Deadhead High guides, GDAO show accounts

## Context

After the blog-index pass, 14 songs on the owner's priority review queue and
11 of the 20 featured shows still have no non-catalog lore resource. They are
listed in `data/editorial/lore-targets-2026-09-08.json` (song ids with titles
and slugs; show ids with dates and venues). This pass fills those gaps from
three reviewed sources whose pages are per-song or per-show, and catalogs
whatever else those sources cover along the way when it is cheap to do so.

- **Dead.net** (`www.dead.net`): David Dodd's "Greatest Stories Ever Told"
  essays, one per song, at URLs of the form
  `https://www.dead.net/features/greatest-stories-ever-told/greatest-stories-ever-told-<slug>`,
  plus song pages under `/song/<slug>`. The source registry
  (`data/source_registry.json`, `deadnet-editorial`) allows search and read.
  `deadbot/deadnet.py` is the reviewed metadata adapter (title and
  description only).
- **Deadhead High** (`deadheadhigh.com`): listener guides with per-song pages
  `https://deadheadhigh.com/songs/<slug>` and era or show guides; the site has
  no search, `deadbot/site_search.py` matches its sitemap by URL slug.
- **Grateful Dead Archive Online** (`www.gdao.org`): UC Santa Cruz's Omeka
  archive of posters, tickets, photographs and first-person accounts, searchable
  by date through the Omeka API already used by `site_search.py` (`_omeka`).

Spec authority: `docs/collection-methodology.md`, `docs/provenance-policy.md`,
`docs/source-registry.md`, and the Global constraints of
`2026-09-08-lore-collection-blog-index.md`, which apply here unchanged
(metadata only; robots first; one request at a time, two seconds apart; the
Deadbot User-Agent; raw records retry-safe; canonical rows append-only with
stable ids; idempotent normalizers; hold, never guess; tests use fixtures,
never the network).

## Global constraints specific to this pass

- Resource ids: `resource-deadnet-gset-<slug>` (Greatest Stories),
  `resource-deadnet-song-<slug>` (song page, only when no `lyrics-and-credits`
  row already carries that URL), `resource-deadheadhigh-<path-slug>`,
  `resource-gdao-item-<omeka-id>`.
- Resource types: Greatest Stories → `song-history-essay`; Deadhead High song
  page → `listening-guide`; Deadhead High other page → `listener-guide`;
  GDAO item → `archive-artifact` for posters, tickets, photographs and
  `first-person-account` for recollections, letters and interviews (use the
  Omeka item type or collection name to decide; unknown → `archive-artifact`).
- `source_name`: `Grateful Dead / Dead.net`, `Deadhead High`,
  `Grateful Dead Archive Online / UC Santa Cruz Library` (matching existing
  rows in `resources.csv`). `creator`: the byline when the page metadata gives
  one (David Dodd for Greatest Stories), else blank. `published_date` when the
  metadata gives one, else blank.
- Mapping: a Dead.net essay or song page maps to the song whose canonical slug
  (or title, normalized the same way as the blog pass) matches the URL slug;
  unmatched slugs go to the held queue with candidates. A Deadhead High song
  page maps the same way. A GDAO item maps to a show when its date field is a
  full date matching exactly one canonical show; a date with two shows or a
  partial date is a hold; an item with no date is stored unmapped only if its
  title names a venue or the band, otherwise skipped. Relationship type
  `about`; notes state the basis.
- Coverage of the target list comes first: every one of the 14 songs and 11
  shows is attempted at each applicable source and the status doc reports the
  outcome per target (found / not found at source / held). Broader coverage
  (every Greatest Stories essay; every Deadhead High song page; GDAO items for
  the other featured shows) is welcome when it costs only more requests at
  the same pace; report the counts.
- Do not touch the canonical CSVs directly in this pass. Each normalizer takes
  `--canonical-dir` (default `data/canonical`) and `--out-dir`; run it for
  real only with `--out-dir` pointing to a scratch directory, and put the
  resulting row counts in the report. The controller runs the normalizers
  against `data/canonical` sequentially after review, so two agents never
  write the same CSV at once.
- Held queue: `data/editorial/lore-mapping-held-<source>.jsonl`.
- Status doc: `docs/collection-status-lore-<source>.md` per source, plus one
  section listing each target song or show and its outcome.
- Commit nothing; leave work in the tree. Full test suite green except the
  known database-bound eval test.

## Task A — Dead.net Greatest Stories and Deadhead High (song-oriented)

1. Collector `scripts/collect/collect_deadnet_song_essays.py`: robots first;
   discover essay URLs through the Dead.net sitemap (try
   `https://www.dead.net/sitemap.xml`, following sitemap indexes, matching
   `greatest-stories-ever-told`); when the sitemap is unavailable, construct
   candidate URLs from the target songs' slugs and confirm each with one
   metadata request through `deadbot.deadnet.DeadnetResearchAdapter` or an
   equivalent HEAD/GET that keeps only title and description. Raw JSONL
   `data/raw/resources/deadnet-greatest-stories.jsonl` (url, title,
   description first 200 characters, byline if present, http status,
   retrieved_at). Tests with a fake transport.
2. Collector `scripts/collect/collect_deadheadhigh_index.py`: robots first;
   walk the sitemap (reuse `SiteSearcher._sitemap_locations` or its logic),
   keep every URL under `/songs/` and any URL whose slug matches a target song
   or a featured-show date; one metadata request per kept URL for the title.
   Raw JSONL `data/raw/resources/deadheadhigh-index.jsonl`. Tests with a fake
   transport.
3. Normalizer `scripts/normalize/normalize_song_guide_resources.py` covering
   both raw files under the mapping rules above, with tests for slug matching
   (apostrophes, "the", trailing punctuation), a slug matching two songs →
   hold, idempotent rerun, and existing rows untouched.
4. Status docs and the per-target outcome table. Register `deadheadhigh.com`
   in `data/source_registry.json` as a reviewed metadata-only source if it is
   not there; Dead.net is already registered.

## Task B — GDAO show accounts (show-oriented)

1. Collector `scripts/collect/collect_gdao_show_items.py`: robots and the
   Omeka API terms first (record what `https://www.gdao.org/robots.txt` and
   the API's own description say). For each target show date, then for the
   other featured shows, query the Omeka items endpoint by date (see
   `SiteSearcher._omeka` for the request shape) and keep item id, title, item
   type, collection, date field, and the item URL
   `https://www.gdao.org/items/show/<id>`; never the description body beyond
   200 characters and never files. Raw JSONL
   `data/raw/resources/gdao-show-items.jsonl`. Tests with a fake transport.
2. Normalizer `scripts/normalize/normalize_gdao_show_resources.py` under the
   mapping rules above, with tests for full-date match, two-shows date → hold,
   partial date → hold, undated item skipped or unmapped by the title rule,
   idempotent rerun.
3. Status doc with the per-target outcome table. GDAO is already in the
   research-site directory; add it to `data/source_registry.json` as a
   reviewed metadata-only source if absent.
