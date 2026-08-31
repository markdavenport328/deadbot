# Selection-evidence review

[`data/editorial/selection-evidence-review.json`](../data/editorial/selection-evidence-review.json)
is the generated reviewed inventory for the initial official-release, critic,
fan, and individual-curator signal passes. Rebuild it with:

```bash
.venv/bin/python -S scripts/build_selection_evidence_review.py
```

It records every reviewed signal with its canonical resolution and access state.
Same-day double shows and repeated performances remain held, even when a
plausible match exists. Runtime tools expose those states and source constraints
without turning them into recommendations. The fully resolved Rolling Stone
show selection can also be presented as a source-attributed discovery list.
No source signal identifies an objectively best show or version.

Keep critic, fan, individual-curator, and official-release evidence as separate
selection types rather than normalizing them into one score. Adding a new
external retrieval adapter still requires a reviewed source-registry entry and
the appropriate rights/access review.
