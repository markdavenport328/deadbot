"""Usage limits: enough that one person or a simple script cannot run up a bill.

Every question that reaches the model is a paid call sequence. There is no
shared store, so nothing here is exact across function instances; three layers
cover for each other instead:

- a signed allowance cookie the browser carries, so a visitor's count follows
  them from instance to instance and people behind one address each get their
  own allowance;
- counters per client address in this instance's memory, which bound requests
  that send no cookie or replay an old one;
- one ceiling on everything this instance sends to the model in a day.

Only questions that reach the model are counted. A stored answer is a cheap
library read and spends the lookup budget instead. These limits keep the
service affordable; they say nothing about what the model may write.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import logging
import math
import secrets
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass

from deadbot.config import Settings


logger = logging.getLogger(__name__)

MINUTE = 60
DAY = 24 * 60 * 60

COOKIE_NAME = "deadbot_allowance"
COOKIE_MAX_AGE = 2 * DAY

# Function instances do not share a clock; a window another instance opened a
# little "in the future" is still this visitor's window.
CLOCK_SKEW = 300
# Past this many keys a window forgets the expired ones before adding another.
SWEEP_AT = 5_000

LOOKUPS = "Too many requests. Please wait a minute and try again."
TOO_FAST = "That is a lot of questions at once. Please ask again {when}."
DAILY = "You have reached today's limit for questions during the beta. You can ask again {when}."
INSTANCE = "Deadbot has answered all the questions it can for now. Please ask again {when}."

State = tuple[float, int]


class LimitReached(Exception):
    """A request the limits turn away, with the plain sentence the visitor reads."""

    def __init__(self, name: str, retry_after: int, message: str) -> None:
        super().__init__(name)
        self.name = name
        self.retry_after = retry_after
        self.message = message


def when(seconds: float) -> str:
    """How long until the visitor can ask again, rounded up so it is never too early."""

    if seconds <= 50:
        return "in under a minute"
    minutes = math.ceil(seconds / 60)
    if minutes < 2:
        return "in about a minute"
    if minutes <= 50:
        return f"in about {minutes} minutes"
    hours = math.ceil(seconds / 3600)
    return "in about an hour" if hours == 1 else f"in about {hours} hours"


class Window:
    """A counter per key over a fixed window, kept in this process's memory.

    A window opens with a key's first counted request and closes ``seconds``
    later, so the wait it reports is exactly when the key may count again.
    A limit of 0 or less turns the window off.
    """

    def __init__(self, limit: int, seconds: int) -> None:
        self.limit = limit
        self.seconds = seconds
        self._states: dict[str, State] = {}

    def live(self, state: State | None, now: float) -> bool:
        return state is not None and state[0] <= now + CLOCK_SKEW and now < state[0] + self.seconds

    def state(self, key: str, now: float) -> State:
        state = self._states.get(key)
        return state if self.live(state, now) else (now, 0)

    def wait(self, state: State, now: float) -> float:
        """Seconds until a key in this state may count again; 0 while it is under the limit."""

        if self.limit <= 0 or state[1] < self.limit:
            return 0.0
        return max(state[0] + self.seconds - now, 0.0)

    def put(self, key: str, state: State, now: float) -> None:
        if self.limit <= 0:
            return
        if key not in self._states and len(self._states) >= SWEEP_AT:
            self._states = {known: kept for known, kept in self._states.items() if self.live(kept, now)}
            if len(self._states) >= SWEEP_AT * 4:
                logger.warning("A usage window held %d live keys; starting it over", len(self._states))
                self._states = {}
        self._states[key] = state

    def add(self, key: str, now: float) -> None:
        started, count = self.state(key, now)
        self.put(key, (started, count + 1), now)


# --- the allowance cookie ---------------------------------------------------------


@dataclass(frozen=True)
class Allowance:
    """What a visitor has used: a random id and two counted windows. No personal data."""

    visitor: str
    minute: State
    day: State


def signing_key(secret: str | None) -> bytes | None:
    """A key of its own for allowances, derived from the deployment's signing secret."""

    if not secret:
        return None
    return hmac.new(secret.encode("utf-8"), b"deadbot-allowance-v1", hashlib.sha256).digest()


def _signature(body: str, key: bytes) -> str:
    return hmac.new(key, body.encode("ascii"), hashlib.sha256).hexdigest()[:32]


def encode(allowance: Allowance, key: bytes) -> str:
    fields = [allowance.visitor, int(allowance.minute[0]), allowance.minute[1], int(allowance.day[0]), allowance.day[1]]
    body = base64.urlsafe_b64encode(json.dumps(fields, separators=(",", ":")).encode("ascii")).decode("ascii").rstrip("=")
    return f"{body}.{_signature(body, key)}"


def decode(token: str | None, key: bytes | None) -> Allowance | None:
    """The allowance a token carries, or None when it is missing, altered or not ours."""

    if not token or key is None or len(token) > 400:
        return None
    body, _, signature = token.partition(".")
    try:
        if not hmac.compare_digest(signature, _signature(body, key)):
            return None
        visitor, minute_start, minute_count, day_start, day_count = json.loads(base64.urlsafe_b64decode(body + "=" * (-len(body) % 4)))
        numbers = (minute_start, minute_count, day_start, day_count)
        if not isinstance(visitor, str) or not all(type(number) is int and number >= 0 for number in numbers):
            return None
    except (ValueError, TypeError, UnicodeError):
        return None
    return Allowance(visitor=visitor, minute=(float(minute_start), minute_count), day=(float(day_start), day_count))


def cookie_header(token: str, *, secure: bool) -> str:
    """The Set-Cookie value. The browser sends it back by itself on same-origin requests."""

    return f"{COOKIE_NAME}={token}; Max-Age={COOKIE_MAX_AGE}; Path=/api; HttpOnly; SameSite=Lax" + ("; Secure" if secure else "")


# --- admission ---------------------------------------------------------------------


def _fuller(window: Window, carried: State, remembered: State, now: float) -> State:
    """The visitor's window from the cookie or from memory, whichever has counted more.

    They agree for an honest browser. A replayed older cookie counts less than
    this instance remembers, so memory wins on the instance that saw it.
    """

    states = [state for state in (carried, remembered) if window.live(state, now)]
    return max(states, key=lambda state: state[1], default=(now, 0))


class Limits:
    """Every usage window of one application instance."""

    _INSTANCE_KEY = "instance"

    def __init__(self, settings: Settings, clock: Callable[[], float] = time.time) -> None:
        self.clock = clock
        self._key = signing_key(settings.notebook_secret)
        self._lock = threading.Lock()
        self.lookups = Window(settings.grid_rate_limit_per_minute, MINUTE)
        self.address_minute = Window(settings.rate_limit_per_minute, MINUTE)
        self.address_day = Window(settings.rate_limit_per_day, DAY)
        self.new_visitors = Window(settings.new_visitors_per_day, DAY)
        self.visitor_minute = Window(settings.visitor_limit_per_minute, MINUTE)
        self.visitor_day = Window(settings.visitor_limit_per_day, DAY)
        self.instance_day = Window(settings.instance_limit_per_day, DAY)

    def _reached(self, name: str, window: Window, wait: float, message: str) -> LimitReached:
        retry_after = max(math.ceil(wait), 1)
        # Which limit, never who: no address or visitor id goes in the log.
        logger.warning("Usage limit reached: %s (limit %d per %d s); open again in %d s", name, window.limit, window.seconds, retry_after)
        return LimitReached(name, retry_after, message.format(when=when(wait)))

    def lookup(self, address: str) -> None:
        """Count one cheap library read (a grid, a row, a stored answer) for this address."""

        with self._lock:
            now = self.clock()
            wait = self.lookups.wait(self.lookups.state(address, now), now)
            if wait:
                raise self._reached("lookups per address per minute", self.lookups, wait, LOOKUPS)
            self.lookups.add(address, now)

    def admit(self, address: str, token: str | None) -> str | None:
        """Count one question that will reach the model, or raise LimitReached.

        Returns the visitor's new allowance token for the cookie, or None when
        allowances are off (no signing secret, or both visitor limits at 0).
        """

        with self._lock:
            now = self.clock()
            carries_allowances = self._key is not None and (self.visitor_minute.limit > 0 or self.visitor_day.limit > 0)
            allowance = decode(token, self._key) if carries_allowances else None
            checks: list[tuple[str, Window, State, str]] = [
                ("instance per day", self.instance_day, self.instance_day.state(self._INSTANCE_KEY, now), INSTANCE),
                ("address per minute", self.address_minute, self.address_minute.state(address, now), TOO_FAST),
                ("address per day", self.address_day, self.address_day.state(address, now), DAILY),
            ]
            minute: State = (now, 0)
            day: State = (now, 0)
            if allowance is not None:
                minute = _fuller(self.visitor_minute, allowance.minute, self.visitor_minute.state(allowance.visitor, now), now)
                day = _fuller(self.visitor_day, allowance.day, self.visitor_day.state(allowance.visitor, now), now)
                checks.append(("visitor per minute", self.visitor_minute, minute, TOO_FAST))
                checks.append(("visitor per day", self.visitor_day, day, DAILY))
            elif carries_allowances:
                # No cookie, or one that is not ours: a first visit, or a script
                # that throws its allowance away to get a fresh one.
                checks.append(("new visitors per address per day", self.new_visitors, self.new_visitors.state(address, now), DAILY))
            waits = [(window.wait(state, now), name, window, message) for name, window, state, message in checks]
            wait, name, window, message = max(waits, key=lambda item: item[0])
            if wait:
                raise self._reached(name, window, wait, message)

            self.instance_day.add(self._INSTANCE_KEY, now)
            self.address_minute.add(address, now)
            self.address_day.add(address, now)
            if not carries_allowances or self._key is None:
                return None
            if allowance is None:
                self.new_visitors.add(address, now)
                visitor = secrets.token_hex(8)
            else:
                visitor = allowance.visitor
            minute = (minute[0], minute[1] + 1)
            day = (day[0], day[1] + 1)
            self.visitor_minute.put(visitor, minute, now)
            self.visitor_day.put(visitor, day, now)
            return encode(Allowance(visitor=visitor, minute=minute, day=day), self._key)
