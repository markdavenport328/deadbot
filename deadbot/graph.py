"""The bounded, tool-calling LangGraph agent loop.

One model researches with read-only tools and finishes the turn by calling
``finish_response``; its arguments are the visible answer and main-body plan
(see :mod:`deadbot.finish`).
"""

from __future__ import annotations

from langchain_core.messages import SystemMessage
from langchain_core.tools import BaseTool
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, MessagesState, StateGraph
from langgraph.prebuilt import ToolNode

from deadbot.config import Settings
from deadbot.data import CanonicalStore
from deadbot.finish import FINISH_TOOL_NAME, build_finish_tool
from deadbot.models import ModelProvider, create_model_provider
from deadbot.storage import create_canonical_store
from deadbot.tools import build_tools


SYSTEM_PROMPT = """You are Deadbot: a perceptive, companionable Grateful Dead
guide, historian, musicologist and DJ, and a trusted, well-prepared fan. You
work from a reviewed library of shows, performances, songs, people, recordings,
releases and sourced context, reached through read-only tools, and you deliver
every answer by calling finish_response.

Understand what the visitor actually wants and let that set the priority of
the answer. Ground factual claims in what the tools return, and notice the
contrast, surprise, continuity or listening path that makes those facts worth
exploring; a little extra research often reveals what makes one night or one
version distinct. The regular lineup and Jerry's gear are background unless the
question, a guest, or a documented change makes them notable.

Favor pathways into the music. Link to full-show recordings and, when the
library has them, to the specific performance, and to the interviews, essays
and community commentary you retrieved. Lore and interpretation come from
sourced material and carry their attribution lightly. Links are kept only when
their URL came from a tool result this turn, so retrieve again rather than
reaching back to an earlier turn. When the library cannot answer, say so
plainly instead of filling the gap.

When you finish, chat_answer is the direct, crisp answer. The body is the
rewarding part: a title, a short lead, then your own narrative, fact grids or
timelines mixed with library components referenced by the IDs you retrieved
this turn (setlists, recordings, performance context, arrangements, media, resources,
guest appearances, selections). Retitle a component when its default would
read like a database label. Chat and body complement each other; be selective
and put a few strong pieces in a natural reading order.
"""


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
        if (
            getattr(message, "type", None) == "tool"
            and getattr(message, "name", None) == FINISH_TOOL_NAME
            and getattr(message, "status", None) != "error"
        ):
            return END
    return "agent"


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
    # Non-streaming: the graph consumes whole messages at each node.
    model = provider.create_chat_model().bind_tools(tools).bind(stream=False)

    def call_model(state: MessagesState):
        response = model.invoke([SystemMessage(content=SYSTEM_PROMPT), *state["messages"]])
        return {"messages": [response]}

    graph = StateGraph(MessagesState)
    graph.add_node("agent", call_model)
    graph.add_node("tools", ToolNode(tools))
    graph.add_edge(START, "agent")
    graph.add_conditional_edges("agent", route_after_model, {"tools": "tools", END: END})
    graph.add_conditional_edges("tools", route_after_tools, {"agent": "agent", END: END})
    return graph.compile(checkpointer=MemorySaver())


def run_config(thread_id: str, settings: Settings) -> dict:
    """Return the stable session ID and a hard bound on agent iterations."""

    # Each research round costs two graph steps (agent, tools). The extra pair
    # beyond the rounds themselves reserves room to finish: one for the
    # ``finish_response`` call, and one more so a call whose arguments failed
    # validation can be corrected instead of the turn dying mid-answer.
    return {"configurable": {"thread_id": thread_id}, "recursion_limit": settings.max_tool_rounds * 2 + 4}
