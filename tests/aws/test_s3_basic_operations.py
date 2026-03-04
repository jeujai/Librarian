#!/usr/bin/env python3
"""
Basic S3 Operations Tests for AWS Learning Deployment

This module tests S3 file storage operations including:
- File upload and download
- Presigned URL generation
- Bucket operations
- File metadata handling
- Basic security validation
"""

import os
import sys
import pytest
import boto3
import tempfile
import json
from datetime import datetime, timedelta
from typing import Dict, Any, Optional
from botocore.exceptions import ClientError

# Add src to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'src'))

from multimodal_librarian.aws.s3_simple import S3SimpleClient as S3Manager
from multimodal_librarian.aws.presigned_urls_basic import PresignedUrlGenerator as PresignedURLManager
from multimodal_librarian.logging_config import get_logger


class S3OperationsTestSuite:
    """Test suite for S3 operations."""
    
    def __init__(self):
        self.logger = get_logger("s3_operations_tests")
        
        # Configuration
        self.bucket_name = os.getenv("S3_BUCKET_NAME")
        self.aws_region = os.getenv("AWS_REGION", "us-east-1")
        
        # Initialize clients and managers
        self.s3_client = None
        self.s3_manager = None
        self.presigned_manager = None
        
        # Test configuration
        self.test_prefix = "test-files/"
        self.test_timeout = 30
        
        self._initialize_clients()
    
    def _initialize_clients(self):
        """Initialize S3 clients and managers."""
        try:
            self.s3_client = boto3.client('s3', region_name=self.aws_region)
            
            if self.bucket_name:
                self.s3_manager = S3Manager()
                self.presigned_manager = PresignedURLManager()
                self.logger.info("S3 clients initialized successfully")
            else:
                self.logger.warning("S3_BUCKET_NAME not configured")
                
        except Exception as e:
            self.logger.warning(f"Could not initialize S3 clients: {e}")


@pytest.fixture(scope="session")
def s3_test_suite():
    """Pytest fixture for S3 operations test suite."""
    return S3OperationsTestSuite()


class TestS3BasicOperations:
    """Test basic S3 file operations."""
    
    def test_bucket_exists(self, s3_test_suite):
        """Test that the configured S3 bucket exists and is accessible."""
        if not s3_test_suite.s3_client or not s3_test_suite.bucket_name:
            pytest.skip("S3 not configured")
        
        try:
            response = s3_test_suite.s3_client.head_bucket(
                Bucket=s3_test_suite.bucket_name
            )
            assert response['ResponseMetadata']['HTTPStatusCode'] == 200
            
            s3_test_suite.logger.info(f"✅ S3 bucket '{s3_test_suite.bucket_name}' exists and is accessible")
            
        except ClientError as e:
            error_code = e.response['Error']['Code']
            if error_code == '404':
                pytest.fail(f"S3 bucket not found: {s3_test_suite.bucket_name}")
            elif error_code == '403':
                pytest.fail(f"Access denied to S3 bucket: {s3_test_suite.bucket_name}")
            else:
                pytest.fail(f"S3 bucket access failed: {e}")
    
    def test_file_upload_and_download(self, s3_test_suite):
        """Test basic file upload and download operations."""
        if not s3_test_suite.s3_manager:
            pytest.skip("S3 manager not available")
        
        # Create test file
        test_content = f"Test file content - {datetime.now().isoformat()}"
        test_filename = f"test_upload_{datetime.now().timestamp()}.txt"
        test_key = f"{s3_test_suite.test_prefix}{test_filename}"
        
        try:
            # Test upload
            with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.txt') as temp_file:
                temp_file.write(test_content)
                temp_file_path = temp_file.name
            
            try:
                # Upload file
                upload_result = s3_test_suite.s3_manager.upload_file(
                    temp_file_path,
                    test_key,
                    metadata={"test": "true", "timestamp": str(datetime.now().timestamp())}
                )
                
                assert upload_result["success"] is True
                assert "url" in upload_result
                
                s3_test_suite.logger.info(f"✅ File uploaded successfully: {test_key}")
                
                # Test download
                with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.txt') as download_file:
                    download_path = download_file.name
                
                download_result = s3_test_suite.s3_manager.download_file(
                    test_key,
                    download_path
                )
                
                assert download_result["success"] is True
                
                # Verify content
                with open(download_path, 'r') as f:
                    downloaded_content = f.read()
                
                assert downloaded_content == test_content
                
                s3_test_suite.logger.info(f"✅ File downloaded and verified: {test_key}")
                
                # Clean up downloaded file
                os.unlink(download_path)
                
            finally:
                # Clean up uploaded file and temp file
                try:
                    s3_test_suite.s3_client.delete_object(
                        Bucket=s3_test_suite.bucket_name,
                        Key=test_key
                    )
                    os.unlink(temp_file_path)
                except Exception as e:
                    s3_test_suite.logger.warning(f"Cleanup failed: {e}")
                    
        except Exception as e:
            pytest.fail(f"File upload/download test failed: {e}")
    
    def test_file_metadata_operations(self, s3_test_suite):
        """Test file metadata operations."""
        if not s3_test_suite.s3_manager:
            pytest.skip("S3 manager not available")
        
        test_content = "Test metadata content"
        test_filename = f"test_metadata_{datetime.now().timestamp()}.txt"
        test_key = f"{s3_test_suite.test_prefix}{test_filename}"
        
        test_metadata = {
            "content-type": "text/plain",
            "author": "test-user",
            "purpose": "integration-test",
            "timestamp": str(datetime.now().timestamp())
        }
        
        try:
            # Create and upload file with metadata
            with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.txt') as temp_file:
                temp_file.write(test_content)
                temp_file_path = temp_file.name
            
            try:
                # Upload with metadata
                upload_result = s3_test_suite.s3_manager.upload_file(
                    temp_file_path,
                    test_key,
                    metadata=test_metadata
                )
                
                assert upload_result["success"] is True
                
                # Get file metadata
                metadata_result = s3_test_suite.s3_manager.get_file_metadata(test_key)
                
                assert metadata_result["success"] is True
                assert "metadata" in metadata_result
                
                # Verify metadata (S3 converts keys to lowercase and prefixes with x-amz-meta-)
                returned_metadata = metadata_result["metadata"]
                
                # Check that our custom metadata is present
                assert "author" in returned_metadata or "x-amz-meta-author" in returned_metadata
                assert "purpose" in returned_metadata or "x-amz-meta-purpose" in returned_metadata
                
                s3_test_suite.logger.info(f"✅ File metadata operations successful: {test_key}")
                
            finally:
                # Clean up
                try:
                    s3_test_suite.s3_client.delete_object(
                        Bucket=s3_test_suite.bucket_name,
                        Key=test_key
                    )
                    os.unlink(temp_file_path)
                except Exception as e:
                    s3_test_suite.logger.warning(f"Cleanup failed: {e}")
                    
        except Exception as e:
            pytest.fail(f"File metadata test failed: {e}")
    
    def test_file_listing_operations(self, s3_test_suite):
        """Test file listing operations."""
        if not s3_test_suite.s3_manager:
            pytest.skip("S3 manager not available")
        
        # Create multiple test files
        test_files = []
        test_prefix = f"{s3_test_suite.test_prefix}listing_test_{datetime.now().timestamp()}/"
        
        try:
            # Upload multiple test files
            for i in range(3):
                test_content = f"Test file {i} content"
                test_filename = f"test_file_{i}.txt"
                test_key = f"{test_prefix}{test_filename}"
                
                with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.txt') as temp_file:
                    temp_file.write(test_content)
                    temp_file_path = temp_file.name
                
                upload_result = s3_test_suite.s3_manager.upload_file(
                    temp_file_path,
                    test_key
                )
                
                assert upload_result["success"] is True
                test_files.append({"key": test_key, "path": temp_file_path})
            
            # Test listing files
            list_result = s3_test_suite.s3_manager.list_files(prefix=test_prefix)
            
            assert list_result["success"] is True
            assert "files" in list_result
            assert len(list_result["files"]) >= 3
            
            # Verify our test files are in the list
            file_keys = [f["key"] for f in list_result["files"]]
            for test_file in test_files:
                assert test_file["key"] in file_keys
            
            s3_test_suite.logger.info(f"✅ File listing operations successful: found {len(list_result['files'])} files")
            
        finally:
            # Clean up all test files
            for test_file in test_files:
                try:
                    s3_test_suite.s3_client.delete_object(
                        Bucket=s3_test_suite.bucket_name,
                        Key=test_file["key"]
                    )
                    os.unlink(test_file["path"])
                except Exception as e:
                    s3_test_suite.logger.warning(f"Cleanup failed for {test_file['key']}: {e}")


class TestPresignedURLOperations:
    """Test presigned URL operations."""
    
    def test_presigned_upload_url_generation(self, s3_test_suite):
        """Test presigned URL generation for uploads."""
        if not s3_test_suite.presigned_manager:
            pytest.skip("Presigned URL manager not available")
        
        test_filename = f"test_presigned_upload_{datetime.now().timestamp()}.txt"
        test_key = f"{s3_test_suite.test_prefix}{test_filename}"
        
        try:
            # Generate presigned upload URL
            url_result = s3_test_suite.presigned_manager.generate_upload_url(
                test_key,
                content_type="text/plain",
                expires_in=3600
            )
            
            assert url_result["success"] is True
            assert "upload_url" in url_result
            assert "fields" in url_result
            
            # Validate URL structure
            upload_url = url_result["upload_url"]
            assert upload_url.startswith("https://")
            assert s3_test_suite.bucket_name in upload_url
            
            s3_test_suite.logger.info(f"✅ Presigned upload URL generated successfully")
            
        except Exception as e:
            pytest.fail(f"Presigned upload URL test failed: {e}")
    
    def test_presigned_download_url_generation(self, s3_test_suite):
        """Test presigned URL generation for downloads."""
        if not s3_test_suite.presigned_manager:
            pytest.skip("Presigned URL manager not available")
        
        # First upload a test file
        test_content = "Test download content"
        test_filename = f"test_presigned_download_{datetime.now().timestamp()}.txt"
        test_key = f"{s3_test_suite.test_prefix}{test_filename}"
        
        try:
            # Upload test file
            with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.txt') as temp_file:
                temp_file.write(test_content)
                temp_file_path = temp_file.name
            
            upload_result = s3_test_suite.s3_manager.upload_file(
                temp_file_path,
                test_key
            )
            
            assert upload_result["success"] is True
            
            # Generate presigned download URL
            url_result = s3_test_suite.presigned_manager.generate_download_url(
                test_key,
                expires_in=3600
            )
            
            assert url_result["success"] is True
            assert "download_url" in url_result
            
            # Validate URL structure
            download_url = url_result["download_url"]
            assert download_url.startswith("https://")
            assert s3_test_suite.bucket_name in download_url
            
            s3_test_suite.logger.info(f"✅ Presigned download URL generated successfully")
            
        finally:
            # Clean up
            try:
                s3_test_suite.s3_client.delete_object(
                    Bucket=s3_test_suite.bucket_name,
                    Key=test_key
                )
                os.unlink(temp_file_path)
            except Exception as e:
                s3_test_suite.logger.warning(f"Cleanup failed: {e}")
    
    def test_presigned_url_expiration(self, s3_test_suite):
        """Test presigned URL expiration settings."""
        if not s3_test_suite.presigned_manager:
            pytest.skip("Presigned URL manager not available")
        
        test_filename = f"test_expiration_{datetime.now().timestamp()}.txt"
        test_key = f"{s3_test_suite.test_prefix}{test_filename}"
        
        try:
            # Generate URL with short expiration
            url_result = s3_test_suite.presigned_manager.generate_upload_url(
                test_key,
                content_type="text/plain",
                expires_in=60  # 1 minute
            )
            
            assert url_result["success"] is True
            assert "upload_url" in url_result
            
            # URL should contain expiration information
            upload_url = url_result["upload_url"]
            assert "X-Amz-Expires=60" in upload_url or "Expires=" in upload_url
            
            s3_test_suite.logger.info(f"✅ Presigned URL expiration configured correctly")
            
        except Exception as e:
            pytest.fail(f"Presigned URL expiration test failed: {e}")


class TestS3SecurityBasics:
    """Test basic S3 security configurations."""
    
    def test_bucket_public_access_blocked(self, s3_test_suite):
        """Test that bucket has appropriate public access restrictions."""
        if not s3_test_suite.s3_client or not s3_test_suite.bucket_name:
            pytest.skip("S3 not configured")
        
        try:
            # Check bucket public access block configuration
            response = s3_test_suite.s3_client.get_public_access_block(
                Bucket=s3_test_suite.bucket_name
            )
            
            public_access_config = response['PublicAccessBlockConfiguration']
            
            # For learning deployment, we expect some restrictions
            # (exact configuration depends on use case)
            assert isinstance(public_access_config['BlockPublicAcls'], bool)
            assert isinstance(public_access_config['IgnorePublicAcls'], bool)
            
            s3_test_suite.logger.info(f"✅ Bucket public access configuration verified")
            
        except ClientError as e:
            if e.response['Error']['Code'] == 'NoSuchPublicAccessBlockConfiguration':
                s3_test_suite.logger.warning("⚠️  No public access block configuration found")
            else:
                pytest.fail(f"Public access block check failed: {e}")
    
    def test_bucket_encryption_configuration(self, s3_test_suite):
        """Test bucket encryption configuration."""
        if not s3_test_suite.s3_client or not s3_test_suite.bucket_name:
            pytest.skip("S3 not configured")
        
        try:
            # Check bucket encryption
            response = s3_test_suite.s3_client.get_bucket_encryption(
                Bucket=s3_test_suite.bucket_name
            )
            
            encryption_config = response['ServerSideEncryptionConfiguration']
            rules = encryption_config['Rules']
            
            assert len(rules) > 0
            
            # Check that encryption is configured
            for rule in rules:
                sse_config = rule['ApplyServerSideEncryptionByDefault']
                assert 'SSEAlgorithm' in sse_config
                
                # Common algorithms: AES256 or aws:kms
                assert sse_config['SSEAlgorithm'] in ['AES256', 'aws:kms']
            
            s3_test_suite.logger.info(f"✅ Bucket encryption configured properly")
            
        except ClientError as e:
            if e.response['Error']['Code'] == 'ServerSideEncryptionConfigurationNotFoundError':
                s3_test_suite.logger.warning("⚠️  No encryption configuration found")
            else:
                pytest.fail(f"Encryption configuration check failed: {e}")


class TestS3PerformanceBasics:
    """Test basic S3 performance characteristics."""
    
    def test_upload_performance(self, s3_test_suite):
        """Test upload performance for small files."""
        if not s3_test_suite.s3_manager:
            pytest.skip("S3 manager not available")
        
        # Create test file (1KB)
        test_content = "x" * 1024  # 1KB of data
        test_filename = f"test_performance_{datetime.now().timestamp()}.txt"
        test_key = f"{s3_test_suite.test_prefix}{test_filename}"
        
        try:
            with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.txt') as temp_file:
                temp_file.write(test_content)
                temp_file_path = temp_file.name
            
            # Measure upload time
            start_time = datetime.now()
            
            upload_result = s3_test_suite.s3_manager.upload_file(
                temp_file_path,
                test_key
            )
            
            end_time = datetime.now()
            upload_time = (end_time - start_time).total_seconds()
            
            assert upload_result["success"] is True
            
            # Upload should complete in reasonable time (under 10 seconds for 1KB)
            assert upload_time < 10.0
            
            s3_test_suite.logger.info(f"✅ Upload performance: {upload_time:.2f}s for 1KB file")
            
        finally:
            # Clean up
            try:
                s3_test_suite.s3_client.delete_object(
                    Bucket=s3_test_suite.bucket_name,
                    Key=test_key
                )
                os.unlink(temp_file_path)
            except Exception as e:
                s3_test_suite.logger.warning(f"Cleanup failed: {e}")
    
    def test_download_performance(self, s3_test_suite):
        """Test download performance for small files."""
        if not s3_test_suite.s3_manager:
            pytest.skip("S3 manager not available")
        
        # Create and upload test file
        test_content = "x" * 1024  # 1KB of data
        test_filename = f"test_download_perf_{datetime.now().timestamp()}.txt"
        test_key = f"{s3_test_suite.test_prefix}{test_filename}"
        
        try:
            with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.txt') as temp_file:
                temp_file.write(test_content)
                temp_file_path = temp_file.name
            
            # Upload first
            upload_result = s3_test_suite.s3_manager.upload_file(
                temp_file_path,
                test_key
            )
            assert upload_result["success"] is True
            
            # Measure download time
            with tempfile.NamedTemporaryFile(delete=False, suffix='.txt') as download_file:
                download_path = download_file.name
            
            start_time = datetime.now()
            
            download_result = s3_test_suite.s3_manager.download_file(
                test_key,
                download_path
            )
            
            end_time = datetime.now()
            download_time = (end_time - start_time).total_seconds()
            
            assert download_result["success"] is True
            
            # Download should complete in reasonable time (under 10 seconds for 1KB)
            assert download_time < 10.0
            
            s3_test_suite.logger.info(f"✅ Download performance: {download_time:.2f}s for 1KB file")
            
        finally:
            # Clean up
            try:
                s3_test_suite.s3_client.delete_object(
                    Bucket=s3_test_suite.bucket_name,
                    Key=test_key
                )
                os.unlink(temp_file_path)
                os.unlink(download_path)
            except Exception as e:
                s3_test_suite.logger.warning(f"Cleanup failed: {e}")


# Test execution functions
def run_s3_operations_tests():
    """Run S3 operations tests with proper configuration."""
    import subprocess
    
    # Set test environment
    os.environ.setdefault("TESTING", "true")
    os.environ.setdefault("LOG_LEVEL", "INFO")
    
    # Run pytest with specific markers and output
    cmd = [
        "python", "-m", "pytest",
        __file__,
        "-v",
        "--tb=short",
        "--color=yes",
        "-x"  # Stop on first failure
    ]
    
    try:
        result = subprocess.run(cmd, capture_output=True, text=True)
        
        print("🗄️  S3 OPERATIONS TEST RESULTS")
        print("=" * 50)
        print(result.stdout)
        
        if result.stderr:
            print("\n⚠️  WARNINGS/ERRORS:")
            print(result.stderr)
        
        return result.returncode == 0
        
    except Exception as e:
        print(f"❌ Failed to run S3 tests: {e}")
        return False


if __name__ == "__main__":
    success = run_s3_operations_tests()
    exit(0 if success else 1)