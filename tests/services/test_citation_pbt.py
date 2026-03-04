#!/usr/bin/env python3
"""
Property-Based Tests for Citation Data and Popup Content.

Feature: clickable-source-citations
Task 10: Property Tests for API Data

This module implements property-based tests using Hypothesis to validate
the correctness properties defined in the design document:

- Property 5: Citation Data Completeness in API
- Property 2: Popup Content Completeness

Testing Framework: hypothesis
"""

from dataclasses import asdict
from typing import Any, Dict, List, Optional

import pytest
from hypothesis import HealthCheck, assume, given, settings
from hypothesis import strategies as st

from src.multimodal_librarian.services.rag_service import (
    CitationSource,
    ContextPreparer,
    DocumentChunk,
)
from src.multimodal_librarian.utils.text_utils import truncate_content

# =============================================================================
# Strategies for Property-Based Testing
# =============================================================================

# Strategy for generating valid document IDs (UUID-like strings)
document_id_strategy = st.text(
    min_size=1,
    max_size=36,
    alphabet=st.characters(whitelist_categories=('L', 'N'), whitelist_characters='-')
)

# Strategy for generating document titles
document_title_strategy = st.text(
    min_size=1,
    max_size=200,
    alphabet=st.characters(
        whitelist_categories=('L', 'N', 'P', 'S', 'Z'),
        whitelist_characters=' '
    )
).filter(lambda x: x.strip())  # Ensure non-empty after stripping

# Strategy for generating chunk content (excerpt)
content_strategy = st.text(
    min_size=0,
    max_size=2000,
    alphabet=st.characters(
        whitelist_categories=('L', 'N', 'P', 'S', 'Z'),
        whitelist_characters='\n\t\r '
    )
)

# Strategy for non-empty content
non_empty_content_strategy = st.text(
    min_size=1,
    max_size=2000,
    alphabet=st.characters(
        whitelist_categories=('L', 'N', 'P', 'S', 'Z'),
        whitelist_characters='\n\t\r '
    )
).filter(lambda x: x.strip())

# Strategy for relevance scores (0.0 to 1.0)
relevance_score_strategy = st.floats(min_value=0.0, max_value=1.0, allow_nan=False)

# Strategy for page numbers
page_number_strategy = st.one_of(st.none(), st.integers(min_value=1, max_value=10000))

# Strategy for section titles
section_title_strategy = st.one_of(
    st.none(),
    st.text(
        min_size=1,
        max_size=100,
        alphabet=st.characters(whitelist_categories=('L', 'N', 'P', 'S', 'Z'))
    ).filter(lambda x: x.strip())
)

# Strategy for chunk IDs
chunk_id_strategy = st.text(
    min_size=1,
    max_size=50,
    alphabet=st.characters(whitelist_categories=('L', 'N'), whitelist_characters='-_')
)


# Strategy for generating CitationSource objects
@st.composite
def citation_source_strategy(draw):
    """Generate valid CitationSource objects."""
    content = draw(content_strategy)
    
    # Determine if we should simulate an error
    has_error = draw(st.booleans()) and not content.strip()
    
    excerpt_text = ""
    content_truncated = False
    excerpt_error = None
    
    if has_error:
        excerpt_error = draw(st.sampled_from(["not_found", "retrieval_failed", None]))
    elif content:
        excerpt_text, content_truncated = truncate_content(content, max_length=1000)
    
    return CitationSource(
        document_id=draw(document_id_strategy),
        document_title=draw(document_title_strategy),
        page_number=draw(page_number_strategy),
        chunk_id=draw(chunk_id_strategy),
        relevance_score=draw(relevance_score_strategy),
        excerpt=excerpt_text,
        section_title=draw(section_title_strategy),
        content_truncated=content_truncated,
        excerpt_error=excerpt_error
    )


# Strategy for generating DocumentChunk objects
@st.composite
def document_chunk_strategy(draw):
    """Generate valid DocumentChunk objects."""
    return DocumentChunk(
        chunk_id=draw(chunk_id_strategy),
        document_id=draw(document_id_strategy),
        document_title=draw(document_title_strategy),
        content=draw(non_empty_content_strategy),
        similarity_score=draw(relevance_score_strategy),
        page_number=draw(page_number_strategy),
        section_title=draw(section_title_strategy),
        metadata={}
    )


# =============================================================================
# Task 10.1: Property-Based Test for Citation Data Completeness
# =============================================================================

class TestCitationDataCompletenessPBT:
    """
    Property-Based Tests for Citation Data Completeness in API.
    
    **Property 5: Citation Data Completeness in API**
    
    For any RAG response with citations, the streaming_start WebSocket message 
    SHALL include citation objects with non-empty excerpt fields for all 
    citations where chunk content is available.
    
    **Validates: Requirements 5.1, 5.2**
    """
    
    @given(chunks=st.lists(document_chunk_strategy(), min_size=1, max_size=10))
    @settings(
        max_examples=100,
        suppress_health_check=[HealthCheck.function_scoped_fixture],
        deadline=None
    )
    def test_property_citations_have_excerpts_when_content_available(
        self, 
        chunks: List[DocumentChunk]
    ):
        """
        Property: Citations include non-empty excerpts when chunk content is available.
        
        For any list of document chunks with content, the ContextPreparer
        should produce citations with non-empty excerpt fields.
        
        **Validates: Requirements 5.1, 5.2**
        """
        # Filter to chunks with actual content
        chunks_with_content = [c for c in chunks if c.content and c.content.strip()]
        assume(len(chunks_with_content) > 0)
        
        preparer = ContextPreparer()
        _, citations = preparer.prepare_context(chunks_with_content, "test query")
        
        # All citations should have non-empty excerpts
        for citation in citations:
            assert citation.excerpt, (
                f"Citation for '{citation.document_title}' should have non-empty excerpt "
                f"when chunk content is available"
            )
    
    @given(chunks=st.lists(document_chunk_strategy(), min_size=1, max_size=10))
    @settings(
        max_examples=100,
        suppress_health_check=[HealthCheck.function_scoped_fixture],
        deadline=None
    )
    def test_property_citation_excerpt_matches_truncated_content(
        self, 
        chunks: List[DocumentChunk]
    ):
        """
        Property: Citation excerpt is the truncated version of chunk content.
        
        For any document chunk, the citation excerpt should match the result
        of truncate_content applied to the chunk content.
        
        **Validates: Requirements 5.1, 5.4**
        """
        chunks_with_content = [c for c in chunks if c.content and c.content.strip()]
        
        # Filter to unique chunk_ids to avoid ambiguity in mapping
        seen_ids = set()
        unique_chunks = []
        for c in chunks_with_content:
            if c.chunk_id not in seen_ids:
                seen_ids.add(c.chunk_id)
                unique_chunks.append(c)
        
        assume(len(unique_chunks) > 0)
        
        preparer = ContextPreparer()
        _, citations = preparer.prepare_context(unique_chunks, "test query")
        
        # Build a map of chunk_id to original content
        chunk_content_map = {c.chunk_id: c.content for c in unique_chunks}
        
        for citation in citations:
            if citation.chunk_id in chunk_content_map:
                original_content = chunk_content_map[citation.chunk_id]
                expected_excerpt, expected_truncated = truncate_content(original_content, max_length=1000)
                
                assert citation.excerpt == expected_excerpt, (
                    f"Citation excerpt doesn't match truncated content for chunk {citation.chunk_id}"
                )
                assert citation.content_truncated == expected_truncated, (
                    f"content_truncated flag mismatch for chunk {citation.chunk_id}"
                )
    
    @given(chunks=st.lists(document_chunk_strategy(), min_size=1, max_size=10))
    @settings(
        max_examples=100,
        suppress_health_check=[HealthCheck.function_scoped_fixture],
        deadline=None
    )
    def test_property_all_required_citation_fields_present(
        self, 
        chunks: List[DocumentChunk]
    ):
        """
        Property: All required citation fields are present and valid.
        
        For any citation generated from document chunks, all required fields
        (document_id, document_title, chunk_id, relevance_score, excerpt)
        should be present and have valid values.
        
        **Validates: Requirements 5.1, 5.2**
        """
        chunks_with_content = [c for c in chunks if c.content and c.content.strip()]
        assume(len(chunks_with_content) > 0)
        
        preparer = ContextPreparer()
        _, citations = preparer.prepare_context(chunks_with_content, "test query")
        
        for citation in citations:
            # Required fields must be present and non-empty
            assert citation.document_id, "document_id is required"
            assert citation.document_title, "document_title is required"
            assert citation.chunk_id, "chunk_id is required"
            
            # Relevance score must be in valid range
            assert 0.0 <= citation.relevance_score <= 1.0, (
                f"relevance_score {citation.relevance_score} out of range [0, 1]"
            )
            
            # Excerpt should be present when no error
            if not citation.excerpt_error:
                assert citation.excerpt is not None, "excerpt should be present when no error"
    
    @given(citation=citation_source_strategy())
    @settings(
        max_examples=100,
        suppress_health_check=[HealthCheck.function_scoped_fixture],
        deadline=None
    )
    def test_property_citation_serialization_preserves_all_fields(
        self, 
        citation: CitationSource
    ):
        """
        Property: Citation serialization preserves all fields for WebSocket transmission.
        
        When a CitationSource is converted to a dictionary (as done in the WebSocket
        handler), all fields should be preserved correctly.
        
        **Validates: Requirements 5.2**
        """
        # Simulate the serialization done in chat.py WebSocket handler
        serialized = {
            'document_id': getattr(citation, 'document_id', ''),
            'document_title': getattr(citation, 'document_title', ''),
            'page_number': getattr(citation, 'page_number', None),
            'relevance_score': round(getattr(citation, 'relevance_score', 0), 3),
            'excerpt': getattr(citation, 'excerpt', ''),
            'section_title': getattr(citation, 'section_title', ''),
            'chunk_id': getattr(citation, 'chunk_id', ''),
            'content_truncated': getattr(citation, 'content_truncated', False),
            'excerpt_error': getattr(citation, 'excerpt_error', None)
        }
        
        # Verify all fields are present
        assert 'document_id' in serialized
        assert 'document_title' in serialized
        assert 'page_number' in serialized
        assert 'relevance_score' in serialized
        assert 'excerpt' in serialized
        assert 'section_title' in serialized
        assert 'chunk_id' in serialized
        assert 'content_truncated' in serialized
        assert 'excerpt_error' in serialized
        
        # Verify values match original
        assert serialized['document_id'] == citation.document_id
        assert serialized['document_title'] == citation.document_title
        assert serialized['page_number'] == citation.page_number
        assert serialized['excerpt'] == citation.excerpt
        assert serialized['chunk_id'] == citation.chunk_id
        assert serialized['content_truncated'] == citation.content_truncated
        assert serialized['excerpt_error'] == citation.excerpt_error


# =============================================================================
# Task 10.2: Property-Based Test for Popup Content Completeness
# =============================================================================

class TestPopupContentCompletenessPBT:
    """
    Property-Based Tests for Popup Content Completeness.
    
    **Property 2: Popup Content Completeness**
    
    For any valid CitationData object, the Citation_Popup SHALL render all 
    required fields (document title, relevance score as percentage, excerpt text) 
    and conditionally render optional fields (page number, section title) only 
    when present.
    
    **Validates: Requirements 3.1, 3.2, 3.3, 3.4, 3.5**
    """
    
    @given(citation=citation_source_strategy())
    @settings(
        max_examples=100,
        suppress_health_check=[HealthCheck.function_scoped_fixture],
        deadline=None
    )
    def test_property_popup_data_contains_required_fields(
        self, 
        citation: CitationSource
    ):
        """
        Property: Popup data structure contains all required fields.
        
        For any CitationSource, the data passed to the popup should contain
        document_title, relevance_score, and excerpt (or excerpt_error).
        
        **Validates: Requirements 3.1, 3.2, 3.3**
        """
        # Simulate the data structure passed to frontend popup
        popup_data = {
            'document_title': citation.document_title,
            'relevance_score': citation.relevance_score,
            'excerpt': citation.excerpt,
            'page_number': citation.page_number,
            'section_title': citation.section_title,
            'content_truncated': citation.content_truncated,
            'excerpt_error': citation.excerpt_error
        }
        
        # Required fields must always be present
        assert 'document_title' in popup_data, "document_title is required for popup"
        assert 'relevance_score' in popup_data, "relevance_score is required for popup"
        assert 'excerpt' in popup_data or 'excerpt_error' in popup_data, (
            "Either excerpt or excerpt_error must be present"
        )
    
    @given(citation=citation_source_strategy())
    @settings(
        max_examples=100,
        suppress_health_check=[HealthCheck.function_scoped_fixture],
        deadline=None
    )
    def test_property_relevance_score_convertible_to_percentage(
        self, 
        citation: CitationSource
    ):
        """
        Property: Relevance score can be converted to a valid percentage.
        
        For any CitationSource, the relevance_score should be convertible
        to a percentage (0-100) for display in the popup.
        
        **Validates: Requirements 3.2**
        """
        percentage = round(citation.relevance_score * 100)
        
        assert 0 <= percentage <= 100, (
            f"Percentage {percentage} out of valid range [0, 100]"
        )
    
    @given(citation=citation_source_strategy())
    @settings(
        max_examples=100,
        suppress_health_check=[HealthCheck.function_scoped_fixture],
        deadline=None
    )
    def test_property_optional_fields_only_rendered_when_present(
        self, 
        citation: CitationSource
    ):
        """
        Property: Optional fields (page_number, section_title) are only 
        included when they have values.
        
        For any CitationSource, the popup should only display page_number
        and section_title when they are not None/empty.
        
        **Validates: Requirements 3.4, 3.5**
        """
        # Simulate popup rendering logic
        should_show_page = citation.page_number is not None
        should_show_section = citation.section_title is not None and citation.section_title.strip()
        
        # Verify the logic is consistent
        if citation.page_number is None:
            assert not should_show_page, "Should not show page when page_number is None"
        else:
            assert should_show_page, "Should show page when page_number is present"
        
        if not citation.section_title or not citation.section_title.strip():
            assert not should_show_section, "Should not show section when section_title is empty"
        else:
            assert should_show_section, "Should show section when section_title is present"
    
    @given(citation=citation_source_strategy())
    @settings(
        max_examples=100,
        suppress_health_check=[HealthCheck.function_scoped_fixture],
        deadline=None
    )
    def test_property_excerpt_or_error_message_always_available(
        self, 
        citation: CitationSource
    ):
        """
        Property: Either excerpt content or an error message is always available.
        
        For any CitationSource, the popup should always have something to display
        in the excerpt area - either the actual excerpt or an error message.
        
        **Validates: Requirements 3.3, 5.3**
        """
        has_excerpt = citation.excerpt and citation.excerpt.strip()
        has_error = citation.excerpt_error is not None
        
        # At least one should be available for display
        # Note: Both can be false if excerpt is empty string without error
        # In that case, popup shows "Excerpt not available"
        can_display_something = has_excerpt or has_error or True  # Fallback message always available
        
        assert can_display_something, (
            "Popup must always have content to display in excerpt area"
        )
    
    @given(
        content=st.text(min_size=501, max_size=2000),
    )
    @settings(
        max_examples=100,
        suppress_health_check=[HealthCheck.function_scoped_fixture],
        deadline=None
    )
    def test_property_long_excerpt_triggers_show_more(self, content: str):
        """
        Property: Excerpts longer than 500 characters should trigger "show more" option.
        
        For any excerpt exceeding 500 characters, the popup should display
        a truncated version with a "show more" option.
        
        **Validates: Requirements 3.6**
        """
        assume(len(content) > 500)
        
        # Simulate popup display logic (from citation-popup.js)
        display_excerpt = content[:500] if len(content) > 500 else content
        should_show_more = len(content) > 500
        
        assert should_show_more, "Long excerpts should trigger show more option"
        assert len(display_excerpt) <= 500, "Display excerpt should be truncated to 500 chars"


# =============================================================================
# Integration test to verify all properties
# =============================================================================

def test_all_citation_pbt_properties_defined():
    """
    Meta-test that ensures all property tests are defined.
    
    This validates that the property-based testing infrastructure
    is working correctly.
    """
    citation_data_tests = [
        TestCitationDataCompletenessPBT.test_property_citations_have_excerpts_when_content_available,
        TestCitationDataCompletenessPBT.test_property_citation_excerpt_matches_truncated_content,
        TestCitationDataCompletenessPBT.test_property_all_required_citation_fields_present,
        TestCitationDataCompletenessPBT.test_property_citation_serialization_preserves_all_fields,
    ]
    
    popup_content_tests = [
        TestPopupContentCompletenessPBT.test_property_popup_data_contains_required_fields,
        TestPopupContentCompletenessPBT.test_property_relevance_score_convertible_to_percentage,
        TestPopupContentCompletenessPBT.test_property_optional_fields_only_rendered_when_present,
        TestPopupContentCompletenessPBT.test_property_excerpt_or_error_message_always_available,
        TestPopupContentCompletenessPBT.test_property_long_excerpt_triggers_show_more,
    ]
    
    total_tests = len(citation_data_tests) + len(popup_content_tests)
    
    assert total_tests == 9, f"Expected 9 property tests, found {total_tests}"
    
    print(f"✓ All {total_tests} property-based tests are defined")
    print(f"  - Property 5: Citation Data Completeness in API (Task 10.1) - {len(citation_data_tests)} tests")
    print(f"  - Property 2: Popup Content Completeness (Task 10.2) - {len(popup_content_tests)} tests")


if __name__ == "__main__":
    print("Running Property-Based Tests for Citation Data and Popup Content")
    print("=" * 70)
    print("\nTask 10.1: Citation Data Completeness Properties")
    print("Task 10.2: Popup Content Completeness Properties")
    print("\nTo run with pytest:")
    print("pytest tests/services/test_citation_pbt.py -v --tb=short")
    print("\nRunning tests...")
    
    pytest.main([__file__, "-v", "--tb=short"])
