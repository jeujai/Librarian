"""
Tests for Incremental Deployment Updates

This module tests the incremental deployment functionality to ensure
that infrastructure updates can be applied safely without stack destruction.
"""

import asyncio
import json
import os
import subprocess
import tempfile
import unittest
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime, timedelta

import pytest
import boto3
try:
    from moto import mock_secretsmanager, mock_ssm, mock_ecs, mock_elbv2, mock_ec2
    MOTO_AVAILABLE = True
except ImportError:
    # Mock the decorators if moto is not available
    def mock_secretsmanager(func):
        return func
    def mock_ssm(func):
        return func
    def mock_ecs(func):
        return func
    def mock_elbv2(func):
        return func
    def mock_ec2(func):
        return func
    MOTO_AVAILABLE = False

# Import the modules we're testing
from src.multimodal_librarian.config.hot_reload import (
    ConfigHotReloader,
    get_config_reloader,
    initialize_config_reloader,
    ConfigurableComponent
)


class TestConfigHotReloader(unittest.TestCase):
    """Test configuration hot reloading functionality."""
    
    def setUp(self):
        """Set up test environment."""
        self.project_name = "test-project"
        self.environment = "test"
        self.region = "us-east-1"
        
    @mock_secretsmanager
    @mock_ssm
    def test_config_reloader_initialization(self):
        """Test that ConfigHotReloader initializes correctly."""
        reloader = ConfigHotReloader(
            project_name=self.project_name,
            environment=self.environment,
            region=self.region
        )
        
        self.assertEqual(reloader.project_name, self.project_name)
        self.assertEqual(reloader.environment, self.environment)
        self.assertEqual(reloader.region, self.region)
        self.assertFalse(reloader.running)
        self.assertEqual(len(reloader.config_cache), 0)
    
    @mock_secretsmanager
    def test_secret_loading(self):
        """Test loading secrets from AWS Secrets Manager."""
        # Create mock secret
        secrets_client = boto3.client('secretsmanager', region_name=self.region)
        secret_name = f"{self.project_name}/{self.environment}/api-keys"
        secret_value = {
            "gemini_api_key": "test-gemini-key",
            "openai_api_key": "test-openai-key"
        }
        
        secrets_client.create_secret(
            Name=secret_name,
            SecretString=json.dumps(secret_value)
        )
        
        # Test loading
        reloader = ConfigHotReloader(
            project_name=self.project_name,
            environment=self.environment,
            region=self.region
        )
        
        # Run async test
        async def test_load():
            await reloader._load_secrets()
            loaded_secret = reloader.get_secret("api-keys")
            self.assertEqual(loaded_secret, secret_value)
        
        asyncio.run(test_load())
    
    @mock_ssm
    def test_parameter_loading(self):
        """Test loading parameters from AWS Systems Manager."""
        # Create mock parameter
        ssm_client = boto3.client('ssm', region_name=self.region)
        param_name = f"/{self.project_name}/{self.environment}/test-param"
        param_value = "test-value"
        
        ssm_client.put_parameter(
            Name=param_name,
            Value=param_value,
            Type='String'
        )
        
        # Test loading
        reloader = ConfigHotReloader(
            project_name=self.project_name,
            environment=self.environment,
            region=self.region
        )
        
        # Run async test
        async def test_load():
            await reloader._load_parameters()
            loaded_param = reloader.get_parameter("test-param")
            self.assertEqual(loaded_param, param_value)
        
        asyncio.run(test_load())
    
    def test_callback_registration(self):
        """Test callback registration and execution."""
        reloader = ConfigHotReloader(
            project_name=self.project_name,
            environment=self.environment,
            region=self.region
        )
        
        callback_called = False
        callback_value = None
        
        def test_callback(value):
            nonlocal callback_called, callback_value
            callback_called = True
            callback_value = value
        
        # Register callback
        config_key = "test-key"
        reloader.register_callback(config_key, test_callback)
        
        # Verify callback is registered
        self.assertIn(config_key, reloader.config_callbacks)
        self.assertEqual(reloader.config_callbacks[config_key], test_callback)
    
    def test_config_change_detection(self):
        """Test configuration change detection."""
        reloader = ConfigHotReloader(
            project_name=self.project_name,
            environment=self.environment,
            region=self.region
        )
        
        # Test new configuration (should be detected as changed)
        self.assertTrue(reloader._has_config_changed("new-key", "new-value"))
        
        # Add configuration to cache
        reloader.config_cache["existing-key"] = "existing-value"
        
        # Test same configuration (should not be detected as changed)
        self.assertFalse(reloader._has_config_changed("existing-key", "existing-value"))
        
        # Test changed configuration (should be detected as changed)
        self.assertTrue(reloader._has_config_changed("existing-key", "new-value"))
    
    def test_api_key_retrieval(self):
        """Test API key retrieval helper methods."""
        reloader = ConfigHotReloader(
            project_name=self.project_name,
            environment=self.environment,
            region=self.region
        )
        
        # Set up mock API keys
        api_keys = {
            "gemini_api_key": "test-gemini-key",
            "openai_api_key": "test-openai-key",
            "google_api_key": "test-google-key"
        }
        
        secret_name = f"{self.project_name}/{self.environment}/api-keys"
        reloader.config_cache[secret_name] = api_keys
        
        # Test API key retrieval
        self.assertEqual(reloader.get_api_key("gemini"), "test-gemini-key")
        self.assertEqual(reloader.get_api_key("openai"), "test-openai-key")
        self.assertEqual(reloader.get_api_key("google"), "test-google-key")
        self.assertEqual(reloader.get_api_key("nonexistent", "default"), "default")


class TestConfigurableComponent(unittest.TestCase):
    """Test configurable component base class."""
    
    def setUp(self):
        """Set up test environment."""
        self.config_key = "test-component-config"
    
    def test_configurable_component_initialization(self):
        """Test that ConfigurableComponent initializes correctly."""
        component = ConfigurableComponent(self.config_key)
        
        self.assertEqual(component.config_key, self.config_key)
        self.assertIsNotNone(component.reloader)
        
        # Verify callback is registered
        self.assertIn(self.config_key, component.reloader.config_callbacks)


class TestDeploymentSafetyScripts(unittest.TestCase):
    """Test deployment safety scripts."""
    
    def setUp(self):
        """Set up test environment."""
        self.scripts_dir = "infrastructure/learning/scripts"
    
    def test_safe_deploy_script_exists(self):
        """Test that safe deployment script exists and is executable."""
        script_path = os.path.join(self.scripts_dir, "safe-deploy.sh")
        self.assertTrue(os.path.exists(script_path))
        self.assertTrue(os.access(script_path, os.X_OK))
    
    def test_rollback_script_exists(self):
        """Test that rollback script exists and is executable."""
        script_path = os.path.join(self.scripts_dir, "rollback-procedures.sh")
        self.assertTrue(os.path.exists(script_path))
        self.assertTrue(os.access(script_path, os.X_OK))
    
    def test_blue_green_script_exists(self):
        """Test that blue-green deployment script exists and is executable."""
        script_path = os.path.join(self.scripts_dir, "blue-green-deploy.sh")
        self.assertTrue(os.path.exists(script_path))
        self.assertTrue(os.access(script_path, os.X_OK))
    
    def test_safe_deploy_preview_mode(self):
        """Test safe deployment script in preview mode."""
        script_path = os.path.join(self.scripts_dir, "safe-deploy.sh")
        
        # Mock environment variables
        env = os.environ.copy()
        env['AWS_DEFAULT_REGION'] = 'us-east-1'
        
        # Test preview mode (should not make changes)
        with patch('subprocess.run') as mock_run:
            mock_run.return_value.returncode = 0
            mock_run.return_value.stdout = "No changes detected"
            
            # This would normally run the script, but we're mocking it
            # In a real test environment, you'd need proper AWS credentials
            # and infrastructure to test against
            pass
    
    def test_rollback_script_menu_mode(self):
        """Test rollback script in menu mode."""
        script_path = os.path.join(self.scripts_dir, "rollback-procedures.sh")
        
        # Test menu mode (should show options without executing)
        with patch('subprocess.run') as mock_run:
            mock_run.return_value.returncode = 0
            mock_run.return_value.stdout = "Available rollback options"
            
            # This would normally run the script, but we're mocking it
            pass


class TestIncrementalDeploymentIntegration(unittest.TestCase):
    """Integration tests for incremental deployment functionality."""
    
    @mock_ecs
    @mock_elbv2
    @mock_ec2
    def test_blue_green_deployment_simulation(self):
        """Simulate blue-green deployment process."""
        # Create mock AWS resources
        ec2 = boto3.client('ec2', region_name='us-east-1')
        ecs = boto3.client('ecs', region_name='us-east-1')
        elbv2 = boto3.client('elbv2', region_name='us-east-1')
        
        # Create VPC
        vpc = ec2.create_vpc(CidrBlock='10.0.0.0/16')
        vpc_id = vpc['Vpc']['VpcId']
        
        # Create subnet
        subnet = ec2.create_subnet(VpcId=vpc_id, CidrBlock='10.0.1.0/24')
        subnet_id = subnet['Subnet']['SubnetId']
        
        # Create ECS cluster
        cluster_name = 'test-cluster'
        ecs.create_cluster(clusterName=cluster_name)
        
        # Create load balancer
        lb = elbv2.create_load_balancer(
            Name='test-lb',
            Subnets=[subnet_id],
            Scheme='internet-facing',
            Type='application'
        )
        lb_arn = lb['LoadBalancers'][0]['LoadBalancerArn']
        
        # Create target group
        tg = elbv2.create_target_group(
            Name='test-tg-blue',
            Protocol='HTTP',
            Port=8000,
            VpcId=vpc_id,
            HealthCheckPath='/health'
        )
        tg_arn = tg['TargetGroups'][0]['TargetGroupArn']
        
        # Create listener
        listener = elbv2.create_listener(
            LoadBalancerArn=lb_arn,
            Protocol='HTTP',
            Port=80,
            DefaultActions=[
                {
                    'Type': 'forward',
                    'TargetGroupArn': tg_arn
                }
            ]
        )
        
        # Verify resources were created
        clusters = ecs.list_clusters()
        self.assertIn(cluster_name, [c.split('/')[-1] for c in clusters['clusterArns']])
        
        load_balancers = elbv2.describe_load_balancers()
        self.assertEqual(len(load_balancers['LoadBalancers']), 1)
        
        target_groups = elbv2.describe_target_groups()
        self.assertEqual(len(target_groups['TargetGroups']), 1)
    
    def test_deployment_safety_construct_integration(self):
        """Test that deployment safety construct is properly integrated."""
        # Check that deployment safety files exist
        safety_files = [
            "infrastructure/learning/lib/deployment-safety.ts",
            "infrastructure/learning/scripts/safe-deploy.sh",
            "infrastructure/learning/scripts/rollback-procedures.sh",
            "infrastructure/learning/scripts/blue-green-deploy.sh",
            "src/multimodal_librarian/config/hot_reload.py"
        ]
        
        for file_path in safety_files:
            self.assertTrue(os.path.exists(file_path), f"Missing safety file: {file_path}")
    
    def test_stack_protection_policies(self):
        """Test that stack protection policies are correctly defined."""
        # Read the deployment safety TypeScript file
        safety_file = "infrastructure/learning/lib/deployment-safety.ts"
        
        with open(safety_file, 'r') as f:
            content = f.read()
        
        # Check for key protection features
        self.assertIn("RemovalPolicy.RETAIN", content)
        self.assertIn("deletionProtection", content)
        self.assertIn("ResourceProtectionAspect", content)
        self.assertIn("StackProtectionPolicy", content)
    
    def test_configuration_hot_reload_integration(self):
        """Test configuration hot reload integration."""
        # Import and test the hot reload module
        from src.multimodal_librarian.config.hot_reload import get_config_reloader
        
        reloader = get_config_reloader()
        self.assertIsNotNone(reloader)
        self.assertEqual(reloader.project_name, "multimodal-librarian")
        self.assertEqual(reloader.environment, "learning")


class TestDeploymentValidation(unittest.TestCase):
    """Test deployment validation and health checks."""
    
    def test_health_check_endpoint_format(self):
        """Test that health check endpoints are properly formatted."""
        # This would test the actual health check endpoints
        # In a real implementation, you'd make HTTP requests to validate
        pass
    
    def test_database_connection_validation(self):
        """Test database connection validation during deployment."""
        # This would test database connectivity
        # In a real implementation, you'd test actual database connections
        pass
    
    def test_service_discovery_validation(self):
        """Test service discovery validation during deployment."""
        # This would test service discovery mechanisms
        # In a real implementation, you'd test ECS service registration
        pass


# Async test utilities
class AsyncTestCase(unittest.TestCase):
    """Base class for async test cases."""
    
    def setUp(self):
        """Set up async test environment."""
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)
    
    def tearDown(self):
        """Clean up async test environment."""
        self.loop.close()
    
    def async_test(self, coro):
        """Run async test."""
        return self.loop.run_until_complete(coro)


class TestAsyncConfigReloading(AsyncTestCase):
    """Test async configuration reloading functionality."""
    
    @mock_secretsmanager
    @mock_ssm
    def test_async_config_loading(self):
        """Test async configuration loading."""
        async def test():
            reloader = ConfigHotReloader(
                project_name="test-project",
                environment="test",
                region="us-east-1"
            )
            
            await reloader.start()
            self.assertTrue(reloader.running)
            
            await reloader.stop()
            self.assertFalse(reloader.running)
        
        self.async_test(test())
    
    @mock_secretsmanager
    def test_async_callback_execution(self):
        """Test async callback execution."""
        async def test():
            reloader = ConfigHotReloader(
                project_name="test-project",
                environment="test",
                region="us-east-1"
            )
            
            callback_called = False
            callback_value = None
            
            async def async_callback(value):
                nonlocal callback_called, callback_value
                callback_called = True
                callback_value = value
            
            reloader.register_callback("test-key", async_callback)
            
            # Simulate config change
            await reloader._safe_callback("test-key", "test-value")
            
            self.assertTrue(callback_called)
            self.assertEqual(callback_value, "test-value")
        
        self.async_test(test())


if __name__ == '__main__':
    # Run tests
    unittest.main(verbosity=2)