"""
Token Budget Manager — estimates token counts and handles over-budget responses.

Ensures every training example fits within the model's token budget
(system prompt + user message + assistant response) without mid-sentence
truncation.  Uses a simple chars / 4.0 heuristic to avoid adding a
tokenizer dependency at generation time.

When a pair exceeds the budget, the manager can optionally use an LLM
client to summarize the response while preserving all ``[Source N]``
citations.

Requirements: 3.1, 3.2, 3.4, 3.5
"""

from __future__ import annotations

import logging
import math
import re
from typing import Any, List, Optional

from .models import InstructionTuningPair

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_CHARS_PER_TOKEN: float = 4.0

# Overhead for Llama 3 chat template special tokens and role markers.
# Accounts for <|begin_of_text|>, <|start_header_id|>, <|end_header_id|>,
# <|eot_id|> across system/user/assistant turns.
_CHAT_TEMPLATE_OVERHEAD_TOKENS: int = 20

# Pattern to find [Source N] citation markers in response text.
_CITATION_PATTERN: re.Pattern[str] = re.compile(r"\[Source\s+\d+\]")

# Prompt sent to the LLM when summarizing an over-budget response.
_SUMMARIZE_PROMPT = (
    "Summarize the following medical response to fit within {target_tokens} "
    "tokens while preserving ALL source citations (e.g., [Source 1], "
    "[Source 2]) and the core factual content. The summary must end with "
    "a complete sentence — do not truncate mid-sentence.\n\n"
    "Response to summarize:\n{response}"
)


# ---------------------------------------------------------------------------
# TokenBudgetManager
# ---------------------------------------------------------------------------


class TokenBudgetManager:
    """Manages token budget estimation and response summarization.

    Parameters
    ----------
    max_tokens:
        Maximum total tokens for a complete training example
        (system prompt + user message + assistant response + chat
        template overhead).  Defaults to 5000.
    chars_per_token:
        Character-to-token ratio for the estimation heuristic.
        Defaults to 4.0 (conservative for English medical text).
    llm_client:
        Optional LLM client with an async ``generate`` or ``chat``
        method.  Used to summarize over-budget responses.  When
        ``None``, over-budget pairs are rejected instead of
        summarized.
    """

    def __init__(
        self,
        max_tokens: int = 5000,
        chars_per_token: float = 4.0,
        llm_client: Optional[Any] = None,
    ) -> None:
        self.max_tokens = max_tokens
        self.chars_per_token = chars_per_token
        self.llm_client = llm_client
        self._summarized_count: int = 0
        self._rejected_count: int = 0

    # ------------------------------------------------------------------
    # Estimation helpers
    # ------------------------------------------------------------------

    def estimate_tokens(self, text: str) -> int:
        """Estimate token count using the chars / chars_per_token heuristic.

        Returns a non-negative integer.  Empty strings yield 0.
        """
        if not text:
            return 0
        return math.ceil(len(text) / self.chars_per_token)

    def estimate_pair_tokens(
        self,
        pair: InstructionTuningPair,
        system_prompt: str,
    ) -> int:
        """Estimate total tokens for a formatted training example.

        Accounts for:
        - System prompt tokens
        - User message tokens (instruction + optional context)
        - Assistant response tokens
        - Chat template overhead (~20 tokens for special tokens and
          role markers)

        The user message is constructed the same way as
        ``format_chat_message`` in ``qlora_trainer.py``: instruction
        followed by ``\\n\\nContext:\\n{context}`` when context is
        present.
        """
        # Build user content matching qlora_trainer.format_chat_message
        user_content = pair.instruction
        if pair.context and pair.context.strip():
            user_content = f"{pair.instruction}\n\nContext:\n{pair.context}"

        system_tokens = self.estimate_tokens(system_prompt)
        user_tokens = self.estimate_tokens(user_content)
        response_tokens = self.estimate_tokens(pair.response)

        return (
            system_tokens
            + user_tokens
            + response_tokens
            + _CHAT_TEMPLATE_OVERHEAD_TOKENS
        )

    def fits_budget(
        self,
        pair: InstructionTuningPair,
        system_prompt: str,
    ) -> bool:
        """Return True if the pair fits within the token budget."""
        return self.estimate_pair_tokens(pair, system_prompt) <= self.max_tokens

    # ------------------------------------------------------------------
    # Response summarization
    # ------------------------------------------------------------------

    async def summarize_response(
        self,
        response: str,
        target_tokens: int,
        citations: Optional[List[str]] = None,
    ) -> Optional[str]:
        """Summarize a response to fit within *target_tokens*.

        Preserves all ``[Source N]`` citation markers from the original
        response.  Returns ``None`` if:

        - No LLM client is configured.
        - The LLM call fails.
        - The summarized response does not preserve all original
          citations.

        Parameters
        ----------
        response:
            The original response text to summarize.
        target_tokens:
            The maximum number of estimated tokens for the summarized
            response.
        citations:
            Optional pre-extracted list of citation markers.  If not
            provided, they are extracted from *response*.
        """
        if self.llm_client is None:
            return None

        # Extract citations from the original response if not provided.
        if citations is None:
            citations = _CITATION_PATTERN.findall(response)

        prompt = _SUMMARIZE_PROMPT.format(
            target_tokens=target_tokens,
            response=response,
        )

        try:
            # The LLM client is expected to expose an async generate or
            # chat method.  We try ``generate`` first, then ``chat``.
            if hasattr(self.llm_client, "generate"):
                summarized = await self.llm_client.generate(prompt)
            elif hasattr(self.llm_client, "chat"):
                summarized = await self.llm_client.chat(prompt)
            else:
                logger.warning(
                    "LLM client has no 'generate' or 'chat' method; "
                    "cannot summarize response."
                )
                return None
        except Exception:
            logger.exception("LLM summarization call failed")
            self._rejected_count += 1
            return None

        if not summarized or not summarized.strip():
            logger.warning("LLM returned empty summarization result")
            self._rejected_count += 1
            return None

        summarized = summarized.strip()

        # Verify all original citations are preserved.
        if citations:
            summarized_citations = set(_CITATION_PATTERN.findall(summarized))
            missing = set(citations) - summarized_citations
            if missing:
                logger.warning(
                    "Summarized response is missing citations: %s",
                    missing,
                )
                self._rejected_count += 1
                return None

        self._summarized_count += 1
        return summarized

    # ------------------------------------------------------------------
    # Statistics
    # ------------------------------------------------------------------

    @property
    def summarized_count(self) -> int:
        """Number of responses successfully summarized."""
        return self._summarized_count

    @property
    def rejected_count(self) -> int:
        """Number of responses that failed summarization."""
        return self._rejected_count
