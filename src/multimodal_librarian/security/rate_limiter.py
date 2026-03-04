"""
Rate limiting service for API endpoints.

This module provides rate limiting functionality to prevent abuse
and ensure fair usage of system resources.
"""

import time
import asyncio
from typing import Dict, Optional, Tuple
from dataclasses import dataclass, field
from collections import defaultdict, deque
from enum import Enum

from ..logging_config import get_logger

logger = get_logger(__name__)


class RateLimitType(str, Enum):
    """Types of rate limits."""
    PER_IP = "per_ip"
    PER_USER = "per_user"
    PER_API_KEY = "per_api_key"
    GLOBAL = "global"


@dataclass
class RateLimit:
    """Rate limit configuration."""
    requests: int  # Number of requests allowed
    window: int    # Time window in seconds
    burst: Optional[int] = None  # Burst allowance (optional)


@dataclass
class RateLimitState:
    """Current state of rate limiting for an identifier."""
    requests: deque = field(default_factory=deque)
    last_request: float = 0.0
    burst_used: int = 0


class RateLimiter:
    """Advanced rate limiter with multiple strategies."""
    
    def __init__(self):
        """Initialize rate limiter."""
        self.limits: Dict[str, RateLimit] = {}
        self.states: Dict[str, Dict[str, RateLimitState]] = defaultdict(lambda: defaultdict(RateLimitState))
        self.global_state = RateLimitState()
        
        # Default rate limits
        self.set_default_limits()
    
    def set_default_limits(self):
        """Set default rate limits for different endpoints."""
        # General API limits
        self.limits["api_general"] = RateLimit(requests=60, window=60)  # 60 requests per minute
        self.limits["api_upload"] = RateLimit(requests=10, window=60)   # 10 uploads per minute
        self.limits["api_query"] = RateLimit(requests=30, window=60)    # 30 queries per minute
        self.limits["api_export"] = RateLimit(requests=5, window=60)    # 5 exports per minute
        
        # ML API limits (more restrictive)
        self.limits["ml_streaming"] = RateLimit(requests=100, window=3600)  # 100 requests per hour
        self.limits["ml_batch"] = RateLimit(requests=10, window=3600)       # 10 batch requests per hour
        self.limits["ml_training"] = RateLimit(requests=50, window=3600)    # 50 training requests per hour
        
        # Authentication limits
        self.limits["auth_login"] = RateLimit(requests=5, window=300)       # 5 login attempts per 5 minutes
        self.limits["auth_token"] = RateLimit(requests=10, window=3600)     # 10 token requests per hour
        
        # WebSocket limits
        self.limits["websocket_connect"] = RateLimit(requests=10, window=60)  # 10 connections per minute
        self.limits["websocket_message"] = RateLimit(requests=120, window=60) # 120 messages per minute
    
    def set_limit(self, endpoint: str, limit: RateLimit):
        """Set rate limit for specific endpoint."""
        self.limits[endpoint] = limit
        logger.info(f"Rate limit set for {endpoint}: {limit.requests} requests per {limit.window}s")
    
    def check_rate_limit(self, identifier: str, endpoint: str, limit_type: RateLimitType = RateLimitType.PER_IP) -> Tuple[bool, Dict[str, any]]:
        """Check if request is within rate limit."""
        try:
            current_time = time.time()
            limit = self.limits.get(endpoint)
            
            if not limit:
                # No limit configured, allow request
                return True, {"allowed": True, "reason": "no_limit_configured"}
            
            # Get state for this identifier and endpoint
            state_key = f"{limit_type.value}:{identifier}"
            state = self.states[state_key][endpoint]
            
            # Clean old requests outside the window
            cutoff_time = current_time - limit.window
            while state.requests and state.requests[0] <= cutoff_time:
                state.requests.popleft()
            
            # Check if we're within the limit
            current_requests = len(state.requests)
            
            if current_requests >= limit.requests:
                # Rate limit exceeded
                oldest_request = state.requests[0] if state.requests else current_time
                reset_time = oldest_request + limit.window
                
                logger.warning(f"Rate limit exceeded for {identifier} on {endpoint}: {current_requests}/{limit.requests}")
                
                return False, {
                    "allowed": False,
                    "reason": "rate_limit_exceeded",
                    "limit": limit.requests,
                    "window": limit.window,
                    "current": current_requests,
                    "reset_time": reset_time,
                    "retry_after": int(reset_time - current_time)
                }
            
            # Allow request and record it
            state.requests.append(current_time)
            state.last_request = current_time
            
            logger.debug(f"Rate limit check passed for {identifier} on {endpoint}: {current_requests + 1}/{limit.requests}")
            
            return True, {
                "allowed": True,
                "limit": limit.requests,
                "window": limit.window,
                "current": current_requests + 1,
                "remaining": limit.requests - current_requests - 1
            }
            
        except Exception as e:
            logger.error(f"Rate limit check failed: {e}")
            # On error, allow the request (fail open)
            return True, {"allowed": True, "reason": "check_failed", "error": str(e)}
    
    def check_burst_limit(self, identifier: str, endpoint: str, burst_requests: int = 5) -> bool:
        """Check burst rate limit (short-term spike protection)."""
        try:
            current_time = time.time()
            state_key = f"burst:{identifier}"
            state = self.states[state_key][endpoint]
            
            # Check requests in last 10 seconds for burst detection
            burst_window = 10
            cutoff_time = current_time - burst_window
            
            # Clean old requests
            while state.requests and state.requests[0] <= cutoff_time:
                state.requests.popleft()
            
            # Check burst limit
            if len(state.requests) >= burst_requests:
                logger.warning(f"Burst limit exceeded for {identifier} on {endpoint}")
                return False
            
            # Record request
            state.requests.append(current_time)
            return True
            
        except Exception as e:
            logger.error(f"Burst limit check failed: {e}")
            return True  # Fail open
    
    def get_rate_limit_status(self, identifier: str, endpoint: str, limit_type: RateLimitType = RateLimitType.PER_IP) -> Dict[str, any]:
        """Get current rate limit status for identifier and endpoint."""
        try:
            current_time = time.time()
            limit = self.limits.get(endpoint)
            
            if not limit:
                return {"status": "no_limit", "endpoint": endpoint}
            
            state_key = f"{limit_type.value}:{identifier}"
            state = self.states[state_key][endpoint]
            
            # Clean old requests
            cutoff_time = current_time - limit.window
            while state.requests and state.requests[0] <= cutoff_time:
                state.requests.popleft()
            
            current_requests = len(state.requests)
            remaining = max(0, limit.requests - current_requests)
            
            # Calculate reset time
            reset_time = None
            if state.requests:
                oldest_request = state.requests[0]
                reset_time = oldest_request + limit.window
            
            return {
                "status": "active",
                "endpoint": endpoint,
                "limit": limit.requests,
                "window": limit.window,
                "current": current_requests,
                "remaining": remaining,
                "reset_time": reset_time,
                "last_request": state.last_request
            }
            
        except Exception as e:
            logger.error(f"Failed to get rate limit status: {e}")
            return {"status": "error", "error": str(e)}
    
    def reset_rate_limit(self, identifier: str, endpoint: str, limit_type: RateLimitType = RateLimitType.PER_IP):
        """Reset rate limit for specific identifier and endpoint."""
        try:
            state_key = f"{limit_type.value}:{identifier}"
            if state_key in self.states and endpoint in self.states[state_key]:
                del self.states[state_key][endpoint]
                logger.info(f"Rate limit reset for {identifier} on {endpoint}")
        except Exception as e:
            logger.error(f"Failed to reset rate limit: {e}")
    
    def cleanup_old_states(self, max_age: int = 3600):
        """Clean up old rate limit states to prevent memory leaks."""
        try:
            current_time = time.time()
            cutoff_time = current_time - max_age
            
            states_to_remove = []
            
            for state_key, endpoints in self.states.items():
                endpoints_to_remove = []
                
                for endpoint, state in endpoints.items():
                    if state.last_request < cutoff_time:
                        endpoints_to_remove.append(endpoint)
                
                for endpoint in endpoints_to_remove:
                    del endpoints[endpoint]
                
                if not endpoints:
                    states_to_remove.append(state_key)
            
            for state_key in states_to_remove:
                del self.states[state_key]
            
            if states_to_remove or any(endpoints_to_remove for endpoints_to_remove in [[]]):
                logger.info(f"Cleaned up {len(states_to_remove)} old rate limit states")
                
        except Exception as e:
            logger.error(f"Failed to cleanup old states: {e}")
    
    async def start_cleanup_task(self, cleanup_interval: int = 300):
        """Start background task to cleanup old states."""
        while True:
            try:
                await asyncio.sleep(cleanup_interval)
                self.cleanup_old_states()
            except Exception as e:
                logger.error(f"Cleanup task error: {e}")
                await asyncio.sleep(60)  # Wait before retrying


# Global rate limiter instance
_rate_limiter = None


def get_rate_limiter() -> RateLimiter:
    """Get global rate limiter instance."""
    global _rate_limiter
    if _rate_limiter is None:
        _rate_limiter = RateLimiter()
    return _rate_limiter