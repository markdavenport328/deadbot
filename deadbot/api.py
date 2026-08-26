"""FastAPI entry point for the Deadbot experience layer."""

from __future__ import annotations

import logging
import os
import uuid
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from langchain_core.messages import AIMessage, HumanMessage

from deadbot.composer import DeterministicComposer, ExperienceComposer, create_experience_composer
from deadbot.config import Settings
from deadbot.data import CanonicalStore, repository_root
from deadbot.experience import ExperienceRequest, ExperienceResponse, compose_experience_response
from deadbot.graph import build_agent, run_config


logger = logging.getLogger(__name__)


def create_app(
    settings: Settings | None = None,
    store: CanonicalStore | None = None,
    agent: Any | None = None,
    composer: ExperienceComposer | None = None,
    client_dist: Path | None = None,
) -> FastAPI:
    """Build an application with injectable runtime dependencies for tests."""

    settings = settings or Settings.from_env()
    store = store or CanonicalStore()
    is_production_runtime = agent is None
    agent = agent or build_agent(settings, store=store)
    # An injected agent is a test/runtime seam. Avoid starting a second model
    # request in that path unless the caller explicitly supplies a composer.
    composer = composer or (create_experience_composer(settings) if is_production_runtime else DeterministicComposer())
    client_dist = client_dist or repository_root() / "web" / "dist"
    app = FastAPI(title="Deadbot", version="0.1.0")
    app.state.settings = settings
    app.state.store = store
    app.state.agent = agent
    app.state.composer = composer

    @app.get("/api/health")
    def health() -> dict[str, str]:
        return {
            "status": "ok",
            "git_commit": os.getenv("VERCEL_GIT_COMMIT_SHA", "unknown"),
            "canonical_shows": str(len(store.rows("shows"))),
            "performer_assignments": str(len(store.rows("show_performers"))),
            "show_equipment_links": str(len(store.rows("show_equipment"))),
        }

    @app.post("/api/experience", response_model=ExperienceResponse)
    def experience(request: ExperienceRequest) -> ExperienceResponse:
        thread_id = request.thread_id or f"web-{uuid.uuid4()}"
        messages = [
            HumanMessage(content=turn.text) if turn.role == "user" else AIMessage(content=turn.text)
            for turn in request.conversation
        ]
        messages.append(HumanMessage(content=request.question.strip()))
        # Vercel may route successive requests to different function instances.
        # When the browser supplies its visible transcript, use an isolated
        # invocation thread so the transcript is authoritative and is not
        # duplicated with a warm instance's MemorySaver checkpoint.
        invocation_thread_id = (
            f"{thread_id}:request:{uuid.uuid4()}" if request.conversation else thread_id
        )
        try:
            result = app.state.agent.invoke(
                {"messages": messages},
                run_config(invocation_thread_id, app.state.settings),
            )
        except Exception as error:  # The browser receives no model/provider internals.
            logger.exception("Deadbot experience request failed")
            raise HTTPException(
                status_code=503,
                detail="Deadbot is temporarily unavailable. Check that the configured model service is running.",
            ) from error
        response = compose_experience_response(
            question=request.question,
            thread_id=thread_id,
            messages=result.get("messages", []),
            store=app.state.store,
        )
        return app.state.composer.compose(request.question, response)

    if client_dist.is_dir():
        assets = client_dist / "assets"
        if assets.is_dir():
            app.mount("/assets", StaticFiles(directory=assets), name="assets")

        @app.get("/{full_path:path}", include_in_schema=False)
        def client(full_path: str) -> FileResponse:
            # The SPA owns browser routes. API routes were registered above.
            return FileResponse(client_dist / "index.html")

    return app


app = create_app()
