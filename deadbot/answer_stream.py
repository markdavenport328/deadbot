"""Decode ``chat_answer`` out of the growing ``finish_response`` arguments.

The model streams its ``finish_response`` tool call as JSON text fragments.
Rather than wait for the whole plan (title, body blocks, and all) to finish
generating, :func:`extract_chat_answer` pulls the ``chat_answer`` string
value out of the arguments text as far as it has been generated so far, and
:class:`AnswerAccumulator` tracks that across a LangGraph ``messages``-mode
stream of ``AIMessageChunk``s so the visible answer can reach the browser
while the rest of the plan is still on the wire.
"""

from __future__ import annotations

import re
from typing import Any

from deadbot.finish import FINISH_TOOL_NAME

_KEY = re.compile(r'"chat_answer"\s*:\s*"')

_SIMPLE_ESCAPES = {
    '"': '"',
    "\\": "\\",
    "/": "/",
    "n": "\n",
    "t": "\t",
    "r": "\r",
    "b": "\b",
    "f": "\f",
}


def extract_chat_answer(partial_json: str) -> tuple[str, bool]:
    """Decode the ``chat_answer`` string value out of partial tool-call JSON.

    Returns the value decoded as far as it has been generated, and whether
    the string is complete (an unescaped closing quote has been seen). A
    trailing incomplete escape sequence (a lone ``\\`` or a partial
    ``\\u12``) is held back rather than emitted, so a later call with more
    text can complete it.
    """

    match = _KEY.search(partial_json)
    if not match:
        return ("", False)

    body = partial_json[match.end() :]
    chars: list[str] = []
    index = 0
    length = len(body)
    complete = False

    while index < length:
        char = body[index]
        if char == '"':
            complete = True
            break
        if char != "\\":
            chars.append(char)
            index += 1
            continue

        # An escape sequence starts here.
        if index + 1 >= length:
            # Lone trailing backslash: hold it back, more text may follow.
            break
        escape = body[index + 1]
        if escape == "u":
            hex_digits = body[index + 2 : index + 6]
            if len(hex_digits) < 4:
                # Partial \uXXXX: hold back, more text may follow.
                break
            code_point = int(hex_digits, 16)
            if 0xD800 <= code_point <= 0xDBFF:
                # High surrogate: look for a following low surrogate to form
                # one character. If it is not there yet, hold everything
                # back since more text may complete the pair.
                low_start = index + 6
                if body[low_start : low_start + 2] != "\\u":
                    break
                low_hex = body[low_start + 2 : low_start + 6]
                if len(low_hex) < 4:
                    break
                low_point = int(low_hex, 16)
                if not (0xDC00 <= low_point <= 0xDFFF):
                    # Not a valid low surrogate; emit the high surrogate on
                    # its own rather than lose it.
                    chars.append(chr(code_point))
                    index += 6
                    continue
                combined = 0x10000 + (code_point - 0xD800) * 0x400 + (low_point - 0xDC00)
                chars.append(chr(combined))
                index = low_start + 6
                continue
            chars.append(chr(code_point))
            index += 6
            continue
        replacement = _SIMPLE_ESCAPES.get(escape)
        if replacement is None:
            # Not a recognized JSON escape; keep the character verbatim
            # rather than drop information.
            chars.append(escape)
        else:
            chars.append(replacement)
        index += 2

    return ("".join(chars), complete)


class AnswerAccumulator:
    """Track the cumulative ``chat_answer`` text across a ``messages`` stream.

    Feed it every ``AIMessageChunk`` yielded by LangGraph's ``messages``
    stream mode. It buffers the argument fragments that belong to the
    ``finish_response`` tool call (identified by name, then by the same
    ``id``/``index`` once the name has been seen) and ignores everything
    else: other tool calls and plain text content.
    """

    def __init__(self) -> None:
        self._buffer = ""
        self._answer = ""
        self._complete = False
        self._call_id: str | None = None
        self._call_index: int | None = None

    @property
    def complete(self) -> bool:
        return self._complete

    def feed(self, message_chunk: Any) -> str | None:
        tool_call_chunks = getattr(message_chunk, "tool_call_chunks", None) or []
        for chunk in tool_call_chunks:
            if self._is_finish_call(chunk):
                self._buffer += chunk.get("args") or ""

        if not self._buffer:
            return None

        answer, complete = extract_chat_answer(self._buffer)
        self._complete = complete
        if answer == self._answer:
            return None
        self._answer = answer
        return answer

    def _is_finish_call(self, chunk: dict) -> bool:
        name = chunk.get("name")
        call_id = chunk.get("id")
        call_index = chunk.get("index")

        if name == FINISH_TOOL_NAME:
            if self._call_id is None:
                self._call_id = call_id
            if self._call_index is None:
                self._call_index = call_index
            return True
        if name:
            # A chunk that names a different tool call is never ours, even
            # if it happens to share an id/index with a prior chunk.
            return False
        if call_id is not None and call_id == self._call_id:
            return True
        if call_index is not None and call_index == self._call_index:
            return True
        return False
