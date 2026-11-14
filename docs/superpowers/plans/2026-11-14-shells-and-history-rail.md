# Workspace direction: history rail, queue rail, docked ask, room to breathe

_Plan, 2026-11-14. Covers `web/src`. Nothing here changes the server, the
model's tools or the response contract._

## Where we are headed

```
┌──────────┬──────────────────────────────────────┬──────────────┐
│ History  │  Answer pane (scrolls)               │ Queue rail   │
│ rail     │   Listen · Charts · Read tabs        │ (scrolls)    │
│          │   cards, one per row, with room      │ Now playing  │
│ New chat │                                      │ Up next      │
│ Recent   │                                      │  ≡ row  ▶ ⋯  │
│  └ f/ups │  ┌────────────────────────────────┐  │  ≡ row  ▶ ⋯  │
│ Clear    │  │ Ask … (docked to pane bottom)  │  │ Clear · Undo │
├──────────┴──┴────────────────────────────────┴──┴──────────────┤
│ Player, full width: cover · title · ◀ ▶ ▶▶ · scrubber · queue    │
└──────────────────────────────────────────────────────────────────┘
```

Phones: the history rail is a drawer from the left, and the queue is a
bottom sheet opened from the player. The ask box docks just above the player.

## What we take from the reference projects

**WAMU Listen** (`~/Development/WAMU Conversational Player`):

- **The app frame.** A fixed header, two panes that scroll on their own, and a
  full-width player across the bottom. The chrome never scrolls away
  (`.app` grid in `styles.css`).
- **The queue as a first-class rail** (`components/QueuePanel.tsx`):
  - "Now playing", then "Up next", each section with its total time
  - drag to reorder by a grip, using pointer events so touch works too
  - a ⋯ menu on each row: Play now, Move up, Move down, About, and Remove.
    Arrow keys move through it, and Escape closes it and returns focus to ⋯.
  - a live announcement for each move or removal
  - Clear, which turns into "Cleared. Undo" for ten seconds
- **Card actions** (`components/SegmentCard.tsx`). Two small round buttons sit
  at the card's edge: Add to queue (+, then ✓ once it's in) and Play (an
  equalizer while it plays). The card's text leads, and play stays one small
  mark.
- **The ask box** is sticky at the bottom of the conversation pane, with a
  soft fade above it. On phones it docks on top of the player.
- **The spacing ladder:**
  - lines within one item: 4–8px
  - an item's text to its actions: 16–20px
  - sibling cards: 16px
  - turns and sections: 48px
  - the rule: the bigger the gap, the looser the relationship
  - the ladder is a set of tokens (`--space-1` … `--space-12`), and the
    stylesheet uses them rather than typed values

**CFP guide** (`~/Development/cfp-agent-dean-design`):

- **A shared core with UX ideas layered on top as concepts.**
  `packages/chat-ui` holds the core, `ConceptA.tsx` plus `conceptA/` is one
  idea, and retiring an idea means deleting its files.
- **The history rail** (`conceptA/Rail.tsx`, `threads.ts`, `prefs.ts`):
  - threads saved in this browser, with follow-ups indented
  - New thread at the top and Clear at the foot
  - on wide screens it collapses to an icon, and the choice is remembered
  - on phones it is a drawer that Escape or a click outside closes
  - storage that may be missing or full never breaks the page

## Where DeadBot stands

- **`App.tsx` is 3,059 lines.** It holds every card, the formatting helpers,
  the now-playing bar, the queue pop-up, the start view, the whole classic
  shell and the workspace wiring. A new layout has to reach back into it.
- **Shells are a hard-coded pair** (`shell-mode.ts`).
- **History is in memory only.** A reload clears it.
- **The queue is a pop-up above the player** (`UpNext`), opened from a
  toggle. It offers Play next and Remove, with no reordering and no menu. The
  player (`player.tsx`) has `enqueue`, `playNext`, `remove` and `jumpTo`, but
  no `move`.
- **The player is inside the answer column,** not across the window.
- **The pages are crowded.** `styles.css` defines a spacing ladder
  (`--space-detail` … `--space-section`), but the stylesheets type about 370
  spacing values by hand against about 70 uses of the tokens. Cards, rows and
  sections end up a few pixels apart with no clear rhythm.

In our favor:

- The response contract is generated from the API (`src/generated/api.ts`).
- The workspace's logic is already separate and tested.
- Fixtures replay through either shell, which gives us before and after
  screenshots for every step.

## The plan

Six steps. Each ships as its own PR, and the live site keeps working
throughout. Steps 1 and 2 change nothing visible. Steps 3–5 land in the
workspace shell (`?shell=workspace`), so the default page is untouched until
step 6.

### 1. Split `App.tsx` into a core, cards, player and shells

Only moves:

```
web/src/
  App.tsx           thin: pick the shell, wrap it in PlayerProvider
  core/             ask-client, page-draft, exploration-state, tab-routing,
                    stream-events, research-notebook, site-nav, format
  cards/            Block and every unit card, setlist, roster, ranked
                    list, sources footer
  player/           player.tsx, PlayerBar, practice loop
  queue/            the queue rail and its row menu (step 4 fills it)
  shells/
    classic/        today's default page
    workspace/      WorkspaceShell, ExplorationPane, tabs, rails
  shells.ts         the registry: name → shell component, plus the default
```

`PageParts` goes away, since shells import `cards/` directly. `shell-mode.ts`
reads `?shell=<name>` against the registry, so a new experiment is a new
folder plus one line, and retiring one means deleting both. Each shell folder
opens with a short note saying what the idea is and when it was chosen.

Done when tests and the build pass, fixture screenshots match before and
after, and `App.tsx` is under about 100 lines.

### 2. Spacing tokens, then a spacing pass

1. **Tokens (no visible change).** Adopt WAMU's ladder and name what each
   step is for:

   | Token | Size | Use |
   | --- | --- | --- |
   | `--space-line` | 4px | lines within one item |
   | `--space-tight` | 8px | parts of one item |
   | `--space-part` | 16px | sibling items; text to its actions |
   | `--space-content` | 24px | a group's heading to its cards |
   | `--space-unit` | 48px | between groups and turns |
   | `--space-section` | 64px | between major page sections |

   Split colors into two layers while we're in the stylesheet: the raw
   palette, then the roles components use.
2. **The pass (visible).** Replace the hand-typed values in `cards/`,
   `styles.css`, `Grid.css`, `SongTimeline.css` and `VersionStrip.css` with
   the tokens:
   - give cards real padding and 16px between siblings
   - put 48px between groups
   - set reading text to a 60–70 character measure
   - drop nested frames where a card sits inside a card (`UX-NEXT-STEPS` item
     2, "reduce card framing")

   This improves both shells.

Done when every fixture is screenshotted before and after, side by side for
your review, and no stylesheet types a spacing value outside the token block
except for icon sizes.

### 3. The app frame: full-width player, docked ask

In the workspace shell:

- **Desktop.** A grid with the history rail on the left, the answer pane in
  the middle and the queue rail on the right, and the player across the full
  width below all three. Only the panes scroll.
- **Ask box.** It is sticky at the bottom of the answer pane, with a soft
  fade above it, and keeps the pane's width.
- **Phones.** One pane. The ask box docks above the player; we already have
  this from #79 and keep it.
- **The player bar** keeps everything it has today: lock screen controls,
  speed, the practice loop and the fold on phones. Its queue button opens or
  focuses the queue rail, or the sheet on phones.

### 4. The queue as a first-class rail

Built from WAMU's `QueuePanel`, fitted to DeadBot's tracks:

- **Sections.** Now playing (with an equalizer and progress), then Up next
  with its total time. Consecutive tracks from one show are grouped under the
  show's date and venue, as `UpNext` does today.
- **Rows.** A position number, the title, the length, a grip and ⋯. Selecting
  a row plays it.
- **Drag to reorder** with pointer events, for mouse and touch. The keyboard
  equivalent is Move up and Move down in the menu. Each move or removal is
  announced.
- **The ⋯ menu:**
  - Play now
  - Play next
  - Move up
  - Move down
  - Go to this show (asks about the show, or opens its page if it is already
    in history)
  - Remove from queue
- **Clear with undo.** "Clear queue" becomes "Cleared. Undo" for ten seconds.
- **The player** gains `move(from, to)` and `replaceQueue(tracks)` (for
  undo). The saved queue (#83) already persists across reloads.
- **Phones.** The same panel in a bottom sheet opened from the player.

### 5. Card actions and the history rail

**Card actions.** Every playable card (show, performance, album, song,
version strip, setlist row) uses the same two round controls at its edge:

- **Add to queue** shows +, then ✓ once it is in the queue.
- **Play** shows an equalizer while it is playing.

`CardPlayButton`, `AddToQueue` and `ListenControl` collapse into one
component in `cards/`. Spotify stays a quieter text action. One primary
action per card.

**History rail**, modeled on CFP:

- Threads are saved in this browser: the root question as the title, the
  follow-ups indented, and each page's response, so reopening a thread
  doesn't ask the model again. Keep at most 20 threads, and halve the list
  when storage is full. Measure a typical response's size first.
- The research-notebook token is stored with each thread, so a follow-up from
  an old thread picks up its research.
- New chat at the top, Recent in the middle, Clear at the foot. It replaces
  the "Your explorations" list and its back and forward arrows.
- On desktop it collapses to an icon and remembers that. On phones it is a
  drawer from the left that Escape or a click outside closes, with focus
  returning to its button. It replaces the history in the site menu.

Done for steps 3–5 when:

- unit tests cover queue moves, the menu's keyboard behavior, drag order,
  history storage (missing, full, corrupt) and drawer focus
- your real questions, run live, survive a reload and reopen correctly
- desktop and phone screenshots are reviewed with you

### 6. Make the workspace the default

First close the gaps listed in `docs/UX-NEXT-STEPS.md`:

- add the reload-on-deploy check
- add static `?fixture=` support

Then flip the default in `shells.ts`, keep `?shell=classic` for one release,
and delete `shells/classic/` after that.

## Decisions (2026-11-14)

- **History survives a reload,** as on CFP.
- **The history rail replaces the back and forward arrows.**
- **The Listen, Charts and Read tabs stay.** The rails and dock work around
  them.
- **The queue is a first-class rail** on the right, with Play and Add to
  queue on every playable card, drag to reorder and a ⋯ menu per row.
- **The player runs full width across the bottom.** The ask box is anchored
  to the bottom of the answer pane, just above the player.
- **Spacing follows WAMU's grouping ladder.** DeadBot is too crowded today.
- **The new layout evolves the existing workspace shell** rather than
  starting a third one. It is already opt-in and already has the tabs and
  history logic.
