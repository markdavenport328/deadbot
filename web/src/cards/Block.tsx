import { Suspense } from "react";
import { type ExperienceBlock, type SourceReference } from "../types";
import { CardHeading, MoreAbout, TopicChips } from "./components";
import { type FollowUp } from "../core/ask-request";
import { Grid } from "./Grid";
import { type PlayerTrack } from "../player/player";
import { ClampText, ListeningHero, PullQuote, toTrack } from "./listening";
import { SongVersions } from "./SongVersions";
import { PeopleTimeline } from "./PeopleTimeline";
import { VersionStrip } from "./VersionStrip";
import { ListenControl, trackFor, type TrackMeta } from "./listen-control";
import { formatShowDateLong, countLabel, capitalize } from "../core/format";
import { ExternalLink, renderInline, Eyebrow, AskChip } from "./inline";
import { MediaEmbed, ListenActionList, IdRow, Meta, PeopleList, GoDeeper, venueFirstShowLabel } from "./parts";
import { splitShowLabel } from "./units/shared";
import { repeatsBlockTitle } from "./headings";
import { RankedList, PersonRoster, EditorialTitle } from "./lists";
import { ShowUnit } from "./units/ShowUnit";
import { AlbumUnit } from "./units/AlbumUnit";
import { PerformanceUnit } from "./units/PerformanceUnit";
import { SongOverviewUnit } from "./units/SongOverviewUnit";
import { DataChart } from "./lazy-chart";

function sourceFor(sources: SourceReference[], sourceId: string): SourceReference | undefined {
  return sources.find((source) => source.source_id === sourceId);
}

export function Block({
  block,
  sources,
  criteria,
  soleUnit,
  onFollowUp,
  inRow = false
}: {
  block: ExperienceBlock;
  sources: SourceReference[];
  criteria: string[];
  soleUnit: boolean;
  onFollowUp: FollowUp;
  // Rendered inside a collapsed row that the visitor opened: the row keeps
  // its header, so the unit shows only what opens beneath it.
  inRow?: boolean;
}) {
  switch (block.type) {
    case "show_unit":
      return <ShowUnit unit={block} criteria={criteria} soleUnit={soleUnit} onFollowUp={onFollowUp} inRow={inRow} />;
    case "performance_unit":
      return <PerformanceUnit block={block} criteria={criteria} onFollowUp={onFollowUp} inRow={inRow} />;
    case "era_unit":
      return (
        <section className="era-unit">
          <IdRow type="Era" when={block.span} />
          <CardHeading>{block.title}</CardHeading>
          {block.note && <ClampText className="unit-note">{renderInline(block.note)}</ClampText>}
          <ul className="era-performances">
            {block.performances.map((performance) => (
              <li key={performance.performance_id}>
                <ListenControl
                  url={performance.listen?.url}
                  label={venueFirstShowLabel(performance.show_date, performance.venue_name, performance.show_label)}
                  track={trackFor(
                    { performance_id: performance.performance_id, audio_url: performance.audio_url, duration_seconds: performance.duration_seconds, listen_url: performance.listen?.is_official ? null : performance.listen?.url },
                    performance.song_title,
                    { showDate: performance.show_date, venueName: performance.venue_name ?? splitShowLabel(performance.show_label).venue }
                  )}
                  name={`${performance.song_title}, ${venueFirstShowLabel(performance.show_date, performance.venue_name, performance.show_label)}`}
                  className="list-item-label"
                />
                <span>{[performance.song_title, performance.set_label].filter(Boolean).join(" · ")}</span>
              </li>
            ))}
          </ul>
          {(block.sources.length > 0 || (block.follow_ups ?? []).length > 0) && (
            <footer className="unit-footer">
              <GoDeeper sources={block.sources} />
              <MoreAbout topics={block.follow_ups} onFollowUp={onFollowUp} />
            </footer>
          )}
        </section>
      );
    case "album_unit":
      return <AlbumUnit block={block} criteria={criteria} soleUnit={soleUnit} onFollowUp={onFollowUp} inRow={inRow} />;
    case "entity_card": {
      const typeLabel = block.entity_type === "song" ? "Song" : block.entity_type === "show" ? "Show" : "Performance";
      return (
        <article className="typography-block entity-block">
          <IdRow type={typeLabel} />
          <CardHeading>{block.title}</CardHeading>
          {block.subtitle && <p className="meta">{block.subtitle}</p>}
          {block.details.length > 0 && (
            <ul className="details">
              {block.details.map((detail) => <li key={detail}>{detail}</li>)}
            </ul>
          )}
          {block.follow_up && (
            <footer className="unit-footer">
              <div className="ask-block">
                <span className="k">Ask</span>
                <AskChip prompt={block.follow_up} onFollowUp={onFollowUp} />
              </div>
            </footer>
          )}
        </article>
      );
    }
    case "show_selection":
      return (
        <section className="typography-block show-selection">
          <IdRow type={block.selection_type} when={countLabel(block.items.length, "show")} />
          <CardHeading>{block.title}</CardHeading>
          <p className="meta">Selected by {block.selector_name}</p>
          <ol className="entry-list two-up">
            {block.items.map((item) => (
              <li key={item.show_id}>
                <ListenControl
                  label={item.venue_name}
                  queue={(item.tracks ?? []).map((track) => toTrack(track, { showDate: item.show_date, venueName: item.venue_name, recordingDetailsUrl: item.recording_identifier ? `https://archive.org/details/${item.recording_identifier}` : null }))}
                  scope="queue"
                  name={`${item.venue_name}, ${formatShowDateLong(item.show_date)}`}
                  className="entry-title"
                />
                <span className="entry-detail">{[formatShowDateLong(item.show_date), item.location].filter(Boolean).join(" · ")}</span>
              </li>
            ))}
          </ol>
          <p className="coverage-note">{block.coverage_note}</p>
        </section>
      );
    case "guest_appearance_list":
      return (
        <section className="typography-block guest-appearance-list">
          <IdRow type="Guest appearances" when={countLabel(block.known_show_count, "show")} />
          <CardHeading>{block.person_name}</CardHeading>
          <ol className="entry-list two-up">
            {block.items.map((item) => (
              <li key={item.show_id}>
                <span className="entry-title">{item.venue_name || formatShowDateLong(item.show_date)}</span>
                <span className="entry-detail">
                  {[item.venue_name ? formatShowDateLong(item.show_date) : null, item.location, item.instruments.join(", "), item.participation_scope].filter(Boolean).join(" · ")}
                </span>
                {item.songs && item.songs.length > 0 && (() => {
                  const meta: TrackMeta = { showDate: item.show_date, venueName: item.venue_name };
                  const tracks = item.songs.map((song) => trackFor(song, song.song_title, meta));
                  const queue = tracks.filter((track): track is PlayerTrack => track !== null);
                  return (
                    <span className="entry-detail">
                      {item.songs.map((song, index) => (
                        <span key={song.performance_id}>
                          {index > 0 && ", "}
                          <ListenControl label={song.song_title} track={tracks[index]} queue={queue} queueable={false} />
                        </span>
                      ))}
                    </span>
                  );
                })()}
              </li>
            ))}
          </ol>
        </section>
      );
    case "person_roster":
      return <PersonRoster block={block} onFollowUp={onFollowUp} />;
    case "equipment_list":
      return (
        <section className="typography-block equipment-list">
          <IdRow type="Equipment" when={countLabel(block.items.length, "item")} />
          <CardHeading>{block.title}</CardHeading>
          <ul className="entry-list two-up">
            {block.items.map((item) => (
              <li key={`${item.equipment_id}-${item.usage_context}-${item.evidence}`}>
                <span className="entry-title">{item.name}</span>
                <span className="entry-detail">{[item.manufacturer, item.model].filter(Boolean).join(" ")}</span>
                <span className="entry-detail">
                  {item.usage_context} · {item.claim_type === "show" ? "seen at this show" : "dated to this period"} · {item.evidence}
                </span>
                <ExternalLink className="entry-link" href={item.source_url}>Source note</ExternalLink>
              </li>
            ))}
          </ul>
        </section>
      );
    case "song_overview":
      return <SongOverviewUnit block={block} criteria={criteria} soleUnit={soleUnit} onFollowUp={onFollowUp} inRow={inRow} />;
    case "resource_list":
      return (
        <section className="typography-block resource-list">
          <IdRow type="Go deeper" when={countLabel(block.items.length, "source")} />
          <CardHeading>{block.title}</CardHeading>
          <div className="reading">
            {block.items.map((item) => (
              <div className="reading-source" key={item.resource_id}>
                <p className="reading-title"><ExternalLink href={item.url}>{item.title}</ExternalLink></p>
                <p className="reading-pub">
                  <span className="pub">{item.source_name}</span> · {item.resource_type}{item.context_note ? ` · ${item.context_note}` : ""}
                </p>
              </div>
            ))}
          </div>
        </section>
      );
    case "credit_list":
      return (
        <section className="typography-block credit-list">
          <IdRow type="Composition" />
          <CardHeading>{block.title}</CardHeading>
          <PeopleList people={block.items.map((item) => ({ key: `${item.person_id}-${item.role}`, name: item.name, detail: item.role }))} />
        </section>
      );
    case "media_link":
      return (
        <section className="card media-card">
          <IdRow type={block.provider} when={block.is_official ? "Official release" : null} />
          <CardHeading>{block.title}</CardHeading>
          <MediaEmbed block={block} />
          <ListenActionList actions={[{ label: `Open on ${block.provider}`, provider: block.provider, url: block.url, is_official: block.is_official }]} />
        </section>
      );
    case "coverage":
      return (
        <aside className="typography-block aside-block coverage-block">
          <span className="k">Library coverage</span>
          <p className="aside-title">{block.title}</p>
          <p>{block.message}</p>
        </aside>
      );
    case "arrangement": {
      const source = sourceFor(sources, block.source_id);
      return (
        <section className="typography-block arrangement-block">
          <IdRow type="Arrangement" when={block.key_signature ? `Key of ${block.key_signature}` : null} />
          <CardHeading>{block.title}</CardHeading>
          <Meta parts={[capitalize(block.arrangement_scope.replaceAll("-", " ")), block.capo ? `Capo ${block.capo}` : null, block.tuning ? `${block.tuning} tuning` : null]} />
          {block.notes && <p className="unit-note">{block.notes}</p>}
          {block.progressions.length > 0 && (
            <ul className="chords">
              {block.progressions.map((progression, index) => <li key={`${index}-${progression}`}>{progression}</li>)}
            </ul>
          )}
          {source?.url && (
            <div className="reading">
              <p className="reading-pub"><ExternalLink href={source.url}>Open the source</ExternalLink></p>
            </div>
          )}
        </section>
      );
    }
    case "arrangement_search":
      return (
        <section className="typography-block arrangement-search">
          <IdRow type="Musician’s reference" when={`Key of ${block.key_signature}`} />
          <CardHeading>{block.title}</CardHeading>
          <p className="meta">{block.coverage_note}</p>
          <ul className="entry-list">
            {block.items.map((item) => (
              <li key={item.arrangement_id}>
                <span className="entry-title">{item.title}</span>
                <span className="entry-detail">{capitalize(item.arrangement_scope.replaceAll("-", " "))} · key of {item.key_signature}</span>
                <ExternalLink className="entry-link" href={item.url}>{item.resource_title} · {item.source_name}</ExternalLink>
              </li>
            ))}
          </ul>
        </section>
      );
    case "editorial":
      if (block.presentation === "narrative") return (
        <section className="typography-block narrative-block">
          <Eyebrow label={block.eyebrow} title={block.title} />
          {block.title && <CardHeading>{block.title}</CardHeading>}
          {block.paragraphs.map((paragraph, index) => <p key={index}>{renderInline(paragraph)}</p>)}
        </section>
      );
      if (block.presentation === "fact_grid") return (
        <section className="typography-block fact-grid-block">
          <Eyebrow label={block.eyebrow} title={block.title} />
          {block.title && <CardHeading>{block.title}</CardHeading>}
          <dl>
            {block.items.map((item, index) => (
              <div key={`${item.marker ?? item.title}-${index}`}>
                {item.marker ? <dt>{item.marker}</dt> : !repeatsBlockTitle(block, item) && <dt className="fact-subject"><EditorialTitle item={item} /></dt>}
                {item.marker && !repeatsBlockTitle(block, item) && <dd className="fact-subject"><EditorialTitle item={item} /></dd>}
                {item.value && (
                  <dd className={item.value.trim().length <= 20 ? "fact-value display" : "fact-value"}>
                    {renderInline(item.value)}
                  </dd>
                )}
                {item.detail && <dd className="fact-detail">{renderInline(item.detail)}</dd>}
                {item.link && <dd className="fact-link"><ExternalLink href={item.link.url} label={item.link.label}>{item.link.label}</ExternalLink></dd>}
                {(item.follow_ups ?? []).length > 0 && <dd className="fact-ask"><TopicChips topics={item.follow_ups} onFollowUp={onFollowUp} /></dd>}
              </div>
            ))}
          </dl>
        </section>
      );
      return (
        <section className="typography-block timeline-block">
          <Eyebrow label={block.eyebrow} title={block.title} />
          {block.title && <CardHeading>{block.title}</CardHeading>}
          <ol>
            {block.items.map((item, index) => (
              <li key={`${item.marker ?? item.title}-${index}`}>
                {item.marker && <span className="timeline-marker">{item.marker}</span>}
                {!repeatsBlockTitle(block, item) && <strong><EditorialTitle item={item} /></strong>}
                {item.detail && <span className="timeline-detail">{renderInline(item.detail)}</span>}
                {item.link && <ExternalLink className="timeline-link" href={item.link.url} label={item.link.label}>{item.link.label}</ExternalLink>}
                {(item.follow_ups ?? []).length > 0 && <span className="timeline-ask"><TopicChips topics={item.follow_ups} onFollowUp={onFollowUp} /></span>}
              </li>
            ))}
          </ol>
        </section>
      );
    case "provenance_note":
      return (
        <aside className="typography-block aside-block provenance-note">
          <span className="k">From the source</span>
          <p>{block.text}</p>
        </aside>
      );
    case "gap_state":
      return (
        <aside className="typography-block aside-block gap-state">
          <span className="k">Not in the library</span>
          <p>{block.message}</p>
        </aside>
      );
    case "listening_hero":
      return <ListeningHero block={block} />;
    case "pull_quote":
      return <PullQuote block={block} />;
    case "ranked_list":
      return <RankedList block={block} onFollowUp={onFollowUp} />;
    case "data_chart":
      return (
        <Suspense fallback={<div className="data-chart-figure data-chart-loading">Loading chart…</div>}>
          <DataChart block={block} onFollowUp={onFollowUp} />
        </Suspense>
      );
    case "version_strip":
      return <VersionStrip block={block} />;
    case "song_versions":
      return <SongVersions block={block} />;
    case "people_timeline":
      return <PeopleTimeline block={block} />;
    case "grid":
      return <Grid block={block} onFollowUp={onFollowUp} />;
  }
}
