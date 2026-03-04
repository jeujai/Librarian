"""
Basic tests for the Multi-Level Chunking Framework.

These tests verify that the chunking framework components can be initialized
and perform basic operations without errors.
"""

import pytest
from unittest.mock import Mock, patch
from src.multimodal_librarian.components.chunking_framework.framework import GenericMultiLevelChunkingFramework
from src.multimodal_librarian.models.core import DocumentContent, ContentType


class TestChunkingFrameworkBasic:
    """Basic tests for chunking framework initialization and operation."""
    
    def test_framework_initialization(self):
        """Test that the framework can be initialized without errors."""
        framework = GenericMultiLevelChunkingFramework()
        assert framework is not None
        assert framework.content_analyzer is not None
        assert framework.config_manager is not None
        assert framework.gap_analyzer is not None
        assert framework.bridge_generator is not None
        assert framework.validator is not None
        assert framework.fallback_system is not None
    
    def test_framework_statistics_initialization(self):
        """Test that framework statistics are properly initialized."""
        framework = GenericMultiLevelChunkingFramework()
        stats = framework.get_framework_statistics()
        
        assert stats['documents_processed'] == 0
        assert stats['total_chunks_created'] == 0
        assert stats['total_bridges_generated'] == 0
        assert stats['total_fallbacks_created'] == 0
        assert stats['average_processing_time'] == 0.0
        assert stats['success_rate'] == 0.0
    
    def test_simple_document_processing(self):
        """Test processing a simple document."""
        framework = GenericMultiLevelChunkingFramework()
        
        # Create a simple test document
        doc = DocumentContent(
            text="This is a test document. It has multiple sentences. Each sentence should be processed correctly.",
            images=[],
            tables=[],
            metadata={'title': 'Test Document'},
            structure=None
        )
        
        # Process the document
        result = framework.process_document(doc, 'test_doc_1')
        
        # Verify basic results
        assert result is not None
        assert result.document_id == 'test_doc_1'
        assert result.content_profile is not None
        assert result.domain_config is not None
        assert len(result.chunks) > 0
        assert result.processing_time > 0
        assert 'content_type' in result.processing_stats
        assert 'chunks_created' in result.processing_stats
    
    def test_framework_statistics_update_after_processing(self):
        """Test that framework statistics are updated after processing."""
        framework = GenericMultiLevelChunkingFramework()
        
        # Initial stats should be zero
        initial_stats = framework.get_framework_statistics()
        assert initial_stats['documents_processed'] == 0
        
        # Process a document
        doc = DocumentContent(
            text="Test document for statistics.",
            images=[],
            tables=[],
            metadata={'title': 'Stats Test'},
            structure=None
        )
        
        framework.process_document(doc, 'stats_test')
        
        # Stats should be updated
        updated_stats = framework.get_framework_statistics()
        assert updated_stats['documents_processed'] == 1
        assert updated_stats['average_processing_time'] > 0
    
    def test_reset_statistics(self):
        """Test that statistics can be reset."""
        framework = GenericMultiLevelChunkingFramework()
        
        # Process a document to generate some stats
        doc = DocumentContent(
            text="Test document for reset.",
            images=[],
            tables=[],
            metadata={'title': 'Reset Test'},
            structure=None
        )
        
        framework.process_document(doc, 'reset_test')
        
        # Verify stats are not zero
        stats_before = framework.get_framework_statistics()
        assert stats_before['documents_processed'] > 0
        
        # Reset statistics
        framework.reset_statistics()
        
        # Verify stats are reset
        stats_after = framework.get_framework_statistics()
        assert stats_after['documents_processed'] == 0
        assert stats_after['total_chunks_created'] == 0
        assert stats_after['average_processing_time'] == 0.0
    
    def test_empty_document_handling(self):
        """Test handling of empty documents."""
        framework = GenericMultiLevelChunkingFramework()
        
        # Create an empty document
        doc = DocumentContent(
            text="",
            images=[],
            tables=[],
            metadata={'title': 'Empty Document'},
            structure=None
        )
        
        # Process should handle empty document gracefully
        result = framework.process_document(doc, 'empty_doc')
        
        assert result is not None
        assert result.document_id == 'empty_doc'
        # Should still have basic structure even for empty document
        assert result.content_profile is not None
        assert result.domain_config is not None
    
    def test_multiple_document_processing(self):
        """Test processing multiple documents."""
        framework = GenericMultiLevelChunkingFramework()
        
        documents = [
            DocumentContent(
                text="First test document with some content.",
                images=[], tables=[], metadata={'title': 'Doc 1'}, structure=None
            ),
            DocumentContent(
                text="Second test document with different content.",
                images=[], tables=[], metadata={'title': 'Doc 2'}, structure=None
            ),
            DocumentContent(
                text="Third test document with more content to process.",
                images=[], tables=[], metadata={'title': 'Doc 3'}, structure=None
            )
        ]
        
        results = []
        for i, doc in enumerate(documents):
            result = framework.process_document(doc, f'multi_doc_{i}')
            results.append(result)
        
        # Verify all documents were processed
        assert len(results) == 3
        for i, result in enumerate(results):
            assert result.document_id == f'multi_doc_{i}'
            assert len(result.chunks) > 0
        
        # Verify statistics reflect multiple documents
        stats = framework.get_framework_statistics()
        assert stats['documents_processed'] == 3