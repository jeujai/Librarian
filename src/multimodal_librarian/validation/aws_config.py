"""
AWS SDK configuration and session management for the validation framework.

This module provides centralized AWS configuration, credential management,
and session handling with comprehensive error handling and retry logic.
"""

import logging
import time
from typing import Dict, Any, Optional
import boto3
from botocore.config import Config
from botocore.exceptions import ClientError, NoCredentialsError, BotoCoreError
from botocore.retries import adaptive


class AWSConfigManager:
    """Manages AWS configuration and client creation for validation framework."""
    
    def __init__(self, region: str = "us-east-1", max_retries: int = 3):
        """
        Initialize AWS configuration manager.
        
        Args:
            region: AWS region to use
            max_retries: Maximum number of retries for AWS API calls
        """
        self.region = region
        self.max_retries = max_retries
        self.logger = logging.getLogger(__name__)
        
        # Configure boto3 with retry strategy
        self.boto_config = Config(
            region_name=region,
            retries={
                'max_attempts': max_retries,
                'mode': 'adaptive'
            },
            max_pool_connections=50
        )
        
        self._session = None
        self._clients = {}
        self._account_id = None
        
    @property
    def session(self) -> boto3.Session:
        """Get or create AWS session with validation."""
        if self._session is None:
            self._session = self._create_validated_session()
        return self._session
    
    def _create_validated_session(self) -> boto3.Session:
        """Create and validate AWS session."""
        try:
            session = boto3.Session(region_name=self.region)
            
            # Validate credentials by getting caller identity
            sts_client = session.client('sts', config=self.boto_config)
            response = sts_client.get_caller_identity()
            self._account_id = response['Account']
            
            self.logger.info(f"AWS session validated for account {self._account_id} in region {self.region}")
            return session
            
        except NoCredentialsError:
            error_msg = (
                "AWS credentials not found. Please configure credentials using one of:\n"
                "1. AWS CLI: aws configure\n"
                "2. Environment variables: AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY\n"
                "3. IAM roles (for EC2/ECS)\n"
                "4. AWS credentials file"
            )
            self.logger.error(error_msg)
            raise AWSConfigurationError(error_msg)
            
        except ClientError as e:
            error_code = e.response['Error']['Code']
            if error_code == 'InvalidUserID.NotFound':
                error_msg = "AWS credentials are invalid or expired"
            else:
                error_msg = f"AWS credential validation failed: {e.response['Error']['Message']}"
            
            self.logger.error(error_msg)
            raise AWSConfigurationError(error_msg)
            
        except Exception as e:
            error_msg = f"Failed to create AWS session: {str(e)}"
            self.logger.error(error_msg)
            raise AWSConfigurationError(error_msg)
    
    def get_client(self, service_name: str, **kwargs):
        """
        Get AWS service client with caching and error handling.
        
        Args:
            service_name: AWS service name (e.g., 'iam', 'ecs', 'elbv2')
            **kwargs: Additional client configuration
            
        Returns:
            Configured AWS service client
        """
        client_key = f"{service_name}_{hash(str(sorted(kwargs.items())))}"
        
        if client_key not in self._clients:
            try:
                # Merge provided config with default config
                client_config = self.boto_config.merge(Config(**kwargs)) if kwargs else self.boto_config
                
                client = self.session.client(service_name, config=client_config)
                self._clients[client_key] = client
                
                self.logger.debug(f"Created {service_name} client")
                
            except Exception as e:
                error_msg = f"Failed to create {service_name} client: {str(e)}"
                self.logger.error(error_msg)
                raise AWSConfigurationError(error_msg)
        
        return self._clients[client_key]
    
    def get_account_id(self) -> str:
        """Get AWS account ID."""
        if self._account_id is None:
            # Trigger session creation to get account ID
            _ = self.session
        return self._account_id
    
    def test_service_access(self, service_name: str, test_operation: str = None) -> bool:
        """
        Test access to a specific AWS service.
        
        Args:
            service_name: AWS service to test
            test_operation: Specific operation to test (optional)
            
        Returns:
            True if service is accessible, False otherwise
        """
        try:
            client = self.get_client(service_name)
            
            # Service-specific test operations
            if service_name == 'iam':
                client.get_account_summary()
            elif service_name == 'ecs':
                client.list_clusters(maxResults=1)
            elif service_name == 'elbv2':
                client.describe_load_balancers(PageSize=1)
            elif service_name == 'secretsmanager':
                client.list_secrets(MaxResults=1)
            elif service_name == 'acm':
                client.list_certificates(MaxItems=1)
            elif test_operation:
                # Custom test operation
                getattr(client, test_operation)()
            else:
                # Generic test - just creating client is sufficient
                pass
            
            self.logger.debug(f"Successfully tested access to {service_name}")
            return True
            
        except ClientError as e:
            error_code = e.response['Error']['Code']
            if error_code in ['AccessDenied', 'UnauthorizedOperation']:
                self.logger.warning(f"Access denied to {service_name}: {e.response['Error']['Message']}")
            else:
                self.logger.error(f"Error testing {service_name}: {e.response['Error']['Message']}")
            return False
            
        except Exception as e:
            self.logger.error(f"Unexpected error testing {service_name}: {str(e)}")
            return False
    
    def get_service_availability(self) -> Dict[str, bool]:
        """
        Test availability of all services used by validation framework.
        
        Returns:
            Dictionary mapping service names to availability status
        """
        services = {
            'iam': 'IAM (Identity and Access Management)',
            'ecs': 'ECS (Elastic Container Service)', 
            'elbv2': 'ELBv2 (Application Load Balancer)',
            'secretsmanager': 'Secrets Manager',
            'acm': 'ACM (Certificate Manager)'
        }
        
        availability = {}
        for service, description in services.items():
            self.logger.info(f"Testing access to {description}...")
            availability[service] = self.test_service_access(service)
        
        return availability
    
    def validate_environment(self) -> Dict[str, Any]:
        """
        Validate the AWS environment for deployment validation.
        
        Returns:
            Dictionary with environment validation results
        """
        results = {
            'account_id': self.get_account_id(),
            'region': self.region,
            'credentials_valid': True,
            'service_availability': self.get_service_availability(),
            'validation_timestamp': time.time()
        }
        
        # Check if all required services are available
        required_services = ['iam', 'ecs', 'elbv2', 'secretsmanager']
        unavailable_services = [
            service for service in required_services 
            if not results['service_availability'].get(service, False)
        ]
        
        results['all_services_available'] = len(unavailable_services) == 0
        results['unavailable_services'] = unavailable_services
        
        if unavailable_services:
            self.logger.warning(f"Some required services are not available: {unavailable_services}")
        else:
            self.logger.info("All required AWS services are available")
        
        return results


class AWSConfigurationError(Exception):
    """Exception raised for AWS configuration issues."""
    pass


# Global AWS configuration manager instance
_aws_config_manager = None


def get_aws_config_manager(region: str = "us-east-1", max_retries: int = 3) -> AWSConfigManager:
    """
    Get global AWS configuration manager instance.
    
    Args:
        region: AWS region
        max_retries: Maximum retries for AWS calls
        
    Returns:
        AWSConfigManager instance
    """
    global _aws_config_manager
    
    if _aws_config_manager is None or _aws_config_manager.region != region:
        _aws_config_manager = AWSConfigManager(region=region, max_retries=max_retries)
    
    return _aws_config_manager