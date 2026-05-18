"""
Unit tests for the fine-tuned-model-regression bugfix spec.

Covers small, focused unit tests that validate the stateless schema and
helper changes made by this bugfix. Property-based tests live in
``tests/ml/test_fine_tuned_model_regression.py``.

Requirements: 3.4
"""

from __future__ import annotations

from multimodal_librarian.ml.models import PairMetadata

# ---------------------------------------------------------------------------
# Task 1.2 — ``PairMetadata.semantic_type`` round-trip and default
#
# Validates Requirement 3.4: ``PairMetadata`` gains a new optional
# ``semantic_type`` field that must (a) serialize to JSON and parse back
# equal, and (b) default to ``None`` when loading legacy JSON payloads that
# predate the field.
# ---------------------------------------------------------------------------


class TestPairMetadataSemanticType:
    """Round-trip and legacy-load behavior for ``PairMetadata.semantic_type``."""

    def test_semantic_type_roundtrip_equal(self) -> None:
        """``PairMetadata`` with a populated ``semantic_type`` round-trips."""
        original = PairMetadata(
            strategy="rag",
            confidence_score=0.85,
            semantic_type="Diagnostic Procedure",
        )

        # ``model_dump`` produces a plain dict suitable for JSON
        # serialization; ``model_validate`` rebuilds the Pydantic model.
        dumped = original.model_dump()
        rebuilt = PairMetadata.model_validate(dumped)

        assert rebuilt == original
        assert rebuilt.semantic_type == "Diagnostic Procedure"

    def test_semantic_type_json_string_roundtrip_equal(self) -> None:
        """JSON-string round-trip also preserves ``semantic_type``."""
        original = PairMetadata(
            strategy="rag",
            confidence_score=0.85,
            semantic_type="Diagnostic Procedure",
        )

        json_line = original.model_dump_json()
        rebuilt = PairMetadata.model_validate_json(json_line)

        assert rebuilt == original
        assert rebuilt.semantic_type == "Diagnostic Procedure"

    def test_legacy_dict_without_semantic_type_loads_as_none(self) -> None:
        """A legacy JSON dict (no ``semantic_type`` key) loads with ``None``.

        This simulates reading a ``training_data.jsonl`` file that predates
        the new field. The model must tolerate the missing key and default
        ``semantic_type`` to ``None`` so existing datasets remain loadable.
        """
        legacy_payload = {
            "strategy": "rag",
            "confidence_score": 0.5,
            # note: no ``semantic_type`` key at all
        }

        # Sanity check: the fixture genuinely lacks the new key.
        assert "semantic_type" not in legacy_payload

        loaded = PairMetadata.model_validate(legacy_payload)

        assert loaded.semantic_type is None
        assert loaded.strategy == "rag"
        assert loaded.confidence_score == 0.5


# ---------------------------------------------------------------------------
# Task 5.1 — ``SeedQuestion.semantic_type`` propagation in ``_process_seed``
#
# Validates Requirements 2.2, 2.3, 2.4, 2.5, 3.4: the generated
# ``InstructionTuningPair`` must carry the originating semantic type on
# ``metadata.semantic_type`` so the per-type training-data balance floor
# (Property 3) can be observed on disk.
# ---------------------------------------------------------------------------

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
from unittest.mock import AsyncMock, MagicMock

import pytest

from multimodal_librarian.ml.rag_qa_strategy import RAGQAStrategy


@dataclass
class _MockCitationSource:
    document_id: str = "doc-001"
    document_title: str = "Harrison's Principles"
    page_number: Optional[int] = 42
    chunk_id: str = "chunk-001"
    relevance_score: float = 0.85
    excerpt: str = "Sample excerpt text."
    section_title: Optional[str] = "Pharmacology"


@dataclass
class _MockRAGResponse:
    response: str = "Metformin is a biguanide..."
    sources: List[_MockCitationSource] = field(default_factory=list)
    confidence_score: float = 0.8
    processing_time_ms: int = 150
    tokens_used: int = 200
    search_results_count: int = 5
    fallback_used: bool = False
    metadata: Dict[str, Any] = field(default_factory=dict)


def _rag_response_with_citations(
    num_citations: int = 3,
) -> _MockRAGResponse:
    sources = [
        _MockCitationSource(
            document_id=f"doc-{i:03d}",
            document_title=f"Source {i + 1}",
            chunk_id=f"chunk-{i:03d}",
            relevance_score=0.9 - i * 0.05,
            excerpt=f"Excerpt {i + 1}",
        )
        for i in range(num_citations)
    ]
    return _MockRAGResponse(
        response=(
            "A sufficiently long well-cited answer to the seed question "
            "that cites all provided sources [Source 1] [Source 2] "
            "[Source 3] and satisfies the quality filter gate."
        ),
        sources=sources,
        search_results_count=num_citations,
    )


def _concept_record(
    name: str, cui: str, semantic_type: str
) -> Dict[str, Any]:
    return {
        "preferred_name": name,
        "cui": cui,
        "semantic_type": semantic_type,
    }


@pytest.mark.asyncio
class TestSemanticTypePropagation:
    """Task 5.1: ``SeedQuestion.semantic_type`` reaches ``metadata.semantic_type``.

    **Validates: Requirements 2.2, 2.3, 2.4, 2.5, 3.4**

    When ``RAGQAStrategy.generate`` runs a seed through ``_process_seed``
    and produces an accepted ``InstructionTuningPair``, the pair's
    ``metadata.semantic_type`` SHALL equal the originating
    ``SeedQuestion.semantic_type``. This is the precondition for the
    per-type training-data balance floor (Property 3) — without it, no
    downstream consumer can inspect the JSONL to verify that the floor is
    met.
    """

    async def _build_strategy_for_type(
        self, semantic_type: str
    ) -> RAGQAStrategy:
        """Build a strategy whose Neo4j mock returns one concept of a given type."""
        rag = MagicMock()
        rag.generate_response = AsyncMock(
            return_value=_rag_response_with_citations(num_citations=3)
        )

        neo4j = MagicMock()
        neo4j.execute_query = AsyncMock(
            return_value=[
                _concept_record(
                    "TestConcept", "C0000001", semantic_type
                )
            ]
        )

        umls_client = MagicMock()
        umls_client.search_by_name = AsyncMock(return_value=None)

        return RAGQAStrategy(
            rag_service=rag,
            neo4j_client=neo4j,
            umls_client=umls_client,
        )

    async def test_diagnostic_procedure_semantic_type_propagates(
        self,
    ) -> None:
        """A Diagnostic Procedure seed yields a pair tagged with that type."""
        strat = await self._build_strategy_for_type(
            "Diagnostic Procedure"
        )

        pairs = await strat.generate(
            target_count=1,
            semantic_types=["Diagnostic Procedure"],
        )

        assert len(pairs) > 0, (
            "Expected at least one accepted pair from the mocked RAG "
            "response"
        )
        assert (
            pairs[0].metadata.semantic_type == "Diagnostic Procedure"
        ), (
            "metadata.semantic_type must match the originating seed's "
            "semantic type so Property 3 can observe per-type balance"
        )

    async def test_pharmacologic_substance_semantic_type_propagates(
        self,
    ) -> None:
        """A Pharmacologic Substance seed yields a pair tagged with that type."""
        strat = await self._build_strategy_for_type(
            "Pharmacologic Substance"
        )

        pairs = await strat.generate(
            target_count=1,
            semantic_types=["Pharmacologic Substance"],
        )

        assert len(pairs) > 0
        assert (
            pairs[0].metadata.semantic_type
            == "Pharmacologic Substance"
        )

    async def test_semantic_type_survives_jsonl_roundtrip(self) -> None:
        """The tagged pair round-trips through JSONL with ``semantic_type`` intact."""
        from multimodal_librarian.ml.models import InstructionTuningPair

        strat = await self._build_strategy_for_type("Sign or Symptom")

        pairs = await strat.generate(
            target_count=1,
            semantic_types=["Sign or Symptom"],
        )

        assert len(pairs) > 0
        pair = pairs[0]
        assert pair.metadata.semantic_type == "Sign or Symptom"

        # JSONL round-trip must preserve the new field end-to-end
        restored = InstructionTuningPair.from_jsonl_line(
            pair.to_jsonl_line()
        )
        assert restored.metadata.semantic_type == "Sign or Symptom"
        assert restored == pair

    async def test_strategy_remains_rag_and_citation_logic_unchanged(
        self,
    ) -> None:
        """Adding ``semantic_type`` leaves strategy/confidence/citations intact.

        Preservation (Property 5): task 5.1 may only add a new field. The
        existing ``strategy="rag"`` tag, ``confidence_score`` computation,
        ``source_document`` selection, and ``chunk_ids`` extraction must
        all be byte-equal to pre-fix behavior.
        """
        strat = await self._build_strategy_for_type(
            "Therapeutic or Preventive Procedure"
        )

        pairs = await strat.generate(
            target_count=1,
            semantic_types=["Therapeutic or Preventive Procedure"],
        )

        assert len(pairs) > 0
        meta = pairs[0].metadata

        assert meta.strategy == "rag"
        # Three citations → confidence score in the high band per
        # ``compute_confidence_score`` (non-empty, > 0.7).
        assert 0.7 < meta.confidence_score <= 1.0
        assert meta.source_document is not None
        assert meta.source_document.startswith("Source 1")
        assert meta.chunk_ids is not None
        assert all(
            cid.startswith("chunk-") for cid in meta.chunk_ids
        )


# ---------------------------------------------------------------------------
# Task 7.3 — Populate ``EvaluationQuestion.context`` from RAG sources in
#             ``generate_eval_set``
#
# Validates Requirements 3.5, 3.6: the evaluation set must have non-empty
# ``context`` whenever RAG returned sources with content, so the eval
# prompt matches the training format (Property 4).
# ---------------------------------------------------------------------------

from multimodal_librarian.ml.evaluation_runner import EvaluationRunner, _extract_context
from multimodal_librarian.ml.models import EvaluationConfig, EvaluationQuestion


class TestExtractContext:
    """Unit tests for the ``_extract_context`` helper."""

    def test_returns_empty_when_no_sources(self) -> None:
        """No sources → empty context string."""
        mock_response = MagicMock()
        mock_response.sources = []
        assert _extract_context(mock_response) == ""

    def test_returns_empty_when_sources_is_none(self) -> None:
        """``sources`` attribute is None → empty context string."""
        mock_response = MagicMock()
        mock_response.sources = None
        assert _extract_context(mock_response) == ""

    def test_returns_concatenated_content_from_sources(self) -> None:
        """Sources with content produce a non-empty context string."""
        mock_response = MagicMock()
        mock_response.sources = [
            MagicMock(excerpt="First chunk content about aspirin.", spec=["excerpt"]),
            MagicMock(excerpt="Second chunk about dosage.", spec=["excerpt"]),
        ]
        result = _extract_context(mock_response)
        assert "[Source 1]" in result
        assert "[Source 2]" in result
        assert "First chunk content about aspirin." in result
        assert "Second chunk about dosage." in result

    def test_skips_sources_with_empty_content(self) -> None:
        """Sources with empty or whitespace-only content are skipped."""
        mock_response = MagicMock()
        mock_response.sources = [
            MagicMock(excerpt="Valid content here.", spec=["excerpt"]),
            MagicMock(excerpt="", spec=["excerpt"]),
            MagicMock(excerpt="   ", spec=["excerpt"]),
            MagicMock(excerpt="Another valid chunk.", spec=["excerpt"]),
        ]
        result = _extract_context(mock_response)
        # Source numbering follows the original index in the sources list
        assert "[Source 1]" in result
        assert "[Source 4]" in result
        assert "Valid content here." in result
        assert "Another valid chunk." in result
        # Sources 2 and 3 had empty content and are skipped
        assert "[Source 2]" not in result
        assert "[Source 3]" not in result

    def test_works_with_dict_sources(self) -> None:
        """Dict-based sources (instead of objects) also work."""
        mock_response = {
            "sources": [
                {"content": "Dict-based content."},
                {"content": "More dict content."},
            ]
        }
        result = _extract_context(mock_response)
        assert "[Source 1]" in result
        assert "Dict-based content." in result
        assert "More dict content." in result


@pytest.mark.asyncio
class TestGenerateEvalSetContextPopulation:
    """Task 7.3: ``generate_eval_set`` populates ``context`` from RAG sources.

    **Validates: Requirements 3.5, 3.6**

    The bug condition was that the regressing eval set had ``context=""``
    for all 50 questions, causing the eval prompt to diverge from the
    training format (H2). The fix ensures ``_extract_context`` output is
    wired into the persisted ``EvaluationQuestion.context`` field.
    """

    async def test_context_populated_when_rag_returns_sources_with_content(
        self,
    ) -> None:
        """Eval questions have non-empty context when RAG sources have content."""
        # Mock RAG that returns sources WITH content (the key difference
        # from the old mock that only had document_title/chunk_id)
        mock_rag = AsyncMock()

        async def _generate_response(query: str, user_id: str = ""):
            return MagicMock(
                response=f"Gold answer for: {query}",
                sources=[
                    MagicMock(
                        document_title="Medical Textbook",
                        chunk_id="chunk-001",
                        excerpt="Aspirin inhibits COX enzymes irreversibly.",
                        spec=["document_title", "chunk_id", "excerpt"],
                    ),
                    MagicMock(
                        document_title="Clinical Guide",
                        chunk_id="chunk-002",
                        excerpt="Dosage ranges from 75mg to 325mg daily.",
                        spec=["document_title", "chunk_id", "excerpt"],
                    ),
                ],
            )

        mock_rag.generate_response = AsyncMock(side_effect=_generate_response)

        # Mock Neo4j returning concepts
        mock_neo4j = AsyncMock()

        async def _execute_query(query: str, params: Dict[str, Any]):
            return [
                {"preferred_name": "Aspirin", "cui": "C0004057"},
                {"preferred_name": "Ibuprofen", "cui": "C0020740"},
                {"preferred_name": "Metformin", "cui": "C0025598"},
            ]

        mock_neo4j.execute_query = AsyncMock(side_effect=_execute_query)

        config = EvaluationConfig(eval_set_path="", eval_count=5)
        runner = EvaluationRunner(config, judge=AsyncMock())

        eval_set = await runner.generate_eval_set(
            rag_service=mock_rag,
            neo4j_client=mock_neo4j,
            training_questions=set(),
            count=5,
            min_semantic_types=1,
        )

        assert len(eval_set.questions) > 0, (
            "Expected at least one eval question to be generated"
        )

        for eq in eval_set.questions:
            assert eq.context != "", (
                f"EvaluationQuestion.context must be non-empty when RAG "
                f"returned sources with content. Got empty context for: "
                f"{eq.question}"
            )
            assert "[Source 1]" in eq.context
            assert "Aspirin inhibits COX enzymes" in eq.context

    async def test_context_empty_when_rag_sources_have_no_content(
        self,
    ) -> None:
        """Eval questions have empty context when RAG sources lack content."""
        mock_rag = AsyncMock()

        async def _generate_response(query: str, user_id: str = ""):
            return MagicMock(
                response=f"Gold answer for: {query}",
                sources=[
                    MagicMock(
                        document_title="Medical Textbook",
                        chunk_id="chunk-001",
                        excerpt="",  # No content
                        spec=["document_title", "chunk_id", "excerpt"],
                    ),
                    MagicMock(
                        document_title="Clinical Guide",
                        chunk_id="chunk-002",
                        excerpt="",  # No content
                        spec=["document_title", "chunk_id", "excerpt"],
                    ),
                ],
            )

        mock_rag.generate_response = AsyncMock(side_effect=_generate_response)

        mock_neo4j = AsyncMock()

        async def _execute_query(query: str, params: Dict[str, Any]):
            return [
                {"preferred_name": "Aspirin", "cui": "C0004057"},
                {"preferred_name": "Ibuprofen", "cui": "C0020740"},
            ]

        mock_neo4j.execute_query = AsyncMock(side_effect=_execute_query)

        config = EvaluationConfig(eval_set_path="", eval_count=5)
        runner = EvaluationRunner(config, judge=AsyncMock())

        eval_set = await runner.generate_eval_set(
            rag_service=mock_rag,
            neo4j_client=mock_neo4j,
            training_questions=set(),
            count=5,
            min_semantic_types=1,
        )

        # When sources have no content, context should be empty
        for eq in eval_set.questions:
            assert eq.context == ""

    async def test_context_persists_through_jsonl_export_and_load(
        self,
    ) -> None:
        """Context survives JSONL export/load round-trip (eval_set.jsonl)."""
        import json
        import tempfile
        from pathlib import Path

        mock_rag = AsyncMock()

        async def _generate_response(query: str, user_id: str = ""):
            return MagicMock(
                response=f"Gold answer for: {query}",
                sources=[
                    MagicMock(
                        document_title="Textbook",
                        chunk_id="chunk-001",
                        content="Important medical context about the topic.",
                    ),
                ],
            )

        mock_rag.generate_response = AsyncMock(side_effect=_generate_response)

        mock_neo4j = AsyncMock()

        async def _execute_query(query: str, params: Dict[str, Any]):
            return [{"preferred_name": "Aspirin", "cui": "C0004057"}]

        mock_neo4j.execute_query = AsyncMock(side_effect=_execute_query)

        config = EvaluationConfig(eval_set_path="", eval_count=3)
        runner = EvaluationRunner(config, judge=AsyncMock())

        eval_set = await runner.generate_eval_set(
            rag_service=mock_rag,
            neo4j_client=mock_neo4j,
            training_questions=set(),
            count=3,
            min_semantic_types=1,
        )

        assert len(eval_set.questions) > 0

        # Export to JSONL
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".jsonl", delete=False
        ) as f:
            output_path = Path(f.name)

        EvaluationRunner.export_eval_set(eval_set, output_path)

        # Load back and verify context is preserved
        loaded = EvaluationRunner.load_eval_set(output_path)

        for original, loaded_q in zip(
            eval_set.questions, loaded.questions
        ):
            assert loaded_q.context == original.context
            assert loaded_q.context != "", (
                "Context must be non-empty after JSONL round-trip"
            )
            assert "[Source 1]" in loaded_q.context

        # Cleanup
        output_path.unlink(missing_ok=True)
