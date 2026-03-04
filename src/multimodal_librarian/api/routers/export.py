"""
Export functionality API endpoints.

This module handles export of query responses, conversations, and knowledge
content to various formats including .txt, .docx, .pdf, .rtf, .pptx, and .xlsx.
"""

import os
import time
import logging
from typing import List, Optional, Dict, Any
from datetime import datetime, timedelta
from uuid import uuid4

from fastapi import APIRouter, HTTPException, Depends, BackgroundTasks
from fastapi.responses import FileResponse, StreamingResponse

from ...components.export_engine.export_engine import ExportEngine
from ...components.conversation.conversation_manager import ConversationManager
from ...components.query_processor.query_processor import UnifiedKnowledgeQueryProcessor
from ...models.core import MultimediaResponse, ExportMetadata, KnowledgeCitation
from ..models import (
    APIResponse, ErrorResponse,
    ExportRequest, ExportResponse
)
from ..middleware import get_user_id, get_request_id
from ...config import get_settings

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1/export")
settings = get_settings()

# Initialize components
export_engine = ExportEngine()
conversation_manager = ConversationManager()

# In-memory export tracking (in production, use database)
export_registry: Dict[str, Dict[str, Any]] = {}


@router.post("/conversation/{thread_id}", response_model=ExportResponse)
async def export_conversation(
    thread_id: str,
    request: ExportRequest,
    background_tasks: BackgroundTasks,
    user_id: Optional[str] = Depends(get_user_id)
):
    """
    Export a conversation thread to the specified format.
    
    Supports all major document formats with multimedia content preservation.
    """
    try:
        # Validate export format
        supported_formats = ["txt", "docx", "pdf", "rtf", "pptx", "xlsx"]
        if request.export_format not in supported_formats:
            raise HTTPException(
                status_code=400,
                detail=f"Unsupported export format. Supported: {', '.join(supported_formats)}"
            )
        
        # Get conversation thread
        conversation = conversation_manager.get_conversation_thread(thread_id)
        if not conversation:
            raise HTTPException(status_code=404, detail="Conversation not found")
        
        # Check user access
        if user_id and conversation.user_id != user_id:
            raise HTTPException(status_code=403, detail="Access denied")
        
        # Generate export ID
        export_id = str(uuid4())
        
        # Create export metadata
        export_metadata = ExportMetadata(
            export_format=request.export_format,
            created_at=datetime.now(),
            includes_media=request.include_multimedia
        )
        
        # Register export job
        export_registry[export_id] = {
            "export_id": export_id,
            "content_type": "conversation",
            "content_id": thread_id,
            "format": request.export_format,
            "status": "processing",
            "created_at": datetime.now(),
            "user_id": user_id,
            "file_path": None,
            "file_size": 0,
            "error": None
        }
        
        # Schedule background export processing
        background_tasks.add_task(
            process_conversation_export,
            export_id=export_id,
            conversation=conversation,
            export_format=request.export_format,
            include_multimedia=request.include_multimedia
        )
        
        # Calculate expiry time (24 hours from now)
        expires_at = datetime.now() + timedelta(hours=24)
        
        logger.info(f"Started export of conversation {thread_id} to {request.export_format}")
        
        return ExportResponse(
            message="Export started successfully",
            export_id=export_id,
            download_url=f"/api/v1/export/{export_id}/download",
            file_size=0,  # Will be updated when processing completes
            expires_at=expires_at
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error starting conversation export: {e}")
        raise HTTPException(status_code=500, detail="Export initialization failed")


@router.post("/query-result", response_model=ExportResponse)
async def export_query_result(
    request: ExportRequest,
    query_data: Dict[str, Any],
    background_tasks: BackgroundTasks,
    user_id: Optional[str] = Depends(get_user_id)
):
    """
    Export query results to the specified format.
    
    Takes query result data and exports it with proper formatting and citations.
    """
    try:
        # Validate export format
        supported_formats = ["txt", "docx", "pdf", "rtf", "pptx", "xlsx"]
        if request.export_format not in supported_formats:
            raise HTTPException(
                status_code=400,
                detail=f"Unsupported export format. Supported: {', '.join(supported_formats)}"
            )
        
        # Validate query data
        if not query_data.get("text_content"):
            raise HTTPException(
                status_code=400,
                detail="Query result must contain text_content"
            )
        
        # Generate export ID
        export_id = str(uuid4())
        
        # Register export job
        export_registry[export_id] = {
            "export_id": export_id,
            "content_type": "query_result",
            "content_id": request.content_id,
            "format": request.export_format,
            "status": "processing",
            "created_at": datetime.now(),
            "user_id": user_id,
            "file_path": None,
            "file_size": 0,
            "error": None
        }
        
        # Schedule background export processing
        background_tasks.add_task(
            process_query_result_export,
            export_id=export_id,
            query_data=query_data,
            export_format=request.export_format,
            include_multimedia=request.include_multimedia
        )
        
        # Calculate expiry time
        expires_at = datetime.now() + timedelta(hours=24)
        
        logger.info(f"Started export of query result to {request.export_format}")
        
        return ExportResponse(
            message="Export started successfully",
            export_id=export_id,
            download_url=f"/api/v1/export/{export_id}/download",
            file_size=0,
            expires_at=expires_at
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error starting query result export: {e}")
        raise HTTPException(status_code=500, detail="Export initialization failed")


@router.get("/{export_id}/status", response_model=Dict[str, Any])
async def get_export_status(
    export_id: str,
    user_id: Optional[str] = Depends(get_user_id)
):
    """
    Get the status of an export job.
    
    Returns current processing status, progress, and any error information.
    """
    try:
        if export_id not in export_registry:
            raise HTTPException(status_code=404, detail="Export not found")
        
        export_info = export_registry[export_id]
        
        # Check user access
        if user_id and export_info.get("user_id") != user_id:
            raise HTTPException(status_code=403, detail="Access denied")
        
        # Calculate progress (simplified)
        progress = 100.0 if export_info["status"] == "completed" else 50.0 if export_info["status"] == "processing" else 0.0
        
        status_response = {
            "export_id": export_id,
            "status": export_info["status"],
            "progress": progress,
            "created_at": export_info["created_at"].isoformat(),
            "file_size": export_info["file_size"],
            "format": export_info["format"],
            "content_type": export_info["content_type"]
        }
        
        if export_info.get("error"):
            status_response["error"] = export_info["error"]
        
        if export_info["status"] == "completed":
            status_response["download_url"] = f"/api/v1/export/{export_id}/download"
        
        return status_response
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting export status: {e}")
        raise HTTPException(status_code=500, detail="Failed to get export status")


@router.get("/{export_id}/download")
async def download_export(
    export_id: str,
    user_id: Optional[str] = Depends(get_user_id)
):
    """
    Download a completed export file.
    
    Returns the exported file as a downloadable response.
    """
    try:
        if export_id not in export_registry:
            raise HTTPException(status_code=404, detail="Export not found")
        
        export_info = export_registry[export_id]
        
        # Check user access
        if user_id and export_info.get("user_id") != user_id:
            raise HTTPException(status_code=403, detail="Access denied")
        
        # Check if export is completed
        if export_info["status"] != "completed":
            raise HTTPException(
                status_code=409,
                detail=f"Export is not ready. Current status: {export_info['status']}"
            )
        
        # Check if file exists
        file_path = export_info.get("file_path")
        if not file_path or not os.path.exists(file_path):
            raise HTTPException(status_code=404, detail="Export file not found")
        
        # Determine media type
        media_type_map = {
            "txt": "text/plain",
            "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            "pdf": "application/pdf",
            "rtf": "application/rtf",
            "pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
            "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        }
        
        media_type = media_type_map.get(export_info["format"], "application/octet-stream")
        
        # Generate filename
        timestamp = export_info["created_at"].strftime("%Y%m%d_%H%M%S")
        filename = f"{export_info['content_type']}_{timestamp}.{export_info['format']}"
        
        logger.info(f"Serving export download: {export_id}")
        
        return FileResponse(
            path=file_path,
            filename=filename,
            media_type=media_type,
            headers={
                "Content-Disposition": f"attachment; filename={filename}",
                "Cache-Control": "no-cache"
            }
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error downloading export: {e}")
        raise HTTPException(status_code=500, detail="Download failed")


@router.delete("/{export_id}", response_model=APIResponse)
async def delete_export(
    export_id: str,
    user_id: Optional[str] = Depends(get_user_id)
):
    """
    Delete an export job and its associated file.
    
    Removes the export from the registry and deletes the file from storage.
    """
    try:
        if export_id not in export_registry:
            raise HTTPException(status_code=404, detail="Export not found")
        
        export_info = export_registry[export_id]
        
        # Check user access
        if user_id and export_info.get("user_id") != user_id:
            raise HTTPException(status_code=403, detail="Access denied")
        
        # Delete file if it exists
        file_path = export_info.get("file_path")
        if file_path and os.path.exists(file_path):
            try:
                os.remove(file_path)
                logger.info(f"Deleted export file: {file_path}")
            except Exception as e:
                logger.warning(f"Could not delete export file {file_path}: {e}")
        
        # Remove from registry
        del export_registry[export_id]
        
        logger.info(f"Deleted export: {export_id}")
        
        return APIResponse(
            message="Export deleted successfully"
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting export: {e}")
        raise HTTPException(status_code=500, detail="Failed to delete export")


@router.get("/", response_model=Dict[str, List[Dict[str, Any]]])
async def list_user_exports(
    user_id: Optional[str] = Depends(get_user_id),
    limit: int = 50,
    status_filter: Optional[str] = None
):
    """
    List export jobs for the current user.
    
    Returns a list of export jobs with their current status and metadata.
    """
    try:
        if not user_id:
            raise HTTPException(status_code=401, detail="Authentication required")
        
        # Filter exports for user
        user_exports = []
        for export_id, export_info in export_registry.items():
            if export_info.get("user_id") == user_id:
                if status_filter and export_info["status"] != status_filter:
                    continue
                
                export_summary = {
                    "export_id": export_id,
                    "content_type": export_info["content_type"],
                    "format": export_info["format"],
                    "status": export_info["status"],
                    "created_at": export_info["created_at"].isoformat(),
                    "file_size": export_info["file_size"]
                }
                
                if export_info["status"] == "completed":
                    export_summary["download_url"] = f"/api/v1/export/{export_id}/download"
                
                user_exports.append(export_summary)
        
        # Sort by creation time (newest first) and limit
        user_exports.sort(key=lambda x: x["created_at"], reverse=True)
        user_exports = user_exports[:limit]
        
        return {
            "exports": user_exports
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error listing user exports: {e}")
        raise HTTPException(status_code=500, detail="Failed to list exports")


# Background task functions

async def process_conversation_export(
    export_id: str,
    conversation,
    export_format: str,
    include_multimedia: bool
):
    """Background task to process conversation export."""
    try:
        logger.info(f"Processing conversation export {export_id}")
        
        # Update status
        export_registry[export_id]["status"] = "processing"
        
        # Create export content
        export_content = create_conversation_export_content(
            conversation, 
            include_multimedia
        )
        
        # Generate export file
        export_data = export_engine.export_to_format(export_content, export_format)
        
        # Save to file
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"conversation_{conversation.thread_id}_{timestamp}.{export_format}"
        file_path = os.path.join(settings.export_dir, filename)
        
        with open(file_path, "wb") as f:
            f.write(export_data)
        
        # Update registry
        export_registry[export_id].update({
            "status": "completed",
            "file_path": file_path,
            "file_size": len(export_data)
        })
        
        logger.info(f"Completed conversation export {export_id}")
        
    except Exception as e:
        logger.error(f"Error processing conversation export {export_id}: {e}")
        export_registry[export_id].update({
            "status": "failed",
            "error": str(e)
        })


async def process_query_result_export(
    export_id: str,
    query_data: Dict[str, Any],
    export_format: str,
    include_multimedia: bool
):
    """Background task to process query result export."""
    try:
        logger.info(f"Processing query result export {export_id}")
        
        # Update status
        export_registry[export_id]["status"] = "processing"
        
        # Create multimedia response from query data
        multimedia_response = MultimediaResponse(
            text_content=query_data["text_content"],
            visualizations=query_data.get("visualizations", []),
            knowledge_citations=[
                KnowledgeCitation.from_dict(citation) 
                for citation in query_data.get("knowledge_citations", [])
            ],
            export_metadata=ExportMetadata(
                export_format=export_format,
                includes_media=include_multimedia
            )
        )
        
        # Generate export file
        export_data = export_engine.export_to_format(multimedia_response, export_format)
        
        # Save to file
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"query_result_{timestamp}.{export_format}"
        file_path = os.path.join(settings.export_dir, filename)
        
        with open(file_path, "wb") as f:
            f.write(export_data)
        
        # Update registry
        export_registry[export_id].update({
            "status": "completed",
            "file_path": file_path,
            "file_size": len(export_data)
        })
        
        logger.info(f"Completed query result export {export_id}")
        
    except Exception as e:
        logger.error(f"Error processing query result export {export_id}: {e}")
        export_registry[export_id].update({
            "status": "failed",
            "error": str(e)
        })


def create_conversation_export_content(conversation, include_multimedia: bool) -> MultimediaResponse:
    """Create export content from conversation thread."""
    content_parts = []
    content_parts.append(f"# Conversation Export")
    content_parts.append(f"**Started:** {conversation.created_at.strftime('%Y-%m-%d %H:%M:%S')}")
    content_parts.append(f"**Thread ID:** {conversation.thread_id}")
    content_parts.append(f"**Total Messages:** {conversation.get_message_count()}")
    content_parts.append("")
    
    visualizations = []
    citations = []
    
    for i, message in enumerate(conversation.messages, 1):
        sender = "User" if message.message_type.value == "user" else "Assistant"
        timestamp = message.timestamp.strftime('%Y-%m-%d %H:%M:%S')
        
        content_parts.append(f"## Message {i} - {sender}")
        content_parts.append(f"**Time:** {timestamp}")
        content_parts.append("")
        content_parts.append(message.content)
        content_parts.append("")
        
        # Include multimedia content info
        if message.has_multimedia() and include_multimedia:
            content_parts.append("**Attachments:**")
            for media in message.multimedia_content:
                content_parts.append(f"- {media.element_type}: {media.filename or 'unnamed'}")
            content_parts.append("")
        
        # Add knowledge references as citations
        for ref_id in message.knowledge_references:
            citation = KnowledgeCitation(
                source_type=SourceType.CONVERSATION,
                source_title=f"Message {i}",
                location_reference=timestamp,
                chunk_id=ref_id,
                relevance_score=1.0
            )
            citations.append(citation)
    
    return MultimediaResponse(
        text_content="\n".join(content_parts),
        visualizations=visualizations,
        knowledge_citations=citations,
        export_metadata=ExportMetadata(
            export_format="conversation",
            includes_media=include_multimedia
        )
    )


@router.get("/health", response_model=Dict[str, Any])
async def export_service_health():
    """Health check for export service."""
    health_status = {
        "status": "healthy",
        "service": "export",
        "components": {
            "export_engine": "healthy" if export_engine else "unavailable",
            "export_directory": "healthy" if os.path.exists(settings.export_dir) else "unhealthy"
        },
        "active_exports": len([e for e in export_registry.values() if e["status"] == "processing"]),
        "completed_exports": len([e for e in export_registry.values() if e["status"] == "completed"])
    }
    
    # Check export directory
    if not os.path.exists(settings.export_dir):
        health_status["status"] = "degraded"
        health_status["components"]["export_directory"] = "missing"
    
    return health_status