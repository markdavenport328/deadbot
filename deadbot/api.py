"""FastAPI entry point for the Deadbot experience layer."""

from __future__ import annotations

import json
import logging
import os
import time
import uuid
from collections import deque
from collections.abc import Iterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from langchain_core.messages import AIMessage, HumanMessage

from deadbot.config import Settings
from deadbot.data import CanonicalStore, repository_root
from deadbot.experience import ExperienceRequest, ExperienceResponse
from deadbot.finish import build_experience_response
from deadbot.graph import build_agent, run_config
from deadbot.progress import status_lines
from deadbot.storage import create_canonical_store


logger = logging.getLogger(__name__)

UNAVAILABLE = "Deadbot is temporarily unavailable. Check that the configured model service is running."


@dataclass(frozen=True)
class _Invocation:
    """One agent run prepared from a browser request."""

    thread_id: str
    invocation_thread_id: str
    messages: list[Any]


def create_app(
    settings: Settings | None = None,
    store: CanonicalStore | None = None,
    agent: Any | None = None,
    client_dist: Path | None = None,
) -> FastAPI:
    """Build an application with injectable runtime dependencies for tests."""

    settings = settings or Settings.from_env()
    store = store or create_canonical_store(settings)
    agent = agent or build_agent(settings, store=store)
    client_dist = client_dist or repository_root() / "web" / "dist"
    close_store = getattr(store, "close", None)

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        try:
            yield
        finally:
            if callable(close_store):
                close_store()

    app = FastAPI(title="Deadbot", version="0.1.0", lifespan=lifespan)
    app.state.settings = settings
    app.state.store = store
    app.state.agent = agent
    # Sliding-window rate-limit state: client IP -> deque of request timestamps
    # within the trailing 60s window. This is per process instance only — on
    # Vercel, separate function instances each keep their own counters, so this
    # is not a real cross-instance limit. A shared store (e.g. Redis) would be
    # needed for that; deferred as a later operational decision.
    app.state.rate_limit_hits = {}

    def _client_ip(http_request: Request) -> str:
        forwarded_for = http_request.headers.get("x-forwarded-for")
        if forwarded_for:
            return forwarded_for.split(",")[0].strip()
        return http_request.client.host if http_request.client else "unknown"

    def _enforce_rate_limit(http_request: Request) -> None:
        limit = app.state.settings.rate_limit_per_minute
        if limit <= 0:
            return
        now = time.monotonic()
        window_start = now - 60
        client_ip = _client_ip(http_request)
        hits = app.state.rate_limit_hits.setdefault(client_ip, deque())
        while hits and hits[0] <= window_start:
            hits.popleft()
        if len(hits) >= limit:
            raise HTTPException(
                status_code=429,
                detail="Too many requests. Please wait a minute and try again.",
            )
        hits.append(now)

    def _trimmed_conversation(conversation: list, window: int) -> list:
        """Return only the most recent `window` turns, dropping the oldest ones.

        Returns a new list; never mutates the request's own conversation list.
        """

        if window <= 0 or len(conversation) <= window:
            return conversation
        return conversation[-window:]

    @app.get("/api/health")
    def health() -> dict[str, str]:
        return {
            "status": "ok",
            "git_commit": os.getenv("VERCEL_GIT_COMMIT_SHA", "unknown"),
            "canonical_shows": str(store.row_count("shows")),
            "performer_assignments": str(store.row_count("show_performers")),
            "show_equipment_links": str(store.row_count("show_equipment")),
        }

    def _prepare(request: ExperienceRequest) -> _Invocation:
        thread_id = request.thread_id or f"web-{uuid.uuid4()}"
        conversation = _trimmed_conversation(request.conversation, app.state.settings.conversation_window)
        messages = [
            HumanMessage(content=turn.text) if turn.role == "user" else AIMessage(content=turn.text)
            for turn in conversation
        ]
        messages.append(HumanMessage(content=request.question.strip()))
        # Vercel may route successive requests to different function instances.
        # When the browser supplies its visible transcript, use an isolated
        # invocation thread so the transcript is authoritative and is not
        # duplicated with a warm instance's MemorySaver checkpoint.
        invocation_thread_id = f"{thread_id}:request:{uuid.uuid4()}" if request.conversation else thread_id
        return _Invocation(thread_id=thread_id, invocation_thread_id=invocation_thread_id, messages=messages)

    def _release(invocation: _Invocation) -> None:
        # The per-request thread is throwaway: it exists only so this
        # invocation replays the browser's transcript in isolation. Without
        # this, MemorySaver would keep its checkpoint forever and leak memory
        # in a long-running `deadbot serve` process. Never delete the stable
        # thread_id path used for warm, server-side follow-ups.
        if invocation.invocation_thread_id != invocation.thread_id:
            checkpointer = getattr(app.state.agent, "checkpointer", None)
            if checkpointer is not None and hasattr(checkpointer, "delete_thread"):
                checkpointer.delete_thread(invocation.invocation_thread_id)

    def _respond(request: ExperienceRequest, invocation: _Invocation, messages: list[Any]) -> ExperienceResponse:
        return build_experience_response(
            question=request.question,
            thread_id=invocation.thread_id,
            messages=messages,
            store=app.state.store,
        )

    @app.post("/api/experience", response_model=ExperienceResponse)
    def experience(request: ExperienceRequest, http_request: Request) -> ExperienceResponse:
        _enforce_rate_limit(http_request)
        invocation = _prepare(request)
        try:
            result = app.state.agent.invoke(
                {"messages": invocation.messages},
                run_config(invocation.invocation_thread_id, app.state.settings),
            )
            # Assembling the response is inside the try so an unexpected raise
            # while resolving the plan reaches the visitor as the same friendly
            # 503 as an agent failure, not as a stack trace.
            return _respond(request, invocation, result.get("messages", []))
        except Exception as error:  # The browser receives no model/provider internals.
            logger.exception("Deadbot experience request failed")
            raise HTTPException(status_code=503, detail=UNAVAILABLE) from error
        finally:
            _release(invocation)

    def _stream_events(request: ExperienceRequest, invocation: _Invocation) -> Iterator[str]:
        """Newline-delimited JSON: status lines while the agent works, then the response.

        LangGraph's ``stream`` with ``stream_mode="values"`` yields the whole
        message list after every step; each new tool call the model makes
        becomes one visitor-facing status. An agent without ``stream`` (the
        test doubles, for one) is invoked whole and yields only the response.
        """

        def line(event: dict[str, Any]) -> str:
            return json.dumps(event, ensure_ascii=False) + "\n"

        try:
            config = run_config(invocation.invocation_thread_id, app.state.settings)
            payload = {"messages": invocation.messages}
            stream = getattr(app.state.agent, "stream", None)
            messages: list[Any] = []
            if callable(stream):
                seen = 0
                for state in stream(payload, config, stream_mode="values"):
                    messages = list(state.get("messages", [])) if isinstance(state, dict) else messages
                    for status in status_lines(messages, seen):
                        yield line({"type": "status", "text": status})
                    seen = len(messages)
            else:
                yield line({"type": "status", "text": "Looking through the library"})
                result = app.state.agent.invoke(payload, config)
                messages = list(result.get("messages", []))
            response = _respond(request, invocation, messages)
            yield line({"type": "response", "response": response.model_dump(mode="json")})
        except Exception:  # The browser receives no model/provider internals.
            logger.exception("Deadbot streamed experience request failed")
            yield line({"type": "error", "detail": UNAVAILABLE})
        finally:
            _release(invocation)

    @app.post("/api/experience/stream")
    def experience_stream(request: ExperienceRequest, http_request: Request) -> StreamingResponse:
        _enforce_rate_limit(http_request)
        invocation = _prepare(request)
        return StreamingResponse(
            _stream_events(request, invocation),
            media_type="application/x-ndjson",
            headers={"Cache-Control": "no-cache, no-store", "X-Accel-Buffering": "no"},
        )

    if client_dist.is_dir():
        assets = client_dist / "assets"
        if assets.is_dir():
            app.mount("/assets", StaticFiles(directory=assets), name="assets")

        @app.get("/{full_path:path}", include_in_schema=False)
        def client(full_path: str) -> FileResponse:
            # The SPA owns browser routes. API routes were registered above.
            # Always revalidate the shell so a production deploy cannot leave a
            # browser loading an older hashed bundle from a cached index page.
            return FileResponse(
                client_dist / "index.html",
                headers={"Cache-Control": "no-cache, no-store, must-revalidate"},
            )

    return app


def __getattr__(name: str) -> Any:
    """Build the production application on first access of ``deadbot.api:app``.

    Importing this module for tests or for the OpenAPI export must not read
    the environment or connect to the database. Uvicorn, the Vercel
    entrypoint, and the ``app`` console script all resolve ``app`` through
    normal attribute access, which reaches this hook once and caches the
    result in the module namespace.
    """

    if name == "app":
        application = create_app()
        globals()["app"] = application
        return application
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
