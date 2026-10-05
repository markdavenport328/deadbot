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

# Keep in step with the `startingPoints` list in web/src/App.tsx. Nothing warms
# these on deploy today, so they answer cold unless you run this by hand.
OPENING_QUESTIONS = [
    "Best shows of 1979",
    "What's the story with Veneta?",
    "Best shows at Madison Square Garden",
    "What songs did they play the most?",
    "When did China-Rider become a combo?",
    "Which albums most impacted the live repertoire?",
    "How often did they play Dark Star each year?",
    "Best Morning Dew?",
    "Find me a few good Ripples",
    "Which Dick's Picks should I start with?",
    "What's on Europe '72: The Complete Recordings?",
    "What shows did Reckoning draw from?",
    "Best Santana contributions",
    "What shows did Branford play?",
    "Who sat in with the Dead?",
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
