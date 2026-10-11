"""Write the song timeline's preview fixtures from the real library.

The card data and every year's performances are the library's own, read
through deadbot.song_life from the real SQLite catalog. The stops, the open
year and the year questions stand in for what the model writes in the app;
they are marked as stand-ins in the fixture. Run from the repository root:

    PYTHONPATH=. python scripts/export_song_timeline_fixture.py

It writes web/src/fixtures/song-timeline-terrapin.json (the card) and
web/src/fixtures/song-timeline-terrapin-years.json (every year's See all list).
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

from deadbot import song_life
from deadbot.sqlite_build import build_database
from deadbot.sqlite_store import SqliteCanonicalStore

OUT = Path(__file__).resolve().parents[1] / "web" / "src" / "fixtures"
SONG_ID = "song-terrapin-station"

# Stand-ins for the model's stops: (show date, label, why).
STAND_IN_STOPS = [
    ("1977-02-26", "The debut", "First time out, opening the show five months before the studio album."),
    ("1977-05-28", "Hartford, the version of record", "Released on its own as To Terrapin. The spring 1977 arrangement at full strength."),
    ("1978-09-15", "At the pyramids", "Played at the foot of the Great Pyramid, coming out of Space."),
    ("1979-01-08", "Charlie Miller's pick", "The 1979 show Charlie Miller singles out, and the one from the visitor's first question."),
    ("1981-12-31", "New Year's, inside Playin'", "Tucked into the middle of Playing in the Band on New Year's Eve."),
    ("1989-12-06", "With Clarence Clemons", "Clemons sits in on sax and the song stretches to almost 23 minutes."),
    ("1993-09-29", "The longest", "Over 25 minutes in Boston, the longest Terrapin on record."),
    ("1995-07-08", "The last", "The final Terrapin, at Soldier Field the night before the band's last show."),
]
STAND_IN_QUESTIONS = {
    1977: "How did Terrapin change between its debut and the fall of 1977?",
    1979: "How did the 1979 Terrapins differ from 1977?",
    1980: "Why did Terrapin start leading into Drums in 1980?",
    1989: "What did Clarence Clemons add to Terrapin?",
    1993: "What made the Boston '93 Terrapin run 25 minutes?",
}


def main() -> None:
    with tempfile.TemporaryDirectory() as folder:
        store = SqliteCanonicalStore(build_database(Path(folder) / "deadbot.sqlite").path, response_cache_path=Path(folder) / "cache.sqlite")
        card = song_life.card_data(store, SONG_ID)
        if card is None:
            raise SystemExit(f"{SONG_ID} is not in the library")
        performances = {p.show_date: p for p in song_life.life_performances(store, SONG_ID)}
        stops = []
        for show_date, label, why in STAND_IN_STOPS:
            performance = performances[show_date]
            stops.append(
                {
                    "performance_id": performance.performance_id,
                    "label": label,
                    "why": why,
                    "show_date": performance.show_date,
                    "venue_name": performance.venue_name,
                    "seconds": performance.seconds,
                    "track": performance.track_json(card["title"]),
                }
            )
        card.update(
            {
                "_note": "Stops, open_year, chart_view and year_questions are stand-ins for the model's choices; every other fact is the library's.",
                "stops": stops,
                "open_year": 1979,
                "chart_view": "count",
                "year_questions": [{"year": year, "question": question} for year, question in STAND_IN_QUESTIONS.items()],
            }
        )
        years = {
            str(row["year"]): song_life.year_detail(store, SONG_ID, row["year"])
            for row in card["year_summaries"]
            if row["count"]
        }
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "song-timeline-terrapin.json").write_text(json.dumps(card, indent=1, ensure_ascii=False) + "\n")
    (OUT / "song-timeline-terrapin-years.json").write_text(json.dumps(years, separators=(",", ":"), ensure_ascii=False) + "\n")
    print(f"Wrote the card ({len(card['year_summaries'])} years, {len(stops)} stops) and {len(years)} years of performances")


if __name__ == "__main__":
    main()
