"""
Tests for ConceptExtractor._extract_cross_references method.

Validates: Requirement 5.1 — cross-reference relationship extraction.
"""

import pytest

from multimodal_librarian.components.knowledge_graph.kg_builder import ConceptExtractor
from multimodal_librarian.models.kg_retrieval import CrossReference


@pytest.fixture
def extractor():
    return ConceptExtractor()


CHUNK_ID = "chunk-001"


class TestExplicitReferences:
    """Explicit patterns: 'see Section X', 'refer to Chapter Y'."""

    def test_see_section(self, extractor):
        text = "For details, see Section 3.1 for more info."
        refs = extractor._extract_cross_references(text, CHUNK_ID)
        assert len(refs) == 1
        ref = refs[0]
        assert ref.reference_type == "explicit"
        assert ref.target_type == "section"
        assert ref.target_label == "3.1"
        assert ref.source_chunk_id == CHUNK_ID

    def test_refer_to_chapter(self, extractor):
        text = "Please refer to Chapter 4 for background."
        refs = extractor._extract_cross_references(text, CHUNK_ID)
        assert len(refs) == 1
        assert refs[0].reference_type == "explicit"
        assert refs[0].target_type == "chapter"
        assert refs[0].target_label == "4"

    def test_see_figure(self, extractor):
        text = "See Figure 12 for the diagram."
        refs = extractor._extract_cross_references(text, CHUNK_ID)
        assert len(refs) == 1
        assert refs[0].target_type == "figure"
        assert refs[0].target_label == "12"

    def test_see_table(self, extractor):
        text = "see Table 2.3 for the results."
        refs = extractor._extract_cross_references(text, CHUNK_ID)
        assert len(refs) == 1
        assert refs[0].target_type == "table"
        assert refs[0].target_label == "2.3"

    def test_see_page(self, extractor):
        text = "see Page 42 for the appendix."
        refs = extractor._extract_cross_references(text, CHUNK_ID)
        assert len(refs) == 1
        assert refs[0].target_type == "page"
        assert refs[0].target_label == "42"


class TestBackwardReferences:
    """Backward patterns: 'as discussed in Section X'."""

    def test_as_discussed_in_section(self, extractor):
        text = "As discussed in Section 2.1, the model works."
        refs = extractor._extract_cross_references(text, CHUNK_ID)
        assert len(refs) == 1
        ref = refs[0]
        assert ref.reference_type == "backward"
        assert ref.target_type == "section"
        assert ref.target_label == "2.1"

    def test_as_mentioned_in_chapter(self, extractor):
        text = "as mentioned in Chapter 3, we proceed."
        refs = extractor._extract_cross_references(text, CHUNK_ID)
        assert len(refs) == 1
        assert refs[0].reference_type == "backward"
        assert refs[0].target_type == "chapter"
        assert refs[0].target_label == "3"

    def test_as_shown_in_figure(self, extractor):
        text = "As shown in Figure 7.2, the trend is clear."
        refs = extractor._extract_cross_references(text, CHUNK_ID)
        assert len(refs) == 1
        assert refs[0].reference_type == "backward"
        assert refs[0].target_type == "figure"
        assert refs[0].target_label == "7.2"

    def test_as_described_in_table(self, extractor):
        text = "as described in Table 1, the data shows."
        refs = extractor._extract_cross_references(text, CHUNK_ID)
        assert len(refs) == 1
        assert refs[0].reference_type == "backward"
        assert refs[0].target_type == "table"
        assert refs[0].target_label == "1"


class TestPositionalReferences:
    """Positional patterns: 'Section X above/below'."""

    def test_section_above(self, extractor):
        text = "Section 3.1 above explains the concept."
        refs = extractor._extract_cross_references(text, CHUNK_ID)
        assert len(refs) == 1
        ref = refs[0]
        assert ref.reference_type == "positional"
        assert ref.target_type == "section"
        assert ref.target_label == "3.1"

    def test_chapter_below(self, extractor):
        text = "Chapter 4 below covers the details."
        refs = extractor._extract_cross_references(text, CHUNK_ID)
        assert len(refs) == 1
        assert refs[0].reference_type == "positional"
        assert refs[0].target_type == "chapter"
        assert refs[0].target_label == "4"

    def test_section_earlier(self, extractor):
        text = "Section 1.2 earlier introduced the topic."
        refs = extractor._extract_cross_references(text, CHUNK_ID)
        assert len(refs) == 1
        assert refs[0].reference_type == "positional"
        assert refs[0].target_label == "1.2"

    def test_table_later(self, extractor):
        text = "Table 5 later summarizes the findings."
        refs = extractor._extract_cross_references(text, CHUNK_ID)
        assert len(refs) == 1
        assert refs[0].reference_type == "positional"
        assert refs[0].target_label == "5"


class TestMultipleReferences:
    """Multiple references in the same text."""

    def test_two_explicit_refs(self, extractor):
        text = "See Section 3.1 and refer to Chapter 4."
        refs = extractor._extract_cross_references(text, CHUNK_ID)
        assert len(refs) == 2
        types = {r.reference_type for r in refs}
        assert types == {"explicit"}

    def test_mixed_ref_types(self, extractor):
        text = (
            "See Section 3.1 for details. "
            "As discussed in Chapter 2, the approach works. "
            "Section 5 below has more."
        )
        refs = extractor._extract_cross_references(text, CHUNK_ID)
        assert len(refs) == 3
        ref_types = {r.reference_type for r in refs}
        assert ref_types == {"explicit", "backward", "positional"}


class TestNoReferences:
    """Text with no cross-reference patterns."""

    def test_empty_string(self, extractor):
        refs = extractor._extract_cross_references("", CHUNK_ID)
        assert refs == []

    def test_no_patterns(self, extractor):
        text = "This is a normal paragraph with no references."
        refs = extractor._extract_cross_references(text, CHUNK_ID)
        assert refs == []

    def test_partial_pattern_no_number(self, extractor):
        text = "See the section on methodology."
        refs = extractor._extract_cross_references(text, CHUNK_ID)
        assert refs == []


class TestCaseInsensitivity:
    """Patterns should match regardless of case."""

    def test_uppercase_see(self, extractor):
        text = "SEE SECTION 3.1 for details."
        refs = extractor._extract_cross_references(text, CHUNK_ID)
        assert len(refs) == 1
        assert refs[0].target_type == "section"

    def test_mixed_case_as_discussed(self, extractor):
        text = "As Discussed In Section 2.1, we note."
        refs = extractor._extract_cross_references(text, CHUNK_ID)
        assert len(refs) == 1
        assert refs[0].reference_type == "backward"

    def test_lowercase_chapter_below(self, extractor):
        text = "chapter 4 below covers this."
        refs = extractor._extract_cross_references(text, CHUNK_ID)
        assert len(refs) == 1
        assert refs[0].reference_type == "positional"


class TestCrossReferenceDataclass:
    """Verify CrossReference dataclass fields."""

    def test_raw_text_captured(self, extractor):
        text = "see Section 3.1 for more."
        refs = extractor._extract_cross_references(text, CHUNK_ID)
        assert refs[0].raw_text == "see Section 3.1"

    def test_resolved_chunk_ids_default_none(self, extractor):
        text = "see Section 3.1 for more."
        refs = extractor._extract_cross_references(text, CHUNK_ID)
        assert refs[0].resolved_chunk_ids is None

    def test_returns_crossreference_instances(self, extractor):
        text = "see Section 3.1 for more."
        refs = extractor._extract_cross_references(text, CHUNK_ID)
        assert all(isinstance(r, CrossReference) for r in refs)
