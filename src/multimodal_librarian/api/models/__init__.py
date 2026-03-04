"""
API Models Package.

This package contains Pydantic models for API requests and responses.
It re-exports models from the legacy api/models.py file for backward compatibility.
"""

# Re-export models from the sibling models.py file for backward compatibility
# These are used by routers like conversations.py
# We use absolute import to avoid circular import issues
import multimodal_librarian.api.models_legacy as _legacy_models

from .chat_document_models import (
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
)

# Re-export the legacy models
APIResponse = _legacy_models.APIResponse
ChatMessageRequest = _legacy_models.ChatMessageRequest
ChatMessageResponse = _legacy_models.ChatMessageResponse
ConversationListResponse = _legacy_models.ConversationListResponse
DeleteConversationRequest = _legacy_models.DeleteConversationRequest
ErrorResponse = _legacy_models.ErrorResponse
ExportRequest = _legacy_models.ExportRequest
ExportResponse = _legacy_models.ExportResponse
FileProcessingStatus = _legacy_models.FileProcessingStatus
FileUploadResponse = _legacy_models.FileUploadResponse
StartConversationRequest = _legacy_models.StartConversationRequest
StartConversationResponse = _legacy_models.StartConversationResponse
SuccessResponse = _legacy_models.SuccessResponse
QueryRequest = _legacy_models.QueryRequest
QueryResponse = _legacy_models.QueryResponse
HealthCheckResponse = _legacy_models.HealthCheckResponse
ServiceHealthResponse = _legacy_models.ServiceHealthResponse
ValidationError = _legacy_models.ValidationError
ValidationResponse = _legacy_models.ValidationResponse
WebSocketMessage = _legacy_models.WebSocketMessage
ChatWebSocketMessage = _legacy_models.ChatWebSocketMessage
FileUploadWebSocketMessage = _legacy_models.FileUploadWebSocketMessage
ProcessingWebSocketMessage = _legacy_models.ProcessingWebSocketMessage
ChunkFiltersModel = _legacy_models.ChunkFiltersModel
TrainingCriteriaModel = _legacy_models.TrainingCriteriaModel
StreamChunksRequest = _legacy_models.StreamChunksRequest
TrainingBatchRequest = _legacy_models.TrainingBatchRequest
TrainingBatchResponse = _legacy_models.TrainingBatchResponse
ChunkSequenceRequest = _legacy_models.ChunkSequenceRequest
ChunkSequenceResponse = _legacy_models.ChunkSequenceResponse
InteractionFeedbackRequest = _legacy_models.InteractionFeedbackRequest
InteractionFeedbackResponse = _legacy_models.InteractionFeedbackResponse
APIConfiguration = _legacy_models.APIConfiguration

__all__ = [
    # Chat Document Models (Client → Server Messages)
    "ChatUploadMessage",
    "DocumentListRequest",
    "DocumentDeleteRequest",
    "DocumentRetryRequest",
    # Chat Document Models (Server → Client Messages)
    "DocumentInfo",
    "DocumentListMessage",
    "DocumentUploadStartedMessage",
    "DocumentUploadErrorMessage",
    "DocumentDeletedMessage",
    "DocumentRetryStartedMessage",
    # Error Codes
    "DocumentUploadErrorCodes",
    # Re-exported from models_legacy.py
    "APIResponse",
    "ChatMessageRequest",
    "ChatMessageResponse",
    "ConversationListResponse",
    "DeleteConversationRequest",
    "ErrorResponse",
    "ExportRequest",
    "ExportResponse",
    "FileProcessingStatus",
    "FileUploadResponse",
    "StartConversationRequest",
    "StartConversationResponse",
    "SuccessResponse",
    "QueryRequest",
    "QueryResponse",
    "HealthCheckResponse",
    "ServiceHealthResponse",
    "ValidationError",
    "ValidationResponse",
    "WebSocketMessage",
    "ChatWebSocketMessage",
    "FileUploadWebSocketMessage",
    "ProcessingWebSocketMessage",
    "ChunkFiltersModel",
    "TrainingCriteriaModel",
    "StreamChunksRequest",
    "TrainingBatchRequest",
    "TrainingBatchResponse",
    "ChunkSequenceRequest",
    "ChunkSequenceResponse",
    "InteractionFeedbackRequest",
    "InteractionFeedbackResponse",
    "APIConfiguration",
]
