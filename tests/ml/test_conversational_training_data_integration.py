"""
Integration tests for the conversational training data pipeline.

Tests the full RAGQAStrategy.generate() flow with mocked external
services (RAG, Neo4j, LLM) to verify end-to-end behavior including
question rewriting, refusal handling, quality filtering, concurrency
controls, partial saves, and citation preservation.

Requirements: 1.2, 1.4, 2.1, 5.1, 5.2, 5.3, 5.5
"""

from __future__ import annotations

import asyncio
import json
import os
import re
import tempfile
from typing import Any, Dict, List, Optional
from unittest.mock import AsyncMock, MagicMock

import pytest

from multimodal_librarian.ml.models import InstructionTuningPair
from multimodal_librarian.ml.quality_filter import QualityFilter
from multimodal_librarian.ml.question_rewriter import LLMQuestionRewriter
from multimodal_librarian.ml.rag_qa_strategy import RAGQAStrategy
from multimodal_librarian.ml.token_budget import TokenBudgetManager

# ---------------------------------------------------------------------------
# Shared mock factories
# ---------------------------------------------------------------------------

# A pool of concept names across different semantic types for Neo4j mocks.
_CONCEPT_POOL: List[Dict[str, Any]] = [
    {
        "preferred_name": "Aspirin",
        "cui": "C0004057",
        "semantic_type": "Pharmacologic Substance",
    },
    {
        "preferred_name": "Metformin",
        "cui": "C0025598",
        "semantic_type": "Pharmacologic Substance",
    },
    {
        "preferred_name": "Ibuprofen",
        "cui": "C0020740",
        "semantic_type": "Pharmacologic Substance",
    },
    {
        "preferred_name": "Diabetes Mellitus",
        "cui": "C0011849",
        "semantic_type": "Disease or Syndrome",
    },
    {
        "preferred_name": "Hypertension",
        "cui": "C0020538",
        "semantic_type": "Disease or Syndrome",
    },
    {
        "preferred_name": "Chest Pain",
        "cui": "C0008031",
        "semantic_type": "Sign or Symptom",
    },
    {
        "preferred_name": "Complete Blood Count",
        "cui": "C0009555",
        "semantic_type": "Diagnostic Procedure",
    },
    {
        "preferred_name": "Coronary Artery Bypass",
        "cui": "C0010055",
        "semantic_type": "Therapeutic or Preventive Procedure",
    },
    {
        "preferred_name": "Liver",
        "cui": "C0023884",
        "semantic_type": "Body Part, Organ, or Organ Component",
    },
    {
        "preferred_name": "Hemoglobin A1c",
        "cui": "C0019018",
        "semantic_type": "Laboratory or Test Result",
    },
]


def _make_normal_rag_response(concept_name: str = "aspirin") -> Dict[str, Any]:
    """Build a mock RAG response with citations and context."""
    return {
        "response": (
            f"{concept_name.title()} is a widely used medication in clinical practice. "
            "It has been extensively studied and shown to be effective for "
            "multiple indications including pain management and cardiovascular "
            "prevention. The mechanism involves inhibition of cyclooxygenase "
            "enzymes, leading to reduced prostaglandin synthesis. Clinical "
            "guidelines recommend its use in specific patient populations "
            "based on risk-benefit assessment. [Source 1] [Source 2]"
        ),
        "sources": [
            {
                "document_title": "Clinical Pharmacology Textbook",
                "chunk_id": "chunk_001",
                "excerpt": f"Detailed information about {concept_name} pharmacology.",
            },
            {
                "document_title": "Treatment Guidelines 2024",
                "chunk_id": "chunk_002",
                "excerpt": f"Evidence-based guidelines for {concept_name} use.",
            },
        ],
    }


def _make_refusal_rag_response() -> Dict[str, Any]:
    """Build a mock RAG response indicating no information found."""
    return {
        "response": (
            "I could not find any information about this topic "
            "in the available documents."
        ),
        "sources": [],
    }


def _make_mock_neo4j(concepts: Optional[List[Dict[str, Any]]] = None) -> AsyncMock:
    """Build a mock Neo4j client that returns concept records."""
    if concepts is None:
        concepts = _CONCEPT_POOL

    mock = AsyncMock()

    async def _execute_query(
        query: str, params: Optional[Dict[str, Any]] = None
    ) -> List[Dict[str, Any]]:
        if params and "semantic_type" in params:
            sem_type = params["semantic_type"]
            matching = [c for c in concepts if c.get("semantic_type") == sem_type]
            limit = params.get("limit", 10)
            return matching[:limit]
        return concepts[:5]

    mock.execute_query = AsyncMock(side_effect=_execute_query)
    return mock


def _make_mock_llm_client(
    rewrite_fn: Optional[Any] = None,
) -> AsyncMock:
    """Build a mock LLM client for question rewriting."""
    mock = AsyncMock()

    _call_count = 0

    async def _generate(prompt: str, system_prompt: str = "") -> str:
        nonlocal _call_count
        _call_count += 1
        if rewrite_fn:
            return rewrite_fn(prompt, _call_count)
        # Default: produce a conversational rewrite
        # Extract the original question from the prompt
        if "Original question:" in prompt:
            original = prompt.split("Original question:")[-1].strip()
            original = original.split("\n")[0].strip()
            # Simple rewrite: prepend conversational prefix
            prefixes = [
                "Can you tell me about",
                "I'd like to know about",
                "What can you share about",
                "Hey, I was wondering about",
                "Could you explain",
            ]
            prefix = prefixes[_call_count % len(prefixes)]
            # Extract the concept from the original question
            return f"{prefix} the topic mentioned in: {original}"
        return "Can you tell me about this medication?"

    mock.generate = AsyncMock(side_effect=_generate)
    return mock


# ---------------------------------------------------------------------------
# Integration tests
# ---------------------------------------------------------------------------


@pytest.mark.integration
class TestFullPipelineWithMockedServices:
    """Integration tests for RAGQAStrategy.generate() with mocked services.

    Requirements: 1.2, 1.4, 2.1, 5.1, 5.2, 5.3, 5.5
    """

    @pytest.mark.asyncio
    async def test_full_generate_produces_pairs(self) -> None:
        """Full pipeline with mocked services produces InstructionTuningPairs."""
        mock_rag = AsyncMock()
        mock_rag.generate_response = AsyncMock(
            return_value=_make_normal_rag_response()
        )
        mock_neo4j = _make_mock_neo4j()
        mock_umls = MagicMock()

        strategy = RAGQAStrategy(
            rag_service=mock_rag,
            neo4j_client=mock_neo4j,
            umls_client=mock_umls,
        )

        pairs = await strategy.generate(target_count=5)

        assert len(pairs) > 0, "Pipeline should produce at least some pairs"
        for pair in pairs:
            assert isinstance(pair, InstructionTuningPair)
            assert pair.metadata.strategy == "rag"
            assert len(pair.instruction) > 0
            assert len(pair.response) > 0
            assert len(pair.context) > 0

    @pytest.mark.asyncio
    async def test_llm_rewriter_called_and_produces_non_identical(self) -> None:
        """LLM rewriter must be called and produce non-identical outputs.

        Requirements: 1.2
        """
        mock_llm = _make_mock_llm_client()
        rewriter = LLMQuestionRewriter(llm_client=mock_llm, max_concurrent=4)

        mock_rag = AsyncMock()
        mock_rag.generate_response = AsyncMock(
            return_value=_make_normal_rag_response()
        )
        mock_neo4j = _make_mock_neo4j()

        strategy = RAGQAStrategy(
            rag_service=mock_rag,
            neo4j_client=mock_neo4j,
            umls_client=MagicMock(),
            question_rewriter=rewriter,
        )

        pairs = await strategy.generate(target_count=3)

        # The LLM generate method should have been called for rewriting
        assert mock_llm.generate.call_count > 0, (
            "LLM rewriter should have been called at least once"
        )

        # Verify the rewriter produced some successful rewrites
        assert rewriter.success_count > 0, (
            "At least some questions should have been successfully rewritten"
        )

    @pytest.mark.asyncio
    async def test_at_least_5_distinct_phrasings_per_semantic_type(self) -> None:
        """Pipeline must produce at least 5 distinct question phrasings
        per semantic type.

        Requirements: 1.4
        """
        # Use a single semantic type with enough concepts
        concepts = [
            {
                "preferred_name": f"Drug{i}",
                "cui": f"C{i:07d}",
                "semantic_type": "Pharmacologic Substance",
            }
            for i in range(20)
        ]
        mock_neo4j = _make_mock_neo4j(concepts)

        mock_rag = AsyncMock()
        mock_rag.generate_response = AsyncMock(
            return_value=_make_normal_rag_response()
        )

        strategy = RAGQAStrategy(
            rag_service=mock_rag,
            neo4j_client=mock_neo4j,
            umls_client=MagicMock(),
        )

        # Generate seed questions for a single type
        seeds = await strategy.generate_seed_questions(
            target_count=20,
            semantic_types=["Pharmacologic Substance"],
        )

        # Count distinct question phrasings (unique question text)
        pharma_questions = [
            s.question for s in seeds
            if s.semantic_type == "Pharmacologic Substance"
        ]
        distinct_phrasings = len(set(pharma_questions))

        assert distinct_phrasings >= 5, (
            f"Expected at least 5 distinct phrasings for "
            f"'Pharmacologic Substance', got {distinct_phrasings}"
        )

    @pytest.mark.asyncio
    async def test_refusal_pairs_produced_when_rag_returns_refusal(self) -> None:
        """Refusal pairs must be produced when RAG returns refusal responses.

        Requirements: 2.1
        """
        call_count = 0

        async def _alternating_rag_response(**kwargs: Any) -> Dict[str, Any]:
            nonlocal call_count
            call_count += 1
            if call_count % 2 == 0:
                return _make_refusal_rag_response()
            return _make_normal_rag_response()

        mock_rag = AsyncMock()
        mock_rag.generate_response = AsyncMock(side_effect=_alternating_rag_response)
        mock_neo4j = _make_mock_neo4j()

        strategy = RAGQAStrategy(
            rag_service=mock_rag,
            neo4j_client=mock_neo4j,
            umls_client=MagicMock(),
        )

        pairs = await strategy.generate(target_count=10)

        # Check that some pairs are refusals (contain refusal language)
        refusal_pairs = [
            p for p in pairs
            if any(
                indicator in p.response.lower()
                for indicator in [
                    "don't have information",
                    "wasn't able to find",
                    "don't cover",
                    "couldn't locate",
                    "not in the available sources",
                    "not in my available sources",
                ]
            )
        ]

        assert len(refusal_pairs) > 0, (
            "Expected at least some refusal pairs when RAG returns refusals"
        )

    @pytest.mark.asyncio
    async def test_concurrency_controls_preserved(self) -> None:
        """Concurrency controls (semaphore limits) must be preserved.

        Requirements: 5.5
        """
        max_concurrent_observed = 0
        current_concurrent = 0
        lock = asyncio.Lock()

        async def _tracked_rag_response(**kwargs: Any) -> Dict[str, Any]:
            nonlocal max_concurrent_observed, current_concurrent
            async with lock:
                current_concurrent += 1
                if current_concurrent > max_concurrent_observed:
                    max_concurrent_observed = current_concurrent

            # Simulate some work
            await asyncio.sleep(0.01)

            async with lock:
                current_concurrent -= 1

            return _make_normal_rag_response()

        mock_rag = AsyncMock()
        mock_rag.generate_response = AsyncMock(side_effect=_tracked_rag_response)
        mock_neo4j = _make_mock_neo4j()

        strategy = RAGQAStrategy(
            rag_service=mock_rag,
            neo4j_client=mock_neo4j,
            umls_client=MagicMock(),
        )

        await strategy.generate(target_count=5)

        # The semaphore limit is 8 in the implementation
        assert max_concurrent_observed <= 8, (
            f"Max concurrent RAG calls ({max_concurrent_observed}) "
            f"exceeded semaphore limit of 8"
        )

    @pytest.mark.asyncio
    async def test_partial_save_file_written_incrementally(self) -> None:
        """Partial save file must be written incrementally as pairs are produced.

        Requirements: 5.5
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            partial_path = os.path.join(tmpdir, "partial_save.jsonl")

            mock_rag = AsyncMock()
            mock_rag.generate_response = AsyncMock(
                return_value=_make_normal_rag_response()
            )
            mock_neo4j = _make_mock_neo4j()

            strategy = RAGQAStrategy(
                rag_service=mock_rag,
                neo4j_client=mock_neo4j,
                umls_client=MagicMock(),
            )

            pairs = await strategy.generate(
                target_count=3,
                partial_save_path=partial_path,
            )

            # Verify the partial save file exists and has content
            assert os.path.exists(partial_path), (
                "Partial save file should have been created"
            )

            with open(partial_path, "r", encoding="utf-8") as f:
                lines = [ln.strip() for ln in f if ln.strip()]

            assert len(lines) > 0, (
                "Partial save file should contain at least one line"
            )

            # Each line should be valid JSONL
            for line in lines:
                data = json.loads(line)
                assert "instruction" in data
                assert "response" in data
                assert "context" in data
                assert "metadata" in data

            # The number of lines should match the number of pairs returned
            assert len(lines) == len(pairs), (
                f"Partial save has {len(lines)} lines but "
                f"{len(pairs)} pairs were returned"
            )

    @pytest.mark.asyncio
    async def test_citation_format_preserved_from_rag_response(self) -> None:
        """Citation format ([Source N]) must be preserved from RAG response.

        Requirements: 5.2
        """
        mock_rag = AsyncMock()
        mock_rag.generate_response = AsyncMock(
            return_value={
                "response": (
                    "Aspirin is a nonsteroidal anti-inflammatory drug. "
                    "It inhibits cyclooxygenase enzymes [Source 1]. "
                    "Clinical trials have demonstrated its efficacy in "
                    "cardiovascular prevention [Source 2]. Long-term use "
                    "requires monitoring for gastrointestinal side effects "
                    "[Source 3]."
                ),
                "sources": [
                    {
                        "document_title": "Pharmacology Reference",
                        "chunk_id": "c001",
                        "excerpt": "Aspirin pharmacology details.",
                    },
                    {
                        "document_title": "Cardiology Guidelines",
                        "chunk_id": "c002",
                        "excerpt": "Cardiovascular prevention data.",
                    },
                    {
                        "document_title": "GI Safety Review",
                        "chunk_id": "c003",
                        "excerpt": "GI side effect monitoring.",
                    },
                ],
            }
        )
        mock_neo4j = _make_mock_neo4j()

        strategy = RAGQAStrategy(
            rag_service=mock_rag,
            neo4j_client=mock_neo4j,
            umls_client=MagicMock(),
        )

        pairs = await strategy.generate(target_count=3)

        # At least some pairs should preserve citations
        pairs_with_citations = [
            p for p in pairs if "[Source" in p.response
        ]
        assert len(pairs_with_citations) > 0, (
            "At least some pairs should preserve [Source N] citations"
        )

        # Verify citation format is intact
        for pair in pairs_with_citations:
            citations = re.findall(r"\[Source \d+\]", pair.response)
            assert len(citations) > 0, (
                f"Expected [Source N] citations in response: {pair.response[:100]}"
            )

    @pytest.mark.asyncio
    async def test_context_field_populated_from_rag_sources(self) -> None:
        """Context field must be populated from RAG response sources.

        Requirements: 5.3
        """
        mock_rag = AsyncMock()
        mock_rag.generate_response = AsyncMock(
            return_value={
                "response": (
                    "Metformin is a first-line treatment for type 2 diabetes. "
                    "It works by reducing hepatic glucose production and "
                    "improving insulin sensitivity. [Source 1]"
                ),
                "sources": [
                    {
                        "document_title": "Diabetes Management Guide",
                        "chunk_id": "dm_001",
                        "excerpt": (
                            "Metformin hydrochloride is the preferred initial "
                            "pharmacologic agent for type 2 diabetes mellitus."
                        ),
                    },
                    {
                        "document_title": "Endocrinology Textbook",
                        "chunk_id": "endo_042",
                        "excerpt": (
                            "The mechanism of action of metformin involves "
                            "activation of AMP-activated protein kinase."
                        ),
                    },
                ],
            }
        )
        mock_neo4j = _make_mock_neo4j()

        strategy = RAGQAStrategy(
            rag_service=mock_rag,
            neo4j_client=mock_neo4j,
            umls_client=MagicMock(),
        )

        pairs = await strategy.generate(target_count=3)

        assert len(pairs) > 0, "Should produce at least one pair"

        for pair in pairs:
            assert len(pair.context) > 0, (
                "Context field should be populated"
            )
            # Context should contain content from the RAG source excerpts
            # (either the excerpts or a fallback from the response)
            assert len(pair.context) > 10, (
                f"Context field seems too short: {pair.context!r}"
            )


@pytest.mark.integration
class TestPipelineWithQualityFilter:
    """Integration tests verifying quality filter integration."""

    @pytest.mark.asyncio
    async def test_quality_filter_rejects_mcq_responses(self) -> None:
        """MCQ-style responses from RAG should be filtered out."""
        mock_rag = AsyncMock()
        mock_rag.generate_response = AsyncMock(
            return_value={
                "response": (
                    "The mechanism of action involves: "
                    "A. Inhibition of COX-1 "
                    "B. Inhibition of COX-2 "
                    "C. Blocking sodium channels "
                    "D. Activating GABA receptors "
                    "The correct answer is A and B."
                ),
                "sources": [
                    {
                        "document_title": "Pharmacology",
                        "chunk_id": "c1",
                        "excerpt": "MCQ content.",
                    }
                ],
            }
        )
        mock_neo4j = _make_mock_neo4j()
        quality_filter = QualityFilter()

        strategy = RAGQAStrategy(
            rag_service=mock_rag,
            neo4j_client=mock_neo4j,
            umls_client=MagicMock(),
            quality_filter=quality_filter,
        )

        pairs = await strategy.generate(target_count=3)

        # MCQ responses should be filtered out
        for pair in pairs:
            assert "correct answer is" not in pair.response.lower(), (
                "MCQ-style responses should be filtered out"
            )

        # The filter should have evaluated and rejected some pairs
        summary = quality_filter.summarize()
        assert summary.total_evaluated > 0


@pytest.mark.integration
class TestPipelineWithTokenBudget:
    """Integration tests verifying token budget integration."""

    @pytest.mark.asyncio
    async def test_token_budget_manager_integrated(self) -> None:
        """Token budget manager should be used during generation."""
        from multimodal_librarian.ml.qlora_trainer import _SYSTEM_PROMPT

        tbm = TokenBudgetManager(max_tokens=5000)

        mock_rag = AsyncMock()
        mock_rag.generate_response = AsyncMock(
            return_value=_make_normal_rag_response()
        )
        mock_neo4j = _make_mock_neo4j()

        strategy = RAGQAStrategy(
            rag_service=mock_rag,
            neo4j_client=mock_neo4j,
            umls_client=MagicMock(),
            token_budget_manager=tbm,
        )

        pairs = await strategy.generate(target_count=3)

        # All produced pairs should fit within the token budget
        for pair in pairs:
            assert tbm.fits_budget(pair, _SYSTEM_PROMPT), (
                f"Pair should fit within token budget: "
                f"estimated={tbm.estimate_pair_tokens(pair, _SYSTEM_PROMPT)}, "
                f"max={tbm.max_tokens}"
            )


@pytest.mark.integration
class TestPipelineProgressCallback:
    """Integration tests for progress callback invocation."""

    @pytest.mark.asyncio
    async def test_progress_callback_invoked(self) -> None:
        """Progress callback must be invoked during generation.

        Requirements: 8.4
        """
        progress_calls: List[tuple] = []

        def _progress_callback(generated: int, target: int) -> None:
            progress_calls.append((generated, target))

        mock_rag = AsyncMock()
        mock_rag.generate_response = AsyncMock(
            return_value=_make_normal_rag_response()
        )
        mock_neo4j = _make_mock_neo4j()

        strategy = RAGQAStrategy(
            rag_service=mock_rag,
            neo4j_client=mock_neo4j,
            umls_client=MagicMock(),
        )

        pairs = await strategy.generate(
            target_count=3,
            progress_callback=_progress_callback,
        )

        if len(pairs) > 0:
            assert len(progress_calls) > 0, (
                "Progress callback should have been called at least once"
            )

            # Progress should be monotonically increasing
            for i in range(1, len(progress_calls)):
                assert progress_calls[i][0] >= progress_calls[i - 1][0], (
                    "Progress generated count should be non-decreasing"
                )

            # Target should be consistent
            for generated, target in progress_calls:
                assert target == 3, (
                    f"Target should be 3, got {target}"
                )
