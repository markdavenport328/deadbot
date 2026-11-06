# Persistent exploration workspace — implementation handoff

Date: 2026-11-03. Status: ready for a bounded first implementation; live-model quality and timing review required before promotion.

## Objective and authority

Turn DeadBot's answer-page experience into a persistent listening/exploration workspace. Retain the left input rail; put every answer in the main workspace; make prior model-generated explorations revisitable; keep music playing across requests. This is an experience migration, not a model or retrieval rewrite.

User decisions in the planning chat supersede older presentation instructions: no answers in the rail, including brief facts. Existing AGENTS.md language allowing the model to choose chat versus main-body placement is superseded for this experiment only. Preserve its broader division: the model owns selection and interpretation; code owns facts, transport, playback, and state. One model continues to own each turn. Do not introduce a second model, keyword routing, or fixed choices of shows.

Implementation ownership: frontend workspace/state/stream integration and the smallest backward-compatible response metadata needed for tab placement. You are not alone in the repository: inspect status, preserve others' changes, and adapt to the current checkout. No production deployment or pushing. Follow repository push restrictions. Use an isolated branch/worktree if appropriate.

## Verified starting points

Inspected checkout: `/Users/markdavenport/Development/DeadBot`, HEAD `85ac036`; clean tracked status at inspection. Reinspect before implementation; this is a selective code review, not a complete audit.

- `web/src/App.tsx`: `askQuestion`, `chooseFollowUp`, `dispatchStreamEvent`, `groupsOfResponse`, draft reconciliation, existing unit components, `NowPlayingBar`, and conversation rail. It currently has response/draft/loading/thread/notebook state and renders assistant text in the rail.
- `web/src/ask-request.ts`: body includes question, thread_id, conversation, optional AskFocus, and signed notebook. Reuse this path for typed and model-invoking chip requests.
- `web/src/research-notebook.ts`: stores the notebook token. One latest token is not sufficient for historical follow-ups.
- `web/src/player.tsx`: shared PlayerProvider. Preserve its lifetime and current playback/queue semantics; do not remount it per exploration or tab.
- `web/src/queue.test.tsx`, `now-playing-bar.test.tsx`, `App.notebook.test.tsx`, `ask-request.test.ts`, `Grid.test.tsx`: existing regression coverage.
- `deadbot/experience.py`, `finish.py`, `plan_stream.py`, `answer_stream.py`: response schema, hydration, streamed page events and answer decoding.
- `deadbot/notebook.py`: signed research memory and conversation reconstruction. It is research context, not a UI-history store.
- `docs/UX-NEXT-STEPS.md`: existing stable unit keys and disclosure preservation; chart/grid client actions and focused asks. Read the full relevant entries.
- `web/src/visual-fixtures.ts` and fixtures: existing visual/replay mechanism; extend it instead of adding another demo framework.

## Settled UX

### Shell

Desktop: left rail with one request history and composer; main workspace with Listening / Charts / Context; persistent compact player with expandable queue. No separate transcript, duplicate undo bar, or assistant answer in the rail. All content remains accessible on narrow widths; reuse the existing dock where possible. Labels are provisional but behavior is settled.

The model may choose the initial tab for a new request. After the visitor interacts with tabs or content, later events must not move their focus or change tabs. Do not populate every tab merely for symmetry. Empty tabs explain absence without an extra model call. A simple factual question opens Context and can end there.

### History — the corrected boundary

One entry per visitor-initiated model operation: typed request, Ask chip, or other explicit action that asks the model to generate/revise the exploration. Label with the actual request or comprehensible chip label. Internal model/tool calls and streaming chunks belong to that entry, not separate entries.

Do NOT record tab changes, local filtering/sorting, chart selection, disclosure toggles, queue additions/removals, playback, or deterministic data hydration. Those are already manageable through interface controls. Preserve local view state with its exploration without adding history rows.

Back/forward arrows live only in the rail, beside history. Selecting an entry restores its response, relevant local view state, conversation, notebook, and request context without a model call. Playback and queue are never restored or changed by history.

Use a linear forward path for v1. Starting from an older entry does not destroy forward entries while loading. Only successful completion replaces that forward path. Failed/cancelled attempts preserve it. A new request from an old entry must not include later turns or their research token.

### Listening and information

Listening items have explicit Play and Add to queue actions. New results never autoplay or replace the queue. Preserve the repository's existing Play semantics for this slice; any change to those semantics requires a separately reviewed design.

Show details use expansion/information controls; hover may supplement but cannot be the only access. Retain source provenance. Context holds the short answer and longer narrative; avoid duplicating the same short answer twice within Context.

Charts refer to the same canonical records as Listening. Chart selection reveals relevant items; it does not automatically play them. Reuse existing chart-to-player interactions.

### Progressive behavior

Keep the current usable exploration while a follow-up is pending. Mark it as the previous result and show pending status in the workspace. A new root request can use an empty pending view.

Display grounded listening blocks as they arrive. Context can finish later. Do not invent an instant recommendation or replace model judgment with arbitrary records. Preserve keys, selections, disclosures and scroll during stream-to-final reconciliation.

For v1 one model request may be active at a time. Disable additional model submissions while it is pending; local controls remain usable. History navigation cancels/invalidates the pending request. Request IDs and base revision checks prevent late callbacks from modifying the restored state. Browser cancellation alone is insufficient.

## State contract (semantic requirements, not mandated filenames)

Create a workspace reducer/store separate from player state. Suggested modules: `web/src/exploration-state.ts`, `ExplorationHistory.tsx`, `ExplorationWorkspace.tsx`, and focused tests; integrate with existing App and stylesheet.

Completed entry: stable id; parent id; request text; source (typed/chip); AskFocus if present; immutable completed response; response conversation; returned signed notebook or null; thread identity; local view state (active tab, selected entities, filters, disclosures, scroll where feasible).

Pending request: unique request id; base entry id; input; staged draft; status/error; whether visitor has interacted; abort handle kept outside serializable state.

Do not clone media elements, player context, or queue into entries. Keep notebook tokens opaque. Missing/invalid notebook returns null rather than retaining a stale token.

History restore synchronizes the active request context and notebook storage. Verify server thread/checkpointer behavior: if server thread state would reintroduce future turns, allocate a fresh thread identity for the restored branch while sending the selected conversation/notebook. Document the chosen behavior with a regression test.

Phase 1 history is in-memory for the session; reload persistence is out of scope. Make this limit clear in delivery notes. Do not pretend the notebook token alone restores an exploration.

## Tab/content contract

Preserve existing content and grouping; do not silently drop unfamiliar blocks. Add optional presentation metadata only where needed: preferred initial tab and group destination (`listening`, `charts`, `context`). Keep existing responses valid. Reuse existing group/block identity and hydration rather than introducing a second page-plan format.

The model chooses initial tab and destinations for new plans. Legacy fallback: playable entity collections to Listening, charts/grids/timelines with data interactions to Charts, prose/facts/source narratives to Context; ambiguous or unsupported content to Context. A block can retain its existing embedded chart/play controls—do not split complex units destructively just to enforce tab purity. Review a song unit, a grid, and a mixed editorial group before finalizing the adapter.

Fallback is compatibility behavior, not a question-keyword router. Answer text streams into Context using the existing answer event; it never renders in the rail. Ensure plain responses and streamed responses resolve to the same tabs and content.

## Work packages and acceptance

### 1. State and history

Implement the reducer and history rail with fixtures before changing model prompts. Test completed request recording, restoring conversation/notebook, excluded local actions, forward navigation, successful branching, failed branching, and stale stream rejection. Preserve player provider placement.

Acceptance: two model asks produce two history entries; ten local control operations produce none. Revisiting entry one does not call the API or alter playback. A follow-up from entry one sends entry one's context, never entry two's.

### 2. Workspace shell and routing

Move all assistant response/progress content to the main area; reuse renderer and existing components in tabs. Introduce optional tab metadata with backwards-compatible defaults if needed. If schema changes, regenerate rather than hand-edit generated types using the repository's existing OpenAPI export workflow.

Acceptance: birthday-style short response appears only in Context; unknown blocks remain accessible; legacy fixtures still render; one player survives requests and tab switches. Keyboard focus, tab semantics, mobile input/player access, and status announcements work.

### 3. Streaming and refinement

Connect pending request/revision guards to live and replay paths. Preserve current content during follow-up. Reconcile stable units without resetting user actions. A successful refinement commits one history entry and its corresponding notebook. Failures keep prior useful content and offer Retry in the workspace.

Acceptance: fixture emits a playable block before the narrative completes, and the visitor can use it immediately. Selecting Charts during streaming is not overridden by late Context output. Restoring history during a request prevents all late events from updating the active entry.

### 4. Vertical-slice evaluation

Use MSG history → chart exploration → focused late-'80s follow-up → prior-entry restoration. Also test a brief birthday question, Veneta narrative with a show, missing audio, no relevant chart, model failure, and retry. Fixtures must be explicitly labeled illustrative; live historical claims require actual catalog/source grounding.

Compare against the existing runtime for first useful playable content, first Context answer, completion, follow-up latency, model-call count, and factual/interaction quality. Browser render timing is distinct from server event timing. Keep model settings and questions comparable; record commit/configuration/sample size. Do not promise improvement from UI structure alone.

## Validation commands

Verified scripts in web/package.json:

```sh
npm --prefix /Users/markdavenport/Development/DeadBot/web test
npm --prefix /Users/markdavenport/Development/DeadBot/web run build
```

Adapt absolute paths if using an isolated worktree. Run focused frontend tests during development and the frontend suite/build for completion. For backend contract changes inspect pyproject.toml and existing test conventions, run affected schema/finish/stream/notebook tests, and record exact commands. Do not claim fixture tests establish model quality; use representative live runs for prompt/schema behavior and report unavailable credentials as a limitation.

Check desktop, 320px, keyboard-only interaction, 200% zoom, reduced motion, stream/final parity, and failure recovery. No automated assertion should substitute for reviewing the rendered transition.

## Rollout and boundaries

Keep the current renderer accessible behind a temporary development/feature toggle during the slice. Rollback selects the old shell; avoid data migrations and persistent history storage. Do not remove the old path before the new slice passes review.

Not in this implementation: new model routing, small-model training, preparation pipeline, cache redesign, cross-session history, generalized JSON patch language, arbitrary tool generation, or rewriting the agent loop. These are separate experiments informed by the slice.

## Review points requiring the planning model

Bring back a concrete proposal if existing mixed groups cannot map into tabs without losing meaning; if stable unit reconciliation requires a new model-level change protocol; or if measured latency prevents the listening-first experience despite streaming. Complete independent state/shell work while identifying these issues. Do not silently solve them with a second model, keyword dispatch, or global architectural rewrite.

The UX requirement is adaptation without losing work. A complete new page plan reconciled by stable identities is acceptable for v1. Fine-grained model-authored mutations are a later hypothesis, not a prerequisite.

## Return package

Changed files and rationale; screenshots/video of the primary path; exact tests and results; live model observations with sample sizes; unmet acceptance criteria; failures/negative findings; remaining decisions. Update docs/UX-NEXT-STEPS.md with final implemented behavior and link this plan. No production deployment or push.

## Start prompt

Read AGENTS.md and this plan. Implement work packages 1–3 as a bounded persistent-workspace slice, then perform package 4 verification. Preserve current code and other contributors' changes. Use existing player, stream, component, and notebook contracts. History is model-turn history, never a log of ordinary UI controls. All answers belong in the main workspace. Do not broaden into runtime optimization. Return evidence and flag the explicit review points above.
