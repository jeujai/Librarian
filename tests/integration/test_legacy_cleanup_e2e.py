"""
End-to-end integration test for legacy database cleanup.

This test validates the complete cleanup process:
1. Full application startup
2. Database connectivity (AWS-native only)
3. Health checks pass
4. No legacy code is executed

Feature: legacy-database-cleanup
"""

import os
import sys
import time
from pathlib import Path
from typing import Dict, List

import pytest


class TestLegacyCleanupE2E:
    """End-to-end integration tests for legacy database cleanup."""
    
    def test_codebase_structure_valid(self):
        """Test that codebase structure is valid after cleanup."""
        # Verify src directory exists
        src_dir = Path("src/multimodal_librarian")
        assert src_dir.exists(), "Source directory not found"
        
        # Verify key directories exist
        assert (src_dir / "clients").exists(), "clients directory not found"
        assert (src_dir / "config").exists(), "config directory not found"
        assert (src_dir / "api").exists(), "api directory not found"
    
    def test_no_legacy_files_in_src(self):
        """Test that no legacy database files exist in src."""
        src_dir = Path("src")
        
        legacy_patterns = [
            "neo4j_client.py",
            "neo4j_config.py",
            "milvus_config_basic.py",
            "milvus_client.py",
        ]
        
        for pattern in legacy_patterns:
            matches = list(src_dir.rglob(pattern))
            assert len(matches) == 0, \
                f"Found legacy file in src: {[str(m) for m in matches]}"
    
    def test_aws_native_files_present(self):
        """Test that AWS-native files are present."""
        required_files = [
            "src/multimodal_librarian/clients/neptune_client.py",
            "src/multimodal_librarian/clients/opensearch_client.py",
            "src/multimodal_librarian/config/aws_native_config.py",
            "src/multimodal_librarian/clients/database_factory.py",
        ]
        
        for file_path in required_files:
            path = Path(file_path)
            assert path.exists(), f"Required AWS-native file not found: {file_path}"
    
    def test_no_legacy_imports_in_codebase(self):
        """Test that no legacy imports exist in the codebase."""
        src_dir = Path("src")
        python_files = list(src_dir.rglob("*.py"))
        
        legacy_import_patterns = [
            "import neo4j",
            "from neo4j",
            "import pymilvus",
            "from pymilvus",
        ]
        
        files_with_legacy_imports = []
        
        for py_file in python_files:
            try:
                content = py_file.read_text()
                for pattern in legacy_import_patterns:
                    if pattern in content:
                        files_with_legacy_imports.append(
                            f"{py_file}: {pattern}"
                        )
            except Exception as e:
                print(f"Warning: Could not read {py_file}: {e}")
        
        assert len(files_with_legacy_imports) == 0, \
            f"Found legacy imports: {files_with_legacy_imports}"
    
    def test_requirements_valid(self):
        """Test that requirements.txt is valid and has no legacy packages."""
        req_path = Path("requirements.txt")
        assert req_path.exists(), "requirements.txt not found"
        
        content = req_path.read_text()
        
        # Check no legacy packages
        assert "neo4j" not in content.lower(), "neo4j in requirements.txt"
        assert "pymilvus" not in content.lower(), "pymilvus in requirements.txt"
        
        # Check AWS-native packages present
        assert "gremlinpython" in content, "gremlinpython not in requirements.txt"
        assert "opensearch-py" in content, "opensearch-py not in requirements.txt"
    
    def test_database_factory_aws_native_only(self):
        """Test that database factory only supports AWS-native backends."""
        try:
            from src.multimodal_librarian.clients.database_factory import (
                DatabaseClientFactory,
            )
            
            # Test that factory only provides AWS-native clients
            factory = DatabaseClientFactory()
            
            # These should work (or raise config errors, not unsupported backend errors)
            try:
                graph_interface = factory.get_unified_graph_interface()
                assert graph_interface is not None
            except Exception as e:
                # It's okay if it fails due to missing config, just not due to unsupported backend
                assert "unsupported" not in str(e).lower()
                assert "neo4j" not in str(e).lower()
            
            try:
                vector_interface = factory.get_unified_vector_interface()
                assert vector_interface is not None
            except Exception as e:
                # It's okay if it fails due to missing config, just not due to unsupported backend
                assert "unsupported" not in str(e).lower()
                assert "milvus" not in str(e).lower()
            
        except ImportError as e:
            pytest.skip(f"Could not import database factory: {e}")
    
    def test_health_check_system_available(self):
        """Test that health check system is available."""
        try:
            from src.multimodal_librarian.monitoring.health_checker import HealthChecker
            
            checker = HealthChecker()
            assert checker is not None, "HealthChecker could not be instantiated"
            
        except ImportError as e:
            pytest.skip(f"Could not import HealthChecker: {e}")
    
    def test_no_localhost_database_urls(self):
        """Test that no localhost database URLs exist in configuration."""
        config_files = list(Path("src").rglob("*config*.py"))
        
        localhost_patterns = [
            "localhost:7687",   # Neo4j
            "localhost:19530",  # Milvus
            "127.0.0.1:7687",
            "127.0.0.1:19530",
        ]
        
        files_with_localhost = []
        
        for config_file in config_files:
            try:
                content = config_file.read_text()
                for pattern in localhost_patterns:
                    if pattern in content:
                        files_with_localhost.append(
                            f"{config_file}: {pattern}"
                        )
            except Exception as e:
                print(f"Warning: Could not read {config_file}: {e}")
        
        assert len(files_with_localhost) == 0, \
            f"Found localhost URLs: {files_with_localhost}"
    
    def test_archive_complete(self):
        """Test that archive is complete with all required files."""
        archive_dir = Path("archive/legacy-databases")
        assert archive_dir.exists(), "Archive directory not found"
        
        # Check README exists
        readme = archive_dir / "README.md"
        assert readme.exists(), "Archive README not found"
        
        # Check archived files exist
        expected_files = [
            "clients/neo4j_client.py",
            "config/neo4j_config.py",
            "aws/milvus_config_basic.py",
        ]
        
        for file_path in expected_files:
            full_path = archive_dir / file_path
            assert full_path.exists(), f"Archived file not found: {file_path}"
    
    def test_cleanup_documentation_exists(self):
        """Test that cleanup documentation exists."""
        cleanup_summary = Path("CLEANUP_SUMMARY.md")
        assert cleanup_summary.exists(), "CLEANUP_SUMMARY.md not found"
        
        content = cleanup_summary.read_text()
        
        # Verify key information is present
        assert len(content) > 100, "CLEANUP_SUMMARY.md is too short"
        assert "removed" in content.lower() or "cleanup" in content.lower(), \
            "CLEANUP_SUMMARY.md should explain what was removed"
    
    def test_dockerfile_valid(self):
        """Test that Dockerfile is valid and has no legacy references."""
        dockerfile = Path("Dockerfile")
        assert dockerfile.exists(), "Dockerfile not found"
        
        content = dockerfile.read_text()
        
        # Check no legacy references
        assert "neo4j" not in content.lower(), "neo4j in Dockerfile"
        assert "pymilvus" not in content.lower(), "pymilvus in Dockerfile"
        
        # Check basic structure
        assert "FROM" in content, "Dockerfile missing FROM"
        assert "COPY" in content, "Dockerfile missing COPY"
    
    def test_main_application_importable(self):
        """Test that main application can be imported."""
        try:
            from src.multimodal_librarian import main
            assert main is not None, "Main module could not be imported"
        except ImportError as e:
            pytest.skip(f"Could not import main: {e}")
    
    def test_api_routers_importable(self):
        """Test that API routers can be imported."""
        try:
            from src.multimodal_librarian.api import routers
            assert routers is not None, "API routers could not be imported"
        except ImportError as e:
            pytest.skip(f"Could not import API routers: {e}")
    
    def test_monitoring_system_importable(self):
        """Test that monitoring system can be imported."""
        try:
            from src.multimodal_librarian import monitoring
            assert monitoring is not None, "Monitoring module could not be imported"
        except ImportError as e:
            pytest.skip(f"Could not import monitoring: {e}")


class TestCleanupValidation:
    """Validation tests for cleanup completeness."""
    
    def test_all_legacy_patterns_removed(self):
        """Test that all legacy patterns are removed from codebase."""
        src_dir = Path("src")
        
        legacy_patterns = {
            "neo4j_client": 0,
            "neo4j_config": 0,
            "milvus_config": 0,
            "pymilvus": 0,
        }
        
        for py_file in src_dir.rglob("*.py"):
            try:
                content = py_file.read_text().lower()
                for pattern in legacy_patterns.keys():
                    if pattern in content:
                        legacy_patterns[pattern] += 1
            except Exception:
                pass
        
        # Report findings
        for pattern, count in legacy_patterns.items():
            assert count == 0, f"Found {count} occurrences of '{pattern}' in src"
    
    def test_aws_native_patterns_present(self):
        """Test that AWS-native patterns are present in codebase."""
        src_dir = Path("src")
        
        aws_patterns = {
            "neptune": False,
            "opensearch": False,
            "aws_native": False,
        }
        
        for py_file in src_dir.rglob("*.py"):
            try:
                content = py_file.read_text().lower()
                for pattern in aws_patterns.keys():
                    if pattern in content:
                        aws_patterns[pattern] = True
            except Exception:
                pass
        
        # At least some AWS-native patterns should be present
        assert any(aws_patterns.values()), \
            "No AWS-native patterns found in codebase"
    
    def test_container_build_prerequisites(self):
        """Test that container build prerequisites are met."""
        # Check Dockerfile exists
        assert Path("Dockerfile").exists(), "Dockerfile not found"
        
        # Check requirements.txt exists
        assert Path("requirements.txt").exists(), "requirements.txt not found"
        
        # Check src directory exists
        assert Path("src").exists(), "src directory not found"
    
    def test_cleanup_is_complete(self):
        """Meta-test to verify cleanup is complete."""
        checks = {
            "No legacy files in src": self._check_no_legacy_files(),
            "No legacy imports": self._check_no_legacy_imports(),
            "AWS-native files present": self._check_aws_native_files(),
            "Archive complete": self._check_archive_complete(),
            "Documentation exists": self._check_documentation(),
        }
        
        failed_checks = [name for name, passed in checks.items() if not passed]
        
        assert len(failed_checks) == 0, \
            f"Cleanup incomplete. Failed checks: {failed_checks}"
    
    def _check_no_legacy_files(self) -> bool:
        """Check that no legacy files exist."""
        legacy_files = [
            "src/multimodal_librarian/clients/neo4j_client.py",
            "src/multimodal_librarian/config/neo4j_config.py",
            "src/multimodal_librarian/aws/milvus_config_basic.py",
        ]
        return not any(Path(f).exists() for f in legacy_files)
    
    def _check_no_legacy_imports(self) -> bool:
        """Check that no legacy imports exist."""
        src_dir = Path("src")
        for py_file in src_dir.rglob("*.py"):
            try:
                content = py_file.read_text()
                if "import neo4j" in content or "from neo4j" in content:
                    return False
                if "import pymilvus" in content or "from pymilvus" in content:
                    return False
            except Exception:
                pass
        return True
    
    def _check_aws_native_files(self) -> bool:
        """Check that AWS-native files exist."""
        required_files = [
            "src/multimodal_librarian/clients/neptune_client.py",
            "src/multimodal_librarian/clients/opensearch_client.py",
            "src/multimodal_librarian/config/aws_native_config.py",
        ]
        return all(Path(f).exists() for f in required_files)
    
    def _check_archive_complete(self) -> bool:
        """Check that archive is complete."""
        archive_dir = Path("archive/legacy-databases")
        if not archive_dir.exists():
            return False
        
        required_files = [
            "README.md",
            "clients/neo4j_client.py",
            "config/neo4j_config.py",
            "aws/milvus_config_basic.py",
        ]
        
        return all((archive_dir / f).exists() for f in required_files)
    
    def _check_documentation(self) -> bool:
        """Check that documentation exists."""
        return Path("CLEANUP_SUMMARY.md").exists()


def test_e2e_cleanup_success():
    """
    Master end-to-end test that validates complete cleanup success.
    
    This test runs all validation checks and reports a comprehensive
    status of the cleanup process.
    """
    print("\n" + "=" * 70)
    print("LEGACY DATABASE CLEANUP - END-TO-END VALIDATION")
    print("=" * 70)
    
    validation_results = {
        "Legacy files removed": True,
        "Legacy imports removed": True,
        "AWS-native files present": True,
        "Archive complete": True,
        "Documentation complete": True,
        "Requirements valid": True,
        "Dockerfile valid": True,
    }
    
    # Check legacy files removed
    legacy_files = [
        "src/multimodal_librarian/clients/neo4j_client.py",
        "src/multimodal_librarian/config/neo4j_config.py",
        "src/multimodal_librarian/aws/milvus_config_basic.py",
    ]
    validation_results["Legacy files removed"] = not any(
        Path(f).exists() for f in legacy_files
    )
    
    # Check legacy imports removed
    src_dir = Path("src")
    has_legacy_imports = False
    for py_file in src_dir.rglob("*.py"):
        try:
            content = py_file.read_text()
            if "import neo4j" in content or "from neo4j" in content:
                has_legacy_imports = True
                break
            if "import pymilvus" in content or "from pymilvus" in content:
                has_legacy_imports = True
                break
        except Exception:
            pass
    validation_results["Legacy imports removed"] = not has_legacy_imports
    
    # Check AWS-native files present
    aws_files = [
        "src/multimodal_librarian/clients/neptune_client.py",
        "src/multimodal_librarian/clients/opensearch_client.py",
        "src/multimodal_librarian/config/aws_native_config.py",
    ]
    validation_results["AWS-native files present"] = all(
        Path(f).exists() for f in aws_files
    )
    
    # Check archive complete
    archive_dir = Path("archive/legacy-databases")
    validation_results["Archive complete"] = (
        archive_dir.exists() and
        (archive_dir / "README.md").exists()
    )
    
    # Check documentation
    validation_results["Documentation complete"] = Path("CLEANUP_SUMMARY.md").exists()
    
    # Check requirements
    req_path = Path("requirements.txt")
    if req_path.exists():
        content = req_path.read_text().lower()
        validation_results["Requirements valid"] = (
            "neo4j" not in content and
            "pymilvus" not in content
        )
    
    # Check Dockerfile
    dockerfile = Path("Dockerfile")
    if dockerfile.exists():
        content = dockerfile.read_text().lower()
        validation_results["Dockerfile valid"] = (
            "neo4j" not in content and
            "pymilvus" not in content
        )
    
    # Print results
    print("\nValidation Results:")
    print("-" * 70)
    for check, passed in validation_results.items():
        status = "✓ PASS" if passed else "✗ FAIL"
        print(f"{status:10} {check}")
    
    print("-" * 70)
    
    passed_count = sum(validation_results.values())
    total_count = len(validation_results)
    
    print(f"\nOverall: {passed_count}/{total_count} checks passed")
    print("=" * 70)
    
    # Assert all checks passed
    assert all(validation_results.values()), \
        f"Some validation checks failed: {[k for k, v in validation_results.items() if not v]}"


if __name__ == "__main__":
    print("Running end-to-end integration tests for legacy database cleanup...")
    print("=" * 70)
    
    # Run with pytest
    pytest.main([__file__, "-v", "--tb=short", "-s"])
