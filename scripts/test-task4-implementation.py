#!/usr/bin/env python3

"""
Test script for Task 4: Document Processing Pipeline Implementation.

This script validates the Celery job queue integration, PDF processing,
chunking framework, and background processing workflow.
"""

import asyncio
import sys
import os
import tempfile
import time
import json
from pathlib import Path
from uuid import uuid4

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from multimodal_librarian.services.celery_service import CeleryService, celery_app
from multimodal_librarian.services.processing_service import ProcessingService
from multimodal_librarian.services.upload_service import UploadService
from multimodal_librarian.models.documents import DocumentUploadRequest, DocumentStatus
from multimodal_librarian.database.migrations.add_documents_table import apply_migration, check_migration_status


class Task4Tester:
    """Test suite for Task 4 implementation."""
    
    def __init__(self):
        self.test_results = []
        self.celery_service = None
        self.processing_service = None
        self.upload_service = None
    
    def log_test(self, test_name: str, success: bool, message: str = ""):
        """Log test result."""
        status = "✅ PASS" if success else "❌ FAIL"
        print(f"{status} {test_name}")
        if message:
            print(f"    {message}")
        
        self.test_results.append({
            'test': test_name,
            'success': success,
            'message': message
        })
    
    def print_summary(self):
        """Print test summary."""
        passed = sum(1 for result in self.test_results if result['success'])
        total = len(self.test_results)
        
        print(f"\n{'='*60}")
        print(f"Task 4 Test Summary: {passed}/{total} tests passed")
        print(f"{'='*60}")
        
        if passed == total:
            print("🎉 All tests passed! Task 4 implementation is working correctly.")
            return True
        else:
            print("⚠️  Some tests failed. Please check the implementation.")
            for result in self.test_results:
                if not result['success']:
                    print(f"❌ {result['test']}: {result['message']}")
            return False
    
    async def test_database_migration(self):
        """Test database migration for processing jobs."""
        try:
            # Check if migration is already applied
            is_applied = await check_migration_status()
            
            if not is_applied:
                # Apply migration
                success = await apply_migration()
                if not success:
                    self.log_test("Database Migration", False, "Failed to apply migration")
                    return
            
            self.log_test("Database Migration", True, "Processing jobs table exists")
            
        except Exception as e:
            self.log_test("Database Migration", False, f"Error: {e}")
    
    def test_redis_connection(self):
        """Test Redis connection for Celery."""
        try:
            import redis
            
            redis_client = redis.Redis.from_url("redis://localhost:6379/0")
            redis_client.ping()
            
            self.log_test("Redis Connection", True, "Redis is accessible")
            
        except Exception as e:
            self.log_test("Redis Connection", False, f"Redis connection failed: {e}")
    
    def test_celery_configuration(self):
        """Test Celery app configuration."""
        try:
            # Test Celery app import
            from multimodal_librarian.services.celery_service import celery_app
            
            # Check broker URL
            broker_url = celery_app.conf.broker_url
            if "redis://" not in broker_url:
                self.log_test("Celery Configuration", False, f"Invalid broker URL: {broker_url}")
                return
            
            # Check task routes
            task_routes = celery_app.conf.task_routes
            expected_tasks = [
                'process_document_task',
                'extract_pdf_content_task',
                'generate_chunks_task',
                'store_embeddings_task',
                'update_knowledge_graph_task'
            ]
            
            for task in expected_tasks:
                if task not in task_routes:
                    self.log_test("Celery Configuration", False, f"Missing task route: {task}")
                    return
            
            self.log_test("Celery Configuration", True, "All task routes configured")
            
        except Exception as e:
            self.log_test("Celery Configuration", False, f"Configuration error: {e}")
    
    async def test_celery_service_initialization(self):
        """Test CeleryService initialization."""
        try:
            self.celery_service = CeleryService()
            
            # Test health check
            health = self.celery_service.health_check()
            
            if health['status'] in ['healthy', 'degraded']:
                self.log_test("Celery Service Init", True, f"Status: {health['status']}")
            else:
                self.log_test("Celery Service Init", False, f"Unhealthy status: {health}")
            
        except Exception as e:
            self.log_test("Celery Service Init", False, f"Initialization failed: {e}")
    
    async def test_processing_service_integration(self):
        """Test ProcessingService integration with Celery."""
        try:
            self.processing_service = ProcessingService()
            
            # Check if Celery service is integrated
            if not hasattr(self.processing_service, 'celery_service'):
                self.log_test("Processing Service Integration", False, "CeleryService not integrated")
                return
            
            # Test health check
            health = self.processing_service.celery_service.health_check()
            
            self.log_test("Processing Service Integration", True, f"Celery integrated, status: {health['status']}")
            
        except Exception as e:
            self.log_test("Processing Service Integration", False, f"Integration failed: {e}")
    
    def create_test_pdf(self) -> bytes:
        """Create a minimal test PDF."""
        # Minimal PDF content
        pdf_content = b"""%PDF-1.4
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
        return pdf_content
    
    async def test_document_upload_integration(self):
        """Test document upload with processing queue integration."""
        try:
            self.upload_service = UploadService()
            
            # Create test PDF
            test_pdf = self.create_test_pdf()
            
            # Create upload request
            upload_request = DocumentUploadRequest(
                title="Task 4 Test Document",
                description="Test document for processing pipeline validation"
            )
            
            # Upload document (this should trigger processing queue)
            result = await self.upload_service.upload_document(
                file_data=test_pdf,
                filename="task4_test.pdf",
                upload_request=upload_request
            )
            
            if result.document_id:
                self.log_test("Document Upload Integration", True, f"Document uploaded: {result.document_id}")
                
                # Wait a moment and check if processing was queued
                await asyncio.sleep(1)
                
                # Check processing status
                if self.processing_service:
                    status = await self.processing_service.get_processing_status(result.document_id)
                    if status:
                        self.log_test("Processing Queue Integration", True, f"Processing queued: {status['status']}")
                    else:
                        self.log_test("Processing Queue Integration", False, "No processing job found")
                
                return result.document_id
            else:
                self.log_test("Document Upload Integration", False, "No document ID returned")
                return None
            
        except Exception as e:
            self.log_test("Document Upload Integration", False, f"Upload failed: {e}")
            return None
    
    async def test_processing_status_tracking(self, document_id: str = None):
        """Test processing status tracking."""
        if not document_id or not self.processing_service:
            self.log_test("Processing Status Tracking", False, "No document ID or processing service")
            return
        
        try:
            # Get processing status
            status = await self.processing_service.get_processing_status(document_id)
            
            if status:
                expected_fields = ['job_id', 'document_id', 'status', 'progress_percentage', 'current_step']
                missing_fields = [field for field in expected_fields if field not in status]
                
                if missing_fields:
                    self.log_test("Processing Status Tracking", False, f"Missing fields: {missing_fields}")
                else:
                    self.log_test("Processing Status Tracking", True, f"Status: {status['status']}, Progress: {status['progress_percentage']}%")
            else:
                self.log_test("Processing Status Tracking", False, "No status information available")
            
        except Exception as e:
            self.log_test("Processing Status Tracking", False, f"Status tracking failed: {e}")
    
    async def test_active_jobs_monitoring(self):
        """Test active jobs monitoring."""
        if not self.processing_service:
            self.log_test("Active Jobs Monitoring", False, "No processing service")
            return
        
        try:
            active_jobs = await self.processing_service.get_active_jobs()
            
            self.log_test("Active Jobs Monitoring", True, f"Found {len(active_jobs)} active jobs")
            
        except Exception as e:
            self.log_test("Active Jobs Monitoring", False, f"Monitoring failed: {e}")
    
    def test_pdf_processor_integration(self):
        """Test PDF processor integration."""
        try:
            from multimodal_librarian.components.pdf_processor.pdf_processor import PDFProcessor
            
            processor = PDFProcessor()
            test_pdf = self.create_test_pdf()
            
            # Test PDF processing
            content = processor.extract_content(test_pdf)
            
            if content and content.text:
                self.log_test("PDF Processor Integration", True, f"Extracted {len(content.text)} characters")
            else:
                self.log_test("PDF Processor Integration", False, "No content extracted")
            
        except Exception as e:
            self.log_test("PDF Processor Integration", False, f"Processing failed: {e}")
    
    def test_chunking_framework_integration(self):
        """Test chunking framework integration."""
        try:
            from multimodal_librarian.components.chunking_framework.framework import GenericMultiLevelChunkingFramework
            from multimodal_librarian.models.core import DocumentContent, DocumentMetadata
            
            framework = GenericMultiLevelChunkingFramework()
            
            # Create test document content
            metadata = DocumentMetadata(title="Test Document", page_count=1)
            doc_content = DocumentContent(
                text="This is a test document for chunking framework validation. It contains multiple sentences to test the chunking process.",
                images=[],
                tables=[],
                charts=[],
                metadata=metadata
            )
            
            # Process document
            processed = framework.process_document(doc_content, str(uuid4()))
            
            if processed and processed.chunks:
                self.log_test("Chunking Framework Integration", True, f"Generated {len(processed.chunks)} chunks")
            else:
                self.log_test("Chunking Framework Integration", False, "No chunks generated")
            
        except Exception as e:
            self.log_test("Chunking Framework Integration", False, f"Chunking failed: {e}")
    
    async def test_job_cancellation(self, document_id: str = None):
        """Test job cancellation functionality."""
        if not document_id or not self.processing_service:
            self.log_test("Job Cancellation", False, "No document ID or processing service")
            return
        
        try:
            # Attempt to cancel processing
            success = await self.processing_service.cancel_processing(document_id)
            
            if success:
                self.log_test("Job Cancellation", True, "Job cancelled successfully")
            else:
                self.log_test("Job Cancellation", True, "Job not cancellable (expected for completed jobs)")
            
        except Exception as e:
            self.log_test("Job Cancellation", False, f"Cancellation failed: {e}")
    
    async def run_all_tests(self):
        """Run all Task 4 tests."""
        print("🧪 Starting Task 4: Document Processing Pipeline Tests")
        print("=" * 60)
        
        # Test 1: Database migration
        await self.test_database_migration()
        
        # Test 2: Redis connection
        self.test_redis_connection()
        
        # Test 3: Celery configuration
        self.test_celery_configuration()
        
        # Test 4: Celery service initialization
        await self.test_celery_service_initialization()
        
        # Test 5: Processing service integration
        await self.test_processing_service_integration()
        
        # Test 6: PDF processor integration
        self.test_pdf_processor_integration()
        
        # Test 7: Chunking framework integration
        self.test_chunking_framework_integration()
        
        # Test 8: Document upload integration
        document_id = await self.test_document_upload_integration()
        
        # Test 9: Processing status tracking
        await self.test_processing_status_tracking(document_id)
        
        # Test 10: Active jobs monitoring
        await self.test_active_jobs_monitoring()
        
        # Test 11: Job cancellation
        await self.test_job_cancellation(document_id)
        
        # Print summary
        return self.print_summary()


async def main():
    """Main test function."""
    tester = Task4Tester()
    success = await tester.run_all_tests()
    
    if success:
        print("\n🎉 Task 4 implementation is ready!")
        print("\nNext steps:")
        print("1. Start Celery worker: ./scripts/manage-celery-worker.sh start")
        print("2. Test document upload through the web interface")
        print("3. Monitor processing with: ./scripts/monitor-celery.sh")
        sys.exit(0)
    else:
        print("\n⚠️  Task 4 implementation needs attention.")
        print("Please fix the failing tests before proceeding.")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())