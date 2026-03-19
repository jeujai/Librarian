"""
Conversation management API endpoints.

This module handles conversation thread management, message history,
and conversation knowledge export functionality.
"""

import logging
import os
from datetime import datetime
from typing import Any, Dict, List, Optional
from uuid import uuid4

from fastapi import APIRouter, BackgroundTasks, Depends, File, HTTPException, UploadFile
from fastapi.responses import FileResponse, StreamingResponse

from ...components.conversation.conversation_manager import ConversationManager
from ...components.export_engine.export_engine import ExportEngine
from ...config import get_settings
from ...models.core import ConversationThread, Message, MessageType, MultimediaElement
from ..dependencies import get_conversation_knowledge_service_optional
from ..middleware import get_request_id, get_user_id
from ..models import (
    APIResponse,
    ChatMessageRequest,
    ChatMessageResponse,
    ConversationListResponse,
    DeleteConversationRequest,
    ErrorResponse,
    ExportRequest,
    ExportResponse,
    FileProcessingStatus,
    FileUploadResponse,
    StartConversationRequest,
    StartConversationResponse,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1/conversations")
settings = get_settings()

# Initialize components
conversation_manager = ConversationManager()
export_engine = ExportEngine()

# File processing status tracking (in-memory for now, could be Redis in production)
_file_processing_status: Dict[str, Dict[str, Any]] = {}


@router.post("/start", response_model=StartConversationResponse)
async def start_conversation(
    request: StartConversationRequest,
    background_tasks: BackgroundTasks,
    user_id: Optional[str] = Depends(get_user_id),
    knowledge_service=Depends(
        get_conversation_knowledge_service_optional
    ),
):
    """Start a new conversation thread."""
    try:
        # Use provided user_id or generate one
        effective_user_id = (
            user_id or request.user_id or str(uuid4())
        )
        
        # Create new conversation thread
        thread = conversation_manager.start_conversation(
            user_id=effective_user_id
        )
        
        # Add initial message if provided
        if request.initial_message:
            initial_msg = Message(
                message_id=str(uuid4()),
                content=request.initial_message,
                message_type=MessageType.USER
            )
            thread.add_message(initial_msg)
        
        # Schedule background conversion for previous thread
        if request.previous_thread_id:
            if knowledge_service is not None:
                prev_thread = (
                    conversation_manager.get_conversation_thread(
                        request.previous_thread_id
                    )
                )
                if (
                    prev_thread
                    and prev_thread.get_message_count() > 0
                ):
                    background_tasks.add_task(
                        knowledge_service.convert_conversation,
                        request.previous_thread_id,
                    )
                    logger.info(
                        "Scheduled background conversion for "
                        f"previous thread: "
                        f"{request.previous_thread_id}"
                    )
            else:
                logger.warning(
                    "Knowledge service unavailable, "
                    "skipping conversion for previous "
                    f"thread: {request.previous_thread_id}"
                )
        
        logger.info(
            f"Started new conversation thread: "
            f"{thread.thread_id}"
        )
        
        return StartConversationResponse(
            message="Conversation started successfully",
            thread_id=thread.thread_id,
            created_at=thread.created_at
        )
        
    except Exception as e:
        logger.error(f"Error starting conversation: {e}")
        raise HTTPException(
            status_code=500,
            detail="Failed to start conversation"
        )


@router.get("/", response_model=ConversationListResponse)
async def list_conversations(
    user_id: Optional[str] = Depends(get_user_id),
    limit: int = 50,
    offset: int = 0
):
    """List conversation threads for a user."""
    try:
        if not user_id:
            raise HTTPException(status_code=401, detail="User authentication required")
        
        # Get conversations for user
        conversations = conversation_manager.list_conversations(
            user_id=user_id,
            limit=limit,
            offset=offset
        )
        
        # Convert to API format
        conversation_data = []
        for thread in conversations:
            conversation_data.append({
                "thread_id": thread.thread_id,
                "created_at": thread.created_at.isoformat(),
                "last_updated": thread.last_updated.isoformat(),
                "message_count": thread.get_message_count(),
                "knowledge_summary": thread.knowledge_summary,
                "latest_message": thread.get_latest_message().content if thread.get_latest_message() else ""
            })
        
        total_count = conversation_manager.count_conversations(user_id=user_id)
        
        return ConversationListResponse(
            message=f"Retrieved {len(conversations)} conversations",
            conversations=conversation_data,
            total_count=total_count
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error listing conversations: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve conversations")


@router.get("/{thread_id}", response_model=dict)
async def get_conversation(
    thread_id: str,
    user_id: Optional[str] = Depends(get_user_id)
):
    """Get a specific conversation thread with full message history."""
    try:
        # Get conversation thread
        thread = conversation_manager.get_conversation_thread(thread_id)
        
        if not thread:
            raise HTTPException(status_code=404, detail="Conversation not found")
        
        # Check user access (if authentication is enabled)
        if user_id and thread.user_id != user_id:
            raise HTTPException(status_code=403, detail="Access denied")
        
        # Convert to API format
        return {
            "success": True,
            "message": "Conversation retrieved successfully",
            "conversation": thread.to_dict()
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error retrieving conversation {thread_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve conversation")


@router.post("/{thread_id}/messages", response_model=ChatMessageResponse)
async def add_message_to_conversation(
    thread_id: str,
    request: ChatMessageRequest,
    user_id: Optional[str] = Depends(get_user_id)
):
    """Add a message to an existing conversation thread."""
    try:
        # Get conversation thread
        thread = conversation_manager.get_conversation_thread(thread_id)
        
        if not thread:
            raise HTTPException(status_code=404, detail="Conversation not found")
        
        # Check user access
        if user_id and thread.user_id != user_id:
            raise HTTPException(status_code=403, detail="Access denied")
        
        # Create message
        message = Message(
            message_id=str(uuid4()),
            content=request.message,
            message_type=MessageType.USER
        )
        
        # Process message through conversation manager
        context = conversation_manager.process_message(thread_id, message)
        
        # Generate response (simplified for now)
        response_content = f"Received your message: '{request.message}'"
        
        response_message = Message(
            message_id=str(uuid4()),
            content=response_content,
            message_type=MessageType.SYSTEM
        )
        
        # Add response to conversation
        thread.add_message(response_message)
        
        return ChatMessageResponse(
            message="Message processed successfully",
            response={
                "text_content": response_content,
                "visualizations": [],
                "knowledge_citations": []
            },
            thread_id=thread_id,
            message_id=response_message.message_id
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error adding message to conversation {thread_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to process message")


@router.delete("/{thread_id}", response_model=APIResponse)
async def delete_conversation(
    thread_id: str,
    user_id: Optional[str] = Depends(get_user_id)
):
    """Delete a conversation thread and all associated data."""
    try:
        # Get conversation thread
        thread = conversation_manager.get_conversation_thread(thread_id)
        
        if not thread:
            raise HTTPException(status_code=404, detail="Conversation not found")
        
        # Check user access
        if user_id and thread.user_id != user_id:
            raise HTTPException(status_code=403, detail="Access denied")
        
        # Delete conversation and associated knowledge (Postgres + Milvus + Neo4j)
        results = await conversation_manager.delete_conversation_completely(thread_id)
        
        if not results.get("postgres_deleted"):
            raise HTTPException(status_code=500, detail="Failed to delete conversation")
        
        # Invalidate retrieval caches so deleted conversation content
        # is no longer returned in search results.
        try:
            from ..dependencies.services import invalidate_rag_cache
            invalidate_rag_cache()
        except Exception as e:
            logger.warning(f"RAG cache invalidation failed: {e}")
        
        logger.info(f"Deleted conversation thread: {thread_id}")
        
        return APIResponse(
            message="Conversation deleted successfully"
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting conversation {thread_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to delete conversation")


@router.post("/{thread_id}/upload", response_model=FileUploadResponse)
async def upload_file_to_conversation(
    thread_id: str,
    file: UploadFile = File(...),
    background_tasks: BackgroundTasks = BackgroundTasks(),
    user_id: Optional[str] = Depends(get_user_id)
):
    """Upload a file to a conversation thread for processing."""
    try:
        # Validate file size
        if file.size and file.size > settings.max_file_size:
            raise HTTPException(status_code=413, detail="File too large")
        
        # Get conversation thread
        thread = conversation_manager.get_conversation_thread(thread_id)
        
        if not thread:
            raise HTTPException(status_code=404, detail="Conversation not found")
        
        # Check user access
        if user_id and thread.user_id != user_id:
            raise HTTPException(status_code=403, detail="Access denied")
        
        # Read file content
        content = await file.read()
        file_id = str(uuid4())
        
        # Create upload message
        upload_message = Message(
            message_id=str(uuid4()),
            content=f"Uploaded file: {file.filename}",
            multimedia_content=[
                MultimediaElement(
                    element_type="document",
                    content=content,
                    filename=file.filename,
                    mime_type=file.content_type
                )
            ],
            message_type=MessageType.UPLOAD
        )
        
        # Add to conversation
        thread.add_message(upload_message)
        
        # Schedule background processing
        background_tasks.add_task(
            process_uploaded_file,
            file_id=file_id,
            thread_id=thread_id,
            content=content,
            filename=file.filename,
            content_type=file.content_type
        )
        
        logger.info(f"File uploaded to conversation {thread_id}: {file.filename}")
        
        return FileUploadResponse(
            message="File uploaded successfully",
            file_id=file_id,
            filename=file.filename,
            size=len(content),
            content_type=file.content_type or "application/octet-stream",
            processing_status="uploaded"
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error uploading file to conversation {thread_id}: {e}")
        raise HTTPException(status_code=500, detail="File upload failed")


@router.get("/{thread_id}/upload/{file_id}/status", response_model=FileProcessingStatus)
async def get_file_processing_status(
    thread_id: str,
    file_id: str,
    user_id: Optional[str] = Depends(get_user_id)
):
    """Get the processing status of an uploaded file."""
    try:
        # Check conversation access
        thread = conversation_manager.get_conversation_thread(thread_id)
        
        if not thread:
            raise HTTPException(status_code=404, detail="Conversation not found")
        
        if user_id and thread.user_id != user_id:
            raise HTTPException(status_code=403, detail="Access denied")
        
        # Get processing status from tracking dictionary
        status_key = f"{thread_id}:{file_id}"
        status_data = _file_processing_status.get(status_key)
        
        if status_data:
            status = FileProcessingStatus(
                file_id=file_id,
                status=status_data.get("status", "unknown"),
                progress=status_data.get("progress", 0.0),
                message=status_data.get("message", ""),
                chunks_created=status_data.get("chunks_created", 0)
            )
        else:
            # File not found in tracking - might be completed and cleaned up
            # or never started
            status = FileProcessingStatus(
                file_id=file_id,
                status="unknown",
                progress=0.0,
                message="File processing status not found",
                chunks_created=0
            )
        
        return status
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting file status for {file_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to get file status")


@router.post("/{thread_id}/export", response_model=ExportResponse)
async def export_conversation(
    thread_id: str,
    request: ExportRequest,
    user_id: Optional[str] = Depends(get_user_id)
):
    """Export a conversation thread to various formats."""
    try:
        # Get conversation thread
        thread = conversation_manager.get_conversation_thread(thread_id)
        
        if not thread:
            raise HTTPException(status_code=404, detail="Conversation not found")
        
        # Check user access
        if user_id and thread.user_id != user_id:
            raise HTTPException(status_code=403, detail="Access denied")
        
        # Create export content
        export_content = create_conversation_export_content(thread)
        
        # Generate export
        export_data = export_engine.export_to_format(export_content, request.export_format)
        export_id = str(uuid4())
        
        # Save export file (in production, save to storage)
        export_filename = f"conversation_{thread_id}_{export_id}.{request.export_format}"
        export_path = f"{settings.export_dir}/{export_filename}"
        
        with open(export_path, "wb") as f:
            f.write(export_data)
        
        # Calculate expiry time
        expires_at = datetime.now().replace(hour=23, minute=59, second=59, microsecond=999999)
        
        logger.info(f"Exported conversation {thread_id} to {request.export_format}")
        
        return ExportResponse(
            message="Conversation exported successfully",
            export_id=export_id,
            download_url=f"/api/v1/conversations/{thread_id}/export/{export_id}/download",
            file_size=len(export_data),
            expires_at=expires_at
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error exporting conversation {thread_id}: {e}")
        raise HTTPException(status_code=500, detail="Export failed")


@router.get("/{thread_id}/export/{export_id}/download")
async def download_conversation_export(
    thread_id: str,
    export_id: str,
    user_id: Optional[str] = Depends(get_user_id)
):
    """Download an exported conversation file."""
    try:
        # Check conversation access
        thread = conversation_manager.get_conversation_thread(thread_id)
        
        if not thread:
            raise HTTPException(status_code=404, detail="Conversation not found")
        
        if user_id and thread.user_id != user_id:
            raise HTTPException(status_code=403, detail="Access denied")
        
        # Find export file
        export_files = [f for f in os.listdir(settings.export_dir) 
                       if f.startswith(f"conversation_{thread_id}_{export_id}")]
        
        if not export_files:
            raise HTTPException(status_code=404, detail="Export file not found")
        
        export_path = f"{settings.export_dir}/{export_files[0]}"
        
        return FileResponse(
            path=export_path,
            filename=export_files[0],
            media_type="application/octet-stream"
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error downloading export {export_id}: {e}")
        raise HTTPException(status_code=500, detail="Download failed")


# Background task functions

async def process_uploaded_file(
    file_id: str,
    thread_id: str,
    content: bytes,
    filename: str,
    content_type: str
):
    """Background task to process uploaded files.
    
    This implements the full document processing pipeline:
    1. Extract content using PDF processor
    2. Apply chunking framework
    3. Generate embeddings
    4. Store in vector database
    5. Update knowledge graph
    6. Update conversation knowledge
    """
    status_key = f"{thread_id}:{file_id}"
    
    def update_status(status: str, progress: float, message: str, chunks_created: int = 0):
        """Helper to update processing status."""
        _file_processing_status[status_key] = {
            "status": status,
            "progress": progress,
            "message": message,
            "chunks_created": chunks_created
        }
    
    try:
        logger.info(f"Processing uploaded file {filename} for conversation {thread_id}")
        update_status("processing", 0.0, "Starting file processing...")
        
        # Import required components
        from ...components.chunking_framework.framework import (
            GenericMultiLevelChunkingFramework,
        )
        from ...components.knowledge_graph.kg_builder import KnowledgeGraphBuilder
        from ...components.pdf_processor.pdf_processor import PDFProcessor
        from ...components.vector_store.vector_store import VectorStore
        from ...models.core import ContentType, KnowledgeChunk, SourceType
        from ...services.knowledge_graph_service import KnowledgeGraphService

        # Step 1: Extract content using PDF processor
        logger.info(f"Step 1: Extracting content from {filename}")
        update_status("processing", 10.0, "Extracting content from file...")
        pdf_processor = PDFProcessor()
        pdf_processor.enable_graceful_degradation_mode(True)
        
        try:
            pdf_content = pdf_processor.extract_content(content)
            logger.info(f"Extracted {len(pdf_content.text)} characters from {filename}")
        except Exception as e:
            logger.error(f"PDF extraction failed for {filename}: {e}")
            # For non-PDF files, treat content as plain text
            from ...models.core import DocumentContent, DocumentMetadata
            pdf_content = DocumentContent(
                text=content.decode('utf-8', errors='ignore') if isinstance(content, bytes) else str(content),
                images=[],
                tables=[],
                charts=[],
                metadata=DocumentMetadata(title=filename, author=None, page_count=1, file_size=len(content))
            )
        
        update_status("processing", 20.0, "Content extracted successfully")
        
        # Step 2: Apply chunking framework
        logger.info(f"Step 2: Applying chunking framework to {filename}")
        update_status("processing", 30.0, "Applying chunking framework...")
        chunking_framework = GenericMultiLevelChunkingFramework()
        processed_document = chunking_framework.process_document(pdf_content, file_id)
        
        chunk_count = len(processed_document.chunks)
        bridge_count = len(processed_document.bridges)
        logger.info(f"Generated {chunk_count} chunks and {bridge_count} bridges for {filename}")
        update_status("processing", 50.0, f"Generated {chunk_count} chunks", chunk_count)
        
        # Step 3 & 4: Generate embeddings and store in vector database
        logger.info(f"Step 3-4: Storing embeddings in vector database for {filename}")
        update_status("processing", 60.0, "Storing embeddings in vector database...")
        vector_store = VectorStore()
        vector_store.connect()
        
        try:
            # Convert processed chunks to KnowledgeChunks
            knowledge_chunks = []
            for i, chunk in enumerate(processed_document.chunks):
                knowledge_chunk = KnowledgeChunk(
                    id=chunk.id,
                    content=chunk.content,
                    source_type=SourceType.CONVERSATION,  # Mark as conversation-sourced
                    source_id=file_id,
                    location_reference=f"conversation:{thread_id}:file:{filename}:chunk:{i}",
                    section=chunk.metadata.get('section', '') if chunk.metadata else '',
                    content_type=ContentType.GENERAL
                )
                knowledge_chunks.append(knowledge_chunk)
            
            # Store chunk embeddings
            vector_store.store_embeddings(knowledge_chunks)
            
            # Store bridge chunks if any
            if processed_document.bridges:
                bridge_chunks = []
                for i, bridge in enumerate(processed_document.bridges):
                    bridge_chunk = KnowledgeChunk(
                        id=f"bridge_{file_id}_{i}",
                        content=bridge.content,
                        source_type=SourceType.CONVERSATION,
                        source_id=file_id,
                        location_reference=f"conversation:{thread_id}:file:{filename}:bridge:{i}",
                        section=f"BRIDGE_{i}",
                        content_type=ContentType.GENERAL
                    )
                    bridge_chunks.append(bridge_chunk)
                
                vector_store.store_bridge_chunks(bridge_chunks)
            
            logger.info(f"Stored {len(knowledge_chunks)} chunks in vector database for {filename}")
            update_status("processing", 75.0, f"Stored {len(knowledge_chunks)} embeddings", chunk_count)
            
        finally:
            vector_store.disconnect()
        
        # Step 5: Update knowledge graph
        logger.info(f"Step 5: Updating knowledge graph for {filename}")
        update_status("processing", 80.0, "Updating knowledge graph...")
        try:
            kg_builder = KnowledgeGraphBuilder()
            kg_service = KnowledgeGraphService()
            await kg_service.client.connect()
            
            # Process each chunk through the knowledge graph builder
            # Collect all concepts first for batched embedding generation
            all_concepts = []
            for chunk in knowledge_chunks:
                extraction = kg_builder.process_knowledge_chunk(chunk)
                all_concepts.extend(extraction.extracted_concepts)
            
            # Batch generate embeddings for all concept names
            concept_embeddings = {}
            if all_concepts:
                try:
                    from ...clients.model_server_client import (
                        get_model_client,
                        initialize_model_client,
                    )
                    
                    model_client = get_model_client()
                    if model_client is None:
                        model_client = await initialize_model_client()
                    
                    if model_client and model_client.enabled:
                        concept_names = [c.concept_name for c in all_concepts]
                        embeddings = await model_client.generate_embeddings(concept_names)
                        if embeddings and len(embeddings) == len(concept_names):
                            for concept, embedding in zip(all_concepts, embeddings):
                                concept_embeddings[concept.concept_id] = embedding
                        else:
                            logger.warning(
                                f"Embedding count mismatch: got "
                                f"{len(embeddings) if embeddings else 0} "
                                f"for {len(concept_names)} concepts"
                            )
                    else:
                        logger.warning(
                            "Model server client unavailable, "
                            "concepts will lack embeddings"
                        )
                except Exception as e:
                    logger.warning(f"Failed to generate concept embeddings: {e}")
            
            # Persist concepts to graph database
            for concept in all_concepts:
                try:
                    properties = {
                        'concept_id': concept.concept_id,
                        'name': concept.concept_name,
                        'type': concept.concept_type,
                        'confidence': concept.confidence,
                        'source_document': file_id,
                        'source_conversation': thread_id
                    }
                    embedding = concept_embeddings.get(concept.concept_id)
                    if embedding is not None:
                        properties['embedding'] = embedding
                    
                    await kg_service.create_node(
                        label='Concept',
                        properties=properties,
                        merge_on=['concept_id']
                    )
                except Exception as e:
                    logger.warning(f"Failed to create concept node: {e}")
            
            logger.info(f"Updated knowledge graph for {filename}")
            
        except Exception as e:
            logger.warning(f"Knowledge graph update failed for {filename}: {e}")
            # Continue without failing - KG is optional enhancement
        
        update_status("processing", 90.0, "Knowledge graph updated", chunk_count)
        
        # Step 6: Update conversation knowledge summary
        logger.info(f"Step 6: Updating conversation knowledge for {filename}")
        try:
            thread = conversation_manager.get_conversation_thread(thread_id)
            if thread:
                # Update the conversation's knowledge summary
                summary_addition = f"\n[File: {filename}] - {chunk_count} knowledge chunks extracted"
                if thread.knowledge_summary:
                    thread.knowledge_summary += summary_addition
                else:
                    thread.knowledge_summary = summary_addition
                
                logger.info(f"Updated conversation {thread_id} knowledge summary")
        except Exception as e:
            logger.warning(f"Failed to update conversation knowledge: {e}")
        
        # Mark as completed
        update_status("completed", 100.0, f"File processed successfully - {chunk_count} chunks, {bridge_count} bridges", chunk_count)
        logger.info(f"Completed processing file {filename} - {chunk_count} chunks, {bridge_count} bridges")
        
    except Exception as e:
        logger.error(f"Error processing file {filename}: {e}")
        update_status("failed", 0.0, f"Processing failed: {str(e)}", 0)
        raise


def create_conversation_export_content(thread: ConversationThread) -> dict:
    """Create export content from conversation thread."""
    content_parts = []
    content_parts.append(f"# Conversation Export")
    content_parts.append(f"**Started:** {thread.created_at.strftime('%Y-%m-%d %H:%M:%S')}")
    content_parts.append(f"**Thread ID:** {thread.thread_id}")
    content_parts.append(f"**Total Messages:** {thread.get_message_count()}")
    content_parts.append("")
    
    for i, message in enumerate(thread.messages, 1):
        sender = "User" if message.message_type == MessageType.USER else "Assistant"
        timestamp = message.timestamp.strftime('%Y-%m-%d %H:%M:%S')
        content_parts.append(f"## Message {i} - {sender}")
        content_parts.append(f"**Time:** {timestamp}")
        content_parts.append("")
        content_parts.append(message.content)
        content_parts.append("")
        
        # Include multimedia content info
        if message.has_multimedia():
            content_parts.append("**Attachments:**")
            for media in message.multimedia_content:
                content_parts.append(f"- {media.element_type}: {media.filename or 'unnamed'}")
            content_parts.append("")
    
    return {
        "text_content": "\n".join(content_parts),
        "visualizations": [],
        "audio_content": None,
        "video_content": None,
        "knowledge_citations": [],
        "export_metadata": {
            "export_format": "conversation",
            "thread_id": thread.thread_id,
            "message_count": thread.get_message_count()
        }
    }