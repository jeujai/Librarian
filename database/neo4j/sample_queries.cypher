// =============================================================================
// MULTIMODAL LIBRARIAN - NEO4J SAMPLE QUERIES
// =============================================================================
// This file contains useful Cypher queries for working with the knowledge graph

// =============================================================================
// DATABASE EXPLORATION
// =============================================================================

// Show database schema visualization
CALL db.schema.visualization();

// List all node labels
CALL db.labels();

// List all relationship types
CALL db.relationshipTypes();

// Count nodes by label
MATCH (n)
RETURN labels(n) as label, count(n) as count
ORDER BY count DESC;

// Count relationships by type
MATCH ()-[r]->()
RETURN type(r) as relationship_type, count(r) as count
ORDER BY count DESC;

// =============================================================================
// KNOWLEDGE GRAPH QUERIES
// =============================================================================

// Find all documents and their concepts
MATCH (d:Document)-[:CONTAINS]->(c:Concept)
RETURN d.title as document, collect(c.name) as concepts
ORDER BY d.title;

// Find concepts shared between documents
MATCH (d1:Document)-[:CONTAINS]->(c:Concept)<-[:CONTAINS]-(d2:Document)
WHERE d1 <> d2
RETURN c.name as shared_concept, 
       collect(DISTINCT d1.title) as documents
ORDER BY size(documents) DESC;

// Find the most connected concepts
MATCH (c:Concept)
RETURN c.name as concept, 
       size((c)-[:RELATED_TO]-()) as connection_count
ORDER BY connection_count DESC
LIMIT 10;

// Multi-hop concept relationships
MATCH path = (c1:Concept)-[:RELATED_TO*1..3]-(c2:Concept)
WHERE c1.name = "Machine Learning"
RETURN c2.name as related_concept, 
       length(path) as distance,
       [node in nodes(path) | node.name] as path_concepts
ORDER BY distance, c2.name;

// Find concept clusters (concepts that are highly interconnected)
MATCH (c1:Concept)-[:RELATED_TO]-(c2:Concept)-[:RELATED_TO]-(c3:Concept)
WHERE c1 <> c3 AND (c1)-[:RELATED_TO]-(c3)
RETURN c1.name, c2.name, c3.name as concept_triangle
LIMIT 20;

// =============================================================================
// DOCUMENT ANALYSIS
// =============================================================================

// Find documents with the most concepts
MATCH (d:Document)-[:CONTAINS]->(c:Concept)
RETURN d.title as document, 
       count(c) as concept_count,
       collect(c.name)[0..5] as sample_concepts
ORDER BY concept_count DESC;

// Find documents that are conceptually similar
MATCH (d1:Document)-[:CONTAINS]->(c:Concept)<-[:CONTAINS]-(d2:Document)
WHERE d1 <> d2
WITH d1, d2, count(c) as shared_concepts
WHERE shared_concepts >= 3
RETURN d1.title as document1, 
       d2.title as document2, 
       shared_concepts
ORDER BY shared_concepts DESC;

// Find orphaned documents (no concepts)
MATCH (d:Document)
WHERE NOT (d)-[:CONTAINS]->(:Concept)
RETURN d.title as orphaned_document;

// =============================================================================
// CONCEPT ANALYSIS
// =============================================================================

// Find orphaned concepts (not connected to documents)
MATCH (c:Concept)
WHERE NOT (:Document)-[:CONTAINS]->(c)
RETURN c.name as orphaned_concept;

// Find concept hierarchies (if using PARENT_OF relationships)
MATCH path = (parent:Concept)-[:PARENT_OF*]->(child:Concept)
RETURN parent.name as root_concept,
       child.name as leaf_concept,
       length(path) as hierarchy_depth
ORDER BY hierarchy_depth DESC, parent.name;

// Find concepts by type/category
MATCH (c:Concept)
WHERE c.type IS NOT NULL
RETURN c.type as concept_type, 
       collect(c.name) as concepts
ORDER BY concept_type;

// =============================================================================
// SEARCH AND DISCOVERY
// =============================================================================

// Full-text search for concepts (requires full-text index)
CALL db.index.fulltext.queryNodes("concept_search", "machine learning") 
YIELD node, score
RETURN node.name as concept, score
ORDER BY score DESC;

// Find concepts related to a search term
MATCH (c:Concept)
WHERE toLower(c.name) CONTAINS toLower("neural")
   OR toLower(c.description) CONTAINS toLower("neural")
RETURN c.name as matching_concept, c.description
ORDER BY c.name;

// Find documents containing specific keywords
MATCH (d:Document)-[:CONTAINS]->(c:Concept)
WHERE toLower(c.name) CONTAINS toLower("artificial intelligence")
RETURN DISTINCT d.title as relevant_document
ORDER BY d.title;

// =============================================================================
// GRAPH ALGORITHMS (requires GDS plugin)
// =============================================================================

// Create a graph projection for analysis
CALL gds.graph.project(
  'knowledge-graph',
  'Concept',
  'RELATED_TO'
);

// Run PageRank to find important concepts
CALL gds.pageRank.stream('knowledge-graph')
YIELD nodeId, score
RETURN gds.util.asNode(nodeId).name AS concept, score
ORDER BY score DESC
LIMIT 10;

// Community detection to find concept clusters
CALL gds.louvain.stream('knowledge-graph')
YIELD nodeId, communityId
WITH gds.util.asNode(nodeId) AS concept, communityId
RETURN communityId, collect(concept.name) as concepts
ORDER BY communityId;

// Find shortest paths between concepts
MATCH (start:Concept {name: "Machine Learning"}), 
      (end:Concept {name: "Natural Language Processing"})
CALL gds.shortestPath.dijkstra.stream('knowledge-graph', {
  sourceNode: start,
  targetNode: end
})
YIELD path
RETURN [node in nodes(path) | node.name] as concept_path;

// Centrality analysis - find bridge concepts
CALL gds.betweenness.stream('knowledge-graph')
YIELD nodeId, score
RETURN gds.util.asNode(nodeId).name AS concept, score
ORDER BY score DESC
LIMIT 10;

// =============================================================================
// DATA MAINTENANCE
// =============================================================================

// Remove duplicate concepts (same name)
MATCH (c1:Concept), (c2:Concept)
WHERE c1.name = c2.name AND id(c1) < id(c2)
WITH c1, c2
MATCH (c2)-[r]-()
CREATE (c1)-[r2:RELATED_TO]-(other)
SET r2 = properties(r)
DELETE r, c2;

// Merge similar concepts (fuzzy matching)
MATCH (c1:Concept), (c2:Concept)
WHERE c1 <> c2 
  AND apoc.text.levenshteinSimilarity(c1.name, c2.name) > 0.8
RETURN c1.name, c2.name, 
       apoc.text.levenshteinSimilarity(c1.name, c2.name) as similarity
ORDER BY similarity DESC;

// Clean up orphaned relationships
MATCH ()-[r:RELATED_TO]-()
WHERE startNode(r) IS NULL OR endNode(r) IS NULL
DELETE r;

// =============================================================================
// PERFORMANCE OPTIMIZATION
// =============================================================================

// Create indexes for better query performance
CREATE INDEX concept_name_index FOR (c:Concept) ON (c.name);
CREATE INDEX document_title_index FOR (d:Document) ON (d.title);
CREATE INDEX concept_type_index FOR (c:Concept) ON (c.type);

// Create full-text search index
CALL db.index.fulltext.createNodeIndex(
  "concept_search", 
  ["Concept"], 
  ["name", "description"]
);

// Show existing indexes
SHOW INDEXES;

// Analyze query performance
PROFILE 
MATCH (d:Document)-[:CONTAINS]->(c:Concept)
WHERE c.name = "Machine Learning"
RETURN d.title;

// =============================================================================
// STATISTICS AND MONITORING
// =============================================================================

// Database size and statistics
CALL apoc.meta.stats() YIELD labels, relTypesCount, nodeCount, relCount
RETURN labels, relTypesCount, nodeCount, relCount;

// Show constraint violations
CALL db.constraints();

// Monitor active queries
CALL dbms.listQueries()
YIELD query, elapsedTimeMillis, allocatedBytes
WHERE elapsedTimeMillis > 1000
RETURN query, elapsedTimeMillis, allocatedBytes
ORDER BY elapsedTimeMillis DESC;

// =============================================================================
// SAMPLE DATA CREATION (for testing)
// =============================================================================

// Create sample documents
CREATE (d1:Document {id: "doc1", title: "Introduction to Machine Learning", created: datetime()})
CREATE (d2:Document {id: "doc2", title: "Deep Learning Fundamentals", created: datetime()})
CREATE (d3:Document {id: "doc3", title: "Natural Language Processing", created: datetime()});

// Create sample concepts
CREATE (c1:Concept {name: "Machine Learning", type: "field"})
CREATE (c2:Concept {name: "Neural Networks", type: "technique"})
CREATE (c3:Concept {name: "Deep Learning", type: "subfield"})
CREATE (c4:Concept {name: "Natural Language Processing", type: "application"})
CREATE (c5:Concept {name: "Supervised Learning", type: "approach"});

// Create relationships between documents and concepts
MATCH (d1:Document {id: "doc1"}), (c1:Concept {name: "Machine Learning"})
CREATE (d1)-[:CONTAINS]->(c1);

MATCH (d1:Document {id: "doc1"}), (c5:Concept {name: "Supervised Learning"})
CREATE (d1)-[:CONTAINS]->(c5);

MATCH (d2:Document {id: "doc2"}), (c2:Concept {name: "Neural Networks"})
CREATE (d2)-[:CONTAINS]->(c2);

MATCH (d2:Document {id: "doc2"}), (c3:Concept {name: "Deep Learning"})
CREATE (d2)-[:CONTAINS]->(c3);

// Create concept relationships
MATCH (c1:Concept {name: "Machine Learning"}), (c3:Concept {name: "Deep Learning"})
CREATE (c1)-[:RELATED_TO {strength: 0.8}]->(c3);

MATCH (c3:Concept {name: "Deep Learning"}), (c2:Concept {name: "Neural Networks"})
CREATE (c3)-[:RELATED_TO {strength: 0.9}]->(c2);

MATCH (c1:Concept {name: "Machine Learning"}), (c4:Concept {name: "Natural Language Processing"})
CREATE (c1)-[:RELATED_TO {strength: 0.7}]->(c4);

// =============================================================================
// CLEANUP QUERIES
// =============================================================================

// Remove all sample data
MATCH (n)
WHERE n.id IN ["doc1", "doc2", "doc3"] 
   OR n.name IN ["Machine Learning", "Neural Networks", "Deep Learning", 
                 "Natural Language Processing", "Supervised Learning"]
DETACH DELETE n;

// Clear entire database (use with caution!)
// MATCH (n) DETACH DELETE n;