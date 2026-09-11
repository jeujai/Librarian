// Neo4j Database Initialization Script
// This script sets up the required indexes and constraints for the Knowledge Graph
// Run this after Neo4j database is created or recreated

// =============================================================================
// Full-Text Indexes for Query Decomposition (KG-Guided Retrieval)
// =============================================================================

// Full-text index on Concept names for fast query decomposition
// Used by QueryDecomposer to match query words against concept names
// Requirement: KG-Guided Retrieval - Query Decomposition (4.1, 4.2)
CREATE FULLTEXT INDEX concept_name_fulltext IF NOT EXISTS
FOR (c:Concept) ON EACH [c.name];

// =============================================================================
// Standard Indexes for Performance
// =============================================================================

// Index on Concept.concept_id for fast lookups
CREATE INDEX concept_id_index IF NOT EXISTS FOR (c:Concept) ON (c.concept_id);

// Index on Concept.source_document for document-based queries
CREATE INDEX concept_source_document_index IF NOT EXISTS FOR (c:Concept) ON (c.source_document);

// Index on Concept.type for filtering by concept type
CREATE INDEX concept_type_index IF NOT EXISTS FOR (c:Concept) ON (c.type);

// Case-insensitive lookup index (avoids toLower(c.name) full scans)
CREATE INDEX concept_name_lower IF NOT EXISTS FOR (c:Concept) ON (c.name_lower);

// Emergent-concepts lifecycle/provenance/privacy range indexes
CREATE INDEX concept_bridge_status IF NOT EXISTS FOR (c:Concept) ON (c.bridge_status);
CREATE INDEX concept_provenance IF NOT EXISTS FOR (c:Concept) ON (c.provenance);
CREATE INDEX concept_scope IF NOT EXISTS FOR (c:Concept) ON (c.scope);
CREATE INDEX concept_owner_id IF NOT EXISTS FOR (c:Concept) ON (c.owner_id);

// Index on Document.document_id for fast document lookups
CREATE INDEX document_id_index IF NOT EXISTS FOR (d:Document) ON (d.document_id);

// =============================================================================
// Constraints for Data Integrity
// =============================================================================

// Unique constraint on Concept.concept_id
CREATE CONSTRAINT concept_id_unique IF NOT EXISTS FOR (c:Concept) REQUIRE c.concept_id IS UNIQUE;

// =============================================================================
// Emergent Concepts — composite identity + reified anchor (Phase 1+)
// =============================================================================
//
// The (name_lower, scope) composite uniqueness constraint is created by
// scripts/migrate_emergent_concepts.py (NOT here), because it can only be
// applied after the dedup migration collapses duplicated name_lower values.
//
//   CREATE CONSTRAINT concept_scope_unique IF NOT EXISTS
//   FOR (c:Concept) REQUIRE (c.name_lower, c.scope) IS UNIQUE
//
// The :Anchor node type reifies what a SAME_AS points at (a subgraph equivalent
// or one sense of a polysemous concept). It is materialized in Phase 2+ and is
// not indexed here. Properties: kind ("composite" | "reading"),
// relationship_type, concept_type, sense_terms, scope, owner_id.
// Edge labels: (:Concept)-[:HAS_READING]->(:Anchor)-[:SAME_AS]->(ontology),
//              (:Anchor {kind:"composite"})-[:HAS_PART]->(ontology).

// =============================================================================
// Verification Queries (run these to verify indexes are created)
// =============================================================================

// List all indexes: SHOW INDEXES
// List all constraints: SHOW CONSTRAINTS
// Test full-text search: CALL db.index.fulltext.queryNodes('concept_name_fulltext', 'chelsea') YIELD node, score RETURN node.name, score LIMIT 5
