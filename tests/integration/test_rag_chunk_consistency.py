"""
RAG Chunk ID Consistency Integration Tests

This module tests the consistency of chunk IDs across PostgreSQL and Milvus
storage systems, ensuring RAG search can find document content.

Validates:
- Requirement 1.4: Chunk IDs in PostgreSQL match chunk IDs in Milvus
- Requirement 2.1: Semantic search returns chunks that exist in both systems
- Requirement 2.2: Returned chunk IDs can retrieve content from PostgreSQL
- Requirement 4.3: Reprocessed documents are searchable via RAG

Test File Location: tests/integration/test_rag_chunk_consistency.py
"""

import asyncio
import json
import logging
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

logger = logging.getLogger(__name__)


# =============================================================================
# Test Fixtures
# =============================================================================

@pytest.fixture
def sample_document_content():
    """Create sample document content for testing."""
    return {
        'text': """
        Machine learning is a subset of artificial intelligence that enables
        systems to learn and improve from experience without being explicitly
        programmed. Deep learning is a type of machine learning that uses
        neural networks with multiple layers to progressively extract higher
        level features from raw input.
        """,
        'metadata': {
            'title': 'Introduction to Machine Learning',
            'author': 'Test Author',
            'page_count': 1,
            'file_size': 1024
        }
    }


@pytest.fixture
def mock_postgres_storage():
    """Mock PostgreSQL storage that tracks stored chunk IDs."""
    stored_chunks = {}
    
    async def store_chunk(document_id: str, chunk: Dict[str, Any], index: int):
        chunk_id = chunk.get('id')
        if document_id not in stored_chunks:
            stored_chunks[document_id] = {}
        stored_chunks[document_id][chunk_id] = {
            'content': chunk.get('content'),
            'chunk_index': index,
            'metadata': chunk.get('metadata', {})
        }
        return chunk_id
    
    async def get_chunk(chunk_id: str) -> Optional[Dict[str, Any]]:
        for doc_chunks in stored_chunks.values():
            if chunk_id in doc_chunks:
                return doc_chunks[chunk_id]
        return None
    
    async def get_document_chunks(document_id: str) -> Dict[str, Any]:
        return stored_chunks.get(document_id, {})
    
    async def delete_document_chunks(document_id: str) -> int:
        if document_id in stored_chunks:
            count = len(stored_chunks[document_id])
            del stored_chunks[document_id]
            return count
        return 0
    
    return {
        'store_chunk': store_chunk,
        'get_chunk': get_chunk,
        'get_document_chunks': get_document_chunks,
        'delete_document_chunks': delete_document_chunks,
        'stored_chunks': stored_chunks
    }


@pytest.fixture
def mock_milvus_storage():
    """Mock Milvus storage that tracks stored chunk IDs."""
    stored_vectors = {}
    
    async def store_embedding(chunk: Dict[str, Any]):
        chunk_id = chunk.get('id')
        source_id = chunk.get('metadata', {}).get('source_id')
        if source_id not in stored_vectors:
            stored_vectors[source_id] = {}
        stored_vectors[source_id][chunk_id] = {
            'content': chunk.get('content'),
            'embedding': chunk.get('embedding', [0.1] * 384),
            'metadata': chunk.get('metadata', {})
        }
        return chunk_id
    
    async def search(query: str, top_k: int = 10) -> List[Dict[str, Any]]:
        results = []
        for source_id, chunks in stored_vectors.items():
            for chunk_id, chunk_data in chunks.items():
                results.append({
                    'chunk_id': chunk_id,
                    'content': chunk_data['content'],
                    'source_id': source_id,
                    'similarity_score': 0.85,
                    'metadata': chunk_data['metadata']
                })
        return results[:top_k]
    
    async def get_document_vectors(source_id: str) -> Dict[str, Any]:
        return stored_vectors.get(source_id, {})
    
    async def delete_by_source(source_id: str) -> int:
        if source_id in stored_vectors:
            count = len(stored_vectors[source_id])
            del stored_vectors[source_id]
            return count
        return 0
    
    return {
        'store_embedding': store_embedding,
        'search': search,
        'get_document_vectors': get_document_vectors,
        'delete_by_source': delete_by_source,
        'stored_vectors': stored_vectors
    }


# =============================================================================
# Test 10.1: End-to-End Document Processing Test
# =============================================================================

class TestEndToEndDocumentProcessing:
    """
    Test end-to-end document processing to verify chunk IDs match
    in PostgreSQL and Milvus.
    
    Validates: Requirements 1.4, 2.3
    """
    
    @pytest.mark.asyncio
    async def test_chunk_ids_match_across_storage_systems(
        self,
        sample_document_content,
        mock_postgres_storage,
        mock_milvus_storage
    ):
        """
        Test that chunk IDs generated by chunking framework are used
        consistently in both PostgreSQL and Milvus storage.
        
        Validates: Requirement 1.4 - Chunk IDs in PostgreSQL match Milvus
        """
        from src.multimodal_librarian.components.chunking_framework.framework import (
            GenericMultiLevelChunkingFramework,
        )
        from src.multimodal_librarian.models.core import (
            DocumentContent,
            DocumentMetadata,
        )

        # Create document content
        metadata = DocumentMetadata(
            title=sample_document_content['metadata']['title'],
            author=sample_document_content['metadata']['author'],
            page_count=sample_document_content['metadata']['page_count'],
            file_size=sample_document_content['metadata']['file_size']
        )
        
        doc_content = DocumentContent(
            text=sample_document_content['text'],
            images=[],
            tables=[],
            charts=[],
            metadata=metadata
        )
        
        # Process document through chunking framework
        document_id = str(uuid.uuid4())
        framework = GenericMultiLevelChunkingFramework()
        processed_doc = framework.process_document(doc_content, document_id)
        
        # Verify chunks have valid UUIDs
        assert len(processed_doc.chunks) > 0, "Should generate at least one chunk"
        
        for chunk in processed_doc.chunks:
            # Validate UUID format
            try:
                uuid.UUID(chunk.id)
            except ValueError:
                pytest.fail(f"Chunk ID is not a valid UUID: {chunk.id}")
        
        # Store chunks in both systems using the same IDs
        postgres_ids = set()
        milvus_ids = set()
        
        for i, chunk in enumerate(processed_doc.chunks):
            # Store in PostgreSQL
            chunk_data = {
                'id': chunk.id,
                'content': chunk.content,
                'metadata': chunk.metadata
            }
            pg_id = await mock_postgres_storage['store_chunk'](document_id, chunk_data, i)
            postgres_ids.add(pg_id)
            
            # Store in Milvus
            vector_data = {
                'id': chunk.id,
                'content': chunk.content,
                'metadata': {'source_id': document_id, **chunk.metadata}
            }
            mv_id = await mock_milvus_storage['store_embedding'](vector_data)
            milvus_ids.add(mv_id)
        
        # Verify IDs match exactly
        assert postgres_ids == milvus_ids, (
            f"Chunk IDs don't match between PostgreSQL and Milvus.\n"
            f"PostgreSQL IDs: {postgres_ids}\n"
            f"Milvus IDs: {milvus_ids}"
        )
        
        # Verify all IDs are valid UUIDs
        for chunk_id in postgres_ids:
            try:
                uuid.UUID(chunk_id)
            except ValueError:
                pytest.fail(f"Stored chunk ID is not a valid UUID: {chunk_id}")
        
        logger.info(f"Successfully verified {len(postgres_ids)} chunk IDs match across storage systems")


    @pytest.mark.asyncio
    async def test_bridge_chunks_have_valid_uuids(self, sample_document_content):
        """
        Test that bridge chunks also have valid UUIDs.
        
        Validates: Requirement 3.1 - Bridge chunks have valid UUIDs
        """
        from src.multimodal_librarian.components.chunking_framework.framework import (
            GenericMultiLevelChunkingFramework,
        )
        from src.multimodal_librarian.models.core import (
            DocumentContent,
            DocumentMetadata,
        )

        # Create longer document content to generate bridges
        long_text = sample_document_content['text'] * 10  # Repeat to ensure multiple chunks
        
        metadata = DocumentMetadata(
            title=sample_document_content['metadata']['title'],
            author=sample_document_content['metadata']['author'],
            page_count=sample_document_content['metadata']['page_count'],
            file_size=len(long_text)
        )
        
        doc_content = DocumentContent(
            text=long_text,
            images=[],
            tables=[],
            charts=[],
            metadata=metadata
        )
        
        # Process document
        document_id = str(uuid.uuid4())
        framework = GenericMultiLevelChunkingFramework()
        processed_doc = framework.process_document(doc_content, document_id)
        
        # Check bridge chunks if any were generated
        for bridge in processed_doc.bridges:
            assert hasattr(bridge, 'id'), "Bridge chunk should have an id field"
            try:
                uuid.UUID(bridge.id)
            except (ValueError, TypeError):
                pytest.fail(f"Bridge chunk ID is not a valid UUID: {bridge.id}")
        
        logger.info(f"Verified {len(processed_doc.bridges)} bridge chunks have valid UUIDs")


# =============================================================================
# Test 10.2: RAG Search Round-Trip Test (Property 3)
# =============================================================================

class TestRAGSearchRoundTrip:
    """
    Test RAG search round-trip consistency.
    
    Property 3: For any chunk ID returned by semantic search, the System
    SHALL be able to retrieve the corresponding chunk content from PostgreSQL.
    
    Validates: Requirements 2.1, 2.2
    """
    
    @pytest.mark.asyncio
    async def test_search_results_retrievable_from_postgres(
        self,
        sample_document_content,
        mock_postgres_storage,
        mock_milvus_storage
    ):
        """
        Test that chunk IDs returned by search can retrieve content from PostgreSQL.
        
        Validates: Requirement 2.2 - Returned IDs retrieve content from PostgreSQL
        """
        from src.multimodal_librarian.components.chunking_framework.framework import (
            GenericMultiLevelChunkingFramework,
        )
        from src.multimodal_librarian.models.core import (
            DocumentContent,
            DocumentMetadata,
        )

        # Create and process document
        metadata = DocumentMetadata(
            title=sample_document_content['metadata']['title'],
            author=sample_document_content['metadata']['author'],
            page_count=sample_document_content['metadata']['page_count'],
            file_size=sample_document_content['metadata']['file_size']
        )
        
        doc_content = DocumentContent(
            text=sample_document_content['text'],
            images=[],
            tables=[],
            charts=[],
            metadata=metadata
        )
        
        document_id = str(uuid.uuid4())
        framework = GenericMultiLevelChunkingFramework()
        processed_doc = framework.process_document(doc_content, document_id)
        
        # Store chunks in both systems
        for i, chunk in enumerate(processed_doc.chunks):
            chunk_data = {
                'id': chunk.id,
                'content': chunk.content,
                'metadata': chunk.metadata
            }
            await mock_postgres_storage['store_chunk'](document_id, chunk_data, i)
            
            vector_data = {
                'id': chunk.id,
                'content': chunk.content,
                'metadata': {'source_id': document_id, **chunk.metadata}
            }
            await mock_milvus_storage['store_embedding'](vector_data)
        
        # Perform search
        search_results = await mock_milvus_storage['search']("machine learning", top_k=10)
        
        assert len(search_results) > 0, "Search should return results"
        
        # Verify each search result can be retrieved from PostgreSQL
        for result in search_results:
            chunk_id = result['chunk_id']
            
            # Retrieve from PostgreSQL
            pg_chunk = await mock_postgres_storage['get_chunk'](chunk_id)
            
            assert pg_chunk is not None, (
                f"Chunk ID {chunk_id} returned by search not found in PostgreSQL"
            )
            
            # Verify content matches
            assert pg_chunk['content'] == result['content'], (
                f"Content mismatch for chunk {chunk_id}"
            )
        
        logger.info(f"Verified {len(search_results)} search results retrievable from PostgreSQL")


    @pytest.mark.asyncio
    async def test_search_returns_chunks_in_both_systems(
        self,
        sample_document_content,
        mock_postgres_storage,
        mock_milvus_storage
    ):
        """
        Test that semantic search returns chunks that exist in both systems.
        
        Validates: Requirement 2.1 - Search returns chunks in both PostgreSQL and Milvus
        """
        from src.multimodal_librarian.components.chunking_framework.framework import (
            GenericMultiLevelChunkingFramework,
        )
        from src.multimodal_librarian.models.core import (
            DocumentContent,
            DocumentMetadata,
        )

        # Create and process document
        metadata = DocumentMetadata(
            title=sample_document_content['metadata']['title'],
            author=sample_document_content['metadata']['author'],
            page_count=sample_document_content['metadata']['page_count'],
            file_size=sample_document_content['metadata']['file_size']
        )
        
        doc_content = DocumentContent(
            text=sample_document_content['text'],
            images=[],
            tables=[],
            charts=[],
            metadata=metadata
        )
        
        document_id = str(uuid.uuid4())
        framework = GenericMultiLevelChunkingFramework()
        processed_doc = framework.process_document(doc_content, document_id)
        
        # Store chunks in both systems
        for i, chunk in enumerate(processed_doc.chunks):
            chunk_data = {
                'id': chunk.id,
                'content': chunk.content,
                'metadata': chunk.metadata
            }
            await mock_postgres_storage['store_chunk'](document_id, chunk_data, i)
            
            vector_data = {
                'id': chunk.id,
                'content': chunk.content,
                'metadata': {'source_id': document_id, **chunk.metadata}
            }
            await mock_milvus_storage['store_embedding'](vector_data)
        
        # Get all stored IDs
        pg_chunks = await mock_postgres_storage['get_document_chunks'](document_id)
        mv_vectors = await mock_milvus_storage['get_document_vectors'](document_id)
        
        pg_ids = set(pg_chunks.keys())
        mv_ids = set(mv_vectors.keys())
        
        # Verify both systems have the same chunks
        assert pg_ids == mv_ids, (
            f"Chunk IDs don't match.\n"
            f"PostgreSQL: {pg_ids}\n"
            f"Milvus: {mv_ids}"
        )
        
        # Perform search and verify results exist in both
        search_results = await mock_milvus_storage['search']("artificial intelligence", top_k=5)
        
        for result in search_results:
            chunk_id = result['chunk_id']
            assert chunk_id in pg_ids, f"Search result {chunk_id} not in PostgreSQL"
            assert chunk_id in mv_ids, f"Search result {chunk_id} not in Milvus"
        
        logger.info("Verified search returns chunks existing in both storage systems")


# =============================================================================
# Test 10.3: Reprocessing Integration Test
# =============================================================================

class TestDocumentReprocessing:
    """
    Test document reprocessing to verify old chunks are replaced
    and search works after reprocessing.
    
    Validates: Requirement 4.3 - Reprocessed documents are searchable
    """
    
    @pytest.mark.asyncio
    async def test_reprocessing_replaces_old_chunks(
        self,
        sample_document_content,
        mock_postgres_storage,
        mock_milvus_storage
    ):
        """
        Test that reprocessing a document replaces old chunks with new ones.
        
        Validates: Requirement 4.1, 4.2 - Old chunks deleted, new chunks stored
        """
        from src.multimodal_librarian.components.chunking_framework.framework import (
            GenericMultiLevelChunkingFramework,
        )
        from src.multimodal_librarian.models.core import (
            DocumentContent,
            DocumentMetadata,
        )

        # Create document content
        metadata = DocumentMetadata(
            title=sample_document_content['metadata']['title'],
            author=sample_document_content['metadata']['author'],
            page_count=sample_document_content['metadata']['page_count'],
            file_size=sample_document_content['metadata']['file_size']
        )
        
        doc_content = DocumentContent(
            text=sample_document_content['text'],
            images=[],
            tables=[],
            charts=[],
            metadata=metadata
        )
        
        document_id = str(uuid.uuid4())
        framework = GenericMultiLevelChunkingFramework()
        
        # First processing
        processed_doc_1 = framework.process_document(doc_content, document_id)
        original_ids = set()
        
        for i, chunk in enumerate(processed_doc_1.chunks):
            chunk_data = {
                'id': chunk.id,
                'content': chunk.content,
                'metadata': chunk.metadata
            }
            await mock_postgres_storage['store_chunk'](document_id, chunk_data, i)
            
            vector_data = {
                'id': chunk.id,
                'content': chunk.content,
                'metadata': {'source_id': document_id, **chunk.metadata}
            }
            await mock_milvus_storage['store_embedding'](vector_data)
            original_ids.add(chunk.id)
        
        # Simulate reprocessing: delete old chunks first
        await mock_postgres_storage['delete_document_chunks'](document_id)
        await mock_milvus_storage['delete_by_source'](document_id)
        
        # Second processing (reprocessing)
        processed_doc_2 = framework.process_document(doc_content, document_id)
        new_ids = set()
        
        for i, chunk in enumerate(processed_doc_2.chunks):
            chunk_data = {
                'id': chunk.id,
                'content': chunk.content,
                'metadata': chunk.metadata
            }
            await mock_postgres_storage['store_chunk'](document_id, chunk_data, i)
            
            vector_data = {
                'id': chunk.id,
                'content': chunk.content,
                'metadata': {'source_id': document_id, **chunk.metadata}
            }
            await mock_milvus_storage['store_embedding'](vector_data)
            new_ids.add(chunk.id)
        
        # Verify new IDs are different from original IDs
        assert original_ids.isdisjoint(new_ids), (
            f"Reprocessing should generate new UUIDs.\n"
            f"Original IDs: {original_ids}\n"
            f"New IDs: {new_ids}\n"
            f"Overlap: {original_ids & new_ids}"
        )
        
        # Verify old IDs no longer exist
        for old_id in original_ids:
            pg_chunk = await mock_postgres_storage['get_chunk'](old_id)
            assert pg_chunk is None, f"Old chunk {old_id} should be deleted from PostgreSQL"
        
        logger.info(f"Verified reprocessing replaced {len(original_ids)} old chunks with {len(new_ids)} new chunks")


    @pytest.mark.asyncio
    async def test_search_works_after_reprocessing(
        self,
        sample_document_content,
        mock_postgres_storage,
        mock_milvus_storage
    ):
        """
        Test that search works correctly after document reprocessing.
        
        Validates: Requirement 4.3 - Reprocessed documents are searchable
        """
        from src.multimodal_librarian.components.chunking_framework.framework import (
            GenericMultiLevelChunkingFramework,
        )
        from src.multimodal_librarian.models.core import (
            DocumentContent,
            DocumentMetadata,
        )

        # Create document content
        metadata = DocumentMetadata(
            title=sample_document_content['metadata']['title'],
            author=sample_document_content['metadata']['author'],
            page_count=sample_document_content['metadata']['page_count'],
            file_size=sample_document_content['metadata']['file_size']
        )
        
        doc_content = DocumentContent(
            text=sample_document_content['text'],
            images=[],
            tables=[],
            charts=[],
            metadata=metadata
        )
        
        document_id = str(uuid.uuid4())
        framework = GenericMultiLevelChunkingFramework()
        
        # First processing
        processed_doc_1 = framework.process_document(doc_content, document_id)
        
        for i, chunk in enumerate(processed_doc_1.chunks):
            chunk_data = {
                'id': chunk.id,
                'content': chunk.content,
                'metadata': chunk.metadata
            }
            await mock_postgres_storage['store_chunk'](document_id, chunk_data, i)
            
            vector_data = {
                'id': chunk.id,
                'content': chunk.content,
                'metadata': {'source_id': document_id, **chunk.metadata}
            }
            await mock_milvus_storage['store_embedding'](vector_data)
        
        # Simulate reprocessing
        await mock_postgres_storage['delete_document_chunks'](document_id)
        await mock_milvus_storage['delete_by_source'](document_id)
        
        # Second processing
        processed_doc_2 = framework.process_document(doc_content, document_id)
        
        for i, chunk in enumerate(processed_doc_2.chunks):
            chunk_data = {
                'id': chunk.id,
                'content': chunk.content,
                'metadata': chunk.metadata
            }
            await mock_postgres_storage['store_chunk'](document_id, chunk_data, i)
            
            vector_data = {
                'id': chunk.id,
                'content': chunk.content,
                'metadata': {'source_id': document_id, **chunk.metadata}
            }
            await mock_milvus_storage['store_embedding'](vector_data)
        
        # Perform search after reprocessing
        search_results = await mock_milvus_storage['search']("machine learning", top_k=10)
        
        assert len(search_results) > 0, "Search should return results after reprocessing"
        
        # Verify all search results can be retrieved from PostgreSQL
        for result in search_results:
            chunk_id = result['chunk_id']
            pg_chunk = await mock_postgres_storage['get_chunk'](chunk_id)
            
            assert pg_chunk is not None, (
                f"Chunk {chunk_id} from search not found in PostgreSQL after reprocessing"
            )
            assert pg_chunk['content'] == result['content'], (
                f"Content mismatch for chunk {chunk_id} after reprocessing"
            )
        
        logger.info(f"Verified search works after reprocessing with {len(search_results)} results")


# =============================================================================
# Additional Integration Tests
# =============================================================================

class TestChunkIDValidation:
    """
    Test chunk ID validation across the pipeline.
    
    Validates: Requirement 5.1, 5.2, 5.3 - Invalid IDs are rejected
    """
    
    def test_processed_chunk_rejects_invalid_uuid(self):
        """
        Test that ProcessedChunk rejects invalid UUIDs.
        
        Validates: Requirement 5.1 - Invalid UUIDs are rejected
        """
        from src.multimodal_librarian.components.chunking_framework.framework import (
            ProcessedChunk,
        )

        # Valid UUID should work
        valid_chunk = ProcessedChunk(
            id=str(uuid.uuid4()),
            content="Test content",
            start_position=0,
            end_position=12
        )
        assert valid_chunk.id is not None
        
        # Invalid UUID should raise ValueError
        with pytest.raises(ValueError) as exc_info:
            ProcessedChunk(
                id="chunk_0",  # Invalid - not a UUID
                content="Test content",
                start_position=0,
                end_position=12
            )
        
        assert "valid UUID" in str(exc_info.value)
        assert "chunk_0" in str(exc_info.value)
    
    def test_processed_chunk_rejects_empty_id(self):
        """
        Test that ProcessedChunk rejects empty IDs.
        
        Validates: Requirement 5.1 - Empty IDs are rejected
        """
        from src.multimodal_librarian.components.chunking_framework.framework import (
            ProcessedChunk,
        )
        
        with pytest.raises(ValueError) as exc_info:
            ProcessedChunk(
                id="",
                content="Test content",
                start_position=0,
                end_position=12
            )
        
        assert "valid UUID" in str(exc_info.value)


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
