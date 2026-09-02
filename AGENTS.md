# Working principles for agents

## Model-first product design

Deadbot should first empower the model to reason over clear, useful context.
When designing a feature, prefer giving the model the facts, relationships,
listening paths, and explicit instructions it needs to make a good choice before
adding deterministic routing or presentation rules. Keep source and coverage
metadata available as background context, but do not make them the center of a
visitor's experience unless they change the meaning of the answer.

For experience composition in particular:

- One model owns the whole turn. It researches with read-only tools and
  delivers the visible chat answer and main-body plan in one `finish_response`
  call. Do not reintroduce a handoff between a retrieval model and an editing
  model; improve the persona, tools, and plan palette instead.
- Supply rich tool output: the facts, relationships, listening paths, and
  sourced context a knowledgeable fan would want, with IDs and URLs the model
  can reference in its plan. Include source or coverage context only where it
  changes how a visitor should understand or use the material.
- Let the model decide relevance, omission, ordering, and layout regions from
  what it retrieves. Do not replace this reasoning with a growing set of
  brittle keyword-to-template rules.
- Do not encode question-specific content choices in deterministic code. In
  particular, do not hard-wire which components appear, how much related
  material to retrieve, what belongs in chat versus the main panel, or a
  response depth in reaction to an individual example. Improve the model's
  tools, persona, instructions, and evaluations instead.
- Use evaluations based on representative user questions to improve context,
  instructions, tool outputs, and model configuration before introducing
  deterministic behavior.

## Keep the model in charge

Deadbot's product quality comes from the model's judgment, not from an
accumulation of corrective code. Give the model a clear persona, a clear goal,
the user's conversation, and rich grounded material. Let it write the chat
answer, synthesize the main body, choose among presentation patterns, and decide
what to leave out.

Deterministic code is limited to transport and structural integrity: parse the
response, resolve references to supplied records, and render supported UI and
provider primitives. It must not veto an editorial choice, demand bookkeeping
about omitted material, force provenance or coverage copy into the experience,
choose content because of keywords, or silently replace the model's work with a
database-shaped dump.

When the model produces a weak experience, first improve its context, tools,
persona, goal, or available presentation palette. Do not encode the example as
a rule. If the model step fails, surface and diagnose that failure rather than
pretending an unedited retrieval packet is a finished response.
