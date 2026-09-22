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
import { Drawer } from "./App";

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

function truncateLabel(value: string, maxLength: number = MAX_TICK_LABEL_LENGTH): string {
  if (value.length <= maxLength) return value;
  return `${value.slice(0, Math.max(0, maxLength - 1)).trimEnd()}…`;
}

// The description composed for `aria-describedby` — same for the plotted
// figure and the empty-state figure, since both carry the same block-level
// facts (metric, scope, total, exclusions).
function chartDescription(block: DataChartBlock): string {
  const excluded = block.excluded_count > 0 ? `, ${block.excluded_count} more not shown` : "";
  return `${block.metric_label}. ${block.scope_note}. Total ${block.total}${excluded}.`;
}

type DataChartColumn = DataChartBlock["columns"][number];
type DataChartRow = { [key: string]: unknown };

export function DataChart({ block }: { block: DataChartBlock }) {
  const titleId = useId();
  const descId = useId();

  // Structural guards — defense in depth against a payload that somehow
  // violates the contract Batch 2 already guarantees server-side. Render a
  // safe, clearly-labeled fallback, never throw.
  if (block.chart !== "bar") {
    return <UnavailableChart block={block} reason="Stacked charts aren't available yet." />;
  }
  if (block.columns.length !== 2) {
    return <UnavailableChart block={block} reason="This chart's data is in an unexpected shape." />;
  }
  const dimensionColumn = block.columns.find((column) => column.key !== "value");
  if (!dimensionColumn) {
    return <UnavailableChart block={block} reason="This chart's data is in an unexpected shape." />;
  }
  const rows = block.rows.filter(
    (row) => typeof row[block.y_field] === "number" && Number.isFinite(row[block.y_field] as number)
  );
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

  return (
    <figure className="data-chart-figure" aria-labelledby={titleId} aria-describedby={descId}>
      <figcaption id={titleId} className="data-chart-title">
        {block.title}
      </figcaption>
      <p id={descId} className="visually-hidden">
        {chartDescription(block)}
      </p>
      {block.note && <p className="unit-note">{block.note}</p>}
      <ResponsiveContainer width="100%" height={320} className="data-chart-plot">
        <BarChart data={rows} layout={isVertical ? "horizontal" : "vertical"} margin={{ top: 8, right: 16, bottom: 8, left: 8 }}>
          <CartesianGrid stroke="var(--hair)" strokeDasharray="0" horizontal={isVertical} vertical={!isVertical} />
          {isVertical ? (
            <>
              <XAxis
                dataKey={block.x_field}
                type="category"
                tickLine={false}
                axisLine={{ stroke: "var(--hair)" }}
                tick={{ fill: "var(--muted)" }}
              />
              <YAxis type="number" allowDecimals={false} tickLine={false} axisLine={{ stroke: "var(--hair)" }} tick={{ fill: "var(--muted)" }} />
            </>
          ) : (
            <>
              <XAxis type="number" allowDecimals={false} tickLine={false} axisLine={{ stroke: "var(--hair)" }} tick={{ fill: "var(--muted)" }} />
              <YAxis
                dataKey={block.x_field}
                type="category"
                tickLine={false}
                axisLine={{ stroke: "var(--hair)" }}
                tick={{ fill: "var(--muted)" }}
                tickFormatter={(value) => truncateLabel(String(value))}
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
            dataKey={block.y_field}
            fill="var(--violet)"
            isAnimationActive={false}
            // Rounded at the data end, square at the baseline. For
            // layout="horizontal" (our orientation="vertical") the data end
            // is the top of each bar: round the top corners. For
            // layout="vertical" (our orientation="horizontal") the data end
            // is the right of each bar: round the right corners. RectRadius
            // order is [top-left, top-right, bottom-right, bottom-left].
            radius={isVertical ? [4, 4, 0, 0] : [0, 4, 4, 0]}
            maxBarSize={24}
          />
        </BarChart>
      </ResponsiveContainer>
      <p className="coverage-note">{block.scope_note}</p>
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
// the shape this batch knows how to plot (a stacked chart, a malformed
// column/row shape). Never implies the visitor did something wrong.
function UnavailableChart({ block, reason }: { block: DataChartBlock; reason: string }) {
  return (
    <div className="data-chart-unavailable" role="note">
      <p className="data-chart-title">{block.title}</p>
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
      <figcaption id={titleId} className="data-chart-title">
        {block.title}
      </figcaption>
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
          <tr key={`${String(row[block.x_field])}-${index}`}>
            <td>{String(row[block.x_field])}</td>
            <td>{(row[block.y_field] as number).toLocaleString()}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
