# Working principles for agents

## First principle

A model with the right goal and the right material will give a visitor an
intelligent, surprising answer. Empower the model and get out of its way.

Divide the labor cleanly:

- **Code guards facts and transport.** It keeps records exact (a show's date,
  a setlist, a credit, a recording), supplies them when the model names them by
  ID, turns stored links into safe players, parses the model's response, and
  renders it.
- **The model owns judgment.** It decides what to say, what to show, what to
  leave out, how deep to go, how to order and group the page, and what belongs
  in chat versus the main body.

Every rule in this file follows from that split. When a choice is unclear, ask
which side of it the work belongs on.

## Give the model shapes, material, and a goal

The model does its best work with three things: a clear persona and goal, rich
tool output, and a palette of well-shaped components.

- **The right components give the model freedom.** Deadbot is a software
  interface over a structured music library: shows, songs, performances,
  releases, people, and eras, with well-defined relationships between them.
  That world rewards a rich component palette. Each component matches a task a
  fan brings to the library: a show, a performance, a song's life on stage, an
  era, a version strip, a ranked list, a chart. It lets the model say "this
  show, with these facets, opened this far" and trust code to fill in the
  facts. Lean into components. Add or reshape one when the model has a task or
  relationship to express that the palette cannot hold, design it for the whole
  family of questions that need it, and let the model choose when and how to
  use it.
- **Tool output carries what a knowledgeable fan would want.** Include facts,
  relationships, listening paths, and IDs and URLs the model can reference. The
  order and grouping of tool output steers how the model organizes the page, so
  design it deliberately. Include source or coverage context where it changes
  how a visitor should understand the material.
- **The persona states goals as principles.** A short prompt the model can hold
  in mind beats a rulebook. Write guidance as what to do, with examples of good
  work. Give the model the latitude to decide how much to include.
- **One model owns the whole turn.** It researches with read-only tools and
  delivers the chat answer and the page plan in one `finish_response` call.
  Improve that model's persona, tools, and palette rather than adding a second
  model step.

## Keep code to facts and transport

Before adding any check, cap, or rule, ask: does it protect a fact or the
transport? If it only polices the model's choices, leave it out.

Code that belongs:

- Resolving a referenced ID to the stored record, and filling a card's facts
  from the store instead of from the model.
- Building players and links from stored or tool-returned URLs.
- Reading the streamed response, and ceilings far above normal use that keep a
  response deliverable (they truncate and log).

How code treats the model's work:

- Read the plan leniently. Ignore keys the schema does not name, keep the rest
  of an item when one field is bad, and infer an obvious missing type.
- Keep the model's work on the page. A reference that does not resolve renders
  the model's own text; an item that does not fit a component becomes prose.
- Size limits trim and log; they keep the content.
- Streamed and delivered pages go through the same path, so what streamed is
  what the visitor keeps.
- When the model step itself fails, surface and diagnose the failure. Show the
  visitor an honest error rather than a database packet dressed as an answer.

## When an answer is weak

1. Ask what the model was missing: context, a tool result, a clearer goal, or a
   component shape that fits what it wanted to say.
2. Supply that, and prefer deleting a constraint over adding one to compensate.
   A field the model must fill that the visitor never sees costs time; remove
   it.
3. Check the fix against the owner's real questions, run live. Fixtures prove
   that rendering works; only live runs prove the model's answers improved.
   Evaluations built from representative questions show whether a change helps
   the whole family of questions, not just the example that prompted it.

Fix the family, not the example. A change written to repair one question, such
as a keyword route, a forced component, or a fixed depth, is case law; it
breaks the next question.

## Continuing UX work

[docs/UX-NEXT-STEPS.md](docs/UX-NEXT-STEPS.md) is the running log of UX
implementation status, repository-folder reconciliation, and remaining work.
Read it for history and open items; this file's principles take precedence
where the two differ.

## Pushing to GitHub

The repository owner's administrator has blocked agents from pushing to
GitHub. An agent may commit locally and open pull requests with `gh` once a
branch exists on the remote, but it cannot push. When work is ready to push,
give the owner the exact `git push` command to run from their terminal, on its
own line in a shell code block, and wait for confirmation before opening or
updating a pull request.
