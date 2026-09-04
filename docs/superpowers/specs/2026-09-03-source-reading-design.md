# Source reading and site search — design

Date: 2026-09-03. Owner decisions recorded here; see `AGENTS.md` for the
working principles this follows.

## Why

The model can point at an essay but cannot read it. Every outside-facing tool
returns a title, a URL and a one-line description, so the model's judgment
about reputation, musical character and history has nothing to work from
except our own structured library. The owner's direction: the model should be
able to search the sites a well-read Deadhead reads, open the pages that
matter, and use what they say. Basic retrieval-augmented answering, at
request time, with nothing stored.

## Decisions (owner, 2026-09-03)

1. **Request-time reading is allowed.** The model fetches a public page and
   reads its text the way a person opens a tab. No page text is stored; an
   in-process cache with a short lifetime avoids fetching the same page twice
   in one conversation.
2. **No search API key.** Search goes through each site's own mechanism
   (Blogger post feeds, Omeka's item API, archive.org's advanced search, a
   sitemap when a site has no search).
3. **Suggested, not restricted.** The site directory is a list of places
   worth looking, with what each is good for and how to search it. The reader
   accepts any public URL. There is no host allowlist.
4. **No quoting rules in the prompt.** The model writes from what it reads,
   as any retrieval-augmented assistant does. Links it offers still have to
   come from a tool result this turn, which is how the page already works.

## What is built

Three tools, two modules, one data file, a prompt update.

### `deadbot/source_reader.py`

`PageReader(transport).read(url, focus=None, offset=0, max_chars=12000)`.
Fetches one page (HTTP or HTTPS, 12 s timeout, 2.5 MB cap, Deadbot
User-Agent) and returns title, byline, date, description and the readable
body text. Boilerplate (navigation, footers, comment threads, share widgets,
sidebars) is dropped; the main body is found by text density with a
preference for `article`, `main` and common content containers. JSON and
plain-text responses come back as text. Long pages page by `offset`; a
`focus` phrase returns the passages around that phrase first so a
ten-thousand-word blog post costs a few thousand characters. Private-network
addresses are refused. The transport is injectable so tests use fixtures.

### `deadbot/site_search.py`

`SiteSearcher(transport).search(site, query, limit=8)`. `site` is a directory
name, a site id, or any host. Methods: `blogger_feed`, `omeka_api`,
`archive_search`, `wordpress_api`, `sitemap`, `none`. An unknown host is
probed in that order. Each hit carries title, URL, snippet and date, so the
model can pick what to read.

### `data/research_sites.json`

The suggested sites with `good_for`, `search.method`, and `read_hints`
(URL patterns for sites without search, such as Dead.net song and feature
pages). Loaded by `get_research_source_directory` and by the searcher.

### Tools (`deadbot/tools.py`)

- `search_site(site, query)`
- `read_page(url, focus="", offset=0)`
- `get_recording_reviews(recording, limit=8)` — archive.org listener reviews
  and star ratings for a canonical recording, an archive identifier, or a
  show; the richest source of "what do listeners say about this tape".
- `get_research_source_directory` now returns the suggested sites and how to
  search each, alongside the existing stored-link catalogs.

Stored titles, notes and lore trails remain the clue about which pages to
open; `read_page` accepts their URLs directly.

### Prompt

The "Reading and lore" paragraph of `SYSTEM_PROMPT` describes the loop:
use stored links and the site directory as clues, search a site, read the
pages that matter, and write from them.

## Not built now

- A quote card block in the page. Narrative paragraphs already carry links;
  revisit once the model's use of page text is visible in real answers.
- robots.txt handling, per-host rate limiting, a persistent cache.
- A generic web search engine. None is free and reliable without a key;
  the owner declined a key.

## Testing

Fixture HTML in tests (Blogger post, Drupal article with comments, a page
with nothing but navigation) drives the extractor. Fake transports drive each
search adapter and the reviews tool. Nothing in CI touches the network. A
live smoke script under the scratchpad exercised each adapter once during
development; its findings are in the site directory notes.
