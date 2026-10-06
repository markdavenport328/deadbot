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


def test_a_local_checkout_keys_cached_answers_to_its_commit(monkeypatch):
    # Without a deploy variable the key used to read "unknown", so a local
    # server kept serving answers cached by earlier code.
    from deadbot import response_cache

    monkeypatch.delenv("VERCEL_GIT_COMMIT_SHA", raising=False)
    monkeypatch.delenv("DEADBOT_GIT_COMMIT", raising=False)
    commit = response_cache.deployed_commit()
    assert commit != "unknown" and len(commit) == 40


def test_a_bundle_of_exported_answers_seeds_a_fresh_cache(tmp_path):
    from deadbot.response_cache import ResponseCache as Cache

    _, producer = _postgres_cache()
    producer.remember("What shows did Branford play on?", _response())
    entries = producer.export(["What shows did Branford play on?", "A question nobody asked"])
    assert [entry["question"] for entry in entries] == ["What shows did Branford play on?"]

    bundle = tmp_path / "warm-answers.json"
    bundle.write_text(json.dumps(entries), encoding="utf-8")
    _, fresh = _postgres_cache()
    assert fresh.lookup("What shows did Branford play on?", thread_id="t") is None
    assert fresh.seed_from_bundle(bundle) == 1
    hit = fresh.lookup("what shows did branford play on", thread_id="new")
    assert hit is not None and hit.answer == "Five shows." and hit.thread_id == "new"


def test_a_bundle_made_for_another_version_is_ignored(tmp_path):
    _, producer = _postgres_cache()
    producer.remember("What shows did Branford play on?", _response())
    stale = [{**entry, "data_version": "older"} for entry in producer.export(["What shows did Branford play on?"])]
    _, fresh = _postgres_cache()
    assert fresh.seed(stale) == 0
    assert fresh.lookup("What shows did Branford play on?", thread_id="t") is None


def test_a_missing_or_broken_bundle_changes_nothing(tmp_path):
    _, cache = _postgres_cache()
    assert cache.seed_from_bundle(tmp_path / "absent.json") == 0
    broken = tmp_path / "broken.json"
    broken.write_text("{not json", encoding="utf-8")
    assert cache.seed_from_bundle(broken) == 0
