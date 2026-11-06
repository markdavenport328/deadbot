"""Time the progressive stream for one question against a running API.

Usage: PY scripts/trace_stream.py "What shows did Branford play on?" [base_url]
Prints seconds from request start to: first answer text, answer complete
("Composing the page" status), the opening-tab event, the first block on each
workspace tab, first block, last block, response. Also prints the opening tab
the model chose and how many groups landed on each tab.
"""

from __future__ import annotations

import json
import sys
import time
import urllib.request
from collections import Counter
from typing import Any

# Mirrors fallbackTab in web/src/tab-routing.ts: where a block goes when its
# group names no tab. Keep the two in step.
LISTEN_TYPES = {"show_unit", "performance_unit", "album_unit", "song_overview", "show_selection", "listening_hero", "version_strip", "media_link"}
CHARTS_TYPES = {"data_chart", "grid"}
TABS = ("listen", "charts", "read")


def fallback_tab(block: dict[str, Any]) -> str:
    kind = block.get("type")
    if kind in LISTEN_TYPES:
        return "listen"
    if kind in CHARTS_TYPES:
        return "charts"
    return "read"


def trace(question: str, base_url: str = "http://127.0.0.1:8000", conversation: list | None = None) -> dict[str, Any]:
    payload: dict[str, Any] = {"question": question, "thread_id": f"trace-{time.time_ns()}"}
    if conversation:
        payload["conversation"] = conversation
    request = urllib.request.Request(
        f"{base_url}/api/experience/stream", data=json.dumps(payload).encode(), headers={"Content-Type": "application/json"}
    )
    start = time.monotonic()
    marks: dict[str, Any] = {
        "first_answer": None, "answer_complete": None, "page_tab": None,
        "first_listen_block": None, "first_charts_block": None, "first_read_block": None,
        "first_block": None, "last_block": None, "response": None,
    }
    opening_tab: str | None = None
    group_tabs: dict[int, str | None] = {}
    group_counts: Counter[str] = Counter()
    answer = ""
    with urllib.request.urlopen(request, timeout=240) as stream:
        for raw in stream:
            event = json.loads(raw)
            now = time.monotonic() - start
            kind = event.get("type")
            if kind == "answer":
                marks["first_answer"] = marks["first_answer"] if marks["first_answer"] is not None else now
                answer = event.get("text") or answer  # each event carries the answer so far
            elif kind == "status" and event.get("text") == "Composing the page":
                marks["answer_complete"] = now
            elif kind == "page_tab":
                marks["page_tab"] = now
                opening_tab = event.get("tab")
            elif kind == "group_open":
                group = event.get("group") or event
                group_tabs[group.get("index", len(group_tabs))] = group.get("tab")
            elif kind == "block":
                block = event.get("block") or {}
                tab = group_tabs.get(event.get("group_index", -1)) or fallback_tab(block)
                key = f"first_{tab}_block"
                if marks.get(key) is None:
                    marks[key] = now
                marks["first_block"] = marks["first_block"] if marks["first_block"] is not None else now
                marks["last_block"] = now
            elif kind == "response":
                marks["response"] = now
                response = event.get("response") or {}
                opening_tab = response.get("initial_tab", opening_tab)
                blocks = response.get("blocks") or []
                for group in response.get("groups") or []:
                    indexes = [i for i in group.get("block_indexes") or [] if 0 <= i < len(blocks)]
                    tab = group.get("tab") or (fallback_tab(blocks[indexes[0]]) if indexes else "read")
                    group_counts[tab] += 1
                answer = response.get("answer") or answer
    return {"marks": marks, "opening_tab": opening_tab, "groups": dict(group_counts), "answer": answer}


if __name__ == "__main__":
    question = sys.argv[1]
    base = sys.argv[2] if len(sys.argv) > 2 else "http://127.0.0.1:8000"
    result = trace(question, base)
    for name, seconds in result["marks"].items():
        print(f"{name}: {'n/a' if seconds is None else f'{seconds:.1f}s'}")
    print(f"opening_tab: {result['opening_tab']}")
    print(f"groups: {result['groups']}")
