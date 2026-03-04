// =============================================================================
// MULTIMODAL LIBRARIAN - NEO4J SCHEMA INITIALIZATION
// =============================================================================
// This script creates the complete schema for the knowledge graph including
// constraints, indexes, and initial schema documentation.
//
// Node Types:
// - Document: Uploaded PDF documents and their metadata
// - Concept: Extracted concepts, entities, and topics
// - User: Application users and their profiles
// - Conversation: Chat conversations and their context
// - Chunk: Document chunks for vector search
// - Topic: Hierarchical topic organization
// - Metric: Performance and analytics metrics
//
// Relationship Types:
// - CONTAINS: Document contains concept/chunk
// - RELATED_TO: Concept relationships and associations
// - OWNS: User owns document
// - PARTICIPATED_IN: User participated in conversation
// - ABOUT: Conversation about document/concept
// - HAS_CHUNK: Document has chunk
// - MENTIONS: Chunk mentions concept
// - HAS_METRIC: Entity has associated metric
// - INCLUDES: Hierarchical inclusion relationships
// - APPLIES_TO: Application/usage relationships
// =============================================================================

// =============================================================================
// 1. CREATE UNIQUE CONSTRAINTS
// =============================================================================

// Document constraints
CREATE CONSTRAINT document_id_unique IF NOT EXISTS
FOR (d:Document) REQUIRE d.id IS UNIQUE;

CREATE CONSTRAINT document_title_not_null IF NOT EXISTS
FOR (d:Document) REQUIRE d.title IS NOT NULL;

// Concept constraints
CREATE CONSTRAINT concept_name_type_unique IF NOT EXISTS
FOR (c:Concept) REQUIRE (c.name, c.type) IS UNIQUE;

CREATE CONSTRAINT concept_name_not_null IF NOT EXISTS
FOR (c:Concept) REQUIRE c.name IS NOT NULL;

CREATE CONSTRAINT concept_type_not_null IF NOT EXISTS
FOR (c:Concept) REQUIRE c.type IS NOT NULL;

// User constraints
CREATE CONSTRAINT user_id_unique IF NOT EXISTS
FOR (u:User) REQUIRE u.id IS UNIQUE;

CREATE CONSTRAINT user_email_unique IF NOT EXISTS
FOR (u:User) REQUIRE u.email IS UNIQUE;

// Conversation constraints
CREATE CONSTRAINT conversation_id_unique IF NOT EXISTS
FOR (conv:Conversation) REQUIRE conv.id IS UNIQUE;

// Chunk constraints
CREATE CONSTRAINT chunk_id_unique IF NOT EXISTS
FOR (ch:Chunk) REQUIRE ch.id IS UNIQUE;

// Topic constraints
CREATE CONSTRAINT topic_name_unique IF NOT EXISTS
FOR (t:Topic) REQUIRE t.name IS UNIQUE;

// Metric constraints
CREATE CONSTRAINT metric_name_timestamp_unique IF NOT EXISTS
FOR (m:Metric) REQUIRE (m.name, m.timestamp) IS UNIQUE;

// =============================================================================
// 2. CREATE PERFORMANCE INDEXES
// =============================================================================

// Document indexes
CREATE INDEX document_created_at IF NOT EXISTS
FOR (d:Document) ON (d.created_at);

CREATE INDEX document_status IF NOT EXISTS
FOR (d:Document) ON (d.status);

CREATE INDEX document_filename IF NOT EXISTS
FOR (d:Document) ON (d.filename);

CREATE INDEX document_file_size IF NOT EXISTS
FOR (d:Document) ON (d.file_size);

// Concept indexes
CREATE INDEX concept_category IF NOT EXISTS
FOR (c:Concept) ON (c.category);

CREATE INDEX concept_confidence IF NOT EXISTS
FOR (c:Concept) ON (c.confidence);

CREATE INDEX concept_type_category IF NOT EXISTS
FOR (c:Concept) ON (c.type, c.category);

// User indexes
CREATE INDEX user_created_at IF NOT EXISTS
FOR (u:User) ON (u.created_at);

CREATE INDEX user_role IF NOT EXISTS
FOR (u:User) ON (u.role);

CREATE INDEX user_name IF NOT EXISTS
FOR (u:User) ON (u.name);

// Conversation indexes
CREATE INDEX conversation_created_at IF NOT EXISTS
FOR (conv:Conversation) ON (conv.created_at);

CREATE INDEX conversation_updated_at IF NOT EXISTS
FOR (conv:Conversation) ON (conv.updated_at);

CREATE INDEX conversation_message_count IF NOT EXISTS
FOR (conv:Conversation) ON (conv.message_count);

// Chunk indexes
CREATE INDEX chunk_position IF NOT EXISTS
FOR (ch:Chunk) ON (ch.position);

CREATE INDEX chunk_page_number IF NOT EXISTS
FOR (ch:Chunk) ON (ch.page_number);

CREATE INDEX chunk_embedding_id IF NOT EXISTS
FOR (ch:Chunk) ON (ch.embedding_id);

// Topic indexes
CREATE INDEX topic_level IF NOT EXISTS
FOR (t:Topic) ON (t.level);

// Metric indexes
CREATE INDEX metric_timestamp IF NOT EXISTS
FOR (m:Metric) ON (m.timestamp);

CREATE INDEX metric_value IF NOT EXISTS
FOR (m:Metric) ON (m.value);

// =============================================================================
// 3. CREATE FULL-TEXT SEARCH INDEXES
// =============================================================================

// Full-text search on concepts (name and description)
CALL db.index.fulltext.createNodeIndex(
  "concept_fulltext_search", 
  ["Concept"], 
  ["name", "description"],
  {
    analyzer: "standard-no-stop-words",
    eventually_consistent: true
  }
) YIELD name, labels, properties, options
RETURN "Created concept full-text index: " + name as status;

// Full-text search on documents (title and content)
CALL db.index.fulltext.createNodeIndex(
  "document_fulltext_search", 
  ["Document"], 
  ["title", "content", "summary"],
  {
    analyzer: "standard-no-stop-words",
    eventually_consistent: true
  }
) YIELD name, labels, properties, options
RETURN "Created document full-text index: " + name as status;

// Full-text search on chunks (content)
CALL db.index.fulltext.createNodeIndex(
  "chunk_fulltext_search", 
  ["Chunk"], 
  ["content"],
  {
    analyzer: "standard-no-stop-words",
    eventually_consistent: true
  }
) YIELD name, labels, properties, options
RETURN "Created chunk full-text index: " + name as status;

// Full-text search on conversations (title)
CALL db.index.fulltext.createNodeIndex(
  "conversation_fulltext_search", 
  ["Conversation"], 
  ["title"],
  {
    analyzer: "standard-no-stop-words",
    eventually_consistent: true
  }
) YIELD name, labels, properties, options
RETURN "Created conversation full-text index: " + name as status;

// =============================================================================
// 4. CREATE SCHEMA DOCUMENTATION NODES
// =============================================================================

// Create schema documentation root
CREATE (schema:SchemaDoc {
  name: "Multimodal Librarian Knowledge Graph Schema",
  version: "1.0.0",
  created: datetime(),
  description: "Complete schema definition for the multimodal librarian knowledge graph",
  last_updated: datetime()
});

// Document node type documentation
CREATE (docNodeType:NodeType {
  label: "Document",
  description: "Represents uploaded PDF documents with metadata and processing status",
  required_properties: ["id", "title", "filename"],
  optional_properties: ["content", "summary", "created_at", "updated_at", "file_size", "page_count", "status", "processing_metadata"],
  example_properties: {
    id: "doc_sample_001",
    title: "Introduction to Machine Learning",
    filename: "ml_intro.pdf",
    content: "Document content text...",
    summary: "Brief document summary...",
    created_at: "2024-01-01T00:00:00Z",
    file_size: 1024000,
    page_count: 25,
    status: "processed"
  }
});

// Concept node type documentation
CREATE (conceptNodeType:NodeType {
  label: "Concept",
  description: "Represents extracted concepts, entities, topics, and knowledge elements",
  required_properties: ["name", "type"],
  optional_properties: ["category", "confidence", "description", "aliases", "external_ids", "source_chunks"],
  example_properties: {
    name: "Machine Learning",
    type: "topic",
    category: "technology",
    confidence: 0.95,
    description: "A subset of artificial intelligence focusing on algorithms that learn from data"
  }
});

// User node type documentation
CREATE (userNodeType:NodeType {
  label: "User",
  description: "Represents application users with authentication and profile information",
  required_properties: ["id", "email"],
  optional_properties: ["name", "role", "created_at", "last_login", "preferences"],
  example_properties: {
    id: "user_dev_001",
    email: "dev@multimodal-librarian.local",
    name: "Developer User",
    role: "developer",
    created_at: "2024-01-01T00:00:00Z"
  }
});

// Conversation node type documentation
CREATE (conversationNodeType:NodeType {
  label: "Conversation",
  description: "Represents chat conversations between users and the AI system",
  required_properties: ["id"],
  optional_properties: ["title", "created_at", "updated_at", "message_count", "context", "metadata"],
  example_properties: {
    id: "conv_001",
    title: "Learning about ML basics",
    created_at: "2024-01-01T00:00:00Z",
    message_count: 5
  }
});

// Chunk node type documentation
CREATE (chunkNodeType:NodeType {
  label: "Chunk",
  description: "Represents document chunks for vector search and retrieval",
  required_properties: ["id", "content"],
  optional_properties: ["position", "page_number", "embedding_id", "metadata", "chunk_type"],
  example_properties: {
    id: "chunk_001",
    content: "Machine learning is a method of data analysis...",
    position: 1,
    page_number: 1,
    embedding_id: "emb_001"
  }
});

// Topic node type documentation
CREATE (topicNodeType:NodeType {
  label: "Topic",
  description: "Represents hierarchical topic organization for knowledge categorization",
  required_properties: ["name"],
  optional_properties: ["level", "description", "parent_topic", "metadata"],
  example_properties: {
    name: "Artificial Intelligence",
    level: 1,
    description: "The simulation of human intelligence in machines"
  }
});

// Metric node type documentation
CREATE (metricNodeType:NodeType {
  label: "Metric",
  description: "Represents performance metrics and analytics data",
  required_properties: ["name", "value", "timestamp"],
  optional_properties: ["unit", "metadata", "source", "tags"],
  example_properties: {
    name: "document_processing_time",
    value: 45.2,
    unit: "seconds",
    timestamp: "2024-01-01T00:00:00Z"
  }
});

// =============================================================================
// 5. CREATE RELATIONSHIP TYPE DOCUMENTATION
// =============================================================================

// CONTAINS relationship documentation
CREATE (containsRelType:RelationType {
  type: "CONTAINS",
  description: "Document contains concept or chunk",
  source_labels: ["Document"],
  target_labels: ["Concept", "Chunk"],
  properties: ["confidence", "frequency", "position", "extraction_method"],
  example_usage: "(d:Document)-[:CONTAINS {confidence: 0.95}]->(c:Concept)"
});

// RELATED_TO relationship documentation
CREATE (relatedRelType:RelationType {
  type: "RELATED_TO",
  description: "Concept is semantically related to another concept",
  source_labels: ["Concept"],
  target_labels: ["Concept"],
  properties: ["strength", "relationship_type", "source", "bidirectional"],
  example_usage: "(c1:Concept)-[:RELATED_TO {strength: 0.8}]->(c2:Concept)"
});

// OWNS relationship documentation
CREATE (ownsRelType:RelationType {
  type: "OWNS",
  description: "User owns or uploaded a document",
  source_labels: ["User"],
  target_labels: ["Document"],
  properties: ["uploaded_at", "permissions"],
  example_usage: "(u:User)-[:OWNS {uploaded_at: datetime()}]->(d:Document)"
});

// PARTICIPATED_IN relationship documentation
CREATE (participatedRelType:RelationType {
  type: "PARTICIPATED_IN",
  description: "User participated in a conversation",
  source_labels: ["User"],
  target_labels: ["Conversation"],
  properties: ["joined_at", "role", "message_count"],
  example_usage: "(u:User)-[:PARTICIPATED_IN {joined_at: datetime()}]->(conv:Conversation)"
});

// ABOUT relationship documentation
CREATE (aboutRelType:RelationType {
  type: "ABOUT",
  description: "Conversation is about a specific document or concept",
  source_labels: ["Conversation"],
  target_labels: ["Document", "Concept"],
  properties: ["relevance", "context"],
  example_usage: "(conv:Conversation)-[:ABOUT {relevance: 0.9}]->(d:Document)"
});

// HAS_CHUNK relationship documentation
CREATE (hasChunkRelType:RelationType {
  type: "HAS_CHUNK",
  description: "Document has a specific chunk",
  source_labels: ["Document"],
  target_labels: ["Chunk"],
  properties: ["chunk_order", "extraction_method"],
  example_usage: "(d:Document)-[:HAS_CHUNK {chunk_order: 1}]->(ch:Chunk)"
});

// MENTIONS relationship documentation
CREATE (mentionsRelType:RelationType {
  type: "MENTIONS",
  description: "Chunk mentions or references a concept",
  source_labels: ["Chunk"],
  target_labels: ["Concept"],
  properties: ["frequency", "confidence", "position"],
  example_usage: "(ch:Chunk)-[:MENTIONS {confidence: 0.85}]->(c:Concept)"
});

// HAS_METRIC relationship documentation
CREATE (hasMetricRelType:RelationType {
  type: "HAS_METRIC",
  description: "Entity has an associated performance metric",
  source_labels: ["Document", "Conversation", "User"],
  target_labels: ["Metric"],
  properties: ["metric_type", "collection_method"],
  example_usage: "(d:Document)-[:HAS_METRIC]->(m:Metric)"
});

// INCLUDES relationship documentation
CREATE (includesRelType:RelationType {
  type: "INCLUDES",
  description: "Hierarchical inclusion relationship (parent includes child)",
  source_labels: ["Topic", "Concept"],
  target_labels: ["Topic", "Concept"],
  properties: ["hierarchy_level", "strength"],
  example_usage: "(parent:Topic)-[:INCLUDES]->(child:Topic)"
});

// APPLIES_TO relationship documentation
CREATE (appliesToRelType:RelationType {
  type: "APPLIES_TO",
  description: "Concept or technique applies to another concept or domain",
  source_labels: ["Concept"],
  target_labels: ["Concept", "Topic"],
  properties: ["applicability_score", "context"],
  example_usage: "(technique:Concept)-[:APPLIES_TO]->(domain:Concept)"
});

// ACCESSED relationship documentation
CREATE (accessedRelType:RelationType {
  type: "ACCESSED",
  description: "User accessed or viewed a document",
  source_labels: ["User"],
  target_labels: ["Document"],
  properties: ["accessed_at", "access_type", "duration"],
  example_usage: "(u:User)-[:ACCESSED {accessed_at: datetime()}]->(d:Document)"
});

// =============================================================================
// 6. LINK SCHEMA DOCUMENTATION
// =============================================================================

// Link schema root to node types
MATCH (s:SchemaDoc), (nt:NodeType)
CREATE (s)-[:DEFINES]->(nt);

// Link schema root to relationship types
MATCH (s:SchemaDoc), (rt:RelationType)
CREATE (s)-[:DEFINES]->(rt);

// =============================================================================
// 7. CREATE SCHEMA VALIDATION FUNCTIONS (using APOC)
// =============================================================================

// Note: These would be custom procedures in a real implementation
// For now, we document the validation rules as properties

CREATE (validationRules:ValidationRules {
  name: "Schema Validation Rules",
  rules: [
    "All Document nodes must have id, title, and filename properties",
    "All Concept nodes must have name and type properties",
    "All User nodes must have id and email properties",
    "Concept confidence values must be between 0.0 and 1.0",
    "Document file_size must be positive integer",
    "Conversation message_count must be non-negative integer",
    "Metric values must be numeric",
    "All datetime properties should use ISO 8601 format"
  ],
  created: datetime()
});

// Link validation rules to schema
MATCH (s:SchemaDoc), (vr:ValidationRules)
CREATE (s)-[:HAS_VALIDATION_RULES]->(vr);

// =============================================================================
// 8. VERIFY SCHEMA CREATION
// =============================================================================

// Show all created constraints
CALL db.constraints() YIELD name, type, entityType, labelsOrTypes, properties
RETURN "Constraint: " + name as item, type, entityType, labelsOrTypes, properties
ORDER BY name

UNION ALL

// Show all created indexes
CALL db.indexes() YIELD name, type, entityType, labelsOrTypes, properties, state
WHERE state = "ONLINE"
RETURN "Index: " + name as item, type, entityType, labelsOrTypes, properties
ORDER BY name

UNION ALL

// Show schema documentation nodes
MATCH (s:SchemaDoc)-[:DEFINES]->(item)
RETURN "Schema Item: " + labels(item)[0] as item, 
       item.label as type, 
       "Documentation" as entityType,
       item.description as labelsOrTypes,
       "N/A" as properties
ORDER BY item;

// =============================================================================
// 9. COMPLETION STATUS
// =============================================================================

RETURN "Neo4j schema initialization completed successfully!" as status,
       datetime() as completed_at,
       "Schema includes constraints, indexes, full-text search, and documentation" as details;