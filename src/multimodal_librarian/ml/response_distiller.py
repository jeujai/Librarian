"""
Response Distiller — rewrites RAG-grounded responses into standalone
authoritative medical prose for knowledge distillation training.

The RAG pipeline produces responses written in a "summarizing documents"
voice (e.g., "Based on the provided sources, metformin activates AMPK
[Source 1]"). For knowledge distillation, we need responses written in
a direct "I know this" voice (e.g., "Metformin works primarily by
activating AMPK, which reduces hepatic glucose production.").

This module uses DeepSeek to rewrite each RAG response into standalone
medical prose suitable for training a model that carries knowledge in
its own weights rather than depending on retrieved context.
"""

from __future__ import annotations

import asyncio
import logging
import re
from typing import Any, Callable, List, Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_DISTILL_SYSTEM_PROMPT = (
    "You are a medical writing editor. Your job is to rewrite a "
    "RAG-generated medical response into clean, authoritative medical "
    "prose — as if written by a knowledgeable medical professional who "
    "simply knows the information.\n\n"
    "Rules:\n"
    "- Remove ALL references to 'sources', 'documents', 'provided "
    "information', 'the text', 'the literature'\n"
    "- Remove ALL citation markers like [Source 1], [Source 2], etc.\n"
    "- Remove any 'References:' sections\n"
    "- Write in a direct, confident voice — not 'the sources say' but "
    "state the facts directly\n"
    "- Keep ALL factual medical content intact — do not add or remove "
    "medical information\n"
    "- Use clean markdown formatting (bold for key terms, bullet lists "
    "where appropriate)\n"
    "- Do NOT add disclaimers like 'consult your doctor' or "
    "'this is for educational purposes'\n"
    "- Do NOT use 'Step 1/Step 2' formatting\n"
    "- Do NOT produce multiple-choice options (A/B/C/D)\n"
    "- CRITICAL: Do NOT start the response with a question or a header "
    "that restates the question (e.g., '### How common is X?' or 'What "
    "are its benefits?'). Start directly with the answer content.\n"
    "- If the original response says information is not available, "
    "rewrite as a brief, direct statement that the topic is outside "
    "your knowledge base\n"
    "- Return ONLY the rewritten response, no preamble"
)

_DISTILL_USER_PROMPT = (
    "Rewrite this RAG-generated medical response into standalone "
    "authoritative prose. Keep all medical facts but remove any "
    "reference to sources or documents.\n\n"
    "Original question: {question}\n\n"
    "RAG response to rewrite:\n{response}\n\n"
    "Rewritten response:"
)

# Minimum length for a rewritten response to be accepted.
_MIN_REWRITE_LENGTH = 50


# ---------------------------------------------------------------------------
# ResponseDistiller
# ---------------------------------------------------------------------------


class ResponseDistiller:
    """Rewrites RAG responses into standalone medical prose.

    Uses an LLM client to transform each RAG-grounded response into
    direct, authoritative medical text suitable for knowledge
    distillation training.

    Parameters
    ----------
    llm_client:
        An LLM client with an async ``generate(prompt, system_prompt=...)``
        method.
    max_concurrent:
        Semaphore limit for concurrent LLM calls.
    """

    def __init__(
        self,
        llm_client: Any,
        max_concurrent: int = 4,
    ) -> None:
        self._llm_client = llm_client
        self._semaphore = asyncio.Semaphore(max_concurrent)
        self._success_count: int = 0
        self._failure_count: int = 0
        self._completed_count: int = 0

    async def distill_response(
        self,
        question: str,
        rag_response: str,
    ) -> Optional[str]:
        """Rewrite a single RAG response into standalone prose.

        Returns the rewritten response, or None if rewriting fails.
        On failure, the caller should fall back to regex cleaning.
        """
        user_prompt = _DISTILL_USER_PROMPT.format(
            question=question,
            response=rag_response,
        )

        async with self._semaphore:
            try:
                result = await self._llm_client.generate(
                    user_prompt,
                    system_prompt=_DISTILL_SYSTEM_PROMPT,
                )
            except Exception:
                logger.debug(
                    "ResponseDistiller: LLM call failed for question: %.60s",
                    question,
                    exc_info=True,
                )
                self._failure_count += 1
                return None

        if not result or len(result.strip()) < _MIN_REWRITE_LENGTH:
            self._failure_count += 1
            return None

        rewritten = result.strip()

        # Sanity check: rewritten should not contain source markers
        if re.search(r"\[Source\s*\d+\]", rewritten):
            # LLM didn't follow instructions — fall back
            self._failure_count += 1
            return None

        self._success_count += 1
        return rewritten

    async def distill_batch(
        self,
        pairs: List[dict],
        progress_callback: Optional[Callable[[int, int], None]] = None,
    ) -> List[dict]:
        """Rewrite a batch of (question, response) pairs.

        Args:
            pairs: List of dicts with 'question' and 'response' keys.
            progress_callback: Optional (completed, total) callback.

        Returns:
            List of dicts with 'question' and 'response' keys, where
            response is the rewritten version (or original on failure).
        """
        self._success_count = 0
        self._failure_count = 0
        self._completed_count = 0
        total = len(pairs)

        async def _process_one(pair: dict) -> dict:
            rewritten = await self.distill_response(
                pair["question"], pair["response"]
            )
            self._completed_count += 1
            if progress_callback:
                try:
                    progress_callback(self._completed_count, total)
                except Exception:
                    pass
            if rewritten:
                return {"question": pair["question"], "response": rewritten}
            # Fall back to original on failure
            return pair

        tasks = [_process_one(p) for p in pairs]
        results = await asyncio.gather(*tasks)

        logger.info(
            "ResponseDistiller: %d/%d succeeded, %d/%d failed",
            self._success_count, total,
            self._failure_count, total,
        )

        return results

    @property
    def success_count(self) -> int:
        return self._success_count

    @property
    def failure_count(self) -> int:
        return self._failure_count
