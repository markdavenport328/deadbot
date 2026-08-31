# Dead.net official release pass (2026-08-30)

## Scope

Bounded review of first-party `dead.net` and `store.dead.net` pages for the 20 featured shows and their 32 priority-song review context. The snapshot retains release metadata, source links, show-date candidates, and song-ID mapping candidates only. It does not retain article prose, liner notes, lyrics, audio, images, or copied page bodies.

## Access and rights findings

- `data/source_registry.json` currently approves `deadnet-editorial` for HTTPS GET metadata/search/read on `dead.net` with `rights_state=restricted`, `retention_policy.mode=metadata_only`, and `store_content=false`.
- The reviewed official store pages are on `store.dead.net`, which is not currently in that registry host allowlist. Treat these records as research candidates requiring registry/adapter review before promotion or runtime retrieval.
- Official store pages expose product title, show/date identity, availability, and track-list headings. Archive pages expose Dick’s Picks title, show/date, venue, and tags. These are metadata facts; no page text was copied into the snapshot.
- Search/category absence is recorded as `not_found_in_bounded_pass`, never as proof that no official release exists.

## Confirmed candidates

1. Dick’s Picks Volume 3 — Sportatorium, Pembroke Pines, FL, 5/22/77; official Dead.net archive page.
2. Duke ’78 — Cameron Indoor Stadium, Durham, NC, 4/12/78; official Dead.net store product page.
3. Madison Square Garden, New York, NY 3/9/81 [3CD]; official Dead.net store product page.
4. Cornell 5/8/77 Digital Album ALAC; exact product surfaced in the official digital collection, but detail URL was not exposed in this pass.

Dick’s Picks Volume 36 / Spectrum 9/21/72 remains a likely series candidate, but this pass only captured the official Dick’s Picks archive category and did not obtain a date-level page. It must remain unresolved.

## Blockers / next pass

- Add `store.dead.net` as a separately reviewed official host (or explicitly route through an approved store adapter) before importing these candidates into canonical release tables.
- Obtain stable detail URLs and structured track listings for Cornell 5/8/77 and Dick’s Picks 36 through official pages.
- Expand the pass with one-request-per-second pacing and a reproducible official collection endpoint if permitted; do not infer no-release from shop search misses.

Raw snapshot: `data/raw/releases/deadnet-featured-release-pass-2026-08-30.jsonl`.
