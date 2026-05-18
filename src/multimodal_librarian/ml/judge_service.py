"""
LLM-as-judge service for pairwise response evaluation.

Uses the DeepSeek API to score pairs of model responses on four
clinical dimensions (factual accuracy, completeness, clinical
relevance, coherence) and pick an overall winner with randomised
A/B ordering to prevent position bias.
"""

from __future__ import annotations

import json
import logging
import random
import re
from typing import Any, Dict

from multimodal_librarian.ml.models import (
    DimensionScores,
    JudgeResult,
    JudgeVerdict,
)
from multimodal_librarian.services.deepseek_ai_service import (
    DeepSeekAIService,
)

logger = logging.getLogger(__name__)


class JudgeParseError(Exception):
    """Raised when the judge response cannot be parsed."""


class JudgeService:
    """LLM-as-judge service for pairwise response evaluation.

    Args:
        deepseek_service: The DeepSeek API service used to send
            judge prompts and receive structured scoring responses.
        max_retries: Number of *additional* attempts after the
            first parse failure (default 2, so up to 3 total).
        temperature: Sampling temperature for the judge LLM. Low
            values (e.g. 0.1) maximise scoring consistency.
    """

    def __init__(
        self,
        deepseek_service: DeepSeekAIService,
        max_retries: int = 2,
        temperature: float = 0.1,
    ) -> None:
        self._deepseek = deepseek_service
        self._max_retries = max_retries
        self._temperature = temperature

        # Counters for tracking judge call outcomes.
        self.success_count: int = 0
        self.failure_count: int = 0

    # --------------------------------------------------------------
    # Prompt construction
    # --------------------------------------------------------------

    def build_judge_prompt(
        self,
        question: str,
        gold_answer: str,
        response_a: str,
        response_b: str,
    ) -> str:
        """Build the judge evaluation prompt.

        The prompt includes the question, gold-standard answer,
        both candidate responses labelled A and B, scoring
        instructions for four dimensions on a 1-5 integer scale,
        a winner instruction, and the expected JSON output format.

        Returns:
            The fully-constructed prompt string.
        """
        return (
            "You are an expert medical evaluator. Your task is "
            "to compare two responses to a medical question "
            "against a gold-standard reference answer.\n\n"
            "## Question\n"
            f"{question}\n\n"
            "## Gold-Standard Answer\n"
            f"{gold_answer}\n\n"
            "## Response A\n"
            f"{response_a}\n\n"
            "## Response B\n"
            f"{response_b}\n\n"
            "## Scoring Instructions\n"
            "Score each response on the following four dimensions"
            " using an integer scale from 1 (worst) to 5 "
            "(best):\n"
            "1. **Factual Accuracy** - correctness of medical "
            "facts compared to the gold-standard answer.\n"
            "2. **Completeness** - how thoroughly the response "
            "covers the key points in the gold-standard answer.\n"
            "3. **Clinical Relevance** - appropriateness and "
            "usefulness of the information in a clinical "
            "context.\n"
            "4. **Coherence** - logical flow, clarity, and "
            "readability of the response.\n\n"
            "## Winner Instruction\n"
            "After scoring, pick an overall winner: "
            '"A", "B", or "tie". '
            "Choose the response that best matches the "
            "gold-standard answer across all dimensions. "
            'If both are equally good, choose "tie".\n\n'
            "## Output Format\n"
            "Return your evaluation as a JSON object with "
            "exactly this structure (no additional text):\n"
            "```json\n"
            "{\n"
            '  "response_a_scores": {\n'
            '    "factual_accuracy": <1-5>,\n'
            '    "completeness": <1-5>,\n'
            '    "clinical_relevance": <1-5>,\n'
            '    "coherence": <1-5>\n'
            "  },\n"
            '  "response_b_scores": {\n'
            '    "factual_accuracy": <1-5>,\n'
            '    "completeness": <1-5>,\n'
            '    "clinical_relevance": <1-5>,\n'
            '    "coherence": <1-5>\n'
            "  },\n"
            '  "winner": "<A|B|tie>",\n'
            '  "explanation": "<brief explanation>"\n'
            "}\n"
            "```"
        )

    # --------------------------------------------------------------
    # Response parsing
    # --------------------------------------------------------------

    @staticmethod
    def _extract_json(raw: str) -> str:
        """Extract a JSON block from *raw*.

        Handles markdown code fences and surrounding text.

        Strategy:
          1. Fenced code block (```json ... ``` or ``` ... ```).
          2. First ``{`` to last ``}``.

        Raises:
            JudgeParseError: If no JSON-like content is found.
        """
        fence_re = re.compile(
            r"```(?:json)?\s*\n?(.*?)\n?\s*```", re.DOTALL
        )
        match = fence_re.search(raw)
        if match:
            return match.group(1).strip()

        first = raw.find("{")
        last = raw.rfind("}")
        if first != -1 and last > first:
            return raw[first:last + 1]

        raise JudgeParseError(
            "No JSON object found in judge response."
        )

    @staticmethod
    def _clamp_score(value: Any, field_name: str) -> int:
        """Clamp *value* to the [1, 5] integer range.

        Logs a warning when clamping is applied.
        """
        try:
            int_val = int(value)
        except (TypeError, ValueError) as exc:
            logger.warning(
                "Non-numeric score for %s (%r).",
                field_name,
                value,
            )
            raise JudgeParseError(
                f"Non-numeric score for "
                f"{field_name}: {value!r}"
            ) from exc

        if int_val < 1:
            logger.warning(
                "Score for %s clamped from %d to 1.",
                field_name,
                int_val,
            )
            return 1
        if int_val > 5:
            logger.warning(
                "Score for %s clamped from %d to 5.",
                field_name,
                int_val,
            )
            return 5
        return int_val

    @classmethod
    def _clamp_dimension_scores(
        cls, raw_scores: Dict[str, Any], label: str
    ) -> DimensionScores:
        """Build ``DimensionScores`` from a raw dict, clamping."""
        dims = [
            "factual_accuracy",
            "completeness",
            "clinical_relevance",
            "coherence",
        ]
        clamped: Dict[str, int] = {}
        for dim in dims:
            raw_val = raw_scores.get(dim)
            if raw_val is None:
                raise JudgeParseError(
                    f"Missing dimension '{dim}' in "
                    f"{label} scores."
                )
            clamped[dim] = cls._clamp_score(
                raw_val, f"{label}.{dim}"
            )
        return DimensionScores(**clamped)

    def parse_judge_response(
        self, raw_response: str
    ) -> JudgeVerdict:
        """Parse a raw LLM response into a ``JudgeVerdict``.

        Handles markdown code fences, surrounding text,
        out-of-range scores (clamped to [1, 5]), and
        unrecognised winner values (defaulted to ``"TIE"``
        by the model validator).

        Args:
            raw_response: Raw text from the DeepSeek API.

        Returns:
            A validated ``JudgeVerdict``.

        Raises:
            JudgeParseError: If the response cannot be parsed.
        """
        json_str = self._extract_json(raw_response)

        try:
            data = json.loads(json_str)
        except json.JSONDecodeError as exc:
            raise JudgeParseError(
                f"Invalid JSON in judge response: {exc}"
            ) from exc

        if not isinstance(data, dict):
            raise JudgeParseError(
                "Judge response JSON is not an object."
            )

        raw_a = data.get("response_a_scores")
        raw_b = data.get("response_b_scores")
        if not isinstance(raw_a, dict) or not isinstance(
            raw_b, dict
        ):
            raise JudgeParseError(
                "Missing or invalid 'response_a_scores' / "
                "'response_b_scores' in judge response."
            )

        scores_a = self._clamp_dimension_scores(
            raw_a, "response_a"
        )
        scores_b = self._clamp_dimension_scores(
            raw_b, "response_b"
        )

        winner = data.get("winner", "tie")
        if not isinstance(winner, str):
            logger.warning(
                "Non-string winner value %r, treating as tie.",
                winner,
            )
            winner = "tie"

        explanation = data.get("explanation", "")
        if not isinstance(explanation, str):
            explanation = str(explanation)

        return JudgeVerdict(
            response_a_scores=scores_a,
            response_b_scores=scores_b,
            winner=winner,
            explanation=explanation,
        )

    # --------------------------------------------------------------
    # Pairwise judging
    # --------------------------------------------------------------

    async def judge_pair(
        self,
        question: str,
        gold_answer: str,
        base_response: str,
        finetuned_response: str,
    ) -> JudgeResult:
        """Judge a pair of model responses for one question.

        The base and fine-tuned responses are randomly assigned
        to "Response A" and "Response B" to prevent position
        bias. The prompt is sent to DeepSeek, the response is
        parsed, and the verdict winner is mapped back to model
        identities.

        Args:
            question: The evaluation question text.
            gold_answer: The gold-standard reference answer.
            base_response: Response from the base model.
            finetuned_response: Response from the fine-tuned
                model.

        Returns:
            A ``JudgeResult`` with scores mapped to model
            identities.

        Raises:
            JudgeParseError: If all retry attempts fail.
        """
        base_is_a = random.random() < 0.5

        if base_is_a:
            response_a = base_response
            response_b = finetuned_response
            position_label = "base_is_A"
        else:
            response_a = finetuned_response
            response_b = base_response
            position_label = "base_is_B"

        prompt = self.build_judge_prompt(
            question=question,
            gold_answer=gold_answer,
            response_a=response_a,
            response_b=response_b,
        )

        messages = [{"role": "user", "content": prompt}]

        last_error: Exception | None = None
        total_attempts = 1 + self._max_retries

        for attempt in range(total_attempts):
            try:
                ai_resp = (
                    await self._deepseek.generate_response(
                        messages=messages,
                        temperature=self._temperature,
                        max_tokens=1024,
                    )
                )

                if ai_resp.confidence_score == 0.0:
                    raise JudgeParseError(
                        "DeepSeek API error: "
                        f"{ai_resp.content}"
                    )

                verdict = self.parse_judge_response(
                    ai_resp.content
                )

                mapped_winner = self._map_winner(
                    verdict.winner, base_is_a
                )

                if base_is_a:
                    base_scores = (
                        verdict.response_a_scores
                    )
                    finetuned_scores = (
                        verdict.response_b_scores
                    )
                else:
                    base_scores = (
                        verdict.response_b_scores
                    )
                    finetuned_scores = (
                        verdict.response_a_scores
                    )

                self.success_count += 1

                return JudgeResult(
                    base_scores=base_scores,
                    finetuned_scores=finetuned_scores,
                    winner=mapped_winner,
                    explanation=verdict.explanation,
                    position_label=position_label,
                )

            except JudgeParseError as exc:
                last_error = exc
                if attempt < total_attempts - 1:
                    logger.warning(
                        "Judge parse failed "
                        "(attempt %d/%d): %s. Retrying.",
                        attempt + 1,
                        total_attempts,
                        exc,
                    )
                else:
                    logger.warning(
                        "Judge parse failed on final "
                        "attempt (%d/%d): %s.",
                        attempt + 1,
                        total_attempts,
                        exc,
                    )

        self.failure_count += 1
        raise JudgeParseError(
            f"All {total_attempts} judge attempts failed. "
            f"Last error: {last_error}"
        )

    # --------------------------------------------------------------
    # Winner mapping
    # --------------------------------------------------------------

    @staticmethod
    def _map_winner(
        verdict_winner: str, base_is_a: bool
    ) -> str:
        """Map a verdict winner ("A", "B", "TIE") to a model
        identity ("base", "finetuned", "tie").

        Args:
            verdict_winner: The winner from the judge verdict
                (normalised to uppercase by the model
                validator).
            base_is_a: Whether the base model was assigned to
                position A.

        Returns:
            One of ``"base"``, ``"finetuned"``, or ``"tie"``.
        """
        if verdict_winner == "TIE":
            return "tie"

        if verdict_winner == "A":
            return "base" if base_is_a else "finetuned"

        if verdict_winner == "B":
            return "finetuned" if base_is_a else "base"

        logger.warning(
            "Unexpected verdict winner %r, "
            "treating as tie.",
            verdict_winner,
        )
        return "tie"

    # --------------------------------------------------------------
    # Availability check
    # --------------------------------------------------------------

    async def verify_available(self) -> None:
        """Verify that the DeepSeek API is reachable.

        Delegates to ``DeepSeekAIService.verify_available()``.
        Raises ``RuntimeError`` if the API is unreachable.
        """
        await self._deepseek.verify_available()
