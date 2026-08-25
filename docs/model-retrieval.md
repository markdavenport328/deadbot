# Resource retrieval for the future model

External links are first-class, queryable graph records. A model should discover relevant resources with structured lookup before browsing the web.

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

The model can therefore answer with known structured facts immediately, offer relevant links, or read a specific source when the user asks for context. It should not indiscriminately crawl every linked page or treat external text as canonical without recording provenance and a normalization decision.

## Contextual material

For interviews, oral histories, articles, reviews, and memoirs, the graph stores the link, author or speaker, date, source, entity relationship, and a brief scope note—not a copied transcript. Retrieval should favor a direct interview or a performance-specific account over a broad essay, then use source quality and relationship type to rank ties.

Source-attributed claims remain source-attributed in answers. A musician's recollection, an eyewitness memoir, or an editor's analysis is valuable context, but it does not silently become a canonical show, songwriting, or recording fact. This lets the model say both *what the source says* and *where to read it*.
