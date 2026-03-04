"""
Authentication and authorization services.

This module provides user authentication, JWT token management, and
role-based access control for the Multimodal Librarian system.
"""

import jwt
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List
from enum import Enum
from dataclasses import dataclass
from fastapi import HTTPException, status
from passlib.context import CryptContext

from ..config import get_settings
from ..logging_config import get_logger
from .encryption import get_encryption_service

logger = get_logger(__name__)


class UserRole(str, Enum):
    """User roles for access control."""
    ADMIN = "admin"
    USER = "user"
    ML_RESEARCHER = "ml_researcher"
    READ_ONLY = "read_only"


class Permission(str, Enum):
    """System permissions."""
    READ_BOOKS = "read_books"
    UPLOAD_BOOKS = "upload_books"
    DELETE_BOOKS = "delete_books"
    READ_CONVERSATIONS = "read_conversations"
    CREATE_CONVERSATIONS = "create_conversations"
    DELETE_CONVERSATIONS = "delete_conversations"
    EXPORT_DATA = "export_data"
    ACCESS_ML_API = "access_ml_api"
    ADMIN_ACCESS = "admin_access"
    AUDIT_LOGS = "audit_logs"


@dataclass
class User:
    """User data model."""
    user_id: str
    username: str
    email: str
    role: UserRole
    is_active: bool = True
    created_at: Optional[datetime] = None
    last_login: Optional[datetime] = None
    permissions: Optional[List[Permission]] = None


@dataclass
class TokenData:
    """JWT token data."""
    user_id: str
    username: str
    role: UserRole
    permissions: List[Permission]
    exp: datetime
    iat: datetime


class AuthenticationService:
    """Service for user authentication and token management."""
    
    def __init__(self):
        """Initialize authentication service."""
        self.settings = get_settings()
        self.encryption_service = get_encryption_service()
        # Use simple password hashing instead of bcrypt for now
        # self.pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
        
        # Role-based permissions mapping
        self.role_permissions = {
            UserRole.ADMIN: [
                Permission.READ_BOOKS,
                Permission.UPLOAD_BOOKS,
                Permission.DELETE_BOOKS,
                Permission.READ_CONVERSATIONS,
                Permission.CREATE_CONVERSATIONS,
                Permission.DELETE_CONVERSATIONS,
                Permission.EXPORT_DATA,
                Permission.ACCESS_ML_API,
                Permission.ADMIN_ACCESS,
                Permission.AUDIT_LOGS,
            ],
            UserRole.USER: [
                Permission.READ_BOOKS,
                Permission.UPLOAD_BOOKS,
                Permission.READ_CONVERSATIONS,
                Permission.CREATE_CONVERSATIONS,
                Permission.DELETE_CONVERSATIONS,
                Permission.EXPORT_DATA,
            ],
            UserRole.ML_RESEARCHER: [
                Permission.READ_BOOKS,
                Permission.READ_CONVERSATIONS,
                Permission.ACCESS_ML_API,
                Permission.EXPORT_DATA,
            ],
            UserRole.READ_ONLY: [
                Permission.READ_BOOKS,
                Permission.READ_CONVERSATIONS,
            ],
        }
    
    def hash_password(self, password: str) -> str:
        """Hash password for secure storage."""
        try:
            # Use encryption service for password hashing
            password_hash, salt = self.encryption_service.hash_password(password)
            # Combine hash and salt for storage
            combined = f"{password_hash}:{salt}"
            logger.debug("Password hashed successfully")
            return combined
        except Exception as e:
            logger.error(f"Failed to hash password: {e}")
            raise AuthenticationError(f"Password hashing failed: {e}")
    
    def verify_password(self, plain_password: str, stored_hash: str) -> bool:
        """Verify password against hash."""
        try:
            # Split combined hash and salt
            if ':' not in stored_hash:
                logger.error("Invalid stored hash format")
                return False
            
            password_hash, salt = stored_hash.split(':', 1)
            result = self.encryption_service.verify_password(plain_password, password_hash, salt)
            logger.debug(f"Password verification: {'successful' if result else 'failed'}")
            return result
        except Exception as e:
            logger.error(f"Failed to verify password: {e}")
            return False
    
    def create_access_token(self, user: User, expires_delta: Optional[timedelta] = None) -> str:
        """Create JWT access token for user."""
        try:
            if expires_delta:
                expire = datetime.utcnow() + expires_delta
            else:
                expire = datetime.utcnow() + timedelta(
                    minutes=self.settings.access_token_expire_minutes
                )
            
            # Get user permissions
            permissions = self.get_user_permissions(user.role)
            
            to_encode = {
                "sub": user.user_id,
                "username": user.username,
                "role": user.role.value,
                "permissions": [p.value for p in permissions],
                "exp": expire,
                "iat": datetime.utcnow(),
                "type": "access"
            }
            
            encoded_jwt = jwt.encode(
                to_encode, 
                self.settings.secret_key, 
                algorithm="HS256"
            )
            
            logger.info(f"Access token created for user {user.username}")
            return encoded_jwt
            
        except Exception as e:
            logger.error(f"Failed to create access token: {e}")
            raise AuthenticationError(f"Token creation failed: {e}")
    
    def verify_token(self, token: str) -> TokenData:
        """Verify and decode JWT token."""
        try:
            payload = jwt.decode(
                token, 
                self.settings.secret_key, 
                algorithms=["HS256"]
            )
            
            user_id: str = payload.get("sub")
            username: str = payload.get("username")
            role_str: str = payload.get("role")
            permissions_str: List[str] = payload.get("permissions", [])
            exp_timestamp: float = payload.get("exp")
            iat_timestamp: float = payload.get("iat")
            
            if user_id is None or username is None:
                raise AuthenticationError("Invalid token payload")
            
            # Convert timestamps
            exp = datetime.fromtimestamp(exp_timestamp)
            iat = datetime.fromtimestamp(iat_timestamp)
            
            # Convert role and permissions
            role = UserRole(role_str)
            permissions = [Permission(p) for p in permissions_str]
            
            token_data = TokenData(
                user_id=user_id,
                username=username,
                role=role,
                permissions=permissions,
                exp=exp,
                iat=iat
            )
            
            logger.debug(f"Token verified for user {username}")
            return token_data
            
        except jwt.ExpiredSignatureError:
            logger.warning("Token has expired")
            raise AuthenticationError("Token has expired")
        except (jwt.InvalidTokenError, jwt.DecodeError, jwt.InvalidSignatureError) as e:
            logger.warning(f"Invalid token: {e}")
            raise AuthenticationError("Invalid token")
        except Exception as e:
            logger.error(f"Token verification failed: {e}")
            raise AuthenticationError(f"Token verification failed: {e}")
    
    def get_user_permissions(self, role: UserRole) -> List[Permission]:
        """Get permissions for user role."""
        return self.role_permissions.get(role, [])
    
    def authenticate_user(self, username: str, password: str) -> Optional[User]:
        """Authenticate user with username and password."""
        # Use the user service for authentication
        try:
            from ..services.user_service import get_user_service
            user_service = get_user_service()
            
            # Use async function in sync context (simplified for development)
            import asyncio
            try:
                loop = asyncio.get_event_loop()
            except RuntimeError:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
            
            return loop.run_until_complete(user_service.authenticate_user(username, password))
            
        except Exception as e:
            logger.error(f"Authentication failed for user {username}: {e}")
            return None
    
    def create_api_key(self, user: User, name: str, expires_days: int = 365) -> str:
        """Create API key for user."""
        try:
            expire = datetime.utcnow() + timedelta(days=expires_days)
            
            api_key_data = {
                "user_id": user.user_id,
                "username": user.username,
                "role": user.role.value,
                "name": name,
                "exp": expire.timestamp(),
                "iat": datetime.utcnow().timestamp(),
                "type": "api_key"
            }
            
            # Create a longer, more secure API key
            api_key = self.encryption_service.generate_secure_token(48)
            
            # In production, store the API key hash in database
            logger.info(f"API key created for user {user.username}: {name}")
            return api_key
            
        except Exception as e:
            logger.error(f"Failed to create API key: {e}")
            raise AuthenticationError(f"API key creation failed: {e}")


class AuthorizationService:
    """Service for role-based access control."""
    
    def __init__(self):
        """Initialize authorization service."""
        self.auth_service = AuthenticationService()
    
    def check_permission(self, user_permissions: List[Permission], required_permission: Permission) -> bool:
        """Check if user has required permission."""
        has_permission = required_permission in user_permissions
        logger.debug(f"Permission check: {required_permission.value} - {'granted' if has_permission else 'denied'}")
        return has_permission
    
    def check_multiple_permissions(self, user_permissions: List[Permission], required_permissions: List[Permission], require_all: bool = True) -> bool:
        """Check if user has multiple permissions."""
        if require_all:
            result = all(perm in user_permissions for perm in required_permissions)
        else:
            result = any(perm in user_permissions for perm in required_permissions)
        
        logger.debug(f"Multiple permission check ({'all' if require_all else 'any'}): {'granted' if result else 'denied'}")
        return result
    
    def check_resource_access(self, user_id: str, resource_owner_id: str, required_permission: Permission, user_permissions: List[Permission]) -> bool:
        """Check if user can access a specific resource."""
        # Admin can access everything
        if Permission.ADMIN_ACCESS in user_permissions:
            return True
        
        # Users can access their own resources
        if user_id == resource_owner_id:
            return self.check_permission(user_permissions, required_permission)
        
        # Check if user has permission for other users' resources
        # This would typically involve more complex business logic
        return False
    
    def require_permission(self, required_permission: Permission):
        """Decorator to require specific permission."""
        def decorator(func):
            def wrapper(*args, **kwargs):
                # This would be used with FastAPI dependency injection
                # Implementation depends on how user context is passed
                return func(*args, **kwargs)
            return wrapper
        return decorator


class AuthenticationError(Exception):
    """Exception raised for authentication errors."""
    pass


class AuthorizationError(Exception):
    """Exception raised for authorization errors."""
    pass


# Global service instances
_auth_service = None
_authz_service = None


def get_auth_service() -> AuthenticationService:
    """Get global authentication service instance."""
    global _auth_service
    if _auth_service is None:
        _auth_service = AuthenticationService()
    return _auth_service


def get_authz_service() -> AuthorizationService:
    """Get global authorization service instance."""
    global _authz_service
    if _authz_service is None:
        _authz_service = AuthorizationService()
    return _authz_service