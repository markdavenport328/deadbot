import { describe, expect, it, vi } from "vitest";
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import europe from "./fixtures/grid-europe72.json";
import years from "./fixtures/grid-song-years.json";
import { Grid, cellFill } from "./Grid";
import type { GridBlock } from "./types";

describe("Grid", () => {
  it("renders a header per column and a row per night", () => {
    render(<Grid block={europe as GridBlock} />);
    const table = screen.getByRole("table");
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
});
