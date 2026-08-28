# Experience and composition architecture

This document defines the durable architecture for Deadbot's user-facing experience. It supplements the product vision and agent-harness documents: it describes how a retrieved answer becomes an explorable interface without allowing a model to invent interface code, bypass provenance, or embed untrusted media.

## Decision summary

Deadbot will use a FastAPI application as its HTTP backend and a React + TypeScript client for its interactive interface. In production, FastAPI may serve the compiled client, so the product remains one deployable application.

The interface is schema-driven. A model may choose and order a small catalog of content blocks, but it does not generate HTML, CSS, JavaScript, iframe markup, or arbitrary URLs. The server validates the resulting response before the client renders it.

## Why this shape

The product needs more than a transcript of a chat answer. A question can meaningfully lead to a performance card, an official listening option, a source-specific chord resource, or a carefully attributed interview excerpt. These are different kinds of information with different provenance and rights rules.

React is suitable for composing those reusable interactive patterns. FastAPI fits the existing Python, LangGraph, and Pydantic runtime, keeps the agent and data access on the server, and can expose both ordinary JSON endpoints and later streaming updates without a second application backend.

## Request-to-interface flow

```text
browser question
      |
      v
FastAPI experience endpoint
      |
      v
read-only agent and approved retrieval tools
      |
      v
answer composer
      |
      v
validated experience response (answer + typed blocks + sources)
      |
      v
React block renderer
```

The agent remains responsible for deciding which read-only tools to use and for obtaining grounded material. The composer is a separate, bounded step that turns those retrieved results into a presentation plan. The renderer is deterministic application code.

This separation is intentional:

- Retrieval determines what the system knows and where it came from.
- Composition determines which approved presentation patterns best help a person explore that grounded material.
- Rendering determines how those patterns look and behave in the browser.

Neither composition nor rendering may alter canonical data or make an unapproved external request.

## Experience response contract

The backend will expose a versioned Pydantic response model. Its top-level shape will contain the latest answer, a bounded experience mode, a browser-safe conversation transcript, optional page metadata, a sequence of typed blocks, and a source/provenance registry. The exact field names may evolve, but the following constraints are durable:

- Every block has an explicit, allowlisted `type`.
- Entity-oriented blocks refer to canonical IDs and/or server-supplied display data; the client does not resolve free-form model text into entities.
- Resources and media refer to approved stored records or server-validated external URLs.
- Any block that makes or presents a source-attributed claim identifies its source and distinguishes it from canonical data.
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

The first release should implement a deliberately small catalog. New block types require a schema, renderer, provenance behavior, accessibility review, and tests before a composer can use them.

| Block | Purpose | Grounding and constraints |
| --- | --- | --- |
| Answer text | Concise direct answer with source references. | Must distinguish canonical facts from source-attributed context. |
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

## Composition rules

Composition is model-guided but bounded. A composer may decide that a question would be clearer with a show card followed by an official listening link, for example. It may not create a new card shape, turn an unverified statement into a fact, or use an unreturned resource because its name seems plausible.

The implemented first composer receives an enriched decision brief rather than raw files. It includes the latest question, recent conversation, grounded agent answer, and a rich inventory of candidates: their scope, purpose, canonical or contextual provenance, coverage metadata, relevant facts, and a structured `usage_guidance` field describing when that candidate helps or is redundant, so block-specific rules live on each candidate rather than in the shared system prompt. The model returns one bounded experience mode (`quick_fact`, `performance`, `show`, `listening`, `comparison`, `research`, `musician`, or `gap`) plus structured layout regions containing only server-owned candidate indexes. The server resolves those indexes back to the original validated blocks. Its system instructions and validation require it to:

- make the direct answer useful even when no optional block is appropriate;
- choose the smallest helpful set of blocks, rather than filling a page by default;
- reference only entities, resources, media links, and excerpts present in the retrieval packet;
- preserve the canonical-versus-contextual distinction in both text and block selection;
- use a gap state for unavailable information; and
- remain within response-size and block-count limits.

Deadbot follows a model-first design principle: improve the model's context,
retrieval brief, instructions, and evaluations before adding deterministic
intent-to-template rules. Deterministic code enforces safety and validation
boundaries; it does not replace ordinary relevance and presentation judgment.
See `AGENTS.md` for the working principle that applies to future changes.

The backend validates the composer output against the response model and resolves each reference against the retrieval packet. Invalid, missing, unsupported, empty, or unavailable-model results fall back to the deterministic candidate order. Provenance and coverage-gap blocks remain present when they were included in the candidate response; nothing is passed through as arbitrary JSON.

The deterministic adapter creates the candidate response directly from agent/tool results. It remains the fallback when the model-guided selection is disabled or fails. The API contract is unchanged by either path.

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
for the left conversation column, while the composition adapter considers only
the newest user turn and its retrieval results for the main content column.
Older cards and source lists must not accumulate in the main column.

The current checkpoint is intentionally in memory. It persists for the life of
one running application process, but is not durable across restart and is not a
multi-process session store. Persistent conversation history is a later
operational feature and must include retention, privacy, and authentication
decisions before it replaces this boundary.

Streaming is a follow-on capability. When added, it should emit typed progress events such as retrieval started, tool completed, composition completed, and final response. Tool payloads, model reasoning, and internal prompts should not be exposed to the browser by default.

Authentication, rate limits, persistent conversation storage, and deployment configuration are separate product decisions. Their eventual addition must not weaken the read-only tool boundary or make the client a direct data-store or model client.

## Testing and observability

The experience layer requires tests at three levels:

- **Schema tests:** valid composed responses parse; malformed references, unknown block types, unsafe media input, and unsupported quotes fail safely.
- **Renderer tests:** every implemented block has an accessible fallback and external links show their source/provider context.
- **End-to-end examples:** representative Veneta questions produce a grounded answer with the expected cards, links, provenance notes, or gap state.

Record enough server-side trace information to diagnose a bad composition: schema version, selected block types, referenced canonical/resource IDs, and validation fallback reason. Do not record protected source text or model reasoning merely for UI analytics.

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
