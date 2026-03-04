"""
Test Neo4j Setup and Plugin Configuration

This test module validates that Neo4j is properly configured with required plugins
and can perform operations needed by the Multimodal Librarian application.
"""

import pytest
import time
from typing import Generator
from neo4j import GraphDatabase, Driver
from neo4j.exceptions import ServiceUnavailable

# Test configuration
NEO4J_URI = "bolt://localhost:7687"
NEO4J_USER = "neo4j"
NEO4J_PASSWORD = "ml_password"
MAX_CONNECTION_RETRIES = 10
RETRY_DELAY = 2


@pytest.fixture(scope="module")
def neo4j_driver() -> Generator[Driver, None, None]:
    """Create Neo4j driver for testing."""
    driver = None
    
    # Try to connect with retries
    for attempt in range(MAX_CONNECTION_RETRIES):
        try:
            driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))
            
            # Test connection
            with driver.session() as session:
                result = session.run("RETURN 1 as test")
                if result.single()["test"] == 1:
                    break
                    
        except ServiceUnavailable:
            if attempt < MAX_CONNECTION_RETRIES - 1:
                time.sleep(RETRY_DELAY)
            else:
                pytest.skip("Neo4j is not available for testing")
        except Exception as e:
            pytest.skip(f"Failed to connect to Neo4j: {e}")
    
    if not driver:
        pytest.skip("Could not establish Neo4j connection")
    
    yield driver
    
    # Cleanup
    if driver:
        driver.close()


@pytest.fixture
def clean_session(neo4j_driver: Driver):
    """Create a clean Neo4j session for each test."""
    with neo4j_driver.session() as session:
        # Clean up any test data before the test
        session.run("MATCH (n) WHERE n.id STARTS WITH 'test-' DETACH DELETE n")
        yield session
        # Clean up any test data after the test
        session.run("MATCH (n) WHERE n.id STARTS WITH 'test-' DETACH DELETE n")


class TestNeo4jConnection:
    """Test Neo4j connection and basic functionality."""
    
    def test_connection_established(self, neo4j_driver: Driver):
        """Test that connection to Neo4j is established."""
        with neo4j_driver.session() as session:
            result = session.run("RETURN 'connection_test' as message")
            record = result.single()
            assert record["message"] == "connection_test"
    
    def test_database_is_empty_or_accessible(self, neo4j_driver: Driver):
        """Test that database is accessible and we can query it."""
        with neo4j_driver.session() as session:
            result = session.run("MATCH (n) RETURN count(n) as nodeCount")
            node_count = result.single()["nodeCount"]
            # Should be able to get a count (even if 0)
            assert isinstance(node_count, int)
            assert node_count >= 0


class TestNeo4jPlugins:
    """Test Neo4j plugin availability and functionality."""
    
    def test_apoc_plugin_available(self, neo4j_driver: Driver):
        """Test that APOC plugin is available and functional."""
        with neo4j_driver.session() as session:
            # Test APOC version call
            result = session.run("CALL apoc.version() YIELD version RETURN version")
            version_record = result.single()
            assert version_record is not None
            assert "version" in version_record
            
            version = version_record["version"]
            assert isinstance(version, str)
            assert len(version) > 0
            
            # Test APOC functionality
            result = session.run("CALL apoc.meta.stats() YIELD labels RETURN labels")
            stats_record = result.single()
            assert stats_record is not None
    
    def test_gds_plugin_available(self, neo4j_driver: Driver):
        """Test that Graph Data Science plugin is available and functional."""
        with neo4j_driver.session() as session:
            # Test GDS version call
            result = session.run("CALL gds.version() YIELD gdsVersion RETURN gdsVersion")
            version_record = result.single()
            assert version_record is not None
            assert "gdsVersion" in version_record
            
            version = version_record["gdsVersion"]
            assert isinstance(version, str)
            assert len(version) > 0
    
    def test_gds_graph_operations(self, clean_session):
        """Test GDS graph projection and algorithm execution."""
        session = clean_session
        
        # Create test data
        session.run("""
            CREATE (a:TestNode {id: 'test-gds-1', name: 'Node A'})
            CREATE (b:TestNode {id: 'test-gds-2', name: 'Node B'})
            CREATE (c:TestNode {id: 'test-gds-3', name: 'Node C'})
            CREATE (a)-[:TEST_CONNECTS]->(b)
            CREATE (b)-[:TEST_CONNECTS]->(c)
            CREATE (c)-[:TEST_CONNECTS]->(a)
        """)
        
        # Create graph projection
        result = session.run("""
            CALL gds.graph.project(
                'test-graph-projection',
                'TestNode',
                'TEST_CONNECTS'
            )
            YIELD graphName, nodeCount, relationshipCount
            RETURN graphName, nodeCount, relationshipCount
        """)
        
        projection_record = result.single()
        assert projection_record["graphName"] == "test-graph-projection"
        assert projection_record["nodeCount"] == 3
        assert projection_record["relationshipCount"] == 3
        
        # Run PageRank algorithm
        result = session.run("""
            CALL gds.pageRank.stream('test-graph-projection')
            YIELD nodeId, score
            RETURN count(*) as resultCount, avg(score) as avgScore
        """)
        
        pagerank_record = result.single()
        assert pagerank_record["resultCount"] == 3
        assert pagerank_record["avgScore"] > 0
        
        # Clean up graph projection
        session.run("CALL gds.graph.drop('test-graph-projection')")


class TestNeo4jOperations:
    """Test Neo4j operations needed by the application."""
    
    def test_node_creation_and_retrieval(self, clean_session):
        """Test creating and retrieving nodes."""
        session = clean_session
        
        # Create a document node
        session.run("""
            CREATE (doc:Document {
                id: 'test-doc-1',
                title: 'Test Document',
                type: 'pdf',
                created_at: datetime()
            })
        """)
        
        # Retrieve the node
        result = session.run("""
            MATCH (doc:Document {id: 'test-doc-1'})
            RETURN doc.title as title, doc.type as type
        """)
        
        record = result.single()
        assert record is not None
        assert record["title"] == "Test Document"
        assert record["type"] == "pdf"
    
    def test_relationship_creation_and_traversal(self, clean_session):
        """Test creating relationships and traversing them."""
        session = clean_session
        
        # Create nodes and relationships
        session.run("""
            CREATE (doc:Document {id: 'test-doc-2', title: 'Test Document 2'})
            CREATE (concept1:Concept {id: 'test-concept-1', name: 'Machine Learning'})
            CREATE (concept2:Concept {id: 'test-concept-2', name: 'Neural Networks'})
            CREATE (doc)-[:CONTAINS]->(concept1)
            CREATE (concept1)-[:RELATED_TO]->(concept2)
        """)
        
        # Test single-hop traversal
        result = session.run("""
            MATCH (doc:Document {id: 'test-doc-2'})-[:CONTAINS]->(concept:Concept)
            RETURN concept.name as conceptName
        """)
        
        record = result.single()
        assert record["conceptName"] == "Machine Learning"
        
        # Test multi-hop traversal
        result = session.run("""
            MATCH (doc:Document {id: 'test-doc-2'})-[:CONTAINS]->(c1:Concept)-[:RELATED_TO]->(c2:Concept)
            RETURN c2.name as relatedConcept
        """)
        
        record = result.single()
        assert record["relatedConcept"] == "Neural Networks"
    
    def test_complex_queries(self, clean_session):
        """Test complex queries that the application might use."""
        session = clean_session
        
        # Create a more complex graph structure
        session.run("""
            CREATE (doc1:Document {id: 'test-doc-3', title: 'AI Research Paper'})
            CREATE (doc2:Document {id: 'test-doc-4', title: 'ML Tutorial'})
            CREATE (concept1:Concept {id: 'test-concept-3', name: 'Artificial Intelligence'})
            CREATE (concept2:Concept {id: 'test-concept-4', name: 'Machine Learning'})
            CREATE (concept3:Concept {id: 'test-concept-5', name: 'Deep Learning'})
            
            CREATE (doc1)-[:CONTAINS]->(concept1)
            CREATE (doc1)-[:CONTAINS]->(concept3)
            CREATE (doc2)-[:CONTAINS]->(concept2)
            CREATE (doc2)-[:CONTAINS]->(concept3)
            
            CREATE (concept2)-[:SUBSET_OF]->(concept1)
            CREATE (concept3)-[:SUBSET_OF]->(concept2)
        """)
        
        # Find documents that share concepts
        result = session.run("""
            MATCH (doc1:Document)-[:CONTAINS]->(shared:Concept)<-[:CONTAINS]-(doc2:Document)
            WHERE doc1.id < doc2.id
            RETURN doc1.title as doc1Title, doc2.title as doc2Title, shared.name as sharedConcept
        """)
        
        record = result.single()
        assert record is not None
        assert record["sharedConcept"] == "Deep Learning"
        
        # Find concept hierarchies
        result = session.run("""
            MATCH path = (child:Concept)-[:SUBSET_OF*]->(parent:Concept)
            WHERE child.id = 'test-concept-5'
            RETURN [node in nodes(path) | node.name] as hierarchy
        """)
        
        record = result.single()
        hierarchy = record["hierarchy"]
        assert "Deep Learning" in hierarchy
        assert "Machine Learning" in hierarchy
        assert "Artificial Intelligence" in hierarchy
    
    def test_performance_with_indexes(self, clean_session):
        """Test that queries perform well (basic performance test)."""
        session = clean_session
        
        # Create index on Document.id if it doesn't exist
        try:
            session.run("CREATE INDEX document_id_index IF NOT EXISTS FOR (d:Document) ON (d.id)")
        except:
            pass  # Index might already exist
        
        # Create some test data
        session.run("""
            UNWIND range(1, 100) as i
            CREATE (doc:Document {
                id: 'test-perf-doc-' + toString(i),
                title: 'Performance Test Document ' + toString(i)
            })
        """)
        
        # Test query performance (should be fast with index)
        import time
        start_time = time.time()
        
        result = session.run("""
            MATCH (doc:Document)
            WHERE doc.id STARTS WITH 'test-perf-doc-'
            RETURN count(doc) as docCount
        """)
        
        end_time = time.time()
        query_time = end_time - start_time
        
        record = result.single()
        assert record["docCount"] == 100
        
        # Query should complete in reasonable time (less than 1 second for this simple case)
        assert query_time < 1.0
        
        # Clean up performance test data
        session.run("MATCH (doc:Document) WHERE doc.id STARTS WITH 'test-perf-doc-' DELETE doc")


class TestNeo4jConfiguration:
    """Test Neo4j configuration and settings."""
    
    def test_memory_settings(self, neo4j_driver: Driver):
        """Test that memory settings are properly configured."""
        with neo4j_driver.session() as session:
            # Check heap memory configuration
            result = session.run("CALL dbms.listConfig() YIELD name, value WHERE name CONTAINS 'memory'")
            
            memory_configs = {record["name"]: record["value"] for record in result}
            
            # Should have some memory configuration
            assert len(memory_configs) > 0
            
            # Check for specific memory settings we configured
            heap_configs = [name for name in memory_configs.keys() if 'heap' in name.lower()]
            assert len(heap_configs) > 0
    
    def test_plugin_security_settings(self, neo4j_driver: Driver):
        """Test that plugin security settings are properly configured."""
        with neo4j_driver.session() as session:
            # Check security configuration
            result = session.run("""
                CALL dbms.listConfig() 
                YIELD name, value 
                WHERE name CONTAINS 'security' AND name CONTAINS 'procedures'
            """)
            
            security_configs = {record["name"]: record["value"] for record in result}
            
            # Should have security configurations for procedures
            assert len(security_configs) > 0
            
            # Check that APOC and GDS procedures are allowed
            unrestricted_found = False
            allowlist_found = False
            
            for name, value in security_configs.items():
                if 'unrestricted' in name and value:
                    if 'apoc' in value.lower() or 'gds' in value.lower():
                        unrestricted_found = True
                if 'allowlist' in name and value:
                    if 'apoc' in value.lower() or 'gds' in value.lower():
                        allowlist_found = True
            
            # At least one of these should be configured
            assert unrestricted_found or allowlist_found


if __name__ == "__main__":
    # Run tests directly if script is executed
    pytest.main([__file__, "-v"])