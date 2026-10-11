import logging

from fastapi.testclient import TestClient

from deadbot import experience, notebook
from deadbot.api import create_app
from deadbot.config import Settings
from notebook_support import LYCEUM, SECRET, record, store, turn
from test_experience import FakeAgent, StreamingFakeAgent, _CachingStore, _ndjson

EUROPE = "What's on Europe '72: The Complete Recordings?"
EUROPE_ANSWER = "Twenty-two nights, every one released."
FIRST_EXCHANGE = [{"role": "user", "text": EUROPE}, {"role": "assistant", "text": EUROPE_ANSWER}]


def _client(agent, *, secret=SECRET, data=None, **settings):
    return TestClient(create_app(settings=Settings(notebook_secret=secret, **settings), store=data or store(), agent=agent))


def _token(*turns):
    book = notebook.Notebook()
    for index, (question, answer, calls) in enumerate(turns):
        book, _ = record(book, question, answer, calls, prefix=f"t{index}")
    return book, notebook.encode(book, SECRET)


def test_an_answer_carries_a_signed_notebook_of_its_research():
    agent = FakeAgent(turn("Tell me about May 26, 1972.", "The last Lyceum night.", LYCEUM))
    body = _client(agent).post("/api/experience", json={"question": "Tell me about May 26, 1972."}).json()
    assert body["notebook"].startswith("v1.")
    book = notebook.decode(body["notebook"], SECRET)
    assert book.turns == 1
    assert [(entry.tool, entry.turn) for entry in book.entries] == [("get_show", 1)]
    assert "gd-1972-05-26" in book.entries[0].ids
    assert book.pages[0].answer_key == notebook.answer_key("The last Lyceum night.")


def test_the_streamed_response_event_carries_the_notebook_too():
    agent = StreamingFakeAgent(turn("Tell me about May 26, 1972.", "The last Lyceum night.", LYCEUM))
    events = _ndjson(_client(agent).post("/api/experience/stream", json={"question": "Tell me about May 26, 1972."}).text)
    assert events[-1]["type"] == "response"
    assert notebook.decode(events[-1]["response"]["notebook"], SECRET).turns == 1


def test_a_follow_up_adds_its_turn_to_the_notebook_it_was_sent():
    first, token = _token((EUROPE, EUROPE_ANSWER, LYCEUM))
    agent = FakeAgent(turn("And Morning Dew?", "It closed the Lyceum run.", [("get_song", {"song_id_or_title": "Morning Dew"})]))
    body = _client(agent).post("/api/experience", json={
        "question": "And Morning Dew?", "thread_id": "browser-1", "conversation": FIRST_EXCHANGE, "notebook": token,
    }).json()
    book = notebook.decode(body["notebook"], SECRET)
    assert book.turns == 2
    assert [(entry.tool, entry.turn) for entry in book.entries] == [("get_show", 1), ("get_song", 2)]


def test_a_tampered_notebook_is_ignored_and_the_visitor_still_gets_an_answer(caplog):
    _, token = _token((EUROPE, EUROPE_ANSWER, LYCEUM))
    tampered = token[:-4] + ("AAAA" if not token.endswith("AAAA") else "BBBB")
    agent = FakeAgent(turn("And Morning Dew?", "It closed the run.", []))
    with caplog.at_level(logging.WARNING, logger="deadbot.notebook"):
        response = _client(agent).post("/api/experience", json={"question": "And Morning Dew?", "conversation": FIRST_EXCHANGE, "notebook": tampered})
    assert response.status_code == 200
    assert notebook.decode(response.json()["notebook"], SECRET).turns == 1
    assert "signature" in caplog.text


def test_without_a_secret_there_is_no_notebook_and_one_log_line(monkeypatch, caplog):
    monkeypatch.setattr(notebook, "_missing_secret_logged", False)
    client = _client(FakeAgent(turn("Q", "A", LYCEUM)), secret=None)
    with caplog.at_level(logging.WARNING, logger="deadbot.notebook"):
        first = client.post("/api/experience", json={"question": "Q"}).json()
        second = client.post("/api/experience", json={"question": "Q"}).json()
    assert first["notebook"] is None and second["notebook"] is None
    assert caplog.text.count("DEADBOT_NOTEBOOK_SECRET is not set") == 1


def test_an_over_long_or_malformed_notebook_never_costs_the_visitor_their_answer(caplog):
    assert notebook.TOKEN_BYTE_CEILING < experience.NOTEBOOK_TOKEN_MAX_CHARS
    agent = FakeAgent(turn("Q", "A", []))
    client = _client(agent)
    with caplog.at_level(logging.WARNING):
        for token in ("x" * (experience.NOTEBOOK_TOKEN_MAX_CHARS + 1), 12345, ["v1"]):
            response = client.post("/api/experience", json={"question": "Q", "notebook": token})
            assert response.status_code == 200
            assert notebook.decode(response.json()["notebook"], SECRET).turns == 1
    assert "research notebook" in caplog.text
    assert "x" * 50 not in caplog.text


def test_a_cached_starter_answer_carries_its_notebook_and_notebook_requests_skip_the_cache():
    data = _CachingStore()
    agent = FakeAgent(turn(EUROPE, EUROPE_ANSWER, LYCEUM))
    client = _client(agent, data=data)
    live = client.post("/api/experience", json={"question": EUROPE}).json()
    cached = client.post("/api/experience", json={"question": EUROPE}).json()
    assert len(agent.calls) == 1
    assert cached["notebook"] == live["notebook"]
    client.post("/api/experience", json={"question": EUROPE, "notebook": live["notebook"]})
    assert len(agent.calls) == 2
