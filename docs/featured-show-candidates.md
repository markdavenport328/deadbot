# Featured-show enhancement queue

[`data/editorial/featured-show-candidates.json`](../data/editorial/featured-show-candidates.json)
is the first bounded show queue for enhancement work. It contains 20
cross-era anchors from 1969 through 1991, selected to exercise retrieval and
source-review work across the available timeline.

This file is a work plan, not a ranked list of performances and not a source
for historical claims. Its editorial rationale says only why a row is useful
to review. Every coverage field is generated from canonical CSV data by
[`scripts/build_featured_show_candidates.py`](../scripts/build_featured_show_candidates.py).
The file stays out of model prompts and runtime response packets.

For each candidate, review these relationship types in order:

1. Source provenance and raw-record availability.
2. Setlist and performer coverage, preserving a missing or held state rather
   than inventing a credit.
3. Recording-to-performance track mappings.
4. Official release-to-performance mappings.
5. Direct show or performance context, kept separate from song-level context.

The existing [`priority-review-queue.json`](../data/editorial/priority-review-queue.json)
is the complementary song queue. Together the two artifacts select the next
research units without asserting that either a show or song is universally
important.
