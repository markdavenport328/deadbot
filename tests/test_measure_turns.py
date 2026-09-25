from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from deadbot.api import create_app
from deadbot.config import Settings
from deadbot.data import CanonicalStore
from scripts.measure_turns import DEFAULT_QUESTIONS, measure, table


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
    assert "Which official releases cover 1972?" in DEFAULT_QUESTIONS
    assert "Which songs did they play most in 1977?" in DEFAULT_QUESTIONS
    assert len(DEFAULT_QUESTIONS) == 19
