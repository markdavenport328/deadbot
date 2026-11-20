import itertools
import json
import sqlite3

import pytest

from deadbot.data import CanonicalStore
from deadbot.response_cache import ResponseCache, question_key
from deadbot.experience import ExperienceResponse
from sqlite_toy import RecordingStore, toy_store


def _response(answer: str = "Five shows.", mode: str = "answer") -> ExperienceResponse:
    return ExperienceResponse(thread_id="original", lead=answer, mode=mode)


@pytest.fixture
def toy_cache(tmp_path):
    """Make a cache over its own toy catalog and its own answers file, as a fresh instance would have."""

    stores: list[RecordingStore] = []
    numbers = itertools.count()

    def make(**kwargs) -> tuple[RecordingStore, ResponseCache]:
        folder = tmp_path / f"instance-{next(numbers)}"
        folder.mkdir()
        store = toy_store(folder, with_metadata=True)
        stores.append(store)
        return store, ResponseCache(store, **kwargs)

    yield make
    for store in stores:
        store.close()


def test_question_key_ignores_case_punctuation_and_spacing():
    assert question_key("What shows did Branford play on?") == question_key("  what shows did branford PLAY on ")
    assert question_key("Franklin's Tower") == question_key("franklins tower")
    assert question_key("?!") == ""


def test_a_store_without_cache_methods_disables_the_cache_quietly():
    cache = ResponseCache(CanonicalStore())
    assert cache.enabled is False
    assert cache.lookup("What shows did Branford play on?", thread_id="t") is None
    cache.remember("What shows did Branford play on?", _response())


def test_a_stored_answer_comes_back_under_the_new_thread(toy_cache):
    _, cache = toy_cache()
    question = "What shows did Branford play on?"
    assert cache.lookup(question, thread_id="first") is None
    cache.remember(question, _response())
    hit = cache.lookup("what shows did branford play on", thread_id="second")
    assert hit is not None
    assert hit.lead == "Five shows."
    assert hit.thread_id == "second"


def test_a_gap_answer_is_never_stored(toy_cache):
    _, cache = toy_cache()
    cache.remember("Who played the kazoo?", _response("The library cannot say.", mode="gap"))
    assert cache.lookup("Who played the kazoo?", thread_id="t") is None


def test_a_changed_data_version_or_commit_invalidates_the_entry(monkeypatch, toy_cache):
    store, cache = toy_cache()
    cache.remember("Q", _response())
    assert cache.lookup("Q", thread_id="t") is not None
    monkeypatch.setenv("VERCEL_GIT_COMMIT_SHA", "deploy-2")
    assert cache.lookup("Q", thread_id="t") is None
    monkeypatch.delenv("VERCEL_GIT_COMMIT_SHA")
    assert cache.lookup("Q", thread_id="t") is not None
    # The catalog file is read as immutable, so a new build replaces it while
    # no connection is open.
    store.close()
    db = sqlite3.connect(store.path)
    db.execute('INSERT INTO "shows" ("show_id") VALUES (\'show-new\')')
    db.commit()
    db.close()
    assert cache.lookup("Q", thread_id="t") is None


def test_an_expired_entry_is_ignored(toy_cache):
    _, cache = toy_cache(max_age_seconds=0)
    cache.remember("Q", _response())
    assert cache.lookup("Q", thread_id="t") is None


def test_a_disabled_cache_never_touches_the_database(toy_cache):
    store, cache = toy_cache(enabled=False)
    before = len(store.statements)
    cache.remember("Q", _response())
    assert cache.lookup("Q", thread_id="t") is None
    assert len(store.statements) == before
    assert not store._cache_path.exists()


def test_a_local_checkout_keys_cached_answers_to_its_commit(monkeypatch):
    # Without a deploy variable the key used to read "unknown", so a local
    # server kept serving answers cached by earlier code.
    from deadbot import response_cache

    monkeypatch.delenv("VERCEL_GIT_COMMIT_SHA", raising=False)
    monkeypatch.delenv("DEADBOT_GIT_COMMIT", raising=False)
    commit = response_cache.deployed_commit()
    assert commit != "unknown" and len(commit) == 40


def test_a_bundle_of_exported_answers_seeds_a_fresh_cache(tmp_path, toy_cache):
    from deadbot.response_cache import ResponseCache as Cache

    _, producer = toy_cache()
    producer.remember("What shows did Branford play on?", _response())
    entries = producer.export(["What shows did Branford play on?", "A question nobody asked"])
    assert [entry["question"] for entry in entries] == ["What shows did Branford play on?"]

    bundle = tmp_path / "warm-answers.json"
    bundle.write_text(json.dumps(entries), encoding="utf-8")
    _, fresh = toy_cache()
    assert fresh.lookup("What shows did Branford play on?", thread_id="t") is None
    assert fresh.seed_from_bundle(bundle) == 1
    hit = fresh.lookup("what shows did branford play on", thread_id="new")
    assert hit is not None and hit.lead == "Five shows." and hit.thread_id == "new"


def test_a_bundle_made_for_another_version_is_ignored(tmp_path, toy_cache):
    _, producer = toy_cache()
    producer.remember("What shows did Branford play on?", _response())
    stale = [{**entry, "data_version": "older"} for entry in producer.export(["What shows did Branford play on?"])]
    _, fresh = toy_cache()
    assert fresh.seed(stale) == 0
    assert fresh.lookup("What shows did Branford play on?", thread_id="t") is None


def test_a_missing_or_broken_bundle_changes_nothing(tmp_path, toy_cache):
    _, cache = toy_cache()
    assert cache.seed_from_bundle(tmp_path / "absent.json") == 0
    broken = tmp_path / "broken.json"
    broken.write_text("{not json", encoding="utf-8")
    assert cache.seed_from_bundle(broken) == 0


def test_an_exported_answer_keeps_its_notebook_through_the_bundle(toy_cache):
    _, cache = toy_cache()
    question = "What's on Europe '72: The Complete Recordings?"
    cache.remember(question, ExperienceResponse(thread_id="original", lead="Twenty-two nights.", notebook="v1.body.sig"))
    (entry,) = cache.export([question])
    assert entry["response"]["notebook"] == "v1.body.sig"
    _, fresh = toy_cache()
    assert fresh.seed([entry]) == 1
    assert fresh.lookup(question, thread_id="new").notebook == "v1.body.sig"
