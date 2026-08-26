# Provenance policy

## Recommended initial approach

Choose a **primary source by fact type**, rather than one global canonical source. This is a practical first-stage policy: it makes normalization consistent while recognizing that different sources are likely strongest in different parts of the domain.

Before any collection, fill in the following decisions using the candidate-source review:

| Fact type | Primary source | Fallback source | Override rule |
| --- | --- | --- | --- |
| Show date, venue, and set order | gdshowsdb — 1972 bulk baseline | JerryBase; Internet Archive item metadata where available | Keep raw values; review a conflict before changing the canonical value. |
| Song title and composition credits | gdshowsdb for the bounded title universe; MusicBrainz and reviewed Dead.net pages for role-level enrichment | Source-specific review or a second catalog | Promote only when title and composition context agree; retain ambiguous title matches as raw evidence |
| Performer and guest assignments | JerryBase — 1965–1995 event snapshots | TBD | Keep raw values; review a conflict before changing the canonical value. |
| Named Jerry Garcia guitar claims | Jerry Garcia instrument history — dated range/specific-show evidence | A second photo/video-supported equipment source | Keep the evidence scope visible; do not treat a date range as an exclusive equipment log. |
| Recording source identifiers and lineage | Internet Archive item metadata — 1972 pilot | Relisten, after access/usage review | Keep raw values; review a conflict before changing the canonical value. |
| Official-release metadata and tracklists | TBD | DeadDisc — research/reference candidate | TBD |
| Educational and reference resources | The original publisher or host for the linked resource | A second attributed source | Store the link and typed relationship; do not turn editorial/contextual material into a canonical fact automatically. |

## Evidence handling

- Keep all collected source records in raw JSONL, including the source name, source identifier, retrieval time where practical, URL, and original payload.
- Normalize canonical data from the selected source for the relevant fact type; do not silently overwrite raw values.
- Record any manual correction with its reason and supporting source material.
- Treat a canonical value as an editable conclusion, not an erased copy of the source record.
- Distinguish transport failure, unresolved page, resolved page without a field,
  and reviewed absence. Never normalize a failed request as a missing fact.
- Run bounded, typed enrichment passes rather than broad undifferentiated
  scraping. A source may be strong for recording metadata and weak for song
  credits, or strong for editorial context and weak for setlist authority.
- For title-based catalog lookups, exact title is only a candidate key. Require
  artist/work context before promotion and retain held matches with an explicit
  reason.
- For lyrics, tabs, transcriptions, audio, and video, canonical knowledge is
  the source link plus concise availability/scope metadata—not a copied work.

The operational checklist and retry-safe collection rules are maintained in
`docs/collection-methodology.md`.

The initial canonical CSV schema remains intentionally small. Once real sources begin to disagree, add an assertion/provenance relationship that can attach source evidence, confidence, and editorial notes to individual canonical claims. That keeps the primary-source policy simple now without losing the ability to reconcile evidence later.
