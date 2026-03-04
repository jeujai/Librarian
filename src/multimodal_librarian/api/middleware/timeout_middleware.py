"""
Request Timeout Middleware

Prevents requests from blocking the event loop indefinitely by enforcing
a maximum request duration. This is critical for maintaining server
responsiveness when individual requests hang.
"""

import asyncio
from typing import Callable

from fastapi import Request, Response
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from ...logging_config import get_logger

logger = get_logger("timeout_middleware")


class TimeoutMiddleware(BaseHTTPMiddleware):
    """
    Middleware that enforces a timeout on all requests.
    
    If a request takes longer than the specified timeout, it returns
    a 504 Gateway Timeout response instead of blocking forever.
    """
    
    def __init__(
        self,
        app,
        timeout_seconds: float = 30.0,
        exclude_paths: list = None
    ):
        super().__init__(app)
        self.timeout_seconds = timeout_seconds
        self.exclude_paths = exclude_paths or [
            "/health/simple",
            "/health/alb",
            "/ws/",  # WebSocket connections handle their own timeouts
        ]
    
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """Process request with timeout enforcement."""
        # Skip timeout for excluded paths
        path = request.url.path
        if any(path.startswith(excluded) for excluded in self.exclude_paths):
            return await call_next(request)
        
        # Skip WebSocket upgrades
        if request.headers.get("upgrade", "").lower() == "websocket":
            return await call_next(request)
        
        try:
            # Wrap the request handler with a timeout
            response = await asyncio.wait_for(
                call_next(request),
                timeout=self.timeout_seconds
            )
            return response
            
        except asyncio.TimeoutError:
            logger.error(
                f"Request timeout after {self.timeout_seconds}s: "
                f"{request.method} {path}"
            )
            return JSONResponse(
                status_code=504,
                content={
                    "error": "Request timeout",
                    "detail": f"Request exceeded {self.timeout_seconds} second limit",
                    "path": path,
                    "method": request.method
                }
            )
        except Exception as e:
            logger.error(f"Error in timeout middleware: {e}")
            raise
