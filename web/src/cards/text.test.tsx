import { render, screen } from "@testing-library/react";
import { expect, test } from "vitest";
import { RichText, renderText } from "./text";

function html(text: string): string {
  return render(<div>{renderText(text)}</div>).container.innerHTML;
}

test("plain single-line text renders as inline content, unchanged", () => {
  expect(html("The *Dead* played [here](https://example.org).")).toBe(
    '<div>The <em>Dead</em> played <a href="https://example.org" target="_blank" rel="noreferrer">here</a>.</div>'
  );
});

test("one paragraph keeps the lead's own <p>", () => {
  const { container } = render(<RichText className="answer-lead" text="Just one line." />);
  expect(container.innerHTML).toBe('<p class="answer-lead">Just one line.</p>');
});

test("blank lines split paragraphs", () => {
  render(<RichText text={"First.\n\nSecond."} />);
  expect(screen.getAllByText(/First|Second/).map((node) => node.tagName)).toEqual(["P", "P"]);
});

test("bullets and numbered lists", () => {
  render(<RichText text={"Two things:\n\n- one\n- *two*\n\n1. first\n2. second"} />);
  expect(screen.getAllByRole("list")).toHaveLength(2);
  expect(screen.getAllByRole("listitem")).toHaveLength(4);
  expect(screen.getByText("two").tagName).toBe("EM");
});

test("a pipe table with links and right-aligned numbers", () => {
  render(<RichText text={"| Player | Shows |\n|---|---:|\n| [Keith](https://example.org/k) | 433 |\n| Pigpen | 1,000 |"} />);
  expect(screen.getAllByRole("columnheader").map((cell) => cell.textContent)).toEqual(["Player", "Shows"]);
  expect(screen.getByRole("link", { name: "Keith" })).toHaveAttribute("href", "https://example.org/k");
  expect(screen.getByText("433")).toHaveClass("num");
  expect(screen.getByText("Pigpen")).not.toHaveClass("num");
});

test("html in the text stays text", () => {
  render(<RichText text={"<img src=x onerror=alert(1)>\n\n- <b>hi</b>"} />);
  expect(document.querySelector("img")).toBeNull();
  expect(screen.getByText("<b>hi</b>")).toBeInTheDocument();
});
