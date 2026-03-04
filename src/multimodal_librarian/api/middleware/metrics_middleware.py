"""
Middleware for automatic comprehensive metrics collection.

This middleware automatically collects response time, user session, and request
metrics for all API endpoints without requiring manual instrumentation.
"""

import time
import uuid
from typing import Callable, Optional

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp

from ...logging_config import get_logger
from ...monitoring.comprehensive_metrics_collector import ComprehensiveMetricsCollector

logger = get_logger("metrics_middleware")


class ComprehensiveMetricsMiddleware(BaseHTTPMiddleware):
    """
    Middleware for automatic comprehensive metrics collection.
    
    Automatically collects:
    - Response times for all endpoints
    - User session activity
    - Request/response sizes
    - Concurrent request tracking
    - User agent and IP information
    """
    
    def __init__(self, app: ASGIApp, metrics_collector: ComprehensiveMetricsCollector):
        super().__init__(app)
        self.metrics_collector = metrics_collector
        self.logger = logger
    
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """Process request and collect metrics."""
        # Skip WebSocket connections - BaseHTTPMiddleware doesn't handle them properly
        if request.headers.get("upgrade", "").lower() == "websocket":
            return await call_next(request)
        
        start_time = time.time()
        
        # Extract request information
        endpoint = request.url.path
        method = request.method
        user_agent = request.headers.get("user-agent")
        client_ip = self._get_client_ip(request)
        
        # Get or create session ID
        session_id = self._get_or_create_session_id(request)
        
        # Extract user ID if available (from auth headers, JWT, etc.)
        user_id = self._extract_user_id(request)
        
        # Calculate request size
        request_size = self._calculate_request_size(request)
        
        # Record request start for concurrent tracking
        self.metrics_collector.record_request_start()
        
        try:
            # Process the request
            response = await call_next(request)
            
            # Calculate response time
            response_time_ms = (time.time() - start_time) * 1000
            
            # Calculate response size
            response_size = self._calculate_response_size(response)
            
            # Record response time metric
            self.metrics_collector.record_response_time(
                endpoint=endpoint,
                method=method,
                response_time_ms=response_time_ms,
                status_code=response.status_code,
                user_id=user_id,
                user_agent=user_agent,
                request_size_bytes=request_size,
                response_size_bytes=response_size
            )
            
            # Record user session activity
            self.metrics_collector.record_user_session_activity(
                session_id=session_id,
                user_id=user_id,
                endpoint=endpoint,
                response_time_ms=response_time_ms,
                user_agent=user_agent,
                ip_address=client_ip
            )
            
            # Add session ID to response headers for client tracking
            response.headers["X-Session-ID"] = session_id
            
            return response
            
        except Exception as e:
            # Record error response time
            response_time_ms = (time.time() - start_time) * 1000
            
            # Record error metric (status code 500 for unhandled exceptions)
            self.metrics_collector.record_response_time(
                endpoint=endpoint,
                method=method,
                response_time_ms=response_time_ms,
                status_code=500,
                user_id=user_id,
                user_agent=user_agent,
                request_size_bytes=request_size,
                response_size_bytes=0
            )
            
            # Record session activity even for errors
            self.metrics_collector.record_user_session_activity(
                session_id=session_id,
                user_id=user_id,
                endpoint=endpoint,
                response_time_ms=response_time_ms,
                user_agent=user_agent,
                ip_address=client_ip
            )
            
            self.logger.error(f"Error processing request {method} {endpoint}: {e}")
            raise
            
        finally:
            # Always record request end for concurrent tracking
            self.metrics_collector.record_request_end()
    
    def _get_client_ip(self, request: Request) -> Optional[str]:
        """Extract client IP address from request."""
        # Check for forwarded headers first (for load balancers/proxies)
        forwarded_for = request.headers.get("x-forwarded-for")
        if forwarded_for:
            # Take the first IP in the chain
            return forwarded_for.split(",")[0].strip()
        
        # Check for real IP header
        real_ip = request.headers.get("x-real-ip")
        if real_ip:
            return real_ip
        
        # Fall back to direct client IP
        if hasattr(request, "client") and request.client:
            return request.client.host
        
        return None
    
    def _get_or_create_session_id(self, request: Request) -> str:
        """Get existing session ID or create a new one."""
        # Check for session ID in headers
        session_id = request.headers.get("x-session-id")
        if session_id:
            return session_id
        
        # Check for session ID in cookies
        session_id = request.cookies.get("session_id")
        if session_id:
            return session_id
        
        # Generate new session ID
        return str(uuid.uuid4())
    
    def _extract_user_id(self, request: Request) -> Optional[str]:
        """Extract user ID from request (auth headers, JWT, etc.)."""
        # Check for user ID in headers
        user_id = request.headers.get("x-user-id")
        if user_id:
            return user_id
        
        # Check for Authorization header and extract user ID from JWT
        auth_header = request.headers.get("authorization")
        if auth_header and auth_header.startswith("Bearer "):
            try:
                # This is a simplified example - in practice, you'd decode the JWT
                # and extract the user ID from the claims
                token = auth_header.split(" ")[1]
                # For now, just return a placeholder - implement JWT decoding as needed
                return f"jwt_user_{hash(token) % 10000}"
            except Exception:
                pass
        
        # Check for user ID in cookies
        user_id = request.cookies.get("user_id")
        if user_id:
            return user_id
        
        return None
    
    def _calculate_request_size(self, request: Request) -> Optional[int]:
        """Calculate request size in bytes."""
        try:
            # Get content length from headers
            content_length = request.headers.get("content-length")
            if content_length:
                return int(content_length)
            
            # For requests without content-length, estimate from URL and headers
            url_size = len(str(request.url))
            headers_size = sum(len(k) + len(v) for k, v in request.headers.items())
            
            return url_size + headers_size
            
        except Exception as e:
            self.logger.warning(f"Could not calculate request size: {e}")
            return None
    
    def _calculate_response_size(self, response: Response) -> Optional[int]:
        """Calculate response size in bytes."""
        try:
            # Check for content-length header
            content_length = response.headers.get("content-length")
            if content_length:
                return int(content_length)
            
            # For streaming responses or responses without content-length,
            # we can't easily calculate size without consuming the response
            # Return None for now - could be enhanced with response wrapping
            return None
            
        except Exception as e:
            self.logger.warning(f"Could not calculate response size: {e}")
            return None


class SearchMetricsMiddleware(BaseHTTPMiddleware):
    """
    Specialized middleware for search endpoint metrics collection.
    
    Automatically detects search requests and collects detailed search performance metrics.
    """
    
    def __init__(self, app: ASGIApp, metrics_collector: ComprehensiveMetricsCollector):
        super().__init__(app)
        self.metrics_collector = metrics_collector
        self.logger = logger
        
        # Search endpoint patterns
        self.search_endpoints = [
            "/api/search",
            "/api/documents/search",
            "/api/vector/search",
            "/api/hybrid/search"
        ]
    
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """Process request and collect search-specific metrics."""
        # Skip WebSocket connections - BaseHTTPMiddleware doesn't handle them properly
        if request.headers.get("upgrade", "").lower() == "websocket":
            return await call_next(request)
        
        endpoint = request.url.path
        
        # Check if this is a search endpoint
        is_search_request = any(
            search_endpoint in endpoint
            for search_endpoint in self.search_endpoints
        )
        
        if not is_search_request:
            # Not a search request, pass through
            return await call_next(request)
        
        start_time = time.time()
        user_id = self._extract_user_id(request)
        
        try:
            # Extract search parameters
            search_params = await self._extract_search_params(request)
            
            # Process the request
            response = await call_next(request)
            
            # Calculate response time
            response_time_ms = (time.time() - start_time) * 1000
            
            # Extract search results information
            results_info = await self._extract_results_info(response)
            
            # Record search performance metric
            self.metrics_collector.record_search_performance(
                query_text=search_params.get("query", ""),
                search_type=search_params.get("search_type", "unknown"),
                response_time_ms=response_time_ms,
                results_count=results_info.get("count", 0),
                cache_hit=results_info.get("cache_hit", False),
                user_id=user_id,
                query_complexity_score=search_params.get("complexity_score")
            )
            
            return response
            
        except Exception as e:
            # Record failed search
            response_time_ms = (time.time() - start_time) * 1000
            
            self.metrics_collector.record_search_performance(
                query_text=search_params.get("query", "") if 'search_params' in locals() else "",
                search_type="error",
                response_time_ms=response_time_ms,
                results_count=0,
                cache_hit=False,
                user_id=user_id
            )
            
            raise
    
    def _extract_user_id(self, request: Request) -> Optional[str]:
        """Extract user ID from request."""
        # Reuse the same logic as the main middleware
        user_id = request.headers.get("x-user-id")
        if user_id:
            return user_id
        
        auth_header = request.headers.get("authorization")
        if auth_header and auth_header.startswith("Bearer "):
            try:
                token = auth_header.split(" ")[1]
                return f"jwt_user_{hash(token) % 10000}"
            except Exception:
                pass
        
        return request.cookies.get("user_id")
    
    async def _extract_search_params(self, request: Request) -> dict:
        """Extract search parameters from request."""
        params = {}
        
        try:
            # Get query parameters
            query_params = dict(request.query_params)
            params.update(query_params)
            
            # For POST requests, also check request body
            if request.method == "POST":
                try:
                    # This is a simplified approach - in practice, you'd need to
                    # handle different content types (JSON, form data, etc.)
                    # and be careful not to consume the request body
                    pass
                except Exception:
                    pass
            
            # Determine search type from endpoint
            endpoint = request.url.path
            if "vector" in endpoint:
                params["search_type"] = "vector"
            elif "hybrid" in endpoint:
                params["search_type"] = "hybrid"
            elif "simple" in endpoint:
                params["search_type"] = "simple"
            else:
                params["search_type"] = "unknown"
            
            # Calculate query complexity score (simple heuristic)
            query = params.get("query", "")
            if query:
                # Simple complexity score based on query length and special characters
                complexity = len(query) / 100.0  # Normalize by length
                complexity += query.count('"') * 0.1  # Phrase queries
                complexity += query.count('AND') * 0.2  # Boolean operators
                complexity += query.count('OR') * 0.2
                params["complexity_score"] = min(complexity, 1.0)
            
        except Exception as e:
            self.logger.warning(f"Could not extract search parameters: {e}")
        
        return params
    
    async def _extract_results_info(self, response: Response) -> dict:
        """Extract search results information from response."""
        info = {"count": 0, "cache_hit": False}
        
        try:
            # Check for cache hit header
            cache_header = response.headers.get("x-cache-status")
            if cache_header and "hit" in cache_header.lower():
                info["cache_hit"] = True
            
            # Check for results count header
            count_header = response.headers.get("x-results-count")
            if count_header:
                info["count"] = int(count_header)
            
            # For JSON responses, we could parse the body to get more detailed info
            # but that would require consuming the response stream
            
        except Exception as e:
            self.logger.warning(f"Could not extract results info: {e}")
        
        return info


def create_metrics_middleware(metrics_collector: ComprehensiveMetricsCollector) -> ComprehensiveMetricsMiddleware:
    """Create and configure the comprehensive metrics middleware."""
    return ComprehensiveMetricsMiddleware(None, metrics_collector)


def create_search_metrics_middleware(metrics_collector: ComprehensiveMetricsCollector) -> SearchMetricsMiddleware:
    """Create and configure the search metrics middleware."""
    return SearchMetricsMiddleware(None, metrics_collector)