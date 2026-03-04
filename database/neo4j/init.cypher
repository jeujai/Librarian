// =============================================================================
// MULTIMODAL LIBRARIAN - NEO4J INITIALIZATION SCRIPT
// =============================================================================
// This script sets up the initial schema and indexes for the knowledge graph
// 
// NOTE: This script is now deprecated in favor of the modular initialization
// scripts in the init/ directory. Use those scripts for new installations.
//
// The init/ directory contains:
// - 00_schema_initialization.cypher: Complete schema setup
// - 01_verify_plugins.cypher: Plugin verification
// - 02_create_constraints.cypher: Additional constraints
// - 03_sample_data.cypher: Sample data for development
// =============================================================================

// =============================================================================
// CREATE INDEXES FOR PERFORMANCE (Legacy - use 00_schema_initialization.cypher)
// =============================================================================

// Index on Concept name for fast lookups
CREATE INDEX concept_name_index IF NOT EXISTS FOR (c:Concept) ON (c.name);

// Index on Concept type for filtering
CREATE INDEX concept_type_index IF NOT EXISTS FOR (c:Concept) ON (c.type);

// Index on Document ID for fast lookups
CREATE INDEX document_id_index IF NOT EXISTS FOR (d:Document) ON (d.id);

// Index on Document title for searching
CREATE INDEX document_title_index IF NOT EXISTS FOR (d:Document) ON (d.title);

// Composite index for document queries
CREATE INDEX document_composite_index IF NOT EXISTS FOR (d:Document) ON (d.id, d.title);

// =============================================================================
// CREATE FULL-TEXT SEARCH INDEXES
// =============================================================================

// Full-text search on concepts
CALL db.index.fulltext.createNodeIndex(
  "concept_search", 
  ["Concept"], 
  ["name", "description"],
  {
    analyzer: "standard-no-stop-words",
    eventually_consistent: true
  }
) YIELD name, labels, properties, options
RETURN name, labels, properties, options;

// Full-text search on documents
CALL db.index.fulltext.createNodeIndex(
  "document_search", 
  ["Document"], 
  ["title", "content", "summary"],
  {
    analyzer: "standard-no-stop-words",
    eventually_consistent: true
  }
) YIELD name, labels, properties, options
RETURN name, labels, properties, options;

// =============================================================================
// CREATE CONSTRAINTS
// =============================================================================

// Unique constraint on Document ID
CREATE CONSTRAINT document_id_unique IF NOT EXISTS FOR (d:Document) REQUIRE d.id IS UNIQUE;

// Unique constraint on Concept name (within type)
CREATE CONSTRAINT concept_name_type_unique IF NOT EXISTS FOR (c:Concept) REQUIRE (c.name, c.type) IS UNIQUE;

// =============================================================================
// VERIFY SETUP
// =============================================================================

// Show all indexes
CALL db.indexes() YIELD name, type, entityType, labelsOrTypes, properties, state
RETURN name, type, entityType, labelsOrTypes, properties, state
ORDER BY name;

// Show all constraints
CALL db.constraints() YIELD name, type, entityType, labelsOrTypes, properties
RETURN name, type, entityType, labelsOrTypes, properties
ORDER BY name;

// =============================================================================
// SAMPLE SCHEMA DOCUMENTATION
// =============================================================================

// Create schema documentation nodes (optional)
CREATE (schema:SchemaDoc {
  name: "Multimodal Librarian Knowledge Graph",
  version: "1.0",
  created: datetime(),
  description: "Graph schema for document knowledge representation"
});

CREATE (docNode:NodeType {
  label: "Document",
  description: "Represents uploaded documents",
  properties: ["id", "title", "filename", "content", "summary", "created", "updated"]
});

CREATE (conceptNode:NodeType {
  label: "Concept",
  description: "Represents extracted concepts and entities",
  properties: ["name", "type", "description", "confidence", "created"]
});

CREATE (containsRel:RelationType {
  type: "CONTAINS",
  description: "Document contains concept",
  properties: ["confidence", "frequency", "position"]
});

CREATE (relatedRel:RelationType {
  type: "RELATED_TO",
  description: "Concept is related to another concept",
  properties: ["strength", "type", "source"]
});

// Link schema documentation
MATCH (s:SchemaDoc), (d:NodeType {label: "Document"}), (c:NodeType {label: "Concept"})
CREATE (s)-[:DEFINES]->(d), (s)-[:DEFINES]->(c);

MATCH (s:SchemaDoc), (contains:RelationType {type: "CONTAINS"}), (related:RelationType {type: "RELATED_TO"})
CREATE (s)-[:DEFINES]->(contains), (s)-[:DEFINES]->(related);

// =============================================================================
// COMPLETION MESSAGE
// =============================================================================

RETURN "Neo4j initialization completed successfully!" as status,
       datetime() as completed_at;