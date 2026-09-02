# Experience and composition architecture

This document defines the durable architecture for Deadbot's user-facing experience. It supplements the product vision and agent-harness documents: it describes how a retrieved answer becomes an explorable interface without allowing a model to invent interface code or embed untrusted media.

## Decision summary

Deadbot will use a FastAPI application as its HTTP backend and a React + TypeScript client for its interactive interface. In production, FastAPI may serve the compiled client, so the product remains one deployable application.

The interface is schema-driven. A model may choose and order a small catalog of content blocks, but it does not generate HTML, CSS, JavaScript, iframe markup, or arbitrary URLs. The server validates the resulting response before the client renders it.

## Why this shape

The product needs more than a transcript of a chat answer. A question can meaningfully lead to a performance card, an official listening option, a chord resource, or an interview excerpt. These should feel like inviting routes into the music, not a display of the system's paperwork.

React is suitable for composing those reusable interactive patterns. FastAPI fits the existing Python, LangGraph, and Pydantic runtime, keeps the agent and data access on the server, and can expose both ordinary JSON endpoints and later streaming updates without a second application backend.

## Request-to-interface flow

```text
browser question
      |
      v
FastAPI experience endpoint
      |
      v
agent loop: read-only tools ... finish_response(plan)
      |
      v
plan resolution (references → validated blocks; ungrounded links dropped)
      |
      v
validated experience response (answer + typed blocks + sources)
      |
      v
React block renderer
```

One model owns the turn. It decides which tools to use, reads their results,
and ends by calling `finish_response`, whose arguments are the chat answer,
title, lead, mode, and a body that mixes model-written editorial blocks with
library components referenced by canonical ID. `deadbot/finish.py` resolves
those references against the store, keeps only links whose URLs the tools
returned this turn, and produces the validated response. The renderer is
deterministic application code.

This separation is intentional:

- Research determines what the system knows and which connections it can offer.
- The plan determines the concise visible answer and which approved
  presentation patterns best help a person explore the supporting material.
- Rendering determines how those patterns look and behave in the browser.

Neither plan resolution nor rendering may alter canonical data or make an unapproved external request.

## Experience response contract

The backend will expose a versioned Pydantic response model. Its top-level shape will contain the latest answer, a bounded experience mode, a browser-safe conversation transcript, optional page metadata, a sequence of typed blocks, and a source/provenance registry. The exact field names may evolve, but the following constraints are durable:

- Every block has an explicit, allowlisted `type`.
- Entity-oriented blocks refer to canonical IDs and/or server-supplied display data; the client does not resolve free-form model text into entities.
- Resources and media refer to approved stored records or server-validated external URLs.
- A block that relies on an outside perspective keeps its source linked and identifiable without making attribution the headline when it adds no value to the visitor.
- The client handles an unknown block type safely and visibly rather than attempting to interpret it.
- The response schema is versioned, tested, and validated on the server before it is returned to a browser.
- The transcript contains only visible human and final assistant text; it never exposes tool requests, tool payloads, internal prompts, or model reasoning.

An illustrative response is:

```json
{
  "schema_version": "1",
  "title": "Bird Song at Veneta",
  "answer": "Bird Song was played in the second set at the Veneta show.",
  "blocks": [
    {"type": "performance_card", "performance_id": "..."},
    {"type": "media_player", "media_link_id": "..."},
    {"type": "resource_list", "title": "Chord charts", "resource_ids": ["..."]}
  ],
  "sources": [
    {"source_id": "...", "kind": "canonical"},
    {"source_id": "...", "kind": "contextual_resource", "url": "..."}
  ]
}
```

The illustration is a contract pattern, not an instruction to expose all database fields. The API should return only the display data necessary for the requested blocks.

## Block catalog

The catalog combines flexible editorial patterns with richer domain components. New visual patterns require a schema, renderer, accessibility review, and tests before the model can reference them in a plan; they are capabilities for the model, never routes tied to question wording.

| Block | Purpose | Grounding and constraints |
| --- | --- | --- |
| Answer text | Concise direct answer with source references. | Must distinguish canonical facts from source-attributed context. |
| Narrative | Connect facts into a short, readable explanation. | Model-written from the grounded packet; never a fixed article template. |
| Fact grid | Emphasize a small set of details that matter together. | Model selects labels, values, and optional context from grounded material. |
| Timeline | Show sequence, change, or span when it clarifies the material. | Model shapes grounded markers and details; chronology is not forced for every date-bearing result. |
| Entity header | Identify a song, show, performance, person, or venue. | Uses a canonical entity reference. |
| Song, show, or performance card | Present core identity, ordering, personnel, recording, or release context. | Uses canonical data; show performance-specific facts only for the referenced rendition. |
| Performance spine | Place one rendition among its directly adjacent songs in a documented set. | Uses only canonical set order; it must not imply musical analysis or a segue beyond what is stored. |
| Comparison strip | Place selected renditions of one song across years. | Canonical performances only; one representative rendition per known year, with an explicit coverage note; never musical analysis. |
| Resource list | Group relevant interviews, articles, lessons, chord charts, or videos. | Links use stored resource metadata and retain source labels. |
| Composition credit list | Show known lyric, music, and writer roles for a song. | Uses canonical person/role rows and source-resource IDs; never presents unresolved candidates as confirmed credits. |
| Media player | Offer approved playback or video. | Uses a server-validated provider link; never model-authored iframe markup. |
| Media link | Offer an external listening/viewing path where an embed is unavailable or unsuitable. | Uses stored link metadata and provider labels. |
| Arrangement/chord resource | Point to a source-specific chord chart or show a concise structured progression where permitted. | Never presents a chart as universal for the song; does not reproduce full tabs, notation, or lyrics. |
| Arrangement key search | List only source-documented arrangements matching a requested key. | Must say that results are arrangement coverage, not universal song keys or a complete transposition catalog. |
| Quote card | Present a short, attributed excerpt. | Available only from a permitted source-reader result with attribution, URL, and excerpt limits. It is contextual material, never canonical fact. |
| Provenance note | Explain the distinction between canonical data and an outside source. | Uses the corresponding source registry entries. |
| Gap state | Explain a library limit or missing result. | Must not substitute a partial entity match or unrelated material. |

Cards and lists are presentation patterns, not new domain entities. The canonical graph remains the source of truth for the relationships they expose.

## Plan resolution rules

The model is Deadbot's editor, not a card sorter. Across the turn it reads the
latest question, recent conversation, and whatever it retrieves with the
read-only tools, then ends by calling `finish_response` with the short chat
answer and the main body as one editorial decision.

The plan can carry a body title and lead, shape grounded material into
narrative, fact-grid, or timeline patterns, and mix those with richer
library components such as setlists, recordings, arrangements, and media,
referenced by canonical ID. The palette supplies expressive options; no
question type is mapped to a particular pattern, depth, or ordering.

The prompt gives the model a persona and an outcome: answer crisply in chat
and make the main body useful, interesting, and explorable without
repetition. It does not provide a checklist for a "complete" guide or
block-specific placement rules. The model decides relevance, emphasis,
omission, titles, and reading order.

Grounding is id-level and deliberate: a component may be referenced by any
canonical ID that appeared in this turn's tool output, including a search
result, and the server then fetches the full component from the store — the
model does not have to re-retrieve an entity in full before it can show it.

Application code enforces only the response shape: it resolves referenced
component IDs against the store, drops any link whose URL the tools did not
return this turn, and rejects a call that does not fit the schema so the
model can correct it. It does not require an omission ledger, veto coverage
or provenance choices, select components from keywords, or substitute an
unedited database packet as though it were a finished experience. Editorial
failures are diagnosed at the model boundary and improved through context,
tools, prompting, palette design, and evaluations.

Research resources resolve differently from stored components. A reviewed
Dead.net tool result is referenced by a projected id, `research:<source>:<identifier>`,
and application code resolves it by re-matching that id against the turn's
own tool output rather than looking it up in the store; the host allowlist
in `deadbot/composition.py` still governs which URLs those tools can ever
surface to the browser. An editorial item may also carry its own outbound
link alongside its title, value, or detail. The browser renders markdown
links in the chat answer, lead, and editorial text, and renders an
editorial item's link the same way, so an outbound link (marked ↗) reads
distinctly from an ask-Deadbot follow-up button (marked →) that keeps the
visitor in the conversation instead of sending them away from it.

## Media and external-resource safety

Deadbot links to externally hosted media; it does not host, download, or proxy it. A media player is allowed only for providers with a deliberately implemented embed adapter, initially Spotify and YouTube where the provider's terms and available link form permit it.

The server owns provider-specific URL parsing and embed construction. It must derive the provider identifier from an approved canonical media link and pass only that identifier to a trusted client component. The model never supplies an iframe URL, iframe attributes, script, or arbitrary embed HTML. Unsupported, malformed, or unapproved links render as normal, clearly labeled outbound links.

Resource lists follow the same principle: they are link-outs backed by stored resource metadata. A future restricted source-reader may provide a short, rights-reviewed excerpt. Only that tool's explicit output may produce a quote card, and every quote card must show the source, attribution, and destination URL.

## API and session boundaries

The FastAPI layer is an experience adapter around the existing read-only runtime. It should initially provide:

- a health endpoint;
- an endpoint that submits a user question and returns a validated experience response;
- stable session/thread handling that maps to the agent's checkpoint identity;
- static delivery of the compiled client in production; and
- development configuration that permits a separate local client server.

The client creates one opaque thread ID and reuses it for follow-up questions.
The FastAPI endpoint maps that ID to the LangGraph checkpoint identity. The
agent therefore receives the preceding user and assistant messages as its
conversation context on each later request. The API returns that safe transcript
for the left conversation column, while plan resolution considers the
newest user turn and its `finish_response` plan for the main content column. Each
answer builds a fresh main-column experience from the current question.

The current checkpoint is intentionally in memory. It persists for the life of
one running application process, but is not durable across restart and is not a
multi-process session store. Persistent conversation history is a later
operational feature and must include retention, privacy, and authentication
decisions before it replaces this boundary.

Streaming is a follow-on capability. When added, it should emit typed progress events such as retrieval started, tool completed, plan resolution completed, and final response. Tool payloads, model reasoning, and internal prompts should not be exposed to the browser by default.

Authentication, rate limits, persistent conversation storage, and deployment configuration are separate product decisions. Their eventual addition must not weaken the read-only tool boundary or make the client a direct data-store or model client.

## Testing and observability

The experience layer requires tests at three levels:

- **Schema tests:** valid composed responses parse; malformed references, unknown block types, unsafe media input, and unsupported quotes fail safely.
- **Renderer tests:** every implemented block has an accessible fallback and external links show their source/provider context.
- **End-to-end examples:** representative Veneta questions produce a grounded answer with the expected cards, links, provenance notes, or gap state.

Record enough server-side trace information to diagnose a bad plan resolution: schema version, selected block types, referenced canonical/resource IDs, and validation fallback reason. Do not record protected source text or model reasoning merely for UI analytics.

## Non-goals

- A general-purpose page builder or model-generated interface code.
- Arbitrary browsing, arbitrary embeds, or client-side access to agent tools.
- Copying full interviews, lyrics, tabs, notation, audio, or video.
- Treating editorial, interview, memoir, or fan material as canonical fact.
- Replacing the canonical graph with a presentation-specific data model.

## Related documents

- `docs/product-vision.md` defines the user experience and information boundaries.
- `docs/architecture.md` places this layer in the wider system.
- `docs/agent-harness.md` defines the bounded read-only agent runtime.
- `docs/graph-scope.md` and `docs/provenance-policy.md` define content and provenance rules.
- `docs/development-plan.md` contains the working implementation sequence.
