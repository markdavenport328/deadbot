# Heady Version fan-signal pass (2026-08-30)

## Scope and retention boundary

This is a bounded metadata-only pass for the priority songs Dark Star,
Sugaree, Friend Of The Devil, Sugar Magnolia, Morning Dew, and Bird Song.
The retained fields are source/page URL, page type, canonical song ID/title,
fan-designation state, vote count where exposed, and named performance date,
venue, and location. Comments, user prose, usernames, audio/video links, and
page captures are intentionally not retained. These records are fan evidence,
not canonical performance assertions.

## Access and source review

Heady Version song pages describe their lists as user-submitted and expose
fan-vote counts. Direct page fetches from this environment returned HTTP 403
for the tested song pages, so collection relied on search-index excerpts that
explicitly showed the page URL and the user-submitted/fan-vote labels. The
indexed excerpts are marked `collection_state: indexed_excerpt`; they are not
treated as complete rankings.

The site’s own terms/robots policy could not be retrieved through the blocked
origin during this pass. No automated crawling, form submission, or bulk
harvest was performed. Until the operator reviews the live site’s terms and
robots directives, keep this source in a review/metadata-only state and use
slow, explicitly bounded requests only.

## Results

`data/raw/fan-signals/headyversion-best-versions.jsonl` contains 16 records:
15 indexed top-ranked Dark Star recommendations and one indexed Bird Song
submission (1972-09-21). Dark Star and Bird Song are therefore the only songs
with retained recommendations in this pass.

Requested but not collected: Sugaree, Friend Of The Devil, Sugar Magnolia,
and Morning Dew. Their direct pages were not accessible and no sufficiently
attributed indexed recommendation excerpt was available in this pass. This is
an access/coverage gap, not evidence that Heady Version has no submissions.
