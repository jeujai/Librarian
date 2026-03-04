// Neo4j Initialization Script - Create Constraints and Indexes
// This script creates the necessary constraints and indexes for the knowledge graph

// Create constraints for Document nodes
CREATE CONSTRAINT document_id_unique IF NOT EXISTS
FOR (d:Document) REQUIRE d.id IS UNIQUE;

CREATE CONSTRAINT document_title_exists IF NOT EXISTS
FOR (d:Document) REQUIRE d.title IS NOT NULL;

// Create constraints for Concept nodes
CREATE CONSTRAINT concept_name_unique IF NOT EXISTS
FOR (c:Concept) REQUIRE c.name IS UNIQUE;

CREATE CONSTRAINT concept_type_exists IF NOT EXISTS
FOR (c:Concept) REQUIRE c.type IS NOT NULL;

// Create constraints for User nodes
CREATE CONSTRAINT user_id_unique IF NOT EXISTS
FOR (u:User) REQUIRE u.id IS UNIQUE;

// Create constraints for Conversation nodes
CREATE CONSTRAINT conversation_id_unique IF NOT EXISTS
FOR (conv:Conversation) REQUIRE conv.id IS UNIQUE;

// Create constraints for Chunk nodes
CREATE CONSTRAINT chunk_id_unique IF NOT EXISTS
FOR (ch:Chunk) REQUIRE ch.id IS UNIQUE;

// Create indexes for better query performance
CREATE INDEX document_created_at IF NOT EXISTS
FOR (d:Document) ON (d.created_at);

CREATE INDEX concept_category IF NOT EXISTS
FOR (c:Concept) ON (c.category);

CREATE INDEX concept_confidence IF NOT EXISTS
FOR (c:Concept) ON (c.confidence);

CREATE INDEX user_created_at IF NOT EXISTS
FOR (u:User) ON (u.created_at);

CREATE INDEX conversation_created_at IF NOT EXISTS
FOR (conv:Conversation) ON (conv.created_at);

CREATE INDEX chunk_position IF NOT EXISTS
FOR (ch:Chunk) ON (ch.position);

// Create full-text search indexes using APOC
CALL apoc.schema.assert(
  {Document: ['title', 'content']},
  {Document: ['id'], Concept: ['name'], User: ['id'], Conversation: ['id'], Chunk: ['id']}
) YIELD label, key, unique, action
RETURN label, key, unique, action;