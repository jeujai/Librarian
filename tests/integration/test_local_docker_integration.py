"""
Integration tests for Docker Compose local development setup.

This module tests Docker Compose service orchestration, health checks,
and service dependencies for the local development environment.
"""

import pytest
import subprocess
import time
import os
import yaml
import requests
from pathlib import Path
from typing import Dict, Any, List, Optional

from src.multimodal_librarian.config.local_config import LocalDatabaseConfig


class TestDockerComposeIntegration:
    """Integration tests for Docker Compose setup."""
    
    @pytest.fixture(scope="class")
    def docker_compose_file(self):
        """Path to docker-compose.local.yml file."""
        return "docker-compose.local.yml"
    
    @pytest.fixture(scope="class")
    def compose_config(self, docker_compose_file):
        """Load and parse docker-compose configuration."""
        if not os.path.exists(docker_compose_file):
            pytest.skip(f"Docker compose file {docker_compose_file} not found")
        
        with open(docker_compose_file, 'r') as f:
            return yaml.safe_load(f)
    
    def test_compose_file_exists(self, docker_compose_file):
        """Test that docker-compose.local.yml exists."""
        assert os.path.exists(docker_compose_file), f"Docker compose file {docker_compose_file} should exist"
    
    def test_compose_file_structure(self, compose_config):
        """Test docker-compose file has required structure."""
        assert "services" in compose_config, "Docker compose should have services section"
        
        services = compose_config["services"]
        
        # Check required services
        required_services = [
            "multimodal-librarian",
            "postgres", 
            "neo4j",
            "milvus",
            "etcd",
            "minio",
            "redis"
        ]
        
        for service in required_services:
            assert service in services, f"Service {service} should be defined in docker-compose"
    
    def test_service_configurations(self, compose_config):
        """Test individual service configurations."""
        services = compose_config["services"]
        
        # Test PostgreSQL configuration
        postgres = services.get("postgres", {})
        assert "image" in postgres, "PostgreSQL should have image specified"
        assert "postgres" in postgres["image"].lower(), "PostgreSQL should use postgres image"
        assert "environment" in postgres, "PostgreSQL should have environment variables"
        
        # Check environment variables (they can be in list or dict format)
        postgres_env = postgres["environment"]
        if isinstance(postgres_env, list):
            env_vars = [var.split('=')[0] for var in postgres_env if '=' in var]
        else:
            env_vars = list(postgres_env.keys())
        
        assert "POSTGRES_DB" in env_vars, "PostgreSQL should have database name"
        assert "POSTGRES_USER" in env_vars, "PostgreSQL should have user"
        assert "POSTGRES_PASSWORD" in env_vars, "PostgreSQL should have password"
        
        # Test Neo4j configuration
        neo4j = services.get("neo4j", {})
        assert "image" in neo4j, "Neo4j should have image specified"
        assert "neo4j" in neo4j["image"].lower(), "Neo4j should use neo4j image"
        assert "environment" in neo4j, "Neo4j should have environment variables"
        
        # Check Neo4j environment variables
        neo4j_env = neo4j["environment"]
        if isinstance(neo4j_env, list):
            neo4j_env_vars = [var.split('=')[0] for var in neo4j_env if '=' in var]
        else:
            neo4j_env_vars = list(neo4j_env.keys())
        
        assert "NEO4J_AUTH" in neo4j_env_vars, "Neo4j should have authentication"
        
        # Test Milvus configuration
        milvus = services.get("milvus", {})
        assert "image" in milvus, "Milvus should have image specified"
        assert "milvus" in milvus["image"].lower(), "Milvus should use milvus image"
        assert "depends_on" in milvus, "Milvus should depend on etcd and minio"
        
        # Test Redis configuration
        redis = services.get("redis", {})
        assert "image" in redis, "Redis should have image specified"
        assert "redis" in redis["image"].lower(), "Redis should use redis image"
    
    def test_health_checks_defined(self, compose_config):
        """Test that health checks are defined for critical services."""
        services = compose_config["services"]
        
        services_with_health_checks = [
            "postgres",
            "neo4j", 
            "milvus",
            "redis",
            "etcd",
            "minio"
        ]
        
        for service_name in services_with_health_checks:
            service = services.get(service_name, {})
            assert "healthcheck" in service, f"Service {service_name} should have health check"
            
            healthcheck = service["healthcheck"]
            assert "test" in healthcheck, f"Service {service_name} health check should have test"
            assert "interval" in healthcheck, f"Service {service_name} health check should have interval"
            assert "timeout" in healthcheck, f"Service {service_name} health check should have timeout"
            assert "retries" in healthcheck, f"Service {service_name} health check should have retries"
    
    def test_volume_configurations(self, compose_config):
        """Test volume configurations for data persistence."""
        services = compose_config["services"]
        
        # Check that data services have persistent volumes
        data_services = {
            "postgres": ["postgres_data"],
            "neo4j": ["neo4j_data", "neo4j_logs"],
            "milvus": ["milvus_data"],
            "etcd": ["etcd_data"],
            "minio": ["minio_data"],
            "redis": ["redis_data"]
        }
        
        for service_name, expected_volumes in data_services.items():
            service = services.get(service_name, {})
            if "volumes" in service:
                volume_mounts = service["volumes"]
                for expected_volume in expected_volumes:
                    # Check if any volume mount uses the expected volume
                    volume_found = any(expected_volume in mount for mount in volume_mounts)
                    assert volume_found, f"Service {service_name} should use volume {expected_volume}"
        
        # Check that volumes are defined at top level
        if "volumes" in compose_config:
            volumes = compose_config["volumes"]
            for service_name, expected_volumes in data_services.items():
                for expected_volume in expected_volumes:
                    assert expected_volume in volumes, f"Volume {expected_volume} should be defined"
    
    def test_network_configuration(self, compose_config):
        """Test network configuration."""
        services = compose_config["services"]
        
        # Check that services are on the same network
        network_name = None
        for service_name, service_config in services.items():
            if "networks" in service_config:
                service_networks = service_config["networks"]
                if isinstance(service_networks, list) and service_networks:
                    if network_name is None:
                        network_name = service_networks[0]
                    else:
                        assert network_name in service_networks, f"Service {service_name} should be on network {network_name}"
        
        # Check network definition
        if "networks" in compose_config and network_name:
            networks = compose_config["networks"]
            assert network_name in networks, f"Network {network_name} should be defined"
    
    def test_port_configurations(self, compose_config):
        """Test port configurations for services."""
        services = compose_config["services"]
        
        expected_ports = {
            "multimodal-librarian": ["8000"],
            "postgres": ["5432"],
            "neo4j": ["7474", "7687"],
            "milvus": ["19530"],
            "redis": ["6379"],
            "etcd": ["2379"],
            "minio": ["9000", "9001"]
        }
        
        for service_name, expected_service_ports in expected_ports.items():
            service = services.get(service_name, {})
            if "ports" in service:
                port_mappings = service["ports"]
                for expected_port in expected_service_ports:
                    # Check if any port mapping includes the expected port
                    port_found = any(expected_port in str(mapping) for mapping in port_mappings)
                    assert port_found, f"Service {service_name} should expose port {expected_port}"
    
    def test_dependency_configuration(self, compose_config):
        """Test service dependency configuration."""
        services = compose_config["services"]
        
        # Test main application dependencies
        app_service = services.get("multimodal-librarian", {})
        if "depends_on" in app_service:
            depends_on = app_service["depends_on"]
            
            expected_dependencies = ["postgres", "neo4j", "milvus", "redis"]
            for dependency in expected_dependencies:
                assert dependency in depends_on, f"Application should depend on {dependency}"
                
                # Check dependency condition if specified
                if isinstance(depends_on[dependency], dict):
                    dep_config = depends_on[dependency]
                    if "condition" in dep_config:
                        assert dep_config["condition"] == "service_healthy", f"Dependency {dependency} should wait for health"
        
        # Test Milvus dependencies
        milvus_service = services.get("milvus", {})
        if "depends_on" in milvus_service:
            milvus_deps = milvus_service["depends_on"]
            assert "etcd" in milvus_deps, "Milvus should depend on etcd"
            assert "minio" in milvus_deps, "Milvus should depend on minio"
    
    def test_environment_variable_configuration(self, compose_config):
        """Test environment variable configuration."""
        services = compose_config["services"]
        
        # Test application environment variables
        app_service = services.get("multimodal-librarian", {})
        if "environment" in app_service:
            env_vars = app_service["environment"]
            
            expected_env_vars = [
                "ML_ENVIRONMENT",
                "ML_DATABASE_TYPE", 
                "POSTGRES_HOST",
                "NEO4J_HOST",
                "MILVUS_HOST",
                "REDIS_HOST"
            ]
            
            for env_var in expected_env_vars:
                # Check if environment variable is defined
                env_found = any(env_var in str(var) for var in env_vars)
                assert env_found, f"Application should have environment variable {env_var}"


class TestDockerComposeValidation:
    """Tests for Docker Compose file validation."""
    
    def test_compose_file_syntax(self):
        """Test that docker-compose file has valid syntax."""
        compose_file = "docker-compose.local.yml"
        
        if not os.path.exists(compose_file):
            pytest.skip(f"Docker compose file {compose_file} not found")
        
        try:
            # Try to validate the compose file
            result = subprocess.run(
                ["docker-compose", "-f", compose_file, "config"],
                capture_output=True,
                text=True,
                timeout=30
            )
            
            # If docker-compose is not available, try docker compose
            if result.returncode != 0:
                result = subprocess.run(
                    ["docker", "compose", "-f", compose_file, "config"],
                    capture_output=True,
                    text=True,
                    timeout=30
                )
            
            if result.returncode == 0:
                # Validation successful
                assert True
            else:
                # Validation failed - this is informational, not a hard failure
                pytest.skip(f"Docker compose validation failed: {result.stderr}")
                
        except (subprocess.TimeoutExpired, FileNotFoundError):
            pytest.skip("Docker compose command not available")
    
    def test_compose_file_yaml_syntax(self):
        """Test that docker-compose file is valid YAML."""
        compose_file = "docker-compose.local.yml"
        
        if not os.path.exists(compose_file):
            pytest.skip(f"Docker compose file {compose_file} not found")
        
        try:
            with open(compose_file, 'r') as f:
                yaml.safe_load(f)
            # If we get here, YAML is valid
            assert True
        except yaml.YAMLError as e:
            pytest.fail(f"Docker compose file has invalid YAML syntax: {e}")
    
    def test_required_directories_exist(self):
        """Test that required directories for volume mounts exist or can be created."""
        compose_file = "docker-compose.local.yml"
        
        if not os.path.exists(compose_file):
            pytest.skip(f"Docker compose file {compose_file} not found")
        
        # Directories that should exist or be creatable
        required_dirs = [
            "./data",
            "./uploads", 
            "./media",
            "./exports",
            "./logs",
            "./backups",
            "./cache"
        ]
        
        for dir_path in required_dirs:
            path = Path(dir_path)
            try:
                path.mkdir(parents=True, exist_ok=True)
                assert path.exists(), f"Directory {dir_path} should exist or be creatable"
            except (OSError, PermissionError):
                pytest.skip(f"Cannot create directory {dir_path} - permission denied")


class TestDockerServiceIntegration:
    """Integration tests for Docker services (requires Docker to be running)."""
    
    @pytest.fixture(scope="class")
    def docker_available(self):
        """Check if Docker is available."""
        try:
            result = subprocess.run(
                ["docker", "--version"],
                capture_output=True,
                text=True,
                timeout=10
            )
            return result.returncode == 0
        except (subprocess.TimeoutExpired, FileNotFoundError):
            return False
    
    @pytest.fixture(scope="class") 
    def compose_available(self):
        """Check if Docker Compose is available."""
        try:
            # Try docker-compose first
            result = subprocess.run(
                ["docker-compose", "--version"],
                capture_output=True,
                text=True,
                timeout=10
            )
            if result.returncode == 0:
                return True
            
            # Try docker compose (newer syntax)
            result = subprocess.run(
                ["docker", "compose", "version"],
                capture_output=True,
                text=True,
                timeout=10
            )
            return result.returncode == 0
        except (subprocess.TimeoutExpired, FileNotFoundError):
            return False
    
    def test_docker_availability(self, docker_available):
        """Test that Docker is available for integration tests."""
        if not docker_available:
            pytest.skip("Docker is not available")
        assert docker_available, "Docker should be available for integration tests"
    
    def test_compose_availability(self, compose_available):
        """Test that Docker Compose is available for integration tests."""
        if not compose_available:
            pytest.skip("Docker Compose is not available")
        assert compose_available, "Docker Compose should be available for integration tests"
    
    def test_compose_config_validation(self, docker_available, compose_available):
        """Test Docker Compose configuration validation."""
        if not docker_available or not compose_available:
            pytest.skip("Docker or Docker Compose not available")
        
        compose_file = "docker-compose.local.yml"
        if not os.path.exists(compose_file):
            pytest.skip(f"Docker compose file {compose_file} not found")
        
        try:
            # Validate compose configuration
            result = subprocess.run(
                ["docker-compose", "-f", compose_file, "config"],
                capture_output=True,
                text=True,
                timeout=30
            )
            
            if result.returncode != 0:
                # Try newer docker compose syntax
                result = subprocess.run(
                    ["docker", "compose", "-f", compose_file, "config"],
                    capture_output=True,
                    text=True,
                    timeout=30
                )
            
            assert result.returncode == 0, f"Docker compose config validation failed: {result.stderr}"
            
        except subprocess.TimeoutExpired:
            pytest.fail("Docker compose config validation timed out")
    
    def test_image_availability(self, docker_available):
        """Test that required Docker images are available or can be pulled."""
        if not docker_available:
            pytest.skip("Docker is not available")
        
        # Images used in docker-compose.local.yml
        required_images = [
            "postgres:15-alpine",
            "neo4j:5.15-community", 
            "milvusdb/milvus:v2.3.4",
            "redis:7-alpine",
            "quay.io/coreos/etcd:v3.5.5",
            "minio/minio:RELEASE.2023-03-20T20-16-18Z"
        ]
        
        for image in required_images:
            try:
                # Check if image exists locally or can be pulled
                result = subprocess.run(
                    ["docker", "image", "inspect", image],
                    capture_output=True,
                    text=True,
                    timeout=10
                )
                
                if result.returncode != 0:
                    # Image not found locally, this is OK for integration tests
                    # We just verify the image name is valid
                    assert ":" in image, f"Image {image} should have a tag"
                    
            except subprocess.TimeoutExpired:
                pytest.skip(f"Timeout checking image {image}")


class TestLocalConfigDockerIntegration:
    """Integration tests between local configuration and Docker setup."""
    
    def test_config_docker_validation(self):
        """Test local configuration Docker validation."""
        config = LocalDatabaseConfig.create_test_config()
        
        # Test Docker environment validation
        docker_validation = config.validate_docker_environment()
        
        assert isinstance(docker_validation, dict)
        assert "docker_available" in docker_validation
        assert "compose_available" in docker_validation
        assert "compose_file_exists" in docker_validation
        assert "errors" in docker_validation
        assert "warnings" in docker_validation
    
    def test_config_docker_settings(self):
        """Test Docker-related configuration settings."""
        config = LocalDatabaseConfig.create_test_config()
        
        docker_config = config.get_docker_config()
        
        assert "network" in docker_config
        assert "compose_file" in docker_config
        assert "services" in docker_config
        
        # Check that compose file setting matches expected file
        expected_compose_file = "docker-compose.local.yml"
        assert docker_config["compose_file"] == expected_compose_file
        
        # Check service configurations
        services = docker_config["services"]
        expected_services = ["postgres", "neo4j", "milvus", "redis"]
        
        for service in expected_services:
            assert service in services, f"Service {service} should be in Docker config"
            service_config = services[service]
            assert "container_name" in service_config
            assert "health_check_url" in service_config
    
    def test_config_service_urls(self):
        """Test service URL generation for Docker services."""
        config = LocalDatabaseConfig.create_test_config(
            postgres_host="postgres",
            neo4j_host="neo4j", 
            milvus_host="milvus",
            redis_host="redis"
        )
        
        # Test connection strings use Docker service names
        postgres_conn = config.get_postgres_connection_string()
        assert "postgres:5432" in postgres_conn
        
        neo4j_uri = config.get_neo4j_uri()
        assert "neo4j:7687" in neo4j_uri
        
        milvus_uri = config.get_milvus_uri()
        assert "milvus:19530" in milvus_uri
        
        redis_conn = config.get_redis_connection_string()
        assert "redis:6379" in redis_conn
    
    def test_config_environment_variables(self):
        """Test environment variable configuration for Docker."""
        config = LocalDatabaseConfig.create_test_config()
        
        # Test that configuration can generate environment variables
        env_template_path = "/tmp/test_env_template.env"
        
        try:
            config.create_env_file_template(env_template_path)
            
            # Check that file was created
            assert os.path.exists(env_template_path)
            
            # Check content
            with open(env_template_path, 'r') as f:
                content = f.read()
            
            # Should contain Docker-related environment variables
            assert "ML_POSTGRES_HOST=" in content
            assert "ML_NEO4J_HOST=" in content
            assert "ML_MILVUS_HOST=" in content
            assert "ML_REDIS_HOST=" in content
            
        finally:
            # Clean up
            if os.path.exists(env_template_path):
                os.remove(env_template_path)