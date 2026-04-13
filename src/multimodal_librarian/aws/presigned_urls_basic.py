"""
Basic presigned URL generation for secure file uploads/downloads

This module provides simple presigned URL functionality for the learning project.
"""

import logging
import os
from datetime import datetime, timedelta
from typing import Any, Dict, Optional

import boto3
from botocore.exceptions import ClientError, NoCredentialsError

logger = logging.getLogger(__name__)

class PresignedUrlGenerator:
    """Generate presigned URLs for S3 operations"""
    
    def __init__(self, bucket_name: Optional[str] = None, region: str = 'us-east-1'):
        """
        Initialize presigned URL generator
        
        Args:
            bucket_name: S3 bucket name
            region: AWS region
        """
        self.bucket_name = bucket_name or os.getenv('S3_BUCKET_NAME')
        self.region = region
        
        if not self.bucket_name:
            raise ValueError("S3 bucket name must be provided or set in S3_BUCKET_NAME environment variable")
        
        try:
            self.s3_client = boto3.client('s3', region_name=region)
        except NoCredentialsError:
            logger.error("AWS credentials not found. Please configure AWS credentials.")
            raise
    
    def generate_upload_url(
        self, 
        s3_key: str, 
        expiration: int = 3600,
        content_type: Optional[str] = None,
        max_file_size: Optional[int] = None  # Defaults to config setting
    ) -> Optional[Dict[str, Any]]:
        """
        Generate a presigned URL for file upload
        
        Args:
            s3_key: S3 object key where file will be stored
            expiration: URL expiration time in seconds (default: 1 hour)
            content_type: Expected content type
            max_file_size: Maximum file size in bytes (defaults to config setting)
            
        Returns:
            Dictionary with presigned URL and fields, or None if failed
        """
        # Use config default if not specified
        if max_file_size is None:
            from ..config.config import get_settings
            max_file_size = get_settings().max_file_size
        
        try:
            # Conditions for the upload
            conditions = [
                {"bucket": self.bucket_name},
                {"key": s3_key},
                ["content-length-range", 1, max_file_size],  # File size limits
            ]
            
            # Fields to include in the form
            fields = {
                "key": s3_key,
            }
            
            # Add content type if specified
            if content_type:
                conditions.append({"Content-Type": content_type})
                fields["Content-Type"] = content_type
            
            # Generate presigned POST URL
            response = self.s3_client.generate_presigned_post(
                Bucket=self.bucket_name,
                Key=s3_key,
                Fields=fields,
                Conditions=conditions,
                ExpiresIn=expiration
            )
            
            logger.info(f"Generated upload URL for {s3_key}, expires in {expiration} seconds")
            
            return {
                'url': response['url'],
                'fields': response['fields'],
                'expires_in': expiration,
                'max_file_size': max_file_size,
                's3_key': s3_key,
            }
            
        except ClientError as e:
            logger.error(f"Failed to generate upload URL for {s3_key}: {e}")
            return None
    
    def generate_download_url(
        self, 
        s3_key: str, 
        expiration: int = 3600,
        response_content_disposition: Optional[str] = None
    ) -> Optional[str]:
        """
        Generate a presigned URL for file download
        
        Args:
            s3_key: S3 object key to download
            expiration: URL expiration time in seconds (default: 1 hour)
            response_content_disposition: Content-Disposition header for download
            
        Returns:
            Presigned URL string, or None if failed
        """
        try:
            params = {
                'Bucket': self.bucket_name,
                'Key': s3_key,
            }
            
            # Add content disposition if specified (for downloads)
            if response_content_disposition:
                params['ResponseContentDisposition'] = response_content_disposition
            
            url = self.s3_client.generate_presigned_url(
                'get_object',
                Params=params,
                ExpiresIn=expiration
            )
            
            logger.info(f"Generated download URL for {s3_key}, expires in {expiration} seconds")
            return url
            
        except ClientError as e:
            logger.error(f"Failed to generate download URL for {s3_key}: {e}")
            return None
    
    def generate_delete_url(self, s3_key: str, expiration: int = 3600) -> Optional[str]:
        """
        Generate a presigned URL for file deletion
        
        Args:
            s3_key: S3 object key to delete
            expiration: URL expiration time in seconds (default: 1 hour)
            
        Returns:
            Presigned URL string, or None if failed
        """
        try:
            url = self.s3_client.generate_presigned_url(
                'delete_object',
                Params={'Bucket': self.bucket_name, 'Key': s3_key},
                ExpiresIn=expiration
            )
            
            logger.info(f"Generated delete URL for {s3_key}, expires in {expiration} seconds")
            return url
            
        except ClientError as e:
            logger.error(f"Failed to generate delete URL for {s3_key}: {e}")
            return None
    
    def generate_batch_upload_urls(
        self, 
        s3_keys: list, 
        expiration: int = 3600,
        content_type: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Generate multiple upload URLs at once
        
        Args:
            s3_keys: List of S3 object keys
            expiration: URL expiration time in seconds
            content_type: Expected content type for all files
            
        Returns:
            Dictionary mapping s3_key to presigned URL data
        """
        results = {}
        
        for s3_key in s3_keys:
            url_data = self.generate_upload_url(s3_key, expiration, content_type)
            if url_data:
                results[s3_key] = url_data
            else:
                results[s3_key] = {'error': 'Failed to generate URL'}
        
        return results


class FileUploadManager:
    """Manage file uploads with presigned URLs"""
    
    def __init__(self, bucket_name: Optional[str] = None):
        self.url_generator = PresignedUrlGenerator(bucket_name)
    
    def create_upload_session(
        self, 
        filename: str, 
        content_type: Optional[str] = None,
        folder: str = 'uploads'
    ) -> Optional[Dict[str, Any]]:
        """
        Create an upload session for a file
        
        Args:
            filename: Original filename
            content_type: MIME type of the file
            folder: S3 folder to upload to
            
        Returns:
            Upload session data with presigned URL
        """
        # Generate unique S3 key
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        safe_filename = filename.replace(' ', '_').replace('/', '_')
        s3_key = f"{folder}/{timestamp}_{safe_filename}"
        
        # Generate upload URL
        upload_data = self.url_generator.generate_upload_url(
            s3_key=s3_key,
            content_type=content_type,
            expiration=3600  # 1 hour
        )
        
        if upload_data:
            return {
                'session_id': f"{timestamp}_{safe_filename}",
                'original_filename': filename,
                's3_key': s3_key,
                'upload_url': upload_data['url'],
                'upload_fields': upload_data['fields'],
                'expires_at': datetime.now() + timedelta(seconds=3600),
                'content_type': content_type,
            }
        
        return None
    
    def get_download_url(self, s3_key: str, filename: Optional[str] = None) -> Optional[str]:
        """
        Get a download URL for a file
        
        Args:
            s3_key: S3 object key
            filename: Suggested filename for download
            
        Returns:
            Download URL
        """
        disposition = None
        if filename:
            disposition = f'attachment; filename="{filename}"'
        
        return self.url_generator.generate_download_url(
            s3_key=s3_key,
            response_content_disposition=disposition
        )


# Convenience functions
def get_upload_url(s3_key: str, content_type: Optional[str] = None, bucket_name: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """Generate upload URL (convenience function)"""
    generator = PresignedUrlGenerator(bucket_name)
    return generator.generate_upload_url(s3_key, content_type=content_type)

def get_download_url(s3_key: str, bucket_name: Optional[str] = None) -> Optional[str]:
    """Generate download URL (convenience function)"""
    generator = PresignedUrlGenerator(bucket_name)
    return generator.generate_download_url(s3_key)

def create_file_upload_session(filename: str, content_type: Optional[str] = None, bucket_name: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """Create file upload session (convenience function)"""
    manager = FileUploadManager(bucket_name)
    return manager.create_upload_session(filename, content_type)