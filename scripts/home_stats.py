#!/usr/bin/env python3
"""Compute the catalog counts the home screen prints.

The home screen carries these numbers as literals so the page costs nothing
to render. Run this after a data import and paste the result into the `stats`
list in web/src/App.tsx; tests/test_home_stats.py fails until you do.

    python scripts/home_stats.py
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from deadbot.data import CanonicalStore

# A JerryBase enrichment pass spelled some appearances as a second person:
# "Bruce Hornsby (complete show)", "Marvin Boxley (songs unknown)". The
# qualifier describes the booking, not another human. Collapse one only when a
# plain row of the same name already exists, so two people who genuinely differ
# are never merged on the strength of a parenthetical.
QUALIFIER = re.compile(r"\s*\([^)]*\)\s*$")


def guest_count(store: CanonicalStore) -> int:
    """Count the humans who have sat in, not the rows crediting them."""

    names = {person["person_id"]: person.get("name", "") for person in store.rows("people")}
    plain = {name.casefold() for name in names.values() if name and not QUALIFIER.search(name)}

    def identity(person_id: str) -> str:
        name = names[person_id]
        base = QUALIFIER.sub("", name).strip()
        return base.casefold() if base.casefold() in plain else (name.casefold() or person_id)

    guests = {
        assignment["person_id"]
        for assignment in store.rows("show_performers")
        if assignment.get("role") == "guest" and assignment.get("person_id") in names
    }
    return len({identity(person_id) for person_id in guests})


def home_stats(store: CanonicalStore | None = None) -> dict[str, int]:
    store = store or CanonicalStore()
    return {
        "shows": store.row_count("shows"),
        "songs": store.row_count("songs"),
        "performances": store.row_count("performances"),
        "recordings": store.row_count("recordings"),
        "guests": guest_count(store),
    }


def main() -> int:
    for noun, count in home_stats().items():
        print(f'  {{ count: "{count:,}", noun: "{noun}" }},')
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
