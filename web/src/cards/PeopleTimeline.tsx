// People timeline: who played, and when, as bars on one year axis. Each person
// is a row; several spans are several bars. Rows overlap where people played
// together. Rose because it reads; nothing here plays.
import { CardHeading } from "./components";
import type { ExperienceBlock } from "../types";
import "./PeopleTimeline.css";

type PeopleTimelineBlock = Extract<ExperienceBlock, { type: "people_timeline" }>;
type Person = PeopleTimelineBlock["people"][number];
type Span = Person["spans"][number];

const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

function parts(iso: string): { year: number; month: number; day: number } | null {
  const match = /^(\d{4})(?:-(\d{2}))?(?:-(\d{2}))?/.exec(iso);
  return match ? { year: Number(match[1]), month: Number(match[2] ?? 1), day: Number(match[3] ?? 1) } : null;
}

// A date as a fractional year, for placing it on the axis.
function yearPosition(iso: string): number | null {
  const date = parts(iso);
  return date ? date.year + (date.month - 1) / 12 + (date.day - 1) / 372 : null;
}

function monthYear(iso: string): string {
  const date = parts(iso);
  return date ? `${MONTHS[date.month - 1] ?? ""} ${date.year}`.trim() : iso;
}

function rangeLabel(span: Span): string {
  const start = monthYear(span.start_date);
  const end = monthYear(span.end_date);
  return start === end ? start : `${start} – ${end}`;
}

function showsLabel(count: number): string {
  return `${count} ${count === 1 ? "show" : "shows"}`;
}

function ticks(first: number, last: number): number[] {
  const marks: number[] = [];
  for (let year = Math.ceil(first / 10) * 10; year <= last; year += 10) marks.push(year);
  if (marks.length < 2) return [first, last].filter((year, index, all) => all.indexOf(year) === index);
  return marks;
}

function roles(person: Person): string {
  return [...new Set(person.spans.map((span) => span.role).filter((role): role is string => Boolean(role)))].join(", ");
}

export function PeopleTimeline({ block }: { block: PeopleTimelineBlock }) {
  const first = block.first_year;
  const end = Math.max(block.last_year, first) + 1;
  const percent = (value: number) => Math.min(100, Math.max(0, ((value - first) / (end - first)) * 100));
  const marks = ticks(first, block.last_year);
  return (
    <section className="people-timeline">
      {(block.title || block.note) && (
        <div className="pt-head">
          {block.title && <CardHeading className="pt-title">{block.title}</CardHeading>}
          {block.note && <p className="pt-note">{block.note}</p>}
        </div>
      )}
      <div className="pt-axis" aria-hidden="true">
        <span className="pt-axis-gap" />
        <div className="pt-ticks">
          {marks.map((year, index) => (
            <span
              key={year}
              className={`pt-tick-label${index === 0 && year === first ? " first" : ""}`}
              style={{ left: `${percent(year)}%` }}
            >
              {year}
            </span>
          ))}
        </div>
      </div>
      <ul className="pt-rows">
        {block.people.map((person) => {
          const role = roles(person);
          const meta = [role, showsLabel(person.show_count)].filter(Boolean).join(" · ");
          const hasBars = person.spans.length > 0;
          return (
            <li className="pt-row" key={person.person_id}>
              <div className="pt-who" aria-hidden={hasBars || undefined}>
                <strong className="pt-name">{person.name}</strong>
                <span className="pt-meta">{meta}</span>
              </div>
              <div className="pt-track">
                {marks.map((year) => <span key={year} className="pt-gridline" aria-hidden="true" style={{ left: `${percent(year)}%` }} />)}
                {person.spans.map((span, index) => {
                  const start = yearPosition(span.start_date);
                  const stop = yearPosition(span.end_date);
                  if (start == null || stop == null) return null;
                  const left = percent(start);
                  const width = Math.max(percent(Math.max(stop, start)) - left, 0.6);
                  const text = [person.name, span.role, `${rangeLabel(span)}${span.member === false ? " (guest)" : ""}`, index === 0 ? showsLabel(person.show_count) : null].filter(Boolean).join(", ");
                  return (
                    <span key={`${span.start_date}-${span.end_date}-${index}`} className={`pt-bar${span.member === false ? " guest" : ""}`} style={{ left: `${left}%`, width: `${width}%` }}>
                      <span className="visually-hidden">{text}</span>
                    </span>
                  );
                })}
              </div>
              {person.note && <p className="pt-row-note">{person.note}</p>}
            </li>
          );
        })}
      </ul>
    </section>
  );
}
