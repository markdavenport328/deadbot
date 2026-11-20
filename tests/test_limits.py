"""Usage limits: what a visitor, an address and an instance may send to the model."""

import json
import logging

import pytest
from fastapi.testclient import TestClient
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from deadbot import limits
from deadbot.api import TOOK_TOO_LONG, create_app
from deadbot.config import Settings
from deadbot.data import CanonicalStore
from deadbot.graph import TurnBudgetExceeded
from deadbot.limits import LimitReached, Limits


SECRET = "a-test-secret"
ASK = {"question": "Tell me about Veneta"}


class Clock:
    def __init__(self, now=1_000_000.0):
        self.now = now

    def __call__(self):
        return self.now


def _limits(clock=None, **settings):
    return Limits(Settings(notebook_secret=SECRET, **settings), clock=clock or Clock())


def _turn(lead="An answer."):
    plan = {"lead": lead, "groups": []}
    return [
        HumanMessage(content="q"),
        AIMessage(content="", tool_calls=[{"name": "finish_response", "args": plan, "id": "f1", "type": "tool_call"}]),
        ToolMessage(content="Response delivered to the visitor.", tool_call_id="f1", name="finish_response"),
    ]


class Agent:
    def __init__(self, error=None):
        self.calls = []
        self.error = error

    def invoke(self, payload, config):
        self.calls.append((payload, config))
        if self.error:
            raise self.error
        return {"messages": _turn()}


def _app(agent=None, **settings):
    settings.setdefault("notebook_secret", SECRET)
    app = create_app(settings=Settings(**settings), store=CanonicalStore(), agent=agent or Agent())
    app.state.limits.clock = Clock()
    return app


# --- the windows and the allowance, without the API ----------------------------------


def test_when_rounds_up_so_it_never_promises_too_early():
    assert limits.when(12) == "in under a minute"
    assert limits.when(58) == "in about a minute"
    assert limits.when(61) == "in about 2 minutes"
    assert limits.when(50 * 60 + 1) == "in about an hour"
    assert limits.when(5 * 3600 + 1) == "in about 6 hours"


def test_a_visitor_is_counted_through_the_allowance_they_carry():
    clock = Clock()
    book = _limits(clock, visitor_limit_per_minute=2)
    token = book.admit("1.1.1.1", None)
    token = book.admit("1.1.1.1", token)
    with pytest.raises(LimitReached) as reached:
        book.admit("1.1.1.1", token)
    assert reached.value.name == "visitor per minute"
    assert reached.value.retry_after == 60
    assert reached.value.message == "That is a lot of questions at once. Please ask again in about a minute."
    clock.now += 61
    assert book.admit("1.1.1.1", token)


def test_the_allowance_follows_the_visitor_to_another_instance():
    clock = Clock()
    first, second = _limits(clock, visitor_limit_per_day=3), _limits(clock, visitor_limit_per_day=3)
    token = first.admit("1.1.1.1", None)
    token = second.admit("2.2.2.2", token)
    token = first.admit("3.3.3.3", token)
    with pytest.raises(LimitReached) as reached:
        second.admit("4.4.4.4", token)
    assert reached.value.name == "visitor per day"
    assert reached.value.message == (
        "You have reached today's limit for questions during the beta. You can ask again in about 24 hours."
    )


def test_people_behind_one_address_each_have_their_own_allowance():
    book = _limits(visitor_limit_per_minute=1, rate_limit_per_minute=10)
    one = book.admit("9.9.9.9", None)
    two = book.admit("9.9.9.9", None)
    for token in (one, two):
        with pytest.raises(LimitReached):
            book.admit("9.9.9.9", token)
    assert book.admit("9.9.9.9", None)  # a third person at that address still gets in


def test_replaying_an_old_allowance_does_not_reset_the_count_on_the_instance_that_saw_it():
    book = _limits(visitor_limit_per_minute=2)
    first = book.admit("1.1.1.1", None)
    book.admit("1.1.1.1", first)
    with pytest.raises(LimitReached):
        book.admit("1.1.1.1", first)  # the cookie says one question; this instance remembers two


def test_throwing_the_allowance_away_runs_into_the_address_limits():
    book = _limits(new_visitors_per_day=3, rate_limit_per_minute=100, rate_limit_per_day=100)
    for _ in range(3):
        book.admit("1.1.1.1", None)
    with pytest.raises(LimitReached) as reached:
        book.admit("1.1.1.1", "not-a-real-token.0000")
    assert reached.value.name == "new visitors per address per day"
    assert book.admit("2.2.2.2", None)  # another address is unaffected


def test_an_altered_or_foreign_allowance_is_not_honoured():
    book = _limits()
    token = book.admit("1.1.1.1", None)
    body, _, signature = token.partition(".")
    key = limits.signing_key(SECRET)
    assert limits.decode(token, key) is not None
    assert limits.decode(body + "A." + signature, key) is None
    assert limits.decode(token, limits.signing_key("another-secret")) is None
    assert limits.decode("x" * 500, key) is None
    assert limits.decode(None, key) is None


def test_the_allowance_holds_a_random_id_and_counts_and_nothing_else():
    token = _limits().admit("203.0.113.7", None)
    allowance = limits.decode(token, limits.signing_key(SECRET))
    assert "203.0.113.7" not in token
    assert len(allowance.visitor) == 16 and allowance.minute[1] == 1 and allowance.day[1] == 1


def test_the_address_and_instance_ceilings_hold_without_any_cookie():
    book = Limits(Settings(rate_limit_per_minute=100, rate_limit_per_day=2), clock=Clock())
    assert book.admit("1.1.1.1", None) is None  # no signing secret, so no allowance to carry
    book.admit("1.1.1.1", None)
    with pytest.raises(LimitReached) as reached:
        book.admit("1.1.1.1", None)
    assert reached.value.name == "address per day"

    busy = _limits(instance_limit_per_day=2)
    busy.admit("1.1.1.1", None)
    busy.admit("2.2.2.2", None)
    with pytest.raises(LimitReached) as reached:
        busy.admit("3.3.3.3", None)
    assert reached.value.name == "instance per day"
    assert reached.value.message.startswith("Deadbot has answered all the questions it can for now.")


def test_a_limit_of_zero_is_off_and_without_limits_turns_them_all_off():
    book = Limits(Settings(notebook_secret=SECRET).without_limits(), clock=Clock())
    for _ in range(600):
        assert book.admit("1.1.1.1", None) is None


def test_a_tripped_limit_logs_which_limit_and_not_who(caplog):
    book = _limits(visitor_limit_per_minute=1)
    token = book.admit("203.0.113.7", None)
    with caplog.at_level(logging.WARNING, logger="deadbot.limits"), pytest.raises(LimitReached):
        book.admit("203.0.113.7", token)
    (record,) = caplog.records
    assert "visitor per minute" in record.getMessage()
    assert "203.0.113.7" not in record.getMessage() and limits.decode(token, limits.signing_key(SECRET)).visitor not in record.getMessage()


def test_a_windows_memory_is_swept_rather_than_growing_forever(monkeypatch):
    monkeypatch.setattr(limits, "SWEEP_AT", 10)
    window = limits.Window(5, 60)
    for number in range(10):
        window.add(f"old-{number}", 0.0)
    window.add("new", 1_000.0)
    assert set(window._states) == {"new"}


# --- through the API ----------------------------------------------------------------


def test_a_visitor_over_the_limit_gets_a_429_the_web_client_can_show():
    client = TestClient(_app(visitor_limit_per_minute=2))
    assert [client.post("/api/experience", json=ASK).status_code for _ in range(2)] == [200, 200]
    refused = client.post("/api/experience", json=ASK)
    assert refused.status_code == 429
    # ask-client.ts shows an error body's "detail" string to the visitor as it is.
    assert refused.json() == {"detail": "That is a lot of questions at once. Please ask again in about a minute."}
    assert refused.headers["retry-after"] == "60"


def test_the_streaming_endpoint_refuses_with_the_same_json_before_any_stream_starts():
    agent = Agent()
    client = TestClient(_app(agent, visitor_limit_per_minute=1))
    first = client.post("/api/experience/stream", json=ASK)
    assert first.status_code == 200 and "deadbot_allowance=" in first.headers["set-cookie"]
    refused = client.post("/api/experience/stream", json=ASK)
    assert refused.status_code == 429
    assert refused.headers["content-type"].startswith("application/json")
    assert refused.json()["detail"].startswith("That is a lot of questions at once.")
    assert len(agent.calls) == 1


def test_the_allowance_cookie_is_http_only_and_scoped_to_the_api():
    client = TestClient(_app())
    cookie = client.post("/api/experience", json=ASK).headers["set-cookie"]
    assert cookie.startswith("deadbot_allowance=")
    assert "HttpOnly" in cookie and "Path=/api" in cookie and "SameSite=Lax" in cookie and "Secure" not in cookie
    secure = TestClient(_app(), base_url="https://testserver").post("/api/experience", json=ASK).headers["set-cookie"]
    assert secure.endswith("; Secure")


class _OneAnswerCache:
    """Stands in for the response cache: remembers the first answer and serves it after."""

    def __init__(self):
        self.stored = None

    def lookup(self, question, *, thread_id):
        return self.stored.model_copy(update={"thread_id": thread_id}) if self.stored else None

    def remember(self, question, response):
        self.stored = response


def test_a_stored_answer_does_not_count_against_the_visitor():
    agent = Agent()
    app = _app(agent, visitor_limit_per_minute=1, visitor_limit_per_day=1, rate_limit_per_minute=1)
    app.state.response_cache = _OneAnswerCache()
    client = TestClient(app)
    assert client.post("/api/experience", json=ASK).status_code == 200
    for _ in range(5):
        served = client.post("/api/experience", json=ASK)
        assert served.status_code == 200 and "set-cookie" not in served.headers
    streamed = client.post("/api/experience/stream", json=ASK)
    assert [json.loads(line)["type"] for line in streamed.text.splitlines()] == ["status", "response"]
    assert len(agent.calls) == 1
    # A follow-up is never served from the store, so it is counted and refused.
    follow_up = {**ASK, "conversation": [{"role": "user", "text": "q"}, {"role": "assistant", "text": "a"}]}
    assert client.post("/api/experience", json=follow_up).status_code == 429


def test_stored_answers_still_spend_the_lookup_budget():
    app = _app(grid_rate_limit_per_minute=2)
    app.state.response_cache = _OneAnswerCache()
    client = TestClient(app)
    assert [client.post("/api/experience", json=ASK).status_code for _ in range(4)] == [200, 200, 200, 429]


def test_a_forwarded_address_is_believed_only_where_the_platform_overwrites_it():
    untrusted = TestClient(_app(rate_limit_per_minute=1, visitor_limit_per_minute=0, visitor_limit_per_day=0))
    codes = [
        untrusted.post("/api/experience", json=ASK, headers={"x-forwarded-for": f"198.51.100.{n}"}).status_code
        for n in range(2)
    ]
    assert codes == [200, 429]  # a script cannot change its address by writing a header

    trusted = TestClient(_app(
        rate_limit_per_minute=1, visitor_limit_per_minute=0, visitor_limit_per_day=0, trust_forwarded_ip=True,
    ))
    codes = [
        trusted.post("/api/experience", json=ASK, headers={"x-vercel-forwarded-for": address}).status_code
        for address in ("198.51.100.1", "198.51.100.2", "198.51.100.1")
    ]
    assert codes == [200, 200, 429]


def test_an_oversized_transcript_loses_its_oldest_turns_before_the_model_sees_it(caplog):
    agent = Agent()
    client = TestClient(_app(agent, conversation_max_chars=10_000))
    conversation = []
    for number in range(4):
        conversation.append({"role": "user", "text": f"Question {number}"})
        conversation.append({"role": "assistant", "text": f"Answer {number} " + "x" * 3_900})
    with caplog.at_level(logging.WARNING, logger="deadbot.api"):
        assert client.post("/api/experience", json={**ASK, "conversation": conversation}).status_code == 200
    sent = [message.content for message in agent.calls[0][0]["messages"]]
    assert [text[:10] for text in sent] == ["Question 2", "Answer 2 x", "Question 3", "Answer 3 x", "Tell me ab"]
    assert sum(len(text) for text in sent[:-1]) <= 10_000
    assert "oldest conversation turns" in caplog.text


def test_a_turn_out_of_time_tells_the_visitor_so_on_both_endpoints():
    agent = Agent(error=TurnBudgetExceeded("out of time"))
    client = TestClient(_app(agent))
    plain = client.post("/api/experience", json=ASK)
    assert plain.status_code == 504 and plain.json() == {"detail": TOOK_TOO_LONG}
    streamed = client.post("/api/experience/stream", json=ASK)
    events = [json.loads(line) for line in streamed.text.splitlines()]
    assert events[-1] == {"type": "error", "detail": TOOK_TOO_LONG}


LIMIT_VARIABLES = (
    "DEADBOT_PROMPT_CACHE_SHARDS", "DEADBOT_PROMPT_CACHE_BREAKPOINT", "DEADBOT_TRUST_FORWARDED_IP",
    "DEADBOT_VISITOR_LIMIT_PER_MINUTE", "DEADBOT_VISITOR_LIMIT_PER_DAY", "DEADBOT_RATE_LIMIT_PER_DAY",
    "DEADBOT_NEW_VISITORS_PER_DAY", "DEADBOT_INSTANCE_LIMIT_PER_DAY", "DEADBOT_CONVERSATION_MAX_CHARS",
    "DEADBOT_MODEL_TIMEOUT_SECONDS", "DEADBOT_MODEL_MAX_RETRIES", "DEADBOT_TURN_BUDGET_SECONDS",
)


def test_limit_defaults_suit_a_small_beta(monkeypatch, tmp_path):
    for name in (*LIMIT_VARIABLES, "VERCEL", "DEADBOT_MODEL_PROVIDER"):
        monkeypatch.delenv(name, raising=False)
    settings = Settings.from_env(tmp_path / "no.env")
    assert (settings.visitor_limit_per_minute, settings.visitor_limit_per_day) == (6, 40)
    assert (settings.rate_limit_per_minute, settings.rate_limit_per_day, settings.new_visitors_per_day) == (10, 150, 20)
    assert settings.instance_limit_per_day == 500 and settings.conversation_max_chars == 24_000
    assert (settings.model_timeout_seconds, settings.model_max_retries) == (25, 1)
    assert settings.prompt_cache_shards == 1 and settings.prompt_cache_breakpoint is False
    # Off Vercel no proxy overwrites the forwarded headers, and a local model has no 60-second function.
    assert settings.trust_forwarded_ip is False and settings.turn_budget_seconds == 0

    monkeypatch.setenv("VERCEL", "1")
    monkeypatch.setenv("DEADBOT_MODEL_PROVIDER", "openai")
    hosted = Settings.from_env(tmp_path / "no.env")
    assert hosted.trust_forwarded_ip is True and hosted.turn_budget_seconds == 55
    # Two silent waits and the pause between them fit inside the function's 60 seconds.
    assert (hosted.model_max_retries + 1) * hosted.model_timeout_seconds < hosted.turn_budget_seconds < 60


def test_every_limit_is_read_from_the_environment(monkeypatch, tmp_path):
    for number, name in enumerate(LIMIT_VARIABLES, start=2):
        monkeypatch.setenv(name, "true" if name.endswith(("BREAKPOINT", "FORWARDED_IP")) else str(number))
    settings = Settings.from_env(tmp_path / "no.env")
    assert settings.prompt_cache_shards == 2 and settings.prompt_cache_breakpoint and settings.trust_forwarded_ip
    assert [
        settings.visitor_limit_per_minute, settings.visitor_limit_per_day, settings.rate_limit_per_day,
        settings.new_visitors_per_day, settings.instance_limit_per_day, settings.conversation_max_chars,
        settings.model_timeout_seconds, settings.model_max_retries, settings.turn_budget_seconds,
    ] == list(range(5, 14))


def test_every_limit_variable_is_documented_in_the_example_file():
    from deadbot.config import ROOT

    example = (ROOT / ".env.example").read_text(encoding="utf-8")
    for name in (*LIMIT_VARIABLES, "DEADBOT_RATE_LIMIT_PER_MINUTE", "DEADBOT_GRID_RATE_LIMIT_PER_MINUTE"):
        assert name in example, name


def test_the_model_client_gets_the_timeout_and_retries_from_settings():
    from deadbot.models import create_model_provider

    streamed = create_model_provider(Settings(model_provider="openai", model_streaming=True))
    assert (streamed.timeout, streamed.max_retries) == (25, 1)
    # Unstreamed, nothing arrives until the whole answer is written.
    whole = create_model_provider(Settings(model_provider="openai", model_streaming=False))
    assert whole.timeout == 90


def test_the_turn_budget_reaches_the_agent_as_a_deadline_only_when_set():
    agent = Agent()
    TestClient(_app(agent, turn_budget_seconds=55)).post("/api/experience", json=ASK)
    assert "deadline" in agent.calls[0][1]["configurable"]
    unhurried = Agent()
    TestClient(_app(unhurried)).post("/api/experience", json=ASK)
    assert "deadline" not in unhurried.calls[0][1]["configurable"]
