// Where each part of a page lives in the workspace. The model names a tab per
// group; this file reads that name leniently and, when a group has none (an
// older response, a cached one, a skipped field), places the whole group by
// its first block. This is compatibility, not routing: the model's choice wins.
import type { ExperienceBlock } from "./types";
import type { RenderGroup } from "./page-draft";

export type WorkspaceTab = "listen" | "charts" | "read";

export const WORKSPACE_TABS: readonly { id: WorkspaceTab; label: string }[] = [
  { id: "listen", label: "Listen" },
  { id: "charts", label: "Charts" },
  { id: "read", label: "Read" }
];

const NAMES: Record<string, WorkspaceTab> = {
  listen: "listen", listening: "listen", hear: "listen",
  charts: "charts", chart: "charts",
  read: "read", context: "read", story: "read", info: "read"
};

export function readTab(value: unknown): WorkspaceTab | null {
  if (typeof value !== "string") return null;
  const name = value.trim().toLowerCase();
  // Own keys only: "constructor" and "toString" must not resolve to inherited members.
  return Object.hasOwn(NAMES, name) ? NAMES[name] : null;
}

const LISTEN = new Set(["show_unit", "performance_unit", "album_unit", "song_overview", "show_selection", "listening_hero", "version_strip", "media_link"]);
const CHARTS = new Set(["data_chart", "grid"]);

export function fallbackTab(block: ExperienceBlock | undefined): WorkspaceTab {
  if (!block) return "read";
  if (block.type === "entity_card") return block.entity_type === "song" ? "read" : "listen";
  if (LISTEN.has(block.type)) return "listen";
  if (CHARTS.has(block.type)) return "charts";
  return "read";
}

export type RoutedPage = Record<WorkspaceTab, RenderGroup[]>;

export function routeGroups(groups: RenderGroup[]): RoutedPage {
  const routed: RoutedPage = { listen: [], charts: [], read: [] };
  for (const group of groups) routed[group.tab ?? fallbackTab(group.blocks[0])].push(group);
  return routed;
}

export function openingTab(initial: WorkspaceTab | null, routed: RoutedPage): WorkspaceTab {
  if (initial) return initial;
  return routed.listen.length > 0 ? "listen" : "read";
}

export function tabsWithContent(routed: RoutedPage, answer: string | null): Set<WorkspaceTab> {
  const tabs = new Set<WorkspaceTab>();
  // A group opened mid-stream has no cards yet; a tab counts once one arrives.
  for (const { id } of WORKSPACE_TABS) if (routed[id].some((group) => group.blocks.length > 0)) tabs.add(id);
  if (answer && answer.trim()) tabs.add("read");
  return tabs;
}
