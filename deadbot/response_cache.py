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

import logging
import os
import re
from typing import Any

from deadbot.experience import ExperienceResponse


logger = logging.getLogger(__name__)

_APOSTROPHE = re.compile(r"[\u2019']")
_WORD = re.compile(r"[^0-9a-z]+")


def question_key(question: str) -> str:
    """Case, punctuation and spacing do not make a different question."""

    return " ".join(_WORD.sub(" ", _APOSTROPHE.sub("", question.casefold())).split())


def deployed_commit() -> str:
    return os.getenv("VERCEL_GIT_COMMIT_SHA") or os.getenv("DEADBOT_GIT_COMMIT") or "unknown"


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
