import json

from deadbot.data import CanonicalStore
from deadbot.postgres import PostgresCanonicalStore
from deadbot.response_cache import ResponseCache, question_key
from deadbot.experience import ExperienceResponse
from test_postgres_store import Connection


def _response(answer: str = "Five shows.", mode: str = "answer") -> ExperienceResponse:
    return ExperienceResponse(thread_id="original", title="Branford", answer=answer, mode=mode)


def _postgres_cache(**kwargs) -> tuple[Connection, ResponseCache]:
    connection = Connection()
    store = PostgresCanonicalStore(connection, schema="canonical")
    # The toy fixture has no metadata table; the fingerprint query needs it.
    connection.raw.execute('CREATE TABLE canonical."deadbot_schema_metadata" ("schema_version" TEXT)')
    connection.raw.execute('INSERT INTO canonical."deadbot_schema_metadata" VALUES (7)')
    connection.raw.execute('CREATE TABLE canonical."selection_evidence" ("selection_evidence_id" TEXT)')
    return connection, ResponseCache(store, **kwargs)


def test_question_key_ignores_case_punctuation_and_spacing():
    assert question_key("What shows did Branford play on?") == question_key("  what shows did branford PLAY on ")
    assert question_key("Franklin's Tower") == question_key("franklins tower")
    assert question_key("?!") == ""


def test_a_store_without_cache_methods_disables_the_cache_quietly():
    cache = ResponseCache(CanonicalStore())
    assert cache.enabled is False
    assert cache.lookup("What shows did Branford play on?", thread_id="t") is None
    cache.remember("What shows did Branford play on?", _response())


def test_a_stored_answer_comes_back_under_the_new_thread():
    _, cache = _postgres_cache()
    question = "What shows did Branford play on?"
    assert cache.lookup(question, thread_id="first") is None
    cache.remember(question, _response())
    hit = cache.lookup("what shows did branford play on", thread_id="second")
    assert hit is not None
    assert hit.answer == "Five shows."
    assert hit.thread_id == "second"


def test_a_gap_answer_is_never_stored():
    _, cache = _postgres_cache()
    cache.remember("Who played the kazoo?", _response("The library cannot say.", mode="gap"))
    assert cache.lookup("Who played the kazoo?", thread_id="t") is None


def test_a_changed_data_version_or_commit_invalidates_the_entry(monkeypatch):
    connection, cache = _postgres_cache()
    cache.remember("Q", _response())
    assert cache.lookup("Q", thread_id="t") is not None
    monkeypatch.setenv("VERCEL_GIT_COMMIT_SHA", "deploy-2")
    assert cache.lookup("Q", thread_id="t") is None
    monkeypatch.delenv("VERCEL_GIT_COMMIT_SHA")
    assert cache.lookup("Q", thread_id="t") is not None
    connection.raw.execute('INSERT INTO canonical."shows" ("show_id") VALUES (\'show-new\')')
    connection.raw.commit()
    assert cache.lookup("Q", thread_id="t") is None


def test_an_expired_entry_is_ignored():
    _, cache = _postgres_cache(max_age_seconds=0)
    cache.remember("Q", _response())
    assert cache.lookup("Q", thread_id="t") is None


def test_a_disabled_cache_never_touches_the_database():
    connection, cache = _postgres_cache(enabled=False)
    before = len(connection.statements)
    cache.remember("Q", _response())
    assert cache.lookup("Q", thread_id="t") is None
    assert len(connection.statements) == before
