# Canonical spine baseline

[`data/coverage/canonical-spine-baseline.json`](../data/coverage/canonical-spine-baseline.json)
is the generated, machine-readable baseline for the show, song, performance,
and person spine. Rebuild it with:

```bash
.venv/bin/python -S scripts/build_baseline_coverage.py
```

The baseline distinguishes two conditions that must not be conflated:

- Referential integrity: every performance and show-performer assignment
  resolves to the canonical entities it names.
- Relationship coverage: a known show can still have no reviewed setlist or
  performer assignment. Those IDs remain visible as gaps, not as empty facts.

People without a show assignment are likewise not automatically missing
performer data: the shared people table also records songwriters and other
relationship subjects. A person becomes a show performer only through a
source-supported `show_performers` relationship.

Use the baseline before each collection pass, then regenerate it after the
canonical review is complete. The featured show and song queues direct
enrichment; this baseline prevents their richer examples from obscuring the
unresolved breadth of the timeline.
