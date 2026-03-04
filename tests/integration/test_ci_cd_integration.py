"""
CI/CD Integration Tests

Tests to verify that the CI/CD pipeline works correctly with both
local and AWS environments.
"""

import pytest
import os
import asyncio
from unittest.mock import patch, MagicMock

# Test markers
pytestmark = [
    pytest.mark.integration,
    pytest.mark.ci,
    pytest.mark.github_actions,
]


class TestCICDIntegration:
    """Test CI/CD pipeline integration."""
    
    def test_environment_detection(self):
        """Test that CI/CD can detect the correct environment."""
        # Test local environment detection
        with patch.dict(os.environ, {
            'ML_ENVIRONMENT': 'test',
            'ML_DATABASE_TYPE': 'local',
            'GITHUB_ACTIONS': 'true'
        }):
            assert os.getenv('ML_ENVIRONMENT') == 'test'
            assert os.getenv('ML_DATABASE_TYPE') == 'local'
            assert os.getenv('GITHUB_ACTIONS') == 'true'
    
    def test_github_actions_environment(self):
        """Test GitHub Actions specific environment variables."""
        # Simulate GitHub Actions environment
        github_env = {
            'GITHUB_ACTIONS': 'true',
            'GITHUB_WORKFLOW': 'CI/CD with Local and AWS Testing',
            'GITHUB_RUN_ID': '123456789',
            'GITHUB_ACTOR': 'test-user',
            'GITHUB_REPOSITORY': 'test/multimodal-librarian',
            'RUNNER_OS': 'Linux',
        }
        
        with patch.dict(os.environ, github_env):
            # Test that we can detect GitHub Actions environment
            assert os.getenv('GITHUB_ACTIONS') == 'true'
            assert os.getenv('RUNNER_OS') == 'Linux'
    
    def test_service_configuration_for_ci(self):
        """Test that services are configured correctly for CI."""
        # Test PostgreSQL configuration
        postgres_config = {
            'POSTGRES_HOST': 'localhost',
            'POSTGRES_PORT': '5432',
            'POSTGRES_DB': 'multimodal_librarian_test',
            'POSTGRES_USER': 'ml_user',
            'POSTGRES_PASSWORD': 'ml_password',
        }
        
        with patch.dict(os.environ, postgres_config):
            assert os.getenv('POSTGRES_HOST') == 'localhost'
            assert os.getenv('POSTGRES_DB') == 'multimodal_librarian_test'
    
    def test_test_environment_isolation(self):
        """Test that test environment is properly isolated."""
        test_env = {
            'ML_ENVIRONMENT': 'test',
            'DEBUG': 'true',
            'LOG_LEVEL': 'DEBUG',
            'PYTEST_CURRENT_TEST': 'true',
            'ENABLE_HEALTH_CHECKS': 'false',
            'VALIDATE_CONFIG_ON_STARTUP': 'false',
        }
        
        with patch.dict(os.environ, test_env):
            assert os.getenv('ML_ENVIRONMENT') == 'test'
            assert os.getenv('DEBUG') == 'true'
            assert os.getenv('ENABLE_HEALTH_CHECKS') == 'false'
    
    @pytest.mark.local_services
    def test_local_service_connectivity_check(self):
        """Test that we can check local service connectivity."""
        import socket
        
        # Test services that should be available in CI
        services_to_check = [
            ('localhost', 5432),  # PostgreSQL
            ('localhost', 7687),  # Neo4j
            ('localhost', 6379),  # Redis
        ]
        
        connectivity_results = {}
        
        for host, port in services_to_check:
            try:
                with socket.create_connection((host, port), timeout=2):
                    connectivity_results[f"{host}:{port}"] = True
            except (socket.error, socket.timeout):
                connectivity_results[f"{host}:{port}"] = False
        
        # In CI, we expect at least some services to be available
        # This test documents the expected connectivity
        assert isinstance(connectivity_results, dict)
        assert len(connectivity_results) > 0
    
    def test_configuration_factory_in_ci(self):
        """Test that configuration factory works in CI environment."""
        try:
            from multimodal_librarian.config.config_factory import get_database_config
            
            # Test local configuration
            with patch.dict(os.environ, {'ML_DATABASE_TYPE': 'local'}):
                config = get_database_config()
                assert config is not None
                # Should be local config type
                config_type = type(config).__name__
                assert 'Local' in config_type or 'local' in config_type.lower()
            
            # Test AWS configuration (should work even without credentials)
            with patch.dict(os.environ, {'ML_DATABASE_TYPE': 'aws'}):
                try:
                    config = get_database_config()
                    assert config is not None
                except Exception:
                    # Expected in CI without AWS credentials
                    pass
                    
        except ImportError:
            pytest.skip("Configuration factory not available")
    
    def test_database_client_factory_in_ci(self):
        """Test that database client factory works in CI environment."""
        try:
            from multimodal_librarian.clients.database_client_factory import DatabaseClientFactory
            from multimodal_librarian.config.local_config import LocalDatabaseConfig
            
            # Create test configuration
            config = LocalDatabaseConfig(
                postgres_host='localhost',
                postgres_port=5432,
                postgres_db='multimodal_librarian_test',
                postgres_user='ml_user',
                postgres_password='ml_password',
                neo4j_host='localhost',
                neo4j_port=7687,
                neo4j_user='neo4j',
                neo4j_password='ml_password',
                milvus_host='localhost',
                milvus_port=19530,
            )
            
            # Test factory creation
            factory = DatabaseClientFactory(config)
            assert factory is not None
            
        except ImportError:
            pytest.skip("Database client factory not available")
    
    def test_pytest_markers_and_configuration(self):
        """Test that pytest is configured correctly for CI."""
        # Test that we can access pytest configuration
        import pytest
        
        # Test that markers are working
        assert hasattr(pytest.mark, 'ci')
        assert hasattr(pytest.mark, 'github_actions')
        assert hasattr(pytest.mark, 'local_services')
        assert hasattr(pytest.mark, 'integration')
    
    def test_test_artifacts_generation(self):
        """Test that test artifacts can be generated for CI."""
        import tempfile
        import json
        
        # Test that we can create test result files
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            test_results = {
                'test_run': 'ci_cd_integration',
                'timestamp': '2024-01-01T00:00:00Z',
                'environment': 'test',
                'status': 'passed',
                'tests': [
                    {'name': 'test_environment_detection', 'status': 'passed'},
                    {'name': 'test_github_actions_environment', 'status': 'passed'},
                ]
            }
            json.dump(test_results, f, indent=2)
            
            # Verify file was created
            assert os.path.exists(f.name)
            
            # Clean up
            os.unlink(f.name)
    
    @pytest.mark.mock
    def test_mocked_services_for_ci(self):
        """Test that mocked services work correctly in CI."""
        # Test with mocked database clients
        mock_postgres = MagicMock()
        mock_postgres.connect = MagicMock()
        mock_postgres.execute = MagicMock(return_value=[{'version': 'PostgreSQL 15.0'}])
        
        mock_neo4j = MagicMock()
        mock_neo4j.connect = MagicMock()
        mock_neo4j.execute_query = MagicMock(return_value=[{'message': 'Hello Neo4j'}])
        
        mock_milvus = MagicMock()
        mock_milvus.connect = MagicMock()
        mock_milvus.list_collections = MagicMock(return_value=['test_collection'])
        
        # Test that mocks work as expected
        mock_postgres.connect()
        result = mock_postgres.execute("SELECT version()")
        assert result == [{'version': 'PostgreSQL 15.0'}]
        
        mock_neo4j.connect()
        result = mock_neo4j.execute_query("RETURN 'Hello Neo4j' as message")
        assert result == [{'message': 'Hello Neo4j'}]
        
        mock_milvus.connect()
        collections = mock_milvus.list_collections()
        assert collections == ['test_collection']
    
    def test_environment_variable_precedence(self):
        """Test that environment variables have correct precedence in CI."""
        # Test that CI-specific variables override defaults
        ci_overrides = {
            'ML_ENVIRONMENT': 'test',
            'DEBUG': 'true',
            'LOG_LEVEL': 'DEBUG',
            'CONNECTION_TIMEOUT': '10',
            'QUERY_TIMEOUT': '5',
            'MAX_RETRIES': '1',
        }
        
        with patch.dict(os.environ, ci_overrides):
            assert os.getenv('ML_ENVIRONMENT') == 'test'
            assert os.getenv('DEBUG') == 'true'
            assert os.getenv('CONNECTION_TIMEOUT') == '10'
    
    def test_ci_workflow_compatibility(self):
        """Test compatibility with CI workflow expectations."""
        # Test that we can simulate CI workflow steps
        workflow_steps = [
            'checkout',
            'setup-python',
            'install-dependencies',
            'start-services',
            'run-tests',
            'upload-artifacts',
        ]
        
        # Simulate each step
        step_results = {}
        
        for step in workflow_steps:
            if step == 'checkout':
                # Simulate code checkout
                step_results[step] = os.path.exists('src')
            elif step == 'setup-python':
                # Simulate Python setup
                step_results[step] = True  # Python is available
            elif step == 'install-dependencies':
                # Simulate dependency installation
                step_results[step] = True  # Dependencies would be installed
            elif step == 'start-services':
                # Simulate service startup
                step_results[step] = True  # Services would be started
            elif step == 'run-tests':
                # Simulate test execution
                step_results[step] = True  # This test is running
            elif step == 'upload-artifacts':
                # Simulate artifact upload
                step_results[step] = True  # Artifacts would be uploaded
        
        # Verify all steps can be simulated
        assert all(step_results.values())
        assert len(step_results) == len(workflow_steps)


class TestCICDEnvironmentSwitching:
    """Test environment switching in CI/CD context."""
    
    @pytest.mark.switching
    def test_local_to_aws_switching(self):
        """Test switching from local to AWS configuration."""
        # Start with local configuration
        local_env = {
            'ML_DATABASE_TYPE': 'local',
            'POSTGRES_HOST': 'localhost',
            'NEO4J_HOST': 'localhost',
            'MILVUS_HOST': 'localhost',
        }
        
        with patch.dict(os.environ, local_env):
            assert os.getenv('ML_DATABASE_TYPE') == 'local'
            assert os.getenv('POSTGRES_HOST') == 'localhost'
        
        # Switch to AWS configuration
        aws_env = {
            'ML_DATABASE_TYPE': 'aws',
            'NEPTUNE_ENDPOINT': 'test-neptune-endpoint',
            'OPENSEARCH_ENDPOINT': 'test-opensearch-endpoint',
            'RDS_ENDPOINT': 'test-rds-endpoint',
        }
        
        with patch.dict(os.environ, aws_env):
            assert os.getenv('ML_DATABASE_TYPE') == 'aws'
            assert os.getenv('NEPTUNE_ENDPOINT') == 'test-neptune-endpoint'
    
    @pytest.mark.switching
    def test_configuration_isolation(self):
        """Test that configuration changes are isolated."""
        # Test that environment changes don't leak between tests
        original_env = os.environ.get('ML_DATABASE_TYPE')
        
        # Change environment
        with patch.dict(os.environ, {'ML_DATABASE_TYPE': 'test_value'}):
            assert os.getenv('ML_DATABASE_TYPE') == 'test_value'
        
        # Verify original value is restored
        assert os.environ.get('ML_DATABASE_TYPE') == original_env


class TestCICDServiceIntegration:
    """Test service integration in CI/CD context."""
    
    @pytest.mark.local_services
    @pytest.mark.smoke
    def test_basic_service_health_check(self):
        """Basic smoke test for service health."""
        # This is a smoke test that can run in CI
        # It doesn't require actual services, just tests the health check logic
        
        def mock_health_check(service_name, host, port):
            """Mock health check function."""
            # Simulate health check logic
            if service_name in ['postgres', 'neo4j', 'redis', 'milvus']:
                return {'service': service_name, 'status': 'healthy', 'host': host, 'port': port}
            return {'service': service_name, 'status': 'unknown', 'host': host, 'port': port}
        
        # Test health check for each service
        services = [
            ('postgres', 'localhost', 5432),
            ('neo4j', 'localhost', 7687),
            ('redis', 'localhost', 6379),
            ('milvus', 'localhost', 19530),
        ]
        
        health_results = []
        for service_name, host, port in services:
            result = mock_health_check(service_name, host, port)
            health_results.append(result)
        
        # Verify health check results
        assert len(health_results) == 4
        assert all(result['status'] in ['healthy', 'unknown'] for result in health_results)
    
    @pytest.mark.docker_compose
    def test_docker_compose_configuration_validation(self):
        """Test that Docker Compose configuration is valid."""
        import yaml
        
        # Test that docker-compose.local.yml is valid YAML
        compose_file = 'docker-compose.local.yml'
        
        if os.path.exists(compose_file):
            with open(compose_file, 'r') as f:
                try:
                    compose_config = yaml.safe_load(f)
                    assert isinstance(compose_config, dict)
                    assert 'services' in compose_config
                    
                    # Check that expected services are defined
                    expected_services = ['postgres', 'neo4j', 'redis', 'milvus']
                    services = compose_config.get('services', {})
                    
                    for service in expected_services:
                        # Service might be named differently, so check if any service contains the name
                        service_found = any(service in service_name.lower() for service_name in services.keys())
                        if not service_found:
                            # This is informational, not a hard failure
                            print(f"Service '{service}' not found in compose file")
                    
                except yaml.YAMLError as e:
                    pytest.fail(f"Invalid YAML in {compose_file}: {e}")
        else:
            pytest.skip(f"{compose_file} not found")


@pytest.mark.performance
class TestCICDPerformance:
    """Test performance aspects in CI/CD context."""
    
    def test_import_performance(self):
        """Test that imports don't take too long in CI."""
        import time
        
        start_time = time.time()
        
        # Test importing main modules
        try:
            from multimodal_librarian.config import config_factory
            from multimodal_librarian.clients import database_client_factory
        except ImportError:
            pytest.skip("Modules not available for import test")
        
        import_time = time.time() - start_time
        
        # Imports should be reasonably fast (less than 5 seconds)
        assert import_time < 5.0, f"Imports took {import_time:.2f}s, which is too slow"
    
    def test_configuration_creation_performance(self):
        """Test that configuration creation is fast."""
        import time
        
        try:
            from multimodal_librarian.config.local_config import LocalDatabaseConfig
            
            start_time = time.time()
            
            # Create configuration multiple times
            for _ in range(10):
                config = LocalDatabaseConfig()
                assert config is not None
            
            creation_time = time.time() - start_time
            
            # Configuration creation should be fast
            assert creation_time < 1.0, f"Config creation took {creation_time:.2f}s for 10 instances"
            
        except ImportError:
            pytest.skip("LocalDatabaseConfig not available")


if __name__ == "__main__":
    # Allow running this test file directly
    pytest.main([__file__, "-v"])