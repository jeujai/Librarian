"""
Authentication middleware for FastAPI application.

This middleware handles JWT token validation, user authentication,
and role-based access control for protected endpoints.
"""

from typing import Callable, List, Optional

from fastapi import HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response

from ...logging_config import get_logger
from ...security.audit import AuditEventType, get_audit_logger
from ...security.auth import (
    AuthenticationError,
    AuthenticationService,
    AuthorizationService,
    Permission,
    TokenData,
    get_auth_service,
    get_authz_service,
)

logger = get_logger(__name__)
security = HTTPBearer(auto_error=False)


class AuthenticationMiddleware(BaseHTTPMiddleware):
    """Middleware for handling authentication and authorization."""
    
    def __init__(self, app, require_auth: bool = True):
        """Initialize authentication middleware."""
        super().__init__(app)
        self.require_auth = require_auth
        self.auth_service = get_auth_service()
        self.authz_service = get_authz_service()
        self.audit_logger = get_audit_logger()
        
        # Public endpoints that don't require authentication
        self.public_endpoints = {
            "/",
            "/health",
            "/features",
            "/docs",
            "/redoc",
            "/openapi.json",
            "/auth/login",
            "/auth/validate",
            "/static",
            "/favicon.ico"
        }
        
        # Endpoints that require specific permissions
        self.protected_endpoints = {
            "/api/documents": [Permission.UPLOAD_BOOKS],
            "/api/analytics": [Permission.READ_BOOKS],
            "/api/cache": [Permission.ADMIN_ACCESS],
            "/api/ai-optimization": [Permission.ACCESS_ML_API],
            "/admin": [Permission.ADMIN_ACCESS],
            "/api/audit": [Permission.AUDIT_LOGS]
        }
    
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        # Skip WebSocket connections - BaseHTTPMiddleware doesn't handle them properly
        # WebSocket connections use the Upgrade header to switch protocols
        if request.headers.get("upgrade", "").lower() == "websocket":
            return await call_next(request)
        """Process request through authentication middleware."""
        try:
            # Skip authentication if disabled
            if not self.require_auth:
                return await call_next(request)
            
            # Check if endpoint is public
            if self._is_public_endpoint(request.url.path):
                return await call_next(request)
            
            # Extract and validate token
            token_data = await self._authenticate_request(request)
            
            # Check permissions for protected endpoints
            if not await self._authorize_request(request, token_data):
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Insufficient permissions"
                )
            
            # Add user context to request
            request.state.user = token_data
            request.state.authenticated = True
            
            # Log successful authentication
            self.audit_logger.log_event(
                event_type=AuditEventType.ACCESS_GRANTED,
                action="endpoint_access",
                result="success",
                user_id=token_data.user_id,
                ip_address=self._get_client_ip(request),
                details={
                    "endpoint": request.url.path,
                    "method": request.method,
                    "user_role": token_data.role.value
                }
            )
            
            return await call_next(request)
            
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Authentication middleware error: {e}")
            
            # Log authentication failure
            self.audit_logger.log_event(
                event_type=AuditEventType.ACCESS_DENIED,
                action="authentication_error",
                result="error",
                ip_address=self._get_client_ip(request),
                details={
                    "endpoint": request.url.path,
                    "method": request.method,
                    "error": str(e)
                }
            )
            
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Authentication system error"
            )
    
    def _is_public_endpoint(self, path: str) -> bool:
        """Check if endpoint is public and doesn't require authentication."""
        # Exact matches
        if path in self.public_endpoints:
            return True
        
        # Prefix matches for static files and docs
        public_prefixes = ["/static/", "/docs", "/redoc", "/auth/"]
        for prefix in public_prefixes:
            if path.startswith(prefix):
                return True
        
        return False
    
    async def _authenticate_request(self, request: Request) -> TokenData:
        """Extract and validate authentication token from request."""
        try:
            # Try to get token from Authorization header
            authorization = request.headers.get("Authorization")
            if not authorization:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Missing authorization header",
                    headers={"WWW-Authenticate": "Bearer"}
                )
            
            # Extract token from Bearer header
            if not authorization.startswith("Bearer "):
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Invalid authorization header format",
                    headers={"WWW-Authenticate": "Bearer"}
                )
            
            token = authorization.split(" ")[1]
            
            # Validate token
            token_data = self.auth_service.verify_token(token)
            
            return token_data
            
        except AuthenticationError as e:
            # Log authentication failure
            self.audit_logger.log_event(
                event_type=AuditEventType.ACCESS_DENIED,
                action="token_validation",
                result="failure",
                ip_address=self._get_client_ip(request),
                details={
                    "endpoint": request.url.path,
                    "error": str(e)
                }
            )
            
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=str(e),
                headers={"WWW-Authenticate": "Bearer"}
            )
        except Exception as e:
            logger.error(f"Token validation error: {e}")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token",
                headers={"WWW-Authenticate": "Bearer"}
            )
    
    async def _authorize_request(self, request: Request, token_data: TokenData) -> bool:
        """Check if user has required permissions for the endpoint."""
        try:
            path = request.url.path
            
            # Check if endpoint requires specific permissions
            required_permissions = None
            for endpoint_pattern, permissions in self.protected_endpoints.items():
                if path.startswith(endpoint_pattern):
                    required_permissions = permissions
                    break
            
            # If no specific permissions required, allow access
            if not required_permissions:
                return True
            
            # Check if user has required permissions
            has_permission = self.authz_service.check_multiple_permissions(
                user_permissions=token_data.permissions,
                required_permissions=required_permissions,
                require_all=False  # User needs at least one of the required permissions
            )
            
            if not has_permission:
                # Log authorization failure
                self.audit_logger.log_event(
                    event_type=AuditEventType.ACCESS_DENIED,
                    action="authorization_check",
                    result="failure",
                    user_id=token_data.user_id,
                    ip_address=self._get_client_ip(request),
                    details={
                        "endpoint": path,
                        "required_permissions": [p.value for p in required_permissions],
                        "user_permissions": [p.value for p in token_data.permissions],
                        "user_role": token_data.role.value
                    }
                )
            
            return has_permission
            
        except Exception as e:
            logger.error(f"Authorization error: {e}")
            return False
    
    def _get_client_ip(self, request: Request) -> str:
        """Extract client IP address from request."""
        # Check for forwarded headers (common in load balancers)
        forwarded_for = request.headers.get("X-Forwarded-For")
        if forwarded_for:
            return forwarded_for.split(",")[0].strip()
        
        real_ip = request.headers.get("X-Real-IP")
        if real_ip:
            return real_ip
        
        # Fallback to direct client IP
        if request.client:
            return request.client.host
        
        return "unknown"


class OptionalAuthenticationMiddleware(AuthenticationMiddleware):
    """Middleware that adds user context if authenticated but doesn't require it."""
    
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """Process request with optional authentication."""
        # Skip WebSocket connections - BaseHTTPMiddleware doesn't handle them properly
        if request.headers.get("upgrade", "").lower() == "websocket":
            return await call_next(request)
        
        try:
            # Always allow request to proceed
            request.state.authenticated = False
            request.state.user = None
            
            # Skip authentication if disabled
            if not self.require_auth:
                return await call_next(request)
            
            # Try to authenticate if token is present
            try:
                authorization = request.headers.get("Authorization")
                if authorization and authorization.startswith("Bearer "):
                    token = authorization.split(" ")[1]
                    token_data = self.auth_service.verify_token(token)
                    
                    # Add user context
                    request.state.user = token_data
                    request.state.authenticated = True
                    
                    logger.debug(f"Optional auth successful for user {token_data.username}")
                    
            except Exception as e:
                # Log but don't fail the request
                logger.debug(f"Optional authentication failed: {e}")
            
            return await call_next(request)
            
        except Exception as e:
            logger.error(f"Optional authentication middleware error: {e}")
            return await call_next(request)


def get_current_user(request: Request) -> Optional[TokenData]:
    """Get current authenticated user from request state."""
    return getattr(request.state, 'user', None)


def require_authentication(request: Request) -> TokenData:
    """Require authentication and return current user."""
    user = get_current_user(request)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required"
        )
    return user


def require_permission(permission: Permission):
    """Decorator to require specific permission."""
    def decorator(func):
        async def wrapper(request: Request, *args, **kwargs):
            user = require_authentication(request)
            authz_service = get_authz_service()
            
            if not authz_service.check_permission(user.permissions, permission):
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail=f"Permission required: {permission.value}"
                )
            
            return await func(request, *args, **kwargs)
        return wrapper
    return decorator


def require_role(required_role: str):
    """Decorator to require specific user role."""
    def decorator(func):
        async def wrapper(request: Request, *args, **kwargs):
            user = require_authentication(request)
            
            if user.role.value != required_role:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail=f"Role required: {required_role}"
                )
            
            return await func(request, *args, **kwargs)
        return wrapper
    return decorator