# Workspace live runs, 2026-11-05

Branch `claude/workspace-tabs-contract` (db843bd, prompt section "THE WORKSPACE")
against `main` at 3e06d64, both served locally with production model settings:
OpenAI provider, reasoning effort from the owner's `.env`, SQLite store, response
cache off. Three runs per question per server. Times are seconds from request
to event, medians of three. Tool: `scripts/trace_stream.py`.

## Opening tab the model chose (branch)

| Question | Opening tab, 3 runs | Groups per tab |
|---|---|---|
| What's their history at Madison Square Garden? | charts, read, charts | 1 chart, 1–2 listen, 0–1 read |
| …then "Focus on the late '80s" | read, listen, listen | 1 chart and 1–3 listen each time |
| When was Jerry Garcia born? | read ×3 | none (chat answer only) |
| Tell me the story of Veneta '72 | listen ×3 | 2–3 listen, 1–2 read |
| How did Dark Star change over the years? | charts ×3 | 1 chart each; listen and read in 2 of 3 |
| Fox Theatre, St. Louis, 1971-12-10 (setlist) | listen, read, read | 1–2 listen, 0–1 read |
| Who wrote the lyrics to Ripple? | read ×3 | 1 read |

No branch run opened on a tab without content. Read always holds the chat
answer.

## Timing, branch vs main (median seconds)

| Question | First answer | First Listen block | First Charts block | Done |
|---|---|---|---|---|
| Madison Square Garden | 15.0 vs 12.4 | 21.5 vs 16.3 | 17.8 vs 19.0 | 29.8 vs 24.5 |
| Garcia's birthday | 3.9 vs 3.7 | – | – | 4.6 vs 4.5 |
| Veneta '72 | 10.9 vs 10.0 | 14.0 vs 12.4 | – | 25.8 vs 25.2 |
| Dark Star | 9.6 vs 8.4 | 19.8 vs 13.8 | 13.3 vs – | 21.8 vs 22.4 |
| Fox Theatre setlist | 3.0 vs 3.3 | 7.3 vs 6.2 | – | 7.6 vs 6.9 |
| Ripple | 3.2 vs 3.0 | – | – | 4.8 vs 4.4 |

Research rounds vary run to run (Madison Square Garden took 3 to 5 tool
rounds), so three runs cannot separate the two servers. Total time is within
noise; the opening tab arrives with the first answer text, so the workspace
knows where to open before any block lands. On Dark Star the branch puts the
song's timeline in Charts, so the first block it streams is the chart the page
opens on.

## Groups-first experiment (rejected)

A scratch copy declared `chat_answer` after `groups` in `FinishPlan`. Madison
Square Garden and Dark Star, three runs each, plus the follow-up three times:

- First Listen block was no faster (Dark Star 18.5 vs 19.8; Madison Square
  Garden 25.5 vs 21.5).
- In most runs the answer text still streamed before the first block, so
  field order does not decide what the model writes first.
- One Dark Star run chose Charts and then built no chart, so it would have
  opened on an empty tab.

The stream order stays answer first. Nothing from the experiment was committed.

## Other observations

- The server logged "finish_response planned a group without an items list;
  leaving it out" on several Madison Square Garden and Dark Star runs. The
  branch's group counts are in line with main's, so this does not look new,
  but it is worth a look in the page-quality eval.
- The Fox Theatre setlist opened on Read in 2 of 3 runs, with the show card
  on Listen. A setlist question arguably belongs on Listen; watch it in use
  before changing the prompt.
- Follow-ups work. The first harness version sent a malformed previous answer
  and got 422s; that was the harness, fixed in b4ce9b2, and the follow-up runs
  above use the fixed version.
- Browser check against the live branch API: Dark Star opened on Charts with
  the song's life-on-stage timeline while Listen showed "preparing".
