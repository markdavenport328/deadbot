"""Write the web's list fixtures from the real library.

Each fixture is a finish_response plan run through the same resolution the
live service uses, against tool results from the real SQLite catalog, so the
rows, covers, counts and tracks on the page are the library's own. Run from
the repository root:

    PYTHONPATH=. python scripts/export_list_fixtures.py

It writes web/src/fixtures/<name>.json for releases1972, shows1977,
harrisburg, darkstar and mostplayed.
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from deadbot import finish
from deadbot.sqlite_build import build_database
from deadbot.sqlite_store import SqliteCanonicalStore
from deadbot.tools import build_tools

OUT = Path(__file__).resolve().parents[1] / "web" / "src" / "fixtures"


def _turn(question: str, calls: list[tuple[str, dict, dict]], plan: dict) -> list:
    messages: list = [HumanMessage(content=question)]
    for index, (name, args, payload) in enumerate(calls):
        call_id = f"call-{index}"
        messages.append(AIMessage(content="", tool_calls=[{"name": name, "args": args, "id": call_id, "type": "tool_call"}]))
        messages.append(ToolMessage(content=json.dumps(payload), tool_call_id=call_id, name=name))
    messages.append(AIMessage(content="", tool_calls=[{"name": finish.FINISH_TOOL_NAME, "args": plan, "id": "finish", "type": "tool_call"}]))
    messages.append(ToolMessage(content="Response delivered to the visitor.", tool_call_id="finish", name=finish.FINISH_TOOL_NAME))
    return messages


def main() -> None:
    with tempfile.TemporaryDirectory() as folder:
        store = SqliteCanonicalStore(build_database(Path(folder) / "deadbot.sqlite").path, response_cache_path=Path(folder) / "cache.sqlite")
        tools = {tool.name: tool for tool in build_tools(store)}

        def call(tool_name: str, **args):
            return tool_name, args, json.loads(tools[tool_name].invoke(args))

        fixtures: dict[str, tuple[str, list, dict]] = {}

        releases = call("query_catalog", name="releases_covering_years", year_from=1972)
        count = len(releases[2]["rows"])
        fixtures["releases1972"] = (
            "Which official releases cover 1972?",
            [releases],
            {
                "chat_answer": f"{count} official releases carry music from 1972, from the Europe '72 tour to the Veneta and Dick's Picks sets.",
                "title": f"{count} official releases carry 1972",
                "lead": "Every record below draws on 1972 shows, in release order. Open one for its tracklist and credits.",
                "groups": [{"presentation": "collection", "items": [{"type": "album_unit", "from_result": releases[2]["result_id"], "disclosure": "collapsed", "visible_facets": ["listen", "tracklist", "personnel"]}]}],
            },
        )

        shows = call("query_catalog", name="shows", year_from=1977)
        fixtures["shows1977"] = (
            "What shows did the Dead play in 1977?",
            [shows],
            {
                "chat_answer": f"The library lists {len(shows[2]['rows'])} Grateful Dead shows in 1977, from the February opener in San Bernardino to the year-end run at Winterland.",
                "title": "The Dead's 1977, show by show",
                "lead": "Every 1977 show in the library, in date order. Open a show for its setlist.",
                "groups": [{"presentation": "collection", "items": [{"type": "show_unit", "from_result": shows[2]["result_id"], "disclosure": "collapsed", "visible_facets": ["setlist", "listen", "guests"]}]}],
            },
        )

        harrisburg = call("query_catalog", sql="SELECT show_id, show_date, venue_name, city FROM show_facts WHERE city = 'Harrisburg' ORDER BY show_date")
        fixtures["harrisburg"] = (
            "When did the Dead play Harrisburg PA?",
            [harrisburg],
            {
                "chat_answer": "Twice, both on City Island in the Susquehanna: June 22, 1983 and June 23, 1984.",
                "title": "Harrisburg saw the Dead twice",
                "groups": [{"presentation": "collection", "items": [{"type": "show_unit", "from_result": harrisburg[2]["result_id"], "disclosure": "expanded", "emphasis": "supporting", "visible_facets": ["setlist", "listen"]}]}],
            },
        )

        dark_star = call("get_song", song_id_or_title="Dark Star")
        years = call("aggregate_data", dataset="performances", group_by="year", measure="count", song_id="song-dark-star", fill_missing=True)
        fixtures["darkstar"] = (
            "When was Dark Star played?",
            [dark_star, years],
            {
                "chat_answer": "Dark Star peaked in 1969, fell nearly silent after 1974, and came back for a run from 1989 to 1994.",
                "title": "Dark Star peaked in 1969 and returned in 1989",
                "groups": [
                    {"presentation": "collection", "items": [{"type": "song_overview", "song_id": "song-dark-star", "emphasis": "primary", "visible_facets": ["by_year", "history"], "note": "Seventy nights in 1969, a handful after 1974, then a late revival that peaked in 1991."}]},
                    {"presentation": "collection", "items": [{"type": "data_chart", "aggregation_id": years[2]["aggregation_id"], "title": "The same years from aggregate_data"}]},
                ],
            },
        )

        top = call("aggregate_data", dataset="performances", group_by="song", measure="count", limit=15)
        first = top[2]["rows"][0]
        fixtures["mostplayed"] = (
            "What songs did the Dead play most?",
            [top],
            {
                "chat_answer": f"{first['label']} leads the count, since the percussion segment sits in nearly every second set; Playing in the Band leads the songs.",
                "title": "The songs the Dead played most",
                "groups": [{"presentation": "collection", "items": [{"type": "ranked_list", "aggregation_id": top[2]["aggregation_id"], "count": 10, "title": "Ten most-played songs", "notes": [{"key": first["id"], "note": "The nightly second-set percussion segment, counted as its own entry."}]}]}],
            },
        )

        OUT.mkdir(parents=True, exist_ok=True)
        for name, (question, calls, plan) in fixtures.items():
            response = finish.build_experience_response(question, f"visual-{name}", _turn(question, calls, plan), store)
            text = json.dumps(response.model_dump(mode="json"), ensure_ascii=False, separators=(",", ":"))
            (OUT / f"{name}.json").write_text(text + "\n", encoding="utf-8")
            print(f"{name}: {len(response.blocks)} blocks, {len(text) / 1024:.0f} KB")
        store.close()


if __name__ == "__main__":
    main()
