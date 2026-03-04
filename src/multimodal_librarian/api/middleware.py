"""
Middleware for the FastAPI application.

This module contains custom middleware for authentication, logging,
error handling, and request/response processing with enhanced security features.
"""

import time
import json
import logging
from typing import Callable, Optional
from uuid import uuid4

from fastapi import Request, Response, HTTPException
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint

from ..config import get_settings
from .models import ErrorResponse
from ..security.auth import get_auth_service, get_authz_service, AuthenticationError, Permission
from ..security.audit import get_audit_logger, AuditEventType, AuditLevel
from ..security.rate_limiter import get_rate_limiter, RateLimitType
from ..security.encryption import get_encryption_service

logger = logging.getLogger(__name__)
settings = get_settings()


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """Middleware for logging HTTP requests and responses with audit trail and metrics collection."""
    
    def __init__(self, app):
        super().__init__(app)
        self.audit_logger = get_audit_logger()
        self._metrics_collector = None
    
    def _get_metrics_collector(self):
        """Get metrics collector instance (lazy loading to avoid circular imports)."""
        if self._metrics_collector is None:
            try:
                from ..main import metrics_collector
                self._metrics_collector = metrics_collector
            except ImportError:
                pass
        return self._metrics_collector
    
    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        """Process request and log details with audit trail and metrics collection."""
        # Generate request ID
        request_id = str(uuid4())
        request.state.request_id = request_id
        
        # Log request
        start_time = time.time()
        client_ip = request.client.host if request.client else "unknown"
        user_agent = request.headers.get("user-agent", "unknown")
        
        logger.info(
            f"Request started - ID: {request_id}, Method: {request.method}, "
            f"URL: {request.url}, Client: {client_ip}"
        )
        
        # Get user info if available
        user_id = getattr(request.state, 'user_id', None)
        
        try:
            # Process request
            response = await call_next(request)
            
            # Calculate response time
            process_time = time.time() - start_time
            
            # Log response
            logger.info(
                f"Request completed - ID: {request_id}, Status: {response.status_code}, "
                f"Time: {process_time:.3f}s"
            )
            
            # Record metrics
            metrics_collector = self._get_metrics_collector()
            if metrics_collector:
                metrics_collector.record_request(
                    endpoint=request.url.path,
                    method=request.method,
                    response_time=process_time,
                    status_code=response.status_code,
                    user_id=user_id
                )
                
                # Record conversation events if applicable
                if "/api/chat" in request.url.path or "/ws" in request.url.path:
                    if request.method == "POST":
                        # Estimate message length from request body size
                        content_length = int(request.headers.get("content-length", 0))
                        metrics_collector.record_conversation_event(
                            "message_sent",
                            message_length=content_length,
                            has_multimedia=self._has_multimedia_content(request)
                        )
                
                # Record ML API events if applicable
                if "/api/ml" in request.url.path:
                    self._record_ml_metrics(request, response, metrics_collector)
            
            # Audit log for sensitive endpoints
            if self._is_sensitive_endpoint(request.url.path):
                self.audit_logger.log_event(
                    event_type=AuditEventType.DATA_READ if request.method == "GET" else AuditEventType.DATA_WRITE,
                    action=f"{request.method} {request.url.path}",
                    result="success" if response.status_code < 400 else "failure",
                    user_id=user_id,
                    ip_address=client_ip,
                    user_agent=user_agent,
                    details={
                        "status_code": response.status_code,
                        "process_time": process_time,
                        "request_id": request_id
                    }
                )
            
            # Add request ID to response headers
            response.headers["X-Request-ID"] = request_id
            response.headers["X-Process-Time"] = f"{process_time:.3f}"
            
            return response
            
        except Exception as e:
            # Calculate response time for error case
            process_time = time.time() - start_time
            
            # Log error
            logger.error(
                f"Request failed - ID: {request_id}, Error: {str(e)}, "
                f"Time: {process_time:.3f}s"
            )
            
            # Record error metrics
            metrics_collector = self._get_metrics_collector()
            if metrics_collector:
                metrics_collector.record_request(
                    endpoint=request.url.path,
                    method=request.method,
                    response_time=process_time,
                    status_code=500,
                    user_id=user_id
                )
            
            # Audit log for errors
            self.audit_logger.log_event(
                event_type=AuditEventType.SECURITY_VIOLATION,
                action=f"{request.method} {request.url.path}",
                result="error",
                level=AuditLevel.ERROR,
                user_id=user_id,
                ip_address=client_ip,
                user_agent=user_agent,
                details={
                    "error": str(e),
                    "process_time": process_time,
                    "request_id": request_id
                }
            )
            raise
    
    def _has_multimedia_content(self, request: Request) -> bool:
        """Check if request contains multimedia content."""
        content_type = request.headers.get("content-type", "")
        return any(media_type in content_type for media_type in [
            "multipart/form-data", "image/", "video/", "audio/"
        ])
    
    def _record_ml_metrics(self, request: Request, response: Response, metrics_collector) -> None:
        """Record ML API specific metrics."""
        path = request.url.path
        
        if "/stream" in path:
            if request.method == "POST":
                metrics_collector.record_ml_request("stream_start")
            elif request.method == "GET":
                # Estimate chunks from response size
                content_length = int(response.headers.get("content-length", 0))
                estimated_chunks = max(1, content_length // 1000)  # Rough estimate
                metrics_collector.record_ml_request("chunk_stream", chunks_count=estimated_chunks)
        
        elif "/batch" in path:
            if response.status_code == 200:
                # Try to extract batch size from response headers or estimate
                batch_size = int(response.headers.get("X-Batch-Size", 100))
                metrics_collector.record_ml_request("training_batch", batch_size=batch_size)
        
        elif "/feedback" in path:
            if request.method == "POST":
                metrics_collector.record_ml_request("feedback")
    
    def _is_sensitive_endpoint(self, path: str) -> bool:
        """Check if endpoint handles sensitive data."""
        sensitive_patterns = [
            "/api/books", "/api/conversations", "/api/query", 
            "/api/export", "/api/ml", "/api/upload"
        ]
        return any(pattern in path for pattern in sensitive_patterns)


class ErrorHandlingMiddleware(BaseHTTPMiddleware):
    """Middleware for handling and formatting errors."""
    
    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        """Process request and handle errors."""
        try:
            return await call_next(request)
            
        except HTTPException as e:
            # Handle FastAPI HTTP exceptions
            error_response = ErrorResponse(
                message=e.detail,
                error_code=f"HTTP_{e.status_code}",
                details={"status_code": e.status_code}
            )
            
            return JSONResponse(
                status_code=e.status_code,
                content=error_response.dict()
            )
            
        except ValueError as e:
            # Handle validation errors
            error_response = ErrorResponse(
                message=f"Validation error: {str(e)}",
                error_code="VALIDATION_ERROR",
                details={"error_type": "ValueError"}
            )
            
            return JSONResponse(
                status_code=400,
                content=error_response.dict()
            )
            
        except Exception as e:
            # Handle unexpected errors
            request_id = getattr(request.state, 'request_id', 'unknown')
            logger.error(f"Unexpected error in request {request_id}: {str(e)}", exc_info=True)
            
            error_response = ErrorResponse(
                message="An internal server error occurred",
                error_code="INTERNAL_SERVER_ERROR",
                details={
                    "request_id": request_id,
                    "error_type": type(e).__name__
                }
            )
            
            return JSONResponse(
                status_code=500,
                content=error_response.dict()
            )


class RateLimitingMiddleware(BaseHTTPMiddleware):
    """Enhanced rate limiting middleware with audit logging."""
    
    def __init__(self, app, calls_per_minute: int = 60):
        super().__init__(app)
        self.rate_limiter = get_rate_limiter()
        self.audit_logger = get_audit_logger()
        
    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        """Process request with enhanced rate limiting."""
        # Skip rate limiting for health checks and static files
        if request.url.path in ["/health", "/"] or request.url.path.startswith("/static"):
            return await call_next(request)
        
        client_ip = request.client.host if request.client else "unknown"
        user_id = getattr(request.state, 'user_id', None)
        
        # Determine endpoint category for rate limiting
        endpoint = self._categorize_endpoint(request.url.path)
        
        # Check rate limit
        allowed, limit_info = self.rate_limiter.check_rate_limit(
            identifier=user_id or client_ip,
            endpoint=endpoint,
            limit_type=RateLimitType.PER_USER if user_id else RateLimitType.PER_IP
        )
        
        if not allowed:
            # Log rate limit violation
            self.audit_logger.log_security_event(
                event_type=AuditEventType.RATE_LIMIT_EXCEEDED,
                action=f"rate_limit_exceeded_{endpoint}",
                user_id=user_id,
                ip_address=client_ip,
                details=limit_info
            )
            
            error_response = ErrorResponse(
                message="Rate limit exceeded. Please try again later.",
                error_code="RATE_LIMIT_EXCEEDED",
                details=limit_info
            )
            
            return JSONResponse(
                status_code=429,
                content=error_response.dict(),
                headers={"Retry-After": str(limit_info.get("retry_after", 60))}
            )
        
        return await call_next(request)
    
    def _categorize_endpoint(self, path: str) -> str:
        """Categorize endpoint for rate limiting."""
        if "/api/upload" in path:
            return "api_upload"
        elif "/api/query" in path:
            return "api_query"
        elif "/api/export" in path:
            return "api_export"
        elif "/api/ml" in path:
            if "stream" in path:
                return "ml_streaming"
            elif "batch" in path:
                return "ml_batch"
            else:
                return "ml_training"
        elif "/auth" in path:
            if "login" in path:
                return "auth_login"
            else:
                return "auth_token"
        elif "/ws" in path:
            return "websocket_connect"
        else:
            return "api_general"


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Middleware for adding security headers."""
    
    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        """Add security headers to response."""
        response = await call_next(request)
        
        # Add security headers
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        
        # Add CSP for non-API endpoints
        if not request.url.path.startswith("/api/"):
            response.headers["Content-Security-Policy"] = (
                "default-src 'self'; "
                "script-src 'self' 'unsafe-inline'; "
                "style-src 'self' 'unsafe-inline'; "
                "img-src 'self' data: blob:; "
                "connect-src 'self' ws: wss:; "
                "font-src 'self'"
            )
        
        return response


class AuthenticationMiddleware(BaseHTTPMiddleware):
    """Enhanced authentication middleware with JWT and API key support."""
    
    def __init__(self, app, require_auth: bool = False):
        super().__init__(app)
        self.require_auth = require_auth
        self.auth_service = get_auth_service()
        self.audit_logger = get_audit_logger()
        self.public_paths = {
            "/", "/health", "/docs", "/redoc", "/openapi.json"
        }
    
    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        """Process request with enhanced authentication."""
        # Skip auth for public paths and static files
        if (request.url.path in self.public_paths or 
            request.url.path.startswith("/static") or
            not self.require_auth):
            return await call_next(request)
        
        client_ip = request.client.host if request.client else "unknown"
        user_agent = request.headers.get("user-agent", "unknown")
        
        # Check for authentication credentials
        auth_header = request.headers.get("Authorization")
        api_key = request.headers.get("X-API-Key")
        
        if not auth_header and not api_key:
            self.audit_logger.log_authentication(
                event_type=AuditEventType.LOGIN_FAILURE,
                username="unknown",
                result="no_credentials",
                ip_address=client_ip,
                user_agent=user_agent
            )
            
            error_response = ErrorResponse(
                message="Authentication required",
                error_code="AUTHENTICATION_REQUIRED",
                details={"auth_methods": ["Bearer token", "API key"]}
            )
            
            return JSONResponse(
                status_code=401,
                content=error_response.dict(),
                headers={"WWW-Authenticate": "Bearer"}
            )
        
        # Validate authentication
        user_data = None
        auth_method = None
        
        try:
            if auth_header and auth_header.startswith("Bearer "):
                # Validate JWT token
                token = auth_header[7:]  # Remove "Bearer " prefix
                token_data = self.auth_service.verify_token(token)
                user_data = {
                    "user_id": token_data.user_id,
                    "username": token_data.username,
                    "role": token_data.role,
                    "permissions": token_data.permissions
                }
                auth_method = "jwt_token"
                
            elif api_key:
                # Validate API key (simplified for demo)
                if api_key == settings.api_key:
                    user_data = {
                        "user_id": "api_user",
                        "username": "api_user",
                        "role": "user",
                        "permissions": [Permission.READ_BOOKS, Permission.ACCESS_ML_API]
                    }
                    auth_method = "api_key"
                else:
                    raise AuthenticationError("Invalid API key")
            
            if not user_data:
                raise AuthenticationError("Authentication failed")
            
            # Log successful authentication
            self.audit_logger.log_authentication(
                event_type=AuditEventType.LOGIN_SUCCESS,
                username=user_data["username"],
                result="success",
                ip_address=client_ip,
                user_agent=user_agent,
                details={"auth_method": auth_method}
            )
            
            # Add user info to request state
            request.state.user_id = user_data["user_id"]
            request.state.username = user_data["username"]
            request.state.user_role = user_data["role"]
            request.state.user_permissions = user_data["permissions"]
            request.state.authenticated = True
            
            return await call_next(request)
            
        except AuthenticationError as e:
            # Log authentication failure
            self.audit_logger.log_authentication(
                event_type=AuditEventType.LOGIN_FAILURE,
                username="unknown",
                result="invalid_credentials",
                ip_address=client_ip,
                user_agent=user_agent,
                details={"error": str(e), "auth_method": auth_method}
            )
            
            error_response = ErrorResponse(
                message="Invalid authentication credentials",
                error_code="INVALID_CREDENTIALS"
            )
            
            return JSONResponse(
                status_code=401,
                content=error_response.dict()
            )


class CORSMiddleware(BaseHTTPMiddleware):
    """Custom CORS middleware with more control."""
    
    def __init__(self, app, allowed_origins: list = None, allow_credentials: bool = True):
        super().__init__(app)
        self.allowed_origins = allowed_origins or ["*"]
        self.allow_credentials = allow_credentials
    
    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        """Handle CORS for requests."""
        origin = request.headers.get("origin")
        
        # Handle preflight requests
        if request.method == "OPTIONS":
            response = Response()
            self._add_cors_headers(response, origin)
            return response
        
        # Process normal request
        response = await call_next(request)
        self._add_cors_headers(response, origin)
        
        return response
    
    def _add_cors_headers(self, response: Response, origin: Optional[str]):
        """Add CORS headers to response."""
        if origin and (self.allowed_origins == ["*"] or origin in self.allowed_origins):
            response.headers["Access-Control-Allow-Origin"] = origin
        elif self.allowed_origins == ["*"]:
            response.headers["Access-Control-Allow-Origin"] = "*"
        
        if self.allow_credentials:
            response.headers["Access-Control-Allow-Credentials"] = "true"
        
        response.headers["Access-Control-Allow-Methods"] = "GET, POST, PUT, DELETE, OPTIONS"
        response.headers["Access-Control-Allow-Headers"] = (
            "Content-Type, Authorization, X-API-Key, X-Request-ID"
        )
        response.headers["Access-Control-Expose-Headers"] = "X-Request-ID, X-Process-Time"


def get_user_id(request: Request) -> Optional[str]:
    """Get user ID from request state."""
    return getattr(request.state, 'user_id', None)


def get_request_id(request: Request) -> Optional[str]:
    """Get request ID from request state."""
    return getattr(request.state, 'request_id', None)


def is_authenticated(request: Request) -> bool:
    """Check if request is authenticated."""
    return getattr(request.state, 'authenticated', False)