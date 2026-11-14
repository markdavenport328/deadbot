import { type ReactNode, createContext } from "react";
import { type AlbumUnitBlock, type ExperienceBlock } from "../../types";
import { type PlayerTrack } from "../../player/player";
import { type SpotifyPanel } from "../spotify-embed";
import { ClampText } from "../listening";
import { albumTrack } from "../AlbumNights";
import { formatShowDateLong } from "../../core/format";
import { renderInline } from "../inline";

export type UnitBlock = Extract<ExperienceBlock, { type: "show_unit" | "performance_unit" | "album_unit" | "song_overview" }>;

// A record's Spotify album, when the server derived an embed for it: the
// listen action it came from and the embed's identifier.
export function albumSpotify(block: AlbumUnitBlock): { action: AlbumUnitBlock["listen"][number]; embedId: string } | null {
  if (block.embed_kind !== "spotify" || !block.embed_id) return null;
  const action = block.listen.find((item) => item.provider.toLowerCase() === "spotify");
  return action ? { action, embedId: block.embed_id } : null;
}

// A collapsed row owns its record's Spotify player (compact, under the row's
// header); the record opened beneath it reaches for the same panel.
export const RowSpotifyContext = createContext<SpotifyPanel | null>(null);

// A unit's container. As a card it is its own framed object; opened inside a
// collapsed row it is the row's body, so the row and its details are one
// object: the row's header stays and this opens beneath it.
export function UnitFrame({ inRow, className, children }: { inRow: boolean; className: string; children: ReactNode }) {
  return inRow ? <div className={`row-body ${className}`}>{children}</div> : <article className={`card ${className}`}>{children}</article>;
}

// A record plays in-page when its tracks carry tape; otherwise its first
// listen action (the streaming album) is the way to hear it.
export function albumQueue(block: AlbumUnitBlock): PlayerTrack[] {
  return block.tracks.map(albumTrack).filter((track): track is PlayerTrack => track !== null);
}

export function isUnit(block: ExperienceBlock): block is UnitBlock {
  return block.type === "show_unit" || block.type === "performance_unit" || block.type === "album_unit" || block.type === "song_overview";
}

// Judgments on a comparison's shared terms, as sentences: the criterion is a
// run-in lead, not a stacked label row. Each sentence clamps on its own.
export function CriteriaTable({ criteria, judgments }: { criteria: string[]; judgments: string[] }) {
  if (criteria.length === 0) return null;
  const rows = criteria.map((criterion, index) => ({ criterion, judgment: (judgments[index] ?? "").trim() })).filter((row) => row.judgment);
  if (rows.length === 0) return null;
  return (
    <div className="criteria">
      {rows.map(({ criterion, judgment }) => (
        <ClampText key={criterion} className="judgment">
          <strong className="lead-in">{/[.:?!]$/.test(criterion.trim()) ? criterion.trim() : `${criterion.trim()}.`}</strong> {renderInline(judgment)}
        </ClampText>
      ))}
    </div>
  );
}

// A disclosure decides once, when it first appears, whether to start open.
// Later renders leave it alone, so a page that finishes composing does not
// snap its facets open beneath the reader.
export function unitKey(block: UnitBlock): string {
  switch (block.type) {
    case "show_unit": return block.show_id;
    case "performance_unit": return block.performance_id;
    case "album_unit": return block.release_id;
    case "song_overview": return block.song_id;
  }
}

export type SongOverviewBlockT = Extract<ExperienceBlock, { type: "song_overview" }>;

// A show label arrives as "1970-06-07 — Fillmore West". The venue is the name;
// the date is written out beneath it.
export function splitShowLabel(label: string, showDate?: string | null): { venue: string; date: string | null } {
  const parts = label.split(/\s+[—–-]\s+/);
  const venue = parts.length > 1 ? parts.slice(1).join(" — ") : label;
  const date = showDate ? formatShowDateLong(showDate) : parts.length > 1 ? parts[0] : null;
  return { venue, date };
}

// The song's own name: its tracks and timeline are named by it, while the
// card's heading (block.title) is the model's to rewrite.
export function songName(block: SongOverviewBlockT): string {
  return block.song_title?.trim() || block.title;
}
