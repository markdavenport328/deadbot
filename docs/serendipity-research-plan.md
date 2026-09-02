# Fact-first answers and serendipitous exploration

Deadbot should feel like an exceptionally knowledgeable Deadhead: useful on
the facts, alive to the strange, revealing, and memorable parts of the music.
Its two columns have complementary jobs:

- The **conversation column** orients the visitor: a concise takeaway, a
  clarification when needed, and a natural handoff to the material prepared in
  the main column.
- The **exploration column** carries the detailed answer when a list,
  comparison, set fragment, recording route, or source trail is more useful
  there than in chat. It may also add color: useful set context, an unexpected
  connection, an attributed story, or a source worth opening.

The model decides how the columns work for each question. A quick fact may use
only chat and a compact supporting block. A comparison, recording request, or
listening route may put the substantive answer in the main column, with chat
offering a short handoff. A factual answer may also earn a source trail or a
bit of show lore when it gives the visitor a worthwhile next move.

## The fact-to-exploration loop

1. Resolve the visitor's entities and answer the direct question through the
   canonical PostgreSQL graph.
2. Supply the model with a compact editorial **discovery guide**: promising
   songs, transitions, show contexts, recording stories, and source trails for
   open-ended exploration. It supplies possible routes alongside canonical
   facts and derived observations.
3. Let the model decide whether additional context would genuinely help this
   visitor. For a Cornell setlist fact, it may choose a tape-history or archive
   trail; for an ordinary date lookup, it may choose nothing.
4. When useful, the model calls an approved source-specific research tool,
   then pairs the returned source-attributed context with the local graph's
   exact performances, recordings, releases, and links.
5. The model ends its turn by calling `finish_response` with the chat answer
   and a main-body plan; the server resolves that plan's references against the
   store into a small, validated set of main-column blocks.

For “What are the best recordings of Sugar Magnolia?”, the chat might say
“I've pulled several highly regarded listening paths; the main column shows the
   recording details and why each is worth trying.” The main column then carries
   the actual recording list, source type/lineage, any clearly attributed fan or
   curator signals, coverage, and playback links. The answer explains the basis
   for any “best” recommendation.

For a question such as “Which songs changed the most across the years?”, the
guide can nominate Friend of the Devil, They Love Each Other, Dancin', Sugaree,
and other productive leads. The model researches the relevant source material,
retrieves performance and recording paths across the relevant eras, and chooses
the strongest examples. It must frame the result as a useful, evidence-backed
set of candidates—not an objectively final musical ranking.

## What guides the model

The one model that owns the turn works from what its read-only tools return.
That grounded material includes:

- latest question and relevant conversation;
- resolved entity IDs for what the question names;
- canonical facts, graph paths, and listening paths retrieved for this question;
- complete eligible component data without block-specific editorial guidance;
- source research results, if requested; and
- a real information gap when it affects the answer.

Its persona and goal encourage curiosity, contrast, surprise, continuity,
weirdness, and a good story. The model may make a transparent
recommendation (“I would start here”), explain its listening judgment, and
surface a source trail when it enriches the answer. Facts, quotations, source
claims, and event details come from the supplied retrieval packet.

Internal collection material—cohort candidate files, review queues, and their
planning budgets—directs human enrichment work. The answer model receives the
capabilities, editorial leads, source trails, and coverage that are useful for
the current question, not a hidden global song ranking.

## Curated source research

Research tools operate only against a reviewed source registry. The registry is
an allowlist and capability declaration, not a substitute for model judgment.
Each source records its host restrictions, authority label, access/rights
policy, allowed operations, rate limits, retention policy, adapter version,
coverage notes, and review/suspension status.

The first available source-specific tool is
`get_deadnet_song_context(song_id_or_title)`. It starts from a resolved
canonical song and returns only approved Dead.net page metadata and a link.
It is deliberately narrow: no article body, lyric text, transcript, audio, or
implied editorial conclusion. The model calls it selectively when a source
trail would make a song question more rewarding; the selected result becomes a
main-column resource candidate.

The current set also includes `get_deadcast_metadata(...)` and
`get_lore_source_trails(...)`. Together they return scoped source metadata,
question themes, and links for reviewed Dead.net, Deadcast, Deadessays, and
Deadhead High paths. The next step is a bounded Dead.net discovery/search
adapter plus source-specific readers that can provide permitted attributed
excerpts after rights review.

Later adapters may cover Deadessays, HeadyVersion, and Deadhead High. They use
the same source-registry contract but remain independently reviewed because
their content, access, and rights policies differ. There is no general
model-controlled `fetch_url` tool.

Source tools return compact, normalized research packets: source identity,
resource metadata, canonical entity scope, retrieval state, coverage, allowed
excerpt status, and links. Failed, blocked, or uncollected results remain
distinct from source absence. A source statement is contextual material; it
does not automatically change canonical facts.

## Information layers

| Layer | Purpose |
| --- | --- |
| Canonical graph | Dates, set order, people, recordings, releases, and other durable facts. |
| Derived observations | Versioned facts calculated from the graph: counts, first/last known occurrences, recurrence, set placement, directed adjacency, and coverage. |
| Discovery guide | Editorial product guidance about fruitful exploration paths; it is not a factual ranking. |
| Resources, claims, and selections | Attributed interviews, criticism, history, community signals, and concise reviewed assertions. |
| Source research/cache | Rights-controlled live or cached source metadata and permitted excerpts. |

The PostgreSQL database is the operational home for joins, source registry,
cache metadata, research packets, observations, and retrieval. Reviewed source
inputs and normalization decisions remain versioned repository artifacts before
they are imported; the application must not accumulate an unreviewed,
database-only lore corpus.

## First implementation slice

1. **Done:** add reviewed source-registry and source-snapshot inputs/schema.
2. **Done:** seed Dead.net and Deadcast as metadata-only sources after access
   and rights review.
3. **Done:** build the resolved-song Dead.net metadata reader and bounded
   Deadcast metadata reader; both return coverage states and source links.
4. **Done:** add an initial reviewed lore-trail catalog and make discovery
   leads, research results, and resource candidates available to the model
   through its read-only tools.
5. **Next:** evaluate live model traces for direct facts, listening requests,
   song evolution, show lore, and unavailable-source cases; use the findings to
   improve the persona, tool descriptions, and source paths.
6. **Next:** add show/performance discovery, snapshot persistence, and
   source-specific permitted excerpts after each source's rights review.

## Evaluation examples

- **Cornell fact:** answer a simple setlist/venue question directly; add a
  Cornell source or listening path only when it makes a useful next move.
- **Veneta exploration:** combine show facts with a selected Deadcast or
  eyewitness path without presenting the account as canonical history.
- **Song evolution:** nominate and research multiple candidates, then pair
  them with cross-era performances/recordings and disclose the metric and
  coverage limits.
- **Negative cases:** source timeout, blocked page, irrelevant result,
  unapproved excerpt, partial coverage, and a model attempt to cite a source
  outside the packet all produce a safe, useful fallback.
