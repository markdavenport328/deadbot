// The grid: two lists and where each pair meets. The model chose the lists,
// their order, what opens first, the cells to point at and the words; every
// cell value comes from the library. Strength is cream only (gold is for
// listen controls, which arrive with the cell interactions).
import { Fragment, useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState, type KeyboardEvent, type MouseEvent, type ReactNode } from "react";
import { CardHeading, MoreAbout } from "./components";
import { GridFacts } from "./GridFacts";
import { columnSummary, rowParts, rowShowDate, sortRows, type GridRow, type Selection } from "./grid-actions";
import { toTrack } from "./listen-control";
import { usePlayer } from "./player";
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
const FOCUS_DELAY_MS = 250;

type Tip = { kind: "cell"; row: number; column: number } | { kind: "column"; column: number };

// A hover card is a mouse convenience; on touch a tap selects and the detail
// bar carries the same facts.
function canHover(): boolean {
  return typeof window.matchMedia !== "function" || !window.matchMedia("(hover: none)").matches;
}

function columnSentence(block: GridBlock, columnIndex: number): string {
  const { played, longest } = columnSummary(block, columnIndex);
  const total = block.rows.length;
  const isShow = block.row_kind === "show";
  const first = isShow ? `Played on ${played} of ${total} nights.` : `${played} of the ${total} songs were played that year.`;
  if (!longest) return first;
  const unit = block.measure === "minutes" ? "minutes" : "shows";
  const where = rowParts({ label: longest.rowLabel } as GridRow).date.replace(/,\s*\d{4}$/, "");
  return `${first} ${block.measure === "minutes" ? "Longest" : "Most"}: ${where}, ${longest.value} ${unit}.`;
}

// The question a selected cell sends, with the night and place written out.
function askAbout(block: GridBlock, selection: Selection): string | null {
  const named = selection.flatMap(({ row, column }) => {
    const cell = block.rows[row]?.cells?.[column];
    const col = block.columns[column];
    if (!cell || !col || (cell.state !== "value" && cell.state !== "no_length")) return [];
    const { date, city } = rowParts(block.rows[row]);
    return block.row_kind === "show"
      ? [{ subject: `the ${col.label} from ${date}`, place: city ? ` in ${city}` : "" }]
      : [{ subject: `${block.rows[row].label} in ${col.sub ?? col.label}`, place: "" }];
  });
  if (named.length === 0) return null;
  if (named.length === 1) return `Tell me about ${named[0].subject}${named[0].place}.`;
  return `Compare ${named[0].subject} and ${named[1].subject}.`;
}

export function Grid({ block, onFollowUp }: { block: GridBlock; onFollowUp?: (question: string) => void }) {
  const [open, setOpen] = useState(false);
  const [sortColumn, setSortColumn] = useState<number | null>(null);
  const [selection, setSelection] = useState<Selection>([]);
  const [setlists, setSetlists] = useState<ReadonlySet<string>>(new Set());
  const [focus, setFocus] = useState({ row: 0, column: 0 });
  const [tip, setTip] = useState<Tip | null>(null);
  const cellRefs = useRef(new Map<string, HTMLElement>());
  const anchorRef = useRef<HTMLElement | null>(null);
  const stageRef = useRef<HTMLDivElement>(null);
  const tipRef = useRef<HTMLDivElement>(null);
  const timer = useRef<number | undefined>(undefined);
  const byKeyboard = useRef(false);

  const canFold = block.open_rows != null && block.open_rows > 0 && block.open_rows < block.rows.length;
  const ordered = useMemo(() => (sortColumn == null ? block.rows : sortRows(block.rows, sortColumn, "desc")), [block.rows, sortColumn]);
  const visible = useMemo(
    () => (open || !canFold ? ordered : ordered.slice(0, block.open_rows ?? undefined)),
    [open, canFold, ordered, block.open_rows],
  );
  const indexOf = useMemo(() => new Map(block.rows.map((row, index) => [row, index])), [block.rows]);
  const rowsLabel = block.row_kind === "show" ? "nights" : "songs";
  const columnsLabel = block.column_kind === "year" ? "years" : "songs";
  const hasHighlight = block.rows.some((row) => (row.cells ?? []).some((cell) => cell.highlight));
  const lastColumn = block.columns.length - 1;
  const active = visible.some((row) => indexOf.get(row) === focus.row)
    ? focus
    : { row: visible.length > 0 ? (indexOf.get(visible[0]) ?? 0) : 0, column: 0 };

  // Whether the last input was the keyboard: focus from a click needs no card,
  // the detail bar already answers it.
  useEffect(() => {
    const key = () => (byKeyboard.current = true);
    const pointer = () => (byKeyboard.current = false);
    window.addEventListener("keydown", key, true);
    window.addEventListener("pointerdown", pointer, true);
    window.addEventListener("mousedown", pointer, true);
    return () => {
      window.removeEventListener("keydown", key, true);
      window.removeEventListener("pointerdown", pointer, true);
      window.removeEventListener("mousedown", pointer, true);
      window.clearTimeout(timer.current);
    };
  }, []);

  const hideTip = useCallback(() => {
    window.clearTimeout(timer.current);
    setTip(null);
  }, []);
  const showTip = useCallback((target: Tip, anchor: HTMLElement, delay: number) => {
    window.clearTimeout(timer.current);
    const show = () => {
      anchorRef.current = anchor;
      setTip(target);
    };
    if (delay > 0) timer.current = window.setTimeout(show, delay);
    else show();
  }, []);

  // Above the anchor, flipped below near the top edge, clamped inside the stage.
  useLayoutEffect(() => {
    const card = tipRef.current;
    const anchor = anchorRef.current;
    const stage = stageRef.current;
    if (!tip || !card || !anchor || !stage) return;
    const a = anchor.getBoundingClientRect();
    const s = stage.getBoundingClientRect();
    const width = card.offsetWidth;
    const height = card.offsetHeight;
    const left = Math.max(0, Math.min(a.left - s.left + a.width / 2 - width / 2, s.width - width));
    const above = a.top - s.top - height - 6;
    card.style.left = `${left}px`;
    card.style.top = `${above >= 0 ? above : a.bottom - s.top + 6}px`;
  }, [tip]);

  function select(row: number, column: number, additive: boolean) {
    setSelection((current) => {
      const at = current.findIndex((entry) => entry.row === row && entry.column === column);
      if (additive) {
        if (at >= 0) return current.filter((_, index) => index !== at);
        return current.length < 2 ? [...current, { row, column }] : [current[0], { row, column }];
      }
      return at >= 0 && current.length === 1 ? [] : [{ row, column }];
    });
  }

  function moveTo(position: number, column: number) {
    const row = visible[Math.max(0, Math.min(position, visible.length - 1))];
    if (!row) return;
    const rowIndex = indexOf.get(row) ?? 0;
    const col = Math.max(0, Math.min(column, lastColumn));
    setFocus({ row: rowIndex, column: col });
    cellRefs.current.get(`${rowIndex}:${col}`)?.focus();
  }

  function onCellKey(event: KeyboardEvent<HTMLElement>, rowIndex: number, column: number) {
    const position = visible.indexOf(block.rows[rowIndex]);
    switch (event.key) {
      case "ArrowRight": moveTo(position, column + 1); break;
      case "ArrowLeft": moveTo(position, column - 1); break;
      case "ArrowDown": moveTo(position + 1, column); break;
      case "ArrowUp": moveTo(position - 1, column); break;
      case "Home": moveTo(event.ctrlKey ? 0 : position, 0); break;
      case "End": moveTo(event.ctrlKey ? visible.length - 1 : position, lastColumn); break;
      case "Enter":
      case " ":
        select(rowIndex, column, event.shiftKey || event.metaKey || event.ctrlKey);
        break;
      case "Escape":
        setSelection([]);
        hideTip();
        break;
      default:
        return;
    }
    event.preventDefault();
  }

  function sortBy(column: number) {
    hideTip();
    setSortColumn((current) => (current === column ? null : column));
  }

  function toggleSetlist(id: string) {
    setSetlists((current) => {
      const next = new Set(current);
      if (!next.delete(id)) next.add(id);
      return next;
    });
  }

  const selected = new Set(selection.map((entry) => `${entry.row}:${entry.column}`));
  const tipCell = tip?.kind === "cell" ? { row: tip.row, column: tip.column } : null;

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
      <div className="grid-stage" ref={stageRef}>
        <div
          className="grid-frame"
          role="region"
          tabIndex={0}
          aria-label={block.title ?? `Grid of ${block.rows.length} ${rowsLabel} by ${block.columns.length} ${columnsLabel}`}
          onScroll={hideTip}
        >
          <table className={`grid-table grid-${block.column_kind}`} role="grid">
            <thead>
              <tr>
                <td role="presentation" />
                {block.columns.map((column, columnIndex) => {
                  const sorted = sortColumn === columnIndex;
                  const target: Tip = { kind: "column", column: columnIndex };
                  return (
                    <th
                      key={column.id}
                      scope="col"
                      role="columnheader"
                      aria-label={column.sub ?? column.label}
                      aria-sort={sorted ? "descending" : undefined}
                      className={`${block.column_kind === "song" ? "is-vertical" : ""}${sorted ? " is-sorted" : ""}`.trim() || undefined}
                    >
                      <button
                        type="button"
                        className="grid-sort"
                        aria-label={`Sort by ${column.sub ?? column.label}`}
                        onClick={() => sortBy(columnIndex)}
                        onMouseEnter={(event) => canHover() && showTip(target, event.currentTarget, 0)}
                        onMouseLeave={hideTip}
                        onFocus={(event) => byKeyboard.current && showTip(target, event.currentTarget, FOCUS_DELAY_MS)}
                        onBlur={hideTip}
                      >
                        {column.label}
                      </button>
                    </th>
                  );
                })}
              </tr>
            </thead>
            <tbody>
              {visible.map((row) => {
                const rowIndex = indexOf.get(row) ?? 0;
                const hasSetlist = (row.setlist ?? []).length > 0;
                const setlistOpen = hasSetlist && setlists.has(row.id);
                const rowName = (
                  <>
                    {row.label}
                    {(row.sub || row.total != null) && (
                      <span className="grid-sub">{row.sub ?? `${row.total} ${UNIT[block.measure]}`}</span>
                    )}
                  </>
                );
                return (
                  <Fragment key={row.id}>
                    <tr>
                      <th scope="row" role="rowheader">
                        {hasSetlist ? (
                          <button
                            type="button"
                            className="grid-row-toggle"
                            aria-label={`Open the setlist for ${rowParts(row).date}`}
                            aria-expanded={setlistOpen}
                            onClick={() => toggleSetlist(row.id)}
                          >
                            {rowName}
                          </button>
                        ) : (
                          rowName
                        )}
                      </th>
                      {(row.cells ?? []).map((cell, index) => {
                        const column = block.columns[index];
                        if (!column) return null;
                        const where = `${row.label}, ${column.sub ?? column.label}`;
                        const noted = cell.highlight ? (cell.note ? `. ${cell.note}` : ", worth a listen") : "";
                        const fill = cell.state === "value" ? cellFill(cell.value, block.max_value) : { alpha: 0, light: false };
                        const key = `${rowIndex}:${index}`;
                        const isSelected = selected.has(key);
                        const classes = [
                          cell.state === "none" ? "is-none" : "",
                          cell.state === "unknown" ? "is-unknown" : "",
                          cell.state === "no_length" ? "is-dot" : "",
                          fill.light ? "is-light" : "",
                          cell.highlight && (cell.state === "value" || cell.state === "no_length") ? "is-highlight" : "",
                          isSelected ? "is-selected" : "",
                          isSelected && (cell.tracks ?? []).length > 0 ? "is-playable" : "",
                        ].filter(Boolean);
                        const label =
                          cell.state === "none"
                            ? `${where}: not played`
                            : cell.state === "unknown"
                              ? `${where}: not matched yet`
                              : cell.state === "no_length"
                                ? `${where}: played, length not known${noted}`
                                : `${where}: ${cell.value} ${UNIT[block.measure]}${noted}`;
                        const target: Tip = { kind: "cell", row: rowIndex, column: index };
                        return (
                          <td
                            key={column.id}
                            role="gridcell"
                            ref={(element) => {
                              if (element) cellRefs.current.set(key, element);
                              else cellRefs.current.delete(key);
                            }}
                            className={classes.join(" ") || undefined}
                            style={cell.state === "value" ? { background: `rgba(var(--grid-cell), ${fill.alpha})` } : undefined}
                            aria-label={label}
                            aria-selected={isSelected}
                            tabIndex={active.row === rowIndex && active.column === index ? 0 : -1}
                            onClick={(event: MouseEvent) => select(rowIndex, index, event.shiftKey || event.metaKey || event.ctrlKey)}
                            onKeyDown={(event) => onCellKey(event, rowIndex, index)}
                            onFocus={(event) => {
                              setFocus({ row: rowIndex, column: index });
                              if (byKeyboard.current) showTip(target, event.currentTarget, FOCUS_DELAY_MS);
                            }}
                            onBlur={hideTip}
                            onMouseEnter={(event) => canHover() && showTip(target, event.currentTarget, 0)}
                            onMouseLeave={hideTip}
                          >
                            {cell.state === "unknown" && "?"}
                            {cell.state === "value" && (
                              <>
                                {cell.value}
                                {cell.passes > 1 && <span className="grid-passes">{cell.passes}</span>}
                              </>
                            )}
                          </td>
                        );
                      })}
                    </tr>
                    {setlistOpen && (
                      <tr className="grid-setlist-row">
                        <td role="cell" colSpan={block.columns.length + 1}>
                          <Setlist row={row} columnIds={block.column_kind === "song" ? new Set(block.columns.map((column) => column.id)) : null} />
                        </td>
                      </tr>
                    )}
                  </Fragment>
                );
              })}
            </tbody>
          </table>
        </div>
        {tip && (
          <div className="grid-tip" role="tooltip" ref={tipRef}>
            {tipCell ? (
              <GridFacts block={block} rowIndex={tipCell.row} columnIndex={tipCell.column} />
            ) : (
              <p className="grid-facts-line">{columnSentence(block, tip.column)}</p>
            )}
          </div>
        )}
      </div>
      {canFold && (
        <button type="button" className="grid-more" onClick={() => setOpen((value) => !value)} aria-expanded={open}>
          {open ? `Show the first ${block.open_rows}` : `Show all ${block.rows.length}`}
        </button>
      )}
      {selection.length > 0 && (
        <DetailBar block={block} selection={selection} onClear={() => setSelection([])} onFollowUp={onFollowUp} />
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

// A night's songs in order: the grid's own songs in cream, the rest muted,
// each set's label as a small break, `>` after a segue.
function Setlist({ row, columnIds }: { row: GridRow; columnIds: ReadonlySet<string> | null }) {
  const items: ReactNode[] = [];
  let currentSet: string | null = null;
  for (const [index, entry] of (row.setlist ?? []).entries()) {
    if (entry.set_label !== currentSet) {
      currentSet = entry.set_label;
      if (currentSet) items.push(<li key={`set-${index}`} className="grid-set-break">{currentSet}</li>);
    }
    items.push(
      <li key={`${index}-${entry.song_id}`} className={columnIds?.has(entry.song_id) ? "is-column" : undefined}>
        {entry.title}
        {entry.segue && <span className="grid-segue" aria-hidden="true"> &gt;</span>}
      </li>,
    );
  }
  return (
    <div className="grid-setlist">
      <ul aria-label="Setlist">{items}</ul>
    </div>
  );
}

function PlayGlyph({ playing }: { playing: boolean }) {
  return playing ? (
    <svg viewBox="0 0 14 14" aria-hidden="true">
      <rect x="2.5" y="2" width="3" height="10" fill="currentColor" />
      <rect x="8.5" y="2" width="3" height="10" fill="currentColor" />
    </svg>
  ) : (
    <svg viewBox="0 0 14 14" aria-hidden="true">
      <path fill="currentColor" d="M4 2.2v9.6l7.6-4.8z" />
    </svg>
  );
}

// What the selection says and offers: each cell's facts, one gold Play, and
// the blue ask. Tapping carries everything a hover card does.
function DetailBar({
  block,
  selection,
  onClear,
  onFollowUp,
}: {
  block: GridBlock;
  selection: Selection;
  onClear: () => void;
  onFollowUp?: (question: string) => void;
}) {
  const player = usePlayer();
  const playable = selection.filter(({ row, column }) => (block.rows[row]?.cells?.[column]?.tracks ?? []).length > 0);
  const queue = playable.flatMap(({ row, column }) => {
    const source = block.rows[row];
    return (source.cells?.[column]?.tracks ?? []).map((track) =>
      toTrack(track, { showDate: rowShowDate(source), venueName: source.sub }),
    );
  });
  const current = player.currentTrack;
  const mine = Boolean(current && queue.some((track) => track.id === current.id && track.audioUrl === current.audioUrl));
  const playing = mine && player.status === "playing";
  const loading = mine && player.status === "loading";

  function onPlay() {
    if (queue.length === 0 || loading) return;
    if (playing) player.pause();
    else if (mine && player.status === "error") player.retry();
    else if (mine) player.toggle();
    else player.play(queue[0], queue);
  }

  const question = askAbout(block, selection);
  const askable = selection.filter(({ row, column }) => {
    const state = block.rows[row]?.cells?.[column]?.state;
    return state === "value" || state === "no_length";
  }).length;
  return (
    <div className="grid-detail" role="group" aria-label="Selected cells">
      <div className="grid-detail-facts" aria-live="polite">
        {selection.map(({ row, column }) => (
          <GridFacts key={`${row}:${column}`} block={block} rowIndex={row} columnIndex={column} />
        ))}
      </div>
      <div className="grid-detail-actions">
        {queue.length > 0 && (
          <button type="button" className="grid-play" aria-busy={loading} onClick={onPlay}>
            <PlayGlyph playing={playing} />
            {playing ? "Pause" : playable.length > 1 ? "Play both" : "Play"}
          </button>
        )}
        {onFollowUp && question && (
          <button type="button" className="ask-chip" onClick={() => onFollowUp(question)}>
            {askable > 1 ? "Compare these" : "Ask about this"}
          </button>
        )}
        <button type="button" className="grid-clear" onClick={onClear}>
          Clear
        </button>
      </div>
    </div>
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
