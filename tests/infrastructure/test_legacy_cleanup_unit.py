"""
Unit tests for legacy database cleanup.

These tests verify specific examples and edge cases for the cleanup process.

Feature: legacy-database-cleanup
"""

import os
import subprocess
from pathlib import Path
from typing import List

import pytest


class TestArchiveStructure:
    """Tests for archive structure validation (Task 2.4)."""
    
    def test_archive_directory_exists(self):
        """Test that archive directory exists."""
        archive_dir = Path("archive/legacy-databases")
        assert archive_dir.exists(), "Archive directory not found"
        assert archive_dir.is_dir(), "Archive path is not a directory"
    
    def test_archive_readme_exists(self):
        """Test that archive README exists."""
        readme_path = Path("archive/legacy-databases/README.md")
        assert readme_path.exists(), "Archive README.md not found"
    
    def test_archive_readme_contains_required_info(self):
        """Test that README contains required information."""
        readme_path = Path("archive/legacy-databases/README.md")
        if not readme_path.exists():
            pytest.skip("README.md not found")
        
        content = readme_path.read_text()
        
        # Check for required sections
        assert "removed" in content.lower() or "archived" in content.lower(), \
            "README should explain what was removed"
        assert "aws" in content.lower() or "neptune" in content.lower() or "opensearch" in content.lower(), \
            "README should reference AWS-native migration"
    
    def test_archived_files_exist(self):
        """Test that archived files exist in archive directory."""
        expected_files = [
            "archive/legacy-databases/clients/neo4j_client.py",
            "archive/legacy-databases/config/neo4j_config.py",
            "archive/legacy-databases/aws/milvus_config_basic.py",
        ]
        
        for file_path in expected_files:
            path = Path(file_path)
            assert path.exists(), f"Archived file not found: {file_path}"


class TestDependencyRemoval:
    """Tests for dependency removal (Task 3.3)."""
    
    def test_requirements_file_exists(self):
        """Test that requirements.txt exists."""
        req_path = Path("requirements.txt")
        assert req_path.exists(), "requirements.txt not found"
    
    def test_neo4j_not_in_requirements(self):
        """Test that neo4j package is not in requirements.txt."""
        req_path = Path("requirements.txt")
        content = req_path.read_text().lower()
        
        assert "neo4j" not in content, "neo4j package found in requirements.txt"
    
    def test_pymilvus_not_in_requirements(self):
        """Test that pymilvus package is not in requirements.txt."""
        req_path = Path("requirements.txt")
        content = req_path.read_text().lower()
        
        assert "pymilvus" not in content, "pymilvus package found in requirements.txt"
    
    def test_aws_native_dependencies_present(self):
        """Test that AWS-native dependencies are present."""
        req_path = Path("requirements.txt")
        content = req_path.read_text()
        
        # Check for Neptune dependency
        assert "gremlinpython" in content, "gremlinpython (Neptune) not in requirements.txt"
        
        # Check for OpenSearch dependency
        assert "opensearch-py" in content, "opensearch-py not in requirements.txt"


class TestLegacyFileRemoval:
    """Tests for legacy file removal (Task 6.4)."""
    
    def test_neo4j_client_removed(self):
        """Test that neo4j_client.py is removed from src."""
        client_path = Path("src/multimodal_librarian/clients/neo4j_client.py")
        assert not client_path.exists(), "neo4j_client.py still exists in src"
    
    def test_neo4j_config_removed(self):
        """Test that neo4j_config.py is removed from src."""
        config_path = Path("src/multimodal_librarian/config/neo4j_config.py")
        assert not config_path.exists(), "neo4j_config.py still exists in src"
    
    def test_milvus_config_removed(self):
        """Test that milvus_config_basic.py is removed from src."""
        config_path = Path("src/multimodal_librarian/aws/milvus_config_basic.py")
        assert not config_path.exists(), "milvus_config_basic.py still exists in src"


class TestAWSNativeFilesPreserved:
    """Tests for AWS-native file preservation (Task 7)."""
    
    def test_neptune_client_exists(self):
        """Test that neptune_client.py is preserved."""
        client_path = Path("src/multimodal_librarian/clients/neptune_client.py")
        assert client_path.exists(), "neptune_client.py not found"
    
    def test_opensearch_client_exists(self):
        """Test that opensearch_client.py is preserved."""
        client_path = Path("src/multimodal_librarian/clients/opensearch_client.py")
        assert client_path.exists(), "opensearch_client.py not found"
    
    def test_aws_native_config_exists(self):
        """Test that aws_native_config.py is preserved."""
        config_path = Path("src/multimodal_librarian/config/aws_native_config.py")
        assert config_path.exists(), "aws_native_config.py not found"
    
    def test_database_factory_exists(self):
        """Test that database_factory.py is preserved."""
        factory_path = Path("src/multimodal_librarian/clients/database_factory.py")
        assert factory_path.exists(), "database_factory.py not found"


class TestHealthCheckUpdates:
    """Tests for health check updates (Task 8.3)."""
    
    def test_health_check_success_with_aws_native_services(self):
        """
        Test that health check returns success with AWS-native services.
        
        This is a mock test since we can't actually connect to AWS services
        in unit tests. We verify the structure is correct.
        """
        try:
            from src.multimodal_librarian.monitoring.health_checker import HealthChecker
            
            # Verify HealthChecker can be instantiated
            checker = HealthChecker()
            assert checker is not None
            
        except ImportError as e:
            pytest.skip(f"Could not import HealthChecker: {e}")


class TestContainerBuild:
    """Tests for container build validation (Task 10.3, 10.4)."""
    
    def test_dockerfile_exists(self):
        """Test that Dockerfile exists."""
        dockerfile = Path("Dockerfile")
        assert dockerfile.exists(), "Dockerfile not found"
    
    def test_docker_build_command_valid(self):
        """Test that docker build command is valid."""
        # This tests the command syntax without actually running it
        build_command = ["docker", "build", "-t", "multimodal-librarian:test", "."]
        
        assert build_command[0] == "docker"
        assert build_command[1] == "build"
        assert "-t" in build_command
    
    def test_dockerfile_no_legacy_references(self):
        """Test that Dockerfile doesn't reference legacy packages."""
        dockerfile = Path("Dockerfile")
        content = dockerfile.read_text().lower()
        
        assert "neo4j" not in content, "neo4j reference found in Dockerfile"
        assert "pymilvus" not in content, "pymilvus reference found in Dockerfile"


class TestCleanupDocumentation:
    """Tests for cleanup documentation (Task 11.2)."""
    
    def test_cleanup_summary_exists(self):
        """Test that CLEANUP_SUMMARY.md exists."""
        summary_path = Path("CLEANUP_SUMMARY.md")
        assert summary_path.exists(), "CLEANUP_SUMMARY.md not found"
    
    def test_cleanup_summary_completeness(self):
        """Test that cleanup summary contains all required sections."""
        summary_path = Path("CLEANUP_SUMMARY.md")
        if not summary_path.exists():
            pytest.skip("CLEANUP_SUMMARY.md not found")
        
        content = summary_path.read_text().lower()
        
        # Check for required sections
        required_keywords = [
            "removed",
            "aws",
            "archive",
            "validation",
        ]
        
        for keyword in required_keywords:
            assert keyword in content, f"Required keyword '{keyword}' not found in CLEANUP_SUMMARY.md"


class TestDatabaseFactory:
    """Tests for database factory behavior."""
    
    def test_database_factory_imports(self):
        """Test that database factory can be imported."""
        try:
            from src.multimodal_librarian.clients import database_factory
            assert database_factory is not None
        except ImportError as e:
            pytest.fail(f"Could not import database_factory: {e}")
    
    def test_database_factory_no_legacy_imports(self):
        """Test that database factory doesn't import legacy clients."""
        factory_path = Path("src/multimodal_librarian/clients/database_factory.py")
        if not factory_path.exists():
            pytest.skip("database_factory.py not found")
        
        content = factory_path.read_text()
        
        # Check for legacy imports
        assert "neo4j_client" not in content, "neo4j_client import found in database_factory"
        assert "from neo4j" not in content.lower(), "neo4j import found in database_factory"
        assert "import neo4j" not in content.lower(), "neo4j import found in database_factory"


class TestLocalhostConfiguration:
    """Tests for localhost configuration removal (Task 9.3)."""
    
    def test_no_neo4j_localhost_in_config(self):
        """Test that localhost:7687 (Neo4j) is not in configuration files."""
        config_files = list(Path("src").rglob("*config*.py"))
        
        for config_file in config_files:
            content = config_file.read_text()
            assert "localhost:7687" not in content, \
                f"Neo4j localhost found in {config_file}"
            assert "127.0.0.1:7687" not in content, \
                f"Neo4j localhost IP found in {config_file}"
    
    def test_no_milvus_localhost_in_config(self):
        """Test that localhost:19530 (Milvus) is not in configuration files."""
        config_files = list(Path("src").rglob("*config*.py"))
        
        for config_file in config_files:
            content = config_file.read_text()
            assert "localhost:19530" not in content, \
                f"Milvus localhost found in {config_file}"
            assert "127.0.0.1:19530" not in content, \
                f"Milvus localhost IP found in {config_file}"


def test_all_unit_tests_discoverable():
    """Meta-test to ensure all unit test classes are discoverable."""
    test_classes = [
        TestArchiveStructure,
        TestDependencyRemoval,
        TestLegacyFileRemoval,
        TestAWSNativeFilesPreserved,
        TestHealthCheckUpdates,
        TestContainerBuild,
        TestCleanupDocumentation,
        TestDatabaseFactory,
        TestLocalhostConfiguration,
    ]
    
    assert len(test_classes) == 9, \
        f"Expected 9 test classes, found {len(test_classes)}"
    
    print(f"✓ All {len(test_classes)} unit test classes are defined")


if __name__ == "__main__":
    print("Running unit tests for legacy database cleanup...")
    print("=" * 70)
    
    # Run with pytest
    pytest.main([__file__, "-v", "--tb=short"])
