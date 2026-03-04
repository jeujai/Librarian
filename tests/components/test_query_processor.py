"""
Tests for Query Processing Component.

This module contains tests for the unified knowledge query processing
and response synthesis functionality.
"""

from datetime import datetime
from unittest.mock import MagicMock, Mock, patch

import pytest

from src.multimodal_librarian.components.query_processor import (
    CitationTracker,
    ProcessedQuery,
    QueryContext,
    ResponseSynthesizer,
    SynthesisContext,
    UnifiedKnowledgeQueryProcessor,
    UnifiedResponseGenerator,
    UnifiedSearchResult,
)
from src.multimodal_librarian.models.core import (
    ContentType,
    ConversationThread,
    KnowledgeChunk,
    KnowledgeCitation,
    Message,
    MessageType,
    MultimediaResponse,
    SourceType,
)

# Import search models first to avoid circular imports
from src.multimodal_librarian.models.search_types import SearchResult


class TestProcessedQuery:
    """Test ProcessedQuery functionality."""
    
    def test_from_raw_query_basic(self):
        """Test basic query processing."""
        query = "What is machine learning?"
        processed = ProcessedQuery.from_raw_query(query)
        
        assert processed.original_query == query
        assert processed.processed_query == "what is machine learning?"
        assert processed.query_intent == "factual"
        assert "machine" in processed.key_concepts
        assert "learning" in processed.key_concepts
    
    def test_query_intent_classification(self):
        """Test query intent classification."""
        test_cases = [
            ("What is Python?", "factual"),
            ("How to install Python?", "procedural"),
            ("Compare Python and Java", "comparative"),
            ("Also, what about Ruby?", "conversational")
        ]
        
        for query, expected_intent in test_cases:
            processed = ProcessedQuery.from_raw_query(query)
            assert processed.query_intent == expected_intent
    
    def test_key_concept_extraction(self):
        """Test key concept extraction."""
        query = "How does machine learning work in artificial intelligence?"
        processed = ProcessedQuery.from_raw_query(query)
        
        assert "machine" in processed.key_concepts
        assert "learning" in processed.key_concepts
        assert "artificial" in processed.key_concepts
        assert "intelligence" in processed.key_concepts


class TestCitationTracker:
    """Test CitationTracker functionality."""
    
    def test_add_citation(self):
        """Test adding citations."""
        tracker = CitationTracker()
        
        citation = KnowledgeCitation(
            source_type=SourceType.BOOK,
            source_title="Test Book",
            location_reference="Page 1",
            chunk_id="chunk_1",
            relevance_score=0.8
        )
        
        citation_num = tracker.add_citation(citation)
        assert citation_num == 1
        assert len(tracker.citations) == 1
        assert tracker.source_counts[SourceType.BOOK] == 1
    
    def test_duplicate_citation(self):
        """Test handling duplicate citations."""
        tracker = CitationTracker()
        
        citation = KnowledgeCitation(
            source_type=SourceType.BOOK,
            source_title="Test Book",
            location_reference="Page 1",
            chunk_id="chunk_1",
            relevance_score=0.8
        )
        
        # Add same citation twice
        num1 = tracker.add_citation(citation)
        num2 = tracker.add_citation(citation)
        
        assert num1 == num2 == 1
        assert len(tracker.citations) == 1
    
    def test_format_citations_inline(self):
        """Test inline citation formatting."""
        tracker = CitationTracker()
        
        citation1 = KnowledgeCitation(
            source_type=SourceType.BOOK,
            source_title="Book 1",
            location_reference="Page 1",
            chunk_id="chunk_1"
        )
        
        citation2 = KnowledgeCitation(
            source_type=SourceType.CONVERSATION,
            source_title="Conversation 1",
            location_reference="2023-01-01",
            chunk_id="chunk_2"
        )
        
        tracker.add_citation(citation1)
        tracker.add_citation(citation2)
        
        formatted = tracker.format_citations("inline")
        assert "[1] Book: Book 1, Page 1" in formatted
        assert "[2] Conversation: Conversation 1, 2023-01-01" in formatted


class TestUnifiedKnowledgeQueryProcessor:
    """Test UnifiedKnowledgeQueryProcessor functionality."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.mock_search_service = Mock()
        self.mock_conversation_manager = Mock()
        self.mock_kg_query_engine = Mock()
        
        # Mock knowledge graph query engine methods (only methods that still exist)
        self.mock_kg_query_engine.enhance_vector_search.return_value = []
        
        self.processor = UnifiedKnowledgeQueryProcessor(
            search_service=self.mock_search_service,
            conversation_manager=self.mock_conversation_manager,
            kg_query_engine=self.mock_kg_query_engine
        )
    
    def test_process_query_basic(self):
        """Test basic query processing."""
        # Mock search results
        mock_search_results = [
            SearchResult(
                chunk_id="chunk_1",
                content="Test content about machine learning",
                source_type=SourceType.BOOK,
                source_id="book_1",
                content_type=ContentType.TECHNICAL,
                location_reference="Page 1",
                section="Chapter 1",
                similarity_score=0.9,
                relevance_score=0.9
            )
        ]
        
        # Mock the source-specific search methods that are actually called
        self.mock_search_service.search_books_only.return_value = mock_search_results
        self.mock_search_service.search_conversations_only.return_value = []
        
        # Process query
        result = self.processor.process_query("What is machine learning?")
        
        assert isinstance(result, UnifiedSearchResult)
        assert result.total_results > 0
        assert len(result.chunks) > 0
        assert len(result.citations) > 0
    
    def test_search_across_sources(self):
        """Test multi-source search functionality."""
        # Mock search results for different sources
        self.mock_search_service.search_books_only.return_value = [
            SearchResult(
                chunk_id="book_chunk_1",
                content="Book content",
                source_type=SourceType.BOOK,
                source_id="book_1",
                content_type=ContentType.TECHNICAL,
                location_reference="Page 1",
                section="Chapter 1",
                similarity_score=0.8,
                relevance_score=0.8
            )
        ]
        
        self.mock_search_service.search_conversations_only.return_value = [
            SearchResult(
                chunk_id="conv_chunk_1",
                content="Conversation content",
                source_type=SourceType.CONVERSATION,
                source_id="conv_1",
                content_type=ContentType.GENERAL,
                location_reference="2023-01-01",
                section="Messages 1-5",
                similarity_score=0.7,
                relevance_score=0.7
            )
        ]
        
        # Test multi-source search
        result = self.processor.search_across_sources(
            "test query",
            source_weights={SourceType.BOOK: 0.6, SourceType.CONVERSATION: 0.4}
        )
        
        assert isinstance(result, UnifiedSearchResult)
        assert SourceType.BOOK in result.source_distribution
        assert SourceType.CONVERSATION in result.source_distribution


class TestResponseSynthesizer:
    """Test ResponseSynthesizer functionality."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.synthesizer = ResponseSynthesizer()
    
    @patch('src.multimodal_librarian.components.query_processor.response_synthesizer.OPENAI_AVAILABLE', True)
    @patch('src.multimodal_librarian.components.query_processor.response_synthesizer.openai')
    def test_synthesize_response_with_gpt4(self, mock_openai_module):
        """Test response synthesis with GPT-4."""
        # Mock OpenAI response
        mock_response = Mock()
        mock_response.choices = [Mock()]
        mock_response.choices[0].message.content = "This is a test response with citations [1] and [2]."
        mock_openai_module.ChatCompletion.create.return_value = mock_response
        
        # Create test data
        chunks = [
            KnowledgeChunk(
                id="chunk_1",
                content="Test content from book",
                source_type=SourceType.BOOK,
                source_id="book_1",
                location_reference="Page 1",
                section="Chapter 1",
                content_type=ContentType.TECHNICAL
            ),
            KnowledgeChunk(
                id="chunk_2",
                content="Test content from conversation",
                source_type=SourceType.CONVERSATION,
                source_id="conv_1",
                location_reference="2023-01-01",
                section="Messages 1-5",
                content_type=ContentType.GENERAL
            )
        ]
        
        search_results = UnifiedSearchResult(
            chunks=chunks,
            citations=[],
            source_distribution={SourceType.BOOK: 1, SourceType.CONVERSATION: 1},
            total_results=2
        )
        
        processed_query = ProcessedQuery.from_raw_query("What is machine learning?")
        
        synthesis_context = SynthesisContext(
            query="What is machine learning?",
            processed_query=processed_query,
            search_results=search_results
        )
        
        # Test synthesis
        response = self.synthesizer.synthesize_response(synthesis_context)
        
        assert isinstance(response, MultimediaResponse)
        assert len(response.text_content) > 0
        assert len(response.knowledge_citations) > 0
        
        # Verify OpenAI was called
        mock_openai_module.ChatCompletion.create.assert_called_once()
    
    def test_synthesize_response_fallback(self):
        """Test fallback response generation when GPT-4 is unavailable."""
        # Create test data without OpenAI API key
        chunks = [
            KnowledgeChunk(
                id="chunk_1",
                content="Test content about machine learning algorithms",
                source_type=SourceType.BOOK,
                source_id="book_1",
                location_reference="Page 1",
                section="Chapter 1",
                content_type=ContentType.TECHNICAL
            )
        ]
        
        search_results = UnifiedSearchResult(
            chunks=chunks,
            citations=[],
            source_distribution={SourceType.BOOK: 1},
            total_results=1
        )
        
        processed_query = ProcessedQuery.from_raw_query("What is machine learning?")
        
        synthesis_context = SynthesisContext(
            query="What is machine learning?",
            processed_query=processed_query,
            search_results=search_results
        )
        
        # Force fallback by causing OpenAI to fail
        with patch('src.multimodal_librarian.components.query_processor.response_synthesizer.OPENAI_AVAILABLE', False):
            response = self.synthesizer.synthesize_response(synthesis_context)
        
        assert isinstance(response, MultimediaResponse)
        assert len(response.text_content) > 0
        assert "machine learning" in response.text_content.lower()


class TestUnifiedResponseGenerator:
    """Test UnifiedResponseGenerator functionality."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.mock_query_processor = Mock()
        self.mock_response_synthesizer = Mock()
        
        self.generator = UnifiedResponseGenerator(
            query_processor=self.mock_query_processor,
            response_synthesizer=self.mock_response_synthesizer
        )
    
    def test_generate_response(self):
        """Test unified response generation."""
        # Mock query processor response
        mock_search_results = UnifiedSearchResult(
            chunks=[],
            citations=[],
            source_distribution={},
            total_results=0
        )
        self.mock_query_processor.process_query.return_value = mock_search_results
        
        # Mock synthesizer response
        mock_response = MultimediaResponse(
            text_content="Test response",
            knowledge_citations=[]
        )
        self.mock_response_synthesizer.synthesize_response.return_value = mock_response
        
        # Test generation
        result = self.generator.generate_response("What is machine learning?")
        
        assert isinstance(result, MultimediaResponse)
        assert result.text_content == "Test response"
        
        # Verify components were called
        self.mock_query_processor.process_query.assert_called_once()
        self.mock_response_synthesizer.synthesize_response.assert_called_once()


# Integration test
class TestQueryProcessorIntegration:
    """Integration tests for query processor components."""
    
    def test_end_to_end_query_processing(self):
        """Test end-to-end query processing without external dependencies."""
        # This test would require actual components to be initialized
        # For now, we'll test that the components can be imported and instantiated
        
        # Test imports
        from src.multimodal_librarian.components.query_processor import (
            ResponseSynthesizer,
            UnifiedKnowledgeQueryProcessor,
            UnifiedResponseGenerator,
        )

        # Test that classes can be instantiated (with mocks)
        mock_search_service = Mock()
        mock_conversation_manager = Mock()
        
        processor = UnifiedKnowledgeQueryProcessor(
            search_service=mock_search_service,
            conversation_manager=mock_conversation_manager
        )
        
        synthesizer = ResponseSynthesizer()
        
        generator = UnifiedResponseGenerator(
            query_processor=processor,
            response_synthesizer=synthesizer
        )
        
        assert processor is not None
        assert synthesizer is not None
        assert generator is not None


if __name__ == "__main__":
    pytest.main([__file__])