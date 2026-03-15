"""
Chunk Resolver Component for Knowledge Graph-Guided Retrieval.

This component resolves chunk IDs from Neo4j source_chunks to actual chunk
content from OpenSearch/Milvus. It handles batch resolution with parallel
requests and graceful handling of missing chunks.

Requirements: 1.2, 1.4
"""

import asyncio
import logging
from typing import Any, Dict, List, Optional

from ...models.kg_retrieval import ChunkSourceMapping, RetrievalSource, RetrievedChunk

logger = logging.getLogger(__name__)


class ChunkResolver:
    """
    Resolves chunk IDs from Neo4j to actual content from vector store.

    Handles batch resolution with parallel requests and graceful
    handling of missing chunks. Works with both Milvus (local) and
    OpenSearch (AWS) via the VectorStoreClient protocol.

    Follows FastAPI DI patterns - no connections at construction time.
    """

    def __init__(self, vector_client: Optional[Any] = None):
        """
        Initialize ChunkResolver with optional vector store client.

        Args:
            vector_client: Vector store client (Milvus or OpenSearch)
                          injected via DI. If None, resolution fails.
        """
        self._vector_client = vector_client
        logger.debug("ChunkResolver initialized")

    async def resolve_chunks(
        self,
        chunk_ids: List[str],
        source_info: Dict[str, ChunkSourceMapping],
    ) -> List[RetrievedChunk]:
        """
        Resolve chunk IDs to full chunk content.

        OPTIMIZED: Uses batch fetching when available, falls back to parallel
        individual requests. Missing chunks are logged and skipped gracefully.

        Args:
            chunk_ids: List of chunk IDs to resolve
            source_info: Mapping of chunk_id to ChunkSourceMapping

        Returns:
            List of RetrievedChunk with content populated.
            Missing chunks are excluded from the result.

        Validates: Requirements 1.2, 1.4
        """
        if not chunk_ids:
            logger.debug("No chunk IDs provided to resolve")
            return []

        if not self._vector_client:
            logger.warning("No vector client available for chunk resolution")
            return []

        # Deduplicate chunk IDs while preserving order
        seen_ids: set = set()
        unique_ids: List[str] = []
        for chunk_id in chunk_ids:
            if chunk_id and chunk_id not in seen_ids:
                seen_ids.add(chunk_id)
                unique_ids.append(chunk_id)

        if not unique_ids:
            logger.debug("No valid chunk IDs after deduplication")
            return []

        logger.debug(f"Resolving {len(unique_ids)} chunks")

        # OPTIMIZATION: Try batch fetch first (more efficient)
        if hasattr(self._vector_client, 'get_chunks_by_ids'):
            try:
                return await self._resolve_chunks_batch(unique_ids, source_info)
            except Exception as e:
                logger.warning(f"Batch fetch failed, falling back to parallel: {e}")

        # Fallback: Parallel individual resolution
        return await self._resolve_chunks_parallel(unique_ids, source_info)

    async def _resolve_chunks_batch(
        self,
        chunk_ids: List[str],
        source_info: Dict[str, ChunkSourceMapping],
        timeout_seconds: float = 10.0,
    ) -> List[RetrievedChunk]:
        """
        Resolve chunks using batch fetch (more efficient).

        Automatically splits into sub-batches to stay within Milvus's
        16,384 query window limit.

        Args:
            chunk_ids: List of chunk IDs to resolve
            source_info: Mapping of chunk_id to ChunkSourceMapping
            timeout_seconds: Max seconds to wait for vector store

        Returns:
            List of RetrievedChunk with content populated
        """
        BATCH_SIZE = 8000  # Stay well under Milvus's 16,384 limit

        # If small enough, fetch in one go
        if len(chunk_ids) <= BATCH_SIZE:
            return await self._resolve_single_batch(
                chunk_ids, source_info, timeout_seconds
            )

        # Split into sub-batches
        resolved_chunks: List[RetrievedChunk] = []
        for i in range(0, len(chunk_ids), BATCH_SIZE):
            batch = chunk_ids[i:i + BATCH_SIZE]
            batch_result = await self._resolve_single_batch(
                batch, source_info, timeout_seconds
            )
            resolved_chunks.extend(batch_result)

        logger.info(
            f"Batch resolved {len(resolved_chunks)}/{len(chunk_ids)} chunks "
            f"in {(len(chunk_ids) + BATCH_SIZE - 1) // BATCH_SIZE} sub-batches"
        )
        return resolved_chunks

    async def _resolve_single_batch(
        self,
        chunk_ids: List[str],
        source_info: Dict[str, ChunkSourceMapping],
        timeout_seconds: float = 10.0,
    ) -> List[RetrievedChunk]:
        """Resolve a single batch of chunk IDs from the vector store."""
        method = self._vector_client.get_chunks_by_ids
        if asyncio.iscoroutinefunction(method):
            coro = method(chunk_ids)
        else:
            loop = asyncio.get_event_loop()
            coro = loop.run_in_executor(None, method, chunk_ids)

        try:
            chunks_data = await asyncio.wait_for(
                coro, timeout=timeout_seconds
            )
        except asyncio.TimeoutError:
            logger.warning(
                f"Batch chunk resolution timed out after "
                f"{timeout_seconds}s for {len(chunk_ids)} chunks"
            )
            return []
        
        if not chunks_data:
            return []
        
        resolved_chunks: List[RetrievedChunk] = []
        for chunk_data in chunks_data:
            chunk_id = chunk_data.get('id', chunk_data.get('chunk_id', ''))
            if not chunk_id:
                continue
                
            chunk = self._build_retrieved_chunk(
                chunk_id, chunk_data, source_info.get(chunk_id)
            )
            if chunk:
                resolved_chunks.append(chunk)
        
        logger.info(f"Batch resolved {len(resolved_chunks)}/{len(chunk_ids)} chunks")
        return resolved_chunks

    async def _resolve_chunks_parallel(
        self,
        chunk_ids: List[str],
        source_info: Dict[str, ChunkSourceMapping],
    ) -> List[RetrievedChunk]:
        """
        Resolve chunks using parallel individual requests (fallback).
        
        Args:
            chunk_ids: List of chunk IDs to resolve
            source_info: Mapping of chunk_id to ChunkSourceMapping
            
        Returns:
            List of RetrievedChunk with content populated
        """
        # Create tasks for parallel resolution
        tasks = [
            self._resolve_single_chunk(chunk_id, source_info.get(chunk_id))
            for chunk_id in chunk_ids
        ]

        # Execute all tasks in parallel
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Collect successful results and log failures
        resolved_chunks: List[RetrievedChunk] = []
        failed_ids: List[str] = []

        for chunk_id, result in zip(chunk_ids, results):
            if isinstance(result, Exception):
                logger.warning(f"Exception resolving {chunk_id}: {result}")
                failed_ids.append(chunk_id)
            elif result is None:
                failed_ids.append(chunk_id)
            elif isinstance(result, RetrievedChunk):
                resolved_chunks.append(result)

        if failed_ids:
            preview = failed_ids[:5]
            suffix = '...' if len(failed_ids) > 5 else ''
            logger.warning(
                f"Failed to resolve {len(failed_ids)}: {preview}{suffix}"
            )

        logger.info(
            f"Parallel resolved {len(resolved_chunks)}/{len(chunk_ids)} chunks"
        )
        return resolved_chunks

    def _build_retrieved_chunk(
        self,
        chunk_id: str,
        chunk_data: Dict[str, Any],
        source_mapping: Optional[ChunkSourceMapping],
    ) -> Optional[RetrievedChunk]:
        """
        Build a RetrievedChunk from chunk data.
        
        OPTIMIZED: Now passes through the embedding from Milvus to avoid
        regenerating it during semantic reranking.
        
        Args:
            chunk_id: Chunk ID
            chunk_data: Raw chunk data from vector store
            source_mapping: Optional mapping with provenance information
            
        Returns:
            RetrievedChunk or None if invalid data
        """
        # Extract content from chunk data
        content = chunk_data.get('content', '')
        if not content:
            content = chunk_data.get('text', '')
        
        if not content:
            return None

        # Determine retrieval source from mapping or default
        if source_mapping:
            source = source_mapping.retrieval_source
            concept_name = source_mapping.source_concept_name
            relationship_path = source_mapping.relationship_path
            kg_relevance_score = source_mapping.get_relevance_score()
        else:
            source = RetrievalSource.DIRECT_CONCEPT
            concept_name = None
            relationship_path = None
            kg_relevance_score = 1.0

        # Build metadata from chunk data
        chunk_metadata = chunk_data.get('metadata', {})
        metadata: Dict[str, Any] = {}
        metadata_keys = [
            'source_id', 'source_type', 'title', 'document_title', 'page_number',
            'chunk_index', 'doc_id', 'document_id'
        ]
        for key in metadata_keys:
            if key in chunk_data:
                metadata[key] = chunk_data[key]
            elif key in chunk_metadata:
                metadata[key] = chunk_metadata[key]

        # Fallback: extract page number from [Page N] markers in content
        if not metadata.get('page_number') and content:
            import re
            m = re.search(r'\[Page\s+(\d+)', content)
            if m:
                try:
                    metadata['page_number'] = int(m.group(1))
                except ValueError:
                    pass

        # OPTIMIZATION: Extract embedding from chunk data to avoid regeneration
        embedding = chunk_data.get('embedding')
        if embedding is None:
            embedding = chunk_data.get('vector')

        return RetrievedChunk(
            chunk_id=chunk_id,
            content=content,
            source=source,
            concept_name=concept_name,
            relationship_path=relationship_path,
            kg_relevance_score=kg_relevance_score,
            semantic_score=0.0,
            final_score=kg_relevance_score,
            metadata=metadata,
            embedding=embedding,
        )

    async def _resolve_single_chunk(
        self,
        chunk_id: str,
        source_mapping: Optional[ChunkSourceMapping],
    ) -> Optional[RetrievedChunk]:
        """
        Resolve a single chunk ID to full content.

        OPTIMIZED: Now passes through the embedding from Milvus.

        Args:
            chunk_id: ID of the chunk to resolve
            source_mapping: Optional mapping with provenance information

        Returns:
            RetrievedChunk with content or None if not found

        Validates: Requirements 1.2, 1.4
        """
        if not chunk_id:
            return None

        if not self._vector_client:
            logger.warning("No vector client for single chunk resolution")
            return None

        try:
            # Check if client has async method, otherwise wrap sync call
            if hasattr(self._vector_client, 'get_chunk_by_id'):
                method = self._vector_client.get_chunk_by_id
                if asyncio.iscoroutinefunction(method):
                    chunk_data = await method(chunk_id)
                else:
                    # Wrap sync call in executor to avoid blocking
                    loop = asyncio.get_event_loop()
                    chunk_data = await loop.run_in_executor(
                        None, method, chunk_id
                    )
            else:
                logger.warning("Vector client missing get_chunk_by_id method")
                return None

            if not chunk_data:
                logger.debug(f"Chunk not found: {chunk_id}")
                return None

            # Extract content from chunk data
            content = chunk_data.get('content', '')
            if not content:
                content = chunk_data.get('text', '')

            # Determine retrieval source from mapping or default
            if source_mapping:
                source = source_mapping.retrieval_source
                concept_name = source_mapping.source_concept_name
                relationship_path = source_mapping.relationship_path
                kg_relevance_score = source_mapping.get_relevance_score()
            else:
                source = RetrievalSource.DIRECT_CONCEPT
                concept_name = None
                relationship_path = None
                kg_relevance_score = 1.0

            # Build metadata from chunk data
            # Metadata can be at top level or nested in 'metadata' key
            chunk_metadata = chunk_data.get('metadata', {})
            metadata: Dict[str, Any] = {}
            metadata_keys = [
                'source_id', 'source_type', 'title', 'document_title',
                'page_number', 'chunk_index', 'doc_id', 'document_id'
            ]
            for key in metadata_keys:
                # Check both top-level and nested metadata
                if key in chunk_data:
                    metadata[key] = chunk_data[key]
                elif key in chunk_metadata:
                    metadata[key] = chunk_metadata[key]

            # Fallback: extract page number from [Page N] markers in content
            if not metadata.get('page_number') and content:
                import re
                m = re.search(r'\[Page\s+(\d+)', content)
                if m:
                    try:
                        metadata['page_number'] = int(m.group(1))
                    except ValueError:
                        pass

            # OPTIMIZATION: Extract embedding to avoid regeneration
            embedding = chunk_data.get('embedding')
            if embedding is None:
                embedding = chunk_data.get('vector')

            return RetrievedChunk(
                chunk_id=chunk_id,
                content=content,
                source=source,
                concept_name=concept_name,
                relationship_path=relationship_path,
                kg_relevance_score=kg_relevance_score,
                semantic_score=0.0,
                final_score=kg_relevance_score,
                metadata=metadata,
                embedding=embedding,
            )

        except Exception as e:
            logger.warning(f"Error resolving chunk {chunk_id}: {e}")
            return None

    def set_vector_client(self, client: Any) -> None:
        """
        Set the vector client after initialization.

        Useful for lazy initialization or testing.

        Args:
            client: Vector store client instance
        """
        self._vector_client = client
        logger.debug("Vector client set on ChunkResolver")

    @property
    def has_vector_client(self) -> bool:
        """Check if vector client is available."""
        return self._vector_client is not None
