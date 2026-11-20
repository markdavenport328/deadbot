import { Suspense, useMemo } from "react";
import { type ExperienceBlock } from "../../types";
import { CardHeading, Drawer, MoreAbout, type DrawerTab } from "../components";
import { type FollowUp } from "../../core/ask-request";
import { ClampText } from "../listening";
import { SongTimeline } from "../SongTimeline";
import { type SongTimelineData } from "../song-timeline-types";
import { askFocus } from "../song-timeline-text";
import { ListenControl, trackFor } from "../listen-control";
import { capitalize } from "../../core/format";
import { renderInline } from "../inline";
import { IdRow, Meta, PlainList, GoDeeper, venueFirstShowLabel } from "../parts";
import { UnitFrame, CriteriaTable, type SongOverviewBlockT, splitShowLabel, songName } from "./shared";
import { DataChart } from "../lazy-chart";

// A song's plays per year, as the same bar chart an aggregate_data result
// draws: years along the bottom, a year it was not played an empty slot.
function songYearChart(block: SongOverviewBlockT): Extract<ExperienceBlock, { type: "data_chart" }> {
  const rows = (block.year_counts ?? []).map((entry) => ({ year: entry.year, value: entry.count }));
  return {
    type: "data_chart",
    aggregation_id: `song-years:${block.song_id}`,
    title: `${songName(block)} by year`,
    note: null,
    chart: "bar",
    orientation: "vertical",
    columns: [
      { key: "year", label: "Year", type: "temporal" },
      { key: "value", label: "Performances", type: "quantitative" }
    ],
    rows,
    metric_label: "Performances",
    total: rows.reduce((sum, row) => sum + row.value, 0),
    excluded_count: 0,
    date_range: null,
    empty_reason: null
  };
}

// A song card's timeline data: the library's years and lengths, and the
// model's stops, open year, first view and year questions.
function timelineData(block: SongOverviewBlockT): SongTimelineData {
  return {
    song_id: block.song_id,
    title: songName(block),
    performance_count: block.known_performance_count,
    year_summaries: block.year_summaries ?? [],
    length_points: block.length_points ?? [],
    stops: block.representative_performances.map((stop) => ({
      performance_id: stop.performance_id,
      label: stop.label ?? null,
      why: stop.why ?? null,
      show_date: stop.show_date ?? null,
      venue_name: stop.venue_name ?? null,
      seconds: stop.seconds ?? null,
      track: stop.audio_url
        ? { performance_id: stop.performance_id, title: songName(block), audio_url: stop.audio_url, duration_seconds: stop.duration_seconds ?? null, set_label: stop.set_label ?? null, audio_parts: stop.audio_parts ?? null }
        : null
    })),
    open_year: block.open_year ?? null,
    chart_view: block.chart_view ?? null,
    year_questions: block.year_questions ?? []
  };
}

export function SongOverviewUnit({
  block,
  criteria,
  soleUnit,
  onFollowUp,
  inRow = false
}: {
  block: SongOverviewBlockT;
  criteria: string[];
  soleUnit: boolean;
  onFollowUp: FollowUp;
  inRow?: boolean;
}) {
  const openFacets = (block.emphasis === "primary" && soleUnit) || inRow;
  const showsFacet = (facet: SongOverviewBlockT["visible_facets"][number]) => block.visible_facets.includes(facet);
  // With by_year the song's life is one timeline: the chart, the model's stops
  // and every performance a year away.
  const timeline = showsFacet("by_year") && (block.year_summaries ?? []).length > 0;

  const tabs: DrawerTab[] = [];
  if (showsFacet("albums") && block.albums.length > 0) {
    tabs.push({
      id: "record",
      label: "On record",
      count: block.albums.length,
      content: (
        <ul className="entry-list two-up records">
          {block.albums.map((album) => {
            const detail = [capitalize(album.release_type), album.release_date?.slice(0, 4)].filter(Boolean).join(" · ");
            return (
              <li key={album.release_id}>
                <ListenControl url={album.listen_url} label={album.title} className="entry-title" />
                <span className="entry-detail">{detail}</span>
              </li>
            );
          })}
        </ul>
      )
    });
  }
  if (showsFacet("credits") && block.credits.length > 0) {
    tabs.push({
      id: "credits",
      label: "Credits",
      count: block.credits.length,
      content: (
        <PlainList items={block.credits.map((credit) => ({ key: `${credit.person_id}-${credit.role}`, title: credit.name, detail: credit.role }))} />
      )
    });
  }
  const initialOpen = openFacets && tabs.length > 0 ? tabs[0].id : null;
  // Without a timeline to carry them, the model's stops list on the card.
  const representatives = (showsFacet("representatives") || showsFacet("by_year")) && !timeline ? block.representative_performances : [];
  const timelineInput = useMemo(() => timelineData(block), [block]);

  return (
    <UnitFrame inRow={inRow} className={`song-overview emphasis-${block.emphasis}`}>
      {!inRow && (
        <>
          <IdRow type="Song" when={`${block.known_performance_count} performance${block.known_performance_count === 1 ? "" : "s"}`} />
          <CardHeading>{block.title}</CardHeading>
          <Meta parts={[block.original_artist ? `Originally by ${block.original_artist}` : null]} />
        </>
      )}
      {block.note && !inRow && <ClampText className="unit-note">{renderInline(block.note)}</ClampText>}
      <CriteriaTable criteria={criteria} judgments={block.judgments} />
      {timeline ? (
        <SongTimeline
          // The final page can change the model's open year or first view after the draft streamed.
          key={`${block.song_id}:${block.open_year ?? ""}:${block.chart_view ?? ""}`}
          data={timelineInput}
          onAsk={(question, focus) => onFollowUp(question, askFocus(focus))}
        />
      ) : (
        showsFacet("by_year") &&
        (block.year_counts ?? []).length > 0 && (
          <Suspense fallback={<div className="data-chart-figure data-chart-loading">Loading chart…</div>}>
            <DataChart block={songYearChart(block)} embedded />
          </Suspense>
        )
      )}
      {representatives.length > 0 && (
        <section className="song-representatives">
          <ul>
            {representatives.map((performance, index) =>
              performance.show_date || performance.show_label ? (
                <li key={`${performance.performance_id}-${index}`}>
                  <ListenControl
                    url={performance.listen_url}
                    label={venueFirstShowLabel(performance.show_date, performance.venue_name, performance.show_label)}
                    track={trackFor(performance, songName(block), { showDate: performance.show_date, venueName: performance.venue_name ?? splitShowLabel(performance.show_label).venue })}
                    name={`${songName(block)}, ${venueFirstShowLabel(performance.show_date, performance.venue_name, performance.show_label)}`}
                    className="list-item-label"
                  />
                  {[performance.label, performance.set_label].filter(Boolean).length > 0 && <span>{[performance.label, performance.set_label].filter(Boolean).join(" · ")}</span>}
                  {performance.why && <span>{performance.why}</span>}
                </li>
              ) : (
                // A stop the library could not place keeps the model's words.
                <li key={`${performance.performance_id}-${index}`}>
                  <span className="list-item-label">{performance.label ?? performance.why}</span>
                  {performance.label && performance.why && <span>{performance.why}</span>}
                </li>
              )
            )}
          </ul>
        </section>
      )}
      <Drawer tabs={tabs} initialOpen={initialOpen} />
      {(block.sources.length > 0 || (block.follow_ups ?? []).length > 0) && (
        <footer className="unit-footer">
          <GoDeeper sources={block.sources} />
          <MoreAbout topics={block.follow_ups} onFollowUp={onFollowUp} />
        </footer>
      )}
    </UnitFrame>
  );
}
