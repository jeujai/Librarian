# Local Database Test Fixtures

This directory contains comprehensive test fixtures for local database testing in the Multimodal Librarian application. The fixtures support testing with PostgreSQL, Neo4j, and Milvus databases in both real and mocked configurations.

## Overview

The test fixtures are organized into several modules:

- **`database_fixtures.py`** - Database connection fixtures (real and mock)
- **`sample_data_fixtures.py`** - Sample data generation for realistic testing
- **`integration_fixtures.py`** - Multi-database integration scenarios
- **`test_utilities.py`** - Utility functions for testing and analysis
- **`test_fixtures_example.py`** - Comprehensive examples of fixture usage

## Quick Start

### Basic Unit Testing (Mock Fixtures)

```python
import pytest
from tests.fixtures.database_fixtures import mock_postgres_client

def test_user_service(mock_postgres_client):
    """Test user service with mocked database."""
    # Configure mock behavior
    mock_postgres_client.execute_query.return_value = [
        {"id": "user-1", "username": "test_user"}
    ]
    
    # Test your service
    result = await user_service.get_user("user-1")
    assert result["username"] == "test_user"
```

### Integration Testing (Real Database Fixtures)

```python
import pytest
from tests.fixtures.database_fixtures import postgres_client, clean_postgres_test_data

@pytest.mark.asyncio
async def test_user_crud_operations(postgres_client, clean_postgres_test_data):
    """Test CRUD operations with real PostgreSQL."""
    # Insert test user
    await postgres_client.execute_command(
        "INSERT INTO users (id, username, email) VALUES (:id, :username, :email)",
        {"id": "test-1", "username": "test_user", "email": "test@example.com"}
    )
    
    # Query user back
    result = await postgres_client.execute_query(
        "SELECT * FROM users WHERE id = :id",
        {"id": "test-1"}
    )
    
    assert len(result) == 1
    assert result[0]["username"] == "test_user"
```

### Multi-Database Integration Testing

```python
import pytest
from tests.fixtures.integration_fixtures import integrated_database_clients

@pytest.mark.asyncio
async def test_document_processing_pipeline(integrated_database_clients):
    """Test complete document processing across all databases."""
    clients = integrated_database_clients
    
    # Insert document in PostgreSQL
    await clients["postgres"].execute_command(...)
    
    # Create knowledge graph in Neo4j
    await clients["neo4j"].execute_query(...)
    
    # Store vectors in Milvus
    await clients["milvus"].insert_vectors(...)
```

## Fixture Categories

### 1. Database Connection Fixtures

#### Real Database Fixtures
- `postgres_client` - Real PostgreSQL client
- `neo4j_client` - Real Neo4j client  
- `milvus_client` - Real Milvus client
- `database_factory` - Factory for all database clients
- `integrated_database_clients` - All clients with clean test data

#### Mock Database Fixtures
- `mock_postgres_client` - Mocked PostgreSQL client
- `mock_neo4j_client` - Mocked Neo4j client
- `mock_milvus_client` - Mocked Milvus client
- `mock_database_factory` - Mocked database factory

#### Service Availability Fixtures
- `require_postgres` - Skip test if PostgreSQL unavailable
- `require_neo4j` - Skip test if Neo4j unavailable
- `require_milvus` - Skip test if Milvus unavailable
- `require_all_services` - Skip test if any service unavailable

### 2. Sample Data Fixtures

#### Basic Sample Data
- `sample_users` - Realistic user accounts
- `sample_documents` - Document metadata and content
- `sample_document_chunks` - Document chunks with content
- `sample_conversations` - Conversation threads
- `sample_messages` - Chat messages
- `sample_knowledge_nodes` - Knowledge graph nodes
- `sample_knowledge_relationships` - Knowledge graph relationships
- `sample_vectors` - Vector embeddings

#### Composite Data
- `complete_sample_dataset` - All sample data types in one fixture

#### Data Insertion Helpers
- `insert_sample_users` - Insert users into PostgreSQL with cleanup
- `insert_sample_knowledge_graph` - Insert knowledge graph into Neo4j with cleanup
- `insert_sample_vectors` - Insert vectors into Milvus with cleanup

### 3. Integration Scenario Fixtures

#### Realistic Scenarios
- `populated_test_database` - Fully populated test environment
- `document_processing_scenario` - Document upload and processing
- `conversation_scenario` - Chat and conversation testing
- `search_scenario` - Vector and knowledge graph search
- `performance_test_data` - Large datasets for performance testing
- `error_handling_scenario` - Error conditions and recovery

### 4. Data Cleanup Fixtures

#### Individual Database Cleanup
- `clean_postgres_test_data` - Clean PostgreSQL test data
- `clean_neo4j_test_data` - Clean Neo4j test data
- `clean_milvus_test_data` - Clean Milvus test data
- `clean_all_test_data` - Clean all databases

#### Transaction-Based Cleanup
- `postgres_transaction` - PostgreSQL transaction that rolls back
- `neo4j_transaction` - Neo4j transaction that rolls back

## Configuration

### Environment Variables

Set these environment variables for local testing:

```bash
# Database configuration
ML_ENVIRONMENT=test
DATABASE_TYPE=local

# PostgreSQL
POSTGRES_HOST=localhost
POSTGRES_PORT=5432
POSTGRES_DB=multimodal_librarian_test
POSTGRES_USER=ml_user
POSTGRES_PASSWORD=ml_password

# Neo4j
NEO4J_HOST=localhost
NEO4J_PORT=7687
NEO4J_USER=neo4j
NEO4J_PASSWORD=ml_password

# Milvus
MILVUS_HOST=localhost
MILVUS_PORT=19530
```

### Docker Compose Setup

Start local services with Docker Compose:

```bash
# Start all services
docker-compose -f docker-compose.local.yml up -d

# Wait for services to be ready
./scripts/wait-for-services.sh

# Run tests
pytest tests/ -v
```

## Usage Patterns

### 1. Unit Tests with Mocks

Use mock fixtures for fast unit tests that don't require real databases:

```python
def test_service_logic(mock_postgres_client):
    """Fast unit test with mocked database."""
    # Configure mock responses
    mock_postgres_client.execute_query.return_value = expected_data
    
    # Test your service logic
    result = service.process_data()
    
    # Verify mock was called correctly
    mock_postgres_client.execute_query.assert_called_with(expected_query)
```

### 2. Integration Tests with Real Databases

Use real database fixtures for integration tests:

```python
@pytest.mark.asyncio
async def test_database_integration(postgres_client, clean_postgres_test_data):
    """Integration test with real database."""
    # Test actual database operations
    await postgres_client.execute_command(insert_sql, data)
    result = await postgres_client.execute_query(select_sql, params)
    
    # Verify real database state
    assert len(result) == expected_count
```

### 3. Multi-Database Scenarios

Use integration fixtures for complex scenarios:

```python
@pytest.mark.asyncio
async def test_full_pipeline(document_processing_scenario):
    """Test complete document processing pipeline."""
    scenario = document_processing_scenario
    clients = scenario["clients"]
    
    # Test cross-database operations
    # PostgreSQL -> Neo4j -> Milvus
```

### 4. Performance Testing

Use performance fixtures and utilities:

```python
@pytest.mark.asyncio
async def test_performance(performance_test_data):
    """Test performance with large datasets."""
    scenario = performance_test_data
    tracker = PerformanceTracker()
    
    async with tracker.measure("bulk_insert"):
        # Perform bulk operations
        pass
    
    summary = tracker.get_summary()
    assert summary["avg_duration"] < max_acceptable_time
```

## Best Practices

### 1. Test Isolation

Always use cleanup fixtures to ensure test isolation:

```python
# Good: Automatic cleanup
async def test_with_cleanup(postgres_client, clean_postgres_test_data):
    # Test data is cleaned before and after test
    pass

# Good: Transaction rollback
async def test_with_transaction(postgres_transaction):
    # All changes are rolled back automatically
    pass
```

### 2. Service Availability

Use availability fixtures to skip tests when services are unavailable:

```python
@pytest.mark.asyncio
async def test_requires_postgres(postgres_client, require_postgres):
    """Test is skipped if PostgreSQL is not available."""
    # Test will be skipped if PostgreSQL is not running
    pass
```

### 3. Realistic Test Data

Use sample data fixtures for realistic testing:

```python
def test_with_realistic_data(sample_users, sample_documents):
    """Test with realistic sample data."""
    # Use pre-generated realistic test data
    for user in sample_users:
        # Test with realistic user data
        pass
```

### 4. Performance Monitoring

Use performance utilities to monitor test performance:

```python
@pytest.mark.asyncio
async def test_with_performance_tracking(integrated_database_clients):
    """Test with performance monitoring."""
    tracker = PerformanceTracker()
    health_checker = DatabaseHealthChecker(tracker)
    
    # Monitor database health and performance
    health = await health_checker.check_all_services(clients)
    
    # Analyze performance metrics
    summary = tracker.get_summary()
```

## Troubleshooting

### Common Issues

1. **Services Not Available**
   ```
   pytest.skip: PostgreSQL service not available
   ```
   - Ensure Docker Compose services are running
   - Check service health with `docker-compose ps`
   - Verify network connectivity

2. **Test Data Conflicts**
   ```
   IntegrityError: duplicate key value violates unique constraint
   ```
   - Use cleanup fixtures: `clean_postgres_test_data`
   - Use transaction fixtures: `postgres_transaction`
   - Ensure test data uses unique IDs

3. **Slow Tests**
   ```
   Tests taking too long to run
   ```
   - Use mock fixtures for unit tests
   - Use smaller sample datasets
   - Run integration tests separately

4. **Memory Issues**
   ```
   MemoryError during test execution
   ```
   - Reduce performance test data size
   - Use cleanup fixtures to free memory
   - Run tests in smaller batches

### Debugging Tips

1. **Enable Debug Logging**
   ```python
   import logging
   logging.basicConfig(level=logging.DEBUG)
   ```

2. **Check Service Health**
   ```python
   health_checker = DatabaseHealthChecker()
   health = await health_checker.check_all_services(clients)
   print(health)
   ```

3. **Monitor Performance**
   ```python
   tracker = PerformanceTracker()
   # ... run tests ...
   summary = tracker.get_summary()
   tracker.export_to_json("test_performance.json")
   ```

4. **Validate Test Data**
   ```python
   validator = DataValidator()
   errors = validator.validate_user_data(user_data)
   if errors:
       print(f"Data validation errors: {errors}")
   ```

## Contributing

When adding new fixtures:

1. Follow the existing naming conventions
2. Include comprehensive docstrings
3. Add cleanup functionality
4. Provide usage examples
5. Update this README

### Fixture Naming Conventions

- Real database fixtures: `{service}_client` (e.g., `postgres_client`)
- Mock fixtures: `mock_{service}_client` (e.g., `mock_postgres_client`)
- Sample data: `sample_{data_type}` (e.g., `sample_users`)
- Cleanup fixtures: `clean_{service}_test_data` (e.g., `clean_postgres_test_data`)
- Scenario fixtures: `{scenario_name}_scenario` (e.g., `document_processing_scenario`)

### Testing Your Fixtures

Test new fixtures with the example test file:

```bash
pytest tests/fixtures/test_fixtures_example.py -v
```

## Related Documentation

- [Local Development Setup](../../docs/local-development-setup.md)
- [Database Configuration](../../database/README.md)
- [Testing Guide](../../docs/testing-guide.md)
- [Docker Compose Setup](../../docker-compose.local.yml)