// A song's life on stage as one explorable timeline: plays or lengths per
// year, the model's stops as gold pins and a listening path, and a panel for
// any year with three ways in. Play it (gold) and See all (rose) are library
// facts served without the model; Ask (blue) starts a new turn with the year
// attached. Every fact comes from the card's data; the stops, their words, the
// open year and the first view are the model's.
import { useCallback, useLayoutEffect, useMemo, useRef, useState, type KeyboardEvent, type MouseEvent, type ReactNode, type RefObject } from "react";
import { toTrack } from "./listen-control";
import { usePlayer, type PlayerTrack } from "./player";
import { clock } from "./VersionStrip";
import { MARGIN, bandX, countTicks, frame, lengthTicks, pinRows, pinY, pointX, tipPosition, yFor, yearLabelStep, type Frame } from "./song-timeline-geometry";
import {
  askQuestion,
  flowLine,
  focusFor,
  initialYear,
  longDate,
  monthDay,
  performanceTags,
  pickEyebrow,
  plural,
  shortDate,
  yearFacts
} from "./song-timeline-text";
import type { ChartView, LengthPoint, SongTimelineData, SongYearDetail, TimelineFocus, TimelineStop, TimelineTrack, YearSummary } from "./song-timeline-types";
import { fetchSongYear, type FetchYear } from "./song-year";
import "./SongTimeline.css";

type Props = {
  data: SongTimelineData;
  onAsk: (question: string, focus: TimelineFocus) => void;
  fetchYear?: FetchYear;
};

type YearState = { status: "loading" } | { status: "ready"; detail: SongYearDetail } | { status: "error"; message: string };

// A stop the library resolved: it has a date, so it can sit on the chart.
type PlacedStop = TimelineStop & { show_date: string; number: number };

const VIEW_CAPTION: Record<ChartView, string> = {
  count: "Each bar is a year. Gold marks are the stops below. Choose a year to open it.",
  length: "Each dot is one performance, by minutes; the pale line is that year's typical length. Choose a dot to play it."
};

function asPlayerTrack(track: TimelineTrack, showDate?: string | null, venueName?: string | null): PlayerTrack {
  return toTrack(track, { showDate: showDate ?? null, venueName: venueName ?? null });
}

function useWidth(ref: RefObject<HTMLDivElement | null>): number {
  const [width, setWidth] = useState(0);
  useLayoutEffect(() => {
    const element = ref.current;
    if (!element) return;
    const measure = () => setWidth(Math.round(element.getBoundingClientRect().width));
    measure();
    const observer = new ResizeObserver(measure);
    observer.observe(element);
    return () => observer.disconnect();
  }, [ref]);
  return width;
}

function PlayIcon({ size }: { size: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 14 14" aria-hidden="true">
      <path d="M3.5 1.5v11l9-5.5z" fill="currentColor" />
    </svg>
  );
}

function PauseIcon({ size }: { size: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 14 14" aria-hidden="true">
      <path d="M3 1.5h3v11H3zM8 1.5h3v11H8z" fill="currentColor" />
    </svg>
  );
}

export function SongTimeline({ data, onAsk, fetchYear = fetchSongYear }: Props) {
  const player = usePlayer();
  const wrapRef = useRef<HTMLDivElement>(null);
  const width = useWidth(wrapRef);
  const [view, setView] = useState<ChartView>(data.chart_view ?? "count");
  const [year, setYear] = useState<number | null>(() => initialYear(data));
  const [listOpen, setListOpen] = useState(false);
  const [years, setYears] = useState<Record<number, YearState>>({});
  // The latest dot the visitor chose; a slower lookup for an earlier dot is ignored.
  const latestPoint = useRef<string | null>(null);

  const summaries = useMemo(() => new Map(data.year_summaries.map((summary) => [summary.year, summary])), [data]);
  const playedYears = useMemo(() => data.year_summaries.filter((summary) => summary.count > 0).map((summary) => summary.year), [data]);
  const stops = useMemo(
    () =>
      data.stops.flatMap((stop, index): PlacedStop[] =>
        stop.show_date ? [{ ...stop, show_date: stop.show_date, number: index + 1 }] : []
      ),
    [data]
  );
  const stopNumbers = useMemo(() => new Map(data.stops.map((stop, index) => [stop.performance_id, index + 1])), [data]);
  const pathQueue = useMemo(
    () => stops.flatMap((stop) => (stop.track ? [asPlayerTrack(stop.track, stop.show_date, stop.venue_name)] : [])),
    [stops]
  );

  const currentId = player.currentTrack?.id ?? null;
  const playingId = player.status === "playing" || player.status === "loading" ? currentId : null;

  const play = useCallback(
    (track: PlayerTrack, queue?: PlayerTrack[]) => {
      if (currentId === track.id) player.toggle();
      else player.play(track, queue);
    },
    [currentId, player]
  );

  const loadYear = useCallback(
    (target: number): Promise<SongYearDetail | null> => {
      const known = years[target];
      if (known?.status === "ready") return Promise.resolve(known.detail);
      setYears((current) => ({ ...current, [target]: { status: "loading" } }));
      return fetchYear(data.song_id, target).then(
        (detail) => {
          setYears((current) => ({ ...current, [target]: { status: "ready", detail } }));
          return detail;
        },
        (error: unknown) => {
          const message = error instanceof Error ? error.message : `The ${target} list could not load.`;
          setYears((current) => ({ ...current, [target]: { status: "error", message } }));
          return null;
        }
      );
    },
    [data.song_id, fetchYear, years]
  );

  const selectYear = useCallback(
    (target: number) => {
      if (target !== year) setListOpen(false);
      setYear(target);
    },
    [year]
  );

  const playPoint = useCallback(
    (point: LengthPoint) => {
      const target = Number(point.show_date.slice(0, 4));
      latestPoint.current = point.performance_id;
      selectYear(target);
      void loadYear(target).then((detail) => {
        if (latestPoint.current !== point.performance_id) return;
        const performance = detail?.performances.find((item) => item.performance_id === point.performance_id);
        if (performance?.track) play(asPlayerTrack(performance.track, performance.show_date, performance.venue_name));
      });
    },
    [loadYear, play, selectYear]
  );

  const playStop = useCallback(
    (stop: PlacedStop) => {
      selectYear(Number(stop.show_date.slice(0, 4)));
      if (!stop.track) return;
      play(asPlayerTrack(stop.track, stop.show_date, stop.venue_name), pathQueue);
    },
    [pathQueue, play, selectYear]
  );

  if (playedYears.length === 0) {
    return <p className="st-empty-note">No dated performances of {data.title} are in the library.</p>;
  }

  const summary = year != null ? summaries.get(year) : undefined;
  const allYears = data.year_summaries.map((item) => item.year);
  // Pins sit in rows above the plot, except Length-view pins that sit on their own dot.
  const inRows = (stop: PlacedStop) => !(view === "length" && stop.seconds != null);
  const base = width > 0 ? frame(width, allYears, view) : null;
  const rows = base ? pinRows(stops.map((stop) => (inRows(stop) ? pointX(base, stop.show_date) : -1e9))) : [];
  const rowCount = 1 + Math.max(0, ...rows.filter((_row, index) => inRows(stops[index])));
  const f = width > 0 ? frame(width, allYears, view, rowCount) : null;

  return (
    <div className="song-timeline">
      <div className="st-view-bar">
        <div className="st-views" role="group" aria-label="Chart view">
          {(["count", "length"] as ChartView[]).map((option) => (
            <button key={option} type="button" className="st-view" aria-pressed={view === option} onClick={() => setView(option)}>
              {option === "count" ? "Times played" : "Length"}
            </button>
          ))}
        </div>
      </div>
      <p className="st-caption">{VIEW_CAPTION[view]}</p>
      <div className="st-chart" ref={wrapRef}>
        {f && (
          <TimelineChart
            data={data}
            f={f}
            view={view}
            selectedYear={year}
            playedYears={playedYears}
            stops={stops}
            rows={rows}
            playingId={playingId}
            onSelectYear={selectYear}
            onPlayStop={playStop}
            onPlayPoint={playPoint}
          />
        )}
      </div>
      <YearTable data={data} />
      {summary && summary.count > 0 && f && (
        <YearPanel
          data={data}
          summary={summary}
          caretX={bandX(f, summary.year) + f.bandWidth / 2}
          stop={stops.find((stop) => stop.show_date.startsWith(String(summary.year))) ?? null}
          stopNumbers={stopNumbers}
          playedYears={playedYears}
          listOpen={listOpen}
          yearState={years[summary.year]}
          playingId={playingId}
          pathQueue={pathQueue}
          onSelectYear={selectYear}
          onToggleList={() => {
            const opening = !listOpen;
            setListOpen(opening);
            if (opening) void loadYear(summary.year);
          }}
          onRetry={() => void loadYear(summary.year)}
          onPlay={play}
          onAsk={onAsk}
        />
      )}
      {data.stops.length > 0 && (
        <StopPath data={data} stops={stops} pathQueue={pathQueue} playingId={playingId} onPlayStop={playStop} onPlayPath={() => pathQueue[0] && player.play(pathQueue[0], pathQueue)} />
      )}
    </div>
  );
}

function TimelineChart({
  data,
  f,
  view,
  selectedYear,
  playedYears,
  stops,
  rows,
  playingId,
  onSelectYear,
  onPlayStop,
  onPlayPoint
}: {
  data: SongTimelineData;
  f: Frame;
  view: ChartView;
  selectedYear: number | null;
  playedYears: number[];
  stops: PlacedStop[];
  rows: number[];
  playingId: string | null;
  onSelectYear: (year: number) => void;
  onPlayStop: (stop: PlacedStop) => void;
  onPlayPoint: (point: LengthPoint) => void;
}) {
  const svgRef = useRef<SVGSVGElement>(null);
  const [tip, setTip] = useState<{ x: number; y: number; content: ReactNode } | null>(null);
  const tipRef = useRef<HTMLDivElement>(null);
  // Place the tooltip from its measured size, before paint, so it never sits under the pointer.
  useLayoutEffect(() => {
    const element = tipRef.current;
    if (!tip || !element) return;
    const { left, top } = tipPosition({ x: tip.x, y: tip.y }, { width: element.offsetWidth, height: element.offsetHeight }, f.width);
    element.style.left = `${left}px`;
    element.style.top = `${top}px`;
    element.style.visibility = "visible";
  }, [tip, f.width]);
  const ticks =
    view === "count"
      ? countTicks(Math.max(1, ...data.year_summaries.map((item) => item.count)))
      : lengthTicks(Math.max(300, ...data.length_points.map((point) => point.seconds)));
  const top = ticks[ticks.length - 1];
  const step = yearLabelStep(f.bandWidth);
  const stopIds = new Set(stops.map((stop) => stop.performance_id));

  const tipAt = (event: MouseEvent, content: ReactNode) => {
    const box = svgRef.current?.getBoundingClientRect();
    setTip({ x: event.clientX - (box?.left ?? 0), y: event.clientY - (box?.top ?? 0), content });
  };

  const moveTo = (from: number, direction: 1 | -1) => {
    const index = playedYears.indexOf(from);
    const target = playedYears[index + direction];
    if (target === undefined) return;
    onSelectYear(target);
    requestAnimationFrame(() => svgRef.current?.querySelector<SVGGElement>(`[data-year="${target}"]`)?.focus());
  };

  const bandTip = (summary: YearSummary): ReactNode => {
    const stop = stops.find((item) => item.show_date.startsWith(String(summary.year)));
    const chosen = stop ? { venue: stop.venue_name, date: stop.show_date } : summary.pick ? { venue: summary.pick.venue_name, date: summary.pick.show_date } : null;
    return view === "count" ? (
      <>
        <strong>
          {plural(summary.count, "performance")} in {summary.year}
        </strong>
        {chosen && (
          <span className="st-tip-gold">
            ▸ {chosen.venue}, {monthDay(chosen.date)}
          </span>
        )}
        <span className="st-tip-hint">Choose to open {summary.year}</span>
      </>
    ) : (
      <>
        <strong>{summary.year}</strong>
        <span>Typically {clock(summary.median_seconds)}</span>
        {summary.longest && <span>Longest {clock(summary.longest.seconds)}</span>}
        <span className="st-tip-hint">Choose to open {summary.year}</span>
      </>
    );
  };

  return (
    <>
      <svg ref={svgRef} className="st-svg" width={f.width} height={f.height} viewBox={`0 0 ${f.width} ${f.height}`} role="group" aria-label={`${data.title} by year`}>
        <g aria-hidden="true">
          {ticks.map((value) => (
            <g key={value}>
              <line x1={MARGIN.left} x2={f.width - MARGIN.right} y1={yFor(f, value, top)} y2={yFor(f, value, top)} className="st-grid" />
              <text x={MARGIN.left - 8} y={yFor(f, value, top) + 4} textAnchor="end" className="st-axis">
                {view === "count" ? value : `${value / 60}m`}
              </text>
            </g>
          ))}
          {data.year_summaries.map((summary, index) =>
            index % step === 0 ? (
              <text
                key={summary.year}
                x={bandX(f, summary.year) + f.bandWidth / 2}
                y={f.height - 6}
                textAnchor="middle"
                className={summary.year === selectedYear ? "st-axis st-axis-selected" : "st-axis"}
              >
                {summary.year}
              </text>
            ) : null
          )}
        </g>
        {data.year_summaries.map((summary) => {
          const x = bandX(f, summary.year);
          const center = x + f.bandWidth / 2;
          const selected = summary.year === selectedYear;
          if (summary.count === 0) return <g key={summary.year} className="st-band st-band-empty" aria-hidden="true" />;
          return (
            <g
              key={summary.year}
              className={selected ? "st-band st-band-selected" : "st-band"}
              data-year={summary.year}
              role="button"
              tabIndex={0}
              aria-pressed={selected}
              aria-label={`${summary.year}: ${yearFacts(summary)}. Open the year.`}
              onClick={() => onSelectYear(summary.year)}
              onKeyDown={(event: KeyboardEvent) => {
                if (event.key === "Enter" || event.key === " ") {
                  event.preventDefault();
                  onSelectYear(summary.year);
                } else if (event.key === "ArrowRight" || event.key === "ArrowLeft") {
                  event.preventDefault();
                  moveTo(summary.year, event.key === "ArrowRight" ? 1 : -1);
                }
              }}
              onMouseMove={(event) => tipAt(event, bandTip(summary))}
              onMouseLeave={() => setTip(null)}
              onFocus={() => setTip({ x: center, y: f.plotTop, content: bandTip(summary) })}
              onBlur={() => setTip(null)}
            >
              <rect className="st-band-bg" x={x + 1} y={f.plotTop - 6} width={Math.max(0, f.bandWidth - 2)} height={f.plotBottom - f.plotTop + 6} rx={2} />
              {view === "count" ? (
                <rect
                  className="st-bar"
                  x={center - f.barWidth / 2}
                  y={yFor(f, summary.count, top)}
                  width={f.barWidth}
                  height={f.plotBottom - yFor(f, summary.count, top)}
                  rx={2}
                />
              ) : (
                summary.median_seconds != null && (
                  <line
                    className="st-median"
                    x1={x + f.bandWidth * 0.12}
                    x2={x + f.bandWidth * 0.88}
                    y1={yFor(f, summary.median_seconds, top)}
                    y2={yFor(f, summary.median_seconds, top)}
                  />
                )
              )}
            </g>
          );
        })}
        {view === "length" && (
          <g aria-hidden="true">
            {data.length_points.map((point) => {
              const x = pointX(f, point.show_date);
              const y = yFor(f, point.seconds, top);
              const inYear = point.show_date.startsWith(String(selectedYear));
              return (
                <g
                  key={point.performance_id}
                  className="st-dot"
                  onClick={(event) => {
                    event.stopPropagation();
                    onPlayPoint(point);
                  }}
                  onMouseMove={(event) =>
                    tipAt(
                      event,
                      <>
                        <strong>{longDate(point.show_date)}</strong>
                        <span>{clock(point.seconds)}</span>
                        <span className="st-tip-hint">Choose to play</span>
                      </>
                    )
                  }
                  onMouseLeave={() => setTip(null)}
                >
                  <circle cx={x} cy={y} r={7} className="st-dot-hit" />
                  {!stopIds.has(point.performance_id) && <circle cx={x} cy={y} r={2.6} className={inYear ? "st-dot-mark st-dot-in-year" : "st-dot-mark"} />}
                </g>
              );
            })}
          </g>
        )}
        {stops.map((stop, index) => {
          const x = pointX(f, stop.show_date);
          const onChart = view === "length" && stop.seconds != null;
          const y = onChart ? yFor(f, stop.seconds!, top) : pinY(f, rows[index]);
          const stopYear = data.year_summaries.find((item) => stop.show_date.startsWith(String(item.year)));
          const active = playingId === stop.performance_id;
          return (
            <g
              key={stop.performance_id}
              className={active ? "st-pin st-pin-active" : "st-pin"}
              role="button"
              tabIndex={0}
              aria-label={`Play stop ${stop.number}${stop.label ? `, ${stop.label}` : ""}, ${longDate(stop.show_date)}`}
              onClick={() => onPlayStop(stop)}
              onKeyDown={(event: KeyboardEvent) => {
                if (event.key === "Enter" || event.key === " ") {
                  event.preventDefault();
                  onPlayStop(stop);
                }
              }}
              onMouseMove={(event) =>
                tipAt(
                  event,
                  <>
                    <span className="st-tip-gold">
                      Stop {stop.number}
                      {stop.label ? ` · ${stop.label}` : ""}
                    </span>
                    <strong>{stop.venue_name}</strong>
                    <span>
                      {longDate(stop.show_date)} · {clock(stop.seconds)}
                    </span>
                  </>
                )
              }
              onMouseLeave={() => setTip(null)}
            >
              {!onChart && view === "count" && stopYear && (
                <line className="st-pin-stem" x1={x} x2={x} y1={y + 8} y2={yFor(f, stopYear.count, top) - 1} />
              )}
              <circle cx={x} cy={y} r={8.5} className="st-pin-dot" />
              <text x={x} y={y + 3.5} textAnchor="middle" className="st-pin-number">
                {stop.number}
              </text>
            </g>
          );
        })}
      </svg>
      {tip && (
        <div ref={tipRef} className="st-tip" role="tooltip" style={{ left: 0, top: 0, visibility: "hidden" }}>
          {tip.content}
        </div>
      )}
    </>
  );
}

// The full-data alternative to the drawing: every year, its count and typical length.
function YearTable({ data }: { data: SongTimelineData }) {
  return (
    <table className="visually-hidden">
      <caption>{data.title} by year, full data table</caption>
      <thead>
        <tr>
          <th scope="col">Year</th>
          <th scope="col">Performances</th>
          <th scope="col">Typical length</th>
        </tr>
      </thead>
      <tbody>
        {data.year_summaries.map((summary) => (
          <tr key={summary.year}>
            <td>{summary.year}</td>
            <td>{summary.count}</td>
            <td>{summary.median_seconds != null ? clock(summary.median_seconds) : "—"}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

function YearPanel({
  data,
  summary,
  caretX,
  stop,
  stopNumbers,
  playedYears,
  listOpen,
  yearState,
  playingId,
  pathQueue,
  onSelectYear,
  onToggleList,
  onRetry,
  onPlay,
  onAsk
}: {
  data: SongTimelineData;
  summary: YearSummary;
  caretX: number;
  stop: PlacedStop | null;
  stopNumbers: Map<string, number>;
  playedYears: number[];
  listOpen: boolean;
  yearState: YearState | undefined;
  playingId: string | null;
  pathQueue: PlayerTrack[];
  onSelectYear: (year: number) => void;
  onToggleList: () => void;
  onRetry: () => void;
  onPlay: (track: PlayerTrack, queue?: PlayerTrack[]) => void;
  onAsk: (question: string, focus: TimelineFocus) => void;
}) {
  const index = playedYears.indexOf(summary.year);
  const previous = playedYears[index - 1];
  const next = playedYears[index + 1];
  const pick = summary.pick;
  // The year's pick: the model's stop when it named one, else the library's.
  const chosen = stop
    ? { id: stop.performance_id, venue: stop.venue_name, date: stop.show_date, setLabel: null, seconds: stop.seconds ?? null, track: stop.track ?? null, why: stop.why }
    : pick
      ? { id: pick.performance_id, venue: pick.venue_name, date: pick.show_date, setLabel: pick.set_label, seconds: pick.seconds, track: pick.track, why: null }
      : null;
  const eyebrow = stop ? `Stop ${stop.number}${stop.label ? ` · ${stop.label}` : ""}` : pick ? pickEyebrow(pick, null) : "";
  const question = askQuestion(data, summary.year);
  const playingChosen = chosen != null && playingId === chosen.id;

  return (
    <section className="st-year" aria-label={String(summary.year)} style={{ ["--st-caret" as string]: `${caretX}px` }}>
      <div className="st-year-head">
        <h4 className="st-year-number">{summary.year}</h4>
        <p className="st-year-facts">{yearFacts(summary)}</p>
        <div className="st-year-step">
          <button type="button" disabled={previous === undefined} onClick={() => previous !== undefined && onSelectYear(previous)} aria-label="Previous year">
            ← {previous ?? ""}
          </button>
          <button type="button" disabled={next === undefined} onClick={() => next !== undefined && onSelectYear(next)} aria-label="Next year">
            {next ?? ""} →
          </button>
        </div>
      </div>
      {chosen && (
        <div className="st-pick">
          <button
            type="button"
            className="st-play-big"
            disabled={!chosen.track}
            aria-label={`${playingChosen ? "Pause" : "Play"} ${data.title}, ${chosen.venue ?? ""}, ${longDate(chosen.date)}`}
            onClick={() => chosen.track && onPlay(asPlayerTrack(chosen.track, chosen.date, chosen.venue), stop ? pathQueue : undefined)}
          >
            {playingChosen ? <PauseIcon size={16} /> : <PlayIcon size={16} />}
          </button>
          <div className="st-pick-body">
            <span className="st-eyebrow-gold">{eyebrow}</span>
            <span className="st-pick-title">{chosen.venue}</span>
            <span className="st-pick-meta">
              {[longDate(chosen.date), chosen.setLabel, chosen.seconds != null ? clock(chosen.seconds) : null].filter(Boolean).join(" · ")}
            </span>
            {chosen.why && <p className="st-pick-why">{chosen.why}</p>}
          </div>
        </div>
      )}
      <div className="st-actions">
        <button type="button" className="st-see-all" aria-expanded={listOpen} onClick={onToggleList}>
          {listOpen ? `Hide the ${summary.year} list` : `See all ${summary.count} from ${summary.year}`}
        </button>
        <button type="button" className="st-ask" onClick={() => onAsk(question, focusFor(data, summary, chosen?.id ?? null))}>
          <span className="st-ask-mark" aria-hidden="true">
            ?
          </span>
          {question}
        </button>
      </div>
      {listOpen && <YearList data={data} yearState={yearState} chosenId={chosen?.id ?? null} stopNumbers={stopNumbers} playingId={playingId} onRetry={onRetry} onPlay={onPlay} year={summary.year} />}
    </section>
  );
}

function YearList({
  data,
  year,
  yearState,
  chosenId,
  stopNumbers,
  playingId,
  onRetry,
  onPlay
}: {
  data: SongTimelineData;
  year: number;
  yearState: YearState | undefined;
  chosenId: string | null;
  stopNumbers: Map<string, number>;
  playingId: string | null;
  onRetry: () => void;
  onPlay: (track: PlayerTrack, queue?: PlayerTrack[]) => void;
}) {
  if (!yearState || yearState.status === "loading") return <p className="st-list-note">Loading the {year} list…</p>;
  if (yearState.status === "error")
    return (
      <p className="st-list-note">
        {yearState.message}{" "}
        <button type="button" className="st-see-all" onClick={onRetry}>
          Try again
        </button>
      </p>
    );
  const performances = yearState.detail.performances;
  const queue = performances.flatMap((item) => (item.track ? [asPlayerTrack(item.track, item.show_date, item.venue_name)] : []));
  return (
    <ol className="st-list">
      {performances.map((performance) => {
        const tags = performanceTags(performance, stopNumbers.get(performance.performance_id) ?? null);
        const playing = playingId === performance.performance_id;
        return (
          <li key={performance.performance_id} className={performance.performance_id === chosenId ? "st-row st-row-chosen" : "st-row"}>
            <button
              type="button"
              className="st-play-small"
              disabled={!performance.track}
              aria-label={performance.track ? `${playing ? "Pause" : "Play"} ${performance.venue_name ?? ""}, ${longDate(performance.show_date)}` : `No tape for ${longDate(performance.show_date)}`}
              onClick={() => performance.track && onPlay(asPlayerTrack(performance.track, performance.show_date, performance.venue_name), queue)}
            >
              {playing ? <PauseIcon size={10} /> : <PlayIcon size={10} />}
            </button>
            <span className="st-row-date">{monthDay(performance.show_date)}</span>
            <span className="st-row-venue">
              {performance.venue_name}
              <small>
                {[performance.city, ...tags].filter(Boolean).join(" · ")}
              </small>
            </span>
            <span className="st-row-flow">{flowLine(performance, data.title)}</span>
            <span className="st-row-length">{clock(performance.seconds)}</span>
          </li>
        );
      })}
    </ol>
  );
}

function StopPath({
  data,
  stops,
  pathQueue,
  playingId,
  onPlayStop,
  onPlayPath
}: {
  data: SongTimelineData;
  stops: PlacedStop[];
  pathQueue: PlayerTrack[];
  playingId: string | null;
  onPlayStop: (stop: PlacedStop) => void;
  onPlayPath: () => void;
}) {
  const placed = new Map(stops.map((stop) => [stop.performance_id, stop]));
  const total = stops.reduce((sum, stop) => sum + (stop.seconds ?? 0), 0);
  const minutes = Math.round(total / 60);
  const length = minutes >= 60 ? `${Math.floor(minutes / 60)} hr ${minutes % 60} min` : `${minutes} min`;
  return (
    <section className="st-path" aria-label="Listening path">
      <div className="st-path-head">
        <div>
          <h4>Hear its life in {plural(data.stops.length, "stop")}</h4>
          {total > 0 && <p>{length} of listening</p>}
        </div>
        {pathQueue.length > 0 && (
          <button type="button" className="st-play-path" onClick={onPlayPath}>
            <PlayIcon size={14} />
            Play the path
          </button>
        )}
      </div>
      <ol className="st-stops">
        {data.stops.map((stop, index) => {
          const place = placed.get(stop.performance_id);
          const body = (
            <>
              <span className="st-stop-number" aria-hidden="true">
                {index + 1}
              </span>
              <span className="st-stop-text">
                {stop.label && <span className="st-stop-label">{stop.label}</span>}
                {place && (
                  <span className="st-stop-meta">
                    {[place.venue_name, shortDate(place.show_date), place.seconds != null ? clock(place.seconds) : null].filter(Boolean).join(" · ")}
                  </span>
                )}
                {stop.why && <span className="st-stop-why">{stop.why}</span>}
              </span>
            </>
          );
          return (
            <li key={`${stop.performance_id}-${index}`}>
              {place && place.track ? (
                <button
                  type="button"
                  className={playingId === stop.performance_id ? "st-stop st-stop-playing" : "st-stop"}
                  aria-label={`Play stop ${index + 1}${stop.label ? `, ${stop.label}` : ""}`}
                  onClick={() => onPlayStop(place)}
                >
                  {body}
                </button>
              ) : (
                <div className="st-stop st-stop-text-only">{body}</div>
              )}
            </li>
          );
        })}
      </ol>
    </section>
  );
}
