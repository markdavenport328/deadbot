import { describe, expect, it } from "vitest";
import { askRequestBody } from "./ask-request";

describe("askRequestBody", () => {
  const conversation = [{ role: "user" as const, text: "Hi" }];

  it("sends the question, thread and transcript, and no focus unless one was clicked", () => {
    const body = JSON.parse(askRequestBody({ question: "Q", threadId: "t", conversation }));
    expect(body).toEqual({ question: "Q", thread_id: "t", conversation });
    expect("focus" in body).toBe(false);
  });

  it("sends what the visitor clicked beside the plain question", () => {
    const focus = { label: "Dark Star · May 11, 1972", block_type: "grid" as const, block_id: "grid:abc", ids: ["gd-1972-05-11"], facts: ["44 minutes."] };
    const body = JSON.parse(askRequestBody({ question: "Tell me about it.", threadId: "t", conversation, focus }));
    expect(body.focus).toEqual(focus);
    expect(body.question).toBe("Tell me about it.");
  });

  it("sends the research notebook beside the question when there is one", () => {
    const body = JSON.parse(askRequestBody({ question: "Q", threadId: "t", conversation, notebook: "v1.body.sig" }));
    expect(body.notebook).toBe("v1.body.sig");
    expect(body.focus).toBeUndefined();
  });

  it("leaves the notebook out when there is none", () => {
    const body = JSON.parse(askRequestBody({ question: "Q", threadId: "t", conversation, notebook: null }));
    expect("notebook" in body).toBe(false);
  });
});
