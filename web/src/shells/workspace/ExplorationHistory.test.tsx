import { fireEvent, render, screen } from "@testing-library/react";
import { expect, test, vi } from "vitest";
import { ExplorationHistory } from "./ExplorationHistory";
import { explorationReducer as reduce, initialExploration } from "../../core/exploration-state";

const reply = (title: string) => ({ schema_version: "2", thread_id: "t", title, answer: "a", conversation: [], blocks: [], groups: [], sources: [] }) as never;
const ask = (s: typeof initialExploration, id: string, q: string, fresh: boolean) =>
  reduce(reduce(s, { type: "submit", requestId: id, question: q, source: fresh ? "typed" : "chip", focus: null, fresh, threadId: id }), { type: "complete", requestId: id, response: reply(q) });

const handlers = () => ({ onNavigate: vi.fn(), onStop: vi.fn(), onRetry: vi.fn(), onNewChat: vi.fn(), headingId: "h" });
const threeAsks = () => {
  let s = ask(initialExploration, "r1", "MSG history", true);
  s = ask(s, "r2", "Late 80s", false);
  return ask(s, "r3", "Garcia birthday", true);
};

test("threads newest first, each question with its follow-ups beneath, and navigation", () => {
  const h = handlers();
  render(<ExplorationHistory state={threeAsks()} {...h} />);
  const threads = document.querySelectorAll(".history-thread");
  expect(threads).toHaveLength(2);
  expect(threads[0]).toHaveTextContent("Garcia birthday");
  const rows = Array.from(threads[1].querySelectorAll<HTMLButtonElement>(".history-row"));
  expect(rows.map((r) => r.textContent)).toEqual(["MSG history", "Follow-up: Late 80s"]);
  expect(rows[1]).toHaveClass("follow-up");
  expect(screen.getByRole("button", { name: "Garcia birthday" })).toHaveAttribute("aria-current", "true");
  expect(rows[0]).not.toHaveAttribute("aria-current");
  fireEvent.click(rows[0]);
  expect(h.onNavigate).toHaveBeenCalledWith(0);
});

test("rows after the page on screen are marked ahead", () => {
  const h = handlers();
  const s = reduce(threeAsks(), { type: "navigate", index: 0 });
  render(<ExplorationHistory state={s} {...h} />);
  expect(screen.getByRole("button", { name: /Late 80s/ })).toHaveClass("ahead");
});

test("Clear sits below the threads and turns into Undo once used", () => {
  const h = { ...handlers(), onClear: vi.fn(), onUndo: vi.fn() };
  const { rerender } = render(<ExplorationHistory state={threeAsks()} {...h} />);
  fireEvent.click(screen.getByRole("button", { name: "Clear history" }));
  expect(h.onClear).toHaveBeenCalled();
  rerender(<ExplorationHistory state={reduce(threeAsks(), { type: "clear" })} {...h} cleared />);
  expect(screen.getByText("History cleared.")).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "Undo clearing history" }));
  expect(h.onUndo).toHaveBeenCalled();
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
  expect(document.querySelector("[aria-current]")).toBeNull();
  fireEvent.click(screen.getByRole("button", { name: "New chat" }));
  expect(h.onNewChat).toHaveBeenCalled();
});
