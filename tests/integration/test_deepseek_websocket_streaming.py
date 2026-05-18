"""
End-to-end integration test harness for DeepSeek WebSocket streaming.

Feature: deepseek-chat-streaming
Task 12.1: Create reusable ``httpx.MockTransport`` fixtures that simulate
DeepSeek SSE responses for use by the Task 12.2-12.10 integration tests.

**Validates: Requirements 12.3, 12.4, 12.5**

This module provides three public helpers and one fixture factory that
together let a test drive the full WebSocket -> ``handle_streaming_rag_response``
-> ``RAGService.generate_response_stream`` -> ``DeepSeekAIService.generate_response_stream``
-> ``httpx.AsyncClient.stream()`` chain without any real network I/O.

Public helpers
--------------

``mock_deepseek_stream(deltas, include_usage=True)``
    Build an ``httpx.MockTransport`` that returns a valid DeepSeek SSE
    response for ``POST /chat/completions``. The body starts with the
    OpenAI-style role-delta frame, follows with one frame per element of
    ``deltas`` (each carrying a non-empty ``choices[0].delta.content``),
    optionally emits a terminal ``usage`` frame when
    ``include_usage=True``, and ends with ``data: [DONE]``.

``mock_deepseek_error(status_code, body=b"", retry_after=None)``
    Build an ``httpx.MockTransport`` that returns a non-2xx HTTP
    response. Used to exercise the HTTP-error branch of the streaming
    client (Req 6.1, 6.2, 6.3). ``retry_after`` is attached as the
    ``Retry-After`` response header when set, covering Req 6.2.

``mock_deepseek_network_drop_after(n_chunks, deltas=None)``
    Build an ``httpx.MockTransport`` that begins emitting SSE frames and
    then raises ``httpx.ReadError`` after the n-th non-empty delta,
    simulating a mid-stream TCP reset. Used for Req 6.4 and the
    disconnect-timing integration tests (Task 12.4).

Fixture factory
---------------

``make_app_with_mocked_deepseek``
    A pytest fixture that returns a callable
    ``make(transport, *, streaming_enabled=True) -> (service, app)`` where:

    - ``service`` is a fully-constructed :class:`DeepSeekAIService` whose
      internal ``httpx.AsyncClient`` is pre-bound to the supplied
      ``MockTransport``. The service's resilience trackers are in their
      default (allowing) state.
    - ``app`` is a ``FastAPI`` application with the chat router mounted
      and two dependency overrides installed:
        * ``get_ai_service`` -> returns the wrapped ``DeepSeekAIService``.
        * ``get_cached_rag_service`` / ``get_rag_service`` -> returns a
          minimal ``RAGService``-shaped stub whose
          ``generate_response_stream`` forwards deltas from the wrapped
          ``DeepSeekAIService.generate_response_stream`` as
          ``RAGStreamingChunk`` objects (plus the mandatory
          leading-citations chunk and terminal-metadata chunk required
          by the WebSocket handler contract).

    All AsyncClients and TCP connections allocated by the factory are
    closed in the fixture's finalizer.

Notes
-----

* The task scope is the fixture module itself — Tasks 12.2-12.10 write
  the actual property/example tests on top of these helpers and are
  marked optional (``*``) in ``tasks.md``.
* The SSE body produced by these helpers is validated against the
  parser in ``services/deepseek_ai_service.py`` via a module-level
  smoke test, guaranteeing byte-for-byte compatibility with the
  production parser.

Testing Framework: ``pytest`` + ``httpx.MockTransport`` (per design
§Testing Strategy, "HTTP mocking" row).
"""

from __future__ import annotations

import json
import logging
from typing import (
    Any,
    AsyncGenerator,
    AsyncIterator,
    Callable,
    Dict,
    List,
    Optional,
    Tuple,
)
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest
from fastapi import FastAPI

from multimodal_librarian.services.ai_service import AIResponse
from multimodal_librarian.services.deepseek_ai_service import (
    DeepSeekAIService,
    parse_sse_line,
)
from multimodal_librarian.services.rag_service import RAGStreamingChunk

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# SSE body renderers
# ---------------------------------------------------------------------------

_MOCK_MODEL = "deepseek-chat"
_MOCK_CREATED = 1_700_000_000


def _sse_role_frame() -> bytes:
    """Render the OpenAI-style first frame that carries only ``role``.

    DeepSeek (and OpenAI's chat completions streaming API) emits this
    frame before any content delta. The production ``parse_sse_line``
    classifies it as ``kind="empty"`` so it yields no user-visible
    chunk; including it here matches the real wire format and ensures
    our fixtures exercise the empty-frame handling path.
    """
    payload = {
        "id": "chatcmpl-test",
        "object": "chat.completion.chunk",
        "created": _MOCK_CREATED,
        "model": _MOCK_MODEL,
        "choices": [
            {
                "index": 0,
                "delta": {"role": "assistant"},
                "finish_reason": None,
            }
        ],
    }
    return f"data: {json.dumps(payload)}\n\n".encode("utf-8")


def _sse_delta_frame(
    text: str,
    finish_reason: Optional[str] = None,
) -> bytes:
    """Render a single SSE frame carrying a content delta.

    The frame conforms to DeepSeek's schema (a subset of OpenAI's):
    ``choices[0].delta.content`` holds the incremental text fragment,
    ``choices[0].finish_reason`` is normally ``None`` until the final
    delta. ``text`` may be empty when the caller wants to emit a
    finish-reason-only frame.
    """
    payload: Dict[str, Any] = {
        "id": "chatcmpl-test",
        "object": "chat.completion.chunk",
        "created": _MOCK_CREATED,
        "model": _MOCK_MODEL,
        "choices": [
            {
                "index": 0,
                "delta": {"content": text},
                "finish_reason": finish_reason,
            }
        ],
    }
    return f"data: {json.dumps(payload)}\n\n".encode("utf-8")


def _sse_usage_frame(
    prompt_tokens: int = 5,
    completion_tokens: int = 5,
    finish_reason: str = "stop",
) -> bytes:
    """Render the terminal ``usage`` frame DeepSeek sends when
    ``stream_options.include_usage=true``.

    Per DeepSeek's docs, the usage frame has an empty ``delta`` object
    and carries a top-level ``usage`` object with ``prompt_tokens``,
    ``completion_tokens``, and ``total_tokens``. The production
    ``parse_sse_line`` classifies this as ``kind="usage"``.
    """
    total = prompt_tokens + completion_tokens
    payload: Dict[str, Any] = {
        "id": "chatcmpl-test",
        "object": "chat.completion.chunk",
        "created": _MOCK_CREATED,
        "model": _MOCK_MODEL,
        "choices": [
            {"index": 0, "delta": {}, "finish_reason": finish_reason}
        ],
        "usage": {
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "total_tokens": total,
        },
    }
    return f"data: {json.dumps(payload)}\n\n".encode("utf-8")


def _sse_done_frame() -> bytes:
    """Render the terminal ``data: [DONE]`` sentinel that ends the stream.

    ``parse_sse_line`` classifies this as ``kind="done"`` and the
    streaming loop in ``DeepSeekAIService`` breaks out of the
    ``aiter_lines`` loop on this frame.
    """
    return b"data: [DONE]\n\n"


def _render_sse_body(deltas: List[str], include_usage: bool = True) -> bytes:
    """Assemble a complete DeepSeek SSE body from a list of deltas.

    Sequence:
      1. One ``role: assistant`` empty frame.
      2. One content-delta frame per element of ``deltas``. When
         ``deltas`` is empty, no content frames are emitted (covers the
         empty-stream branch exercised by Task 12.6).
      3. One ``usage`` frame when ``include_usage=True``. When disabled,
         emit a trailing empty delta with ``finish_reason="stop"``
         instead, which still signals clean termination to the parser.
      4. One ``data: [DONE]`` sentinel.
    """
    frames: List[bytes] = [_sse_role_frame()]
    for d in deltas:
        frames.append(_sse_delta_frame(d))
    if include_usage:
        frames.append(_sse_usage_frame())
    else:
        # Emit an empty-content frame carrying finish_reason so the
        # service's ``final_finish_reason`` is populated before [DONE].
        frames.append(_sse_delta_frame("", finish_reason="stop"))
    frames.append(_sse_done_frame())
    return b"".join(frames)


# ---------------------------------------------------------------------------
# MockTransport factory helpers (Public API)
# ---------------------------------------------------------------------------


def mock_deepseek_stream(
    deltas: List[str],
    include_usage: bool = True,
) -> httpx.MockTransport:
    """Return an ``httpx.MockTransport`` that serves a successful SSE stream.

    Handler behavior:
      - Responds to any ``POST /chat/completions`` with a 200 OK,
        ``content-type: text/event-stream``, and a body composed by
        ``_render_sse_body(deltas, include_usage)``.
      - Responds to any other path with a 404 so misrouted requests
        surface immediately in test failures rather than silently
        succeeding.

    The returned transport can be plugged into an ``httpx.AsyncClient``
    via the ``transport=`` keyword. The ``make_app_with_mocked_deepseek``
    fixture does this automatically.

    Args:
        deltas: Content fragments to emit, one SSE frame each. May be
            empty to simulate a ``[DONE]``-only stream (Req 7.4).
        include_usage: When ``True`` (default), emit a terminal ``usage``
            frame matching DeepSeek's ``stream_options.include_usage``
            behavior. When ``False``, emit a finish-reason-only frame
            instead, so the service's ``final_finish_reason`` is still
            populated.

    Returns:
        An ``httpx.MockTransport`` ready to attach to an
        ``httpx.AsyncClient``.

    **Validates: Requirements 12.3**
    """
    body = _render_sse_body(deltas, include_usage=include_usage)

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method != "POST" or not request.url.path.endswith(
            "/chat/completions"
        ):
            return httpx.Response(
                404,
                content=b'{"error": "unexpected path"}',
                headers={"content-type": "application/json"},
            )
        return httpx.Response(
            200,
            content=body,
            headers={"content-type": "text/event-stream"},
        )

    return httpx.MockTransport(handler)


def mock_deepseek_error(
    status_code: int,
    body: bytes = b"",
    retry_after: Optional[Any] = None,
) -> httpx.MockTransport:
    """Return an ``httpx.MockTransport`` that serves a non-2xx HTTP error.

    Exercises the HTTP-error branch of the streaming client (Reqs 6.1,
    6.2, 6.3). When ``retry_after`` is provided, the handler attaches a
    ``Retry-After`` response header so the service's rate-limit branch
    (Req 6.2) can read it.

    Args:
        status_code: HTTP status to return (e.g. 401, 403, 429, 500,
            502, 503).
        body: Optional response body. When empty, a minimal JSON error
            object is returned instead so the service's body-truncation
            logic sees non-empty text.
        retry_after: Optional value for the ``Retry-After`` header.
            Stringified with ``str()``; pass a numeric value (e.g. ``30``)
            or an HTTP-date string per RFC 7231. The service parses
            numeric values and falls back to a 60-second default on
            non-numeric values (Req 6.2 default clause).

    Returns:
        An ``httpx.MockTransport`` ready to attach to an
        ``httpx.AsyncClient``.

    **Validates: Requirements 12.4**
    """
    if not body:
        body = json.dumps(
            {"error": f"Mocked HTTP {status_code}"}
        ).encode("utf-8")

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method != "POST" or not request.url.path.endswith(
            "/chat/completions"
        ):
            return httpx.Response(
                404,
                content=b'{"error": "unexpected path"}',
                headers={"content-type": "application/json"},
            )
        headers: Dict[str, str] = {"content-type": "application/json"}
        if retry_after is not None:
            headers["retry-after"] = str(retry_after)
        return httpx.Response(status_code, content=body, headers=headers)

    return httpx.MockTransport(handler)


class _DropAfterNStream(httpx.AsyncByteStream):
    """Async byte stream that emits ``n_chunks`` SSE deltas then raises.

    Implements the ``httpx.AsyncByteStream`` protocol. The ``__aiter__``
    method yields:
      1. The OpenAI-style role frame (``parse_sse_line`` sees it as
         ``kind="empty"``).
      2. ``n_chunks`` content-delta frames, one per element of
         ``deltas[:n_chunks]``. If ``n_chunks`` exceeds ``len(deltas)``
         the iteration is capped at ``len(deltas)``.
      3. A ``httpx.ReadError`` raised from the async generator body,
         which the ``httpx.AsyncClient`` surfaces to callers iterating
         ``response.aiter_lines()`` — exactly the mid-stream failure
         mode the service's ``httpx.ReadError`` handler is designed to
         catch (Req 6.4).
    """

    def __init__(self, deltas: List[str], n_chunks: int) -> None:
        self._deltas = deltas
        self._n_chunks = max(0, int(n_chunks))

    async def __aiter__(self) -> AsyncIterator[bytes]:
        yield _sse_role_frame()
        emit_count = min(self._n_chunks, len(self._deltas))
        for i in range(emit_count):
            yield _sse_delta_frame(self._deltas[i])
        # Raise a network error on the next read, simulating a mid-stream
        # TCP reset. The service's ``except httpx.ReadError`` branch
        # catches this and emits the terminal network-error chunk.
        raise httpx.ReadError("Simulated mid-stream connection drop")

    async def aclose(self) -> None:
        # No resources to release; the raised ReadError already
        # terminates iteration.
        return None


def mock_deepseek_network_drop_after(
    n_chunks: int,
    deltas: Optional[List[str]] = None,
) -> httpx.MockTransport:
    """Return an ``httpx.MockTransport`` that drops the stream mid-flight.

    The transport responds to ``POST /chat/completions`` with a 200 OK
    whose body is an async byte stream that emits ``n_chunks`` content
    deltas and then raises ``httpx.ReadError``, simulating a mid-stream
    TCP reset. Used for Req 6.4 and Task 12.4 (client-disconnect
    timing).

    Args:
        n_chunks: Number of content deltas to emit before the drop.
            Must be ``>= 0``. Capped at ``len(deltas)``.
        deltas: Content fragments to emit before the drop. Defaults to a
            10-element sequence of single lowercase letters so callers
            that don't care about the specific payload can simulate a
            drop after arbitrary chunk counts without passing a list.

    Returns:
        An ``httpx.MockTransport`` ready to attach to an
        ``httpx.AsyncClient``.

    **Validates: Requirements 12.5**
    """
    if deltas is None:
        deltas = [
            "a",
            "b",
            "c",
            "d",
            "e",
            "f",
            "g",
            "h",
            "i",
            "j",
        ]

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method != "POST" or not request.url.path.endswith(
            "/chat/completions"
        ):
            return httpx.Response(
                404,
                content=b'{"error": "unexpected path"}',
                headers={"content-type": "application/json"},
            )
        return httpx.Response(
            200,
            stream=_DropAfterNStream(deltas, n_chunks),
            headers={"content-type": "text/event-stream"},
        )

    return httpx.MockTransport(handler)


# ---------------------------------------------------------------------------
# DeepSeekAIService wrapping / DI override builder
# ---------------------------------------------------------------------------


def _build_deepseek_service_with_transport(
    transport: httpx.MockTransport,
    *,
    streaming_enabled: bool = True,
    api_key: str = "test-key-not-used",
    model: str = _MOCK_MODEL,
) -> DeepSeekAIService:
    """Construct a ``DeepSeekAIService`` bound to a ``MockTransport``.

    The returned service has its internal ``httpx.AsyncClient`` pre-
    allocated and wired to ``transport`` so the lazy ``_get_client``
    path never opens a real TCP connection. Resilience trackers
    (``CircuitBreaker``, ``ErrorRateTracker``) are in their default
    allowing state so every test starts from a clean slate; individual
    tests can mutate them in-place before invoking the streaming path.

    Args:
        transport: The ``httpx.MockTransport`` produced by one of the
            ``mock_deepseek_*`` helpers.
        streaming_enabled: When ``False``, disables the streaming feature
            flag so the service takes the Streaming_Disabled_Fallback
            path (Req 10.2). Defaults to ``True`` for the common test
            case.
        api_key: Dummy API key for the service constructor; never
            transmitted because the transport is mocked.
        model: Model name the service reports on every chunk.

    Returns:
        A ready-to-use ``DeepSeekAIService``.
    """
    service = DeepSeekAIService(
        api_key=api_key,
        model=model,
        base_url="https://api.deepseek.com",
        timeout=10.0,
    )
    # Override the feature flag regardless of the ambient env value so
    # tests are deterministic across environments.
    service.streaming_enabled_config = streaming_enabled
    # Pre-create the AsyncClient bound to the mock transport. Subsequent
    # calls to ``_get_client()`` return this instance rather than opening
    # a real connection. ``headers=`` matches the real ``_get_client``
    # output so any header-sensitive assertions remain valid.
    service._client = httpx.AsyncClient(
        base_url=service.base_url,
        transport=transport,
        timeout=httpx.Timeout(service.timeout),
        headers={
            "Authorization": f"Bearer {service.api_key}",
            "Content-Type": "application/json",
        },
    )
    return service


def _build_rag_service_stub(deepseek_service: DeepSeekAIService) -> MagicMock:
    """Build a RAG-service-shaped stub that forwards deltas verbatim.

    The chat WebSocket handler calls ``rag_service.generate_response_stream(...)``
    and expects ``RAGStreamingChunk`` objects: one leading
    citations/metadata chunk (``is_final=False``, no content), zero or
    more content chunks (``is_final=False``, ``content=<delta>``), and
    exactly one terminal chunk (``is_final=True``). This stub produces
    that shape by forwarding every ``AIResponse`` from the wrapped
    ``deepseek_service.generate_response_stream`` and wrapping each in a
    ``RAGStreamingChunk``.

    The leading chunk carries ``citations=[]`` (the integration tests
    do not assert on citation content beyond "list shape"). The
    terminal chunk's metadata includes the keys the handler needs to
    populate ``response_complete.metadata``.
    """

    async def _stream(
        query: str,
        user_id: str,
        conversation_context: Optional[List[Dict[str, str]]] = None,
        document_filter: Optional[List[str]] = None,
        preferred_ai_provider: Optional[str] = None,
    ) -> AsyncGenerator[RAGStreamingChunk, None]:
        # 1) Leading citations chunk. ``is_final=False`` so the handler
        #    emits ``streaming_start`` and begins draining content.
        yield RAGStreamingChunk(
            content="",
            is_final=False,
            citations=[],
            search_results_count=0,
            metadata={"processed_query": query},
        )

        cumulative_tokens = 0
        last_ai_metadata: Dict[str, Any] = {}
        ai_chunks_seen = 0

        # 2) Forward deltas from the real DeepSeek streaming client.
        async for ai_chunk in deepseek_service.generate_response_stream(
            messages=[{"role": "user", "content": query}],
            context=None,
            temperature=0.7,
            max_tokens=512,
            preferred_provider=None,
        ):
            ai_chunks_seen += 1
            ai_metadata = dict(ai_chunk.metadata or {})
            last_ai_metadata = ai_metadata
            is_final = bool(ai_metadata.get("is_final", False))
            if is_final:
                # Save for the terminal chunk below.
                break
            # Non-terminal content chunk.
            cumulative_tokens += max(1, len(ai_chunk.content) // 4)
            yield RAGStreamingChunk(
                content=ai_chunk.content,
                is_final=False,
                tokens_used=cumulative_tokens,
                metadata={
                    "chunk_index": ai_metadata.get("chunk_index"),
                    "is_final": False,
                },
            )

        # 3) Terminal metadata chunk mirroring the real RAGService
        #    contract. ``ai_provider`` is sourced from the wrapped
        #    service's ``provider_name`` so Task 8.1's dynamic lookup
        #    is exercised.
        provider_name = getattr(
            deepseek_service, "provider_name", "unknown"
        )
        terminal_metadata: Dict[str, Any] = {
            "ai_provider": provider_name,
            "kg_retrieval_used": False,
        }
        # Propagate error-type hints from the AI terminal chunk so
        # handler branches (streaming_error -> non-streaming fallback,
        # Req 5.3) can observe them.
        for k in ("error_type", "recoverable", "user_message", "finish_reason"):
            if k in last_ai_metadata:
                terminal_metadata[k] = last_ai_metadata[k]

        yield RAGStreamingChunk(
            content="",
            is_final=True,
            citations=[],
            confidence_score=0.8,
            processing_time_ms=100,
            tokens_used=max(cumulative_tokens, 1),
            search_results_count=0,
            fallback_used=False,
            metadata=terminal_metadata,
        )

    # Construct the MagicMock AFTER defining ``_stream`` so we can bind
    # it directly without AsyncMock wrapping (AsyncMock doesn't play
    # nicely with async generators — it returns a coroutine that
    # resolves to the generator, not the generator itself).
    stub = MagicMock()
    stub.generate_response_stream = _stream
    stub.get_service_status = MagicMock(
        return_value={"status": "healthy"}
    )
    # The handler also asks the RAG service's ``query_processor`` to
    # classify intent; provide a no-op that always returns ``general``.
    stub.query_processor = MagicMock()
    stub.query_processor._classify_query_intent = AsyncMock(
        return_value=("general", {})
    )
    # Non-streaming fallback used by Reqs 5.3 / 5.4.
    stub.generate_response = AsyncMock(
        return_value={
            "response": "Non-streaming fallback response",
            "citations": [],
            "tokens_used": 1,
            "processing_time_ms": 10,
            "confidence_score": 0.5,
            "search_results_count": 0,
            "fallback_used": True,
        }
    )
    return stub


# ---------------------------------------------------------------------------
# Fixture: factory that builds an app with mocked DeepSeek wired through DI
# ---------------------------------------------------------------------------

_AppFactoryResult = Tuple[DeepSeekAIService, FastAPI, MagicMock]


@pytest.fixture
def make_app_with_mocked_deepseek(
    request: pytest.FixtureRequest,
) -> Callable[..., _AppFactoryResult]:
    """Factory fixture that builds a FastAPI app wired to a mocked DeepSeek.

    Returns a callable ``make(transport, *, streaming_enabled=True)``.
    Each invocation:
      1. Constructs a ``DeepSeekAIService`` bound to ``transport`` via
         ``_build_deepseek_service_with_transport``.
      2. Builds a minimal ``FastAPI`` app, mounts the chat router, and
         wires a ``ConnectionManager`` whose ``rag_service`` is a stub
         forwarding deltas from the wrapped DeepSeek service.
      3. Installs ``app.dependency_overrides`` for:
           * ``get_ai_service`` / ``get_ai_service_optional``
             -> returns the wrapped ``DeepSeekAIService``.
           * ``get_cached_rag_service`` / ``get_rag_service``
             -> returns the RAG-stub for any override-consuming route.
           * ``get_connection_manager_with_services``
             -> returns a ``ConnectionManager`` pre-wired to both.
           * ``get_conversation_manager``
             -> returns an in-memory stub so ``start_conversation``
             and ``_persist_message`` don't hit Postgres.

    The factory yields a ``(service, app, rag_stub)`` triple per call.
    Callers drive the app with ``fastapi.testclient.TestClient(app)``
    (or ``httpx.AsyncClient(transport=ASGITransport(app))`` for async
    tests) and assert on the wire-level WebSocket messages the chat
    router emits.

    All ``DeepSeekAIService`` instances the factory creates are closed
    in the fixture finalizer so the underlying ``httpx.AsyncClient``
    instances release their mock transports cleanly.
    """
    from multimodal_librarian.api.dependencies import services as di_services
    from multimodal_librarian.api.dependencies.services import (
        ConnectionManager,
        get_ai_service,
        get_ai_service_optional,
        get_cached_rag_service,
        get_connection_manager_with_services,
        get_conversation_manager,
        get_rag_service,
    )
    from multimodal_librarian.api.routers.chat import router as chat_router

    created_services: List[DeepSeekAIService] = []

    def _make(
        transport: httpx.MockTransport,
        *,
        streaming_enabled: bool = True,
        model: str = _MOCK_MODEL,
    ) -> _AppFactoryResult:
        service = _build_deepseek_service_with_transport(
            transport,
            streaming_enabled=streaming_enabled,
            model=model,
        )
        created_services.append(service)

        rag_stub = _build_rag_service_stub(service)

        # In-memory ConversationManager stub so ``start_conversation``
        # and ``_persist_message`` calls are side-effect-free. The
        # ``MessageType`` enum imported by chat.py is not accessed on
        # this object, so a MagicMock is sufficient.
        mock_thread = MagicMock()
        mock_thread.thread_id = "test-thread-deepseek-streaming"
        mock_thread.created_at = "2025-01-01T00:00:00Z"
        mock_conv_manager = MagicMock()
        mock_conv_manager.start_conversation.return_value = mock_thread
        mock_conv_manager.process_message = MagicMock()

        manager = ConnectionManager()
        manager.set_services(
            rag_service=rag_stub,
            ai_service=service,
            readiness=None,
        )

        app = FastAPI()
        app.include_router(chat_router, tags=["chat"])

        async def _override_manager() -> ConnectionManager:
            return manager

        async def _override_conv_manager() -> MagicMock:
            return mock_conv_manager

        async def _override_ai_service() -> DeepSeekAIService:
            return service

        async def _override_ai_service_optional() -> DeepSeekAIService:
            return service

        async def _override_rag_service() -> MagicMock:
            return rag_stub

        async def _override_cached_rag_service() -> MagicMock:
            return rag_stub

        app.dependency_overrides[get_connection_manager_with_services] = (
            _override_manager
        )
        app.dependency_overrides[get_conversation_manager] = (
            _override_conv_manager
        )
        app.dependency_overrides[get_ai_service] = _override_ai_service
        app.dependency_overrides[get_ai_service_optional] = (
            _override_ai_service_optional
        )
        app.dependency_overrides[get_rag_service] = _override_rag_service
        app.dependency_overrides[get_cached_rag_service] = (
            _override_cached_rag_service
        )

        # Also short-circuit the module-level conversation-manager cache
        # that handler-internal code paths (``_get_legacy_components``,
        # ``_persist_message``) read directly instead of through the DI
        # graph. Cache the stub here and restore ``None`` after the
        # test so no cross-test state leaks.
        previous_conv_cache = di_services._conversation_manager_cache
        di_services._conversation_manager_cache = mock_conv_manager

        def _restore_cache() -> None:
            di_services._conversation_manager_cache = previous_conv_cache

        request.addfinalizer(_restore_cache)

        return service, app, rag_stub

    yield _make

    # Fixture finalizer: close every ``DeepSeekAIService`` we created so
    # its internal ``AsyncClient`` releases the MockTransport cleanly.
    # The MockTransport holds no real network resources, so failing to
    # aclose() gracefully is non-fatal; we log and continue.
    import asyncio

    for svc in created_services:
        client = svc._client
        svc._client = None  # Break the reference so repeat closes no-op.
        if client is None:
            continue
        try:
            # Prefer running on the existing loop when present (the
            # pytest-asyncio function-scoped loop). If no loop is
            # running in this thread, spin up a short-lived one just
            # for cleanup.
            try:
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    # Cannot run_until_complete on a running loop.
                    # Schedule a non-blocking close and move on.
                    asyncio.ensure_future(client.aclose(), loop=loop)
                    continue
                if loop.is_closed():
                    raise RuntimeError("loop closed")
            except RuntimeError:
                loop = asyncio.new_event_loop()
                try:
                    loop.run_until_complete(client.aclose())
                finally:
                    loop.close()
                continue
            loop.run_until_complete(client.aclose())
        except Exception as exc:  # pragma: no cover
            logger.warning(
                "DeepSeekAIService close failed in fixture finalizer: %s",
                exc,
            )


# ---------------------------------------------------------------------------
# Smoke tests — verify the helpers produce parser-compatible SSE bodies.
#
# These are not the full Task 12.2-12.10 integration tests (those are
# optional per ``tasks.md``); they only prove that the fixture file
# imports cleanly, the SSE bodies are round-trip-safe through the
# production parser, and the error/drop transports wire through
# ``httpx.AsyncClient.stream()`` correctly. Having at least one
# collectible test also lets ``pytest --collect-only`` confirm the
# file is importable in the project's test environment.
# ---------------------------------------------------------------------------


def test_mock_deepseek_stream_body_is_parser_compatible() -> None:
    """The body produced by ``mock_deepseek_stream`` round-trips through
    ``parse_sse_line``: concatenating every ``kind="delta"`` frame's
    content yields the original delta sequence.

    **Validates: Requirements 12.3 (helper contract)**
    """
    deltas = ["Hello ", "world", "!", " 你好", "🎉"]
    body = _render_sse_body(deltas, include_usage=True)
    parsed_deltas: List[str] = []
    done_seen = False
    usage_seen = False
    for line in body.decode("utf-8").splitlines():
        frame = parse_sse_line(line)
        if frame is None:
            continue
        if frame.kind == "delta":
            parsed_deltas.append(frame.delta_content or "")
        elif frame.kind == "done":
            done_seen = True
        elif frame.kind == "usage":
            usage_seen = True

    assert parsed_deltas == deltas, (
        f"Parser round-trip mismatch: expected {deltas!r}, "
        f"got {parsed_deltas!r}"
    )
    assert done_seen, "Rendered body is missing the terminal [DONE] frame"
    assert usage_seen, (
        "Rendered body is missing the terminal ``usage`` frame when "
        "``include_usage=True``"
    )


def test_mock_deepseek_stream_body_without_usage_is_parser_compatible() -> None:
    """When ``include_usage=False`` the rendered body contains no
    ``usage`` frame but still terminates cleanly with ``[DONE]``.
    """
    deltas = ["one", "two"]
    body = _render_sse_body(deltas, include_usage=False)
    parsed_deltas: List[str] = []
    done_seen = False
    usage_seen = False
    for line in body.decode("utf-8").splitlines():
        frame = parse_sse_line(line)
        if frame is None:
            continue
        if frame.kind == "delta":
            # Skip the finish-reason-only trailer (empty content).
            if frame.delta_content:
                parsed_deltas.append(frame.delta_content)
        elif frame.kind == "done":
            done_seen = True
        elif frame.kind == "usage":
            usage_seen = True

    assert parsed_deltas == deltas
    assert done_seen
    assert not usage_seen, (
        "``include_usage=False`` must not emit a ``usage`` frame"
    )


def test_mock_deepseek_stream_empty_deltas_yields_done_only() -> None:
    """An empty ``deltas`` list renders a body with no content-delta
    frames but still terminates with ``[DONE]``.

    **Validates: Requirements 7.4 (empty-stream contract)**
    """
    body = _render_sse_body([], include_usage=True)
    content_deltas = [
        parse_sse_line(line).delta_content  # type: ignore[union-attr]
        for line in body.decode("utf-8").splitlines()
        if parse_sse_line(line) is not None
        and parse_sse_line(line).kind == "delta"  # type: ignore[union-attr]
        and parse_sse_line(line).delta_content  # type: ignore[union-attr]
    ]
    assert content_deltas == [], (
        f"Expected no content deltas for empty ``deltas`` input, "
        f"got {content_deltas!r}"
    )
    assert b"data: [DONE]" in body


@pytest.mark.asyncio
async def test_mock_deepseek_stream_drives_deepseek_service() -> None:
    """End-to-end smoke: the rendered SSE body flows through the
    production ``DeepSeekAIService.generate_response_stream`` and
    produces content chunks whose concatenation equals the input
    deltas plus exactly one terminal chunk.

    This is the canonical "does the fixture actually work?" check.
    If ``parse_sse_line`` semantics ever diverge from what
    ``_render_sse_body`` produces, this test fails first.
    """
    deltas = ["alpha ", "beta ", "gamma"]
    transport = mock_deepseek_stream(deltas, include_usage=True)
    service = _build_deepseek_service_with_transport(transport)
    try:
        content_chunks: List[AIResponse] = []
        async for chunk in service.generate_response_stream(
            messages=[{"role": "user", "content": "hi"}],
            context=None,
            temperature=0.7,
            max_tokens=16,
            preferred_provider=None,
        ):
            content_chunks.append(chunk)

        # At least one chunk must be yielded (Req 2.4) and exactly one
        # must be terminal.
        assert len(content_chunks) >= 1
        terminal_indices = [
            i
            for i, c in enumerate(content_chunks)
            if (c.metadata or {}).get("is_final") is True
        ]
        assert len(terminal_indices) == 1, (
            "Exactly one terminal chunk must be yielded; got "
            f"{len(terminal_indices)} in {content_chunks!r}"
        )
        assert terminal_indices[0] == len(content_chunks) - 1, (
            "Terminal chunk must be the last yielded chunk"
        )

        # Concatenated non-terminal content must equal the input deltas.
        non_terminal_content = "".join(
            c.content
            for c in content_chunks
            if not (c.metadata or {}).get("is_final")
        )
        assert non_terminal_content == "".join(deltas), (
            f"Content mismatch: expected {''.join(deltas)!r}, "
            f"got {non_terminal_content!r}"
        )

        # Every chunk advertises the DeepSeek provider and model.
        for c in content_chunks:
            assert c.provider == "deepseek"
            assert c.model == _MOCK_MODEL
    finally:
        await service.close()


@pytest.mark.asyncio
async def test_mock_deepseek_error_drives_deepseek_service() -> None:
    """HTTP-error transports produce exactly one terminal error chunk
    whose ``error_type`` matches the service's classification.
    """
    transport = mock_deepseek_error(500)
    service = _build_deepseek_service_with_transport(transport)
    try:
        chunks: List[AIResponse] = []
        async for chunk in service.generate_response_stream(
            messages=[{"role": "user", "content": "hi"}],
            context=None,
            temperature=0.7,
            max_tokens=16,
            preferred_provider=None,
        ):
            chunks.append(chunk)

        assert len(chunks) == 1
        terminal = chunks[0]
        meta = terminal.metadata or {}
        assert meta.get("is_final") is True
        # classify_http_status(500) -> MODEL_OVERLOADED.
        assert meta.get("error_type") == "model_overloaded"
        assert meta.get("recoverable") is True
    finally:
        await service.close()


@pytest.mark.asyncio
async def test_mock_deepseek_error_429_retry_after_is_propagated() -> None:
    """A 429 response with a numeric ``Retry-After`` header surfaces on
    the terminal chunk as ``metadata["retry_after_seconds"]``.

    **Validates: Requirements 6.2 (helper contract)**
    """
    transport = mock_deepseek_error(429, retry_after=30)
    service = _build_deepseek_service_with_transport(transport)
    try:
        chunks: List[AIResponse] = []
        async for chunk in service.generate_response_stream(
            messages=[{"role": "user", "content": "hi"}],
            context=None,
            temperature=0.7,
            max_tokens=16,
            preferred_provider=None,
        ):
            chunks.append(chunk)

        assert len(chunks) == 1
        meta = chunks[0].metadata or {}
        assert meta.get("error_type") == "rate_limit"
        assert meta.get("retry_after_seconds") == 30.0
    finally:
        await service.close()


@pytest.mark.asyncio
async def test_mock_deepseek_network_drop_drives_deepseek_service() -> None:
    """Mid-stream network drop produces the content chunks received
    before the drop followed by exactly one terminal ``network_error``
    chunk.

    **Validates: Requirements 6.4, 12.5 (helper contract)**
    """
    deltas = ["one", "two", "three", "four", "five"]
    transport = mock_deepseek_network_drop_after(3, deltas=deltas)
    service = _build_deepseek_service_with_transport(transport)
    try:
        chunks: List[AIResponse] = []
        async for chunk in service.generate_response_stream(
            messages=[{"role": "user", "content": "hi"}],
            context=None,
            temperature=0.7,
            max_tokens=16,
            preferred_provider=None,
        ):
            chunks.append(chunk)

        # 3 content chunks + 1 terminal error chunk.
        assert len(chunks) == 4
        # First three chunks are non-terminal deltas.
        content_received = "".join(
            c.content
            for c in chunks[:3]
            if not (c.metadata or {}).get("is_final")
        )
        assert content_received == "onetwothree"
        # Terminal chunk has the network_error classification.
        terminal = chunks[-1]
        meta = terminal.metadata or {}
        assert meta.get("is_final") is True
        assert meta.get("error_type") == "network_error"
        assert meta.get("recoverable") is True
    finally:
        await service.close()


def test_factory_fixture_builds_app_with_overrides(
    make_app_with_mocked_deepseek: Callable[..., _AppFactoryResult],
) -> None:
    """The ``make_app_with_mocked_deepseek`` fixture installs all
    expected DI overrides and returns a closable service handle.

    This is the structural contract for Tasks 12.2-12.10: they call the
    factory, grab the ``TestClient(app)``, and drive the WebSocket. If
    any of the overrides go missing this test catches it before the
    downstream tests run.
    """
    from multimodal_librarian.api.dependencies.services import (
        get_ai_service,
        get_ai_service_optional,
        get_cached_rag_service,
        get_connection_manager_with_services,
        get_conversation_manager,
        get_rag_service,
    )

    transport = mock_deepseek_stream(["a", "b"])
    service, app, rag_stub = make_app_with_mocked_deepseek(transport)

    assert isinstance(service, DeepSeekAIService)
    assert service.streaming_enabled_config is True
    assert service.provider_name == "deepseek"

    # Required DI overrides are present.
    for dep in (
        get_ai_service,
        get_ai_service_optional,
        get_rag_service,
        get_cached_rag_service,
        get_connection_manager_with_services,
        get_conversation_manager,
    ):
        assert dep in app.dependency_overrides, (
            f"Expected DI override for {dep.__name__}; present overrides: "
            f"{[d.__name__ for d in app.dependency_overrides]}"
        )

    # RAG stub exposes the streaming method expected by the chat handler.
    assert hasattr(rag_stub, "generate_response_stream")
    assert callable(rag_stub.generate_response_stream)


if __name__ == "__main__":  # pragma: no cover
    pytest.main([__file__, "-v", "-s"])
