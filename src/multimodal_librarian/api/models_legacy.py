"""
Pydantic models for API request/response validation.

This module contains all the Pydantic models used for API endpoint
request validation and response serialization.
"""

from datetime import datetime
from typing import List, Dict, Optional, Any, Union
from pydantic import BaseModel, Field, validator
from enum import Enum

from ..models.core import SourceType, ContentType, MessageType, SequenceType, InteractionType


class APIResponse(BaseModel):
    """Base API response model."""
    success: bool = True
    message: str = ""
    timestamp: datetime = Field(default_factory=datetime.now)


class SuccessResponse(APIResponse):
    """Success response model."""
    success: bool = True
    details: Optional[Dict[str, Any]] = None


class ErrorResponse(APIResponse):
    """Error response model."""
    success: bool = False
    error_code: Optional[str] = None
    details: Optional[Dict[str, Any]] = None


# Chat and Conversation Models

class ChatMessageRequest(BaseModel):
    """Request model for chat messages."""
    message: str = Field(..., min_length=1, max_length=10000)
    thread_id: Optional[str] = None
    include_multimedia: bool = True


class ChatMessageResponse(APIResponse):
    """Response model for chat messages."""
    response: Dict[str, Any]
    thread_id: str
    message_id: str


class StartConversationRequest(BaseModel):
    """Request model for starting a conversation."""
    user_id: Optional[str] = None
    initial_message: Optional[str] = None


class StartConversationResponse(APIResponse):
    """Response model for starting a conversation."""
    thread_id: str
    created_at: datetime


class ConversationListResponse(APIResponse):
    """Response model for listing conversations."""
    conversations: List[Dict[str, Any]]
    total_count: int


class DeleteConversationRequest(BaseModel):
    """Request model for deleting a conversation."""
    thread_id: str


# File Upload Models

class FileUploadResponse(APIResponse):
    """Response model for file uploads."""
    file_id: str
    filename: str
    size: int
    content_type: str
    processing_status: str = "uploaded"


class FileProcessingStatus(BaseModel):
    """Model for file processing status."""
    file_id: str
    status: str  # uploaded, processing, completed, failed
    progress: float = 0.0
    message: str = ""
    chunks_created: int = 0


# Query Processing Models

class QueryRequest(BaseModel):
    """Request model for knowledge queries."""
    query: str = Field(..., min_length=1, max_length=5000)
    thread_id: Optional[str] = None
    include_multimedia: bool = True
    max_results: int = Field(default=10, ge=1, le=100)
    source_types: Optional[List[str]] = None
    content_types: Optional[List[str]] = None


class QueryResponse(APIResponse):
    """Response model for knowledge queries."""
    results: Dict[str, Any]
    total_results: int
    processing_time: float


# Export Models

class ExportRequest(BaseModel):
    """Request model for content export."""
    content_type: str  # conversation, query_result, knowledge_base
    content_id: str
    export_format: str = Field(..., pattern="^(txt|docx|pdf|rtf|pptx|xlsx)$")
    include_multimedia: bool = True


class ExportResponse(APIResponse):
    """Response model for content export."""
    export_id: str
    download_url: str
    file_size: int
    expires_at: datetime


# ML Training API Models

class ChunkFiltersModel(BaseModel):
    """Model for chunk filtering criteria."""
    content_types: Optional[List[str]] = None
    source_types: Optional[List[str]] = None
    complexity_range: Optional[Dict[str, float]] = None
    temporal_range: Optional[Dict[str, datetime]] = None
    reward_threshold: Optional[float] = Field(None, ge=-1.0, le=1.0)
    interaction_threshold: Optional[int] = Field(None, ge=0)


class TrainingCriteriaModel(BaseModel):
    """Model for training batch criteria."""
    batch_size: int = Field(default=100, ge=1, le=10000)
    include_sequences: bool = True
    sequence_length: int = Field(default=5, ge=1, le=50)
    balance_content_types: bool = True
    balance_source_types: bool = True
    reward_weighting: bool = True
    temporal_weighting: bool = True


class StreamChunksRequest(BaseModel):
    """Request model for streaming knowledge chunks."""
    filters: Optional[ChunkFiltersModel] = None
    stream_format: str = Field(default="json", pattern="^(json|jsonl)$")
    batch_size: int = Field(default=100, ge=1, le=1000)


class TrainingBatchRequest(BaseModel):
    """Request model for training batch generation."""
    criteria: TrainingCriteriaModel
    filters: Optional[ChunkFiltersModel] = None


class TrainingBatchResponse(APIResponse):
    """Response model for training batch."""
    batch_id: str
    total_chunks: int
    total_sequences: int
    batch_metadata: Dict[str, Any]


class ChunkSequenceRequest(BaseModel):
    """Request model for chunk sequences."""
    pattern: str = Field(..., min_length=1)
    sequence_length: int = Field(default=5, ge=1, le=50)
    sequence_type: str = Field(default="semantic", pattern="^(temporal|semantic|causal)$")
    max_sequences: int = Field(default=10, ge=1, le=100)


class ChunkSequenceResponse(APIResponse):
    """Response model for chunk sequences."""
    sequences: List[Dict[str, Any]]
    total_sequences: int


class InteractionFeedbackRequest(BaseModel):
    """Request model for interaction feedback."""
    chunk_id: str
    interaction_type: str = Field(..., pattern="^(view|cite|export|rate)$")
    feedback_score: float = Field(..., ge=-1.0, le=1.0)
    context_query: Optional[str] = None


class InteractionFeedbackResponse(APIResponse):
    """Response model for interaction feedback."""
    feedback_id: str
    updated_reward_signal: float


# WebSocket Models

class WebSocketMessage(BaseModel):
    """Base WebSocket message model."""
    type: str
    timestamp: datetime = Field(default_factory=datetime.now)


class ChatWebSocketMessage(WebSocketMessage):
    """WebSocket message for chat communication."""
    message: Optional[str] = None
    thread_id: Optional[str] = None
    data: Optional[Dict[str, Any]] = None


class FileUploadWebSocketMessage(WebSocketMessage):
    """WebSocket message for file upload progress."""
    file_id: str
    status: str
    progress: float = 0.0
    message: str = ""


class ProcessingWebSocketMessage(WebSocketMessage):
    """WebSocket message for processing status."""
    operation: str
    status: str
    progress: float = 0.0
    message: str = ""


# Health Check Models

class HealthCheckResponse(BaseModel):
    """Health check response model."""
    status: str = "healthy"
    service: str
    timestamp: datetime = Field(default_factory=datetime.now)
    version: str = "0.1.0"
    components: Dict[str, str] = Field(default_factory=dict)


class ServiceHealthResponse(BaseModel):
    """Detailed service health response."""
    overall_status: str
    services: Dict[str, HealthCheckResponse]
    active_connections: int = 0
    active_threads: int = 0
    uptime_seconds: float = 0.0


# Validation Models

class ValidationError(BaseModel):
    """Validation error details."""
    field: str
    message: str
    invalid_value: Any


class ValidationResponse(APIResponse):
    """Response for validation errors."""
    success: bool = False
    errors: List[ValidationError]


# Configuration Models

class APIConfiguration(BaseModel):
    """API configuration model."""
    max_file_size: int = 100 * 1024 * 1024  # 100MB
    max_query_length: int = 5000
    max_results_per_query: int = 100
    websocket_timeout: int = 300  # 5 minutes
    export_expiry_hours: int = 24
    rate_limit_per_minute: int = 60


# Utility functions for model conversion

def convert_core_model_to_dict(core_model) -> Dict[str, Any]:
    """Convert core data model to dictionary for API response."""
    if hasattr(core_model, 'to_dict'):
        return core_model.to_dict()
    elif hasattr(core_model, '__dict__'):
        return core_model.__dict__
    else:
        return {}


def validate_enum_value(value: str, enum_class) -> bool:
    """Validate if a string value is valid for an enum."""
    try:
        enum_class(value)
        return True
    except ValueError:
        return False


# Custom validators

@validator('source_types', pre=True, each_item=True)
def validate_source_type(cls, v):
    """Validate source type values."""
    if not validate_enum_value(v, SourceType):
        raise ValueError(f"Invalid source type: {v}")
    return v


@validator('content_types', pre=True, each_item=True)
def validate_content_type(cls, v):
    """Validate content type values."""
    if not validate_enum_value(v, ContentType):
        raise ValueError(f"Invalid content type: {v}")
    return v