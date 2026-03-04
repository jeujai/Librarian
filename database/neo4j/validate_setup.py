#!/usr/bin/env python3
"""
Neo4j Setup Validation Script

This script validates that Neo4j is properly configured with required plugins
and can perform basic operations needed by the Multimodal Librarian application.
"""

import sys
import time
import logging
from typing import Dict, List, Optional, Tuple
from neo4j import GraphDatabase, Driver
from neo4j.exceptions import ServiceUnavailable, AuthError

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class Neo4jValidator:
    """Validates Neo4j setup and plugin configuration."""
    
    def __init__(self, uri: str = "bolt://localhost:7687", user: str = "neo4j", password: str = "ml_password"):
        self.uri = uri
        self.user = user
        self.password = password
        self.driver: Optional[Driver] = None
        
    def connect(self, max_retries: int = 5, retry_delay: int = 5) -> bool:
        """Connect to Neo4j with retries."""
        for attempt in range(max_retries):
            try:
                logger.info(f"Attempting to connect to Neo4j (attempt {attempt + 1}/{max_retries})")
                self.driver = GraphDatabase.driver(self.uri, auth=(self.user, self.password))
                
                # Test connection
                with self.driver.session() as session:
                    result = session.run("RETURN 1 as test")
                    test_value = result.single()["test"]
                    if test_value == 1:
                        logger.info("Successfully connected to Neo4j")
                        return True
                        
            except (ServiceUnavailable, AuthError) as e:
                logger.warning(f"Connection attempt {attempt + 1} failed: {e}")
                if attempt < max_retries - 1:
                    logger.info(f"Retrying in {retry_delay} seconds...")
                    time.sleep(retry_delay)
                else:
                    logger.error("Failed to connect to Neo4j after all retries")
                    return False
            except Exception as e:
                logger.error(f"Unexpected error during connection: {e}")
                return False
                
        return False
    
    def close(self):
        """Close the Neo4j connection."""
        if self.driver:
            self.driver.close()
            logger.info("Neo4j connection closed")
    
    def validate_apoc_plugin(self) -> Tuple[bool, str]:
        """Validate APOC plugin is loaded and functional."""
        try:
            with self.driver.session() as session:
                # Check if APOC procedures are available (using a common one)
                result = session.run("SHOW PROCEDURES YIELD name WHERE name STARTS WITH 'apoc' RETURN count(name) as apocCount")
                count_record = result.single()
                
                if count_record and count_record["apocCount"] > 0:
                    apoc_count = count_record["apocCount"]
                    logger.info(f"APOC plugin detected with {apoc_count} procedures available")
                    
                    # Test APOC functionality with a simple procedure
                    result = session.run("CALL apoc.meta.stats() YIELD labels RETURN labels")
                    stats_record = result.single()
                    if stats_record is not None:
                        logger.info("APOC functionality test passed")
                        return True, f"APOC Core (with {apoc_count} procedures)"
                    else:
                        return False, "APOC meta.stats failed"
                else:
                    return False, "No APOC procedures found"
                    
        except Exception as e:
            logger.error(f"APOC validation failed: {e}")
            return False, str(e)
    
    def validate_gds_plugin(self) -> Tuple[bool, str]:
        """Validate Graph Data Science plugin is loaded and functional."""
        try:
            with self.driver.session() as session:
                # Check if GDS is available
                result = session.run("CALL gds.version() YIELD gdsVersion RETURN gdsVersion")
                version_record = result.single()
                
                if version_record:
                    version = version_record["gdsVersion"]
                    logger.info(f"GDS plugin detected, version: {version}")
                    
                    # Test GDS functionality with a simple graph projection
                    # First, create some test data
                    session.run("""
                        MERGE (a:TestNode {id: 'test1', name: 'Node 1'})
                        MERGE (b:TestNode {id: 'test2', name: 'Node 2'})
                        MERGE (c:TestNode {id: 'test3', name: 'Node 3'})
                        MERGE (a)-[:TEST_REL]->(b)
                        MERGE (b)-[:TEST_REL]->(c)
                    """)
                    
                    # Create a graph projection
                    session.run("""
                        CALL gds.graph.project(
                            'test-validation-graph',
                            'TestNode',
                            'TEST_REL'
                        )
                    """)
                    
                    # Run a simple algorithm
                    result = session.run("""
                        CALL gds.pageRank.stream('test-validation-graph')
                        YIELD nodeId, score
                        RETURN count(*) as nodeCount
                    """)
                    
                    node_count = result.single()["nodeCount"]
                    logger.info(f"GDS PageRank test completed on {node_count} nodes")
                    
                    # Clean up
                    session.run("CALL gds.graph.drop('test-validation-graph')")
                    session.run("MATCH (n:TestNode) DETACH DELETE n")
                    
                    logger.info("GDS functionality test passed")
                    return True, f"GDS v{version}"
                else:
                    return False, "GDS version not found"
                    
        except Exception as e:
            logger.error(f"GDS validation failed: {e}")
            # Clean up in case of error
            try:
                with self.driver.session() as session:
                    session.run("CALL gds.graph.drop('test-validation-graph')")
                    session.run("MATCH (n:TestNode) DETACH DELETE n")
            except:
                pass
            return False, str(e)
    
    def validate_basic_operations(self) -> Tuple[bool, str]:
        """Validate basic Neo4j operations needed by the application."""
        try:
            with self.driver.session() as session:
                # Clean up any existing validation data first
                session.run("""
                    MATCH (n) 
                    WHERE n.id STARTS WITH 'validation-'
                    DETACH DELETE n
                """)
                
                # Test node creation
                session.run("""
                    CREATE (doc:Document {
                        id: 'validation-doc-1',
                        title: 'Validation Document',
                        type: 'test'
                    })
                """)
                
                # Test node query
                result = session.run("""
                    MATCH (doc:Document {id: 'validation-doc-1'})
                    RETURN doc.title as title
                """)
                
                record = result.single()
                if not record or record["title"] != "Validation Document":
                    return False, "Node creation/query test failed"
                
                # Test relationship creation
                session.run("""
                    MATCH (doc:Document {id: 'validation-doc-1'})
                    CREATE (concept:Concept {
                        id: 'validation-concept-1',
                        name: 'Test Concept Validation',
                        type: 'validation'
                    })
                    CREATE (doc)-[:CONTAINS]->(concept)
                """)
                
                # Test relationship query
                result = session.run("""
                    MATCH (doc:Document {id: 'validation-doc-1'})-[:CONTAINS]->(concept:Concept)
                    RETURN concept.name as conceptName
                """)
                
                record = result.single()
                if not record or record["conceptName"] != "Test Concept Validation":
                    return False, "Relationship creation/query test failed"
                
                # Test complex query (multi-hop)
                session.run("""
                    MATCH (concept:Concept {id: 'validation-concept-1'})
                    CREATE (related:Concept {
                        id: 'validation-concept-2',
                        name: 'Related Concept Validation',
                        type: 'validation'
                    })
                    CREATE (concept)-[:RELATED_TO]->(related)
                """)
                
                result = session.run("""
                    MATCH (doc:Document {id: 'validation-doc-1'})-[:CONTAINS]->(c1:Concept)-[:RELATED_TO]->(c2:Concept)
                    RETURN c2.name as relatedName
                """)
                
                record = result.single()
                if not record or record["relatedName"] != "Related Concept Validation":
                    return False, "Multi-hop query test failed"
                
                # Clean up test data
                session.run("""
                    MATCH (n) 
                    WHERE n.id STARTS WITH 'validation-'
                    DETACH DELETE n
                """)
                
                logger.info("Basic operations validation passed")
                return True, "All basic operations working correctly"
                
        except Exception as e:
            logger.error(f"Basic operations validation failed: {e}")
            # Clean up in case of error
            try:
                with self.driver.session() as session:
                    session.run("""
                        MATCH (n) 
                        WHERE n.id STARTS WITH 'validation-'
                        DETACH DELETE n
                    """)
            except:
                pass
            return False, str(e)
    
    def get_database_info(self) -> Dict[str, any]:
        """Get general database information."""
        try:
            with self.driver.session() as session:
                # Get node and relationship counts
                result = session.run("""
                    MATCH (n)
                    RETURN count(n) as nodeCount
                """)
                node_count = result.single()["nodeCount"]
                
                result = session.run("""
                    MATCH ()-[r]->()
                    RETURN count(r) as relCount
                """)
                rel_count = result.single()["relCount"]
                
                # Get label information
                result = session.run("CALL db.labels()")
                labels = [record["label"] for record in result]
                
                # Get relationship types
                result = session.run("CALL db.relationshipTypes()")
                rel_types = [record["relationshipType"] for record in result]
                
                return {
                    "node_count": node_count,
                    "relationship_count": rel_count,
                    "labels": labels,
                    "relationship_types": rel_types
                }
                
        except Exception as e:
            logger.error(f"Failed to get database info: {e}")
            return {}
    
    def run_full_validation(self) -> bool:
        """Run complete validation suite."""
        logger.info("Starting Neo4j validation suite")
        logger.info("=" * 50)
        
        # Connection test
        if not self.connect():
            logger.error("❌ Connection test failed")
            return False
        logger.info("✅ Connection test passed")
        
        validation_results = []
        
        # APOC plugin validation
        apoc_success, apoc_info = self.validate_apoc_plugin()
        if apoc_success:
            logger.info(f"✅ APOC plugin validation passed: {apoc_info}")
        else:
            logger.error(f"❌ APOC plugin validation failed: {apoc_info}")
        validation_results.append(apoc_success)
        
        # GDS plugin validation
        gds_success, gds_info = self.validate_gds_plugin()
        if gds_success:
            logger.info(f"✅ GDS plugin validation passed: {gds_info}")
        else:
            logger.error(f"❌ GDS plugin validation failed: {gds_info}")
        validation_results.append(gds_success)
        
        # Basic operations validation
        ops_success, ops_info = self.validate_basic_operations()
        if ops_success:
            logger.info(f"✅ Basic operations validation passed: {ops_info}")
        else:
            logger.error(f"❌ Basic operations validation failed: {ops_info}")
        validation_results.append(ops_success)
        
        # Database info
        db_info = self.get_database_info()
        if db_info:
            logger.info("📊 Database Information:")
            logger.info(f"   Nodes: {db_info.get('node_count', 0)}")
            logger.info(f"   Relationships: {db_info.get('relationship_count', 0)}")
            logger.info(f"   Labels: {', '.join(db_info.get('labels', []))}")
            logger.info(f"   Relationship Types: {', '.join(db_info.get('relationship_types', []))}")
        
        # Summary
        logger.info("=" * 50)
        all_passed = all(validation_results)
        if all_passed:
            logger.info("🎉 All validations passed! Neo4j is properly configured.")
        else:
            logger.error("❌ Some validations failed. Please check the configuration.")
        
        return all_passed


def main():
    """Main validation function."""
    validator = Neo4jValidator()
    
    try:
        success = validator.run_full_validation()
        sys.exit(0 if success else 1)
    finally:
        validator.close()


if __name__ == "__main__":
    main()