"""
LLM Question Rewriter — transforms template-style medical questions
into natural conversational phrasing.

The existing seed question pipeline generates questions from UMLS
concept templates (e.g., "What is the mechanism of action of
{concept_name}?").  These textbook-style questions produce training
data that causes the fine-tuned model to output MCQ-format answers.

This module uses an LLM (DeepSeek) to rewrite template questions into
the kind of natural language a patient or healthcare worker would type
in a chat interface, while preserving the medical concept and intent.

On rewrite failure (LLM error, empty/short result, identical to input),
the original question text is kept unchanged.  If more than 50% of
rewrites fail, an error-level message is logged.

Requirements: 1.1, 1.2, 1.4, 1.5
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, List

from .models import SeedQuestion

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Minimum length (in characters) for a rewritten question to be accepted.
# Shorter results are treated as failures and the original is kept.
_MIN_REWRITE_LENGTH: int = 10

# System prompt sent to the LLM for question rewriting.
_REWRITE_SYSTEM_PROMPT: str = (
    "You are a medical question rephraser. Your job is to rewrite "
    "a template-style medical question into a natural, conversational "
    "question that a patient or healthcare worker might type in a chat "
    "app.\n\n"
    "Rules:\n"
    "- Rephrase as if a real person is asking in a chat interface\n"
    "- Vary sentence structure: use questions, statements seeking info, "
    '"Can you tell me about...", "I\'d like to know...", etc.\n'
    "- Do NOT start with textbook stems like:\n"
    '  "What is the mechanism of action of"\n'
    '  "What is the pathophysiology of"\n'
    '  "Describe the"\n'
    '  "What are the indications and contraindications for"\n'
    "- Keep the medical concept but use natural, everyday language\n"
    "- Return ONLY the rewritten question, no preamble or explanation\n"
    "- The rewritten question must be a single sentence or short phrase"
)

# User prompt template for individual rewrites.
_REWRITE_USER_PROMPT: str = (
    "Rewrite this medical question into a natural conversational style. "
    "The question is about a {semantic_type} concept.\n\n"
    "Original question: {question}\n\n"
    "Rewritten question:"
)


# ---------------------------------------------------------------------------
# LLMQuestionRewriter
# ---------------------------------------------------------------------------


class LLMQuestionRewriter:
    """Rewrites template-style medical questions into conversational phrasing.

    Uses an LLM client to transform each seed question into a natural
    user query.  Successfully rewritten questions have their ``source``
    field set to ``"llm_rewritten"``.  Questions that fail rewriting
    are kept with their original text and source.

    Parameters
    ----------
    llm_client:
        An LLM client with an async ``generate`` or ``chat`` method
        (the same DeepSeek client used by the RAG pipeline).
    max_concurrent:
        Semaphore limit for concurrent LLM rewrite calls.  Defaults
        to 4 to avoid overwhelming the LLM API alongside RAG calls.
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

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def rewrite_questions(
        self,
        seed_questions: List[SeedQuestion],
        progress_callback: Any = None,
    ) -> List[SeedQuestion]:
        """Rewrite a batch of seed questions into conversational phrasing.

        For each seed question, sends the template question to the LLM
        with a system prompt instructing it to rephrase as a natural
        user query.  Returns new ``SeedQuestion`` objects with the
        rewritten question text and ``source="llm_rewritten"``.

        Questions that fail rewriting are kept with their original text
        and source unchanged.

        If more than 50% of rewrites fail, an error-level message is
        logged suggesting the LLM service may be degraded.

        Args:
            seed_questions: The list of seed questions to rewrite.
            progress_callback: Optional callable invoked after each
                rewrite completes with ``(completed, total)``.

        Returns:
            A new list of ``SeedQuestion`` objects (same length as
            input) with rewritten or original question text.
        """
        if not seed_questions:
            return []

        logger.info(
            "LLMQuestionRewriter: rewriting %d seed questions",
            len(seed_questions),
        )

        # Reset counters for this batch.
        self._success_count = 0
        self._failure_count = 0
        self._completed_count = 0

        total = len(seed_questions)

        async def _rewrite_and_report(seed: SeedQuestion) -> SeedQuestion:
            result = await self._rewrite_with_fallback(seed)
            self._completed_count += 1
            if progress_callback is not None:
                try:
                    progress_callback(self._completed_count, total)
                except Exception:
                    pass
            return result

        tasks = [_rewrite_and_report(seed) for seed in seed_questions]
        results: List[SeedQuestion] = await asyncio.gather(*tasks)

        logger.info(
            "LLMQuestionRewriter: completed — %d/%d succeeded, "
            "%d/%d failed",
            self._success_count,
            total,
            self._failure_count,
            total,
        )

        if total > 0 and self._failure_count > total / 2:
            logger.error(
                "LLMQuestionRewriter: >50%% of rewrites failed "
                "(%d/%d). The LLM service may be degraded.",
                self._failure_count,
                total,
            )

        return results

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _rewrite_with_fallback(
        self,
        seed: SeedQuestion,
    ) -> SeedQuestion:
        """Attempt to rewrite a single seed question, falling back to
        the original on failure.

        Returns a new ``SeedQuestion`` with ``source="llm_rewritten"``
        on success, or the original seed unchanged on failure.
        """
        semantic_type = seed.semantic_type or "general medical"

        try:
            rewritten = await self._rewrite_single(
                seed.question, semantic_type
            )
        except Exception:
            logger.warning(
                "LLMQuestionRewriter: rewrite failed for question: "
                "%.80s...",
                seed.question,
                exc_info=True,
            )
            self._failure_count += 1
            return seed

        # Validate the rewrite result.
        if not rewritten or len(rewritten.strip()) < _MIN_REWRITE_LENGTH:
            logger.debug(
                "LLMQuestionRewriter: rewrite too short or empty for: "
                "%.80s...",
                seed.question,
            )
            self._failure_count += 1
            return seed

        rewritten = rewritten.strip()

        if rewritten == seed.question:
            logger.debug(
                "LLMQuestionRewriter: rewrite identical to original: "
                "%.80s...",
                seed.question,
            )
            self._failure_count += 1
            return seed

        self._success_count += 1
        return SeedQuestion(
            question=rewritten,
            source="llm_rewritten",
            semantic_type=seed.semantic_type,
            concept_name=seed.concept_name,
        )

    async def _rewrite_single(
        self,
        question: str,
        semantic_type: str,
    ) -> str:
        """Rewrite a single question via a semaphore-guarded LLM call.

        Args:
            question: The original template-style question.
            semantic_type: The UMLS semantic type for context.

        Returns:
            The rewritten question text from the LLM.

        Raises:
            Exception: If the LLM call fails.
        """
        user_prompt = _REWRITE_USER_PROMPT.format(
            semantic_type=semantic_type,
            question=question,
        )

        async with self._semaphore:
            if hasattr(self._llm_client, "generate"):
                result = await self._llm_client.generate(
                    user_prompt,
                    system_prompt=_REWRITE_SYSTEM_PROMPT,
                )
            elif hasattr(self._llm_client, "chat"):
                result = await self._llm_client.chat(
                    user_prompt,
                    system_prompt=_REWRITE_SYSTEM_PROMPT,
                )
            else:
                raise TypeError(
                    "LLM client has no 'generate' or 'chat' method"
                )

        return result if isinstance(result, str) else str(result)

    # ------------------------------------------------------------------
    # Statistics
    # ------------------------------------------------------------------

    @property
    def success_count(self) -> int:
        """Number of questions successfully rewritten in the last batch."""
        return self._success_count

    @property
    def failure_count(self) -> int:
        """Number of questions that failed rewriting in the last batch."""
        return self._failure_count
