"""
Property-based tests for the DeepSeek SSE parser.

Feature: deepseek-chat-streaming
Task 2.3: Property-based test for SSE parser round-trip

This module validates the pure SSE parser (``parse_sse_line`` + ``SSEFrame``)
defined in ``src/multimodal_librarian/services/deepseek_ai_service.py`` by
rendering DeepSeek-format SSE streams from arbitrary lists of deltas,
parsing each line, and asserting that the concatenated ``delta_content``
of every ``SSEFrame(kind="delta")`` returned equals the concatenation of
the original input deltas.

Testing Framework: hypothesis (per design document)
"""

from __future__ import annotations

import json
from typing import List

from hypothesis import example, given, settings
from hypothesis import strategies as st

from multimodal_librarian.services.deepseek_ai_service import SSEFrame, parse_sse_line

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _render_deepseek_sse(deltas: List[str]) -> str:
    """Render a list of content deltas as a DeepSeek SSE response body.

    Each delta becomes one ``data: {...}\\n\\n`` frame shaped like the
    OpenAI-compatible chat-completions streaming payload DeepSeek emits:
    ``{"choices": [{"delta": {"content": "<delta>"}}]}``. The stream is
    terminated by a ``data: [DONE]\\n\\n`` sentinel.
    """
    frames: List[str] = []
    for delta in deltas:
        payload = {"choices": [{"delta": {"content": delta}}]}
        # ``ensure_ascii=False`` so unicode (emoji, CJK, zero-width) is
        # preserved verbatim inside the JSON payload; the parser uses
        # ``json.loads`` which handles both escaped and raw forms.
        frames.append("data: " + json.dumps(payload, ensure_ascii=False) + "\n\n")
    frames.append("data: [DONE]\n\n")
    return "".join(frames)


def _parsed_delta_contents(sse_body: str) -> List[str]:
    """Feed ``sse_body`` line-by-line through ``parse_sse_line`` and collect
    the ``delta_content`` of every frame classified as ``kind="delta"``.
    """
    out: List[str] = []
    for line in sse_body.split("\n"):
        frame = parse_sse_line(line)
        if frame is None:
            continue
        if frame.kind == "delta":
            assert frame.delta_content is not None
            out.append(frame.delta_content)
    return out


# ---------------------------------------------------------------------------
# Property 1: SSE parser round-trip
# ---------------------------------------------------------------------------
#
# Validates: Requirements 1.2, 12.1
#
# For any list of non-empty content deltas, rendering them as DeepSeek SSE
# frames and then feeding each line back through ``parse_sse_line`` must
# reconstruct the original deltas in order. Concretely, concatenating the
# ``delta_content`` of every returned ``SSEFrame(kind="delta")`` must equal
# the concatenation of the original input deltas.


@given(deltas=st.lists(st.text(min_size=1)))
@settings(max_examples=500, deadline=None)
@example(deltas=["**bold**"])
@example(deltas=["🔥"])
@example(deltas=["你好"])
@example(deltas=["\u200b"])
@example(deltas=["\n\n"])
def test_sse_parser_round_trip(deltas: List[str]) -> None:
    """Round-trip: render deltas as SSE, parse, reassemble.

    **Validates: Requirements 1.2, 12.1**
    """
    sse_body = _render_deepseek_sse(deltas)
    parsed = _parsed_delta_contents(sse_body)
    assert "".join(parsed) == "".join(deltas)
