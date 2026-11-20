import { type SourceReference } from "../types";
import { HeadingContext } from "./components";
import { type FollowUp } from "../core/ask-request";
import { type RenderGroup } from "../core/page-draft";
import { archiveTrack } from "./listen-control";
import { formatShowDateLong } from "../core/format";
import { ExternalLink } from "./inline";
import { RichText } from "./text";
import { isUnit, unitKey } from "./units/shared";
import { MentionRow, chunkMentions, CollapsedRow } from "./units/rows";
import { blockHeading, sameHeading } from "./headings";
import { Block } from "./Block";

function dedupeSources(sources: SourceReference[]): SourceReference[] {
  const seen = new Set<string>();
  const result: SourceReference[] = [];
  for (const source of sources) {
    const key = `${source.label}|${source.url ?? ""}`;
    if (seen.has(key)) continue;
    seen.add(key);
    result.push(source);
  }
  return result;
}

// The Internet Archive tapes behind the page's playable tracks, each once,
// named by the show the block places it in, for the sources footer.
type Tape = { identifier: string; showDate: string | null; venueName: string | null };

const ARCHIVE_DETAILS = /^https?:\/\/(?:www\.)?archive\.org\/details\/([^/?#]+)/;

function pageTapes(groups: RenderGroup[]): Tape[] {
  const tapes = new Map<string, Tape>();
  const visit = (value: unknown, show: { showDate: string | null; venueName: string | null }) => {
    if (Array.isArray(value)) {
      for (const item of value) visit(item, show);
      return;
    }
    if (!value || typeof value !== "object") return;
    const record = value as Record<string, unknown>;
    const here = {
      showDate: typeof record.show_date === "string" ? record.show_date : show.showDate,
      venueName: typeof record.venue_name === "string" ? record.venue_name : show.venueName
    };
    for (const [key, field] of Object.entries(record)) {
      if (typeof field !== "string") {
        visit(field, here);
        continue;
      }
      const identifier = key === "recording_identifier" ? field : (archiveTrack(field)?.identifier ?? ARCHIVE_DETAILS.exec(field)?.[1]);
      if (!identifier) continue;
      const known = tapes.get(identifier);
      if (!known || (!known.showDate && here.showDate)) tapes.set(identifier, { identifier, ...here });
    }
  };
  for (const group of groups) visit(group.blocks, { showDate: null, venueName: null });
  return [...tapes.values()].sort((a, b) => (a.showDate ?? "9999").localeCompare(b.showDate ?? "9999") || a.identifier.localeCompare(b.identifier));
}

function showLabel(tape: Tape): string {
  if (!tape.showDate) return tape.venueName ?? tape.identifier;
  return [tape.venueName, formatShowDateLong(tape.showDate)].filter(Boolean).join(", ");
}

// Two tapes of one show are told apart by the tape's own name after its date
// ("sbd.hicks"), the way tapers know them.
function tapeLabels(tapes: Tape[]): Map<string, string> {
  const shows = tapes.map(showLabel);
  return new Map(
    tapes.map((tape, index) => {
      const shared = shows.filter((label) => label === shows[index]).length > 1;
      const name = tape.identifier.replace(/^gd\d{2,4}-\d{2}-\d{2}\.?/, "") || tape.identifier;
      return [tape.identifier, shared && name !== shows[index] ? `${shows[index]} (${name})` : shows[index]];
    })
  );
}

// The page's groups in the model's order, each with its heading and its
// blocks.
export function PageGroups({
  groups,
  sources,
  composing,
  onFollowUp
}: {
  groups: RenderGroup[];
  sources: SourceReference[];
  composing: boolean;
  onFollowUp: FollowUp;
}) {
  // A primary unit's facets start open only when it is the page's sole unit;
  // typography blocks (era_unit, editorial, and the rest) do not count.
  const unitCount = groups.reduce((count, group) => count + group.blocks.filter(isUnit).length, 0);
  return (
    <>
      {groups.map((group, groupIndex) => {
        const groupTitle = group.blocks.length === 1 && sameHeading(group.title, blockHeading(group.blocks[0])) ? null : group.title;
        return (
        <section className={`experience-group group-${group.presentation}${groupTitle ? " has-heading" : ""}`} key={groupIndex}>
          {(groupTitle || group.lead) && (
            group.presentation === "argument" ? (
              <header className="group-heading claim">
                {groupTitle && <h2>{groupTitle}</h2>}
                {group.lead && <RichText className="claim-text" text={group.lead} />}
              </header>
            ) : (
              <header className="group-heading">
                {groupTitle && <h2>{groupTitle}</h2>}
                {group.lead && <RichText text={group.lead} />}
              </header>
            )
          )}
          <HeadingContext.Provider value={groupTitle ? "h3" : "h2"}>
            <div className="block-grid group-blocks">
              {chunkMentions(group.blocks).map((entry) =>
                entry.kind === "mentions" ? (
                  <ul className="mention-list" key={entry.key}>
                    {entry.blocks.map((block) => <MentionRow key={`${block.type}-${unitKey(block)}`} block={block} />)}
                  </ul>
                ) : entry.kind === "collapsed" ? (
                  <ul className="collapsed-list" key={entry.key}>
                    {entry.blocks.map((block, index) => (
                      <CollapsedRow key={`${block.type}-${unitKey(block)}-${index}`} block={block} onFollowUp={onFollowUp}>
                        <Block
                          block={block}
                          sources={sources}
                          criteria={group.presentation === "comparison" ? group.criteria : []}
                          soleUnit={false}
                          onFollowUp={onFollowUp}
                          inRow
                        />
                      </CollapsedRow>
                    ))}
                  </ul>
                ) : (
                  <Block
                    key={entry.key}
                    block={entry.block}
                    sources={sources}
                    criteria={group.presentation === "comparison" ? group.criteria : []}
                    soleUnit={composing ? false : unitCount === 1}
                    onFollowUp={onFollowUp}
                  />
                )
              )}
            </div>
          </HeadingContext.Provider>
        </section>
        );
      })}
    </>
  );
}

// The page's sources and the Internet Archive tapes behind its playable
// tracks, once the page is finished.
export function SourcesFooter({ groups, sources }: { groups: RenderGroup[]; sources: SourceReference[] }) {
  const tapes = pageTapes(groups);
  const tapeNames = tapeLabels(tapes);
  if (sources.length === 0 && tapes.length === 0) return null;
  return (
    <footer className="sources-footer">
      <p className="sources-footer-label">Sources</p>
      <ul>
        {dedupeSources(sources).map((source) => (
          <li key={`${source.label}-${source.url ?? source.source_id}`}>
            <span className="source-kind-chip">
              {source.kind === "canonical" ? "Canonical" : "External source"}
            </span>
            {source.url ? (
              <ExternalLink href={source.url}>{source.label}</ExternalLink>
            ) : (
              <span>{source.label}</span>
            )}
          </li>
        ))}
        {tapes.map((tape) => (
          <li key={tape.identifier}>
            <span className="source-kind-chip">Internet Archive</span>
            <ExternalLink href={`https://archive.org/details/${tape.identifier}`}>{tapeNames.get(tape.identifier)}</ExternalLink>
          </li>
        ))}
      </ul>
    </footer>
  );
}
