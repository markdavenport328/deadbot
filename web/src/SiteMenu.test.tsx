import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeAll, beforeEach, expect, test } from "vitest";
import { AboutPage } from "./AboutPage";
import { SiteMenu } from "./SiteMenu";
import { usePath } from "./site-nav";

function Page() {
  const path = usePath();
  return <p data-testid="path">{path}</p>;
}

function renderMenu() {
  const root = document.createElement("div");
  root.id = "root";
  document.body.appendChild(root);
  return render(<><SiteMenu /><Page /></>, { container: root });
}

beforeAll(() => {
  window.scrollTo = (() => {}) as typeof window.scrollTo;
});

beforeEach(() => window.history.replaceState({}, "", "/"));

afterEach(() => {
  cleanup();
  document.getElementById("root")?.remove();
});

test("the menu opens to two links and the rest of the page goes inert", () => {
  renderMenu();
  const toggle = screen.getByRole("button", { name: "Menu" });
  expect(toggle).toHaveAttribute("aria-expanded", "false");

  fireEvent.click(toggle);

  expect(toggle).toHaveAttribute("aria-expanded", "true");
  expect(document.getElementById("root")).toHaveAttribute("inert");
  expect(screen.getByRole("button", { name: "Close menu" })).toHaveFocus();
  const dialog = screen.getByRole("dialog", { name: "Site menu" });
  const links = dialog.querySelectorAll(".site-menu-link");
  expect([...links].map((link) => link.textContent)).toEqual(["About Deadbot", "About Mark Davenport↗ (opens in a new tab)"]);
});

test("Escape closes the menu and returns focus to the toggle", () => {
  renderMenu();
  const toggle = screen.getByRole("button", { name: "Menu" });
  fireEvent.click(toggle);

  fireEvent.keyDown(window, { key: "Escape" });

  expect(toggle).toHaveAttribute("aria-expanded", "false");
  expect(document.getElementById("root")).not.toHaveAttribute("inert");
  expect(toggle).toHaveFocus();
});

test("About Deadbot moves to /about in place and closes the menu", () => {
  renderMenu();
  fireEvent.click(screen.getByRole("button", { name: "Menu" }));

  fireEvent.click(screen.getByRole("link", { name: "About Deadbot" }));

  expect(window.location.pathname).toBe("/about");
  expect(screen.getByTestId("path")).toHaveTextContent("/about");
  expect(screen.getByRole("button", { name: "Menu" })).toHaveAttribute("aria-expanded", "false");
});

test("the browser's back button returns to the previous page", () => {
  renderMenu();
  fireEvent.click(screen.getByRole("button", { name: "Menu" }));
  fireEvent.click(screen.getByRole("link", { name: "About Deadbot" }));

  act(() => {
    window.history.replaceState({}, "", "/");
    window.dispatchEvent(new PopStateEvent("popstate"));
  });

  expect(screen.getByTestId("path")).toHaveTextContent("/");
});

test("About Mark Davenport opens the résumé site in a new tab", () => {
  renderMenu();
  fireEvent.click(screen.getByRole("button", { name: "Menu" }));

  const link = screen.getByRole("link", { name: /About Mark Davenport/ });

  expect(link).toHaveAttribute("href", "https://mark-davenport.vercel.app");
  expect(link).toHaveAttribute("target", "_blank");
});

test("the About page lists its sections and credits Mark", () => {
  render(<AboutPage />);

  expect(screen.getByRole("heading", { level: 1, name: "How Deadbot works" })).toBeInTheDocument();
  const contents = screen.getByRole("navigation", { name: "On this page" });
  expect(contents.querySelectorAll("a")).toHaveLength(7);
  expect(screen.getByRole("link", { name: /Mark Davenport/ })).toHaveAttribute("href", "https://mark-davenport.vercel.app");
  expect(document.title).toBe("About Deadbot");
});
