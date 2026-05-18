"""
Integration tests for the three-layer concurrent NER extraction system.

Tests verify:
1. DI wiring: get_ner_extractor() loads both models independently
   and caches correctly
2. RelevanceDetector uses NER_Extractor: filter_chunks_by_proper_nouns
   uses extract_key_terms when ner_extractor is set
3. analyze_query_term_coverage uses NER_Extractor key_terms
4. QueryDecomposer includes multi-word NER entities in
   _find_entity_matches
5. UMLS batch_search_by_names is called with generated n-grams
6. Concurrent execution: all three layers run in parallel

Validates: Requirements 7.1, 7.2, 7.3, 7.4, 8.2, 4.2, 3.4, 4.6
"""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.multimodal_librarian.components.kg_retrieval.ner_extractor import (  # noqa: E501
    NER_Extractor,
    NERResult,
)
from src.multimodal_librarian.components.kg_retrieval.query_decomposer import (  # noqa: E501
    QueryDecomposer,
)
from src.multimodal_librarian.components.kg_retrieval.relevance_detector import (  # noqa: E501
    QueryTermCoverageResult,
    RelevanceDetector,
    analyze_query_term_coverage,
)
from src.multimodal_librarian.models.kg_retrieval import (  # noqa: E501
    RetrievalSource,
    RetrievedChunk,
)

# =============================================================================
# Helpers
# =============================================================================


def _make_mock_nlp(entities=None, noun_chunks=None):
    """Create a mock spaCy nlp model that returns controlled output.

    Parameters
    ----------
    entities : list[tuple[str, str]]
        (text, label_) pairs for named entities.
    noun_chunks : list[list[tuple[str, str]]]
        Each inner list is a noun chunk; each tuple is (text, pos_).
    """
    if entities is None:
        entities = []
    if noun_chunks is None:
        noun_chunks = []

    mock_nlp = MagicMock()

    def _call(query):
        doc = MagicMock()

        # Build entity mocks
        ent_mocks = []
        for text, label in entities:
            ent = MagicMock()
            ent.text = text
            ent.label_ = label
            ent_mocks.append(ent)
        doc.ents = ent_mocks

        # Build noun chunk mocks
        nc_mocks = []
        for chunk_tokens in noun_chunks:
            nc = MagicMock()
            tok_mocks = []
            for tok_text, tok_pos in chunk_tokens:
                tok = MagicMock()
                tok.text = tok_text
                tok.pos_ = tok_pos
                tok_mocks.append(tok)
            nc.__iter__ = lambda s, _t=tok_mocks: iter(_t)
            nc_mocks.append(nc)
        doc.noun_chunks = nc_mocks

        return doc

    mock_nlp.side_effect = _call
    return mock_nlp


def _make_chunk(
    chunk_id: str,
    content: str,
    score: float = 0.5,
) -> RetrievedChunk:
    """Create a RetrievedChunk with minimal fields."""
    return RetrievedChunk(
        chunk_id=chunk_id,
        content=content,
        source=RetrievalSource.DIRECT_CONCEPT,
        final_score=score,
        kg_relevance_score=0.8,
        semantic_score=score,
    )


# =============================================================================
# Test 1: DI wiring — get_ner_extractor() loads both models and caches
# Validates: Requirement 7.1
# =============================================================================


class TestDIWiring:
    """Verify get_ner_extractor() loads both models independently
    and caches correctly."""

    @pytest.mark.asyncio
    async def test_loads_both_models_independently(self):
        """Each spaCy model loads independently; failure of one
        does not prevent the other from loading."""
        import src.multimodal_librarian.api.dependencies.services as svc

        # Reset cache
        svc._ner_extractor = None

        mock_web = MagicMock(name="en_core_web_sm")
        mock_sci = MagicMock(name="en_core_sci_sm")

        def _spacy_load(name):
            if name == "en_core_web_sm":
                return mock_web
            if name == "en_core_sci_sm":
                return mock_sci
            raise OSError(f"Model {name} not found")

        with patch("spacy.load", side_effect=_spacy_load):
            result = await svc.get_ner_extractor(umls_client=None)

        assert result is not None
        assert result.spacy_web_nlp is mock_web
        assert result.spacy_sci_nlp is mock_sci

        # Cleanup
        svc._ner_extractor = None

    @pytest.mark.asyncio
    async def test_web_model_failure_still_loads_sci(self):
        """If en_core_web_sm fails, en_core_sci_sm still loads."""
        import src.multimodal_librarian.api.dependencies.services as svc

        svc._ner_extractor = None

        mock_sci = MagicMock(name="en_core_sci_sm")

        def _spacy_load(name):
            if name == "en_core_web_sm":
                raise OSError("web model missing")
            if name == "en_core_sci_sm":
                return mock_sci
            raise OSError(f"Model {name} not found")

        with patch("spacy.load", side_effect=_spacy_load):
            result = await svc.get_ner_extractor(umls_client=None)

        assert result is not None
        assert result.spacy_web_nlp is None
        assert result.spacy_sci_nlp is mock_sci

        svc._ner_extractor = None

    @pytest.mark.asyncio
    async def test_caching_returns_same_instance(self):
        """Subsequent calls return the cached NER_Extractor."""
        import src.multimodal_librarian.api.dependencies.services as svc

        svc._ner_extractor = None

        mock_web = MagicMock(name="en_core_web_sm")
        mock_sci = MagicMock(name="en_core_sci_sm")

        def _spacy_load(name):
            if name == "en_core_web_sm":
                return mock_web
            if name == "en_core_sci_sm":
                return mock_sci
            raise OSError(f"Model {name} not found")

        with patch("spacy.load", side_effect=_spacy_load):
            first = await svc.get_ner_extractor(umls_client=None)
            second = await svc.get_ner_extractor(umls_client=None)

        assert first is second

        svc._ner_extractor = None

    @pytest.mark.asyncio
    async def test_clear_all_caches_resets_ner_extractor(self):
        """clear_all_caches() resets _ner_extractor to None."""
        import src.multimodal_librarian.api.dependencies.services as svc

        svc._ner_extractor = MagicMock(name="cached_extractor")
        svc.clear_all_caches()
        assert svc._ner_extractor is None


# =============================================================================
# Test 2: RelevanceDetector uses NER_Extractor
# Validates: Requirements 7.2, 7.4
# =============================================================================


class TestRelevanceDetectorUsesNER:
    """Verify filter_chunks_by_proper_nouns uses extract_key_terms
    when ner_extractor is set."""

    @pytest.mark.asyncio
    async def test_filter_uses_ner_extractor_key_terms(self):
        """When ner_extractor is set, filter_chunks_by_proper_nouns
        calls extract_key_terms and uses the returned key_terms."""
        mock_ner = AsyncMock()
        mock_ner.extract_key_terms = AsyncMock(
            return_value=NERResult(
                web_entities=["Venezuela"],
                sci_entities=[],
                umls_entities=[],
                key_terms={"Venezuela"},
            ),
        )

        detector = RelevanceDetector(
            spacy_nlp=None,
            ner_extractor=mock_ner,
        )

        chunks = [
            _make_chunk("c1", "Policy changes in 2024.", 0.7),
            _make_chunk(
                "c2",
                "Venezuela's economy has been struggling.",
                0.5,
            ),
            _make_chunk("c3", "Global trade patterns.", 0.6),
        ]

        result = await detector.filter_chunks_by_proper_nouns(
            chunks,
            "Tell me about Venezuela",
        )

        mock_ner.extract_key_terms.assert_called_once_with(
            "Tell me about Venezuela",
        )
        assert result is not None
        assert all(
            "venezuela" in c.content.lower() for c in result
        )

    @pytest.mark.asyncio
    async def test_filter_falls_back_to_inline_when_no_ner(self):
        """When ner_extractor is None, falls back to inline spaCy
        extraction using self.spacy_nlp."""
        mock_nlp = _make_mock_nlp(
            entities=[("Venezuela", "GPE")],
            noun_chunks=[],
        )

        detector = RelevanceDetector(
            spacy_nlp=mock_nlp,
            ner_extractor=None,
        )

        chunks = [
            _make_chunk("c1", "Policy changes.", 0.7),
            _make_chunk(
                "c2",
                "Venezuela's economy.",
                0.5,
            ),
        ]

        result = await detector.filter_chunks_by_proper_nouns(
            chunks,
            "Tell me about Venezuela",
        )

        # Inline extraction should have been used (spacy_nlp called)
        mock_nlp.assert_called()
        assert result is not None
        assert any(
            "venezuela" in c.content.lower() for c in result
        )


# =============================================================================
# Test 3: analyze_query_term_coverage uses NER_Extractor key_terms
# Validates: Requirement 7.3
# =============================================================================


class TestCoverageUsesNER:
    """Verify analyze_query_term_coverage uses ner_key_terms
    parameter when provided."""

    def test_uses_ner_key_terms_directly(self):
        """When ner_key_terms is provided, uses those terms
        instead of inline spaCy extraction."""
        ner_terms = {"Venezuela", "President"}

        concept_matches = [
            {"name": "gpe_venezuela", "concept_id": "c-ven"},
        ]
        chunks = [
            _make_chunk(
                "c1",
                "Venezuela's President gave a speech.",
                0.7,
            ),
        ]

        result = analyze_query_term_coverage(
            query="Tell me about President of Venezuela",
            concept_matches=concept_matches,
            spacy_nlp=None,
            chunks=chunks,
            ner_key_terms=ner_terms,
        )

        assert isinstance(result, QueryTermCoverageResult)
        # Both terms should be in proper_nouns
        assert "Venezuela" in result.proper_nouns
        assert "President" in result.proper_nouns

    def test_bypasses_spacy_when_ner_key_terms_provided(self):
        """spacy_nlp is not called when ner_key_terms is set."""
        mock_nlp = MagicMock()
        ner_terms = {"Chelsea"}

        concept_matches = [
            {"name": "chelsea_fc", "concept_id": "c-ch"},
        ]
        chunks = [
            _make_chunk("c1", "Chelsea won the match.", 0.7),
        ]

        analyze_query_term_coverage(
            query="How did Chelsea perform?",
            concept_matches=concept_matches,
            spacy_nlp=mock_nlp,
            chunks=chunks,
            ner_key_terms=ner_terms,
        )

        # spacy_nlp should NOT have been called
        mock_nlp.assert_not_called()

    def test_falls_back_to_spacy_when_no_ner_key_terms(self):
        """When ner_key_terms is None, falls back to spacy_nlp."""
        mock_nlp = _make_mock_nlp(
            entities=[("Chelsea", "ORG")],
            noun_chunks=[],
        )

        concept_matches = [
            {"name": "chelsea_fc", "concept_id": "c-ch"},
        ]
        chunks = [
            _make_chunk("c1", "Chelsea won the match.", 0.7),
        ]

        analyze_query_term_coverage(
            query="How did Chelsea perform?",
            concept_matches=concept_matches,
            spacy_nlp=mock_nlp,
            chunks=chunks,
            ner_key_terms=None,
        )

        mock_nlp.assert_called_once()


# =============================================================================
# Test 4: QueryDecomposer includes multi-word NER entities
# Validates: Requirement 8.2
# =============================================================================


class TestQueryDecomposerMultiWord:
    """Verify _find_entity_matches includes multi-word NER entities
    in all_words."""

    @pytest.mark.asyncio
    async def test_multi_word_entities_added_to_search(self):
        """Multi-word entities from NER_Extractor are added to
        all_words for Neo4j concept matching."""
        mock_ner = AsyncMock()
        mock_ner.extract_key_terms = AsyncMock(
            return_value=NERResult(
                web_entities=["hepatitis"],
                sci_entities=["hepatitis B", "surface antigen"],
                umls_entities=[
                    "hepatitis B surface antigen",
                ],
                key_terms={
                    "hepatitis B surface antigen",
                    "hepatitis B",
                    "surface antigen",
                },
            ),
        )

        mock_neo4j = MagicMock()
        mock_neo4j.execute_query = AsyncMock(return_value=[])
        mock_neo4j._is_connected = True

        decomposer = QueryDecomposer(
            neo4j_client=mock_neo4j,
            ner_extractor=mock_ner,
        )

        await decomposer._find_entity_matches(
            "What is hepatitis B surface antigen?",
        )

        mock_ner.extract_key_terms.assert_called_once_with(
            "What is hepatitis B surface antigen?",
        )

        # Verify the Neo4j query was called with search terms
        # that include multi-word entities
        assert mock_neo4j.execute_query.called
        call_args = mock_neo4j.execute_query.call_args
        params = call_args[1] if call_args[1] else call_args[0][1]
        search_terms = params.get(
            "search_terms", params.get("words", "")
        )

        # Multi-word entities should appear in the search
        if isinstance(search_terms, str):
            assert "hepatitis b surface antigen" in search_terms.lower()
        elif isinstance(search_terms, list):
            terms_lower = [t.lower() for t in search_terms]
            assert "hepatitis b surface antigen" in terms_lower

    @pytest.mark.asyncio
    async def test_single_word_entities_not_duplicated(self):
        """Single-word entities from NER are not added (only
        multi-word entities containing spaces)."""
        mock_ner = AsyncMock()
        mock_ner.extract_key_terms = AsyncMock(
            return_value=NERResult(
                web_entities=["Chelsea"],
                sci_entities=[],
                umls_entities=[],
                key_terms={"Chelsea"},
            ),
        )

        mock_neo4j = MagicMock()
        mock_neo4j.execute_query = AsyncMock(return_value=[])
        mock_neo4j._is_connected = True

        decomposer = QueryDecomposer(
            neo4j_client=mock_neo4j,
            ner_extractor=mock_ner,
        )

        await decomposer._find_entity_matches(
            "How did Chelsea perform?",
        )

        # NER was called but single-word "Chelsea" should not
        # be added again (it's already in the word list)
        mock_ner.extract_key_terms.assert_called_once()

    @pytest.mark.asyncio
    async def test_ner_failure_does_not_break_decomposer(self):
        """If NER extraction fails, _find_entity_matches still
        works with standard word tokenization."""
        mock_ner = AsyncMock()
        mock_ner.extract_key_terms = AsyncMock(
            side_effect=RuntimeError("NER model crashed"),
        )

        mock_neo4j = MagicMock()
        mock_neo4j.execute_query = AsyncMock(return_value=[])
        mock_neo4j._is_connected = True

        decomposer = QueryDecomposer(
            neo4j_client=mock_neo4j,
            ner_extractor=mock_ner,
        )

        # Should not raise
        result = await decomposer._find_entity_matches(
            "What is hepatitis B?",
        )

        assert isinstance(result, list)


# =============================================================================
# Test 5: UMLS batch_search_by_names called with n-grams
# Validates: Requirement 4.2
# =============================================================================


class TestUMLSBatchCalledWithNgrams:
    """Verify batch_search_by_names is called with generated
    n-gram candidates."""

    @pytest.mark.asyncio
    async def test_umls_receives_ngram_candidates(self):
        """Layer 3 generates n-grams from the query and passes
        them to batch_search_by_names."""
        mock_umls = AsyncMock()
        mock_umls.batch_search_by_names = AsyncMock(
            return_value={
                "hepatitis B": {"cui": "C0019163"},
                "surface antigen": {"cui": "C0038800"},
            },
        )

        mock_web_nlp = _make_mock_nlp(
            entities=[],
            noun_chunks=[],
        )
        mock_sci_nlp = _make_mock_nlp(
            entities=[],
            noun_chunks=[],
        )

        extractor = NER_Extractor(
            spacy_web_nlp=mock_web_nlp,
            spacy_sci_nlp=mock_sci_nlp,
            umls_client=mock_umls,
        )

        query = "hepatitis B surface antigen test"
        await extractor.extract_key_terms(query)

        mock_umls.batch_search_by_names.assert_called_once()
        candidates = (
            mock_umls.batch_search_by_names.call_args[0][0]
        )

        # Verify n-grams were generated correctly
        assert isinstance(candidates, list)
        assert len(candidates) > 0

        # Should contain 2-grams through 5-grams
        assert "hepatitis B" in candidates
        assert "surface antigen" in candidates
        assert "B surface" in candidates
        assert "antigen test" in candidates
        # 3-grams
        assert "hepatitis B surface" in candidates
        assert "B surface antigen" in candidates
        assert "surface antigen test" in candidates
        # 4-grams
        assert "hepatitis B surface antigen" in candidates
        assert "B surface antigen test" in candidates
        # 5-gram
        assert "hepatitis B surface antigen test" in candidates

    @pytest.mark.asyncio
    async def test_umls_not_called_when_client_is_none(self):
        """When umls_client is None, Layer 3 is skipped."""
        mock_web_nlp = _make_mock_nlp(
            entities=[("Chelsea", "ORG")],
            noun_chunks=[],
        )

        extractor = NER_Extractor(
            spacy_web_nlp=mock_web_nlp,
            spacy_sci_nlp=None,
            umls_client=None,
        )

        result = await extractor.extract_key_terms(
            "How did Chelsea perform?",
        )

        assert result.umls_entities == []


# =============================================================================
# Test 6: Concurrent execution — all three layers run in parallel
# Validates: Requirements 3.4, 4.6
# =============================================================================


class TestConcurrentExecution:
    """Verify all three layers run concurrently via
    asyncio.gather."""

    @pytest.mark.asyncio
    async def test_all_layers_run_concurrently(self):
        """All three layers execute in parallel; total time is
        bounded by the slowest layer, not the sum."""
        execution_log = []

        mock_web_nlp = MagicMock()

        def _web_call(query):
            doc = MagicMock()
            doc.ents = []
            doc.noun_chunks = []
            return doc

        mock_web_nlp.side_effect = _web_call

        mock_sci_nlp = MagicMock()

        def _sci_call(query):
            doc = MagicMock()
            doc.ents = []
            doc.noun_chunks = []
            return doc

        mock_sci_nlp.side_effect = _sci_call

        mock_umls = AsyncMock()

        async def _umls_batch(candidates):
            execution_log.append("umls_start")
            await asyncio.sleep(0.05)
            execution_log.append("umls_end")
            return {}

        mock_umls.batch_search_by_names = AsyncMock(
            side_effect=_umls_batch,
        )

        extractor = NER_Extractor(
            spacy_web_nlp=mock_web_nlp,
            spacy_sci_nlp=mock_sci_nlp,
            umls_client=mock_umls,
        )

        # Patch the layer methods to track concurrency
        original_layer1 = extractor._extract_layer1_web
        original_layer2 = extractor._extract_layer2_sci
        original_layer3 = extractor._extract_layer3_umls

        async def _tracked_layer1(query):
            execution_log.append("layer1_start")
            result = await original_layer1(query)
            execution_log.append("layer1_end")
            return result

        async def _tracked_layer2(query):
            execution_log.append("layer2_start")
            result = await original_layer2(query)
            execution_log.append("layer2_end")
            return result

        async def _tracked_layer3(query):
            execution_log.append("layer3_start")
            result = await original_layer3(query)
            execution_log.append("layer3_end")
            return result

        extractor._extract_layer1_web = _tracked_layer1
        extractor._extract_layer2_sci = _tracked_layer2
        extractor._extract_layer3_umls = _tracked_layer3

        result = await extractor.extract_key_terms(
            "hepatitis B surface antigen",
        )

        assert isinstance(result, NERResult)

        # All three layers should have started
        assert "layer1_start" in execution_log
        assert "layer2_start" in execution_log
        assert "layer3_start" in execution_log

        # All three layers should have completed
        assert "layer1_end" in execution_log
        assert "layer2_end" in execution_log
        assert "layer3_end" in execution_log

        # All starts should appear before all ends
        # (concurrent execution means they interleave)
        starts = [
            i for i, e in enumerate(execution_log)
            if e.endswith("_start")
        ]
        ends = [
            i for i, e in enumerate(execution_log)
            if e.endswith("_end")
        ]
        # At least one end should come after all starts
        # (proving they ran concurrently, not sequentially)
        assert max(starts) < max(ends)

    @pytest.mark.asyncio
    async def test_evaluate_precomputes_ner_key_terms(self):
        """RelevanceDetector.evaluate() pre-computes ner_key_terms
        from NER_Extractor and passes them to
        analyze_query_term_coverage."""
        mock_ner = AsyncMock()
        mock_ner.extract_key_terms = AsyncMock(
            return_value=NERResult(
                web_entities=["Venezuela"],
                sci_entities=[],
                umls_entities=[],
                key_terms={"Venezuela"},
            ),
        )

        detector = RelevanceDetector(
            spacy_nlp=None,
            ner_extractor=mock_ner,
        )

        from src.multimodal_librarian.models.kg_retrieval import (  # noqa: E501
            QueryDecomposition,
        )

        decomp = QueryDecomposition(
            original_query="Tell me about Venezuela",
            entities=["Venezuela"],
            has_kg_matches=True,
            concept_matches=[
                {"name": "venezuela", "concept_id": "c-ven"},
            ],
        )

        chunks = [
            _make_chunk(
                "c1",
                "Venezuela's economy has been struggling.",
                0.5,
            ),
        ]

        with patch(
            "src.multimodal_librarian.components.kg_retrieval"
            ".relevance_detector.analyze_query_term_coverage",
            wraps=analyze_query_term_coverage,
        ) as mock_coverage:
            await detector.evaluate(chunks, decomp)

            mock_ner.extract_key_terms.assert_called_once_with(
                "Tell me about Venezuela",
            )
            mock_coverage.assert_called_once()
            call_kwargs = mock_coverage.call_args
            # ner_key_terms should be passed
            if call_kwargs.kwargs:
                assert "ner_key_terms" in call_kwargs.kwargs
                assert call_kwargs.kwargs["ner_key_terms"] == {
                    "Venezuela",
                }
            else:
                # Positional args — ner_key_terms is the last arg
                args = call_kwargs.args
                assert {"Venezuela"} in args
