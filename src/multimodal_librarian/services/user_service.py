"""
User management service for registration, profile management, and user operations.

This service handles user registration, profile updates, password changes,
and user-related database operations.

Note: This is a simplified version that works without database connectivity
for development and testing purposes.
"""

import uuid
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any

from ..security.auth import (
    get_auth_service, AuthenticationService, User, UserRole, 
    AuthenticationError, Permission
)
from ..security.audit import get_audit_logger, AuditEventType
from ..logging_config import get_logger

logger = get_logger(__name__)


class UserRegistrationRequest:
    """User registration request model."""
    
    def __init__(self, username: str, email: str, password: str, role: UserRole = UserRole.USER):
        self.username = username
        self.email = email
        self.password = password
        self.role = role


class UserProfileUpdate:
    """User profile update model."""
    
    def __init__(self, email: Optional[str] = None, current_password: Optional[str] = None, 
                 new_password: Optional[str] = None):
        self.email = email
        self.current_password = current_password
        self.new_password = new_password


class UserService:
    """Service for user management operations."""
    
    def __init__(self):
        """Initialize user service."""
        self.auth_service = get_auth_service()
        self.audit_logger = get_audit_logger()
        
        # In-memory user storage for development/testing
        # In production, this would use a database
        self.users = {}
        
        # Initialize with default admin user
        self._initialize_default_users()
    
    def _initialize_default_users(self):
        """Initialize default users for development."""
        try:
            # Create default admin user
            admin_user = User(
                user_id="admin-001",
                username="admin",
                email="admin@multimodal-librarian.local",
                role=UserRole.ADMIN,
                is_active=True,
                created_at=datetime.utcnow()
            )
            
            # Store with hashed password
            admin_password_hash = self.auth_service.hash_password("admin123")
            self.users["admin"] = {
                "user": admin_user,
                "password_hash": admin_password_hash
            }
            
            logger.info("Default admin user initialized (username: admin, password: admin123)")
            
        except Exception as e:
            logger.error(f"Failed to initialize default users: {e}")
    
    async def register_user(self, registration: UserRegistrationRequest, 
                          created_by: Optional[str] = None) -> User:
        """Register a new user account."""
        try:
            # Validate registration data
            await self._validate_registration(registration)
            
            # Check if user already exists
            if registration.username in self.users:
                raise AuthenticationError("Username already exists")
            
            # Check if email already exists
            for stored_data in self.users.values():
                if stored_data["user"].email == registration.email:
                    raise AuthenticationError("Email already exists")
            
            # Generate user ID
            user_id = f"user-{str(uuid.uuid4())[:8]}"
            
            # Hash password
            password_hash = self.auth_service.hash_password(registration.password)
            
            # Create user object
            user = User(
                user_id=user_id,
                username=registration.username,
                email=registration.email,
                role=registration.role,
                is_active=True,
                created_at=datetime.utcnow()
            )
            
            # Store user
            self.users[registration.username] = {
                "user": user,
                "password_hash": password_hash
            }
            
            # Log user registration
            self.audit_logger.log_event(
                event_type=AuditEventType.USER_CREATED,
                action="user_registration",
                result="success",
                user_id=created_by or "system",
                details={
                    "new_user_id": user_id,
                    "username": registration.username,
                    "email": registration.email,
                    "role": registration.role.value
                }
            )
            
            logger.info(f"User registered successfully: {registration.username}")
            return user
            
        except AuthenticationError:
            raise
        except Exception as e:
            logger.error(f"User registration failed: {e}")
            
            # Log registration error
            self.audit_logger.log_event(
                event_type=AuditEventType.USER_CREATED,
                action="user_registration",
                result="error",
                user_id=created_by or "system",
                details={
                    "username": registration.username,
                    "error": str(e)
                }
            )
            
            raise AuthenticationError(f"Registration failed: {e}")
    
    async def get_user_by_id(self, user_id: str) -> Optional[User]:
        """Get user by user ID."""
        try:
            for stored_data in self.users.values():
                if stored_data["user"].user_id == user_id:
                    return stored_data["user"]
            return None
                
        except Exception as e:
            logger.error(f"Failed to get user by ID {user_id}: {e}")
            return None
    
    async def get_user_by_username(self, username: str) -> Optional[User]:
        """Get user by username."""
        try:
            stored_data = self.users.get(username)
            if stored_data:
                return stored_data["user"]
            return None
                
        except Exception as e:
            logger.error(f"Failed to get user by username {username}: {e}")
            return None
    
    async def authenticate_user(self, username: str, password: str) -> Optional[User]:
        """Authenticate user with username and password."""
        try:
            stored_data = self.users.get(username)
            if not stored_data:
                logger.warning(f"User not found: {username}")
                return None
            
            user = stored_data["user"]
            password_hash = stored_data["password_hash"]
            
            if not user.is_active:
                logger.warning(f"User account disabled: {username}")
                return None
            
            if not self.auth_service.verify_password(password, password_hash):
                logger.warning(f"Invalid password for user: {username}")
                return None
            
            # Update last login
            user.last_login = datetime.utcnow()
            
            logger.info(f"User authenticated successfully: {username}")
            return user
            
        except Exception as e:
            logger.error(f"Authentication failed for user {username}: {e}")
            return None
    
    async def update_user_profile(self, user_id: str, update: UserProfileUpdate,
                                updated_by: str) -> bool:
        """Update user profile information."""
        try:
            # Find user
            user_data = None
            for stored_data in self.users.values():
                if stored_data["user"].user_id == user_id:
                    user_data = stored_data
                    break
            
            if not user_data:
                raise AuthenticationError("User not found")
            
            user = user_data["user"]
            
            # Update email if provided
            if update.email:
                user.email = update.email
            
            # Update password if provided
            if update.new_password and update.current_password:
                # Verify current password
                current_hash = user_data["password_hash"]
                
                if not self.auth_service.verify_password(update.current_password, current_hash):
                    raise AuthenticationError("Current password is incorrect")
                
                # Hash new password
                new_password_hash = self.auth_service.hash_password(update.new_password)
                user_data["password_hash"] = new_password_hash
            
            # Log profile update
            self.audit_logger.log_event(
                event_type=AuditEventType.USER_UPDATED,
                action="profile_update",
                result="success",
                user_id=updated_by,
                details={"target_user_id": user_id}
            )
            
            logger.info(f"User profile updated successfully: {user_id}")
            return True
            
        except AuthenticationError:
            raise
        except Exception as e:
            logger.error(f"Failed to update user profile {user_id}: {e}")
            
            # Log update failure
            self.audit_logger.log_event(
                event_type=AuditEventType.USER_UPDATED,
                action="profile_update",
                result="error",
                user_id=updated_by,
                details={
                    "target_user_id": user_id,
                    "error": str(e)
                }
            )
            
            raise AuthenticationError(f"Profile update failed: {e}")
    
    async def deactivate_user(self, user_id: str, deactivated_by: str) -> bool:
        """Deactivate user account."""
        try:
            # Find and deactivate user
            for stored_data in self.users.values():
                if stored_data["user"].user_id == user_id:
                    stored_data["user"].is_active = False
                    
                    # Log user deactivation
                    self.audit_logger.log_event(
                        event_type=AuditEventType.USER_DEACTIVATED,
                        action="user_deactivation",
                        result="success",
                        user_id=deactivated_by,
                        details={"target_user_id": user_id}
                    )
                    
                    logger.info(f"User deactivated successfully: {user_id}")
                    return True
            
            return False
            
        except Exception as e:
            logger.error(f"Failed to deactivate user {user_id}: {e}")
            
            # Log deactivation failure
            self.audit_logger.log_event(
                event_type=AuditEventType.USER_DEACTIVATED,
                action="user_deactivation",
                result="error",
                user_id=deactivated_by,
                details={
                    "target_user_id": user_id,
                    "error": str(e)
                }
            )
            
            return False
    
    async def list_users(self, limit: int = 100, offset: int = 0) -> List[User]:
        """List all users with pagination."""
        try:
            users = [stored_data["user"] for stored_data in self.users.values()]
            # Simple pagination
            return users[offset:offset + limit]
                
        except Exception as e:
            logger.error(f"Failed to list users: {e}")
            return []
    
    async def _validate_registration(self, registration: UserRegistrationRequest):
        """Validate user registration data."""
        # Username validation
        if not registration.username or len(registration.username) < 3:
            raise AuthenticationError("Username must be at least 3 characters long")
        
        if len(registration.username) > 50:
            raise AuthenticationError("Username must be less than 50 characters")
        
        # Email validation
        if not registration.email or "@" not in registration.email:
            raise AuthenticationError("Valid email address is required")
        
        if len(registration.email) > 255:
            raise AuthenticationError("Email address is too long")
        
        # Password validation
        if not registration.password or len(registration.password) < 8:
            raise AuthenticationError("Password must be at least 8 characters long")
        
        if len(registration.password) > 128:
            raise AuthenticationError("Password is too long")
        
        # Role validation
        if registration.role not in [UserRole.USER, UserRole.ML_RESEARCHER, UserRole.READ_ONLY]:
            # Only allow non-admin roles for regular registration
            raise AuthenticationError("Invalid user role")


# Global service instance
_user_service = None


def get_user_service() -> UserService:
    """Get global user service instance."""
    global _user_service
    if _user_service is None:
        _user_service = UserService()
    return _user_service