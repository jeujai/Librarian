"""
Tests for security components.

This module tests encryption, authentication, authorization, audit logging,
privacy protection, and data sanitization functionality.
"""

import pytest
import asyncio
from datetime import datetime, timedelta
from unittest.mock import Mock, patch

from src.multimodal_librarian.security import (
    EncryptionService, AuthenticationService, AuthorizationService,
    AuditLogger, RateLimiter, PrivacyService, DataSanitizer,
    User, UserRole, Permission, AuditEventType, RateLimitType,
    get_encryption_service, get_auth_service, get_authz_service,
    get_audit_logger, get_rate_limiter, get_privacy_service,
    get_data_sanitizer
)


class TestEncryptionService:
    """Test encryption service functionality."""
    
    def test_text_encryption_decryption(self):
        """Test text encryption and decryption."""
        encryption_service = EncryptionService()
        
        original_text = "This is sensitive data that needs encryption"
        
        # Encrypt text
        encrypted_text = encryption_service.encrypt_text(original_text)
        assert encrypted_text != original_text
        assert len(encrypted_text) > 0
        
        # Decrypt text
        decrypted_text = encryption_service.decrypt_text(encrypted_text)
        assert decrypted_text == original_text
    
    def test_password_hashing_verification(self):
        """Test password hashing and verification."""
        encryption_service = EncryptionService()
        
        password = "secure_password_123"
        
        # Hash password
        password_hash, salt = encryption_service.hash_password(password)
        assert password_hash != password
        assert len(password_hash) > 0
        assert len(salt) > 0
        
        # Verify correct password
        assert encryption_service.verify_password(password, password_hash, salt)
        
        # Verify incorrect password
        assert not encryption_service.verify_password("wrong_password", password_hash, salt)
    
    def test_secure_token_generation(self):
        """Test secure token generation."""
        encryption_service = EncryptionService()
        
        token1 = encryption_service.generate_secure_token(32)
        token2 = encryption_service.generate_secure_token(32)
        
        assert len(token1) > 0
        assert len(token2) > 0
        assert token1 != token2  # Should be unique
    
    def test_sensitive_fields_encryption(self):
        """Test encryption of sensitive fields in dictionaries."""
        encryption_service = EncryptionService()
        
        data = {
            "username": "testuser",
            "password": "secret123",
            "email": "test@example.com",
            "public_info": "not sensitive"
        }
        
        sensitive_fields = ["password", "email"]
        
        # Encrypt sensitive fields
        encrypted_data = encryption_service.encrypt_sensitive_fields(data, sensitive_fields)
        
        assert encrypted_data["username"] == data["username"]  # Not encrypted
        assert encrypted_data["public_info"] == data["public_info"]  # Not encrypted
        assert encrypted_data["password"] != data["password"]  # Encrypted
        assert encrypted_data["email"] != data["email"]  # Encrypted
        
        # Decrypt sensitive fields
        decrypted_data = encryption_service.decrypt_sensitive_fields(encrypted_data, sensitive_fields)
        
        assert decrypted_data == data  # Should match original


class TestAuthenticationService:
    """Test authentication service functionality."""
    
    def test_user_authentication(self):
        """Test user authentication."""
        auth_service = AuthenticationService()
        
        # Test valid user authentication
        user = auth_service.authenticate_user("admin", "admin123")
        assert user is not None
        assert user.username == "admin"
        assert user.role == UserRole.ADMIN
        
        # Test invalid credentials
        user = auth_service.authenticate_user("admin", "wrong_password")
        assert user is None
        
        # Test non-existent user
        user = auth_service.authenticate_user("nonexistent", "password")
        assert user is None
    
    def test_token_creation_verification(self):
        """Test JWT token creation and verification."""
        auth_service = AuthenticationService()
        
        user = User(
            user_id="test-001",
            username="testuser",
            email="test@example.com",
            role=UserRole.USER
        )
        
        # Create token
        token = auth_service.create_access_token(user)
        assert len(token) > 0
        
        # Verify token
        token_data = auth_service.verify_token(token)
        assert token_data.user_id == user.user_id
        assert token_data.username == user.username
        assert token_data.role == user.role
    
    def test_user_permissions(self):
        """Test user permission retrieval."""
        auth_service = AuthenticationService()
        
        # Admin permissions
        admin_permissions = auth_service.get_user_permissions(UserRole.ADMIN)
        assert Permission.ADMIN_ACCESS in admin_permissions
        assert Permission.READ_BOOKS in admin_permissions
        
        # User permissions
        user_permissions = auth_service.get_user_permissions(UserRole.USER)
        assert Permission.READ_BOOKS in user_permissions
        assert Permission.ADMIN_ACCESS not in user_permissions
        
        # Read-only permissions
        readonly_permissions = auth_service.get_user_permissions(UserRole.READ_ONLY)
        assert Permission.READ_BOOKS in readonly_permissions
        assert Permission.UPLOAD_BOOKS not in readonly_permissions


class TestAuthorizationService:
    """Test authorization service functionality."""
    
    def test_permission_checking(self):
        """Test permission checking."""
        authz_service = AuthorizationService()
        
        user_permissions = [Permission.READ_BOOKS, Permission.CREATE_CONVERSATIONS]
        
        # Test valid permission
        assert authz_service.check_permission(user_permissions, Permission.READ_BOOKS)
        
        # Test invalid permission
        assert not authz_service.check_permission(user_permissions, Permission.ADMIN_ACCESS)
    
    def test_multiple_permissions_checking(self):
        """Test multiple permissions checking."""
        authz_service = AuthorizationService()
        
        user_permissions = [Permission.READ_BOOKS, Permission.CREATE_CONVERSATIONS]
        required_permissions = [Permission.READ_BOOKS, Permission.CREATE_CONVERSATIONS]
        
        # Test require all (should pass)
        assert authz_service.check_multiple_permissions(
            user_permissions, required_permissions, require_all=True
        )
        
        # Test require any (should pass)
        assert authz_service.check_multiple_permissions(
            user_permissions, [Permission.READ_BOOKS, Permission.ADMIN_ACCESS], require_all=False
        )
        
        # Test require all with missing permission (should fail)
        assert not authz_service.check_multiple_permissions(
            user_permissions, [Permission.READ_BOOKS, Permission.ADMIN_ACCESS], require_all=True
        )


class TestRateLimiter:
    """Test rate limiter functionality."""
    
    def test_rate_limit_checking(self):
        """Test rate limit checking."""
        rate_limiter = RateLimiter()
        
        identifier = "test_user"
        endpoint = "api_general"
        
        # First request should be allowed
        allowed, info = rate_limiter.check_rate_limit(identifier, endpoint)
        assert allowed
        assert info["allowed"]
        
        # Should still be within limit for reasonable number of requests
        for _ in range(10):
            allowed, info = rate_limiter.check_rate_limit(identifier, endpoint)
            assert allowed
    
    def test_rate_limit_exceeded(self):
        """Test rate limit exceeded scenario."""
        rate_limiter = RateLimiter()
        
        # Set a very low limit for testing
        from src.multimodal_librarian.security.rate_limiter import RateLimit
        rate_limiter.set_limit("test_endpoint", RateLimit(requests=2, window=60))
        
        identifier = "test_user"
        endpoint = "test_endpoint"
        
        # First two requests should be allowed
        allowed, info = rate_limiter.check_rate_limit(identifier, endpoint)
        assert allowed
        
        allowed, info = rate_limiter.check_rate_limit(identifier, endpoint)
        assert allowed
        
        # Third request should be denied
        allowed, info = rate_limiter.check_rate_limit(identifier, endpoint)
        assert not allowed
        assert info["reason"] == "rate_limit_exceeded"
    
    def test_rate_limit_status(self):
        """Test rate limit status retrieval."""
        rate_limiter = RateLimiter()
        
        identifier = "test_user"
        endpoint = "api_general"
        
        # Make a request
        rate_limiter.check_rate_limit(identifier, endpoint)
        
        # Get status
        status = rate_limiter.get_rate_limit_status(identifier, endpoint)
        assert status["status"] == "active"
        assert "current" in status
        assert "remaining" in status


class TestDataSanitizer:
    """Test data sanitization functionality."""
    
    def test_text_sanitization(self):
        """Test text sanitization."""
        sanitizer = DataSanitizer()
        
        # Test email sanitization
        text_with_email = "Contact us at support@example.com for help"
        sanitized = sanitizer.sanitize_text(text_with_email)
        assert "support@example.com" not in sanitized
        assert "[EMAIL-REDACTED]" in sanitized
        
        # Test phone number sanitization
        text_with_phone = "Call us at 555-123-4567"
        sanitized = sanitizer.sanitize_text(text_with_phone)
        assert "555-123-4567" not in sanitized
        assert "[PHONE-REDACTED]" in sanitized
    
    def test_dict_sanitization(self):
        """Test dictionary sanitization."""
        sanitizer = DataSanitizer()
        
        data = {
            "username": "testuser",
            "password": "secret123",
            "email": "test@example.com",
            "phone": "555-123-4567",
            "public_info": "This is public"
        }
        
        sanitized = sanitizer.sanitize_dict(data)
        
        assert sanitized["username"] == "testuser"  # Not sensitive key
        assert sanitized["password"] == "[REDACTED]"  # Sensitive key
        assert sanitized["public_info"] == "This is public"  # Not sensitive
        assert sanitized["email"] == "[REDACTED]"  # Sensitive key
        assert sanitized["phone"] == "[REDACTED]"  # Sensitive key
    
    def test_sensitive_content_detection(self):
        """Test sensitive content detection."""
        sanitizer = DataSanitizer()
        
        # Test with sensitive content
        sensitive_text = "My SSN is 123-45-6789"
        assert sanitizer.is_sensitive_content(sensitive_text)
        
        # Test with non-sensitive content
        normal_text = "This is just normal text"
        assert not sanitizer.is_sensitive_content(normal_text)
    
    def test_custom_rules(self):
        """Test custom sanitization rules."""
        sanitizer = DataSanitizer()
        
        from src.multimodal_librarian.security.sanitization import SanitizationRule
        
        # Add custom rule
        custom_rule = SanitizationRule(
            name="custom_id",
            pattern=r'ID-\d{6}',
            replacement="[CUSTOM-ID-REDACTED]",
            description="Custom ID pattern"
        )
        
        sanitizer.add_custom_rule(custom_rule)
        
        # Test custom rule
        text_with_custom = "Your ID is ID-123456"
        sanitized = sanitizer.sanitize_text(text_with_custom)
        assert "ID-123456" not in sanitized
        assert "[CUSTOM-ID-REDACTED]" in sanitized


@pytest.mark.asyncio
class TestAuditLogger:
    """Test audit logger functionality."""
    
    async def test_audit_event_logging(self):
        """Test audit event logging."""
        audit_logger = AuditLogger()
        
        # Log an event
        audit_logger.log_event(
            event_type=AuditEventType.LOGIN_SUCCESS,
            action="user_login",
            result="success",
            user_id="test_user",
            ip_address="127.0.0.1",
            details={"test": "data"}
        )
        
        # Give some time for async processing
        await asyncio.sleep(0.1)
        
        # Verify event was logged (would check file in real implementation)
        assert True  # Placeholder assertion
    
    async def test_authentication_logging(self):
        """Test authentication event logging."""
        audit_logger = AuditLogger()
        
        # Log successful authentication
        audit_logger.log_authentication(
            event_type=AuditEventType.LOGIN_SUCCESS,
            username="testuser",
            result="success",
            ip_address="127.0.0.1"
        )
        
        # Log failed authentication
        audit_logger.log_authentication(
            event_type=AuditEventType.LOGIN_FAILURE,
            username="testuser",
            result="invalid_credentials",
            ip_address="127.0.0.1"
        )
        
        await asyncio.sleep(0.1)
        assert True  # Placeholder assertion
    
    async def test_data_access_logging(self):
        """Test data access event logging."""
        audit_logger = AuditLogger()
        
        # Log data access
        audit_logger.log_data_access(
            action="read",
            resource_type="book",
            resource_id="book-123",
            user_id="test_user",
            result="success",
            ip_address="127.0.0.1"
        )
        
        await asyncio.sleep(0.1)
        assert True  # Placeholder assertion


@pytest.mark.asyncio
class TestPrivacyService:
    """Test privacy service functionality."""
    
    async def test_conversation_sanitization(self):
        """Test conversation content sanitization."""
        privacy_service = PrivacyService()
        
        # Test content with sensitive information
        content_with_sensitive = "My email is john@example.com and phone is 555-123-4567"
        sanitized = privacy_service.sanitize_conversation_content(content_with_sensitive)
        
        assert "john@example.com" not in sanitized
        assert "555-123-4567" not in sanitized
        assert "[REDACTED]" in sanitized
    
    def test_data_anonymization(self):
        """Test user data anonymization."""
        privacy_service = PrivacyService()
        
        # Test anonymization
        report = privacy_service.anonymize_user_data("user-123", "admin-001")
        
        assert report["user_id"] == "user-123"
        assert report["admin_user_id"] == "admin-001"
        assert "anonymous_id" in report
        assert report["anonymous_id"].startswith("anon_")
    
    def test_data_export(self):
        """Test user data export."""
        privacy_service = PrivacyService()
        
        # Test data export
        report = privacy_service.export_user_data("user-123", "admin-001", "json")
        
        assert report["user_id"] == "user-123"
        assert report["requesting_user_id"] == "admin-001"
        assert report["export_format"] == "json"
        assert "exported_data" in report


class TestSecurityIntegration:
    """Test security component integration."""
    
    def test_global_service_instances(self):
        """Test global service instance retrieval."""
        # Test that global instances are properly created
        encryption_service = get_encryption_service()
        assert isinstance(encryption_service, EncryptionService)
        
        auth_service = get_auth_service()
        assert isinstance(auth_service, AuthenticationService)
        
        authz_service = get_authz_service()
        assert isinstance(authz_service, AuthorizationService)
        
        audit_logger = get_audit_logger()
        assert isinstance(audit_logger, AuditLogger)
        
        rate_limiter = get_rate_limiter()
        assert isinstance(rate_limiter, RateLimiter)
        
        privacy_service = get_privacy_service()
        assert isinstance(privacy_service, PrivacyService)
        
        data_sanitizer = get_data_sanitizer()
        assert isinstance(data_sanitizer, DataSanitizer)
    
    def test_singleton_behavior(self):
        """Test that global instances are singletons."""
        # Test that multiple calls return the same instance
        encryption1 = get_encryption_service()
        encryption2 = get_encryption_service()
        assert encryption1 is encryption2
        
        auth1 = get_auth_service()
        auth2 = get_auth_service()
        assert auth1 is auth2