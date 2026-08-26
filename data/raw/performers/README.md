# Raw performer records

`jerrybase-<year>.jsonl` contains compact, source-specific performer records
for canonical Grateful Dead shows. Each record preserves the JerryBase event
identifier, source URL, retrieval time, exact musician/guest display names,
and source instrument strings. The records are evidence, not an assertion that
every source-listed musician is a standing band member.

Collect one year with:

```bash
.venv/bin/python scripts/collect/fetch_jerrybase_performers.py 1972
```

The collector also supports `--all` for the canonical 1965–1995 year range.
Normalization promotes only identified, non-question-marked assignments into
`people.csv` and `show_performers.csv`; uncertain or unidentified names remain
in the raw snapshot for review. Batch collection can also write a matching
`.coverage.json` file when JerryBase omits or ambiguously dates a canonical
show; those held shows are not silently treated as covered.
