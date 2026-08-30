# Cross-decade song cohort candidate queue

`data/editorial/song-cohort-candidates.csv` is the first reproducible review
queue for the cross-decade enrichment pilot. It contains 72 candidates derived
only from the current `data/canonical` snapshot by
`scripts/build_song_cohort_candidates.py`.

This is not a popularity, quality, or interestingness ranking. Queue order is
only a stable presentation order after stratification. The documented strategy
calls for a 50–100-song pilot selected from recorded question utility, with
cross-era comparison potential, recording/release evidence, writing/history
evidence, and a reserved long-tail share. This first pass can measure those
dimensions from canonical data; it does not invent community recommendations
or editorial judgments that are not present in the snapshot.

## Selection and strata

Eligibility requires at least 10 years between the first and last known
canonical performance and performances in at least two calendar decades. The
queue is stratified by five-year debut era, with a secondary 10–14, 15–19, or
20+ year span band. Era quotas are 24 (1965–69), 28 (1970–74), 10 (1975–79), 8
(1980–84), and 2 (1985–89); later eras currently have no eligible songs.
Within each quota, the stable selection key favors broader span, then resource
and writer coverage, then canonical song ID. Roughly one-fifth of each quota
is reserved for the lowest-frequency eligible songs (with stable span and ID
tie-breaks) to preserve a long-tail review share. These keys are
reproducibility devices, not claims about listener value.

## Coverage fields and caveats

Performance counts and first/last years come from `performances.csv`. Recording
counts and linked-performance counts come only from accepted
`performance_recordings.csv` joins; an unlinked performance is not evidence
that no recording exists. Resource and writer counts come from
`resource_songs.csv` and `song_writers.csv`, respectively, and count distinct
canonical IDs. `coverage_risk` is a transparent data-completeness warning:
high means recording-linked ratio below 25% (or both resource and writer
counts are zero), medium means below 60% or one enrichment dimension is absent,
and low otherwise.

The broad canonical spine is itself source-bounded and may contain duplicate,
held, or incompletely linked source history. A candidate is therefore a prompt
for review and enrichment, not proof that its career history is complete.
Re-run the script after canonical changes and review the resulting snapshot
before treating counts as current.

To regenerate:

```sh
python scripts/build_song_cohort_candidates.py
```
