"""
vLLM-backed AI Service for training data and eval set generation.

Drop-in replacement for ``AIService`` that routes ``generate_response()``
calls to the host-native vLLM server (Apple Metal, OpenAI-compatible) instead
of a cloud LLM.  Used by the ML training pipeline so RAG
gold-answer and eval-set generation run against the local vLLM model with
zero API cost.
"""

from __future__ import annotations

import logging
import os
import time
from typing import Any, Dict, List, Optional

import httpx

from .ai_service import AIResponse

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_DEFAULT_URL = "http://host.docker.internal:8002"
_DEFAULT_MODEL = "mlx-community/Llama-3.2-3B-Instruct-4bit"
_DEFAULT_TIMEOUT = 180.0  # 3 minutes — gold answers can be long


# ---------------------------------------------------------------------------
# VLLMAIService
# ---------------------------------------------------------------------------


class VLLMAIService:
    """AI service backed by the host-native vLLM server.

    Implements the same ``generate_response`` interface that ``RAGService``
    expects from ``AIService``, so it can be used as a drop-in replacement
    when constructing the RAG service for training data generation.

    Args:
        model: vLLM model name (default ``VLLM_MODEL`` env var or
            ``mlx-community/Llama-3.2-3B-Instruct-4bit``).
        url: vLLM API base URL.  Defaults to ``VLLM_URL`` env var or
            ``http://host.docker.internal:8002``.
        timeout: Request timeout in seconds.
    """

    def __init__(
        self,
        model: Optional[str] = None,
        url: Optional[str] = None,
        timeout: Optional[float] = None,
    ) -> None:
        self.model: str = model or os.environ.get("VLLM_MODEL", _DEFAULT_MODEL) or _DEFAULT_MODEL
        self.url: str = url or os.environ.get("VLLM_URL", _DEFAULT_URL) or _DEFAULT_URL
        self.timeout: float = timeout or float(
            os.environ.get("VLLM_TIMEOUT", str(_DEFAULT_TIMEOUT))
        )
        self._client: Optional[httpx.AsyncClient] = None

        # Minimal stats
        self._total_calls = 0
        self._successful_calls = 0
        self._failed_calls = 0

        logger.info(
            "VLLMAIService initialised: model=%s, url=%s, timeout=%.0fs",
            self.model,
            self.url,
            self.timeout,
        )

    # ------------------------------------------------------------------
    # HTTP client lifecycle
    # ------------------------------------------------------------------

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(
                base_url=self.url,
                timeout=httpx.Timeout(self.timeout),
                limits=httpx.Limits(
                    max_keepalive_connections=5,
                    max_connections=10,
                ),
            )
        return self._client

    async def close(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    # ------------------------------------------------------------------
    # Pre-flight verification
    # ------------------------------------------------------------------

    async def verify_available(self) -> None:
        """Confirm vLLM is reachable and the model responds.

        Sends a single-token test prompt to ``/v1/chat/completions`` and
        checks for a successful response.  This MUST be called before any
        expensive pipeline work begins.

        Raises:
            RuntimeError: If vLLM is unreachable or the test prompt fails.
        """
        logger.info(
            "VLLMAIService: Pre-flight check — verifying model "
            "'%s' is available at %s",
            self.model,
            self.url,
        )

        # Send a trivial test prompt to confirm inference works
        try:
            client = await self._get_client()
            test_resp = await client.post(
                "/v1/chat/completions",
                json={
                    "model": self.model,
                    "messages": [{"role": "user", "content": "Say OK."}],
                    "max_tokens": 5,
                    "temperature": 0.0,
                },
                timeout=30.0,
            )
        except Exception as exc:
            raise RuntimeError(
                f"PREFLIGHT FAILED: Cannot reach vLLM at {self.url}. "
                f"Is vLLM running (--host 0.0.0.0)? Error: {exc}"
            ) from exc

        if test_resp.status_code != 200:
            raise RuntimeError(
                f"PREFLIGHT FAILED: vLLM returned HTTP "
                f"{test_resp.status_code}: {test_resp.text[:200]}"
            )

        test_content = (
            test_resp.json().get("choices", [{}])[0]
            .get("message", {}).get("content", "")
            or ""
        )
        logger.info(
            "VLLMAIService: Pre-flight PASSED — model '%s' "
            "responded: %s",
            self.model,
            test_content[:50],
        )

    # ------------------------------------------------------------------
    # Public API — matches AIService.generate_response signature
    # ------------------------------------------------------------------

    async def generate_response(
        self,
        messages: List[Dict[str, str]],
        context: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: int = 2048,
        preferred_provider: Optional[Any] = None,
    ) -> AIResponse:
        """Generate a response via vLLM's ``/v1/chat/completions`` endpoint.

        The signature matches ``AIService.generate_response`` so that
        ``RAGService`` can use this as a transparent replacement.
        """
        self._total_calls += 1
        start = time.time()

        # If context is provided separately, fold it into the messages
        # the same way DeepSeekAIService does.
        if context:
            messages = list(messages)  # shallow copy
            if messages and messages[-1].get("role") == "user":
                messages[-1] = {
                    "role": "user",
                    "content": messages[-1]["content"]
                    + "\n\nAdditional context:\n"
                    + context,
                }

        try:
            client = await self._get_client()

            payload = {
                "model": self.model,
                "messages": messages,
                "max_tokens": max_tokens,
                "temperature": temperature,
            }

            response = await client.post("/v1/chat/completions", json=payload)

            elapsed_ms = int((time.time() - start) * 1000)

            if response.status_code != 200:
                self._failed_calls += 1
                error_msg = (
                    f"vLLM API error: {response.status_code} — "
                    f"{response.text[:200]}"
                )
                logger.error(error_msg)
                return AIResponse(
                    content=error_msg,
                    provider="vllm",
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
            content = (
                data.get("choices", [{}])[0]
                .get("message", {}).get("content", "")
                or ""
            )

            usage = data.get("usage", {}) or {}
            prompt_tokens = int(usage.get("prompt_tokens", 0) or 0)
            completion_tokens = int(usage.get("completion_tokens", 0) or 0)

            self._successful_calls += 1

            logger.debug(
                "VLLMAIService: %d prompt + %d completion tokens in %dms "
                "(model=%s)",
                prompt_tokens,
                completion_tokens,
                elapsed_ms,
                self.model,
            )

            return AIResponse(
                content=content,
                provider="vllm",
                model=self.model,
                tokens_used=prompt_tokens + completion_tokens,
                processing_time_ms=elapsed_ms,
                confidence_score=1.0,
                metadata={
                    "finish_reason": "completed",
                    "completion_tokens": completion_tokens,
                    "prompt_tokens": prompt_tokens,
                },
            )

        except httpx.TimeoutException:
            elapsed_ms = int((time.time() - start) * 1000)
            self._failed_calls += 1
            error_msg = (
                f"vLLM request timed out after {self.timeout:.0f}s "
                f"(model={self.model})"
            )
            logger.error(error_msg)
            return AIResponse(
                content=error_msg,
                provider="vllm",
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
            error_msg = f"vLLM generation failed: {exc}"
            logger.error(error_msg)
            return AIResponse(
                content=error_msg,
                provider="vllm",
                model=self.model,
                tokens_used=0,
                processing_time_ms=elapsed_ms,
                confidence_score=0.0,
                metadata={
                    "finish_reason": "error",
                    "error": error_msg,
                },
            )

    # ------------------------------------------------------------------
    # Convenience — used by RAGService for provider status checks
    # ------------------------------------------------------------------

    def get_available_providers(self) -> List[str]:
        return ["vllm"]

    def get_provider_status(self) -> Dict[str, Dict[str, Any]]:
        return {
            "vllm": {
                "available": True,
                "model": self.model,
                "total_calls": self._total_calls,
                "successful_calls": self._successful_calls,
                "failed_calls": self._failed_calls,
            }
        }
