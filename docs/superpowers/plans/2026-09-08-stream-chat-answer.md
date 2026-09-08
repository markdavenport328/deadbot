# Stream the chat answer while the plan is still generating

## Context

Every Deadbot turn ends with one `finish_response` tool call whose arguments
are a JSON object: `chat_answer` (the visible conversation answer) first, then
`title`, `lead`, `mode`, `groups`, `body`. That final model call takes 19–20
seconds in production traces (about 1,500 output tokens), and today the
visitor sees only status lines until the whole object has been generated and
resolved. The API already streams newline-delimited JSON events to the browser
(`POST /api/experience/stream` in `deadbot/api.py`; consumer `askStreaming` in
`web/src/App.tsx`).

Goal: show `chat_answer` in the conversation column as it is generated, so the
visitor reads the answer while the body plan is still being written and
resolved. No second model step; no change to the response contract.

Spec authority: `docs/decisions.md` ("Do not reintroduce a second model
step"), `docs/agent-harness.md` (the finish contract), and this file.

## Global constraints

- One model owns the turn; the answer is streamed out of the `finish_response`
  arguments, never produced by another call.
- New stream event, emitted zero or more times before the `response` event:
  `{"type": "answer", "text": "<the chat_answer decoded so far, cumulative>"}`.
  Cumulative means each event carries the full text so far; the client
  replaces, never appends. Text is the decoded JSON string value (escapes
  resolved), never raw JSON.
- Existing events are unchanged: `status`, `response`, `error`. The cached
  answer path (`_cached` in `api.py`) is unchanged.
- Ollama keeps non-streaming model calls (its tool-call streaming is not
  relied on); OpenAI streams. Controlled by one setting,
  `DEADBOT_MODEL_STREAMING`, default true for the openai provider and false
  for ollama.
- Test doubles whose `stream` yields plain state dicts (see
  `StreamingFakeAgent` in `tests/test_experience.py`) keep working.
- Never assume field order: if `chat_answer` is not the first key, the answer
  simply streams later; nothing breaks.
- Write prompt or comment guidance affirmatively (repo rule: no "do not").
- Tests run with
  `PYTHONPATH=. /Users/markdavenport/Development/DeadBot/.venv/bin/python -m pytest -q`.
  Expect `tests/test_evaluations.py::test_evaluate_cli_exits_non_zero_when_a_case_fails`
  to fail (database-bound, pre-existing). Everything else must pass.
- Commit with the trailer `Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>`.
  Never push. Never use bare `git stash`.

## Library facts (verified 2026-09-08, langchain-core 1.6.0, langgraph current)

- `BaseChatModel._streaming_disabled` returns True when the call kwargs carry
  `stream=<falsy>`. `deadbot/graph.py` currently does
  `provider.create_chat_model().bind_tools(tools).bind(stream=False)`, which
  hard-disables streaming. Removing that bind lets LangGraph's
  `stream_mode="messages"` callback trigger token streaming inside the node.
- With `stream_mode=["values", "messages"]`, `graph.stream(...)` yields
  `(mode, payload)` tuples: `("values", state_dict)` and
  `("messages", (message_chunk, metadata))`. Chunks are `AIMessageChunk`;
  partial tool-call arguments arrive in `chunk.tool_call_chunks`, each a dict
  with `name` (often only on the first chunk), `args` (a string fragment of
  the JSON), `id`, and `index`. Concatenate `args` fragments per `index`.
- Verify the above against the real model as part of Task 1 (see below); the
  OpenAI Responses API is expected to stream `function_call_arguments.delta`
  events, which langchain-openai maps to `tool_call_chunks`.

## Task 1 — Backend: stream `chat_answer` out of the finish arguments

Files: `deadbot/config.py`, `deadbot/graph.py`, new `deadbot/answer_stream.py`,
`deadbot/api.py`, `docs/agent-harness.md`, tests.

1. `deadbot/config.py`: add `model_streaming: bool` to `Settings`. In
   `from_env`, read `DEADBOT_MODEL_STREAMING` with `_as_bool`; when the
   variable is absent, default to `model_provider == "openai"`. Add the
   variable to `.env.example` with a two-line comment.
2. `deadbot/graph.py` `build_agent`: bind `stream=False` only when
   `settings.model_streaming` is false. Update the comment to say why (Ollama
   tool-call streaming is not relied on; OpenAI streams so the answer can
   reach the visitor early).
3. New `deadbot/answer_stream.py`:
   - `extract_chat_answer(partial_json: str) -> tuple[str, bool]`: given the
     concatenated `finish_response` argument text so far, return the decoded
     value of the `"chat_answer"` string as far as it has been generated, and
     whether the string is complete (closing quote seen). Rules: find the key
     `"chat_answer"` followed by optional whitespace, `:`, optional
     whitespace, and an opening `"`; decode characters up to an unescaped `"`;
     resolve JSON escapes (`\"`, `\\`, `\/`, `\n`, `\t`, `\r`, `\b`, `\f`,
     `\uXXXX`, including surrogate pairs); a trailing incomplete escape (a lone
     `\` or a partial `\u12`) is held back, not emitted. Return `("", False)`
     when the key or its opening quote has not appeared yet. Pure function, no
     JSON library needed for the partial case.
   - `class AnswerAccumulator`: `feed(message_chunk) -> str | None` appends
     every `tool_call_chunks` entry whose call is the `finish_response` call
     (name `FINISH_TOOL_NAME` from `deadbot.finish`, or the same `index`/`id`
     as a chunk that carried that name) to an internal buffer, then returns
     the new cumulative answer text when it grew since the last call, else
     `None`. Property `complete: bool`. Ignore chunks for other tools and
     plain text content.
4. `deadbot/api.py` `_stream_events`: request
   `stream_mode=["values", "messages"]`. For each yielded item: if it is a
   `(mode, payload)` tuple, route `values` payloads through the existing
   status logic and `messages` payloads through an `AnswerAccumulator`,
   yielding `{"type": "answer", "text": ...}` whenever `feed` returns text;
   if it is a plain dict (an agent that ignores the mode list, or a test
   double), treat it as a `values` state as today. Keep the per-step
   `query_cache_scope(cache)` re-entry around each `next(steps, None)`.
   Emit at most one `answer` event per yielded chunk; no timers.
5. Tests:
   - `tests/test_answer_stream.py`: `extract_chat_answer` on: empty string;
     text before the key appears; key present but no opening quote yet;
     a partial value; a value with `\"` and `\\n` escapes; a `\uXXXX` escape
     and a surrogate pair (an emoji); a trailing lone backslash and a partial
     `\u00` (held back, then emitted once completed); a completed value
     followed by other fields (complete is True and later fields are
     ignored); `chat_answer` appearing as the second key. `AnswerAccumulator`
     on a sequence of `AIMessageChunk`s: first chunk names the tool with
     `args=""`, later chunks carry fragments; a chunk for a different tool
     (`get_show`) is ignored; returns `None` when nothing grew.
   - `tests/test_experience.py`: a fake agent whose `stream` yields
     `("messages", (AIMessageChunk(content="", tool_call_chunks=[...]), {}))`
     items interleaved with `("values", state)` items; assert the NDJSON
     stream contains at least two `answer` events before the `response`
     event, that their `text` values are cumulative prefixes of one another,
     and that the final `answer` text equals `response["answer"]`. Keep the
     existing `StreamingFakeAgent` (plain dict states) test passing unchanged.
   - `tests/test_config.py`: `model_streaming` defaults true for openai,
     false for ollama, and `DEADBOT_MODEL_STREAMING=false` overrides.
6. Real-model verification (report only, no committed artifact): with
   `DEADBOT_MODEL_PROVIDER=openai` and settings read from
   `/Users/markdavenport/Development/DeadBot/.env` via
   `Settings.from_env(Path(".../.env"))` (the worktree has no `.env`; that file
   holds the database URL and API key, never print its values), run
   `build_agent(settings).stream({"messages": [HumanMessage("What shows did
   Branford play on?")]}, run_config("verify", settings),
   stream_mode=["values", "messages"])` and record: whether `tool_call_chunks`
   arrive incrementally for `finish_response`, the wall-clock time from the
   start of the finish call to the first non-empty `chat_answer` text, and the
   time to the end of the turn. Put the numbers in the report. If arguments
   arrive as a single chunk rather than incrementally, say so plainly; the
   code still ships and the report names the gap.
7. `docs/agent-harness.md`: replace the paragraph that says the graph uses
   non-streaming requests with one that describes the setting and what is
   streamed.

## Task 2 — Frontend: render the streaming answer

Files: `web/src/App.tsx` (and `web/src/styles.css` if a class is needed).

1. In `askStreaming`, accept a second callback `onAnswer(text: string)` and
   call it for `{"type": "answer"}` events with `event.text`.
2. In the submit handler, add state `const [streamingAnswer, setStreamingAnswer] = useState<string | null>(null)`;
   reset it to `null` alongside `setProgress([])` at the start and in
   `finally`; pass `setStreamingAnswer` as `onAnswer`.
3. In the pending assistant message (`loading && ...`): when
   `streamingAnswer` is a non-empty string, render
   `<div>{renderInline(streamingAnswer)}<span className="cursor" aria-hidden="true" /></div>`
   in place of the progress list (the status lines have done their job once
   the answer is arriving). Otherwise render exactly what renders today.
4. `web/src/styles.css`: a `.message.pending .cursor` rule: an inline-block
   0.55em × 1em bar in the current text color with a 1s step blink animation,
   respecting `prefers-reduced-motion: reduce` (no animation).
5. Build check: `npm --prefix web ci && npm --prefix web run build` must
   succeed (this installs dependencies; the worktree has no
   `web/node_modules`). `web/dist` is git-ignored; commit only source.
6. No change to `web/openapi.json` or generated types: the NDJSON events are
   not part of the OpenAPI schema.
