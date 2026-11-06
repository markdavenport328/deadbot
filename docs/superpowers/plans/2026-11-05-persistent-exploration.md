# Persistent Exploration Workspace Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Put every answer in a three-tab workspace (Listen · Charts · Read) with a rail of revisitable request history, behind `?shell=workspace`, without disturbing today's shell or the player.

**Architecture:** Pure modules first: page-draft helpers, tab routing, a request client with abort and request IDs, and an exploration reducer. A new `WorkspaceShell` renders from them and reuses `App.tsx`'s group renderers through render props, so nothing imports `App.tsx`. Each visited exploration stays mounted (hidden when not shown), so disclosures, chart picks and stream-to-final reconciliation keep their state with no extra bookkeeping. PR 3 adds an optional `initial_tab` and a per-group `tab` to the model contract.

**Tech Stack:** React 18 + TypeScript + Vite + Vitest/Testing Library (`web/`), FastAPI + Pydantic + LangGraph (`deadbot/`), pytest.

**Spec:** [docs/superpowers/specs/2026-11-05-persistent-exploration-design.md](../specs/2026-11-05-persistent-exploration-design.md). Read it before starting any task. The UX sketch it links (`docs/plans/persistent-exploration/workspace-sketch.html`) shows every state.

## Global Constraints

- Read `AGENTS.md` first. Code guards facts and transport; the model owns judgment. Parse leniently, never drop the model's content, and stream must equal final.
- The old shell stays the default. The workspace renders only when `readShellMode()` returns `"workspace"`. Old-shell behavior and its tests stay unchanged.
- One `PlayerProvider` wraps both shells and is never remounted. History never reads, restores or changes playback or the queue.
- Tab ids are exactly `"listen" | "charts" | "read"`. Labels are exactly `Listen`, `Charts`, `Read`.
- Unit cards are always one per row in the workspace, including comparison groups.
- No "still composing" banner once the page has usable content. Unused tabs are grayed out and `aria-disabled` after the page finishes.
- There is no Sources tab. Sources sit at the foot of Read.
- Prompt and copy guidance is written as what to do. No caveat or data-hygiene copy in page text.
- Generated files (`web/openapi.json`, `web/src/generated/api.ts`) are only regenerated: `.venv/bin/python scripts/export_openapi.py`, then `npm --prefix web run gen:types`.
- Python tests run as `PYTHONPATH=. .venv/bin/python -m pytest …` from the worktree root.
- Web tests: `npm --prefix web test -- <pattern>` focused; `npm --prefix web test` and `npm --prefix web run build` before each PR is done.
- Agents commit locally and never push. Commit messages end with `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.

## Branches and PRs

Worktree: `/Users/markdavenport/Development/DeadBot/.claude/worktrees/app-update-planning-2a4e74`.

- **PR 1** (Tasks 1–5) on `claude/app-update-planning-2a4e74`, which already holds the spec. No visible change.
- **PR 2** (Tasks 6–10) on `claude/workspace-shell`, cut from PR 1's tip.
- **PR 3** (Tasks 11–14) on `claude/workspace-tabs-contract`, cut from PR 2's tip.

## File map

| File | Responsibility |
| --- | --- |
| `web/src/page-draft.ts` (new) | `RenderGroup`, `Draft`, `applyPageEvent`, `groupsOfResponse`, moved out of `App.tsx`; groups gain `tab`. |
| `web/src/tab-routing.ts` (new) | Tab vocabulary, lenient tab reading, fallback placement, routing, opening tab. |
| `web/src/ask-client.ts` (new) | Streaming and plain requests with `AbortSignal`, event dispatch, fixture replay. |
| `web/src/exploration-state.ts` (new) | Pure reducer: entries, cursor, pending request, view; request-context selector. |
| `web/src/shell-mode.ts` (new) | `?shell=` toggle remembered in `localStorage`. |
| `web/src/menu-slot.tsx` (new) | Lets the workspace put its history at the top of `SiteMenu` on phone. |
| `web/src/WorkspaceTabs.tsx` (new) | Tablist with preparing / new / unused states and keyboard support. |
| `web/src/ExplorationHistory.tsx` (new) | History list, ← →, pending/failed row, thread dividers, New chat. |
| `web/src/WorkspaceShell.tsx` (new) + `WorkspaceShell.css` | The workspace layout, wiring reducer + client + tabs + history. |
| `web/src/App.tsx` | Imports moved helpers; uses `ask-client`; extracts `PageGroups` and `SourcesFooter`; adds `WorkspaceApp`; `AppWithPlayer` picks the shell. |
| `web/src/SiteMenu.tsx` | Renders the menu slot above its links. |
| `web/src/stream-events.ts` | PR 3: `page_tab` event and `tab` on `group_open`. |
| `web/src/visual-fixtures.ts` | `msg-workspace` stream fixture (illustrative). |
| `deadbot/experience.py` | PR 3: `WorkspaceTab`, `workspace_tab()`, optional `ExperienceGroup.tab`, `ExperienceResponse.initial_tab`. |
| `deadbot/finish.py` | PR 3: `FinishPlan.initial_tab` (first field), `GroupPlan.tab` (first field), passed through resolution. |
| `deadbot/plan_stream.py` | PR 3: emits `page_tab`; adds `tab` to group payloads. |
| `deadbot/graph.py` | PR 3: a short THE WORKSPACE section in `SYSTEM_PROMPT`. |
| `scripts/trace_stream.py` | PR 3: marks for `page_tab` and the first block per tab. |

---

# PR 1 — client, state, routing (no visible change)

### Task 1: Move page-draft helpers out of App.tsx

**Files:**
- Create: `web/src/page-draft.ts`
- Modify: `web/src/App.tsx` (delete `RenderGroup`, `Draft`, `emptyGroup`, `applyPageEvent`, `groupsOfResponse` around lines 1034–1093; import them instead)
- Test: `web/src/page-draft.test.ts`

**Interfaces:**
- Produces: `RenderGroup = { title: string | null; lead: string | null; presentation: ExperienceGroup["presentation"]; criteria: string[]; blocks: ExperienceBlock[]; tab: WorkspaceTab | null }`, `Draft = { title: string; lead: string | null; groups: RenderGroup[] }`, `applyPageEvent(draft: Draft | null, event: PageEvent): Draft | null`, `groupsOfResponse(response: ExperienceResponse): RenderGroup[]`.
- Consumes: `WorkspaceTab` and `readTab` from Task 2. Write Task 2's `tab-routing.ts` vocabulary first if you take this task alone. Both tasks are small; do Task 2's Step 3 (`WorkspaceTab`, `readTab`) before this task's Step 3.

- [ ] **Step 1: Write the failing test**

```ts
// web/src/page-draft.test.ts
import { describe, expect, test } from "vitest";
import { applyPageEvent, groupsOfResponse } from "./page-draft";
import type { ExperienceResponse } from "./types";

const block = { type: "editorial", presentation: "narrative", items: [] } as never;

describe("applyPageEvent", () => {
  test("a block before its group_open gets a provisional group", () => {
    const draft = applyPageEvent(null, { type: "block", group_index: 0, block });
    expect(draft?.groups).toHaveLength(1);
    expect(draft?.groups[0].tab).toBeNull();
  });

  test("group_open fills the heading and reads the tab leniently", () => {
    const opened = applyPageEvent(null, { type: "group_open", index: 0, title: "T", lead: null, presentation: "collection", criteria: [], tab: "Listen" } as never);
    expect(opened?.groups[0]).toMatchObject({ title: "T", tab: "listen" });
    const unknown = applyPageEvent(null, { type: "group_open", index: 0, title: "T", lead: null, presentation: "collection", criteria: [], tab: "sideways" } as never);
    expect(unknown?.groups[0].tab).toBeNull();
  });

  test("page_reset clears, groups_reset keeps the head", () => {
    const head = applyPageEvent(null, { type: "page_head", title: "A", lead: null });
    expect(applyPageEvent(head, { type: "page_reset" })).toBeNull();
    expect(applyPageEvent({ ...head!, groups: [{ title: null, lead: null, presentation: "collection", criteria: [], blocks: [], tab: null }] }, { type: "groups_reset" })?.groups).toEqual([]);
  });
});

test("groupsOfResponse carries each group's tab when present", () => {
  const response = {
    schema_version: "2", thread_id: "t", title: "x", answer: "a", conversation: [], sources: [],
    blocks: [block, block],
    groups: [
      { title: null, lead: null, presentation: "collection", criteria: [], block_indexes: [0], tab: "charts" },
      { title: null, lead: null, presentation: "collection", criteria: [], block_indexes: [1] }
    ]
  } as unknown as ExperienceResponse;
  expect(groupsOfResponse(response).map((g) => g.tab)).toEqual(["charts", null]);
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `npm --prefix web test -- page-draft`
Expected: FAIL, cannot resolve `./page-draft`.

- [ ] **Step 3: Implement**

Create `web/src/page-draft.ts`. Move the five definitions from `App.tsx` verbatim, including their comments, and make these changes:
- Add `tab: WorkspaceTab | null` to `RenderGroup`. `emptyGroup()` returns `tab: null`.
- In `applyPageEvent`'s `group_open`/`group_close` branch, set `tab: readTab((event as { tab?: unknown }).tab) ?? groups[index].tab`.
- Add an explicit `if (event.type === "page_tab") return draft;` guard before the group handling. Write it as `if ((event as { type: string }).type === "page_tab") return draft;` so it compiles before PR 3 adds the type.
- In `groupsOfResponse`, add `tab: readTab((group as { tab?: unknown }).tab)`.

Export all five. In `App.tsx`, delete the moved code and add `import { applyPageEvent, groupsOfResponse, type Draft, type RenderGroup } from "./page-draft";`.

- [ ] **Step 4: Run tests**

Run: `npm --prefix web test -- page-draft` (PASS), then `npm --prefix web test` (all existing suites PASS).

- [ ] **Step 5: Commit**

```bash
git add web/src/page-draft.ts web/src/page-draft.test.ts web/src/App.tsx web/src/tab-routing.ts
git commit -m "Move page-draft helpers out of App.tsx; groups carry an optional tab"
```

### Task 2: Tab routing

**Files:**
- Create: `web/src/tab-routing.ts`
- Test: `web/src/tab-routing.test.ts`

**Interfaces:**
- Produces:
  - `type WorkspaceTab = "listen" | "charts" | "read"`
  - `const WORKSPACE_TABS: readonly { id: WorkspaceTab; label: string }[]` (Listen, Charts, Read, in that order)
  - `readTab(value: unknown): WorkspaceTab | null`
  - `fallbackTab(block: ExperienceBlock | undefined): WorkspaceTab`
  - `type RoutedPage = Record<WorkspaceTab, RenderGroup[]>`
  - `routeGroups(groups: RenderGroup[]): RoutedPage`
  - `openingTab(initial: WorkspaceTab | null, routed: RoutedPage): WorkspaceTab`
  - `tabsWithContent(routed: RoutedPage, answer: string | null): Set<WorkspaceTab>`

- [ ] **Step 1: Write the failing test**

```ts
// web/src/tab-routing.test.ts
import { expect, test } from "vitest";
import { fallbackTab, openingTab, readTab, routeGroups, tabsWithContent, WORKSPACE_TABS } from "./tab-routing";
import type { RenderGroup } from "./page-draft";

const g = (types: string[], tab: RenderGroup["tab"] = null, extra: Record<string, unknown> = {}): RenderGroup => ({
  title: null, lead: null, presentation: "collection", criteria: [], tab,
  blocks: types.map((type) => ({ type, ...extra }) as never)
});

test("labels and order", () => {
  expect(WORKSPACE_TABS.map((t) => t.label)).toEqual(["Listen", "Charts", "Read"]);
});

test("readTab is lenient", () => {
  expect(readTab("listen")).toBe("listen");
  expect(readTab(" Listening ")).toBe("listen");
  expect(readTab("chart")).toBe("charts");
  expect(readTab("context")).toBe("read");
  expect(readTab("sideways")).toBeNull();
  expect(readTab(3)).toBeNull();
});

test.each([
  ["show_unit", "listen"], ["performance_unit", "listen"], ["album_unit", "listen"], ["song_overview", "listen"],
  ["show_selection", "listen"], ["listening_hero", "listen"], ["version_strip", "listen"], ["media_link", "listen"],
  ["data_chart", "charts"], ["grid", "charts"],
  ["editorial", "read"], ["pull_quote", "read"], ["person_roster", "read"], ["era_unit", "read"], ["gap_state", "read"],
  ["something_new", "read"]
])("fallback for %s is %s", (type, tab) => {
  expect(fallbackTab({ type } as never)).toBe(tab);
});

test("entity cards go by entity type", () => {
  expect(fallbackTab({ type: "entity_card", entity_type: "show" } as never)).toBe("listen");
  expect(fallbackTab({ type: "entity_card", entity_type: "performance" } as never)).toBe("listen");
  expect(fallbackTab({ type: "entity_card", entity_type: "song" } as never)).toBe("read");
  expect(fallbackTab(undefined)).toBe("read");
});

test("a group goes whole by its own tab, else by its first block, keeping order", () => {
  const routed = routeGroups([g(["editorial", "show_unit"]), g(["song_overview"], "charts"), g(["show_unit"]), g(["data_chart"])]);
  expect(routed.read).toHaveLength(1);
  expect(routed.read[0].blocks).toHaveLength(2);
  expect(routed.charts.map((x) => x.blocks[0].type)).toEqual(["song_overview", "data_chart"]);
  expect(routed.listen).toHaveLength(1);
});

test("opening tab: the model's choice, else Listen when it has groups, else Read", () => {
  const withListen = routeGroups([g(["show_unit"])]);
  expect(openingTab("charts", withListen)).toBe("charts");
  expect(openingTab(null, withListen)).toBe("listen");
  expect(openingTab(null, routeGroups([g(["editorial"])]))).toBe("read");
});

test("tabs with content count the short answer for Read", () => {
  expect([...tabsWithContent(routeGroups([]), "Yes.")]).toEqual(["read"]);
  expect(tabsWithContent(routeGroups([g(["grid"])]), null).has("charts")).toBe(true);
});
```

- [ ] **Step 2: Run to verify failure**

Run: `npm --prefix web test -- tab-routing`. Expected: FAIL, module not found.

- [ ] **Step 3: Implement**

```ts
// web/src/tab-routing.ts
// Where each part of a page lives in the workspace. The model names a tab per
// group; this file reads that name leniently and, when a group has none (an
// older response, a cached one, a skipped field), places the whole group by
// its first block. This is compatibility, not routing: the model's choice wins.
import type { ExperienceBlock } from "./types";
import type { RenderGroup } from "./page-draft";

export type WorkspaceTab = "listen" | "charts" | "read";

export const WORKSPACE_TABS: readonly { id: WorkspaceTab; label: string }[] = [
  { id: "listen", label: "Listen" },
  { id: "charts", label: "Charts" },
  { id: "read", label: "Read" }
];

const NAMES: Record<string, WorkspaceTab> = {
  listen: "listen", listening: "listen", hear: "listen",
  charts: "charts", chart: "charts",
  read: "read", context: "read", story: "read", info: "read"
};

export function readTab(value: unknown): WorkspaceTab | null {
  return typeof value === "string" ? NAMES[value.trim().toLowerCase()] ?? null : null;
}

const LISTEN = new Set(["show_unit", "performance_unit", "album_unit", "song_overview", "show_selection", "listening_hero", "version_strip", "media_link"]);
const CHARTS = new Set(["data_chart", "grid"]);

export function fallbackTab(block: ExperienceBlock | undefined): WorkspaceTab {
  if (!block) return "read";
  if (block.type === "entity_card") return block.entity_type === "song" ? "read" : "listen";
  if (LISTEN.has(block.type)) return "listen";
  if (CHARTS.has(block.type)) return "charts";
  return "read";
}

export type RoutedPage = Record<WorkspaceTab, RenderGroup[]>;

export function routeGroups(groups: RenderGroup[]): RoutedPage {
  const routed: RoutedPage = { listen: [], charts: [], read: [] };
  for (const group of groups) routed[group.tab ?? fallbackTab(group.blocks[0])].push(group);
  return routed;
}

export function openingTab(initial: WorkspaceTab | null, routed: RoutedPage): WorkspaceTab {
  if (initial) return initial;
  return routed.listen.length > 0 ? "listen" : "read";
}

export function tabsWithContent(routed: RoutedPage, answer: string | null): Set<WorkspaceTab> {
  const tabs = new Set<WorkspaceTab>();
  for (const { id } of WORKSPACE_TABS) if (routed[id].length > 0) tabs.add(id);
  if (answer && answer.trim()) tabs.add("read");
  return tabs;
}
```

- [ ] **Step 4: Run tests**

Run: `npm --prefix web test -- tab-routing page-draft`. Expected: PASS.

- [ ] **Step 5: Commit** (with Task 1 if done together)

```bash
git add web/src/tab-routing.ts web/src/tab-routing.test.ts
git commit -m "Tab routing: lenient tab names and whole-group fallback placement"
```

### Task 3: Request client with abort and request ids

**Files:**
- Create: `web/src/ask-client.ts`
- Modify: `web/src/App.tsx` (delete `StreamHandlers`, `PAGE_EVENT_TYPES`, `dispatchStreamEvent`, the inner `askStreaming`/`askPlain`, and the body of `replayStreamFixture`; call the module instead)
- Test: `web/src/ask-client.test.ts`

**Interfaces:**
- Produces:
  - `const ASK_ERROR = "Deadbot could not answer just now. Try again, or rephrase the question."`
  - `type StreamHandlers = { onStatus(text: string): void; onAnswer(text: string): void; onPage(event: PageEvent): void; onResponse(response: ExperienceResponse): void }`
  - `dispatchStreamEvent(event: StreamEvent, handlers: StreamHandlers): void` (throws on `error`)
  - `askStreaming(body: string, handlers: Omit<StreamHandlers, "onResponse">, signal?: AbortSignal): Promise<ExperienceResponse | null>`. `null` means use `askPlain`. A started stream that ends without `response` throws `"The connection closed before Deadbot finished the page. Please ask again."`
  - `askPlain(body: string, signal?: AbortSignal): Promise<ExperienceResponse>`
  - `replayStreamEvents(events: StreamEvent[], handlers: StreamHandlers, signal?: AbortSignal): Promise<void>`, with today's delays (`block` 600 ms, `answer` 40 ms, others 300 ms). It returns quietly once `signal.aborted`.
  - `isAbort(error: unknown): boolean` (true for a `DOMException` named `AbortError`)

- [ ] **Step 1: Write the failing test**

```ts
// web/src/ask-client.test.ts
import { afterEach, expect, test, vi } from "vitest";
import { askPlain, askStreaming, isAbort, replayStreamEvents } from "./ask-client";

const response = { schema_version: "2", thread_id: "t", title: "T", answer: "A", conversation: [], blocks: [], groups: [], sources: [] };

function streamOf(lines: string[], { status = 200 } = {}) {
  const text = lines.join("\n");
  const body = new ReadableStream({
    start(controller) {
      // Split mid-line to prove buffering.
      const bytes = new TextEncoder().encode(text);
      controller.enqueue(bytes.slice(0, 7));
      controller.enqueue(bytes.slice(7));
      controller.close();
    }
  });
  return new Response(body, { status });
}

afterEach(() => vi.unstubAllGlobals());

test("streams statuses, answer and page events, then returns the response", async () => {
  vi.stubGlobal("fetch", vi.fn(async () => streamOf([
    JSON.stringify({ type: "status", text: "Looking" }),
    JSON.stringify({ type: "answer", text: "Yes" }),
    JSON.stringify({ type: "page_head", title: "T", lead: null }),
    JSON.stringify({ type: "response", response })
  ])));
  const seen: string[] = [];
  const result = await askStreaming("{}", {
    onStatus: (t) => seen.push(`s:${t}`), onAnswer: (t) => seen.push(`a:${t}`), onPage: (e) => seen.push(`p:${e.type}`)
  });
  expect(seen).toEqual(["s:Looking", "a:Yes", "p:page_head"]);
  expect(result?.title).toBe("T");
});

test("404 means no stream: the caller falls back", async () => {
  vi.stubGlobal("fetch", vi.fn(async () => new Response("", { status: 404 })));
  expect(await askStreaming("{}", { onStatus() {}, onAnswer() {}, onPage() {} })).toBeNull();
});

test("a stream that ends without its response fails instead of re-asking", async () => {
  vi.stubGlobal("fetch", vi.fn(async () => streamOf([JSON.stringify({ type: "status", text: "x" })])));
  await expect(askStreaming("{}", { onStatus() {}, onAnswer() {}, onPage() {} })).rejects.toThrow("connection closed");
});

test("an error event throws its detail", async () => {
  vi.stubGlobal("fetch", vi.fn(async () => streamOf([JSON.stringify({ type: "error", detail: "Nope" })])));
  await expect(askStreaming("{}", { onStatus() {}, onAnswer() {}, onPage() {} })).rejects.toThrow("Nope");
});

test("the signal reaches fetch, and an abort is recognisable", async () => {
  const controller = new AbortController();
  const fetchMock = vi.fn(async (_url: unknown, init?: RequestInit) => {
    expect(init?.signal).toBe(controller.signal);
    throw new DOMException("aborted", "AbortError");
  });
  vi.stubGlobal("fetch", fetchMock);
  controller.abort();
  const error = await askPlain("{}", controller.signal).catch((e) => e);
  expect(isAbort(error)).toBe(true);
});

test("replay stops once aborted", async () => {
  vi.useFakeTimers();
  const controller = new AbortController();
  const statuses: string[] = [];
  const done = replayStreamEvents(
    [{ type: "status", text: "one" }, { type: "status", text: "two" }],
    { onStatus: (t) => statuses.push(t), onAnswer() {}, onPage() {}, onResponse() {} },
    controller.signal
  );
  await vi.advanceTimersByTimeAsync(300);
  controller.abort();
  await vi.advanceTimersByTimeAsync(1000);
  await done;
  expect(statuses).toEqual(["one"]);
  vi.useRealTimers();
});
```

- [ ] **Step 2: Run to verify failure**

Run: `npm --prefix web test -- ask-client`. Expected: FAIL, module not found.

- [ ] **Step 3: Implement**

Move the code from `App.tsx` into `web/src/ask-client.ts` with its comments, adding `signal` to both `fetch` calls (`{ method: "POST", headers: { "Content-Type": "application/json" }, body, signal }`). Replace the three copies of the error string with `ASK_ERROR`. Write `replayStreamEvents` from the loop in `App.tsx`'s `replayStreamFixture`, without the React state: `for (const event of events) { if (signal?.aborted) return; await delay(ms); if (signal?.aborted) return; dispatchStreamEvent(event, handlers); }`. Add:

```ts
export function isAbort(error: unknown): boolean {
  return error instanceof DOMException && error.name === "AbortError";
}
```

In `App.tsx`:
- `import { askPlain, askStreaming, dispatchStreamEvent, replayStreamEvents } from "./ask-client";`
- `askQuestion` calls `askStreaming(body, {...})` and `askPlain(body)` as before.
- `replayStreamFixture` becomes `const events = await loadRequestedStreamEvents(); if (!events) return; await replayStreamEvents(events, {...same handlers as today...});`.

The old shell never passes a signal, so its behavior is unchanged.

- [ ] **Step 4: Run tests**

Run: `npm --prefix web test -- ask-client` (PASS), then `npm --prefix web test` (PASS; `App.notebook.test.tsx` covers the old path).

- [ ] **Step 5: Commit**

```bash
git add web/src/ask-client.ts web/src/ask-client.test.ts web/src/App.tsx
git commit -m "Request client module: streaming and plain asks take an AbortSignal"
```

### Task 4: Exploration reducer

**Files:**
- Create: `web/src/exploration-state.ts`
- Test: `web/src/exploration-state.test.ts`

**Interfaces:**
- Consumes: `Draft`, `applyPageEvent` (Task 1); `WorkspaceTab`, `routeGroups`, `openingTab` (Task 2); `PageEvent` from `stream-events.ts`; `AskFocus`, `ExperienceResponse` from `types.ts`.
- Produces (exact):

```ts
export type RequestSource = "typed" | "chip";
export type EntryView = { tab: WorkspaceTab | null; scroll: Partial<Record<WorkspaceTab, number>> };
export type Entry = {
  id: string;             // the request id that produced it
  parentId: string | null;
  root: boolean;
  request: string;
  source: RequestSource;
  focus: AskFocus | null;
  threadId: string;
  response: ExperienceResponse;
  view: EntryView;
};
export type Pending = {
  requestId: string;
  baseEntryId: string | null; // null: a fresh start
  question: string;
  source: RequestSource;
  focus: AskFocus | null;
  threadId: string;
  statuses: string[];
  answer: string | null;
  draft: Draft | null;
  initialTab: WorkspaceTab | null;
  view: EntryView;
  interacted: boolean;
  error: string | null;
};
export type ExplorationState = { entries: Entry[]; cursor: number; pending: Pending | null; startView: boolean };
export type ExplorationAction =
  | { type: "submit"; requestId: string; question: string; source: RequestSource; focus: AskFocus | null; fresh: boolean; threadId: string }
  | { type: "status"; requestId: string; text: string }
  | { type: "answer"; requestId: string; text: string }
  | { type: "page"; requestId: string; event: PageEvent }
  | { type: "initialTab"; requestId: string; tab: WorkspaceTab }
  | { type: "complete"; requestId: string; response: ExperienceResponse }
  | { type: "fail"; requestId: string; message: string }
  | { type: "cancel" }
  | { type: "dismiss" }
  | { type: "navigate"; index: number }
  | { type: "newChat" }
  | { type: "view"; patch: Partial<EntryView>; interacted?: boolean };
export const initialExploration: ExplorationState;
export function explorationReducer(state: ExplorationState, action: ExplorationAction): ExplorationState;
export function currentEntry(state: ExplorationState): Entry | null;
export function isAsking(state: ExplorationState): boolean;           // pending && !error
export function pendingHasContent(pending: Pending): boolean;          // answer text or any draft block
export function requestContext(state: ExplorationState, fresh: boolean): { conversation: ExperienceResponse["conversation"]; notebook: string | null; threadId: string | null };
export type Visible =
  | { kind: "start" }
  | { kind: "working"; pending: Pending }                  // fresh start, nothing to show yet
  | { kind: "held"; entry: Entry; pending: Pending }       // follow-up, previous page held
  | { kind: "draft"; pending: Pending }                    // streamed content is showing
  | { kind: "failed"; entry: Entry | null; pending: Pending }
  | { kind: "entry"; entry: Entry };
export function visible(state: ExplorationState): Visible;
```

Rules the reducer implements (from the spec):
- `submit` is ignored while `isAsking`. Fresh: `baseEntryId: null`. Otherwise `baseEntryId` = current entry's id (or null when there is none or `startView`). It clears `startView`.
- `status`/`answer`/`page`/`initialTab`/`complete`/`fail` with a `requestId` other than `pending?.requestId` return `state` unchanged (same object).
- `initialTab` sets `pending.initialTab`, and also `pending.view.tab` unless `interacted`.
- On the first `answer` or `page` that gives the pending request content, if `view.tab` is null and not `interacted`, set `view.tab = openingTab(pending.initialTab, routeGroups(draft.groups))`. Once set, later events never change it.
- `complete`:
  - Build the entry: `id = requestId`, `parentId = baseEntryId`, `root = baseEntryId === null`, and `view.tab` = `pending.view.tab ?? openingTab(readTab(response.initial_tab), routeGroups(groupsOfResponse(response)))`. `response.initial_tab` is read as `(response as { initial_tab?: unknown }).initial_tab` until PR 3 types it.
  - A root entry is appended at the end. A follow-up drops entries after its base (`entries.slice(0, baseIndex + 1)`), then appends.
  - Cursor moves to the new entry, and `pending` becomes null.
- `fail` sets `pending.error` and leaves entries alone. `dismiss` clears a failed pending. `cancel` clears any pending.
- `navigate` clears `pending` (the shell aborts the fetch first), sets the cursor if the index is in range, and clears `startView`.
- `newChat` is ignored while asking; otherwise it sets `startView: true` and clears a failed pending.
- `view` patches `pending.view` while `visible()` is `draft`, otherwise the current entry's view (immutably). With `interacted: true`, it also marks `pending.interacted` whenever a pending request exists.
- `requestContext(state, fresh)`: fresh, or no current entry, or `startView` → `{ conversation: [], notebook: null, threadId: null }` (the caller makes a new thread id). Otherwise the current entry's `response.conversation`, `response.notebook ?? null`, and `threadId`.
- `visible()`: no pending → `startView` or no entries → `start`, else `entry`. Pending with error → `failed` (entry = base entry or null). Pending with content → `draft`. Pending without content → `held` when its base entry exists, else `working`.

- [ ] **Step 1: Write the failing test**

```ts
// web/src/exploration-state.test.ts
import { describe, expect, test } from "vitest";
import { explorationReducer as reduce, initialExploration, requestContext, visible, isAsking, type ExplorationAction, type ExplorationState } from "./exploration-state";
import type { ExperienceResponse } from "./types";

const reply = (title: string, notebook: string | null, extra: Record<string, unknown> = {}) => ({
  schema_version: "2", thread_id: "t", title, answer: `${title} answer`, body_lead: null, mode: "answer",
  conversation: [{ role: "user", text: title }, { role: "assistant", text: `${title} answer` }],
  blocks: [{ type: "show_unit" }], groups: [{ title: null, lead: null, presentation: "collection", criteria: [], block_indexes: [0] }],
  sources: [], notebook, ...extra
}) as unknown as ExperienceResponse;

function run(state: ExplorationState, ...actions: ExplorationAction[]) {
  return actions.reduce(reduce, state);
}
function ask(state: ExplorationState, id: string, title: string, { fresh = false, notebook = `nb-${id}` } = {}) {
  return run(state,
    { type: "submit", requestId: id, question: title, source: "typed", focus: null, fresh, threadId: `th-${id}` },
    { type: "complete", requestId: id, response: reply(title, notebook) });
}

test("two asks make two entries; local view changes make none", () => {
  let s = ask(initialExploration, "r1", "MSG", { fresh: true });
  s = ask(s, "r2", "Late 80s");
  for (let i = 0; i < 10; i += 1) s = reduce(s, { type: "view", patch: { tab: i % 2 ? "charts" : "read", scroll: { read: i } }, interacted: true });
  expect(s.entries.map((e) => e.request)).toEqual(["MSG", "Late 80s"]);
  expect(s.cursor).toBe(1);
});

test("a follow-up from entry 1 sends entry 1's conversation and notebook", () => {
  let s = ask(initialExploration, "r1", "MSG", { fresh: true });
  s = ask(s, "r2", "Late 80s");
  s = reduce(s, { type: "navigate", index: 0 });
  const ctx = requestContext(s, false);
  expect(ctx.notebook).toBe("nb-r1");
  expect(ctx.conversation.map((t) => t.text)).toEqual(["MSG", "MSG answer"]);
  expect(ctx.threadId).toBe("th-r1");
  expect(requestContext(s, true)).toEqual({ conversation: [], notebook: null, threadId: null });
});

describe("branching", () => {
  const twoDeep = () => reduce(ask(ask(initialExploration, "r1", "MSG", { fresh: true }), "r2", "Late 80s"), { type: "navigate", index: 0 });

  test("a successful follow-up from an old entry replaces what came after it", () => {
    const s = ask(twoDeep(), "r3", "Guests");
    expect(s.entries.map((e) => e.request)).toEqual(["MSG", "Guests"]);
    expect(s.entries[1].parentId).toBe("r1");
  });

  test("a successful fresh start from an old entry appends and drops nothing", () => {
    const s = ask(twoDeep(), "r3", "Birthday", { fresh: true });
    expect(s.entries.map((e) => e.request)).toEqual(["MSG", "Late 80s", "Birthday"]);
    expect(s.entries[2].root).toBe(true);
  });

  test("failure and cancel leave history alone", () => {
    let s = run(twoDeep(), { type: "submit", requestId: "r3", question: "x", source: "typed", focus: null, fresh: false, threadId: "t" }, { type: "fail", requestId: "r3", message: "boom" });
    expect(s.entries).toHaveLength(2);
    expect(visible(s).kind).toBe("failed");
    s = run(s, { type: "dismiss" });
    expect(s.pending).toBeNull();
    s = run(s, { type: "submit", requestId: "r4", question: "y", source: "typed", focus: null, fresh: false, threadId: "t" }, { type: "cancel" });
    expect(s.entries).toHaveLength(2);
  });
});

test("events from a stale request are ignored", () => {
  let s = run(ask(initialExploration, "r1", "MSG", { fresh: true }),
    { type: "submit", requestId: "r2", question: "x", source: "typed", focus: null, fresh: false, threadId: "t" });
  s = reduce(s, { type: "navigate", index: 0 });
  const before = s;
  expect(reduce(s, { type: "answer", requestId: "r2", text: "late" })).toBe(before);
  expect(reduce(s, { type: "complete", requestId: "r2", response: reply("late", null) })).toBe(before);
});

test("only one request at a time", () => {
  const s = run(initialExploration, { type: "submit", requestId: "r1", question: "a", source: "typed", focus: null, fresh: true, threadId: "t" });
  expect(isAsking(s)).toBe(true);
  expect(reduce(s, { type: "submit", requestId: "r2", question: "b", source: "typed", focus: null, fresh: true, threadId: "t" })).toBe(s);
});

describe("opening tab and the visitor's focus", () => {
  const started = () => run(ask(initialExploration, "r1", "MSG", { fresh: true }),
    { type: "submit", requestId: "r2", question: "x", source: "chip", focus: null, fresh: false, threadId: "t" });

  test("a follow-up holds the previous page until content arrives", () => {
    let s = started();
    expect(visible(s).kind).toBe("held");
    s = reduce(s, { type: "status", requestId: "r2", text: "Looking" });
    expect(visible(s).kind).toBe("held");
    s = reduce(s, { type: "answer", requestId: "r2", text: "Yes" });
    expect(visible(s).kind).toBe("draft");
  });

  test("the model's tab opens unless the visitor has acted", () => {
    let s = run(started(), { type: "initialTab", requestId: "r2", tab: "listen" }, { type: "answer", requestId: "r2", text: "Yes" });
    expect(s.pending?.view.tab).toBe("listen");
    s = reduce(s, { type: "view", patch: { tab: "charts" }, interacted: true });
    s = reduce(s, { type: "initialTab", requestId: "r2", tab: "read" });
    expect(s.pending?.view.tab).toBe("charts");
    s = reduce(s, { type: "complete", requestId: "r2", response: reply("x", null) });
    expect(s.entries[s.cursor].view.tab).toBe("charts");
  });

  test("without a model choice the first content picks once and then stays", () => {
    let s = run(started(), { type: "answer", requestId: "r2", text: "Yes" });
    expect(s.pending?.view.tab).toBe("read");
    s = reduce(s, { type: "page", requestId: "r2", event: { type: "block", group_index: 0, block: { type: "show_unit" } as never } });
    expect(s.pending?.view.tab).toBe("read");
  });
});

test("new chat shows the start view and keeps history", () => {
  const s = reduce(ask(initialExploration, "r1", "MSG", { fresh: true }), { type: "newChat" });
  expect(visible(s).kind).toBe("start");
  expect(s.entries).toHaveLength(1);
  expect(requestContext(s, false).notebook).toBeNull();
});
```

- [ ] **Step 2: Run to verify failure**

Run: `npm --prefix web test -- exploration-state`. Expected: FAIL, module not found.

- [ ] **Step 3: Implement** `web/src/exploration-state.ts` to the interface and rules above. Use a short header comment in the style of `research-notebook.ts`: what the reducer holds, and that player state never enters it.

- [ ] **Step 4: Run tests**

Run: `npm --prefix web test -- exploration-state`. Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add web/src/exploration-state.ts web/src/exploration-state.test.ts
git commit -m "Exploration reducer: model-turn history, linear follow-ups, appended fresh starts"
```

### Task 5: Server regression test for restored branches

**Files:**
- Test: `tests/test_api_notebook.py` (append)

- [ ] **Step 1: Write the test**

```python
def test_a_follow_up_from_an_earlier_page_runs_on_an_isolated_thread():
    # The workspace can resend an older entry's transcript on the same
    # thread_id. The API must not replay a warm checkpoint holding later turns.
    _, token = _token((EUROPE, EUROPE_ANSWER, LYCEUM))
    agent = FakeAgent(turn("And Morning Dew?", "It closed the run.", []))
    client = _client(agent)
    client.post("/api/experience", json={"question": "And Morning Dew?", "thread_id": "browser-1", "conversation": FIRST_EXCHANGE, "notebook": token})
    client.post("/api/experience", json={"question": "And Morning Dew?", "thread_id": "browser-1", "conversation": FIRST_EXCHANGE})
    invoked = [config["configurable"]["thread_id"] for _, config in agent.calls]
    assert len(invoked) == 2
    assert all(thread.startswith("browser-1:request:") for thread in invoked)
    assert invoked[0] != invoked[1]
```

- [ ] **Step 2: Run it**

Run: `PYTHONPATH=. .venv/bin/python -m pytest tests/test_api_notebook.py -k isolated -v`
Expected: PASS. This pins existing behavior. If it fails, stop and report: the spec's assumption is wrong and the plan needs a fresh-thread step.

- [ ] **Step 3: Run PR 1's full checks, then commit**

Run: `npm --prefix web test && npm --prefix web run build && PYTHONPATH=. .venv/bin/python -m pytest tests/test_api_notebook.py tests/test_plan_stream.py -q`

```bash
git add tests/test_api_notebook.py
git commit -m "Pin isolated invocation threads for follow-ups sent with a transcript"
```

---

# PR 2 — the workspace shell (behind `?shell=workspace`)

Before Task 6: `git -C /Users/markdavenport/Development/DeadBot/.claude/worktrees/app-update-planning-2a4e74 checkout -b claude/workspace-shell`.

### Task 6: Shell toggle and menu slot

**Files:**
- Create: `web/src/shell-mode.ts`, `web/src/menu-slot.tsx`
- Modify: `web/src/SiteMenu.tsx` (render `<MenuSlotOutlet />` at the top of the panel, above `<nav aria-label="Site">`)
- Test: `web/src/shell-mode.test.ts`, `web/src/SiteMenu.test.tsx` (append)

**Interfaces:**
- Produces:
  - `type ShellMode = "classic" | "workspace"`
  - `readShellMode(search?: string): ShellMode`. `?shell=workspace|classic` wins and is remembered under `localStorage["deadbot-shell"]`; otherwise the stored value; otherwise `"classic"`. Storage errors fall back to `"classic"`.
  - `MenuSlotProvider({ children })`, `useMenuSlot(node: ReactNode | null): void` (sets the slot while mounted and clears it on unmount), `MenuSlotOutlet()` (renders the node or nothing), and `useCloseSiteMenu(): () => void` (lets slot content close the menu after navigating). `SiteMenu` provides the close callback through the same context.

- [ ] **Step 1: Write the failing tests**

```ts
// web/src/shell-mode.test.ts
import { beforeEach, expect, test } from "vitest";
import { readShellMode } from "./shell-mode";

beforeEach(() => window.localStorage.clear());

test("classic by default", () => expect(readShellMode("")).toBe("classic"));
test("the query opts in and is remembered", () => {
  expect(readShellMode("?shell=workspace")).toBe("workspace");
  expect(readShellMode("")).toBe("workspace");
  expect(readShellMode("?shell=classic")).toBe("classic");
  expect(readShellMode("")).toBe("classic");
});
test("unknown values are ignored", () => expect(readShellMode("?shell=fancy")).toBe("classic"));
```

Append to `SiteMenu.test.tsx`: render `<MenuSlotProvider><Probe /><SiteMenu /></MenuSlotProvider>`, where `Probe` calls `useMenuSlot(<p>History here</p>)`. Open the menu and assert the text appears inside `#site-menu` before the "About Deadbot" link (`compareDocumentPosition`). Without a provider, `SiteMenu` still renders (the existing tests prove it).

- [ ] **Step 2: Run to verify failure.** `npm --prefix web test -- shell-mode SiteMenu`: FAIL.

- [ ] **Step 3: Implement.** Use `useState` in the provider holding `{ node, setNode }` and a `useContext` with a no-op default, so `SiteMenu` works outside the provider. `useMenuSlot` uses `useEffect(() => { setNode(node); return () => setNode(null); }, [node])`.

- [ ] **Step 4: Run tests.** PASS.

- [ ] **Step 5: Commit**

```bash
git add web/src/shell-mode.ts web/src/shell-mode.test.ts web/src/menu-slot.tsx web/src/SiteMenu.tsx web/src/SiteMenu.test.tsx
git commit -m "Shell toggle (?shell=workspace) and a menu slot for workspace history"
```

### Task 7: WorkspaceTabs

**Files:**
- Create: `web/src/WorkspaceTabs.tsx`
- Test: `web/src/WorkspaceTabs.test.tsx`

**Interfaces:**
- Consumes: `WORKSPACE_TABS`, `WorkspaceTab`.
- Produces: `type TabState = "ready" | "preparing" | "new" | "unused"`, and `WorkspaceTabs({ active, states, onSelect, idPrefix }: { active: WorkspaceTab | null; states: Record<WorkspaceTab, TabState>; onSelect(tab: WorkspaceTab): void; idPrefix: string })`. It renders `<div role="tablist" aria-label="Views of this exploration">`. Each tab is a `<button role="tab" id={`${idPrefix}-tab-${id}`} aria-controls={`${idPrefix}-panel-${id}`} aria-selected tabIndex>` with its label plus a quiet state mark: "preparing" as text, "new" as a dot with sr-only "has new content". An `unused` tab gets `aria-disabled="true"` and the class `unused`, and clicks do nothing. Arrow Left/Right/Home/End move focus and selection, skipping unused tabs (the WAI-ARIA automatic-activation pattern). Only the active tab has `tabIndex=0`.

- [ ] **Step 1: Write the failing test**

```tsx
// web/src/WorkspaceTabs.test.tsx
import { fireEvent, render, screen } from "@testing-library/react";
import { expect, test, vi } from "vitest";
import { WorkspaceTabs } from "./WorkspaceTabs";

const states = { listen: "ready", charts: "unused", read: "new" } as const;

test("labels, selection and unused tabs", () => {
  const onSelect = vi.fn();
  render(<WorkspaceTabs active="listen" states={states} onSelect={onSelect} idPrefix="x" />);
  expect(screen.getAllByRole("tab").map((t) => t.textContent?.replace(/has new content/, "").trim())).toEqual(["Listen", "Charts", "Read"]);
  expect(screen.getByRole("tab", { name: /Listen/ })).toHaveAttribute("aria-selected", "true");
  fireEvent.click(screen.getByRole("tab", { name: /Charts/ }));
  expect(onSelect).not.toHaveBeenCalled();
  expect(screen.getByRole("tab", { name: /Charts/ })).toHaveAttribute("aria-disabled", "true");
});

test("arrow keys skip unused tabs", () => {
  const onSelect = vi.fn();
  render(<WorkspaceTabs active="listen" states={states} onSelect={onSelect} idPrefix="x" />);
  fireEvent.keyDown(screen.getByRole("tab", { name: /Listen/ }), { key: "ArrowRight" });
  expect(onSelect).toHaveBeenCalledWith("read");
});

test("preparing tabs say so", () => {
  render(<WorkspaceTabs active={null} states={{ listen: "preparing", charts: "preparing", read: "new" }} onSelect={() => {}} idPrefix="x" />);
  expect(screen.getByRole("tab", { name: /Listen/ })).toHaveTextContent("preparing");
});
```

- [ ] **Step 2: Run, verify failure.** `npm --prefix web test -- WorkspaceTabs`
- [ ] **Step 3: Implement** to the interface. Styles go in `WorkspaceShell.css` (Task 9): an underline on the selected tab, the unused tab in a muted color with `cursor: default`, and the bar `position: sticky; top: 0`.
- [ ] **Step 4: Run, PASS.**
- [ ] **Step 5: Commit** `git commit -m "Workspace tablist: preparing, new and unused states"`

### Task 8: ExplorationHistory

**Files:**
- Create: `web/src/ExplorationHistory.tsx`
- Test: `web/src/ExplorationHistory.test.tsx`

**Interfaces:**
- Consumes: `ExplorationState`, `Entry`, `Pending` (Task 4).
- Produces: `ExplorationHistory({ state, onNavigate, onStop, onRetry, onNewChat, headingId }: { state: ExplorationState; onNavigate(index: number): void; onStop(): void; onRetry(): void; onNewChat(): void; headingId: string })`. It renders:
  - The heading "Your explorations" with ← → buttons ("Previous exploration" / "Next exploration"), disabled at the ends or while `startView` for ←.
  - A `<ol>` of entries. Each row is a button showing the request text, with a small line reading `n · Typed` or `n · Chip`. The current entry gets `aria-current="true"` (unless `startView`); entries after the cursor get the class `ahead`. Before each `root` entry except the first, an `<li className="thread-divider">New thread</li>`.
  - A pending row: "Asking · {question}" with a Stop button. A failed pending row instead reads "Didn't finish · {question}" with a Retry button.
  - A "New chat" button, disabled while asking.

- [ ] **Step 1: Write the failing test.** Build states with the reducer from Task 4 (two fresh-thread asks and one follow-up, then a failed submit). Assert:
  - the row texts and order;
  - one "New thread" divider before the second root;
  - `aria-current` on the cursor row;
  - clicking row 1 calls `onNavigate(0)`;
  - ← is disabled at index 0;
  - the failed row shows Retry and calls `onRetry`;
  - while asking, the row shows Stop and New chat is disabled.

```tsx
// web/src/ExplorationHistory.test.tsx (skeleton — fill every assertion listed above)
import { fireEvent, render, screen } from "@testing-library/react";
import { expect, test, vi } from "vitest";
import { ExplorationHistory } from "./ExplorationHistory";
import { explorationReducer as reduce, initialExploration } from "./exploration-state";

const reply = (title: string) => ({ schema_version: "2", thread_id: "t", title, answer: "a", conversation: [], blocks: [], groups: [], sources: [] }) as never;
const ask = (s: typeof initialExploration, id: string, q: string, fresh: boolean) =>
  reduce(reduce(s, { type: "submit", requestId: id, question: q, source: fresh ? "typed" : "chip", focus: null, fresh, threadId: id }), { type: "complete", requestId: id, response: reply(q) });

test("rows, dividers, current and navigation", () => {
  let s = ask(initialExploration, "r1", "MSG history", true);
  s = ask(s, "r2", "Late 80s", false);
  s = ask(s, "r3", "Garcia birthday", true);
  const onNavigate = vi.fn();
  render(<ExplorationHistory state={s} onNavigate={onNavigate} onStop={() => {}} onRetry={() => {}} onNewChat={() => {}} headingId="h" />);
  expect(screen.getAllByText("New thread")).toHaveLength(1);
  expect(screen.getByRole("button", { name: /Garcia birthday/ })).toHaveAttribute("aria-current", "true");
  fireEvent.click(screen.getByRole("button", { name: /MSG history/ }));
  expect(onNavigate).toHaveBeenCalledWith(0);
});
```

- [ ] **Step 2: Run, verify failure.**
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run, PASS.**
- [ ] **Step 5: Commit** `git commit -m "Exploration history list with back/forward, pending and failed rows"`

### Task 9: WorkspaceShell

**Files:**
- Create: `web/src/WorkspaceShell.tsx`, `web/src/WorkspaceShell.css`
- Modify: `web/src/App.tsx`:
  - Extract `PageGroups({ groups, sources, composing, onFollowUp })`: the body of `ComposedPage` from `bodyGroups.map` through the composing note, with the hero handling kept as it is. `ComposedPage` calls it, so the old shell renders identically.
  - Extract `SourcesFooter({ groups, sources })`: the `sources-footer` block.
  - Export `PageGroups`, `SourcesFooter` and `renderInline` for use in `WorkspaceApp` (same file, so no circular import).
- Test: `web/src/WorkspaceShell.test.tsx`

**Interfaces:**
- Consumes: Tasks 1–8.
- Produces:

```ts
export type PageParts = {
  groups(groups: RenderGroup[], composing: boolean, onFollowUp: FollowUp): ReactNode;
  sources(groups: RenderGroup[], sources: SourceReference[]): ReactNode;
  inline(text: string): ReactNode;
};
export function WorkspaceShell(props: {
  parts: PageParts;
  startView(ask: (question: string) => void): ReactNode; // the existing start-screen content
  player: ReactNode;                                      // <NowPlayingBar />
  phonePlayer: ReactNode;                                 // <NowPlayingBar collapsible />
  isPhone: boolean;
  linkedQuestion: string | null;                          // from takeQuestionFromUrl(), asked once on mount as a fresh start
  registerAskFromPage(handler: (question: string) => void): void; // wraps useAskFromPage
}): JSX.Element;
```

Behavior (all from the spec; the sketch shows each):
- **State**: `useReducer(explorationReducer, initialExploration)`. An `AbortController` and the current request id live in refs.
- **Asking**:
  - `ask(question, { source, focus, fresh })` returns early when `isAsking`. It creates `requestId = crypto.randomUUID()` and gets `ctx = requestContext(state, fresh)`; the thread id is `ctx.threadId ?? createThreadId()` (reuse `App.tsx`'s `createThreadId` by moving it to `ask-client.ts` as an export).
  - It writes `storeNotebook(ctx.notebook)`, dispatches `submit`, and builds the body with `askRequestBody`.
  - It runs `askStreaming(body, handlers, signal) ?? askPlain(body, signal)`. In dev with `requestedStreamFixture` it runs `replayStreamEvents(await loadRequestedStreamEvents(), handlers, signal)` instead.
  - The handlers dispatch `status` / `answer` / `page` with this `requestId`. On a `page_tab` page event it dispatches `initialTab` with `readTab(event.tab)`. This code is written now and exercised in PR 3.
  - On success it dispatches `complete` and `storeNotebook(response.notebook ?? null)`. On an error that is not an abort it dispatches `fail`.
- **Navigating**: `navigate(index)` aborts the controller, dispatches `navigate`, then `storeNotebook(requestContext(next, false).notebook)`. New chat dispatches `newChat`. Stop aborts and dispatches `cancel`. Retry re-runs `ask` with the failed pending's `question`, `source`, `focus` and `baseEntryId === null` as `fresh`. It dispatches `dismiss` first, then (for a follow-up) `navigate` back to the base entry if needed.
- **Rendering**:
  - One list of exploration panes, `[...entries.map(entry), pending]`, each keyed by its id (the pending pane's key is `requestId`, which becomes the entry id on complete, so React keeps the same subtree from draft to final).
  - Only the pane that `visible()` points at is shown; the rest get the `hidden` attribute. A `held` pane gets the class `previous` under a banner (`role="status"`) reading "Working on “{question}”", plus the last status and Stop.
  - A `working` pane shows the request as its heading and the last four statuses.
  - A `failed` pane shows `role="alert"` with "Deadbot couldn't finish “{question}”." plus Retry and Dismiss, above the held base page if there is one.
- **Each pane**:
  - Eyebrow-free heading `<h1 id={`${paneId}-title`} tabIndex={-1}>` (the response title, the draft title, or the question while working).
  - `WorkspaceTabs`, with states from `tabsWithContent`: `new` when content exists and the tab is not active while streaming, `preparing` when empty and streaming, `unused` when empty and done, else `ready`.
  - Three `role="tabpanel"` divs, all mounted, inactive ones `hidden`. Read renders `<p className="workspace-answer">{parts.inline(answer)}</p>`, then `body_lead`, then `parts.groups(routed.read…)`, then `parts.sources` when done. Listen and Charts render `parts.groups(routed.x…)`. An empty panel while streaming renders a quiet placeholder ("Finding recordings" / "Drawing the picture" / "Writing the answer"). The panel's `id` is `${paneId}-panel-${tab}`.
- **Interaction**: the pane container's `onPointerDown`, `onKeyDown` and `onWheel`/`onTouchMove` dispatch `view` with `interacted: true` (no patch) once per request. Tab selection dispatches `view` with `{ tab }` and `interacted: true`. Remember scroll per tab: on tab change and before navigating, save the workspace scroller's `scrollTop` into `view.scroll[tab]`, and restore it in a layout effect when the active pane or tab changes.
- **Announcements**: an sr-only `role="status"` announces "Listen ready" (and so on) the first time each tab gets content during a request, and "Ready: {title}" on complete. Focus moves to the new pane's heading with `preventScroll` on complete only if the visitor has not interacted.
- **One request at a time**: while asking, the composer's submit button, Ask chips (`onFollowUp`) and start chips do nothing; everything else works.
- **Layout**:
  - Desktop: a two-column grid (rail ~270px, main). The rail holds wordmark, New chat, `ExplorationHistory` and the composer (textarea, Enter submits, Shift+Enter is a newline, "Explore" button). The main column holds the panes and then `player`.
  - Phone (`isPhone`): no rail. `useMenuSlot(<ExplorationHistory …/>)` puts history in the site menu, and a selected row also closes the menu via `useCloseSiteMenu`. A dock at the foot holds `phonePlayer` plus the composer, reusing the old `mobile-dock` / `dock-composer` classes and the `--dock-h` measuring effect from `App.tsx` (copy it). A small dot on the site menu toggle while asking is out of scope; leave it out.
- **CSS** (`WorkspaceShell.css`, scoped under `.workspace-shell`): stack comparison groups one per row with `.workspace-shell .group-comparison .group-blocks { display: block }` plus a gap; sticky tabs; `.previous { opacity: .55 }`; reduced-motion respected. Use the existing design tokens from `styles.css` (read the top of that file) rather than new colors.

- [ ] **Step 1: Write the failing tests** in `web/src/WorkspaceShell.test.tsx`. Use the `fetch` stub pattern and `matchMedia`/`scrollTo` setup from `App.notebook.test.tsx`. Render `AppWithPlayer` from `./App` after setting `window.history.replaceState({}, "", "/?shell=workspace")` (so this test also covers Task 10's wiring; write the test now and expect it to pass after Task 10). Cover:
  1. Ask "MSG" (typed, Enter) then click an Ask chip from the fixture's groups (or type a second question). The history shows two rows, and `fetch` was called twice.
  2. Click row 1. `fetch` is not called again, and the heading shows entry 1's title. The second row stays, with the class `ahead`.
  3. Ask from row 1. The sent body's `conversation` equals entry 1's conversation and `notebook` equals entry 1's token, never entry 2's.
  4. A response whose only content is the answer (`groups: []`): the Listen and Charts tabs are `aria-disabled`, and Read shows the answer text. Nothing renders in the rail except the request row.
  5. Streaming (a stubbed stream body) of `answer` → `group_open` → `block` (show_unit) → hold. During the hold, click Charts. Then release a further `group_open` with a Read editorial block and the `response`. Charts stays selected.
  6. Player survival: render, call `usePlayer().play` through a test probe placed inside `PlayerProvider` (or click a card's Play in the fixture), navigate history, and assert the now-playing title is unchanged.
  7. A rejected `fetch` keeps the previous page and shows Retry; clicking Retry re-sends the same body.
- [ ] **Step 2: Run, verify failure.**
- [ ] **Step 3: Implement** `WorkspaceShell.tsx` and `WorkspaceShell.css`, plus the `PageGroups` / `SourcesFooter` extraction in `App.tsx`. Run `npm --prefix web test -- App.notebook` after the extraction to prove the old shell is unchanged.
- [ ] **Step 4: Run tests.** They pass after Task 10. Commit this task when its own unit-level assertions pass, then finish the wiring in Task 10.
- [ ] **Step 5: Commit** `git commit -m "Workspace shell: tabs, held previous page, mounted explorations, phone history in the menu"`

### Task 10: Wire the shell into App, plus the illustrative stream fixture

**Files:**
- Modify: `web/src/App.tsx`, `web/src/visual-fixtures.ts`
- Test: `web/src/WorkspaceShell.test.tsx` (from Task 9) and `web/src/App.notebook.test.tsx` (unchanged, still passing)

- [ ] **Step 1: Add `WorkspaceApp`** in `App.tsx`, next to `App`:
  - It builds `parts` from `PageGroups`, `SourcesFooter` and `renderInline`.
  - It passes `startView = (ask) => <the start-screen JSX from App: lead heading, library stats with starting-point chips calling ask(prompt)>`. Factor that JSX into a `StartLibrary({ onAsk, disabled })` component used by both shells, so the old shell is unchanged.
  - It passes `player={<NowPlayingBar />}`, `phonePlayer={<NowPlayingBar collapsible />}`, `isPhone={useMediaQuery(PHONE_QUERY)}`, `linkedQuestion={takeQuestionFromUrl()}` (read once with `useState(() => …)`), and `registerAskFromPage={useAskFromPage}`.
- [ ] **Step 2: Pick the shell** in `AppWithPlayer`: `const [mode] = useState(() => readShellMode(window.location.search));`, wrap the tree in `<MenuSlotProvider>`, and render `{mode === "workspace" ? <WorkspaceApp /> : <App />}` inside `.app-view`. The `PlayerProvider` stays outermost.
- [ ] **Step 3: Fixture.** In `visual-fixtures.ts`, add a `msg-workspace` response modeled on the sketch's MSG page: three show units in a comparison group, a data chart of nights per year, and an editorial group with Ask chips. Put "Illustrative fixture — not catalog records" in its header comment, use placeholder show ids from existing fixtures where possible, and register it with the existing stream-fixture builder so `?stream=msg-workspace` replays it (Listen's first card lands before the Read editorial).
- [ ] **Step 4: Run all checks.** `npm --prefix web test && npm --prefix web run build`. All PASS, including Task 9's shell tests.
- [ ] **Step 5: Look at it.** Run the dev server via the project's `.claude/launch.json` (see memory notes in `docs/UX-NEXT-STEPS.md` on fixtures). Open `/?shell=workspace&stream=msg-workspace`, ask anything, and capture desktop and 375px screenshots into the scratchpad for the PR. Check keyboard-only tab and history use.
- [ ] **Step 6: Commit** `git commit -m "Workspace shell behind ?shell=workspace; shared start library; msg-workspace stream fixture"`

---

# PR 3 — model contract: opening tab and group tabs

Before Task 11: `git -C /Users/markdavenport/Development/DeadBot/.claude/worktrees/app-update-planning-2a4e74 checkout -b claude/workspace-tabs-contract`.

### Task 11: Schema, resolution and stream events

**Files:**
- Modify: `deadbot/experience.py`, `deadbot/finish.py`, `deadbot/plan_stream.py`
- Test: `tests/test_finish.py`, `tests/test_plan_stream.py`, `tests/test_experience_contract.py` (append)

**Interfaces:**
- Produces (Python):
  - `experience.WorkspaceTab = Literal["listen", "charts", "read"]`
  - `experience.workspace_tab(value: Any) -> WorkspaceTab | None`, with the same lenient names as the web `readTab`: listen/listening/hear, charts/chart, read/context/story/info.
  - `ExperienceGroup.tab: WorkspaceTab | None = None`, `ExperienceResponse.initial_tab: WorkspaceTab | None = None`
  - `FinishPlan.initial_tab` (the **first** declared field) and `GroupPlan.tab` (the **first** declared field). Both are `WorkspaceTab | None = None`, with a `mode="before"` validator that maps through `workspace_tab`, so an unknown value reads as `None` and never fails the plan.
  - `PlanEvent("page_tab", {"tab": ...})`, emitted once per plan when `initial_tab` closes with a readable value (reset with the rest of the state on a retried call). Group payloads gain `"tab": workspace_tab(group.get("tab"))`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_plan_stream.py (append)
def test_the_opening_tab_streams_before_the_answer_and_groups_carry_tabs():
    plan = {"initial_tab": "Listen", **PLAN, "groups": [{"tab": "charts", **PLAN["groups"][0]}, PLAN["groups"][1]]}
    streamer = PlanStreamer(resolve=fake_resolve)
    events = streamer.feed(chunk(json.dumps(plan), name="finish_response"))
    kinds = [event.kind for event in events]
    assert kinds[0] == "page_tab" and events[0].payload == {"tab": "listen"}
    opens = [event.payload["tab"] for event in events if event.kind == "group_open"]
    assert opens == ["charts", None]


def test_an_unreadable_opening_tab_emits_nothing():
    plan = {"initial_tab": "sideways", **PLAN}
    events = PlanStreamer(resolve=fake_resolve).feed(chunk(json.dumps(plan), name="finish_response"))
    assert "page_tab" not in [event.kind for event in events]
```

Adapt the `PlanStreamer` construction and `feed` call to how the existing tests in that file build it. Read `test_events_arrive_in_reading_order_with_group_metadata` first and copy its harness exactly.

```python
# tests/test_finish.py (append)
from deadbot.finish import FinishPlan


def test_finish_plan_reads_tabs_leniently_and_puts_initial_tab_first():
    plan = FinishPlan.model_validate({"initial_tab": "Context", "chat_answer": "a", "title": "t", "groups": [
        {"tab": "chart", "presentation": "collection", "items": [{"type": "editorial", "presentation": "narrative", "paragraphs": ["x"], "items": []}]},
        {"tab": 7, "presentation": "collection", "items": [{"type": "editorial", "presentation": "narrative", "paragraphs": ["y"], "items": []}]},
    ]})
    assert plan.initial_tab == "read"
    assert [group.tab for group in plan.groups] == ["charts", None]
    assert list(FinishPlan.model_json_schema()["properties"])[0] == "initial_tab"
```

Also append to `tests/test_finish.py` a test that runs a plan with `initial_tab` and a group `tab` through `build_experience_response`. Copy the call shape from an existing `build_experience_response` test in that file. Assert `response.initial_tab` and `response.groups[0].tab` come through, and that a plan without them gives `None` for both. In `tests/test_experience_contract.py`, assert an `ExperienceResponse` payload without `initial_tab` or `tab` still validates.

- [ ] **Step 2: Run, verify failure.** `PYTHONPATH=. .venv/bin/python -m pytest tests/test_plan_stream.py tests/test_finish.py tests/test_experience_contract.py -q`
- [ ] **Step 3: Implement.**
  - `experience.py`: add the type, the reader and the two optional fields (with short `description`s).
  - `finish.py`: add the fields to `FinishPlan` and `GroupPlan` as their first declarations, with descriptions:
    - `initial_tab`: "The tab the page opens on: listen (to hear), charts (to see across time or categories) or read (the answer and its story). Write it first."
    - group `tab`: "Where this group lives: listen, charts or read."
    - Pass `tab=group.tab` into `ExperienceGroup(...)` in the group resolver, and `initial_tab=plan.initial_tab` where `build_experience_response` builds `ExperienceResponse`.
  - `plan_stream.py`: in `_string_closed`, handle `path == ["initial_tab"]`. Add a `_tab_sent` guard reset in `_reset_state`, and add `tab` to `_group_payload`. Confirm the API serializes `PlanEvent` kinds generically (`deadbot/api.py` stream route). If page events are filtered by kind there, add `page_tab`.
- [ ] **Step 4: Run tests and regenerate types**

```bash
PYTHONPATH=. .venv/bin/python -m pytest tests/test_plan_stream.py tests/test_finish.py tests/test_experience_contract.py tests/test_measure_finish_schema.py tests/test_api_notebook.py -q
.venv/bin/python scripts/export_openapi.py
npm --prefix web run gen:types
```

If `test_measure_finish_schema.py` holds a schema-size budget, update its expected value only by the measured delta, and say so in the commit message.

- [ ] **Step 5: Web types.** In `stream-events.ts`, add `| { type: "page_tab"; tab: string }` to `PageEvent` and `tab?: string | null` to the `group_open | group_close` member. Add `"page_tab"` to `PAGE_EVENT_TYPES` in `ask-client.ts`. Remove the `as { type: string }` cast in `page-draft.ts`'s `page_tab` guard, and the `as { tab?: unknown }` casts in `groupsOfResponse` and in the reducer's `complete` (the generated types now carry the fields). Run `npm --prefix web test && npm --prefix web run build`.
- [ ] **Step 6: Commit** `git commit -m "Model contract: initial_tab streams first; groups name their tab"`

### Task 12: Prompt guidance

**Files:**
- Modify: `deadbot/graph.py` (`SYSTEM_PROMPT`, a new short section right after `## ANSWER FIRST, THEN EARN THE REST`)
- Test: run `tests/test_graph.py` and any prompt-size test

- [ ] **Step 1: Add the section** (exact text; affirmative, no rules lists):

```
## THE WORKSPACE

The page has three tabs. Listen holds what the visitor can hear: shows,
performances, albums, songs and version strips. Charts holds what is seen
across time or categories: data charts, grids, and a song's life on stage when
its timeline is the point. Read holds the chat answer, the lead, and the
story, argument and context. Give each group the tab where it does its job,
and open the page (initial_tab) where this question's first attention
belongs: Listen when the visitor wants to hear something, Charts when the
shape of the numbers is the answer, Read when the answer is a fact or a story.
A tab with nothing to offer this question stays empty.
```

- [ ] **Step 2: Run** `PYTHONPATH=. .venv/bin/python -m pytest tests/test_graph.py tests/test_measure_finish_schema.py -q`. Expected: PASS (adjust a measured prompt-size budget by its measured delta only).
- [ ] **Step 3: Commit** `git commit -m "Persona: what each workspace tab is for, and choosing where the page opens"`

### Task 13: Trace marks, live runs and the groups-first experiment (controller, not a subagent)

**Files:**
- Modify: `scripts/trace_stream.py`
- Create: `docs/plans/persistent-exploration/live-runs-2026-11.md`

- [ ] **Step 1: Trace marks.** Add `page_tab` (seconds), `opening_tab` (value), and `first_listen_block` / `first_charts_block` / `first_read_block`. Track a `group_index → tab` map from `group_open` events (fallback: the block's type, via the same table as `tab-routing.ts`, duplicated as a small dict with a comment pointing at the TS source).
- [ ] **Step 2: Live runs.** Start the local API with the production model settings (see memory: local replay, `DEADBOT_*` env, effort low). Run each question 3 times on `main` and 3 times on this branch:
  - "What's their history at Madison Square Garden?" then "Focus on the late '80s" as a follow-up
  - "When was Jerry Garcia born?"
  - "Tell me the story of Veneta '72"
  - "How did Dark Star change over the years?"
  - one show question with no audio
  - one question with nothing to chart

  Record commit, model, effort and every mark, plus the opening tab chosen and per-tab group counts.
- [ ] **Step 3: Groups-first variant.** Locally (uncommitted), move `chat_answer` after `groups` in `FinishPlan` and re-run the MSG and Dark Star questions 3×. Compare first-Listen-block time and answer quality. Commit the reorder only if first playable content improves without hurting answers, and only after asking Mark.
- [ ] **Step 4: Browser pass.** In the workspace shell against the live API: desktop, 320px, keyboard only, 200% zoom, reduced motion. Take screenshots of the MSG → Charts → follow-up → back path.
- [ ] **Step 5: Write up** the table and observations (sample sizes, failures, negative findings) in `live-runs-2026-11.md`. Commit.

### Task 14: Docs

**Files:**
- Modify: `docs/UX-NEXT-STEPS.md`

- [ ] **Step 1:** Add a "Batch: persistent exploration workspace (November 2026)" entry covering:
  - what shipped behind `?shell=workspace`;
  - that history is in memory only for the session;
  - the stream-order gap and what the live runs found;
  - links to the spec, this plan, the sketch and the live-runs note.

  Mark item 5 ("Preserve exploration across turns") as implemented by it.
- [ ] **Step 2:** Commit `git commit -m "UX next steps: the persistent exploration workspace"`.

---

## Self-review notes

- **Spec coverage.** State and history → Tasks 4, 9. Thread isolation → Task 5. Shell, desktop and phone → Tasks 6–10. Tabs and fallback → Tasks 2, 7, 9. Contract and prompt → Tasks 11–12. Progressive behavior, focus rule and errors → Tasks 4, 9. Testing and live → Tasks 9–10, 13. Docs → Task 14. Rollout toggle → Tasks 6, 10.
- **Deliberate simplification of the spec's view state.** Disclosures and chart picks are preserved by keeping each exploration's pane mounted (hidden), not by storing their keys in the reducer. `EntryView` keeps only `tab` and per-tab `scroll`. Behavior is the same, with far less code.
- **Not built.** A dot on the phone hamburger while asking (the sketch has one; left out to keep `SiteMenu` changes to the slot only), and the opening animation for the workspace's first ask (the start view simply gives way to the working pane).
