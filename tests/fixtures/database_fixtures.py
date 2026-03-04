"""
Database connection fixtures for local development testing.

This module provides pytest fixtures for connecting to local database services
including PostgreSQL, Neo4j, and Milvus. It includes both real connections
for integration testing and mock clients for unit testing.
"""

import pytest
import asyncio
import socket
import time
from typing import Dict, Any, Optional, AsyncGenerator, Generator
from unittest.mock import Mock, AsyncMock, MagicMock
from contextlib import asynccontextmanager

# Database client imports with fallbacks
try:
    from multimodal_librarian.clients.local_postgresql_client import LocalPostgreSQLClient
    from multimodal_librarian.clients.neo4j_client import Neo4jClient
    from multimodal_librarian.clients.milvus_client import MilvusClient
    from multimodal_librarian.clients.database_client_factory import DatabaseClientFactory
    from multimodal_librarian.config.local_config import LocalDatabaseConfig
    CLIENTS_AVAILABLE = True
except ImportError:
    CLIENTS_AVAILABLE = False


# =============================================================================
# Service Availability Utilities
# =============================================================================

def check_service_available(host: str, port: int, timeout: float = 2.0) -> bool:
    """Check if a service is available on the given host and port."""
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except (socket.error, socket.timeout, ConnectionRefusedError):
        return False


def wait_for_service(host: str, port: int, max_wait: int = 30, check_interval: float = 1.0) -> bool:
    """Wait for a service to become available."""
    start_time = time.time()
    while time.time() - start_time < max_wait:
        if check_service_available(host, port):
            return True
        time.sleep(check_interval)
    return False


# =============================================================================
# Configuration Fixtures
# =============================================================================

@pytest.fixture(scope="session")
def local_db_config():
    """Local database configuration for testing."""
    if not CLIENTS_AVAILABLE:
        pytest.skip("Database clients not available")
    
    return LocalDatabaseConfig(
        # Test database settings
        postgres_host="localhost",
        postgres_port=5432,
        postgres_db="multimodal_librarian_test",
        postgres_user="ml_user",
        postgres_password="ml_password",
        
        neo4j_host="localhost",
        neo4j_port=7687,
        neo4j_user="neo4j",
        neo4j_password="ml_password",
        
        milvus_host="localhost",
        milvus_port=19530,
        milvus_default_collection="test_knowledge_chunks",
        
        # Test optimizations
        connection_timeout=10,
        query_timeout=5,
        max_retries=1,
        
        # Enable services for testing
        enable_relational_db=True,
        enable_vector_search=True,
        enable_graph_db=True,
        enable_health_checks=False,  # Disable for faster tests
        
        # Test-specific settings
        environment="test",
        enable_query_logging=False,
    )


@pytest.fixture(scope="session")
def docker_services_config():
    """Configuration for Docker Compose services."""
    return {
        'postgres': {
            'host': 'localhost',
            'port': 5432,
            'database': 'multimodal_librarian_test',
            'user': 'ml_user',
            'password': 'ml_password',
            'health_check_query': 'SELECT 1',
            'max_wait_time': 30,
        },
        'neo4j': {
            'host': 'localhost',
            'port': 7687,
            'user': 'neo4j',
            'password': 'ml_password',
            'uri': 'bolt://localhost:7687',
            'health_check_query': 'RETURN 1',
            'max_wait_time': 30,
        },
        'milvus': {
            'host': 'localhost',
            'port': 19530,
            'collection': 'test_knowledge_chunks',
            'health_check_endpoint': 'http://localhost:9091/healthz',
            'max_wait_time': 45,  # Milvus takes longer to start
        }
    }


# =============================================================================
# Service Availability Fixtures
# =============================================================================

@pytest.fixture(scope="session")
def check_services_available(docker_services_config):
    """Check which local services are available."""
    available_services = {}
    
    for service_name, config in docker_services_config.items():
        if service_name == 'milvus':
            # For Milvus, check the main port
            available = check_service_available(config['host'], config['port'])
        else:
            available = check_service_available(config['host'], config['port'])
        
        available_services[service_name] = available
    
    return available_services


@pytest.fixture
def require_postgres(check_services_available):
    """Skip test if PostgreSQL is not available."""
    if not check_services_available.get('postgres', False):
        pytest.skip("PostgreSQL service not available")


@pytest.fixture
def require_neo4j(check_services_available):
    """Skip test if Neo4j is not available."""
    if not check_services_available.get('neo4j', False):
        pytest.skip("Neo4j service not available")


@pytest.fixture
def require_milvus(check_services_available):
    """Skip test if Milvus is not available."""
    if not check_services_available.get('milvus', False):
        pytest.skip("Milvus service not available")


@pytest.fixture
def require_all_services(check_services_available):
    """Skip test if any required service is not available."""
    required_services = ['postgres', 'neo4j', 'milvus']
    unavailable = [svc for svc in required_services if not check_services_available.get(svc, False)]
    
    if unavailable:
        pytest.skip(f"Required services not available: {', '.join(unavailable)}")


# =============================================================================
# Real Database Client Fixtures
# =============================================================================

@pytest.fixture
async def postgres_client(local_db_config, require_postgres) -> AsyncGenerator[LocalPostgreSQLClient, None]:
    """
    Real PostgreSQL client for integration testing.
    
    This fixture provides a connection to the actual local PostgreSQL service.
    Use this for integration tests that need to verify real database operations.
    """
    client = LocalPostgreSQLClient(
        host=local_db_config.postgres_host,
        port=local_db_config.postgres_port,
        database=local_db_config.postgres_db,
        user=local_db_config.postgres_user,
        password=local_db_config.postgres_password,
        pool_size=2,  # Small pool for testing
        max_overflow=1
    )
    
    try:
        await client.connect()
        yield client
    finally:
        await client.disconnect()


@pytest.fixture
async def neo4j_client(local_db_config, require_neo4j) -> AsyncGenerator[Neo4jClient, None]:
    """
    Real Neo4j client for integration testing.
    
    This fixture provides a connection to the actual local Neo4j service.
    Use this for integration tests that need to verify real graph operations.
    """
    client = Neo4jClient(
        uri=f"bolt://{local_db_config.neo4j_host}:{local_db_config.neo4j_port}",
        user=local_db_config.neo4j_user,
        password=local_db_config.neo4j_password,
    )
    
    try:
        await client.connect()
        yield client
    finally:
        await client.disconnect()


@pytest.fixture
async def milvus_client(local_db_config, require_milvus) -> AsyncGenerator[MilvusClient, None]:
    """
    Real Milvus client for integration testing.
    
    This fixture provides a connection to the actual local Milvus service.
    Use this for integration tests that need to verify real vector operations.
    """
    client = MilvusClient(
        host=local_db_config.milvus_host,
        port=local_db_config.milvus_port,
    )
    
    try:
        await client.connect()
        yield client
    finally:
        await client.disconnect()


@pytest.fixture
async def database_factory(local_db_config) -> AsyncGenerator[DatabaseClientFactory, None]:
    """
    Database client factory for comprehensive testing.
    
    This fixture provides a factory that can create all types of database clients
    based on the local configuration.
    """
    factory = DatabaseClientFactory(local_db_config)
    
    try:
        yield factory
    finally:
        await factory.close()


# =============================================================================
# Mock Database Client Fixtures
# =============================================================================

@pytest.fixture
def mock_postgres_client():
    """
    Mock PostgreSQL client for unit testing.
    
    This fixture provides a fully mocked PostgreSQL client that doesn't
    require a real database connection. Use this for unit tests.
    """
    mock_client = AsyncMock(spec=LocalPostgreSQLClient)
    
    # Configure common mock behaviors
    mock_client.connect = AsyncMock()
    mock_client.disconnect = AsyncMock()
    mock_client.health_check = AsyncMock(return_value={
        "status": "healthy",
        "response_time": 0.001,
        "connection_count": 1,
        "pool_size": 10,
        "last_check": "2023-01-01T00:00:00Z"
    })
    
    # Mock query methods
    mock_client.execute_query = AsyncMock(return_value=[])
    mock_client.execute_command = AsyncMock(return_value=0)
    
    # Mock transaction context manager
    @asynccontextmanager
    async def mock_transaction():
        yield mock_client
    
    mock_client.transaction = mock_transaction
    
    # Mock session context managers
    @asynccontextmanager
    async def mock_async_session():
        session = AsyncMock()
        session.execute = AsyncMock()
        session.commit = AsyncMock()
        session.rollback = AsyncMock()
        yield session
    
    mock_client.get_async_session = mock_async_session
    
    return mock_client


@pytest.fixture
def mock_neo4j_client():
    """
    Mock Neo4j client for unit testing.
    
    This fixture provides a fully mocked Neo4j client that doesn't
    require a real database connection. Use this for unit tests.
    """
    mock_client = AsyncMock(spec=Neo4jClient)
    
    # Configure common mock behaviors
    mock_client.connect = AsyncMock()
    mock_client.disconnect = AsyncMock()
    mock_client.health_check = AsyncMock(return_value={
        "status": "healthy",
        "response_time": 0.001,
        "connection_count": 1,
        "last_check": "2023-01-01T00:00:00Z"
    })
    
    # Mock query methods
    mock_client.execute_query = AsyncMock(return_value=[])
    mock_client.create_node = AsyncMock(return_value="node_id_123")
    mock_client.create_relationship = AsyncMock(return_value="rel_id_123")
    mock_client.find_nodes = AsyncMock(return_value=[])
    mock_client.find_paths = AsyncMock(return_value=[])
    
    # Mock transaction context manager
    @asynccontextmanager
    async def mock_transaction():
        yield mock_client
    
    mock_client.transaction = mock_transaction
    
    return mock_client


@pytest.fixture
def mock_milvus_client():
    """
    Mock Milvus client for unit testing.
    
    This fixture provides a fully mocked Milvus client that doesn't
    require a real database connection. Use this for unit tests.
    """
    mock_client = AsyncMock(spec=MilvusClient)
    
    # Configure common mock behaviors
    mock_client.connect = AsyncMock()
    mock_client.disconnect = AsyncMock()
    mock_client.health_check = AsyncMock(return_value={
        "status": "healthy",
        "response_time": 0.001,
        "collections": ["test_knowledge_chunks"],
        "last_check": "2023-01-01T00:00:00Z"
    })
    
    # Mock collection methods
    mock_client.create_collection = AsyncMock(return_value=True)
    mock_client.drop_collection = AsyncMock(return_value=True)
    mock_client.list_collections = AsyncMock(return_value=["test_knowledge_chunks"])
    mock_client.collection_exists = AsyncMock(return_value=True)
    
    # Mock vector operations
    mock_client.insert_vectors = AsyncMock(return_value={"insert_count": 1, "ids": ["vec_1"]})
    mock_client.search_vectors = AsyncMock(return_value=[])
    mock_client.delete_vectors = AsyncMock(return_value={"delete_count": 1})
    
    # Mock index operations
    mock_client.create_index = AsyncMock(return_value=True)
    mock_client.drop_index = AsyncMock(return_value=True)
    
    return mock_client


@pytest.fixture
def mock_database_factory(mock_postgres_client, mock_neo4j_client, mock_milvus_client):
    """
    Mock database factory for unit testing.
    
    This fixture provides a mocked database factory that returns mock clients
    instead of real database connections.
    """
    mock_factory = AsyncMock(spec=DatabaseClientFactory)
    
    # Configure factory methods to return mock clients
    mock_factory.get_relational_client = AsyncMock(return_value=mock_postgres_client)
    mock_factory.get_graph_client = AsyncMock(return_value=mock_neo4j_client)
    mock_factory.get_vector_client = AsyncMock(return_value=mock_milvus_client)
    mock_factory.close = AsyncMock()
    
    return mock_factory


# =============================================================================
# Database Cleanup Fixtures
# =============================================================================

@pytest.fixture
async def clean_postgres_test_data(postgres_client):
    """
    Clean PostgreSQL test data before and after tests.
    
    This fixture ensures test isolation by cleaning up test data
    that might interfere with other tests.
    """
    # Clean before test
    await _clean_postgres_data(postgres_client)
    
    yield
    
    # Clean after test
    await _clean_postgres_data(postgres_client)


@pytest.fixture
async def clean_neo4j_test_data(neo4j_client):
    """
    Clean Neo4j test data before and after tests.
    
    This fixture ensures test isolation by cleaning up test nodes
    and relationships that might interfere with other tests.
    """
    # Clean before test
    await _clean_neo4j_data(neo4j_client)
    
    yield
    
    # Clean after test
    await _clean_neo4j_data(neo4j_client)


@pytest.fixture
async def clean_milvus_test_data(milvus_client):
    """
    Clean Milvus test data before and after tests.
    
    This fixture ensures test isolation by cleaning up test collections
    and vectors that might interfere with other tests.
    """
    # Clean before test
    await _clean_milvus_data(milvus_client)
    
    yield
    
    # Clean after test
    await _clean_milvus_data(milvus_client)


@pytest.fixture
async def clean_all_test_data(clean_postgres_test_data, clean_neo4j_test_data, clean_milvus_test_data):
    """
    Clean test data from all databases.
    
    This fixture combines all database cleanup fixtures to ensure
    complete test isolation across all database services.
    """
    yield


# =============================================================================
# Database State Management Fixtures
# =============================================================================

@pytest.fixture
async def postgres_transaction(postgres_client):
    """
    PostgreSQL transaction that rolls back after the test.
    
    This fixture provides a transaction context that automatically
    rolls back all changes made during the test, ensuring test isolation.
    """
    async with postgres_client.transaction() as session:
        # Store original autocommit state
        original_autocommit = getattr(session, 'autocommit', None)
        
        try:
            yield session
        finally:
            # Rollback the transaction
            await session.rollback()
            
            # Restore original autocommit state if it was set
            if original_autocommit is not None:
                session.autocommit = original_autocommit


@pytest.fixture
async def neo4j_transaction(neo4j_client):
    """
    Neo4j transaction that rolls back after the test.
    
    This fixture provides a transaction context that automatically
    rolls back all changes made during the test, ensuring test isolation.
    """
    async with neo4j_client.transaction() as tx:
        try:
            yield tx
        finally:
            # Transaction will be rolled back automatically when context exits
            pass


# =============================================================================
# Helper Functions
# =============================================================================

async def _clean_postgres_data(client: LocalPostgreSQLClient) -> None:
    """Clean PostgreSQL test data."""
    try:
        # Delete test data in order of foreign key dependencies
        cleanup_queries = [
            "DELETE FROM document_chunks WHERE document_id LIKE 'test-%'",
            "DELETE FROM knowledge_chunks WHERE id LIKE 'test-%'",
            "DELETE FROM documents WHERE id LIKE 'test-%'",
            "DELETE FROM conversation_messages WHERE thread_id LIKE 'test-%'",
            "DELETE FROM conversation_threads WHERE id LIKE 'test-%'",
            "DELETE FROM api_keys WHERE name LIKE '%test%'",
            "DELETE FROM users WHERE username LIKE 'test_%'",
            "DELETE FROM knowledge_sources WHERE id LIKE 'test-%'",
        ]
        
        for query in cleanup_queries:
            try:
                await client.execute_command(query)
            except Exception:
                # Ignore errors for non-existent tables or data
                pass
                
    except Exception as e:
        # Log but don't fail the test
        print(f"Warning: Failed to clean PostgreSQL test data: {e}")


async def _clean_neo4j_data(client: Neo4jClient) -> None:
    """Clean Neo4j test data."""
    try:
        # Delete all test nodes and relationships
        cleanup_queries = [
            "MATCH (n) WHERE n.id STARTS WITH 'test-' DETACH DELETE n",
            "MATCH (n:TestNode) DETACH DELETE n",
            "MATCH (n:TestDocument) DETACH DELETE n",
            "MATCH (n:TestConcept) DETACH DELETE n",
        ]
        
        for query in cleanup_queries:
            try:
                await client.execute_query(query)
            except Exception:
                # Ignore errors for non-existent nodes
                pass
                
    except Exception as e:
        # Log but don't fail the test
        print(f"Warning: Failed to clean Neo4j test data: {e}")


async def _clean_milvus_data(client: MilvusClient) -> None:
    """Clean Milvus test data."""
    try:
        # List and clean test collections
        collections = await client.list_collections()
        
        for collection_name in collections:
            if collection_name.startswith('test_') or 'test' in collection_name.lower():
                try:
                    # Delete vectors with test IDs
                    await client.delete_vectors(
                        collection_name=collection_name,
                        filter_expr="id like 'test-%'"
                    )
                except Exception:
                    # Ignore errors for non-existent collections or vectors
                    pass
                    
    except Exception as e:
        # Log but don't fail the test
        print(f"Warning: Failed to clean Milvus test data: {e}")