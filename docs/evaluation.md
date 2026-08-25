# Veneta evaluation baseline

`evals/veneta-v1.json` is the versioned, model-independent retrieval baseline
for the 1972-08-27 Veneta pilot. It contains 30 questions across entity
resolution, song/show/performance lookup, set order, performer roles, recording
metadata, media links, source discovery, provenance, and negative cases.

Each case includes:

- the user-facing question;
- the local tool and fixed arguments used to retrieve its answer;
- exact or partial expected JSON data;
- required resource IDs when a particular source must be found; and
- model-review failure conditions, especially around attribution and scope.

Run it locally with:

```bash
.venv/bin/deadbot evaluate
```

The command is deterministic: it invokes only the local canonical-data tools and
prints JSON containing a result for every case. Use `--output` to save a report
for comparison. Generated reports belong under the ignored `eval-results/`
directory; the suite itself is the tracked artifact.

To run local model responses for review, use the same suite with `--model`:

```bash
.venv/bin/deadbot evaluate --model --case media-full-show \
  --output eval-results/media-full-show.json
```

Use `--case` to keep an iteration focused, or omit it to run the full suite. The
model report contains the final answer, tool calls, required source URLs, and a
mechanical URL-citation check. It deliberately leaves source scope and prose
quality to a reviewer.

## What this measures

The baseline proves that the current tool contract can surface the canonical
entity, expected fact, media link, or attached resource. It does not invoke an
LLM, fetch an external URL, judge prose, or claim that an external source proves
more than its stored metadata.

For a model-response run, ask the case question in a fresh chat session, capture
the final response and tool trace, then assess it against the case's
`failure_conditions`. A passing response should use the relevant returned source
name and URL for contextual claims; identify interviews, memoirs, and editorial
analysis as attributed material; avoid generalizing a performance-specific source;
and plainly say when the pilot does not contain the requested entity or media
surface.

When model-response scoring is automated, add it as a separate versioned suite.
Keep tool retrieval failures distinct from model routing, citation, and prose
failures so that improvements remain diagnosable.

## Initial model findings

The first local `qwen3:8b` pass showed correct routing and attribution for a
set-opening question, an eyewitness-source question, and a full-show media link
after show-media lookup was made date-aware. It also revealed that the model can
substitute a broad show summary when a named song is absent. The system prompt now
explicitly forbids substituting a partial entity match for an unresolved named
entity. Re-run the negative cases whenever this prompt or entity search changes.
