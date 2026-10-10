// The grid: two lists and where each pair meets. The model chose the lists,
// their order, what opens first, the cells to point at and the words; every
// cell value comes from the library. Strength is cream only (gold is for
// listen controls, which arrive with the cell interactions).
import { useMemo, useState } from "react";
import { CardHeading, MoreAbout } from "./components";
import type { GridBlock } from "./types";
import "./Grid.css";

// Cell strength scales to the block's own maximum, so the strongest cell is
// always the brightest. Past `light` the cream is bright enough that the text
// flips to dark ink.
export function cellFill(value: number | null | undefined, max: number): { alpha: number; light: boolean } {
  if (!value || max <= 0) return { alpha: 0, light: false };
  const alpha = Math.round((0.08 + 0.82 * Math.min(1, value / max)) * 100) / 100;
  return { alpha, light: alpha > 0.55 };
}

const UNIT = { shows: "shows", minutes: "min" } as const;

export function Grid({ block, onFollowUp }: { block: GridBlock; onFollowUp?: (question: string) => void }) {
  const [open, setOpen] = useState(false);
  const canFold = block.open_rows != null && block.open_rows > 0 && block.open_rows < block.rows.length;
  const visible = useMemo(
    () => (open || !canFold ? block.rows : block.rows.slice(0, block.open_rows ?? undefined)),
    [open, canFold, block.rows, block.open_rows],
  );
  const rowsLabel = block.row_kind === "show" ? "nights" : "songs";
  const columnsLabel = block.column_kind === "year" ? "years" : "songs";
  const hasHighlight = block.rows.some((row) => (row.cells ?? []).some((cell) => cell.highlight));
  return (
    <article className="grid-card">
      <header className="grid-head">
        <div className="grid-eyebrow">
          <span className="k">Grid</span>
          <span className="grid-fact">
            {block.rows.length} {rowsLabel} · {block.columns.length} {columnsLabel} ·{" "}
            {block.measure === "minutes" ? "minutes played" : "shows per year"}
          </span>
        </div>
        {block.title && <CardHeading className="grid-headline">{block.title}</CardHeading>}
        {block.note && <p className="grid-note">{block.note}</p>}
      </header>
      <div className="grid-frame" role="region" tabIndex={0} aria-label={block.title ?? `Grid of ${block.rows.length} ${rowsLabel} by ${block.columns.length} ${columnsLabel}`}>
        <table className={`grid-table grid-${block.column_kind}`}>
          <thead>
            <tr>
              <td />
              {block.columns.map((column) => (
                <th
                  key={column.id}
                  scope="col"
                  aria-label={column.sub ?? column.label}
                  className={block.column_kind === "song" ? "is-vertical" : undefined}
                >
                  {column.label}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {visible.map((row) => (
              <tr key={row.id}>
                <th scope="row">
                  {row.label}
                  {(row.sub || row.total != null) && (
                    <span className="grid-sub">{row.sub ?? `${row.total} ${UNIT[block.measure]}`}</span>
                  )}
                </th>
                {(row.cells ?? []).map((cell, index) => {
                  const column = block.columns[index];
                  if (!column) return null;
                  const where = `${row.label}, ${column.sub ?? column.label}`;
                  const mark = cell.highlight ? " is-highlight" : "";
                  const noted = cell.highlight ? (cell.note ? `. ${cell.note}` : ", worth a listen") : "";
                  if (cell.state === "none")
                    return <td key={column.id} className="is-none" aria-label={`${where}: not played`} />;
                  if (cell.state === "unknown")
                    return (
                      <td key={column.id} className="is-unknown" aria-label={`${where}: not matched yet`}>
                        ?
                      </td>
                    );
                  if (cell.state === "no_length")
                    return (
                      <td
                        key={column.id}
                        className={`is-dot${mark}`}
                        aria-label={`${where}: played, length not known${noted}`}
                      />
                    );
                  const fill = cellFill(cell.value, block.max_value);
                  return (
                    <td
                      key={column.id}
                      className={`${fill.light ? "is-light" : ""}${mark}`.trim() || undefined}
                      style={{ background: `rgba(var(--grid-cell), ${fill.alpha})` }}
                      aria-label={`${where}: ${cell.value} ${UNIT[block.measure]}${noted}`}
                    >
                      {cell.value}
                      {cell.passes > 1 && <span className="grid-passes">{cell.passes}</span>}
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {canFold && (
        <button type="button" className="grid-more" onClick={() => setOpen((value) => !value)} aria-expanded={open}>
          {open ? `Show the first ${block.open_rows}` : `Show all ${block.rows.length}`}
        </button>
      )}
      <GridLegend block={block} hasHighlight={hasHighlight} />
      {block.coverage && (
        <aside className="grid-aside">
          <span className="k">Coverage</span>
          <p>{block.coverage}</p>
        </aside>
      )}
      {onFollowUp && <MoreAbout topics={block.follow_ups} onFollowUp={onFollowUp} />}
    </article>
  );
}

// The legend names only the marks this grid uses.
function GridLegend({ block, hasHighlight }: { block: GridBlock; hasHighlight: boolean }) {
  const states = new Set(block.rows.flatMap((row) => (row.cells ?? []).map((cell) => cell.state)));
  return (
    <div className="grid-legend">
      <span>
        <i className="grid-swatch ramp" />
        {block.measure === "minutes" ? "minutes" : "shows that year"}
      </span>
      {states.has("none") && (
        <span>
          <i className="grid-swatch dash" />
          not played
        </span>
      )}
      {states.has("no_length") && (
        <span>
          <i className="grid-swatch dot" />
          played, length not known
        </span>
      )}
      {states.has("unknown") && (
        <span>
          <i className="grid-swatch q">?</i>
          not matched yet
        </span>
      )}
      {hasHighlight && (
        <span>
          <i className="grid-swatch ring" />
          worth a listen
        </span>
      )}
    </div>
  );
}
