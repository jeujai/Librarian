"""
Security module for the Multimodal Librarian system.

This module provides encryption, authentication, authorization, audit logging,
privacy protection, and data sanitization functionality to ensure data security
and privacy compliance.
"""

from .encryption import EncryptionService, get_encryption_service
from .auth import (
    AuthenticationService, AuthorizationService, User, UserRole, Permission,
    get_auth_service, get_authz_service
)
from .audit import AuditLogger, AuditEventType, AuditLevel, get_audit_logger
from .rate_limiter import RateLimiter, RateLimitType, get_rate_limiter
from .privacy import PrivacyService, get_privacy_service
from .sanitization import DataSanitizer, SanitizationRule, get_data_sanitizer

__all__ = [
    # Encryption
    "EncryptionService",
    "get_encryption_service",
    
    # Authentication and Authorization
    "AuthenticationService",
    "AuthorizationService", 
    "User",
    "UserRole",
    "Permission",
    "get_auth_service",
    "get_authz_service",
    
    # Audit Logging
    "AuditLogger",
    "AuditEventType",
    "AuditLevel",
    "get_audit_logger",
    
    # Rate Limiting
    "RateLimiter",
    "RateLimitType",
    "get_rate_limiter",
    
    # Privacy Protection
    "PrivacyService",
    "get_privacy_service",
    
    # Data Sanitization
    "DataSanitizer",
    "SanitizationRule",
    "get_data_sanitizer"
]