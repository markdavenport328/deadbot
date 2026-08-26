"""The bounded, tool-calling LangGraph agent loop."""

from __future__ import annotations

from langchain_core.messages import SystemMessage
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, MessagesState, StateGraph
from langgraph.prebuilt import ToolNode

from deadbot.config import Settings
from deadbot.data import CanonicalStore
from deadbot.models import ModelProvider, create_model_provider
from deadbot.tools import build_tools


SYSTEM_PROMPT = """You are Deadbot, a provenance-aware Grateful Dead knowledge assistant.

Use the provided read-only tools for factual questions about the canonical library.
Resolve an entity before making claims about it. Cite source names and URLs returned
by a tool whenever you use contextual material. Clearly distinguish canonical data
from an interview, oral history, eyewitness memoir, or editorial interpretation.
Never invent a source, URL, performance detail, chord, or historical claim. External
links are references, not proof beyond their recorded metadata. If the library lacks
the requested information, say so plainly. In particular, if a named song, person,
or performance is not returned by entity search or lookup, do not substitute a
different partial match (such as its show or venue), summarize that match, or attach
unrelated links. Say the named entity is not in the current library and, only if
useful, state the narrowest relevant library boundary.

For questions about what was happening around a show's date, use the show's canonical ID or date with the historical-weather, astronomy, and astrology tools as appropriate. Cite the external source URLs they return. Describe historical weather as nearby-grid-cell reanalysis rather than a precise station observation. Treat astrology only as explicitly labeled cultural/interpretive context; never present it as scientific evidence or as a cause of the music or events.
"""


def build_agent(
    settings: Settings | None = None,
    store: CanonicalStore | None = None,
    provider: ModelProvider | None = None,
):
    """Build a stateful LangGraph agent with a bounded read-only tool loop."""
    settings = settings or Settings.from_env()
    store = store or CanonicalStore()
    provider = provider or create_model_provider(settings)
    tools = build_tools(store)
    # The local Ollama client is reliable in non-streaming request mode. The
    # graph consumes complete messages anyway, so streaming provides no benefit
    # here and can be enabled later only when the provider path is verified.
    model = provider.create_chat_model().bind_tools(tools).bind(stream=False)

    def call_model(state: MessagesState):
        response = model.invoke([SystemMessage(content=SYSTEM_PROMPT), *state["messages"]])
        return {"messages": [response]}

    def route_after_model(state: MessagesState) -> str:
        last_message = state["messages"][-1]
        return "tools" if getattr(last_message, "tool_calls", None) else END

    graph = StateGraph(MessagesState)
    graph.add_node("agent", call_model)
    graph.add_node("tools", ToolNode(tools))
    graph.add_edge(START, "agent")
    graph.add_conditional_edges("agent", route_after_model, {"tools": "tools", END: END})
    graph.add_edge("tools", "agent")
    return graph.compile(checkpointer=MemorySaver())


def run_config(thread_id: str, settings: Settings) -> dict:
    """Return the stable session ID and a hard bound on agent iterations."""
    return {"configurable": {"thread_id": thread_id}, "recursion_limit": settings.max_tool_rounds * 2 + 2}
