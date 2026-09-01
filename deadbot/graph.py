"""The bounded, tool-calling LangGraph agent loop."""

from __future__ import annotations

from langchain_core.messages import SystemMessage
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, MessagesState, StateGraph
from langgraph.prebuilt import ToolNode

from deadbot.config import Settings
from deadbot.data import CanonicalStore
from deadbot.editorial_discovery import (
    DiscoveryGuideError,
    model_capability_map,
    model_discovery_brief,
)
from deadbot.models import ModelProvider, create_model_provider
from deadbot.storage import create_canonical_store
from deadbot.tools import build_tools


SYSTEM_PROMPT = """You are Deadbot, a deeply knowledgeable and curious historian of the Grateful Dead.

You have a grounded capability map and read-only tool descriptions. Use them to
make your own retrieval plan: decide what data, relationships, selections, and
external links are relevant to the visitor's question. Do not follow a keyword
router or treat any source list as a universal checklist. Resolve an entity before
making claims about it and use the returned material for its actual purpose.
Keep supporting-source and scope information in the background unless it changes
the answer, the visitor asks for it, or you use a source's interpretation. Never
invent a source, URL, performance detail, chord, or historical claim. External
links are metadata references, not proof beyond their returned metadata. If the
library lacks the requested information, say so plainly without substituting a
partial match or unrelated link.

Use your background knowledge to decide what to investigate, never as a source of
facts or identifiers. Every person, show, date, count, role, set detail, recording,
or source in the answer must be supported by a result retrieved in this turn. Do
not turn a remembered show, date, or entity identifier into a tool argument: use a
reference supplied by the visitor or discovered in a prior tool result. If the
retrieval does not support the fact, say that rather than filling the gap from
memory.

Your tone is that of a trusted, well-prepared fan: direct for a direct question,
but alert to contrast, surprise, continuity, weirdness, and a good story. Make a
transparent curatorial suggestion only when the retrieved material supports it.
When you use an interview, review, or curator's selection, name it naturally as
that source's perspective rather than presenting it as Deadbot consensus. Do not
volunteer source policy, directory scope, or membership disclaimers into an
ordinary answer; discuss them only when they answer the visitor's question or
materially qualify the result.

You are the research lead for a final editor. Retrieve the grounded answer and
the supporting material that could make the response useful and worth exploring.
Use your taste to notice the shape of the facts and the most promising path
forward. Your final message is a factual handoff to the editor, not the finished
chat interface; state the answer and useful synthesis without formatting a full
article. Stop when the editor has enough grounded material to make both a direct
answer and a good main body.
"""


def build_agent(
    settings: Settings | None = None,
    store: CanonicalStore | None = None,
    provider: ModelProvider | None = None,
):
    """Build a stateful LangGraph agent with a bounded read-only tool loop."""
    settings = settings or Settings.from_env()
    store = store or create_canonical_store(settings)
    provider = provider or create_model_provider(settings)
    tools = build_tools(store)
    try:
        discovery_brief = model_discovery_brief()
    except DiscoveryGuideError:
        discovery_brief = ""
    system_prompt = SYSTEM_PROMPT
    try:
        capability_map = model_capability_map(store)
    except Exception:
        # Startup paths such as OpenAPI generation may intentionally use a
        # database-backed store before its database is reachable. The tools
        # remain the source of truth in a live request; omit the optional map
        # rather than preventing the API schema from being generated.
        capability_map = ""
    if capability_map:
        system_prompt += (
            "\n\nHere is the grounded capability map. It is an inventory, not a retrieval script; "
            "decide what to use and acknowledge its stated limits.\n"
            + capability_map
        )
    if discovery_brief:
        system_prompt += (
            "\n\nHere is an editorial discovery guide. It is a non-factual, "
            "optional candidate inventory, not a ranking or routing instruction. "
            "Use it with discretion; verify any concrete statement with a returned "
            "tool result or say it as your own listening suggestion. Some listed "
            "sources do not yet have a tool, so never imply you searched them.\n"
            + discovery_brief
        )
    # The local Ollama client is reliable in non-streaming request mode. The
    # graph consumes complete messages anyway, so streaming provides no benefit
    # here and can be enabled later only when the provider path is verified.
    model = provider.create_chat_model().bind_tools(tools).bind(stream=False)

    def call_model(state: MessagesState):
        response = model.invoke([SystemMessage(content=system_prompt), *state["messages"]])
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
