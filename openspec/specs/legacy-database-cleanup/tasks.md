# Implementation Plan: Legacy Database Cleanup

## Overview

This plan outlines the systematic removal of all Neo4j and Milvus dependencies, client code, and configuration from the Multimodal Librarian codebase. The cleanup will be performed incrementally with validation at each step to ensure AWS-native functionality remains intact.

## Tasks

- [x] 1. Create archive structure and document removal plan
  - Create `archive/legacy-databases/` directory structure
  - Create `archive/legacy-databases/README.md` with removal documentation
  - Document original file paths, removal date, and migration reference
  - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.5_

- [x] 2. Archive legacy client files before removal
  - [x] 2.1 Copy `src/multimodal_librarian/clients/neo4j_client.py` to archive
    - Copy to `archive/legacy-databases/clients/neo4j_client.py`
    - Preserve file permissions and metadata
    - _Requirements: 4.1_
  
  - [x] 2.2 Copy `src/multimodal_librarian/config/neo4j_config.py` to archive
    - Copy to `archive/legacy-databases/config/neo4j_config.py`
    - Preserve file permissions and metadata
    - _Requirements: 4.1_
  
  - [x] 2.3 Copy `src/multimodal_librarian/aws/milvus_config_basic.py` to archive
    - Copy to `archive/legacy-databases/aws/milvus_config_basic.py`
    - Preserve file permissions and metadata
    - _Requirements: 4.1_
  
  - [ ]* 2.4 Write unit tests to verify archive structure
    - Test that all files exist in archive
    - Test that README.md contains required information
    - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.5_

- [x] 3. Remove legacy dependencies from requirements.txt
  - [x] 3.1 Remove `neo4j` package from requirements.txt
    - Remove line containing neo4j package specification
    - _Requirements: 1.1_
  
  - [x] 3.2 Remove `pymilvus` package from requirements.txt
    - Remove line containing pymilvus package specification
    - _Requirements: 1.2_
  
  - [ ]* 3.3 Write unit test to verify dependencies removed
    - Test that requirements.txt does not contain neo4j
    - Test that requirements.txt does not contain pymilvus
    - _Requirements: 1.1, 1.2_

- [x] 4. Update database factory to remove legacy backend support
  - [x] 4.1 Remove Neo4j client instantiation from database factory
    - Remove neo4j_client import
    - Remove Neo4j backend case from get_graph_client()
    - Add ValueError for unsupported backends
    - _Requirements: 6.1, 6.2, 6.4_
  
  - [x] 4.2 Remove Milvus client instantiation from database factory
    - Remove milvus references
    - Remove Milvus backend case from get_vector_client()
    - Add ValueError for unsupported backends
    - _Requirements: 6.1, 6.3, 6.4_
  
  - [ ]* 4.3 Write property test for database factory AWS-native only behavior
    - **Property 3: Database Factory Only Returns AWS-Native Clients**
    - **Validates: Requirements 5.5, 6.1**
  
  - [ ]* 4.4 Write property test for database factory legacy rejection
    - **Property 4: Database Factory Rejects Legacy Backends**
    - **Validates: Requirements 6.4**

- [x] 5. Remove legacy imports from service files
  - [x] 5.1 Update knowledge_graph_service.py to remove Neo4j imports
    - Remove neo4j_client import statements
    - Verify file uses only Neptune client
    - _Requirements: 3.1_
  
  - [x] 5.2 Update health_checker.py to remove Neo4j imports
    - Remove neo4j_client and neo4j_config imports
    - Remove Neo4j health check logic
    - _Requirements: 3.2, 8.3_
  
  - [x] 5.3 Update component_health_checks.py to remove legacy imports
    - Remove neo4j_client imports
    - Remove pymilvus imports
    - Remove Neo4j and Milvus health check functions
    - _Requirements: 3.3, 8.3, 8.4_
  
  - [x] 5.4 Update secrets_manager_basic.py to remove Neo4j configuration
    - Remove Neo4j configuration references
    - Remove Neo4j secret retrieval logic
    - _Requirements: 3.4_
  
  - [ ]* 5.5 Write property test for no legacy imports in codebase
    - **Property 1: No Legacy Imports in Codebase**
    - **Validates: Requirements 3.5, 3.6**

- [x] 6. Delete legacy client files
  - [x] 6.1 Delete `src/multimodal_librarian/clients/neo4j_client.py`
    - Verify file is archived before deletion
    - _Requirements: 2.1_
  
  - [x] 6.2 Delete `src/multimodal_librarian/config/neo4j_config.py`
    - Verify file is archived before deletion
    - _Requirements: 2.2_
  
  - [x] 6.3 Delete `src/multimodal_librarian/aws/milvus_config_basic.py`
    - Verify file is archived before deletion
    - _Requirements: 2.3_
  
  - [ ]* 6.4 Write property test for no legacy client files
    - **Property 2: No Legacy Client Files**
    - **Validates: Requirements 2.4**

- [x] 7. Checkpoint - Verify AWS-native files preserved
  - Verify neptune_client.py exists and is unchanged
  - Verify opensearch_client.py exists and is unchanged
  - Verify aws_native_config.py exists and is unchanged
  - Verify database_factory.py exists
  - Ensure all tests pass, ask the user if questions arise
  - _Requirements: 5.1, 5.2, 5.3, 5.4_

- [x] 8. Update health checks to only validate AWS-native services
  - [x] 8.1 Update health check system to only check Neptune
    - Remove Neo4j health check calls
    - Ensure Neptune health check remains
    - _Requirements: 8.1, 8.3_
  
  - [x] 8.2 Update health check system to only check OpenSearch
    - Remove Milvus health check calls
    - Ensure OpenSearch health check remains
    - _Requirements: 8.2, 8.4_
  
  - [ ]* 8.3 Write unit test for health check success with AWS-native services
    - Mock healthy Neptune and OpenSearch
    - Verify health check returns success
    - _Requirements: 8.5_

- [x] 9. Remove localhost database configuration
  - [x] 9.1 Search and remove localhost:7687 references (Neo4j)
    - Search all configuration files
    - Remove or replace with AWS endpoints
    - _Requirements: 9.1_
  
  - [x] 9.2 Search and remove localhost:19530 references (Milvus)
    - Search all configuration files
    - Remove or replace with AWS endpoints
    - _Requirements: 9.2_
  
  - [ ]* 9.3 Write property test for no localhost database URLs
    - **Property 5: No Localhost Database URLs**
    - **Validates: Requirements 9.1, 9.2, 9.3**
  
  - [ ]* 9.4 Write property test for only AWS endpoints in configuration
    - **Property 6: Only AWS Endpoints in Database Configuration**
    - **Validates: Requirements 9.4**

- [x] 10. Validate container build
  - [x] 10.1 Build container image with updated dependencies
    - Run docker build command
    - Verify build completes without errors
    - _Requirements: 1.3, 7.1_
  
  - [x] 10.2 Inspect container image for legacy packages
    - Verify neo4j package is not in image
    - Verify pymilvus package is not in image
    - _Requirements: 7.2, 7.3_
  
  - [ ]* 10.3 Write unit test for container build success
    - Test that build command exits with code 0
    - Test that image is created successfully
    - _Requirements: 1.3, 7.1_
  
  - [ ]* 10.4 Write unit test for reduced image size
    - Compare image size before and after cleanup
    - Verify size reduction
    - _Requirements: 7.4_

- [x] 11. Create cleanup documentation
  - [x] 11.1 Create CLEANUP_SUMMARY.md in repository root
    - List all removed files with original paths
    - Explain migration to AWS-native databases
    - Reference archive location
    - Include validation steps
    - _Requirements: 10.1, 10.2, 10.3, 10.4, 10.5_
  
  - [ ]* 11.2 Write unit test for cleanup documentation completeness
    - Verify CLEANUP_SUMMARY.md exists
    - Verify all required sections are present
    - _Requirements: 10.1, 10.2, 10.3, 10.4, 10.5_

- [x] 12. Final validation and integration testing
  - [x]* 12.1 Run all property tests
    - Execute all property-based tests
    - Verify all properties pass with 100+ iterations
    - _Requirements: All_
  
  - [x]* 12.2 Run all unit tests
    - Execute complete unit test suite
    - Verify all tests pass
    - _Requirements: All_
  
  - [x]* 12.3 Write end-to-end integration test
    - Test full application startup
    - Test database connectivity (AWS-native only)
    - Test health checks pass
    - Verify no legacy code is executed
    - _Requirements: All_

- [x] 13. Final checkpoint - Ensure all tests pass
  - Run complete test suite
  - Verify container builds successfully
  - Verify health checks pass with AWS-native services
  - Verify no legacy imports or files remain
  - Ensure all tests pass, ask the user if questions arise

## Notes

- Tasks marked with `*` are optional and can be skipped for faster completion
- Each task references specific requirements for traceability
- Checkpoints ensure incremental validation
- Archive is created before any deletions to enable rollback
- Property tests validate universal correctness properties across the codebase
- Unit tests validate specific examples and edge cases
