import { beforeEach, describe, expect, it, vi } from "vitest";
import { act, fireEvent, render as renderPlain, screen, within } from "@testing-library/react";
import type { ReactElement } from "react";
import userEvent from "@testing-library/user-event";
import { PlayerProvider, usePlayer } from "./player";
import { columnSummary, reshapeGrid, sortRows } from "./grid-actions";
import europe from "./fixtures/grid-europe72.json";
import years from "./fixtures/grid-song-years.json";
import records from "./fixtures/grid-dicks-picks.json";
import guests from "./fixtures/grid-guests.json";
import { Grid, cellFill } from "./Grid";
import type { GridBlock } from "./types";

// The grid plays through the shared player, so it renders inside one.
const render = (ui: ReactElement) => renderPlain(ui, { wrapper: PlayerProvider });

// The player's queue as track ids and audio URLs, in order.
function Queue() {
  const player = usePlayer();
  return (
    <>
      <output data-testid="queue">{player.queue.map((track) => track.id).join(",")}</output>
      <output data-testid="urls">{player.queue.map((track) => track.audioUrl).join(",")}</output>
      <output data-testid="dates">{player.queue.map((track) => track.showDate).join(",")}</output>
    </>
  );
}

type FixtureTrack = { performance_id: string; audio_url: string };
const tracksOf = (rowId: string, column: number) =>
  (europe.rows.find((row) => row.id === rowId)!.cells[column].tracks as FixtureTrack[]);
const DARK_STAR = 1;
let lastAudio: HTMLMediaElement | null = null;
const startPlaying = () => act(() => void lastAudio?.dispatchEvent(new Event("playing")));

beforeEach(() => {
  lastAudio = null;
  vi.spyOn(HTMLMediaElement.prototype, "play").mockImplementation(function (this: HTMLMediaElement) {
    lastAudio = this;
    return Promise.resolve();
  });
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
    expect(await screen.findByRole("tooltip")).toHaveTextContent("Played on 11 of 22 nights. Longest: May 11, 1972, 44 minutes.");
  });

  it("selects on click and offers Play and Ask", () => {
    render(<Grid block={europe as GridBlock} onFollowUp={() => {}} />);
    fireEvent.click(screen.getByLabelText(/May 11.*Dark Star/i));
    expect(screen.getByRole("button", { name: /^play$/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /ask about this/i })).toBeInTheDocument();
  });

  it("asks about one night, or compares two, with the question written out and what was clicked", () => {
    const onFollowUp = vi.fn();
    render(<Grid block={europe as GridBlock} onFollowUp={onFollowUp} />);
    fireEvent.click(screen.getByLabelText(/May 11.*Dark Star/i));
    fireEvent.click(screen.getByRole("button", { name: /ask about this/i }));
    expect(onFollowUp).toHaveBeenLastCalledWith(
      "Tell me about the Dark Star from May 11, 1972 in Rotterdam.",
      expect.objectContaining({
        label: "Dark Star · May 11, 1972",
        block_type: "grid",
        block_id: europe.grid_id,
        ids: ["gd-1972-05-11", "gd-1972-05-11-dark-star-2-7", "gd-1972-05-11-dark-star-2-9", "song-dark-star"],
      }),
    );
    const single = onFollowUp.mock.lastCall![1];
    expect(single.facts).toHaveLength(1);
    expect(single.facts[0]).toMatch(/^Set 2, into Sugar Magnolia\. 44 minutes in 2 passes/);
    fireEvent.click(screen.getByLabelText(/April 24.*Dark Star/i), { shiftKey: true });
    expect(screen.getByRole("button", { name: /play both/i })).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /compare these/i }));
    expect(onFollowUp).toHaveBeenLastCalledWith(
      "Compare the Dark Star from May 11, 1972 and the Dark Star from April 24, 1972.",
      expect.objectContaining({ block_type: "grid", block_id: europe.grid_id }),
    );
    const pair = onFollowUp.mock.lastCall![1];
    expect(pair.ids).toEqual(
      expect.arrayContaining(["gd-1972-05-11", "gd-1972-04-24", "gd-1972-04-24-dark-star-2-1", "song-dark-star"]),
    );
    expect(new Set(pair.ids).size).toBe(pair.ids.length);
    expect(pair.facts).toHaveLength(2);
    expect(pair.facts[1]).toMatch(/April 24, 1972/);
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
    const tracks = tracksOf("gd-1972-05-11", DARK_STAR);
    expect(tracks).toHaveLength(2);
    expect(screen.getByTestId("queue").textContent).toBe(tracks.map((t) => t.performance_id).join(","));
    expect(screen.getByTestId("urls").textContent).toBe(tracks.map((t) => t.audio_url).join(","));
  });

  it("plays both selected cells as one queue, in selection order", () => {
    render(
      <>
        <Grid block={europe as GridBlock} />
        <Queue />
      </>,
    );
    fireEvent.click(screen.getByLabelText(/May 11.*Dark Star/i));
    fireEvent.click(screen.getByLabelText(/April 24.*Dark Star/i), { shiftKey: true });
    fireEvent.click(screen.getByRole("button", { name: /play both/i }));
    const expected = [...tracksOf("gd-1972-05-11", DARK_STAR), ...tracksOf("gd-1972-04-24", DARK_STAR)];
    expect(screen.getByTestId("queue").textContent).toBe(expected.map((t) => t.performance_id).join(","));
    expect(screen.getByTestId("urls").textContent).toBe(expected.map((t) => t.audio_url).join(","));
  });

  it("plays both after only the first was playing, rather than resuming the one", () => {
    render(
      <>
        <Grid block={europe as GridBlock} />
        <Queue />
      </>,
    );
    fireEvent.click(screen.getByLabelText(/May 11.*Dark Star/i));
    fireEvent.click(screen.getByRole("button", { name: /^play$/i }));
    startPlaying();
    expect(screen.getByRole("button", { name: /^pause$/i })).toBeInTheDocument();
    fireEvent.click(screen.getByLabelText(/April 24.*Dark Star/i), { shiftKey: true });
    // The player is on a different queue now, so the control offers Play, not Pause.
    fireEvent.click(screen.getByRole("button", { name: /^play both$/i }));
    const expected = [...tracksOf("gd-1972-05-11", DARK_STAR), ...tracksOf("gd-1972-04-24", DARK_STAR)];
    expect(screen.getByTestId("queue").textContent).toBe(expected.map((t) => t.performance_id).join(","));
  });

  it("pauses when this selection's queue is the one playing", () => {
    render(<Grid block={europe as GridBlock} />);
    fireEvent.click(screen.getByLabelText(/May 11.*Dark Star/i));
    fireEvent.click(screen.getByRole("button", { name: /^play$/i }));
    startPlaying();
    const pause = vi.mocked(HTMLMediaElement.prototype.pause);
    pause.mockClear();
    fireEvent.click(screen.getByRole("button", { name: /^pause$/i }));
    expect(pause).toHaveBeenCalledTimes(1);
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

  it("writes the sorted column's summary on the page, and clears it when the order is restored", () => {
    render(<Grid block={europe as GridBlock} />);
    const line = document.querySelector(".grid-sorted") as HTMLElement;
    expect(line).toHaveAttribute("aria-live", "polite");
    expect(line).toBeEmptyDOMElement();
    fireEvent.click(screen.getByRole("button", { name: /sort by dark star/i }));
    expect(line).toHaveTextContent("Sorted by Dark Star. Played on 11 of 22 nights. Longest: May 11, 1972, 44 minutes.");
    fireEvent.click(screen.getByRole("button", { name: /sort by dark star/i }));
    expect(line).toBeEmptyDOMElement();
  });

  it("describes the anchor by the card, and Escape dismisses the card from a header button", async () => {
    render(<Grid block={europe as GridBlock} />);
    expect(screen.getByRole("grid")).toHaveAttribute("aria-multiselectable", "true");
    const header = screen.getByRole("button", { name: /sort by dark star/i });
    fireEvent.mouseEnter(header);
    const card = await screen.findByRole("tooltip");
    expect(header).toHaveAttribute("aria-describedby", card.id);
    fireEvent.keyDown(header, { key: "Escape" });
    expect(screen.queryByRole("tooltip")).toBeNull();
    expect(header).not.toHaveAttribute("aria-describedby");
    const cell = screen.getByLabelText(/May 11.*Dark Star/i);
    fireEvent.mouseEnter(cell);
    expect(cell).toHaveAttribute("aria-describedby", (await screen.findByRole("tooltip")).id);
  });

  it("keeps focus on the sort button after sorting, and on the toggle after Show all", async () => {
    render(<Grid block={{ ...(europe as GridBlock), open_rows: 5 }} />);
    const sort = screen.getByRole("button", { name: /sort by dark star/i });
    await userEvent.click(sort);
    expect(document.activeElement).toBe(sort);
    const more = screen.getByRole("button", { name: /show all 22/i });
    await userEvent.click(more);
    expect(document.activeElement).toBe(screen.getByRole("button", { name: /show the first 5/i }));
  });

  it("still shows the keyboard-focus card when focus scrolls the frame while it waits", async () => {
    render(<Grid block={europe as GridBlock} />);
    const cells = screen.getAllByRole("gridcell");
    cells[0].focus();
    fireEvent.keyDown(cells[0], { key: "ArrowRight" });
    fireEvent.scroll(screen.getByRole("region"));
    expect(await screen.findByRole("tooltip")).toBeInTheDocument();
  });
});

// The block the server sends back after a reshape: the same grid with the
// columns the request named, every cell taken from the fixture.
function reshapedFrom(base: GridBlock, columnIds: string[], extra: Partial<GridBlock> = {}): GridBlock {
  const keep = base.columns.map((column, index) => ({ column, index })).filter(({ column }) => columnIds.includes(column.id));
  return {
    ...base,
    columns: keep.map(({ column }) => column),
    rows: base.rows.map((row) => ({ ...row, cells: keep.map(({ index }) => row.cells![index]) })),
    follow_ups: [],
    ...extra,
  } as GridBlock;
}

describe("Grid of records and of guests", () => {
  it("names a record grid's lists and measure in its own words", () => {
    render(<Grid block={records as GridBlock} />);
    expect(screen.getByText(/6 records · 5 songs · minutes on the record/)).toBeInTheDocument();
    expect(screen.getByText("Dick’s Picks 36")).toBeInTheDocument();
    expect(screen.getByText("The Spectrum, Philadelphia, PA 9/21/72")).toBeInTheDocument();
    expect(screen.getByText("not on the record")).toBeInTheDocument();
    expect(screen.getByText("not matched yet")).toBeInTheDocument();
  });

  it("says how long a song runs on a record, and when a blank track may hold it", async () => {
    render(<Grid block={records as GridBlock} />);
    fireEvent.mouseEnter(screen.getByLabelText(/^Dick’s Picks 36, Dark Star: 37 min/));
    const card = await screen.findByRole("tooltip");
    expect(card).toHaveTextContent("Dark Star · Dick’s Picks 36");
    expect(card).toHaveTextContent("37 minutes on the record, on 1 track.");
    expect(card).toHaveTextContent("The longest Dark Star in the series.");
    fireEvent.mouseEnter(screen.getByLabelText(/^Dick’s Picks 16, Dark Star/));
    expect(await screen.findByRole("tooltip")).toHaveTextContent("18 minutes on the record, across 3 tracks.");
    fireEvent.mouseEnter(screen.getByLabelText(/^Dick’s Picks 13, Scarlet Begonias: not matched yet$/));
    expect(await screen.findByRole("tooltip")).toHaveTextContent(/a track on this record that names no song/i);
    fireEvent.mouseEnter(screen.getByLabelText(/^Dick’s Picks 3, Dark Star: not on the record$/));
    expect(await screen.findByRole("tooltip")).toHaveTextContent("Not on this record.");
  });

  it("summarises a song's column across the records", async () => {
    render(<Grid block={records as GridBlock} />);
    fireEvent.mouseEnter(screen.getByRole("button", { name: /sort by dark star/i }));
    expect(await screen.findByRole("tooltip")).toHaveTextContent("On 4 of 6 records. Longest: Dick’s Picks 36, 37 minutes.");
  });

  it("opens a record's tracks under its row", () => {
    render(<Grid block={records as GridBlock} />);
    const toggle = screen.getByRole("button", { name: "Open the tracks of Dick’s Picks 36" });
    fireEvent.click(toggle);
    const list = screen.getByRole("list", { name: "Tracks" });
    expect(list).toHaveTextContent(/Promised Land/);
    expect(list).toHaveTextContent(/Disc 1/);
  });

  it("asks about a song on a record by name", () => {
    const onFollowUp = vi.fn();
    render(<Grid block={records as GridBlock} onFollowUp={onFollowUp} />);
    fireEvent.click(screen.getByLabelText(/^Dick’s Picks 36, Dark Star/));
    fireEvent.click(screen.getByRole("button", { name: "Ask about this" }));
    expect(onFollowUp.mock.calls[0][0]).toBe("Tell me about the Dark Star on Dick’s Picks 36.");
    expect(onFollowUp.mock.calls[0][1].label).toBe("Dark Star · Dick’s Picks 36");
  });

  it("plays a record's cell with the show date read from its performance", () => {
    render(
      <>
        <Grid block={records as GridBlock} />
        <Queue />
      </>,
    );
    fireEvent.click(screen.getByLabelText(/^Dick’s Picks 36, Dark Star/));
    fireEvent.click(screen.getByRole("button", { name: "Play" }));
    expect(screen.getByTestId("queue")).toHaveTextContent("gd-1972-09-21-dark-star-2-5");
    expect(screen.getByTestId("dates")).toHaveTextContent("1972-09-21");
  });

  it("counts the shows a guest sat in on, year by year", async () => {
    render(<Grid block={guests as GridBlock} />);
    expect(screen.getByText(/4 guests · 27 years · shows sat in/)).toBeInTheDocument();
    fireEvent.mouseEnter(screen.getByLabelText(/^Bruce Hornsby, 1989: 3 shows$/));
    const card = await screen.findByRole("tooltip");
    expect(card).toHaveTextContent("Bruce Hornsby · 1989");
    expect(card).toHaveTextContent("Sat in on 3 shows that year.");
    fireEvent.mouseEnter(screen.getByLabelText(/^Bruce Hornsby, 1991: none that year$/));
    expect(await screen.findByRole("tooltip")).toHaveTextContent("Did not sit in that year.");
    fireEvent.mouseEnter(screen.getByRole("button", { name: "Sort by 1974" }));
    expect(await screen.findByRole("tooltip")).toHaveTextContent(/of the 4 guests sat in that year\. Most: Ned Lagin, \d+ shows\./);
  });
});

describe("Grid reshape", () => {
  const original = europe as GridBlock;
  const fetchMock = vi.fn();
  const requestBody = () => JSON.parse(fetchMock.mock.calls.at(-1)![1].body as string);

  beforeEach(() => {
    fetchMock.mockReset();
    vi.stubGlobal("fetch", fetchMock);
  });

  it("asks the server for the grid with the picked column added, and draws what comes back", async () => {
    const added = { ...original, columns: [...original.columns, { id: "song-mr-charlie", label: "Mr. Charlie" }] } as GridBlock;
    added.rows = original.rows.map((row) => ({ ...row, cells: [...row.cells!, { state: "none", passes: 0, highlight: false }] })) as GridBlock["rows"];
    fetchMock.mockResolvedValue({ ok: true, json: async () => added });
    render(<Grid block={original} />);
    await userEvent.click(screen.getByRole("button", { name: "Add a column" }));
    await userEvent.click(screen.getByRole("button", { name: "Mr. Charlie · on 22 of 22 nights" }));
    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(fetchMock.mock.calls[0][0]).toBe("/api/grid");
    expect(fetchMock.mock.calls[0][1].method).toBe("POST");
    const body = requestBody();
    expect(body.spec.column_ids).toEqual([...original.columns.map((c) => c.id), "song-mr-charlie"]);
    expect(body.spec.row_ids).toEqual(original.rows.map((r) => r.id));
    expect(body.title).toBe(original.title);
    expect(body.note).toBe(original.note);
    expect(body.coverage).toBe(original.coverage ?? null);
    expect(await screen.findByRole("button", { name: /sort by mr\. charlie/i })).toBeInTheDocument();
    expect(screen.queryByRole("dialog")).toBeNull();
  });

  it("puts focus on the new column's header after an add", async () => {
    const added = { ...original, columns: [...original.columns, { id: "song-mr-charlie", label: "Mr. Charlie" }] } as GridBlock;
    added.rows = original.rows.map((row) => ({ ...row, cells: [...row.cells!, { state: "none", passes: 0, highlight: false }] })) as GridBlock["rows"];
    fetchMock.mockResolvedValue({ ok: true, json: async () => added });
    render(<Grid block={original} />);
    await userEvent.click(screen.getByRole("button", { name: "Add a column" }));
    await userEvent.click(screen.getByRole("button", { name: /^Mr\. Charlie/ }));
    const header = await screen.findByRole("button", { name: /sort by mr\. charlie/i });
    await vi.waitFor(() => expect(document.activeElement).toBe(header));
  });

  it("removes a column from its header menu and focuses the neighbouring header", async () => {
    const without = reshapedFrom(original, original.columns.map((c) => c.id).filter((id) => id !== "song-dark-star"));
    fetchMock.mockResolvedValue({ ok: true, json: async () => without });
    render(<Grid block={original} />);
    await userEvent.click(screen.getByRole("button", { name: "Options for Dark Star" }));
    await userEvent.click(screen.getByRole("button", { name: "Remove Dark Star" }));
    expect(requestBody().spec.column_ids).not.toContain("song-dark-star");
    expect(requestBody().spec.column_ids).toHaveLength(original.columns.length - 1);
    await vi.waitFor(() => expect(screen.queryByRole("button", { name: /sort by dark star/i })).toBeNull());
    expect(screen.getAllByRole("columnheader")).toHaveLength(original.columns.length - 1);
    // Dark Star sat second; the header now in its place is Dark Star's old neighbour, The Other One.
    await vi.waitFor(() => expect(document.activeElement).toBe(screen.getByRole("button", { name: /sort by the other one/i })));
  });

  it("says the headline and note were written for the original grid once it changes, and not before", async () => {
    const without = reshapedFrom(original, original.columns.map((c) => c.id).slice(0, -1));
    fetchMock.mockResolvedValue({ ok: true, json: async () => without });
    render(<Grid block={original} />);
    expect(screen.queryByText("Written for the original grid")).toBeNull();
    await userEvent.click(screen.getByRole("button", { name: `Options for ${original.columns.at(-1)!.label}` }));
    await userEvent.click(screen.getByRole("button", { name: /^Remove / }));
    expect(await screen.findByText("Written for the original grid")).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: /One big jam a night/ })).toBeInTheDocument();
  });

  it("offers to ask Deadbot about the reshaped grid, and not the original", async () => {
    const without = reshapedFrom(original, original.columns.map((c) => c.id).slice(0, -1), { grid_id: "grid:reshaped" });
    fetchMock.mockResolvedValue({ ok: true, json: async () => without });
    const onFollowUp = vi.fn();
    render(<Grid block={original} onFollowUp={onFollowUp} />);
    expect(screen.queryByRole("button", { name: "Ask Deadbot about this grid" })).toBeNull();
    await userEvent.click(screen.getByRole("button", { name: `Options for ${original.columns.at(-1)!.label}` }));
    await userEvent.click(screen.getByRole("button", { name: /^Remove / }));
    const chip = await screen.findByRole("button", { name: "Ask Deadbot about this grid" });
    expect(chip).toHaveClass("ask-chip");
    await userEvent.click(chip);
    expect(onFollowUp).toHaveBeenCalledTimes(1);
    const [question, focus] = onFollowUp.mock.calls[0];
    expect(question).toBe("What stands out in this grid?");
    expect(focus.block_type).toBe("grid");
    expect(focus.block_id).toBe("grid:reshaped");
    expect(focus.label).toContain(original.title);
    expect(focus.ids.length).toBeLessThanOrEqual(40);
    expect(focus.ids).toEqual(expect.arrayContaining(without.columns.map((c) => c.id)));
    expect(focus.ids).not.toContain(original.columns.at(-1)!.id);
    expect(focus.facts.length).toBeGreaterThan(0);
    expect(focus.facts.length).toBeLessThanOrEqual(12);
    expect(focus.facts[0]).toMatch(/^Truckin': Played on \d+ of 22 nights/);
  });

  it("shows the ask-about-this-grid chip even when the model wrote no words for the grid", async () => {
    const quiet = { ...original, title: null, note: null, coverage: null } as GridBlock;
    fetchMock.mockResolvedValue({ ok: true, json: async () => reshapedFrom(quiet, quiet.columns.map((c) => c.id).slice(1)) });
    render(<Grid block={quiet} onFollowUp={() => {}} />);
    await userEvent.click(screen.getByRole("button", { name: "Options for Dark Star" }));
    await userEvent.click(screen.getByRole("button", { name: "Remove Dark Star" }));
    expect(await screen.findByRole("button", { name: "Ask Deadbot about this grid" })).toBeInTheDocument();
    expect(screen.queryByText("Written for the original grid")).toBeNull();
  });

  it("keeps the old grid and says so when the server cannot reshape it", async () => {
    fetchMock.mockResolvedValue({ ok: false, status: 500, json: async () => ({}) });
    render(<Grid block={original} />);
    await userEvent.click(screen.getByRole("button", { name: "Options for Dark Star" }));
    await userEvent.click(screen.getByRole("button", { name: "Remove Dark Star" }));
    expect(await screen.findByText("Couldn't change the grid. Try again.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /sort by dark star/i })).toBeInTheDocument();
    expect(screen.queryByText("Written for the original grid")).toBeNull();
    fetchMock.mockRejectedValue(new Error("offline"));
    await userEvent.click(screen.getByRole("button", { name: "Options for Dark Star" }));
    await userEvent.click(screen.getByRole("button", { name: "Remove Dark Star" }));
    expect(await screen.findByText("Couldn't change the grid. Try again.")).toBeInTheDocument();
  });

  it("also shows the original-grid line when only the coverage was written", async () => {
    const quiet = { ...original, title: null, note: null, coverage: "Setlists are thin before 1971." } as GridBlock;
    fetchMock.mockResolvedValue({ ok: true, json: async () => ({ ...quiet, columns: quiet.columns.slice(1), rows: quiet.rows.map((r) => ({ ...r, cells: r.cells!.slice(1) })) }) });
    render(<Grid block={quiet} />);
    expect(screen.queryByText("Written for the original grid")).toBeNull();
    await userEvent.click(screen.getByRole("button", { name: "Options for Dark Star" }));
    await userEvent.click(screen.getByRole("button", { name: "Remove Dark Star" }));
    expect(await screen.findByText("Written for the original grid")).toBeInTheDocument();
    expect(requestBody().coverage).toBe("Setlists are thin before 1971.");
  });

  it("asks to wait when the reshape budget is spent", async () => {
    fetchMock.mockResolvedValue({ ok: false, status: 429, json: async () => ({}) });
    render(<Grid block={original} />);
    await userEvent.click(screen.getByRole("button", { name: "Options for Dark Star" }));
    await userEvent.click(screen.getByRole("button", { name: "Remove Dark Star" }));
    expect(await screen.findByText("Too many changes at once. Try again in a minute.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /sort by dark star/i })).toBeInTheDocument();
  });

  it("keeps a live region in the page and fills it when a change fails", async () => {
    fetchMock.mockResolvedValue({ ok: false, status: 500, json: async () => ({}) });
    render(<Grid block={original} />);
    const status = document.querySelector(".grid-error") as HTMLElement;
    expect(status).toHaveAttribute("role", "status");
    expect(status).toBeEmptyDOMElement();
    await userEvent.click(screen.getByRole("button", { name: "Options for Dark Star" }));
    await userEvent.click(screen.getByRole("button", { name: "Remove Dark Star" }));
    await vi.waitFor(() => expect(status).toHaveTextContent("Couldn't change the grid. Try again."));
    expect(document.activeElement).toBe(screen.getByRole("button", { name: "Options for Dark Star" }));
    expect(document.querySelector(".grid-error")).toBe(status);
  });

  it("disables the column controls while a change is on its way", async () => {
    let finish: (value: unknown) => void = () => {};
    fetchMock.mockReturnValue(new Promise((resolve) => (finish = resolve)));
    render(<Grid block={original} />);
    await userEvent.click(screen.getByRole("button", { name: "Options for Dark Star" }));
    await userEvent.click(screen.getByRole("button", { name: "Remove Dark Star" }));
    expect(screen.getByRole("button", { name: "Add a column" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Options for Dark Star" })).toBeDisabled();
    expect(document.querySelector(".grid-stage")).toHaveClass("is-working");
    await act(async () => finish({ ok: true, json: async () => original }));
    expect(screen.getByRole("button", { name: "Add a column" })).toBeEnabled();
    expect(document.querySelector(".grid-stage")).not.toHaveClass("is-working");
  });

  it("cannot remove the last remaining column", async () => {
    const single = reshapedFrom(original, ["song-dark-star"]);
    render(<Grid block={single} />);
    await userEvent.click(screen.getByRole("button", { name: "Options for Dark Star" }));
    expect(screen.getByRole("button", { name: "Remove Dark Star" })).toBeDisabled();
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("closes a menu on Escape and returns focus to its button", async () => {
    render(<Grid block={original} />);
    const trigger = screen.getByRole("button", { name: "Add a column" });
    await userEvent.click(trigger);
    expect(screen.getByRole("button", { name: /Mr\. Charlie/ })).toBeInTheDocument();
    await userEvent.keyboard("{Escape}");
    expect(screen.queryByRole("button", { name: /Mr\. Charlie/ })).toBeNull();
    expect(document.activeElement).toBe(trigger);
  });

  it("offers no Add a column when the library has no songs to suggest", () => {
    render(<Grid block={years as GridBlock} />);
    expect(screen.queryByRole("button", { name: "Add a column" })).toBeNull();
    expect(screen.getByRole("button", { name: /^Options for 1969/ })).toBeInTheDocument();
  });

  it("posts the rows in the order the grid shows them, and the grid's own open_rows", async () => {
    fetchMock.mockResolvedValue({ ok: true, json: async () => original });
    const block = { ...original, open_rows: 5 };
    await reshapeGrid(block, { removeColumn: "song-truckin" });
    const body = requestBody();
    expect(body.open_rows).toBe(5);
    expect(body.spec.row_kind).toBe("show");
    expect(body.spec.column_kind).toBe("song");
    expect(body.spec.column_ids).not.toContain("song-truckin");
    await reshapeGrid(block, { removeRow: "gd-1972-05-11" });
    expect(requestBody().spec.row_ids).not.toContain("gd-1972-05-11");
    expect(requestBody().spec.row_ids).toHaveLength(original.rows.length - 1);
  });

  it("rejects when the server says no", async () => {
    fetchMock.mockResolvedValue({ ok: false, status: 404, json: async () => ({ detail: "nothing" }) });
    await expect(reshapeGrid(original, { addColumn: "song-nope" })).rejects.toThrow();
  });
});
