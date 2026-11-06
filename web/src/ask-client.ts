// Talking to the Deadbot API: the streaming ask, the plain ask it falls back
// to, and the dev fixture replay. No React in here; callers pass handlers and
// an optional AbortSignal so a request can be dropped when the visitor moves on.
import type { ExperienceResponse } from "./types";
import type { PageEvent, StreamEvent } from "./stream-events";

// A conversation's id on the server; a fresh start gets a new one.
export function createThreadId(): string {
  return `web-${crypto.randomUUID()}`;
}

export const ASK_ERROR = "Deadbot could not answer just now. Try again, or rephrase the question.";

export type StreamHandlers = {
  onStatus: (status: string) => void;
  onAnswer: (text: string) => void;
  onPage: (event: PageEvent) => void;
  onResponse: (response: ExperienceResponse) => void;
};

// Shared between the network reader and the fixture replay: turn one parsed
// event into the matching handler call. Error throws; everything else is
// handed to the caller's handlers, including the response, which the network
// reader captures and the replay applies immediately.
const PAGE_EVENT_TYPES = new Set(["page_head", "page_tab", "group_open", "group_close", "block", "page_reset", "groups_reset"]);

export function dispatchStreamEvent(event: StreamEvent, handlers: StreamHandlers): void {
  if (event.type === "status") handlers.onStatus(event.text);
  else if (event.type === "answer") handlers.onAnswer(event.text);
  else if (event.type === "response") handlers.onResponse(event.response);
  else if (event.type === "error") throw new Error(event.detail ?? ASK_ERROR);
  else if (PAGE_EVENT_TYPES.has(event.type)) handlers.onPage(event);
}

export function isAbort(error: unknown): boolean {
  return error instanceof DOMException && error.name === "AbortError";
}

// The streaming endpoint sends one JSON object per line: statuses while the
// agent works, page events as the page is composed, then the response. A
// null return means the stream was not available and the caller should
// fall back to the plain request. A stream that started and then ended
// without its response is a failure, not a reason to run the question
// again: a second run writes a different answer, and the visitor would
// watch the first one be replaced without knowing why.
export async function askStreaming(
  body: string,
  handlers: Omit<StreamHandlers, "onResponse">,
  signal?: AbortSignal
): Promise<ExperienceResponse | null> {
  const result = await fetch("/api/experience/stream", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body,
    signal
  });
  if (result.status === 404 || result.status === 405) return null;
  if (!result.ok) {
    const detail = await result.json().catch(() => null) as { detail?: string } | null;
    throw new Error(detail?.detail ?? ASK_ERROR);
  }
  if (!result.body) return null;
  const reader = result.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  let answer: ExperienceResponse | null = null;
  let sawEvent = false;
  const consume = (line: string) => {
    if (!line.trim()) return;
    sawEvent = true;
    const event = JSON.parse(line) as StreamEvent;
    dispatchStreamEvent(event, {
      onStatus: handlers.onStatus,
      onAnswer: handlers.onAnswer,
      onPage: handlers.onPage,
      onResponse: (response) => { answer = response; }
    });
  };
  for (;;) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    let newline = buffer.indexOf("\n");
    while (newline >= 0) {
      consume(buffer.slice(0, newline));
      buffer = buffer.slice(newline + 1);
      newline = buffer.indexOf("\n");
    }
  }
  consume(buffer);
  if (answer === null && sawEvent) {
    throw new Error("The connection closed before Deadbot finished the page. Please ask again.");
  }
  return answer;
}

export async function askPlain(body: string, signal?: AbortSignal): Promise<ExperienceResponse> {
  const result = await fetch("/api/experience", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body,
    signal
  });
  if (!result.ok) {
    const detail = await result.json().catch(() => null) as { detail?: string } | null;
    throw new Error(detail?.detail ?? ASK_ERROR);
  }
  return await result.json() as ExperienceResponse;
}

function delay(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

// The dev `?stream=` fixture replays a canned event sequence through the same
// dispatch the network path uses, so progressive rendering can be reviewed
// without a model. It stops quietly once the signal aborts.
export async function replayStreamEvents(events: StreamEvent[], handlers: StreamHandlers, signal?: AbortSignal): Promise<void> {
  for (const event of events) {
    if (signal?.aborted) return;
    await delay(event.type === "block" ? 600 : event.type === "answer" ? 40 : 300);
    if (signal?.aborted) return;
    dispatchStreamEvent(event, handlers);
  }
}
