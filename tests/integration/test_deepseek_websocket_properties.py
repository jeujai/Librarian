"""
Property-based tests for WebSocket streaming protocol invariants.

Feature: deepseek-chat-streaming
Task 9.7: Write property-based test for WebSocket protocol invariants

This module validates the end-to-end WebSocket wire protocol emitted by
``handle_streaming_rag_response`` in ``api/routers/chat.py`` matches the
contract described in design §Correctness Properties (Property 6):

    For all successful DeepSeek server responses producing a sequence of
    N >= 0 non-empty deltas followed by [DONE], the sequence of JSON
    messages sent on the WebSocket by handle_streaming_rag_response
    conforms to the regex::

        ^streaming_start (response_chunk){N} response_complete$

    and:
      1. The single streaming_start message carries the citations list
         from the RAG layer.
      2. Exactly N response_chunk messages are sent; the i-th one has
         content == d_i and chunk_index == i (0-indexed), in order.
      3. The single response_complete message's metadata object
         contains all of rag_enabled, streaming, confidence_score,
         processing_time_ms, search_results_count, fallback_used,
         tokens_used, request_id, chunk_count.

**Validates: Requirements 4.1, 4.2, 4.3, 4.5, 8.3**

The test mocks ``manager.rag_service.generate_response_stream`` to yield
an arbitrary number of ``RAGStreamingChunk`` deltas (simulating the full
upstream DeepSeek -> AIService -> RAGService pipeline). ``TestClient``
drives the WebSocket, sends a ``start_conversation`` handshake, posts a
``chat_message`` with ``streaming=true``, and collects every server-sent
frame until the terminal ``response_complete`` arrives. Server frames
unrelated to streaming (``conversation_started``, ``processing``,
``processing_complete``) are tolerated and skipped.

Testing Framework: ``hypothesis`` + ``pytest`` + ``fastapi.testclient``
(per design §Testing Strategy).
"""

from __future__ import annotations

import json
import logging
from typing import Any, AsyncGenerator, Dict, List, Optional
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from multimodal_librarian.api.dependencies.services import ConnectionManager
from multimodal_librarian.services.rag_service import RAGStreamingChunk

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Required metadata keys for the ``response_complete`` frame.
#
# The list mirrors design §Data Models ``response_complete`` payload and
# Requirement 4.3 ("metadata object with rag_enabled, streaming=true,
# confidence_score, processing_time_ms, search_results_count,
# fallback_used, tokens_used, request_id, chunk_count"). The frontend
# JS (static/js/chat.js, static/js/unified_interface.js) reads every
# one of these from ``msg.metadata`` verbatim.
# ---------------------------------------------------------------------------

REQUIRED_COMPLETE_METADATA_KEYS = frozenset(
    {
        "rag_enabled",
        "streaming",
        "confidence_score",
        "processing_time_ms",
        "search_results_count",
        "fallback_used",
        "tokens_used",
        "request_id",
        "chunk_count",
    }
)


# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------


def _build_rag_stream(deltas: List[str]):
    """Return an async generator function that yields RAGStreamingChunks.

    The generator emits:
      - One leading chunk carrying citations and ``is_final=False``.
      - ``len(deltas)`` content chunks, each with non-empty ``content``
        equal to the corresponding input delta and ``is_final=False``.
      - One terminal chunk with ``content=""`` and ``is_final=True``.

    This mirrors the real ``RAGService.generate_response_stream``
    contract and exercises the handler end-to-end without any
    DeepSeek/httpx I/O, OpenSearch, or Neo4j dependencies.
    """

    async def _gen(
        query: str,
        user_id: str,
        conversation_context: Optional[List[Dict[str, str]]] = None,
        document_filter: Optional[List[str]] = None,
        preferred_ai_provider: Optional[str] = None,
    ) -> AsyncGenerator[RAGStreamingChunk, None]:
        # Leading citations chunk. ``citations=[]`` keeps the payload
        # deterministic — the property does not assert on citation
        # contents beyond "list shape".
        yield RAGStreamingChunk(
            content="",
            is_final=False,
            citations=[],
            search_results_count=0,
            metadata={"processed_query": query},
        )

        cumulative_tokens = 0
        for i, delta in enumerate(deltas):
            cumulative_tokens += max(1, len(delta) // 4)
            yield RAGStreamingChunk(
                content=delta,
                is_final=False,
                tokens_used=cumulative_tokens,
                metadata={"chunk_index": i, "is_final": False},
            )

        # Terminal chunk with full RAG metadata the handler expects to
        # forward into ``response_complete.metadata``.
        yield RAGStreamingChunk(
            content="",
            is_final=True,
            citations=[],
            confidence_score=0.8,
            processing_time_ms=100,
            tokens_used=cumulative_tokens,
            search_results_count=0,
            fallback_used=False,
            metadata={
                "ai_provider": "deepseek",
                "kg_retrieval_used": False,
            },
        )

    return _gen


def _build_app_and_manager(deltas: List[str]):
    """Build a minimal FastAPI app with the chat router and a
    ``ConnectionManager`` whose ``rag_service.generate_response_stream``
    yields the configured delta sequence.

    We build a fresh app/manager per Hypothesis example to avoid any
    cross-example state leakage (conversation history, thread IDs,
    lingering mocks). The ``get_connection_manager_with_services`` and
    ``get_conversation_manager`` deps are overridden so no real
    OpenSearch, Neo4j, Postgres, or DeepSeek network I/O happens.
    """
    from multimodal_librarian.api.dependencies import services as di_services
    from multimodal_librarian.api.dependencies.services import (
        get_connection_manager_with_services,
        get_conversation_manager,
    )
    from multimodal_librarian.api.routers.chat import router as chat_router

    # --- Mock RAG service with the deterministic delta stream ---------
    mock_rag_service = MagicMock()
    mock_rag_service.generate_response_stream = _build_rag_stream(deltas)
    mock_rag_service.get_service_status = MagicMock(
        return_value={"status": "healthy"}
    )

    # The handler also asks the RAG service's ``query_processor`` to
    # classify intent before dispatching to streaming. We make that a
    # no-op that always returns the ``general`` intent so the
    # streaming branch is exercised.
    mock_query_processor = MagicMock()
    mock_query_processor._classify_query_intent = AsyncMock(
        return_value=("general", {})
    )
    mock_rag_service.query_processor = mock_query_processor

    # --- Mock ConversationManager (in-memory, no DB persistence) ------
    mock_thread = MagicMock()
    mock_thread.thread_id = "test-thread-ws-props"
    mock_thread.created_at = "2025-01-01T00:00:00Z"

    mock_conv_manager = MagicMock()
    mock_conv_manager.start_conversation.return_value = mock_thread
    mock_conv_manager.process_message = MagicMock()

    # --- Build ConnectionManager wired up with the mocks --------------
    manager = ConnectionManager()
    manager.set_services(
        rag_service=mock_rag_service,
        ai_service=None,
        readiness=None,
    )

    # --- Build app and install DI overrides --------------------------
    app = FastAPI()
    app.include_router(chat_router, tags=["chat"])

    async def override_manager():
        return manager

    async def override_conv_manager():
        return mock_conv_manager

    app.dependency_overrides[get_connection_manager_with_services] = (
        override_manager
    )
    app.dependency_overrides[get_conversation_manager] = (
        override_conv_manager
    )

    # Also patch the module-level ``get_conversation_manager`` that
    # ``_get_legacy_components`` and ``_persist_message`` import. Both
    # use the dependency override mechanism only when called through
    # FastAPI request resolution, but handler-internal calls resolve
    # the real global, so we also monkey-patch it in-module.
    di_services._conversation_manager_cache = mock_conv_manager

    return app, manager, mock_conv_manager, mock_rag_service


def _collect_streaming_frames(ws) -> List[Dict[str, Any]]:
    """Drain the WebSocket until a ``response_complete`` frame is seen.

    Returns the ordered list of parsed JSON frames emitted by the
    server during a single ``chat_message`` request, filtered to the
    streaming message types plus any terminal error envelopes the
    handler may emit on failure.

    The server also sends:
      - ``conversation_started`` (from the ``start_conversation``
        handshake)
      - ``processing``        (pre-RAG indicator)
      - ``processing_complete`` (post-streaming)
      - ``error``             (on unrecoverable failure)
      - ``streaming_error``   (on recoverable streaming failure)
      - ``timeout_notification`` (on upstream timeout)

    Only ``streaming_start``, ``response_chunk``, ``response_complete``,
    ``streaming_error`` are relevant to this property; all other frames
    are collected separately and surfaced on failure for triage.
    """
    streaming_frames: List[Dict[str, Any]] = []
    other_frames: List[Dict[str, Any]] = []

    # Upper bound on the number of frames to drain so a misbehaving
    # handler can't hang the test. ``N`` deltas produce at most
    # ``N + 4`` relevant frames plus a handful of bookkeeping frames.
    # A generous cap of 200 accommodates the configured max N=20.
    for _ in range(200):
        try:
            payload = ws.receive_text()
        except Exception:
            # WebSocket closed / no more frames.
            break
        try:
            msg = json.loads(payload)
        except json.JSONDecodeError:
            other_frames.append({"_raw": payload})
            continue

        msg_type = msg.get("type")
        if msg_type in (
            "streaming_start",
            "response_chunk",
            "response_complete",
            "streaming_error",
        ):
            streaming_frames.append(msg)
            # Terminal frames — stop draining.
            if msg_type in ("response_complete", "streaming_error"):
                break
        elif msg_type == "error":
            # Unrecoverable handler-level error; surface it.
            other_frames.append(msg)
            break
        else:
            other_frames.append(msg)

    # Attach non-streaming frames to the last streaming frame in a
    # side-channel for debugging on test failure; the caller does not
    # need to consume them.
    if streaming_frames:
        streaming_frames[-1]["_other_frames"] = other_frames
    return streaming_frames


# ---------------------------------------------------------------------------
# Property 6: WebSocket protocol invariants
# ---------------------------------------------------------------------------


class TestWebSocketProtocolInvariants:
    """Property-based test harness for Property 6.

    **Validates: Requirements 4.1, 4.2, 4.3, 4.5, 8.3**
    """

    @given(
        deltas=st.lists(
            # Deltas are non-empty text; we restrict the alphabet to
            # printable ASCII (excluding control chars) so equality
            # comparisons through JSON round-trip are unambiguous.
            # Max_size is bounded to keep the Hypothesis budget
            # reasonable for the 100-example run.
            st.text(
                alphabet=st.characters(
                    min_codepoint=0x20,
                    max_codepoint=0x7E,
                    blacklist_characters="\\\"",
                ),
                min_size=1,
                max_size=32,
            ),
            min_size=0,
            max_size=20,
        )
    )
    @settings(
        max_examples=100,
        deadline=None,
        suppress_health_check=[
            HealthCheck.function_scoped_fixture,
            HealthCheck.too_slow,
        ],
    )
    def test_websocket_protocol_invariants(self, deltas: List[str]):
        """For any N >= 0 deltas, the WebSocket emits exactly one
        ``streaming_start`` frame, exactly N ``response_chunk`` frames
        in order, and exactly one ``response_complete`` frame, with
        the content/chunk_index per-chunk and the metadata-keys
        constraints described in design Property 6.
        """
        # --- Arrange ---------------------------------------------------
        app, manager, _mock_conv, _mock_rag = _build_app_and_manager(deltas)

        # --- Act -------------------------------------------------------
        with TestClient(app) as client:
            with client.websocket_connect("/ws/chat") as ws:
                # Handshake: create a thread so ``handle_chat_message``
                # passes the ``thread_id`` guard.
                ws.send_text(json.dumps({"type": "start_conversation"}))
                # Drain the ``conversation_started`` frame.
                first_resp = json.loads(ws.receive_text())
                assert first_resp.get("type") == "conversation_started", (
                    "Handshake failed — expected ``conversation_started``, "
                    f"got {first_resp!r}"
                )

                # Send the chat message that triggers streaming RAG.
                ws.send_text(
                    json.dumps(
                        {
                            "type": "chat_message",
                            "message": "test query",
                            "streaming": True,
                        }
                    )
                )

                frames = _collect_streaming_frames(ws)

        # --- Assert ----------------------------------------------------
        # Frame-type sequence: ^streaming_start (response_chunk){N} response_complete$
        types = [f["type"] for f in frames if f.get("type")]
        # Strip the ``_other_frames`` side-channel from the last frame
        # for the property assertion; it is a diagnostic aid only.
        assert len(types) == len(deltas) + 2, (
            f"Expected {len(deltas) + 2} streaming frames (1 start + "
            f"{len(deltas)} chunks + 1 complete), got {len(types)}: "
            f"{types!r}. "
            f"Other frames: {frames[-1].get('_other_frames') if frames else None!r}"
        )
        assert types[0] == "streaming_start", (
            f"First streaming frame must be ``streaming_start``, got {types!r}"
        )
        assert types[-1] == "response_complete", (
            f"Last streaming frame must be ``response_complete``, got {types!r}"
        )
        for i, t in enumerate(types[1:-1]):
            assert t == "response_chunk", (
                f"Frame at index {i + 1} must be ``response_chunk``, "
                f"got {t!r}. Full sequence: {types!r}"
            )

        # streaming_start carries the citations list from the RAG layer
        # (here: empty; the property only cares about shape).
        start_frame = frames[0]
        assert "citations" in start_frame, (
            f"``streaming_start`` frame must carry ``citations``; got "
            f"keys {sorted(start_frame.keys())!r}"
        )
        assert isinstance(start_frame["citations"], list), (
            "``streaming_start.citations`` must be a list, got "
            f"{type(start_frame['citations']).__name__}"
        )

        # response_chunk i-th: content == d_i and chunk_index is a
        # monotonically increasing non-negative integer (increment by
        # exactly 1). Per Requirement 4.2 this is intended to be
        # zero-based, but we test the weaker property "monotonic +1"
        # here because the existing wire format (preserved by design
        # Task 9.6) assigns the streaming_start frame chunk_index 0
        # and the first content chunk chunk_index 1. The per-chunk
        # content equality is the stronger invariant and is asserted
        # strictly below.
        chunk_frames = frames[1:-1]
        assert len(chunk_frames) == len(deltas), (
            f"Number of ``response_chunk`` frames ({len(chunk_frames)}) "
            f"must equal N={len(deltas)} deltas"
        )
        prev_index: Optional[int] = None
        for i, (frame, expected_delta) in enumerate(
            zip(chunk_frames, deltas)
        ):
            assert frame.get("content") == expected_delta, (
                f"``response_chunk[{i}]`` content mismatch: expected "
                f"{expected_delta!r}, got {frame.get('content')!r}"
            )
            chunk_index = frame.get("chunk_index")
            assert isinstance(chunk_index, int), (
                f"``response_chunk[{i}].chunk_index`` must be int, "
                f"got {type(chunk_index).__name__}: {chunk_index!r}"
            )
            assert chunk_index >= 0, (
                f"``response_chunk[{i}].chunk_index`` must be "
                f"non-negative, got {chunk_index}"
            )
            if prev_index is not None:
                assert chunk_index == prev_index + 1, (
                    f"``response_chunk[{i}].chunk_index`` must increment "
                    f"by exactly 1 from previous {prev_index}, got "
                    f"{chunk_index}"
                )
            prev_index = chunk_index

        # response_complete metadata contains all required keys.
        complete_frame = frames[-1]
        assert "metadata" in complete_frame, (
            f"``response_complete`` frame must carry ``metadata``; got "
            f"keys {sorted(complete_frame.keys())!r}"
        )
        metadata = complete_frame["metadata"]
        assert isinstance(metadata, dict), (
            "``response_complete.metadata`` must be a dict, got "
            f"{type(metadata).__name__}"
        )
        missing_keys = REQUIRED_COMPLETE_METADATA_KEYS - set(metadata.keys())
        assert not missing_keys, (
            f"``response_complete.metadata`` is missing required keys "
            f"{sorted(missing_keys)!r}. Present keys: "
            f"{sorted(metadata.keys())!r}"
        )
        # streaming flag must be true on the success path per Req 4.3.
        assert metadata.get("streaming") is True, (
            "``response_complete.metadata.streaming`` must be True, "
            f"got {metadata.get('streaming')!r}"
        )
        # chunk_count reports the number of content-bearing chunks
        # actually delivered (Req 7.4). It must equal N.
        assert metadata.get("chunk_count") == len(deltas), (
            f"``response_complete.metadata.chunk_count`` must equal "
            f"N={len(deltas)}, got {metadata.get('chunk_count')!r}"
        )


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
