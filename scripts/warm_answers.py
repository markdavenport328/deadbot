"""Ask a deployment its opening questions so their answers are stored.

Run after a deploy or a data import. Each question is answered live once and
then served from the response cache until the data version or commit changes.

    python scripts/warm_answers.py https://deadbot-ten.vercel.app
    python scripts/warm_answers.py http://127.0.0.1:8000 "What shows did Branford play on?"
"""

from __future__ import annotations

import json
import sys
import time
from urllib.request import Request, urlopen

# Keep in step with the `suggestions` list in web/src/App.tsx.
OPENING_QUESTIONS = [
    "What are the best versions of Franklin's Tower?",
    "What shows did Branford play on?",
    "What was the live legacy of American Beauty?",
]


def main(argv: list[str]) -> int:
    if not argv:
        print(__doc__)
        return 2
    base = argv[0].rstrip("/")
    questions = argv[1:] or OPENING_QUESTIONS
    for question in questions:
        started = time.monotonic()
        request = Request(
            f"{base}/api/experience",
            data=json.dumps({"question": question}).encode("utf-8"),
            headers={"Content-Type": "application/json"},
        )
        with urlopen(request, timeout=300) as response:
            payload = json.loads(response.read().decode("utf-8"))
        print(f"{time.monotonic() - started:6.1f}s  {payload.get('mode', '?'):12s}  {question}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
