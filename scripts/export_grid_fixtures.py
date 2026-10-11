"""Write the grid fixtures from the canonical data, with sketch-written model fields.

Run from the repo root: PYTHONPATH=. .venv/bin/python scripts/export_grid_fixtures.py
"""

import json
from pathlib import Path

from deadbot import grids
from deadbot.data import CanonicalStore

OUT = Path("web/src/fixtures")
EUROPE = ["gd-1972-04-07", "gd-1972-04-08", "gd-1972-04-11", "gd-1972-04-14", "gd-1972-04-16", "gd-1972-04-17",
          "gd-1972-04-21", "gd-1972-04-24", "gd-1972-04-26", "gd-1972-04-29", "gd-1972-05-03", "gd-1972-05-04",
          "gd-1972-05-07", "gd-1972-05-10", "gd-1972-05-11", "gd-1972-05-13", "gd-1972-05-16", "gd-1972-05-18",
          "gd-1972-05-23", "gd-1972-05-24", "gd-1972-05-25", "gd-1972-05-26"]


def write(name, spec, **model):
    store = CanonicalStore()
    payload = grids.tool_payload(grids.build(store, spec))
    block = grids.grid_block(store, payload, **model)
    (OUT / name).write_text(json.dumps(block.model_dump(mode="json"), indent=1) + "\n")


write(
    "grid-europe72.json",
    grids.GridSpec("show", tuple(EUROPE), "song", ("song-truckin", "song-dark-star", "song-the-other-one",
                   "song-morning-dew", "song-good-lovin", "song-playing-in-the-band", "song-china-cat-sunflower")),
    row_ids=None, open_rows=None,
    highlights=[{"row_id": "gd-1972-05-11", "column_id": "song-dark-star", "note": "The longest stretch of the tour, in two passes."},
                {"row_id": "gd-1972-05-07", "column_id": "song-dark-star", "note": "Bickershaw: the one night with both."},
                {"row_id": "gd-1972-05-07", "column_id": "song-the-other-one", "note": "Bickershaw: the one night with both."}],
    title="One big jam a night, and they traded it.",
    note="Every night of the tour had Dark Star or The Other One, and only Bickershaw on May 7 had both.",
    coverage=None, follow_ups=[],
)
write(
    "grid-song-years.json",
    grids.GridSpec("song", ("song-dark-star", "song-the-other-one", "song-playing-in-the-band"), "year",
                   tuple(grids.year_id(y) for y in range(1967, 1996))),
    row_ids=None, open_rows=None,
    highlights=[{"row_id": "song-dark-star", "column_id": "year:1969", "note": "Its height, on surviving setlists."}],
    title="Dark Star burned out early. Playing never left.",
    note="Dark Star was at its height in 1969 and was gone after 1974 apart from a handful of nights.",
    coverage="Before 1971 the library has setlists for only some shows, so early counts run low.",
    follow_ups=[],
)
