import { type ExperienceBlock } from "../types";

// The heading a block prints for itself, when it has one. A group whose only
// block repeats the group's own heading would stutter; the block keeps its
// heading and the group's is dropped.
export function blockHeading(block: ExperienceBlock): string | null {
  if ("title" in block && typeof block.title === "string") return block.title;
  return null;
}

// Two headings are the same idea when they match ignoring case, outer
// whitespace, and curly versus straight quotes.
function headingKey(text: string): string {
  return text.trim().toLowerCase().replace(/[\u2018\u2019\u201B]/g, "'").replace(/[\u201C\u201D]/g, '"');
}

export function sameHeading(a: string | null, b: string | null): boolean {
  return !!a && !!b && headingKey(a) === headingKey(b);
}

type EditorialBlockT = Extract<ExperienceBlock, { type: "editorial" }>;

// An item whose title repeats its block's title would print the same heading
// twice; the block's heading stands. An item whose title plays a tape keeps it.
export function repeatsBlockTitle(block: EditorialBlockT, item: EditorialBlockT["items"][number]): boolean {
  return sameHeading(block.title ?? null, item.title) && (item.tracks ?? []).length === 0;
}
