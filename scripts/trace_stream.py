"""Time the progressive stream for one question against a running API.

Usage: PY scripts/trace_stream.py "What shows did Branford play on?" [base_url]
Prints seconds from request start to: first answer text, answer complete
("Composing the page" status), first block, last block, response.
"""

from __future__ import annotations

import json
import sys
import time
import urllib.request


def trace(question: str, base_url: str = "http://127.0.0.1:8000") -> dict[str, float | None]:
    body = json.dumps({"question": question, "thread_id": f"trace-{int(time.time())}"}).encode()
    request = urllib.request.Request(f"{base_url}/api/experience/stream", data=body, headers={"Content-Type": "application/json"})
    start = time.monotonic()
    marks: dict[str, float | None] = {"first_answer": None, "answer_complete": None, "first_block": None, "last_block": None, "response": None}
    with urllib.request.urlopen(request) as stream:
        for raw in stream:
            event = json.loads(raw)
            now = time.monotonic() - start
            kind = event.get("type")
            if kind == "answer" and marks["first_answer"] is None:
                marks["first_answer"] = now
            elif kind == "status" and event.get("text") == "Composing the page":
                marks["answer_complete"] = now
            elif kind == "block":
                marks["first_block"] = marks["first_block"] if marks["first_block"] is not None else now
                marks["last_block"] = now
            elif kind == "response":
                marks["response"] = now
    return marks


if __name__ == "__main__":
    question = sys.argv[1]
    base = sys.argv[2] if len(sys.argv) > 2 else "http://127.0.0.1:8000"
    for name, seconds in trace(question, base).items():
        print(f"{name}: {'n/a' if seconds is None else f'{seconds:.1f}s'}")
