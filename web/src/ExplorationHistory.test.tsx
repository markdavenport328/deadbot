import { fireEvent, render, screen } from "@testing-library/react";
import { expect, test, vi } from "vitest";
import { ExplorationHistory } from "./ExplorationHistory";
import { explorationReducer as reduce, initialExploration } from "./exploration-state";

const reply = (title: string) => ({ schema_version: "2", thread_id: "t", title, answer: "a", conversation: [], blocks: [], groups: [], sources: [] }) as never;
const ask = (s: typeof initialExploration, id: string, q: string, fresh: boolean) =>
  reduce(reduce(s, { type: "submit", requestId: id, question: q, source: fresh ? "typed" : "chip", focus: null, fresh, threadId: id }), { type: "complete", requestId: id, response: reply(q) });

const handlers = () => ({ onNavigate: vi.fn(), onStop: vi.fn(), onRetry: vi.fn(), onNewChat: vi.fn(), headingId: "h" });
const threeAsks = () => {
  let s = ask(initialExploration, "r1", "MSG history", true);
  s = ask(s, "r2", "Late 80s", false);
  return ask(s, "r3", "Garcia birthday", true);
};

test("rows, dividers, current and navigation", () => {
  const h = handlers();
  render(<ExplorationHistory state={threeAsks()} {...h} />);
  const rows = screen.getAllByRole("button", { name: /MSG history|Late 80s|Garcia birthday/ });
  expect(rows.map((r) => r.textContent)).toEqual(["1 · Typed: MSG history", "2 · Chip: Late 80s", "3 · Typed: Garcia birthday"]);
  expect(screen.getAllByText("New thread")).toHaveLength(1);
  expect(screen.getByText("New thread").nextElementSibling).toContainElement(rows[2]);
  expect(rows[2]).toHaveAttribute("aria-current", "true");
  expect(rows[0]).not.toHaveAttribute("aria-current");
  fireEvent.click(rows[0]);
  expect(h.onNavigate).toHaveBeenCalledWith(0);
});

test("the back arrow is disabled at the first entry and ahead rows are marked", () => {
  const h = handlers();
  const s = reduce(threeAsks(), { type: "navigate", index: 0 });
  render(<ExplorationHistory state={s} {...h} />);
  expect(screen.getByRole("button", { name: "Previous exploration" })).toBeDisabled();
  expect(screen.getByRole("button", { name: "Next exploration" })).toBeEnabled();
  expect(screen.getByRole("button", { name: /Late 80s/ })).toHaveClass("ahead");
  fireEvent.click(screen.getByRole("button", { name: "Next exploration" }));
  expect(h.onNavigate).toHaveBeenCalledWith(1);
});

test("a failed request shows Retry", () => {
  const h = handlers();
  let s = ask(initialExploration, "r1", "MSG history", true);
  s = reduce(s, { type: "submit", requestId: "r2", question: "Late 80s", source: "typed", focus: null, fresh: false, threadId: "t" });
  s = reduce(s, { type: "fail", requestId: "r2", message: "boom" });
  render(<ExplorationHistory state={s} {...h} />);
  expect(screen.getByText(/Didn't finish · Late 80s/)).toBeInTheDocument();
  expect(screen.queryByRole("button", { name: "Stop" })).toBeNull();
  expect(screen.getByRole("button", { name: "New chat" })).toBeEnabled();
  fireEvent.click(screen.getByRole("button", { name: "Retry" }));
  expect(h.onRetry).toHaveBeenCalled();
});

test("while asking, Stop is shown and New chat is disabled", () => {
  const h = handlers();
  let s = ask(initialExploration, "r1", "MSG history", true);
  s = reduce(s, { type: "submit", requestId: "r2", question: "Late 80s", source: "typed", focus: null, fresh: false, threadId: "t" });
  render(<ExplorationHistory state={s} {...h} />);
  expect(screen.getByText(/Asking · Late 80s/)).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "New chat" })).toBeDisabled();
  fireEvent.click(screen.getByRole("button", { name: "Stop" }));
  expect(h.onStop).toHaveBeenCalled();
});

test("the start view has no current row and New chat calls through", () => {
  const h = handlers();
  const s = reduce(threeAsks(), { type: "newChat" });
  render(<ExplorationHistory state={s} {...h} />);
  expect(screen.getByRole("button", { name: "Previous exploration" })).toBeDisabled();
  expect(document.querySelector("[aria-current]")).toBeNull();
  fireEvent.click(screen.getByRole("button", { name: "New chat" }));
  expect(h.onNewChat).toHaveBeenCalled();
});
