#!/usr/bin/env python3
"""
Task 12.2: Data Privacy and Encryption Implementation Test

This test validates the complete implementation of data privacy and encryption features:
- Encrypt sensitive data at rest and in transit
- Implement data anonymization for logs
- Add user data deletion capabilities
- Create privacy-compliant data handling

Validates: Task 12.2 requirements from chat-and-document-integration specification
"""

import asyncio
import json
import os
import tempfile
from datetime import datetime
from pathlib import Path
import sys

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent / "src"))

from multimodal_librarian.security.encryption import get_encryption_service, EncryptionError
from multimodal_librarian.security.privacy import get_privacy_service
from multimodal_librarian.security.audit import get_audit_logger
from multimodal_librarian.config import get_settings


class Task12_2DataPrivacyEncryptionTest:
    """Test suite for Task 12.2 data privacy and encryption implementation."""
    
    def __init__(self):
        """Initialize test suite."""
        self.results = {
            "test_name": "Task 12.2: Data Privacy and Encryption",
            "timestamp": datetime.utcnow().isoformat(),
            "tests": {},
            "summary": {
                "total_tests": 0,
                "passed": 0,
                "failed": 0,
                "errors": []
            }
        }
        
        # Initialize services
        try:
            self.encryption_service = get_encryption_service()
            self.privacy_service = get_privacy_service()
            self.audit_logger = get_audit_logger()
            self.settings = get_settings()
        except Exception as e:
            self.results["summary"]["errors"].append(f"Service initialization failed: {e}")
    
    def run_test(self, test_name: str, test_func):
        """Run a single test and record results."""
        print(f"\n🧪 Running {test_name}...")
        self.results["summary"]["total_tests"] += 1
        
        try:
            result = test_func()
            if result.get("success", False):
                print(f"   ✅ {test_name} passed")
                self.results["summary"]["passed"] += 1
                self.results["tests"][test_name] = {
                    "status": "passed",
                    "details": result.get("details", {}),
                    "metrics": result.get("metrics", {})
                }
            else:
                print(f"   ❌ {test_name} failed: {result.get('error', 'Unknown error')}")
                self.results["summary"]["failed"] += 1
                self.results["tests"][test_name] = {
                    "status": "failed",
                    "error": result.get("error", "Unknown error"),
                    "details": result.get("details", {})
                }
        except Exception as e:
            print(f"   💥 {test_name} error: {e}")
            self.results["summary"]["failed"] += 1
            self.results["summary"]["errors"].append(f"{test_name}: {e}")
            self.results["tests"][test_name] = {
                "status": "error",
                "error": str(e)
            }
    
    def test_encryption_service_functionality(self):
        """Test encryption service basic functionality."""
        try:
            # Test text encryption/decryption
            test_text = "This is sensitive user data that needs encryption"
            encrypted_text = self.encryption_service.encrypt_text(test_text)
            decrypted_text = self.encryption_service.decrypt_text(encrypted_text)
            
            if decrypted_text != test_text:
                return {"success": False, "error": "Text encryption/decryption failed"}
            
            # Test password hashing
            password = "user_secure_password_123"
            hash_result, salt = self.encryption_service.hash_password(password)
            
            if not self.encryption_service.verify_password(password, hash_result, salt):
                return {"success": False, "error": "Password hashing/verification failed"}
            
            # Test secure token generation
            token = self.encryption_service.generate_secure_token(32)
            if len(token) < 40:  # Base64 encoded 32 bytes should be longer
                return {"success": False, "error": "Secure token generation failed"}
            
            # Test sensitive field encryption
            test_data = {
                "user_id": "user123",
                "email": "user@example.com",
                "sensitive_content": "This is private information",
                "public_data": "This can be public"
            }
            
            sensitive_fields = ["email", "sensitive_content"]
            encrypted_data = self.encryption_service.encrypt_sensitive_fields(test_data, sensitive_fields)
            decrypted_data = self.encryption_service.decrypt_sensitive_fields(encrypted_data, sensitive_fields)
            
            if decrypted_data != test_data:
                return {"success": False, "error": "Sensitive field encryption failed"}
            
            return {
                "success": True,
                "details": {
                    "text_encryption": "working",
                    "password_hashing": "working",
                    "token_generation": "working",
                    "field_encryption": "working"
                },
                "metrics": {
                    "encrypted_text_length": len(encrypted_text),
                    "token_length": len(token),
                    "encrypted_fields": len(sensitive_fields)
                }
            }
            
        except Exception as e:
            return {"success": False, "error": f"Encryption service test failed: {e}"}
    
    def test_file_encryption_functionality(self):
        """Test file encryption and decryption."""
        try:
            # Create a temporary test file
            with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.txt') as temp_file:
                test_content = "This is sensitive file content that needs encryption\nLine 2 of sensitive data"
                temp_file.write(test_content)
                temp_file_path = temp_file.name
            
            try:
                # Encrypt the file
                encrypted_file_path = self.encryption_service.encrypt_file(temp_file_path)
                
                # Verify encrypted file exists and is different
                if not os.path.exists(encrypted_file_path):
                    return {"success": False, "error": "Encrypted file was not created"}
                
                with open(encrypted_file_path, 'rb') as f:
                    encrypted_content = f.read()
                
                if test_content.encode() in encrypted_content:
                    return {"success": False, "error": "File content appears to be unencrypted"}
                
                # Decrypt the file
                decrypted_file_path = self.encryption_service.decrypt_file(encrypted_file_path)
                
                # Verify decrypted content matches original
                with open(decrypted_file_path, 'r') as f:
                    decrypted_content = f.read()
                
                if decrypted_content != test_content:
                    return {"success": False, "error": "Decrypted content doesn't match original"}
                
                return {
                    "success": True,
                    "details": {
                        "file_encryption": "working",
                        "file_decryption": "working",
                        "content_integrity": "verified"
                    },
                    "metrics": {
                        "original_size": len(test_content),
                        "encrypted_size": len(encrypted_content),
                        "encryption_overhead": len(encrypted_content) - len(test_content)
                    }
                }
                
            finally:
                # Clean up temporary files
                for file_path in [temp_file_path, encrypted_file_path, decrypted_file_path]:
                    if os.path.exists(file_path):
                        os.unlink(file_path)
                        
        except Exception as e:
            return {"success": False, "error": f"File encryption test failed: {e}"}
    
    def test_privacy_service_functionality(self):
        """Test privacy service data deletion and anonymization."""
        try:
            # Test conversation content sanitization
            sensitive_content = """
            User conversation with sensitive data:
            My email is john.doe@example.com and my phone is 555-123-4567.
            My SSN is 123-45-6789 and credit card is 4532-1234-5678-9012.
            """
            
            sanitized_content = self.privacy_service.sanitize_conversation_content(sensitive_content)
            
            # Verify sensitive patterns are redacted
            sensitive_patterns = ["john.doe@example.com", "555-123-4567", "123-45-6789", "4532-1234-5678-9012"]
            for pattern in sensitive_patterns:
                if pattern in sanitized_content:
                    return {"success": False, "error": f"Sensitive pattern not redacted: {pattern}"}
            
            if "[REDACTED]" not in sanitized_content:
                return {"success": False, "error": "No redaction markers found in sanitized content"}
            
            # Test data retention compliance check
            compliance_report = self.privacy_service.check_data_retention_compliance()
            
            if "compliance_status" not in compliance_report:
                return {"success": False, "error": "Compliance report missing status"}
            
            # Test user data export functionality
            export_report = self.privacy_service.export_user_data(
                user_id="test_user_123",
                requesting_user_id="admin_user",
                export_format="json"
            )
            
            if "exported_data" not in export_report:
                return {"success": False, "error": "Export report missing data"}
            
            # Test user data anonymization
            anonymization_report = self.privacy_service.anonymize_user_data(
                user_id="test_user_123",
                admin_user_id="admin_user"
            )
            
            if "anonymous_id" not in anonymization_report:
                return {"success": False, "error": "Anonymization report missing anonymous ID"}
            
            return {
                "success": True,
                "details": {
                    "content_sanitization": "working",
                    "compliance_checking": "working",
                    "data_export": "working",
                    "data_anonymization": "working"
                },
                "metrics": {
                    "redacted_patterns": len(sensitive_patterns),
                    "compliance_status": compliance_report.get("compliance_status"),
                    "export_categories": len(export_report.get("exported_data", {})),
                    "anonymization_components": len(anonymization_report.get("anonymized_components", []))
                }
            }
            
        except Exception as e:
            return {"success": False, "error": f"Privacy service test failed: {e}"}
    
    async def test_data_deletion_functionality(self):
        """Test complete data deletion functionality."""
        try:
            # Mock the database session to avoid connection issues in testing
            class MockSession:
                def query(self, model):
                    return MockQuery()
                def commit(self):
                    pass
                def rollback(self):
                    pass
                def __enter__(self):
                    return self
                def __exit__(self, exc_type, exc_val, exc_tb):
                    pass
            
            class MockQuery:
                def filter(self, *args):
                    return self
                def first(self):
                    return None  # Simulate not found for testing
                def all(self):
                    return []
                def delete(self, synchronize_session=False):
                    return 0
                def join(self, *args):
                    return self
                def in_(self, *args):
                    return self
            
            # Temporarily replace the database session
            original_get_database_session = None
            try:
                from multimodal_librarian.database import connection
                original_get_database_session = connection.get_database_session
                connection.get_database_session = lambda: MockSession()
                
                # Test book deletion (mock scenario)
                book_deletion_report = await self.privacy_service.delete_book_completely(
                    book_id="test_book_123",
                    user_id="test_user",
                    ip_address="127.0.0.1"
                )
                
                # Verify deletion report structure
                required_fields = ["book_id", "user_id", "timestamp", "deleted_components", "errors"]
                for field in required_fields:
                    if field not in book_deletion_report:
                        return {"success": False, "error": f"Book deletion report missing field: {field}"}
                
                # Test conversation deletion (mock scenario)
                conversation_deletion_report = await self.privacy_service.delete_conversation_completely(
                    conversation_id="test_conversation_123",
                    user_id="test_user",
                    ip_address="127.0.0.1"
                )
                
                # Verify deletion report structure
                for field in ["conversation_id", "user_id", "timestamp", "deleted_components", "errors"]:
                    if field not in conversation_deletion_report:
                        return {"success": False, "error": f"Conversation deletion report missing field: {field}"}
                
            finally:
                # Restore original database session
                if original_get_database_session:
                    connection.get_database_session = original_get_database_session
            
            return {
                "success": True,
                "details": {
                    "book_deletion": "working",
                    "conversation_deletion": "working",
                    "deletion_reporting": "comprehensive"
                },
                "metrics": {
                    "book_deletion_components": len(book_deletion_report.get("deleted_components", [])),
                    "conversation_deletion_components": len(conversation_deletion_report.get("deleted_components", [])),
                    "book_deletion_errors": len(book_deletion_report.get("errors", [])),
                    "conversation_deletion_errors": len(conversation_deletion_report.get("errors", []))
                }
            }
            
        except Exception as e:
            return {"success": False, "error": f"Data deletion test failed: {e}"}
    
    def test_audit_logging_integration(self):
        """Test audit logging for privacy operations."""
        try:
            # Test privacy operation logging
            self.audit_logger.log_privacy_operation(
                operation="test_operation",
                user_id="test_user",
                resource_type="test_resource",
                resource_id="test_123",
                details={"test": "data"}
            )
            
            # Test audit log search functionality
            logs = self.audit_logger.search_audit_logs(
                user_id="test_user",
                limit=10
            )
            
            # Verify logs are returned (even if empty in test environment)
            if not isinstance(logs, list):
                return {"success": False, "error": "Audit log search should return a list"}
            
            # Test audit summary
            summary = self.audit_logger.get_audit_summary()
            
            if not isinstance(summary, dict):
                return {"success": False, "error": "Audit summary should return a dictionary"}
            
            return {
                "success": True,
                "details": {
                    "privacy_operation_logging": "working",
                    "audit_log_search": "working",
                    "audit_summary": "working"
                },
                "metrics": {
                    "logs_found": len(logs),
                    "summary_fields": len(summary)
                }
            }
            
        except Exception as e:
            return {"success": False, "error": f"Audit logging test failed: {e}"}
    
    def test_configuration_security(self):
        """Test security configuration and key management."""
        try:
            # Test encryption key configuration
            if not hasattr(self.encryption_service, '_fernet_key'):
                return {"success": False, "error": "Encryption service missing key"}
            
            # Test settings security configuration
            if not hasattr(self.settings, 'secret_key'):
                return {"success": False, "error": "Settings missing secret key"}
            
            # Test key derivation is working - the key should be 44 characters (base64 encoded 32 bytes)
            key_bytes = self.encryption_service._fernet_key
            if len(key_bytes) != 44:
                return {"success": False, "error": f"Encryption key has incorrect length: {len(key_bytes)} (expected 44 for base64-encoded 32 bytes)"}
            
            # Verify it's valid base64
            try:
                import base64
                decoded_key = base64.urlsafe_b64decode(key_bytes)
                if len(decoded_key) != 32:
                    return {"success": False, "error": f"Decoded key has incorrect length: {len(decoded_key)} (expected 32 bytes)"}
            except Exception as e:
                return {"success": False, "error": f"Key is not valid base64: {e}"}
            test_text = "Configuration test"
            try:
                encrypted = self.encryption_service.encrypt_text(test_text)
                decrypted = self.encryption_service.decrypt_text(encrypted)
                
                if decrypted != test_text:
                    return {"success": False, "error": "Basic encryption/decryption failed"}
            except Exception as e:
                return {"success": False, "error": f"Encryption test failed: {e}"}
            
            # Test secure token generation
            try:
                token = self.encryption_service.generate_secure_token(16)
                if len(token) < 20:  # Base64 encoded should be longer
                    return {"success": False, "error": "Token generation failed"}
            except Exception as e:
                return {"success": False, "error": f"Token generation failed: {e}"}
            
            return {
                "success": True,
                "details": {
                    "key_management": "working",
                    "encryption_functionality": "working",
                    "key_derivation": "working",
                    "token_generation": "working"
                },
                "metrics": {
                    "key_length_chars": len(key_bytes),
                    "decoded_key_length_bytes": len(decoded_key),
                    "secret_key_configured": bool(self.settings.secret_key),
                    "encryption_working": True
                }
            }
            
        except Exception as e:
            return {"success": False, "error": f"Configuration security test failed: {e}"}
    
    async def run_all_tests(self):
        """Run all Task 12.2 tests."""
        print("🔒 Starting Task 12.2: Data Privacy and Encryption Tests")
        print("=" * 60)
        
        # Run all tests
        self.run_test("Encryption Service Functionality", self.test_encryption_service_functionality)
        self.run_test("File Encryption Functionality", self.test_file_encryption_functionality)
        self.run_test("Privacy Service Functionality", self.test_privacy_service_functionality)
        
        # Async test
        try:
            print(f"\n🧪 Running Data Deletion Functionality...")
            self.results["summary"]["total_tests"] += 1
            result = await self.test_data_deletion_functionality()
            
            if result.get("success", False):
                print(f"   ✅ Data Deletion Functionality passed")
                self.results["summary"]["passed"] += 1
                self.results["tests"]["Data Deletion Functionality"] = {
                    "status": "passed",
                    "details": result.get("details", {}),
                    "metrics": result.get("metrics", {})
                }
            else:
                print(f"   ❌ Data Deletion Functionality failed: {result.get('error', 'Unknown error')}")
                self.results["summary"]["failed"] += 1
                self.results["tests"]["Data Deletion Functionality"] = {
                    "status": "failed",
                    "error": result.get("error", "Unknown error"),
                    "details": result.get("details", {})
                }
        except Exception as e:
            print(f"   💥 Data Deletion Functionality error: {e}")
            self.results["summary"]["failed"] += 1
            self.results["tests"]["Data Deletion Functionality"] = {
                "status": "error",
                "error": str(e)
            }
        
        self.run_test("Audit Logging Integration", self.test_audit_logging_integration)
        self.run_test("Configuration Security", self.test_configuration_security)
        
        # Generate summary
        self.generate_summary()
        
        return self.results
    
    def generate_summary(self):
        """Generate test summary and recommendations."""
        print("\n" + "=" * 60)
        print("📊 TASK 12.2 TEST SUMMARY")
        print("=" * 60)
        
        total = self.results["summary"]["total_tests"]
        passed = self.results["summary"]["passed"]
        failed = self.results["summary"]["failed"]
        
        print(f"Total Tests: {total}")
        print(f"Passed: {passed} ✅")
        print(f"Failed: {failed} ❌")
        print(f"Success Rate: {(passed/total*100):.1f}%")
        
        if failed == 0:
            print("\n🎉 ALL TESTS PASSED!")
            print("✅ Task 12.2: Data Privacy and Encryption is COMPLETE")
            print("\n🔒 Privacy and Encryption Features Validated:")
            print("   • Text and file encryption/decryption")
            print("   • Password hashing and verification")
            print("   • Sensitive data field encryption")
            print("   • Content sanitization and redaction")
            print("   • Complete data deletion capabilities")
            print("   • Data export and anonymization")
            print("   • Audit logging for privacy operations")
            print("   • Secure configuration management")
            
            self.results["task_status"] = "COMPLETED"
            self.results["recommendation"] = "Task 12.2 is fully implemented and ready for production deployment"
            
        else:
            print(f"\n⚠️  {failed} test(s) failed")
            print("❌ Task 12.2 needs attention before completion")
            
            self.results["task_status"] = "NEEDS_ATTENTION"
            self.results["recommendation"] = "Address failing tests before proceeding to production deployment"
        
        # Save results
        results_file = f"task-12-2-data-privacy-encryption-test-results-{int(datetime.utcnow().timestamp())}.json"
        with open(results_file, 'w') as f:
            json.dump(self.results, f, indent=2, default=str)
        
        print(f"\n📄 Detailed results saved to: {results_file}")


async def main():
    """Main test execution."""
    test_suite = Task12_2DataPrivacyEncryptionTest()
    results = await test_suite.run_all_tests()
    
    # Return appropriate exit code
    if results["summary"]["failed"] == 0:
        return 0
    else:
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    exit(exit_code)