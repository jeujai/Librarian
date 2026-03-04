"""
Simple S3 operations for Multimodal Librarian (Learning Project)

This module provides basic S3 operations optimized for learning and cost efficiency.
"""

import os
import logging
from typing import Optional, Dict, Any, List
from datetime import datetime, timedelta
import boto3
from botocore.exceptions import ClientError, NoCredentialsError

logger = logging.getLogger(__name__)

class S3SimpleClient:
    """Simple S3 client for basic file operations"""
    
    def __init__(self, bucket_name: Optional[str] = None, region: str = 'us-east-1'):
        """
        Initialize S3 client
        
        Args:
            bucket_name: S3 bucket name (can be set via environment variable)
            region: AWS region
        """
        self.bucket_name = bucket_name or os.getenv('S3_BUCKET_NAME')
        self.region = region
        
        if not self.bucket_name:
            raise ValueError("S3 bucket name must be provided or set in S3_BUCKET_NAME environment variable")
        
        try:
            self.s3_client = boto3.client('s3', region_name=region)
            self.s3_resource = boto3.resource('s3', region_name=region)
            self.bucket = self.s3_resource.Bucket(self.bucket_name)
        except NoCredentialsError:
            logger.error("AWS credentials not found. Please configure AWS credentials.")
            raise
    
    def upload_file(self, file_path: str, s3_key: str, content_type: Optional[str] = None) -> bool:
        """
        Upload a file to S3
        
        Args:
            file_path: Local file path
            s3_key: S3 object key (path in bucket)
            content_type: MIME type of the file
            
        Returns:
            True if successful, False otherwise
        """
        try:
            extra_args = {}
            if content_type:
                extra_args['ContentType'] = content_type
            
            self.s3_client.upload_file(file_path, self.bucket_name, s3_key, ExtraArgs=extra_args)
            logger.info(f"Successfully uploaded {file_path} to s3://{self.bucket_name}/{s3_key}")
            return True
            
        except ClientError as e:
            logger.error(f"Failed to upload {file_path} to S3: {e}")
            return False
        except FileNotFoundError:
            logger.error(f"File not found: {file_path}")
            return False
    
    def upload_bytes(self, data: bytes, s3_key: str, content_type: Optional[str] = None) -> bool:
        """
        Upload bytes data to S3
        
        Args:
            data: Bytes data to upload
            s3_key: S3 object key
            content_type: MIME type of the data
            
        Returns:
            True if successful, False otherwise
        """
        try:
            extra_args = {}
            if content_type:
                extra_args['ContentType'] = content_type
            
            self.s3_client.put_object(
                Bucket=self.bucket_name,
                Key=s3_key,
                Body=data,
                **extra_args
            )
            logger.info(f"Successfully uploaded data to s3://{self.bucket_name}/{s3_key}")
            return True
            
        except ClientError as e:
            logger.error(f"Failed to upload data to S3: {e}")
            return False
    
    def download_file(self, s3_key: str, local_path: str) -> bool:
        """
        Download a file from S3
        
        Args:
            s3_key: S3 object key
            local_path: Local file path to save to
            
        Returns:
            True if successful, False otherwise
        """
        try:
            # Create directory if it doesn't exist
            os.makedirs(os.path.dirname(local_path), exist_ok=True)
            
            self.s3_client.download_file(self.bucket_name, s3_key, local_path)
            logger.info(f"Successfully downloaded s3://{self.bucket_name}/{s3_key} to {local_path}")
            return True
            
        except ClientError as e:
            logger.error(f"Failed to download {s3_key} from S3: {e}")
            return False
    
    def get_object_bytes(self, s3_key: str) -> Optional[bytes]:
        """
        Get object content as bytes
        
        Args:
            s3_key: S3 object key
            
        Returns:
            Object content as bytes, or None if failed
        """
        try:
            response = self.s3_client.get_object(Bucket=self.bucket_name, Key=s3_key)
            return response['Body'].read()
            
        except ClientError as e:
            logger.error(f"Failed to get object {s3_key} from S3: {e}")
            return None
    
    def delete_object(self, s3_key: str) -> bool:
        """
        Delete an object from S3
        
        Args:
            s3_key: S3 object key
            
        Returns:
            True if successful, False otherwise
        """
        try:
            self.s3_client.delete_object(Bucket=self.bucket_name, Key=s3_key)
            logger.info(f"Successfully deleted s3://{self.bucket_name}/{s3_key}")
            return True
            
        except ClientError as e:
            logger.error(f"Failed to delete {s3_key} from S3: {e}")
            return False
    
    def list_objects(self, prefix: str = '', max_keys: int = 1000) -> List[Dict[str, Any]]:
        """
        List objects in the bucket
        
        Args:
            prefix: Object key prefix to filter by
            max_keys: Maximum number of objects to return
            
        Returns:
            List of object metadata dictionaries
        """
        try:
            response = self.s3_client.list_objects_v2(
                Bucket=self.bucket_name,
                Prefix=prefix,
                MaxKeys=max_keys
            )
            
            objects = []
            if 'Contents' in response:
                for obj in response['Contents']:
                    objects.append({
                        'key': obj['Key'],
                        'size': obj['Size'],
                        'last_modified': obj['LastModified'],
                        'etag': obj['ETag'].strip('"'),
                    })
            
            return objects
            
        except ClientError as e:
            logger.error(f"Failed to list objects in S3: {e}")
            return []
    
    def object_exists(self, s3_key: str) -> bool:
        """
        Check if an object exists in S3
        
        Args:
            s3_key: S3 object key
            
        Returns:
            True if object exists, False otherwise
        """
        try:
            self.s3_client.head_object(Bucket=self.bucket_name, Key=s3_key)
            return True
        except ClientError as e:
            if e.response['Error']['Code'] == '404':
                return False
            logger.error(f"Error checking if object {s3_key} exists: {e}")
            return False
    
    def get_object_url(self, s3_key: str) -> str:
        """
        Get the public URL for an object (via CloudFront if available)
        
        Args:
            s3_key: S3 object key
            
        Returns:
            Object URL
        """
        # In production, this would use CloudFront domain
        cloudfront_domain = os.getenv('CLOUDFRONT_DOMAIN')
        if cloudfront_domain:
            return f"https://{cloudfront_domain}/{s3_key}"
        else:
            return f"https://{self.bucket_name}.s3.{self.region}.amazonaws.com/{s3_key}"
    
    def get_bucket_info(self) -> Dict[str, Any]:
        """
        Get basic bucket information
        
        Returns:
            Dictionary with bucket information
        """
        try:
            # Get bucket location
            location = self.s3_client.get_bucket_location(Bucket=self.bucket_name)
            region = location.get('LocationConstraint') or 'us-east-1'
            
            # Count objects (limited for cost)
            response = self.s3_client.list_objects_v2(Bucket=self.bucket_name, MaxKeys=1000)
            object_count = response.get('KeyCount', 0)
            
            return {
                'bucket_name': self.bucket_name,
                'region': region,
                'object_count': object_count,
                'url': f"https://{self.bucket_name}.s3.{region}.amazonaws.com",
            }
            
        except ClientError as e:
            logger.error(f"Failed to get bucket info: {e}")
            return {'bucket_name': self.bucket_name, 'error': str(e)}


# Convenience functions for common operations
def get_s3_client(bucket_name: Optional[str] = None) -> S3SimpleClient:
    """Get a configured S3 client"""
    return S3SimpleClient(bucket_name)

def upload_file_to_s3(file_path: str, s3_key: str, bucket_name: Optional[str] = None) -> bool:
    """Upload a file to S3 (convenience function)"""
    client = get_s3_client(bucket_name)
    return client.upload_file(file_path, s3_key)

def download_file_from_s3(s3_key: str, local_path: str, bucket_name: Optional[str] = None) -> bool:
    """Download a file from S3 (convenience function)"""
    client = get_s3_client(bucket_name)
    return client.download_file(s3_key, local_path)