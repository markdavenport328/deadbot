import { expect, test } from "vitest";
import { fallbackTab, openingTab, readTab, routeGroups, tabsWithContent, WORKSPACE_TABS } from "./tab-routing";
import type { RenderGroup } from "./page-draft";

const g = (types: string[], tab: RenderGroup["tab"] = null, extra: Record<string, unknown> = {}): RenderGroup => ({
  title: null, lead: null, presentation: "collection", criteria: [], tab,
  blocks: types.map((type) => ({ type, ...extra }) as never)
});

test("labels and order", () => {
  expect(WORKSPACE_TABS.map((t) => t.label)).toEqual(["Listen", "Charts", "Read"]);
});

test("readTab is lenient", () => {
  expect(readTab("listen")).toBe("listen");
  expect(readTab(" Listening ")).toBe("listen");
  expect(readTab("chart")).toBe("charts");
  expect(readTab("context")).toBe("read");
  expect(readTab("sideways")).toBeNull();
  expect(readTab(3)).toBeNull();
});

test("inherited object names are not tabs", () => {
  expect(readTab("constructor")).toBeNull();
  expect(readTab("__proto__")).toBeNull();
  expect(readTab("toString")).toBeNull();
  const routed = routeGroups([g(["show_unit"], readTab("toString"))]);
  expect(routed.listen).toHaveLength(1);
});

test.each([
  ["show_unit", "listen"], ["performance_unit", "listen"], ["album_unit", "listen"], ["song_overview", "listen"],
  ["show_selection", "listen"], ["listening_hero", "listen"], ["version_strip", "listen"], ["media_link", "listen"],
  ["data_chart", "charts"], ["grid", "charts"],
  ["editorial", "read"], ["pull_quote", "read"], ["person_roster", "read"], ["era_unit", "read"], ["gap_state", "read"],
  ["something_new", "read"]
])("fallback for %s is %s", (type, tab) => {
  expect(fallbackTab({ type } as never)).toBe(tab);
});

test("entity cards go by entity type", () => {
  expect(fallbackTab({ type: "entity_card", entity_type: "show" } as never)).toBe("listen");
  expect(fallbackTab({ type: "entity_card", entity_type: "performance" } as never)).toBe("listen");
  expect(fallbackTab({ type: "entity_card", entity_type: "song" } as never)).toBe("read");
  expect(fallbackTab(undefined)).toBe("read");
});

test("a group goes whole by its own tab, else by its first block, keeping order", () => {
  const routed = routeGroups([g(["editorial", "show_unit"]), g(["song_overview"], "charts"), g(["show_unit"]), g(["data_chart"])]);
  expect(routed.read).toHaveLength(1);
  expect(routed.read[0].blocks).toHaveLength(2);
  expect(routed.charts.map((x) => x.blocks[0].type)).toEqual(["song_overview", "data_chart"]);
  expect(routed.listen).toHaveLength(1);
});

test("opening tab: the model's choice, else Listen when it has groups, else Read", () => {
  const withListen = routeGroups([g(["show_unit"])]);
  expect(openingTab("charts", withListen)).toBe("charts");
  expect(openingTab(null, withListen)).toBe("listen");
  expect(openingTab(null, routeGroups([g(["editorial"])]))).toBe("read");
});

test("tabs with content count the short answer for Read", () => {
  expect([...tabsWithContent(routeGroups([]), "Yes.")]).toEqual(["read"]);
  expect(tabsWithContent(routeGroups([g(["grid"])]), null).has("charts")).toBe(true);
});
