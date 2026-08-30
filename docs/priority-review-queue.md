# First priority review queue

[`data/editorial/priority-review-queue.json`](../data/editorial/priority-review-queue.json)
is a current, bounded first pass over the factual review queue. It contains 32
review priorities: 29 selected from the coverage cohort plus three explicit
editorial-guide entries. It is an internal review artifact and is excluded from
runtime model instructions and answer packets.

The queue makes its selection logic visible. A priority can be included for:

- `data_coverage`: high-value cross-decade performance and recording facts;
- `discovery_lead`: a matching invitation in the editorial discovery guide;
- `lore_source_trail`: a reviewed trail that can bring a factual answer to life;
- `transition_suite`: usefulness for segue and set-architecture questions; or
- `long_tail`: a deliberate test of thin, unusual, or under-documented coverage.

These reasons can overlap. Lore or transition potential can bring forward a
song with thin factual coverage; its `coverage_risk` travels with the row and
guides research effort and answer scope. The remaining cohort candidates stay
available for later review as question logs, source research, and canonical
coverage improve.

## Editorial overrides

The three `editorial_override` rows—Dark Star, Dancin' In The Streets, and They
Love Each Other—come from the discovery guide's unusually fruitful evolution,
improvisation, or transition questions. Their factual fields are computed
directly from the current canonical performances and accepted recording links,
using the same definitions as the cohort CSV. `queue_position` is `null` for
these editorial paths. They direct research attention toward especially fertile
questions.

Overrides carry a discovery-guide lead ID. A reviewed lore-trail ID is also
carried when one exists. Dark Star currently has no registered trail, which
keeps the next research step visible.

For cohort rows, the queue copies the factual coverage fields from
`song-cohort-candidates.csv`; for overrides, the loader recomputes those fields
from the canonical performance, recording-link, resource, and writer tables.
Both paths preserve discovery lead IDs and lore trail IDs. The loader validates
that values still match their source files and that no unregistered provenance
is introduced.
