// The song timeline's words: every line is built from library facts or the
// model's own text, never invented here.
import { clock } from "./VersionStrip";
import type { SongTimelineData, TimelineFocus, YearPerformance, YearPick, YearSummary } from "./song-timeline-types";

const MONTHS = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"];

export function longDate(iso: string): string {
  return `${MONTHS[Number(iso.slice(5, 7)) - 1]} ${Number(iso.slice(8, 10))}, ${iso.slice(0, 4)}`;
}

export function monthDay(iso: string): string {
  return `${MONTHS[Number(iso.slice(5, 7)) - 1].slice(0, 3)} ${Number(iso.slice(8, 10))}`;
}

export function shortDate(iso: string): string {
  return `${Number(iso.slice(5, 7))}/${Number(iso.slice(8, 10))}/${iso.slice(2, 4)}`;
}

export function plural(count: number, noun: string): string {
  return `${count} ${noun}${count === 1 ? "" : "s"}`;
}

// "23 performances · typically 12:38 · usually into Playing In The Band (20 of 23)"
export function yearFacts(summary: YearSummary): string {
  const parts = [plural(summary.count, "performance")];
  if (summary.median_seconds != null) parts.push(`typically ${clock(summary.median_seconds)}`);
  const next = summary.top_next;
  if (next) parts.push(`${next.count * 2 > summary.count ? "usually" : "most often"} into ${next.title} (${next.count} of ${summary.count})`);
  return parts.join(" · ");
}

// Why this is the year's pick: the model's stop if it named one, else the library's reason.
export function pickEyebrow(pick: YearPick, stop: { number: number; label: string | null } | null): string {
  if (stop) return stop.label ? `Stop ${stop.number} · ${stop.label}` : `Stop ${stop.number}`;
  const detail = pick.basis_detail ?? "";
  switch (pick.basis) {
    case "picked":
      return `Picked by ${detail}`;
    case "show_picked":
      return `Show picked by ${detail}`;
    case "released":
      return `On ${detail.split(":")[0]}`;
    default:
      return "First of the year";
  }
}

export function askQuestion(data: SongTimelineData, year: number): string {
  return data.year_questions.find((item) => item.year === year)?.question ?? `Tell me about ${data.title} in ${year}`;
}

// "Samson And Delilah › Terrapin Station › Playing In The Band": a segue joins with ›.
export function flowLine(performance: YearPerformance, title: string): string {
  const before = performance.previous?.segued ? `${performance.previous.title} › ` : "";
  const next = performance.next;
  const after = next ? (next.segued ? ` › ${next.title}` : `, then ${next.title}`) : ", closing the set";
  return `${before}${title}${after}`;
}

export function performanceTags(performance: YearPerformance, stopNumber: number | null): string[] {
  const tags: string[] = [];
  if (stopNumber) tags.push(`Stop ${stopNumber}`);
  for (const signal of performance.signals) tags.push(`${signal.scope === "show" ? "Show picked" : "Picked"} by ${signal.voice}`);
  for (const guest of performance.guests) tags.push(`With ${guest.name}`);
  if (performance.releases.length) tags.push("Released");
  return tags;
}

export function focusFor(data: SongTimelineData, summary: YearSummary): TimelineFocus {
  return {
    label: `${data.title} in ${summary.year}`,
    song_id: data.song_id,
    year: summary.year,
    ids: [data.song_id, ...(summary.pick ? [summary.pick.performance_id] : [])],
    facts: [yearFacts(summary)]
  };
}

// The model's open year when it was played; otherwise the first year with a pick.
export function initialYear(data: SongTimelineData): number | null {
  const played = data.year_summaries.filter((summary) => summary.count > 0);
  if (data.open_year != null && played.some((summary) => summary.year === data.open_year)) return data.open_year;
  return (played.find((summary) => summary.pick) ?? played[0])?.year ?? null;
}
