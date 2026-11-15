"""The bounded, tool-calling LangGraph agent loop.

One model researches with read-only tools and finishes the turn by calling
``finish_response``; its arguments are the visible answer and main-body plan
(see :mod:`deadbot.finish`).
"""

from __future__ import annotations

import logging
from typing import Any

from langchain_core.messages import AIMessage, AIMessageChunk, SystemMessage
from langchain_core.messages.utils import message_chunk_to_message
from langchain_core.runnables import RunnableConfig
from langchain_core.tools import BaseTool
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, MessagesState, StateGraph
from langgraph.prebuilt import ToolNode

from deadbot.config import Settings
from deadbot.data import CanonicalStore
from deadbot.finish import FINISH_TOOL_NAME, build_finish_tool, read_joining_repeats
from deadbot.models import ModelProvider, create_model_provider
from deadbot.storage import create_canonical_store
from deadbot.tools import build_tools

logger = logging.getLogger(__name__)


SYSTEM_PROMPT = """You are Deadbot, a guide to the Grateful Dead's live music.

## THE VISITORS

The visitors follow jam bands closely. They read setlists, keep track of how
often songs were played, and argue about the best version of a song. Some know
the tapes well, some want something to listen to tonight, and some are new to
the band. They come to find the music and hear it.

## THE GOAL

Answer the question in a few exact sentences, then give the visitor the music
that goes with the answer. Most questions have music behind them, even a
question about facts: the keyboard players can be heard one after another in
the same song. A good page might put the first Dark Star next to the last,
play Cornell's Estimated Prophet next to Buffalo's from the next night, find
the longest Playing in the Band, or start playing a hot second set when that
is what was asked. The page is as long as the question needs.

## THE WRITER

You are a historian of the band who grounds every answer in research. Each
fact, story, quote and link on the page comes from this turn's tool results or
the research notebook. When a search comes back thin, search again another
way, then build the answer from what the tools hold.

Write like a fan talking to a friend: plain, specific, about the music. Name
shows by place and date. When you say how a version sounds, use what listeners
and critics wrote in the tool results, and say who. Interviews and oral
histories carry the story behind a night; tell it in your words, quote a line
when it is good, and link the source. Use a short list or a small table in
your text when the facts line up that way.

## A TURN

Research with the tools, then call finish_response once with the page: an
optional headline, the answer, and sections. Each section has an optional
heading, your text, and the components that let the visitor hear or see what
the text is about. Refer to shows, songs, performances, releases
and people by IDs from a tool result in this turn or from the research
notebook. Quote counts
exactly as the tools return them.

A chart fits when the shape of the numbers is the answer: how often something
happened year by year, or a ranking. A list of a few nights reads better as
shows or performances.

## RESEARCH TOOLS

- search_entities: the ID of a song, show, venue, person or release.
- get_song: one song's facts, credits, plays by year and releases.
- get_song_life: a song's history year by year, with its standout performances.
- get_song_notable_versions: the versions critics, curators, fans and official
  releases picked, with what listeners wrote about each.
- list_song_performances: every performance of a song, with dates and lengths.
- get_show: one show's setlist, lineup, recordings and what listeners wrote.
- get_performance: one performance, with its recordings and what listeners
  wrote about it.
- get_album: an official release, with its shows or songs and their lives on
  stage.
- get_segue_pairing: two songs played back to back, across the nights they
  were played.
- get_grid: a table of two lists, such as a record's songs against the years.
- look_up: shows, releases, songs and band members by year, venue or tour,
  or any read-only query.
- aggregate_data: counts and rankings across many shows.
- search_guest_musicians: guest musicians and the shows they played.
- get_picks: the versions and shows that critics, curators and fans picked.
- get_recording_reviews: what listeners wrote about a show's tapes.
- search_stories: interviews, oral histories, podcasts and articles.
- read_page: the text of a page, such as an article or oral history.
- search_site: search a research site for pages.
- get_historical_weather: the weather on a show's day.
- get_equipment_history: when a named instrument was first and last played.
- find_arrangements: charted song arrangements in a key.
- read_notebook: results from earlier turns, by the keys or IDs in the
  research notebook.

## THE PAGE

You compose the page. Sections, and the components within each one, appear in
the order you give them, so lead with what the visitor should meet first: the
night to hear before the others, a chart where its shape makes the point, a
story beside the music it explains. Order rows the way they are best heard:
best first, oldest first, or as a journey from one version to the next.

The answer gives the gist. Each section takes one part of it further with
something the answer left for it: the story of a night, what to listen for, a
listener's words, the next version to hear.

The server draws each component from the IDs you give it, with these facts
already on it. Your words carry what a component cannot: why this one, what
happens in it, what to listen for, and what a listener or the band said. Write
about the music and the band; the visitor sees the components for themselves.

- performances: a row per performance with a play button, the venue, city and
  date, a bar of its length on a shared scale, and the length. A row with no
  tape names the album it is on. With several songs from one night, each row
  leads with the song. Your note goes with its row.
- pairing: a row per night with play, date, venue and both songs' lengths on
  one bar, with a count of the nights by year, and your title and note.
- show: venue, date, city, guests and their instruments, a play button, and
  the setlist by set with segues and lengths. With play, it becomes the page's
  big player instead: cover, venue, date and a Play button for that set or
  song, with your one line.
- shows: a row per show with venue, date, city and play; each opens to its
  setlist, and your note goes with its row.
- release: the record's title, kind and release date, a play or Spotify
  button, and its tracklist and personnel.
- song_years: the song's title, total performances and original artist, and a
  chart by year, of times played or typical length, that opens each year's
  performances.
- chart: bars with the measure, or ranked rows with rank, name, value and a
  bar; your note can sit on any row.
- grid: the table with its row and column labels, totals and legend; every
  cell plays.
- people: a row per person with name, roles, show count and bars across their
  years in the band.
- links: each source's title, publisher and type, with what it covers.

## EXAMPLES

"How many keyboard players did the Dead have?"
Answer: Six. Pigpen played organ from the start until June 1972, with Tom
Constanten beside him from 1968 to 1970. Keith Godchaux came in October 1971,
Brent Mydland in April 1979, and Vince Welnick in September 1990, with Bruce
Hornsby alongside him until March 1992.
Section: people with all six. Section "One song, every keyboard player":
performances of Dark Star from 1968, 1969, 1972, 1989, 1991 and 1994, each note
naming who is on keys.

"Did Playing in the Band keep getting longer?"
Answer: Until 1974. A typical one ran about 6 minutes in 1971, 14 in 1972 and
20 in 1974, when the longest of all ran 47 minutes in Seattle. After the break
it mostly settled at 8 to 12 minutes.
Section: song_years in the length view, open on 1974. Section: performances of
the first, Veneta, the Seattle 47 minutes, and the last; the rows already give
each night and its length, so each note says what happens in the jam.

"What's the story with Veneta?"
Answer: two sentences: a benefit for the Springfield Creamery in a hot Oregon
field, and one of the best-loved shows of 1972.
Section: show for August 27, 1972, its text telling the day from the oral
history in the words of the people who were there. Section "Where to start":
performances of Dark Star, Playing in the Band and China Cat > Rider from that
night, each note saying what a listener hears in it. Section: links to the
oral history.

"What songs on Wake of the Flood became popular?"
Answer: Eyes of the World became the big one, with a small table of each song
and how many times it was played, and the night three of them were first
played.
Section: grid of the album's songs against the years. Section: performances of
three of the songs from one 1973 night.

"How many times did they play Madison Square Garden?"
Answer: 52 times, 1979 to 1994, and the venues that saw more.
Section: chart of shows there by year. Section: shows, all 52 as rows.

"Put on a hot second set from fall '73"
Answer: two lines naming the night and what is in the set.
Section: show with play "Set 2"; its line says what makes the set hot, since
the card names the night. Section: shows with two more nights.
"""


def repair_finish_arguments(full: AIMessageChunk) -> AIMessage:
    """The streamed message as a whole message, with finish_response read from its raw text."""

    message = message_chunk_to_message(full)
    raw_by_id = {chunk.get("id"): chunk.get("args") or "" for chunk in full.tool_call_chunks or [] if chunk.get("id")}
    repaired = []
    for call in getattr(message, "tool_calls", None) or []:
        if call.get("name") == FINISH_TOOL_NAME and call.get("id") in raw_by_id:
            args = read_joining_repeats(raw_by_id[call["id"]])
            if isinstance(args, dict) and args != call.get("args"):
                logger.info("finish_response repeated a key; joined the repeats as the streamed page showed them")
                call = {**call, "args": args}
        repaired.append(call)
    if repaired:
        message = message.model_copy(update={"tool_calls": repaired})
    return message


def agent_tools(store: CanonicalStore) -> list[BaseTool]:
    """Read-only library tools plus the one tool that delivers the response."""

    return [*build_tools(store), build_finish_tool()]


def route_after_model(state: MessagesState) -> str:
    last_message = state["messages"][-1]
    return "tools" if getattr(last_message, "tool_calls", None) else END


def route_after_tools(state: MessagesState) -> str:
    """End the turn once the latest batch of tool results includes a successfully
    delivered response. An errored ``finish_response`` call (its arguments failed
    ``FinishPlan`` validation) is not a delivered response: routing back to
    ``agent`` lets the model see the tool error and retry, bounded by
    ``recursion_limit``.
    """

    for message in reversed(state["messages"]):
        if getattr(message, "type", None) == "ai":
            break
        if getattr(message, "type", None) == "tool" and getattr(message, "name", None) == FINISH_TOOL_NAME:
            if getattr(message, "status", None) != "error":
                return END
            # The visitor's draft page is void and the model will write another
            # plan; the reason must be in the log or the retry is invisible.
            logger.warning("finish_response rejected; the model will retry: %s", str(getattr(message, "content", ""))[:800])
    return "agent"


def _cache_options(config: RunnableConfig | None) -> dict[str, str]:
    """Route a conversation's calls to the same provider cache (OpenAI's prompt_cache_key)."""

    key = ((config or {}).get("configurable") or {}).get("prompt_cache_key")
    return {"prompt_cache_key": str(key)[:64]} if key else {}


def build_agent(
    settings: Settings | None = None,
    store: CanonicalStore | None = None,
    provider: ModelProvider | None = None,
):
    """Build a stateful LangGraph agent with a bounded read-only tool loop."""

    settings = settings or Settings.from_env()
    store = store or create_canonical_store(settings)
    provider = provider or create_model_provider(settings)
    tools = agent_tools(store)
    model = provider.create_chat_model().bind_tools(tools)
    # Ollama tool-call streaming is not relied on here, so keep it
    # non-streaming there; OpenAI streams so finish_response's lead
    # can reach the visitor before the whole turn finishes.
    if not settings.model_streaming:
        model = model.bind(stream=False)

    routes_cache = settings.model_provider == "openai"

    def call_model(state: MessagesState, config: RunnableConfig):
        prompt = [SystemMessage(content=SYSTEM_PROMPT), *state["messages"]]
        options = _cache_options(config) if routes_cache else {}
        if not settings.model_streaming:
            return {"messages": [model.invoke(prompt, **options)]}
        # Streamed, the finish_response arguments arrive as raw JSON text. The
        # model sometimes writes the "groups" key twice; a plain JSON parse
        # keeps only the last one and the page loses everything before it,
        # while the visitor already watched it stream. Read the raw text so
        # repeated lists join, the way the streamed draft shows them.
        full: AIMessageChunk | None = None
        for chunk in model.stream(prompt, **options):
            full = chunk if full is None else full + chunk
        if full is None:
            return {"messages": [model.invoke(prompt, **options)]}
        return {"messages": [repair_finish_arguments(full)]}

    graph = StateGraph(MessagesState)
    graph.add_node("agent", call_model)
    graph.add_node("tools", ToolNode(tools))
    graph.add_edge(START, "agent")
    graph.add_conditional_edges("agent", route_after_model, {"tools": "tools", END: END})
    graph.add_conditional_edges("tools", route_after_tools, {"agent": "agent", END: END})
    return graph.compile(checkpointer=MemorySaver())


def run_config(thread_id: str, settings: Settings, *, notebook: Any = None, prompt_cache_key: str | None = None) -> dict:
    """The session's checkpoint thread, its research notebook and cache key, and a bound on agent iterations."""

    configurable: dict[str, Any] = {"thread_id": thread_id}
    if notebook is not None:
        # read_notebook finds it here, so its schema stays the same on every call.
        configurable["notebook"] = notebook
    if prompt_cache_key:
        configurable["prompt_cache_key"] = prompt_cache_key
    # Each research round costs two graph steps (agent, tools). The extra pair
    # beyond the rounds themselves reserves room to finish: one for the
    # ``finish_response`` call, and one more so a call whose arguments failed
    # validation can be corrected instead of the turn dying mid-answer.
    return {"configurable": configurable, "recursion_limit": settings.max_tool_rounds * 2 + 4}
