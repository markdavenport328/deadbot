

export function formatShowDate(iso: string | null | undefined): string {
  if (!iso) return "Undated";
  const match = /^(\d{4})-(\d{2})-(\d{2})$/.exec(iso);
  if (!match) return iso;
  const [, year, month, day] = match;
  return `${Number(month)}/${Number(day)}/${year.slice(2)}`;
}

const MONTH_NAMES = [
  "January", "February", "March", "April", "May", "June",
  "July", "August", "September", "October", "November", "December"
];

// A card's identity row wants a reading date ("March 29, 1990"), not the
// short numeric form the rest of the page uses.
export function formatShowDateLong(iso: string | null | undefined): string {
  if (!iso) return "Undated";
  const match = /^(\d{4})-(\d{2})-(\d{2})$/.exec(iso);
  if (!match) return iso;
  const [, year, month, day] = match;
  const monthName = MONTH_NAMES[Number(month) - 1];
  if (!monthName) return iso;
  return `${monthName} ${Number(day)}, ${year}`;
}

// A release date is sometimes only a year. Prefer the full reading date and
// fall back to the year alone rather than showing nothing.
export function formatReleaseDate(iso: string | null | undefined): string | null {
  if (!iso) return null;
  if (/^\d{4}-\d{2}-\d{2}$/.test(iso)) return formatShowDateLong(iso);
  const year = /^(\d{4})/.exec(iso);
  return year ? year[1] : iso;
}

// "studio" becomes "Studio album"; a release type that already reads as an
// album ("live album") is not doubled up.
export function formatReleaseType(releaseType: string): string {
  const words = releaseType.split(/[\s-]+/).filter(Boolean);
  const capitalized = words.map((word, index) => (index === 0 ? capitalize(word) : word)).join(" ");
  return /album/i.test(releaseType) ? capitalized : `${capitalized} album`;
}

export function countLabel(count: number, noun: string): string {
  return `${count} ${noun}${count === 1 ? "" : "s"}`;
}

export function capitalize(text: string): string {
  return text.length > 0 ? text.charAt(0).toUpperCase() + text.slice(1) : text;
}
