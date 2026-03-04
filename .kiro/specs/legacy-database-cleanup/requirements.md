# Requirements Document

## Introduction

The Multimodal Librarian system has been successfully migrated to AWS-native databases (Neptune for graph operations, OpenSearch for vector search). However, legacy Neo4j and Milvus code, dependencies, and configuration remain in the codebase. This creates a risk of accidental regressions where development configuration (localhost connections) could be deployed to production, as evidenced by a recent incident where a task definition was deployed without AWS-native configuration.

This specification defines the requirements for completely removing all Neo4j and Milvus dependencies, client code, and configuration from the codebase while preserving AWS-native functionality and maintaining an archive for reference.

## Glossary

- **System**: The Multimodal Librarian application codebase
- **Legacy_Database**: Neo4j or Milvus database systems that have been replaced by AWS-native alternatives
- **AWS_Native_Database**: Neptune (graph) or OpenSearch (vector search) database systems
- **Container_Image**: Docker image built from the application codebase
- **Health_Check**: System validation that verifies service availability and correctness
- **Archive**: Storage location for removed code with documentation explaining removal rationale

## Requirements

### Requirement 1: Remove Legacy Dependencies

**User Story:** As a developer, I want legacy database dependencies removed from requirements.txt, so that the container image does not include unnecessary packages that could cause confusion or regressions.

#### Acceptance Criteria

1. WHEN the requirements.txt file is processed, THE System SHALL NOT include the `neo4j` package
2. WHEN the requirements.txt file is processed, THE System SHALL NOT include the `pymilvus` package
3. WHEN the container image is built, THE System SHALL complete successfully without legacy database dependencies

### Requirement 2: Remove Legacy Client Files

**User Story:** As a developer, I want legacy database client files removed from the codebase, so that there is no code that could accidentally connect to localhost services.

#### Acceptance Criteria

1. THE System SHALL NOT contain the file `src/multimodal_librarian/clients/neo4j_client.py`
2. THE System SHALL NOT contain the file `src/multimodal_librarian/config/neo4j_config.py`
3. THE System SHALL NOT contain the file `src/multimodal_librarian/aws/milvus_config_basic.py`
4. WHEN searching the codebase for legacy client files, THE System SHALL return zero results

### Requirement 3: Remove Legacy Import References

**User Story:** As a developer, I want all import statements referencing legacy databases removed, so that the code does not attempt to use removed modules.

#### Acceptance Criteria

1. WHEN parsing `src/multimodal_librarian/services/knowledge_graph_service.py`, THE System SHALL NOT contain imports from `neo4j_client`
2. WHEN parsing `src/multimodal_librarian/monitoring/health_checker.py`, THE System SHALL NOT contain imports from `neo4j_client` or `neo4j_config`
3. WHEN parsing `src/multimodal_librarian/monitoring/component_health_checks.py`, THE System SHALL NOT contain imports from `neo4j_client` or `pymilvus`
4. WHEN parsing `src/multimodal_librarian/aws/secrets_manager_basic.py`, THE System SHALL NOT contain Neo4j configuration references
5. WHEN searching the entire codebase for `neo4j` imports, THE System SHALL return zero results
6. WHEN searching the entire codebase for `pymilvus` imports, THE System SHALL return zero results

### Requirement 4: Archive Removed Files

**User Story:** As a developer, I want removed files archived with documentation, so that I can reference the legacy implementation if needed for historical context.

#### Acceptance Criteria

1. WHEN legacy files are removed, THE System SHALL copy them to `archive/legacy-databases/` before deletion
2. WHEN files are archived, THE System SHALL create a README.md in the archive directory explaining what was removed and why
3. THE Archive SHALL include the original file paths in the documentation
4. THE Archive SHALL include the date of removal in the documentation
5. THE Archive SHALL include a reference to the AWS-native migration that replaced the legacy code

### Requirement 5: Preserve AWS-Native Functionality

**User Story:** As a developer, I want AWS-native database clients and configuration preserved, so that the application continues to function correctly with Neptune and OpenSearch.

#### Acceptance Criteria

1. WHEN the cleanup is complete, THE System SHALL retain `src/multimodal_librarian/clients/neptune_client.py`
2. WHEN the cleanup is complete, THE System SHALL retain `src/multimodal_librarian/clients/opensearch_client.py`
3. WHEN the cleanup is complete, THE System SHALL retain `src/multimodal_librarian/config/aws_native_config.py`
4. WHEN the cleanup is complete, THE System SHALL retain `src/multimodal_librarian/clients/database_factory.py`
5. THE Database_Factory SHALL only support AWS-native database backends after cleanup

### Requirement 6: Update Database Factory

**User Story:** As a developer, I want the database factory to only support AWS-native backends, so that there is no code path that could instantiate legacy database clients.

#### Acceptance Criteria

1. WHEN the database factory is invoked with any configuration, THE System SHALL only return Neptune or OpenSearch clients
2. WHEN searching the database factory code for Neo4j references, THE System SHALL return zero results
3. WHEN searching the database factory code for Milvus references, THE System SHALL return zero results
4. THE Database_Factory SHALL raise an error if legacy database types are requested

### Requirement 7: Validate Container Build

**User Story:** As a developer, I want to verify the container image builds successfully, so that I can confirm the cleanup did not break the build process.

#### Acceptance Criteria

1. WHEN the container image is built after cleanup, THE System SHALL complete the build without errors
2. WHEN the container image is built, THE System SHALL NOT include `neo4j` package in the final image
3. WHEN the container image is built, THE System SHALL NOT include `pymilvus` package in the final image
4. WHEN inspecting the container image layers, THE System SHALL show reduced image size compared to pre-cleanup

### Requirement 8: Update Health Checks

**User Story:** As a developer, I want health checks to only validate AWS-native services, so that the application does not attempt to check connectivity to services that no longer exist.

#### Acceptance Criteria

1. WHEN health checks execute, THE System SHALL only check Neptune connectivity
2. WHEN health checks execute, THE System SHALL only check OpenSearch connectivity
3. WHEN health checks execute, THE System SHALL NOT attempt to connect to Neo4j
4. WHEN health checks execute, THE System SHALL NOT attempt to connect to Milvus
5. WHEN all AWS-native services are healthy, THE Health_Check SHALL return success

### Requirement 9: Remove Localhost Configuration

**User Story:** As a developer, I want all localhost database connection configuration removed, so that there is no risk of accidentally deploying development configuration to production.

#### Acceptance Criteria

1. WHEN searching the codebase for `localhost:7687` (Neo4j), THE System SHALL return zero results
2. WHEN searching the codebase for `localhost:19530` (Milvus), THE System SHALL return zero results
3. WHEN searching configuration files for localhost database URLs, THE System SHALL return zero results
4. THE System SHALL only contain AWS service endpoints in database configuration

### Requirement 10: Document Cleanup

**User Story:** As a developer, I want documentation explaining what was removed and why, so that future developers understand the system's evolution.

#### Acceptance Criteria

1. THE System SHALL include a CLEANUP_SUMMARY.md document in the repository root
2. THE Cleanup_Summary SHALL list all removed files with their original paths
3. THE Cleanup_Summary SHALL explain the migration to AWS-native databases
4. THE Cleanup_Summary SHALL reference the archive location for removed code
5. THE Cleanup_Summary SHALL include validation steps to confirm cleanup success
