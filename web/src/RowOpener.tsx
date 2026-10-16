// One shared row behavior for ranked answers: a chart's bar, a ranked list's
// row or a roster's name that names a song, person, venue, record or year
// opens in place to that record's facts, one gold play and one blue ask.
// The server fills every fact and picks the recording (GET /api/rows/{id});
// this file only fetches, draws and wires the two actions.
import { useCallback, useEffect, useRef, useState, type KeyboardEvent } from "react";
import type { FollowUp } from "./ask-request";
import { PlayGlyph, toTrack, usePlayControl, type InPagePlay } from "./listen-control";
import type { AskFocus } from "./types";
import type { components } from "./generated/api";

export type RowDetail = components["schemas"]["RowDetail"];
export type RowBlockType = "data_chart" | "ranked_list" | "person_roster";
// Where a row sits: the block it belongs to and, for a year chart that counts
// one song, that song.
export type RowSource = { blockType: RowBlockType; blockId: string; scope?: string | null };
export type FetchRow = (id: string, scope?: string | null) => Promise<RowDetail>;

const kept = new Map<string, Promise<RowDetail>>();

export function rowUrl(id: string, scope?: string | null): string {
  const base = `/api/rows/${encodeURIComponent(id)}`;
  return scope ? `${base}?scope=${encodeURIComponent(scope)}` : base;
}

// Fetched once per row and kept for the session; library facts do not change
// between deploys. A failed lookup is forgotten so a retry asks again.
export const fetchRowDetail: FetchRow = (id, scope) => {
  const key = `${id}|${scope ?? ""}`;
  let pending = kept.get(key);
  if (!pending) {
    pending = fetch(rowUrl(id, scope)).then(async (response) => {
      if (!response.ok) throw new Error(`This row could not open (${response.status}).`);
      return (await response.json()) as RowDetail;
    });
    pending.catch(() => kept.delete(key));
    kept.set(key, pending);
  }
  return pending;
};

export function forgetRowDetails(): void {
  kept.clear();
}

// The question's focus: the opened record, the night it plays and its facts
// as the page showed them. A year is not a library ID, so it rides in the label.
export function rowFocus(detail: RowDetail, source: RowSource): AskFocus {
  const ids = [detail.kind === "year" ? null : detail.id, source.scope ?? null, detail.play?.show_id ?? null].filter(
    (id): id is string => Boolean(id)
  );
  return {
    block_type: source.blockType,
    block_id: source.blockId,
    label: detail.title,
    ids: [...new Set(ids)],
    facts: (detail.facts ?? []).map((fact) => `${fact.label}: ${fact.value}.`)
  };
}

const MONTHS = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"];

function longDate(iso: string): string {
  const match = /^(\d{4})-(\d{2})-(\d{2})$/.exec(iso);
  if (!match) return iso;
  return `${MONTHS[Number(match[2]) - 1] ?? match[2]} ${Number(match[3])}, ${match[1]}`;
}

// One open row per block. Closing returns focus to the row's trigger.
export function useOpenRow() {
  const [openId, setOpenId] = useState<string | null>(null);
  const current = useRef<string | null>(null);
  current.current = openId;
  const triggers = useRef(new Map<string, HTMLElement | SVGElement>());
  const toggle = useCallback((id: string) => setOpenId((open) => (open === id ? null : id)), []);
  const close = useCallback(() => {
    const open = current.current;
    setOpenId(null);
    if (open) triggers.current.get(open)?.focus();
  }, []);
  const register = useCallback(
    (id: string) => (element: HTMLElement | SVGElement | null) => {
      if (element) triggers.current.set(id, element);
      else triggers.current.delete(id);
    },
    []
  );
  return { openId, toggle, close, register };
}

// A stable DOM id for a row's panel inside one block.
export function panelId(base: string, rowId: string): string {
  return `${base}-row-${rowId.replace(/[^A-Za-z0-9_-]/g, "_")}`;
}

function RowPlayButton({ play, title }: { play: NonNullable<RowDetail["play"]>; title: string }) {
  const queue = play.tracks.map((track) => toTrack(track, { showDate: play.show_date, venueName: play.venue_name ?? null }));
  const inPage: InPagePlay | null = queue.length > 0 ? { start: queue[0], queue } : null;
  const control = usePlayControl(inPage, "queue");
  if (!inPage) return null;
  const when = [longDate(play.show_date), play.venue_name].filter(Boolean).join(", ");
  return (
    <div className="opened-play-line">
      <button
        type="button"
        className="opened-play"
        data-playable="in-page"
        aria-label={`${control.playing ? "Pause" : control.errored ? "Retry" : "Play"} ${title}, ${when}`}
        aria-pressed={control.mine}
        aria-busy={control.loading}
        onClick={control.onClick}
      >
        <PlayGlyph playing={control.playing} />
        {control.playing ? "Pause" : "Play"}
      </button>
      <span className="opened-play-when">
        {when}
        {play.why && <span className="opened-play-why">{play.why}</span>}
      </span>
    </div>
  );
}

// The opened row: facts in two aligned columns, the play, the ask.
export function RowPanel({
  id,
  rowId,
  source,
  onFollowUp,
  onClose,
  standalone = false,
  fetchRow = fetchRowDetail
}: {
  id: string;
  rowId: string;
  source: RowSource;
  onFollowUp?: FollowUp;
  onClose: () => void;
  // A panel apart from its row (under a chart) names its record and offers Close.
  standalone?: boolean;
  fetchRow?: FetchRow;
}) {
  const [state, setState] = useState<{ detail?: RowDetail; failed?: boolean }>({});
  const [attempt, setAttempt] = useState(0);
  useEffect(() => {
    let live = true;
    setState({});
    fetchRow(rowId, source.scope).then(
      (detail) => live && setState({ detail }),
      () => live && setState({ failed: true })
    );
    return () => {
      live = false;
    };
  }, [rowId, source.scope, fetchRow, attempt]);

  function onKeyDown(event: KeyboardEvent<HTMLDivElement>) {
    if (event.key === "Escape") {
      event.stopPropagation();
      onClose();
    }
  }

  const { detail, failed } = state;
  return (
    <div
      id={id}
      className={standalone ? "row-panel standalone" : "row-panel"}
      role="region"
      aria-label={detail?.title ?? "Row details"}
      aria-busy={!detail && !failed}
      onKeyDown={onKeyDown}
    >
      {standalone && (
        <div className="row-panel-head">
          {detail && <p className="row-panel-title">{detail.title}</p>}
          <button type="button" className="row-close" onClick={onClose}>
            Close
          </button>
        </div>
      )}
      {failed ? (
        <p className="row-panel-status">
          This row could not open.{" "}
          <button type="button" className="row-retry" onClick={() => setAttempt((count) => count + 1)}>
            Try again
          </button>
        </p>
      ) : !detail ? (
        <p className="row-panel-status">Opening…</p>
      ) : (
        <>
          {(detail.facts ?? []).length > 0 && (
            <dl className="row-facts">
              {(detail.facts ?? []).map((fact) => (
                <div key={fact.label}>
                  <dt>{fact.label}</dt>
                  <dd>{fact.value}</dd>
                </div>
              ))}
            </dl>
          )}
          {detail.play && detail.play.tracks.length > 0 && <RowPlayButton play={detail.play} title={detail.title} />}
          {onFollowUp && (
            <button type="button" className="ask-chip row-ask" onClick={() => onFollowUp(detail.ask, rowFocus(detail, source))}>
              {detail.ask}
            </button>
          )}
        </>
      )}
    </div>
  );
}
