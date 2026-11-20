"""FastAPI entry point for the Deadbot experience layer."""

from __future__ import annotations

import json
import logging
import os
import time
import uuid
from collections.abc import Iterator
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from langchain_core.messages import AIMessage, HumanMessage

from deadbot import composition, finish, grids, limits, notebook, row_details
from deadbot.lead_stream import LeadAccumulator
from deadbot.config import Settings
from deadbot.data import CanonicalStore, repository_root
from deadbot.experience import AskFocus, ExperienceRequest, ExperienceResponse, GridBlock, GridRequest, RowDetail, SongYearDetail, fit
from deadbot.finish import FINISH_TOOL_NAME, FOCUS_MESSAGE_NAME, build_experience_response
from deadbot.graph import TurnBudgetExceeded, build_agent, run_config
from deadbot.plan_stream import PlanStreamer
from deadbot.sqlite_store import query_cache_scope
from deadbot.song_life import year_detail
from deadbot.progress import describe_tool_call, status_lines
from deadbot.response_cache import ResponseCache
from deadbot.storage import create_canonical_store
from deadbot.turn_metrics import turn_metrics


logger = logging.getLogger(__name__)

metrics_logger = logging.getLogger("deadbot.turn_metrics")
metrics_logger.setLevel(logging.INFO)
metrics_logger.propagate = False
if not metrics_logger.handlers:
    metrics_logger.addHandler(logging.StreamHandler())

# Ceilings far above what a model writes; a longer text is cut and logged, never refused.
GRID_TITLE_CEILING = 1_000
GRID_TEXT_CEILING = 10_000


def _trim_text(text: str | None, ceiling: int, what: str) -> str | None:
    if text is not None and len(text) > ceiling:
        logger.warning("Truncated a %d-character %s to the ceiling of %d", len(text), what, ceiling)
        return text[:ceiling]
    return text


# The tables a clicked cell's IDs can name, tried in order.
FOCUS_TABLES = ("shows", "performances", "songs", "people", "venues", "official_releases")

# Where the visitor asked from, in the note's words.
FOCUS_PLACES = {
    "grid": "a grid",
    "song_overview": "a song's timeline",
    "data_chart": "a row they opened on a chart",
    "ranked_list": "a row they opened in a ranked list",
    "person_roster": "a name they opened in a roster",
}


def focus_ids(store: Any, focus: AskFocus | None) -> set[str]:
    """The IDs a visitor's click named that the library holds.

    These join the turn's grounded IDs, so the model can place a card for the
    clicked night without looking it up again. An ID the library does not hold
    is dropped; hydration still reads every fact from the store.
    """

    found: set[str] = set()
    for entity_id in focus.ids if focus else []:
        for table in FOCUS_TABLES:
            try:
                if store.one(table, entity_id):
                    found.add(entity_id)
                    break
            except Exception:
                logger.debug("Could not look up focus id %r in %s", entity_id, table, exc_info=True)
        else:
            logger.debug("Dropped focus id %r: the library holds no such record", entity_id)
    return found


def _one_line(text: str) -> str:
    """The browser's words on a single line, so a label or fact cannot add lines to the note."""

    return " ".join(str(text).split())


def focus_note(focus: AskFocus, known_ids: set[str]) -> str:
    """What was clicked, written for the model; it decides whether to research further.

    The label and facts are what the page showed, as the browser reported
    them; only the library IDs are checked against the store.
    """

    place = FOCUS_PLACES.get(focus.block_type, "the page")
    lines = [f'The visitor asked from {place} on the page ("{_one_line(focus.label)}").']
    facts = [fact for fact in (_one_line(fact) for fact in focus.facts) if fact]
    if facts:
        lines.append(f"Facts as the page showed them: {' '.join(facts)}")
    ids = [entity_id for entity_id in focus.ids if entity_id in known_ids]
    if ids:
        lines.append(f"Library IDs: {', '.join(ids)}")
    return "\n".join(lines)


UNAVAILABLE = "Deadbot is temporarily unavailable. Check that the configured model service is running."
TOOK_TOO_LONG = "That one took longer than Deadbot has for a single answer. Please ask again, or ask about something narrower."

# The platform's own headers for the visitor's address, read only when the
# deployment says a proxy that overwrites them is in front (see _client_ip).
FORWARDED_ADDRESS_HEADERS = ("x-vercel-forwarded-for", "x-forwarded-for")


def _names_finish_call(message_chunk: Any) -> bool:
    return any(chunk.get("name") == FINISH_TOOL_NAME for chunk in getattr(message_chunk, "tool_call_chunks", None) or [])


@dataclass(frozen=True)
class _Invocation:
    """One agent run prepared from a browser request."""

    thread_id: str
    invocation_thread_id: str
    messages: list[Any]
    focus_ids: frozenset[str] = frozenset()
    notebook: notebook.Notebook = field(default_factory=notebook.Notebook)


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
    # Usage windows live in this process's memory: on Vercel each function
    # instance keeps its own, and there is no shared store. The signed
    # allowance cookie carries a visitor's count between instances
    # (deadbot/limits.py says what that does and does not cover).
    app.state.limits = limits.Limits(settings)
    app.state.response_cache = ResponseCache(
        store,
        enabled=settings.response_cache,
        max_age_seconds=settings.response_cache_ttl_seconds,
    )

    def _client_ip(http_request: Request) -> str:
        """The visitor's address, from a header only where the platform vouches for it.

        Vercel overwrites the forwarded headers with the public address of the
        client, so a value sent by the client never reaches the function. Off
        Vercel nothing overwrites them, any client can write them, and reading
        them would let a script change its address on every request; there the
        address of the connection is used.
        """

        if app.state.settings.trust_forwarded_ip:
            for header in FORWARDED_ADDRESS_HEADERS:
                forwarded = http_request.headers.get(header)
                if forwarded and forwarded.strip():
                    return forwarded.split(",")[0].strip()
        return http_request.client.host if http_request.client else "unknown"

    def _too_many(reached: limits.LimitReached, headers: dict[str, str] | None = None) -> HTTPException:
        # The web client shows an error body's "detail" to the visitor as it is.
        return HTTPException(
            status_code=429,
            detail=reached.message,
            headers={**(headers or {}), "Retry-After": str(reached.retry_after)},
        )

    def _count_lookup(http_request: Request) -> None:
        """One cheap library read against this address's per-minute lookup budget."""

        try:
            app.state.limits.lookup(_client_ip(http_request))
        except limits.LimitReached as reached:
            raise _too_many(reached) from None

    def _admit(request: ExperienceRequest, http_request: Request, thread_id: str) -> tuple[ExperienceResponse | None, dict[str, str]]:
        """A stored answer, or leave to ask the model and the cookie that records it.

        A stored answer costs no model call, so it spends the lookup budget and
        leaves the visitor's question allowance alone. Anything else is counted
        before the model is called; over a limit it is refused with a 429.
        """

        with query_cache_scope():
            cached = _cached(request, thread_id)
        if cached is not None:
            _count_lookup(http_request)
            return cached, {}
        try:
            token = app.state.limits.admit(_client_ip(http_request), http_request.cookies.get(limits.COOKIE_NAME))
        except limits.LimitReached as reached:
            raise _too_many(reached) from None
        if token is None:
            return None, {}
        secure = http_request.url.scheme == "https" or http_request.headers.get("x-forwarded-proto") == "https"
        return None, {"Set-Cookie": limits.cookie_header(token, secure=secure)}

    def _bounded_conversation(conversation: list) -> list:
        """The most recent turns that fit the turn window and the character budget.

        The browser sends the transcript and nothing vouches for it, so its
        size is bounded here: the oldest turns are dropped and the drop is
        logged; the turns that remain are sent whole. Returns a new list.
        """

        window = app.state.settings.conversation_window
        kept = list(conversation[-window:]) if window > 0 else list(conversation)
        budget = app.state.settings.conversation_max_chars
        if budget > 0:
            total = sum(len(turn.text) for turn in kept)
            dropped = 0
            while kept and (total > budget or (dropped and kept[0].role == "assistant")):
                # Past the budget, and then on to the next question, so the
                # transcript never opens on an answer whose question is gone.
                total -= len(kept.pop(0).text)
                dropped += 1
            if dropped:
                logger.warning("Dropped the %d oldest conversation turns to fit %d characters", dropped, budget)
        return kept

    @app.get("/api/version")
    def version() -> dict[str, str]:
        # Open tabs ask this when they come back into view, to reload after a
        # deploy. It must stay free: no store queries, so an idle tab never
        # keeps a function (or a database) busy.
        return {"git_commit": os.getenv("VERCEL_GIT_COMMIT_SHA", "unknown")}

    @app.get("/api/health")
    def health() -> dict[str, str]:
        return {
            "status": "ok",
            "git_commit": os.getenv("VERCEL_GIT_COMMIT_SHA", "unknown"),
            "canonical_shows": str(store.row_count("shows")),
            "performer_assignments": str(store.row_count("show_performers")),
            "show_equipment_links": str(store.row_count("show_equipment")),
        }

    def _thread_id(request: ExperienceRequest) -> str:
        return request.thread_id or f"web-{uuid.uuid4()}"

    def _prepare(request: ExperienceRequest, thread_id: str) -> _Invocation:
        book = notebook.decode(request.notebook, app.state.settings.notebook_secret)
        conversation = _bounded_conversation(request.conversation)
        # Each earlier turn's notebook lines sit right after that turn's
        # answer, so a new turn only appends and the provider's prompt cache
        # keeps everything before the new question.
        messages = notebook.transcript_with_notebook(book, conversation)
        if request.focus is not None:
            # Research already done on what the visitor clicked, in a message of
            # its own before the question (the grid's note of the click follows it).
            flags = notebook.render_flags(notebook.entries_mentioning(book, request.focus.ids))
            if flags:
                messages.append(notebook.notebook_message(flags))
        messages.append(HumanMessage(content=request.question.strip()))
        grounded_focus = focus_ids(app.state.store, request.focus)
        if request.focus is not None:
            # A note of its own after the question: the visitor's transcript
            # holds only what they typed, and the model reads what they clicked.
            messages.append(HumanMessage(content=focus_note(request.focus, grounded_focus), name=FOCUS_MESSAGE_NAME))
        # Vercel may route successive requests to different function instances,
        # so the browser's transcript is the conversation. Every request runs
        # on a throwaway thread of its own: the transcript is authoritative
        # and is never doubled with a warm instance's MemorySaver checkpoint.
        # A kept checkpoint would also let a client that repeats a thread_id
        # without a transcript grow one turn's input by every earlier turn's
        # tool results, which no size limit on the request could bound.
        invocation_thread_id = f"{thread_id}:request:{uuid.uuid4()}"
        return _Invocation(
            thread_id=thread_id,
            invocation_thread_id=invocation_thread_id,
            messages=messages,
            focus_ids=frozenset(grounded_focus),
            notebook=book,
        )

    def _deadline(started: float) -> float | None:
        """When this turn must stop, so it ends with an honest error before the platform cuts it off."""

        budget = app.state.settings.turn_budget_seconds
        return started + budget if budget > 0 else None

    def _run_config(invocation: _Invocation, started: float) -> dict:
        return run_config(
            invocation.invocation_thread_id,
            app.state.settings,
            notebook=invocation.notebook,
            # The conversation, not this request's throwaway thread, picks the
            # provider cache key, so a conversation's calls stay on one key.
            conversation_id=invocation.thread_id,
            deadline=_deadline(started),
        )

    def _turn_grounding(invocation: _Invocation) -> finish.GroundedContext:
        """IDs and URLs this turn may use beyond its own tool results: the notebook and what was clicked."""

        ids, urls = notebook.grounding(invocation.notebook)
        return finish.GroundedContext(ids=frozenset(ids) | invocation.focus_ids, urls=frozenset(urls))

    def _release(invocation: _Invocation) -> None:
        # The per-request thread is throwaway: it exists only so this
        # invocation replays the browser's transcript in isolation. Without
        # this, MemorySaver would keep its checkpoint forever and leak memory
        # in a warm function instance or a long-running `deadbot serve`.
        checkpointer = getattr(app.state.agent, "checkpointer", None)
        if checkpointer is not None and hasattr(checkpointer, "delete_thread"):
            checkpointer.delete_thread(invocation.invocation_thread_id)

    def _with_notebook(invocation: _Invocation, messages: list[Any], response: ExperienceResponse) -> ExperienceResponse:
        """The response plus the signed notebook the browser sends back with the next question."""

        secret = app.state.settings.notebook_secret
        if not secret:
            notebook.note_missing_secret()
            return response
        try:
            book = notebook.record_turn(invocation.notebook, composition._latest_turn(list(messages)), response)
            token = notebook.encode(book, secret)
        except Exception:  # The answer matters more than its notebook.
            logger.exception("The research notebook could not be saved; the answer goes out without it")
            return response
        return response.model_copy(update={"notebook": token})

    def _respond(request: ExperienceRequest, invocation: _Invocation, messages: list[Any]) -> ExperienceResponse:
        response = build_experience_response(
            question=request.question,
            thread_id=invocation.thread_id,
            messages=messages,
            store=app.state.store,
            extra_grounding=_turn_grounding(invocation),
        )
        return _with_notebook(invocation, messages, response)

    def _cached(request: ExperienceRequest, thread_id: str) -> ExperienceResponse | None:
        """A stored answer for a fresh (no-conversation) repeat of a question."""

        # A focused ask depends on what was clicked, which the cache key (the
        # question text) does not capture. A notebook marks a follow-up in a
        # session: its answer may lean on earlier research.
        if request.conversation or request.focus is not None or request.notebook:
            return None
        return app.state.response_cache.lookup(request.question, thread_id=thread_id)

    def _remember(request: ExperienceRequest, response: ExperienceResponse) -> None:
        if not request.conversation and request.focus is None and not request.notebook:
            app.state.response_cache.remember(request.question, response)

    @app.post("/api/experience", response_model=ExperienceResponse)
    def experience(request: ExperienceRequest, http_request: Request, http_response: Response) -> ExperienceResponse:
        started = time.monotonic()
        thread_id = _thread_id(request)
        cached, headers = _admit(request, http_request, thread_id)
        if cached is not None:
            return cached
        http_response.headers.update(headers)
        invocation = _prepare(request, thread_id)
        try:
            with query_cache_scope():
                result = app.state.agent.invoke(
                    {"messages": invocation.messages},
                    _run_config(invocation, started),
                )
                # Assembling the response is inside the try so an unexpected raise
                # while resolving the plan reaches the visitor as the same friendly
                # 503 as an agent failure, not as a stack trace.
                response = _respond(request, invocation, result.get("messages", []))
                _remember(request, response)
                return response
        except TurnBudgetExceeded as error:
            logger.warning("Deadbot experience request ran out of time: %s", error)
            raise HTTPException(status_code=504, detail=TOOK_TOO_LONG, headers=headers) from error
        except Exception as error:  # The browser receives no model/provider internals.
            logger.exception("Deadbot experience request failed")
            raise HTTPException(status_code=503, detail=UNAVAILABLE, headers=headers) from error
        finally:
            _release(invocation)

    def _line(event: dict[str, Any]) -> str:
        # A lone surrogate that slipped through the model's JSON (see
        # extract_lead) cannot be UTF-8 encoded; Starlette encodes
        # this text outside any try/except of ours, so it is made safe
        # here rather than letting that raise and kill the stream.
        serialized = json.dumps(event, ensure_ascii=False)
        return serialized.encode("utf-8", "replace").decode("utf-8") + "\n"

    def _stream_cached(cached: ExperienceResponse) -> Iterator[str]:
        yield _line({"type": "status", "text": "Found a recent answer"})
        yield _line({"type": "response", "response": cached.model_dump(mode="json")})

    def _stream_events(request: ExperienceRequest, invocation: _Invocation, started: float) -> Iterator[str]:
        """Newline-delimited JSON: status lines while the agent works, then the response.

        LangGraph's ``stream`` with ``stream_mode=["values", "messages"]``
        yields ``(mode, payload)`` tuples: a ``values`` payload is the whole
        message list after each step, from which each new tool call the
        model makes becomes one visitor-facing status; a ``messages``
        payload is one ``(AIMessageChunk, metadata)`` pair from the model's
        own token stream, from which an ``LeadAccumulator`` pulls the
        growing ``lead`` text out of the ``finish_response`` call's
        arguments as it is generated, so the visible answer can reach the
        browser before the rest of the plan finishes. An agent whose
        ``stream`` ignores the mode list and yields plain state dicts (the
        test doubles, for one) is handled the same way ``values`` always
        was. An agent without ``stream`` at all is invoked whole and yields
        only the response.
        """

        line = _line
        first_lead_at: float | None = None
        error: str | None = None
        messages: list[Any] = []
        config: dict = {}
        try:
            config = _run_config(invocation, started)
            payload = {"messages": invocation.messages}
            stream = getattr(app.state.agent, "stream", None)
            # One query cache for the whole request. Each step of this
            # generator may resume in a fresh context copy, so the same dict
            # is re-entered around every graph step and the final resolution.
            cache: dict = {}
            if callable(stream):
                seen = 0
                lead_accumulator = LeadAccumulator()
                composing_page_announced = False
                plan_streamer: PlanStreamer | None = None
                plan_streaming_off = False
                steps = iter(stream(payload, config, stream_mode=["values", "messages"]))
                while True:
                    with query_cache_scope(cache):
                        item = next(steps, None)
                    if item is None:
                        break
                    if isinstance(item, tuple) and len(item) == 2 and item[0] in ("values", "messages"):
                        mode, chunk_payload = item
                    else:
                        mode, chunk_payload = "values", item
                    if mode == "messages":
                        message_chunk = chunk_payload[0] if isinstance(chunk_payload, tuple) else chunk_payload
                        lead_text = lead_accumulator.feed(message_chunk)
                        if lead_text:
                            first_lead_at = first_lead_at or time.monotonic()
                            yield line({"type": "lead", "text": lead_text})
                        if lead_accumulator.complete and not composing_page_announced:
                            composing_page_announced = True
                            yield line({"type": "status", "text": "Composing the page"})
                        if plan_streamer is None and not plan_streaming_off and _names_finish_call(message_chunk):
                            try:
                                # Research is done by the time the plan starts; ground once.
                                payloads = composition._tool_payloads(composition._latest_turn(messages))
                                grounded = finish.merge_grounding(finish.grounded_context(payloads), _turn_grounding(invocation))
                                plan_streamer = PlanStreamer(
                                    lambda items, _g=grounded, _p=payloads: finish.resolve_items(items, _g, _p, app.state.store)[0],
                                    grounded_urls=grounded.urls,
                                )
                            except Exception:
                                logger.exception("Progressive page streaming disabled for this turn")
                                plan_streaming_off = True
                        if plan_streamer is not None:
                            with query_cache_scope(cache):
                                page_events = plan_streamer.feed(message_chunk)
                            for event in page_events:
                                # The fresh accumulator's partial answer (below) is yielded
                                # before the page_reset event; this ordering is harmless only
                                # because the browser's page_reset handling clears the draft
                                # page, not the lead already on screen.
                                if event.type == "page_reset":
                                    # The model is retrying finish_response; the previous
                                    # draft's answer text is void, so the fresh accumulator
                                    # must still see the current chunk's own answer text.
                                    # The visitor sees the draft vanish, so say why.
                                    yield line({"type": "status", "text": "Starting the page over"})
                                    lead_accumulator = LeadAccumulator()
                                    reset_lead = lead_accumulator.feed(message_chunk)
                                    if reset_lead:
                                        first_lead_at = first_lead_at or time.monotonic()
                                        yield line({"type": "lead", "text": reset_lead})
                                yield line({"type": event.type, **event.payload})
                        continue
                    state = chunk_payload
                    messages = list(state.get("messages", [])) if isinstance(state, dict) else messages
                    for status in status_lines(messages, seen):
                        # Once the messages-mode stream has already told the visitor
                        # the page is being composed, the values-mode status for the
                        # same finish_response tool call becoming visible would just
                        # repeat that announcement.
                        if composing_page_announced and status == describe_tool_call(FINISH_TOOL_NAME, None):
                            continue
                        yield line({"type": "status", "text": status})
                    seen = len(messages)
            else:
                yield line({"type": "status", "text": "Looking through the library"})
                with query_cache_scope(cache):
                    result = app.state.agent.invoke(payload, config)
                messages = list(result.get("messages", []))
            with query_cache_scope(cache):
                response = _respond(request, invocation, messages)
                _remember(request, response)
            yield line({"type": "response", "response": response.model_dump(mode="json")})
        except TurnBudgetExceeded as exceeded:
            # Said plainly while the function can still say it; the platform
            # would otherwise drop the connection a few seconds later.
            logger.warning("Deadbot streamed experience request ran out of time: %s", exceeded)
            error = "turn budget exceeded"
            yield line({"type": "error", "detail": TOOK_TOO_LONG})
        except Exception:  # The browser receives no model/provider internals.
            logger.exception("Deadbot streamed experience request failed")
            error = "stream failed"
            yield line({"type": "error", "detail": UNAVAILABLE})
        finally:
            try:
                metrics_logger.info(json.dumps(turn_metrics(
                    request.question, messages, started=started,
                    first_answer_at=first_lead_at, finished_at=time.monotonic(), error=error,
                    prompt_cache_key=(config.get("configurable") or {}).get("prompt_cache_key"),
                    earlier_turns=sum(1 for turn in request.conversation if turn.role == "user"),
                )))
            except Exception:
                logger.exception("Turn metrics failed")
            _release(invocation)

    @app.post("/api/experience/stream")
    def experience_stream(request: ExperienceRequest, http_request: Request) -> StreamingResponse:
        started = time.monotonic()
        thread_id = _thread_id(request)
        cached, headers = _admit(request, http_request, thread_id)
        events = _stream_cached(cached) if cached is not None else _stream_events(request, _prepare(request, thread_id), started)
        return StreamingResponse(
            events,
            media_type="application/x-ndjson",
            headers={"Cache-Control": "no-cache, no-store", "X-Accel-Buffering": "no", **headers},
        )

    @app.post("/api/grid", response_model=GridBlock)
    def reshape_grid(request: GridRequest, http_request: Request) -> GridBlock:
        """Rebuild a grid from the library after the visitor adds or removes a list.

        The model's headline, note, cell notes and follow-up chips come back
        with it; a note whose cell is gone drops away.
        """

        _count_lookup(http_request)
        spec = grids.GridSpec.from_json(request.spec.model_dump())
        if spec is None:
            raise HTTPException(status_code=422, detail="That pair of lists is not one the library can draw.")
        block = grids.grid_block(
            app.state.store,
            # grid_block builds the data itself; it needs only the spec and its id.
            {"spec": spec.to_json(), "grid_id": grids.grid_id(spec)},
            row_ids=None,
            open_rows=request.open_rows,
            highlights=[h.model_dump() for h in fit(request.highlights, "grid highlights")],
            title=_trim_text(request.title, GRID_TITLE_CEILING, "grid title"),
            note=_trim_text(request.note, GRID_TEXT_CEILING, "grid note"),
            follow_ups=fit(request.follow_ups, "grid follow-ups"),
        )
        if block is None:
            raise HTTPException(status_code=404, detail="The library has nothing to draw for those lists.")
        return block

    @app.get("/api/songs/{song_id}/years/{year}", response_model=SongYearDetail)
    def song_year(song_id: str, year: int, http_request: Request, response: Response) -> SongYearDetail:
        """One song's performances in one year for the timeline's See all; library facts only, no model call.

        It shares the grid's lookup limit. Library facts change only with a
        deploy, so the browser and any cache may keep the answer for an hour.
        """

        _count_lookup(http_request)
        detail = year_detail(app.state.store, song_id, year)
        if detail is None:
            raise HTTPException(status_code=404, detail="The library has no such song.")
        response.headers["Cache-Control"] = "public, max-age=3600"
        return SongYearDetail.model_validate(detail)

    @app.get("/api/rows/{row_id}", response_model=RowDetail)
    def row_detail(row_id: str, http_request: Request, response: Response, scope: str | None = None) -> RowDetail:
        """What a ranked row, chart bar or roster name opens to; library facts only, no model call.

        ``scope`` is the song a year chart counts, so its years open to that
        song's year. It shares the grid's lookup limit and, like a song's
        year, may be cached for an hour.
        """

        _count_lookup(http_request)
        if len(row_id) > 200 or (scope and len(scope) > 200):
            raise HTTPException(status_code=404, detail="The library has no such record.")
        detail = row_details.row_detail(app.state.store, row_id, scope)
        if detail is None:
            raise HTTPException(status_code=404, detail="The library has no such record.")
        response.headers["Cache-Control"] = "public, max-age=3600"
        return detail

    if client_dist.is_dir():
        assets = client_dist / "assets"
        if assets.is_dir():
            app.mount("/assets", StaticFiles(directory=assets), name="assets")
        # Self-hosted fonts are copied verbatim from web/public/fonts, so they
        # are not under /assets; without this mount the SPA catch-all below
        # would answer /fonts/*.woff2 with index.html and the browser would
        # fall back to system fonts.
        fonts = client_dist / "fonts"
        if fonts.is_dir():
            app.mount("/fonts", StaticFiles(directory=fonts), name="fonts")
        # The home-screen icons, the web app manifest and the service worker
        # are copied from web/public too. The worker must be served from the
        # root so it can serve the whole site, and always revalidated so a
        # deploy's new worker is picked up.
        icons = client_dist / "icons"
        if icons.is_dir():
            app.mount("/icons", StaticFiles(directory=icons), name="icons")
        root_files = {
            "sw.js": ("text/javascript", "no-cache"),
            "manifest.webmanifest": ("application/manifest+json", "public, max-age=3600"),
        }
        for file_name, (media_type, cache_control) in root_files.items():
            if (client_dist / file_name).is_file():

                def serve(file_name: str = file_name, media_type: str = media_type, cache_control: str = cache_control) -> FileResponse:
                    return FileResponse(client_dist / file_name, media_type=media_type, headers={"Cache-Control": cache_control})

                app.add_api_route(f"/{file_name}", serve, methods=["GET"], include_in_schema=False)

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
