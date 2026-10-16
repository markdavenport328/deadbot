"""Tour names the way fans say them.

A fan writes "Europe '72", "Europe 72", "europe 1972 tour" or "Spring '77";
the library stores "Europe 1972" and "Spring 1977". One normalizer serves every
place a tour is matched, so each spelling lands on the stored name.
"""

from __future__ import annotations

import re
from collections.abc import Iterable


def normalize_tour(name: str) -> str:
    """Lowercase, apostrophe or two-digit years widened to 19xx, "tour" and punctuation dropped."""

    text = (name or "").lower().replace("’", "'").replace("‘", "'")
    text = re.sub(r"(?<!\d)'(\d{2})(?!\d)", r"19\1", text)
    text = re.sub(r"\btour\b", " ", text)
    text = re.sub(r"[^a-z0-9]+", " ", text)
    text = re.sub(r"(?<!\d)(\d{2})(?!\d)", r"19\1", text)
    return " ".join(text.split())


def matching_tours(known: Iterable[str], name: str) -> list[str]:
    """The stored tour names that equal ``name`` once both are normalized."""

    wanted = normalize_tour(name)
    if not wanted:
        return []
    return sorted({tour for tour in known if tour and normalize_tour(tour) == wanted})
