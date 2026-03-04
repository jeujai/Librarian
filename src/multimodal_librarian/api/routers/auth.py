"""
Authentication API endpoints.

This module provides authentication endpoints for user login, token management,
and API key generation with comprehensive audit logging.
"""

from datetime import timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel

from ...security.auth import (
    get_auth_service, get_authz_service, AuthenticationService, 
    User, UserRole, Permission, AuthenticationError
)
from ...security.audit import get_audit_logger, AuditEventType
from ...services.user_service import (
    get_user_service, UserRegistrationRequest as ServiceUserRegistrationRequest, UserProfileUpdate
)
from ...config import get_settings
from ..models import SuccessResponse, ErrorResponse

router = APIRouter(prefix="/auth", tags=["authentication"])
security = HTTPBearer()
settings = get_settings()


class UserRegistrationRequestAPI(BaseModel):
    """User registration request model for API."""
    username: str
    email: str
    password: str
    role: str = "user"


class UserRegistrationResponse(BaseModel):
    """User registration response model."""
    user_id: str
    username: str
    email: str
    role: str
    created_at: str
    message: str


class UserProfileUpdateRequest(BaseModel):
    """User profile update request model."""
    email: Optional[str] = None
    current_password: Optional[str] = None
    new_password: Optional[str] = None


class UserListResponse(BaseModel):
    """User list response model."""
    users: list[dict]
    total: int
    limit: int
    offset: int


class LoginRequest(BaseModel):
    """Login request model."""
    username: str
    password: str


class LoginResponse(BaseModel):
    """Login response model."""
    access_token: str
    token_type: str = "bearer"
    expires_in: int
    user_id: str
    username: str
    role: str
    permissions: list[str]


class TokenValidationResponse(BaseModel):
    """Token validation response model."""
    valid: bool
    user_id: Optional[str] = None
    username: Optional[str] = None
    role: Optional[str] = None
    permissions: Optional[list[str]] = None
    expires_at: Optional[str] = None


class APIKeyRequest(BaseModel):
    """API key creation request model."""
    name: str
    expires_days: int = 365


class APIKeyResponse(BaseModel):
    """API key creation response model."""
    api_key: str
    name: str
    expires_days: int
    created_at: str


@router.post("/login", response_model=LoginResponse)
async def login(
    request: Request,
    login_data: LoginRequest,
    auth_service: AuthenticationService = Depends(get_auth_service)
):
    """Authenticate user and return access token."""
    try:
        client_ip = request.client.host if request.client else "unknown"
        user_agent = request.headers.get("user-agent", "unknown")
        audit_logger = get_audit_logger()
        
        # Authenticate user
        user = auth_service.authenticate_user(login_data.username, login_data.password)
        
        if not user:
            # Log failed authentication
            audit_logger.log_authentication(
                event_type=AuditEventType.LOGIN_FAILURE,
                username=login_data.username,
                result="invalid_credentials",
                ip_address=client_ip,
                user_agent=user_agent
            )
            
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid username or password",
                headers={"WWW-Authenticate": "Bearer"},
            )
        
        # Create access token
        access_token_expires = timedelta(minutes=settings.access_token_expire_minutes)
        access_token = auth_service.create_access_token(
            user=user, 
            expires_delta=access_token_expires
        )
        
        # Log successful authentication
        audit_logger.log_authentication(
            event_type=AuditEventType.LOGIN_SUCCESS,
            username=user.username,
            result="success",
            ip_address=client_ip,
            user_agent=user_agent,
            details={
                "user_id": user.user_id,
                "role": user.role.value,
                "token_expires_minutes": settings.access_token_expire_minutes
            }
        )
        
        # Get user permissions
        permissions = auth_service.get_user_permissions(user.role)
        
        return LoginResponse(
            access_token=access_token,
            expires_in=settings.access_token_expire_minutes * 60,
            user_id=user.user_id,
            username=user.username,
            role=user.role.value,
            permissions=[p.value for p in permissions]
        )
        
    except HTTPException:
        raise
    except Exception as e:
        audit_logger.log_authentication(
            event_type=AuditEventType.LOGIN_FAILURE,
            username=login_data.username,
            result="system_error",
            ip_address=client_ip,
            user_agent=user_agent,
            details={"error": str(e)}
        )
        
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Authentication system error"
        )


@router.post("/validate", response_model=TokenValidationResponse)
async def validate_token(
    request: Request,
    credentials: HTTPAuthorizationCredentials = Depends(security),
    auth_service: AuthenticationService = Depends(get_auth_service)
):
    """Validate JWT token and return user information."""
    try:
        client_ip = request.client.host if request.client else "unknown"
        audit_logger = get_audit_logger()
        
        # Validate token
        token_data = auth_service.verify_token(credentials.credentials)
        
        # Log token validation
        audit_logger.log_event(
            event_type=AuditEventType.TOKEN_CREATED,
            action="token_validation",
            result="success",
            user_id=token_data.user_id,
            ip_address=client_ip,
            details={
                "username": token_data.username,
                "role": token_data.role.value,
                "expires_at": token_data.exp.isoformat()
            }
        )
        
        return TokenValidationResponse(
            valid=True,
            user_id=token_data.user_id,
            username=token_data.username,
            role=token_data.role.value,
            permissions=[p.value for p in token_data.permissions],
            expires_at=token_data.exp.isoformat()
        )
        
    except AuthenticationError as e:
        audit_logger.log_event(
            event_type=AuditEventType.TOKEN_EXPIRED,
            action="token_validation",
            result="failure",
            ip_address=client_ip,
            details={"error": str(e)}
        )
        
        return TokenValidationResponse(valid=False)
    except Exception as e:
        audit_logger.log_event(
            event_type=AuditEventType.TOKEN_EXPIRED,
            action="token_validation",
            result="error",
            ip_address=client_ip,
            details={"error": str(e)}
        )
        
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Token validation error"
        )


@router.post("/api-key", response_model=APIKeyResponse)
async def create_api_key(
    request: Request,
    api_key_data: APIKeyRequest,
    credentials: HTTPAuthorizationCredentials = Depends(security),
    auth_service: AuthenticationService = Depends(get_auth_service)
):
    """Create API key for authenticated user."""
    try:
        client_ip = request.client.host if request.client else "unknown"
        audit_logger = get_audit_logger()
        
        # Validate token and get user
        token_data = auth_service.verify_token(credentials.credentials)
        
        # Create user object for API key generation
        user = User(
            user_id=token_data.user_id,
            username=token_data.username,
            email=f"{token_data.username}@example.com",  # Placeholder
            role=token_data.role
        )
        
        # Create API key
        api_key = auth_service.create_api_key(
            user=user,
            name=api_key_data.name,
            expires_days=api_key_data.expires_days
        )
        
        # Log API key creation
        audit_logger.log_event(
            event_type=AuditEventType.TOKEN_CREATED,
            action="api_key_creation",
            result="success",
            user_id=token_data.user_id,
            ip_address=client_ip,
            details={
                "api_key_name": api_key_data.name,
                "expires_days": api_key_data.expires_days
            }
        )
        
        return APIKeyResponse(
            api_key=api_key,
            name=api_key_data.name,
            expires_days=api_key_data.expires_days,
            created_at=token_data.iat.isoformat()
        )
        
    except AuthenticationError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(e)
        )
    except Exception as e:
        audit_logger.log_event(
            event_type=AuditEventType.TOKEN_CREATED,
            action="api_key_creation",
            result="error",
            ip_address=client_ip,
            details={"error": str(e)}
        )
        
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="API key creation error"
        )


@router.post("/logout", response_model=SuccessResponse)
async def logout(
    request: Request,
    credentials: HTTPAuthorizationCredentials = Depends(security),
    auth_service: AuthenticationService = Depends(get_auth_service)
):
    """Logout user (invalidate token)."""
    try:
        client_ip = request.client.host if request.client else "unknown"
        audit_logger = get_audit_logger()
        
        # Validate token to get user info
        token_data = auth_service.verify_token(credentials.credentials)
        
        # Log logout (in production, you would invalidate the token)
        audit_logger.log_authentication(
            event_type=AuditEventType.LOGOUT,
            username=token_data.username,
            result="success",
            ip_address=client_ip,
            details={"user_id": token_data.user_id}
        )
        
        return SuccessResponse(
            message="Logged out successfully",
            details={"user_id": token_data.user_id}
        )
        
    except AuthenticationError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(e)
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Logout error"
        )


@router.get("/me", response_model=dict)
async def get_current_user(
    request: Request,
    credentials: HTTPAuthorizationCredentials = Depends(security),
    auth_service: AuthenticationService = Depends(get_auth_service)
):
    """Get current user information."""
    try:
        # Validate token and get user info
        token_data = auth_service.verify_token(credentials.credentials)
        
        return {
            "user_id": token_data.user_id,
            "username": token_data.username,
            "role": token_data.role.value,
            "permissions": [p.value for p in token_data.permissions],
            "token_expires_at": token_data.exp.isoformat(),
            "token_issued_at": token_data.iat.isoformat()
        }
        
    except AuthenticationError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(e)
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="User information retrieval error"
        )


@router.post("/register", response_model=UserRegistrationResponse)
async def register_user(
    request: Request,
    registration_data: UserRegistrationRequestAPI,
    user_service = Depends(get_user_service)
):
    """Register a new user account."""
    try:
        client_ip = request.client.host if request.client else "unknown"
        audit_logger = get_audit_logger()
        
        # Validate role
        try:
            role = UserRole(registration_data.role)
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid role: {registration_data.role}"
            )
        
        # Create registration request using the service's UserRegistrationRequest
        registration = ServiceUserRegistrationRequest(
            username=registration_data.username,
            email=registration_data.email,
            password=registration_data.password,
            role=role
        )
        
        # Register user
        user = await user_service.register_user(registration)
        
        # Log successful registration
        audit_logger.log_event(
            event_type=AuditEventType.USER_CREATED,
            action="user_registration",
            result="success",
            ip_address=client_ip,
            details={
                "user_id": user.user_id,
                "username": user.username,
                "email": user.email,
                "role": user.role.value
            }
        )
        
        return UserRegistrationResponse(
            user_id=user.user_id,
            username=user.username,
            email=user.email,
            role=user.role.value,
            created_at=user.created_at.isoformat() if user.created_at else "",
            message="User registered successfully"
        )
        
    except AuthenticationError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        audit_logger.log_event(
            event_type=AuditEventType.USER_CREATED,
            action="user_registration",
            result="error",
            ip_address=client_ip,
            details={"error": str(e)}
        )
        
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Registration system error"
        )


@router.put("/profile", response_model=SuccessResponse)
async def update_profile(
    request: Request,
    profile_data: UserProfileUpdateRequest,
    credentials: HTTPAuthorizationCredentials = Depends(security),
    auth_service: AuthenticationService = Depends(get_auth_service),
    user_service = Depends(get_user_service)
):
    """Update user profile information."""
    try:
        client_ip = request.client.host if request.client else "unknown"
        audit_logger = get_audit_logger()
        
        # Validate token and get user
        token_data = auth_service.verify_token(credentials.credentials)
        
        # Create profile update request
        update = UserProfileUpdate(
            email=profile_data.email,
            current_password=profile_data.current_password,
            new_password=profile_data.new_password
        )
        
        # Update profile
        success = await user_service.update_user_profile(
            user_id=token_data.user_id,
            update=update,
            updated_by=token_data.user_id
        )
        
        if not success:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Profile update failed"
            )
        
        return SuccessResponse(
            message="Profile updated successfully",
            details={"user_id": token_data.user_id}
        )
        
    except AuthenticationError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Profile update error"
        )


@router.get("/users", response_model=UserListResponse)
async def list_users(
    request: Request,
    limit: int = 100,
    offset: int = 0,
    credentials: HTTPAuthorizationCredentials = Depends(security),
    auth_service: AuthenticationService = Depends(get_auth_service),
    user_service = Depends(get_user_service)
):
    """List all users (admin only)."""
    try:
        # Validate token and get user
        token_data = auth_service.verify_token(credentials.credentials)
        
        # Check admin permission
        if Permission.ADMIN_ACCESS not in token_data.permissions:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Admin access required"
            )
        
        # Get users
        users = await user_service.list_users(limit=limit, offset=offset)
        
        # Convert to response format
        user_list = []
        for user in users:
            user_list.append({
                "user_id": user.user_id,
                "username": user.username,
                "email": user.email,
                "role": user.role.value,
                "is_active": user.is_active,
                "created_at": user.created_at.isoformat() if user.created_at else None,
                "last_login": user.last_login.isoformat() if user.last_login else None
            })
        
        return UserListResponse(
            users=user_list,
            total=len(user_list),
            limit=limit,
            offset=offset
        )
        
    except AuthenticationError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(e)
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="User list retrieval error"
        )