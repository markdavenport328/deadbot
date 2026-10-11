import logging

from fastapi.testclient import TestClient
from langchain_core.messages import AIMessage, HumanMessage

from deadbot import composition, experience, notebook
from deadbot.api import create_app
from deadbot.config import Settings
from deadbot.finish import FOCUS_MESSAGE_NAME, build_experience_response
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


def test_each_turns_research_follows_its_answer_and_the_question_comes_last():
    book, token = _token((EUROPE, EUROPE_ANSWER, LYCEUM))
    agent = FakeAgent(turn("Compare the Lyceum nights.", "Four nights.", []))
    _client(agent).post("/api/experience", json={
        "question": "Compare the Lyceum nights.", "thread_id": "browser-1", "conversation": FIRST_EXCHANGE, "notebook": token,
    })
    sent = agent.calls[0][0]["messages"]
    assert [message.type for message in sent] == ["human", "ai", "human", "human"]
    assert sent[2].name == composition.NOTEBOOK_MESSAGE_NAME
    assert sent[2].content.startswith("Research notebook, turn 1:")
    assert f"[{book.entries[0].key}] get_show gd-1972-05-26" in sent[2].content
    assert sent[3].content == "Compare the Lyceum nights."


def test_a_new_turn_leaves_every_earlier_message_byte_identical():
    first, first_token = _token((EUROPE, EUROPE_ANSWER, LYCEUM))
    second, _ = record(first, "Tell me about May 26.", "The last Lyceum night.", [("get_song", {"song_id_or_title": "Morning Dew"})], prefix="t1")
    second_token = notebook.encode(second, SECRET)
    agent_one = FakeAgent(turn("Tell me about May 26.", "The last Lyceum night.", []))
    _client(agent_one).post("/api/experience", json={"question": "Tell me about May 26.", "conversation": FIRST_EXCHANGE, "notebook": first_token})
    agent_two = FakeAgent(turn("And its Morning Dew?", "Out of The Other One.", []))
    two_exchanges = FIRST_EXCHANGE + [{"role": "user", "text": "Tell me about May 26."}, {"role": "assistant", "text": "The last Lyceum night."}]
    _client(agent_two).post("/api/experience", json={"question": "And its Morning Dew?", "conversation": two_exchanges, "notebook": second_token})
    one = [message.content for message in agent_one.calls[0][0]["messages"]][:-1]
    two = [message.content for message in agent_two.calls[0][0]["messages"]]
    assert two[: len(one)] == one
    assert two[len(one) + 2].startswith("Research notebook, turn 2:")


def test_a_click_on_something_already_researched_is_flagged_before_the_question_beside_the_grid_note():
    book, token = _token((EUROPE, EUROPE_ANSWER, LYCEUM))
    question = "Tell me about the Morning Dew from May 26, 1972."
    agent = FakeAgent(turn(question, "Out of The Other One.", []))
    _client(agent).post("/api/experience", json={
        "question": question,
        "conversation": FIRST_EXCHANGE,
        "notebook": token,
        "focus": {"label": "Morning Dew \u00b7 May 26, 1972", "block_type": "grid", "block_id": "grid:abc",
                  "ids": ["gd-1972-05-26", "song-morning-dew"], "facts": []},
    })
    sent = agent.calls[0][0]["messages"]
    # [... flags, question, the grid's own focus note]: separate messages.
    assert sent[-3].name == composition.NOTEBOOK_MESSAGE_NAME
    assert sent[-3].content.startswith("Already in the research notebook for what the visitor clicked:")
    assert book.entries[0].key in sent[-3].content
    assert sent[-2].content == question
    assert sent[-1].name == FOCUS_MESSAGE_NAME
    assert "Already in the research notebook" not in sent[-1].content


def test_a_focus_with_nothing_researched_adds_no_flags_message():
    agent = FakeAgent(turn("Q", "A", []))
    _client(agent).post("/api/experience", json={
        "question": "Q", "conversation": FIRST_EXCHANGE,
        "focus": {"label": "x", "block_type": "grid", "block_id": "g", "ids": ["gd-1972-05-26"], "facts": []},
    })
    sent = agent.calls[0][0]["messages"]
    assert [message.name for message in sent if message.type == "human"].count(composition.NOTEBOOK_MESSAGE_NAME) == 0


def test_a_notebook_without_a_transcript_still_gets_its_own_invocation_thread_and_the_cache_key():
    _, token = _token((EUROPE, EUROPE_ANSWER, LYCEUM))
    agent = FakeAgent(turn("Q", "A", []))
    _client(agent).post("/api/experience", json={"question": "Q", "thread_id": "browser-1", "notebook": token})
    config = agent.calls[0][1]
    assert config["configurable"]["thread_id"].startswith("browser-1:request:")
    assert config["configurable"]["prompt_cache_key"] == "browser-1"
    assert isinstance(config["configurable"]["notebook"], notebook.Notebook)


def test_the_streamed_run_gets_the_same_config():
    _, token = _token((EUROPE, EUROPE_ANSWER, LYCEUM))
    agent = StreamingFakeAgent(turn("Q", "A", []))
    _client(agent).post("/api/experience/stream", json={"question": "Q", "thread_id": "browser-1", "notebook": token})
    config = agent.calls[0][1]
    assert config["configurable"]["prompt_cache_key"] == "browser-1"
    assert isinstance(config["configurable"]["notebook"], notebook.Notebook)


def test_notebook_messages_stay_out_of_the_visible_conversation():
    messages = [
        HumanMessage(content="q1"), AIMessage(content="a1"),
        notebook.notebook_message("Research notebook, turn 1: what the tools returned"),
        *turn("q2", "a2", []),
    ]
    response = build_experience_response("q2", "t", messages, store())
    assert [item.text for item in response.conversation] == ["q1", "a1", "q2", "a2"]
