# API Documentation

## Overview

The Multimodal Librarian provides a comprehensive REST API and WebSocket interface for document management, semantic search, and AI-powered chat functionality. This documentation covers all available endpoints, request/response formats, and integration examples.

## Base URL

- **Production**: `https://your-domain.com`
- **Development**: `http://localhost:8000`
- **API Prefix**: `/api`

## Authentication

### JWT Token Authentication

Most endpoints support optional JWT authentication. When authenticated, users get personalized experiences and access to private documents.

```http
Authorization: Bearer <jwt_token>
```

### Authentication Endpoints

#### POST /api/auth/login
Authenticate user and receive JWT token.

**Request:**
```json
{
  "username": "user@example.com",
  "password": "secure_password"
}
```

**Response:**
```json
{
  "access_token": "eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9...",
  "token_type": "bearer",
  "expires_in": 3600,
  "user": {
    "id": "user_123",
    "username": "user@example.com",
    "role": "user"
  }
}
```

#### POST /api/auth/register
Register new user account.

**Request:**
```json
{
  "username": "user@example.com",
  "password": "secure_password",
  "email": "user@example.com",
  "full_name": "John Doe"
}
```

#### POST /api/auth/refresh
Refresh JWT token.

**Request:**
```json
{
  "refresh_token": "refresh_token_here"
}
```

## Document Management API

### POST /api/documents/upload
Upload a document for processing and indexing.

**Content-Type**: `multipart/form-data`

**Parameters:**
- `file` (required): PDF or TXT file (max 100MB)
- `title` (optional): Document title
- `description` (optional): Document description
- `user_id` (optional): User identifier (defaults to "default_user")

**Example Request:**
```bash
curl -X POST "http://localhost:8000/api/documents/upload" \
  -H "Authorization: Bearer <token>" \
  -F "file=@document.pdf" \
  -F "title=Research Paper" \
  -F "description=Important research findings"
```

**Response:**
```json
{
  "document_id": "doc_123456",
  "title": "Research Paper",
  "filename": "document.pdf",
  "file_size": 2048576,
  "content_type": "application/pdf",
  "upload_status": "success",
  "processing_status": "queued",
  "s3_key": "documents/doc_123456/document.pdf",
  "created_at": "2026-01-10T10:30:00Z",
  "estimated_processing_time": 120
}
```

**Error Responses:**
- `400 Bad Request`: Invalid file type or size
- `413 Request Entity Too Large`: File exceeds 100MB limit
- `422 Unprocessable Entity`: Validation errors

### GET /api/documents/
List documents with optional filtering and pagination.

**Query Parameters:**
- `page` (optional): Page number (default: 1)
- `limit` (optional): Items per page (default: 20, max: 100)
- `user_id` (optional): Filter by user
- `status` (optional): Filter by processing status
- `search` (optional): Search in title/description

**Example Request:**
```bash
curl "http://localhost:8000/api/documents/?page=1&limit=10&status=completed"
```

**Response:**
```json
{
  "documents": [
    {
      "document_id": "doc_123456",
      "title": "Research Paper",
      "filename": "document.pdf",
      "file_size": 2048576,
      "processing_status": "completed",
      "created_at": "2026-01-10T10:30:00Z",
      "processed_at": "2026-01-10T10:32:15Z",
      "chunk_count": 45,
      "user_id": "user_123"
    }
  ],
  "total_count": 1,
  "page": 1,
  "limit": 10,
  "total_pages": 1
}
```

### GET /api/documents/{document_id}
Get detailed information about a specific document.

**Response:**
```json
{
  "document_id": "doc_123456",
  "title": "Research Paper",
  "description": "Important research findings",
  "filename": "document.pdf",
  "file_size": 2048576,
  "content_type": "application/pdf",
  "processing_status": "completed",
  "created_at": "2026-01-10T10:30:00Z",
  "processed_at": "2026-01-10T10:32:15Z",
  "chunk_count": 45,
  "user_id": "user_123",
  "metadata": {
    "pages": 12,
    "word_count": 3500,
    "language": "en"
  },
  "processing_details": {
    "chunks_created": 45,
    "embeddings_generated": 45,
    "processing_time_seconds": 135
  }
}
```

### DELETE /api/documents/{document_id}
Delete a document and all associated data.

**Response:**
```json
{
  "message": "Document deleted successfully",
  "document_id": "doc_123456",
  "deleted_at": "2026-01-10T11:00:00Z"
}
```

### GET /api/documents/{document_id}/status
Get processing status for a document.

**Response:**
```json
{
  "document_id": "doc_123456",
  "processing_status": "processing",
  "progress_percentage": 75,
  "current_step": "generating_embeddings",
  "estimated_completion": "2026-01-10T10:33:00Z",
  "steps_completed": [
    "file_validation",
    "content_extraction",
    "chunking"
  ],
  "steps_remaining": [
    "embedding_generation",
    "indexing"
  ]
}
```

## Search API

### POST /api/search
Perform semantic search across documents.

**Request:**
```json
{
  "query": "machine learning algorithms",
  "limit": 10,
  "similarity_threshold": 0.1,
  "filters": {
    "source_type": "pdf",
    "user_id": "user_123",
    "document_ids": ["doc_123456", "doc_789012"]
  },
  "options": {
    "enable_hybrid_search": true,
    "enable_reranking": true,
    "include_metadata": true
  }
}
```

**Response:**
```json
{
  "results": [
    {
      "chunk_id": "chunk_123",
      "content": "Machine learning algorithms are computational methods...",
      "source_type": "pdf",
      "source_id": "doc_123456",
      "content_type": "text",
      "location_reference": "page_5",
      "section": "Introduction to ML",
      "similarity_score": 0.89,
      "relevance_score": 0.92,
      "is_bridge": false,
      "created_at": "2026-01-10T10:32:15Z",
      "metadata": {
        "document_title": "Research Paper",
        "page_number": 5,
        "section_title": "Introduction to ML"
      }
    }
  ],
  "total_results": 1,
  "query": {
    "query_text": "machine learning algorithms",
    "limit": 10,
    "similarity_threshold": 0.1
  },
  "execution_time_ms": 245.7,
  "search_metadata": {
    "service_type": "complex",
    "cache_hit": false,
    "optimization_applied": true
  }
}
```

### GET /api/search/suggestions
Get search suggestions based on query.

**Query Parameters:**
- `q`: Partial query text
- `limit`: Number of suggestions (default: 5)

**Response:**
```json
{
  "suggestions": [
    "machine learning algorithms",
    "machine learning models",
    "machine learning applications"
  ],
  "query": "machine learn"
}
```

## Chat API

### WebSocket /ws/chat/{connection_id}
Real-time chat interface with AI assistant.

**Connection:**
```javascript
const ws = new WebSocket('ws://localhost:8000/ws/chat/user_123');

ws.onopen = function(event) {
    console.log('Connected to chat');
};

ws.onmessage = function(event) {
    const message = JSON.parse(event.data);
    console.log('Received:', message);
};
```

**Message Format (Client to Server):**
```json
{
  "type": "user_message",
  "content": "What is machine learning?",
  "context": {
    "document_ids": ["doc_123456"],
    "conversation_id": "conv_789"
  }
}
```

**Message Format (Server to Client):**
```json
{
  "type": "assistant_response",
  "content": "Machine learning is a subset of artificial intelligence...",
  "sources": [
    {
      "chunk_id": "chunk_123",
      "document_title": "Research Paper",
      "relevance_score": 0.89
    }
  ],
  "metadata": {
    "response_time_ms": 1250,
    "model_used": "gpt-3.5-turbo",
    "context_used": true
  }
}
```

### POST /api/chat/conversations
Create a new conversation.

**Request:**
```json
{
  "title": "ML Discussion",
  "context": {
    "document_ids": ["doc_123456"],
    "user_expertise": "intermediate"
  }
}
```

**Response:**
```json
{
  "conversation_id": "conv_789",
  "title": "ML Discussion",
  "created_at": "2026-01-10T11:00:00Z",
  "message_count": 0
}
```

### GET /api/chat/conversations/{conversation_id}/history
Get conversation history.

**Response:**
```json
{
  "conversation_id": "conv_789",
  "messages": [
    {
      "message_id": "msg_001",
      "type": "user_message",
      "content": "What is machine learning?",
      "timestamp": "2026-01-10T11:01:00Z"
    },
    {
      "message_id": "msg_002",
      "type": "assistant_response",
      "content": "Machine learning is a subset of artificial intelligence...",
      "sources": ["chunk_123"],
      "timestamp": "2026-01-10T11:01:02Z"
    }
  ],
  "total_messages": 2
}
```

## Analytics API

### GET /api/analytics/documents
Get document processing analytics.

**Query Parameters:**
- `start_date`: Start date (ISO format)
- `end_date`: End date (ISO format)
- `user_id`: Filter by user

**Response:**
```json
{
  "period": {
    "start_date": "2026-01-01T00:00:00Z",
    "end_date": "2026-01-10T23:59:59Z"
  },
  "document_stats": {
    "total_uploaded": 150,
    "total_processed": 145,
    "processing_failed": 5,
    "total_size_mb": 2048.5,
    "avg_processing_time_seconds": 125.3
  },
  "processing_breakdown": {
    "pdf": 120,
    "txt": 30
  },
  "daily_uploads": [
    {
      "date": "2026-01-10",
      "count": 15,
      "size_mb": 204.8
    }
  ]
}
```

### GET /api/analytics/search
Get search analytics and performance metrics.

**Response:**
```json
{
  "search_stats": {
    "total_searches": 1250,
    "avg_response_time_ms": 245.7,
    "cache_hit_rate": 0.72,
    "fallback_usage_rate": 0.05
  },
  "popular_queries": [
    {
      "query": "machine learning",
      "count": 45,
      "avg_results": 12.3
    }
  ],
  "performance_trends": [
    {
      "date": "2026-01-10",
      "avg_response_time_ms": 230.5,
      "search_count": 125
    }
  ]
}
```

## Health and Monitoring API

### GET /health/simple
Basic health check endpoint.

**Response:**
```json
{
  "status": "healthy",
  "timestamp": "2026-01-10T11:00:00Z",
  "uptime_seconds": 86400
}
```

### GET /health/detailed
Comprehensive health check with component status.

**Response:**
```json
{
  "status": "healthy",
  "timestamp": "2026-01-10T11:00:00Z",
  "components": {
    "database": {
      "status": "healthy",
      "response_time_ms": 15.2,
      "connection_pool": {
        "active": 5,
        "idle": 10,
        "max": 20
      }
    },
    "vector_store": {
      "status": "healthy",
      "response_time_ms": 45.8,
      "index_count": 15000
    },
    "cache": {
      "status": "healthy",
      "hit_rate": 0.72,
      "memory_usage_mb": 256.5
    },
    "search_service": {
      "status": "healthy",
      "service_type": "complex",
      "fallback_active": false,
      "avg_response_time_ms": 245.7
    }
  },
  "performance": {
    "avg_response_time_ms": 180.5,
    "requests_per_minute": 45.2,
    "error_rate": 0.001
  }
}
```

### GET /api/monitoring/metrics
Get system performance metrics.

**Response:**
```json
{
  "timestamp": "2026-01-10T11:00:00Z",
  "performance": {
    "avg_response_time_ms": 180.5,
    "p95_response_time_ms": 450.2,
    "requests_per_minute": 45.2,
    "error_rate": 0.001
  },
  "resources": {
    "memory_usage_mb": 1024.5,
    "cpu_usage_percent": 35.2,
    "disk_usage_percent": 45.8
  },
  "cache": {
    "hit_rate": 0.72,
    "size_mb": 256.5,
    "evictions_per_hour": 12
  },
  "search": {
    "avg_latency_ms": 245.7,
    "cache_hit_rate": 0.68,
    "fallback_rate": 0.05
  }
}
```

## Error Handling

### Standard Error Response Format

```json
{
  "error": {
    "code": "VALIDATION_ERROR",
    "message": "Invalid request parameters",
    "details": {
      "field": "file",
      "reason": "File size exceeds maximum limit"
    },
    "timestamp": "2026-01-10T11:00:00Z",
    "request_id": "req_123456"
  }
}
```

### Common Error Codes

| Code | HTTP Status | Description |
|------|-------------|-------------|
| `VALIDATION_ERROR` | 400 | Request validation failed |
| `AUTHENTICATION_REQUIRED` | 401 | Authentication required |
| `AUTHORIZATION_FAILED` | 403 | Insufficient permissions |
| `RESOURCE_NOT_FOUND` | 404 | Requested resource not found |
| `FILE_TOO_LARGE` | 413 | File exceeds size limit |
| `RATE_LIMIT_EXCEEDED` | 429 | Too many requests |
| `INTERNAL_ERROR` | 500 | Internal server error |
| `SERVICE_UNAVAILABLE` | 503 | Service temporarily unavailable |

## Rate Limiting

API endpoints are rate-limited to ensure fair usage:

- **Authentication endpoints**: 5 requests per minute per IP
- **Upload endpoints**: 10 requests per minute per user
- **Search endpoints**: 60 requests per minute per user
- **Chat endpoints**: 30 messages per minute per user

Rate limit headers are included in responses:
```http
X-RateLimit-Limit: 60
X-RateLimit-Remaining: 45
X-RateLimit-Reset: 1641811200
```

## SDK Examples

### Python SDK Example

```python
import requests
import json

class MultimodalLibrarianClient:
    def __init__(self, base_url, token=None):
        self.base_url = base_url
        self.token = token
        self.session = requests.Session()
        if token:
            self.session.headers.update({
                'Authorization': f'Bearer {token}'
            })
    
    def upload_document(self, file_path, title=None, description=None):
        """Upload a document."""
        with open(file_path, 'rb') as f:
            files = {'file': f}
            data = {}
            if title:
                data['title'] = title
            if description:
                data['description'] = description
            
            response = self.session.post(
                f'{self.base_url}/api/documents/upload',
                files=files,
                data=data
            )
            return response.json()
    
    def search(self, query, limit=10):
        """Perform semantic search."""
        payload = {
            'query': query,
            'limit': limit
        }
        response = self.session.post(
            f'{self.base_url}/api/search',
            json=payload
        )
        return response.json()

# Usage
client = MultimodalLibrarianClient('http://localhost:8000', 'your_token')
result = client.upload_document('document.pdf', title='My Document')
search_results = client.search('machine learning', limit=5)
```

### JavaScript SDK Example

```javascript
class MultimodalLibrarianClient {
    constructor(baseUrl, token = null) {
        this.baseUrl = baseUrl;
        this.token = token;
    }
    
    async uploadDocument(file, title = null, description = null) {
        const formData = new FormData();
        formData.append('file', file);
        if (title) formData.append('title', title);
        if (description) formData.append('description', description);
        
        const response = await fetch(`${this.baseUrl}/api/documents/upload`, {
            method: 'POST',
            headers: this.token ? {
                'Authorization': `Bearer ${this.token}`
            } : {},
            body: formData
        });
        
        return await response.json();
    }
    
    async search(query, limit = 10) {
        const response = await fetch(`${this.baseUrl}/api/search`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                ...(this.token ? { 'Authorization': `Bearer ${this.token}` } : {})
            },
            body: JSON.stringify({ query, limit })
        });
        
        return await response.json();
    }
    
    connectChat(connectionId) {
        const ws = new WebSocket(`${this.baseUrl.replace('http', 'ws')}/ws/chat/${connectionId}`);
        
        ws.onopen = () => console.log('Chat connected');
        ws.onmessage = (event) => {
            const message = JSON.parse(event.data);
            console.log('Received:', message);
        };
        
        return ws;
    }
}

// Usage
const client = new MultimodalLibrarianClient('http://localhost:8000', 'your_token');
const uploadResult = await client.uploadDocument(fileInput.files[0], 'My Document');
const searchResults = await client.search('machine learning', 5);
const chatWs = client.connectChat('user_123');
```

## OpenAPI Specification

The complete OpenAPI 3.0 specification is available at:
- **JSON**: `/openapi.json`
- **Interactive Docs**: `/docs`
- **ReDoc**: `/redoc`

---

*This API documentation is automatically generated from the codebase and kept up-to-date with the latest changes. Last updated: January 2026*