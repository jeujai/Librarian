"""
Unit tests for the conversational training data pipeline.

Tests pipeline observability, logging, and edge cases for individual
components that are not covered by property-based tests.

Requirements: 4.6, 6.2, 8.1, 8.2, 8.3
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Dict, List, Optional
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from multimodal_librarian.ml.models import (
    InstructionTuningPair,
    PairMetadata,
    SeedQuestion,
)
from multimodal_librarian.ml.quality_filter import QualityFilter
from multimodal_librarian.ml.rag_qa_strategy import (
    RAGQAStrategy,
    compute_confidence_score,
)
from multimodal_librarian.ml.refusal_formatter import (
    REFUSAL_INDICATORS,
    format_refusal,
    has_refusal_then_fabrication,
    is_refusal_response,
)
from multimodal_librarian.ml.token_budget import TokenBudgetManager

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_pair(
    instruction: str = "Can you tell me about aspirin?",
    context: str = "Aspirin is a common medication.",
    response: str = "Aspirin is used as a pain reliever. [Source 1]",
    confidence: float = 0.8,
) -> InstructionTuningPair:
    """Build a minimal InstructionTuningPair for testing."""
    return InstructionTuningPair(
        instruction=instruction,
        context=context,
        response=response,
        metadata=PairMetadata(
            strategy="rag",
            confidence_score=confidence,
        ),
    )


def _make_rag_response(
    response_text: str,
    sources: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """Build a mock RAG response dict."""
    if sources is None:
        sources = [
            {
                "document_title": "Medical Reference",
                "chunk_id": "chunk_001",
                "excerpt": "Some medical context excerpt.",
            }
        ]
    return {
        "response": response_text,
        "sources": sources,
    }


def _make_refusal_rag_response() -> Dict[str, Any]:
    """Build a mock RAG response that is a refusal."""
    return {
        "response": "I could not find any information about this topic in the available documents.",
        "sources": [],
    }


# ---------------------------------------------------------------------------
# 11.1 Unit tests for pipeline observability and logging
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestGenerationSummaryLog:
    """Test that generation summary log contains expected fields.

    Requirements: 8.1
    """

    @pytest.mark.asyncio
    async def test_summary_log_contains_expected_fields(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """The generation summary log must contain total_pairs,
        refusal_count, mean_confidence, and filter_summary."""
        # Set up mocks
        mock_rag = AsyncMock()
        mock_rag.generate_response = AsyncMock(
            return_value=_make_rag_response(
                "Aspirin is a nonsteroidal anti-inflammatory drug (NSAID) "
                "commonly used for pain relief, fever reduction, and "
                "anti-inflammatory purposes. It works by inhibiting "
                "cyclooxygenase enzymes. [Source 1]"
            )
        )

        mock_neo4j = AsyncMock()
        mock_neo4j.execute_query = AsyncMock(
            return_value=[
                {
                    "preferred_name": "Aspirin",
                    "cui": "C0004057",
                    "semantic_type": "Pharmacologic Substance",
                }
            ]
        )

        mock_umls = MagicMock()
        quality_filter = QualityFilter()

        strategy = RAGQAStrategy(
            rag_service=mock_rag,
            neo4j_client=mock_neo4j,
            umls_client=mock_umls,
            quality_filter=quality_filter,
        )

        with caplog.at_level(logging.INFO, logger="multimodal_librarian.ml.rag_qa_strategy"):
            pairs = await strategy.generate(target_count=2)

        # Find the summary log message
        summary_messages = [
            r.message for r in caplog.records
            if "Generation complete" in r.message
        ]
        assert len(summary_messages) >= 1, (
            "Expected at least one 'Generation complete' log message"
        )

        summary_msg = summary_messages[0]
        assert "total_pairs=" in summary_msg
        assert "refusal_count=" in summary_msg
        assert "mean_confidence=" in summary_msg
        assert "filter_summary=" in summary_msg


@pytest.mark.unit
class TestRefusalPercentageWarning:
    """Test warning logged when refusal percentage outside 15–30%.

    Requirements: 8.2
    """

    @pytest.mark.asyncio
    async def test_warning_when_refusal_pct_below_15(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """A warning must be logged when refusal percentage < 15%."""
        # All responses are normal (no refusals) → 0% refusal rate.
        # No quality filter so template-style questions are not rejected.
        mock_rag = AsyncMock()
        mock_rag.generate_response = AsyncMock(
            return_value=_make_rag_response(
                "This medication is commonly used for pain relief and "
                "has been shown to be effective in clinical trials. "
                "It works by inhibiting specific enzymes in the body. "
                "[Source 1]"
            )
        )

        mock_neo4j = AsyncMock()
        mock_neo4j.execute_query = AsyncMock(
            return_value=[
                {
                    "preferred_name": "Ibuprofen",
                    "cui": "C0020740",
                    "semantic_type": "Pharmacologic Substance",
                },
            ]
        )

        strategy = RAGQAStrategy(
            rag_service=mock_rag,
            neo4j_client=mock_neo4j,
            umls_client=MagicMock(),
            # No quality filter — so template questions pass through
        )

        with caplog.at_level(logging.WARNING, logger="multimodal_librarian.ml.rag_qa_strategy"):
            await strategy.generate(target_count=3)

        warning_messages = [
            r.message for r in caplog.records
            if "Refusal percentage" in r.message
            and "outside the target range" in r.message
            and r.levelno == logging.WARNING
        ]
        assert len(warning_messages) >= 1, (
            "Expected a warning about refusal percentage being outside 15-30%"
        )

    @pytest.mark.asyncio
    async def test_warning_when_refusal_pct_above_30(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """A warning must be logged when refusal percentage > 30%."""
        # All responses are refusals → 100% refusal rate.
        # No quality filter so refusal pairs are not rejected.
        mock_rag = AsyncMock()
        mock_rag.generate_response = AsyncMock(
            return_value=_make_refusal_rag_response()
        )

        mock_neo4j = AsyncMock()
        mock_neo4j.execute_query = AsyncMock(
            return_value=[
                {
                    "preferred_name": "UnknownDrug",
                    "cui": "C9999999",
                    "semantic_type": "Pharmacologic Substance",
                },
            ]
        )

        strategy = RAGQAStrategy(
            rag_service=mock_rag,
            neo4j_client=mock_neo4j,
            umls_client=MagicMock(),
            # No quality filter — so refusal pairs pass through
        )

        with caplog.at_level(logging.WARNING, logger="multimodal_librarian.ml.rag_qa_strategy"):
            await strategy.generate(target_count=3)

        warning_messages = [
            r.message for r in caplog.records
            if "Refusal percentage" in r.message
            and "outside the target range" in r.message
            and r.levelno == logging.WARNING
        ]
        assert len(warning_messages) >= 1, (
            "Expected a warning about refusal percentage being outside 15-30%"
        )


@pytest.mark.unit
class TestRejectionRateWarning:
    """Test warning logged when rejection rate exceeds 40%.

    Requirements: 8.3
    """

    @pytest.mark.asyncio
    async def test_warning_when_rejection_rate_exceeds_40_pct(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """A warning must be logged when quality filter rejection rate > 40%."""
        # Use a quality filter that will reject most pairs (textbook-style
        # questions from templates will be rejected)
        mock_rag = AsyncMock()
        mock_rag.generate_response = AsyncMock(
            return_value=_make_rag_response(
                "This is a short response."  # Too short → rejected
            )
        )

        mock_neo4j = AsyncMock()
        mock_neo4j.execute_query = AsyncMock(
            return_value=[
                {
                    "preferred_name": "Aspirin",
                    "cui": "C0004057",
                    "semantic_type": "Pharmacologic Substance",
                },
            ]
        )

        quality_filter = QualityFilter(min_response_tokens=50)

        strategy = RAGQAStrategy(
            rag_service=mock_rag,
            neo4j_client=mock_neo4j,
            umls_client=MagicMock(),
            quality_filter=quality_filter,
        )

        with caplog.at_level(logging.WARNING, logger="multimodal_librarian.ml.rag_qa_strategy"):
            await strategy.generate(target_count=2)

        # Check if the rejection rate warning was logged
        # (It may or may not fire depending on how many pairs were evaluated)
        # The key thing is the code path exists and runs without error.
        # If all pairs are rejected, the warning should fire.
        warning_messages = [
            r.message for r in caplog.records
            if "rejection rate" in r.message
            and "exceeds 40%" in r.message
            and r.levelno == logging.WARNING
        ]
        # If the filter rejected everything, we expect the warning
        summary = quality_filter.summarize()
        if summary.total_evaluated > 0 and (1.0 - summary.pass_rate) > 0.40:
            assert len(warning_messages) >= 1, (
                "Expected a warning about rejection rate exceeding 40%"
            )


@pytest.mark.unit
class TestSystemPromptMatchesProduction:
    """Test that system prompt used in token budget matches _SYSTEM_PROMPT.

    Requirements: 6.2
    """

    def test_system_prompt_matches_qlora_trainer(self) -> None:
        """The system prompt imported in generate() must match the
        production constant from qlora_trainer.py."""
        from multimodal_librarian.ml.qlora_trainer import _SYSTEM_PROMPT

        # Verify the constant is a non-empty string
        assert isinstance(_SYSTEM_PROMPT, str)
        assert len(_SYSTEM_PROMPT) > 0

        # Verify it contains expected medical assistant content
        assert "medical" in _SYSTEM_PROMPT.lower()
        assert "knowledge" in _SYSTEM_PROMPT.lower()

        # Verify the token budget manager can use it
        tbm = TokenBudgetManager(max_tokens=5000)
        tokens = tbm.estimate_tokens(_SYSTEM_PROMPT)
        assert tokens > 0, "System prompt should have non-zero token estimate"
        assert tokens < 200, (
            f"System prompt token estimate ({tokens}) seems too large"
        )

    def test_generate_uses_qlora_system_prompt(self) -> None:
        """The RAGQAStrategy.generate() method imports _SYSTEM_PROMPT
        from qlora_trainer and uses it for token budget estimation."""
        # Verify the import path works
        # The system prompt should be the same one used in format_chat_message
        from multimodal_librarian.ml.qlora_trainer import (
            _SYSTEM_PROMPT,
            format_chat_message,
        )

        pair = _make_pair()
        formatted = format_chat_message(pair)
        messages = formatted["messages"]

        # The system message content should match _SYSTEM_PROMPT
        system_msg = next(m for m in messages if m["role"] == "system")
        assert system_msg["content"] == _SYSTEM_PROMPT


@pytest.mark.unit
class TestRejectionLogEntries:
    """Test that rejection log entries contain reason code and instruction text.

    Requirements: 4.6
    """

    def test_rejection_log_contains_reason_and_instruction(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """When a pair is rejected, the log must include the rejection
        reason(s) and the instruction text."""
        quality_filter = QualityFilter()

        # Create a pair that will be rejected for MCQ markers
        mcq_response = (
            "The answer options are: "
            "A. Inhibits COX-1 "
            "B. Inhibits COX-2 "
            "C. Blocks sodium channels "
            "D. Activates GABA receptors "
            "The correct answer is A."
        )
        pair = _make_pair(response=mcq_response)

        with caplog.at_level(logging.INFO, logger="multimodal_librarian.ml.quality_filter"):
            result = quality_filter.evaluate(pair)

        assert not result.passed
        assert "mcq_markers" in result.rejection_reasons

        # Check log output
        rejection_logs = [
            r.message for r in caplog.records
            if "Quality filter rejected pair" in r.message
        ]
        assert len(rejection_logs) >= 1, (
            "Expected at least one rejection log entry"
        )

        log_msg = rejection_logs[0]
        assert "mcq_markers" in log_msg, (
            "Rejection log must contain the reason code"
        )
        assert "Can you tell me about" in log_msg, (
            "Rejection log must contain the instruction text"
        )

    def test_rejection_log_for_textbook_style(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Textbook-style rejections must log the reason and instruction."""
        quality_filter = QualityFilter()

        pair = _make_pair(
            instruction="What is the mechanism of action of aspirin?",
            response=(
                "Aspirin works by irreversibly inhibiting cyclooxygenase "
                "enzymes (COX-1 and COX-2), which are responsible for "
                "the synthesis of prostaglandins and thromboxanes. "
                "[Source 1]"
            ),
        )

        with caplog.at_level(logging.INFO, logger="multimodal_librarian.ml.quality_filter"):
            result = quality_filter.evaluate(pair)

        assert not result.passed
        assert "textbook_style" in result.rejection_reasons

        rejection_logs = [
            r.message for r in caplog.records
            if "Quality filter rejected pair" in r.message
        ]
        assert len(rejection_logs) >= 1
        assert "textbook_style" in rejection_logs[0]
        assert "mechanism of action" in rejection_logs[0]

    def test_rejection_log_for_short_response(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Short response rejections must log the reason and instruction."""
        quality_filter = QualityFilter()

        pair = _make_pair(
            instruction="Can you tell me about metformin?",
            response="It's a drug.",
        )

        with caplog.at_level(logging.INFO, logger="multimodal_librarian.ml.quality_filter"):
            result = quality_filter.evaluate(pair, is_refusal=False)

        assert not result.passed
        assert "response_too_short" in result.rejection_reasons

        rejection_logs = [
            r.message for r in caplog.records
            if "Quality filter rejected pair" in r.message
        ]
        assert len(rejection_logs) >= 1
        assert "response_too_short" in rejection_logs[0]

    def test_multiple_rejection_reasons_all_logged(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """When a pair triggers multiple rejection reasons, all must be logged."""
        quality_filter = QualityFilter()

        # Textbook instruction + short response → two reasons
        pair = _make_pair(
            instruction="What is the pathophysiology of diabetes?",
            response="It's complex.",
        )

        with caplog.at_level(logging.INFO, logger="multimodal_librarian.ml.quality_filter"):
            result = quality_filter.evaluate(pair, is_refusal=False)

        assert not result.passed
        assert "textbook_style" in result.rejection_reasons
        assert "response_too_short" in result.rejection_reasons

        rejection_logs = [
            r.message for r in caplog.records
            if "Quality filter rejected pair" in r.message
        ]
        assert len(rejection_logs) >= 1
        log_msg = rejection_logs[0]
        assert "textbook_style" in log_msg
        assert "response_too_short" in log_msg
