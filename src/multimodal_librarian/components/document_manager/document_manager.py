"""
Document Manager Component.

This component coordinates the complete document lifecycle from upload
through processing, storage, and integration with the knowledge base.
"""

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional
from uuid import UUID

from ...models.core import DocumentContent
from ...models.documents import Document, DocumentStatus
from ...services.processing_service import ProcessingService
from ...services.upload_service import UploadService

logger = logging.getLogger(__name__)


class DocumentManagerError(Exception):
    """Base exception for document manager operations."""
    pass


class DocumentManager:
    """
    Document manager that coordinates document lifecycle operations.
    
    Provides high-level interface for document operations including
    upload, processing, status tracking, and content retrieval.
    """
    
    def __init__(self, upload_service: Optional[UploadService] = None,
                 processing_service: Optional[ProcessingService] = None):
        """
        Initialize document manager.
        
        Args:
            upload_service: Upload service instance
            processing_service: Processing service instance
        """
        self.upload_service = upload_service or UploadService()
        self.processing_service = processing_service or ProcessingService(self.upload_service)
        
        # Document lifecycle statistics
        self.lifecycle_stats = {
            'documents_uploaded': 0,
            'documents_processed': 0,
            'documents_failed': 0,
            'average_processing_time': 0.0,
            'total_content_size': 0
        }
        
        logger.info("Document manager initialized")
    
    async def upload_and_process_document(self, file_data: bytes, filename: str,
                                        title: Optional[str] = None,
                                        description: Optional[str] = None) -> Dict[str, Any]:
        """
        Upload document and start processing workflow.
        
        Args:
            file_data: Document file content
            filename: Original filename
            title: Document title (optional)
            description: Document description (optional)
            
        Returns:
            Dictionary with upload and processing information
            
        Raises:
            DocumentManagerError: If upload or processing setup fails
        """
        try:
            # Upload document
            from ...models.documents import DocumentUploadRequest
            upload_request = DocumentUploadRequest(title=title, description=description)
            
            upload_response = await self.upload_service.upload_document(
                file_data, filename, upload_request
            )
            
            # NOTE: upload_service.upload_document() already queues
            # the Celery task via _queue_for_processing(). Do NOT
            # call processing_service.process_document() here — that
            # caused a double-dispatch bug where two workers ran the
            # full pipeline for the same document, producing duplicate
            # bridges, vectors, and KG nodes.
            
            # Update statistics
            self.lifecycle_stats['documents_uploaded'] += 1
            self.lifecycle_stats['total_content_size'] += len(file_data)
            
            logger.info(f"Document uploaded and processing started: {upload_response.document_id}")
            
            return {
                'document_id': upload_response.document_id,
                'title': upload_response.title,
                'status': upload_response.status,
                'file_size': upload_response.file_size,
                'upload_timestamp': upload_response.upload_timestamp,
                'processing_job_id': str(upload_response.document_id),
                'processing_status': 'queued',
                'estimated_completion': self._estimate_completion_time(len(file_data))
            }
            
        except Exception as e:
            logger.error(f"Failed to upload and process document: {e}")
            raise DocumentManagerError(f"Document upload and processing failed: {e}")
    
    async def get_document_status(self, document_id: UUID) -> Dict[str, Any]:
        """
        Get comprehensive document status including processing progress.
        
        Args:
            document_id: Document identifier
            
        Returns:
            Dictionary with document and processing status
        """
        try:
            # Get document information
            document = await self.upload_service.get_document(document_id)
            if not document:
                raise DocumentManagerError(f"Document not found: {document_id}")
            
            # Build status info from document
            status_info = {
                'document_id': document_id,
                'title': document.title,
                'filename': document.filename,
                'file_size': document.file_size,
                'status': document.status.value if hasattr(document.status, 'value') else str(document.status),
                'upload_timestamp': document.upload_timestamp,
                'processing_started_at': document.processing_started_at,
                'processing_completed_at': document.processing_completed_at,
                'processing_error': document.processing_error
            }
            
            # Try to get processing job details (async method)
            try:
                processing_status = await self.processing_service.get_processing_status(document_id)
                if processing_status:
                    status_info.update({
                        'processing_progress': processing_status.get('progress_percentage', 0),
                        'current_step': processing_status.get('current_step'),
                        'retry_count': processing_status.get('retry_count', 0),
                        'job_metadata': processing_status.get('metadata')
                    })
            except Exception as e:
                logger.debug(f"Could not get processing status for {document_id}: {e}")
            
            # Add enrichment status if available
            enrichment_status = await self._get_enrichment_status(document_id)
            if enrichment_status:
                status_info['enrichment_status'] = enrichment_status
            
            return status_info
            
        except Exception as e:
            logger.error(f"Failed to get document status: {e}")
            raise DocumentManagerError(f"Failed to get document status: {e}")
    
    async def _get_enrichment_status(self, document_id: UUID) -> Optional[Dict[str, Any]]:
        """
        Get enrichment status for a document.
        
        Args:
            document_id: Document identifier
            
        Returns:
            Dictionary with enrichment status or None if not found
        """
        try:
            from sqlalchemy import text

            from ...database.connection import get_database_connection
            
            db_pool = await get_database_connection()
            async with db_pool.acquire() as conn:
                result = await conn.fetchrow(
                    """
                    SELECT state, total_concepts, concepts_enriched,
                           yago_hits, conceptnet_hits, cache_hits,
                           error_count, retry_count, started_at, completed_at,
                           duration_ms, last_error
                    FROM enrichment_status
                    WHERE document_id = $1
                    """,
                    str(document_id)
                )
                
                if result is None:
                    return None
                
                # Calculate progress percentage
                total = result['total_concepts'] or 0
                enriched = result['concepts_enriched'] or 0
                progress = (enriched / total * 100) if total > 0 else 0
                
                return {
                    'state': result['state'],
                    'total_concepts': total,
                    'concepts_enriched': enriched,
                    'progress_percentage': round(progress, 1),
                    'yago_hits': result['yago_hits'] or 0,
                    'conceptnet_hits': result['conceptnet_hits'] or 0,
                    'cache_hits': result['cache_hits'] or 0,
                    'error_count': result['error_count'] or 0,
                    'retry_count': result['retry_count'] or 0,
                    'started_at': result['started_at'].isoformat() if result['started_at'] else None,
                    'completed_at': result['completed_at'].isoformat() if result['completed_at'] else None,
                    'duration_ms': result['duration_ms'],
                    'last_error': result['last_error'],
                }
                
        except Exception as e:
            logger.warning(f"Failed to get enrichment status for {document_id}: {e}")
            return None
    
    async def list_documents_with_status(self, status_filter: Optional[DocumentStatus] = None,
                                       limit: int = 50, offset: int = 0) -> Dict[str, Any]:
        """
        List documents with their processing status.
        
        Args:
            status_filter: Filter by document status
            limit: Maximum number of documents to return
            offset: Number of documents to skip
            
        Returns:
            Dictionary with document list and metadata
        """
        try:
            # Calculate page from offset
            page = (offset // limit) + 1 if limit > 0 else 1
            
            # Call upload_service.list_documents with individual parameters
            document_list = await self.upload_service.list_documents(
                status=status_filter,
                page=page,
                page_size=limit
            )
            
            # Enhance with processing status
            enhanced_documents = []
            for document in document_list.documents:
                # Handle status - it might be an enum or a string
                status_value = document.status.value if hasattr(document.status, 'value') else str(document.status)
                
                doc_info = {
                    'document_id': document.id,
                    'title': document.title,
                    'filename': document.filename,
                    'file_size': document.file_size,
                    'status': status_value,
                    'upload_timestamp': document.upload_timestamp,
                    'processing_completed_at': document.processing_completed_at,
                    'source_type': 'conversation' if document.metadata.get('source_thread_id') else 'upload',
                    'thread_id': document.metadata.get('source_thread_id'),
                }
                
                # Note: Processing job info is available via get_processing_status()
                # but we skip it here to avoid async complexity in the loop
                # The document status from the database is sufficient for listing
                
                enhanced_documents.append(doc_info)
            
            return {
                'documents': enhanced_documents,
                'total_count': document_list.total_count,
                'page': document_list.page,
                'page_size': document_list.page_size,
                'has_more': len(enhanced_documents) == limit
            }
            
        except Exception as e:
            logger.error(f"Failed to list documents: {e}")
            raise DocumentManagerError(f"Failed to list documents: {e}")
    
    async def retry_document_processing(self, document_id: UUID) -> bool:
        """
        Retry processing for a failed document.
        
        This method restarts processing from the failed stage if available,
        otherwise starts from the beginning.
        
        Args:
            document_id: Document identifier
            
        Returns:
            True if retry was initiated
            
        Requirements: 8.4 - Restart processing from appropriate stage
        """
        try:
            # Check if document exists and is in failed state
            document = await self.upload_service.get_document(document_id)
            if not document:
                raise DocumentManagerError(f"Document not found: {document_id}")
            
            if document.status != DocumentStatus.FAILED:
                raise DocumentManagerError(f"Document is not in failed state: {document.status}")
            
            # Get the failed stage from processing job metadata
            failed_stage = await self._get_failed_stage(document_id)
            
            logger.info(f"Retrying document {document_id} from stage: {failed_stage or 'beginning'}")
            
            # Reset document status to processing
            await self.upload_service.update_document_status(
                document_id, DocumentStatus.PROCESSING
            )
            
            # Use CeleryService to retry from the appropriate stage
            # This will read the failed_stage from job_metadata and restart accordingly
            task_id = await self.processing_service.celery_service.retry_from_stage(
                document_id, failed_stage
            )
            
            logger.info(f"Retry initiated for document {document_id} with task {task_id}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to retry document processing: {e}")
            raise DocumentManagerError(f"Failed to retry processing: {e}")
    
    async def _get_failed_stage(self, document_id: UUID) -> Optional[str]:
        """
        Get the failed stage for a document from processing job metadata.
        
        Args:
            document_id: Document identifier
            
        Returns:
            Stage name where processing failed, or None if not found
            
        Requirements: 8.4 - Track failed stage in processing metadata
        """
        try:
            return await self.processing_service.celery_service.get_failed_stage(document_id)
        except Exception as e:
            logger.warning(f"Could not get failed stage for document {document_id}: {e}")
            return None
    
    async def delete_document_completely(self, document_id: UUID) -> Dict[str, Any]:
        """
        Delete document and all associated data from every store.

        Cleans up:
        - Milvus: vector embeddings for this document
        - Neo4j: Concept nodes with source_document = document_id
        - MinIO: the uploaded PDF file
        - PostgreSQL: knowledge_sources (cascades to knowledge_chunks),
          bridge_chunks, processing_jobs, enrichment_status,
          conversation_threads + messages, export_history,
          performance_metrics, user_feedback

        Args:
            document_id: Document identifier

        Returns:
            Dictionary with per-store deletion counts and errors

        Raises:
            DocumentManagerError: If critical deletion fails
        """
        results: Dict[str, Any] = {
            'success': False,
            'milvus_deleted': 0,
            'neo4j_deleted': 0,
            'minio_deleted': False,
            'postgresql_deleted': False,
            'errors': [],
        }
        doc_id = str(document_id)

        try:
            # For conversation documents, chunks/concepts use the
            # raw thread_id as source_id, not the UUID5.  Resolve
            # the correct ID for Milvus/Neo4j cleanup.
            vector_id = doc_id
            try:
                from sqlalchemy import text as sa_text

                from ...database.connection import db_manager
                async with db_manager.get_async_session() as sess:
                    row = (await sess.execute(
                        sa_text(
                            "SELECT source_type, file_path, metadata "
                            "FROM multimodal_librarian.knowledge_sources "
                            "WHERE id = :did"
                        ),
                        {"did": doc_id},
                    )).fetchone()
                if row and row.source_type == "CONVERSATION":
                    tid = None
                    if row.metadata and isinstance(
                        row.metadata, dict
                    ):
                        tid = row.metadata.get("source_thread_id")
                    if not tid and row.file_path:
                        tid = str(row.file_path).replace(
                            "conversation://", ""
                        )
                    if tid:
                        vector_id = tid
            except Exception as e:
                logger.debug(
                    f"Could not resolve conversation thread_id "
                    f"for {doc_id}: {e}"
                )

            # Cancel any active Celery processing
            try:
                await self.processing_service.cancel_processing(
                    document_id
                )
            except Exception:
                pass  # best-effort

            # 1. Milvus — delete vectors
            #    Conversation chunks are stored with source_id = UUID5.
            #    Regular documents use the doc UUID directly.
            #    Delete with BOTH IDs to handle any legacy data.
            milvus_total = 0
            milvus_total += await self._delete_from_milvus(
                doc_id, results
            )
            if vector_id != doc_id:
                milvus_total += await self._delete_from_milvus(
                    vector_id, results
                )
            results['milvus_deleted'] = milvus_total

            # 2. Neo4j — batch-delete Chunk nodes and orphaned Concepts
            #    Conversation Chunk nodes use the raw thread_id as
            #    source_id (set in _persist_concepts).  Regular docs
            #    use the doc UUID.  Delete with BOTH IDs to be safe.
            neo4j_total = 0
            neo4j_total += await self._delete_from_neo4j(
                doc_id, results
            )
            if vector_id != doc_id:
                neo4j_total += await self._delete_from_neo4j(
                    vector_id, results
                )
            results['neo4j_deleted'] = neo4j_total

            # 3. MinIO + PostgreSQL via UploadService
            #    (deletes the S3 object and knowledge_sources row,
            #     which cascades to knowledge_chunks)
            try:
                ok = await self.upload_service.delete_document(
                    document_id
                )
                results['minio_deleted'] = ok
                results['postgresql_deleted'] = ok
                if not ok:
                    results['errors'].append(
                        "Document not found in PostgreSQL"
                    )
            except Exception as e:
                logger.error(
                    f"Failed to delete from MinIO/PostgreSQL: {e}"
                )
                results['errors'].append(
                    f"MinIO/PostgreSQL: {e}"
                )

            # 4. PostgreSQL — clean remaining tables that don't
            #    cascade from knowledge_sources
            await self._delete_pg_extras(doc_id, results)

            results['success'] = results['postgresql_deleted']

            if results['success']:
                logger.info(
                    f"Document deleted: {doc_id} "
                    f"(Milvus: {results['milvus_deleted']}, "
                    f"Neo4j: {results['neo4j_deleted']})"
                )
            else:
                logger.warning(
                    f"Deletion incomplete: {doc_id}, "
                    f"errors: {results['errors']}"
                )

            return results

        except Exception as e:
            logger.error(f"Failed to delete document completely: {e}")
            results['errors'].append(f"Unexpected: {e}")
            raise DocumentManagerError(
                f"Failed to delete document: {e}"
            )

    # ------------------------------------------------------------------
    # Per-store deletion helpers
    # ------------------------------------------------------------------

    async def _delete_from_milvus(
        self, document_id: str, results: Dict[str, Any]
    ) -> int:
        """Delete vectors from Milvus for this document.

        Uses pymilvus directly with a unique connection alias to avoid
        conflicts with the application's existing 'default' connection.
        Wrapped in a 15-second timeout to prevent blocking the event
        loop if Milvus is slow (e.g. after a restart).
        """
        try:
            import asyncio

            return await asyncio.wait_for(
                self._delete_from_milvus_inner(document_id, results),
                timeout=15,
            )
        except asyncio.TimeoutError:
            logger.warning(
                f"Milvus deletion timed out after 15s for {document_id}"
            )
            results['errors'].append("Milvus: timed out after 15s")
            return 0
        except Exception as e:
            logger.warning(f"Milvus deletion failed: {e}")
            results['errors'].append(f"Milvus: {e}")
            return 0

    async def _delete_from_milvus_inner(
        self, document_id: str, results: Dict[str, Any]
    ) -> int:
        """Inner Milvus delete logic (called with timeout wrapper)."""
        import asyncio
        import os

        from pymilvus import Collection, connections, utility

        host = os.environ.get('MILVUS_HOST', 'milvus')
        port = os.environ.get('MILVUS_PORT', '19530')
        collection_name = os.environ.get(
            'MILVUS_COLLECTION_NAME', 'knowledge_chunks'
        )
        alias = f"delete_{document_id[:8]}"

        loop = asyncio.get_event_loop()

        await loop.run_in_executor(
            None,
            lambda: connections.connect(
                alias=alias, host=host, port=port, timeout=10,
            ),
        )
        try:
            has = await loop.run_in_executor(
                None,
                lambda: utility.has_collection(
                    collection_name, using=alias
                ),
            )
            if not has:
                logger.warning(
                    f"Milvus collection '{collection_name}' "
                    "not found"
                )
                return 0

            col = await loop.run_in_executor(
                None,
                lambda: Collection(
                    collection_name, using=alias
                ),
            )
            await loop.run_in_executor(None, col.load)

            expr = (
                f'metadata["source_id"] == "{document_id}"'
            )
            mut = await loop.run_in_executor(
                None, col.delete, expr
            )
            # NOTE: col.flush() removed — it can block indefinitely
            # after Milvus restarts.  Milvus auto-flushes deletes.

            deleted = (
                mut.delete_count
                if hasattr(mut, 'delete_count')
                else 0
            )
            logger.info(
                f"Milvus: deleted {deleted} vectors "
                f"for {document_id}"
            )
            return deleted
        finally:
            await loop.run_in_executor(
                None, connections.disconnect, alias
            )

    async def _delete_from_neo4j(
        self, document_id: str, results: Dict[str, Any]
    ) -> int:
        """Delete Chunk nodes, EXTRACTED_FROM relationships, and orphaned Concepts from Neo4j."""
        try:
            import asyncio

            return await asyncio.wait_for(
                self._delete_from_neo4j_inner(document_id, results),
                timeout=30,
            )
        except asyncio.TimeoutError:
            logger.warning(
                f"Neo4j deletion timed out after 30s for {document_id}"
            )
            results['errors'].append("Neo4j: timed out after 30s")
            return 0
        except Exception as e:
            logger.warning(f"Neo4j deletion failed: {e}")
            results['errors'].append(f"Neo4j: {e}")
            return 0

    async def _delete_from_neo4j_inner(
        self, document_id: str, results: Dict[str, Any]
    ) -> int:
        """Inner Neo4j delete logic (called with timeout wrapper)."""
        try:
            from ...services.knowledge_graph_service import KnowledgeGraphService
            kg = KnowledgeGraphService()
            await kg.client.connect()
            try:
                # Step 1: Delete EXTRACTED_FROM relationships to this source's Chunk nodes
                res_rels = await kg.client.execute_write_query(
                    """
                    MATCH (ch:Chunk {source_id: $doc_id})<-[r:EXTRACTED_FROM]-(c:Concept)
                    DELETE r
                    RETURN count(r) AS deleted_rels
                    """,
                    {"doc_id": document_id},
                )
                deleted_rels = res_rels[0]["deleted_rels"] if res_rels else 0

                # Step 2: Delete Chunk nodes for this source_id
                res_chunks = await kg.client.execute_write_query(
                    """
                    MATCH (ch:Chunk {source_id: $doc_id})
                    DELETE ch
                    RETURN count(ch) AS deleted_chunks
                    """,
                    {"doc_id": document_id},
                )
                deleted_chunks = res_chunks[0]["deleted_chunks"] if res_chunks else 0

                # Step 3: Delete orphaned Concepts (no remaining EXTRACTED_FROM and no SAME_AS)
                res_concepts = await kg.client.execute_write_query(
                    """
                    MATCH (c:Concept)
                    WHERE NOT EXISTS { MATCH (c)-[:EXTRACTED_FROM]->() }
                      AND NOT EXISTS { MATCH (c)<-[:SAME_AS]-() }
                    DETACH DELETE c
                    RETURN count(c) AS deleted_concepts
                    """,
                    {},
                )
                deleted_concepts = res_concepts[0]["deleted_concepts"] if res_concepts else 0

                # Also remove Document nodes if any
                try:
                    await kg.client.execute_write_query(
                        """
                        MATCH (d:Document {document_id: $doc_id})
                        DETACH DELETE d
                        """,
                        {"doc_id": document_id},
                    )
                except Exception:
                    pass

                total = deleted_rels + deleted_chunks + deleted_concepts
                logger.info(
                    f"Neo4j: deleted {deleted_rels} EXTRACTED_FROM rels, "
                    f"{deleted_chunks} Chunk nodes, "
                    f"{deleted_concepts} orphaned Concepts "
                    f"for {document_id}"
                )
                return total
            finally:
                await kg.client.disconnect()
        except Exception as e:
            logger.warning(f"Neo4j deletion failed: {e}")
            results['errors'].append(f"Neo4j: {e}")
            return 0

    async def _delete_pg_extras(
        self, document_id: str, results: Dict[str, Any]
    ) -> None:
        """
        Delete rows from PostgreSQL tables that don't cascade
        from knowledge_sources.
        """
        from sqlalchemy import text

        from ...database.connection import db_manager

        if not db_manager.AsyncSessionLocal:
            db_manager.initialize()

        tables_and_cols = [
            ("bridge_chunks", "source_id"),
            ("processing_jobs", "source_id"),
            ("enrichment_status", "document_id"),
            ("export_history", "document_id"),
            ("performance_metrics", "document_id"),
            ("user_feedback", "document_id"),
        ]
        try:
            async with db_manager.get_async_session() as session:
                for table, col in tables_and_cols:
                    try:
                        await session.execute(
                            text(
                                f"DELETE FROM multimodal_librarian.{table} "
                                f"WHERE {col} = :doc_id"
                            ),
                            {"doc_id": document_id},
                        )
                    except Exception as te:
                        logger.debug(
                            f"PG cleanup {table}: {te}"
                        )
                # Conversations referencing this document
                try:
                    await session.execute(
                        text(
                            "DELETE FROM multimodal_librarian.messages "
                            "WHERE thread_id IN ("
                            "  SELECT id "
                            "  FROM multimodal_librarian.conversation_threads "
                            "  WHERE metadata::text LIKE :pattern"
                            ")"
                        ),
                        {"pattern": f"%{document_id}%"},
                    )
                    await session.execute(
                        text(
                            "DELETE FROM multimodal_librarian.conversation_threads "
                            "WHERE metadata::text LIKE :pattern"
                        ),
                        {"pattern": f"%{document_id}%"},
                    )
                except Exception as ce:
                    logger.debug(f"PG conversation cleanup: {ce}")
        except Exception as e:
            logger.warning(f"PG extras cleanup failed: {e}")
            results['errors'].append(f"PG extras: {e}")
    
    async def get_document_content_summary(self, document_id: UUID) -> Optional[Dict[str, Any]]:
        """
        Get summary of processed document content.
        
        Args:
            document_id: Document identifier
            
        Returns:
            Dictionary with content summary or None if not processed
        """
        try:
            # Check if document is processed
            document = await self.upload_service.get_document(document_id)
            if not document or document.status != DocumentStatus.COMPLETED:
                return None
            
            # Build basic summary from document
            summary = {
                'document_id': document_id,
                'title': document.title,
                'processing_completed_at': document.processing_completed_at,
                'file_size': document.file_size
            }
            
            # Try to get processing status for additional metadata
            try:
                processing_status = await self.processing_service.get_processing_status(document_id)
                if processing_status and processing_status.get('metadata'):
                    metadata = processing_status['metadata']
                    
                    # Add PDF processing info
                    if 'pdf_processing' in metadata:
                        pdf_info = metadata['pdf_processing']
                        summary.update({
                            'text_length': pdf_info.get('text_length', 0),
                            'page_count': pdf_info.get('page_count', 0),
                            'image_count': pdf_info.get('image_count', 0),
                            'table_count': pdf_info.get('table_count', 0),
                            'chart_count': pdf_info.get('chart_count', 0)
                        })
                    
                    # Add chunking info
                    if 'chunking' in metadata:
                        chunking_info = metadata['chunking']
                        summary.update({
                            'chunk_count': chunking_info.get('chunk_count', 0),
                            'bridge_count': chunking_info.get('bridge_count', 0),
                            'content_type': chunking_info.get('content_type', 'unknown'),
                            'complexity_score': chunking_info.get('complexity_score', 0.0)
                        })
                    
                    # Add vector storage info
                    if 'vector_storage' in metadata:
                        vector_info = metadata['vector_storage']
                        summary.update({
                            'chunks_stored': vector_info.get('chunks_stored', 0),
                            'bridges_stored': vector_info.get('bridges_stored', 0)
                        })
            except Exception as e:
                logger.debug(f"Could not get processing metadata for {document_id}: {e}")
            
            return summary
            
        except Exception as e:
            logger.error(f"Failed to get document content summary: {e}")
            return None
    
    def get_active_processing_jobs(self) -> List[Dict[str, Any]]:
        """
        Get information about all active processing jobs.
        
        Returns:
            List of active job information
        """
        active_jobs = self.processing_service.get_active_jobs()
        
        job_info = []
        for job in active_jobs:
            info = {
                'document_id': job.get('document_id'),
                'status': job.get('status'),
                'progress_percentage': job.get('progress_percentage', 0),
                'current_step': job.get('current_step'),
                'started_at': job.get('started_at'),
                'retry_count': job.get('retry_count', 0),
                'estimated_completion': self._estimate_job_completion(job)
            }
            job_info.append(info)
        
        return job_info
    
    def _estimate_completion_time(self, file_size: int) -> Optional[datetime]:
        """
        Estimate processing completion time based on file size.
        
        Args:
            file_size: Size of the file in bytes
            
        Returns:
            Estimated completion datetime
        """
        # Simple heuristic: ~1MB per minute processing time
        estimated_minutes = max(1, file_size // (1024 * 1024))
        return datetime.utcnow() + timedelta(minutes=estimated_minutes)
    
    def _estimate_job_completion(self, job: Dict[str, Any]) -> Optional[datetime]:
        """
        Estimate when a job will complete based on current progress.
        
        Args:
            job: Processing job dictionary
            
        Returns:
            Estimated completion datetime
        """
        started_at = job.get('started_at')
        progress_percentage = job.get('progress_percentage', 0)
        
        if not started_at or progress_percentage <= 0:
            return None
        
        # Convert started_at to datetime if it's a string
        if isinstance(started_at, str):
            from datetime import datetime
            started_at = datetime.fromisoformat(started_at.replace('Z', '+00:00'))
        
        elapsed = (datetime.utcnow() - started_at).total_seconds()
        if progress_percentage >= 100:
            return datetime.utcnow()
        
        # Estimate remaining time based on current progress
        estimated_total_time = elapsed / (progress_percentage / 100.0)
        remaining_time = estimated_total_time - elapsed
        
        return datetime.utcnow() + timedelta(seconds=remaining_time)
    
    def get_manager_statistics(self) -> Dict[str, Any]:
        """
        Get comprehensive document manager statistics.
        
        Returns:
            Dictionary with manager statistics
        """
        # Get component statistics
        upload_stats = self.upload_service.get_upload_statistics()
        processing_stats = self.processing_service.get_processing_statistics()
        
        # Combine with lifecycle statistics
        combined_stats = {
            'lifecycle': self.lifecycle_stats,
            'upload_service': upload_stats,
            'processing_service': processing_stats,
            'active_jobs': len(self.processing_service.get_active_jobs())
        }
        
        return combined_stats
    
    def health_check(self) -> Dict[str, Any]:
        """
        Perform comprehensive health check.
        
        Returns:
            Health status information
        """
        try:
            # Check component health
            upload_health = self.upload_service.get_upload_statistics()
            processing_health = self.processing_service.health_check()
            
            overall_status = 'healthy'
            if processing_health.get('status') != 'healthy':
                overall_status = 'degraded'
            
            return {
                'status': overall_status,
                'upload_service': {
                    'status': 'healthy',
                    'storage_service': upload_health.get('storage_service_status', {})
                },
                'processing_service': processing_health,
                'knowledge_graph': {
                    'status': processing_health.get('knowledge_graph', 'unknown'),
                    'statistics': self.processing_service.get_knowledge_graph_statistics()
                },
                'active_jobs': len(self.processing_service.get_active_jobs()),
                'total_documents': upload_health.get('total_documents', 0)
            }
            
        except Exception as e:
            return {
                'status': 'unhealthy',
                'error': str(e)
            }
    
    async def search_document_knowledge(self, document_id: UUID, query: str, 
                                      max_results: int = 10) -> Dict[str, Any]:
        """
        Search knowledge graph within a specific document.
        
        Args:
            document_id: Document identifier
            query: Search query
            max_results: Maximum number of results
            
        Returns:
            Dictionary with search results
        """
        try:
            return await self.processing_service.search_document_knowledge(
                document_id, query, max_results
            )
        except Exception as e:
            logger.error(f"Failed to search document knowledge: {e}")
            raise DocumentManagerError(f"Knowledge search failed: {e}")
    
    async def get_document_knowledge_summary(self, document_id: UUID) -> Dict[str, Any]:
        """
        Get knowledge graph summary for a document.
        
        Args:
            document_id: Document identifier
            
        Returns:
            Dictionary with knowledge summary
        """
        try:
            return await self.processing_service.get_document_knowledge_summary(document_id)
        except Exception as e:
            logger.error(f"Failed to get document knowledge summary: {e}")
            raise DocumentManagerError(f"Knowledge summary failed: {e}")
    
    async def process_knowledge_feedback(self, feedback_data: Dict[str, Any]) -> bool:
        """
        Process user feedback about knowledge graph elements.
        
        Args:
            feedback_data: Feedback information
            
        Returns:
            True if feedback was processed successfully
        """
        try:
            return await self.processing_service.process_knowledge_feedback(feedback_data)
        except Exception as e:
            logger.error(f"Failed to process knowledge feedback: {e}")
            raise DocumentManagerError(f"Knowledge feedback processing failed: {e}")


from datetime import timedelta
