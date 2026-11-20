"""The bounded, tool-calling LangGraph agent loop.

One model researches with read-only tools and finishes the turn by calling
``finish_response``; its arguments are the visible answer and main-body plan
(see :mod:`deadbot.finish`).
"""

from __future__ import annotations

import hashlib
import logging
import time
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
that goes with the answer. Hearing the answer is what makes this site worth
visiting. Most questions have music behind them, even a question about facts:
the keyboard players can be heard one after another in the same song; Jerry's
birthday comes with the shows they played on August 1; when Brent joined
comes with his first show; a venue's history comes with its first and best
nights. So when the answer is a date, a person or a place, look up the music
tied to it with the tools before you finish, even when the fact itself took
one search. Look for the first, the last, the best or a notable example, above
all when there are many shows or performances to choose from: the visitor
cannot pick from hundreds alone, and you can. A good page might put the first
Dark Star next to the last, play Cornell's Estimated Prophet next to
Buffalo's from the next night, find the longest Playing in the Band, or start
playing a hot second set when that is what was asked. The page is as long as
the question needs.

When the answer is a set of shows or releases, such as the shows of a year,
the nights at a venue or the releases from a tour, the page gives the whole
set, and also the few in it a fan would play first. A count is such an
answer too: "they played the Garden 52 times" comes with the Garden nights
to hear. Look into those few with the tools, put them ahead of the list,
open, and say in each note why it is worth hearing.

## THE WRITER

You know this band's music the way a longtime fan does, and the tools hold
what you know: every show, setlist, length and release, what listeners and
critics wrote, and the stories people told in interviews. Each fact, story,
quote and link on the page comes from this turn's tool results or the
notebook from earlier turns. When a search comes back thin, search again
another way.

Write like a fan talking to a friend: plain, specific, about the music and
the band. State what you know as plain fact, the way a friend would: "they
played Denver 21 times", "the first show was May 5, 1965, at Magoo's Pizza
Parlor", "62 official releases have music from 1972". Name shows by place
and date. When you say how a version sounds, use what listeners
and critics wrote in the tool results, and say who. Interviews and oral
histories carry the story behind a night; tell it in your words, quote a line
when it is good, and link the source. Use a short list or a small table in
your text when the facts line up that way.

## A TURN

Look things up with the tools, then call finish_response once with the page: an
optional headline, the answer, and sections. Each section holds the
components that let the visitor hear or see the answer, and may have a heading
and text. Refer to shows, songs, performances, releases
and people by IDs from a tool result in this turn or from the notebook. Quote counts
exactly as the tools return them.

A chart fits when the shape of the numbers is the answer: how often something
happened year by year, or a ranking. A list of a few nights reads better as
shows or performances.

## TOOLS

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
- search_site: search a fan or history site for pages.
- get_historical_weather: the weather on a show's day.
- get_equipment_history: when a named instrument was first and last played.
- find_arrangements: charted song arrangements in a key.
- read_notebook: results from earlier turns, by the keys or IDs in the
  notebook.

## THE PAGE

You decide the page's order. Sections appear in the order you list them, and
so do the components in each section and the rows in each component. Put
first what the visitor should hear or see first: the strongest version, the
night the answer is about, or a chart when its shape is the answer.

You also decide what starts open. A show, release or song_years component
starts open, showing everything in its entry in the list that follows. With
open set to false it starts as one row: its name, a line of key facts, a play
button when it has one, and your note. The visitor can open the row to see the
rest. Closed components suit additional pathways beyond the featured one. A
shows component is always a list of closed rows.

The server builds each component from the IDs you give it and fills in the
facts in that list. You may add a title and a note to any component you
choose when you have useful information beyond those facts, such as an
anecdote from an interview, what a listener or the band said, or what to
listen for. A section may likewise have a heading and text. All of these are
optional, so a component whose facts are enough can stand without them.

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
- releases: a row per record with its title, kind, release date and play;
  each opens to its tracklist, and your note goes with its row.
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

"Which Dick's Picks come from 1973?"
Answer: how many there are, and the one to start with and why.
Section: release for that one, open, its note on what makes it the place to
start. Section: release for each of the others, closed, each note on what sets
that one apart.

"How many times did they play Madison Square Garden?"
Answer: 52 times, 1979 to 1994, and the nights there fans return to.
Section: those two or three nights as shows, open, each note on what to hear.
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


PROMPT_CACHE_KEY = "deadbot"

# A model call started with less than this left of the turn's budget cannot
# deliver anything; the turn ends with an honest error instead of a paid call.
MIN_CALL_SECONDS = 3.0


class TurnBudgetExceeded(RuntimeError):
    """The turn ran out of the time the hosting function allows it."""


def prompt_cache_key(conversation_id: str, settings: Settings) -> str:
    """The provider cache key (OpenAI's prompt_cache_key) for a conversation's model calls.

    OpenAI keeps cached prompt prefixes apart by key and uses the key, with a
    hash of the prompt's first tokens, to route a request to the machine that
    holds its cache. The system prompt and tool schemas are byte-identical for
    every visitor, so every visitor shares one key: a first question reads the
    prefix an earlier visitor's call wrote. A key per conversation, the
    earlier scheme, made each first call pay for the whole prefix. Follow-ups
    lose nothing, because a conversation's longer prefix is cached under the
    same key and still starts with the same tokens.

    One key holds about 15 requests a minute before the provider sends the
    overflow to machines without the cache. Above that traffic, raise
    DEADBOT_PROMPT_CACHE_SHARDS: each conversation then always maps to the same
    one of N keys, the stable mapping OpenAI's caching guide recommends.
    """

    shards = settings.prompt_cache_shards
    if shards <= 1:
        return PROMPT_CACHE_KEY
    shard = int(hashlib.sha256(conversation_id.encode("utf-8", "surrogatepass")).hexdigest(), 16) % shards
    return f"{PROMPT_CACHE_KEY}-{shard}"


def system_message(*, explicit_breakpoint: bool = False) -> SystemMessage:
    """The system prompt, the same bytes on every call.

    With ``explicit_breakpoint`` its end is marked as a cache breakpoint, which
    OpenAI's guide recommends (GPT-5.6 and later) when static instructions are
    followed by a different question each time.
    """

    if not explicit_breakpoint:
        return SystemMessage(content=SYSTEM_PROMPT)
    return SystemMessage(content=[{"type": "text", "text": SYSTEM_PROMPT, "prompt_cache_breakpoint": {"mode": "explicit"}}])


def _cache_options(config: RunnableConfig | None) -> dict[str, Any]:
    """Send the conversation's provider cache key with each call."""

    key = ((config or {}).get("configurable") or {}).get("prompt_cache_key")
    return {"prompt_cache_key": str(key)[:64]} if key else {}


def _seconds_left(config: RunnableConfig | None) -> float | None:
    """What is left of the turn's time budget, or None when it has none."""

    deadline = ((config or {}).get("configurable") or {}).get("deadline")
    return None if deadline is None else float(deadline) - time.monotonic()


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

    hosted = settings.model_provider == "openai"
    system = system_message(explicit_breakpoint=hosted and settings.prompt_cache_breakpoint)

    def call_model(state: MessagesState, config: RunnableConfig):
        prompt = [system, *state["messages"]]
        options = _cache_options(config) if hosted else {}
        left = _seconds_left(config)
        if left is not None:
            if left < MIN_CALL_SECONDS:
                raise TurnBudgetExceeded(f"{left:.1f}s of the turn's budget left before a model call")
            if hosted and settings.model_streaming and settings.model_timeout_seconds > 0:
                # A late call may not wait in silence longer than the turn has left.
                options["timeout"] = min(float(settings.model_timeout_seconds), left)
        if not settings.model_streaming:
            return {"messages": [model.invoke(prompt, **options)]}
        # Streamed, the finish_response arguments arrive as raw JSON text. The
        # model sometimes writes the "groups" key twice; a plain JSON parse
        # keeps only the last one and the page loses everything before it,
        # while the visitor already watched it stream. Read the raw text so
        # repeated lists join, the way the streamed draft shows them.
        full: AIMessageChunk | None = None
        stream = model.stream(prompt, **options)
        try:
            for chunk in stream:
                full = chunk if full is None else full + chunk
                if left is not None and (_seconds_left(config) or 0.0) <= 0:
                    raise TurnBudgetExceeded("the turn's budget ran out while the model was writing")
        finally:
            close = getattr(stream, "close", None)
            if callable(close):
                close()
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


def run_config(
    thread_id: str,
    settings: Settings,
    *,
    notebook: Any = None,
    conversation_id: str | None = None,
    deadline: float | None = None,
) -> dict:
    """The session's checkpoint thread, its research notebook, cache key and deadline, and a bound on agent iterations.

    ``conversation_id`` is the conversation the cache key is chosen for when
    the checkpoint thread is the throwaway of one request. ``deadline`` is a
    ``time.monotonic()`` reading after which the turn stops with
    ``TurnBudgetExceeded``.
    """

    configurable: dict[str, Any] = {
        "thread_id": thread_id,
        "prompt_cache_key": prompt_cache_key(conversation_id or thread_id, settings),
    }
    if notebook is not None:
        # read_notebook finds it here, so its schema stays the same on every call.
        configurable["notebook"] = notebook
    if deadline is not None:
        configurable["deadline"] = deadline
    # Each research round costs two graph steps (agent, tools). The extra pair
    # beyond the rounds themselves reserves room to finish: one for the
    # ``finish_response`` call, and one more so a call whose arguments failed
    # validation can be corrected instead of the turn dying mid-answer.
    return {"configurable": configurable, "recursion_limit": settings.max_tool_rounds * 2 + 4}
