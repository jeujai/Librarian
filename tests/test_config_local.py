"""
Test configuration for local services.

This module provides test configuration and utilities specifically
for testing with local Docker Compose services.
"""

import pytest
import os
import asyncio
from typing import Dict, Any, Optional
from unittest.mock import patch

# Test configuration constants
TEST_DATABASE_NAMES = {
    'postgres': 'multimodal_librarian_test',
    'neo4j': 'neo4j_test',
    'milvus': 'test_knowledge_chunks',
    'redis': 1,  # Redis DB number
}

TEST_TIMEOUTS = {
    'connection': 10,
    'query': 5,
    'health_check': 3,
}

TEST_RETRY_SETTINGS = {
    'max_retries': 1,
    'retry_delay': 0.1,
    'backoff_factor': 1.0,
}


class LocalServiceTestConfig:
    """Configuration class for local service testing."""
    
    def __init__(self):
        self.postgres_config = {
            'host': 'localhost',
            'port': 5432,
            'database': TEST_DATABASE_NAMES['postgres'],
            'user': 'ml_user',
            'password': 'ml_password',
            'pool_size': 5,
            'max_overflow': 10,
            'timeout': TEST_TIMEOUTS['connection'],
        }
        
        self.neo4j_config = {
            'host': 'localhost',
            'port': 7687,
            'user': 'neo4j',
            'password': 'ml_password',
            'uri': 'bolt://localhost:7687',
            'timeout': TEST_TIMEOUTS['connection'],
        }
        
        self.milvus_config = {
            'host': 'localhost',
            'port': 19530,
            'collection': TEST_DATABASE_NAMES['milvus'],
            'timeout': TEST_TIMEOUTS['connection'],
        }
        
        self.redis_config = {
            'host': 'localhost',
            'port': 6379,
            'db': TEST_DATABASE_NAMES['redis'],
            'timeout': TEST_TIMEOUTS['connection'],
        }
    
    def get_service_config(self, service_name: str) -> Dict[str, Any]:
        """Get configuration for a specific service."""
        configs = {
            'postgres': self.postgres_config,
            'neo4j': self.neo4j_config,
            'milvus': self.milvus_config,
            'redis': self.redis_config,
        }
        return configs.get(service_name, {})
    
    def get_all_configs(self) -> Dict[str, Dict[str, Any]]:
        """Get all service configurations."""
        return {
            'postgres': self.postgres_config,
            'neo4j': self.neo4j_config,
            'milvus': self.milvus_config,
            'redis': self.redis_config,
        }


def create_test_environment_patch() -> Dict[str, str]:
    """
    Create environment variable patch for testing.
    
    Returns a dictionary of environment variables that should be
    set for local service testing.
    """
    return {
        # Environment type
        'ML_ENVIRONMENT': 'test',
        'ML_DATABASE_TYPE': 'local',
        'DATABASE_TYPE': 'local',
        
        # Application settings
        'DEBUG': 'true',
        'LOG_LEVEL': 'DEBUG',
        'VALIDATE_CONFIG_ON_STARTUP': 'false',
        'STRICT_CONFIG_VALIDATION': 'false',
        
        # Database settings
        'POSTGRES_HOST': 'localhost',
        'POSTGRES_PORT': '5432',
        'POSTGRES_DB': TEST_DATABASE_NAMES['postgres'],
        'POSTGRES_USER': 'ml_user',
        'POSTGRES_PASSWORD': 'ml_password',
        
        'NEO4J_HOST': 'localhost',
        'NEO4J_PORT': '7687',
        'NEO4J_USER': 'neo4j',
        'NEO4J_PASSWORD': 'ml_password',
        
        'MILVUS_HOST': 'localhost',
        'MILVUS_PORT': '19530',
        'MILVUS_COLLECTION_NAME': TEST_DATABASE_NAMES['milvus'],
        
        'REDIS_HOST': 'localhost',
        'REDIS_PORT': '6379',
        'REDIS_DB': str(TEST_DATABASE_NAMES['redis']),
        
        # Disable external services
        'OPENAI_API_KEY': '',
        'GOOGLE_API_KEY': '',
        'ANTHROPIC_API_KEY': '',
        
        # Test optimizations
        'ENABLE_HEALTH_CHECKS': 'false',
        'CONNECTION_TIMEOUT': str(TEST_TIMEOUTS['connection']),
        'QUERY_TIMEOUT': str(TEST_TIMEOUTS['query']),
        'MAX_RETRIES': str(TEST_RETRY_SETTINGS['max_retries']),
    }


@pytest.fixture(scope="session")
def local_service_config():
    """Provide local service configuration for tests."""
    return LocalServiceTestConfig()


@pytest.fixture(scope="session")
def test_env_patch():
    """Provide environment variable patch for testing."""
    return create_test_environment_patch()


def pytest_configure(config):
    """Configure pytest for local service testing."""
    # Add custom markers
    config.addinivalue_line(
        "markers", "local_services: mark test as requiring local Docker services"
    )
    config.addinivalue_line(
        "markers", "integration: mark test as integration test"
    )
    config.addinivalue_line(
        "markers", "database: mark test as requiring database access"
    )
    config.addinivalue_line(
        "markers", "slow: mark test as slow running"
    )


def pytest_collection_modifyitems(config, items):
    """Modify test collection to add markers based on test location."""
    for item in items:
        # Add markers based on test file location
        if "integration" in str(item.fspath):
            item.add_marker(pytest.mark.integration)
        
        if "database" in str(item.fspath):
            item.add_marker(pytest.mark.database)
        
        # Add local_services marker for tests that use local service fixtures
        if any(fixture in item.fixturenames for fixture in [
            'local_postgres_client', 'local_neo4j_client', 
            'local_milvus_client', 'local_database_factory'
        ]):
            item.add_marker(pytest.mark.local_services)


def pytest_runtest_setup(item):
    """Set up individual test runs."""
    # Skip AWS service tests in local development
    if item.get_closest_marker("aws_services"):
        if os.getenv("ML_DATABASE_TYPE", "local") == "local":
            pytest.skip("AWS services not available in local development")
    
    # Check for local services if test requires them
    if item.get_closest_marker("local_services"):
        # This will be handled by the skip_if_no_local_services fixture
        pass


class TestDatabaseManager:
    """Utility class for managing test databases."""
    
    def __init__(self, config: LocalServiceTestConfig):
        self.config = config
    
    async def setup_test_databases(self):
        """Set up test databases with clean state."""
        # This would typically create test databases, run migrations, etc.
        # For now, we'll just ensure the configuration is correct
        pass
    
    async def cleanup_test_databases(self):
        """Clean up test databases after tests."""
        # This would typically drop test data, reset sequences, etc.
        pass
    
    async def reset_database_state(self, service_name: str):
        """Reset a specific database to clean state."""
        # Implementation would depend on the specific database
        pass


@pytest.fixture(scope="session")
async def test_database_manager(local_service_config):
    """Provide test database manager for session-level setup/teardown."""
    manager = TestDatabaseManager(local_service_config)
    
    # Setup
    await manager.setup_test_databases()
    
    yield manager
    
    # Teardown
    await manager.cleanup_test_databases()


# Test data factories
def create_test_document_data():
    """Create test document data."""
    return {
        'id': 'test-doc-1',
        'title': 'Test Document',
        'content': 'This is a test document for testing purposes.',
        'metadata': {
            'author': 'Test Author',
            'created_at': '2023-01-01T00:00:00Z',
            'tags': ['test', 'document'],
        }
    }


def create_test_conversation_data():
    """Create test conversation data."""
    return {
        'thread_id': 'test-thread-1',
        'user_id': 'test-user-1',
        'messages': [
            {
                'id': 'msg-1',
                'content': 'Hello, this is a test message.',
                'role': 'user',
                'timestamp': '2023-01-01T00:00:00Z',
            },
            {
                'id': 'msg-2',
                'content': 'Hello! How can I help you today?',
                'role': 'assistant',
                'timestamp': '2023-01-01T00:00:01Z',
            }
        ]
    }


def create_test_vector_data():
    """Create test vector data."""
    return {
        'id': 'test-vector-1',
        'vector': [0.1, 0.2, 0.3, 0.4] * 96,  # 384-dimensional vector
        'metadata': {
            'document_id': 'test-doc-1',
            'chunk_index': 0,
            'text': 'This is a test text chunk for vector embedding.',
        }
    }


def create_test_graph_data():
    """Create test graph data."""
    return {
        'nodes': [
            {
                'id': 'concept-1',
                'label': 'Concept',
                'properties': {
                    'name': 'Machine Learning',
                    'type': 'topic',
                    'confidence': 0.95,
                }
            },
            {
                'id': 'concept-2',
                'label': 'Concept',
                'properties': {
                    'name': 'Neural Networks',
                    'type': 'subtopic',
                    'confidence': 0.90,
                }
            }
        ],
        'relationships': [
            {
                'from': 'concept-1',
                'to': 'concept-2',
                'type': 'CONTAINS',
                'properties': {
                    'strength': 0.85,
                }
            }
        ]
    }


# Export test data factories
__all__ = [
    'LocalServiceTestConfig',
    'create_test_environment_patch',
    'TestDatabaseManager',
    'create_test_document_data',
    'create_test_conversation_data',
    'create_test_vector_data',
    'create_test_graph_data',
    'TEST_DATABASE_NAMES',
    'TEST_TIMEOUTS',
    'TEST_RETRY_SETTINGS',
]