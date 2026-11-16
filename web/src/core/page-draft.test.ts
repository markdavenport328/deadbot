import { describe, expect, test } from "vitest";
import { applyPageEvent, groupsOfResponse } from "./page-draft";
import type { ExperienceResponse } from "../types";

const block = { type: "editorial", presentation: "narrative", items: [] } as never;

describe("applyPageEvent", () => {
  test("a block before its group_open gets a provisional group", () => {
    const draft = applyPageEvent(null, { type: "block", group_index: 0, block });
    expect(draft?.groups).toHaveLength(1);
  });

  test("group_open fills the heading; a tab it names changes nothing", () => {
    const opened = applyPageEvent(null, { type: "group_open", index: 0, title: "T", lead: null, presentation: "collection", criteria: [], tab: "Listen" } as never);
    expect(opened?.groups[0]).toEqual({ title: "T", lead: null, presentation: "collection", criteria: [], blocks: [] });
    const head = applyPageEvent(null, { type: "page_head", headline: "A", lead: null });
    expect(applyPageEvent(head, { type: "page_tab", tab: "charts" } as never)).toBe(head);
  });

  test("page_reset clears, groups_reset keeps the head", () => {
    const head = applyPageEvent(null, { type: "page_head", headline: "A", lead: null });
    expect(applyPageEvent(head, { type: "page_reset" })).toBeNull();
    expect(applyPageEvent({ ...head!, groups: [{ title: null, lead: null, presentation: "collection", criteria: [], blocks: [] }] }, { type: "groups_reset" })?.groups).toEqual([]);
  });
});

test("groupsOfResponse keeps the groups in the model's order", () => {
  const response = {
    schema_version: "3", thread_id: "t", headline: "x", lead: "a", conversation: [], sources: [],
    blocks: [block, block],
    groups: [
      { title: null, lead: null, presentation: "collection", criteria: [], block_indexes: [0], tab: "charts" },
      { title: null, lead: null, presentation: "collection", criteria: [], block_indexes: [1] }
    ]
  } as unknown as ExperienceResponse;
  expect(groupsOfResponse(response).map((g) => g.blocks.length)).toEqual([1, 1]);
  expect(groupsOfResponse(response)[0]).not.toHaveProperty("tab");
});
