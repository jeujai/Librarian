"""
Storage service for managing file uploads and downloads using S3-compatible storage.

This service provides secure file storage, presigned URL generation,
and file management operations for the document upload system.
Supports both AWS S3 and MinIO (local S3-compatible storage).
"""

import logging
import os
from datetime import datetime
from typing import Any, Dict, Optional, Tuple
from uuid import UUID

import boto3
from botocore.config import Config
from botocore.exceptions import ClientError, NoCredentialsError

logger = logging.getLogger(__name__)


class StorageError(Exception):
    """Base exception for storage operations."""
    pass


class StorageService:
    """
    S3-compatible storage service for document management.
    
    Handles file uploads, downloads, and secure access using presigned URLs.
    Supports both AWS S3 and MinIO for local development.
    """
    
    def __init__(
        self,
        bucket_name: Optional[str] = None,
        region: str = 'us-east-1',
        endpoint_url: Optional[str] = None,
        access_key: Optional[str] = None,
        secret_key: Optional[str] = None
    ):
        """
        Initialize storage service.
        
        Args:
            bucket_name: S3 bucket name (defaults to environment variable)
            region: AWS region
            endpoint_url: Custom endpoint URL for MinIO (None for AWS S3)
            access_key: Access key (for MinIO, defaults to env var)
            secret_key: Secret key (for MinIO, defaults to env var)
        """
        # Determine if using MinIO or AWS S3
        self.endpoint_url = endpoint_url or os.getenv('MINIO_ENDPOINT', os.getenv('S3_ENDPOINT_URL'))
        self.use_minio = self.endpoint_url is not None
        
        # Set bucket name
        default_bucket = 'documents' if self.use_minio else 'multimodal-librarian-storage'
        self.bucket_name = bucket_name or os.getenv('S3_BUCKET_NAME', default_bucket)
        self.region = region
        
        # Set credentials for MinIO
        self.access_key = access_key or os.getenv('MINIO_ACCESS_KEY', 'minioadmin')
        self.secret_key = secret_key or os.getenv('MINIO_SECRET_KEY', 'minioadmin')
        
        self.s3_client = None
        self._initialize_client()
    
    def _initialize_client(self) -> None:
        """Initialize S3 client with error handling."""
        try:
            if self.use_minio:
                # Configure for MinIO
                self.s3_client = boto3.client(
                    's3',
                    endpoint_url=self.endpoint_url,
                    aws_access_key_id=self.access_key,
                    aws_secret_access_key=self.secret_key,
                    region_name=self.region,
                    config=Config(signature_version='s3v4')
                )
                logger.info(f"MinIO client initialized: {self.endpoint_url}, bucket: {self.bucket_name}")
                
                # Ensure bucket exists for MinIO
                self._ensure_bucket_exists()
            else:
                # Configure for AWS S3
                self.s3_client = boto3.client('s3', region_name=self.region)
                logger.info(f"S3 client initialized for bucket: {self.bucket_name}")
                
        except NoCredentialsError:
            logger.error("Storage credentials not found")
            raise StorageError("Storage credentials not configured")
        except Exception as e:
            logger.error(f"Failed to initialize storage client: {e}")
            raise StorageError(f"Storage initialization failed: {e}")
    
    def _ensure_bucket_exists(self) -> None:
        """Ensure the bucket exists, create if it doesn't (for MinIO)."""
        try:
            self.s3_client.head_bucket(Bucket=self.bucket_name)
        except ClientError as e:
            error_code = e.response.get('Error', {}).get('Code', '')
            if error_code in ('404', 'NoSuchBucket'):
                try:
                    self.s3_client.create_bucket(Bucket=self.bucket_name)
                    logger.info(f"Created bucket: {self.bucket_name}")
                except Exception as create_error:
                    logger.error(f"Failed to create bucket: {create_error}")
                    raise StorageError(f"Failed to create bucket: {create_error}")
            else:
                logger.warning(f"Bucket check failed: {e}")
    
    def upload_file(self, file_data: bytes, document_id: UUID, filename: str, 
                   content_type: str = 'application/pdf') -> str:
        """
        Upload file to S3/MinIO and return the storage key.
        
        Args:
            file_data: File content as bytes
            document_id: Unique document identifier
            filename: Original filename
            content_type: MIME type of the file
            
        Returns:
            str: Storage key for the uploaded file
            
        Raises:
            StorageError: If upload fails
        """
        try:
            # Generate storage key with document ID and timestamp
            timestamp = datetime.utcnow().strftime('%Y%m%d_%H%M%S')
            s3_key = f"documents/{document_id}/{timestamp}_{filename}"
            
            # Upload file with metadata
            metadata = {
                'document_id': str(document_id),
                'original_filename': filename,
                'upload_timestamp': datetime.utcnow().isoformat(),
                'content_type': content_type
            }
            
            put_params = {
                'Bucket': self.bucket_name,
                'Key': s3_key,
                'Body': file_data,
                'ContentType': content_type,
                'Metadata': metadata
            }
            
            # Only add encryption for AWS S3, not MinIO
            if not self.use_minio:
                put_params['ServerSideEncryption'] = 'AES256'
            
            self.s3_client.put_object(**put_params)
            
            logger.info(f"File uploaded successfully: {s3_key}")
            return s3_key
            
        except ClientError as e:
            error_code = e.response['Error']['Code']
            logger.error(f"Storage upload failed with error {error_code}: {e}")
            raise StorageError(f"File upload failed: {error_code}")
        except Exception as e:
            logger.error(f"Unexpected error during upload: {e}")
            raise StorageError(f"Upload failed: {e}")
    
    def download_file(self, s3_key: str) -> bytes:
        """
        Download file from S3.
        
        Args:
            s3_key: S3 key of the file to download
            
        Returns:
            bytes: File content
            
        Raises:
            StorageError: If download fails
        """
        try:
            response = self.s3_client.get_object(
                Bucket=self.bucket_name,
                Key=s3_key
            )
            
            file_data = response['Body'].read()
            logger.info(f"File downloaded successfully: {s3_key}")
            return file_data
            
        except ClientError as e:
            error_code = e.response['Error']['Code']
            if error_code == 'NoSuchKey':
                raise StorageError(f"File not found: {s3_key}")
            logger.error(f"S3 download failed with error {error_code}: {e}")
            raise StorageError(f"File download failed: {error_code}")
        except Exception as e:
            logger.error(f"Unexpected error during download: {e}")
            raise StorageError(f"Download failed: {e}")
    
    def generate_presigned_url(self, s3_key: str, expiration: int = 3600, 
                              operation: str = 'get_object') -> str:
        """
        Generate presigned URL for secure file access.
        
        Args:
            s3_key: S3 key of the file
            expiration: URL expiration time in seconds (default 1 hour)
            operation: S3 operation ('get_object' or 'put_object')
            
        Returns:
            str: Presigned URL
            
        Raises:
            StorageError: If URL generation fails
        """
        try:
            url = self.s3_client.generate_presigned_url(
                operation,
                Params={'Bucket': self.bucket_name, 'Key': s3_key},
                ExpiresIn=expiration
            )
            
            logger.info(f"Presigned URL generated for: {s3_key}")
            return url
            
        except ClientError as e:
            logger.error(f"Presigned URL generation failed: {e}")
            raise StorageError(f"URL generation failed: {e}")
        except Exception as e:
            logger.error(f"Unexpected error generating URL: {e}")
            raise StorageError(f"URL generation failed: {e}")
    
    def delete_file(self, s3_key: str) -> bool:
        """
        Delete file from S3.
        
        Args:
            s3_key: S3 key of the file to delete
            
        Returns:
            bool: True if deletion successful
            
        Raises:
            StorageError: If deletion fails
        """
        try:
            self.s3_client.delete_object(
                Bucket=self.bucket_name,
                Key=s3_key
            )
            
            logger.info(f"File deleted successfully: {s3_key}")
            return True
            
        except ClientError as e:
            error_code = e.response['Error']['Code']
            logger.error(f"S3 deletion failed with error {error_code}: {e}")
            raise StorageError(f"File deletion failed: {error_code}")
        except Exception as e:
            logger.error(f"Unexpected error during deletion: {e}")
            raise StorageError(f"Deletion failed: {e}")
    
    def get_file_metadata(self, s3_key: str) -> Dict[str, Any]:
        """
        Get file metadata from S3.
        
        Args:
            s3_key: S3 key of the file
            
        Returns:
            Dict[str, Any]: File metadata
            
        Raises:
            StorageError: If metadata retrieval fails
        """
        try:
            response = self.s3_client.head_object(
                Bucket=self.bucket_name,
                Key=s3_key
            )
            
            metadata = {
                'content_length': response.get('ContentLength', 0),
                'content_type': response.get('ContentType', ''),
                'last_modified': response.get('LastModified'),
                'etag': response.get('ETag', '').strip('"'),
                'metadata': response.get('Metadata', {})
            }
            
            logger.info(f"Metadata retrieved for: {s3_key}")
            return metadata
            
        except ClientError as e:
            error_code = e.response['Error']['Code']
            if error_code == 'NoSuchKey':
                raise StorageError(f"File not found: {s3_key}")
            logger.error(f"Metadata retrieval failed with error {error_code}: {e}")
            raise StorageError(f"Metadata retrieval failed: {error_code}")
        except Exception as e:
            logger.error(f"Unexpected error retrieving metadata: {e}")
            raise StorageError(f"Metadata retrieval failed: {e}")
    
    def validate_file(self, file_data: bytes, filename: str) -> Tuple[bool, str]:
        """
        Validate uploaded file.
        
        Args:
            file_data: File content as bytes
            filename: Original filename
            
        Returns:
            Tuple[bool, str]: (is_valid, error_message)
        """
        # Check file size (100MB limit)
        max_size = 100 * 1024 * 1024  # 100MB
        if len(file_data) > max_size:
            return False, f"File size exceeds maximum ({max_size // (1024*1024)}MB)"
        
        # Check file extension
        lower_filename = filename.lower()
        if not lower_filename.endswith(('.pdf', '.txt')):
            return False, "Only PDF and TXT files are supported"
        
        # Basic content validation
        if len(file_data) == 0:
            return False, "File is empty"
        
        # PDF-specific validation
        if lower_filename.endswith('.pdf'):
            if not file_data.startswith(b'%PDF-'):
                return False, "Invalid PDF file format"
            if len(file_data) < 1024:  # 1KB minimum for PDFs
                return False, "PDF file appears to be empty or corrupted"
        
        return True, ""
    
    def health_check(self) -> Dict[str, Any]:
        """
        Perform health check on storage service.
        
        Returns:
            Dict[str, Any]: Health status information
        """
        try:
            # Test bucket access
            self.s3_client.head_bucket(Bucket=self.bucket_name)
            
            return {
                'status': 'healthy',
                'storage_type': 'minio' if self.use_minio else 's3',
                'bucket_name': self.bucket_name,
                'endpoint': self.endpoint_url if self.use_minio else 'aws',
                'accessible': True
            }
            
        except ClientError as e:
            error_code = e.response['Error']['Code']
            return {
                'status': 'unhealthy',
                'storage_type': 'minio' if self.use_minio else 's3',
                'bucket_name': self.bucket_name,
                'accessible': False,
                'error': error_code
            }
        except Exception as e:
            return {
                'status': 'unhealthy',
                'storage_type': 'minio' if self.use_minio else 's3',
                'bucket_name': self.bucket_name,
                'accessible': False,
                'error': str(e)
            }
