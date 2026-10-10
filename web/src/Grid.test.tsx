import { beforeEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render as renderPlain, screen, within } from "@testing-library/react";
import type { ReactElement } from "react";
import userEvent from "@testing-library/user-event";
import { PlayerProvider, usePlayer } from "./player";
import { columnSummary, sortRows } from "./grid-actions";
import europe from "./fixtures/grid-europe72.json";
import years from "./fixtures/grid-song-years.json";
import { Grid, cellFill } from "./Grid";
import type { GridBlock } from "./types";

// The grid plays through the shared player, so it renders inside one.
const render = (ui: ReactElement) => renderPlain(ui, { wrapper: PlayerProvider });

function Queue() {
  const player = usePlayer();
  return <output data-testid="queue">{player.queue.map((track) => track.title).join(" > ")}</output>;
}

beforeEach(() => {
  vi.spyOn(HTMLMediaElement.prototype, "play").mockImplementation(() => Promise.resolve());
  vi.spyOn(HTMLMediaElement.prototype, "pause").mockImplementation(() => undefined);
});

describe("Grid", () => {
  it("renders a header per column and a row per night", () => {
    render(<Grid block={europe as GridBlock} />);
    const table = screen.getByRole("grid");
    expect(within(table).getAllByRole("columnheader")).toHaveLength(7); // the corner stays an empty td
    expect(within(table).getAllByRole("rowheader")).toHaveLength(22);
  });

  it("marks empty cells as not played, and highlighted cells", () => {
    render(<Grid block={europe as GridBlock} />);
    expect(screen.getAllByLabelText(/not played/).length).toBeGreaterThan(0);
    expect(document.querySelectorAll("td.is-highlight")).toHaveLength(3);
  });

  it("hides rows past open_rows until Show all", async () => {
    const block = { ...(europe as GridBlock), open_rows: 5 };
    render(<Grid block={block} />);
    expect(screen.getAllByRole("rowheader")).toHaveLength(5);
    const more = screen.getByRole("button", { name: /show all 22/i });
    expect(more).toHaveAttribute("aria-expanded", "false");
    await userEvent.click(more);
    expect(await screen.findAllByRole("rowheader")).toHaveLength(22);
    const fold = screen.getByRole("button", { name: /show the first 5/i });
    expect(fold).toHaveAttribute("aria-expanded", "true");
    await userEvent.click(fold);
    expect(screen.getAllByRole("rowheader")).toHaveLength(5);
  });

  it("scales fill to the block's max and flips text colour on strong cells", () => {
    expect(cellFill(null, 44).alpha).toBe(0);
    expect(cellFill(44, 44)).toEqual({ alpha: 0.9, light: true });
    expect(cellFill(4, 44).light).toBe(false);
  });

  it("labels year columns in short form with the full year for screen readers", () => {
    render(<Grid block={years as GridBlock} />);
    expect(screen.getByRole("columnheader", { name: "1969" })).toHaveTextContent("'69");
  });

  it("shows the model's headline, note and coverage, and a legend for the states present", () => {
    render(<Grid block={years as GridBlock} />);
    expect(screen.getByRole("heading", { name: /Dark Star burned out early/ })).toBeInTheDocument();
    expect(screen.getByText(/Before 1971 the library has setlists/)).toBeInTheDocument();
    expect(screen.getByText("not played")).toBeInTheDocument();
    expect(screen.queryByText("not matched yet")).toBeNull();
  });

  it("draws follow-up chips under the grid and sends the model's question", async () => {
    const onFollowUp = vi.fn();
    const block = { ...(europe as GridBlock), follow_ups: [{ label: "Bickershaw", question: "What happened at Bickershaw?" }] };
    render(<Grid block={block} onFollowUp={onFollowUp} />);
    await userEvent.click(screen.getByRole("button", { name: "Bickershaw" }));
    expect(onFollowUp).toHaveBeenCalledWith("What happened at Bickershaw?");
  });

  it("labels each kind of cell for screen readers", () => {
    const base = europe as GridBlock;
    const cells = [
      { state: "value", value: 28, passes: 1, highlight: false },
      { state: "none", passes: 0, highlight: false },
      { state: "no_length", passes: 1, highlight: false },
      { state: "unknown", passes: 0, highlight: false },
      { state: "value", value: 11, passes: 1, highlight: true },
    ] as GridBlock["rows"][number]["cells"];
    const block = {
      ...base,
      columns: base.columns.slice(0, 5),
      rows: [{ ...base.rows[0], label: "Night", cells }],
    } as GridBlock;
    render(<Grid block={block} />);
    expect(screen.getByLabelText(/^Night, .*: 28 min$/)).toBeInTheDocument();
    expect(screen.getByLabelText(/: not played$/)).toBeInTheDocument();
    expect(screen.getByLabelText(/: played, length not known$/)).toBeInTheDocument();
    expect(screen.getByLabelText(/: not matched yet$/)).toBeInTheDocument();
    expect(screen.getByLabelText(/: 11 min, worth a listen$/)).toBeInTheDocument();
  });

  it("makes the scrolling frame a labelled, focusable region", () => {
    render(<Grid block={europe as GridBlock} />);
    const frame = screen.getByRole("region", { name: /One big jam a night/ });
    expect(frame).toHaveAttribute("tabindex", "0");
    render(<Grid block={{ ...(europe as GridBlock), title: null }} />);
    expect(screen.getByRole("region", { name: "Grid of 22 nights by 7 songs" })).toBeInTheDocument();
  });

  it("shows a hover card with the cell's facts and the model's note", async () => {
    render(<Grid block={europe as GridBlock} />);
    const cell = screen.getByLabelText(/May 11.*Dark Star/i);
    fireEvent.mouseEnter(cell);
    const card = await screen.findByRole("tooltip");
    expect(card).toHaveTextContent(/Set 2/);
    expect(card).toHaveTextContent(/2 passes/);
    expect(card).toHaveTextContent(/The longest stretch of the tour/);
    expect(card).toHaveTextContent(/Europe|release/i); // where the length came from
    expect(card).toHaveTextContent(/Dark Star · May 11, 1972/);
    expect(card).toHaveTextContent(/Grote Zaal, De Doelen, Rotterdam/);
    fireEvent.mouseLeave(cell);
    expect(screen.queryByRole("tooltip")).toBeNull();
  });

  it("says where a mixed length came from, and when the length is not known", async () => {
    const base = europe as GridBlock;
    const rows = base.rows.map((row, r) =>
      r !== 0
        ? row
        : { ...row, cells: (row.cells ?? []).map((cell, c) => (c === 0 ? { ...cell, length_source: "mixed" as const } : c === 2 ? { ...cell, state: "no_length" as const, value: null } : cell)) },
    );
    render(<Grid block={{ ...base, rows }} />);
    fireEvent.mouseEnter(screen.getAllByRole("gridcell")[0]);
    expect(await screen.findByRole("tooltip")).toHaveTextContent(/timed from the official release and the archive tape/);
    fireEvent.mouseEnter(screen.getAllByRole("gridcell")[2]);
    expect(await screen.findByRole("tooltip")).toHaveTextContent(/Length not known/);
  });

  it("shows how many of the year's shows a song was on, for a song by year grid", async () => {
    render(<Grid block={years as GridBlock} />);
    fireEvent.mouseEnter(screen.getAllByRole("gridcell")[2]);
    expect(await screen.findByRole("tooltip")).toHaveTextContent(/On 67 of the 124 shows with a setlist that year\./);
  });

  it("shows a column's summary when the header is hovered", async () => {
    render(<Grid block={europe as GridBlock} />);
    fireEvent.mouseEnter(screen.getByRole("button", { name: /sort by dark star/i }));
    expect(await screen.findByRole("tooltip")).toHaveTextContent("Played on 11 of 22 nights. Longest: May 11, 44 minutes.");
  });

  it("selects on click and offers Play and Ask", () => {
    render(<Grid block={europe as GridBlock} onFollowUp={() => {}} />);
    fireEvent.click(screen.getByLabelText(/May 11.*Dark Star/i));
    expect(screen.getByRole("button", { name: /^play$/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /ask about this/i })).toBeInTheDocument();
  });

  it("asks about one night, or compares two, with the question written out", () => {
    const onFollowUp = vi.fn();
    render(<Grid block={europe as GridBlock} onFollowUp={onFollowUp} />);
    fireEvent.click(screen.getByLabelText(/May 11.*Dark Star/i));
    fireEvent.click(screen.getByRole("button", { name: /ask about this/i }));
    expect(onFollowUp).toHaveBeenLastCalledWith("Tell me about the Dark Star from May 11, 1972 in Rotterdam.");
    fireEvent.click(screen.getByLabelText(/April 24.*Dark Star/i), { shiftKey: true });
    expect(screen.getByRole("button", { name: /play both/i })).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /compare these/i }));
    expect(onFollowUp).toHaveBeenLastCalledWith("Compare the Dark Star from May 11, 1972 and the Dark Star from April 24, 1972.");
  });

  it("keeps at most two cells selected, and Escape clears them", () => {
    render(<Grid block={europe as GridBlock} onFollowUp={() => {}} />);
    for (const night of [/May 11.*Dark Star/i, /April 24.*Dark Star/i, /May 7.*Dark Star/i])
      fireEvent.click(screen.getByLabelText(night), { metaKey: true });
    expect(document.querySelectorAll("td.is-selected")).toHaveLength(2);
    fireEvent.keyDown(screen.getByLabelText(/May 7.*Dark Star/i), { key: "Escape" });
    expect(document.querySelectorAll("td.is-selected")).toHaveLength(0);
    expect(screen.queryByRole("button", { name: /^play/i })).toBeNull();
  });

  it("plays every pass of the selected cells through the shared player, in order", () => {
    render(
      <>
        <Grid block={europe as GridBlock} />
        <Queue />
      </>,
    );
    fireEvent.click(screen.getByLabelText(/May 11.*Dark Star/i));
    fireEvent.click(screen.getByRole("button", { name: /^play$/i }));
    expect(screen.getByTestId("queue")).toHaveTextContent("Dark Star > Dark Star");
    expect(screen.getByRole("button", { name: /^(play|pause)$/i })).toBeInTheDocument();
  });

  it("plays both selected cells as one queue", () => {
    render(
      <>
        <Grid block={europe as GridBlock} />
        <Queue />
      </>,
    );
    fireEvent.click(screen.getByLabelText(/May 11.*Dark Star/i));
    fireEvent.click(screen.getByLabelText(/April 24.*Dark Star/i), { shiftKey: true });
    fireEvent.click(screen.getByRole("button", { name: /play both/i }));
    expect(screen.getByTestId("queue").textContent).toBe("Dark Star > Dark Star > Dark Star > Dark Star");
  });

  it("offers no Play for a cell with no recording, only its facts", () => {
    render(<Grid block={years as GridBlock} onFollowUp={() => {}} />);
    fireEvent.click(screen.getAllByRole("gridcell")[2]);
    expect(screen.queryByRole("button", { name: /^play/i })).toBeNull();
    expect(screen.getAllByText(/On 67 of the 124 shows/).length).toBeGreaterThan(0);
  });

  it("moves between cells with arrow keys", () => {
    render(<Grid block={europe as GridBlock} />);
    const first = screen.getAllByRole("gridcell")[0];
    first.focus();
    fireEvent.keyDown(first, { key: "ArrowRight" });
    expect(document.activeElement).toBe(screen.getAllByRole("gridcell")[1]);
    fireEvent.keyDown(document.activeElement as Element, { key: "ArrowDown" });
    expect(document.activeElement).toBe(screen.getAllByRole("gridcell")[1 + 7]);
    fireEvent.keyDown(document.activeElement as Element, { key: "ArrowLeft" });
    fireEvent.keyDown(document.activeElement as Element, { key: "ArrowUp" });
    expect(document.activeElement).toBe(first);
  });

  it("keeps one cell in the tab order, and selects with Enter", () => {
    render(<Grid block={europe as GridBlock} />);
    const cells = screen.getAllByRole("gridcell");
    expect(cells.filter((cell) => cell.getAttribute("tabindex") === "0")).toHaveLength(1);
    expect(cells[0]).toHaveAttribute("tabindex", "0");
    fireEvent.keyDown(cells[0], { key: "Enter" });
    expect(cells[0]).toHaveAttribute("aria-selected", "true");
  });

  it("sorts by a column on header click and restores on second click", () => {
    render(<Grid block={europe as GridBlock} />);
    const order = () => screen.getAllByRole("rowheader").map((h) => h.textContent);
    const before = order();
    fireEvent.click(screen.getByRole("button", { name: /sort by dark star/i }));
    expect(order()[0]).toMatch(/May 11/);
    fireEvent.click(screen.getByRole("button", { name: /sort by dark star/i }));
    expect(order()).toEqual(before);
  });

  it("opens a night's setlist under its row", () => {
    render(<Grid block={europe as GridBlock} />);
    const toggle = screen.getByRole("button", { name: /setlist.*May 7/i });
    fireEvent.click(toggle);
    const list = screen.getByRole("list", { name: /setlist/i });
    expect(list).toHaveTextContent(/Dark Star/);
    expect(toggle).toHaveAttribute("aria-expanded", "true");
    fireEvent.click(toggle);
    expect(screen.queryByRole("list", { name: /setlist/i })).toBeNull();
  });

  it("sorts rows by a column's value and summarises a column", () => {
    const block = europe as GridBlock;
    const sorted = sortRows(block.rows, 1, "desc");
    expect(sorted[0].label).toMatch(/May 11/);
    expect(sorted.at(-1)?.cells?.[1].state).toBe("none");
    expect(sortRows(block.rows, 1, "asc")[0].cells?.[1].value).toBe(20);
    expect(columnSummary(block, 1)).toMatchObject({ played: 11, longest: { value: 44 }, shortest: { value: 20 } });
  });
});
