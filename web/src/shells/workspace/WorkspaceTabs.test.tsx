import { fireEvent, render, screen } from "@testing-library/react";
import { expect, test, vi } from "vitest";
import { WorkspaceTabs } from "./WorkspaceTabs";

const states = { listen: "ready", charts: "unused", read: "new" } as const;

test("labels, selection and unused tabs", () => {
  const onSelect = vi.fn();
  render(<WorkspaceTabs active="listen" states={states} onSelect={onSelect} idPrefix="x" />);
  expect(screen.getAllByRole("tab").map((t) => t.textContent?.replace(/has new content/, "").trim())).toEqual(["Listen", "Charts", "Read"]);
  expect(screen.getByRole("tab", { name: /Listen/ })).toHaveAttribute("aria-selected", "true");
  fireEvent.click(screen.getByRole("tab", { name: /Charts/ }));
  expect(onSelect).not.toHaveBeenCalled();
  expect(screen.getByRole("tab", { name: /Charts/ })).toHaveAttribute("aria-disabled", "true");
});

test("arrow keys skip unused tabs", () => {
  const onSelect = vi.fn();
  render(<WorkspaceTabs active="listen" states={states} onSelect={onSelect} idPrefix="x" />);
  fireEvent.keyDown(screen.getByRole("tab", { name: /Listen/ }), { key: "ArrowRight" });
  expect(onSelect).toHaveBeenCalledWith("read");
});

test("preparing tabs say so", () => {
  render(<WorkspaceTabs active={null} states={{ listen: "preparing", charts: "preparing", read: "new" }} onSelect={() => {}} idPrefix="x" />);
  expect(screen.getByRole("tab", { name: /Listen/ })).toHaveTextContent("preparing");
});

test("ids, controls and roving tabindex", () => {
  render(<WorkspaceTabs active="read" states={states} onSelect={() => {}} idPrefix="x" />);
  const read = screen.getByRole("tab", { name: /Read/ });
  expect(read).toHaveAttribute("id", "x-tab-read");
  expect(read).toHaveAttribute("aria-controls", "x-panel-read");
  expect(read).toHaveAttribute("tabindex", "0");
  expect(screen.getByRole("tab", { name: /Listen/ })).toHaveAttribute("tabindex", "-1");
});

test("Home, End and wrapping skip unused tabs", () => {
  const onSelect = vi.fn();
  render(<WorkspaceTabs active="read" states={states} onSelect={onSelect} idPrefix="x" />);
  const read = screen.getByRole("tab", { name: /Read/ });
  fireEvent.keyDown(read, { key: "Home" });
  expect(onSelect).toHaveBeenLastCalledWith("listen");
  fireEvent.keyDown(read, { key: "ArrowRight" });
  expect(onSelect).toHaveBeenLastCalledWith("listen");
  fireEvent.keyDown(screen.getByRole("tab", { name: /Listen/ }), { key: "End" });
  expect(onSelect).toHaveBeenLastCalledWith("read");
});
