# Progressive page streaming

Design for the batch after PR #29. The palette cut showed that finish-call
latency is dominated by the model writing the plan (1500 to 1900 output tokens,
17 to 20 seconds), not by schema size. The page cannot appear before the plan is
written, but it can appear while the plan is written. This spec makes the main
body build in reading order as the model composes it.

## Problem

Today the browser receives the chat answer token by token, then nothing until
one `response` event carries the whole page. Between those two moments the
visitor sees a working panel for 15 to 20 seconds. Meanwhile the server has
everything it needs to render the first group: research is finished before
`finish_response` begins, so every referenced ID and URL is already grounded,
and the plan arrives in reading order because the schema lists `chat_answer`,
`title`, `lead`, then `groups`, and each group lists its scalar fields before
`items`.

## Goal

The page title appears as soon as the model has written it. Each unit or
editorial block appears, fully hydrated, within a second of the model closing
its JSON. The final response still arrives whole and remains the record the
cache stores. Measured target: time to first rendered block under 5 seconds
after the chat answer completes, on the three traced questions.

Non-goals: changing what the model writes, changing the plan schema, streaming
tool results, conversation history across turns.

## How it works

```text
model tokens ──► AnswerAccumulator ──► answer events (unchanged)
      │
      └──────► PlanStreamer ──► page_head / group_open / block / group_close
                                  │
                                  └── resolve_items([item]) hydrates each block
                                      with this turn's grounded payloads
                          ...
finish call complete ──► ToolNode ──► build_experience_response ──► response
```

### Server: `deadbot/plan_stream.py`

A `PlanStreamer` sits beside `AnswerAccumulator` in `_stream_events`. It is fed
the same `finish_response` argument fragments and scans them with a small
state machine instead of re-parsing the whole buffer:

- Tracks string state and escapes, a container stack, and the key path of the
  current position (`title`, `groups[2].items[0]`, and so on).
- When a top-level string value for `title` or `lead` closes, records it.
- When `groups[i].items` opens, emits `group_open` with the group's scalar
  fields that have already closed (`title`, `lead`, `presentation`,
  `criteria`). With the current schema order these are always complete; the
  design tolerates a model that writes them later.
- When an element of `groups[i].items` closes, slices its exact text,
  `json.loads` it, validates it as a `BodyItem`, resolves it through
  `finish.resolve_items([item], grounded, payloads, store)`, and emits one
  `block` event per resolved block (an ungrounded item emits nothing, as it
  does today). Judgments are truncated to the group's criteria count when the
  group has closed its criteria before the item; otherwise the final
  `response` corrects them.
- When `groups[i]` closes, emits `group_close` with the group's final scalar
  fields, so a heading written after its items still lands.
- `page_head` is emitted once, when `groups` opens or, for a plan with no
  groups, when the call completes. It carries `title` and `lead`.

A second `finish_response` call in the same turn (the first failed
validation and the model retried) resets the streamer and emits `page_reset`
so the browser discards the draft. Any parse failure disables progressive
events for the rest of the turn without breaking the stream; the final
`response` is unaffected.

`grounded_context(payloads)` is computed once when the first finish fragment
arrives, from the tool payloads of the latest `values` step the stream has seen
(`composition._tool_payloads` over the current turn), which by then holds every
tool result of the turn. Resolution runs inside the request's existing `query_cache_scope`,
so the final `_respond` re-hydration hits warm caches rather than repeating
database reads. Reusing the streamed blocks to assemble the final response is
a later optimization, not part of this batch; the final response is built the
same way it is today so it stays authoritative.

### Event contract additions (NDJSON, `/api/experience/stream`)

| Event | Payload | When |
| --- | --- | --- |
| `page_head` | `{title, lead}` | `groups` opens |
| `group_open` | `{index, title, lead, presentation, criteria}` | a group's `items` opens |
| `block` | `{group_index, block}` (a validated `ExperienceBlock`) | an item closes and resolves |
| `group_close` | `{index, title, lead, presentation, criteria}` | a group closes |
| `page_reset` | `{}` | a retried finish call begins |
| `response` | unchanged | the turn completes |

Existing `status`, `answer`, and `error` events are unchanged. Cached answers
skip progressive events and send `response` directly, as today. The plain
`/api/experience` endpoint is unchanged.

### Browser: `web/src/App.tsx`

A `draft` state holds `{title, lead, groups: [{index, title, lead,
presentation, criteria, blocks: ExperienceBlock[]}]}` built from the events.
While a question is pending:

- Before `page_head`: the working panel, as today.
- After `page_head`: the content pane renders the draft with the same
  components the final page uses (`Block`, group sections, emphasis and
  relationship layouts), plus one quiet line at the bottom, "Composing the
  page…", until `response` arrives. New blocks appear in place with no
  animation beyond the existing reduced-motion-safe transitions.
- `page_reset` clears the draft and returns to the working panel.
- `response` replaces the draft. Because the final response has the same
  blocks in the same order, the swap does not move content; the sources
  footer and any corrected judgments appear at that moment.

The chat pane behavior is unchanged: the streamed answer, then the newest
status beneath it.

## Failure handling

- Malformed or truncated plan JSON: progressive events stop; the final path
  handles validation and the gap state exactly as today.
- An item that fails `BodyItem` validation mid-stream: skipped; the model's
  final call will fail validation as a whole and retry, producing
  `page_reset`.
- Hydration error for one item: logged, that block is skipped, the stream
  continues.
- Client receives `block` for an unknown `group_index`: creates the group
  provisionally with empty metadata; `group_close` fills it.

## Testing

- `tests/test_plan_stream.py`: unit tests for the scanner. Cases: title and
  lead closure; escaped quotes and braces inside strings; nested objects in an
  item (a unit with `judgments` and `supporting_sources`); an item split across
  fragments at every byte boundary (drive the same plan one character at a
  time and assert identical events); two groups; a plan with no groups; a
  retried call producing `page_reset`; malformed JSON disabling events without
  raising.
- `tests/test_experience.py`: the streaming endpoint emits, in order, the
  last `answer`, `page_head`, `group_open`, one or more `block`, `group_close`,
  `response`; blocks match the final response's blocks by type and id; a
  cached answer emits no progressive events; an agent without `stream` emits
  only `response`.
- Frontend: `npm run build`. Add a development-only fixture stream
  (`?stream=legacy`) that replays a recorded event sequence with delays so the
  progressive rendering can be reviewed without a model call, at 1440px and
  375px.

## Measurement

Extend the trace script from the latency work to record, per question: chat
answer complete, first `block`, last `block`, `response`. Report time to first
block and time to full page for Branford, Franklin's Tower best versions, and
American Beauty live legacy, before and after, in `docs/UX-NEXT-STEPS.md`.

## Sequence

1. `PlanStreamer` scanner with unit tests (no API change).
2. Server events in `_stream_events`, with per-item resolution and reset.
3. Browser draft state and rendering, plus the replay fixture.
4. Measurement and docs.
