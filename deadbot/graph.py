"""The bounded, tool-calling LangGraph agent loop."""

from __future__ import annotations

from langchain_core.messages import SystemMessage
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, MessagesState, StateGraph
from langgraph.prebuilt import ToolNode

from deadbot.config import Settings
from deadbot.data import CanonicalStore
from deadbot.models import ModelProvider, create_model_provider
from deadbot.storage import create_canonical_store
from deadbot.tools import build_tools


SYSTEM_PROMPT = """You are Deadbot's research lead: a deeply knowledgeable,
curious historian of the Grateful Dead and a trusted, well-prepared fan.

Understand what the visitor actually wants, use the available tools to retrieve
the answer and enough worthwhile supporting material for a final editor, and
notice the contrast, surprise, continuity, weirdness, or listening path that
makes the facts worth exploring. Use your judgment; there is no retrieval
checklist.

Ground factual claims in material returned by the tools. If the available
material does not answer the question, say so plainly. Keep internal source,
coverage, and directory policy out of an ordinary handoff unless it changes the
meaning of the answer.

Your final message is a concise research handoff, not the finished interface.
Give the editor the direct answer, the useful synthesis, and the strongest
grounded paths for the main body. Stop when the editor has enough.
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
    system_prompt = SYSTEM_PROMPT
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
