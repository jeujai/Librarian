"""
AWS-specific Milvus configuration for learning deployment.

This module provides configuration and utilities for connecting to Milvus
deployed on AWS ECS, with service discovery and basic AWS integration.
"""

import os
import logging
from typing import Optional, Dict, Any
import boto3
from botocore.exceptions import ClientError, NoCredentialsError

logger = logging.getLogger(__name__)


class AWSMilvusConfig:
    """
    AWS-specific configuration for Milvus vector database.
    
    This class handles:
    - Service discovery for ECS-deployed Milvus
    - AWS-specific connection parameters
    - Health checking and failover
    - Basic monitoring integration
    """
    
    def __init__(self, 
                 cluster_name: str = "multimodal-librarian-full-ml",
                 service_name: str = "milvus-learning",
                 region: str = "us-east-1"):
        """
        Initialize AWS Milvus configuration.
        
        Args:
            cluster_name: ECS cluster name where Milvus is deployed
            service_name: ECS service name for Milvus
            region: AWS region
        """
        self.cluster_name = cluster_name
        self.service_name = service_name
        self.region = region
        
        # Default configuration
        self.default_host = "milvus.milvus.local"
        self.default_port = 19530
        self.collection_name = "knowledge_chunks"
        
        # AWS clients
        self._ecs_client = None
        self._cloudwatch_client = None
        
    @property
    def ecs_client(self):
        """Get ECS client with lazy initialization."""
        if self._ecs_client is None:
            try:
                self._ecs_client = boto3.client('ecs', region_name=self.region)
            except NoCredentialsError:
                logger.warning("AWS credentials not available, using default configuration")
        return self._ecs_client
    
    @property
    def cloudwatch_client(self):
        """Get CloudWatch client with lazy initialization."""
        if self._cloudwatch_client is None:
            try:
                self._cloudwatch_client = boto3.client('cloudwatch', region_name=self.region)
            except NoCredentialsError:
                logger.warning("AWS credentials not available, monitoring disabled")
        return self._cloudwatch_client
    
    def get_milvus_endpoint(self) -> tuple[str, int]:
        """
        Get Milvus endpoint using service discovery or environment variables.
        
        Returns:
            Tuple of (host, port)
        """
        # First, try environment variables (for local development)
        env_host = os.getenv('MILVUS_HOST')
        env_port = os.getenv('MILVUS_PORT')
        
        if env_host and env_port:
            try:\n                port = int(env_port)\n                logger.info(f\"Using Milvus endpoint from environment: {env_host}:{port}\")\n                return env_host, port\n            except ValueError:\n                logger.warning(f\"Invalid MILVUS_PORT in environment: {env_port}\")\n        \n        # Try AWS service discovery\n        aws_endpoint = self._discover_milvus_service()\n        if aws_endpoint:\n            return aws_endpoint\n        \n        # Fall back to default\n        logger.info(f\"Using default Milvus endpoint: {self.default_host}:{self.default_port}\")\n        return self.default_host, self.default_port\n    \n    def _discover_milvus_service(self) -> Optional[tuple[str, int]]:\n        \"\"\"Discover Milvus service endpoint using AWS ECS service discovery.\"\"\"\n        if not self.ecs_client:\n            return None\n        \n        try:\n            # Get service details\n            response = self.ecs_client.describe_services(\n                cluster=self.cluster_name,\n                services=[self.service_name]\n            )\n            \n            services = response.get('services', [])\n            if not services:\n                logger.warning(f\"Milvus service '{self.service_name}' not found in cluster '{self.cluster_name}'\")\n                return None\n            \n            service = services[0]\n            \n            # Check service status\n            if service.get('status') != 'ACTIVE':\n                logger.warning(f\"Milvus service is not active: {service.get('status')}\")\n                return None\n            \n            # Check running count\n            running_count = service.get('runningCount', 0)\n            if running_count == 0:\n                logger.warning(\"No running Milvus tasks found\")\n                return None\n            \n            logger.info(f\"Found {running_count} running Milvus tasks\")\n            \n            # For learning deployment, use service discovery name\n            # In production, you might want to use a load balancer\n            return self.default_host, self.default_port\n            \n        except ClientError as e:\n            logger.error(f\"Failed to discover Milvus service: {e}\")\n            return None\n    \n    def get_connection_config(self) -> Dict[str, Any]:\n        \"\"\"Get complete Milvus connection configuration.\"\"\"\n        host, port = self.get_milvus_endpoint()\n        \n        return {\n            'host': host,\n            'port': port,\n            'collection_name': self.collection_name,\n            'timeout': 30,  # Connection timeout\n            'retry_attempts': 3,\n            'retry_delay': 5,  # Seconds between retries\n        }\n    \n    def check_service_health(self) -> Dict[str, Any]:\n        \"\"\"Check Milvus service health using AWS ECS.\"\"\"\n        health_status = {\n            'healthy': False,\n            'service_status': 'unknown',\n            'running_tasks': 0,\n            'desired_tasks': 0,\n            'last_deployment': None,\n            'errors': []\n        }\n        \n        if not self.ecs_client:\n            health_status['errors'].append('AWS ECS client not available')\n            return health_status\n        \n        try:\n            # Get service details\n            response = self.ecs_client.describe_services(\n                cluster=self.cluster_name,\n                services=[self.service_name]\n            )\n            \n            services = response.get('services', [])\n            if not services:\n                health_status['errors'].append(f\"Service '{self.service_name}' not found\")\n                return health_status\n            \n            service = services[0]\n            \n            # Update health status\n            health_status['service_status'] = service.get('status', 'unknown')\n            health_status['running_tasks'] = service.get('runningCount', 0)\n            health_status['desired_tasks'] = service.get('desiredCount', 0)\n            \n            # Check deployments\n            deployments = service.get('deployments', [])\n            if deployments:\n                primary_deployment = next(\n                    (d for d in deployments if d.get('status') == 'PRIMARY'),\n                    deployments[0]\n                )\n                health_status['last_deployment'] = {\n                    'status': primary_deployment.get('status'),\n                    'created_at': primary_deployment.get('createdAt'),\n                    'task_definition': primary_deployment.get('taskDefinition')\n                }\n            \n            # Determine overall health\n            health_status['healthy'] = (\n                health_status['service_status'] == 'ACTIVE' and\n                health_status['running_tasks'] > 0 and\n                health_status['running_tasks'] == health_status['desired_tasks']\n            )\n            \n            # Check for service events (errors)\n            events = service.get('events', [])\n            recent_errors = [\n                event['message'] for event in events[:5]\n                if 'error' in event.get('message', '').lower() or\n                   'failed' in event.get('message', '').lower()\n            ]\n            \n            if recent_errors:\n                health_status['errors'].extend(recent_errors)\n            \n        except ClientError as e:\n            health_status['errors'].append(f\"AWS API error: {e}\")\n        \n        return health_status\n    \n    def get_service_metrics(self, hours: int = 1) -> Dict[str, Any]:\n        \"\"\"Get basic CloudWatch metrics for Milvus service.\"\"\"\n        metrics = {\n            'cpu_utilization': None,\n            'memory_utilization': None,\n            'task_count': None,\n            'errors': []\n        }\n        \n        if not self.cloudwatch_client:\n            metrics['errors'].append('CloudWatch client not available')\n            return metrics\n        \n        try:\n            from datetime import datetime, timedelta\n            \n            end_time = datetime.utcnow()\n            start_time = end_time - timedelta(hours=hours)\n            \n            # Get CPU utilization\n            try:\n                cpu_response = self.cloudwatch_client.get_metric_statistics(\n                    Namespace='AWS/ECS',\n                    MetricName='CPUUtilization',\n                    Dimensions=[\n                        {'Name': 'ServiceName', 'Value': self.service_name},\n                        {'Name': 'ClusterName', 'Value': self.cluster_name}\n                    ],\n                    StartTime=start_time,\n                    EndTime=end_time,\n                    Period=300,  # 5 minutes\n                    Statistics=['Average']\n                )\n                \n                if cpu_response['Datapoints']:\n                    latest_cpu = sorted(cpu_response['Datapoints'], \n                                      key=lambda x: x['Timestamp'])[-1]\n                    metrics['cpu_utilization'] = latest_cpu['Average']\n            \n            except ClientError as e:\n                metrics['errors'].append(f\"Failed to get CPU metrics: {e}\")\n            \n            # Get Memory utilization\n            try:\n                memory_response = self.cloudwatch_client.get_metric_statistics(\n                    Namespace='AWS/ECS',\n                    MetricName='MemoryUtilization',\n                    Dimensions=[\n                        {'Name': 'ServiceName', 'Value': self.service_name},\n                        {'Name': 'ClusterName', 'Value': self.cluster_name}\n                    ],\n                    StartTime=start_time,\n                    EndTime=end_time,\n                    Period=300,\n                    Statistics=['Average']\n                )\n                \n                if memory_response['Datapoints']:\n                    latest_memory = sorted(memory_response['Datapoints'], \n                                         key=lambda x: x['Timestamp'])[-1]\n                    metrics['memory_utilization'] = latest_memory['Average']\n            \n            except ClientError as e:\n                metrics['errors'].append(f\"Failed to get memory metrics: {e}\")\n        \n        except Exception as e:\n            metrics['errors'].append(f\"Unexpected error getting metrics: {e}\")\n        \n        return metrics\n    \n    def restart_service(self) -> bool:\n        \"\"\"Restart Milvus service (force new deployment).\"\"\"\n        if not self.ecs_client:\n            logger.error(\"ECS client not available for service restart\")\n            return False\n        \n        try:\n            response = self.ecs_client.update_service(\n                cluster=self.cluster_name,\n                service=self.service_name,\n                forceNewDeployment=True\n            )\n            \n            logger.info(f\"Initiated Milvus service restart: {response['service']['serviceName']}\")\n            return True\n            \n        except ClientError as e:\n            logger.error(f\"Failed to restart Milvus service: {e}\")\n            return False\n\n\ndef get_aws_milvus_config() -> AWSMilvusConfig:\n    \"\"\"Get AWS Milvus configuration instance.\"\"\"\n    cluster_name = os.getenv('ECS_CLUSTER_NAME', 'multimodal-librarian-full-ml')\n    service_name = os.getenv('MILVUS_SERVICE_NAME', 'milvus-learning')\n    region = os.getenv('AWS_REGION', 'us-east-1')\n    \n    return AWSMilvusConfig(\n        cluster_name=cluster_name,\n        service_name=service_name,\n        region=region\n    )\n\n\ndef create_aws_vector_store(collection_name: Optional[str] = None):\n    \"\"\"Create VectorStore instance configured for AWS deployment.\"\"\"\n    from ..components.vector_store.vector_store import VectorStore\n    \n    # Get AWS configuration\n    aws_config = get_aws_milvus_config()\n    connection_config = aws_config.get_connection_config()\n    \n    # Override environment variables for VectorStore\n    os.environ['MILVUS_HOST'] = connection_config['host']\n    os.environ['MILVUS_PORT'] = str(connection_config['port'])\n    \n    if collection_name:\n        os.environ['MILVUS_COLLECTION_NAME'] = collection_name\n    \n    # Create and return VectorStore instance\n    vector_store = VectorStore(collection_name or connection_config['collection_name'])\n    \n    # Add AWS-specific attributes\n    vector_store._aws_config = aws_config\n    vector_store._connection_config = connection_config\n    \n    return vector_store\n\n\ndef check_milvus_health() -> Dict[str, Any]:\n    \"\"\"Check Milvus health from AWS perspective.\"\"\"\n    aws_config = get_aws_milvus_config()\n    \n    # Get service health\n    service_health = aws_config.check_service_health()\n    \n    # Get metrics\n    metrics = aws_config.get_service_metrics()\n    \n    # Combine results\n    health_report = {\n        'timestamp': datetime.now().isoformat(),\n        'service': service_health,\n        'metrics': metrics,\n        'endpoint': aws_config.get_milvus_endpoint(),\n        'overall_healthy': service_health['healthy'] and not service_health['errors']\n    }\n    \n    return health_report\n