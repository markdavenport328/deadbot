import { render, screen } from "@testing-library/react";
import { expect, test } from "vitest";
import type { ExperienceBlock } from "../types";
import { PeopleTimeline } from "./PeopleTimeline";

type Block = Extract<ExperienceBlock, { type: "people_timeline" }>;

const block: Block = {
  type: "people_timeline",
  title: "Keyboard players",
  first_year: 1965,
  last_year: 1995,
  people: [
    { person_id: "keith", name: "Keith Godchaux", show_count: 433, spans: [{ role: "keyboards", start_date: "1971-10-19", end_date: "1979-02-17", member: true }] },
    {
      person_id: "bruce",
      name: "Bruce Hornsby",
      show_count: 100,
      spans: [
        { role: "keyboards", start_date: "1990-09-15", end_date: "1992-03-24", member: true },
        { role: "keyboards", start_date: "1988-01-01", end_date: "1988-06-01", member: false }
      ]
    }
  ]
};

test("each person is a row with a text equivalent for the bar", () => {
  render(<PeopleTimeline block={block} />);
  expect(screen.getByRole("heading", { name: "Keyboard players" })).toBeInTheDocument();
  expect(screen.getAllByRole("listitem")).toHaveLength(2);
  expect(screen.getByText("Keith Godchaux, keyboards, Oct 1971 – Feb 1979, 433 shows")).toBeInTheDocument();
  expect(screen.getByText("Bruce Hornsby, keyboards, Sep 1990 – Mar 1992, 100 shows")).toBeInTheDocument();
  expect(screen.getByText("1970")).toBeInTheDocument();
});

test("a guest-only span is drawn quieter and named as a guest", () => {
  const { container } = render(<PeopleTimeline block={block} />);
  expect(screen.getByText("Bruce Hornsby, keyboards, Jan 1988 – Jun 1988 (guest)")).toBeInTheDocument();
  expect(container.querySelectorAll(".pt-bar")).toHaveLength(3);
  expect(container.querySelectorAll(".pt-bar.guest")).toHaveLength(1);
});
