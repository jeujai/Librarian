"""
Ollama-backed AI Service for training data and eval set generation.

Drop-in replacement for ``AIService`` that routes ``generate_response()``
calls to a local Ollama instance instead of Gemini.  Used exclusively by
the ML training pipeline so that RAG gold-answer generation and eval-set
generation run against a local model (e.g. ``llama3.1:8b``) with zero
API cost.

The rest of the application continues to use ``AIService`` (Gemini) for
user-facing chat and ``OllamaClient`` (llama3.2:3b) for bridge
generation and KG extraction.
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

_DEFAULT_HOST = "http://host.docker.internal:11434"
_DEFAULT_MODEL = "llama3.1:8b"
_DEFAULT_TIMEOUT = 180.0  # 3 minutes — gold answers can be long


# ---------------------------------------------------------------------------
# OllamaAIService
# ---------------------------------------------------------------------------


class OllamaAIService:
    """AI service backed by a local Ollama model.

    Implements the same ``generate_response`` interface that
    ``RAGService`` expects from ``AIService``, so it can be used as
    a drop-in replacement when constructing the RAG service for
    training data generation.

    Args:
        model: Ollama model name (default ``llama3.1:8b``).
        host: Ollama API URL.  Defaults to
            ``OLLAMA_HOST`` env var or ``http://host.docker.internal:11434``.
        timeout: Request timeout in seconds.
    """

    def __init__(
        self,
        model: Optional[str] = None,
        host: Optional[str] = None,
        timeout: Optional[float] = None,
    ) -> None:
        self.model: str = model or os.environ.get(
            "OLLAMA_TRAINING_MODEL", _DEFAULT_MODEL
        ) or _DEFAULT_MODEL
        self.host: str = host or os.environ.get(
            "OLLAMA_HOST", _DEFAULT_HOST
        ) or _DEFAULT_HOST
        self.timeout: float = timeout or float(
            os.environ.get("OLLAMA_TRAINING_TIMEOUT", str(_DEFAULT_TIMEOUT))
        )
        self._client: Optional[httpx.AsyncClient] = None

        # Minimal stats
        self._total_calls = 0
        self._successful_calls = 0
        self._failed_calls = 0

        logger.info(
            "OllamaAIService initialised: model=%s, host=%s, timeout=%.0fs",
            self.model,
            self.host,
            self.timeout,
        )

    # ------------------------------------------------------------------
    # HTTP client lifecycle
    # ------------------------------------------------------------------

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(
                base_url=self.host,
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
        """Confirm Ollama is reachable and the training model is loaded.

        Sends a single-token test prompt to ``/api/chat`` and checks
        for a successful response.  This MUST be called before any
        expensive pipeline work begins.

        Raises:
            RuntimeError: If Ollama is unreachable, the model is not
                found, or the test prompt fails.  The error message
                includes the model name and host so the operator can
                diagnose immediately.
        """
        logger.info(
            "OllamaAIService: Pre-flight check — verifying model "
            "'%s' is available at %s",
            self.model,
            self.host,
        )

        # Step 1: Check Ollama is running and list models
        try:
            client = await self._get_client()
            tags_resp = await client.get("/api/tags", timeout=10.0)
        except Exception as exc:
            raise RuntimeError(
                f"PREFLIGHT FAILED: Cannot reach Ollama at {self.host}. "
                f"Is Ollama running? Error: {exc}"
            ) from exc

        if tags_resp.status_code != 200:
            raise RuntimeError(
                f"PREFLIGHT FAILED: Ollama returned HTTP "
                f"{tags_resp.status_code} from {self.host}/api/tags."
            )

        # Step 2: Verify the model exists
        tags_data = tags_resp.json()
        available_models = [
            m.get("name", "") for m in tags_data.get("models", [])
        ]
        model_found = any(
            self.model in m or m.startswith(self.model.split(":")[0])
            for m in available_models
        )
        if not model_found:
            raise RuntimeError(
                f"PREFLIGHT FAILED: Model '{self.model}' not found in "
                f"Ollama. Available models: {available_models}. "
                f"Run: ollama pull {self.model}"
            )

        # Step 3: Send a trivial test prompt to confirm inference works
        try:
            test_resp = await client.post(
                "/api/chat",
                json={
                    "model": self.model,
                    "messages": [
                        {"role": "user", "content": "Say OK."}
                    ],
                    "stream": False,
                    "options": {"num_predict": 5},
                },
                timeout=30.0,
            )
        except Exception as exc:
            raise RuntimeError(
                f"PREFLIGHT FAILED: Test prompt to '{self.model}' "
                f"failed: {exc}"
            ) from exc

        if test_resp.status_code != 200:
            raise RuntimeError(
                f"PREFLIGHT FAILED: Test prompt returned HTTP "
                f"{test_resp.status_code}: {test_resp.text[:200]}"
            )

        test_content = (
            test_resp.json().get("message", {}).get("content", "")
        )
        logger.info(
            "OllamaAIService: Pre-flight PASSED — model '%s' "
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
        """Generate a response via Ollama's ``/api/chat`` endpoint.

        The signature matches ``AIService.generate_response`` so that
        ``RAGService`` can use this as a transparent replacement.

        Args:
            messages: List of ``{"role": ..., "content": ...}`` dicts.
            context: Optional additional context (appended to the last
                user message if provided).
            temperature: Sampling temperature.
            max_tokens: Maximum tokens to generate.
            preferred_provider: Ignored (present for interface compat).

        Returns:
            An ``AIResponse`` with the generated text.
        """
        self._total_calls += 1
        start = time.time()

        # If context is provided separately, fold it into the messages
        # the same way GeminiProvider does.
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
                "stream": False,
                "options": {
                    "temperature": temperature,
                    "num_predict": max_tokens,
                },
            }

            response = await client.post("/api/chat", json=payload)

            elapsed_ms = int((time.time() - start) * 1000)

            if response.status_code != 200:
                self._failed_calls += 1
                error_msg = (
                    f"Ollama API error: {response.status_code} — "
                    f"{response.text[:200]}"
                )
                logger.error(error_msg)
                return AIResponse(
                    content=error_msg,
                    provider="ollama",
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
            message = data.get("message", {})
            content = message.get("content", "")

            eval_count = data.get("eval_count", 0)
            prompt_eval_count = data.get("prompt_eval_count", 0)

            self._successful_calls += 1

            logger.debug(
                "OllamaAIService: %d prompt + %d eval tokens in %dms "
                "(model=%s)",
                prompt_eval_count,
                eval_count,
                elapsed_ms,
                self.model,
            )

            return AIResponse(
                content=content,
                provider="ollama",
                model=self.model,
                tokens_used=prompt_eval_count + eval_count,
                processing_time_ms=elapsed_ms,
                confidence_score=1.0,
                metadata={
                    "finish_reason": "completed",
                    "eval_count": eval_count,
                    "prompt_eval_count": prompt_eval_count,
                },
            )

        except httpx.TimeoutException:
            elapsed_ms = int((time.time() - start) * 1000)
            self._failed_calls += 1
            error_msg = (
                f"Ollama request timed out after {self.timeout:.0f}s "
                f"(model={self.model})"
            )
            logger.error(error_msg)
            return AIResponse(
                content=error_msg,
                provider="ollama",
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
            error_msg = f"Ollama generation failed: {exc}"
            logger.error(error_msg)
            return AIResponse(
                content=error_msg,
                provider="ollama",
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
        return ["ollama"]

    def get_provider_status(self) -> Dict[str, Dict[str, Any]]:
        return {
            "ollama": {
                "available": True,
                "model": self.model,
                "total_calls": self._total_calls,
                "successful_calls": self._successful_calls,
                "failed_calls": self._failed_calls,
            }
        }
