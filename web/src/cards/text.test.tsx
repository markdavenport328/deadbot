import { render, screen } from "@testing-library/react";
import { expect, test } from "vitest";
import { Block } from "./Block";
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

test("a prose block reads the model's markdown: paragraphs and a list", () => {
  // A section with a heading and text but no cards arrives as one narrative block.
  const { container } = render(
    <Block
      block={{ type: "editorial", presentation: "narrative", eyebrow: null, title: null, paragraphs: ["What to hear:\n\n- The 1990 run\n- The 1991 run"], items: [] }}
      sources={[]}
      criteria={[]}
      soleUnit={false}
      onFollowUp={() => {}}
    />
  );
  expect(container.querySelector(".narrative-block")).not.toBeNull();
  expect(screen.getAllByRole("listitem").map((item) => item.textContent)).toEqual(["The 1990 run", "The 1991 run"]);
  expect(screen.getByText("What to hear:").tagName).toBe("P");
});
