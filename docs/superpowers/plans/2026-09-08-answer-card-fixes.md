# Answer card fixes: insight first, honest labels, visible work

Spec: the design agreed in chat on 2026-09-08 (see "Rationale" below). No separate spec file.

## Rationale

Deadbot's differentiating material is what the model writes: the note on why an
object matters, highlighted performances, sourced disagreement, and the next
question. Everything the server hydrates (tracklists, personnel, setlists,
counts) is reference inventory. The page should let insight lead and inventory
follow. Internal vocabulary (roles, group presentation names) must not leak to
the visitor as badges or labels. Every slot the model fills must have one
defined meaning and one form. The visitor must always be able to see that
Deadbot is still working.

## Global constraints

- Follow `AGENTS.md`: deterministic code is transport, structural integrity and
  form. It never chooses content, never adds copy the model did not write, and
  never routes on keywords. Renderer changes are form only.
- Keep the model-facing schema field names unchanged in this batch. Only field
  descriptions change (Task 1).
- When `deadbot/experience.py` changes, regenerate the browser contract:
  `.venv/bin/python scripts/export_openapi.py` then `npm run gen:types --prefix web`,
  and commit `web/openapi.json` and `web/src/generated/api.ts`. CI fails on drift.
- Python tests: run the targeted files named in each task with `.venv/bin/python -m pytest`.
  Frontend: `npm run build --prefix web` must pass (it runs `tsc`). There is no browser
  test runner; visual fixtures at `web/src/visual-fixtures.ts` (`?fixture=<name>` in Vite dev)
  are the review surface.
- Do not push to GitHub. Commit locally only.
- Dark palette and existing spacing tokens in `web/src/styles.css` are the design system.
  Reuse them; do not introduce new colors.
- User-facing copy: no em-dashes; plain words.

## Task 1: Define editorial slots and announce page composition (backend)

Files: `deadbot/experience.py`, `deadbot/api.py`, `deadbot/progress.py`,
`tests/test_progress.py`, the API streaming test (find it with
`grep -ln "experience/stream" tests/*.py`), `web/openapi.json`,
`web/src/generated/api.ts`.

1. In `deadbot/experience.py`, class `EditorialItem`, give every field a
   `Field(description=...)` written as what the visitor sees. Use these texts verbatim:
   - `marker`: "A short label that classifies or indexes this item and renders as small type above the subject: a year, a date, a set position, or a category such as 'The skeptical view'. Never the subject itself."
   - `title`: "The specific subject of this item, rendered as its heading: a song, show, person, place, fact, or claim. Put measurements and assessments in value or detail."
   - `value`: "The concise measurement or assessment for the subject, such as '330 performances, 1972–1995' or 'Track six'. A short value renders as display type; a sentence renders as text."
   - `detail`: "One or two sentences of context or evidence for this item."
   - `follow_up`: "A question in the visitor's voice, rendered as an Ask chip that starts a new turn. Only the composer writes these."
   - `link`: "An outbound link for this item; kept only when its URL appeared in a tool result this turn."
   Keep the existing comment explaining why fields are optional. Keep defaults unchanged.
2. In `EditorialBlock`, give `presentation` this description verbatim:
   "narrative for prose; fact_grid for a compact set judged on shared terms, including attributed viewpoints; timeline for a sequence."
3. Regenerate the OpenAPI file and TypeScript types (see Global constraints). Confirm
   `git diff --stat` shows only description changes in the generated files.
4. In `deadbot/progress.py`, `describe_tool_call`, change the finish tool's status text
   from "Composing the answer" to "Assembling the page". Update `tests/test_progress.py`.
5. In `deadbot/api.py`, `_stream_events`: after `answer_accumulator.feed(...)`, when
   `answer_accumulator.complete` is true for the first time in this request, yield one
   status event `{"type": "status", "text": "Composing the page"}` before continuing.
   Emit it once only. It must arrive after the last `answer` event for the chat answer
   and before the `response` event.
6. Add a test in the API streaming test file: drive the stream with a fake agent whose
   `stream` yields `messages` chunks that complete a `chat_answer` string, and assert the
   event sequence contains the final `answer` event, then exactly one
   `{"type":"status","text":"Composing the page"}`, then `response`. Follow the existing
   test doubles in that file.
7. Run: `.venv/bin/python -m pytest tests/test_progress.py tests/test_answer_stream.py tests/test_experience.py tests/test_finish.py` plus the API streaming test file.
8. Commit: "Define editorial slots for the composer and announce page composition".

## Task 2: Remove leaked vocabulary and fix fact grid typography (frontend)

Files: `web/src/App.tsx`, `web/src/styles.css`, `web/src/visual-fixtures.ts`.

1. Remove `RoleChip`, `roleLabels`, and `silentRoles` from `App.tsx`, and every
   `<RoleChip role={...} />` usage (show_unit, album_unit, performance_unit, era_unit,
   song_overview). Keep the `role-${role}` class on each unit element so
   `.role-anchor` emphasis still works. Remove the `.role-chip` rules from `styles.css`;
   keep `.show-unit.role-anchor, .performance-unit.role-anchor, .album-unit.role-anchor`.
2. Remove `groupLabels` and the group-heading `<Eyebrow label={groupLabels[...]} ...>` line.
   Remove `organizationLabels` and the show_explorer `<Eyebrow ...>` line. A group header
   renders only its title and lead.
3. Restyle `.current-performance` as plain text: remove border, border-radius, padding,
   text-transform, letter-spacing and the small font size. Use
   `font-family: Georgia, "Times New Roman", serif; font-size: 1.15rem; font-weight: 700; color: #f1efdf; line-height: 1.3;`.
   Keep the element and its `aria-label`. Keep `.performance-unit .current-performance { text-align: center; }`.
4. Fact grid renderer (`presentation === "fact_grid"`): add a `display` class to the value
   when it is short. Rule: `item.value.trim().length <= 20`. Render the value as
   `<dd className={isShort ? "fact-value display" : "fact-value"}>` in both the marker and
   no-marker cases. Keep `fact-subject`, `fact-detail`, `fact-link`, `fact-ask` as they are.
5. Fact grid CSS: replace the current `.fact-grid-block dd`, `.fact-value`, `.fact-detail`
   rules with:
   - `.fact-grid-block dd { margin: 0.3rem 0 0; color: #f1efdf; }`
   - `.fact-grid-block .fact-subject { font-family: Georgia, "Times New Roman", serif; font-size: 1.1rem; font-weight: 700; line-height: 1.3; }`
   - `.fact-grid-block .fact-value { color: #bdc9bb; font-size: 0.95rem; font-weight: 400; line-height: 1.45; }`
   - `.fact-grid-block .fact-value.display { color: #f1efdf; font-family: Georgia, "Times New Roman", serif; font-size: 1.5rem; font-weight: 700; line-height: 1.1; }`
   - `.fact-grid-block .fact-detail { color: #bdc9bb; font-size: 0.92rem; font-weight: 400; line-height: 1.45; }`
   The `dt` rule stays as the small uppercase label.
6. Add a visual fixture named `views` to `web/src/visual-fixtures.ts` and to
   `visualFixtureNames`. It has two groups:
   - A `comparison` group titled "What listeners agree and argue about" with one
     `fact_grid` block of three items: markers "The skeptical view", "The sympathetic view",
     "The lasting consensus"; titles are one-sentence claims about the 1995-07-09 Soldier
     Field show; each has a `detail` sentence; the first has a `link`
     `{ url: "https://archive.org/details/gd1995-07-09.sbd.miller.97483.flac16", label: "Listener reviews" }`.
   - A `collection` group titled "The album songs in the live repertoire" with one
     `fact_grid` block of four items with no marker: titles "Mississippi Half-Step Uptown Toodeloo",
     "Row Jimmy", "Stella Blue", "Let Me Sing Your Blues Away"; values
     "237 performances", "277 performances", "330", "6 performances, all in 1973"; each with a
     `detail` sentence. This shows both display and text values side by side.
   Follow the shapes already used by the `fact` fixture. Every url in a fixture must also
   appear in the fixture's `sources` if the existing fixtures do that.
7. Run `npm run build --prefix web`. Commit: "Remove leaked role and group labels and fix fact grid hierarchy".

## Task 3: Album unit, insight first (frontend)

Files: `web/src/App.tsx`, `web/src/styles.css`, `web/src/visual-fixtures.ts`.

1. Reorder `AlbumUnit` so the model's material leads: header, `note`, listen actions,
   then a "Listen for" row of highlighted tracks (reuse the `unit-highlights` markup used
   in `ShowUnit`, with `ListeningLabel` per highlighted track), then the album body,
   then sources, then follow-up.
2. Album body: `<div className="album-body">` containing the tracklist section (left) and
   the personnel section (right). CSS: set `container-type: inline-size` on `.album-unit`;
   `.album-body { display: grid; gap: var(--space-content); margin-top: var(--space-part); }`
   and `@container (min-width: 40rem) { .album-body { grid-template-columns: minmax(0, 1fr) minmax(0, 1fr); } }`.
3. Tracklist stays a numbered `<ol className="album-tracks">` but compact: font-size 0.92rem,
   `li` padding 0.1rem 0 0.1rem 0.2rem. Highlighted tracks keep their bold style and star.
4. Personnel renders inside `<details className="album-credits unit-setlist">` with
   `<summary>Personnel and credits</summary>`, collapsed by default. Group the `personnel`
   array by `person_id`, preserving first-seen order. Each `<li>`: `<strong>{name}</strong>`
   then `<span>` with the person's distinct instruments joined by ", ", followed by
   " · " and the capitalized role for any role other than "performer" (for example "Guest").
   Empty instrument strings are skipped. Write this grouping as a small pure function
   `groupPersonnel(personnel: AlbumUnitBlock["personnel"])` in `App.tsx`.
5. Add a visual fixture named `album` (and to `visualFixtureNames`): one `collection`
   group titled "The record" with one `album_unit`: Workingman's Dead, release_id
   "workingmans-dead", release_date "1970-06-14", release_type "studio", artist_name
   "Grateful Dead", role "anchor", note "Its eight songs collectively became a second
   repertoire engine for the band: concise, character-driven material that could anchor a
   set without limiting the surrounding improvisation.", eight tracks in album order
   (Uncle John's Band, High Time, Dire Wolf, New Speedway Boogie, Cumberland Blues,
   Black Peter, Easy Wind, Casey Jones) with Cumberland Blues and Casey Jones highlighted,
   a `listen` action labeled "Listen to Workingman's Dead" with url
   "https://open.spotify.com/album/0Dx3ntxFk1ZzIWFp2mL6oN", personnel rows that repeat
   people across instruments (Bill Kreutzmann: Drums (Drum Set), Percussion; Bob Weir:
   Guitar, Lead Vocals; David Nelson: Acoustic Guitar with role "guest"; Jerry Garcia:
   Banjo, Guitar, Lead Vocals, Pedal Steel Guitar; Mickey Hart: Drums (Drum Set),
   Percussion; Phil Lesh: Bass; Ron "Pigpen" McKernan: Harmonica, Keyboard), one source,
   and follow_up "Why did the band turn toward acoustic material in 1970?".
6. Run `npm run build --prefix web`. Commit: "Let the album unit lead with insight".

## Task 4: Show the work while the page is composed (frontend)

Files: `web/src/App.tsx`, `web/src/styles.css`.

1. Content pane: while `loading` is true, render a working panel instead of the previous
   response or the empty state:
   ```
   <div className="content-working" aria-live="polite">
     <p className="eyebrow">Working</p>
     <h1>{pendingQuestion}</h1>
     <ol className="progress-lines"> last four progress lines, newest marked current with "…" </ol>
   </div>
   ```
   When `progress` is empty, the list shows one line "Looking through the library".
   Reuse `.progress-lines` styles; add `.content-working { max-width: 780px; padding-top: 2rem; }`
   and `.content-working h1 { font-size: clamp(1.5rem, 2.4vw, 2.1rem); color: #c3cec3; font-weight: 400; }`.
2. Chat pane: track where the answer began. Add state `answerProgressStart: number | null`.
   In the `onAnswer` callback passed to `askStreaming`, when `streamingAnswer` is still null,
   set `answerProgressStart` to the current `progress.length` (use a ref or functional
   update so it reads the latest value). Reset it to null in the `finally` block.
   Compute `postAnswerStatus` = the last element of `progress.slice(answerProgressStart)`
   when `answerProgressStart` is not null and that slice is non-empty.
   In the pending assistant message, when `streamingAnswer` is set: render the answer;
   if `postAnswerStatus` exists render `<p className="post-answer-status">{postAnswerStatus}…</p>`
   instead of the blinking cursor; otherwise keep the cursor.
   CSS: `.post-answer-status { margin: 0.5rem 0 0; color: #7f9582; font-size: 0.86rem; font-style: normal; }`
   with the same `▸ ` marker treatment as `.progress-lines li.current::before`.
3. `npm run build --prefix web`. Commit: "Show that Deadbot is still working after the chat answer".

## Task 5: Diagnose the missing follow-up and record the direction (backend, report only)

Files: `docs/UX-NEXT-STEPS.md`. No product code changes.

1. Using the local store (`.venv/bin/python -c` with `deadbot.storage.create_canonical_store`
   and `deadbot.tools.build_tools`, or the `deadbot` CLI if it exposes tools), call
   `search_entities("Wake of the Flood")` and `get_album` for the resolved release id.
   Report in the task report: does the release payload carry a `pathways` object, is it
   `cataloged`, and what does it contain? Do not change product code.
2. Append a section "## Batch: answer card fixes (September 8, 2026)" to
   `docs/UX-NEXT-STEPS.md` that records: role badges and group presentation labels are no
   longer rendered; editorial item slots are described by what the visitor sees; fact grid
   gives display type only to short values; album unit leads with the note, listen actions
   and highlights, with personnel grouped and collapsed; the page shows a working panel
   and a "Composing the page" status while the plan is generated. Then record the agreed
   next direction under "## Next: knob audit and emphasis": every field in `FinishPlan`
   must change what the visitor sees or be removed; roles become an emphasis axis
   (lead, supporting, mention); group presentations gain distinct layouts; progressive
   page streaming; fixture-first design for four question shapes. Keep it under 40 lines.
3. Commit: "Record the answer card batch and the knob audit direction".
