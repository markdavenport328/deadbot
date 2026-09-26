import { useId } from "react";
import {
  Bar,
  BarChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
  type TooltipContentProps
} from "recharts";
import type { ExperienceBlock } from "./types";
import { CardHeading, Drawer } from "./components";

// `./types` re-exports several block types individually (ShowUnitBlock,
// AlbumUnitBlock, ...) but not this one -- it only appears as a member of
// the ExperienceBlock union. Deriving it here via its discriminant keeps
// this file's only change to ./types-derived surface to a type-only import,
// without hand-editing the shared types.ts file (out of this task's scope
// per the plan; see task-2-report.md).
export type DataChartBlock = Extract<ExperienceBlock, { type: "data_chart" }>;

// Bounded character count for a plotted category-axis tick. The tooltip and
// the table always show the full, untruncated label — only the plotted tick
// text is ever shortened.
const MAX_TICK_LABEL_LENGTH = 18;

// The horizontal (ranked/categorical) layout's plot height scales with row
// count so every row gets a readable tick label -- a fixed height forced
// recharts' tick-skipping to drop most labels at realistic row counts (15-50
// rows). The vertical (temporal/year-series) layout keeps a fixed height:
// year-series row counts are naturally bounded (a handful of years), so
// there's nothing to scale for.
const VERTICAL_CHART_HEIGHT = 320;
const EMBEDDED_CHART_HEIGHT = 220;
const HORIZONTAL_ROW_HEIGHT = 28;
const HORIZONTAL_CHART_BASE_HEIGHT = 48;
const HORIZONTAL_CHART_MIN_HEIGHT = 240;

function horizontalChartHeight(rowCount: number): number {
  return Math.max(HORIZONTAL_CHART_MIN_HEIGHT, rowCount * HORIZONTAL_ROW_HEIGHT + HORIZONTAL_CHART_BASE_HEIGHT);
}

function truncateLabel(value: string, maxLength: number = MAX_TICK_LABEL_LENGTH): string {
  if (value.length <= maxLength) return value;
  return `${value.slice(0, Math.max(0, maxLength - 1)).trimEnd()}…`;
}

// The description composed for `aria-describedby` — same for the plotted
// figure and the empty-state figure, since both carry the same block-level
// facts (metric, total, exclusions).
function chartDescription(block: DataChartBlock): string {
  const excluded = block.excluded_count > 0 ? `, ${block.excluded_count} more not shown` : "";
  return `${block.metric_label}. Total ${block.total}${excluded}.`;
}

type DataChartColumn = DataChartBlock["columns"][number];
type DataChartRow = { [key: string]: unknown };

// A plain, reasonable plural: the dimension column's label is always a
// count-friendly noun ("Venue", "Year", "Song"), never irregular, so a
// trailing "s" (skipped when the label already ends in one) is sufficient.
function pluralizeLabel(label: string): string {
  const lower = label.toLowerCase();
  return lower.endsWith("s") ? lower : `${lower}s`;
}

// The visible (sighted-reader) counterpart to the hidden `excluded_count`
// fact already carried in the figure's aria-describedby text: "Top 5 of 24
// venues" whenever some rows were left out of the plot. Renders nothing when
// nothing was excluded, so a complete result doesn't say "Top 7 of 7".
function CoverageDetail({ block, dimensionLabel, shownCount }: { block: DataChartBlock; dimensionLabel: string; shownCount: number }) {
  if (block.excluded_count <= 0) return null;
  const totalCount = shownCount + block.excluded_count;
  return (
    <p className="data-chart-coverage-detail">
      Top {shownCount} of {totalCount} {pluralizeLabel(dimensionLabel)}
    </p>
  );
}

// ``embedded`` draws the chart inside a card that already names its subject:
// no heading of its own, and a shorter plot.
export function DataChart({ block, embedded = false }: { block: DataChartBlock; embedded?: boolean }) {
  const titleId = useId();
  const descId = useId();

  // Structural guards — defense in depth against a payload that somehow
  // violates the contract the server already guarantees. Render a safe,
  // clearly-labeled fallback, never throw.
  if (block.columns.length !== 2) {
    return <UnavailableChart block={block} reason="This chart's data is in an unexpected shape." />;
  }
  const dimensionColumn = block.columns.find((column) => column.key !== "value");
  if (!dimensionColumn) {
    return <UnavailableChart block={block} reason="This chart's data is in an unexpected shape." />;
  }
  if (block.rows.some((row: unknown) => row === null || typeof row !== "object")) {
    return <UnavailableChart block={block} reason="This chart's data is in an unexpected shape." />;
  }
  const rows = block.rows.filter((row) => typeof row.value === "number" && Number.isFinite(row.value as number));
  if (rows.length !== block.rows.length) {
    // Some row failed the finite-number check — this should never happen
    // given Batch 2's server-side validation; render what's safe rather
    // than silently dropping rows the visitor can't see were dropped.
    return <UnavailableChart block={block} reason="This chart's data is in an unexpected shape." />;
  }

  if (rows.length === 0) {
    return <EmptyChart block={block} titleId={titleId} descId={descId} />;
  }

  // orientation="vertical" -> bars grow upward from a shared baseline (a
  // year series) -> recharts' own (oppositely-named) layout="horizontal".
  // orientation="horizontal" -> bars grow rightward, one per row (a ranked
  // category) -> recharts' layout="vertical".
  const isVertical = block.orientation === "vertical";
  const plotHeight = isVertical ? (embedded ? EMBEDDED_CHART_HEIGHT : VERTICAL_CHART_HEIGHT) : horizontalChartHeight(rows.length);

  return (
    <figure className={embedded ? "data-chart-figure embedded" : "data-chart-figure"} aria-labelledby={titleId} aria-describedby={descId}>
      {embedded ? (
        <figcaption id={titleId} className="visually-hidden">{block.title}</figcaption>
      ) : (
        <CardHeading id={titleId} className="data-chart-title">
          {block.title}
        </CardHeading>
      )}
      <p id={descId} className="visually-hidden">
        {chartDescription(block)}
      </p>
      {block.note && <p className="unit-note">{block.note}</p>}
      {/* The structural fact of what the bars count ("Performances", "Shows",
          ...) -- always visible, not just in the hover tooltip, the
          collapsed table, or the screen-reader-only description above. This
          is server-derived, never model-chosen, so it stays present
          regardless of what the model's title/note choose to say. */}
      <p className="data-chart-metric-label">{block.metric_label}</p>
      <ResponsiveContainer width="100%" height={plotHeight} className="data-chart-plot">
        <BarChart data={rows} layout={isVertical ? "horizontal" : "vertical"} margin={{ top: 8, right: 16, bottom: 8, left: 8 }}>
          <CartesianGrid stroke="var(--hair)" strokeDasharray="0" horizontal={isVertical} vertical={!isVertical} />
          {isVertical ? (
            <>
              <XAxis
                dataKey={dimensionColumn.key}
                type="category"
                tickLine={false}
                axisLine={{ stroke: "var(--hair)" }}
                tick={{ fill: "var(--muted)" }}
              />
              <YAxis
                type="number"
                allowDecimals={false}
                tickLine={false}
                axisLine={{ stroke: "var(--hair)" }}
                tick={{ fill: "var(--muted)" }}
                tickFormatter={(value) => Number(value).toLocaleString()}
              />
            </>
          ) : (
            <>
              <XAxis
                type="number"
                allowDecimals={false}
                tickLine={false}
                axisLine={{ stroke: "var(--hair)" }}
                tick={{ fill: "var(--muted)" }}
                tickFormatter={(value) => Number(value).toLocaleString()}
              />
              <YAxis
                dataKey={dimensionColumn.key}
                type="category"
                tickLine={false}
                axisLine={{ stroke: "var(--hair)" }}
                tick={{ fill: "var(--muted)" }}
                tickFormatter={(value) => truncateLabel(String(value))}
                interval={0}
                width={120}
              />
            </>
          )}
          <Tooltip
            content={<ChartTooltip dimensionLabel={dimensionColumn.label} valueLabel={block.metric_label} />}
            isAnimationActive={false}
            cursor={{ fill: "var(--hair)" }}
          />
          <Bar
            dataKey="value"
            fill="var(--muted)"
            isAnimationActive={false}
            // Rounded at the data end, square at the baseline. For
            // layout="horizontal" (our orientation="vertical") the data end
            // is the top of each bar: round the top corners. For
            // layout="vertical" (our orientation="horizontal") the data end
            // is the right of each bar: round the right corners. RectRadius
            // order is [top-left, top-right, bottom-right, bottom-left].
            // 2px matches --r, the design system's corner radius.
            radius={isVertical ? [2, 2, 0, 0] : [0, 2, 2, 0]}
            maxBarSize={24}
          />
        </BarChart>
      </ResponsiveContainer>
      <CoverageDetail block={block} dimensionLabel={dimensionColumn.label} shownCount={rows.length} />
      <Drawer
        tabs={[
          {
            id: "table",
            label: "View as table",
            count: rows.length,
            content: <DataChartTable block={block} dimensionColumn={dimensionColumn} rows={rows} />
          }
        ]}
        initialOpen={null}
      />
    </figure>
  );
}

// A limitation, not an error: rendered whenever the payload doesn't match
// the shape this batch knows how to plot (a malformed column/row shape).
// Never implies the visitor did something wrong.
function UnavailableChart({ block, reason }: { block: DataChartBlock; reason: string }) {
  return (
    <div className="data-chart-unavailable" role="note">
      <CardHeading className="data-chart-title">{block.title}</CardHeading>
      <p className="data-chart-unavailable-reason">{reason}</p>
    </div>
  );
}

// A valid, well-shaped result that simply has no rows. Same accessible
// figure/description pattern as the plotted chart, so assistive tech treats
// it consistently either way.
function EmptyChart({ block, titleId, descId }: { block: DataChartBlock; titleId: string; descId: string }) {
  return (
    <figure className="data-chart-figure data-chart-empty" aria-labelledby={titleId} aria-describedby={descId}>
      <CardHeading id={titleId} className="data-chart-title">
        {block.title}
      </CardHeading>
      <p id={descId} className="visually-hidden">
        {chartDescription(block)}
      </p>
      <p className="data-chart-empty-reason">{block.empty_reason ?? "No data is available for this chart."}</p>
    </figure>
  );
}

// Per-mark hover/focus content. Value leads (bold, high-contrast), the
// dimension label is secondary — inverted from a legend's hierarchy on
// purpose, since here the reader already has the series and wants the
// number. `label` is recharts' own categorical-axis value for the active
// row, always the untruncated raw value regardless of the plotted tick's
// truncation.
function ChartTooltip({
  active,
  payload,
  label,
  dimensionLabel,
  valueLabel
}: Partial<TooltipContentProps> & { dimensionLabel: string; valueLabel: string }) {
  if (!active || !payload || payload.length === 0) return null;
  const value = payload[0]?.value;
  if (typeof value !== "number") return null;
  return (
    <div className="data-chart-tooltip" role="tooltip">
      <p className="data-chart-tooltip-value">
        <strong>{value.toLocaleString()}</strong> {valueLabel}
      </p>
      <p className="data-chart-tooltip-label">
        {dimensionLabel}: {String(label)}
      </p>
    </div>
  );
}

// The authoritative keyboard-readable alternative to the plot — every row,
// in full, never truncated.
function DataChartTable({
  block,
  dimensionColumn,
  rows
}: {
  block: DataChartBlock;
  dimensionColumn: DataChartColumn;
  rows: DataChartRow[];
}) {
  return (
    <table className="data-chart-table">
      <caption className="visually-hidden">{block.title}, full data table</caption>
      <thead>
        <tr>
          <th scope="col">{dimensionColumn.label}</th>
          <th scope="col">{block.metric_label}</th>
        </tr>
      </thead>
      <tbody>
        {rows.map((row, index) => (
          <tr key={`${String(row[dimensionColumn.key])}-${index}`}>
            <td>{String(row[dimensionColumn.key])}</td>
            <td>{(row.value as number).toLocaleString()}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
