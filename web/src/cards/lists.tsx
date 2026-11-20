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

// An editorial item's title; when the item names a show or performance the
// library can play, the title plays it in-page.
export function EditorialTitle({ item }: { item: Extract<ExperienceBlock, { type: "editorial" }>["items"][number] }) {
  const queue = (item.tracks ?? []).map((track) => toTrack(track, {}));
  if (queue.length === 0) return <>{renderInline(item.title)}</>;
  return <ListenControl label={plainText(item.title)} track={queue[0]} queue={queue} scope="queue">{renderInline(item.title)}</ListenControl>;
}
