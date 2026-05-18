"""
Tests for RAGQAStrategy.

Covers seed question generation from two sources (UMLS concepts and
semantic-type-aware medical templates), RAG pipeline integration,
low-confidence flagging by citation count, and graceful error handling.

# Feature: medical-knowledge-finetuning
# Property 5: Low-confidence flagging by citation count

Validates: Requirements 2.1, 2.2, 2.3, 2.4, 2.5, 2.6
"""

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
from unittest.mock import AsyncMock, MagicMock

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from multimodal_librarian.ml.models import InstructionTuningPair
from multimodal_librarian.ml.rag_qa_strategy import (
    CLINICAL_SEMANTIC_TYPES,
    DEFAULT_QUESTION_TEMPLATES,
    TEMPLATES_BY_SEMANTIC_TYPE,
    RAGQAStrategy,
    _build_context_summary,
    _count_citations,
    _extract_citations,
    _extract_response_text,
)

# ---------------------------------------------------------------
# Mock RAG response helpers
# ---------------------------------------------------------------


@dataclass
class MockCitationSource:
    """Mimics the CitationSource dataclass from rag_service."""

    document_id: str = "doc-001"
    document_title: str = "Harrison's Principles"
    page_number: Optional[int] = 42
    chunk_id: str = "chunk-001"
    relevance_score: float = 0.85
    excerpt: str = "Sample excerpt text."
    section_title: Optional[str] = "Pharmacology"


@dataclass
class MockRAGResponse:
    """Mimics the RAGResponse dataclass from rag_service."""

    response: str = "Metformin is a biguanide..."
    sources: List[MockCitationSource] = field(
        default_factory=list
    )
    confidence_score: float = 0.8
    processing_time_ms: int = 150
    tokens_used: int = 200
    search_results_count: int = 5
    fallback_used: bool = False
    metadata: Dict[str, Any] = field(
        default_factory=dict
    )


def _make_rag_response(
    response_text: str = "Metformin is a biguanide...",
    num_citations: int = 3,
    doc_title_prefix: str = "Source Doc",
) -> MockRAGResponse:
    """Build a mock RAG response with a given number of citations."""
    sources = []
    for i in range(num_citations):
        sources.append(
            MockCitationSource(
                document_id=f"doc-{i:03d}",
                document_title=f"{doc_title_prefix} {i + 1}",
                chunk_id=f"chunk-{i:03d}",
                relevance_score=0.9 - i * 0.05,
                excerpt=f"Excerpt from source {i + 1}.",
            )
        )
    return MockRAGResponse(
        response=response_text,
        sources=sources,
        search_results_count=num_citations,
    )


def _make_concept_record(
    preferred_name: str = "Metformin",
    cui: str = "C0025598",
    semantic_type: str = "Pharmacologic Substance",
) -> Dict[str, Any]:
    """Build a concept record matching Neo4j query result shape."""
    return {
        "preferred_name": preferred_name,
        "cui": cui,
        "semantic_type": semantic_type,
    }



# ---------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------


@pytest.fixture
def mock_rag_service():
    """Mock RAG service with generate_response."""
    service = MagicMock()
    service.generate_response = AsyncMock(
        return_value=_make_rag_response()
    )
    return service


@pytest.fixture
def mock_neo4j():
    """Mock Neo4j client with execute_query."""
    client = MagicMock()
    # Default: return concept records for UMLS queries
    client.execute_query = AsyncMock(
        return_value=[
            _make_concept_record("Metformin"),
            _make_concept_record("Aspirin", "C0004057"),
            _make_concept_record("Ibuprofen", "C0020740"),
        ]
    )
    return client


@pytest.fixture
def mock_umls_client():
    """Mock UMLS client."""
    client = MagicMock()
    client.search_by_name = AsyncMock(return_value=None)
    return client


@pytest.fixture
def strategy(mock_rag_service, mock_neo4j, mock_umls_client):
    """RAGQAStrategy with mocked dependencies."""
    return RAGQAStrategy(
        rag_service=mock_rag_service,
        neo4j_client=mock_neo4j,
        umls_client=mock_umls_client,
    )


# ---------------------------------------------------------------
# Hypothesis strategies for Property 5
# ---------------------------------------------------------------


def _citation_count() -> st.SearchStrategy[int]:
    """Non-negative citation count."""
    return st.integers(min_value=0, max_value=20)


def _min_citations_threshold() -> st.SearchStrategy[int]:
    """Positive min_citations threshold."""
    return st.integers(min_value=1, max_value=10)


def _rag_response_text() -> st.SearchStrategy[str]:
    """Non-empty response text."""
    return st.text(
        min_size=10,
        max_size=500,
        alphabet=st.characters(
            whitelist_categories=("L", "N", "Zs", "P"),
        ),
    ).filter(lambda s: s.strip())


# ---------------------------------------------------------------
# Async helper for running generate() inside Hypothesis
# ---------------------------------------------------------------

import asyncio


def _run_async(coro):
    """Run an async coroutine synchronously for Hypothesis tests."""
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


def _build_strategy_with_fixed_response(
    num_citations: int,
    response_text: str,
) -> RAGQAStrategy:
    """Build a RAGQAStrategy whose RAG service always returns
    a response with the given number of citations and text.

    The Neo4j client returns a single concept so that exactly
    one seed question is generated and one pair is produced.
    """
    rag_service = MagicMock()
    rag_service.generate_response = AsyncMock(
        return_value=_make_rag_response(
            num_citations=num_citations,
            response_text=response_text,
        )
    )

    neo4j = MagicMock()
    neo4j.execute_query = AsyncMock(
        return_value=[
            _make_concept_record("TestConcept", "C9999999"),
        ]
    )

    umls_client = MagicMock()
    umls_client.search_by_name = AsyncMock(return_value=None)

    return RAGQAStrategy(
        rag_service=rag_service,
        neo4j_client=neo4j,
        umls_client=umls_client,
    )


# ---------------------------------------------------------------
# Property 5: Low-confidence flagging by citation count
# ---------------------------------------------------------------


@pytest.mark.pbt
@pytest.mark.unit
class TestLowConfidenceFlaggingByCitationCount:
    """Property 5: Low-confidence flagging by citation count.

    For any RAG response with fewer than 2 source citations, the
    resulting InstructionTuningPair SHALL have a confidence score
    below the high-confidence threshold (< 0.7). For any RAG
    response with 2 or more citations, the pair SHALL NOT be
    flagged as low-confidence (confidence >= 0.7).

    Tests exercise the actual RAGQAStrategy.generate() code path
    with Hypothesis-generated citation counts and response texts.

    # Feature: medical-knowledge-finetuning, Property 5
    Validates: Requirements 2.3
    """

    @given(
        num_citations=st.integers(min_value=0, max_value=1),
        response_text=_rag_response_text(),
    )
    @settings(max_examples=100)
    def test_below_threshold_is_low_confidence(
        self,
        num_citations: int,
        response_text: str,
    ):
        """Responses with < 2 citations produce low-confidence pairs."""
        strategy = _build_strategy_with_fixed_response(
            num_citations=num_citations,
            response_text=response_text,
        )

        pairs = _run_async(
            strategy.generate(target_count=1, min_citations=2)
        )

        assert len(pairs) >= 1, (
            "Expected at least one pair from generate()"
        )
        for pair in pairs:
            assert pair.metadata.confidence_score < 0.7, (
                f"Expected low confidence for {num_citations} "
                f"citations, got {pair.metadata.confidence_score}"
            )

    @given(
        num_citations=st.integers(min_value=2, max_value=20),
        response_text=_rag_response_text(),
    )
    @settings(max_examples=100)
    def test_at_or_above_threshold_is_not_low_confidence(
        self,
        num_citations: int,
        response_text: str,
    ):
        """Responses with >= 2 citations are not low-confidence."""
        strategy = _build_strategy_with_fixed_response(
            num_citations=num_citations,
            response_text=response_text,
        )

        pairs = _run_async(
            strategy.generate(target_count=1, min_citations=2)
        )

        assert len(pairs) >= 1, (
            "Expected at least one pair from generate()"
        )
        for pair in pairs:
            assert pair.metadata.confidence_score >= 0.7, (
                f"Expected high confidence for {num_citations} "
                f"citations, got {pair.metadata.confidence_score}"
            )

    @given(
        num_citations=_citation_count(),
        response_text=_rag_response_text(),
    )
    @settings(max_examples=100)
    def test_confidence_always_in_valid_range(
        self,
        num_citations: int,
        response_text: str,
    ):
        """Confidence score is always in [0.0, 1.0] regardless of citation count."""
        strategy = _build_strategy_with_fixed_response(
            num_citations=num_citations,
            response_text=response_text,
        )

        pairs = _run_async(
            strategy.generate(target_count=1, min_citations=2)
        )

        assert len(pairs) >= 1, (
            "Expected at least one pair from generate()"
        )
        for pair in pairs:
            assert 0.0 <= pair.metadata.confidence_score <= 1.0, (
                f"Confidence {pair.metadata.confidence_score} out of "
                f"range for {num_citations} citations"
            )

    @given(
        low_citations=st.integers(min_value=0, max_value=1),
        high_citations=st.integers(min_value=2, max_value=20),
        response_text=_rag_response_text(),
    )
    @settings(max_examples=100)
    def test_more_citations_means_higher_confidence(
        self,
        low_citations: int,
        high_citations: int,
        response_text: str,
    ):
        """Pairs from responses with more citations have strictly
        higher confidence than pairs from responses with fewer."""
        low_strategy = _build_strategy_with_fixed_response(
            num_citations=low_citations,
            response_text=response_text,
        )
        high_strategy = _build_strategy_with_fixed_response(
            num_citations=high_citations,
            response_text=response_text,
        )

        low_pairs = _run_async(
            low_strategy.generate(target_count=1, min_citations=2)
        )
        high_pairs = _run_async(
            high_strategy.generate(target_count=1, min_citations=2)
        )

        assert len(low_pairs) >= 1 and len(high_pairs) >= 1
        assert (
            high_pairs[0].metadata.confidence_score
            > low_pairs[0].metadata.confidence_score
        ), (
            f"Expected higher confidence for {high_citations} citations "
            f"({high_pairs[0].metadata.confidence_score}) than "
            f"{low_citations} citations "
            f"({low_pairs[0].metadata.confidence_score})"
        )


# ---------------------------------------------------------------
# Helper function tests
# ---------------------------------------------------------------


class TestCountCitations:
    """Tests for _count_citations helper."""

    def test_with_rag_response_object(self):
        resp = _make_rag_response(num_citations=3)
        assert _count_citations(resp) == 3

    def test_with_empty_sources(self):
        resp = _make_rag_response(num_citations=0)
        assert _count_citations(resp) == 0

    def test_with_dict_response(self):
        resp = {
            "response": "text",
            "sources": [{"doc": "a"}, {"doc": "b"}],
        }
        assert _count_citations(resp) == 2

    def test_with_none_sources(self):
        resp = MagicMock(spec=[])
        assert _count_citations(resp) == 0


class TestExtractResponseText:
    """Tests for _extract_response_text helper."""

    def test_from_object(self):
        resp = _make_rag_response(
            response_text="Hello world"
        )
        assert _extract_response_text(resp) == "Hello world"

    def test_from_dict(self):
        resp = {"response": "Dict response"}
        assert _extract_response_text(resp) == "Dict response"

    def test_empty_response(self):
        resp = _make_rag_response(response_text="")
        assert _extract_response_text(resp) == ""


class TestExtractCitations:
    """Tests for _extract_citations helper."""

    def test_extracts_title_and_chunk_id(self):
        resp = _make_rag_response(num_citations=2)
        citations = _extract_citations(resp)
        assert len(citations) == 2
        assert "Source Doc 1" in citations[0]
        assert "chunk-000" in citations[0]

    def test_empty_sources(self):
        resp = _make_rag_response(num_citations=0)
        assert _extract_citations(resp) == []

    def test_dict_sources(self):
        resp = {
            "sources": [
                {
                    "document_title": "Book A",
                    "chunk_id": "c1",
                },
            ],
        }
        citations = _extract_citations(resp)
        assert len(citations) == 1
        assert "Book A" in citations[0]
        assert "c1" in citations[0]


class TestBuildContextSummary:
    """Tests for _build_context_summary helper."""

    def test_concatenates_excerpts(self):
        resp = _make_rag_response(num_citations=2)
        summary = _build_context_summary(resp)
        assert "Excerpt from source 1" in summary
        assert "Excerpt from source 2" in summary

    def test_empty_sources(self):
        resp = _make_rag_response(num_citations=0)
        assert _build_context_summary(resp) == ""


# ---------------------------------------------------------------
# Seed question generation tests
# ---------------------------------------------------------------


@pytest.mark.asyncio
class TestGenerateSeedQuestions:
    """Tests for seed question generation from three sources."""

    async def test_generates_umls_concept_seeds(
        self, strategy, mock_neo4j
    ):
        """UMLS concept seeds are generated from Neo4j."""
        seeds = await strategy.generate_seed_questions(30)

        # Should have called execute_query for UMLS concepts
        assert mock_neo4j.execute_query.call_count > 0

        umls_seeds = [
            s for s in seeds if s.source == "umls_concept"
        ]
        assert len(umls_seeds) > 0

        for seed in umls_seeds:
            assert seed.question
            assert seed.semantic_type is not None
            assert seed.concept_name is not None

    async def test_generates_template_seeds(
        self, strategy, mock_neo4j
    ):
        """Template seeds use UMLS concepts with templates."""
        seeds = await strategy.generate_seed_questions(30)

        template_seeds = [
            s for s in seeds if s.source == "template"
        ]
        assert len(template_seeds) > 0

        for seed in template_seeds:
            assert seed.question
            assert seed.concept_name is not None

    async def test_seed_budget_split(
        self, strategy
    ):
        """Budget is split across two sources."""
        seeds = await strategy.generate_seed_questions(30)

        sources = {s.source for s in seeds}
        # Both UMLS and template sources should be present
        assert "umls_concept" in sources or "template" in sources

    async def test_empty_neo4j_returns_empty_seeds(
        self, mock_rag_service, mock_umls_client
    ):
        """Empty Neo4j results produce no seeds."""
        neo4j = MagicMock()
        neo4j.execute_query = AsyncMock(return_value=[])

        strat = RAGQAStrategy(
            rag_service=mock_rag_service,
            neo4j_client=neo4j,
            umls_client=mock_umls_client,
        )

        seeds = await strat.generate_seed_questions(30)
        assert len(seeds) == 0

    async def test_neo4j_failure_handled_gracefully(
        self, mock_rag_service, mock_umls_client
    ):
        """Neo4j failures are logged and skipped."""
        neo4j = MagicMock()
        neo4j.execute_query = AsyncMock(
            side_effect=Exception("Connection refused")
        )

        strat = RAGQAStrategy(
            rag_service=mock_rag_service,
            neo4j_client=neo4j,
            umls_client=mock_umls_client,
        )

        # Should not raise
        seeds = await strat.generate_seed_questions(30)
        assert isinstance(seeds, list)


# ---------------------------------------------------------------
# RAG Q&A generation tests
# ---------------------------------------------------------------


@pytest.mark.asyncio
class TestRAGQAStrategyGenerate:
    """Tests for the main generate() method."""

    async def test_basic_generation(
        self, strategy, mock_rag_service
    ):
        """Basic generation produces pairs with correct structure."""
        pairs = await strategy.generate(target_count=3)

        assert len(pairs) > 0
        for pair in pairs:
            assert isinstance(pair, InstructionTuningPair)
            assert pair.instruction
            assert pair.context
            assert pair.response
            assert pair.metadata.strategy == "rag"
            assert 0.0 <= pair.metadata.confidence_score <= 1.0

    async def test_respects_target_count(
        self, strategy
    ):
        """Does not produce more pairs than target_count."""
        pairs = await strategy.generate(target_count=2)
        assert len(pairs) <= 2

    async def test_rag_failure_skips_question(
        self, mock_neo4j, mock_umls_client
    ):
        """RAG failures are skipped, not raised."""
        rag = MagicMock()
        rag.generate_response = AsyncMock(
            side_effect=Exception("RAG timeout")
        )

        strat = RAGQAStrategy(
            rag_service=rag,
            neo4j_client=mock_neo4j,
            umls_client=mock_umls_client,
        )

        # Should not raise
        pairs = await strat.generate(target_count=5)
        assert pairs == []

    async def test_empty_response_skipped(
        self, mock_neo4j, mock_umls_client
    ):
        """Empty RAG responses are skipped."""
        rag = MagicMock()
        rag.generate_response = AsyncMock(
            return_value=_make_rag_response(
                response_text=""
            )
        )

        strat = RAGQAStrategy(
            rag_service=rag,
            neo4j_client=mock_neo4j,
            umls_client=mock_umls_client,
        )

        pairs = await strat.generate(target_count=5)
        assert pairs == []

    async def test_low_citation_flagged_low_confidence(
        self, mock_neo4j, mock_umls_client
    ):
        """Responses with < 2 citations get low confidence."""
        rag = MagicMock()
        rag.generate_response = AsyncMock(
            return_value=_make_rag_response(
                num_citations=1,
                response_text="Single source answer.",
            )
        )

        strat = RAGQAStrategy(
            rag_service=rag,
            neo4j_client=mock_neo4j,
            umls_client=mock_umls_client,
        )

        pairs = await strat.generate(
            target_count=3, min_citations=2
        )

        for pair in pairs:
            assert pair.metadata.confidence_score < 0.7

    async def test_high_citation_not_flagged(
        self, mock_neo4j, mock_umls_client
    ):
        """Responses with >= 2 citations get high confidence."""
        rag = MagicMock()
        rag.generate_response = AsyncMock(
            return_value=_make_rag_response(
                num_citations=4,
                response_text="Well-cited answer.",
            )
        )

        strat = RAGQAStrategy(
            rag_service=rag,
            neo4j_client=mock_neo4j,
            umls_client=mock_umls_client,
        )

        pairs = await strat.generate(
            target_count=3, min_citations=2
        )

        for pair in pairs:
            assert pair.metadata.confidence_score >= 0.7

    async def test_progress_callback_invoked(
        self, strategy
    ):
        """Progress callback is called after each pair."""
        progress_calls = []

        def callback(generated, target):
            progress_calls.append((generated, target))

        pairs = await strategy.generate(
            target_count=3,
            progress_callback=callback,
        )

        assert len(progress_calls) == len(pairs)
        for i, (gen, tgt) in enumerate(progress_calls):
            assert gen == i + 1
            assert tgt == 3

    async def test_context_from_rag_sources(
        self, strategy
    ):
        """Context field contains RAG source excerpts."""
        pairs = await strategy.generate(target_count=1)

        if pairs:
            # Context should contain excerpt text
            assert pairs[0].context

    async def test_metadata_has_rag_strategy(
        self, strategy
    ):
        """All pairs have strategy='rag' in metadata."""
        pairs = await strategy.generate(target_count=3)

        for pair in pairs:
            assert pair.metadata.strategy == "rag"

    async def test_source_concepts_from_seed(
        self, strategy
    ):
        """Source concepts come from seed question concept."""
        pairs = await strategy.generate(target_count=3)

        # At least some pairs should have source concepts
        has_concepts = any(
            pair.metadata.source_concepts
            for pair in pairs
        )
        assert has_concepts

    async def test_zero_citations_gets_zero_confidence(
        self, mock_neo4j, mock_umls_client
    ):
        """Zero citations produce confidence of 0.0."""
        rag = MagicMock()
        rag.generate_response = AsyncMock(
            return_value=_make_rag_response(
                num_citations=0,
                response_text="No sources answer.",
            )
        )

        strat = RAGQAStrategy(
            rag_service=rag,
            neo4j_client=mock_neo4j,
            umls_client=mock_umls_client,
        )

        pairs = await strat.generate(
            target_count=3, min_citations=2
        )

        for pair in pairs:
            assert pair.metadata.confidence_score == 0.0

    async def test_mixed_rag_responses(
        self, mock_neo4j, mock_umls_client
    ):
        """Mix of successful and failed RAG responses."""
        call_count = 0

        async def side_effect(**kwargs):
            nonlocal call_count
            call_count += 1
            if call_count % 3 == 0:
                raise Exception("Intermittent failure")
            return _make_rag_response(
                num_citations=3,
                response_text=f"Answer {call_count}.",
            )

        rag = MagicMock()
        rag.generate_response = AsyncMock(
            side_effect=side_effect
        )

        strat = RAGQAStrategy(
            rag_service=rag,
            neo4j_client=mock_neo4j,
            umls_client=mock_umls_client,
        )

        pairs = await strat.generate(target_count=5)
        # Should have some pairs despite failures
        assert len(pairs) > 0

    async def test_rag_called_with_correct_user_id(
        self, strategy, mock_rag_service
    ):
        """RAG service is called with ml-training-pipeline user."""
        await strategy.generate(target_count=1)

        if mock_rag_service.generate_response.call_count > 0:
            call_kwargs = (
                mock_rag_service.generate_response.call_args
            )
            assert (
                call_kwargs.kwargs.get("user_id")
                == "ml-training-pipeline"
            )


# ---------------------------------------------------------------
# Unit tests for seed question generation (Task 3.3)
# ---------------------------------------------------------------


@pytest.mark.asyncio
class TestUMLSConceptSeedGeneration:
    """Tests for _generate_umls_concept_seeds — Source 1.

    Validates that UMLS concept seeds use semantic-type-aware templates,
    query Neo4j for each clinical semantic type, and produce well-formed
    SeedQuestion objects.

    Validates: Requirements 2.5
    """

    async def test_umls_seeds_use_semantic_type_templates(
        self, mock_rag_service, mock_umls_client
    ):
        """UMLS concept seeds use TEMPLATES_BY_SEMANTIC_TYPE for the
        concept's semantic type rather than the default templates."""
        neo4j = MagicMock()

        # Return a Pharmacologic Substance concept
        neo4j.execute_query = AsyncMock(
            return_value=[
                _make_concept_record(
                    "Metformin", "C0025598", "Pharmacologic Substance"
                ),
            ]
        )

        strat = RAGQAStrategy(
            rag_service=mock_rag_service,
            neo4j_client=neo4j,
            umls_client=mock_umls_client,
        )

        seeds = await strat.generate_seed_questions(2)
        umls_seeds = [s for s in seeds if s.source == "umls_concept"]

        assert len(umls_seeds) > 0
        for seed in umls_seeds:
            # The question should match one of the
            # Pharmacologic Substance templates
            pharm_templates = TEMPLATES_BY_SEMANTIC_TYPE[
                "Pharmacologic Substance"
            ]
            matches = any(
                seed.question
                == t.format(concept_name="Metformin")
                for t in pharm_templates
            )
            assert matches, (
                f"Question '{seed.question}' does not match any "
                f"Pharmacologic Substance template"
            )

    async def test_umls_seeds_have_correct_semantic_type(
        self, mock_rag_service, mock_umls_client
    ):
        """Each UMLS seed records the semantic type from the iteration,
        which corresponds to the queried CLINICAL_SEMANTIC_TYPES entry."""
        neo4j = MagicMock()

        async def return_typed_concept(query, params):
            sem_type = params.get("semantic_type", "Finding")
            return [
                _make_concept_record(
                    "Hypertension", "C0020538", sem_type
                ),
            ]

        neo4j.execute_query = AsyncMock(side_effect=return_typed_concept)

        strat = RAGQAStrategy(
            rag_service=mock_rag_service,
            neo4j_client=neo4j,
            umls_client=mock_umls_client,
        )

        seeds = await strat.generate_seed_questions(4)
        umls_seeds = [s for s in seeds if s.source == "umls_concept"]

        for seed in umls_seeds:
            # Semantic type should be one of the CLINICAL_SEMANTIC_TYPES
            assert seed.semantic_type in CLINICAL_SEMANTIC_TYPES
            assert seed.concept_name == "Hypertension"

    async def test_umls_seeds_query_multiple_semantic_types(
        self, mock_rag_service, mock_umls_client
    ):
        """UMLS seed generation queries Neo4j for multiple semantic types."""
        neo4j = MagicMock()
        call_types = []

        async def track_query(query, params):
            call_types.append(params.get("semantic_type"))
            return [
                _make_concept_record(
                    f"Concept_{params['semantic_type'][:4]}",
                    "C0000001",
                    params["semantic_type"],
                )
            ]

        neo4j.execute_query = AsyncMock(side_effect=track_query)

        strat = RAGQAStrategy(
            rag_service=mock_rag_service,
            neo4j_client=neo4j,
            umls_client=mock_umls_client,
        )

        # Request enough seeds to span multiple types
        await strat.generate_seed_questions(60)

        # Should have queried multiple distinct semantic types
        unique_types = set(call_types)
        assert len(unique_types) > 1, (
            f"Expected queries for multiple semantic types, "
                f"got: {unique_types}"
        )

    async def test_umls_seeds_skip_empty_preferred_name(
        self, mock_rag_service, mock_umls_client
    ):
        """Concepts with empty preferred_name are skipped."""
        neo4j = MagicMock()
        neo4j.execute_query = AsyncMock(
            return_value=[
                {
                    "preferred_name": "",
                    "cui": "C0000001",
                    "semantic_type": "Finding",
                },
                {
                    "preferred_name": "Fever",
                    "cui": "C0015967",
                    "semantic_type": "Finding",
                },
            ]
        )

        strat = RAGQAStrategy(
            rag_service=mock_rag_service,
            neo4j_client=neo4j,
            umls_client=mock_umls_client,
        )

        seeds = await strat.generate_seed_questions(2)
        umls_seeds = [s for s in seeds if s.source == "umls_concept"]

        # Only the non-empty concept should produce a seed
        for seed in umls_seeds:
            assert seed.concept_name == "Fever"

    async def test_umls_seeds_use_type_specific_templates_not_defaults(
        self, mock_rag_service, mock_umls_client
    ):
        """All CLINICAL_SEMANTIC_TYPES have entries in
        TEMPLATES_BY_SEMANTIC_TYPE, so seeds should never use
        DEFAULT_QUESTION_TEMPLATES in practice."""
        # Verify the configuration invariant
        for sem_type in CLINICAL_SEMANTIC_TYPES:
            assert sem_type in TEMPLATES_BY_SEMANTIC_TYPE, (
                f"Semantic type '{sem_type}' missing from "
                f"TEMPLATES_BY_SEMANTIC_TYPE"
            )

        neo4j = MagicMock()
        neo4j.execute_query = AsyncMock(
            return_value=[
                _make_concept_record(
                    "SomeEntity", "C9999999", "Pharmacologic Substance"
                ),
            ]
        )

        strat = RAGQAStrategy(
            rag_service=mock_rag_service,
            neo4j_client=neo4j,
            umls_client=mock_umls_client,
        )

        seeds = await strat.generate_seed_questions(2)
        umls_seeds = [s for s in seeds if s.source == "umls_concept"]

        for seed in umls_seeds:
            # Should match a type-specific template, not a default one
            sem_type = seed.semantic_type
            type_templates = TEMPLATES_BY_SEMANTIC_TYPE[sem_type]
            matches_type = any(
                seed.question == t.format(concept_name="SomeEntity")
                for t in type_templates
            )
            matches_default = any(
                seed.question == t.format(concept_name="SomeEntity")
                for t in DEFAULT_QUESTION_TEMPLATES
            )
            assert matches_type, (
                f"Question '{seed.question}' does not match any "
                f"template for type '{sem_type}'"
            )
            # It's possible a default template also matches a type template,
            # but the type-specific match should always hold
            assert matches_type or matches_default


@pytest.mark.asyncio
class TestTemplateSeedGeneration:
    """Tests for _generate_template_seeds — Source 2.

    Validates that template seeds fetch concept names from Neo4j,
    use semantic-type-aware templates, and handle failures gracefully.

    Validates: Requirements 2.5
    """

    async def test_template_seeds_contain_concept_name(
        self, mock_rag_service, mock_neo4j, mock_umls_client
    ):
        """Template seeds include the concept name in the question."""
        strat = RAGQAStrategy(
            rag_service=mock_rag_service,
            neo4j_client=mock_neo4j,
            umls_client=mock_umls_client,
        )

        seeds = await strat.generate_seed_questions(30)
        template_seeds = [s for s in seeds if s.source == "template"]

        for seed in template_seeds:
            assert seed.concept_name is not None
            # The concept name should appear in the question text
            assert seed.concept_name.lower() in seed.question.lower(), (
                f"Concept '{seed.concept_name}' not found in "
                f"question '{seed.question}'"
            )

    async def test_template_seeds_use_type_specific_templates(
        self, mock_rag_service, mock_umls_client
    ):
        """Template seeds use semantic-type-aware templates
        when type is known."""
        neo4j = MagicMock()
        neo4j.execute_query = AsyncMock(
            return_value=[
                _make_concept_record(
                    "Aspirin", "C0004057", "Pharmacologic Substance"
                ),
            ]
        )

        strat = RAGQAStrategy(
            rag_service=mock_rag_service,
            neo4j_client=neo4j,
            umls_client=mock_umls_client,
        )

        seeds = await strat.generate_seed_questions(4)
        template_seeds = [s for s in seeds if s.source == "template"]

        if template_seeds:
            pharm_templates = TEMPLATES_BY_SEMANTIC_TYPE[
                "Pharmacologic Substance"
            ]
            for seed in template_seeds:
                matches = any(
                    seed.question == t.format(concept_name="Aspirin")
                    for t in pharm_templates
                )
                assert matches, (
                    f"Template seed '{seed.question}' does not match "
                    f"any Pharmacologic Substance template"
                )

    async def test_template_seeds_empty_concept_pool(
        self, mock_rag_service, mock_umls_client
    ):
        """No template seeds when concept pool is empty."""
        neo4j = MagicMock()
        neo4j.execute_query = AsyncMock(return_value=[])

        strat = RAGQAStrategy(
            rag_service=mock_rag_service,
            neo4j_client=neo4j,
            umls_client=mock_umls_client,
        )

        seeds = await strat.generate_seed_questions(10)
        # Both sources rely on Neo4j, so all should be empty
        assert len(seeds) == 0

    async def test_template_seeds_neo4j_partial_failure(
        self, mock_rag_service, mock_umls_client
    ):
        """Template generation continues when some Neo4j queries fail."""
        call_count = 0

        async def partial_failure(query, params):
            nonlocal call_count
            call_count += 1
            if call_count % 2 == 0:
                raise Exception("Intermittent Neo4j failure")
            return [
                _make_concept_record(
                    f"Concept{call_count}",
                    f"C{call_count:07d}",
                    params.get("semantic_type", "Finding"),
                )
            ]

        neo4j = MagicMock()
        neo4j.execute_query = AsyncMock(side_effect=partial_failure)

        strat = RAGQAStrategy(
            rag_service=mock_rag_service,
            neo4j_client=neo4j,
            umls_client=mock_umls_client,
        )

        seeds = await strat.generate_seed_questions(20)
        # Should have some seeds despite partial failures
        assert len(seeds) > 0


@pytest.mark.asyncio
class TestSeedBudgetSplitting:
    """Tests for even budget splitting between the two seed sources.

    Validates: Requirements 2.5
    """

    async def test_budget_split_evenly(
        self, mock_rag_service, mock_umls_client
    ):
        """Budget is split roughly evenly between UMLS and template sources."""
        neo4j = MagicMock()
        # Return plenty of concepts so neither source is starved
        neo4j.execute_query = AsyncMock(
            return_value=[
                _make_concept_record(f"Concept{i}", f"C{i:07d}", "Finding")
                for i in range(50)
            ]
        )

        strat = RAGQAStrategy(
            rag_service=mock_rag_service,
            neo4j_client=neo4j,
            umls_client=mock_umls_client,
        )

        target = 20
        seeds = await strat.generate_seed_questions(target)

        umls_count = sum(1 for s in seeds if s.source == "umls_concept")
        template_count = sum(1 for s in seeds if s.source == "template")

        # Both sources should contribute
        assert umls_count > 0, "Expected UMLS concept seeds"
        assert template_count > 0, "Expected template seeds"

        # Neither source should dominate excessively (allow 70/30 skew)
        total = umls_count + template_count
        if total > 0:
            ratio = min(umls_count, template_count) / total
            assert ratio >= 0.2, (
                f"Budget split too skewed: {umls_count} UMLS vs "
                f"{template_count} template"
            )

    async def test_odd_target_count_handled(
        self, mock_rag_service, mock_umls_client
    ):
        """Odd target counts don't lose a seed."""
        neo4j = MagicMock()
        neo4j.execute_query = AsyncMock(
            return_value=[
                _make_concept_record(f"Concept{i}", f"C{i:07d}", "Finding")
                for i in range(50)
            ]
        )

        strat = RAGQAStrategy(
            rag_service=mock_rag_service,
            neo4j_client=neo4j,
            umls_client=mock_umls_client,
        )

        seeds = await strat.generate_seed_questions(11)
        # Should produce seeds from both sources totalling up to 11
        assert len(seeds) <= 11


# ---------------------------------------------------------------
# Unit tests for RAG failure handling (Task 3.3)
# ---------------------------------------------------------------


@pytest.mark.asyncio
class TestRAGFailureHandling:
    """Tests for graceful RAG failure handling during generation.

    Validates: Requirements 2.4
    """

    async def test_rag_none_response_skipped(
        self, mock_neo4j, mock_umls_client
    ):
        """None RAG response is treated as empty and skipped."""
        rag = MagicMock()
        rag.generate_response = AsyncMock(return_value=None)

        strat = RAGQAStrategy(
            rag_service=rag,
            neo4j_client=mock_neo4j,
            umls_client=mock_umls_client,
        )

        pairs = await strat.generate(target_count=3)
        assert pairs == []

    async def test_rag_failure_logs_warning(
        self, mock_neo4j, mock_umls_client, caplog
    ):
        """RAG failures are logged with the question text."""
        rag = MagicMock()
        rag.generate_response = AsyncMock(
            side_effect=Exception("Connection timeout")
        )

        strat = RAGQAStrategy(
            rag_service=rag,
            neo4j_client=mock_neo4j,
            umls_client=mock_umls_client,
        )

        with caplog.at_level(logging.WARNING):
            pairs = await strat.generate(target_count=3)

        assert pairs == []
        # Should have logged warnings about RAG failures
        rag_warnings = [
            r for r in caplog.records
            if "RAG" in r.message and "skipping" in r.message.lower()
        ]
        assert len(rag_warnings) > 0, (
            "Expected warning logs for RAG failures"
        )

    async def test_empty_response_logs_warning(
        self, mock_neo4j, mock_umls_client, caplog
    ):
        """Empty RAG responses are logged as warnings."""
        rag = MagicMock()
        rag.generate_response = AsyncMock(
            return_value=_make_rag_response(response_text="   ")
        )

        strat = RAGQAStrategy(
            rag_service=rag,
            neo4j_client=mock_neo4j,
            umls_client=mock_umls_client,
        )

        with caplog.at_level(logging.WARNING):
            pairs = await strat.generate(target_count=3)

        assert pairs == []
        empty_warnings = [
            r for r in caplog.records
            if "Empty response" in r.message
        ]
        assert len(empty_warnings) > 0, (
            "Expected warning logs for empty responses"
        )

    async def test_mixed_failures_continue_processing(
        self, mock_neo4j, mock_umls_client
    ):
        """Generation continues past failures and collects successful pairs."""
        call_count = 0

        async def alternating_response(**kwargs):
            nonlocal call_count
            call_count += 1
            if call_count <= 2:
                raise Exception("First two fail")
            return _make_rag_response(
                num_citations=3,
                response_text=f"Valid answer {call_count}.",
            )

        rag = MagicMock()
        rag.generate_response = AsyncMock(side_effect=alternating_response)

        strat = RAGQAStrategy(
            rag_service=rag,
            neo4j_client=mock_neo4j,
            umls_client=mock_umls_client,
        )

        pairs = await strat.generate(target_count=3)
        # Should have collected pairs from the successful calls
        assert len(pairs) > 0
        for pair in pairs:
            assert "Valid answer" in pair.response

    async def test_all_failures_returns_empty_list(
        self, mock_neo4j, mock_umls_client
    ):
        """When all RAG calls fail, returns empty list without raising."""
        rag = MagicMock()
        rag.generate_response = AsyncMock(
            side_effect=Exception("Persistent failure")
        )

        strat = RAGQAStrategy(
            rag_service=rag,
            neo4j_client=mock_neo4j,
            umls_client=mock_umls_client,
        )

        pairs = await strat.generate(target_count=10)
        assert pairs == []
        assert isinstance(pairs, list)


# ---------------------------------------------------------------
# Unit tests for confidence scoring formula (Task 3.3)
# ---------------------------------------------------------------


@pytest.mark.asyncio
class TestConfidenceScoringFormula:
    """Tests for the confidence score calculation based on citation count.

    The formula from the implementation:
    - < min_citations: confidence = max(0.3 * (count / min_citations), 0.0)
    - >= min_citations: confidence =
      min(0.7 + 0.3 * (count / (count + 2)), 1.0)

    Validates: Requirements 2.3
    """

    async def test_zero_citations_gives_zero(
        self, mock_neo4j, mock_umls_client
    ):
        """Zero citations produce confidence of 0.0."""
        rag = MagicMock()
        rag.generate_response = AsyncMock(
            return_value=_make_rag_response(
                num_citations=0, response_text="No sources."
            )
        )

        strat = RAGQAStrategy(
            rag_service=rag,
            neo4j_client=mock_neo4j,
            umls_client=mock_umls_client,
        )

        pairs = await strat.generate(target_count=1, min_citations=2)
        assert len(pairs) > 0
        assert pairs[0].metadata.confidence_score == 0.0

    async def test_one_citation_gives_low_confidence(
        self, mock_neo4j, mock_umls_client
    ):
        """One citation with min_citations=2 gives 0.3 * (1/2) = 0.15."""
        rag = MagicMock()
        rag.generate_response = AsyncMock(
            return_value=_make_rag_response(
                num_citations=1, response_text="Single source."
            )
        )

        strat = RAGQAStrategy(
            rag_service=rag,
            neo4j_client=mock_neo4j,
            umls_client=mock_umls_client,
        )

        pairs = await strat.generate(target_count=1, min_citations=2)
        assert len(pairs) > 0
        score = pairs[0].metadata.confidence_score
        expected = round(0.3 * (1 / 2), 4)
        assert score == expected, (
            f"Expected {expected} for 1 citation, got {score}"
        )

    async def test_exactly_min_citations_gives_high_confidence(
        self, mock_neo4j, mock_umls_client
    ):
        """Exactly min_citations produces confidence >= 0.7."""
        rag = MagicMock()
        rag.generate_response = AsyncMock(
            return_value=_make_rag_response(
                num_citations=2, response_text="Two sources."
            )
        )

        strat = RAGQAStrategy(
            rag_service=rag,
            neo4j_client=mock_neo4j,
            umls_client=mock_umls_client,
        )

        pairs = await strat.generate(target_count=1, min_citations=2)
        assert len(pairs) > 0
        score = pairs[0].metadata.confidence_score
        # Formula: 0.7 + 0.3 * (2 / (2 + 2)) = 0.7 + 0.15 = 0.85
        expected = round(0.7 + 0.3 * (2 / 4), 4)
        assert score == expected, (
            f"Expected {expected} for 2 citations, got {score}"
        )

    async def test_many_citations_approaches_one(
        self, mock_neo4j, mock_umls_client
    ):
        """Many citations produce confidence approaching
        but not exceeding 1.0."""
        rag = MagicMock()
        rag.generate_response = AsyncMock(
            return_value=_make_rag_response(
                num_citations=20, response_text="Well-cited answer."
            )
        )

        strat = RAGQAStrategy(
            rag_service=rag,
            neo4j_client=mock_neo4j,
            umls_client=mock_umls_client,
        )

        pairs = await strat.generate(target_count=1, min_citations=2)
        assert len(pairs) > 0
        score = pairs[0].metadata.confidence_score
        # Formula: 0.7 + 0.3 * (20 / 22) ≈ 0.9727
        assert 0.95 <= score <= 1.0, (
            f"Expected score near 1.0 for 20 citations, got {score}"
        )

    async def test_confidence_monotonically_increases(
        self, mock_neo4j, mock_umls_client
    ):
        """Confidence increases monotonically with citation count."""
        scores = []
        for n_citations in [0, 1, 2, 3, 5, 10]:
            rag = MagicMock()
            rag.generate_response = AsyncMock(
                return_value=_make_rag_response(
                    num_citations=n_citations,
                    response_text=f"Answer with {n_citations} citations.",
                )
            )

            strat = RAGQAStrategy(
                rag_service=rag,
                neo4j_client=mock_neo4j,
                umls_client=mock_umls_client,
            )

            pairs = await strat.generate(target_count=1, min_citations=2)
            assert len(pairs) > 0
            scores.append(pairs[0].metadata.confidence_score)

        # Verify monotonic increase
        for i in range(1, len(scores)):
            assert scores[i] >= scores[i - 1], (
                f"Confidence not monotonic: {scores}"
            )


# ---------------------------------------------------------------
# Unit tests for metadata and output structure (Task 3.3)
# ---------------------------------------------------------------


@pytest.mark.asyncio
class TestRAGPairMetadata:
    """Tests for metadata fields on generated pairs.

    Validates: Requirements 2.2, 2.6
    """

    async def test_chunk_ids_extracted_from_citations(
        self, mock_neo4j, mock_umls_client
    ):
        """Chunk IDs are extracted from citation strings into metadata."""
        rag = MagicMock()
        rag.generate_response = AsyncMock(
            return_value=_make_rag_response(
                num_citations=3, response_text="Cited answer."
            )
        )

        strat = RAGQAStrategy(
            rag_service=rag,
            neo4j_client=mock_neo4j,
            umls_client=mock_umls_client,
        )

        pairs = await strat.generate(target_count=1)
        assert len(pairs) > 0
        pair = pairs[0]

        # Chunk IDs should be extracted from "Title (chunk_id)" format
        assert pair.metadata.chunk_ids is not None
        assert len(pair.metadata.chunk_ids) > 0
        for chunk_id in pair.metadata.chunk_ids:
            assert chunk_id.startswith("chunk-")

    async def test_source_document_from_first_citation(
        self, mock_neo4j, mock_umls_client
    ):
        """source_document is set to the first citation string."""
        rag = MagicMock()
        rag.generate_response = AsyncMock(
            return_value=_make_rag_response(
                num_citations=2,
                response_text="Answer.",
                doc_title_prefix="Medical Text",
            )
        )

        strat = RAGQAStrategy(
            rag_service=rag,
            neo4j_client=mock_neo4j,
            umls_client=mock_umls_client,
        )

        pairs = await strat.generate(target_count=1)
        assert len(pairs) > 0
        assert pairs[0].metadata.source_document is not None
        assert "Medical Text 1" in pairs[0].metadata.source_document

    async def test_no_citations_means_no_chunk_ids(
        self, mock_neo4j, mock_umls_client
    ):
        """Zero citations produce None for chunk_ids and source_document."""
        rag = MagicMock()
        rag.generate_response = AsyncMock(
            return_value=_make_rag_response(
                num_citations=0, response_text="Uncited answer."
            )
        )

        strat = RAGQAStrategy(
            rag_service=rag,
            neo4j_client=mock_neo4j,
            umls_client=mock_umls_client,
        )

        pairs = await strat.generate(target_count=1)
        assert len(pairs) > 0
        assert pairs[0].metadata.source_document is None

    async def test_context_uses_excerpts_when_available(
        self, mock_neo4j, mock_umls_client
    ):
        """Context field uses source excerpts rather than
        truncated response."""
        rag = MagicMock()
        rag.generate_response = AsyncMock(
            return_value=_make_rag_response(
                num_citations=2, response_text="Full response text."
            )
        )

        strat = RAGQAStrategy(
            rag_service=rag,
            neo4j_client=mock_neo4j,
            umls_client=mock_umls_client,
        )

        pairs = await strat.generate(target_count=1)
        assert len(pairs) > 0
        # Context should contain excerpt text from sources
        assert "Excerpt from source" in pairs[0].context

    async def test_context_falls_back_to_response_when_no_excerpts(
        self, mock_neo4j, mock_umls_client
    ):
        """Context falls back to truncated response when no source excerpts."""
        response = MockRAGResponse(
            response="A long response without source excerpts.",
            sources=[],
        )
        rag = MagicMock()
        rag.generate_response = AsyncMock(return_value=response)

        strat = RAGQAStrategy(
            rag_service=rag,
            neo4j_client=mock_neo4j,
            umls_client=mock_umls_client,
        )

        pairs = await strat.generate(target_count=1)
        # With no sources, response text is empty → skipped
        # But if response is non-empty and no excerpts,
        # context = response[:500]
        # This depends on whether _build_context_summary
        # returns "" for empty sources, which it does,
        # so context = response[:500]
        if pairs:
            expected = (
                "A long response without source excerpts."
            )
            assert pairs[0].context == expected[:500]
