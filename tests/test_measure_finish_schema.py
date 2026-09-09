from scripts.measure_finish_schema import schema_size


def test_schema_size_reports_chars_and_tokens_for_the_finish_tool():
    size = schema_size()
    assert size["chars"] > 1000
    assert size["approx_tokens"] == size["chars"] // 4
