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
    await userEvent.click(screen.getByRole("button", { name: /show all 22/i }));
    expect(await screen.findAllByRole("rowheader")).toHaveLength(22);
    await userEvent.click(screen.getByRole("button", { name: /show the first 5/i }));
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
});
