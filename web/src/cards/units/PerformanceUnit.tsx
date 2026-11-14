import { useMemo } from "react";
import { type ExperienceBlock } from "../../types";
import { CardHeading, MoreAbout } from "../components";
import { type FollowUp } from "../../core/ask-request";
import { type PlayerTrack } from "../../player/player";
import { ClampText, ListenLinks, splitListen, toTrack } from "../listening";
import { ListenControl } from "../listen-control";
import { formatShowDateLong } from "../../core/format";
import { renderInline } from "../inline";
import { CardHead, IdRow, Meta, GoDeeper } from "../parts";
import { UnitFrame, CriteriaTable } from "./shared";

type PerformanceUnitBlockT = Extract<ExperienceBlock, { type: "performance_unit" }>;

export function PerformanceUnit({
  block,
  criteria,
  onFollowUp,
  inRow = false
}: {
  block: PerformanceUnitBlockT;
  criteria: string[];
  onFollowUp: FollowUp;
  inRow?: boolean;
}) {
  const rightParts = [block.set_label, block.position_in_set ? `Song ${block.position_in_set}` : null].filter(Boolean) as string[];
  // The card's performance is the current track: its title, venue and date
  // name it in the now-playing bar. The show's tape, when the card carries
  // it, queues after it and plays for a full-show action.
  const showQueue = useMemo(
    () => (block.show_tracks ?? []).map((track) => toTrack(track, { showDate: block.show_date, venueName: block.venue_name })),
    [block.show_tracks, block.show_date, block.venue_name]
  );
  const standalone = (url: string): PlayerTrack =>
    toTrack({ performance_id: block.performance_id, title: block.song_title, audio_url: url }, { showDate: block.show_date, venueName: block.venue_name });
  const listen = splitListen(block.listen, showQueue, standalone);
  const primary = listen.primary ? { play: listen.primary.play, label: listen.primary.action.label } : null;
  return (
    <UnitFrame inRow={inRow} className={`performance-unit emphasis-${block.emphasis}`}>
      {!inRow && (
        <>
          <IdRow type="Performance" when={rightParts.length > 0 ? rightParts.join(" · ") : null} />
          <CardHead primary={primary}>
            <CardHeading>{block.song_title}</CardHeading>
            <Meta parts={[block.venue_name, formatShowDateLong(block.show_date), block.location]} />
          </CardHead>
        </>
      )}
      {block.note && !inRow && <ClampText className="unit-note">{renderInline(block.note)}</ClampText>}
      <CriteriaTable criteria={criteria} judgments={block.judgments} />
      {(block.previous || block.next) && (() => {
        // Three consecutive setlist lines with this performance lit, numbered
        // from its position when the set position is known.
        const parsed = block.position_in_set ? Number(block.position_in_set) : NaN;
        const here = Number.isFinite(parsed) && parsed > 0 ? parsed : null;
        const setName = block.set_label || "the set";
        // A neighbor plays in-page when the card carries the show's tape.
        const neighborTrack = (performanceId: string) => showQueue.find((track) => track.id === performanceId) ?? null;
        const rows: { key: string; n: number | null; title: string; here?: boolean; edge?: boolean; track?: PlayerTrack | null }[] = [
          block.previous
            ? { key: "prev", n: here ? here - 1 : null, title: block.previous.title, track: neighborTrack(block.previous.performance_id) }
            : { key: "prev", n: null, title: `Opens ${setName}`, edge: true },
          { key: "here", n: here, title: block.song_title, here: true },
          block.next
            ? { key: "next", n: here ? here + 1 : null, title: block.next.title, track: neighborTrack(block.next.performance_id) }
            : { key: "next", n: null, title: `Closes ${setName}`, edge: true }
        ];
        // Each leg is a stop with its trailing arrow, so a narrow card wraps
        // between legs and every line but the last ends on an arrow.
        return (
          <p className="set-excerpt" aria-label="Where this sits in the set">
            {rows.map((row, index) => (
              <span key={row.key} className="leg">
                <span className={row.here ? "stop here" : row.edge ? "stop edge" : "stop"}>
                  {row.n !== null && <span className="n">{row.n}</span>}
                  {row.track ? <ListenControl label={row.title} track={row.track} queue={showQueue} queueable={false} /> : row.title}
                </span>
                {index < rows.length - 1 && <span className="arrow" aria-hidden="true">→</span>}
              </span>
            ))}
          </p>
        );
      })()}
      <ListenLinks actions={listen.restActions} plays={listen.restPlays} />
      {(block.sources.length > 0 || (block.follow_ups ?? []).length > 0) && (
        <footer className="unit-footer">
          <GoDeeper sources={block.sources} />
          <MoreAbout topics={block.follow_ups} onFollowUp={onFollowUp} />
        </footer>
      )}
    </UnitFrame>
  );
}
