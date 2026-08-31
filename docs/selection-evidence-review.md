# Selection-evidence review

[`data/editorial/selection-evidence-review.json`](../data/editorial/selection-evidence-review.json)
is a generated staging review for the initial official-release, critic, and
fan-signal passes. Rebuild it with:

```bash
.venv/bin/python -S scripts/build_selection_evidence_review.py
```

It resolves only evidence whose source date and target are unambiguous in the
canonical graph. Same-day double shows and repeated performances are held,
even when a plausible match exists. The file remains outside runtime packets
and does not claim that a source signal identifies an objectively best show or
version.

Promotion requires a reviewed source-registry entry, a typed `resource`, and
a selection-list import path. Keep critic, fan, and official-release evidence
as separate selection types rather than normalizing them into one score.
