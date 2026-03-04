"""
Example tests demonstrating the use of local database fixtures.

This module provides comprehensive examples of how to use the various
test fixtures for local database testing, including unit tests,
integration tests, and performance tests.
"""

import pytest
import asyncio
import json
from typing import Dict, Any, List

# Import all fixture modules
from .database_fixtures import (
    postgres_client, neo4j_client, milvus_client, database_factory,
    mock_postgres_client, mock_neo4j_client, mock_milvus_client,
    clean_postgres_test_data, clean_neo4j_test_data, clean_milvus_test_data,
    require_postgres, require_neo4j, require_milvus, require_all_services
)
from .sample_data_fixtures import (
    sample_users, sample_documents, sample_document_chunks,
    sample_conversations, sample_messages, sample_knowledge_nodes,
    sample_knowledge_relationships, sample_vectors, complete_sample_dataset,
    insert_sample_users, insert_sample_knowledge_graph, insert_sample_vectors
)
from .integration_fixtures import (
    integrated_database_clients, populated_test_database,
    document_processing_scenario, conversation_scenario, search_scenario,
    performance_test_data, error_handling_scenario
)
from .test_utilities import (
    PerformanceTracker, DataValidator, DatabaseHealthChecker,
    TestDataGenerator, TestResultAnalyzer, TestLogger
)


# =============================================================================
# Unit Test Examples (Using Mock Fixtures)
# =============================================================================

class TestUnitTestExamples:
    """Examples of unit tests using mock database fixtures."""
    
    def test_mock_postgres_basic_operations(self, mock_postgres_client):
        """Test basic PostgreSQL operations with mock client."""
        # Configure mock behavior
        mock_postgres_client.execute_query.return_value = [
            {"id": "test-1", "name": "Test User 1"},
            {"id": "test-2", "name": "Test User 2"}
        ]
        
        # Test the mock
        result = asyncio.run(mock_postgres_client.execute_query("SELECT * FROM users"))
        
        assert len(result) == 2
        assert result[0]["name"] == "Test User 1"
        mock_postgres_client.execute_query.assert_called_once()
    
    def test_mock_neo4j_basic_operations(self, mock_neo4j_client):
        """Test basic Neo4j operations with mock client."""
        # Configure mock behavior
        mock_neo4j_client.execute_query.return_value = [
            {"n.name": "Machine Learning", "n.id": "concept-1"}
        ]
        
        # Test the mock
        result = asyncio.run(mock_neo4j_client.execute_query("MATCH (n:Concept) RETURN n"))
        
        assert len(result) == 1
        assert result[0]["n.name"] == "Machine Learning"
        mock_neo4j_client.execute_query.assert_called_once()
    
    def test_mock_milvus_basic_operations(self, mock_milvus_client):
        """Test basic Milvus operations with mock client."""
        # Configure mock behavior
        mock_milvus_client.search_vectors.return_value = [
            {"id": "vec-1", "distance": 0.1, "metadata": {"title": "Test Doc"}}
        ]
        
        # Test the mock
        query_vector = [0.1] * 384
        result = asyncio.run(mock_milvus_client.search_vectors(
            collection_name="test_collection",
            query_vectors=[query_vector],
            limit=10
        ))
        
        assert len(result) == 1
        assert result[0]["id"] == "vec-1"
        mock_milvus_client.search_vectors.assert_called_once()
    
    def test_data_validation_utilities(self):
        """Test data validation utilities."""
        validator = DataValidator()
        
        # Test valid user data
        valid_user = {
            "id": "test-user-1",
            "username": "test_user",
            "email": "test@example.com",
            "role": "user"
        }
        errors = validator.validate_user_data(valid_user)
        assert len(errors) == 0
        
        # Test invalid user data
        invalid_user = {
            "id": "test-user-2",
            "username": "test_user_2",
            "email": "invalid-email",  # Invalid email
            "role": "invalid_role"     # Invalid role
        }
        errors = validator.validate_user_data(invalid_user)
        assert len(errors) == 2
        assert any("Invalid email format" in error for error in errors)
        assert any("Invalid role" in error for error in errors)


# =============================================================================
# Integration Test Examples (Using Real Database Fixtures)
# =============================================================================

class TestIntegrationExamples:
    """Examples of integration tests using real database fixtures."""
    
    @pytest.mark.asyncio
    async def test_postgres_real_operations(self, postgres_client, clean_postgres_test_data):
        """Test real PostgreSQL operations."""
        # Insert test user
        insert_sql = """
            INSERT INTO users (id, username, email, password_hash, salt, role, is_active, is_verified)
            VALUES (:id, :username, :email, :password_hash, :salt, :role, :is_active, :is_verified)
        """
        
        user_data = {
            "id": "test-integration-user-1",
            "username": "integration_test_user",
            "email": "integration@test.local",
            "password_hash": "test_hash",
            "salt": "test_salt",
            "role": "user",
            "is_active": True,
            "is_verified": True
        }
        
        await postgres_client.execute_command(insert_sql, user_data)
        
        # Query the user back
        select_sql = "SELECT * FROM users WHERE id = :id"
        result = await postgres_client.execute_query(select_sql, {"id": user_data["id"]})
        
        assert len(result) == 1
        assert result[0]["username"] == user_data["username"]
        assert result[0]["email"] == user_data["email"]
    
    @pytest.mark.asyncio
    async def test_neo4j_real_operations(self, neo4j_client, clean_neo4j_test_data):
        """Test real Neo4j operations."""
        # Create test nodes
        create_query = """
            CREATE (d:Document {id: 'test-doc-1', title: 'Test Document'})
            CREATE (c:Concept {id: 'test-concept-1', name: 'Machine Learning'})
            CREATE (d)-[:CONTAINS]->(c)
            RETURN d, c
        """
        
        result = await neo4j_client.execute_query(create_query)
        assert len(result) == 1
        
        # Query the relationship
        query = """
            MATCH (d:Document)-[:CONTAINS]->(c:Concept)
            WHERE d.id = 'test-doc-1'
            RETURN d.title as doc_title, c.name as concept_name
        """
        
        result = await neo4j_client.execute_query(query)
        assert len(result) == 1
        assert result[0]["doc_title"] == "Test Document"
        assert result[0]["concept_name"] == "Machine Learning"
    
    @pytest.mark.asyncio
    async def test_milvus_real_operations(self, milvus_client, clean_milvus_test_data):
        """Test real Milvus operations."""
        collection_name = "test_integration_collection"
        
        # Create collection
        await milvus_client.create_collection(
            collection_name=collection_name,
            dimension=384,
            description="Integration test collection"
        )
        
        # Insert test vectors
        test_vectors = []
        for i in range(5):
            vector = [0.1 * i] * 384  # Simple test vectors
            test_vectors.append({
                "id": f"test-vec-{i}",
                "vector": vector,
                "metadata": {"title": f"Test Document {i}"}
            })
        
        result = await milvus_client.insert_vectors(
            collection_name=collection_name,
            data=test_vectors
        )
        
        assert result["insert_count"] == 5
        
        # Search for similar vectors
        query_vector = [0.1] * 384  # Should be similar to first vector
        search_results = await milvus_client.search_vectors(
            collection_name=collection_name,
            query_vectors=[query_vector],
            limit=3
        )
        
        assert len(search_results) > 0
        
        # Cleanup
        await milvus_client.drop_collection(collection_name)


# =============================================================================
# Sample Data Fixture Examples
# =============================================================================

class TestSampleDataExamples:
    """Examples of using sample data fixtures."""
    
    def test_sample_users_fixture(self, sample_users):
        """Test sample users fixture."""
        assert len(sample_users) >= 4  # At least the predefined users
        
        # Check that we have different roles
        roles = {user.role for user in sample_users}
        assert "admin" in roles
        assert "user" in roles
        assert "ml_researcher" in roles
        
        # Validate user data
        validator = DataValidator()
        for user in sample_users:
            user_dict = {
                "id": user.id,
                "username": user.username,
                "email": user.email,
                "role": user.role
            }
            errors = validator.validate_user_data(user_dict)
            assert len(errors) == 0, f"Invalid user data: {errors}"
    
    def test_sample_documents_fixture(self, sample_documents):
        """Test sample documents fixture."""
        assert len(sample_documents) >= 5  # At least the predefined documents
        
        # Check document properties
        for doc in sample_documents:
            assert doc.id.startswith("test-doc-")
            assert doc.title is not None
            assert doc.filename.endswith(".pdf")
            assert doc.file_size > 0
            assert doc.page_count > 0
        
        # Check that we have completed documents
        completed_docs = [doc for doc in sample_documents if doc.status == "completed"]
        assert len(completed_docs) > 0
    
    def test_sample_vectors_fixture(self, sample_vectors):
        """Test sample vectors fixture."""
        assert len(sample_vectors) == 20  # Should generate 20 vectors
        
        # Check vector properties
        for vector in sample_vectors:
            assert vector.id.startswith("test-vector-")
            assert isinstance(vector.vector, list)
            assert len(vector.vector) in [384, 768, 1536]  # Valid dimensions
            assert vector.metadata is not None
            
            # Check vector normalization (should be approximately unit length)
            magnitude = sum(x**2 for x in vector.vector) ** 0.5
            assert abs(magnitude - 1.0) < 0.01  # Allow small floating point errors
    
    def test_complete_sample_dataset(self, complete_sample_dataset):
        """Test complete sample dataset fixture."""
        dataset = complete_sample_dataset
        
        # Check all data types are present
        required_keys = [
            "users", "documents", "document_chunks", "conversations",
            "messages", "knowledge_nodes", "knowledge_relationships", "vectors"
        ]
        
        for key in required_keys:
            assert key in dataset
            assert len(dataset[key]) > 0
        
        # Check data consistency
        user_ids = {user.id for user in dataset["users"]}
        doc_user_ids = {doc.user_id for doc in dataset["documents"]}
        
        # All document user_ids should reference existing users
        assert doc_user_ids.issubset(user_ids)


# =============================================================================
# Integration Scenario Examples
# =============================================================================

class TestIntegrationScenarios:
    """Examples of using integration scenario fixtures."""
    
    @pytest.mark.asyncio
    async def test_document_processing_scenario(self, document_processing_scenario):
        """Test document processing integration scenario."""
        scenario = document_processing_scenario
        clients = scenario["clients"]
        users = scenario["users"]
        documents = scenario["documents"]
        
        assert len(users) == 3
        assert len(documents) == 2
        
        # Verify users were inserted in PostgreSQL
        for user in users:
            result = await clients["postgres"].execute_query(
                "SELECT * FROM users WHERE id = :id",
                {"id": user.id}
            )
            assert len(result) == 1
            assert result[0]["username"] == user.username
        
        # Verify documents were inserted in PostgreSQL
        for doc in documents:
            result = await clients["postgres"].execute_query(
                "SELECT * FROM documents WHERE id = :id",
                {"id": doc.id}
            )
            assert len(result) == 1
            assert result[0]["title"] == doc.title
        
        # Verify knowledge graph was created in Neo4j
        kg_result = await clients["neo4j"].execute_query(
            "MATCH (d:Document) RETURN count(d) as doc_count"
        )
        assert kg_result[0]["doc_count"] >= len(documents)
        
        # Verify vectors were created in Milvus
        collections = await clients["milvus"].list_collections()
        assert "test_document_vectors" in collections
    
    @pytest.mark.asyncio
    async def test_search_scenario(self, search_scenario):
        """Test search integration scenario."""
        scenario = search_scenario
        clients = scenario["clients"]
        collection_name = scenario["collection_name"]
        vectors = scenario["vectors"]
        
        # Test vector search
        if vectors:
            query_vector = vectors[0].vector  # Use first vector as query
            search_results = await clients["milvus"].search_vectors(
                collection_name=collection_name,
                query_vectors=[query_vector],
                limit=5
            )
            
            assert len(search_results) > 0
            # First result should be the query vector itself (highest similarity)
            assert search_results[0]["id"] == vectors[0].id
        
        # Test knowledge graph search
        kg_results = await clients["neo4j"].execute_query(
            "MATCH (n) WHERE n.id STARTS WITH 'test-' RETURN count(n) as node_count"
        )
        assert kg_results[0]["node_count"] >= len(scenario["knowledge_nodes"])


# =============================================================================
# Performance Testing Examples
# =============================================================================

class TestPerformanceExamples:
    """Examples of performance testing with fixtures."""
    
    @pytest.mark.asyncio
    async def test_performance_tracking(self, integrated_database_clients):
        """Test performance tracking utilities."""
        clients = integrated_database_clients
        tracker = PerformanceTracker()
        
        # Measure PostgreSQL operations
        async with tracker.measure("postgres_health_check"):
            health = await clients["postgres"].health_check()
            assert health["status"] == "healthy"
        
        async with tracker.measure("postgres_simple_query"):
            result = await clients["postgres"].execute_query("SELECT 1 as test")
            assert result[0]["test"] == 1
        
        # Measure Neo4j operations
        async with tracker.measure("neo4j_health_check"):
            health = await clients["neo4j"].health_check()
            assert health["status"] == "healthy"
        
        # Get performance summary
        summary = tracker.get_summary()
        assert summary["total_operations"] == 3
        assert summary["successful_operations"] == 3
        assert summary["success_rate"] == 1.0
        
        # Check operation-specific metrics
        postgres_metrics = tracker.get_metrics("postgres_health_check")
        assert len(postgres_metrics) == 1
        assert postgres_metrics[0].success is True
        assert postgres_metrics[0].duration > 0
    
    @pytest.mark.asyncio
    async def test_database_health_checker(self, integrated_database_clients):
        """Test database health checker utility."""
        clients = integrated_database_clients
        health_checker = DatabaseHealthChecker()
        
        # Check individual service health
        postgres_health = await health_checker.check_postgres_health(clients["postgres"])
        assert postgres_health["status"] == "healthy"
        assert postgres_health["version_check"] is True
        
        neo4j_health = await health_checker.check_neo4j_health(clients["neo4j"])
        assert neo4j_health["status"] == "healthy"
        assert neo4j_health["components_check"] is True
        
        milvus_health = await health_checker.check_milvus_health(clients["milvus"])
        assert milvus_health["status"] == "healthy"
        assert milvus_health["collections_check"] is True
        
        # Check all services health
        all_health = await health_checker.check_all_services(clients)
        assert all_health["overall"]["status"] == "healthy"
        assert all_health["overall"]["services_checked"] == 3
        assert all_health["overall"]["healthy_services"] == 3
    
    @pytest.mark.asyncio
    async def test_performance_test_data(self, performance_test_data):
        """Test performance test data fixture."""
        scenario = performance_test_data
        clients = scenario["clients"]
        perf_data = scenario["performance_data"]
        
        # Verify performance data was created
        assert perf_data["users_created"] == 50
        assert perf_data["vectors_created"] == 1000
        assert perf_data["nodes_created"] == 200
        
        # Test querying the performance data
        user_count_result = await clients["postgres"].execute_query(
            "SELECT COUNT(*) as count FROM users WHERE username LIKE 'perf_user_%'"
        )
        assert user_count_result[0]["count"] == 50
        
        node_count_result = await clients["neo4j"].execute_query(
            "MATCH (n:PerfTestNode) RETURN count(n) as count"
        )
        assert node_count_result[0]["count"] == 200
        
        # Test vector search performance
        collection_name = scenario["collection_name"]
        collections = await clients["milvus"].list_collections()
        assert collection_name in collections


# =============================================================================
# Utility Function Examples
# =============================================================================

class TestUtilityExamples:
    """Examples of using test utility functions."""
    
    def test_test_data_generator(self):
        """Test data generation utilities."""
        generator = TestDataGenerator()
        
        # Test random vector generation
        vector = generator.generate_random_vector(384)
        assert len(vector) == 384
        
        # Check normalization
        magnitude = sum(x**2 for x in vector) ** 0.5
        assert abs(magnitude - 1.0) < 0.01
        
        # Test similar vector generation
        similar_vector = generator.generate_similar_vector(vector, similarity=0.9)
        assert len(similar_vector) == 384
        
        # Check similarity (dot product should be close to 0.9)
        dot_product = sum(a * b for a, b in zip(vector, similar_vector))
        assert abs(dot_product - 0.9) < 0.1
        
        # Test document generation
        user_ids = ["user-1", "user-2", "user-3"]
        documents = generator.generate_test_documents(5, user_ids)
        
        assert len(documents) == 5
        for doc in documents:
            assert doc["user_id"] in user_ids
            assert doc["id"].startswith("test-gen-doc-")
            assert doc["file_size"] > 0
    
    def test_test_result_analyzer(self):
        """Test result analysis utilities."""
        analyzer = TestResultAnalyzer()
        
        # Add some test results
        analyzer.add_result("test_1", True, 0.5, category="unit")
        analyzer.add_result("test_2", True, 1.2, category="integration")
        analyzer.add_result("test_3", False, 0.8, category="unit", error="Assertion failed")
        analyzer.add_result("test_4", True, 2.1, category="performance")
        
        # Get summary
        summary = analyzer.get_summary()
        
        assert summary["total_tests"] == 4
        assert summary["successful_tests"] == 3
        assert summary["failed_tests"] == 1
        assert summary["success_rate"] == 0.75
        assert summary["avg_duration"] == (0.5 + 1.2 + 0.8 + 2.1) / 4
        assert "test_3" in summary["failed_test_names"]
    
    def test_test_logger(self):
        """Test logging utilities."""
        logger = TestLogger("test_example")
        
        # Log test events
        logger.log_test_start("example_test", database="postgres")
        logger.log_operation("insert_user", True, 0.1, user_id="test-1")
        logger.log_operation("query_user", False, 0.05, error="User not found")
        logger.log_test_end("example_test", True, 1.5, assertions=5)
        
        # Check logs
        logs = logger.get_logs()
        assert len(logs) == 4
        
        assert logs[0]["event"] == "test_start"
        assert logs[0]["test_name"] == "example_test"
        assert logs[0]["context"]["database"] == "postgres"
        
        assert logs[1]["event"] == "operation"
        assert logs[1]["operation"] == "insert_user"
        assert logs[1]["success"] is True
        
        assert logs[2]["event"] == "operation"
        assert logs[2]["operation"] == "query_user"
        assert logs[2]["success"] is False
        
        assert logs[3]["event"] == "test_end"
        assert logs[3]["test_name"] == "example_test"
        assert logs[3]["success"] is True
        assert logs[3]["duration"] == 1.5


# =============================================================================
# Error Handling Examples
# =============================================================================

class TestErrorHandlingExamples:
    """Examples of error handling in database tests."""
    
    @pytest.mark.asyncio
    async def test_error_handling_scenario(self, error_handling_scenario):
        """Test error handling integration scenario."""
        scenario = error_handling_scenario
        clients = scenario["clients"]
        error_scenarios = scenario["error_scenarios"]
        
        # Check that error scenarios were captured
        assert len(error_scenarios["invalid_data"]) > 0 or \
               len(error_scenarios["constraint_violations"]) > 0
        
        # Test handling of connection errors
        try:
            # Try to query with invalid parameters
            await clients["postgres"].execute_query("")  # Empty query should fail
            assert False, "Expected query to fail"
        except Exception as e:
            assert "empty" in str(e).lower() or "invalid" in str(e).lower()
    
    @pytest.mark.asyncio
    async def test_service_unavailable_handling(self, mock_postgres_client):
        """Test handling when services are unavailable."""
        # Configure mock to simulate service unavailability
        mock_postgres_client.health_check.return_value = {
            "status": "unhealthy",
            "error": "Connection refused"
        }
        
        health = await mock_postgres_client.health_check()
        assert health["status"] == "unhealthy"
        assert "Connection refused" in health["error"]
        
        # Test graceful degradation
        mock_postgres_client.execute_query.side_effect = Exception("Service unavailable")
        
        with pytest.raises(Exception) as exc_info:
            await mock_postgres_client.execute_query("SELECT 1")
        
        assert "Service unavailable" in str(exc_info.value)


if __name__ == "__main__":
    # Run the example tests
    pytest.main([__file__, "-v"])