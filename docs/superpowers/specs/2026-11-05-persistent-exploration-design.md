# Persistent exploration workspace — design

Date: 2026-11-05. Status: approved design, ready for an implementation plan.

Sources: [the planning handoff](../../plans/persistent-exploration/PLAN.md),
[the original MSG wireframe](../../plans/persistent-exploration/msg-wireframe.html),
and [the workspace sketch](../../plans/persistent-exploration/workspace-sketch.html),
which shows every state below as a scene. Where this spec and the handoff
differ, this spec wins; the differences are listed at the end.

## Goal

Every answer lives in one main workspace with three tabs (Listen, Charts,
Read). The left rail holds only the request history and the ask box. Earlier
explorations can be revisited without a model call, and the music keeps playing
through all of it.

This is a change to the experience, not to research or retrieval. One model
still owns each turn and delivers it in one `finish_response` call. The model
picks what to show, where it goes and which tab opens. Code keeps the facts,
transport, playback and history state.

## Settled decisions

| Question | Decision |
| --- | --- |
| Opening tab | The model chooses it (`initial_tab`) for every new request. |
| Stream order | Unchanged for v1: the short answer still streams before the cards. A groups-first variant is a measured experiment in PR 3. |
| Rollout | Visitors keep today's shell. The workspace is opt-in with `?shell=workspace` (remembered per browser) until reviewed. |
| Tab names | Listen · Charts · Read. |
| Sources | No Sources tab. Sources sit at the foot of Read and stay on each card's disclosure. |
| Card layout | Unit cards are always one per row. No two- or three-up layouts in the workspace. |
| Unused tabs | Grayed out and inert once the page is finished. While streaming, a waiting tab says "preparing". |
| Progress | No "still composing" banner after the first usable content. Remaining work shows only on tab marks and the rail's pending row. |
| New chat | Starts a new thread and keeps history. Fresh starts append at the end and never drop entries. |
| Phone history | Behind the hamburger menu, above the site links. The dock keeps two rows: player and ask box. |
| Song units in Charts | Allowed, with their Play and + Queue controls intact. |

## Architecture

Approach: lift the request client out of `App.tsx`, add a new shell beside the
old one, and share everything else.

- **`web/src/ask-client.ts`** (new). `askStreaming` and `askPlain` move here from
  `App.tsx`, along with the dev `?stream=` replay. Each call takes an
  `AbortSignal` and a request id, and every event it hands back carries that
  id. The old shell calls it exactly as it calls the inline functions today.
- **`web/src/exploration-state.ts`** (new). A pure reducer with no React and no
  player state: entries, cursor, pending request, per-entry view state. It can
  be tested on its own.
- **`web/src/tab-routing.ts`** (new). Places a group in a tab using the group's
  `tab`, falling back to its first block's type when `tab` is absent (see
  below). The streamed draft and the final response both go through it.
- **`web/src/WorkspaceShell.tsx`** (new) with **`ExplorationHistory.tsx`** and
  **`WorkspaceTabs.tsx`**. The shell reuses `ComposedPage`'s group and unit
  renderers, `NowPlayingBar`, the start screen, the phone dock and `SiteMenu`.
- **`App.tsx`** reads the shell toggle and renders the old shell or the new one.
  Both sit inside the one `PlayerProvider`, which is never remounted.

## State and history

**Entry**: one per visitor-started model request (typed question, Ask chip,
splash chip, or ask-from-page).
- `id`, `parentId`, `root` (whether it started a thread)
- `request` (the text shown in history), `source` (typed / chip), `focus` (`AskFocus` or null)
- `response`: the final `ExperienceResponse`, never edited after commit. Its
  `conversation` and `notebook` are this entry's request context.
- `threadId`
- `view`: active tab, open disclosures (by stable unit key), chart/grid
  selection, and scroll position per tab

**Pending request**: `requestId`, `baseEntryId` (null for a fresh start),
`question`, `focus`, the streamed draft, statuses, the model's `initialTab`,
`interacted`, and `error`. The `AbortController` lives in a ref, outside the
reducer.

**Actions**: `submit`, `streamEvent(requestId, …)`, `complete(requestId, response)`,
`fail(requestId, message)`, `cancel`, `navigate(entryId)`, `updateView(entryId | pending, patch)`.

**Rules:**
- The reducer ignores any stream, complete or fail action whose `requestId` is
  not the current pending one. Navigating aborts the fetch *and* clears the
  pending request, so late events are dropped even if the abort arrives late.
- **Follow-up succeeds**: entries after the base entry are dropped, the new entry
  is appended, and the cursor moves to it.
- **Fresh start succeeds**: the new entry is appended at the end with
  `root: true`, and nothing is dropped.
- **Failure or cancel**: entries are unchanged.
- **Follow-ups send the current entry's context**: its `response.conversation`
  and `response.notebook`, never the latest entry's. The notebook in
  `localStorage` is rewritten when the visitor navigates.
- **Fresh starts send no context**: no conversation and no notebook, with a new
  `threadId`.
- **Server thread state is already safe.** When conversation or notebook is
  present, `deadbot/api.py` runs the turn on an isolated invocation thread, so a
  restored branch cannot pick up later turns. A regression test pins this; no
  new thread id is needed for follow-ups.
- **Local actions never add history**: tabs, disclosures, chart picks, scrolling,
  Play, + Queue and queue edits only patch `view` (or touch the player). History
  never reads or restores the player or queue.
- History is in memory for the session. A reload starts with an empty list,
  and the delivery notes will say so.

## Shell

**Desktop.**
- **Rail**: masthead with New chat, "Your explorations" with ← →, the history
  list, and the composer. A pending request shows as one extra row ("Asking ·
  …" with Stop). A failed request shows "Didn't finish". A fresh thread gets a
  "New thread" divider. The rail holds no answers, messages or progress.
- **Workspace**: eyebrow and title, a sticky tab bar, then the active tab panel.
- **Player bar**: in place, as today.

**Phone.**
- The tab bar sticks to the top of the workspace.
- The dock holds the player strip and the ask box.
- The site hamburger opens the menu with history first (← →, the list, New
  chat), then the existing site links. A dot on the hamburger means a request
  is running.

**Start screen**: unchanged. The first ask moves into the workspace instead of
the old layout. After New chat, the workspace shows the start view, and
history stays in the rail.

## Tabs and content

**Contract (backward compatible):**
- `finish_response` gains `initial_tab: "listen" | "charts" | "read"` as its
  **first** field, so the stream scanner reads it before the answer starts.
  Each group gains an optional `tab` with the same three values.
- `ExperienceResponse.initial_tab` and `ExperienceGroup.tab` are optional.
  `page_head` carries `initial_tab`, and `group_open` carries `tab`.
- Regenerate `openapi.json` and run `gen:types`. Generated files are never
  edited by hand.
- **Prompt**: two or three sentences in the persona on what each tab is for
  (hear it, see it across time or categories, read the answer and its story),
  written as goals. The model picks the opening tab by where this question's
  first attention belongs, and can leave tabs empty.

**Fallback when `tab` is absent** (old fixtures, cached responses, a skipped
field). This is compatibility only, not a router. The whole group is placed
by its first block:
- **Listen**: `show_unit`, `performance_unit`, `album_unit`, `song_overview`,
  `show_selection`, `listening_hero`, `version_strip`, `media_link`, and
  `entity_card` for shows and performances.
- **Charts**: `data_chart`, `grid`.
- **Read**: everything else, including unrecognised blocks.

When `initial_tab` is absent: Listen if any group placed there, else Read.

**Placement rules:**
- Groups are never split. A song unit placed in Charts keeps its timeline,
  Play and + Queue.
- Within a tab, groups keep the model's order.
- **Read** shows, in order: the short answer (`chat_answer`, streaming live),
  `body_lead` if present, the Read groups, then sources. The short answer
  appears once on the page.
- **One per row**: comparison groups stack in the workspace rather than
  laying out side by side. The old shell keeps its aligned peer cards.

**Tab states:**
- *Preparing*: the request is running and nothing has landed in this tab yet.
  The panel shows a quiet placeholder.
- *New* (●): content arrived while the visitor is on another tab.
- *Unused*: the page is finished and the tab is empty. It is grayed out and
  `aria-disabled`, and clicks do nothing.
- The status region announces "Listen ready" (and so on) once per tab per
  request.

**Focus rule**: `initial_tab` opens a tab only until the visitor clicks a tab,
opens a disclosure, picks a chart mark, plays or queues something, or scrolls
the workspace. After that, nothing changes their tab or scroll.

## Progressive behavior

**Fresh start**: the title "Working" with the request, then the status lines.
When `page_head` arrives, the tab bar appears and opens `initial_tab`. The
short answer streams into Read, and groups fill their tabs as they arrive.
Cards are usable (Play, + Queue, disclosures) as soon as they render.

**Follow-up**: the current page stays up, dimmed and labelled "Previous result"
but still fully usable, under a banner with the request, the latest status and
Stop. The workspace switches to the draft when the first answer text or card
arrives. From then on there is no banner.

**Stream to final**: the draft and the final response use the same routing and
the same stable unit keys, so open disclosures, chart picks, the active tab and
scroll survive the swap. The visitor keeps what was streamed.

**One request at a time**: while a request runs, the composer's submit, Ask
chips and splash chips are disabled. Every other control works.

**Known gap**: when the model opens on Listen, the answer is ready in Read a
few seconds before the first card. v1 accepts this. PR 3 measures a variant
where `groups` comes before `chat_answer` in `finish_response`.

## Errors

- **Transport failure** (network, server error, or a stream that closes before
  `response`): the previous page stays unchanged under an error line with
  **Retry** and **Dismiss**, and the rail row shows "Didn't finish". Retry
  resends the same question, focus and base entry. For a failed fresh start,
  the line sits on the start view.
- **Gap-state response**: a real answer. It commits as an entry and renders in
  Read.
- **Navigating during a request**: the request is cancelled with no error
  shown.

## Testing

**Unit and fixture tests (Vitest):**
- **Reducer**: two asks make two entries, and ten local actions make none. A
  follow-up from entry 1 sends entry 1's conversation and notebook. A
  successful follow-up from an old entry drops the entries after it; a
  successful fresh start drops none; failure and cancel change nothing. Stale
  `requestId` events are ignored. Navigation clears the pending request.
- **Routing**: each fallback block type lands in its tab; unknown blocks land
  in Read; the model's `tab` overrides the fallback; the draft and the final
  response route identically.
- **Shell**: a birthday-style fixture has only Read enabled. Legacy fixtures
  render. Choosing Charts mid-stream survives late Read groups. Navigating
  never calls fetch or touches the player. One `PlayerProvider` survives
  requests, tab switches and history moves. Tablist keyboard behaviour works.
- **Server** (pytest, `PYTHONPATH=.`): `_prepare` isolates the invocation thread
  when conversation or notebook is present. `initial_tab` and group `tab`
  round-trip through `finish`, `plan_stream` events and `ExperienceResponse`.
  Responses without them still validate.
- **Existing suites** (`queue`, `now-playing-bar`, `App.notebook`,
  `ask-request`, `Grid`, Python finish/stream/notebook) pass against the old
  shell.
- A `?stream=msg-workspace` fixture, labelled illustrative, where a playable
  card lands before the Read narrative finishes.

**Live verification** (model-facing work is not done until this runs):
- **Questions**: MSG history → Charts → "Focus on the late '80s" → back to
  entry 1; Jerry Garcia's birthday; Veneta '72; a show with no audio; a
  question with nothing to chart; a forced failure, then Retry.
- **Timing**: `scripts/trace_stream.py` logs when `initial_tab` arrives and the
  first group per tab. Old and new are compared on first playable card, first
  Read text, completion, follow-up time, and model calls per turn. Each record
  notes commit, model, effort and sample size. Server timing and browser render
  timing are reported separately.
- **By eye**: desktop, 320px, keyboard only, 200% zoom and reduced motion,
  with screenshots of the main path.

## Delivery

Three PRs, each safe to merge behind the toggle:

1. **Client and state.** `ask-client.ts` extracted (old shell uses it),
   `exploration-state.ts`, `tab-routing.ts`, their tests, and the server
   thread-isolation test. No visible change.
2. **Workspace shell.** `?shell=workspace`, rail history, tabs with fallback
   routing, the phone menu history, the stream fixture, and shell tests.
3. **Model contract.** `initial_tab` and group `tab` in the schema, stream
   events and prompt; regenerated types; live runs and the groups-first timing
   experiment; `docs/UX-NEXT-STEPS.md` updated to link this spec.

Flipping the default shell is a separate small PR after review.

## Out of scope

Cross-session or reload persistence, branching history trees, model routing or
keyword dispatch, a second model step, cache redesign, fine-grained
model-authored page edits, a Sources tab, and a one-tap phone back button.
The last two are easy to add later if the sketch or live use calls for them.

## Differences from the handoff plan

- Tab names: Listen / Charts / Read instead of Listening / Charts / Context.
- Empty tabs are grayed and inert instead of explaining themselves in a line.
- Fresh starts append instead of replacing forward entries.
- No progress banner once content is usable.
- Phone history lives in the hamburger menu, not in the dock.
- Cards are always one per row in the workspace.
- No new thread id is needed for restored branches, because the server already
  isolates them.
