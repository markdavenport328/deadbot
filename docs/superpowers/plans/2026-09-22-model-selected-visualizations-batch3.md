# Model-selected data visualizations — Batch 3: React chart renderer

## Context

Batches 1-2 (merged to this branch; PR #57) built the backend contract and
server-side hydration. The browser now receives, as one member of the
`ExperienceBlock` union, a fully-formed `DataChartBlock`:

```ts
type DataChartBlock = {
  type: "data_chart";
  aggregation_id: string;
  title: string;
  note: string | null;
  chart: "bar" | "stacked_bar";       // only "bar" is ever actually sent in this batch
  orientation: "vertical" | "horizontal";
  x_field: string;                     // always the dimension column's key
  y_field: string;                     // always "value"
  x_label: string | null;
  y_label: string | null;
  columns: { key: string; label: string; type: "temporal" | "categorical" | "quantitative" }[]; // exactly 2
  rows: { [key: string]: unknown }[];  // each row: {year, value} OR {id, label, value}
  metric_label: string;
  scope_note: string;
  total: number;
  excluded_count: number;
  date_range: { from: number; to: number } | null;
  empty_reason: string | null;
};
```

Confirmed by research before this plan was written: blocks **always arrive
fully-formed** — the streaming protocol (`web/src/stream-events.ts`) sends one
complete `block` event per block, never a partial/patched one, so
`DataChart.tsx` never needs a "mid-arrival" state. `columns` is always exactly
2 entries (a dimension column + a `"value"` column) in this batch —
`chart: "stacked_bar"` and any third column are schema-permitted (Batch 2 kept
the type forward-compatible) but Batch 2's backend hydration never actually
produces one; Batch 3 must render a safe "not yet available" state for
`stacked_bar` rather than attempting a real stack.

Batch 3's job: `web/src/DataChart.tsx`, wired into `App.tsx`'s block switch,
styled via `styles.css`, covered by a new Vitest/Testing Library suite (this
repo has zero frontend tests today — Task 1 sets up the harness from
scratch), plus a hands-on responsive/accessibility review the controller
performs directly in a browser (DOM unit tests cannot establish chart
geometry or label density — see the end of this plan).

**Dependency note:** `web/package.json` already has `recharts`,
`@testing-library/{react,jest-dom,user-event}`, `jsdom`, and `vitest` added
(pinned to stable versions — the initial `"latest"` pin on `vitest` resolved
to an unstable 5.x release whose peer-dependency graph crashes this npm
version's resolver; do not change these pins without a specific reason).
`npm install --prefix web` must be run (by the repo owner — this sandbox's
Bash permission policy blocks `npm install`/`npm ci` outright, confirmed
repeatedly across Batch 2 and the start of this batch; `npm run <script>`
itself is NOT blocked, only the install step) before any task in this batch
can run tests or build. If `web/node_modules` doesn't exist when a task
starts, that task is blocked — escalate immediately rather than guessing.

## Global constraints

- **Never invent a number.** Every value `DataChart.tsx` displays — bar
  heights, axis ticks, tooltip values, totals — comes from `block.rows`/
  `block.total`/etc. verbatim. The component may format (round, add commas,
  truncate a label) but never compute, estimate, or fall back to a
  placeholder number.
- **Orientation mapping — the single highest-risk detail in this batch.**
  This app's `orientation` field names which way the bars visually grow:
  `"vertical"` = bars grow upward from a shared baseline (a year series);
  `"horizontal"` = bars grow rightward, one per row (a ranked category).
  recharts' own `layout` prop is, confusingly, named for the *axis* layout,
  and its meaning is the **opposite** of ours:
  ```
  orientation="vertical"   -> <BarChart layout="horizontal"> (recharts' default)
                              <XAxis type="category" dataKey={x_field} />, <YAxis type="number" />
  orientation="horizontal" -> <BarChart layout="vertical">
                              <XAxis type="number" />, <YAxis type="category" dataKey={x_field} />
  ```
  Get this backwards and the chart renders sideways or upside down while
  still "looking plausible" in a quick code read — every task touching this
  must verify it **visually** (a real render, not just passing type-checks),
  and Task 2's tests must assert on the actual rendered axis roles, not just
  that *a* chart rendered.
- **`x_field`/`y_field` drive `dataKey`, never a hardcoded `"year"`/`"label"`
  string.** `x_field` is always the dimension column's key (`"year"` for a
  temporal result, `"label"` for a categorical one) and `y_field` is always
  `"value"` — read them from `block`, don't assume which literal string
  they'll be.
- **`chart: "stacked_bar"` and any row/column shape beyond the guaranteed
  2-column contract render a clear, safe "not available" state** — not a
  crash, not a silently-wrong single-series bar pretending to be a stack.
  Same for any row whose value isn't a finite number, or a `columns` array
  that isn't exactly 2 entries (defense in depth — Batch 2's backend already
  guarantees this, but the frontend must never trust a payload blindly:
  "Render an empty explanation when no rows are returned and a safe fallback
  when a payload violates assumptions. Never throw the whole page.").
- **Animation is unconditionally disabled** (`isAnimationActive={false}` on
  every recharts element that accepts it) — not conditional on
  `prefers-reduced-motion`, just off, matching the outcome doc's explicit
  instruction.
- **Color: `var(--violet)` (`#8b5cf6`) is the one bar color**, already
  defined in `styles.css`'s `:root` and independently validated for this
  app's dark surface (`#14221b`) via the dataviz skill's
  `scripts/validate_palette.js` before this plan was written — passes the
  lightness band, chroma floor, and contrast-vs-surface checks cleanly. This
  is a single-series chart (never more than one series in this batch), so no
  legend is needed — the block's own title names what's plotted, per the
  dataviz skill's rule that "a single series needs no legend box." Do not
  introduce a second hue, and do not reuse `--listen`/`--read`/`--ask`
  (gold/rose/blue) — those are reserved for this app's listen/read/ask
  action vocabulary and a chart is none of those actions.
- **Mark spec** (from the dataviz skill, `references/marks-and-anatomy.md`):
  bars ≤24px thick (cap it, let the leftover band width be air — never fill
  the slot); 4px rounded corner at the data end, square at the baseline;
  gridlines/axis lines hairline (1px), solid, one-step-off-surface gray
  (reuse `--hair`/`--muted`, don't invent a new gray); text (axis ticks,
  tooltip, table) always uses text tokens (`--text`/`--cream`/`--muted`),
  never the bar's violet — "text wears text tokens, never the series color."
- **Tooltip**: per-mark hover/focus (not a crosshair — that's for line
  charts), showing the row's dimension label and value; value leads
  (Strong/high-contrast), dimension label is secondary — this is the
  tooltip hierarchy the dataviz skill specifies, and it's inverted from a
  legend's hierarchy on purpose ("here the reader has the series and wants
  the number"). Same information must be reachable on keyboard focus, not
  hover-only.
- **Accessible figure + table alternative, always present.** Wrap the chart
  in a `<figure>` with an accessible name (the block's `title`) and
  description (composed from `metric_label`/`scope_note`/`total`) via
  `aria-labelledby`/`aria-describedby` pointing at visually-hidden or
  already-visible heading/caption elements. Reuse the existing `Drawer`
  component (`web/src/App.tsx`, the tabbed disclosure that replaced this
  codebase's old stacked `<details>` facets — read it in full before
  building anything new) for the table-view toggle, rather than inventing a
  second disclosure pattern: a single-tab `Drawer` with one tab labeled "View
  as table" (or similar) containing a native `<table>` with every row is
  both idiomatic for this codebase and free keyboard accessibility (the
  `Drawer` already handles arrow-key nav and `aria-expanded`/`aria-controls`
  correctly). The table is the authoritative keyboard-readable alternative —
  every value the chart shows must also be in the table, in full (no
  truncation in the table, even where the chart's axis labels are
  truncated).
- **Long labels**: truncate with an ellipsis in the plotted axis tick only
  (bounded width, e.g. via a recharts tick `formatter`), never in the
  tooltip or the table — both of those always show the full label. This is
  the outcome doc's own instruction: "Format long labels with bounded
  wrapping/truncation in the plot while showing the full label in the
  tooltip and table."
- Explicitly out of scope for this batch: `deadbot/aggregation.py`,
  `deadbot/data.py`, `deadbot/postgres.py`, `deadbot/tools.py`,
  `deadbot/finish.py`, `deadbot/experience.py`, `deadbot/composition.py`,
  `deadbot/graph.py` (Batches 1-2 own these; Batch 3 only consumes
  `web/src/types.ts`'s already-generated `DataChartBlock`), the `series_field`
  concept (never populated in this batch, so nothing to render), and any
  bar-click/drill-down interaction (the outcome doc explicitly defers this:
  "Optional bar selection is explicitly deferred").
- Tests: `npm test --prefix web` (once Task 1 defines this script's real
  behavior) per task; `npm run build --prefix web` and a manual browser
  check before the batch is considered done. Python tests are untouched by
  this batch, but running `PYTHONPATH=.
  /Users/markdavenport/Development/DeadBot/.venv/bin/python -m pytest -q`
  once at the end is still worth confirming nothing broke by accident (it
  shouldn't — no Python files change).
- Never push; never bare `git stash`. Commit trailer:
  `Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>`.

## Task 1 — Vitest test infrastructure (from scratch)

This repo has zero frontend tests today: no `.test.ts(x)`/`.spec.ts(x)`
files, no Vitest config anywhere, no `test:` block in `vite.config.ts`
(confirmed by reading it in full — it's an 11-line file with only the React
plugin and a dev-server proxy). This task builds that harness from nothing.

1. `web/vite.config.ts` — add a `test` block to the existing
   `defineConfig({...})` call (Vitest reads Vite's own config when there's no
   separate `vitest.config.ts` — prefer this over a second config file to
   keep one source of truth):
   ```ts
   export default defineConfig({
     plugins: [react()],
     server: { proxy: { "/api": "http://127.0.0.1:8000" } },
     test: {
       environment: "jsdom",
       setupFiles: ["./src/setupTests.ts"],
       globals: true,
       css: false,
     },
   });
   ```
   (`globals: true` avoids per-file `import { describe, it, expect } from
   "vitest"` boilerplate — if you'd rather keep explicit imports for
   consistency with this codebase's existing style, that's a defensible
   alternative; note your choice in the report and update step 3
   accordingly.)

2. `web/src/setupTests.ts` (new file):
   ```ts
   import "@testing-library/jest-dom/vitest";

   // jsdom has no ResizeObserver; recharts' ResponsiveContainer needs one.
   class ResizeObserverMock {
     observe() {}
     unobserve() {}
     disconnect() {}
   }
   // eslint-disable-next-line @typescript-eslint/no-explicit-any -- test shim, not app code
   (globalThis as any).ResizeObserver = ResizeObserverMock;
   ```
   Adapt the exact shim to whatever recharts' `ResponsiveContainer` actually
   needs once you can run it (it may also read `getBoundingClientRect`, which
   jsdom stubs to all-zeros by default — if a test needs a non-zero container
   size for `ResponsiveContainer` to render children at all, mock
   `Element.prototype.getBoundingClientRect` to return a plausible fixed
   size, e.g. 600×300, in the same setup file or per-test as needed. Note in
   your report which of these you needed.)

3. `web/tsconfig.json` — add `"vitest/globals"` (if you chose `globals:
   true` above) to the `"types"` array (currently `["vite/client"]`) so
   `describe`/`it`/`expect` type-check without per-file imports. If you chose
   explicit imports instead, skip this.

4. `web/package.json` — `"test": "vitest run"` is already present (added
   ahead of this task); leave it as-is unless you have a specific reason to
   change it (e.g. adding a `"test:watch": "vitest"` script is fine to add,
   changing the existing `test` script's behavior is not, without noting why
   in your report).

5. One smoke test, `web/src/setupTests.test.tsx` (or fold it into the first
   real component test in Task 2 if you'd rather not have a throwaway file —
   your call, note which you did): render a trivial component with React
   Testing Library and assert `screen.getByText(...)` finds it, proving
   `jsdom` + `@testing-library/react` + `@testing-library/jest-dom` matchers
   (e.g. `toBeInTheDocument()`) all actually work together end-to-end.

6. Verify: `npm test --prefix web` runs and the smoke test passes. If
   `web/node_modules` doesn't exist (i.e. `npm install --prefix web` hasn't
   been run yet by the repo owner), STOP and report BLOCKED — do not attempt
   to work around a missing `node_modules` by hand-rolling anything.

Run: `npm test --prefix web`

## Task 2 — `web/src/DataChart.tsx`: the chart component

Depends on Task 1 (needs a working test harness to verify against).

1. Create `web/src/DataChart.tsx`. Import `DataChartBlock` from `./types`
   (there's no path alias in this codebase — `web/tsconfig.json` has no
   `paths`/`baseUrl`; use a relative import like every other file does).
   Recharts pieces needed: `ResponsiveContainer`, `BarChart`, `Bar`, `XAxis`,
   `YAxis`, `CartesianGrid`, `Tooltip`, and `Cell` only if you end up needing
   per-bar styling beyond a single uniform fill (you likely won't, given
   there's exactly one series/color).

2. Component shape (a starting skeleton — flesh out per Global Constraints;
   deviate from this exact structure where the constraints require it, but
   keep the overall shape: guard clauses first, then the figure):

   ```tsx
   export function DataChart({ block }: { block: DataChartBlock }) {
     const titleId = useId();
     const descId = useId();

     // Structural guards — defense in depth against a payload that somehow
     // violates the contract Batch 2 already guarantees server-side. Render
     // a safe, clearly-labeled fallback, never throw.
     if (block.chart !== "bar") {
       return <UnavailableChart block={block} reason="stacked charts aren't available yet" />;
     }
     if (block.columns.length !== 2) {
       return <UnavailableChart block={block} reason="this chart's data is in an unexpected shape" />;
     }
     const dimensionColumn = block.columns.find((c) => c.key !== "value");
     if (!dimensionColumn) {
       return <UnavailableChart block={block} reason="this chart's data is in an unexpected shape" />;
     }
     const rows = block.rows.filter(
       (row) => typeof row[block.y_field] === "number" && Number.isFinite(row[block.y_field] as number)
     );
     if (rows.length !== block.rows.length) {
       // Some row failed the finite-number check — this should never happen
       // given Batch 2's server-side validation; render what's safe rather
       // than silently dropping rows the visitor can't see were dropped.
       return <UnavailableChart block={block} reason="this chart's data is in an unexpected shape" />;
     }

     if (rows.length === 0) {
       return <EmptyChart block={block} titleId={titleId} descId={descId} />;
     }

     const isVertical = block.orientation === "vertical"; // see Global Constraints' orientation table

     return (
       <figure className="data-chart-figure" aria-labelledby={titleId} aria-describedby={descId}>
         <figcaption id={titleId} className="data-chart-title">{block.title}</figcaption>
         <p id={descId} className="visually-hidden">
           {block.metric_label}. {block.scope_note}. Total {block.total}
           {block.excluded_count > 0 ? `, ${block.excluded_count} more not shown` : ""}.
         </p>
         {block.note && <p className="unit-note">{block.note}</p>}
         <ResponsiveContainer width="100%" height={/* pick a sensible fixed height, e.g. 320 */}>
           <BarChart data={rows} layout={isVertical ? "horizontal" : "vertical"} /* ...margins, etc. */>
             <CartesianGrid stroke="var(--hair)" strokeDasharray="0" {/* solid, not dashed — see mark spec */} />
             {/* XAxis/YAxis per the orientation table in Global Constraints */}
             <Tooltip content={<ChartTooltip dimensionLabel={dimensionColumn.label} valueLabel={block.metric_label} />} isAnimationActive={false} />
             <Bar dataKey={block.y_field} fill="var(--violet)" isAnimationActive={false} radius={/* per mark spec, oriented correctly */} maxBarSize={24} />
           </BarChart>
         </ResponsiveContainer>
         <p className="coverage-note">{block.scope_note}</p>
         <Drawer
           tabs={[{ id: "table", label: "View as table", count: rows.length, content: <DataChartTable block={block} dimensionColumn={dimensionColumn} rows={rows} /> }]}
           initialOpen={null}
         />
       </figure>
     );
   }
   ```

   `UnavailableChart`, `EmptyChart`, `ChartTooltip`, and `DataChartTable` are
   your own small helper components/functions in this same file — sizes and
   exact JSX are your judgment, but each must satisfy Global Constraints
   (`EmptyChart` shows `block.empty_reason` and still renders inside a
   `<figure>` with the same accessible name/description pattern;
   `UnavailableChart` is clearly worded as a limitation, not an error, and
   never implies the visitor did something wrong). `Drawer` is imported from
   `./App` — check whether it's already exported; if not, export it (a
   one-line change to `App.tsx`, note it in your report) rather than
   duplicating it.

3. Apply the mark spec precisely: `maxBarSize={24}`, `radius` on `<Bar>`
   oriented correctly for each layout (rounded at the data end, square at the
   baseline — for `layout="horizontal"` i.e. our `orientation="vertical"`,
   that's the top corners: `radius={[4, 4, 0, 0]}`; for `layout="vertical"`
   i.e. our `orientation="horizontal"`, that's the end away from the
   baseline — verify visually which corners that actually is once you can
   render it, recharts' corner-radius argument order is easy to get backwards
   too). `isAnimationActive={false}` on both `<Bar>` and `<Tooltip>`.

4. Long-label truncation on the categorical axis only (when
   `orientation==="horizontal"`, the `YAxis` category tick labels — song/
   venue/city/guest names can be long): a tick `formatter`/custom tick
   component that truncates with an ellipsis at a bounded character count,
   while the tooltip and table always show the untruncated `label`. Do not
   truncate year values (they're never long).

5. Wire `Element.prototype.getBoundingClientRect`/`ResizeObserver` concerns
   are Task 1's job (the setup file) — if you find you need something
   `DataChart.tsx`-specific beyond what Task 1 provided, add it there and
   note the addition in your report rather than silently expanding scope.

6. Tests, `web/src/DataChart.test.tsx`:
   - a temporal (year) fixture renders with the category axis showing years
     and value on the numeric axis — assert on actual rendered DOM (e.g. the
     presence of specific year tick text, or query the `<Bar>` elements'
     count matching `rows.length`), not just "a chart rendered";
   - a categorical (ranked) fixture with `orientation="horizontal"` renders
     with categories on one axis and values on the other — assert this is
     genuinely the transposed layout from the temporal case, not the same
     layout relabeled (this is the test that actually catches an inverted
     orientation mapping — don't skip it);
   - hovering/focusing a bar shows the tooltip with the exact row value and
     dimension label, value rendered with more visual weight than the label
     (assert via `screen.getByRole`/text content, not just "a tooltip
     exists");
   - an empty result (`rows: []`, `empty_reason` set) renders the empty
     state with that exact reason text, not a blank chart;
   - a malformed payload (hand-construct one violating a Global Constraint —
     e.g. `chart: "stacked_bar"`, or `columns` with 1 entry, or a row with a
     non-numeric value) renders the safe fallback, not a thrown error —
     assert the component doesn't throw (React Testing Library will surface
     an uncaught render error as a test failure automatically if you don't
     guard it) and shows clear, non-alarming wording;
   - a long category label is truncated in the rendered axis tick but the
     full label is present, untruncated, in both the tooltip and the table
     view;
   - the figure has an accessible name matching `block.title` (assert via
     `screen.getByRole("figure", { name: ... })` or equivalent) and every
     displayed row's value appears in the table (open the `Drawer`'s tab via
     `userEvent.click`/keyboard activation first, then assert on the table's
     content — this is also your keyboard-accessibility test for the
     disclosure);
   - `isAnimationActive={false}` is actually passed to the relevant recharts
     elements — this may be easiest to verify by rendering and checking
     recharts doesn't apply a CSS animation/transition class, or by a
     lighter-weight prop-level assertion if you structure the component to
     make that straightforward; use your judgment on the most reliable way
     to test this without over-fitting to recharts' internals;
   - `block.chart` typed as `"bar" | "stacked_bar"` at the TypeScript level
     means `"line"`/`"scatter"`/anything else is already a compile error —
     write one test asserting the *runtime* `stacked_bar` case (the value
     TypeScript does allow but this batch can't render) hits the
     `UnavailableChart` path, which is the practical equivalent of "line
     rendering is rejected" for a value TypeScript's own type system doesn't
     even let you construct.

   Build fixture data directly in the test file (plain object literals
   matching `DataChartBlock`'s shape) rather than importing from
   `visual-fixtures.ts` (that module has a dev-only guard —
   `if (!import.meta.env.DEV) return null;` patterns — and isn't meant to be
   a test data source; Task 3 adds the visual-fixtures.ts entry separately,
   for human/browser review, not for these unit tests).

Run: `npm test --prefix web`

## Task 3 — Wire into `App.tsx`, style, and add a visual fixture

Depends on Task 2.

1. `web/src/App.tsx`: add `import { DataChart } from "./DataChart";` and a
   `case "data_chart": return <DataChart block={block} />;` to the `Block`
   switch (`App.tsx:1230-1516`). The switch has no `default:` clause today,
   so TypeScript's exhaustiveness check is already forcing this — if you add
   the case and the file still doesn't type-check, something else is wrong,
   don't add a `default:` to silence it.
2. `web/src/styles.css`: add the chart-specific rules — `.data-chart-figure`,
   `.data-chart-title`, and whatever `UnavailableChart`/`EmptyChart` classes
   Task 2 introduced. `.typography-block`'s default `max-width: 58rem` may
   read as too narrow for a comfortable bar chart — consider a wider
   `max-width` specifically for `.data-chart-figure` (verify this visually,
   don't guess a number and leave it unverified). Reuse existing tokens
   throughout (`--space-*`, `--r`, `--hair`, `--muted`, `--cream`, `--text`,
   `--violet`) — do not introduce new spacing/color values not already in
   `:root` unless Global Constraints' color section requires it (it
   doesn't — `--violet` already exists).
3. `web/src/visual-fixtures.ts`: add at least one `DataChartBlock` object
   into the existing `blocks` fixture's block array (the fixture explicitly
   documented as "every typography block on one page, for reviewing the
   open-block anatomy" — the idiomatic home for this). Add both a temporal
   (year) example and a categorical (ranked) example if the `blocks` fixture
   can reasonably hold both without becoming unwieldy — check the file's
   existing length/organization and use your judgment; at minimum, one of
   each orientation must be reviewable somewhere in the fixture set.
4. Confirm the production-build exclusion still holds: `visual-fixtures.ts`
   is only reachable via the `import.meta.env.DEV`-guarded dynamic import in
   `visual-fixture-loader.ts` — you're not changing that mechanism, just
   adding data to a file it already dynamically imports, so no action is
   needed here beyond noting in your report that you didn't touch the
   loader.
5. Tests: if `Block`/the switch is easily unit-testable in isolation (check
   whether it's already exported or trivially exportable), add one test
   confirming a `data_chart`-typed block routes to `DataChart`. If wiring it
   up cleanly would require exporting internals that aren't otherwise
   exported and reads as more disruptive than it's worth, skip this and note
   why — the controller will verify the real integration visually in the
   browser afterward regardless, which is the stronger check for this
   specific concern.

Run:
```
npm test --prefix web
npm run build --prefix web
```
Both must succeed. If `npm run build` fails for a `node_modules`/install
reason rather than a real type/build error, report that distinction clearly.

## After Task 3 — controller-performed visual review (not a task; do not
## delegate this to a subagent)

DOM unit tests cannot establish chart geometry, readable label density, or
genuine responsive behavior. Once Task 3 is merged into this batch's
branch state:

1. Start the dev server (`npm run dev --prefix web`, or via this session's
   `preview_start`) and open `/?fixture=blocks` (or whichever fixture name
   Task 3 used) in the browser tool.
2. Review at 1440px, 600px, 390px, and 320px widths (`resize_window`), with
   the OS-level "enlarged text" case if easily testable, keyboard-only
   navigation through the chart's tab/table disclosure, and
   `prefers-reduced-motion: reduce` (via `resize_window`'s `colorScheme`-
   adjacent options if it exposes a media-feature override, otherwise via
   the OS/browser setting) — confirm no residual animation.
3. Check both orientations render correctly (this is the visual confirmation
   the orientation-mapping tests can't fully replace — actually look at
   whether a year chart's bars grow up and a ranked chart's bars grow
   sideways, not just that some bars exist).
4. Note every finding (label collisions, overflow, a color that doesn't
   actually read as `--violet` once rendered, a tooltip that's hard to
   trigger, anything the mark spec/dataviz skill's anti-patterns file would
   flag) and fold them into this batch's final whole-branch review /fix wave
   alongside a dispatched text-based code reviewer, the same two-track
   pattern used for the "npm run build couldn't be verified" gap in Batch 2.
