# Resource retrieval for the future model

External links are first-class, queryable graph records. A model should discover
relevant resources through structured lookup before opening a reviewed source.

## The answer brief

The agent answers from a compact decision brief assembled for the current
question. Its layers have different jobs:

- **Canonical facts** answer identity, date, set order, people, recording, and
  release questions.
- **Derived observations** provide recalculable performance facts with their
  scope and denominator.
- **Editorial discovery guidance** offers fruitful song, transition, era, and
  show-context routes the model may investigate.
- **Source trails and research results** make selected lore, criticism, oral
  history, and listening paths available with their source context.
- **Eligible experience blocks** let the model put a detailed list,
  comparison, recording route, or source trail in the main column when that is
  the clearest answer.

The model chooses which of these layers serve the question. A straightforward
fact can stand on its own; the same fact can open into a source trail when that
adds a useful connection. Cohort files and review queues remain internal
collection-planning artifacts and are excluded from runtime answer packets.

## Retrieval path

```text
User asks about a song, show, or performance
      ↓
Resolve canonical entity ID
      ↓
Query attached resources and media links
      ↓
Rank by relationship type, source, and provenance
      ↓
Open only the relevant external link when more detail is needed
```

For example, an interview about a song receives a `resources` row with type `interview` and a `resource_songs` row with relationship `about`. An essay discussing a show receives the same resource record plus a `resource_shows` row. A resource about one rendition can additionally link to `resource_performances`.

The model can therefore answer with known structured facts immediately, offer
relevant links, or research a registered source when context would make the
answer more useful. Source tools have reviewed hosts, paths, and capabilities;
their result packets preserve source identity, scope, coverage, and permitted
use. The fact-first/serendipity loop and source-adapter plan are in
`docs/serendipity-research-plan.md`.

## Contextual material

For interviews, oral histories, articles, reviews, and memoirs, the graph stores the link, author or speaker, date, source, entity relationship, and a brief scope note—not a copied transcript. Retrieval should favor a direct interview or a performance-specific account over a broad essay, then use source quality and relationship type to rank ties.

Source-attributed claims remain source-attributed in answers. A musician's recollection, an eyewitness memoir, or an editor's analysis is valuable context, but it does not silently become a canonical show, songwriting, or recording fact. This lets the model say both *what the source says* and *where to read it*.
