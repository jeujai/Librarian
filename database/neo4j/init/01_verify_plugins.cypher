// Neo4j Plugin Verification Script
// This script verifies that required plugins are loaded and functional

// Check APOC plugin availability
CALL apoc.help("apoc") YIELD name, type, signature, description
WHERE name STARTS WITH "apoc.version"
RETURN "APOC Plugin Status: " + CASE WHEN count(*) > 0 THEN "LOADED" ELSE "NOT LOADED" END as status;

// Check GDS plugin availability  
CALL gds.version() YIELD gdsVersion
RETURN "GDS Plugin Status: LOADED, Version: " + gdsVersion as status;

// Create sample data for testing
CREATE (doc1:Document {id: 'sample-doc-1', title: 'Sample Document', type: 'pdf'})
CREATE (concept1:Concept {id: 'ml-concept-1', name: 'Machine Learning', type: 'topic'})
CREATE (concept2:Concept {id: 'ai-concept-1', name: 'Artificial Intelligence', type: 'field'})
CREATE (doc1)-[:CONTAINS]->(concept1)
CREATE (concept1)-[:RELATED_TO]->(concept2);

// Test APOC functionality
CALL apoc.meta.stats() YIELD labels, relTypesCount
RETURN "APOC Meta Stats - Labels: " + toString(size(labels)) + ", Relationships: " + toString(relTypesCount) as apoc_test;

// Test GDS functionality with a simple algorithm
CALL gds.graph.project(
  'test-graph',
  ['Document', 'Concept'],
  ['CONTAINS', 'RELATED_TO']
);

CALL gds.pageRank.stream('test-graph')
YIELD nodeId, score
WITH gds.util.asNode(nodeId) AS node, score
RETURN "GDS PageRank Test - Node: " + coalesce(node.title, node.name) + ", Score: " + toString(score) as gds_test
LIMIT 3;

// Clean up test graph
CALL gds.graph.drop('test-graph');

RETURN "Neo4j Plugin Configuration Complete" as final_status;