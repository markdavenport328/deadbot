# Lore source trails

`data/lore-source-trails.json` is a small, reviewed catalog of links that can
make a factual answer more vivid. Each trail is scoped to a canonical song or
show ID and gives the model question themes plus a `why_open` invitation.

The offline `source_trails_for_entity` lookup returns metadata-only records in
the same resource-oriented shape used by research results. The catalog supplies
link metadata; the model pairs it with local canonical facts and uses the source
when the user's question benefits from context. Source claims stay attributed,
and editorial judgments stay recognizable as judgments.
