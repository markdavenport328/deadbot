# Provenance policy

## Recommended initial approach

Choose a **primary source by fact type**, rather than one global canonical source. This is a practical first-stage policy: it makes normalization consistent while recognizing that different sources are likely strongest in different parts of the domain.

Before any collection, fill in the following decisions using the candidate-source review:

| Fact type | Primary source | Fallback source | Override rule |
| --- | --- | --- | --- |
| Show date, venue, and set order | gdshowsdb — 1972 bulk baseline | JerryBase; Internet Archive item metadata where available | Keep raw values; review a conflict before changing the canonical value. |
| Song title and composition credits | TBD | TBD | TBD |
| Performer and guest assignments | JerryBase — 1972 pilot | TBD | Keep raw values; review a conflict before changing the canonical value. |
| Recording source identifiers and lineage | Internet Archive item metadata — 1972 pilot | Relisten, after access/usage review | Keep raw values; review a conflict before changing the canonical value. |
| Official-release metadata and tracklists | TBD | DeadDisc — research/reference candidate | TBD |
| Educational and reference resources | TBD | TBD | TBD |

## Evidence handling

- Keep all collected source records in raw JSONL, including the source name, source identifier, retrieval time where practical, URL, and original payload.
- Normalize canonical data from the selected source for the relevant fact type; do not silently overwrite raw values.
- Record any manual correction with its reason and supporting source material.
- Treat a canonical value as an editable conclusion, not an erased copy of the source record.

The initial canonical CSV schema remains intentionally small. Once real sources begin to disagree, add an assertion/provenance relationship that can attach source evidence, confidence, and editorial notes to individual canonical claims. That keeps the primary-source policy simple now without losing the ability to reconcile evidence later.
