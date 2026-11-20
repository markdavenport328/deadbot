"""Small local terminal interface for the first Deadbot agent."""

from __future__ import annotations

import argparse
import json
import sys
import uuid
from pathlib import Path

from langchain_core.messages import HumanMessage

from deadbot.config import Settings
from deadbot.evaluations import DEFAULT_SUITE_PATH, evaluate_suite, model_evaluate_suite
from deadbot.finish import build_experience_response
from deadbot.graph import build_agent, run_config
from deadbot.storage import create_canonical_store


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the local Deadbot LangGraph agent.")
    parser.add_argument(
        "command",
        choices=["chat", "evaluate", "serve", "db-build"],
        help="Run chat, an evaluation, the web experience, or a build of the SQLite catalog.",
    )
    parser.add_argument("--thread-id", default=None, help="Optional in-memory session identifier.")
    parser.add_argument("--suite", type=Path, default=DEFAULT_SUITE_PATH, help="Evaluation-suite JSON file.")
    parser.add_argument("--output", type=Path, default=None, help="Evaluation results JSON file, or the database path for db-build.")
    parser.add_argument("--model", action="store_true", help="Run model responses and capture tool traces for manual review.")
    parser.add_argument("--case", action="append", default=None, help="Run only this evaluation case ID; may be repeated with --model.")
    parser.add_argument("--host", default="127.0.0.1", help="Host interface for the web experience.")
    parser.add_argument("--port", type=int, default=8000, help="Port for the web experience.")
    parser.add_argument("--reload", action="store_true", help="Reload the web experience when Python files change.")
    args = parser.parse_args()

    settings = Settings.from_env()

    if args.command == "db-build":
        from deadbot.sqlite_build import DEFAULT_SQLITE_PATH, main as build_main

        build_main(["--output", str(args.output or settings.sqlite_path or DEFAULT_SQLITE_PATH)])
        return

    if args.command == "serve":
        import uvicorn

        # `kill -USR1 <pid>` prints every thread's stack, so a stuck local
        # server can be diagnosed without restarting it.
        import faulthandler
        import signal

        faulthandler.register(signal.SIGUSR1, all_threads=True)
        uvicorn.run("deadbot.api:app", host=args.host, port=args.port, reload=args.reload)
        return

    if args.command == "evaluate":
        if args.case and not args.model:
            parser.error("--case requires --model")
        if args.model:
            results = model_evaluate_suite(
                args.suite,
                set(args.case) if args.case else None,
                agent=build_agent(settings),
                config_factory=lambda thread_id: run_config(thread_id, settings),
            )
        else:
            results = evaluate_suite(args.suite, store=create_canonical_store(settings))
        rendered = json.dumps(results, ensure_ascii=False, indent=2)
        print(rendered)
        if args.output:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(rendered + "\n", encoding="utf-8")
        if not args.model and results["failed"] > 0:
            sys.exit(1)
        return

    store = create_canonical_store(settings)
    agent = build_agent(settings, store=store)
    thread_id = args.thread_id or f"cli-{uuid.uuid4()}"
    config = run_config(thread_id, settings)
    print(f"Deadbot is ready using {settings.model_provider}:{settings.ollama_model}. Type 'quit' to exit.")

    while True:
        try:
            question = input("\nYou: ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return
        if question.casefold() in {"quit", "exit"}:
            return
        if not question:
            continue
        result = agent.invoke({"messages": [HumanMessage(content=question)]}, config=config)
        response = build_experience_response(question, thread_id, result["messages"], store)
        if response.headline:
            print(f"\n{response.headline}")
        print(f"\nDeadbot: {response.lead}")


if __name__ == "__main__":
    main()
