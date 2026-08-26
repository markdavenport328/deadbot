# Working principles for agents

## Model-first product design

Deadbot should first empower the model to reason over clear, grounded context.
When designing a feature, prefer giving the model the information, relationships,
provenance, coverage limits, and explicit instructions it needs to make a good
choice before adding deterministic routing or presentation rules.

For experience composition in particular:

- Supply a structured decision brief: the latest question, relevant
  conversation, grounded agent answer, canonical facts, coverage metadata, and
  a rich inventory of eligible blocks with their scope, purpose, relationship,
  and provenance.
- Let the model decide relevance, omission, ordering, and layout regions from
  that brief. Do not replace this reasoning with a growing set of brittle
  keyword-to-template rules.
- Use evaluations based on representative user questions to improve context,
  instructions, tool outputs, and model configuration before introducing
  deterministic behavior.

## Deterministic guardrails

Deterministic code remains essential, but its job is to enforce boundaries—not
to take over ordinary product judgment. It must:

- validate model references against the supplied retrieval packet;
- allow only known response schemas, block types, layout regions, and provider
  embeds;
- preserve source/provenance requirements and prevent partial coverage from
  being presented as a complete factual result;
- reject invented entities, URLs, markup, and ungrounded content; and
- provide a safe deterministic fallback when a model response is unavailable
  or invalid.

If an evaluation exposes a repeated safety failure that cannot be addressed by
better context or instructions, add the narrowest deterministic guardrail that
solves that failure and document why it is necessary.
