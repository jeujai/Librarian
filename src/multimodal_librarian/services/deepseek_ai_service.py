"""
DeepSeek AI service for training data generation.

Drop-in replacement for OllamaAIService that uses the DeepSeek API
(OpenAI-compatible) for higher-quality medical Q&A generation.

The service implements the same ``generate_response`` interface that
``RAGService`` expects, so it can be swapped in transparently.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import time
import uuid
from collections import deque
from dataclasses import dataclass
from typing import Any, AsyncGenerator, Deque, Dict, List, Literal, Optional

import httpx

from .ai_service import AIResponse
from .provider_resilience import (
    USER_FRIENDLY_ERROR_MESSAGES,
    CircuitBreaker,
    ErrorRateTracker,
    ErrorType,
    ProviderError,
    classify_http_status,
)

logger = logging.getLogger(__name__)

_DEFAULT_BASE_URL = "https://api.deepseek.com"
_DEFAULT_MODEL = "deepseek-chat"
_DEFAULT_TIMEOUT = 120.0


def _parse_float_env(name: str, default: float) -> float:
    """Parse a float env var, falling back to ``default`` with WARN on error.

    This helper never raises: if the environment variable is present but
    cannot be parsed as a float, a WARNING is logged with the offending value
    and ``default`` is returned. Absent env vars also return ``default``.
    """
    raw = os.environ.get(name)
    if raw is None:
        return default
    try:
        return float(raw)
    except ValueError:
        logger.warning(
            "Invalid float value for %s=%r; falling back to default %s",
            name,
            raw,
            default,
        )
        return default


@dataclass(frozen=True)
class SSEFrame:
    """A single parsed Server-Sent Event frame from DeepSeek's streaming API.

    This is the internal representation used by :func:`parse_sse_line` and the
    streaming loop inside :class:`DeepSeekAIService`. It never crosses the
    service boundary; callers outside this module receive ``AIResponse``
    objects, not ``SSEFrame`` objects.

    Attributes:
        kind: The category of frame.

            - ``"delta"``: Frame carries an incremental content fragment.
            - ``"done"``: Terminal ``data: [DONE]`` sentinel.
            - ``"usage"``: Frame with no delta content but a top-level
              ``usage`` object (DeepSeek emits this on the last chunk when
              ``stream_options.include_usage=true``).
            - ``"malformed"``: Payload was not valid JSON.
            - ``"empty"``: Frame with no delta content and no usage (e.g. the
              first frame that carries only ``delta: {"role": "assistant"}``).
        delta_content: The ``choices[0].delta.content`` text for
            ``kind="delta"`` frames; otherwise ``None``.
        finish_reason: The ``choices[0].finish_reason`` if present on the
            frame; otherwise ``None``.
        usage: The top-level ``usage`` object when present; otherwise ``None``.
        raw_line: The raw payload (truncated to 200 chars) for
            ``kind="malformed"`` frames; otherwise ``None``.
    """

    kind: Literal["delta", "done", "usage", "malformed", "empty"]
    delta_content: Optional[str] = None
    finish_reason: Optional[str] = None
    usage: Optional[Dict[str, int]] = None
    raw_line: Optional[str] = None


def parse_sse_line(line: str) -> Optional[SSEFrame]:
    """Parse a single SSE line from DeepSeek's streaming response.

    This is a pure function with no I/O; it is safe to call on arbitrary
    strings and never raises. It is the sole JSON-decoding seam for the
    streaming client, which makes the streaming loop trivially
    property-testable.

    Args:
        line: A single line read from the SSE response body (without a
            trailing newline, as returned by ``httpx.Response.aiter_lines``).

    Returns:
        ``None`` for blank lines, SSE comment lines (starting with ``:``), and
        other non-``data:`` lines (e.g. ``event:``, ``retry:``). Otherwise an
        :class:`SSEFrame` classifying the frame:

        - ``data: [DONE]`` → ``SSEFrame(kind="done")``.
        - Invalid JSON payload → ``SSEFrame(kind="malformed", raw_line=...)``
          with the payload truncated to 200 characters.
        - Frame with non-empty ``choices[0].delta.content`` →
          ``SSEFrame(kind="delta", delta_content=..., finish_reason=...,
          usage=...)``.
        - Frame with no delta content but a top-level ``usage`` object →
          ``SSEFrame(kind="usage", usage=..., finish_reason=...)``.
        - Otherwise (e.g. the first frame with only a role delta) →
          ``SSEFrame(kind="empty", finish_reason=...)``.
    """
    line = line.strip()
    if not line or not line.startswith("data:"):
        return None
    payload = line[len("data:"):].strip()
    if payload == "[DONE]":
        return SSEFrame(kind="done")
    try:
        obj = json.loads(payload)
    except json.JSONDecodeError:
        return SSEFrame(kind="malformed", raw_line=payload[:200])
    choice = (obj.get("choices") or [{}])[0]
    delta = (choice.get("delta") or {}).get("content") or ""
    finish = choice.get("finish_reason")
    usage = obj.get("usage")
    if delta:
        return SSEFrame(
            kind="delta",
            delta_content=delta,
            finish_reason=finish,
            usage=usage,
        )
    if usage is not None:
        return SSEFrame(kind="usage", usage=usage, finish_reason=finish)
    return SSEFrame(kind="empty", finish_reason=finish)


class DeepSeekAIService:
    """AI service backed by the DeepSeek API.

    Uses the OpenAI-compatible chat completions endpoint.

    Args:
        api_key: DeepSeek API key. Defaults to ``DEEPSEEK_API_KEY`` env var.
        model: Model name (default ``deepseek-chat`` for V3).
        base_url: API base URL.
        timeout: Request timeout in seconds.
    """

    provider_name: str = "deepseek"

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: Optional[str] = None,
        base_url: Optional[str] = None,
        timeout: Optional[float] = None,
    ) -> None:
        self.api_key: str = api_key or os.environ.get(
            "DEEPSEEK_API_KEY", ""
        )
        if not self.api_key:
            raise RuntimeError(
                "DEEPSEEK_API_KEY not set. Provide it via environment "
                "variable or constructor argument."
            )

        self.model: str = model or os.environ.get(
            "DEEPSEEK_MODEL", _DEFAULT_MODEL
        )
        self.base_url: str = base_url or os.environ.get(
            "DEEPSEEK_BASE_URL", _DEFAULT_BASE_URL
        )
        self.timeout: float = timeout or float(
            os.environ.get("DEEPSEEK_TIMEOUT", str(_DEFAULT_TIMEOUT))
        )
        self._client: Optional[httpx.AsyncClient] = None
        # Tracks the event loop the cached ``_client`` is bound to so we
        # can detect (and transparently recover from) reuse across
        # separate ``asyncio.run`` boundaries. ``httpx.AsyncClient``'s
        # transport pool is attached to the loop that created it; reusing
        # it after that loop is closed raises
        # ``RuntimeError("Event loop is closed")``.
        self._client_loop: Optional[asyncio.AbstractEventLoop] = None

        # Stats
        self._total_calls = 0
        self._successful_calls = 0
        self._failed_calls = 0

        # -------------------------------------------------------------
        # Streaming configuration (read from environment)
        # -------------------------------------------------------------
        self.streaming_enabled_config: bool = (
            os.environ.get("DEEPSEEK_STREAMING_ENABLED", "true")
            .strip()
            .lower()
            == "true"
        )
        self.stream_ttft_timeout: float = _parse_float_env(
            "DEEPSEEK_STREAM_TIMEOUT", 60.0
        )
        self.stream_total_timeout: float = _parse_float_env(
            "DEEPSEEK_STREAM_TOTAL_TIMEOUT", 180.0
        )
        self.stream_include_usage: bool = (
            os.environ.get("DEEPSEEK_STREAM_INCLUDE_USAGE", "true")
            .strip()
            .lower()
            == "true"
        )

        # -------------------------------------------------------------
        # Shared resilience primitives (circuit breaker + error-rate tracker)
        # -------------------------------------------------------------
        self._circuit_breaker = CircuitBreaker()
        self._error_rate_tracker = ErrorRateTracker()

        # -------------------------------------------------------------
        # Streaming metrics (counters + bounded sample deques)
        # -------------------------------------------------------------
        self._stream_total: int = 0
        self._stream_success: int = 0
        self._stream_failed: int = 0
        self._stream_duration_samples: Deque[float] = deque(maxlen=100)
        self._stream_ttft_samples: Deque[float] = deque(maxlen=100)
        self._stream_chunks_samples: Deque[int] = deque(maxlen=100)

        logger.info(
            "DeepSeekAIService initialised: model=%s, base_url=%s, "
            "timeout=%.0fs",
            self.model,
            self.base_url,
            self.timeout,
        )

    async def _get_client(self) -> httpx.AsyncClient:
        # ``httpx.AsyncClient`` binds its transport pool to the event loop
        # that first uses it; when the evaluation CLI previously invoked
        # ``asyncio.run`` twice (once for ``verify_available`` and once for
        # the evaluation loop) the cached client was still bound to the
        # first, now-closed loop and every request raised
        # ``RuntimeError("Event loop is closed")``. Detect a loop change or
        # a closed tracked loop and rebuild a fresh client in that case.
        current_loop = asyncio.get_running_loop()
        needs_new_client = (
            self._client is None
            or self._client_loop is None
            or self._client_loop is not current_loop
            or self._client_loop.is_closed()
        )
        if needs_new_client:
            if self._client is not None:
                # Best-effort close of the stale client; the underlying
                # loop may already be closed, in which case ``aclose``
                # itself can raise. Suppress so a stale client never
                # blocks the fresh loop.
                try:
                    await self._client.aclose()
                except Exception:
                    pass
                self._client = None
            new_client = httpx.AsyncClient(
                base_url=self.base_url,
                timeout=httpx.Timeout(self.timeout),
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
                limits=httpx.Limits(
                    max_keepalive_connections=5,
                    max_connections=10,
                ),
            )
            self._client = new_client
            self._client_loop = current_loop
            return new_client
        # ``self._client`` is guaranteed non-None here by the branch above.
        assert self._client is not None
        return self._client

    async def close(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None
        self._client_loop = None

    async def verify_available(self) -> None:
        """Confirm the DeepSeek API is reachable.

        Sends a minimal test prompt to verify connectivity and auth.
        """
        logger.info(
            "DeepSeekAIService: Pre-flight check — verifying model "
            "'%s' at %s",
            self.model,
            self.base_url,
        )
        try:
            client = await self._get_client()
            resp = await client.post(
                "/chat/completions",
                json={
                    "model": self.model,
                    "messages": [
                        {"role": "user", "content": "Say OK."}
                    ],
                    "max_tokens": 5,
                },
                timeout=30.0,
            )
        except Exception as exc:
            raise RuntimeError(
                f"PREFLIGHT FAILED: Cannot reach DeepSeek API at "
                f"{self.base_url}. Error: {exc}"
            ) from exc

        if resp.status_code != 200:
            raise RuntimeError(
                f"PREFLIGHT FAILED: DeepSeek returned HTTP "
                f"{resp.status_code}: {resp.text[:300]}"
            )

        data = resp.json()
        content = (
            data.get("choices", [{}])[0]
            .get("message", {})
            .get("content", "")
        )
        logger.info(
            "DeepSeekAIService: Pre-flight PASSED — model '%s' "
            "responded: %s",
            self.model,
            content[:50],
        )

    def _merge_context(
        self,
        messages: List[Dict[str, str]],
        context: Optional[str],
    ) -> List[Dict[str, str]]:
        """Return ``messages`` with ``context`` appended to the user message.

        Mirrors the inline context-merge behavior inside
        :meth:`generate_response` so that the streaming path
        (:meth:`generate_response_stream`) produces identical merged
        payloads. The helper is pure and never mutates its inputs; when a
        merge is performed, the returned list contains the original dict
        references for all elements except the last, which is a newly
        allocated dict.

        Args:
            messages: Chat messages. Each dict has ``role`` and
                ``content`` keys.
            context: Optional additional context to append to the last
                user message. When ``None`` or an empty string, ``messages``
                is returned unchanged (same reference).

        Returns:
            The original ``messages`` reference when ``context`` is falsy,
            when ``messages`` is empty, or when the last message's role is
            not ``"user"``. Otherwise a new list whose elements before the
            last are the same dict references from the input, and whose
            last element is a new dict with ``role="user"`` and ``content``
            equal to ``original_content + "\n\nAdditional context:\n" +
            context``.
        """
        if not context:
            return messages
        if not messages:
            return messages
        last = messages[-1]
        if last.get("role") != "user":
            return messages
        merged_last = {
            "role": "user",
            "content": last["content"]
            + "\n\nAdditional context:\n"
            + context,
        }
        return [*messages[:-1], merged_last]

    async def generate_response(
        self,
        messages: List[Dict[str, str]],
        context: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: int = 2048,
        preferred_provider: Optional[Any] = None,
    ) -> AIResponse:
        """Generate a response via the DeepSeek chat completions API.

        Signature matches ``AIService.generate_response`` for
        transparent use with ``RAGService``.
        """
        self._total_calls += 1
        start = time.time()

        if context:
            messages = list(messages)
            if messages and messages[-1].get("role") == "user":
                messages[-1] = {
                    "role": "user",
                    "content": (
                        messages[-1]["content"]
                        + "\n\nAdditional context:\n"
                        + context
                    ),
                }

        try:
            client = await self._get_client()

            payload = {
                "model": self.model,
                "messages": messages,
                "temperature": temperature,
                "max_tokens": max_tokens,
            }

            response = await client.post(
                "/chat/completions", json=payload
            )

            elapsed_ms = int((time.time() - start) * 1000)

            if response.status_code != 200:
                self._failed_calls += 1
                error_msg = (
                    f"DeepSeek API error: {response.status_code} — "
                    f"{response.text[:200]}"
                )
                logger.error(error_msg)
                return AIResponse(
                    content=error_msg,
                    provider="deepseek",
                    model=self.model,
                    tokens_used=0,
                    processing_time_ms=elapsed_ms,
                    confidence_score=0.0,
                    metadata={
                        "finish_reason": "error",
                        "error": error_msg,
                    },
                )

            data = response.json()
            choice = data.get("choices", [{}])[0]
            content = choice.get("message", {}).get("content", "")
            finish_reason = choice.get("finish_reason", "unknown")

            usage = data.get("usage", {})
            prompt_tokens = usage.get("prompt_tokens", 0)
            completion_tokens = usage.get("completion_tokens", 0)
            total_tokens = usage.get("total_tokens", 0)

            self._successful_calls += 1

            logger.debug(
                "DeepSeekAIService: %d prompt + %d completion tokens "
                "in %dms (model=%s)",
                prompt_tokens,
                completion_tokens,
                elapsed_ms,
                self.model,
            )

            return AIResponse(
                content=content,
                provider="deepseek",
                model=self.model,
                tokens_used=total_tokens,
                processing_time_ms=elapsed_ms,
                confidence_score=1.0,
                metadata={
                    "finish_reason": finish_reason,
                    "prompt_tokens": prompt_tokens,
                    "completion_tokens": completion_tokens,
                },
            )

        except httpx.TimeoutException:
            elapsed_ms = int((time.time() - start) * 1000)
            self._failed_calls += 1
            error_msg = (
                f"DeepSeek request timed out after "
                f"{self.timeout:.0f}s (model={self.model})"
            )
            logger.error(error_msg)
            return AIResponse(
                content=error_msg,
                provider="deepseek",
                model=self.model,
                tokens_used=0,
                processing_time_ms=elapsed_ms,
                confidence_score=0.0,
                metadata={
                    "finish_reason": "timeout",
                    "error": error_msg,
                },
            )

        except Exception as exc:
            elapsed_ms = int((time.time() - start) * 1000)
            self._failed_calls += 1
            error_msg = f"DeepSeek generation failed: {exc}"
            logger.error(error_msg)
            return AIResponse(
                content=error_msg,
                provider="deepseek",
                model=self.model,
                tokens_used=0,
                processing_time_ms=elapsed_ms,
                confidence_score=0.0,
                metadata={
                    "finish_reason": "error",
                    "error": error_msg,
                },
            )

    def get_available_providers(self) -> List[str]:
        return ["deepseek"]

    # -----------------------------------------------------------------
    # Streaming: private chunk constructors
    # -----------------------------------------------------------------

    def _make_circuit_breaker_chunk(
        self, call_id: str
    ) -> AIResponse:
        """Build the terminal chunk yielded when the breaker is OPEN.

        No HTTP request is issued when this chunk is used; the breaker has
        decided the upstream provider is unhealthy and callers should
        retry later (``recoverable=True``).
        """
        retry_after = getattr(
            self._circuit_breaker.config,
            "reset_timeout_seconds",
            30.0,
        )
        user_message = USER_FRIENDLY_ERROR_MESSAGES[
            ErrorType.CIRCUIT_BREAKER
        ]
        return AIResponse(
            content=user_message,
            provider="deepseek",
            model=self.model,
            tokens_used=0,
            processing_time_ms=0,
            confidence_score=0.0,
            metadata={
                "is_final": True,
                "chunk_index": 0,
                "error_type": ErrorType.CIRCUIT_BREAKER.value,
                "recoverable": True,
                "retry_after_seconds": float(retry_after),
                "user_message": user_message,
                "finish_reason": "circuit_breaker",
                "call_id": call_id,
            },
        )

    def _make_http_error_chunk(
        self,
        status_code: int,
        body: str,
        *,
        chunk_index: int,
        call_id: str,
        duration_ms: int,
        retry_after_header: Optional[str] = None,
    ) -> AIResponse:
        """Build the terminal chunk yielded when DeepSeek returns non-2xx.

        Uses :func:`classify_http_status` to translate the status code into
        an :class:`ErrorType` and sets the appropriate recoverability and
        retry-after hints on the chunk metadata. The ``body`` is truncated
        to 500 characters before being embedded in ``metadata["error"]``.
        """
        body_excerpt = (body or "")[:500]
        error_type = classify_http_status(status_code, body_excerpt)

        recoverable = error_type in {
            ErrorType.RATE_LIMIT,
            ErrorType.MODEL_OVERLOADED,
            ErrorType.NETWORK_ERROR,
            ErrorType.TIMEOUT,
        }

        user_message = USER_FRIENDLY_ERROR_MESSAGES[error_type]

        metadata: Dict[str, Any] = {
            "is_final": True,
            "chunk_index": chunk_index,
            "error_type": error_type.value,
            "recoverable": recoverable,
            "error": f"HTTP {status_code}: {body_excerpt}",
            "user_message": user_message,
            "finish_reason": "error",
            "call_id": call_id,
            "duration_ms": duration_ms,
        }

        if error_type == ErrorType.RATE_LIMIT:
            # Prefer the provider's Retry-After hint when available and
            # parseable; otherwise default to 60 seconds (Req 6.2).
            retry_after: float = 60.0
            if retry_after_header:
                try:
                    retry_after = float(retry_after_header)
                except (TypeError, ValueError):
                    # Ignore non-numeric Retry-After values (e.g. HTTP-date
                    # format) and stick with the default.
                    retry_after = 60.0
            metadata["retry_after_seconds"] = retry_after
        elif error_type == ErrorType.MODEL_OVERLOADED:
            metadata["retry_after_seconds"] = 30.0

        return AIResponse(
            content=user_message,
            provider="deepseek",
            model=self.model,
            tokens_used=0,
            processing_time_ms=duration_ms,
            confidence_score=0.0,
            metadata=metadata,
        )

    def _make_final_chunk(
        self,
        *,
        chunk_index: int,
        finish_reason: str,
        usage: Optional[Dict[str, int]],
        duration_ms: int,
        cumulative_chars: int,
        call_id: str,
    ) -> AIResponse:
        """Build the terminal chunk yielded on a clean ``[DONE]``.

        When DeepSeek provided a ``usage`` object we populate
        ``tokens_used`` from ``usage.total_tokens``; otherwise fall back to
        a rough estimate of ``cumulative_chars // 4`` so callers always
        see a non-zero value for successful generations.
        """
        usage = usage or {}
        prompt_tokens = int(usage.get("prompt_tokens", 0))
        completion_tokens = int(usage.get("completion_tokens", 0))
        total_tokens = usage.get("total_tokens")
        if total_tokens is None:
            tokens_used = cumulative_chars // 4
        else:
            tokens_used = int(total_tokens)

        return AIResponse(
            content="",
            provider="deepseek",
            model=self.model,
            tokens_used=tokens_used,
            processing_time_ms=duration_ms,
            confidence_score=1.0,
            metadata={
                "is_final": True,
                "chunk_index": chunk_index,
                "finish_reason": finish_reason,
                "prompt_tokens": prompt_tokens,
                "completion_tokens": completion_tokens,
                "call_id": call_id,
            },
        )

    def _make_content_blocked_chunk(
        self, chunk_index: int, call_id: str
    ) -> AIResponse:
        """Build the terminal chunk yielded when DeepSeek content-filters.

        Content-filter rejections represent a successful API call that
        refused to emit a response; the breaker/error-rate tracker should
        record ``success`` for this outcome (Req 6.5).
        """
        user_message = USER_FRIENDLY_ERROR_MESSAGES[
            ErrorType.CONTENT_BLOCKED
        ]
        return AIResponse(
            content=user_message,
            provider="deepseek",
            model=self.model,
            tokens_used=0,
            processing_time_ms=0,
            confidence_score=0.0,
            metadata={
                "is_final": True,
                "chunk_index": chunk_index,
                "error_type": ErrorType.CONTENT_BLOCKED.value,
                "recoverable": False,
                "user_message": user_message,
                "finish_reason": "content_filter",
                "call_id": call_id,
            },
        )

    # -----------------------------------------------------------------
    # Streaming: non-streaming fallback wrapper
    # -----------------------------------------------------------------

    async def _streaming_disabled_fallback(
        self,
        messages: List[Dict[str, str]],
        context: Optional[str],
        temperature: float,
        max_tokens: int,
        preferred_provider: Optional[Any],
        call_id: str,
    ) -> AsyncGenerator[AIResponse, None]:
        """Emit a single terminal chunk produced by ``generate_response``.

        Used when streaming is disabled by feature flag, by the error-rate
        tracker, or (implicitly) when the caller falls back from a failed
        stream. The yielded chunk carries ``streaming_fallback=True`` and
        ``is_final=True`` so downstream consumers know it is the single
        terminal chunk in this response.
        """
        response = await self.generate_response(
            messages=messages,
            context=context,
            temperature=temperature,
            max_tokens=max_tokens,
            preferred_provider=preferred_provider,
        )
        metadata: Dict[str, Any] = dict(response.metadata or {})
        metadata["streaming_fallback"] = True
        metadata["is_final"] = True
        metadata["chunk_index"] = 0
        metadata.setdefault("call_id", call_id)
        yield AIResponse(
            content=response.content,
            provider=response.provider,
            model=response.model,
            tokens_used=response.tokens_used,
            processing_time_ms=response.processing_time_ms,
            confidence_score=response.confidence_score,
            metadata=metadata,
        )

    # -----------------------------------------------------------------
    # Streaming: the main SSE client
    # -----------------------------------------------------------------

    async def generate_response_stream(
        self,
        messages: List[Dict[str, str]],
        context: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: int = 4096,
        preferred_provider: Optional[Any] = None,
    ) -> AsyncGenerator[AIResponse, None]:
        """Stream the DeepSeek chat-completions response token-by-token.

        Issues a single ``POST /chat/completions`` request with
        ``stream=true`` and yields one ``AIResponse`` per non-empty
        ``choices[0].delta.content`` frame, terminated by exactly one
        final ``AIResponse`` with ``metadata["is_final"]=True``. The
        generator yields at least one chunk for every call that does not
        raise externally (Req 2.4): all branches (disabled, breaker open,
        HTTP error, timeout, content filter, or clean ``[DONE]``) emit
        either deltas plus a final chunk or a single terminal chunk.

        Resilience pre-flight:
        - When ``self.streaming_enabled_config`` is false, or the shared
          error-rate tracker has disabled streaming, the call is delegated
          to :meth:`_streaming_disabled_fallback`.
        - When the circuit breaker denies the request, a single terminal
          chunk with ``error_type="circuit_breaker"`` is yielded and no
          HTTP request is issued (Req 5.2).

        Cancellation:
        - Client disconnects propagate as ``GeneratorExit``; the
          ``async with client.stream(...)`` context manager closes the TCP
          connection on exit, terminating the DeepSeek generation
          server-side. A ``deepseek_stream_aborted`` INFO log is emitted
          in the ``finally`` block in that case.

        Args:
            messages: Chat messages. Each dict has ``role`` / ``content``.
            context: Optional extra context merged into the last user
                message via :meth:`_merge_context`.
            temperature: Sampling temperature for the model.
            max_tokens: Maximum completion tokens.
            preferred_provider: Accepted for API compatibility with the
                Gemini ``AIService.generate_response_stream``; unused
                because this service only has one provider.

        Yields:
            ``AIResponse`` chunks. For the happy path: zero or more
            chunks with ``metadata["is_final"]=False`` followed by exactly
            one chunk with ``metadata["is_final"]=True``. For every error
            branch: exactly one terminal chunk with
            ``metadata["is_final"]=True`` and an ``error_type`` field.
        """
        call_id = uuid.uuid4().hex[:8]
        start_time = time.time()
        self._stream_total += 1

        # Structured stream-start log (Req 9.1). Emitted before any
        # pre-flight checks so that every invocation is observable in
        # logs, including fallback and circuit-breaker paths.
        prompt_chars = sum(
            len(m.get("content") or "") for m in messages
        )
        logger.info(
            "deepseek_stream_start",
            extra={
                "event": "deepseek_stream_start",
                "call_id": call_id,
                "model": self.model,
                "prompt_chars": prompt_chars,
                "message_count": len(messages),
                "temperature": temperature,
                "max_tokens": max_tokens,
            },
        )

        # Pre-flight: feature flag.
        if not self.streaming_enabled_config:
            async for chunk in self._streaming_disabled_fallback(
                messages,
                context,
                temperature,
                max_tokens,
                preferred_provider,
                call_id,
            ):
                yield chunk
            return

        # Pre-flight: error-rate tracker soft-disable.
        if not self._error_rate_tracker.streaming_enabled:
            async for chunk in self._streaming_disabled_fallback(
                messages,
                context,
                temperature,
                max_tokens,
                preferred_provider,
                call_id,
            ):
                yield chunk
            return

        # Pre-flight: circuit breaker.
        if not await self._circuit_breaker.allow_request():
            logger.warning(
                "deepseek_stream_circuit_open",
                extra={
                    "event": "deepseek_stream_circuit_open",
                    "call_id": call_id,
                },
            )
            yield self._make_circuit_breaker_chunk(call_id)
            return

        # Build request.
        merged_messages = self._merge_context(messages, context)
        payload: Dict[str, Any] = {
            "model": self.model,
            "messages": merged_messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": True,
        }
        if self.stream_include_usage:
            payload["stream_options"] = {"include_usage": True}

        chunk_index = 0
        cumulative_chars = 0
        final_usage: Optional[Dict[str, int]] = None
        final_finish_reason: str = "stop"
        first_token_at: Optional[float] = None
        aborted = False

        try:
            client = await self._get_client()
            timeout = httpx.Timeout(
                connect=self.timeout,
                read=self.stream_ttft_timeout,
                write=self.timeout,
                pool=self.timeout,
            )

            try:
                async with client.stream(
                    "POST",
                    "/chat/completions",
                    json=payload,
                    timeout=timeout,
                ) as resp:
                    # Non-2xx: drain body (<=1000 chars), record failure,
                    # yield one terminal error chunk, return (Req 1.7).
                    if resp.status_code != 200:
                        raw_body = await resp.aread()
                        body = raw_body.decode(
                            "utf-8", errors="replace"
                        )[:1000]
                        duration_ms = int(
                            (time.time() - start_time) * 1000
                        )
                        body_excerpt = body[:500]
                        http_error_type = classify_http_status(
                            resp.status_code, body_excerpt
                        )
                        # Structured stream-error log (Req 9.4).
                        logger.error(
                            "deepseek_stream_error",
                            extra={
                                "event": "deepseek_stream_error",
                                "call_id": call_id,
                                "duration_ms": duration_ms,
                                "chunks_received_before_error": (
                                    chunk_index
                                ),
                                "error_type": http_error_type.value,
                                "error_message": (
                                    f"HTTP {resp.status_code}: "
                                    f"{body_excerpt}"
                                )[:500],
                            },
                        )
                        await self._circuit_breaker.record_failure()
                        await self._error_rate_tracker.record_call(
                            success=False
                        )
                        self._stream_failed += 1
                        retry_after_hdr = resp.headers.get(
                            "Retry-After"
                        )
                        yield self._make_http_error_chunk(
                            resp.status_code,
                            body,
                            chunk_index=chunk_index,
                            call_id=call_id,
                            duration_ms=duration_ms,
                            retry_after_header=retry_after_hdr,
                        )
                        return

                    # 200 OK: iterate SSE frames. Enforce the overall
                    # stream deadline via an elapsed-time check before each
                    # iteration; wrapping ``async for`` in ``asyncio.
                    # wait_for`` would cancel the generator and lose any
                    # partial content already yielded.
                    content_filter_triggered = False
                    total_deadline = (
                        start_time + self.stream_total_timeout
                    )

                    async for line in resp.aiter_lines():
                        if time.time() > total_deadline:
                            # Total-timeout budget exhausted.
                            duration_ms = int(
                                (time.time() - start_time) * 1000
                            )
                            # Structured stream-error log (Req 9.4).
                            logger.error(
                                "deepseek_stream_error",
                                extra={
                                    "event": "deepseek_stream_error",
                                    "call_id": call_id,
                                    "duration_ms": duration_ms,
                                    "chunks_received_before_error": (
                                        chunk_index
                                    ),
                                    "error_type": (
                                        ErrorType.TIMEOUT.value
                                    ),
                                    "error_message": (
                                        "Total stream timeout "
                                        f"exceeded "
                                        f"({self.stream_total_timeout}s)"
                                    )[:500],
                                },
                            )
                            await self._circuit_breaker.record_failure()
                            await self._error_rate_tracker.record_call(
                                success=False
                            )
                            self._stream_failed += 1
                            yield AIResponse(
                                content=USER_FRIENDLY_ERROR_MESSAGES[
                                    ErrorType.TIMEOUT
                                ],
                                provider="deepseek",
                                model=self.model,
                                tokens_used=cumulative_chars // 4,
                                processing_time_ms=duration_ms,
                                confidence_score=0.0,
                                metadata={
                                    "is_final": True,
                                    "chunk_index": chunk_index,
                                    "finish_reason": "timeout",
                                    "error_type": (
                                        ErrorType.TIMEOUT.value
                                    ),
                                    "recoverable": True,
                                    "user_message":
                                        USER_FRIENDLY_ERROR_MESSAGES[
                                            ErrorType.TIMEOUT
                                        ],
                                    "call_id": call_id,
                                    "duration_ms": duration_ms,
                                },
                            )
                            return

                        frame = parse_sse_line(line)
                        if frame is None:
                            continue

                        if frame.kind == "malformed":
                            # Structured malformed-chunk log (Req 1.6).
                            # ``parse_sse_line`` already truncates
                            # ``raw_line`` to 200 chars on malformed
                            # frames; the defensive ``[:200]`` here
                            # guarantees the cap even if the parser's
                            # invariant is ever relaxed, and guards
                            # against ``None`` slicing on unexpected
                            # frames.
                            raw_line = (frame.raw_line or "")[:200]
                            logger.warning(
                                "deepseek_stream_malformed_chunk",
                                extra={
                                    "event": (
                                        "deepseek_stream_malformed_chunk"
                                    ),
                                    "call_id": call_id,
                                    "raw_line": raw_line,
                                },
                            )
                            continue

                        if frame.kind == "done":
                            break

                        if frame.kind == "usage":
                            if frame.usage is not None:
                                final_usage = frame.usage
                            if frame.finish_reason:
                                final_finish_reason = (
                                    frame.finish_reason
                                )
                            continue

                        if frame.kind == "empty":
                            if frame.finish_reason:
                                final_finish_reason = (
                                    frame.finish_reason
                                )
                            continue

                        # frame.kind == "delta"
                        if first_token_at is None:
                            first_token_at = time.time()
                            ttft_ms = int(
                                (first_token_at - start_time) * 1000
                            )
                            self._stream_ttft_samples.append(ttft_ms)
                            # Structured first-token log (Req 9.2).
                            logger.info(
                                "deepseek_stream_first_token",
                                extra={
                                    "event": (
                                        "deepseek_stream_first_token"
                                    ),
                                    "call_id": call_id,
                                    "time_to_first_token_ms": ttft_ms,
                                },
                            )

                        # Content-filter rejection (Req 6.5): yield
                        # terminal content-blocked chunk, record success
                        # in resilience trackers, and return.
                        if frame.finish_reason == "content_filter":
                            yield self._make_content_blocked_chunk(
                                chunk_index, call_id
                            )
                            await self._circuit_breaker.record_success()
                            await self._error_rate_tracker.record_call(
                                success=True
                            )
                            self._stream_success += 1
                            content_filter_triggered = True
                            return

                        if frame.usage is not None:
                            final_usage = frame.usage
                        if frame.finish_reason:
                            final_finish_reason = frame.finish_reason

                        delta_text = frame.delta_content or ""
                        cumulative_chars += len(delta_text)

                        yield AIResponse(
                            content=delta_text,
                            provider="deepseek",
                            model=self.model,
                            tokens_used=cumulative_chars // 4,
                            processing_time_ms=0,
                            confidence_score=1.0,
                            metadata={
                                "is_final": False,
                                "chunk_index": chunk_index,
                                "call_id": call_id,
                            },
                        )
                        chunk_index += 1

                    # content_filter branch already returned above.
                    if content_filter_triggered:
                        return

                    # Clean termination: emit terminal chunk and record
                    # success in resilience trackers.
                    duration_ms = int(
                        (time.time() - start_time) * 1000
                    )
                    await self._circuit_breaker.record_success()
                    await self._error_rate_tracker.record_call(
                        success=True
                    )
                    self._stream_success += 1
                    self._stream_duration_samples.append(duration_ms)
                    self._stream_chunks_samples.append(chunk_index)

                    # Structured stream-complete log (Req 9.3). Emitted
                    # only on the clean-[DONE] success path; error/
                    # timeout/cancellation paths have their own events.
                    # Token fields default to 0 when ``usage`` was not
                    # received (e.g. ``stream_include_usage=False``), to
                    # match the token-field convention used by
                    # ``_make_final_chunk`` on the terminal chunk.
                    usage_for_log = final_usage or {}
                    logger.info(
                        "deepseek_stream_complete",
                        extra={
                            "event": "deepseek_stream_complete",
                            "call_id": call_id,
                            "duration_ms": duration_ms,
                            "chunks_received": chunk_index,
                            "prompt_tokens": int(
                                usage_for_log.get("prompt_tokens", 0)
                            ),
                            "completion_tokens": int(
                                usage_for_log.get(
                                    "completion_tokens", 0
                                )
                            ),
                            "total_tokens": int(
                                usage_for_log.get("total_tokens", 0)
                            ),
                            "finish_reason": final_finish_reason,
                        },
                    )

                    yield self._make_final_chunk(
                        chunk_index=chunk_index,
                        finish_reason=final_finish_reason,
                        usage=final_usage,
                        duration_ms=duration_ms,
                        cumulative_chars=cumulative_chars,
                        call_id=call_id,
                    )
                    return

            except httpx.ReadTimeout as exc:
                # No first byte within the TTFT window, or read timed out
                # while waiting for the next chunk. Treat as timeout
                # (Req 1.8).
                duration_ms = int((time.time() - start_time) * 1000)
                # Structured stream-error log (Req 9.4).
                logger.error(
                    "deepseek_stream_error",
                    extra={
                        "event": "deepseek_stream_error",
                        "call_id": call_id,
                        "duration_ms": duration_ms,
                        "chunks_received_before_error": chunk_index,
                        "error_type": ErrorType.TIMEOUT.value,
                        "error_message": (
                            f"ReadTimeout after "
                            f"{self.stream_ttft_timeout}s: {exc}"
                        )[:500],
                    },
                )
                await self._circuit_breaker.record_failure()
                await self._error_rate_tracker.record_call(success=False)
                self._stream_failed += 1
                user_message = USER_FRIENDLY_ERROR_MESSAGES[
                    ErrorType.TIMEOUT
                ]
                yield AIResponse(
                    content=user_message,
                    provider="deepseek",
                    model=self.model,
                    tokens_used=cumulative_chars // 4,
                    processing_time_ms=duration_ms,
                    confidence_score=0.0,
                    metadata={
                        "is_final": True,
                        "chunk_index": chunk_index,
                        "finish_reason": "timeout",
                        "error_type": ErrorType.TIMEOUT.value,
                        "recoverable": True,
                        "user_message": user_message,
                        "call_id": call_id,
                        "duration_ms": duration_ms,
                    },
                )
                return

            except (
                httpx.ReadError,
                httpx.RemoteProtocolError,
                httpx.ConnectError,
                httpx.NetworkError,
            ) as exc:
                # Mid-stream network failure (Req 6.4). Partial deltas
                # already yielded remain delivered; emit one terminal
                # chunk preserving the chunk_index of the last successful
                # delta.
                duration_ms = int((time.time() - start_time) * 1000)
                # Structured stream-error log (Req 9.4).
                logger.error(
                    "deepseek_stream_error",
                    extra={
                        "event": "deepseek_stream_error",
                        "call_id": call_id,
                        "duration_ms": duration_ms,
                        "chunks_received_before_error": chunk_index,
                        "error_type": ErrorType.NETWORK_ERROR.value,
                        "error_message": str(exc)[:500],
                    },
                )
                await self._circuit_breaker.record_failure()
                await self._error_rate_tracker.record_call(success=False)
                self._stream_failed += 1
                user_message = USER_FRIENDLY_ERROR_MESSAGES[
                    ErrorType.NETWORK_ERROR
                ]
                yield AIResponse(
                    content=user_message,
                    provider="deepseek",
                    model=self.model,
                    tokens_used=cumulative_chars // 4,
                    processing_time_ms=duration_ms,
                    confidence_score=0.0,
                    metadata={
                        "is_final": True,
                        "chunk_index": chunk_index,
                        "finish_reason": "error",
                        "error_type": ErrorType.NETWORK_ERROR.value,
                        "recoverable": True,
                        "user_message": user_message,
                        "error": str(exc)[:500],
                        "call_id": call_id,
                        "duration_ms": duration_ms,
                    },
                )
                return

            except asyncio.TimeoutError as exc:
                # Generic async timeout wrapper (defensive; the
                # elapsed-time check above is the primary gate).
                duration_ms = int((time.time() - start_time) * 1000)
                # Structured stream-error log (Req 9.4).
                logger.error(
                    "deepseek_stream_error",
                    extra={
                        "event": "deepseek_stream_error",
                        "call_id": call_id,
                        "duration_ms": duration_ms,
                        "chunks_received_before_error": chunk_index,
                        "error_type": ErrorType.TIMEOUT.value,
                        "error_message": (
                            f"asyncio.TimeoutError: {exc}"
                        )[:500],
                    },
                )
                await self._circuit_breaker.record_failure()
                await self._error_rate_tracker.record_call(success=False)
                self._stream_failed += 1
                user_message = USER_FRIENDLY_ERROR_MESSAGES[
                    ErrorType.TIMEOUT
                ]
                yield AIResponse(
                    content=user_message,
                    provider="deepseek",
                    model=self.model,
                    tokens_used=cumulative_chars // 4,
                    processing_time_ms=duration_ms,
                    confidence_score=0.0,
                    metadata={
                        "is_final": True,
                        "chunk_index": chunk_index,
                        "finish_reason": "timeout",
                        "error_type": ErrorType.TIMEOUT.value,
                        "recoverable": True,
                        "user_message": user_message,
                        "call_id": call_id,
                        "duration_ms": duration_ms,
                    },
                )
                return

            except Exception as exc:
                # Last-resort catch-all. Classify via the exception-based
                # classifier and emit one terminal chunk.
                duration_ms = int((time.time() - start_time) * 1000)
                provider_error = ProviderError.from_exception(exc)
                # Structured stream-error log (Req 9.4). Preserve the
                # traceback via the adjacent ``logger.error`` below so the
                # structured event carries the classification and the
                # traceback log carries the stack.
                logger.error(
                    "deepseek_stream_error",
                    extra={
                        "event": "deepseek_stream_error",
                        "call_id": call_id,
                        "duration_ms": duration_ms,
                        "chunks_received_before_error": chunk_index,
                        "error_type": provider_error.error_type.value,
                        "error_message": str(exc)[:500],
                    },
                )
                logger.error(
                    "DeepSeek streaming unexpected error: "
                    "call_id=%s chunks=%d error=%s",
                    call_id,
                    chunk_index,
                    exc,
                    exc_info=True,
                )
                await self._circuit_breaker.record_failure()
                await self._error_rate_tracker.record_call(success=False)
                self._stream_failed += 1
                yield AIResponse(
                    content=provider_error.user_message,
                    provider="deepseek",
                    model=self.model,
                    tokens_used=cumulative_chars // 4,
                    processing_time_ms=duration_ms,
                    confidence_score=0.0,
                    metadata={
                        "is_final": True,
                        "chunk_index": chunk_index,
                        "finish_reason": "error",
                        "error_type": provider_error.error_type.value,
                        "recoverable": provider_error.recoverable,
                        "user_message": provider_error.user_message,
                        "error": str(exc)[:500],
                        "call_id": call_id,
                        "duration_ms": duration_ms,
                    },
                )
                return

        except GeneratorExit:
            # Client disconnect propagates up through the generator
            # protocol. Mark aborted so the ``finally`` block emits the
            # structured log, then re-raise to honour the protocol.
            aborted = True
            raise

        finally:
            if aborted:
                duration_ms = int((time.time() - start_time) * 1000)
                logger.info(
                    "deepseek_stream_aborted",
                    extra={
                        "event": "deepseek_stream_aborted",
                        "call_id": call_id,
                        "reason": "client_disconnect",
                        "chunks_sent": chunk_index,
                        "duration_ms": duration_ms,
                    },
                )

    def get_provider_status(self) -> Dict[str, Dict[str, Any]]:
        """Return a status snapshot for the DeepSeek provider.

        Includes the pre-existing non-streaming counters (``total_calls``,
        ``successful_calls``, ``failed_calls``) plus streaming-specific
        metrics introduced for the SSE streaming client (Req 9.5, 9.6):

        - ``streaming_total_calls`` / ``streaming_successful_calls`` /
          ``streaming_failed_calls``: cumulative counters of streaming
          invocations since process start.
        - ``streaming_avg_duration_ms``: mean wall-clock duration in
          milliseconds of the last (≤100) successful streams.
        - ``streaming_avg_time_to_first_token_ms``: mean time from request
          start to the first non-empty delta across the last (≤100)
          streams.
        - ``streaming_avg_chunks_per_response``: mean number of non-empty
          delta chunks per successful stream across the last (≤100)
          streams.
        - ``circuit_breaker_state``: current :class:`CircuitState` as a
          string (``"closed"`` / ``"half_open"`` / ``"open"``).
        - ``streaming_enabled``: effective feature flag — true only when
          both the config flag and the error-rate tracker's soft-disable
          gate allow streaming.

        Empty sample deques yield ``0.0`` averages so callers never see a
        ``ZeroDivisionError``.
        """

        def _avg(samples: "Deque[Any]") -> float:
            if not samples:
                return 0.0
            return float(sum(samples)) / float(len(samples))

        return {
            "deepseek": {
                "available": True,
                "model": self.model,
                "total_calls": self._total_calls,
                "successful_calls": self._successful_calls,
                "failed_calls": self._failed_calls,
                "streaming_total_calls": self._stream_total,
                "streaming_successful_calls": self._stream_success,
                "streaming_failed_calls": self._stream_failed,
                "streaming_avg_duration_ms": _avg(
                    self._stream_duration_samples
                ),
                "streaming_avg_time_to_first_token_ms": _avg(
                    self._stream_ttft_samples
                ),
                "streaming_avg_chunks_per_response": _avg(
                    self._stream_chunks_samples
                ),
                "circuit_breaker_state": self._circuit_breaker.state.value,
                "streaming_enabled": bool(
                    self.streaming_enabled_config
                    and self._error_rate_tracker.streaming_enabled
                ),
            }
        }

    def get_performance_stats(self) -> Dict[str, Any]:
        """Return a performance-stats snapshot for the DeepSeek provider.

        Mirrors :meth:`AIService.get_performance_stats` (the Gemini
        implementation at ``services/ai_service.py``) so that the
        `/api/performance`-style endpoint surfaces a consistent shape
        regardless of which provider is active (Req 9.6).

        The returned dict is keyed by provider name (``"deepseek"``) and
        its value includes the non-streaming counters kept on the
        instance (``total_calls`` / ``successful_calls`` /
        ``failed_calls``), the streaming counters and sample-derived
        averages populated by the SSE streaming client, and the shared
        resilience trackers' ``get_stats()`` payloads under the
        ``circuit_breaker`` and ``error_rate`` keys.

        Empty sample deques yield ``0.0`` averages so callers never see
        a ``ZeroDivisionError``.
        """

        def _avg(samples: "Deque[Any]") -> float:
            if not samples:
                return 0.0
            return float(sum(samples)) / float(len(samples))

        total = self._total_calls
        success_rate = (
            round(self._successful_calls / total * 100, 2)
            if total > 0
            else 0.0
        )

        return {
            "deepseek": {
                "provider": "deepseek",
                "model": self.model,
                "total_calls": total,
                "successful_calls": self._successful_calls,
                "failed_calls": self._failed_calls,
                "success_rate": success_rate,
                "streaming_total_calls": self._stream_total,
                "streaming_successful_calls": self._stream_success,
                "streaming_failed_calls": self._stream_failed,
                "streaming_avg_duration_ms": round(
                    _avg(self._stream_duration_samples), 2
                ),
                "streaming_avg_time_to_first_token_ms": round(
                    _avg(self._stream_ttft_samples), 2
                ),
                "streaming_avg_chunks_per_response": round(
                    _avg(self._stream_chunks_samples), 2
                ),
                "circuit_breaker": self._circuit_breaker.get_stats(),
                "error_rate": self._error_rate_tracker.get_stats(),
            }
        }
