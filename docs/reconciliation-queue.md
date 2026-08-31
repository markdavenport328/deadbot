# Reconciliation queue

[`data/coverage/reconciliation-queue.json`](../data/coverage/reconciliation-queue.json)
turns the unresolved relationships in the canonical-spine baseline into a
source-scoped collection queue. Rebuild it with:

```bash
.venv/bin/python -S scripts/build_reconciliation_queue.py
```

The queue contains separate entries for two conditions:

- A known show whose current gdshowsdb record has no setlist entries. These
  remain `source_empty` until an approved secondary source establishes a
  setlist.
- A known show without a JerryBase performer assignment. Its recorded hold
  reason distinguishes ambiguous candidates, an unavailable source-index
  date, and a source page that lacks musician fields.

Each entry carries the canonical show and source identifiers, the raw record
or coverage-report path, and a narrow next action. It is a collection ledger,
not a runtime source or an invitation to infer facts from nearby dates.
