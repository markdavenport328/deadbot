"""Report the size of the finish_response tool schema the model sees each call."""

from __future__ import annotations

import json

from deadbot.finish import build_finish_tool


def schema_size() -> dict[str, int]:
    tool = build_finish_tool()
    schema = tool.args_schema.model_json_schema()
    text = json.dumps({"name": tool.name, "description": tool.description, "parameters": schema}, separators=(",", ":"))
    chars = len(text)
    return {"chars": chars, "approx_tokens": chars // 4}


if __name__ == "__main__":
    size = schema_size()
    print(f"finish_response schema: {size['chars']} chars, about {size['approx_tokens']} tokens")
