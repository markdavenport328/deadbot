// The grid's client-side arithmetic: sorting rows by a column and summarising
// a column. Every value comes from the block the server filled; nothing here
// invents a fact.
import type { GridBlock } from "./types";

export type GridRow = GridBlock["rows"][number];
export type GridCellData = NonNullable<GridRow["cells"]>[number];
export type Selection = { row: number; column: number }[];

// Rows ordered by one column's value, strongest first (or weakest first).
// Rows with no value in that column keep the model's order after the rest.
export function sortRows(rows: GridRow[], columnIndex: number, direction: "desc" | "asc" = "desc"): GridRow[] {
  const valueOf = (row: GridRow): number | null => {
    const cell = row.cells?.[columnIndex];
    return cell && cell.state === "value" && cell.value != null ? cell.value : null;
  };
  const indexed = rows.map((row, position) => ({ row, position, value: valueOf(row) }));
  indexed.sort((a, b) => {
    if (a.value == null && b.value == null) return a.position - b.position;
    if (a.value == null) return 1;
    if (b.value == null) return -1;
    if (a.value !== b.value) return direction === "desc" ? b.value - a.value : a.value - b.value;
    return a.position - b.position;
  });
  return indexed.map((entry) => entry.row);
}

type Extreme = { rowLabel: string; value: number };

// How many rows meet this column, and where it runs longest and shortest.
export function columnSummary(
  block: GridBlock,
  columnIndex: number,
): { played: number; longest?: Extreme; shortest?: Extreme } {
  let played = 0;
  let longest: Extreme | undefined;
  let shortest: Extreme | undefined;
  for (const row of block.rows) {
    const cell = row.cells?.[columnIndex];
    if (!cell || (cell.state !== "value" && cell.state !== "no_length")) continue;
    played += 1;
    if (cell.state !== "value" || cell.value == null) continue;
    if (!longest || cell.value > longest.value) longest = { rowLabel: row.label, value: cell.value };
    if (!shortest || cell.value < shortest.value) shortest = { rowLabel: row.label, value: cell.value };
  }
  return { played, ...(longest ? { longest } : {}), ...(shortest ? { shortest } : {}) };
}

// "May 11, 1972 · Rotterdam" reads as a date and a city; a song row has only a date part.
export function rowParts(row: GridRow): { date: string; city: string | null } {
  const [date, ...rest] = row.label.split(" · ");
  return { date, city: rest.length > 0 ? rest.join(" · ") : null };
}

// The day the row's show was played, read from the show id ("gd-1972-05-11").
export function rowShowDate(row: GridRow): string | null {
  return row.id.match(/\d{4}-\d{2}-\d{2}/)?.[0] ?? null;
}

export type GridChange = { addColumn?: string; removeColumn?: string; removeRow?: string };

// The grid as the visitor now sees it, with one change applied: rows and
// columns in the order on screen, so the server redraws the same grid.
function reshapedSpec(block: GridBlock, change: GridChange): GridBlock["spec"] {
  const columnIds = block.columns.map((column) => column.id).filter((id) => id !== change.removeColumn);
  if (change.addColumn && !columnIds.includes(change.addColumn)) columnIds.push(change.addColumn);
  return {
    row_kind: block.spec.row_kind,
    row_ids: block.rows.map((row) => row.id).filter((id) => id !== change.removeRow),
    column_kind: block.spec.column_kind,
    column_ids: columnIds,
  };
}

// Ask the server to redraw this grid with one list added or removed. The
// headline and note go along and come back as they were; the cells, tracks
// and suggestions are filled fresh from the library.
export async function reshapeGrid(block: GridBlock, change: GridChange): Promise<GridBlock> {
  const result = await fetch("/api/grid", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      spec: reshapedSpec(block, change),
      title: block.title ?? null,
      note: block.note ?? null,
      open_rows: block.open_rows ?? null,
    }),
  });
  if (!result.ok) throw new Error(`The grid could not be reshaped (${result.status}).`);
  return (await result.json()) as GridBlock;
}
