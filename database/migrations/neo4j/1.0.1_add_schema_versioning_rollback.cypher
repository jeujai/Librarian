// Rollback Migration: Remove schema versioning from Neo4j
// Version: 1.0.1
// Description: Remove schema version tracking and migration history

// Remove rollback information
MATCH (rb:RollbackInfo {migration_id: "neo4j_1.0.1_add_schema_versioning"})
DETACH DELETE rb;

// Remove migration system
MATCH (ms:MigrationSystem)
DETACH DELETE ms;

// Remove version and validation queries
MATCH (vq:VersionQuery)
DETACH DELETE vq;

MATCH (viq:ValidationQuery)
DETACH DELETE viq;

// Remove migration relationships
MATCH ()-[r:FOLLOWED_BY]->()
DELETE r;

MATCH ()-[r:INCLUDES_MIGRATION]->()
DELETE r;

MATCH ()-[r:HAS_ROLLBACK]->()
DELETE r;

MATCH ()-[r:HAS_QUERY]->()
DELETE r;

MATCH ()-[r:MANAGED_BY]->()
DELETE r;

// Remove migration nodes
MATCH (m:Migration)
DELETE m;

// Remove schema version nodes
MATCH (sv:SchemaVersion)
DELETE sv;

// Drop migration-related constraints
DROP CONSTRAINT migration_id_unique IF EXISTS;
DROP CONSTRAINT schema_version_unique IF EXISTS;

// Drop migration-related indexes
DROP INDEX migration_version IF EXISTS;
DROP INDEX migration_applied_at IF EXISTS;
DROP INDEX schema_version_applied_at IF EXISTS;

// Revert schema documentation changes
MATCH (s:SchemaDoc)
REMOVE s.versioning_enabled, s.migration_tracking
SET s.version = "1.0.0",
    s.last_updated = datetime();

// Return confirmation of successful rollback
RETURN "Neo4j schema versioning rollback 1.0.1 completed successfully" as status,
       datetime() as completed_at,
       "Removed all schema versioning components" as details;