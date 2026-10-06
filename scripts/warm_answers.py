"""Make the opening questions' answers ready before a visitor asks.

Two ways to run it:

    # At build time (vercel.json): answer each opening question once and write
    # the answers to a file that ships in the deploy. The app seeds its cache
    # from that file on startup, so the first visitor gets an instant answer
    # even on a fresh serverless instance. Skips quietly where no model key is
    # configured (preview builds) and never fails the build.
    python -m scripts.warm_answers --bundle build/warm-answers.json

    # By hand against a running server (only warms the instance that answers):
    python scripts/warm_answers.py https://deadbot-ten.vercel.app
    python scripts/warm_answers.py http://127.0.0.1:8000 "What shows did Branford play on?"
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from urllib.request import Request, urlopen

# Keep in step with the `startingPoints` list in web/src/App.tsx; the build
# bundles an answer to each (see --bundle above).
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


BUNDLE_WORKERS = 3
BUNDLE_ATTEMPTS = 3


def _answer(client, question: str) -> bool:
    """One fresh turn; a rate limit or a stumble gets another try."""

    for attempt in range(1, BUNDLE_ATTEMPTS + 1):
        started = time.monotonic()
        try:
            response = client.post("/api/experience", json={"question": question})
        except Exception as error:  # a failed question must not fail the build
            print(f"  attempt {attempt}: {question!r} raised {error!r}")
        else:
            if response.status_code == 200 and response.json().get("mode") != "gap":
                print(f"{time.monotonic() - started:6.1f}s  {question}")
                return True
            print(f"  attempt {attempt}: {question!r} returned {response.status_code}")
        time.sleep(5 * attempt)
    return False


def build_bundle(path: Path, questions: list[str]) -> int:
    """Answer each question live and write the answers to ``path``. Always returns 0."""

    from deadbot.config import Settings

    settings = Settings.from_env()
    if settings.model_provider == "openai" and not settings.openai_api_key:
        print("warm answers: no OPENAI_API_KEY here (a preview build?); skipping, answers will be computed live")
        return 0
    # The producer fills a scratch cache and must not seed itself from a stale bundle.
    scratch = Path(tempfile.mkdtemp()) / "cache.sqlite"
    os.environ["DEADBOT_RESPONSE_CACHE_PATH"] = str(scratch)
    os.environ["DEADBOT_WARM_ANSWERS_PATH"] = str(scratch.parent / "none.json")
    try:
        import dataclasses

        from fastapi.testclient import TestClient

        from deadbot.api import create_app
        from deadbot.graph import build_agent
        from deadbot.storage import create_canonical_store

        settings = dataclasses.replace(settings, response_cache=True, rate_limit_per_minute=0)
        store = create_canonical_store(settings)
        app = create_app(settings, store=store, agent=build_agent(settings, store=store))
        client = TestClient(app)
        with ThreadPoolExecutor(max_workers=BUNDLE_WORKERS) as pool:
            done = list(pool.map(lambda question: _answer(client, question), questions))
        entries = app.state.response_cache.export(questions)
    except Exception as error:  # the build ships either way; answers are then live
        print(f"warm answers: skipped after an error: {error!r}")
        return 0
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(entries, ensure_ascii=False), encoding="utf-8")
    print(f"warm answers: wrote {len(entries)} of {len(questions)} to {path} ({sum(done)} answered)")
    return 0


def main(argv: list[str]) -> int:
    if not argv:
        print(__doc__)
        return 2
    if argv[0] == "--bundle":
        if len(argv) < 2:
            print(__doc__)
            return 2
        return build_bundle(Path(argv[1]), argv[2:] or OPENING_QUESTIONS)
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
