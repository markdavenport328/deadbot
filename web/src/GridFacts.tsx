// One cell's facts as plain sentences: the song and night (or record, or
// year), the place, then one line about the passage itself. The hover card and
// the detail bar both draw this, so a tap carries everything a hover does.
// Every fact is read from the cell the server filled; the model's note follows
// in its own words.
import { rowParts } from "./grid-actions";
import type { GridBlock } from "./types";

type Cell = NonNullable<GridBlock["rows"][number]["cells"]>[number];
type Row = GridBlock["rows"][number];
type Column = GridBlock["columns"][number];

// What a grid's rows are, in the words the page uses for them.
export const ROW_WORDS = {
  song: { many: "songs", measure: "shows per year", legend: "shows that year", none: "not played" },
  show: { many: "nights", measure: "minutes played", legend: "minutes", none: "not played" },
  release: { many: "records", measure: "minutes on the record", legend: "minutes on the record", none: "not on the record" },
  guest: { many: "guests", measure: "shows sat in", legend: "shows sat in", none: "none that year" },
} as const;

const SOURCE = {
  release: "timed from the official release",
  tape: "timed from the archive tape",
  mixed: "timed from the official release and the archive tape",
} as const;

function plural(count: number, one: string, many = `${one}s`): string {
  return `${count} ${count === 1 ? one : many}`;
}

// "Set 2, after Drums, into Sugar Magnolia."
function placement(cell: Cell): string | null {
  const parts = [cell.set_label, cell.segue_from ? `after ${cell.segue_from}` : null, cell.segue_into ? `into ${cell.segue_into}` : null].filter(Boolean);
  return parts.length > 0 ? `${parts.join(", ")}.` : null;
}

// "Dark Star · May 11, 1972", "Dark Star · Dick's Picks 36", "Bruce Hornsby · 1989".
export function cellTitle(block: GridBlock, row: Row, column: Column): string {
  if (block.row_kind === "show") return `${column.label} · ${rowParts(row).date}`;
  if (block.row_kind === "release") return `${column.label} · ${row.label}`;
  return `${row.label} · ${column.sub ?? column.label}`;
}

export function sentence(block: GridBlock, cell: Cell, yearLabel: string): string {
  if (block.row_kind === "guest") {
    if (cell.state === "none") return "Did not sit in that year.";
    if (cell.state === "unknown") return "Not matched yet.";
    return `Sat in on ${plural(cell.value ?? 0, "show")} that year.`;
  }
  if (block.row_kind === "song") {
    if (cell.state === "none")
      return cell.of_shows != null ? `Not played in the ${cell.of_shows} shows with a setlist that year.` : "Not played that year.";
    if (cell.state === "unknown") return "Not matched yet.";
    return cell.of_shows != null
      ? `On ${cell.value ?? 0} of the ${cell.of_shows} shows with a setlist that year.`
      : `On ${plural(cell.value ?? 0, "show")} in ${yearLabel}.`;
  }
  if (block.row_kind === "release") {
    if (cell.state === "none") return "Not on this record.";
    if (cell.state === "unknown") return "Not matched yet: a track on this record that names no song mentions it.";
    const tracks = cell.passes > 1 ? `across ${cell.passes} tracks` : "on 1 track";
    if (cell.state === "no_length") return `On the record ${tracks}, length not known.`;
    return `${plural(cell.value ?? 0, "minute")} on the record, ${tracks}.`;
  }
  if (cell.state === "none") return "Not played that night.";
  if (cell.state === "unknown") return "Not matched to a recording yet.";
  if (cell.state === "no_length") return [placement(cell), "Length not known."].filter(Boolean).join(" ");
  const passes = cell.passes > 1 ? ` in ${cell.passes} passes` : "";
  const source = cell.length_source ? `, ${SOURCE[cell.length_source]}` : "";
  return [placement(cell), `${plural(cell.value ?? 0, "minute")}${passes}${source}.`].filter(Boolean).join(" ");
}

export function GridFacts({ block, rowIndex, columnIndex }: { block: GridBlock; rowIndex: number; columnIndex: number }) {
  const row = block.rows[rowIndex];
  const column = block.columns[columnIndex];
  const cell = row?.cells?.[columnIndex];
  if (!row || !column || !cell) return null;
  const yearLabel = column.sub ?? column.label;
  const place =
    block.row_kind === "show" ? [row.sub, rowParts(row).city].filter(Boolean).join(", ") : block.row_kind === "release" ? (row.sub ?? "") : "";
  return (
    <div className="grid-facts">
      <p className="grid-facts-title">{cellTitle(block, row, column)}</p>
      {place && <p className="grid-facts-place">{place}</p>}
      <p className="grid-facts-line">{sentence(block, cell, yearLabel)}</p>
      {cell.note && <p className={`grid-facts-note${cell.highlight ? " is-pulled" : ""}`}>{cell.note}</p>}
    </div>
  );
}
