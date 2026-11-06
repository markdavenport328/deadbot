import { describe, expect, test } from "vitest";
import { applyPageEvent, groupsOfResponse } from "./page-draft";
import type { ExperienceResponse } from "./types";

const block = { type: "editorial", presentation: "narrative", items: [] } as never;

describe("applyPageEvent", () => {
  test("a block before its group_open gets a provisional group", () => {
    const draft = applyPageEvent(null, { type: "block", group_index: 0, block });
    expect(draft?.groups).toHaveLength(1);
    expect(draft?.groups[0].tab).toBeNull();
  });

  test("group_open fills the heading and reads the tab leniently", () => {
    const opened = applyPageEvent(null, { type: "group_open", index: 0, title: "T", lead: null, presentation: "collection", criteria: [], tab: "Listen" } as never);
    expect(opened?.groups[0]).toMatchObject({ title: "T", tab: "listen" });
    const unknown = applyPageEvent(null, { type: "group_open", index: 0, title: "T", lead: null, presentation: "collection", criteria: [], tab: "sideways" } as never);
    expect(unknown?.groups[0].tab).toBeNull();
  });

  test("page_reset clears, groups_reset keeps the head", () => {
    const head = applyPageEvent(null, { type: "page_head", title: "A", lead: null });
    expect(applyPageEvent(head, { type: "page_reset" })).toBeNull();
    expect(applyPageEvent({ ...head!, groups: [{ title: null, lead: null, presentation: "collection", criteria: [], blocks: [], tab: null }] }, { type: "groups_reset" })?.groups).toEqual([]);
  });
});

test("groupsOfResponse carries each group's tab when present", () => {
  const response = {
    schema_version: "2", thread_id: "t", title: "x", answer: "a", conversation: [], sources: [],
    blocks: [block, block],
    groups: [
      { title: null, lead: null, presentation: "collection", criteria: [], block_indexes: [0], tab: "charts" },
      { title: null, lead: null, presentation: "collection", criteria: [], block_indexes: [1] }
    ]
  } as unknown as ExperienceResponse;
  expect(groupsOfResponse(response).map((g) => g.tab)).toEqual(["charts", null]);
});
