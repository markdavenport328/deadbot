import { fireEvent, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { DataChart, type DataChartBlock } from "./DataChart";

// Plain object literals matching DataChartBlock's generated shape directly --
// this file intentionally does not import from visual-fixtures.ts (that
// module is a dev-only, browser-review fixture set, not a unit test data
// source).

const yearBlock: DataChartBlock = {
  type: "data_chart",
  aggregation_id: "agg-year",
  chart: "bar",
  columns: [
    { key: "year", label: "Year", type: "temporal" },
    { key: "value", label: "Shows", type: "quantitative" }
  ],
  date_range: { from: 1977, to: 1979 },
  empty_reason: null,
  excluded_count: 0,
  metric_label: "Shows performed",
  note: null,
  orientation: "vertical",
  rows: [
    { year: 1977, value: 59 },
    { year: 1978, value: 61 },
    { year: 1979, value: 47 }
  ],
  title: "Shows per year, 1977-1979",
  total: 167
};

const rankedBlock: DataChartBlock = {
  type: "data_chart",
  aggregation_id: "agg-rank",
  chart: "bar",
  columns: [
    { key: "label", label: "Venue", type: "categorical" },
    { key: "value", label: "Shows", type: "quantitative" }
  ],
  date_range: null,
  empty_reason: null,
  excluded_count: 2,
  metric_label: "Shows performed",
  note: null,
  orientation: "horizontal",
  rows: [
    { label: "Winterland", value: 12 },
    { label: "Fillmore West", value: 9 },
    { label: "Boston Garden", value: 7 }
  ],
  title: "Most-played venues",
  // total is computed server-side over the full, unlimited result set, not
  // just these three shown rows (28) -- the 2 excluded venues account for
  // the remainder, so total is deliberately larger than the visible sum.
  total: 37
};

const longLabelBlock: DataChartBlock = {
  ...rankedBlock,
  aggregation_id: "agg-long-label",
  title: "Most-played venues, full names",
  rows: [
    { label: "The Fillmore East, New York City, New York", value: 15 },
    { label: "Winterland", value: 12 }
  ]
};

const emptyBlock: DataChartBlock = {
  ...rankedBlock,
  aggregation_id: "agg-empty",
  title: "No shows found",
  rows: [],
  empty_reason: "No shows matched this search."
};

// 20 rows -- this app's default `limit` -- is exactly the row count the
// reviewer measured recharts' default tick-skipping (interval="preserveEnd")
// dropping most labels at: only 10 of 20 survived. A fixed-height plot with
// only a handful of rows never exercised this.
const manyRowsBlock: DataChartBlock = {
  ...rankedBlock,
  aggregation_id: "agg-many-rows",
  title: "Twenty venues",
  excluded_count: 0,
  rows: Array.from({ length: 20 }, (_, index) => ({ label: `Venue ${index + 1}`, value: 20 - index })),
  total: 210
};

function withOverride(overrides: Partial<DataChartBlock>): DataChartBlock {
  return { ...rankedBlock, ...overrides };
}

// Tick labels render into recharts' own z-index portal layer (a DOM sibling
// far from the .xAxis/.yAxis groups themselves, per recharts 3.4+'s
// ZIndexLayer/createPortal architecture) -- but the portal-rendered group
// still carries an axis-specific class, which is what scopes these queries
// correctly.
function xTickLabels(container: HTMLElement) {
  return container.querySelector(".recharts-xAxis-tick-labels") as HTMLElement;
}
function yTickLabels(container: HTMLElement) {
  return container.querySelector(".recharts-yAxis-tick-labels") as HTMLElement;
}

// recharts' mouse-driven hover requires real SVG geometry (getScreenCTM and
// friends) that jsdom doesn't implement, so tests trigger the tooltip via
// the keyboard path instead: focusing the chart wrapper and pressing a key
// moves the active index the same way a real keyboard user would. This also
// doubles as the keyboard-accessibility check the brief asks for.
function focusFirstDataPoint(container: HTMLElement) {
  const wrapper = container.querySelector(".recharts-wrapper") as HTMLElement;
  fireEvent.focus(wrapper);
  fireEvent.keyDown(wrapper, { key: "ArrowDown" });
}

describe("DataChart", () => {
  it("renders a temporal (year) fixture with years on the category axis and values on the numeric axis", () => {
    const { container } = render(<DataChart block={yearBlock} />);

    const xLabels = xTickLabels(container);
    const yLabels = yTickLabels(container);
    expect(within(xLabels).getByText("1977")).toBeInTheDocument();
    expect(within(xLabels).getByText("1978")).toBeInTheDocument();
    expect(within(xLabels).getByText("1979")).toBeInTheDocument();
    // The numeric axis shows counts, not years.
    expect(within(yLabels).queryByText("1977")).not.toBeInTheDocument();

    const bars = container.querySelectorAll(".recharts-bar-rectangle path");
    expect(bars.length).toBe(yearBlock.rows.length);
    // orientation="vertical" bars grow upward from a shared baseline: a
    // fixed (capped) width and a per-row height.
    bars.forEach((bar) => {
      expect(bar.getAttribute("width")).toBe("24");
      expect(Number(bar.getAttribute("height"))).toBeGreaterThan(0);
    });
  });

  it("renders a categorical (ranked) fixture transposed from the temporal layout", () => {
    const { container } = render(<DataChart block={rankedBlock} />);

    const xLabels = xTickLabels(container);
    const yLabels = yTickLabels(container);
    // Categories live on the y axis here -- the opposite axis from the
    // temporal case above. This is the assertion that actually catches an
    // inverted orientation mapping, not just "a chart rendered".
    expect(within(yLabels).getByText("Winterland")).toBeInTheDocument();
    expect(within(yLabels).getByText("Fillmore West")).toBeInTheDocument();
    expect(within(xLabels).queryByText("Winterland")).not.toBeInTheDocument();
    // And the numeric axis now carries plain counts, not venue names.
    expect(within(xLabels).getByText("0")).toBeInTheDocument();

    const bars = container.querySelectorAll(".recharts-bar-rectangle path");
    expect(bars.length).toBe(rankedBlock.rows.length);
    // orientation="horizontal" bars grow rightward: a fixed (capped) height
    // and a per-row width -- genuinely transposed from the year case, not
    // the same layout relabeled.
    bars.forEach((bar) => {
      expect(bar.getAttribute("height")).toBe("24");
      expect(Number(bar.getAttribute("width"))).toBeGreaterThan(0);
    });
  });

  it("draws bars in var(--muted) with a 2px corner radius matching --r, not the reserved action colors", () => {
    const { container } = render(<DataChart block={rankedBlock} />);

    const bars = container.querySelectorAll(".recharts-bar-rectangle path");
    expect(bars.length).toBeGreaterThan(0);
    bars.forEach((bar) => {
      expect(bar.getAttribute("fill")).toBe("var(--muted)");
      // recharts' Rectangle draws each rounded corner as an SVG elliptical
      // arc "A rx,ry,0,0,sweep,..." -- a radius of 2 on exactly two of the
      // four corners (orientation="horizontal" passes radius={[0, 2, 2, 0]},
      // rounding only the data-end corners) shows up as exactly two
      // "A 2,2,0,0," arcs in the path's `d` attribute, confirmed directly
      // against this component's rendered output for both orientations.
      const d = bar.getAttribute("d") ?? "";
      const roundedCorners = d.match(/A 2,2,0,0,/g) ?? [];
      expect(roundedCorners).toHaveLength(2);
    });
  });

  it("shows the tooltip with the exact row value and dimension label on keyboard focus, value leading", () => {
    const { container } = render(<DataChart block={rankedBlock} />);

    focusFirstDataPoint(container);

    const tooltip = container.querySelector(".data-chart-tooltip") as HTMLElement;
    expect(tooltip).toBeInTheDocument();
    const value = within(tooltip).getByText("12");
    expect(value.tagName.toLowerCase()).toBe("strong");
    const label = within(tooltip).getByText(
      (_content, node) => node?.tagName.toLowerCase() === "p" && node.textContent === "Venue: Winterland"
    );
    expect(label).toBeInTheDocument();
    // The value carries more visual weight (a <strong>) than the plain-text label.
    expect(label.tagName.toLowerCase()).not.toBe("strong");
  });

  it("renders the empty state with the exact empty_reason text, not a blank chart", () => {
    const { container } = render(<DataChart block={emptyBlock} />);

    expect(screen.getByText("No shows matched this search.")).toBeInTheDocument();
    expect(screen.getByRole("figure", { name: emptyBlock.title })).toBeInTheDocument();
    // No plot was attempted.
    expect(container.querySelector(".recharts-wrapper")).not.toBeInTheDocument();
  });

  it("renders a safe fallback for a malformed columns array, never throwing", () => {
    const malformedColumns = withOverride({
      title: "Malformed columns example",
      columns: [{ key: "value", label: "Shows", type: "quantitative" }]
    });

    expect(() => render(<DataChart block={malformedColumns} />)).not.toThrow();
    expect(screen.getByText("Malformed columns example")).toBeInTheDocument();
    expect(screen.getByText(/unexpected shape/i)).toBeInTheDocument();
  });

  it("renders a safe fallback for a row with a non-numeric value, never throwing", () => {
    const malformedRow = withOverride({
      title: "Malformed row example",
      rows: [
        { label: "Winterland", value: 12 },
        { label: "Fillmore West", value: "not-a-number" as unknown as number }
      ]
    });

    expect(() => render(<DataChart block={malformedRow} />)).not.toThrow();
    expect(screen.getByText("Malformed row example")).toBeInTheDocument();
    expect(screen.getByText(/unexpected shape/i)).toBeInTheDocument();
  });

  it("truncates a long category label on the axis tick but shows it in full in the tooltip and table", async () => {
    const user = userEvent.setup();
    const { container } = render(<DataChart block={longLabelBlock} />);
    const fullLabel = "The Fillmore East, New York City, New York";

    const yLabels = yTickLabels(container);
    expect(within(yLabels).queryByText(fullLabel)).not.toBeInTheDocument();
    // A truncated version (ellipsis) is present instead.
    expect(yLabels.textContent).toContain("…");
    expect(yLabels.textContent).not.toBe(fullLabel);

    // The tooltip always shows the full label.
    focusFirstDataPoint(container);
    const tooltip = container.querySelector(".data-chart-tooltip") as HTMLElement;
    expect(
      within(tooltip).getByText(
        (_content, node) => node?.tagName.toLowerCase() === "p" && node.textContent === `Venue: ${fullLabel}`
      )
    ).toBeInTheDocument();

    // The table always shows the full label too.
    const tableTab = screen.getByRole("button", { name: /view as table/i });
    await user.click(tableTab);
    const table = screen.getByRole("table");
    expect(within(table).getByText(fullLabel)).toBeInTheDocument();
  });

  it("has an accessible name matching block.title and every row's value in the table, reachable via keyboard", async () => {
    const user = userEvent.setup();
    render(<DataChart block={rankedBlock} />);

    const figure = screen.getByRole("figure", { name: rankedBlock.title });
    expect(figure).toBeInTheDocument();

    const tableTab = screen.getByRole("button", { name: /view as table/i });
    tableTab.focus();
    expect(tableTab).toHaveFocus();
    await user.keyboard("{Enter}");

    const table = screen.getByRole("table");
    for (const row of rankedBlock.rows) {
      expect(within(table).getByText(String(row.label))).toBeInTheDocument();
      expect(within(table).getByText(String(row.value))).toBeInTheDocument();
    }
  });

  it("renders bars at their final, data-driven geometry immediately (isAnimationActive={false}, not an in-progress entrance frame)", () => {
    const { container } = render(<DataChart block={rankedBlock} />);

    // recharts' bar-entrance animation interpolates from a zero-size start;
    // with isAnimationActive left enabled, a synchronous render (no timers
    // advanced) shows an element with no computed width/height at all. With
    // it explicitly disabled, the bar renders its real, final geometry on
    // the very first synchronous render -- verified directly against this
    // component (see task-2-report.md) by comparing isAnimationActive=true
    // vs false render output for the same data.
    const bars = Array.from(container.querySelectorAll(".recharts-bar-rectangle path"));
    expect(bars.length).toBe(rankedBlock.rows.length);
    const widths = bars.map((bar) => Number(bar.getAttribute("width")));
    widths.forEach((width) => expect(Number.isFinite(width) && width > 0).toBe(true));
    // Widths are proportional to each row's value (12, 9, 7) -- the largest
    // value's bar must be the widest -- which is only true once the
    // interpolation has resolved to its final frame.
    expect(widths[0]).toBeGreaterThan(widths[1]);
    expect(widths[1]).toBeGreaterThan(widths[2]);

    // The Tooltip is also configured with isAnimationActive={false}: it
    // shows its full content on the very first synchronous focus event
    // rather than an intermediate (hidden/fading) frame.
    focusFirstDataPoint(container);
    const tooltipWrapper = container.querySelector(".recharts-tooltip-wrapper") as HTMLElement;
    expect(tooltipWrapper.style.visibility).toBe("visible");
    expect(within(tooltipWrapper).getByText("12")).toBeInTheDocument();
  });

  it("renders every row's label at a realistic (20-row) categorical row count, not just a handful", () => {
    const { container } = render(<DataChart block={manyRowsBlock} />);

    const yLabels = yTickLabels(container);
    for (const row of manyRowsBlock.rows) {
      expect(within(yLabels).getByText(String(row.label))).toBeInTheDocument();
    }
  });

  it("shows a visible top-N-of-M caption when rows were excluded, and nothing when none were", () => {
    const { container: withExclusions } = render(<DataChart block={rankedBlock} />);
    const detail = withExclusions.querySelector(".data-chart-coverage-detail");
    expect(detail).toBeInTheDocument();
    expect(detail?.textContent).toBe("Top 3 of 5 venues");

    const { container: withoutExclusions } = render(<DataChart block={yearBlock} />);
    expect(withoutExclusions.querySelector(".data-chart-coverage-detail")).not.toBeInTheDocument();
  });

  it("renders block.metric_label as a visible caption, not only in the hidden description, the tooltip, or the table", () => {
    const { container } = render(<DataChart block={rankedBlock} />);

    const caption = container.querySelector(".data-chart-metric-label");
    expect(caption).toBeInTheDocument();
    expect(caption).not.toHaveClass("visually-hidden");
    expect(caption?.textContent).toBe(rankedBlock.metric_label);
  });

  it("renders block.note as visible text when present, and renders no empty note element when it is absent", () => {
    const withNote = withOverride({
      aggregation_id: "agg-with-note",
      note: "Counts every show with a known setlist."
    });
    const { container: withNoteContainer } = render(<DataChart block={withNote} />);
    expect(within(withNoteContainer).getByText("Counts every show with a known setlist.")).toBeInTheDocument();

    // rankedBlock.note is null -- no stray empty <p> should be rendered.
    const { container: withoutNoteContainer } = render(<DataChart block={rankedBlock} />);
    expect(withoutNoteContainer.querySelector(".unit-note")).not.toBeInTheDocument();
  });

  it("renders a safe fallback for a null row, never throwing", () => {
    const nullRow = withOverride({
      title: "Null row example",
      rows: [{ label: "Winterland", value: 12 }, null as unknown as { label: string; value: number }]
    });

    expect(() => render(<DataChart block={nullRow} />)).not.toThrow();
    expect(screen.getByText("Null row example")).toBeInTheDocument();
    expect(screen.getByText(/unexpected shape/i)).toBeInTheDocument();
  });

  it("renders block.title as a heading element (not a figcaption), participating in the page's heading outline", () => {
    render(<DataChart block={rankedBlock} />);
    const heading = screen.getByRole("heading", { name: rankedBlock.title });
    expect(heading.tagName.toLowerCase()).toBe("h2");
  });
});
