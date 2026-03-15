"""
Document management API endpoints.

This module provides REST API endpoints for PDF document upload,
management, and retrieval operations with integrated processing.
"""

import logging
from datetime import datetime
from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from fastapi.responses import JSONResponse, RedirectResponse, StreamingResponse

from ...components.document_manager.document_manager import (
    DocumentManager,
    DocumentManagerError,
)
from ...models.documents import (
    Document,
    DocumentListResponse,
    DocumentSearchRequest,
    DocumentStatus,
    DocumentUploadRequest,
    DocumentUploadResponse,
)
from ...services.processing_service import ProcessingError, ProcessingService
from ...services.upload_service import (
    DuplicateDocumentError,
    UploadError,
    UploadService,
    ValidationError,
)

logger = logging.getLogger(__name__)

# Create router
router = APIRouter(prefix="/api/documents", tags=["documents"])

# Service dependencies
_upload_service_instance = None

def get_upload_service() -> UploadService:
    """Dependency to get upload service instance."""
    global _upload_service_instance
    if _upload_service_instance is None:
        _upload_service_instance = UploadService()
    return _upload_service_instance


def get_document_manager() -> DocumentManager:
    """Dependency to get document manager instance."""
    return DocumentManager()


def get_processing_service() -> ProcessingService:
    """Dependency to get processing service instance."""
    return ProcessingService()


_conversation_manager_instance = None

def get_conversation_manager():
    """Dependency to get conversation manager instance."""
    global _conversation_manager_instance
    if _conversation_manager_instance is None:
        from ...components.conversation.conversation_manager import ConversationManager
        _conversation_manager_instance = ConversationManager()
    return _conversation_manager_instance


@router.post("/upload", response_model=DocumentUploadResponse)
async def upload_document(
    file: UploadFile = File(..., description="PDF file to upload"),
    title: Optional[str] = Form(None, description="Document title"),
    description: Optional[str] = Form(None, description="Document description"),
    user_id: str = Form("default_user", description="User identifier"),
    force_upload: bool = Form(False, description="Force upload even if duplicate exists"),
    upload_service: UploadService = Depends(get_upload_service)
):
    """
    Upload a PDF document with enhanced validation and S3 storage.
    
    - **file**: PDF file to upload (max 100MB)
    - **title**: Optional document title (defaults to filename)
    - **description**: Optional document description
    - **user_id**: User identifier for document ownership
    - **force_upload**: If true, upload even if a duplicate document exists
    
    Returns document ID, upload status, and processing information.
    
    If a duplicate is detected (same file content), returns HTTP 409 Conflict
    with the existing document's ID and title, unless force_upload is true.
    """
    try:
        # Validate file type and size
        supported_types = ["application/pdf", "text/plain"]
        if not file.content_type or file.content_type not in supported_types:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Only PDF and TXT files are supported"
            )
        
        # Check file size before reading (100MB limit)
        if hasattr(file, 'size') and file.size and file.size > 100 * 1024 * 1024:
            raise HTTPException(
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                detail="File size exceeds 100MB limit"
            )
        
        # Read file content
        try:
            file_data = await file.read()
        except Exception as e:
            logger.error(f"Failed to read uploaded file: {e}")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Failed to read uploaded file"
            )
        
        # Create upload request
        upload_request = DocumentUploadRequest(
            title=title,
            description=description
        )
        
        # Upload document
        try:
            result = await upload_service.upload_document(
                file_data=file_data,
                filename=file.filename or "document.pdf",
                upload_request=upload_request,
                force_upload=force_upload
            )
            
            logger.info(f"Document uploaded successfully: {result.document_id}")
            return result
            
        except DuplicateDocumentError as e:
            # Return 409 Conflict with duplicate info
            return JSONResponse(
                status_code=status.HTTP_409_CONFLICT,
                content={
                    "detail": "Document already exists",
                    "message": str(e),
                    "existing_document": {
                        "id": e.existing_document_id,
                        "title": e.existing_title,
                        "url": f"/api/documents/{e.existing_document_id}"
                    },
                    "action_required": "Use force_upload=true to upload anyway"
                }
            )
        except ValidationError as e:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=str(e)
            )
        except UploadError as e:
            logger.error(f"Upload failed: {e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Upload failed: {str(e)}"
            )
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Unexpected error during upload: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error during upload"
        )


@router.get("/", response_model=DocumentListResponse)
async def list_documents(
    query: Optional[str] = None,
    status_filter: Optional[DocumentStatus] = None,
    page: int = 1,
    page_size: int = 50,
    user_id: str = "default_user",
    upload_service: UploadService = Depends(get_upload_service)
):
    """
    List documents with optional filtering and pagination.
    
    - **query**: Search query for title and description
    - **status_filter**: Filter by document status
    - **page**: Page number (starts from 1)
    - **page_size**: Number of items per page (max 100)
    - **user_id**: User identifier for filtering user documents
    
    Returns paginated list of documents with processing status.
    """
    try:
        # Validate pagination parameters
        if page < 1:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Page number must be >= 1"
            )
        
        if page_size < 1 or page_size > 100:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Page size must be between 1 and 100"
            )
        
        # Create search request
        search_request = DocumentSearchRequest(
            query=query,
            status=status_filter,
            page=page,
            page_size=page_size
        )
        
        # Get documents
        result = await upload_service.list_documents(
            user_id="default_user",
            search=query,
            status=status_filter,
            page=page,
            page_size=page_size
        )
        
        return result
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error listing documents: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve documents"
        )


@router.get("/health")
async def get_document_service_health():
    """
    Get document service health status.
    
    Returns service health information and component status.
    """
    try:
        return {
            "status": "healthy",
            "service": "document_management",
            "version": "1.0.0",
            "timestamp": datetime.utcnow().isoformat(),
            "services": {
                "upload_service": "healthy",
                "storage_service": "healthy",
                "processing_service": "healthy"
            },
            "features": {
                "document_upload": True,
                "document_search": True,
                "document_processing": True,
                "s3_storage": True
            }
        }
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        return {
            "status": "unhealthy",
            "service": "document_management",
            "error": str(e),
            "timestamp": datetime.utcnow().isoformat()
        }


@router.get("/{document_id}", response_model=Document)
async def get_document(
    document_id: UUID,
    upload_service: UploadService = Depends(get_upload_service)
):
    """
    Get document details by ID.
    
    - **document_id**: Unique document identifier
    
    Returns document details.
    """
    try:
        document = await upload_service.get_document(document_id)
        
        if not document:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Document not found: {document_id}"
            )
        
        return document
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error retrieving document {document_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve document"
        )


@router.delete("/{document_id}")
async def delete_document(
    document_id: UUID,
    document_manager: DocumentManager = Depends(get_document_manager)
):
    """
    Delete a document and all associated data completely.
    
    - **document_id**: Unique document identifier
    
    Returns deletion confirmation.
    """
    try:
        doc_id = str(document_id)

        # Collect chunk IDs belonging to this document BEFORE deletion
        # so we can surgically evict them from the KG retrieval cache.
        # Query with both doc UUID and thread_id (conversations store
        # Chunk nodes under the raw thread_id as source_id).
        stale_chunk_ids: set = set()
        try:
            source_ids = [doc_id]
            # Resolve thread_id for conversation documents
            from sqlalchemy import text as sa_text

            from ...database.connection import db_manager
            try:
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
                    if row.metadata and isinstance(row.metadata, dict):
                        tid = row.metadata.get("source_thread_id")
                    if not tid and row.file_path:
                        tid = str(row.file_path).replace("conversation://", "")
                    if tid and tid != doc_id:
                        source_ids.append(tid)
            except Exception:
                pass

            from ...services.knowledge_graph_service import KnowledgeGraphService
            kg = KnowledgeGraphService()
            await kg.client.connect()
            try:
                rows = await kg.client.execute_query(
                    "MATCH (ch:Chunk) WHERE ch.source_id IN $ids "
                    "RETURN ch.chunk_id AS chunk_id",
                    {"ids": source_ids},
                )
                stale_chunk_ids = {
                    r["chunk_id"] for r in (rows or []) if r.get("chunk_id")
                }
            finally:
                await kg.client.disconnect()
        except Exception as e:
            logger.debug(f"Could not pre-fetch chunk IDs for cache eviction: {e}")

        result = await document_manager.delete_document_completely(document_id)
        
        if not result.get('success'):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Document not found: {document_id}"
            )
        
        # Targeted cache eviction: remove only this document's chunks
        evicted = 0
        if stale_chunk_ids:
            try:
                from ..dependencies.services import _kg_retrieval_service
                if _kg_retrieval_service is not None:
                    evicted = _kg_retrieval_service.evict_chunks(stale_chunk_ids)
            except Exception as e:
                logger.warning(f"KG cache eviction failed: {e}")

        return JSONResponse(
            status_code=status.HTTP_200_OK,
            content={
                "message": "Document and all associated data deleted successfully",
                "document_id": str(document_id),
                "milvus_deleted": result.get('milvus_deleted', 0),
                "neo4j_deleted": result.get('neo4j_deleted', 0),
                "cache_entries_evicted": evicted,
            }
        )
        
    except HTTPException:
        raise
    except DocumentManagerError as e:
        logger.error(f"Error deleting document {document_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to delete document: {str(e)}"
        )
    except Exception as e:
        logger.error(f"Unexpected error deleting document {document_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to delete document"
        )


@router.post("/{document_id}/retry")
async def retry_document_processing(
    document_id: UUID,
    document_manager: DocumentManager = Depends(get_document_manager)
):
    """
    Retry processing for a failed document.
    
    - **document_id**: Unique document identifier
    
    Returns retry confirmation.
    """
    try:
        success = await document_manager.retry_document_processing(document_id)
        
        if not success:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Document cannot be retried (not found or not in failed state)"
            )
        
        return JSONResponse(
            status_code=status.HTTP_200_OK,
            content={
                "message": "Document processing retry initiated",
                "document_id": str(document_id)
            }
        )
        
    except HTTPException:
        raise
    except DocumentManagerError as e:
        logger.error(f"Error retrying document {document_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        logger.error(f"Unexpected error retrying document {document_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retry document processing"
        )


@router.get("/{document_id}/summary")
async def get_document_content_summary(
    document_id: UUID,
    document_manager: DocumentManager = Depends(get_document_manager)
):
    """
    Get summary of processed document content.
    
    - **document_id**: Unique document identifier
    
    Returns content summary including chunks, images, tables, etc.
    """
    try:
        summary = await document_manager.get_document_content_summary(document_id)
        
        if not summary:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Document not found or not yet processed"
            )
        
        return JSONResponse(
            status_code=status.HTTP_200_OK,
            content=summary
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting content summary for document {document_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get document content summary"
        )


@router.get("/processing/active")
async def get_active_processing_jobs(
    document_manager: DocumentManager = Depends(get_document_manager)
):
    """
    Get information about all active processing jobs.
    
    Returns list of currently processing documents.
    """
    try:
        active_jobs = document_manager.get_active_processing_jobs()
        
        return JSONResponse(
            status_code=status.HTTP_200_OK,
            content={
                "active_jobs": active_jobs,
                "total_active": len(active_jobs)
            }
        )
        
    except Exception as e:
        logger.error(f"Error getting active processing jobs: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get active processing jobs"
        )


@router.get("/{document_id}/download")
async def download_document(
    document_id: UUID,
    redirect: bool = False,
    upload_service: UploadService = Depends(get_upload_service)
):
    """
    Download document file content.
    
    - **document_id**: Unique document identifier
    - **redirect**: If true, redirect to the presigned URL instead of returning JSON
    
    Returns file content or presigned URL for download.
    For conversation sources, redirects to the conversation view.
    """
    try:
        # Check if this is a conversation source first
        from sqlalchemy import text as sa_text

        from ...database.connection import db_manager
        try:
            async with db_manager.get_async_session() as sess:
                row = (await sess.execute(
                    sa_text(
                        "SELECT source_type, file_path, title "
                        "FROM multimodal_librarian.knowledge_sources "
                        "WHERE id = :did"
                    ),
                    {"did": str(document_id)},
                )).fetchone()
        except Exception:
            row = None

        if row and row.source_type == "CONVERSATION":
            # Extract thread_id from file_path
            thread_id = (row.file_path or "").replace(
                "conversation://", ""
            )
            return JSONResponse(
                status_code=status.HTTP_200_OK,
                content={
                    "source_type": "conversation",
                    "thread_id": thread_id,
                    "title": row.title,
                    "redirect_url": (
                        f"/api/conversations/{thread_id}"
                    ),
                },
            )

        document = await upload_service.get_document(document_id)
        
        if not document:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Document not found: {document_id}"
            )
        
        # Generate presigned URL for secure download
        try:
            presigned_url = upload_service.storage_service.generate_presigned_url(
                s3_key=document.s3_key,
                expiration=3600  # 1 hour
            )
            
            if redirect:
                import io
                file_data = upload_service.storage_service.download_file(document.s3_key)
                filename = document.filename or "document.pdf"
                return StreamingResponse(
                    io.BytesIO(file_data),
                    media_type="application/pdf",
                    headers={"Content-Disposition": f'attachment; filename="{filename}"'}
                )
            
            return JSONResponse(
                status_code=status.HTTP_200_OK,
                content={
                    "download_url": presigned_url,
                    "filename": document.filename,
                    "file_size": document.file_size,
                    "expires_in": 3600
                }
            )
            
        except Exception as e:
            logger.error(f"Failed to generate download URL for {document_id}: {e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to generate download URL"
            )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error processing download request for {document_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to process download request"
        )


@router.get("/{document_id}/export-conversation")
async def export_conversation_by_document(document_id: UUID):
    """
    Export a conversation source as a downloadable PDF file.

    Resolves the thread_id from knowledge_sources, loads messages
    directly from the DB (including knowledge_references / citations),
    builds markdown content matching the main Export format, and
    uses ExportEngine to generate a styled PDF.
    """
    import io
    import json as _json
    import re

    from sqlalchemy import text as sa_text

    from ...components.export_engine.export_engine import ExportEngine
    from ...database.connection import db_manager
    from ...models.core import MultimediaResponse

    # 1. Look up the conversation thread_id from knowledge_sources
    try:
        async with db_manager.get_async_session() as sess:
            row = (await sess.execute(
                sa_text(
                    "SELECT source_type, file_path, title "
                    "FROM multimodal_librarian.knowledge_sources "
                    "WHERE id = :did"
                ),
                {"did": str(document_id)},
            )).fetchone()
    except Exception as exc:
        logger.error(
            f"DB error looking up document {document_id}: {exc}"
        )
        raise HTTPException(status_code=500, detail="Database error")

    if not row or row.source_type != "CONVERSATION":
        raise HTTPException(
            status_code=404, detail="Conversation source not found"
        )

    thread_id = (row.file_path or "").replace(
        "conversation://", ""
    )
    if not thread_id:
        raise HTTPException(
            status_code=404,
            detail="Thread ID not found for document",
        )

    # 2. Load thread metadata + messages directly from DB
    try:
        async with db_manager.get_async_session() as sess:
            t_row = (await sess.execute(
                sa_text(
                    "SELECT created_at "
                    "FROM multimodal_librarian.conversation_threads "
                    "WHERE id = :tid"
                ),
                {"tid": thread_id},
            )).fetchone()

            msg_rows = (await sess.execute(
                sa_text(
                    "SELECT content, message_type::text, "
                    "       knowledge_references, created_at "
                    "FROM multimodal_librarian.messages "
                    "WHERE thread_id = :tid "
                    "ORDER BY created_at ASC"
                ),
                {"tid": thread_id},
            )).fetchall()
    except Exception as exc:
        logger.error(
            f"DB error loading conversation {thread_id}: {exc}"
        )
        raise HTTPException(status_code=500, detail="Database error")

    if not t_row or not msg_rows:
        raise HTTPException(
            status_code=404, detail="Conversation not found"
        )

    # 3. Build markdown content matching the main Export format
    content_parts = []
    content_parts.append("# Conversation Export")
    content_parts.append(f"**Title:** {row.title or 'Untitled'}")
    content_parts.append(f"**Started:** {t_row.created_at.strftime('%Y-%m-%d %H:%M:%S')}")
    content_parts.append(f"**Messages:** {len(msg_rows)}")
    content_parts.append("")

    for mr in msg_rows:
        content = mr.content or ""
        mt_str = (mr.message_type or "USER").upper()
        sender = "User" if mt_str == "USER" else "Assistant"
        ts = mr.created_at.strftime("%H:%M:%S")

        content_parts.append(f"## {sender} ({ts})")

        # Parse knowledge_references (JSONB column)
        kr_raw = mr.knowledge_references
        refs = []
        if kr_raw:
            if isinstance(kr_raw, str):
                try:
                    kr_raw = _json.loads(kr_raw)
                except Exception:
                    kr_raw = []
            if isinstance(kr_raw, list):
                refs = [r for r in kr_raw if isinstance(r, dict)]

        # Replace inline [Source N] references with markdown links
        msg_content = content
        if refs and mt_str != "USER":
            def _expand_multi(m):
                inner = m.group(1)
                parts = [p.strip() for p in inner.split(',')]
                return ' '.join(f'[{p}]' for p in parts)
            msg_content = re.sub(
                r'\[(Source \d+(?:\s*,\s*Source \d+)+)\]',
                _expand_multi, msg_content,
            )

            def _replace_source_ref(match):
                idx = int(match.group(1)) - 1
                if 0 <= idx < len(refs):
                    url = refs[idx].get("url", "")
                    if url:
                        return f"[Source {idx+1}]({url})"
                return match.group(0)
            msg_content = re.sub(r'\[Source (\d+)\]', _replace_source_ref, msg_content)

        content_parts.append(msg_content)

        # Add citations section for assistant messages
        if refs and mt_str != "USER":
            content_parts.append("")
            content_parts.append("**Sources:**")
            for idx, ref in enumerate(refs, 1):
                title = ref.get("document_title") or "Unknown"
                url = ref.get("url", "")
                relevance = ref.get("relevance_score", 0)
                if url:
                    content_parts.append(
                        f"  {idx}. [{title}]({url}) - {int(relevance * 100)}% relevant"
                    )
                else:
                    page = ref.get("page_number", "")
                    page_str = f" (p.{page})" if page else ""
                    content_parts.append(
                        f"  {idx}. {title}{page_str} - {int(relevance * 100)}% relevant"
                    )

        content_parts.append("")

    # 4. Generate PDF via ExportEngine
    export_content = MultimediaResponse(
        text_content="\n".join(content_parts),
        visualizations=[],
        audio_content=None,
        video_content=None,
        knowledge_citations=[],
        export_metadata=None,
    )

    export_engine = ExportEngine()
    pdf_bytes = export_engine.export_to_format(export_content, "pdf")

    safe_title = (row.title or "conversation").replace(" ", "_")[:60]
    filename = f"{safe_title}.pdf"

    return StreamingResponse(
        io.BytesIO(pdf_bytes),
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"'
        },
    )


@router.get("/{document_id}/status")
async def get_document_status(
    document_id: UUID,
    document_manager: DocumentManager = Depends(get_document_manager)
):
    """
    Get comprehensive document processing status.
    
    - **document_id**: Unique document identifier
    
    Returns current processing status, progress, and detailed information
    including enrichment status if available.
    """
    try:
        status_info = await document_manager.get_document_status(document_id)
        
        response_content = {
            "document_id": str(status_info['document_id']),
            "title": status_info['title'],
            "filename": status_info['filename'],
            "file_size": status_info['file_size'],
            "status": status_info['status'],
            "progress_percentage": status_info.get('processing_progress', 0),
            "current_step": status_info.get('current_step', 'Unknown'),
            "upload_timestamp": status_info['upload_timestamp'].isoformat(),
            "processing_started_at": status_info['processing_started_at'].isoformat() if status_info['processing_started_at'] else None,
            "processing_completed_at": status_info['processing_completed_at'].isoformat() if status_info['processing_completed_at'] else None,
            "processing_error": status_info['processing_error'],
            "retry_count": status_info.get('retry_count', 0),
            "job_metadata": status_info.get('job_metadata', {})
        }
        
        # Include enrichment status if available
        if 'enrichment_status' in status_info:
            response_content['enrichment_status'] = status_info['enrichment_status']
        
        return JSONResponse(
            status_code=status.HTTP_200_OK,
            content=response_content
        )
        
    except DocumentManagerError as e:
        if "not found" in str(e).lower():
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=str(e)
            )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )
    except Exception as e:
        logger.error(f"Error getting status for document {document_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get document status"
        )


@router.get("/stats/summary")
async def get_comprehensive_statistics(
    document_manager: DocumentManager = Depends(get_document_manager)
):
    """
    Get comprehensive statistics including processing metrics.
    
    Returns detailed statistics about uploads, processing, and system health.
    """
    try:
        stats = document_manager.get_manager_statistics()
        return JSONResponse(
            status_code=status.HTTP_200_OK,
            content=stats
        )
        
    except Exception as e:
        logger.error(f"Error getting comprehensive statistics: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get statistics"
        )


# Health check endpoint
@router.get("/health")
async def health_check(
    document_manager: DocumentManager = Depends(get_document_manager)
):
    """
    Comprehensive health check for document service.
    
    Returns service health status including all components.
    """
    try:
        health_status = document_manager.health_check()
        
        status_code = status.HTTP_200_OK
        if health_status.get('status') == 'unhealthy':
            status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        elif health_status.get('status') == 'degraded':
            status_code = status.HTTP_200_OK  # Still operational
        
        health_status['timestamp'] = logger.info("Health check completed")
        
        return JSONResponse(
            status_code=status_code,
            content=health_status
        )
        
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={
                "status": "unhealthy",
                "service": "documents",
                "error": str(e)
            }
        )


@router.get("/manager")
async def document_manager_page():
    """
    Serve the document manager web interface.
    
    Returns the HTML page for document management.
    """
    from fastapi import Request
    from fastapi.responses import HTMLResponse
    from fastapi.templating import Jinja2Templates

    # This is a placeholder - in a real implementation, you'd use proper templating
    # For now, return a simple redirect or basic HTML
    html_content = """
    <!DOCTYPE html>
    <html>
    <head>
        <title>Document Manager</title>
        <meta http-equiv="refresh" content="0; url=/static/document_manager.html">
    </head>
    <body>
        <p>Redirecting to document manager...</p>
        <p>If not redirected, <a href="/static/document_manager.html">click here</a></p>
    </body>
    </html>
    """
    
    return HTMLResponse(content=html_content)


# Processing Management Endpoints

@router.get("/{document_id}/processing/status")
async def get_processing_status(
    document_id: UUID,
    processing_service: ProcessingService = Depends(get_processing_service)
):
    """
    Get detailed processing status for a document.
    
    - **document_id**: Unique document identifier
    
    Returns comprehensive processing status including Celery task information.
    """
    try:
        status_info = await processing_service.get_processing_status(document_id)
        
        if not status_info:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"No processing job found for document: {document_id}"
            )
        
        return JSONResponse(
            status_code=status.HTTP_200_OK,
            content=status_info
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting processing status for {document_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get processing status"
        )


@router.post("/{document_id}/processing/cancel")
async def cancel_processing(
    document_id: UUID,
    processing_service: ProcessingService = Depends(get_processing_service)
):
    """
    Cancel document processing.
    
    - **document_id**: Unique document identifier
    
    Returns cancellation confirmation.
    """
    try:
        success = await processing_service.cancel_processing(document_id)
        
        if not success:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Document processing cannot be cancelled (not found or not cancellable)"
            )
        
        return JSONResponse(
            status_code=status.HTTP_200_OK,
            content={
                "message": "Document processing cancelled successfully",
                "document_id": str(document_id)
            }
        )
        
    except HTTPException:
        raise
    except ProcessingError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        logger.error(f"Error cancelling processing for {document_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to cancel processing"
        )


@router.post("/{document_id}/processing/retry")
async def retry_processing(
    document_id: UUID,
    processing_service: ProcessingService = Depends(get_processing_service)
):
    """
    Retry failed document processing.
    
    - **document_id**: Unique document identifier
    
    Returns retry job information.
    """
    try:
        result = await processing_service.retry_failed_processing(document_id)
        
        return JSONResponse(
            status_code=status.HTTP_200_OK,
            content={
                "message": "Document processing retry initiated",
                "document_id": result['document_id'],
                "task_id": result['task_id'],
                "status": result['status']
            }
        )
        
    except ProcessingError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        logger.error(f"Error retrying processing for {document_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retry processing"
        )


@router.get("/processing/jobs/active")
async def get_active_processing_jobs(
    processing_service: ProcessingService = Depends(get_processing_service)
):
    """
    Get all active processing jobs.
    
    Returns list of currently active processing jobs across all documents.
    """
    try:
        active_jobs = await processing_service.get_active_jobs()
        
        return JSONResponse(
            status_code=status.HTTP_200_OK,
            content={
                "active_jobs": active_jobs,
                "total_active": len(active_jobs)
            }
        )
        
    except Exception as e:
        logger.error(f"Error getting active processing jobs: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get active processing jobs"
        )


@router.get("/processing/health")
async def get_processing_health(
    processing_service: ProcessingService = Depends(get_processing_service)
):
    """
    Get processing service health status.
    
    Returns health status of Celery workers, Redis, and processing components.
    """
    try:
        health_status = processing_service.celery_service.health_check()
        
        status_code = status.HTTP_200_OK
        if health_status.get('status') == 'unhealthy':
            status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        elif health_status.get('status') == 'degraded':
            status_code = status.HTTP_200_OK
        
        return JSONResponse(
            status_code=status_code,
            content=health_status
        )
        
    except Exception as e:
        logger.error(f"Error getting processing health: {e}")
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={
                "status": "unhealthy",
                "error": str(e)
            }
        )


# Knowledge Graph Endpoints

@router.get("/{document_id}/knowledge/search")
async def search_document_knowledge(
    document_id: UUID,
    query: str,
    max_results: int = 10,
    document_manager: DocumentManager = Depends(get_document_manager)
):
    """
    Search knowledge graph within a specific document.
    
    - **document_id**: Unique document identifier
    - **query**: Search query for concepts and relationships
    - **max_results**: Maximum number of results to return (default: 10)
    
    Returns concepts and relationships matching the query within the document.
    """
    try:
        if not query or len(query.strip()) < 2:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Query must be at least 2 characters long"
            )
        
        if max_results < 1 or max_results > 100:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="max_results must be between 1 and 100"
            )
        
        search_results = await document_manager.search_document_knowledge(
            document_id, query.strip(), max_results
        )
        
        return JSONResponse(
            status_code=status.HTTP_200_OK,
            content=search_results
        )
        
    except HTTPException:
        raise
    except DocumentManagerError as e:
        logger.error(f"Knowledge search failed for document {document_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Knowledge search failed: {str(e)}"
        )
    except Exception as e:
        logger.error(f"Unexpected error in knowledge search for document {document_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Knowledge search failed"
        )


@router.get("/{document_id}/knowledge/summary")
async def get_document_knowledge_summary(
    document_id: UUID,
    document_manager: DocumentManager = Depends(get_document_manager)
):
    """
    Get knowledge graph summary for a specific document.
    
    - **document_id**: Unique document identifier
    
    Returns summary of concepts, relationships, and knowledge statistics for the document.
    """
    try:
        knowledge_summary = await document_manager.get_document_knowledge_summary(document_id)
        
        if 'error' in knowledge_summary:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=knowledge_summary['error']
            )
        
        return JSONResponse(
            status_code=status.HTTP_200_OK,
            content=knowledge_summary
        )
        
    except HTTPException:
        raise
    except DocumentManagerError as e:
        logger.error(f"Knowledge summary failed for document {document_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Knowledge summary failed: {str(e)}"
        )
    except Exception as e:
        logger.error(f"Unexpected error getting knowledge summary for document {document_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Knowledge summary failed"
        )


@router.post("/knowledge/feedback")
async def process_knowledge_feedback(
    feedback_data: dict,
    document_manager: DocumentManager = Depends(get_document_manager)
):
    """
    Process user feedback about knowledge graph elements.
    
    - **feedback_data**: Feedback information including type, element_id, score, and user_id
    
    Expected format:
    ```json
    {
        "type": "concept|relationship",
        "element_id": "concept_id or relationship_key",
        "score": -1.0 to 1.0,
        "user_id": "user_identifier",
        "comment": "optional feedback comment"
    }
    ```
    
    Returns feedback processing confirmation.
    """
    try:
        # Validate required fields
        required_fields = ['type', 'element_id', 'score', 'user_id']
        missing_fields = [field for field in required_fields if field not in feedback_data]
        
        if missing_fields:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Missing required fields: {', '.join(missing_fields)}"
            )
        
        # Validate field values
        if feedback_data['type'] not in ['concept', 'relationship']:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Type must be 'concept' or 'relationship'"
            )
        
        try:
            score = float(feedback_data['score'])
            if score < -1.0 or score > 1.0:
                raise ValueError()
        except (ValueError, TypeError):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Score must be a number between -1.0 and 1.0"
            )
        
        # Process feedback
        success = await document_manager.process_knowledge_feedback(feedback_data)
        
        if not success:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to process feedback"
            )
        
        return JSONResponse(
            status_code=status.HTTP_200_OK,
            content={
                "message": "Feedback processed successfully",
                "type": feedback_data['type'],
                "element_id": feedback_data['element_id'],
                "score": score
            }
        )
        
    except HTTPException:
        raise
    except DocumentManagerError as e:
        logger.error(f"Knowledge feedback processing failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Feedback processing failed: {str(e)}"
        )
    except Exception as e:
        logger.error(f"Unexpected error processing knowledge feedback: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Feedback processing failed"
        )


@router.get("/knowledge/statistics")
async def get_knowledge_graph_statistics(
    document_manager: DocumentManager = Depends(get_document_manager)
):
    """
    Get comprehensive knowledge graph statistics.
    
    Returns statistics about concepts, relationships, processing metrics, and health.
    """
    try:
        # Get knowledge graph statistics from processing service
        kg_stats = document_manager.processing_service.get_knowledge_graph_statistics()
        
        return JSONResponse(
            status_code=status.HTTP_200_OK,
            content=kg_stats
        )
        
    except Exception as e:
        logger.error(f"Error getting knowledge graph statistics: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get knowledge graph statistics"
        )
