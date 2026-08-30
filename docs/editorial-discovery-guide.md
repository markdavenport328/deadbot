# Editorial discovery guide

`data/editorial/discovery-guide.json` is a small, source-controlled candidate
inventory for model-led exploration. It gives the model promising lore paths
across songs, improvisation, transitions, lyrics/history, show context, and
late-era sound/MIDI.

The model may select, combine, reorder, or omit leads based on the current user
question and grounded retrieval context. Each lead asks the model to research
and verify concrete details before presenting them. Retrieved evidence, coverage
limits, and provenance anchor the answer.

The offline loader (`deadbot.editorial_discovery.load_discovery_guide`) validates
the schema, required fields, unique IDs, allowed categories, and verification
instructions. It performs no network calls.

At agent construction, `model_discovery_brief()` provides the answering model
the whole compact inventory. The model decides which leads fit, which ones to
combine, and when a direct answer needs no exploration. The composer retains
its separate, narrower job of selecting only server-owned main-column blocks.
