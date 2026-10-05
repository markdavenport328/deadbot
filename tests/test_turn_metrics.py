import json
import logging

from fastapi.testclient import TestClient
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from deadbot.api import create_app
from deadbot.config import Settings
from deadbot.data import CanonicalStore
from deadbot.turn_metrics import turn_metrics


def _turn():
    return [
        HumanMessage(content="an earlier question"),
        AIMessage(content="an earlier answer"),
        HumanMessage(content="Which releases cover 1972?"),
        AIMessage(content="", tool_calls=[{"name": "get_album", "args": {}, "id": "a", "type": "tool_call"}],
                  usage_metadata={"input_tokens": 1200, "output_tokens": 40, "total_tokens": 1240}),
        ToolMessage(content='{"release":{}}', tool_call_id="a", name="get_album"),
        ToolMessage(content='{"rows":[],"_truncated":[{"path":"rows"}]}', tool_call_id="b", name="query_catalog"),
        AIMessage(content="", usage_metadata={"input_tokens": 5000, "output_tokens": 300, "total_tokens": 5300}),
    ]


def test_metrics_cover_only_this_turn():
    metrics = turn_metrics("Which releases cover 1972?", _turn(), started=10.0, first_answer_at=14.5, finished_at=20.0, error=None)
    assert metrics["model_calls"] == 2
    assert metrics["peak_input_tokens"] == 5000
    assert metrics["total_input_tokens"] == 6200
    assert [tool["name"] for tool in metrics["tools"]] == ["get_album", "query_catalog"]
    assert metrics["tools"][1]["truncated"] is True and metrics["tools"][0]["truncated"] is False
    assert metrics["largest_tool_result_chars"] == len('{"rows":[],"_truncated":[{"path":"rows"}]}')
    assert metrics["seconds_to_first_answer"] == 4.5 and metrics["seconds_total"] == 10.0
    json.dumps(metrics)  # serializable


def test_metrics_report_cached_and_reasoning_tokens_and_research_rounds():
    messages = [
        HumanMessage(content="How did Eyes of the World evolve?"),
        AIMessage(content="", tool_calls=[{"name": "get_song", "args": {}, "id": "a", "type": "tool_call"}],
                  usage_metadata={"input_tokens": 12000, "output_tokens": 90, "total_tokens": 12090,
                                  "input_token_details": {"cache_read": 11520},
                                  "output_token_details": {"reasoning": 64}}),
        ToolMessage(content="{}", tool_call_id="a", name="get_song"),
        AIMessage(content="", tool_calls=[{"name": "finish_response", "args": {}, "id": "f", "type": "tool_call"}],
                  usage_metadata={"input_tokens": 20000, "output_tokens": 1500, "total_tokens": 21500,
                                  "input_token_details": {"priority_cache_read": 11904},
                                  "output_token_details": {"reasoning": 200}}),
        ToolMessage(content="Response delivered to the visitor.", tool_call_id="f", name="finish_response"),
    ]
    metrics = turn_metrics("q", messages, started=0.0, first_answer_at=9.0, finished_at=20.0, error=None)
    assert metrics["calls"][0]["cached_input_tokens"] == 11520 and metrics["calls"][0]["reasoning_tokens"] == 64
    assert metrics["calls"][1]["cached_input_tokens"] == 11904 and metrics["calls"][1]["finish"] is True
    assert metrics["total_cached_input_tokens"] == 23424
    assert metrics["cached_input_share"] == round(23424 / 32000, 3)
    assert metrics["total_output_tokens"] == 1590 and metrics["total_reasoning_tokens"] == 264
    assert metrics["research_rounds"] == 1 and metrics["model_calls"] == 2
    assert metrics["seconds_to_first_answer"] == 9.0


def test_missing_usage_is_reported_as_unknown():
    messages = [HumanMessage(content="q"), AIMessage(content="done")]
    metrics = turn_metrics("q", messages, started=0.0, first_answer_at=None, finished_at=1.0, error="boom")
    assert metrics["calls"] == [{"input_tokens": None, "output_tokens": None}]
    assert metrics["peak_input_tokens"] is None and metrics["error"] == "boom"
    assert metrics["total_cached_input_tokens"] is None and metrics["cached_input_share"] is None
    assert metrics["research_rounds"] == 0


class _StreamingAgent:
    def __init__(self, messages):
        self.messages = messages

    def stream(self, payload, config, stream_mode="values"):
        yield ("values", {"messages": self.messages})


def test_stream_endpoint_logs_one_metrics_line(caplog):
    finish = {"chat_answer": "Done.", "title": "T", "lead": None, "groups": []}
    messages = [
        HumanMessage(content="hello"),
        AIMessage(content="", tool_calls=[{"name": "finish_response", "args": finish, "id": "f", "type": "tool_call"}],
                  usage_metadata={"input_tokens": 900, "output_tokens": 50, "total_tokens": 950}),
        ToolMessage(content="Response delivered to the visitor.", tool_call_id="f", name="finish_response"),
    ]
    client = TestClient(create_app(settings=Settings(response_cache=False), store=CanonicalStore(), agent=_StreamingAgent(messages)))
    with caplog.at_level(logging.INFO, logger="deadbot.turn_metrics"):
        client.post("/api/experience/stream", json={"question": "hello"})
    lines = [json.loads(record.getMessage()) for record in caplog.records if record.name == "deadbot.turn_metrics"]
    assert len(lines) == 1
    assert lines[0]["question"] == "hello" and lines[0]["peak_input_tokens"] == 900 and lines[0]["error"] is None
