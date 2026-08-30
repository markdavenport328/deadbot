# Data and retrieval roadmap

This document records the order in which Deadbot should collect data, derive
insights, move query traffic to PostgreSQL, and expand from the 1972 proving
ground to the full Grateful Dead timeline. It complements the practical source
workflow in `collection-methodology.md` and the durable decisions in
`decisions.md`.

## The central rule

Do not wait for every possible base-data collection pass before building any
insights. Do require every published insight to name the data slice it depends
on and the coverage actually available within that slice.

This gives Deadbot two compatible kinds of progress:

- a **broad spine** of stable shows, venues, songs, set positions,
  performances, and people across the timeline; and
- **deep, bounded slices** with recordings, release mappings, selections,
  claims, lore, equipment, and other context needed to make one year, show, or
  question family genuinely rewarding.

The whole graph does not need to be complete before a 1972 observation is
useful. The observation does need complete enough 1972 inputs, a stated
coverage boundary, source provenance, and a reproducible calculation.

## Optimal data-laying order

Use the following dependency order for each bounded collection or question
family. Later stages may begin for one slice while earlier collection continues
elsewhere.

1. **Define the questions and coverage boundary.** Write the questions the
   product should answer, the entities and relationships they require, the
   expected universe, and what would count as partial coverage.
2. **Preserve source evidence.** Collect source-shaped raw records with source
   identifiers, retrieval time, rights/usage notes, and an explicit success,
   missing, held, or error state. An empty response caused by transport failure
   is not evidence that a fact does not exist.
3. **Build and reconcile the canonical spine.** Normalize stable IDs and the
   core song → performance → show → venue relationships. Record provenance,
   unresolved conflicts, and coverage counts alongside the result.
4. **Add typed enrichment.** In dependency order, add recording lineage and
   performance mappings, official-release/show/track mappings, curator or fan
   selection lists, contextual resources, attributed claims, and equipment or
   personnel details. Preserve these as separate relationship types rather than
   flattening them into general show prose.
5. **Project the reviewed snapshot into PostgreSQL.** Import canonical CSV
   deterministically. PostgreSQL is the operational query surface, not an
   independently edited second source of truth.
6. **Compute structured observations.** Calculate patterns such as rarity,
   recurrence, set-position tendencies, adjacency, release representation, or
   selection-list overlap. Store the calculation version, canonical input
   revision, coverage boundary, supporting entity/resource IDs, and structured
   result—not a polished narrative.
7. **Retrieve a bounded evidence packet.** Resolve the question, traverse only
   relevant relationships, rank or aggregate outside the model, and return
   compact facts, graph paths, provenance, coverage, and gaps.
8. **Compose the explanation at request time.** Let the model decide what is
   relevant and how approved blocks should be ordered, while deterministic
   validation prevents invented facts, links, and unsupported completeness.
9. **Evaluate, correct, and recompute.** A canonical correction creates a new
   input revision. Recompute affected observations and compare representative
   answers before promoting the new snapshot.

The important sequencing rule is local, not global: base facts precede their
dependent observation, but observations for a ready slice do not wait for the
entire band's history to reach the same depth.

## PostgreSQL transition

The switch should start now. The full-timeline show/performance spine and the
next enrichment relationships are large and connected enough that SQL joins,
indexes, integrity constraints, aggregation, and pagination are preferable to
loading and scanning all CSV rows for each process.

The current foundation provides a PostgreSQL schema, a deterministic canonical
import path, and a read-store implementation behind the same application
interface as CSV. CSV remains the reviewable source of truth and zero-setup
fallback. Driver-independent importer and parity tests exercise the bridge. A
local Docker PostgreSQL 16 smoke check completed a clean schema-v2 bootstrap
of all 107,404 canonical rows, recorded a named snapshot, and read the Veneta
show through the PostgreSQL store. That establishes the basic live path, but
not deployment verification: reconnect, populated-database rebuild,
deliberately-invalid rollback, parity measurements, and production-like query
measurements remain required.

Use these cutover gates:

1. A clean database can be rebuilt from one named canonical snapshot in a
   transaction.
2. Row counts, foreign keys, representative query results, empty/null behavior,
   and provenance fields match the CSV store.
3. The retrieval and experience evaluation suites pass against both stores.
4. A live database test covers import, restart, reconnect, and rollback on a
   deliberately invalid input.
5. Representative full-timeline queries meet an agreed latency target and have
   inspected query plans and indexes.
6. Operations have a documented rebuild, migration, backup, and rollback path.

After these gates pass, make PostgreSQL the normal deployed read store while
retaining CSV for review, regeneration, tests, and recovery. Do not dual-write
canonical facts. Rebuild or migrate the operational projection from a named
canonical revision.

A dedicated graph database is not currently justified. PostgreSQL can handle
the expected one-to-three-hop traversals and aggregates. Reconsider only after
measured production questions demonstrate a repeatable limitation that SQL,
indexes, materialized views, or precomputed observations cannot solve cleanly.

## Full-timeline retrieval without full-timeline context

The model should never receive the entire timeline. The knowledge graph makes
context smaller by letting retrieval select a connected subgraph around the
question.

The request path should be:

```text
question
  → resolve typed seed entities and requested scope
  → choose one or more bounded traversal/query plans
  → query, filter, aggregate, rank, and paginate in PostgreSQL
  → assemble a compact evidence packet
  → let the model explain and compose from that packet
  → validate every returned reference against the packet
```

Useful traversal plans include:

- **Show:** show → ordered performances → performers, recordings, releases,
  resources, claims, and neighboring performances.
- **Song:** song → performances constrained by date/era/venue → ranked or
  representative shows → recordings, releases, arrangements, and resources.
- **Release:** release → tracks/segments → performances → source shows and
  alternate recordings.
- **Curator or fan choice:** selection list → entries → shows/performances →
  shared songs, eras, venues, releases, and evidence for the list.
- **Lore or claim:** subject entity → attributed claims → supporting resources,
  with canonical facts returned separately.
- **Pattern:** question scope → SQL aggregate or versioned observation → a small
  set of representative supporting and counterexample entities.

Every plan needs an explicit scope and budget: maximum hops, rows per edge,
ranked examples, source excerpts, and total serialized context. Prefer query-side
counts and distributions over hundreds of raw rows; include stable IDs so the
experience can expand a summary into another bounded request. Long lists should
be paginated or linked to an archive page rather than silently truncated.

Initial context targets are a 10,000-token p95 retrieval packet and a 20,000-token
hard ceiling, measured rather than assumed. The packet should prioritize:

1. the direct facts or structured observation needed to answer;
2. the graph path that explains how the entities connect;
3. provenance, calculation/input versions, and coverage limits;
4. a few representative examples and useful alternatives; and
5. an expansion cursor or link when more evidence exists.

These are packet budgets, not answer-length targets. The visible response should
remain much smaller and should not repeat the conversational answer in multiple
layout regions.

## Staged rollout: 1972 to the full timeline

### Stage 1 — Stabilize the broad spine

Keep show, venue, song, performance, and performer IDs stable across 1965–1995.
Finish held-date review, record coverage by year and fact type, and treat missing
early-year setlists distinctly from confirmed empty data. This creates reliable
cross-era navigation even while richer coverage remains uneven.

### Stage 2 — Make all of 1972 the first deep slice

Complete the relationships that turn 1972 from a setlist lookup into an
exploration experience:

- recording-to-performance track and timing mappings;
- official release → show → track/segment → performance coverage;
- Dick's Picks and other documented critic, curator, and fan selections;
- show- and performance-specific resources, reviews, interviews, and lore;
- attributed claims separated from canonical facts;
- personnel, guest, instrument, and equipment evidence where sources support it;
  and
- explicit completeness measures for every enrichment type.

Use stable source records and typed relationships so one fact can support many
future questions without duplicating prose.

### Stage 3 — Build and evaluate 1972 retrieval and observations

Implement a small observation library driven by questions people plausibly ask:
what made a show unusual, which performances connect to official releases or
fan selections, what preceded or followed a notable performance, and where
sources disagree. 1972 is a proof of retrieval and provenance mechanics, not
the natural scope of a career-evolution question. Each observation must include
its coverage boundary and representative evidence. Evaluate both factual
correctness and whether the presentation reveals a useful connection rather
than merely returning matching rows.

### Stage 4 — Select and enrich the cross-decade song cohort

Use a documented, question-driven rubric to select a stratified 50–100-song
cohort. This is an internal review and collection target. Runtime tools and
model instructions receive factual capabilities, coverage, editorial leads,
and source trails for the current question; they receive no cohort-size
metadata or global song rank. The criteria include recurring visitor-interest
signals, cross-era comparison potential, transition/suite role, lyric/history
evidence, recording/release coverage, and a reserved long-tail share. Signals
from fan communities are attributed selection evidence. Validate the same
question plans against sparse early and later eras before producing a full-span
observation.

Materialize only repeated, stable performance facts whose measured query cost
or packet size warrants it: first/last known dates, known totals, common
immediate neighbors, and their scopes and denominators. Request-time graph
queries and model judgment serve era, venue, tour, listening, and comparison
questions that depend on the visitor's actual framing.

For outdoor shows, enrich weather and event conditions only where a source
shows they materially shaped the event. Keep concert-site observations,
nearby-station or grid data, and recollections as separately scoped claims;
the historical-weather tool provides nearby-grid reanalysis, not an exact
concert-site observation. See `docs/question-driven-enrichment.md`.

### Stage 5 — Repeat typed passes across the timeline

Expand by reusable enrichment pass, not by writing one-off show dossiers. Pick
the next years or eras using product demand, source availability, and coverage
gaps. Re-run the same normalizers, importers, observation calculations, and
evaluations. High-interest anchor shows may receive deep review early, but they
must still use the shared model and expose their narrower coverage.

### Stage 6 — Add document retrieval selectively

Once rights and access rules are settled, index permitted source text separately
from canonical facts. Link chunks to resources and graph entities, retain source
and rights metadata, and retrieve excerpts only after the structured graph has
narrowed the question's scope.

## Operational considerations

- **Snapshot identity:** give each canonical import an immutable revision or
  content manifest so observations and evaluations can name their exact inputs.
- **Coverage as data:** track expected, observed, unresolved, held, and failed
  counts by source, fact type, and scope. Never infer completeness from row count
  alone.
- **Provenance at the relationship level:** record which source supports the
  release mapping, claim, selection, lineup, or recording relationship—not only
  the parent entity.
- **Correction propagation:** maintain dependencies from observations to input
  revisions and supporting entities so changed slices can be recomputed without
  rebuilding unrelated analysis.
- **Claim discipline:** keep attributed recollection, criticism, and lore
  queryable but distinct from canonical event facts and computed observations.
- **Evaluation by question family:** test entity resolution, traversal choice,
  ranking, coverage language, source attribution, and presentation—not just
  whether a row was returned.
- **Retrieval observability:** record query-plan name, resolved scope, row and
  token counts, selected examples, truncation, observation version, and fallback
  category without logging private reasoning or protected source text.
- **Source durability and rights:** expect external URLs and provider identifiers
  to change; verify them periodically and do not copy protected material into
  canonical or observation tables.
- **Performance:** add indexes and precomputation from measured queries. Avoid
  encoding brittle question-keyword routing where model reasoning over a clear
  retrieval brief can make the choice safely.

## Immediate next sequence

1. Run live-model evaluations for direct facts, recording recommendations,
   cross-decade song evolution, show-lore handoffs, notable-weather questions,
   source failures, and questions that merit no main-column expansion.
2. Use those traces to refine the decision brief, tool descriptions, eligible
   blocks, and source research routes. Measure when derived facts should become
   materialized observations.
3. Review the existing cross-decade priority queue against the question matrix:
   enrich its songs with performance/recording paths, editorial leads, and
   source trails while carrying each row's coverage risk.
4. Complete the remaining 1972 typed passes for release/track mappings,
   selections, claims/resources, equipment/personnel, and material outdoor-show
   context.
5. Add bounded show/performance source discovery and source snapshots after
   each source's access and rights review, then expand the same pattern through
   the cross-decade cohort.
