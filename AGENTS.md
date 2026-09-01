# Working principles for agents

## Model-first product design

Deadbot should first empower the model to reason over clear, useful context.
When designing a feature, prefer giving the model the facts, relationships,
listening paths, and explicit instructions it needs to make a good choice before
adding deterministic routing or presentation rules. Keep source and coverage
metadata available as background context, but do not make them the center of a
visitor's experience unless they change the meaning of the answer.

For experience composition in particular:

- Supply a structured decision brief: the latest question, relevant
  conversation, grounded answer, useful facts and relationships, and a rich
  inventory of eligible blocks with their purpose, exploration value, and
  connections. Include source or coverage context only where it changes how a
  visitor should understand or use the material.
- Let the model decide relevance, omission, ordering, and layout regions from
  that brief. Do not replace this reasoning with a growing set of brittle
  keyword-to-template rules.
- Do not encode question-specific content choices in deterministic code. In
  particular, do not hard-wire which components appear, how much related
  material to retrieve, what belongs in chat versus the main panel, or a
  response depth in reaction to an individual example. Improve the model's
  brief, candidate design, instructions, and evaluations instead.
- Use evaluations based on representative user questions to improve context,
  instructions, tool outputs, and model configuration before introducing
  deterministic behavior.

## Deterministic guardrails

Deterministic code remains essential, but its job is to enforce boundaries—not
to take over ordinary product judgment. It must:

- validate model references against the supplied retrieval packet;
- allow only known response schemas, block types, layout regions, and provider
  embeds;
- retain the evidence and scope needed to support claims, while leaving the
  model to decide when that context belongs in the visitor-facing experience;
- reject invented entities, URLs, markup, and ungrounded content; and
- provide a safe deterministic fallback when a model response is unavailable
  or invalid.

Do not turn ordinary editorial or product-quality feedback into a deterministic
rule. Validation remains about the boundary of what the model may return, not
about choosing the visitor's experience.
