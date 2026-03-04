#!/usr/bin/env python3
"""
Test script for Task 3: Document Upload and Management System

This script validates the document upload and management functionality
including API endpoints, database operations, and file handling.
"""

import asyncio
import sys
import os
import json
import tempfile
import logging
from pathlib import Path
from typing import Dict, Any, List

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root / "src"))

from multimodal_librarian.services.upload_service import UploadService, ValidationError, UploadError
from multimodal_librarian.services.storage_service import StorageService, StorageError
from multimodal_librarian.models.documents import DocumentUploadRequest, DocumentStatus, DocumentSearchRequest
from multimodal_librarian.database.migrations.add_documents_table import apply_migration, check_migration_status

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


class Task3Tester:
    """Test suite for Task 3 document upload and management system."""
    
    def __init__(self):
        self.upload_service = None
        self.storage_service = None
        self.test_results = []
        self.test_document_ids = []
    
    async def run_all_tests(self) -> Dict[str, Any]:
        """Run all Task 3 tests and return results."""
        logger.info("🧪 Starting Task 3 implementation tests...")
        
        try:
            # Initialize services
            await self.setup_services()
            
            # Run test suite
            await self.test_database_migration()
            await self.test_storage_service()
            await self.test_upload_service()
            await self.test_document_management()
            await self.test_file_validation()
            await self.test_search_and_filtering()
            await self.test_statistics()
            
            # Cleanup
            await self.cleanup_test_data()
            
            # Generate report
            return self.generate_test_report()
            
        except Exception as e:
            logger.error(f"Test suite failed: {e}")
            return {
                "success": False,
                "error": str(e),
                "tests_run": len(self.test_results),
                "results": self.test_results
            }
    
    async def setup_services(self):
        """Initialize services for testing."""
        logger.info("Setting up services...")
        
        try:
            self.storage_service = StorageService()
            self.upload_service = UploadService(self.storage_service)
            
            self.add_test_result("service_initialization", True, "Services initialized successfully")
            
        except Exception as e:
            self.add_test_result("service_initialization", False, f"Service initialization failed: {e}")
            raise
    
    async def test_database_migration(self):
        """Test database migration for documents tables."""
        logger.info("Testing database migration...")
        
        try:
            # Check if migration is applied
            migration_status = await check_migration_status()
            
            if not migration_status:
                # Apply migration
                success = await apply_migration()
                if not success:
                    raise Exception("Migration application failed")
            
            # Verify tables exist
            migration_status = await check_migration_status()
            
            if migration_status:
                self.add_test_result("database_migration", True, "Documents tables exist and migration is applied")
            else:
                self.add_test_result("database_migration", False, "Migration verification failed")
                
        except Exception as e:
            self.add_test_result("database_migration", False, f"Database migration test failed: {e}")
    
    async def test_storage_service(self):
        """Test S3 storage service functionality."""
        logger.info("Testing storage service...")
        
        try:
            # Test health check
            health = self.storage_service.health_check()
            
            if health['status'] == 'healthy':
                self.add_test_result("storage_health", True, f"Storage service healthy - Bucket: {health['bucket_name']}")
            else:
                self.add_test_result("storage_health", False, f"Storage service unhealthy: {health.get('error', 'Unknown')}")
            
            # Test file validation
            test_pdf_content = b'%PDF-1.4\n1 0 obj\n<<\n/Type /Catalog\n/Pages 2 0 R\n>>\nendobj\n'
            
            is_valid, error_msg = self.storage_service.validate_file(test_pdf_content, "test.pdf")
            
            if is_valid:
                self.add_test_result("file_validation", True, "PDF file validation working")
            else:
                self.add_test_result("file_validation", False, f"File validation failed: {error_msg}")
            
            # Test invalid file validation
            is_valid, error_msg = self.storage_service.validate_file(b'not a pdf', "test.txt")
            
            if not is_valid:
                self.add_test_result("invalid_file_validation", True, "Invalid file rejection working")
            else:
                self.add_test_result("invalid_file_validation", False, "Invalid file validation failed")
                
        except Exception as e:
            self.add_test_result("storage_service", False, f"Storage service test failed: {e}")
    
    async def test_upload_service(self):
        """Test document upload service functionality."""
        logger.info("Testing upload service...")
        
        try:
            # Create test PDF content
            test_pdf_content = self.create_test_pdf_content()
            
            # Test document upload
            upload_request = DocumentUploadRequest(
                title="Test Document",
                description="Test document for Task 3 validation"
            )
            
            result = await self.upload_service.upload_document(
                file_data=test_pdf_content,
                filename="test_document.pdf",
                upload_request=upload_request,
                user_id="test_user"
            )
            
            if result and result.document_id:
                self.test_document_ids.append(result.document_id)
                self.add_test_result("document_upload", True, f"Document uploaded successfully: {result.document_id}")
                
                # Test document retrieval
                from uuid import UUID
                document = await self.upload_service.get_document(UUID(result.document_id))
                
                if document:
                    self.add_test_result("document_retrieval", True, f"Document retrieved successfully: {document.title}")
                else:
                    self.add_test_result("document_retrieval", False, "Document retrieval failed")
            else:
                self.add_test_result("document_upload", False, "Document upload failed")
                
        except Exception as e:
            self.add_test_result("upload_service", False, f"Upload service test failed: {e}")
    
    async def test_document_management(self):
        """Test document management operations."""
        logger.info("Testing document management...")
        
        try:
            if not self.test_document_ids:
                self.add_test_result("document_management", False, "No test documents available")
                return
            
            from uuid import UUID
            test_doc_id = UUID(self.test_document_ids[0])
            
            # Test status update
            success = await self.upload_service.update_document_status(
                test_doc_id, 
                DocumentStatus.PROCESSING
            )
            
            if success:
                self.add_test_result("status_update", True, "Document status update working")
            else:
                self.add_test_result("status_update", False, "Document status update failed")
            
            # Test document content retrieval
            content = await self.upload_service.get_document_content(test_doc_id)
            
            if content and len(content) > 0:
                self.add_test_result("content_retrieval", True, f"Document content retrieved: {len(content)} bytes")
            else:
                self.add_test_result("content_retrieval", False, "Document content retrieval failed")
                
        except Exception as e:
            self.add_test_result("document_management", False, f"Document management test failed: {e}")
    
    async def test_file_validation(self):
        """Test file validation functionality."""
        logger.info("Testing file validation...")
        
        try:
            # Test oversized file
            large_content = b'%PDF-1.4\n' + b'x' * (101 * 1024 * 1024)  # 101MB
            
            try:
                upload_request = DocumentUploadRequest(title="Large Test")
                await self.upload_service.upload_document(
                    file_data=large_content,
                    filename="large_test.pdf",
                    upload_request=upload_request
                )
                self.add_test_result("file_size_validation", False, "Large file validation failed - should have been rejected")
            except ValidationError:
                self.add_test_result("file_size_validation", True, "Large file correctly rejected")
            
            # Test invalid file type
            try:
                upload_request = DocumentUploadRequest(title="Invalid Test")
                await self.upload_service.upload_document(
                    file_data=b'not a pdf',
                    filename="invalid.txt",
                    upload_request=upload_request
                )
                self.add_test_result("file_type_validation", False, "Invalid file type validation failed")
            except ValidationError:
                self.add_test_result("file_type_validation", True, "Invalid file type correctly rejected")
                
        except Exception as e:
            self.add_test_result("file_validation", False, f"File validation test failed: {e}")
    
    async def test_search_and_filtering(self):
        """Test document search and filtering functionality."""
        logger.info("Testing search and filtering...")
        
        try:
            # Create search request
            search_request = DocumentSearchRequest(
                query="Test",
                page=1,
                page_size=10
            )
            
            # Test document listing
            result = await self.upload_service.list_documents(search_request, user_id="test_user")
            
            if result:
                self.add_test_result("document_listing", True, f"Document listing working - Found {result.total_count} documents")
                
                # Test search functionality
                if result.total_count > 0 and any("Test" in doc.title for doc in result.documents):
                    self.add_test_result("document_search", True, "Document search functionality working")
                else:
                    self.add_test_result("document_search", False, "Document search not finding expected results")
            else:
                self.add_test_result("document_listing", False, "Document listing failed")
                
        except Exception as e:
            self.add_test_result("search_filtering", False, f"Search and filtering test failed: {e}")
    
    async def test_statistics(self):
        """Test statistics functionality."""
        logger.info("Testing statistics...")
        
        try:
            stats = await self.upload_service.get_upload_statistics()
            
            if stats and 'total_documents' in stats:
                self.add_test_result("statistics", True, f"Statistics working - Total docs: {stats['total_documents']}")
            else:
                self.add_test_result("statistics", False, "Statistics retrieval failed")
                
        except Exception as e:
            self.add_test_result("statistics", False, f"Statistics test failed: {e}")
    
    async def cleanup_test_data(self):
        """Clean up test documents."""
        logger.info("Cleaning up test data...")
        
        try:
            from uuid import UUID
            for doc_id in self.test_document_ids:
                try:
                    await self.upload_service.delete_document(UUID(doc_id))
                    logger.info(f"Cleaned up test document: {doc_id}")
                except Exception as e:
                    logger.warning(f"Failed to cleanup document {doc_id}: {e}")
            
            self.add_test_result("cleanup", True, f"Cleaned up {len(self.test_document_ids)} test documents")
            
        except Exception as e:
            self.add_test_result("cleanup", False, f"Cleanup failed: {e}")
    
    def create_test_pdf_content(self) -> bytes:
        """Create minimal valid PDF content for testing."""
        return b"""%PDF-1.4
1 0 obj
<<
/Type /Catalog
/Pages 2 0 R
>>
endobj

2 0 obj
<<
/Type /Pages
/Kids [3 0 R]
/Count 1
>>
endobj

3 0 obj
<<
/Type /Page
/Parent 2 0 R
/MediaBox [0 0 612 792]
/Contents 4 0 R
>>
endobj

4 0 obj
<<
/Length 44
>>
stream
BT
/F1 12 Tf
100 700 Td
(Test Document) Tj
ET
endstream
endobj

xref
0 5
0000000000 65535 f 
0000000009 00000 n 
0000000058 00000 n 
0000000115 00000 n 
0000000206 00000 n 
trailer
<<
/Size 5
/Root 1 0 R
>>
startxref
300
%%EOF"""
    
    def add_test_result(self, test_name: str, success: bool, message: str):
        """Add a test result to the results list."""
        result = {
            "test": test_name,
            "success": success,
            "message": message
        }
        self.test_results.append(result)
        
        status = "✅" if success else "❌"
        logger.info(f"{status} {test_name}: {message}")
    
    def generate_test_report(self) -> Dict[str, Any]:
        """Generate comprehensive test report."""
        total_tests = len(self.test_results)
        passed_tests = sum(1 for result in self.test_results if result["success"])
        failed_tests = total_tests - passed_tests
        
        success_rate = (passed_tests / total_tests * 100) if total_tests > 0 else 0
        
        return {
            "success": failed_tests == 0,
            "total_tests": total_tests,
            "passed_tests": passed_tests,
            "failed_tests": failed_tests,
            "success_rate": round(success_rate, 2),
            "results": self.test_results
        }


async def main():
    """Main test execution function."""
    print("🧪 Task 3 Implementation Test Suite")
    print("=" * 50)
    
    tester = Task3Tester()
    report = await tester.run_all_tests()
    
    print("\n📊 Test Report")
    print("=" * 50)
    print(f"Total Tests: {report['total_tests']}")
    print(f"Passed: {report['passed_tests']}")
    print(f"Failed: {report['failed_tests']}")
    print(f"Success Rate: {report['success_rate']}%")
    
    if report['success']:
        print("\n🎉 All tests passed! Task 3 implementation is working correctly.")
        return 0
    else:
        print("\n❌ Some tests failed. Please review the results above.")
        
        # Print failed tests
        failed_tests = [r for r in report['results'] if not r['success']]
        if failed_tests:
            print("\nFailed Tests:")
            for test in failed_tests:
                print(f"  • {test['test']}: {test['message']}")
        
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)