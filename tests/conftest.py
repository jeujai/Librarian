"""
Pytest configuration and shared fixtures for the Multimodal Librarian tests.

Updated for Local Development Conversion (Task 5.3):
- Added local service configuration fixtures
- Added Docker Compose service management
- Added local database client fixtures
- Updated for both local and AWS testing environments
- Added DI-aware fixtures that use app.dependency_overrides
- Added fixtures for clearing DI caches between tests
- Added mock service fixtures for testing
"""

import pytest
import os
import asyncio
import tempfile
from typing import Optional, Dict, Any
from unittest.mock import MagicMock, AsyncMock, patch
from fastapi.testclient import TestClient

from multimodal_librarian.main import create_minimal_app
from multimodal_librarian.config import Settings


# =============================================================================
# DI Cache Management Fixtures
# =============================================================================

@pytest.fixture(autouse=False)
def clear_di_caches():
    """
    Fixture to clear DI caches before and after tests.
    
    Use this fixture in tests that need isolated DI state.
    Not autouse to avoid overhead in tests that don't need it.
    
    Usage:
        def test_something(clear_di_caches):
            # DI caches are cleared before this test
            ...
            # DI caches will be cleared after this test
    """
    try:
        from multimodal_librarian.api.dependencies.services import clear_service_cache
        clear_service_cache()
    except ImportError:
        pass
    
    yield
    
    try:
        from multimodal_librarian.api.dependencies.services import clear_service_cache
        clear_service_cache()
    except ImportError:
        pass


# =============================================================================
# Mock Service Fixtures
# =============================================================================

@pytest.fixture
def mock_opensearch_client():
    """
    Mock OpenSearch client for testing.
    
    Usage:
        def test_something(mock_opensearch_client):
            # Use mock_opensearch_client in dependency overrides
    """
    mock = MagicMock()
    mock.connect = MagicMock()
    mock.disconnect = MagicMock()
    mock.health_check = MagicMock(return_value=True)
    mock.semantic_search = MagicMock(return_value=[])
    mock.index_document = MagicMock(return_value=True)
    mock.delete_document = MagicMock(return_value=True)
    return mock


@pytest.fixture
def mock_ai_service():
    """
    Mock AI service for testing.
    
    Usage:
        def test_something(mock_ai_service):
            # Use mock_ai_service in dependency overrides
    """
    mock = MagicMock()
    mock.generate_response = AsyncMock(return_value={
        "response": "Mock AI response for testing",
        "citations": [],
        "context_used": 0
    })
    mock.health_check = MagicMock(return_value=True)
    mock.get_available_models = MagicMock(return_value=["gpt-4", "gpt-3.5-turbo"])
    return mock


@pytest.fixture
def mock_rag_service(mock_opensearch_client, mock_ai_service):
    """
    Mock RAG service for testing.
    
    Usage:
        def test_something(mock_rag_service):
            # Use mock_rag_service in dependency overrides
    """
    mock = MagicMock()
    mock.get_relevant_context = AsyncMock(return_value=[])
    mock.get_service_status = MagicMock(return_value={"status": "healthy"})
    mock.opensearch_client = mock_opensearch_client
    mock.ai_service = mock_ai_service
    mock.search_and_generate = AsyncMock(return_value={
        "response": "Mock RAG response",
        "sources": [],
        "context_used": 0
    })
    return mock


@pytest.fixture
def mock_connection_manager():
    """
    Mock ConnectionManager for testing.
    
    Usage:
        def test_something(mock_connection_manager):
            # Use mock_connection_manager in dependency overrides
    """
    try:
        from multimodal_librarian.api.dependencies.services import ConnectionManager
        manager = ConnectionManager()
        return manager
    except ImportError:
        mock = MagicMock()
        mock.active_connections = {}
        mock.conversation_history = {}
        mock.user_threads = {}
        mock._rag_service = None
        mock._ai_service = None
        mock.rag_available = False
        mock.connect = AsyncMock()
        mock.disconnect = MagicMock()
        mock.send_personal_message = AsyncMock()
        return mock


# =============================================================================
# Application Fixtures with DI Support
# =============================================================================

@pytest.fixture
def test_settings():
    """Test settings with overrides for testing."""
    return Settings(
        debug=True,
        log_level="DEBUG",
        postgres_db="test_multimodal_librarian",
        milvus_collection_name="test_knowledge_chunks",
        upload_dir="test_uploads",
        media_dir="test_media",
        export_dir="test_exports",
    )


@pytest.fixture
def app(test_settings, clear_di_caches):
    """
    FastAPI application instance for testing with DI cache clearing.
    
    This fixture:
    1. Clears DI caches before creating the app
    2. Creates the app with test settings
    3. Clears DI caches and dependency overrides after the test
    """
    # Override settings for testing
    from multimodal_librarian.config import get_settings
    
    # Clear cache if it exists
    if hasattr(get_settings, 'cache_clear'):
        get_settings.cache_clear()
    
    # Monkey patch settings
    import multimodal_librarian.config
    multimodal_librarian.config.get_settings = lambda: test_settings
    
    app = create_minimal_app()
    
    yield app
    
    # Clean up dependency overrides after test
    app.dependency_overrides.clear()


@pytest.fixture
def app_with_mocked_services(
    test_settings,
    clear_di_caches,
    mock_opensearch_client,
    mock_ai_service,
    mock_rag_service,
    mock_connection_manager
):
    """
    FastAPI application with all services mocked via dependency overrides.
    
    This is the recommended fixture for tests that need to mock services.
    
    Usage:
        def test_something(app_with_mocked_services):
            client = TestClient(app_with_mocked_services)
            response = client.get("/some/endpoint")
            # Services are mocked, no real connections made
    """
    try:
        from multimodal_librarian.api.dependencies.services import (
            get_opensearch_client,
            get_opensearch_client_optional,
            get_ai_service,
            get_ai_service_optional,
            get_rag_service,
            get_cached_rag_service,
            get_connection_manager,
            get_connection_manager_with_services,
        )
        
        # Override settings
        from multimodal_librarian.config import get_settings
        if hasattr(get_settings, 'cache_clear'):
            get_settings.cache_clear()
        import multimodal_librarian.config
        multimodal_librarian.config.get_settings = lambda: test_settings
        
        app = create_minimal_app()
        
        # Set up services on connection manager
        mock_connection_manager.set_services(
            rag_service=mock_rag_service,
            ai_service=mock_ai_service
        )
        
        # Define override functions
        async def override_opensearch():
            return mock_opensearch_client
        
        async def override_opensearch_optional():
            return mock_opensearch_client
        
        async def override_ai():
            return mock_ai_service
        
        async def override_ai_optional():
            return mock_ai_service
        
        async def override_rag(opensearch=None, ai_service=None):
            return mock_rag_service
        
        async def override_cached_rag(opensearch=None, ai_service=None):
            return mock_rag_service
        
        async def override_connection_manager():
            return mock_connection_manager
        
        async def override_connection_manager_with_services(rag_service=None, ai_service=None):
            return mock_connection_manager
        
        # Apply overrides
        app.dependency_overrides[get_opensearch_client] = override_opensearch
        app.dependency_overrides[get_opensearch_client_optional] = override_opensearch_optional
        app.dependency_overrides[get_ai_service] = override_ai
        app.dependency_overrides[get_ai_service_optional] = override_ai_optional
        app.dependency_overrides[get_rag_service] = override_rag
        app.dependency_overrides[get_cached_rag_service] = override_cached_rag
        app.dependency_overrides[get_connection_manager] = override_connection_manager
        app.dependency_overrides[get_connection_manager_with_services] = override_connection_manager_with_services
        
        yield app
        
        # Clean up
        app.dependency_overrides.clear()
        
    except ImportError:
        # Fall back to basic app if DI module not available
        from multimodal_librarian.config import get_settings
        if hasattr(get_settings, 'cache_clear'):
            get_settings.cache_clear()
        import multimodal_librarian.config
        multimodal_librarian.config.get_settings = lambda: test_settings
        
        yield create_minimal_app()


@pytest.fixture
def client(app):
    """Test client for making HTTP requests."""
    return TestClient(app)


@pytest.fixture
def client_with_mocks(app_with_mocked_services):
    """
    Test client with all services mocked.
    
    Usage:
        def test_something(client_with_mocks):
            response = client_with_mocks.get("/some/endpoint")
            # Services are mocked, no real connections made
    """
    return TestClient(app_with_mocked_services)


@pytest.fixture
def sample_pdf_content():
    """Sample PDF content for testing."""
    return b"%PDF-1.4\n1 0 obj\n<<\n/Type /Catalog\n/Pages 2 0 R\n>>\nendobj\n"


@pytest.fixture
def sample_conversation_data():
    """Sample conversation data for testing."""
    return {
        "thread_id": "test-thread-123",
        "user_id": "test-user-456",
        "messages": [
            {
                "message_id": "msg-1",
                "content": "What is machine learning?",
                "timestamp": "2023-01-01T10:00:00Z",
                "message_type": "USER"
            },
            {
                "message_id": "msg-2", 
                "content": "Machine learning is a subset of artificial intelligence...",
                "timestamp": "2023-01-01T10:00:05Z",
                "message_type": "SYSTEM"
            }
        ]
    }


# =============================================================================
# Environment and Configuration Fixtures for Local Services
# =============================================================================

@pytest.fixture(scope="session")
def test_environment():
    """
    Set up test environment variables for local services.
    
    This fixture ensures tests run with local database configuration
    and proper test isolation.
    """
    original_env = os.environ.copy()
    
    # Set test environment variables
    test_env_vars = {
        'ML_ENVIRONMENT': 'test',
        'ML_DATABASE_TYPE': 'local',
        'DATABASE_TYPE': 'local',
        'DEBUG': 'true',
        'LOG_LEVEL': 'DEBUG',
        
        # Test database configuration
        'POSTGRES_HOST': 'localhost',
        'POSTGRES_PORT': '5432',
        'POSTGRES_DB': 'multimodal_librarian_test',
        'POSTGRES_USER': 'ml_user',
        'POSTGRES_PASSWORD': 'ml_password',
        
        'NEO4J_HOST': 'localhost',
        'NEO4J_PORT': '7687',
        'NEO4J_USER': 'neo4j',
        'NEO4J_PASSWORD': 'ml_password',
        
        'MILVUS_HOST': 'localhost',
        'MILVUS_PORT': '19530',
        'MILVUS_COLLECTION_NAME': 'test_knowledge_chunks',
        
        'REDIS_HOST': 'localhost',
        'REDIS_PORT': '6379',
        'REDIS_DB': '1',  # Use different DB for tests
        
        # Disable external services for testing
        'OPENAI_API_KEY': '',
        'GOOGLE_API_KEY': '',
        'ANTHROPIC_API_KEY': '',
        
        # Test-specific settings
        'ENABLE_HEALTH_CHECKS': 'false',
        'VALIDATE_CONFIG_ON_STARTUP': 'false',
        'STRICT_CONFIG_VALIDATION': 'false',
    }
    
    # Apply test environment
    os.environ.update(test_env_vars)
    
    yield test_env_vars
    
    # Restore original environment
    os.environ.clear()
    os.environ.update(original_env)


@pytest.fixture
def local_test_config():
    """
    Create a local database configuration optimized for testing.
    """
    try:
        from multimodal_librarian.config.local_config import LocalDatabaseConfig
        
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
            
            redis_host="localhost",
            redis_port=6379,
            redis_db=1,  # Use different DB for tests
            
            # Test optimizations
            connection_timeout=10,  # Shorter timeout for tests
            query_timeout=5,
            max_retries=1,
            
            # Enable all services for comprehensive testing
            enable_relational_db=True,
            enable_vector_search=True,
            enable_graph_db=True,
            enable_health_checks=False,  # Disable for faster tests
            
            # Test-specific settings
            environment="test",
            enable_query_logging=False,  # Reduce noise in tests
        )
    except ImportError:
        # Fallback if local config not available
        return None


@pytest.fixture
def docker_compose_services():
    """
    Information about Docker Compose services for integration tests.
    
    This fixture provides service connection details for tests that
    need to connect to actual local services.
    """
    return {
        'postgres': {
            'host': 'localhost',
            'port': 5432,
            'database': 'multimodal_librarian_test',
            'user': 'ml_user',
            'password': 'ml_password',
            'health_check_query': 'SELECT 1',
        },
        'neo4j': {
            'host': 'localhost',
            'port': 7687,
            'user': 'neo4j',
            'password': 'ml_password',
            'uri': 'bolt://localhost:7687',
            'health_check_query': 'RETURN 1',
        },
        'milvus': {
            'host': 'localhost',
            'port': 19530,
            'collection': 'test_knowledge_chunks',
            'health_check_endpoint': 'http://localhost:9091/healthz',
        },
        'redis': {
            'host': 'localhost',
            'port': 6379,
            'db': 1,
            'health_check_command': 'PING',
        }
    }


# =============================================================================
# Service Availability Fixtures
# =============================================================================

@pytest.fixture
def check_service_availability():
    """
    Utility fixture to check if local services are available.
    
    Returns a function that can check individual services.
    """
    import socket
    
    def check_service(host: str, port: int, timeout: float = 1.0) -> bool:
        """Check if a service is available on the given host and port."""
        try:
            with socket.create_connection((host, port), timeout=timeout):
                return True
        except (socket.error, socket.timeout):
            return False
    
    def check_all_services(services: Dict[str, Dict[str, Any]]) -> Dict[str, bool]:
        """Check availability of all services."""
        results = {}
        for service_name, config in services.items():
            results[service_name] = check_service(config['host'], config['port'])
        return results
    
    return {
        'check_service': check_service,
        'check_all_services': check_all_services,
    }


@pytest.fixture
def skip_if_no_local_services(docker_compose_services, check_service_availability):
    """
    Skip tests if local services are not available.
    
    This fixture can be used to conditionally skip integration tests
    when Docker Compose services are not running.
    """
    def skip_if_unavailable(required_services=None):
        if required_services is None:
            required_services = list(docker_compose_services.keys())
        
        unavailable_services = []
        for service_name in required_services:
            if service_name in docker_compose_services:
                config = docker_compose_services[service_name]
                if not check_service_availability['check_service'](config['host'], config['port']):
                    unavailable_services.append(service_name)
        
        if unavailable_services:
            pytest.skip(f"Required services not available: {', '.join(unavailable_services)}")
    
    return skip_if_unavailable


# =============================================================================
# Local Database Client Fixtures
# =============================================================================

@pytest.fixture
async def local_postgres_client(local_test_config, skip_if_no_local_services):
    """
    Create a local PostgreSQL client for testing.
    
    This fixture provides a real connection to the local PostgreSQL service
    for integration tests.
    """
    if local_test_config is None:
        pytest.skip("Local test config not available")
    
    skip_if_no_local_services(['postgres'])
    
    try:
        from multimodal_librarian.clients.local_postgresql_client import LocalPostgreSQLClient
        
        client = LocalPostgreSQLClient(
            host=local_test_config.postgres_host,
            port=local_test_config.postgres_port,
            database=local_test_config.postgres_db,
            user=local_test_config.postgres_user,
            password=local_test_config.postgres_password,
        )
        
        await client.connect()
        yield client
        await client.disconnect()
        
    except ImportError:
        pytest.skip("Local PostgreSQL client not available")


@pytest.fixture
async def local_neo4j_client(local_test_config, skip_if_no_local_services):
    """
    Create a local Neo4j client for testing.
    
    This fixture provides a real connection to the local Neo4j service
    for integration tests.
    """
    if local_test_config is None:
        pytest.skip("Local test config not available")
    
    skip_if_no_local_services(['neo4j'])
    
    try:
        from multimodal_librarian.clients.neo4j_client import Neo4jClient
        
        client = Neo4jClient(
            uri=f"bolt://{local_test_config.neo4j_host}:{local_test_config.neo4j_port}",
            user=local_test_config.neo4j_user,
            password=local_test_config.neo4j_password,
        )
        
        await client.connect()
        yield client
        await client.disconnect()
        
    except ImportError:
        pytest.skip("Neo4j client not available")


@pytest.fixture
async def local_milvus_client(local_test_config, skip_if_no_local_services):
    """
    Create a local Milvus client for testing.
    
    This fixture provides a real connection to the local Milvus service
    for integration tests.
    """
    if local_test_config is None:
        pytest.skip("Local test config not available")
    
    skip_if_no_local_services(['milvus'])
    
    try:
        from multimodal_librarian.clients.milvus_client import MilvusClient
        
        client = MilvusClient(
            host=local_test_config.milvus_host,
            port=local_test_config.milvus_port,
        )
        
        await client.connect()
        yield client
        await client.disconnect()
        
    except ImportError:
        pytest.skip("Milvus client not available")


@pytest.fixture
async def local_database_factory(local_test_config):
    """
    Create a database client factory configured for local services.
    
    This fixture provides a factory that creates local database clients
    for comprehensive testing.
    """
    if local_test_config is None:
        pytest.skip("Local test config not available")
    
    try:
        from multimodal_librarian.clients.database_client_factory import DatabaseClientFactory
        
        factory = DatabaseClientFactory(local_test_config)
        yield factory
        await factory.close()
        
    except ImportError:
        pytest.skip("Database client factory not available")


@pytest.fixture
def test_data_cleanup():
    """
    Fixture to clean up test data after tests.
    
    This fixture provides utilities to clean up test databases
    and ensure test isolation.
    """
    cleanup_tasks = []
    
    def register_cleanup(cleanup_func):
        """Register a cleanup function to be called after the test."""
        cleanup_tasks.append(cleanup_func)
    
    yield register_cleanup
    
    # Execute all cleanup tasks
    for cleanup_func in cleanup_tasks:
        try:
            if asyncio.iscoroutinefunction(cleanup_func):
                asyncio.run(cleanup_func())
            else:
                cleanup_func()
        except Exception as e:
            # Log cleanup errors but don't fail the test
            print(f"Cleanup error: {e}")


@pytest.fixture
def temp_test_files():
    """
    Fixture to create temporary files for testing.
    
    This fixture provides a way to create temporary files that are
    automatically cleaned up after the test.
    """
    temp_files = []
    
    def create_temp_file(content: str = "", suffix: str = ".txt") -> str:
        """Create a temporary file with the given content."""
        temp_file = tempfile.NamedTemporaryFile(mode='w', delete=False, suffix=suffix)
        temp_file.write(content)
        temp_file.close()
        temp_files.append(temp_file.name)
        return temp_file.name
    
    yield create_temp_file
    
    # Clean up temporary files
    for temp_file in temp_files:
        try:
            os.unlink(temp_file)
        except OSError:
            pass  # File might already be deleted


@pytest.fixture
def sample_conversation_data():
    """Sample conversation data for testing."""
    return {
        "thread_id": "test-thread-123",
        "user_id": "test-user-456",
        "messages": [
            {
                "message_id": "msg-1",
                "content": "What is machine learning?",
                "timestamp": "2023-01-01T10:00:00Z",
                "message_type": "USER"
            },
            {
                "message_id": "msg-2", 
                "content": "Machine learning is a subset of artificial intelligence...",
                "timestamp": "2023-01-01T10:00:05Z",
                "message_type": "SYSTEM"
            }
        ]
    }

# =============================================================================
# Import Local Database Test Fixtures
# =============================================================================

# Import all fixtures from the fixtures package to make them available
# to all tests without explicit imports
try:
    from .fixtures.database_fixtures import *
    from .fixtures.sample_data_fixtures import *
    from .fixtures.integration_fixtures import *
    from .fixtures.test_utilities import *
except ImportError:
    # Fixtures may not be available in all environments
    pass