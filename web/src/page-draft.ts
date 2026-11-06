// The page as it grows while streaming, and the same shape read back from a
// finished response, so streamed and delivered pages go through one path.
import type { ExperienceBlock, ExperienceGroup, ExperienceResponse } from "./types";
import type { PageEvent } from "./stream-events";
import { readTab, type WorkspaceTab } from "./tab-routing";

export type RenderGroup = {
  title: string | null;
  lead: string | null;
  presentation: ExperienceGroup["presentation"];
  criteria: string[];
  blocks: ExperienceBlock[];
  tab: WorkspaceTab | null;
};
export type Draft = { title: string; lead: string | null; groups: RenderGroup[] };

export function emptyGroup(): RenderGroup {
  return { title: null, lead: null, presentation: "collection", criteria: [], blocks: [], tab: null };
}

// The draft page grows in reading order. A block for a group we have not
// heard of yet gets a provisional group; group_close fills the heading in.
export function applyPageEvent(draft: Draft | null, event: PageEvent): Draft | null {
  // A page_tab event carries no draft content; leave the draft as it is.
  if (event.type === "page_tab") return draft;
  if (event.type === "page_reset") return null;
  if (event.type === "groups_reset") return draft ? { ...draft, groups: [] } : draft;
  if (event.type === "page_head") return { title: event.title, lead: event.lead, groups: draft?.groups ?? [] };
  const current: Draft = draft ?? { title: "", lead: null, groups: [] };
  const groups = current.groups.slice();
  const index = event.type === "block" ? event.group_index : event.index;
  if (!Number.isInteger(index) || index < 0) return draft;
  while (groups.length <= index) groups.push(emptyGroup());
  if (event.type === "block") {
    groups[index] = { ...groups[index], blocks: [...groups[index].blocks, event.block] };
  } else {
    groups[index] = {
      ...groups[index],
      title: event.title,
      lead: event.lead,
      presentation: event.presentation,
      criteria: event.criteria,
      tab: readTab(event.tab) ?? groups[index].tab
    };
  }
  return { ...current, groups };
}

export function groupsOfResponse(response: ExperienceResponse): RenderGroup[] {
  return response.groups.map((group) => ({
    title: group.title ?? null,
    lead: group.lead ?? null,
    presentation: group.presentation,
    criteria: group.criteria ?? [],
    blocks: group.block_indexes.map((index) => response.blocks[index]).filter((block): block is ExperienceBlock => Boolean(block)),
    tab: readTab(group.tab)
  }));
}
