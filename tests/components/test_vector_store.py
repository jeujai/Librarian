"""
Tests for the Vector Store component.

This module contains tests for the vector database integration including
Milvus connection, embedding generation, storage, and semantic search.
"""

import pytest
import numpy as np
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime

from src.multimodal_librarian.components.vector_store import (
    VectorStore, 
    VectorStoreError
)
from src.multimodal_librarian.components.vector_store.search_service import (
    EnhancedSemanticSearchService as SemanticSearchService
)
from src.multimodal_librarian.models.search_types import (
    SearchResult,
    SearchQuery
)
from src.multimodal_librarian.models.core import (
    KnowledgeChunk, 
    SourceType, 
    ContentType,
    KnowledgeMetadata
)


class TestVectorStore:
    """Test cases for VectorStore class."""
    
    def test_vector_store_initialization(self):
        """Test vector store initialization."""
        vector_store = VectorStore("test_collection")
        assert vector_store.collection_name == "test_collection"
        assert not vector_store._connected
        assert vector_store.embedding_model is None
        assert vector_store.collection is None
    
    @patch('src.multimodal_librarian.components.vector_store.vector_store.connections')
    @patch('src.multimodal_librarian.components.vector_store.vector_store.SentenceTransformer')
    def test_connect_success(self, mock_transformer, mock_connections):
        """Test successful connection to Milvus."""
        # Mock the sentence transformer
        mock_model = Mock()
        mock_transformer.return_value = mock_model
        
        vector_store = VectorStore("test_collection")
        
        with patch.object(vector_store, '_initialize_collection'):
            vector_store.connect()
            
            assert vector_store._connected
            assert vector_store.embedding_model == mock_model
            mock_connections.connect.assert_called_once()
    
    @patch('src.multimodal_librarian.components.vector_store.vector_store.connections')
    def test_connect_failure(self, mock_connections):
        """Test connection failure handling."""
        mock_connections.connect.side_effect = Exception("Connection failed")
        
        vector_store = VectorStore("test_collection")
        
        with pytest.raises(VectorStoreError, match="Failed to connect to vector database"):
            vector_store.connect()
    
    def test_generate_embedding(self):
        """Test embedding generation."""
        vector_store = VectorStore("test_collection")
        
        # Mock embedding model
        mock_model = Mock()
        mock_embedding = np.array([0.1, 0.2, 0.3])
        mock_model.encode.return_value = [mock_embedding]
        vector_store.embedding_model = mock_model
        
        result = vector_store.generate_embedding("test text")
        
        assert np.array_equal(result, mock_embedding)
        mock_model.encode.assert_called_once_with(["test text"])
    
    def test_generate_embedding_no_model(self):
        """Test embedding generation without initialized model."""
        vector_store = VectorStore("test_collection")
        
        with pytest.raises(VectorStoreError, match="Embedding model not initialized"):
            vector_store.generate_embedding("test text")
    
    def test_store_embeddings_not_connected(self):
        """Test storing embeddings when not connected."""
        vector_store = VectorStore("test_collection")
        chunks = [KnowledgeChunk(id="test", content="test content")]
        
        with pytest.raises(VectorStoreError, match="Vector store not connected"):
            vector_store.store_embeddings(chunks)
    
    def test_store_embeddings_empty_list(self):
        """Test storing empty list of chunks."""
        vector_store = VectorStore("test_collection")
        vector_store._connected = True
        vector_store.collection = Mock()
        
        # Should not raise an error, just log a warning
        vector_store.store_embeddings([])
    
    def test_semantic_search_not_connected(self):
        """Test semantic search when not connected."""
        vector_store = VectorStore("test_collection")
        
        with pytest.raises(VectorStoreError, match="Vector store not connected"):
            vector_store.semantic_search("test query")
    
    def test_health_check_not_connected(self):
        """Test health check when not connected."""
        vector_store = VectorStore("test_collection")
        assert not vector_store.health_check()
    
    def test_context_manager(self):
        """Test vector store as context manager."""
        vector_store = VectorStore("test_collection")
        
        with patch.object(vector_store, 'connect') as mock_connect, \
             patch.object(vector_store, 'disconnect') as mock_disconnect:
            
            with vector_store:
                pass
            
            mock_connect.assert_called_once()
            mock_disconnect.assert_called_once()


class TestSearchQuery:
    """Test cases for SearchQuery class."""
    
    def test_search_query_creation(self):
        """Test SearchQuery creation from text."""
        query = SearchQuery.from_text("What is machine learning?")
        
        assert query.original_query == "What is machine learning?"
        assert query.processed_query == "what is machine learning?"
        assert query.query_type == "factual"
        assert "machine" in query.key_terms
        assert "learning" in query.key_terms
    
    def test_query_preprocessing(self):
        """Test query preprocessing."""
        processed = SearchQuery._preprocess_query("What's   the    difference?")
        assert processed == "what is the difference?"
    
    def test_query_type_classification(self):
        """Test query type classification."""
        assert SearchQuery._classify_query_type("What is AI?") == "factual"
        assert SearchQuery._classify_query_type("How to train a model?") == "procedural"
        assert SearchQuery._classify_query_type("Why does this work?") == "conceptual"
        assert SearchQuery._classify_query_type("Compare A vs B") == "comparative"
        assert SearchQuery._classify_query_type("Random query") == "general"
    
    def test_key_term_extraction(self):
        """Test key term extraction."""
        terms = SearchQuery._extract_key_terms("What is machine learning algorithm?")
        
        assert "machine" in terms
        assert "learning" in terms
        assert "algorithm" in terms
        assert "what" not in terms  # Stop word should be filtered
        assert "is" not in terms    # Stop word should be filtered
    
    def test_context_hints_extraction(self):
        """Test context hints extraction."""
        hints = SearchQuery._extract_context_hints("How to implement a software algorithm?")
        assert "domain:technical" in hints
        
        hints = SearchQuery._extract_context_hints("What is the medical treatment?")
        assert "domain:medical" in hints


class TestSearchResult:
    """Test cases for SearchResult class."""
    
    def test_search_result_from_vector_result(self):
        """Test SearchResult creation from vector store result."""
        vector_result = {
            'chunk_id': 'test_chunk',
            'content': 'Test content',
            'source_type': 'book',
            'source_id': 'test_book',
            'content_type': 'technical',
            'location_reference': 'page_1',
            'section': 'chapter_1',
            'similarity_score': 0.85,
            'created_at': int(datetime.now().timestamp() * 1000)
        }
        
        result = SearchResult.from_vector_result(vector_result)
        
        assert result.chunk_id == 'test_chunk'
        assert result.content == 'Test content'
        assert result.source_type == SourceType.BOOK
        assert result.content_type == ContentType.TECHNICAL
        assert result.similarity_score == 0.85
        assert result.relevance_score == 0.85
        assert not result.is_bridge
    
    def test_search_result_bridge_detection(self):
        """Test bridge chunk detection in SearchResult."""
        vector_result = {
            'chunk_id': 'bridge_chunk',
            'content': 'Bridge content',
            'source_type': 'book',
            'source_id': 'test_book',
            'content_type': 'technical',
            'location_reference': 'page_1',
            'section': 'BRIDGE_chapter_1',
            'similarity_score': 0.75,
            'created_at': int(datetime.now().timestamp() * 1000)
        }
        
        result = SearchResult.from_vector_result(vector_result)
        assert result.is_bridge


class TestSemanticSearchService:
    """Test cases for SemanticSearchService class."""
    
    def test_search_service_initialization(self):
        """Test search service initialization."""
        mock_vector_store = Mock()
        service = SemanticSearchService(mock_vector_store)
        
        assert service.vector_store == mock_vector_store
    
    def test_search_basic(self):
        """Test basic search functionality."""
        mock_vector_store = Mock()
        mock_vector_store.semantic_search.return_value = [
            {
                'chunk_id': 'test_chunk',
                'content': 'Test content about machine learning',
                'source_type': 'book',
                'source_id': 'ml_book',
                'content_type': 'technical',
                'location_reference': 'page_1',
                'section': 'chapter_1',
                'similarity_score': 0.85,
                'created_at': int(datetime.now().timestamp() * 1000)
            }
        ]
        
        service = SemanticSearchService(mock_vector_store)
        
        with patch.object(service, '_search_bridge_chunks', return_value=[]):
            results = service.search("What is machine learning?", top_k=5)
        
        assert len(results) == 1
        assert results[0].chunk_id == 'test_chunk'
        assert results[0].content == 'Test content about machine learning'
        mock_vector_store.semantic_search.assert_called_once()
    
    def test_search_with_filters(self):
        """Test search with various filters."""
        mock_vector_store = Mock()
        mock_vector_store.semantic_search.return_value = []
        
        service = SemanticSearchService(mock_vector_store)
        
        with patch.object(service, '_search_bridge_chunks', return_value=[]):
            service.search(
                "test query",
                source_type=SourceType.BOOK,
                content_type=ContentType.TECHNICAL,
                source_id="specific_book"
            )
        
        mock_vector_store.semantic_search.assert_called_once()
        call_args = mock_vector_store.semantic_search.call_args
        assert call_args[1]['source_type'] == SourceType.BOOK
        assert call_args[1]['content_type'] == ContentType.TECHNICAL
        assert call_args[1]['source_id'] == "specific_book"
    
    def test_search_conversations_only(self):
        """Test conversation-only search."""
        mock_vector_store = Mock()
        mock_vector_store.semantic_search.return_value = []
        
        service = SemanticSearchService(mock_vector_store)
        
        with patch.object(service, '_search_bridge_chunks', return_value=[]):
            service.search_conversations_only("test query")
        
        call_args = mock_vector_store.semantic_search.call_args
        assert call_args[1]['source_type'] == SourceType.CONVERSATION
    
    def test_search_books_only(self):
        """Test book-only search."""
        mock_vector_store = Mock()
        mock_vector_store.semantic_search.return_value = []
        
        service = SemanticSearchService(mock_vector_store)
        
        with patch.object(service, '_search_bridge_chunks', return_value=[]):
            service.search_books_only("test query", content_type=ContentType.ACADEMIC)
        
        call_args = mock_vector_store.semantic_search.call_args
        assert call_args[1]['source_type'] == SourceType.BOOK
        assert call_args[1]['content_type'] == ContentType.ACADEMIC
    
    def test_find_similar_chunks(self):
        """Test finding similar chunks."""
        mock_vector_store = Mock()
        mock_vector_store.get_chunk_by_id.return_value = {
            'chunk_id': 'reference_chunk',
            'content': 'Reference content',
            'source_id': 'test_source'
        }
        mock_vector_store.semantic_search.return_value = [
            {
                'chunk_id': 'similar_chunk',
                'content': 'Similar content',
                'source_type': 'book',
                'source_id': 'other_source',
                'content_type': 'technical',
                'location_reference': 'page_2',
                'section': 'chapter_2',
                'similarity_score': 0.75,
                'created_at': int(datetime.now().timestamp() * 1000)
            }
        ]
        
        service = SemanticSearchService(mock_vector_store)
        results = service.find_similar_chunks("reference_chunk", top_k=5)
        
        assert len(results) == 1
        assert results[0].chunk_id == 'similar_chunk'
        mock_vector_store.get_chunk_by_id.assert_called_once_with("reference_chunk")
    
    def test_get_search_suggestions(self):
        """Test search suggestions generation."""
        service = SemanticSearchService(Mock())
        
        suggestions = service.get_search_suggestions("what", max_suggestions=3)
        assert len(suggestions) <= 3
        assert all("what" in suggestion for suggestion in suggestions)
        
        suggestions = service.get_search_suggestions("how", max_suggestions=3)
        assert len(suggestions) <= 3
        assert all("how" in suggestion for suggestion in suggestions)
    
    def test_ranking_factors(self):
        """Test result ranking with various factors."""
        mock_vector_store = Mock()
        service = SemanticSearchService(mock_vector_store)
        
        # Create test results with different characteristics
        results = [
            SearchResult(
                chunk_id="chunk1",
                content="technical algorithm implementation",
                source_type=SourceType.BOOK,
                source_id="book1",
                content_type=ContentType.TECHNICAL,
                location_reference="page1",
                section="section1",
                similarity_score=0.7,
                relevance_score=0.7
            ),
            SearchResult(
                chunk_id="chunk2", 
                content="general information",
                source_type=SourceType.BOOK,
                source_id="book2",
                content_type=ContentType.GENERAL,
                location_reference="page2",
                section="section2",
                similarity_score=0.8,
                relevance_score=0.8
            )
        ]
        
        search_query = SearchQuery.from_text("how to implement algorithm")
        ranked_results = service._rank_results(results, search_query)
        
        # Results should be ranked by relevance score
        assert ranked_results[0].relevance_score >= ranked_results[1].relevance_score


if __name__ == "__main__":
    pytest.main([__file__])