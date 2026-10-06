"""Stored composed answers for repeated fresh questions.

The opening suggestion chips are fixed strings, and every visitor who clicks
one waits for the same minute of research. A stored answer is served instead
while two things hold: the canonical data version the store reports is the
one the answer was computed from, and the deployed commit is the one whose
prompt and tools composed it. Either changing invalidates every entry without
deleting anything. Answers to follow-ups (requests carrying a conversation)
are never stored or served from here.

The store decides whether it can hold answers at all: a store without the
cache methods (the CSV store, test doubles) simply disables the feature.
"""

from __future__ import annotations

import functools
import json
import logging
import os
import re
import subprocess
from pathlib import Path
from typing import Any

from deadbot.experience import ExperienceResponse


logger = logging.getLogger(__name__)

_APOSTROPHE = re.compile(r"[\u2019']")
_WORD = re.compile(r"[^0-9a-z]+")


def question_key(question: str) -> str:
    """Case, punctuation and spacing do not make a different question."""

    return " ".join(_WORD.sub(" ", _APOSTROPHE.sub("", question.casefold())).split())


def deployed_commit() -> str:
    return os.getenv("VERCEL_GIT_COMMIT_SHA") or os.getenv("DEADBOT_GIT_COMMIT") or _local_commit() or "unknown"


@functools.cache
def _local_commit() -> str | None:
    """The checked-out commit when running from a git checkout.

    A local server has no deploy variable, so without this every code change
    kept serving answers cached by the previous code.
    """

    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=Path(__file__).resolve().parent,
            capture_output=True,
            text=True,
            timeout=2,
            check=True,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return result.stdout.strip() or None


# Answers computed at build time ship with the deploy. A serverless instance
# starts with an empty cache of its own, so the first visitor to each opening
# question would otherwise wait for a live turn; seeding from this file serves
# them at once. The file is optional.
DEFAULT_BUNDLE_PATH = Path(__file__).resolve().parents[1] / "build" / "warm-answers.json"


def bundle_path() -> Path:
    return Path(os.getenv("DEADBOT_WARM_ANSWERS_PATH") or DEFAULT_BUNDLE_PATH)


class ResponseCache:
    def __init__(self, store: Any, *, enabled: bool = True, max_age_seconds: int = 7 * 24 * 60 * 60) -> None:
        self._store = store
        self._max_age = max_age_seconds
        self._ready = False
        self._enabled = enabled and all(
            callable(getattr(store, name, None))
            for name in ("data_version", "ensure_response_cache", "cached_response", "store_response")
        )

    @property
    def enabled(self) -> bool:
        return self._enabled

    def _version(self) -> str:
        return f"{self._store.data_version()}|commit={deployed_commit()}"

    def _prepare(self) -> bool:
        if not self._enabled:
            return False
        if not self._ready:
            try:
                self._store.ensure_response_cache()
            except Exception:
                logger.exception("Response cache is unavailable; answering live")
                self._enabled = False
                return False
            self._ready = True
            self.seed_from_bundle()
        return True

    def lookup(self, question: str, *, thread_id: str) -> ExperienceResponse | None:
        if not self._prepare():
            return None
        key = question_key(question)
        if not key:
            return None
        try:
            payload = self._store.cached_response(key, self._version(), self._max_age)
        except Exception:
            logger.exception("Response cache lookup failed; answering live")
            return None
        if payload is None:
            return None
        try:
            response = ExperienceResponse.model_validate({**payload, "thread_id": thread_id})
        except Exception:
            logger.warning("Discarding a stored answer that no longer validates for %r", key)
            return None
        # A stored answer is served under a fresh thread so follow-ups start
        # a conversation of their own rather than reviving the original one.
        return response

    def remember(self, question: str, response: ExperienceResponse) -> None:
        if not self._prepare():
            return
        key = question_key(question)
        # A gap answer records what the library could not do, not an answer
        # worth repeating; the next visitor gets a fresh attempt.
        if not key or response.mode == "gap":
            return
        try:
            self._store.store_response(key, self._version(), question, response.model_dump(mode="json"))
        except Exception:
            logger.exception("Response cache write failed; the answer was still delivered")


    def export(self, questions: list[str]) -> list[dict[str, Any]]:
        """The stored answers to these questions, ready to ship as a bundle."""

        if not self._prepare():
            return []
        entries = []
        for question in questions:
            key = question_key(question)
            payload = self._store.cached_response(key, self._version(), self._max_age) if key else None
            if payload is not None:
                entries.append(
                    {"question": question, "question_key": key, "data_version": self._version(), "response": payload}
                )
        return entries

    def seed(self, entries: list[dict[str, Any]]) -> int:
        """Store bundled answers made from this data version and commit; skip the rest."""

        if not self._prepare():
            return 0
        version = self._version()
        stored = 0
        for entry in entries:
            if entry.get("data_version") != version or not entry.get("question_key"):
                continue
            try:
                self._store.store_response(entry["question_key"], version, entry.get("question", ""), entry["response"])
                stored += 1
            except Exception:
                logger.exception("Could not seed a bundled answer for %r", entry.get("question_key"))
        return stored

    def seed_from_bundle(self, path: Path | None = None) -> int:
        path = path or bundle_path()
        try:
            entries = json.loads(path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return 0
        except (OSError, ValueError):
            logger.exception("Ignoring an unreadable warm-answers bundle at %s", path)
            return 0
        stored = self.seed(entries) if isinstance(entries, list) else 0
        logger.info("Seeded %d of %d bundled answers from %s", stored, len(entries) if isinstance(entries, list) else 0, path)
        return stored
