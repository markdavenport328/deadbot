"""The home screen's catalog numbers are literals; keep them true.

They are written into web/src/App.tsx so the page renders without a request.
That trade is only safe if an import that moves a count fails a test rather
than quietly shipping a wrong number to the first screen anyone sees.
"""

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from home_stats import home_stats
from warm_answers import OPENING_QUESTIONS

APP = Path(__file__).resolve().parents[1] / "web" / "src" / "App.tsx"
ENTRY = re.compile(r'\{\s*count:\s*"([\d,]+)",\s*noun:\s*"(\w+)"\s*\}')


def published_stats() -> dict[str, int]:
    source = APP.read_text(encoding="utf-8")
    block = source.split("const stats = [", 1)[1].split("];", 1)[0]
    return {noun: int(count.replace(",", "")) for count, noun in ENTRY.findall(block)}


def test_home_screen_counts_match_the_canonical_csvs():
    published = published_stats()
    assert published, "no stats found in App.tsx"
    assert published == home_stats(), (
        "Home screen counts are stale. Run `python scripts/home_stats.py` "
        "and paste the result into the `stats` list in web/src/App.tsx."
    )


def test_every_counted_noun_is_shown():
    assert set(published_stats()) == set(home_stats())


QUESTION = re.compile(r'"((?:[^"\\]|\\.)*)"')


def published_questions() -> list[str]:
    source = APP.read_text(encoding="utf-8")
    block = source.split("const startingPoints = [", 1)[1].split("\n];", 1)[0]
    groups = block.split('category: "')[1:]
    questions: list[str] = []
    for group in groups:
        body = group.split("questions: [", 1)[1].split("]", 1)[0]
        questions.extend(text.replace('\\"', '"') for text in QUESTION.findall(body))
    return questions


def test_warm_script_asks_exactly_what_the_home_screen_offers():
    """Nothing warms these on deploy, so the script is the only way to warm
    them by hand. A starting point missing from its list warms nothing."""

    assert published_questions() == OPENING_QUESTIONS
