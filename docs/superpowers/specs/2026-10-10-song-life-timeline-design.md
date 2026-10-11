# Life of a song: the song card's timeline as navigation

Status: approved design, 2026-10-10. Mockup:
https://claude.ai/artifact/9KKz4RjCcf9yHZL3z1Tfky (real Terrapin Station data;
stop reasons written to stand in for the model).

## Revisions (2026-10-11, the owner's decisions; these supersede the text below)

- **No code-chosen pick.** The year panel features only the model's stops for
  that year (every one of them). The "fallback pick" described below is gone;
  every performance stays playable in See all.
- **History is the timeline.** The `history` facet and History tab are
  retired; an older plan's `history` reads as `by_year`.
- **Standouts are grouped, not ranked.** Kinds: firsts and lasts, longest,
  picks (of the performance), show picks, releases, guests, played inside
  another song, unusual placements, rare neighbors. Each kind is in date order;
  a long kind keeps a sample spread across the song's years and counts the
  rest. Each year's longest moved into `years`. `get_song` carries two of each
  kind and the first and last venues; `get_song_life` six of each.
- **Mobile.** Drag sideways across the chart to choose a year (a vertical
  swipe scrolls), a tap on a Length dot opens that year's list, no tooltips on
  touch, 44px controls, list rows stack on narrow screens.
- The year lookup is cached for an hour, not a day.

## Why

A song card already draws plays per year and, under a History tab, a first,
last and one-per-year listening list. Visitors love the listening list, but it
is hidden, and code picks it by calendar (the first performance of each year,
thinned to 12 years), so the years in the list do not match the chart and
"interesting" is an accident. The chart and the list are one thing: the song's
life on stage. This design merges them into one explorable timeline where the
model chooses the stops that matter and says why, and every year is a doorway
to play, see the facts, or ask.

This is the pilot for explorable answers in general. Its three actions map to
the approved colors: play (gold, hears), see all (rose, reads), ask (blue,
asks). Play and see-all are facts, so code serves them without a model call;
ask is judgment, so it starts a new turn with the clicked context attached.

## What the visitor sees

On a song card whose `visible_facets` include `by_year`:

- **One chart, two views.** "Times played" (bars per year, as today) and
  "Length" (one dot per performance by minutes, with each year's typical
  length as a short line). The model may name which view opens first.
- **Stops.** Gold numbered pins on the chart for the model's chosen
  performances, each with a short label and a one-line reason. Below the chart,
  the stops as a numbered list with "Play the path", which queues them in order
  in the existing player.
- **A year panel.** Hovering a year shows a tooltip (count, that year's pick).
  Clicking or pressing Enter on a year opens a panel under the chart with:
  - the year's facts: count, typical length, what it usually led into;
  - the year's pick with a gold Play: the model's stop for that year if there
    is one, else code's fallback (a picked version, then a released version,
    then the first of the year with a tape);
  - "See all N from YEAR" (rose): every performance that year, each playable,
    with set, what it came out of and went into, length, and tags (stop, pick,
    released, guest);
  - an Ask chip (blue): the model's question for that year if it wrote one,
    else "Tell me about SONG in YEAR". Asking sends the question with the song,
    year and pick attached as focus.
  The model may name the year that opens first (for example the year the
  visitor asked about). Previous and next year controls and arrow keys move
  through years. Years with no performances are drawn as empty slots and are
  not clickable.
- **Length dots.** Each dot is one performance; clicking it opens its year and
  plays it.
- **History tab.** Not shown when the timeline is on the card (its content now
  lives on the chart). Cards without `by_year` keep today's History tab.
  On record and Credits tabs are unchanged.

## Who supplies what

Following AGENTS.md: code guards facts and transport; the model owns judgment.

The model decides, all optional:

- which performances are stops, in what order, each with a `label` (a few
  words) and a `why` (one line);
- `open_year`: the year whose panel opens first;
- `chart_view`: `count` or `length`, the view that opens first;
- `year_questions`: a follow-up question for any years it chooses.

A card with none of these is still a complete chart: no pins, the earliest year
with a pick opens, the count view shows.

Code supplies every fact: counts, lengths, set neighbors and segues, tapes,
releases, selection signals, guest notes, and the fallback pick for years
without a stop. A stop ID that does not resolve renders the model's label and
reason as text without a Play, never dropped.

## Pieces

### 1. Song-life data (`deadbot/song_life.py`, new)

Pure functions over the store, using only `rows_in`, `one` and
`filtered_rows`, which the CSV, SQLite and Postgres stores implement alike.
Selection signals load only from the SQLite and Postgres stores (production
uses SQLite); on the CSV store a performance simply carries no picks.

- `life_performances(store, song_id)`: every performance of the song, dated,
  in order, each with performance and show IDs, date, venue, city, set label,
  position, encore, the previous and next songs in the same set with whether
  each segued, length seconds and its source, the tape track (reusing
  `sequences._archive_tracks`), the official releases carrying it, the
  selection signals naming it or its show, and guest notes.
- **Length rule.** Official release track seconds when present, otherwise the
  tape track's seconds; `length_source` is `release` or `tape`. A length under
  60 seconds is treated as unknown and logged (a partial tape track, such as
  Terrapin 1977-02-27 at 14 seconds, is not the performance's length).
- `year_summaries(performances)`: per year from first to last, count, median
  length, longest length with its performance ID, and the fallback pick.
- `standouts(performances)`: facts that stand out, each with a performance ID
  and a plain fact line. The model judges which make good stops; this list
  makes no quality claims.
  - first, last, longest;
  - longest of each year;
  - picked (selection signals, attributed) and released (release titles);
  - placement: opened a show, opened a set, played in a set other than the
    song's usual one, encore, closed a set, played inside another song (the
    same song immediately before and after it), next to a song it met two or
    fewer times;
  - guests named on the performance.
  Each standout is listed once with all its facts joined, ordered by date, and
  the list is capped with a logged note when cut.
- `tool_payload(store, song)`: the model-facing digest (below).
- `card_data(store, song_id)`: what the card carries: year summaries with the
  fallback pick as a playable item, and one length point per performance
  (performance ID, date, venue, seconds).
- `year_detail(store, song_id, year)`: every performance that year with the
  full facts above, for See all.

### 2. Model tool: `get_song_life`

Registered beside `get_song`. Docstring, in the persona's affirmative style:
the song's life on stage year by year, with the performances that stand out
and why, for building a song_overview timeline or answering how a song changed.
Payload: song identity, `years` (year, count, typical and longest minutes),
`standouts` (performance ID, date, venue, fact line), and a one-line note that
a song_overview's representatives become the timeline's stops, plus
`patterns`: rare placements shared by more than five performances, said once
("opened the show 20 times, 1968–1970") instead of listed. Size: under 9,000
characters, measured in tests (Terrapin 7,400; Dark Star 8,500; Sugar Magnolia,
606 performances, 7,700). Standouts stop at 30; within a tier, versions with
more facts rank first, so the list spans the song's whole life.

### 3. Plan and page schema

`SongOverviewRef` (finish.py):

- `representatives: list[{performance_id, label?, why?}]` replaces
  `representative_performance_ids` in the schema the model sees, described as
  "your stops through the song's life, in listening order; with by_year they
  mark the timeline and form a listening path." A plan that sends the old key
  is read leniently and converted.
- `open_year: int | None`, `chart_view: "count" | "length" | None`,
  `year_questions: list[{year, question}]`.
- The `history` facet description notes that with `by_year` its content lives
  on the timeline.

`SongOverviewBlock` (experience.py):

- `representative_performances[*]` gain `label` and `why`.
- New: `open_year`, `chart_view`, `year_questions`, `year_summaries`,
  `length_points` (the last two filled only when `by_year` is visible).
- `year_counts` stays until the old chart path is removed.

### 4. Year lookup

`GET /api/songs/{song_id}/years/{year}` returns `SongYearDetail` from
`year_detail`. No model call. Rate limited with the grid branch's lookup
limiter. `Cache-Control: public, max-age=86400`, since library facts do not
change between deploys. 404 for an unknown song; an empty list for a year with
no performances.

### 5. Timeline component (`web/src/SongTimeline.tsx`, new)

- Hand-drawn SVG (bands, bars, dots, pins), sized by a ResizeObserver; the
  approved tokens; 2px corners; Fraunces for the year numeral.
- Every year band and pin is focusable with an accessible name; Enter or Space
  opens or plays; left and right arrows move between years. A visually hidden
  table remains the full-data alternative, as DataChart provides today.
- Tooltips on hover and focus; the year panel is inline under the chart (not a
  floating popover), so it works by touch and keyboard.
- Plays through `usePlayer`; "Play the path" passes the stops as the queue.
- See all fetches the year lookup once per year and keeps it for the session.
- Ask calls `onAsk(question, focus)`, where focus carries the song ID, the year,
  the pick's performance ID, a label ("Terrapin Station in 1979") and the
  year's fact line.
- `SongOverviewUnit` renders `SongTimeline` in place of the DataChart and
  History panel when `by_year` is visible.

### 6. Ask with focus

Reuse the grid branch's `AskFocus` and `askRequestBody`: widen
`AskFocus.block_type` to include `song_overview`. The server already resolves
focus IDs (songs, performances) into the turn's grounded IDs and writes the
model a note of what was clicked.

## Phases (to stay clear of the grid branch)

The grid branch (`claude/whereyouworkmatters-research-8634ea`) is active and
edits experience.py, finish.py, tools.py, api.py, App.tsx, components.tsx,
player.tsx, styles.css, openapi.json, generated/api.ts and types.ts. The
research-notebook branch edits tools.py, composition.py and graph.py.

**Phase 1, now, new files only:**

- `deadbot/song_life.py` and `tests/test_song_life.py` (data module, standouts,
  tool payload function, card data, year detail).
- `scripts/export_song_timeline_fixture.py` writing
  `web/src/fixtures/song-timeline-terrapin.json` from `card_data` plus
  hand-written stand-in stops clearly marked as such.
- `web/src/SongTimeline.tsx`, `web/src/SongTimeline.css`,
  `web/src/SongTimeline.test.tsx`, `web/src/song-year.ts` (lookup client), with
  local TypeScript types that phase 2 replaces with generated ones.
- A dev-only preview page (`web/song-timeline-preview.html` and
  `web/src/song-timeline-preview.tsx`) served by the Vite dev server, so the
  component can be seen without registering a visual fixture (the grid branch
  edits visual-fixtures.ts). Not part of the production build.

**Phase 2, after the grid branch merges, from fresh main:**

- Register `get_song_life` in tools.py; schema fields in finish.py and
  experience.py; fill them in composition.py.
- Year lookup endpoint in api.py.
- Swap `SongTimeline` into `SongOverviewUnit`; widen `AskFocus`.
- Regenerate openapi.json and the generated types; replace local types.
- Register the visual fixture; retire the preview page.
- Whichever of the grid and notebook branches lands later rebases; phase 2's
  shared-file edits are small additions.

## Testing and evaluation

- Unit tests on the real canonical data: Terrapin has 302 performances and 23
  in 1979; its longest is 1993-09-29 (1,514 seconds); 1981-12-31 is inside
  Playing in the Band; 1989-12-06 carries the Clemons guest note; 1977-02-27's
  14-second tape length is unknown; the payload stays under the size target; a
  song played once and a song with gap years both produce valid summaries.
- Component tests: renders both views; keyboard opens years and moves between
  them; zero-play years are inert; performances without a length are absent
  from the Length view but counted; See all loads once per year; Play the path
  queues stops in order; an unresolved stop renders as text.
- Phase 2 live runs on real questions across a family of songs: "How often did
  they play Terrapin", "How did Dark Star change over the years", "Best Sugar
  Magnolias", a rarity, and a cover. Check that stops are chosen with reasons
  and are not just first-of-year, that `open_year` follows the question, and
  that the added tool call's latency is acceptable. Score pages with
  `scripts/page_eval.py`.

## Out of scope for the pilot

- The "What came next" view (mocked; added once the first two views prove out).
- The click-for-actions panel on other charts, ranked lists and inline links.
- Changes to the model's persona beyond the tool docstring and field
  descriptions.
