import { Suspense } from "react";
import { type ExperienceBlock, type SourceReference } from "../types";
import { RichText } from "./text";
import { CardHeading, TopicChips } from "./components";
import { type FollowUp } from "../core/ask-request";
import { Grid } from "./Grid";
import { ListeningHero, PullQuote } from "./listening";
import { SongVersions } from "./SongVersions";
import { PeopleTimeline } from "./PeopleTimeline";
import { VersionStrip } from "./VersionStrip";
import { countLabel } from "../core/format";
import { ExternalLink, renderInline, Eyebrow, AskChip } from "./inline";
import { MediaEmbed, ListenActionList, IdRow, PeopleList } from "./parts";
import { repeatsBlockTitle } from "./headings";
import { RankedList, EditorialTitle } from "./lists";
import { ShowUnit } from "./units/ShowUnit";
import { AlbumUnit } from "./units/AlbumUnit";
import { SongOverviewUnit } from "./units/SongOverviewUnit";
import { DataChart } from "./lazy-chart";

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
    case "editorial":
      if (block.presentation === "narrative") return (
        <section className="typography-block narrative-block">
          <Eyebrow label={block.eyebrow} title={block.title} />
          {block.title && <CardHeading>{block.title}</CardHeading>}
          {block.paragraphs.map((paragraph, index) => <RichText key={index} text={paragraph} />)}
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
