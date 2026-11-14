import { useId } from "react";
import { type ExperienceBlock } from "../types";
import { CardHeading } from "./components";
import { type FollowUp } from "../core/ask-request";
import { toTrack } from "./listening";
import { ListenControl } from "./listen-control";
import { RowPanel, panelId, useOpenRow, type RowSource } from "./RowOpener";
import { countLabel } from "../core/format";
import { plainText, renderInline } from "./inline";
import { IdRow } from "./parts";

// The top rows of one aggregate_data result: rank, name, count, and the
// model's note where it wrote one. One column, numbers aligned.
export function RankedList({ block, onFollowUp }: { block: Extract<ExperienceBlock, { type: "ranked_list" }>; onFollowUp?: FollowUp }) {
  // Each row carries a bar on one shared scale, so the list is also the chart.
  const peak = Math.max(0, ...block.rows.map((row) => row.value));
  const rows = useOpenRow();
  const base = useId();
  const source: RowSource = { blockType: "ranked_list", blockId: block.aggregation_id, scope: block.open_scope ?? null };
  return (
    <section className="typography-block ranked-list">
      <CardHeading>{block.title}</CardHeading>
      {block.note && <p className="ranked-lead">{renderInline(block.note)}</p>}
      <ol className="ranked-rows">
        {block.rows.map((row) => {
          const rowId = row.opens && row.id ? row.id : null;
          const open = rowId !== null && rows.openId === rowId;
          const panel = rowId ? panelId(base, rowId) : undefined;
          return (
            <li key={`${row.rank}-${row.id ?? row.label}`} className={open ? "is-open" : undefined}>
              <span className="ranked-rank">{row.rank}</span>
              <span className="ranked-label">
                {rowId ? (
                  <button
                    type="button"
                    className="row-open"
                    aria-expanded={open}
                    aria-controls={open ? panel : undefined}
                    ref={rows.register(rowId)}
                    onClick={() => rows.toggle(rowId)}
                  >
                    {row.label}
                  </button>
                ) : (
                  row.label
                )}
                {peak > 0 && <span className="ranked-bar" aria-hidden="true" style={{ width: `${(row.value / peak) * 100}%` }} />}
                {row.note && <span className="ranked-note">{renderInline(row.note)}</span>}
              </span>
              <span className="ranked-value">{row.value.toLocaleString()}</span>
              {open && rowId && panel && <RowPanel id={panel} rowId={rowId} source={source} onFollowUp={onFollowUp} onClose={rows.close} />}
            </li>
          );
        })}
      </ol>
      <p className="ranked-meta">
        {block.metric_label}
        {block.more_count > 0 ? ` · ${block.more_count.toLocaleString()} more in the result` : ""}
      </p>
    </section>
  );
}

// A roster: each name opens in place to the person's facts, a night to hear
// them and a question about them.
export function PersonRoster({ block, onFollowUp }: { block: Extract<ExperienceBlock, { type: "person_roster" }>; onFollowUp?: FollowUp }) {
  const rows = useOpenRow();
  const base = useId();
  const source: RowSource = { blockType: "person_roster", blockId: block.title };
  return (
    <section className="typography-block person-roster">
      <IdRow type="Roster" when={countLabel(block.items.length, "name")} />
      <CardHeading>{block.title}</CardHeading>
      {block.lead && <p className="unit-note">{renderInline(block.lead)}</p>}
      <ul className="people roster">
        {block.items.map((item) => {
          const open = rows.openId === item.person_id;
          const panel = panelId(base, item.person_id);
          return (
            <li key={item.person_id} className={open ? "is-open" : undefined}>
              <button
                type="button"
                className="row-open"
                aria-expanded={open}
                aria-controls={open ? panel : undefined}
                ref={rows.register(item.person_id)}
                onClick={() => rows.toggle(item.person_id)}
              >
                {item.name}
              </button>
              <span>{rosterDetail(item)}</span>
              {item.note && <em className="roster-note">{renderInline(item.note)}</em>}
              {open && <RowPanel id={panel} rowId={item.person_id} source={source} onFollowUp={onFollowUp} onClose={rows.close} />}
            </li>
          );
        })}
      </ul>
    </section>
  );
}

// An editorial item's title; when the item names a show or performance the
// library can play, the title plays it in-page.
export function EditorialTitle({ item }: { item: Extract<ExperienceBlock, { type: "editorial" }>["items"][number] }) {
  const queue = (item.tracks ?? []).map((track) => toTrack(track, {}));
  if (queue.length === 0) return <>{renderInline(item.title)}</>;
  return <ListenControl label={plainText(item.title)} track={queue[0]} queue={queue} scope="queue">{renderInline(item.title)}</ListenControl>;
}

// The roles, show count and years line under a roster name; blank parts dropped.
function rosterDetail(item: Extract<ExperienceBlock, { type: "person_roster" }>["items"][number]): string {
  const years = item.first_year && item.last_year
    ? item.first_year === item.last_year ? item.first_year : `${item.first_year}–${item.last_year.slice(2)}`
    : null;
  return [(item.roles ?? []).join(", "), item.show_count > 0 ? countLabel(item.show_count, "show") : null, years].filter(Boolean).join(" · ");
}
