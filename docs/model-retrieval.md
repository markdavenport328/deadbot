# Resource retrieval for the model

External links are first-class, queryable graph records. A model should discover
relevant resources through structured lookup before opening a reviewed source.

## What the model retrieves

One model owns the whole turn. It calls read-only tools directly for what the
current question needs, then ends the turn with one `finish_response` call
carrying the chat answer and main-body plan. There is no separate
research-then-compose step and no assembled hand-off packet between models;
the tools' JSON output, gathered over however many calls the turn takes, is
what the model reasons over. That output serves different jobs:

- **Canonical facts** answer identity, date, set order, people, recording, and
  release questions.
- **Derived observations** provide recalculable performance facts with their
  scope and denominator.
- **Editorial discovery guidance** offers fruitful song, transition, era, and
  show-context routes the model may investigate.
- **Source trails and research results** make selected lore, criticism, oral
  history, and listening paths available when they add something worth
  exploring.
- **Eligible experience blocks** let the model reference a library component
  by canonical ID in `finish_response`'s body plan — a detailed list,
  comparison, recording route, or source trail — when that is the clearest
  answer.

The model chooses which of these serve the question. A straightforward
fact can stand on its own; the same fact can open into a source trail when that
adds a useful connection. Cohort files and review queues remain internal
collection-planning artifacts and are excluded from runtime tool output.

## Retrieval path

```text
User asks about a song, show, or performance
      ↓
Resolve canonical entity ID
      ↓
Query attached resources and media links
      ↓
Rank by relationship type, relevance, and usefulness
      ↓
Open only the relevant external link when more detail is needed
```

For example, an interview about a song receives a `resources` row with type `interview` and a `resource_songs` row with relationship `about`. An essay discussing a show receives the same resource record plus a `resource_shows` row. A resource about one rendition can additionally link to `resource_performances`.

The model can therefore answer with known structured facts immediately, offer
relevant links, or research a registered source when context would make the
answer more useful. Source tools have reviewed hosts, paths, and capabilities;
their result packets retain the information needed to use them responsibly
without turning every answer into a methodology note. The fact-first/serendipity
loop and source-adapter plan are in
`docs/serendipity-research-plan.md`.

## Contextual material

For interviews, oral histories, articles, reviews, and memoirs, the graph stores the link, author or speaker, date, source, entity relationship, and a brief scope note—not a copied transcript. Retrieval should favor a direct interview or a performance-specific account over a broad essay, then use source quality and relationship type to rank ties.

When Deadbot relies on a musician's recollection, an eyewitness memoir, or an
editor's analysis, it should name the source naturally and link to it. Otherwise,
keep the sourcing in the supporting card or link rather than interrupting a
straightforward answer.
