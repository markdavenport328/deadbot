# Question-driven enrichment strategy

Deadbot should deepen information where it helps answer recurring visitor
questions, not attempt to write an equal dossier for every song or show.
The first deep collection year, 1972, is a proving ground for sources,
relationships, retrieval, and coverage reporting. It is not the natural scope
of questions such as "How did Sugaree change?" Those are cross-decade questions
and require an explicitly stated full-span performance universe.

## Two complementary scopes

1. **Broad spine, 1965–1995.** Maintain reviewed identities, dates, venues,
   ordered performances, lineup evidence, and coverage states for navigation
   and for honest full-span denominators.
2. **Deep, typed slices.** Use all of 1972 to validate release, recording,
   selection, claim, resource, equipment, and observation relationships. Then
   apply the same passes to a deliberately selected cross-decade song cohort
   and to high-interest show contexts.

A 1972 observation may describe only the clearly named 1972 source universe.
It must not imply that a song's evolution is limited to 1972 or that a
partial year is a complete career denominator.

## Start from question families

Question families can guide collection toward useful graph paths and evidence,
but they must not become response templates or deterministic fallback rules.
The models decide what a particular question needs from the material available.

| Question family | Example | Required enrichment |
| --- | --- | --- |
| Cross-decade song evolution | “How did Sugaree differ in 1974 and 1980?” | bounded performance universe, era scopes, recording/release paths, source-specific arrangements or attributed context where available |
| Version and listening path | “Which recordings document this rendition?” | recording lineage, track mappings, completeness, official/archive status, provider link metadata |
| Transition and set flow | “Where did China Cat flow into Rider?” | ordered performance adjacency, raw segue notation, accepted transition evidence and track boundaries |
| Song history | “When did it debut, return, or disappear?” | source-scoped counts, first/last dates, gaps, held or missing-data states |
| Show context | “Did weather materially affect this outdoor show?” | source-qualified event, weather, production, benefit, guest, or venue-context claims |
| Attributed taste | “Which versions are frequently recommended?” | dated curator/fan selection lists or reviewed sources, never a canonical ranking |

## Select a stratified 50–100-song cohort

This is an internal collection and review budget. It directs research effort
across the repertoire and carries no runtime rank or cohort-size metadata into
the model's tools, prompt, or retrieved context. Let collected evidence
determine the mix. Start with a transparent candidate score and preserve its dimensions:

- recurring version or recommendation discussion from independent, dated fan
  signals;
- opportunity for meaningful cross-era comparison;
- transition/suite centrality;
- documented lyric, writing, or historical context;
- official-release, recording, and source diversity;
- ability to answer more than one question family; and
- a reserved long-tail share for low-frequency but distinctive songs.

Community recommendations are attributed selection signals. They can nominate
a cohort and help answer “frequently recommended” but cannot establish that a
performance is objectively best. Inclusion in the cohort requires a documented
rationale, source inventory, and coverage state; it does not require complete
coverage before the song can be useful.

## What this changes about enrichment

Collection produces two complementary outputs:

1. **Factual enrichment** strengthens the broad graph: show/setlist identity,
   recording lineage and mappings, release relationships, credits, personnel,
   and explicit coverage. It supports direct answers and reproducible derived
   observations across the timeline.
2. **Discovery enrichment** makes the graph rewarding to explore: reviewed
   source trails, concise attributed lore, curator/fan selection signals,
   transition and arrangement leads, and noteworthy show context. It gives the
   model promising paths to investigate or surface in the main column.

Discovery enrichment is question-led and selective. Source metadata, scope,
review state, access/rights policy, and typed entity links make each lead
retrievable. The model decides whether a lead fits the visitor's question and
may keep a direct answer self-contained.

### Four reusable enrichment products

- **Derived performance profiles**: recalculable facts such as first and last
  known performance, known total, immediate predecessor/successor patterns,
  and their denominators and coverage scope.
- **Editorial discovery leads**: compact invitations to investigate a musical,
  historical, transition, or listening question. They help the model notice
  fertile routes without making a claim about the song.
- **Source-researched lore**: attributed, reviewable context about a song,
  show, tour, recording, or community conversation, stored with source scope
  and a clear distinction between documentation and interpretation.
- **Source-linked listening paths**: canonical performance and recording links
  paired with selected source trails so a visitor can hear the comparison and
  follow the story.

Measure this pass by question utility, not just rows: direct source coverage by
song/show/performance, diversity of useful source types, reviewed lore claims,
recording/listening paths across relevant eras, and honest unavailable/held
states. The source-registry and research-tool rollout is defined in
`docs/serendipity-research-plan.md`.

### Derived performance facts: calculate first, materialize when measured

The first factual profile is intentionally an **on-demand derived observation**:
for a resolved song, it returns the known-performance total, first and last
known dates, and the most frequent immediate predecessor/successor in the
documented set order, including the relevant denominators and current-library
scope. This is useful now because it is small, transparent, and easy to
recalculate after an import.

Do not confuse that with model reasoning. The model can explain why a pattern
is worth noticing or choose to pair it with a discovery lead; it must not infer
an arrangement change, transition quality, or fan consensus from these counts
alone. Once bounded PostgreSQL retrieval is measured, materialize the most
frequent profiles as versioned observations only where it meaningfully reduces
packet cost or repeated query work. Arbitrary date/venue/tour/era cuts remain
parameterized queries rather than an explosion of precomputed rows.

## Notable outdoor-show conditions

Weather and event conditions enter enrichment when they materially shaped the
show: heat, rain, lightning, snow, wind, evacuation, a benefit setting,
production constraints, or a documented crowd response. This keeps the focus
on the conditions a visitor may actually want Deadbot to bring to life.

Keep these as typed, source-qualified context rather than a flat canonical
weather field. Every record should preserve:

- the show and context type;
- source/resource, source kind, and attribution where relevant;
- geographic scope (`concert_site`, `nearby_station`, or `nearby_grid_cell`);
- coverage (`direct`, `nearby_proxy`, `reported_claim`, `partial`, or
  `unknown`); and
- a review state and verification date.

When a question or stored source indicates notable conditions, the agent may
call `get_historical_weather` to add Open-Meteo's nearby-grid-cell historical
reanalysis. It is corroborating context, not an exact station reading or proof
of conditions at the stage. Direct observations, government-station data, and
oral-history claims must remain visibly distinct.

## Pilot and rollout

1. Define and test the coverage matrix with representative questions,
   including absent and held cases.
2. Complete 1972 typed enrichment sufficient to test those graph paths and
   provenance rules.
3. Measure packet size, query plans, ranking, coverage language, and model
   composition on 1972.
4. Validate the same question suite against at least one sparse early-era and
   one later-era slice.
5. Select the first cross-decade 50–100-song cohort from the recorded signals,
   then expand only where evaluation and source coverage justify it.

Every derived observation records its input snapshot, calculation version,
scope, denominator, exclusions, supporting entities/resources, and whether it
is current. Visitor-facing prose is composed only from that grounded packet.
