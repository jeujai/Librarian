"""
Logging middleware for automatic request/response logging and distributed tracing.

This middleware automatically:
- Creates traces for all requests
- Logs request/response details
- Tracks performance metrics
- Handles error logging
- Adds correlation IDs
"""

import time
import uuid
from typing import Callable, Optional

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

from ...logging_config import get_logger
from ...monitoring.logging_service import (
    get_logging_service,
    log_error,
    log_info,
    log_performance,
)
from ...monitoring.structured_logging_service import (
    get_structured_logging_service,
    log_error_structured,
    log_info_structured,
)


class LoggingMiddleware(BaseHTTPMiddleware):
    """Middleware for comprehensive request/response logging and tracing."""
    
    def __init__(self, app, exclude_paths: Optional[list] = None):
        super().__init__(app)
        self.logger = get_logger("logging_middleware")
        self.logging_service = get_logging_service()
        self.structured_logging_service = get_structured_logging_service()
        
        # Paths to exclude from logging (e.g., health checks, static files)
        self.exclude_paths = exclude_paths or [
            "/health/simple",
            "/static/",
            "/favicon.ico"
        ]
    
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """Process request with comprehensive logging and tracing."""
        
        # Skip WebSocket connections - BaseHTTPMiddleware doesn't handle them properly
        if request.headers.get("upgrade", "").lower() == "websocket":
            return await call_next(request)
        
        # Check if path should be excluded
        if any(request.url.path.startswith(exclude_path) for exclude_path in self.exclude_paths):
            return await call_next(request)
        
        # Generate correlation ID and trace
        correlation_id = str(uuid.uuid4())
        request.state.correlation_id = correlation_id
        
        # Extract user information if available
        user_id = None
        session_id = None
        
        try:
            # Try to get user info from auth middleware
            if hasattr(request.state, 'user') and request.state.user:
                user_id = getattr(request.state.user, 'id', None) or getattr(request.state.user, 'username', None)
            
            # Try to get session ID from headers or cookies
            session_id = request.headers.get('X-Session-ID') or request.cookies.get('session_id')
            
        except Exception:
            pass  # Continue without user info if not available
        
        # Start distributed trace
        trace_id = self.logging_service.create_trace(
            service="api",
            operation=f"{request.method} {request.url.path}"
        )
        
        request.state.trace_id = trace_id
        
        # Log request start
        start_time = time.time()
        
        request_metadata = {
            "method": request.method,
            "path": request.url.path,
            "query_params": str(request.query_params),
            "user_agent": request.headers.get("user-agent"),
            "client_ip": self._get_client_ip(request),
            "content_type": request.headers.get("content-type"),
            "content_length": request.headers.get("content-length"),
            "correlation_id": correlation_id
        }
        
        # Log request start with structured logging
        log_info_structured(
            service="api",
            operation="request_start",
            message=f"Request started: {request.method} {request.url.path}",
            correlation_id=correlation_id,
            trace_id=trace_id,
            user_id=user_id,
            session_id=session_id,
            metadata=request_metadata,
            tags={'request_phase': 'start', 'method': request.method}
        )
        
        # Also log to base service for compatibility
        log_info(
            service="api",
            operation="request_start",
            message=f"Request started: {request.method} {request.url.path}",
            trace_id=trace_id,
            user_id=user_id,
            session_id=session_id,
            metadata=request_metadata
        )
        
        # Process request
        response = None
        error_occurred = False
        error_message = None
        
        try:
            response = await call_next(request)
            
        except Exception as e:
            error_occurred = True
            error_message = str(e)
            
            # Log error with structured logging
            log_error_structured(
                service="api",
                operation="request_error",
                message=f"Request failed: {request.method} {request.url.path}",
                correlation_id=correlation_id,
                trace_id=trace_id,
                user_id=user_id,
                session_id=session_id,
                error_type=type(e).__name__,
                stack_trace=str(e),
                metadata=request_metadata,
                tags={'request_phase': 'error', 'method': request.method}
            )
            
            # Also log to base service for compatibility
            log_error(
                service="api",
                operation="request_error",
                message=f"Request failed: {request.method} {request.url.path}",
                trace_id=trace_id,
                user_id=user_id,
                session_id=session_id,
                error=e,
                metadata=request_metadata
            )
            
            # Create error response
            response = JSONResponse(
                status_code=500,
                content={
                    "error": "Internal server error",
                    "correlation_id": correlation_id,
                    "trace_id": trace_id
                }
            )
        
        # Calculate duration
        end_time = time.time()
        duration_ms = (end_time - start_time) * 1000
        
        # Add correlation and trace headers to response
        if response:
            response.headers["X-Correlation-ID"] = correlation_id
            response.headers["X-Trace-ID"] = trace_id
        
        # Prepare response metadata
        response_metadata = {
            "status_code": response.status_code if response else 500,
            "response_size": len(response.body) if hasattr(response, 'body') and response.body else 0,
            "response_headers": dict(response.headers) if response else {}
        }
        
        # Log response with structured logging
        if error_occurred:
            log_error_structured(
                service="api",
                operation="request_complete",
                message=f"Request completed with error: {request.method} {request.url.path} - {response.status_code}",
                correlation_id=correlation_id,
                trace_id=trace_id,
                user_id=user_id,
                session_id=session_id,
                duration_ms=duration_ms,
                status_code=response.status_code,
                metadata={**request_metadata, **response_metadata},
                tags={'request_phase': 'complete', 'status': 'error', 'method': request.method}
            )
            
            # Also log to base service
            log_error(
                service="api",
                operation="request_complete",
                message=f"Request completed with error: {request.method} {request.url.path} - {response.status_code}",
                trace_id=trace_id,
                user_id=user_id,
                session_id=session_id,
                duration_ms=duration_ms,
                metadata={**request_metadata, **response_metadata}
            )
        else:
            log_info_structured(
                service="api",
                operation="request_complete",
                message=f"Request completed: {request.method} {request.url.path} - {response.status_code}",
                correlation_id=correlation_id,
                trace_id=trace_id,
                user_id=user_id,
                session_id=session_id,
                duration_ms=duration_ms,
                status_code=response.status_code,
                metadata={**request_metadata, **response_metadata},
                tags={'request_phase': 'complete', 'status': 'success', 'method': request.method}
            )
            
            # Also log to base service
            log_info(
                service="api",
                operation="request_complete",
                message=f"Request completed: {request.method} {request.url.path} - {response.status_code}",
                trace_id=trace_id,
                user_id=user_id,
                session_id=session_id,
                duration_ms=duration_ms,
                metadata={**request_metadata, **response_metadata}
            )
        
        # Log performance metric
        log_performance(
            service="api",
            operation=f"{request.method} {request.url.path}",
            duration_ms=duration_ms,
            success=not error_occurred and (response.status_code < 400 if response else False),
            trace_id=trace_id,
            metadata={
                "status_code": response.status_code if response else 500,
                "user_id": user_id,
                "correlation_id": correlation_id
            }
        )
        
        # Finish trace
        self.logging_service.finish_trace(
            trace_id=trace_id,
            error=error_occurred,
            error_message=error_message
        )
        
        # Log business metrics for specific endpoints
        self._log_business_metrics(request, response, user_id, trace_id)
        
        return response
    
    def _get_client_ip(self, request: Request) -> str:
        """Get client IP address from request."""
        # Check for forwarded headers (common in load balancers)
        forwarded_for = request.headers.get("X-Forwarded-For")
        if forwarded_for:
            return forwarded_for.split(",")[0].strip()
        
        real_ip = request.headers.get("X-Real-IP")
        if real_ip:
            return real_ip
        
        # Fallback to direct client IP
        return request.client.host if request.client else "unknown"
    
    def _log_business_metrics(self, request: Request, response: Response, 
                             user_id: Optional[str], trace_id: str) -> None:
        """Log business metrics for specific endpoints."""
        
        try:
            path = request.url.path
            method = request.method
            status_code = response.status_code if response else 500
            
            # API endpoint usage metrics
            self.logging_service.log_business_metric(
                metric_name="api_requests_total",
                metric_value=1,
                metric_type="counter",
                tags={
                    "method": method,
                    "endpoint": path,
                    "status_code": str(status_code),
                    "user_id": user_id or "anonymous"
                },
                trace_id=trace_id
            )
            
            # Success/error metrics
            if status_code < 400:
                self.logging_service.log_business_metric(
                    metric_name="api_requests_success",
                    metric_value=1,
                    metric_type="counter",
                    tags={"endpoint": path, "method": method},
                    trace_id=trace_id
                )
            else:
                self.logging_service.log_business_metric(
                    metric_name="api_requests_error",
                    metric_value=1,
                    metric_type="counter",
                    tags={
                        "endpoint": path,
                        "method": method,
                        "status_code": str(status_code)
                    },
                    trace_id=trace_id
                )
            
            # User activity metrics
            if user_id:
                self.logging_service.log_business_metric(
                    metric_name="user_activity",
                    metric_value=1,
                    metric_type="counter",
                    tags={
                        "user_id": user_id,
                        "endpoint": path,
                        "method": method
                    },
                    trace_id=trace_id
                )
            
            # Specific endpoint metrics
            if path.startswith("/api/chat"):
                self.logging_service.log_business_metric(
                    metric_name="chat_requests",
                    metric_value=1,
                    metric_type="counter",
                    tags={"endpoint": path, "user_id": user_id or "anonymous"},
                    trace_id=trace_id
                )
            
            elif path.startswith("/api/documents"):
                self.logging_service.log_business_metric(
                    metric_name="document_requests",
                    metric_value=1,
                    metric_type="counter",
                    tags={"endpoint": path, "method": method, "user_id": user_id or "anonymous"},
                    trace_id=trace_id
                )
            
            elif path.startswith("/api/analytics"):
                self.logging_service.log_business_metric(
                    metric_name="analytics_requests",
                    metric_value=1,
                    metric_type="counter",
                    tags={"endpoint": path, "user_id": user_id or "anonymous"},
                    trace_id=trace_id
                )
            
            elif path.startswith("/api/auth"):
                self.logging_service.log_business_metric(
                    metric_name="auth_requests",
                    metric_value=1,
                    metric_type="counter",
                    tags={"endpoint": path, "method": method},
                    trace_id=trace_id
                )
        
        except Exception as e:
            # Don't let business metrics logging break the request
            self.logger.warning(f"Failed to log business metrics: {e}")


class WebSocketLoggingMixin:
    """Mixin for adding logging to WebSocket connections."""
    
    def __init__(self):
        self.logger = get_logger("websocket_logging")
        self.logging_service = get_logging_service()
    
    def log_websocket_connection(self, connection_id: str, user_id: Optional[str] = None) -> str:
        """Log WebSocket connection start."""
        trace_id = self.logging_service.create_trace(
            service="websocket",
            operation="connection_start"
        )
        
        log_info(
            service="websocket",
            operation="connection_start",
            message=f"WebSocket connection established: {connection_id}",
            trace_id=trace_id,
            user_id=user_id,
            metadata={"connection_id": connection_id}
        )
        
        # Business metric
        self.logging_service.log_business_metric(
            metric_name="websocket_connections",
            metric_value=1,
            metric_type="counter",
            tags={"user_id": user_id or "anonymous"},
            trace_id=trace_id
        )
        
        return trace_id
    
    def log_websocket_disconnection(self, connection_id: str, trace_id: str, 
                                   user_id: Optional[str] = None, duration_ms: Optional[float] = None):
        """Log WebSocket connection end."""
        log_info(
            service="websocket",
            operation="connection_end",
            message=f"WebSocket connection closed: {connection_id}",
            trace_id=trace_id,
            user_id=user_id,
            duration_ms=duration_ms,
            metadata={"connection_id": connection_id}
        )
        
        # Business metric
        self.logging_service.log_business_metric(
            metric_name="websocket_disconnections",
            metric_value=1,
            metric_type="counter",
            tags={"user_id": user_id or "anonymous"},
            trace_id=trace_id
        )
        
        self.logging_service.finish_trace(trace_id)
    
    def log_websocket_message(self, connection_id: str, message_type: str, 
                             user_id: Optional[str] = None, trace_id: Optional[str] = None,
                             metadata: Optional[dict] = None):
        """Log WebSocket message."""
        log_info(
            service="websocket",
            operation="message_received",
            message=f"WebSocket message: {message_type} from {connection_id}",
            trace_id=trace_id,
            user_id=user_id,
            metadata={
                "connection_id": connection_id,
                "message_type": message_type,
                **(metadata or {})
            }
        )
        
        # Business metric
        self.logging_service.log_business_metric(
            metric_name="websocket_messages",
            metric_value=1,
            metric_type="counter",
            tags={
                "message_type": message_type,
                "user_id": user_id or "anonymous"
            },
            trace_id=trace_id
        )