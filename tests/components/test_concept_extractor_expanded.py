"""
Tests for expanded concept extraction: PMI collocation detection.

Tests the _extract_collocations_pmi method on ConceptExtractor.
"""

import math
from collections import Counter

import pytest

from src.multimodal_librarian.components.knowledge_graph.kg_builder import (
    ConceptExtractor,
)
from src.multimodal_librarian.models.knowledge_graph import ConceptNode


class TestExtractCollocationsPMI:
    """Tests for _extract_collocations_pmi method."""

    @pytest.fixture
    def extractor(self):
        """Create a ConceptExtractor instance."""
        return ConceptExtractor()

    def test_returns_empty_for_short_text(self, extractor):
        """Text shorter than 10 words returns empty list."""
        short_text = "hello world foo bar"
        result = extractor._extract_collocations_pmi(short_text)
        assert result == []

    def test_returns_empty_for_exactly_nine_words(self, extractor):
        """Text with exactly 9 words returns empty list."""
        text = "one two three four five six seven eight nine"
        result = extractor._extract_collocations_pmi(text)
        assert result == []

    def test_returns_empty_when_no_bigram_meets_threshold(self, extractor):
        """When no bigram has PMI above threshold, returns empty."""
        # All unique words — no repeated bigrams
        text = "alpha beta gamma delta epsilon zeta eta theta iota kappa"
        result = extractor._extract_collocations_pmi(text)
        assert result == []

    def test_requires_minimum_two_occurrences(self, extractor):
        """Bigrams appearing only once are excluded."""
        # "knowledge graph" appears once, padded with filler
        text = (
            "knowledge graph lorem ipsum dolor sit amet "
            "consectetur adipiscing elit sed"
        )
        result = extractor._extract_collocations_pmi(text)
        # Should be empty since "knowledge graph" only appears once
        assert all(
            c.concept_name != "knowledge graph" for c in result
        )

    def test_extracts_high_pmi_bigram(self, extractor):
        """A bigram appearing multiple times with high PMI is extracted."""
        # Construct text where "quantum computing" appears 3 times
        # among enough filler to make it statistically significant
        filler = " ".join(
            f"word{i}" for i in range(30)
        )
        text = (
            f"quantum computing {filler} "
            f"quantum computing {filler} "
            f"quantum computing {filler}"
        )
        result = extractor._extract_collocations_pmi(text)
        names = [c.concept_name for c in result]
        assert "quantum computing" in names

    def test_concept_type_is_multi_word(self, extractor):
        """Extracted concepts have concept_type MULTI_WORD."""
        filler = " ".join(f"word{i}" for i in range(30))
        text = (
            f"quantum computing {filler} "
            f"quantum computing {filler} "
            f"quantum computing {filler}"
        )
        result = extractor._extract_collocations_pmi(text)
        for concept in result:
            assert concept.concept_type == "MULTI_WORD"

    def test_confidence_uses_settings_base(self, extractor):
        """Confidence starts at multi_word_pmi_confidence from settings."""
        base = getattr(
            extractor.settings, 'multi_word_pmi_confidence', 0.65
        )
        filler = " ".join(f"word{i}" for i in range(30))
        text = (
            f"quantum computing {filler} "
            f"quantum computing {filler} "
            f"quantum computing {filler}"
        )
        result = extractor._extract_collocations_pmi(text)
        for concept in result:
            assert concept.confidence >= base

    def test_confidence_increases_with_frequency(self, extractor):
        """More occurrences yield higher confidence (frequency boost)."""
        base = getattr(
            extractor.settings, 'multi_word_pmi_confidence', 0.65
        )
        # 4 occurrences → boost = min(0.1, (4-2)*0.02) = 0.04
        filler = " ".join(f"word{i}" for i in range(30))
        text = " ".join(
            [f"quantum computing {filler}"] * 4
        )
        result = extractor._extract_collocations_pmi(text)
        qc = [c for c in result if c.concept_name == "quantum computing"]
        if qc:
            assert qc[0].confidence >= base + 0.04

    def test_confidence_boost_capped_at_0_1(self, extractor):
        """Frequency boost is capped at 0.1."""
        base = getattr(
            extractor.settings, 'multi_word_pmi_confidence', 0.65
        )
        # Many occurrences — boost should cap at 0.1
        filler = " ".join(f"word{i}" for i in range(20))
        text = " ".join(
            [f"quantum computing {filler}"] * 20
        )
        result = extractor._extract_collocations_pmi(text)
        for concept in result:
            assert concept.confidence <= base + 0.1

    def test_filters_stopword_bigrams(self, extractor):
        """Bigrams containing stopwords are excluded."""
        # "for the" is a stopword-only bigram
        text = (
            "for the record for the record for the record "
            "alpha beta gamma delta epsilon zeta eta theta"
        )
        result = extractor._extract_collocations_pmi(text)
        names = [c.concept_name for c in result]
        assert "for the" not in names

    def test_filters_bigram_with_one_stopword(self, extractor):
        """Bigrams where either word is a stopword are excluded."""
        # "learning the" — "the" is a stopword
        text = (
            "learning the basics learning the basics "
            "learning the basics alpha beta gamma delta "
            "epsilon zeta eta theta"
        )
        result = extractor._extract_collocations_pmi(text)
        names = [c.concept_name for c in result]
        assert "learning the" not in names

    def test_concept_id_format(self, extractor):
        """Concept IDs follow multi_word_{normalized} format."""
        filler = " ".join(f"word{i}" for i in range(30))
        text = (
            f"quantum computing {filler} "
            f"quantum computing {filler} "
            f"quantum computing {filler}"
        )
        result = extractor._extract_collocations_pmi(text)
        for concept in result:
            assert concept.concept_id.startswith("multi_word_")

    def test_source_chunks_is_empty_list(self, extractor):
        """Extracted concepts have empty source_chunks."""
        filler = " ".join(f"word{i}" for i in range(30))
        text = (
            f"quantum computing {filler} "
            f"quantum computing {filler} "
            f"quantum computing {filler}"
        )
        result = extractor._extract_collocations_pmi(text)
        for concept in result:
            assert concept.source_chunks == []

    def test_returns_valid_concept_nodes(self, extractor):
        """All returned objects are valid ConceptNode instances."""
        filler = " ".join(f"word{i}" for i in range(30))
        text = (
            f"quantum computing {filler} "
            f"quantum computing {filler} "
            f"quantum computing {filler}"
        )
        result = extractor._extract_collocations_pmi(text)
        for concept in result:
            assert isinstance(concept, ConceptNode)
            assert concept.validate()

    def test_text_is_lowercased(self, extractor):
        """PMI operates on lowercased text; concept names are lowercase."""
        filler = " ".join(f"word{i}" for i in range(30))
        text = (
            f"Quantum Computing {filler} "
            f"Quantum Computing {filler} "
            f"Quantum Computing {filler}"
        )
        result = extractor._extract_collocations_pmi(text)
        qc = [c for c in result if "quantum" in c.concept_name]
        if qc:
            assert qc[0].concept_name == "quantum computing"

    def test_multiple_distinct_collocations(self, extractor):
        """Multiple distinct high-PMI bigrams are all extracted."""
        filler = " ".join(f"word{i}" for i in range(30))
        text = (
            f"quantum computing neural network {filler} "
            f"quantum computing neural network {filler} "
            f"quantum computing neural network {filler}"
        )
        result = extractor._extract_collocations_pmi(text)
        names = [c.concept_name for c in result]
        assert "quantum computing" in names
        assert "neural network" in names


class TestCollocationCache:
    """Tests for _collocation_cache and _update_collocation_cache."""

    @pytest.fixture
    def extractor(self):
        """Create a ConceptExtractor instance."""
        return ConceptExtractor()

    def test_cache_initialized_empty(self, extractor):
        """Cache starts as an empty dict."""
        assert extractor._collocation_cache == {}

    def test_update_cache_single_document(self, extractor):
        """Updating with one document populates frequency and doc_count."""
        extractor._update_collocation_cache(
            "knowledge graph knowledge graph vector database"
        )
        assert "knowledge_graph" in extractor._collocation_cache
        entry = extractor._collocation_cache["knowledge_graph"]
        assert entry["frequency"] == 2
        assert entry["doc_count"] == 1

    def test_update_cache_increments_doc_count(self, extractor):
        """A second document increments doc_count for shared bigrams."""
        extractor._update_collocation_cache("knowledge graph foo bar")
        extractor._update_collocation_cache("knowledge graph baz qux")
        entry = extractor._collocation_cache["knowledge_graph"]
        assert entry["frequency"] == 2  # 1 + 1
        assert entry["doc_count"] == 2

    def test_update_cache_accumulates_frequency(self, extractor):
        """Frequency accumulates across documents."""
        extractor._update_collocation_cache(
            "knowledge graph knowledge graph"
        )
        extractor._update_collocation_cache(
            "knowledge graph knowledge graph knowledge graph"
        )
        entry = extractor._collocation_cache["knowledge_graph"]
        # doc1: 2 bigrams, doc2: 3 bigrams → total 5
        assert entry["frequency"] == 5
        assert entry["doc_count"] == 2

    def test_update_cache_skips_single_word(self, extractor):
        """Text with fewer than 2 words is skipped."""
        extractor._update_collocation_cache("single")
        assert extractor._collocation_cache == {}

    def test_update_cache_skips_empty_string(self, extractor):
        """Empty text is skipped."""
        extractor._update_collocation_cache("")
        assert extractor._collocation_cache == {}

    def test_cache_keys_are_lowercased(self, extractor):
        """Cache keys use lowercased words."""
        extractor._update_collocation_cache("Knowledge Graph foo bar")
        assert "knowledge_graph" in extractor._collocation_cache

    def test_doc_count_incremented_once_per_document(self, extractor):
        """Even if a bigram appears many times, doc_count += 1 per call."""
        extractor._update_collocation_cache(
            "ab cd ab cd ab cd ab cd ab cd"
        )
        entry = extractor._collocation_cache["ab_cd"]
        assert entry["doc_count"] == 1
        assert entry["frequency"] >= 4

    def test_pmi_uses_corpus_cache_when_populated(self, extractor):
        """_extract_collocations_pmi uses corpus cache when available."""
        # Build a text where "quantum computing" is a strong collocation
        # and populate the cache with the same text so corpus stats match
        filler = " ".join(f"word{i}" for i in range(30))
        base_text = (
            f"quantum computing {filler} "
            f"quantum computing {filler} "
            f"quantum computing {filler}"
        )
        # Populate cache with multiple documents of the same shape
        for _ in range(3):
            extractor._update_collocation_cache(base_text)

        # Run PMI on the same text — corpus cache is now populated
        result = extractor._extract_collocations_pmi(base_text)
        names = [c.concept_name for c in result]
        assert "quantum computing" in names

    def test_pmi_falls_back_to_document_level_with_empty_cache(
        self, extractor
    ):
        """With empty cache, PMI uses document-level frequencies."""
        filler = " ".join(f"word{i}" for i in range(30))
        text = (
            f"quantum computing {filler} "
            f"quantum computing {filler} "
            f"quantum computing {filler}"
        )
        result = extractor._extract_collocations_pmi(text)
        names = [c.concept_name for c in result]
        assert "quantum computing" in names


class TestLinkAcronymExpansions:
    """Tests for _link_acronym_expansions method."""

    @pytest.fixture
    def extractor(self):
        """Create a ConceptExtractor instance."""
        return ConceptExtractor()

    def _make_concept(self, concept_id, name, concept_type="ACRONYM"):
        return ConceptNode(
            concept_id=concept_id,
            concept_name=name,
            concept_type=concept_type,
            confidence=0.7,
        )

    def test_expansion_first_pattern_links_acronym(self, extractor):
        """'Expanded Form (ACRONYM)' adds expansion as alias on acronym concept."""
        text = "Natural Language Processing (NLP) is important."
        acr = self._make_concept("acronym_nlp", "NLP", "ACRONYM")
        concepts = [acr]
        id_map = {"acronym_nlp": acr}
        extractor._link_acronym_expansions(text, concepts, id_map)
        assert "Natural Language Processing" in acr.aliases

    def test_expansion_first_pattern_links_expansion(self, extractor):
        """'Expanded Form (ACRONYM)' adds acronym as alias on expansion concept."""
        text = "Natural Language Processing (NLP) is important."
        exp = self._make_concept(
            "entity_natural_language_processing",
            "Natural Language Processing",
            "ENTITY",
        )
        concepts = [exp]
        id_map = {"entity_natural_language_processing": exp}
        extractor._link_acronym_expansions(text, concepts, id_map)
        assert "NLP" in exp.aliases

    def test_acronym_first_pattern_links_acronym(self, extractor):
        """'ACRONYM (Expanded Form)' adds expansion as alias on acronym concept."""
        text = "NLP (Natural Language Processing) is widely used."
        acr = self._make_concept("acronym_nlp", "NLP", "ACRONYM")
        concepts = [acr]
        id_map = {"acronym_nlp": acr}
        extractor._link_acronym_expansions(text, concepts, id_map)
        assert "Natural Language Processing" in acr.aliases

    def test_acronym_first_pattern_links_expansion(self, extractor):
        """'ACRONYM (Expanded Form)' adds acronym as alias on expansion concept."""
        text = "NLP (Natural Language Processing) is widely used."
        exp = self._make_concept(
            "entity_natural_language_processing",
            "Natural Language Processing",
            "ENTITY",
        )
        concepts = [exp]
        id_map = {"entity_natural_language_processing": exp}
        extractor._link_acronym_expansions(text, concepts, id_map)
        assert "NLP" in exp.aliases

    def test_both_concepts_linked_bidirectionally(self, extractor):
        """When both acronym and expansion exist, both get aliases."""
        text = "Natural Language Processing (NLP) is a field."
        acr = self._make_concept("acronym_nlp", "NLP", "ACRONYM")
        exp = self._make_concept(
            "entity_natural_language_processing",
            "Natural Language Processing",
            "ENTITY",
        )
        concepts = [acr, exp]
        id_map = {
            "acronym_nlp": acr,
            "entity_natural_language_processing": exp,
        }
        extractor._link_acronym_expansions(text, concepts, id_map)
        assert "Natural Language Processing" in acr.aliases
        assert "NLP" in exp.aliases

    def test_skips_stopword_acronyms(self, extractor):
        """Stopword acronyms like 'IT' are not linked."""
        text = "Information Technology (IT) is everywhere."
        acr = self._make_concept("acronym_it", "IT", "ACRONYM")
        concepts = [acr]
        id_map = {"acronym_it": acr}
        extractor._link_acronym_expansions(text, concepts, id_map)
        assert acr.aliases == []

    def test_skips_when_neither_concept_exists(self, extractor):
        """When neither acronym nor expansion is in the map, nothing happens."""
        text = "Natural Language Processing (NLP) is important."
        concepts = []
        id_map = {}
        # Should not raise
        extractor._link_acronym_expansions(text, concepts, id_map)

    def test_no_duplicate_aliases(self, extractor):
        """Calling twice with same text doesn't duplicate aliases."""
        text = "Natural Language Processing (NLP) is important."
        acr = self._make_concept("acronym_nlp", "NLP", "ACRONYM")
        concepts = [acr]
        id_map = {"acronym_nlp": acr}
        extractor._link_acronym_expansions(text, concepts, id_map)
        extractor._link_acronym_expansions(text, concepts, id_map)
        assert acr.aliases.count("Natural Language Processing") == 1

    def test_multiple_acronym_patterns_in_same_text(self, extractor):
        """Multiple acronym-expansion pairs in one text are all linked."""
        text = (
            "Natural Language Processing (NLP) and "
            "Knowledge Graph (KG) are related."
        )
        acr_nlp = self._make_concept("acronym_nlp", "NLP", "ACRONYM")
        acr_kg = self._make_concept("acronym_kg", "KG", "ACRONYM")
        concepts = [acr_nlp, acr_kg]
        id_map = {"acronym_nlp": acr_nlp, "acronym_kg": acr_kg}
        extractor._link_acronym_expansions(text, concepts, id_map)
        assert "Natural Language Processing" in acr_nlp.aliases
        assert "Knowledge Graph" in acr_kg.aliases

    def test_multi_word_expansion_concept_lookup(self, extractor):
        """Expansion concepts stored under multi_word_ prefix are found."""
        text = "Machine Learning (ML) is powerful."
        exp = self._make_concept(
            "multi_word_machine_learning",
            "Machine Learning",
            "MULTI_WORD",
        )
        concepts = [exp]
        id_map = {"multi_word_machine_learning": exp}
        extractor._link_acronym_expansions(text, concepts, id_map)
        assert "ML" in exp.aliases

    def test_empty_text_does_nothing(self, extractor):
        """Empty text produces no errors and no aliases."""
        acr = self._make_concept("acronym_nlp", "NLP", "ACRONYM")
        concepts = [acr]
        id_map = {"acronym_nlp": acr}
        extractor._link_acronym_expansions("", concepts, id_map)
        assert acr.aliases == []
