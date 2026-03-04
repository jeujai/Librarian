"""
API middleware package for the Multimodal Librarian system.

This package contains middleware components for:
- Authentication and authorization
- Request/response logging
- Performance monitoring
- Error handling
- Security controls
"""

from .auth_middleware import OptionalAuthenticationMiddleware
from .logging_middleware import LoggingMiddleware, WebSocketLoggingMixin

# Import utility functions from the main middleware file
try:
    from ..middleware import get_user_id, get_request_id
except ImportError:
    # Fallback implementations if not available
    def get_user_id(request):
        """Get user ID from request state."""
        return getattr(request.state, 'user_id', None)
    
    def get_request_id(request):
        """Get request ID from request state."""
        return getattr(request.state, 'request_id', None)

__all__ = [
    "OptionalAuthenticationMiddleware",
    "LoggingMiddleware",
    "WebSocketLoggingMixin",
    "get_user_id",
    "get_request_id"
]