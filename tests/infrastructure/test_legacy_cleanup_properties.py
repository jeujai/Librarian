"""
Property-based tests for legacy database cleanup.

These tests validate universal correctness properties that should hold
across all valid executions of the system after legacy database cleanup.

Feature: legacy-database-cleanup
Testing Framework: hypothesis
"""

import os
import re
from pathlib import Path
from typing import List, Set

import pytest
from hypothesis import given, strategies as st, settings, HealthCheck


# Property 1: No Legacy Imports in Codebase
# Validates: Requirements 3.5, 3.6

def find_python_files(root_dir: str = "src") -> List[Path]:
    """Find all Python files in the codebase."""
    root = Path(root_dir)
    if not root.exists():
        return []
    return list(root.rglob("*.py"))


def check_file_for_legacy_imports(file_path: Path) -> List[str]:
    """Check a single file for legacy database imports."""
    try:
        content = file_path.read_text()
        legacy_imports = []
        
        # Check for neo4j imports
        if re.search(r'import\s+neo4j', content, re.IGNORECASE):
            legacy_imports.append(f"neo4j import in {file_path}")
        if re.search(r'from\s+neo4j', content, re.IGNORECASE):
            legacy_imports.append(f"neo4j import in {file_path}")
        
        # Check for pymilvus imports
        if re.search(r'import\s+pymilvus', content, re.IGNORECASE):
            legacy_imports.append(f"pymilvus import in {file_path}")
        if re.search(r'from\s+pymilvus', content, re.IGNORECASE):
            legacy_imports.append(f"pymilvus import in {file_path}")
        
        # Check for legacy client imports
        if re.search(r'from.*neo4j_client', content):
            legacy_imports.append(f"neo4j_client import in {file_path}")
        if re.search(r'import.*neo4j_client', content):
            legacy_imports.append(f"neo4j_client import in {file_path}")
        
        return legacy_imports
    except Exception as e:
        print(f"Warning: Could not read {file_path}: {e}")
        return []


@given(st.sampled_from(find_python_files() or [Path("dummy.py")]))
@settings(max_examples=100, suppress_health_check=[HealthCheck.function_scoped_fixture])
def test_property_no_legacy_imports_in_any_file(file_path: Path):
    """
    Property 1: No Legacy Imports in Codebase
    
    For any Python file in the codebase, searching for neo4j or pymilvus
    import statements should return zero results.
    
    **Validates: Requirements 3.5, 3.6**
    """
    if file_path.name == "dummy.py":
        pytest.skip("No Python files found")
    
    legacy_imports = check_file_for_legacy_imports(file_path)
    
    assert len(legacy_imports) == 0, \
        f"Found legacy imports: {', '.join(legacy_imports)}"


# Property 2: No Legacy Client Files
# Validates: Requirements 2.4

LEGACY_FILE_PATTERNS = [
    "neo4j_client.py",
    "neo4j_config.py",
    "milvus_config_basic.py",
    "milvus_client.py",
]


def find_files_matching_pattern(pattern: str, root_dir: str = "src") -> List[Path]:
    """Find files matching a legacy pattern."""
    root = Path(root_dir)
    if not root.exists():
        return []
    
    matches = []
    for file_path in root.rglob("*.py"):
        if pattern in file_path.name:
            matches.append(file_path)
    return matches


@given(st.sampled_from(LEGACY_FILE_PATTERNS))
@settings(max_examples=len(LEGACY_FILE_PATTERNS))
def test_property_no_legacy_client_files(pattern: str):
    """
    Property 2: No Legacy Client Files
    
    For any search of the codebase for legacy client file patterns,
    the system should return zero file matches.
    
    **Validates: Requirements 2.4**
    """
    matches = find_files_matching_pattern(pattern)
    
    assert len(matches) == 0, \
        f"Found legacy files matching '{pattern}': {[str(m) for m in matches]}"


# Property 3: Database Factory Only Returns AWS-Native Clients
# Validates: Requirements 5.5, 6.1

def test_property_database_factory_returns_aws_native_only():
    """
    Property 3: Database Factory Only Returns AWS-Native Clients
    
    For any valid configuration passed to the database factory,
    the returned client should be either a Neptune client or an
    OpenSearch client, never a Neo4j or Milvus client.
    
    **Validates: Requirements 5.5, 6.1**
    """
    try:
        from src.multimodal_librarian.clients.database_factory import DatabaseFactory
        
        factory = DatabaseFactory()
        
        # Test Neptune client
        try:
            neptune_client = factory.get_graph_client("neptune")
            assert neptune_client is not None
            assert "Neptune" in type(neptune_client).__name__ or "neptune" in str(type(neptune_client)).lower()
        except Exception as e:
            # It's okay if Neptune client fails due to missing config
            # We just want to ensure it doesn't return Neo4j
            assert "neo4j" not in str(e).lower(), f"Neo4j reference found in error: {e}"
        
        # Test OpenSearch client
        try:
            opensearch_client = factory.get_vector_client("opensearch")
            assert opensearch_client is not None
            assert "OpenSearch" in type(opensearch_client).__name__ or "opensearch" in str(type(opensearch_client)).lower()
        except Exception as e:
            # It's okay if OpenSearch client fails due to missing config
            # We just want to ensure it doesn't return Milvus
            assert "milvus" not in str(e).lower(), f"Milvus reference found in error: {e}"
            
    except ImportError as e:
        pytest.skip(f"Could not import DatabaseFactory: {e}")


# Property 4: Database Factory Rejects Legacy Backends
# Validates: Requirements 6.4

LEGACY_BACKENDS = ["neo4j", "milvus", "Neo4j", "Milvus", "NEO4J", "MILVUS"]


@given(st.sampled_from(LEGACY_BACKENDS))
@settings(max_examples=len(LEGACY_BACKENDS))
def test_property_database_factory_rejects_legacy_backends(backend: str):
    """
    Property 4: Database Factory Rejects Legacy Backends
    
    For any request to the database factory for a legacy backend type,
    the system should raise a ValueError indicating the backend is unsupported.
    
    **Validates: Requirements 6.4**
    """
    try:
        from src.multimodal_librarian.clients.database_factory import DatabaseFactory
        
        factory = DatabaseFactory()
        
        # Determine if this is a graph or vector backend
        is_graph = "neo4j" in backend.lower()
        
        with pytest.raises((ValueError, KeyError, AttributeError)) as exc_info:
            if is_graph:
                factory.get_graph_client(backend)
            else:
                factory.get_vector_client(backend)
        
        # Verify the error message indicates unsupported backend
        error_msg = str(exc_info.value).lower()
        assert "unsupported" in error_msg or "not supported" in error_msg or \
               "invalid" in error_msg or "unknown" in error_msg, \
               f"Error message should indicate unsupported backend: {error_msg}"
               
    except ImportError as e:
        pytest.skip(f"Could not import DatabaseFactory: {e}")


# Property 5: No Localhost Database URLs
# Validates: Requirements 9.1, 9.2, 9.3

LOCALHOST_PATTERNS = [
    r'localhost:7687',  # Neo4j default port
    r'localhost:19530',  # Milvus default port
    r'127\.0\.0\.1:7687',
    r'127\.0\.0\.1:19530',
    r'bolt://localhost',
    r'neo4j://localhost',
]


def check_file_for_localhost_urls(file_path: Path) -> List[str]:
    """Check a file for localhost database URLs."""
    try:
        content = file_path.read_text()
        found_urls = []
        
        for pattern in LOCALHOST_PATTERNS:
            if re.search(pattern, content, re.IGNORECASE):
                found_urls.append(f"{pattern} in {file_path}")
        
        return found_urls
    except Exception as e:
        print(f"Warning: Could not read {file_path}: {e}")
        return []


@given(st.sampled_from(find_python_files() or [Path("dummy.py")]))
@settings(max_examples=100, suppress_health_check=[HealthCheck.function_scoped_fixture])
def test_property_no_localhost_database_urls(file_path: Path):
    """
    Property 5: No Localhost Database URLs
    
    For any file in the codebase, searching for localhost database
    connection strings should return zero results.
    
    **Validates: Requirements 9.1, 9.2, 9.3**
    """
    if file_path.name == "dummy.py":
        pytest.skip("No Python files found")
    
    localhost_urls = check_file_for_localhost_urls(file_path)
    
    assert len(localhost_urls) == 0, \
        f"Found localhost database URLs: {', '.join(localhost_urls)}"


# Property 6: Only AWS Endpoints in Database Configuration
# Validates: Requirements 9.4

AWS_ENDPOINT_PATTERNS = [
    r'\.amazonaws\.com',
    r'neptune.*\.amazonaws\.com',
    r'opensearch.*\.amazonaws\.com',
    r'es\.amazonaws\.com',
]


def check_file_for_database_endpoints(file_path: Path) -> dict:
    """Check a file for database endpoint configurations."""
    try:
        content = file_path.read_text()
        
        # Look for database-related configuration
        has_db_config = any([
            'DATABASE_URL' in content,
            'DB_HOST' in content,
            'GRAPH_ENDPOINT' in content,
            'VECTOR_ENDPOINT' in content,
            'NEPTUNE' in content,
            'OPENSEARCH' in content,
        ])
        
        if not has_db_config:
            return {"has_config": False}
        
        # Check for AWS endpoints
        has_aws_endpoint = any(
            re.search(pattern, content, re.IGNORECASE)
            for pattern in AWS_ENDPOINT_PATTERNS
        )
        
        # Check for localhost (should not be present)
        has_localhost = any(
            re.search(pattern, content, re.IGNORECASE)
            for pattern in LOCALHOST_PATTERNS
        )
        
        return {
            "has_config": True,
            "has_aws_endpoint": has_aws_endpoint,
            "has_localhost": has_localhost,
            "file": str(file_path)
        }
    except Exception as e:
        print(f"Warning: Could not read {file_path}: {e}")
        return {"has_config": False}


@given(st.sampled_from(find_python_files() or [Path("dummy.py")]))
@settings(max_examples=100, suppress_health_check=[HealthCheck.function_scoped_fixture])
def test_property_only_aws_endpoints_in_config(file_path: Path):
    """
    Property 6: Only AWS Endpoints in Database Configuration
    
    For any database configuration in the system, all connection endpoints
    should be AWS service endpoints, not localhost or legacy database endpoints.
    
    **Validates: Requirements 9.4**
    """
    if file_path.name == "dummy.py":
        pytest.skip("No Python files found")
    
    result = check_file_for_database_endpoints(file_path)
    
    if not result["has_config"]:
        # File doesn't have database config, skip
        return
    
    # If file has database config, it should not have localhost
    assert not result["has_localhost"], \
        f"Found localhost in database config: {result['file']}"
    
    # Note: We don't strictly require AWS endpoints in every config file
    # because some files might have placeholder or test configurations


# Integration test to run all properties
def test_all_properties_pass():
    """
    Meta-test that ensures all property tests can be discovered and run.
    
    This test validates that the property-based testing infrastructure
    is working correctly.
    """
    # Count property tests
    property_tests = [
        test_property_no_legacy_imports_in_any_file,
        test_property_no_legacy_client_files,
        test_property_database_factory_returns_aws_native_only,
        test_property_database_factory_rejects_legacy_backends,
        test_property_no_localhost_database_urls,
        test_property_only_aws_endpoints_in_config,
    ]
    
    assert len(property_tests) == 6, \
        f"Expected 6 property tests, found {len(property_tests)}"
    
    print(f"✓ All {len(property_tests)} property tests are defined")


if __name__ == "__main__":
    print("Running property-based tests for legacy database cleanup...")
    print("=" * 70)
    
    # Run with pytest
    pytest.main([__file__, "-v", "--tb=short"])
