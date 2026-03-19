"""
Chat Document WebSocket Message Handlers.

This module provides WebSocket message handlers for document operations
within the chat interface, including upload, list, delete, and retry.

Requirements: 1.1, 7.2, 8.3, 8.4
"""

import base64
import logging
from datetime import datetime
from typing import TYPE_CHECKING, Optional
from uuid import UUID, uuid4

from ..models.chat_document_models import (
    ChatUploadMessage,
    DocumentDeletedMessage,
    DocumentDeleteRequest,
    DocumentInfo,
    DocumentListMessage,
    DocumentListRequest,
    DocumentRetryRequest,
    DocumentRetryStartedMessage,
    DocumentUploadErrorCodes,
    DocumentUploadErrorMessage,
    DocumentUploadStartedMessage,
    RelatedDocsGraphEdge,
    RelatedDocsGraphError,
    RelatedDocsGraphNode,
    RelatedDocsGraphResponse,
)

if TYPE_CHECKING:
    from ...components.document_manager.document_manager import DocumentManager
    from ...services.processing_status_service import ProcessingStatusService
    from ..dependencies.services import ConnectionManager

logger = logging.getLogger(__name__)

# Constants for validation
MAX_FILE_SIZE_BYTES = 100 * 1024 * 1024  # 100MB
SUPPORTED_MIME_TYPES = ["application/pdf"]


async def handle_chat_document_upload(
    message_data: dict,
    connection_id: str,
    manager: "ConnectionManager",
    document_manager: "DocumentManager",
    processing_status_service: Optional["ProcessingStatusService"] = None
) -> None:
    """
    Handle document upload initiated from chat interface.
    
    This handler validates the uploaded file, decodes the base64 content,
    and initiates document processing through the DocumentManager.
    Status updates are sent via the ProcessingStatusService.
    
    Args:
        message_data: Upload message with file data
        connection_id: WebSocket connection ID
        manager: Connection manager for sending responses
        document_manager: Document manager for processing
        processing_status_service: Optional status service for progress updates
        
    Requirements: 1.1, 1.4, 1.5, 7.2
    """
    try:
        # Parse and validate the upload message
        try:
            upload_msg = ChatUploadMessage(**message_data)
        except Exception as e:
            logger.error(f"Invalid upload message format: {e}")
            await _send_upload_error(
                manager, connection_id,
                filename=message_data.get('filename', 'unknown'),
                error_code=DocumentUploadErrorCodes.UNKNOWN_ERROR,
                error_message=f"Invalid message format: {str(e)}"
            )
            return
        
        # Validate file type (Requirement 1.4)
        if upload_msg.content_type not in SUPPORTED_MIME_TYPES:
            logger.warning(f"Rejected non-PDF file: {upload_msg.filename} ({upload_msg.content_type})")
            await _send_upload_error(
                manager, connection_id,
                filename=upload_msg.filename,
                error_code=DocumentUploadErrorCodes.INVALID_FILE_TYPE,
                error_message="Only PDF files are supported for document cataloging"
            )
            return
        
        # Validate file size (Requirement 1.5)
        if upload_msg.file_size > MAX_FILE_SIZE_BYTES:
            logger.warning(f"Rejected oversized file: {upload_msg.filename} ({upload_msg.file_size} bytes)")
            await _send_upload_error(
                manager, connection_id,
                filename=upload_msg.filename,
                error_code=DocumentUploadErrorCodes.FILE_TOO_LARGE,
                error_message=f"File exceeds 100MB limit. Please upload a smaller file."
            )
            return
        
        # Decode base64 file data
        try:
            file_data = base64.b64decode(upload_msg.file_data)
        except Exception as e:
            logger.error(f"Failed to decode base64 file data: {e}")
            await _send_upload_error(
                manager, connection_id,
                filename=upload_msg.filename,
                error_code=DocumentUploadErrorCodes.INVALID_BASE64,
                error_message="Failed to decode file data"
            )
            return
        
        # Verify decoded size matches declared size
        if len(file_data) != upload_msg.file_size:
            logger.warning(f"File size mismatch: declared {upload_msg.file_size}, actual {len(file_data)}")
            # Allow some tolerance for encoding differences
            if abs(len(file_data) - upload_msg.file_size) > 1024:  # 1KB tolerance
                await _send_upload_error(
                    manager, connection_id,
                    filename=upload_msg.filename,
                    error_code=DocumentUploadErrorCodes.UNKNOWN_ERROR,
                    error_message="File size mismatch after decoding"
                )
                return
        
        # Generate document ID
        document_id = uuid4()
        
        # Start document processing first to check for duplicates
        # before creating any UI elements
        try:
            result = await document_manager.upload_and_process_document(
                file_data=file_data,
                filename=upload_msg.filename,
                title=upload_msg.title,
                description=upload_msg.description
            )
            
            # Use the actual document_id from the database (not the
            # locally generated one) so the tracker matches what
            # Celery workers report progress against.
            actual_document_id = result.get('document_id', document_id)
            
            # Only register and send started message after we know
            # it's not a duplicate
            if processing_status_service:
                await processing_status_service.register_upload(
                    document_id=actual_document_id,
                    connection_id=connection_id,
                    filename=upload_msg.filename
                )
            
            # Send upload started message
            started_msg = DocumentUploadStartedMessage(
                document_id=str(actual_document_id),
                filename=upload_msg.filename,
                file_size=len(file_data)
            )
            await manager.send_personal_message(
                started_msg.model_dump(mode='json'), connection_id
            )
            
            logger.info(f"Document upload initiated: {result.get('document_id')}")
            
        except Exception as e:
            error_str = str(e)
            logger.error(f"Document processing failed: {error_str}")
            
            # Determine error code based on error type
            error_code = DocumentUploadErrorCodes.PROCESSING_FAILED
            error_message = f"Failed to process document: {error_str}"
            retry_available = True
            
            # Check for duplicate document error
            if "already exists" in error_str.lower() or "duplicate" in error_str.lower():
                error_code = DocumentUploadErrorCodes.DUPLICATE_DOCUMENT
                # Extract the cleaner message
                if "Document already exists:" in error_str:
                    error_message = error_str.split("Document already exists:")[-1].strip().strip("'\"")
                    error_message = f"Document already exists: {error_message}"
                else:
                    error_message = "A document with the same content already exists"
                retry_available = False
            
            # Send error via upload error message only (not processing status)
            # to avoid duplicate error messages in the UI
            await _send_upload_error(
                manager, connection_id,
                filename=upload_msg.filename,
                error_code=error_code,
                error_message=error_message
            )
            
    except Exception as e:
        logger.error(f"Unexpected error in chat document upload: {e}")
        await _send_upload_error(
            manager, connection_id,
            filename=message_data.get('filename', 'unknown'),
            error_code=DocumentUploadErrorCodes.UNKNOWN_ERROR,
            error_message="An unexpected error occurred during upload"
        )


async def _fetch_document_stats(document_ids: list) -> dict:
    """Fetch chunk/bridge/concept/relationship stats for a batch of documents.
    
    Returns dict keyed by document_id string with stats sub-dicts.
    
    For conversation documents, the knowledge_sources.id is a UUID5 derived
    from the thread_id. Chunks in PostgreSQL are stored under the raw
    thread_id, while concepts in Neo4j are stored under the UUID5 source_id.
    This function resolves that mapping so stats are found correctly.
    """
    stats = {}
    if not document_ids:
        return stats

    # Build a mapping: query_id -> original_doc_id
    # For conversations, query_id = source_thread_id (raw thread UUID)
    # For regular docs, query_id = document_id (same)
    query_to_doc: dict = {}  # query_id_str -> doc_id_str
    all_query_ids = []       # UUIDs to use in SQL queries

    try:
        from ...database.connection import get_async_connection
        conn = await get_async_connection()
        try:
            # Look up conversation documents to get their source_thread_id
            rows = await conn.fetch("""
                SELECT id::text AS doc_id,
                       source_type::text AS stype,
                       metadata->>'source_thread_id' AS thread_id
                FROM multimodal_librarian.knowledge_sources
                WHERE id = ANY($1::uuid[])
            """, document_ids)

            import uuid as _uuid_mod
            thread_id_set = set()
            for r in rows:
                doc_id_str = r['doc_id']
                stype = (r['stype'] or '').upper()
                thread_id = r['thread_id']
                if stype == 'CONVERSATION' and thread_id:
                    try:
                        tid_uuid = _uuid_mod.UUID(thread_id)
                        query_to_doc[str(tid_uuid)] = doc_id_str
                        all_query_ids.append(tid_uuid)
                        thread_id_set.add(str(tid_uuid))
                    except ValueError:
                        query_to_doc[doc_id_str] = doc_id_str
                        all_query_ids.append(_uuid_mod.UUID(doc_id_str))
                else:
                    query_to_doc[doc_id_str] = doc_id_str
                    all_query_ids.append(_uuid_mod.UUID(doc_id_str))

            # Also include any document_ids that weren't found in the lookup
            # (shouldn't happen, but be safe)
            found_doc_ids = {r['doc_id'] for r in rows}
            for did in document_ids:
                did_str = str(did)
                if did_str not in found_doc_ids and did_str not in query_to_doc.values():
                    query_to_doc[did_str] = did_str
                    all_query_ids.append(did)

            if not all_query_ids:
                return stats

            # Chunk counts — query using resolved IDs
            rows = await conn.fetch("""
                SELECT source_id::text AS doc_id, count(*) AS cnt
                FROM multimodal_librarian.knowledge_chunks
                WHERE source_id = ANY($1::uuid[])
                GROUP BY source_id
            """, all_query_ids)
            for r in rows:
                orig = query_to_doc.get(r['doc_id'], r['doc_id'])
                stats.setdefault(orig, {})['chunk_count'] = r['cnt']

            # Bridge counts
            rows = await conn.fetch("""
                SELECT kc.source_id::text AS doc_id, count(*) AS cnt
                FROM multimodal_librarian.bridge_chunks bc
                JOIN multimodal_librarian.knowledge_chunks kc
                    ON bc.source_chunk_id = kc.id
                WHERE kc.source_id = ANY($1::uuid[])
                GROUP BY kc.source_id
            """, all_query_ids)
            for r in rows:
                orig = query_to_doc.get(r['doc_id'], r['doc_id'])
                stats.setdefault(orig, {})['bridge_count'] = r['cnt']
        finally:
            await conn.close()
    except Exception as e:
        logger.warning(f"Failed to fetch PG document stats: {e}")
        # If the metadata lookup failed, fall back to using document_ids directly
        if not query_to_doc:
            for did in document_ids:
                query_to_doc[str(did)] = str(did)
                all_query_ids.append(did)

    # Neo4j concept/relationship stats — batched into 2 queries total
    # (instead of 2 per document) for O(1) round-trips.
    try:
        from ...clients.database_factory import get_database_factory
        factory = get_database_factory()
        client = factory.get_graph_client()
        if not getattr(client, '_is_connected', False):
            await client.connect()

        # Build a flat list of all source_ids to query and a reverse map
        # from each source_id back to the original doc_id_str.
        all_neo4j_ids: list[str] = []
        neo4j_id_to_doc: dict[str, str] = {}  # neo4j source_id -> doc_id_str
        for query_id_str, doc_id_str in query_to_doc.items():
            for sid in {query_id_str, doc_id_str}:
                if sid not in neo4j_id_to_doc:
                    neo4j_id_to_doc[sid] = doc_id_str
                    all_neo4j_ids.append(sid)

        if all_neo4j_ids:
            # Query 1: concept counts per source_id
            try:
                result = await client.execute_query(
                    "MATCH (ch:Chunk) WHERE ch.source_id IN $ids "
                    "MATCH (ch)<-[:EXTRACTED_FROM]-(c:Concept) "
                    "RETURN ch.source_id AS sid, count(DISTINCT c) AS concepts",
                    {"ids": all_neo4j_ids}
                )
                for row in (result or []):
                    sid = row.get('sid')
                    doc_id_str = neo4j_id_to_doc.get(sid)
                    if doc_id_str:
                        s = stats.setdefault(doc_id_str, {})
                        # Take the max in case both query_id and doc_id match
                        s['concept_count'] = max(
                            s.get('concept_count', 0), row.get('concepts', 0)
                        )
            except Exception as e:
                logger.debug(f"Neo4j batch concept count failed: {e}")

            # Relationship breakdown removed from list view for performance.
            # Concept-to-concept edge traversal across 260K+ nodes was ~10s.
            # Can be fetched on-demand per document if needed.
    except Exception as e:
        logger.debug(f"KG stats unavailable: {e}")

    return stats


async def handle_document_list_request(
    message_data: dict,
    connection_id: str,
    manager: "ConnectionManager",
    document_manager: "DocumentManager"
) -> None:
    """
    Handle request to list user's documents.
    
    Args:
        message_data: Request message with optional filters
        connection_id: WebSocket connection ID
        manager: Connection manager for sending responses
        document_manager: Document manager for retrieving documents
        
    Requirements: 8.2
    """
    try:
        # Parse request
        try:
            list_request = DocumentListRequest(**message_data)
        except Exception as e:
            logger.error(f"Invalid document list request: {e}")
            await manager.send_personal_message({
                'type': 'error',
                'message': f"Invalid request format: {str(e)}"
            }, connection_id)
            return
        
        # Map status filter string to DocumentStatus enum if provided
        status_filter = None
        if list_request.status_filter:
            from ...models.documents import DocumentStatus
            status_map = {
                'uploaded': DocumentStatus.UPLOADED,
                'processing': DocumentStatus.PROCESSING,
                'completed': DocumentStatus.COMPLETED,
                'failed': DocumentStatus.FAILED
            }
            status_filter = status_map.get(list_request.status_filter.lower())
        
        # Get documents from document manager
        # Convert page/page_size to limit/offset for the document manager
        limit = list_request.page_size
        offset = (list_request.page - 1) * list_request.page_size
        
        documents_result = await document_manager.list_documents_with_status(
            status_filter=status_filter,
            limit=limit,
            offset=offset
        )
        
        # Convert to DocumentInfo models
        document_infos = []
        for doc in documents_result.get('documents', []):
            # Map DocumentStatus to string status
            status_str = _map_status_to_string(doc.get('status'))
            
            doc_info = DocumentInfo(
                document_id=str(doc.get('document_id', '')),
                title=doc.get('title', 'Untitled'),
                filename=doc.get('filename', 'unknown'),
                status=status_str,
                upload_timestamp=doc.get('upload_timestamp', datetime.utcnow()),
                file_size=doc.get('file_size', 0),
                source_type=doc.get('source_type'),
                thread_id=doc.get('thread_id'),
                chunk_count=doc.get('chunk_count'),
                error_message=doc.get('processing_error')
            )
            document_infos.append(doc_info)
        
        # Stats are fetched on-demand per document (document_stats_request)
        # to keep the list response fast.

        # Send response
        response = DocumentListMessage(
            documents=document_infos,
            total_count=documents_result.get(
                'total_count', len(document_infos)
            ),
            page=list_request.page,
            page_size=list_request.page_size
        )

        await manager.send_personal_message(
            response.model_dump(mode='json'), connection_id
        )
        
        logger.debug(f"Sent document list to {connection_id}: {len(document_infos)} documents")
        
    except Exception as e:
        logger.error(f"Error handling document list request: {e}")
        await manager.send_personal_message({
            'type': 'error',
            'message': 'Failed to retrieve document list'
        }, connection_id)


async def handle_document_stats_request(
    message_data: dict,
    connection_id: str,
    manager: "ConnectionManager",
) -> None:
    """Fetch detailed stats for a single document on demand.

    Returns chunk_count, bridge_count, concept_count, relationship_count,
    and relationship_breakdown via a ``document_stats`` WebSocket message.
    """
    document_id = (message_data.get("document_id") or "").strip()
    if not document_id:
        await manager.send_personal_message({
            'type': 'document_stats',
            'document_id': '',
            'error': 'document_id is required',
        }, connection_id)
        return

    stats: dict = {'document_id': document_id, 'type': 'document_stats'}

    # --- Resolve conversation mapping ---
    import uuid as _uuid_mod
    query_ids: list = []  # UUIDs for PG queries
    neo4j_ids: list[str] = []  # strings for Neo4j
    try:
        from ...database.connection import get_async_connection
        conn = await get_async_connection()
        try:
            row = await conn.fetchrow(
                "SELECT id::text AS doc_id, source_type::text AS stype, "
                "metadata->>'source_thread_id' AS thread_id "
                "FROM multimodal_librarian.knowledge_sources WHERE id = $1::uuid",
                _uuid_mod.UUID(document_id),
            )
            if row and (row['stype'] or '').upper() == 'CONVERSATION' and row['thread_id']:
                tid = _uuid_mod.UUID(row['thread_id'])
                doc_uuid = _uuid_mod.UUID(document_id)
                # Include both thread_id and UUID5 document_id so we
                # match chunks regardless of which ID was used as source_id
                query_ids.extend([tid, doc_uuid])
                neo4j_ids.extend([str(tid), document_id])
            else:
                query_ids.append(_uuid_mod.UUID(document_id))
                neo4j_ids.append(document_id)

            # Chunk count
            r = await conn.fetchrow(
                "SELECT count(*) AS cnt FROM multimodal_librarian.knowledge_chunks "
                "WHERE source_id = ANY($1::uuid[])", query_ids,
            )
            if r:
                stats['chunk_count'] = r['cnt']

            # Bridge count
            r = await conn.fetchrow(
                "SELECT count(*) AS cnt FROM multimodal_librarian.bridge_chunks bc "
                "JOIN multimodal_librarian.knowledge_chunks kc ON bc.source_chunk_id = kc.id "
                "WHERE kc.source_id = ANY($1::uuid[])", query_ids,
            )
            if r:
                stats['bridge_count'] = r['cnt']
        finally:
            await conn.close()
    except Exception as e:
        logger.warning(f"PG stats failed for {document_id}: {e}")
        if not neo4j_ids:
            neo4j_ids.append(document_id)

    # --- Neo4j: concept count + relationship breakdown ---
    try:
        from ...clients.database_factory import get_database_factory
        factory = get_database_factory()
        client = factory.get_graph_client()
        if not getattr(client, '_is_connected', False):
            await client.connect()

        # Concept count
        try:
            result = await client.execute_query(
                "MATCH (ch:Chunk) WHERE ch.source_id IN $ids "
                "MATCH (ch)<-[:EXTRACTED_FROM]-(c:Concept) "
                "RETURN count(DISTINCT c) AS concepts",
                {"ids": neo4j_ids},
            )
            for row in (result or []):
                stats['concept_count'] = row.get('concepts', 0)
        except Exception as e:
            logger.debug(f"Neo4j concept count failed for {document_id}: {e}")

        # Relationship breakdown — single doc so much smaller working set
        try:
            result = await client.execute_query(
                "MATCH (ch:Chunk) WHERE ch.source_id IN $ids "
                "MATCH (ch)<-[:EXTRACTED_FROM]-(c:Concept) "
                "WITH DISTINCT c "
                "MATCH (c)-[r]->(:Concept) "
                "RETURN type(r) AS rel_type, count(r) AS cnt",
                {"ids": neo4j_ids},
            )
            total_rels = 0
            breakdown = {}
            for row in (result or []):
                rt = row.get('rel_type')
                cnt = row.get('cnt', 0)
                total_rels += cnt
                if rt:
                    breakdown[rt] = {
                        'count': cnt,
                        'source': _classify_rel_source(rt),
                    }
            stats['relationship_count'] = total_rels
            if breakdown:
                stats['relationship_breakdown'] = breakdown
        except Exception as e:
            logger.debug(f"Neo4j relationship breakdown failed for {document_id}: {e}")
    except Exception as e:
        logger.debug(f"KG stats unavailable for {document_id}: {e}")

    await manager.send_personal_message(stats, connection_id)


async def handle_document_delete_request(
    message_data: dict,
    connection_id: str,
    manager: "ConnectionManager",
    document_manager: "DocumentManager"
) -> None:
    """
    Handle request to delete a document.

    This handler removes the document from all storage locations:
    S3, OpenSearch, Neptune, and PostgreSQL.

    Args:
        message_data: Delete request with document_id
        connection_id: WebSocket connection ID
        manager: Connection manager for sending responses
        document_manager: Document manager for deletion

    Requirements: 8.3
    """
    try:
        # Parse request
        try:
            delete_request = DocumentDeleteRequest(**message_data)
        except Exception as e:
            logger.error(f"Invalid document delete request: {e}")
            await manager.send_personal_message({
                'type': 'error',
                'message': f"Invalid request format: {str(e)}"
            }, connection_id)
            return

        # Parse document ID
        try:
            document_id = UUID(delete_request.document_id)
        except ValueError:
            await manager.send_personal_message({
                'type': 'error',
                'message': 'Invalid document ID format'
            }, connection_id)
            return

        logger.info(f"Deleting document {document_id} for connection {connection_id}")

        # Delete document completely from all stores
        deletion_results = await document_manager.delete_document_completely(document_id)

        # Extract success status from results
        success = deletion_results.get('success', False)

        # Invalidate retrieval caches so deleted content is no longer returned.
        if success:
            try:
                from ..dependencies.services import invalidate_rag_cache
                invalidate_rag_cache()
            except Exception as e:
                logger.warning(f"RAG cache invalidation failed: {e}")

        # Build detailed message
        if success:
            details = []
            if deletion_results.get('milvus_deleted', 0) > 0:
                details.append(f"{deletion_results['milvus_deleted']} vectors from Milvus")
            if deletion_results.get('neo4j_deleted', 0) > 0:
                details.append(f"{deletion_results['neo4j_deleted']} nodes from Neo4j")

            message = "Document deleted successfully"
            if details:
                message += f" (removed {', '.join(details)})"
        else:
            errors = deletion_results.get('errors', [])
            message = "Failed to delete document"
            if errors:
                message += f": {'; '.join(errors)}"

        # Send response
        response = DocumentDeletedMessage(
            document_id=str(document_id),
            success=success,
            message=message
        )

        await manager.send_personal_message(response.model_dump(mode='json'), connection_id)

        if success:
            logger.info(
                f"Document {document_id} deleted successfully "
                f"(Milvus: {deletion_results.get('milvus_deleted', 0)}, "
                f"Neo4j: {deletion_results.get('neo4j_deleted', 0)})"
            )
        else:
            logger.warning(f"Failed to delete document {document_id}: {deletion_results.get('errors', [])}")

    except Exception as e:
        logger.error(f"Error handling document delete request: {e}")
        await manager.send_personal_message({
            'type': 'error',
            'message': 'Failed to delete document'
        }, connection_id)


async def handle_document_retry_request(
    message_data: dict,
    connection_id: str,
    manager: "ConnectionManager",
    document_manager: "DocumentManager",
    processing_status_service: Optional["ProcessingStatusService"] = None
) -> None:
    """
    Handle request to retry failed document processing.
    
    This handler restarts processing from the failed stage.
    
    Args:
        message_data: Retry request with document_id
        connection_id: WebSocket connection ID
        manager: Connection manager for sending responses
        document_manager: Document manager for retry
        processing_status_service: Optional status service for progress updates
        
    Requirements: 8.4
    """
    try:
        # Parse request
        try:
            retry_request = DocumentRetryRequest(**message_data)
        except Exception as e:
            logger.error(f"Invalid document retry request: {e}")
            await manager.send_personal_message({
                'type': 'error',
                'message': f"Invalid request format: {str(e)}"
            }, connection_id)
            return
        
        # Parse document ID
        try:
            document_id = UUID(retry_request.document_id)
        except ValueError:
            await manager.send_personal_message({
                'type': 'error',
                'message': 'Invalid document ID format'
            }, connection_id)
            return
        
        logger.info(f"Retrying document processing for {document_id}")
        
        # Register retry with processing status service
        if processing_status_service:
            # Get document info for filename
            try:
                doc_status = await document_manager.get_document_status(document_id)
                filename = doc_status.get('filename', 'unknown')
            except Exception:
                filename = 'unknown'
            
            await processing_status_service.register_upload(
                document_id=document_id,
                connection_id=connection_id,
                filename=filename
            )
        
        # Retry document processing
        success = await document_manager.retry_document_processing(document_id)
        
        if success:
            # Send retry started message
            response = DocumentRetryStartedMessage(
                document_id=str(document_id),
                filename=filename,
                message="Document processing retry initiated"
            )
            await manager.send_personal_message(response.model_dump(mode='json'), connection_id)
            logger.info(f"Document {document_id} retry initiated successfully")
        else:
            await manager.send_personal_message({
                'type': 'error',
                'message': 'Failed to retry document processing. Document may not be in a failed state.'
            }, connection_id)
            logger.warning(f"Failed to retry document {document_id}")
        
    except Exception as e:
        logger.error(f"Error handling document retry request: {e}")
        await manager.send_personal_message({
            'type': 'error',
            'message': 'Failed to retry document processing'
        }, connection_id)


# =============================================================================
# Helper Functions
# =============================================================================

async def _send_upload_error(
    manager: "ConnectionManager",
    connection_id: str,
    filename: str,
    error_code: str,
    error_message: str
) -> None:
    """Send an upload error message to the client."""
    error_msg = DocumentUploadErrorMessage(
        filename=filename,
        error_code=error_code,
        error_message=error_message
    )
    await manager.send_personal_message(error_msg.model_dump(mode='json'), connection_id)


def _map_status_to_string(status) -> str:
    """Map DocumentStatus enum to string for API response."""
    if status is None:
        return "uploaded"
    
    # Handle both enum and string values
    status_str = status.value if hasattr(status, 'value') else str(status)
    
    status_map = {
        'uploaded': 'uploaded',
        'processing': 'processing',
        'completed': 'completed',
        'failed': 'failed',
        'pending': 'uploaded',
        'error': 'failed'
    }
    
    return status_map.get(status_str.lower(), 'uploaded')


def _classify_rel_source(rel_type: str) -> str:
    """Classify a Neo4j relationship type to its ontological source.

    Naming conventions:
    - UPPER_SNAKE_CASE (e.g. RELATED_TO, IS_A) → document extraction (pattern/embedding)
    - CamelCase (e.g. RelatedTo, IsA, HasContext) → ConceptNet enrichment
    - dbpedia_* → ConceptNet (DBpedia-sourced edges within ConceptNet data)
    - INSTANCE_OF → YAGO entity linking
    - SAME_AS → cross-document concept linking
    """
    if rel_type.startswith('dbpedia_'):
        return 'ConceptNet'
    if rel_type == 'INSTANCE_OF':
        return 'YAGO'
    if rel_type == 'SAME_AS':
        return 'Cross-document'
    # CamelCase: starts with uppercase, contains at least one lowercase
    # followed by uppercase (e.g. RelatedTo, IsA, HasContext)
    if (rel_type[0].isupper()
            and not rel_type.isupper()
            and '_' not in rel_type):
        return 'ConceptNet'
    return 'Document'


async def _resolve_conversation_source_id(document_id: str) -> str:
    """Resolve a knowledge_sources.id to the Neo4j source_document key.

    Conversation documents store concepts in Neo4j using the UUID5
    knowledge_sources.id as source_document (not the raw thread_id).
    For regular documents the id is used directly.  In both cases the
    document_id passed in is already the correct Neo4j key, so this
    function simply returns it unchanged.
    """
    return document_id


async def handle_related_docs_graph(
    message_data: dict,
    connection_id: str,
    manager: "ConnectionManager",
) -> None:
    """
    Handle request for the related documents graph.

    Queries Neo4j for all RELATED_DOCS edges involving the requested document,
    resolves document titles from PostgreSQL, and returns a nodes-and-edges
    payload for the frontend force-directed graph popup.

    Args:
        message_data: WebSocket message with ``document_id``.
        connection_id: WebSocket connection ID.
        manager: Connection manager for sending responses.

    Requirements: 6.1, 6.2, 6.3, 6.4, 6.5, 6.6, 6.7, 6.8
    """
    document_id = (message_data.get("document_id") or "").strip()

    # --- Validate document_id (Req 6.8) ---
    if not document_id:
        error_resp = RelatedDocsGraphError(
            document_id=document_id,
            message="document_id is required and must be non-empty",
        )
        await manager.send_personal_message(
            error_resp.model_dump(mode="json"), connection_id
        )
        return

    # --- Obtain Neo4j client (Req 6.7) ---
    try:
        from ...clients.database_factory import get_database_factory
        factory = get_database_factory()
        client = factory.get_graph_client()
        if not getattr(client, "_is_connected", False):
            await client.connect()
    except Exception as exc:
        logger.error(f"Neo4j client unavailable for related docs graph: {exc}")
        error_resp = RelatedDocsGraphError(
            document_id=document_id,
            message="Knowledge graph service is unavailable",
        )
        await manager.send_personal_message(
            error_resp.model_dump(mode="json"), connection_id
        )
        return

    # --- Resolve conversation source_id (UUID5 → thread_id) ---
    neo4j_doc_id = await _resolve_conversation_source_id(document_id)

    # --- Query RELATED_DOCS edges (Req 6.1) ---
    # Optimized: collect source concept IDs first via CALL {},
    # then traverse RELATED_DOCS → target concept → chunk in a
    # single pass.  Avoids the 4-hop cartesian explosion that
    # timed out on large documents (9k+ concepts).
    try:
        results = await client.execute_query(
            "CALL { "
            "  MATCH (ch1:Chunk {source_id: $doc_id})"
            "        <-[:EXTRACTED_FROM]-(c1:Concept) "
            "  RETURN collect(DISTINCT id(c1)) AS src_ids "
            "} "
            "MATCH (c1)-[r:RELATED_DOCS]->(c2) "
            "WHERE id(c1) IN src_ids AND NOT id(c2) IN src_ids "
            "WITH c2, max(r.score) AS best_score, "
            "     sum(r.edge_count) AS total_ec "
            "MATCH (c2)-[:EXTRACTED_FROM]->(ch2:Chunk) "
            "WITH DISTINCT ch2.source_id AS related_doc_id, "
            "     best_score, total_ec "
            "RETURN related_doc_id, "
            "  max(best_score) AS score, "
            "  sum(total_ec) AS edge_count",
            {"doc_id": neo4j_doc_id},
        )
    except Exception as exc:
        logger.error(f"Neo4j query failed for related docs graph ({document_id}): {exc}")
        error_resp = RelatedDocsGraphError(
            document_id=document_id,
            message=f"Failed to query related documents: {exc}",
        )
        await manager.send_personal_message(
            error_resp.model_dump(mode="json"), connection_id
        )
        return

    # --- Collect all document IDs that need title lookup ---
    related_rows = results or []
    all_doc_ids = [document_id]
    for row in related_rows:
        rid = row.get("related_doc_id")
        if rid and rid not in all_doc_ids:
            all_doc_ids.append(rid)

    # --- Look up titles and source types from PostgreSQL (Req 6.4, 6.5) ---
    titles: dict = {}
    source_types: dict = {}
    try:
        from ...database.connection import get_async_connection
        conn = await get_async_connection()
        try:
            rows = await conn.fetch(
                "SELECT id::text, title, source_type::text "
                "FROM multimodal_librarian.knowledge_sources "
                "WHERE id = ANY($1::uuid[])",
                all_doc_ids,
            )
            for r in rows:
                titles[r["id"]] = r["title"] or r["id"]
                source_types[r["id"]] = (r["source_type"] or "").upper()
        finally:
            await conn.close()
    except Exception as exc:
        logger.warning(f"PostgreSQL title lookup failed, using document_id fallback: {exc}")

    def _title(doc_id: str) -> str:
        from urllib.parse import unquote
        raw = titles.get(doc_id, doc_id)
        return unquote(raw) if raw else doc_id

    origin_is_conversation = (
        source_types.get(document_id) == "CONVERSATION"
    )

    if origin_is_conversation:
        # --- Conversation origin: use actual citations, not RELATED_DOCS ---
        # RELATED_DOCS edges for conversations are spurious (generic
        # concept overlap like "data", "use", "applications").  Instead,
        # extract the real cited document IDs from the messages table.
        cited_doc_ids: set = set()
        try:
            import json as _json
            conn2 = await get_async_connection()
            try:
                # Get the thread_id from knowledge_sources metadata
                meta_row = await conn2.fetchrow(
                    "SELECT metadata->>'source_thread_id' AS tid "
                    "FROM multimodal_librarian.knowledge_sources "
                    "WHERE id::text = $1",
                    document_id,
                )
                thread_id = meta_row["tid"] if meta_row else None
                if thread_id:
                    ref_rows = await conn2.fetch(
                        "SELECT knowledge_references "
                        "FROM multimodal_librarian.messages "
                        "WHERE thread_id = $1::uuid "
                        "AND knowledge_references IS NOT NULL",
                        thread_id,
                    )
                    for rr in ref_rows:
                        refs = rr["knowledge_references"]
                        if isinstance(refs, str):
                            refs = _json.loads(refs)
                        if isinstance(refs, list):
                            for ref in refs:
                                did = ref.get("document_id")
                                if did:
                                    cited_doc_ids.add(str(did))
            finally:
                await conn2.close()
        except Exception as exc:
            logger.warning(
                f"Citation lookup failed for conversation "
                f"{document_id}: {exc}"
            )

        # Filter out non-UUID document IDs (e.g. web_brave, web_google)
        # before passing to PostgreSQL — invalid UUIDs cause the entire
        # ANY($1::uuid[]) cast to fail, silently dropping all results.
        import uuid as _uuid_mod
        valid_cited: set = set()
        for _cid in cited_doc_ids:
            try:
                _uuid_mod.UUID(_cid)
                valid_cited.add(_cid)
            except (ValueError, AttributeError):
                pass
        cited_doc_ids = valid_cited

        # Fetch titles for cited docs not already loaded
        missing = [d for d in cited_doc_ids if d not in titles]
        if missing:
            try:
                conn3 = await get_async_connection()
                try:
                    extra = await conn3.fetch(
                        "SELECT id::text, title "
                        "FROM multimodal_librarian.knowledge_sources "
                        "WHERE id = ANY($1::uuid[])",
                        missing,
                    )
                    for r in extra:
                        titles[r["id"]] = r["title"] or r["id"]
                finally:
                    await conn3.close()
            except Exception:
                logger.warning(
                    f"Title lookup failed for cited docs {missing}",
                    exc_info=True,
                )

        # Build citation-based related_rows (score=1.0 for cited docs)
        # Exclude the origin document itself to avoid self-edges.
        related_rows = [
            {"related_doc_id": did, "score": 1.0, "edge_count": 1}
            for did in cited_doc_ids
            if did in titles and did != document_id
        ]
    else:
        # --- Regular document origin ---
        # Filter out deleted docs and conversation documents.
        # Conversation RELATED_DOCS edges are based on shallow
        # generic concept overlap, not real topical similarity.
        related_rows = [
            row for row in related_rows
            if row.get("related_doc_id") in titles
            and source_types.get(
                row.get("related_doc_id")
            ) != "CONVERSATION"
        ]

    # --- Build nodes (Req 6.2, 6.3) ---
    seen_node_ids = {document_id}
    nodes = [RelatedDocsGraphNode(document_id=document_id, title=_title(document_id), is_origin=True)]
    for row in related_rows:
        rid = row.get("related_doc_id")
        if rid and rid not in seen_node_ids:
            seen_node_ids.add(rid)
            nodes.append(RelatedDocsGraphNode(document_id=rid, title=_title(rid)))

    # --- Build edges (Req 6.2) ---
    edges = []
    for row in related_rows:
        rid = row.get("related_doc_id")
        if rid:
            score = row.get("score", 0.0)
            edge_count = row.get("edge_count", 0)
            edges.append(RelatedDocsGraphEdge(
                source=document_id,
                target=rid,
                score=float(score),
                edge_count=int(edge_count),
            ))

    # --- Send response (Req 6.6 — valid even if no edges) ---
    response = RelatedDocsGraphResponse(
        document_id=document_id,
        nodes=nodes,
        edges=edges,
    )
    await manager.send_personal_message(
        response.model_dump(mode="json"), connection_id
    )
    logger.debug(
        f"Sent related docs graph for {document_id}: "
        f"{len(nodes)} nodes, {len(edges)} edges"
    )
