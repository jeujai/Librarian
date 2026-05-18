# Design Document: Legacy Database Cleanup

## Overview

This design document outlines the approach for removing all Neo4j and Milvus dependencies, client code, and configuration from the Multimodal Librarian codebase. The system has been successfully migrated to AWS-native databases (Neptune for graph operations, OpenSearch for vector search), but legacy code remains and poses a risk of accidental regressions.

The cleanup will be performed systematically to ensure:
1. All legacy dependencies are removed from package manifests
2. All legacy client files are archived and deleted
3. All import references are removed from active code
4. AWS-native functionality remains intact
5. Container builds succeed without legacy packages
6. Health checks only validate AWS-native services

## Architecture

### Current State

The codebase currently contains a mix of:
- **AWS-native clients**: `neptune_client.py`, `opensearch_client.py`
- **Legacy clients**: `neo4j_client.py` (to be removed)
- **Legacy configuration**: `neo4j_config.py`, `milvus_config_basic.py` (to be removed)
- **Database factory**: Supports both legacy and AWS-native backends
- **Health checks**: Check both legacy and AWS-native services

### Target State

After cleanup:
- **AWS-native clients only**: Neptune and OpenSearch clients remain
- **No legacy clients**: All Neo4j and Milvus code removed
- **Simplified database factory**: Only supports AWS-native backends
- **AWS-native health checks**: Only validate Neptune and OpenSearch
- **Archive**: Legacy code preserved in `archive/legacy-databases/` with documentation

### Cleanup Strategy

The cleanup follows a safe, incremental approach:

1. **Archive First**: Copy all files to be removed to archive directory
2. **Remove Dependencies**: Update requirements.txt to remove `neo4j` and `pymilvus`
3. **Remove Client Files**: Delete legacy client and configuration files
4. **Update Imports**: Remove all import statements referencing legacy code
5. **Update Database Factory**: Remove legacy backend support
6. **Update Health Checks**: Remove legacy service checks
7. **Validate Build**: Ensure container image builds successfully
8. **Document**: Create comprehensive cleanup documentation

## Components and Interfaces

### Files to Archive and Remove

**Client Files:**
- `src/multimodal_librarian/clients/neo4j_client.py`
- `src/multimodal_librarian/config/neo4j_config.py`
- `src/multimodal_librarian/aws/milvus_config_basic.py`

**Files to Update (Remove Imports):**
- `src/multimodal_librarian/services/knowledge_graph_service.py`
- `src/multimodal_librarian/monitoring/health_checker.py`
- `src/multimodal_librarian/monitoring/component_health_checks.py`
- `src/multimodal_librarian/aws/secrets_manager_basic.py`
- `src/multimodal_librarian/clients/database_factory.py`

**Files to Preserve:**
- `src/multimodal_librarian/clients/neptune_client.py`
- `src/multimodal_librarian/clients/opensearch_client.py`
- `src/multimodal_librarian/config/aws_native_config.py`

### Archive Structure

```
archive/legacy-databases/
├── README.md                          # Explains what was removed and why
├── clients/
│   └── neo4j_client.py               # Archived Neo4j client
├── config/
│   └── neo4j_config.py               # Archived Neo4j configuration
└── aws/
    └── milvus_config_basic.py        # Archived Milvus configuration
```

### Database Factory Interface

**Before Cleanup:**
```python
class DatabaseFactory:
    def get_graph_client(self, backend: str):
        if backend == "neo4j":
            return Neo4jClient()
        elif backend == "neptune":
            return NeptuneClient()
        
    def get_vector_client(self, backend: str):
        if backend == "milvus":
            return MilvusClient()
        elif backend == "opensearch":
            return OpenSearchClient()
```

**After Cleanup:**
```python
class DatabaseFactory:
    def get_graph_client(self, backend: str):
        if backend == "neptune":
            return NeptuneClient()
        else:
            raise ValueError(f"Unsupported graph backend: {backend}")
        
    def get_vector_client(self, backend: str):
        if backend == "opensearch":
            return OpenSearchClient()
        else:
            raise ValueError(f"Unsupported vector backend: {backend}")
```

### Health Check Updates

**Before Cleanup:**
```python
def check_databases():
    results = {}
    results['neo4j'] = check_neo4j_connection()
    results['neptune'] = check_neptune_connection()
    results['milvus'] = check_milvus_connection()
    results['opensearch'] = check_opensearch_connection()
    return results
```

**After Cleanup:**
```python
def check_databases():
    results = {}
    results['neptune'] = check_neptune_connection()
    results['opensearch'] = check_opensearch_connection()
    return results
```

## Data Models

### Archive Metadata

```python
@dataclass
class ArchivedFile:
    original_path: str
    archive_path: str
    removal_date: str
    removal_reason: str
    migration_reference: str
```

### Cleanup Validation Result

```python
@dataclass
class CleanupValidation:
    legacy_imports_found: List[str]
    legacy_files_found: List[str]
    localhost_configs_found: List[str]
    container_build_success: bool
    health_checks_pass: bool
    aws_native_clients_intact: bool
```

## Correctness Properties

*A property is a characteristic or behavior that should hold true across all valid executions of a system—essentially, a formal statement about what the system should do. Properties serve as the bridge between human-readable specifications and machine-verifiable correctness guarantees.*


### Property 1: No Legacy Imports in Codebase

*For any* Python file in the codebase, searching for `neo4j` or `pymilvus` import statements should return zero results.

**Validates: Requirements 3.5, 3.6**

### Property 2: No Legacy Client Files

*For any* search of the codebase for legacy client file patterns (neo4j_client, milvus_config), the system should return zero file matches.

**Validates: Requirements 2.4**

### Property 3: Database Factory Only Returns AWS-Native Clients

*For any* valid configuration passed to the database factory, the returned client should be either a Neptune client or an OpenSearch client, never a Neo4j or Milvus client.

**Validates: Requirements 5.5, 6.1**

### Property 4: Database Factory Rejects Legacy Backends

*For any* request to the database factory for a legacy backend type (neo4j, milvus), the system should raise a ValueError indicating the backend is unsupported.

**Validates: Requirements 6.4**

### Property 5: No Localhost Database URLs

*For any* file in the codebase, searching for localhost database connection strings (localhost:7687, localhost:19530, or any localhost database URL pattern) should return zero results.

**Validates: Requirements 9.1, 9.2, 9.3**

### Property 6: Only AWS Endpoints in Database Configuration

*For any* database configuration in the system, all connection endpoints should be AWS service endpoints (Neptune, OpenSearch), not localhost or legacy database endpoints.

**Validates: Requirements 9.4**

## Error Handling

### Archive Creation Failures

If archiving fails (e.g., insufficient disk space, permission issues):
- **Abort cleanup**: Do not proceed with file deletion
- **Log error**: Record the specific failure reason
- **Notify user**: Provide clear error message with remediation steps

### Import Removal Failures

If removing imports breaks code (e.g., missing alternative imports):
- **Validate syntax**: Ensure Python files remain syntactically valid
- **Check for undefined references**: Scan for references to removed imports
- **Provide fix suggestions**: Suggest AWS-native alternatives

### Build Failures

If container build fails after cleanup:
- **Preserve logs**: Capture full build output for debugging
- **Identify missing dependencies**: Check if AWS-native dependencies are present
- **Rollback option**: Provide clear rollback instructions

### Health Check Failures

If health checks fail after cleanup:
- **Distinguish failure types**: Separate AWS service issues from code issues
- **Provide diagnostics**: Include connection details and error messages
- **Verify AWS services**: Confirm Neptune and OpenSearch are accessible

## Testing Strategy

### Dual Testing Approach

This cleanup will use both unit tests and property-based tests to ensure comprehensive validation:

**Unit Tests** will verify:
- Specific files are removed (neo4j_client.py, neo4j_config.py, milvus_config_basic.py)
- Specific files are preserved (neptune_client.py, opensearch_client.py, aws_native_config.py)
- Archive structure is correct with README.md
- Container builds successfully
- Health checks pass with AWS-native services
- Cleanup documentation exists and is complete

**Property Tests** will verify:
- No legacy imports exist anywhere in the codebase (search all .py files)
- No localhost database URLs exist anywhere in the codebase
- Database factory always returns AWS-native clients for valid inputs
- Database factory always rejects legacy backend requests
- All database configurations use only AWS endpoints

### Property-Based Testing Configuration

- **Testing Library**: Python's `hypothesis` library for property-based testing
- **Iterations**: Minimum 100 iterations per property test
- **Tag Format**: Each test will include a comment:
  ```python
  # Feature: legacy-database-cleanup, Property 1: No Legacy Imports in Codebase
  ```

### Test Organization

```
tests/
├── unit/
│   ├── test_file_removal.py           # Verify specific files removed
│   ├── test_file_preservation.py      # Verify AWS-native files preserved
│   ├── test_archive_structure.py      # Verify archive created correctly
│   ├── test_container_build.py        # Verify build succeeds
│   └── test_health_checks.py          # Verify health checks work
├── property/
│   ├── test_no_legacy_imports.py      # Property 1: No legacy imports
│   ├── test_no_legacy_files.py        # Property 2: No legacy files
│   ├── test_database_factory.py       # Properties 3-4: Factory behavior
│   └── test_no_localhost_config.py    # Properties 5-6: No localhost URLs
└── integration/
    └── test_end_to_end_cleanup.py     # Full cleanup validation
```

### Validation Steps

After cleanup, run these validation steps:

1. **Dependency Check**: Verify requirements.txt contains no legacy packages
2. **File Check**: Verify legacy files are removed and archived
3. **Import Check**: Search codebase for legacy imports (should be zero)
4. **Build Check**: Build container image successfully
5. **Health Check**: Run health checks (should pass with AWS-native services only)
6. **Configuration Check**: Verify no localhost database URLs in codebase
7. **Documentation Check**: Verify CLEANUP_SUMMARY.md exists and is complete

### Rollback Plan

If cleanup causes issues:

1. **Restore from archive**: Copy archived files back to original locations
2. **Restore requirements.txt**: Add back legacy dependencies
3. **Rebuild container**: Build with restored dependencies
4. **Verify functionality**: Run full test suite to confirm restoration

The archive serves as both documentation and a rollback mechanism.
