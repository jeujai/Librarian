"""
Conversation Knowledge API Router

Provides endpoints for:
- Converting a conversation thread into queryable knowledge
- Loading conversation history for reopening in chat UI
- Updating conversation document titles

Validates: Requirements 6.1, 7.1, 7.2, 7.3, 7.4, 7.5, 9.2, 9.4
"""

import logging
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from ..dependencies.services import (
    get_conversation_knowledge_service,
    get_conversation_manager,
)

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/conversations",
    tags=["conversation-knowledge"],
)


class ConvertToKnowledgeResponse(BaseModel):
    """API response for conversation knowledge conversion."""

    thread_id: str
    chunks_created: int
    concepts_extracted: int
    status: str = "success"


# --- Conversation History Models ---


class ConversationMessageResponse(BaseModel):
    """A single message in a conversation history."""

    role: str
    content: str
    timestamp: str
    citations: Optional[List[dict]] = None


class ConversationHistoryResponse(BaseModel):
    """Full conversation history for reopening in chat UI."""

    thread_id: str
    messages: List[ConversationMessageResponse]
    title: Optional[str] = None


# --- Title Update Models ---


class TitleUpdateRequest(BaseModel):
    """Request body for updating a conversation document title."""

    title: str = Field(..., min_length=1, max_length=200)


class TitleUpdateResponse(BaseModel):
    """Response after a successful title update."""

    thread_id: str
    title: str
    status: str = "updated"


class ConvertToKnowledgeRequest(BaseModel):
    """Request body for conversation-to-knowledge conversion."""

    title: Optional[str] = None


@router.post(
    "/{thread_id}/convert-to-knowledge",
    response_model=ConvertToKnowledgeResponse,
)
async def convert_conversation_to_knowledge(
    thread_id: str,
    body: ConvertToKnowledgeRequest = ConvertToKnowledgeRequest(),
    service=Depends(get_conversation_knowledge_service),
) -> ConvertToKnowledgeResponse:
    """Convert a conversation thread into searchable knowledge.

    Triggers the full ingestion pipeline: chunking, embedding,
    vector storage, and knowledge graph extraction.

    Accepts an optional title that will be persisted on the
    conversation's knowledge source record.

    Returns:
        ConvertToKnowledgeResponse with counts and status.

    Raises:
        404: Thread not found.
        400: Conversation has no messages.
        500: Pipeline failure with stage info.
    """
    try:
        result = await service.convert_conversation(
            thread_id, title=body.title
        )
        return ConvertToKnowledgeResponse(
            thread_id=result.thread_id,
            chunks_created=result.chunks_created,
            concepts_extracted=result.concepts_extracted,
        )
    except ValueError as e:
        msg = str(e)
        if "not found" in msg:
            raise HTTPException(status_code=404, detail=msg)
        if "no messages" in msg:
            raise HTTPException(status_code=400, detail=msg)
        raise HTTPException(status_code=400, detail=msg)
    except Exception as e:
        logger.error(
            f"Conversation knowledge pipeline failed for "
            f"{thread_id}: {e}"
        )
        raise HTTPException(
            status_code=500,
            detail=f"Ingestion failed at stage: {type(e).__name__}",
        )


@router.get(
    "/{thread_id}/history",
    response_model=ConversationHistoryResponse,
)
async def get_conversation_history(
    thread_id: str,
    conversation_manager=Depends(get_conversation_manager),
) -> ConversationHistoryResponse:
    """Load full conversation messages for reopening in chat UI.

    Returns:
        ConversationHistoryResponse with all messages.

    Raises:
        404: Thread not found.
    """
    conversation = conversation_manager.get_conversation(thread_id)
    if not conversation:
        raise HTTPException(
            status_code=404,
            detail=f"Conversation {thread_id} not found",
        )

    messages = []
    for msg in conversation.messages:
        # Restore citations from knowledge_references for assistant messages
        citations = None
        if msg.message_type.value != "user" and msg.knowledge_references:
            citations = []
            for ref in msg.knowledge_references:
                if isinstance(ref, dict):
                    citations.append(ref)
        messages.append(
            ConversationMessageResponse(
                role=msg.message_type.value,
                content=msg.content,
                timestamp=msg.timestamp.isoformat(),
                citations=citations if citations else None,
            )
        )

    title = conversation_manager.get_conversation_title(thread_id)

    return ConversationHistoryResponse(
        thread_id=thread_id,
        messages=messages,
        title=title,
    )


@router.patch(
    "/{thread_id}/title",
    response_model=TitleUpdateResponse,
)
async def update_conversation_title(
    thread_id: str,
    body: TitleUpdateRequest,
    conversation_manager=Depends(get_conversation_manager),
) -> TitleUpdateResponse:
    """Update the title of a conversation knowledge document.

    Returns:
        TitleUpdateResponse with the persisted title.

    Raises:
        404: Thread not found.
        422: Validation error (empty or too-long title handled by Pydantic).
    """
    # Verify the conversation exists
    conversation = conversation_manager.get_conversation(thread_id)
    if not conversation:
        raise HTTPException(
            status_code=404,
            detail=f"Conversation {thread_id} not found",
        )

    success = conversation_manager.update_conversation_title(
        thread_id, body.title
    )
    if not success:
        raise HTTPException(
            status_code=500,
            detail="Failed to update conversation title",
        )

    return TitleUpdateResponse(
        thread_id=thread_id,
        title=body.title,
    )
