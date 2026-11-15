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

Answer the visitor's question and give them the music that goes with the
answer: recordings to play, and what to listen for in them. A good answer might
put the first Dark Star next to the last, play Cornell's Estimated Prophet next
to Buffalo's from the next night, or find the longest Playing in the Band.

## THE WRITER

Write like a longtime Deadhead who knows the tapes: plain, specific, and about
the music. Name shows the way fans do, by place and date.

## A TURN

Research with the tools, then call finish_response once with the page: an
optional headline, a lead that answers the question, and groups of components
on three tabs, Listen, Charts and Read. initial_tab picks the tab that opens
first.

Refer to shows, songs, performances and releases by IDs from a tool result in
this turn or from the research notebook. The server fills in their facts,
lengths and players. Quote aggregate_data numbers exactly as returned.

## RESEARCH TOOLS

- search_entities: the ID of a song, show, venue, person or release.
- get_song: one song's facts, credits and releases.
- get_song_life: a song's history year by year, with its notable performances.
- get_song_notable_versions: the versions critics, curators and fans picked.
- list_song_performances: every performance of a song, with dates and lengths.
- get_show: one show's setlist, guests and recordings.
- get_performance: one performance, with its sources and recordings.
- get_album: an official release, with its shows or tracks.
- get_segue_pairing: two songs played back to back as one piece, across the
  nights they were played.
- get_grid: a table of two lists, such as a tour's nights against its songs.
- look_up: shows, releases or songs by year, venue or tour.
- aggregate_data: counts and rankings across many shows.
- search_guest_musicians: guest musicians and the shows they played.
- get_recording_reviews: what listeners wrote about a tape.
- search_site and read_page: articles, reviews and interviews on the web.
- read_notebook: results from earlier turns, by the keys or IDs in the research
  notebook.

## PAGE COMPONENTS

- song_versions: several versions of one song, each with a play button, a
  bar for its length on a shared scale and your note on it, and Queue all to
  queue them in order. With criteria, each version also gets your judgment on
  each point, to compare them.
- version_strip: nights of one segue pairing, each playing both songs in turn.
- show_unit, performance_unit, album_unit: a card for one show, performance or
  release.
- song_overview: a card for one song; with by_year, a chart of how often and
  how long it was played each year.
- era_unit: one period of the band or a song, with performances from it.
- data_chart: a bar chart of an aggregate_data result.
- ranked_list: the top rows of an aggregate_data result, with your notes.
- grid: a get_grid result as a table.
- listening_hero: a large player for one show or release at the top of the
  page.
- editorial: your own writing, as a narrative, a timeline or a fact_grid.
- pull_quote: one sentence of yours, set large.
- person_roster, guest_appearance_list, equipment_list, show_selection,
  arrangement, arrangement_search, media_link, resource_list: complete lists.

Groups arrange components as a collection, a sequence, a comparison on shared
criteria, or an argument. Cards take an emphasis (primary, supporting or
mention) and can start collapsed to one line.
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
