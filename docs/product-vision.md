# Product vision

## What Deadbot is for

Deadbot is an agentic Grateful Dead knowledge and music companion. A person should be able to explore a song, a show, a performance, a recording source, or a musician in ordinary language and move naturally between them.

The product is not meant to be a generic chat interface with a few links attached. Its useful core is a connected, provenance-aware model of the Dead's live history: what was played, where and when it happened, who performed, how pieces flowed together, which recordings and official releases document it, and where a listener can hear or learn more about it.

The user experience should feel like a knowledgeable guide and research companion. It should support both a quick factual answer ("What did they play after Dark Star?") and a richer path of discovery ("Show me a strong Veneta Bird Song recording, the players' roles, official listening options, chords, and worthwhile reading about it").

## The core mental model

Deadbot connects a small number of durable entities:

```text
song ← played as ← performance → occurs at → show → held at → venue
  ↑                     ↓                 ↓
writers               appears on        performers and roles
                        ↓
                    recording source → track/timestamp → playback link
                        ↓
                 official release / archival source

song, show, or performance → contextual resources → interviews, articles,
lessons, chords, videos, reviews, and other reading or listening
```

The distinctions are intentional:

- A **song** is a composition.
- A **performance** is that song played at one particular show, in a particular set position.
- A **recording** is one captured source of a show (for example AUD, SBD, or matrix), not the show itself.
- A **resource** is a source-owned piece of context, such as an interview, lesson, review, or video. It remains a link-out item with clear attribution.

That model enables questions and recommendations that a flat discography, a setlist site, or an ungrounded language model cannot answer well.

## What the assistant should do

The runtime uses an agent loop: the model decides which structured or approved external tool is useful, reads the result, and answers. It should:

- resolve a natural-language question to the correct entities;
- traverse structured relationships for factual answers;
- offer listening and viewing links for the relevant show or performance;
- surface relevant interviews, articles, lessons, chord sources, and anecdotal material when useful;
- distinguish a verified canonical fact from an attributed claim, recollection, or interpretation;
- acknowledge a gap rather than inventing an answer; and
- use live external tools only when a question actually requires current or outside information (for example weather, maps, astronomy, or newly published material).

The agent is a reasoning and retrieval layer over a reviewable knowledge base. It is not authorized to silently alter that knowledge base.

## What belongs in Deadbot versus a link

Deadbot should retain the structured facts and metadata needed to find, explain, connect, and evaluate information: identities, dates, set order, personnel and roles, recording lineage, identifiers, release mappings, resource relationships, provenance, and concise source-specific musical facts such as chord progressions.

It should usually link out to hosted or rights-sensitive material: audio, video, full lyrics, complete tabs or notation, full interviews, articles, books, reviews, and lesson text. Future document retrieval may use licensed or permitted excerpts and metadata, but must keep their source and rights context visible.

See `docs/graph-scope.md` for the detailed boundary.

## Product shape over time

The system has four complementary parts:

1. **Canonical knowledge graph** — reviewable normalized data for factual relationships.
2. **Context and document layer** — source-attributed prose and research material, separate from canonical facts.
3. **Tool-using agent** — a bounded agent loop that combines structured retrieval, approved source reading, and later live tools.
4. **Listening and exploration experience** — a FastAPI-backed interface that presents answers, provenance, entity cards, contextual links, and approved external-media paths clearly.

PostgreSQL is the planned operational store for the canonical graph. It can later support structured queries plus full-text/vector retrieval without prematurely adopting a separate graph database. The initial agent reads the canonical CSV layer directly while the importer is still to be built.

## Near-term definition of success

The first success criterion is not a broad all-years chatbot. It is a trustworthy Veneta 1972 vertical slice that can answer structured questions, find the relevant source links, make provenance clear, and hand a listener off to official or archival media.

After that is measured with an evaluation set, the collection can expand through 1972 and then outward. The product should grow by adding well-attributed coverage and dependable retrieval, not by pretending that all web material or model-generated music knowledge is equally authoritative.

## How an answer becomes an experience

Deadbot should not ask a model to create a page from scratch. Instead, grounded retrieval is followed by a bounded composition step that selects and orders approved display patterns: direct answer text, entity and performance cards, resource lists, media paths, provenance notes, and explicit gap states. The application renders that validated composition with normal frontend code.

This means a question about a song can naturally become a concise answer, performance listing, official listening option, source-specific chord link, and attributed reading list, while a question outside current coverage remains an honest explanation of the gap. Media embeds and short quotes are specialized patterns with their own approval, attribution, and rights safeguards; they are not arbitrary model output. See `docs/experience-architecture.md`.
