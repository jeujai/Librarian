// Migration: Add schema versioning to Neo4j
// Version: 1.0.1
// Description: Add schema version tracking and migration history

// Create SchemaVersion nodes for tracking versions
CREATE (sv:SchemaVersion {
  version: "1.0.1",
  description: "Add schema versioning and migration tracking",
  migration_id: "neo4j_1.0.1_add_schema_versioning",
  applied_at: datetime(),
  applied_by: "schema_migration_system",
  status: "completed"
});

// Create Migration nodes for tracking individual migrations
CREATE (m:Migration {
  id: "neo4j_1.0.1_add_schema_versioning",
  version: "1.0.1",
  description: "Add schema versioning and migration tracking",
  type: "schema_enhancement",
  applied_at: datetime(),
  status: "completed",
  checksum: "schema_versioning_1_0_1"
});

// Create initial migration record for the base schema (1.0.0)
CREATE (m0:Migration {
  id: "neo4j_1.0.0_initial_schema",
  version: "1.0.0",
  description: "Initial schema setup from initialization scripts",
  type: "initial_setup",
  applied_at: datetime() - duration({days: 1}),
  status: "completed",
  checksum: "initial_schema_1_0_0"
});

// Link migrations to schema versions
MATCH (sv:SchemaVersion {version: "1.0.1"})
MATCH (m:Migration {version: "1.0.1"})
CREATE (sv)-[:INCLUDES_MIGRATION]->(m);

// Create schema validation constraints for migration tracking
CREATE CONSTRAINT migration_id_unique IF NOT EXISTS
FOR (m:Migration) REQUIRE m.id IS UNIQUE;

CREATE CONSTRAINT schema_version_unique IF NOT EXISTS
FOR (sv:SchemaVersion) REQUIRE sv.version IS UNIQUE;

// Create indexes for performance
CREATE INDEX migration_version IF NOT EXISTS
FOR (m:Migration) ON (m.version);

CREATE INDEX migration_applied_at IF NOT EXISTS
FOR (m:Migration) ON (m.applied_at);

CREATE INDEX schema_version_applied_at IF NOT EXISTS
FOR (sv:SchemaVersion) ON (sv.applied_at);

// Update the main schema documentation to include versioning info
MATCH (s:SchemaDoc)
SET s.version = "1.0.1",
    s.last_updated = datetime(),
    s.versioning_enabled = true,
    s.migration_tracking = true;

// Create a function-like query for getting current schema version
// (Neo4j doesn't have stored procedures in Community Edition, so we document the query)
CREATE (vq:VersionQuery {
  name: "get_current_schema_version",
  description: "Query to get the current schema version",
  cypher_query: "MATCH (sv:SchemaVersion) RETURN sv.version, sv.applied_at ORDER BY sv.applied_at DESC LIMIT 1",
  usage: "Use this query to check the current schema version"
});

// Create a validation query for schema integrity
CREATE (viq:ValidationQuery {
  name: "validate_schema_integrity",
  description: "Query to validate schema integrity and completeness",
  cypher_query: "CALL db.constraints() YIELD name, type RETURN count(*) as constraint_count UNION ALL CALL db.indexes() YIELD name, type WHERE state = 'ONLINE' RETURN count(*) as index_count",
  usage: "Use this query to validate that all required constraints and indexes exist"
});

// Link queries to schema documentation
MATCH (s:SchemaDoc)
MATCH (vq:VersionQuery)
MATCH (viq:ValidationQuery)
CREATE (s)-[:HAS_QUERY]->(vq)
CREATE (s)-[:HAS_QUERY]->(viq);

// Create migration history relationship
MATCH (m0:Migration {version: "1.0.0"})
MATCH (m1:Migration {version: "1.0.1"})
CREATE (m0)-[:FOLLOWED_BY]->(m1);

// Add metadata about the migration system
CREATE (ms:MigrationSystem {
  name: "Neo4j Schema Migration System",
  version: "1.0.1",
  description: "Tracks schema versions and migrations for the Multimodal Librarian knowledge graph",
  created: datetime(),
  features: [
    "Version tracking",
    "Migration history",
    "Schema validation",
    "Rollback support"
  ]
});

// Link migration system to schema documentation
MATCH (s:SchemaDoc)
MATCH (ms:MigrationSystem)
CREATE (s)-[:MANAGED_BY]->(ms);

// Create rollback information
CREATE (rb:RollbackInfo {
  migration_id: "neo4j_1.0.1_add_schema_versioning",
  rollback_available: true,
  rollback_script: "1.0.1_add_schema_versioning_rollback.cypher",
  rollback_description: "Removes schema versioning nodes and relationships",
  created: datetime()
});

// Link rollback info to migration
MATCH (m:Migration {id: "neo4j_1.0.1_add_schema_versioning"})
MATCH (rb:RollbackInfo {migration_id: "neo4j_1.0.1_add_schema_versioning"})
CREATE (m)-[:HAS_ROLLBACK]->(rb);

// Return confirmation of successful migration
RETURN "Neo4j schema versioning migration 1.0.1 completed successfully" as status,
       datetime() as completed_at,
       "Added schema version tracking, migration history, and validation queries" as details;