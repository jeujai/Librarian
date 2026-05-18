## Purpose

The Multimodal Librarian system has been successfully migrated to AWS-native databases (Neptune for graph operations, OpenSearch for vector search). However, legacy Neo4j and Milvus code, dependencies, and configuration remain in the codebase. This creates a risk of accidental regressions where development configuration (localhost connections) could be deployed to production, as evidenced by a recent incident where a task definition was deployed without AWS-native configuration.

This specification defines the requirements for completely removing all Neo4j and Milvus dependencies, client code, and configuration from the codebase while preserving AWS-native functionality and maintaining an archive for reference.


### Key Terms
- **System**: The Multimodal Librarian application codebase
- **Legacy_Database**: Neo4j or Milvus database systems that have been replaced by AWS-native alternatives
- **AWS_Native_Database**: Neptune (graph) or OpenSearch (vector search) database systems
- **Container_Image**: Docker image built from the application codebase
- **Health_Check**: System validation that verifies service availability and correctness
- **Archive**: Storage location for removed code with documentation explaining removal rationale

## Requirements

### Requirement: Remove Legacy Dependencies

The system SHALL support: As a developer, I want legacy database dependencies removed from requirements.txt, so that the container image does not include unnecessary packages that could cause confusion or regressions.

#### Scenario: WHEN the requirements.txt file is processed, THE System SHAL

- **THEN** WHEN the requirements.txt file is processed, THE System SHALL NOT include the `neo4j` package

#### Scenario: WHEN the requirements.txt file is processed, THE System SHAL

- **THEN** WHEN the requirements.txt file is processed, THE System SHALL NOT include the `pymilvus` package

#### Scenario: WHEN the container image is built, THE System SHALL complete

- **THEN** WHEN the container image is built, THE System SHALL complete successfully without legacy database dependencies

### Requirement: Remove Legacy Client Files

The system SHALL support: As a developer, I want legacy database client files removed from the codebase, so that there is no code that could accidentally connect to localhost services.

#### Scenario: THE System SHALL NOT contain the file `src/multimodal_librar

- **THEN** THE System SHALL NOT contain the file `src/multimodal_librarian/clients/neo4j_client.py`

#### Scenario: THE System SHALL NOT contain the file `src/multimodal_librar

- **THEN** THE System SHALL NOT contain the file `src/multimodal_librarian/config/neo4j_config.py`

#### Scenario: THE System SHALL NOT contain the file `src/multimodal_librar

- **THEN** THE System SHALL NOT contain the file `src/multimodal_librarian/aws/milvus_config_basic.py`

#### Scenario: WHEN searching the codebase for legacy client files, THE Sys

- **THEN** WHEN searching the codebase for legacy client files, THE System SHALL return zero results

### Requirement: Remove Legacy Import References

The system SHALL support: As a developer, I want all import statements referencing legacy databases removed, so that the code does not attempt to use removed modules.

#### Scenario: WHEN parsing `src/multimodal_librarian/services/knowledge_gr

- **THEN** WHEN parsing `src/multimodal_librarian/services/knowledge_graph_service.py`, THE System SHALL NOT contain imports from `neo4j_client`

#### Scenario: WHEN parsing `src/multimodal_librarian/monitoring/health_che

- **THEN** WHEN parsing `src/multimodal_librarian/monitoring/health_checker.py`, THE System SHALL NOT contain imports from `neo4j_client` or `neo4j_config`

#### Scenario: WHEN parsing `src/multimodal_librarian/monitoring/component_

- **THEN** WHEN parsing `src/multimodal_librarian/monitoring/component_health_checks.py`, THE System SHALL NOT contain imports from `neo4j_client` or `pymilvus`

#### Scenario: WHEN parsing `src/multimodal_librarian/aws/secrets_manager_b

- **THEN** WHEN parsing `src/multimodal_librarian/aws/secrets_manager_basic.py`, THE System SHALL NOT contain Neo4j configuration references

#### Scenario: WHEN searching the entire codebase for `neo4j` imports, THE

- **THEN** WHEN searching the entire codebase for `neo4j` imports, THE System SHALL return zero results

#### Scenario: WHEN searching the entire codebase for `pymilvus` imports, T

- **THEN** WHEN searching the entire codebase for `pymilvus` imports, THE System SHALL return zero results

### Requirement: Archive Removed Files

The system SHALL support: As a developer, I want removed files archived with documentation, so that I can reference the legacy implementation if needed for historical context.

#### Scenario: WHEN legacy files are removed, THE System SHALL copy them to

- **THEN** WHEN legacy files are removed, THE System SHALL copy them to `archive/legacy-databases/` before deletion

#### Scenario: WHEN files are archived, THE System SHALL create a README.md

- **THEN** WHEN files are archived, THE System SHALL create a README.md in the archive directory explaining what was removed and why

#### Scenario: THE Archive SHALL include the original file paths in the doc

- **THEN** THE Archive SHALL include the original file paths in the documentation

#### Scenario: THE Archive SHALL include the date of removal in the documen

- **THEN** THE Archive SHALL include the date of removal in the documentation

#### Scenario: THE Archive SHALL include a reference to the AWS-native migr

- **THEN** THE Archive SHALL include a reference to the AWS-native migration that replaced the legacy code

### Requirement: Preserve AWS-Native Functionality

The system SHALL support: As a developer, I want AWS-native database clients and configuration preserved, so that the application continues to function correctly with Neptune and OpenSearch.

#### Scenario: WHEN the cleanup is complete, THE System SHALL retain `src/m

- **THEN** WHEN the cleanup is complete, THE System SHALL retain `src/multimodal_librarian/clients/neptune_client.py`

#### Scenario: WHEN the cleanup is complete, THE System SHALL retain `src/m

- **THEN** WHEN the cleanup is complete, THE System SHALL retain `src/multimodal_librarian/clients/opensearch_client.py`

#### Scenario: WHEN the cleanup is complete, THE System SHALL retain `src/m

- **THEN** WHEN the cleanup is complete, THE System SHALL retain `src/multimodal_librarian/config/aws_native_config.py`

#### Scenario: WHEN the cleanup is complete, THE System SHALL retain `src/m

- **THEN** WHEN the cleanup is complete, THE System SHALL retain `src/multimodal_librarian/clients/database_factory.py`

#### Scenario: THE Database_Factory SHALL only support AWS-native database

- **THEN** THE Database_Factory SHALL only support AWS-native database backends after cleanup

### Requirement: Update Database Factory

The system SHALL support: As a developer, I want the database factory to only support AWS-native backends, so that there is no code path that could instantiate legacy database clients.

#### Scenario: WHEN the database factory is invoked with any configuration,

- **THEN** WHEN the database factory is invoked with any configuration, THE System SHALL only return Neptune or OpenSearch clients

#### Scenario: WHEN searching the database factory code for Neo4j reference

- **THEN** WHEN searching the database factory code for Neo4j references, THE System SHALL return zero results

#### Scenario: WHEN searching the database factory code for Milvus referenc

- **THEN** WHEN searching the database factory code for Milvus references, THE System SHALL return zero results

#### Scenario: THE Database_Factory SHALL raise an error if legacy database

- **THEN** THE Database_Factory SHALL raise an error if legacy database types are requested

### Requirement: Validate Container Build

The system SHALL support: As a developer, I want to verify the container image builds successfully, so that I can confirm the cleanup did not break the build process.

#### Scenario: WHEN the container image is built after cleanup, THE System

- **THEN** WHEN the container image is built after cleanup, THE System SHALL complete the build without errors

#### Scenario: WHEN the container image is built, THE System SHALL NOT incl

- **THEN** WHEN the container image is built, THE System SHALL NOT include `neo4j` package in the final image

#### Scenario: WHEN the container image is built, THE System SHALL NOT incl

- **THEN** WHEN the container image is built, THE System SHALL NOT include `pymilvus` package in the final image

#### Scenario: WHEN inspecting the container image layers, THE System SHALL

- **THEN** WHEN inspecting the container image layers, THE System SHALL show reduced image size compared to pre-cleanup

### Requirement: Update Health Checks

The system SHALL support: As a developer, I want health checks to only validate AWS-native services, so that the application does not attempt to check connectivity to services that no longer exist.

#### Scenario: WHEN health checks execute, THE System SHALL only check Nept

- **THEN** WHEN health checks execute, THE System SHALL only check Neptune connectivity

#### Scenario: WHEN health checks execute, THE System SHALL only check Open

- **THEN** WHEN health checks execute, THE System SHALL only check OpenSearch connectivity

#### Scenario: WHEN health checks execute, THE System SHALL NOT attempt to

- **THEN** WHEN health checks execute, THE System SHALL NOT attempt to connect to Neo4j

#### Scenario: WHEN health checks execute, THE System SHALL NOT attempt to

- **THEN** WHEN health checks execute, THE System SHALL NOT attempt to connect to Milvus

#### Scenario: WHEN all AWS-native services are healthy, THE Health_Check S

- **THEN** WHEN all AWS-native services are healthy, THE Health_Check SHALL return success

### Requirement: Remove Localhost Configuration

The system SHALL support: As a developer, I want all localhost database connection configuration removed, so that there is no risk of accidentally deploying development configuration to production.

#### Scenario: WHEN searching the codebase for `localhost:7687` (Neo4j), TH

- **THEN** WHEN searching the codebase for `localhost:7687` (Neo4j), THE System SHALL return zero results

#### Scenario: WHEN searching the codebase for `localhost:19530` (Milvus),

- **THEN** WHEN searching the codebase for `localhost:19530` (Milvus), THE System SHALL return zero results

#### Scenario: WHEN searching configuration files for localhost database UR

- **THEN** WHEN searching configuration files for localhost database URLs, THE System SHALL return zero results

#### Scenario: THE System SHALL only contain AWS service endpoints in datab

- **THEN** THE System SHALL only contain AWS service endpoints in database configuration

### Requirement: Document Cleanup

The system SHALL support: As a developer, I want documentation explaining what was removed and why, so that future developers understand the system's evolution.

#### Scenario: THE System SHALL include a CLEANUP_SUMMARY.md document in th

- **THEN** THE System SHALL include a CLEANUP_SUMMARY.md document in the repository root

#### Scenario: THE Cleanup_Summary SHALL list all removed files with their

- **THEN** THE Cleanup_Summary SHALL list all removed files with their original paths

#### Scenario: THE Cleanup_Summary SHALL explain the migration to AWS-nativ

- **THEN** THE Cleanup_Summary SHALL explain the migration to AWS-native databases

#### Scenario: THE Cleanup_Summary SHALL reference the archive location for

- **THEN** THE Cleanup_Summary SHALL reference the archive location for removed code

#### Scenario: THE Cleanup_Summary SHALL include validation steps to confir

- **THEN** THE Cleanup_Summary SHALL include validation steps to confirm cleanup success
