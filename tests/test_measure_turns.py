from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from deadbot.api import create_app
from deadbot.config import Settings
from deadbot.data import CanonicalStore
from scripts.measure_turns import DEFAULT_QUESTIONS, SEQUENCES, measure, measure_sequence, sequence_label, table


class _Agent:
    def stream(self, payload, config, stream_mode="values"):
        question = payload["messages"][-1].content
        finish = {"chat_answer": f"About {question}", "title": "T", "lead": None, "groups": []}
        yield ("values", {"messages": [
            HumanMessage(content=question),
            AIMessage(content="", tool_calls=[{"name": "finish_response", "args": finish, "id": "f", "type": "tool_call"}],
                      usage_metadata={"input_tokens": 700, "output_tokens": 20, "total_tokens": 720}),
            ToolMessage(content="Response delivered to the visitor.", tool_call_id="f", name="finish_response"),
        ]})


def test_measure_returns_one_row_per_question_and_renders_a_table():
    app = create_app(settings=Settings(response_cache=False), store=CanonicalStore(), agent=_Agent())
    rows = measure(["one", "two"], app=app)
    assert [row["question"] for row in rows] == ["one", "two"]
    assert rows[0]["peak_input_tokens"] == 700
    rendered = table(rows)
    assert rendered.splitlines()[0].startswith("| Question |") and "| one |" in rendered


def test_default_questions_include_the_opening_and_set_questions():
    assert "What's on Europe '72: The Complete Recordings?" in DEFAULT_QUESTIONS
    assert "Which songs did they play most in 1977?" in DEFAULT_QUESTIONS
    assert len(DEFAULT_QUESTIONS) == 19


def test_warm_answers_skips_quietly_without_a_model_key(monkeypatch, tmp_path, capsys):
    from scripts.warm_answers import build_bundle

    keyless = Settings(model_provider="openai", openai_api_key=None)
    monkeypatch.setattr(Settings, "from_env", classmethod(lambda cls, *args, **kwargs: keyless))
    bundle = tmp_path / "bundle.json"
    assert build_bundle(bundle, ["one"]) == 0
    assert not bundle.exists()
    assert "skipping" in capsys.readouterr().out


class _RecordingAgent(_Agent):
    def __init__(self):
        self.sent = []

    def stream(self, payload, config, stream_mode="values"):
        self.sent.append([message.content for message in payload["messages"]])
        yield from super().stream(payload, config, stream_mode)


def test_a_sequence_is_asked_as_one_conversation():
    agent = _RecordingAgent()
    app = create_app(settings=Settings(response_cache=False), store=CanonicalStore(), agent=agent)
    rows = measure_sequence(["one", "two"], app=app)
    assert [row["turn"] for row in rows] == [1, 2]
    assert agent.sent[1] == ["one", "About one", "two"]
    assert [row["notebook_bytes"] for row in rows] == [0, 0]
    rendered = table(rows)
    assert "Cached share" in rendered.splitlines()[0] and "Notebook reads" in rendered.splitlines()[0]


def test_the_sequences_cover_the_owners_follow_up_path():
    assert SEQUENCES["europe72"][0] == "What's on Europe '72: The Complete Recordings?"
    assert "Lyceum" in SEQUENCES["europe72"][1] and "Morning Dew" in SEQUENCES["europe72"][2]


def _app_returning_a_token(monkeypatch, agent):
    from deadbot import api as api_module

    app = create_app(settings=Settings(response_cache=False), store=CanonicalStore(), agent=agent)
    original = api_module.ExperienceResponse.model_dump

    def dump(self, *args, **kwargs):
        data = original(self, *args, **kwargs)
        data["notebook"] = "tok"
        return data

    monkeypatch.setattr(api_module.ExperienceResponse, "model_dump", dump)
    return app


def test_the_notebook_token_is_sent_back_only_when_asked(monkeypatch):
    sent_bodies = []
    from fastapi.testclient import TestClient

    original_stream = TestClient.stream

    def spy(self, method, url, **kwargs):
        sent_bodies.append(kwargs.get("json"))
        return original_stream(self, method, url, **kwargs)

    monkeypatch.setattr(TestClient, "stream", spy)
    app = _app_returning_a_token(monkeypatch, _RecordingAgent())

    rows = measure_sequence(["one", "two"], app=app, use_notebook=True)
    assert "notebook" not in sent_bodies[0] and sent_bodies[1]["notebook"] == "tok"
    assert [row["notebook_bytes"] for row in rows] == [0, 3]
    # The request model does not accept a notebook field until Task 4, so only what was sent is asserted here.

    sent_bodies.clear()
    rows = measure_sequence(["one", "two"], app=app, use_notebook=False)
    assert all("notebook" not in body for body in sent_bodies)
    assert [row["notebook_bytes"] for row in rows] == [0, 0]


def test_a_run_is_labeled_by_what_was_sent():
    sent = [{"notebook_bytes": 0}, {"notebook_bytes": 40}]
    none = [{"notebook_bytes": 0}, {"notebook_bytes": 0}]
    assert sequence_label("europe72", True, sent) == "europe72, with the notebook"
    assert sequence_label("europe72", True, none) == "europe72, notebook requested, none sent"
    assert sequence_label("europe72", False, none) == "europe72, without the notebook"
