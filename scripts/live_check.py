"""Run real questions through the real app and show what the model did.

Fixtures prove a component renders; this proves the model uses it. Each run
costs one real model turn.

    PYTHONPATH=. python scripts/live_check.py ask "When was Dark Star played?" --out DIR
    PYTHONPATH=. python scripts/live_check.py serve --out DIR [--port 8000]
    PYTHONPATH=. python scripts/live_check.py report DIR/<run>.json

``ask`` posts one question to /api/experience/stream through a FastAPI
TestClient and saves the NDJSON stream plus a turn dump (tool calls, tool
output sizes, the finish_response plan, log lines). ``serve`` runs the same
app under uvicorn so the question can be asked in the browser (the Vite dev
server proxies /api to port 8000); every turn it serves is dumped the same way.
``report`` prints a saved dump again.

Settings: the owner's .env is read line by line (it cannot be sourced: a value
contains ``&``), then the provider is forced to OpenAI, the store to SQLite and
the response cache off, so every run is a fresh model turn.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import re
import sys
import time
from pathlib import Path
from typing import Any

ENV_FILE = Path("/Users/markdavenport/Development/DeadBot/.env")


def load_env() -> None:
    try:
        lines = ENV_FILE.read_text(encoding="utf-8").splitlines()
    except FileNotFoundError:
        lines = []
    for raw in lines:
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
            value = value[1:-1]
        os.environ.setdefault(key.strip(), value)
    os.environ["DEADBOT_MODEL_PROVIDER"] = "openai"
    os.environ["DEADBOT_DATA_STORE"] = "sqlite"
    os.environ["DEADBOT_RESPONSE_CACHE"] = "false"
    os.environ["DEADBOT_RATE_LIMIT_PER_MINUTE"] = "1000"


class LogCollector(logging.Handler):
    def __init__(self) -> None:
        super().__init__(level=logging.INFO)
        self.lines: list[str] = []

    def emit(self, record: logging.LogRecord) -> None:
        if record.name.startswith(("httpx", "httpcore", "openai", "urllib3")):
            return
        self.lines.append(f"{record.levelname} {record.name}: {record.getMessage()[:1200]}")


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:48]


def turn_dump(question: str, messages: list[Any], logs: list[str]) -> dict[str, Any]:
    """The facts about one turn worth reading: calls, sizes, the plan, the logs."""

    from deadbot.finish import FINISH_TOOL_NAME

    start = 0
    for index, message in enumerate(messages):
        if getattr(message, "type", None) == "human":
            start = index
    tools: list[dict[str, Any]] = []
    plans: list[dict[str, Any]] = []
    results_by_id: dict[str, Any] = {}
    for message in messages[start:]:
        if getattr(message, "type", None) == "tool":
            results_by_id[getattr(message, "tool_call_id", "")] = message
    for message in messages[start:]:
        if getattr(message, "type", None) != "ai":
            continue
        for call in getattr(message, "tool_calls", None) or []:
            if call.get("name") == FINISH_TOOL_NAME:
                result = results_by_id.get(call.get("id"))
                plans.append({"args": call.get("args"), "status": getattr(result, "status", None),
                              "result": str(getattr(result, "content", ""))[:600] if result else None})
                continue
            result = results_by_id.get(call.get("id"))
            content = str(getattr(result, "content", "")) if result is not None else ""
            tools.append({
                "name": call.get("name"),
                "args": call.get("args"),
                "chars": len(content),
                "truncated": '"_truncated"' in content,
                "error": content[:300] if content.startswith('{"error"') else None,
            })
    return {"question": question, "tools": tools, "plans": plans, "logs": logs}


def _block_line(block: dict[str, Any]) -> str:
    kind = block.get("type")
    bits = [kind]
    for key in ("emphasis", "disclosure", "chart", "orientation"):
        if block.get(key):
            bits.append(f"{key}={block[key]}")
    if block.get("visible_facets"):
        bits.append("facets=" + ",".join(block["visible_facets"]))
    for key in ("title", "release_title", "venue_name", "show_date"):
        if block.get(key):
            bits.append(f"{key}={str(block[key])[:60]!r}")
            break
    for key in ("rows", "tracks", "year_counts", "listen", "items", "setlist", "performances", "representative_performances"):
        value = block.get(key)
        if isinstance(value, list) and value:
            bits.append(f"{key}={len(value)}")
    if block.get("note"):
        bits.append(f"note={block['note'][:80]!r}")
    if kind == "data_chart":
        bits.append(f"total={block.get('total')} excluded={block.get('excluded_count')}")
    if kind == "ranked_list":
        bits.append(f"more={block.get('more_count')}")
    if kind == "editorial":
        bits.append(f"presentation={block.get('presentation')} items={len(block.get('items') or [])}")
    return " ".join(str(bit) for bit in bits)


def print_report(dump: dict[str, Any], response: dict[str, Any] | None) -> None:
    print(f"\n=== {dump['question']}")
    print("-- tools")
    for tool in dump["tools"]:
        flag = " TRUNCATED" if tool["truncated"] else ""
        flag += f" ERROR {tool['error']}" if tool.get("error") else ""
        print(f"  {tool['name']}({json.dumps(tool['args'], ensure_ascii=False)[:200]}) -> {tool['chars']} chars{flag}")
    print("-- finish_response plans")
    for plan in dump["plans"]:
        text = json.dumps(plan["args"], ensure_ascii=False)
        print(f"  status={plan['status']} {len(text)} chars")
        print("  " + text[:6000])
        if plan["status"] == "error":
            print("  ERROR: " + str(plan["result"]))
    if response:
        print("-- page")
        print(f"  title: {response.get('title')}")
        print(f"  answer: {response.get('answer', '')[:700]}")
        if response.get("body_lead"):
            print(f"  lead: {response['body_lead'][:300]}")
        for group in response.get("groups") or []:
            print(f"  group {group.get('presentation')} {group.get('title')!r} blocks={group.get('block_indexes')}")
        for index, block in enumerate(response.get("blocks") or []):
            print(f"  [{index}] {_block_line(block)}")
    print("-- logs")
    for line in dump["logs"]:
        if "turn_metrics" in line or line.startswith(("WARNING", "ERROR")) or "Dropped" in line or "Skipped" in line:
            print("  " + line)


class DumpingAgent:
    """Wraps the compiled graph so each turn's final messages are dumped."""

    def __init__(self, agent: Any, out_dir: Path, collector: LogCollector) -> None:
        self._agent = agent
        self._out = out_dir
        self._collector = collector
        self.last_path: Path | None = None

    def __getattr__(self, name: str) -> Any:
        return getattr(self._agent, name)

    def stream(self, payload: dict[str, Any], config: dict[str, Any], **kwargs: Any):
        self._collector.lines.clear()
        messages: list[Any] = []
        for item in self._agent.stream(payload, config, **kwargs):
            if isinstance(item, tuple) and len(item) == 2 and item[0] == "values":
                messages = list(item[1].get("messages", []))
            yield item
        question = ""
        for message in messages:
            if getattr(message, "type", None) == "human":
                question = str(message.content)
        dump = turn_dump(question, messages, list(self._collector.lines))
        path = self._out / f"{time.strftime('%H%M%S')}-{_slug(question)}.json"
        path.write_text(json.dumps(dump, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
        self.last_path = path
        print(f"[live_check] turn dump: {path}", file=sys.stderr)


def build_app(out_dir: Path):
    load_env()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    collector = LogCollector()
    logging.getLogger().addHandler(collector)
    from deadbot.api import create_app
    from deadbot.config import Settings
    from deadbot.graph import build_agent
    from deadbot.storage import create_canonical_store

    settings = Settings.from_env()
    store = create_canonical_store(settings)
    agent = DumpingAgent(build_agent(settings, store=store), out_dir, collector)
    return create_app(settings, store=store, agent=agent), agent, collector


def ask(question: str, out_dir: Path) -> None:
    from fastapi.testclient import TestClient

    app, agent, collector = build_app(out_dir)
    started = time.monotonic()
    events: list[dict[str, Any]] = []
    with TestClient(app) as client:
        with client.stream("POST", "/api/experience/stream", json={"question": question, "conversation": []}) as reply:
            for raw in reply.iter_lines():
                if raw:
                    events.append(json.loads(raw))
    elapsed = time.monotonic() - started
    dump_path = agent.last_path or out_dir / f"{time.strftime('%H%M%S')}-{_slug(question)}.json"
    stream_path = dump_path.with_suffix(".ndjson")
    stream_path.write_text("".join(json.dumps(event, ensure_ascii=False) + "\n" for event in events), encoding="utf-8")
    response = next((event["response"] for event in events if event.get("type") == "response"), None)
    dump = json.loads(dump_path.read_text()) if dump_path.exists() else turn_dump(question, [], collector.lines)
    dump["response"] = response
    dump["logs"] = list(collector.lines)
    dump["seconds"] = round(elapsed, 1)
    dump_path.write_text(json.dumps(dump, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    print_report(dump, response)
    errors = [event for event in events if event.get("type") == "error"]
    print(f"-- {elapsed:.1f}s, {len(events)} events, errors={errors}; saved {stream_path}")


def serve(out_dir: Path, port: int) -> None:
    import uvicorn

    app, agent, collector = build_app(out_dir)

    class RecordingCache:
        """Never serves a stored answer; writes each finished page into its turn dump."""

        def lookup(self, *_: Any, **__: Any) -> None:
            return None

        def remember(self, question: str, response: Any) -> None:
            if agent.last_path is None:
                return
            dump = json.loads(agent.last_path.read_text())
            dump["response"] = response.model_dump(mode="json")
            dump["logs"] = list(collector.lines)
            agent.last_path.write_text(json.dumps(dump, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
            print_report(dump, dump["response"])

    app.state.response_cache = RecordingCache()
    uvicorn.run(app, host="127.0.0.1", port=port, log_config=None)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)
    ask_parser = sub.add_parser("ask")
    ask_parser.add_argument("question")
    ask_parser.add_argument("--out", type=Path, default=Path("build/live-runs"))
    serve_parser = sub.add_parser("serve")
    serve_parser.add_argument("--out", type=Path, default=Path("build/live-runs"))
    serve_parser.add_argument("--port", type=int, default=8000)
    report_parser = sub.add_parser("report")
    report_parser.add_argument("path", type=Path)
    args = parser.parse_args()
    if args.command == "report":
        dump = json.loads(args.path.read_text())
        print_report(dump, dump.get("response"))
        return
    args.out.mkdir(parents=True, exist_ok=True)
    if args.command == "ask":
        ask(args.question, args.out)
    else:
        serve(args.out, args.port)


if __name__ == "__main__":
    main()
