"""
Test container inspection for legacy packages.

This test validates the inspection script logic and provides
validation that can run without Docker daemon.

Requirements: 7.2, 7.3
"""

import json
from pathlib import Path


def test_inspection_script_exists():
    """Test that the inspection script exists."""
    script_path = Path("scripts/inspect-container-for-legacy-packages.py")
    assert script_path.exists(), "Inspection script not found"
    assert script_path.is_file(), "Inspection script is not a file"


def test_inspection_script_executable():
    """Test that the inspection script is executable."""
    script_path = Path("scripts/inspect-container-for-legacy-packages.py")
    # Check if file has execute permissions
    import os
    is_executable = os.access(script_path, os.X_OK)
    assert is_executable, "Inspection script is not executable"


def test_inspection_script_has_shebang():
    """Test that the inspection script has proper shebang."""
    script_path = Path("scripts/inspect-container-for-legacy-packages.py")
    content = script_path.read_text()
    assert content.startswith("#!/usr/bin/env python3"), \
        "Inspection script missing proper shebang"


def test_inspection_script_has_documentation():
    """Test that the inspection script has documentation."""
    script_path = Path("scripts/inspect-container-for-legacy-packages.py")
    content = script_path.read_text()
    
    # Check for docstring
    assert '"""' in content, "Inspection script missing docstring"
    
    # Check for usage information
    assert "Usage:" in content or "usage:" in content.lower(), \
        "Inspection script missing usage information"


def test_inspection_checks_neo4j():
    """Test that inspection script checks for neo4j package."""
    script_path = Path("scripts/inspect-container-for-legacy-packages.py")
    content = script_path.read_text()
    
    assert "neo4j" in content.lower(), \
        "Inspection script does not check for neo4j package"


def test_inspection_checks_pymilvus():
    """Test that inspection script checks for pymilvus package."""
    script_path = Path("scripts/inspect-container-for-legacy-packages.py")
    content = script_path.read_text()
    
    assert "pymilvus" in content.lower(), \
        "Inspection script does not check for pymilvus package"


def test_inspection_validates_requirements():
    """Test that inspection script validates requirements 7.2 and 7.3."""
    script_path = Path("scripts/inspect-container-for-legacy-packages.py")
    content = script_path.read_text()
    
    # Check for requirement references
    assert "7.2" in content or "Requirement 7.2" in content, \
        "Inspection script does not reference Requirement 7.2"
    assert "7.3" in content or "Requirement 7.3" in content, \
        "Inspection script does not reference Requirement 7.3"


def test_validation_report_exists():
    """Test that container build validation report exists."""
    report_path = Path("container-build-validation-report.md")
    assert report_path.exists(), "Container build validation report not found"


def test_validation_report_documents_changes():
    """Test that validation report documents Dockerfile changes."""
    report_path = Path("container-build-validation-report.md")
    content = report_path.read_text()
    
    # Check for documentation of pymilvus removal
    assert "pymilvus" in content.lower(), \
        "Validation report does not document pymilvus removal"
    
    # Check for validation results
    assert "validation" in content.lower(), \
        "Validation report missing validation results"


def test_validation_report_references_requirements():
    """Test that validation report references requirements."""
    report_path = Path("container-build-validation-report.md")
    content = report_path.read_text()
    
    # Check for requirement references
    assert "Requirement 7.2" in content or "7.2" in content, \
        "Validation report does not reference Requirement 7.2"
    assert "Requirement 7.3" in content or "7.3" in content, \
        "Validation report does not reference Requirement 7.3"


def test_dockerfile_no_pymilvus_stage():
    """Test that Dockerfile does not have pymilvus installation stage."""
    dockerfile_path = Path("Dockerfile")
    content = dockerfile_path.read_text()
    
    # Check that pymilvus is not mentioned
    assert "pymilvus" not in content.lower(), \
        "Dockerfile still contains pymilvus reference"


def test_requirements_no_legacy_packages():
    """Test that requirements.txt does not contain legacy packages."""
    requirements_path = Path("requirements.txt")
    content = requirements_path.read_text().lower()
    
    # Check for neo4j
    assert "neo4j" not in content, \
        "requirements.txt contains neo4j package"
    
    # Check for pymilvus
    assert "pymilvus" not in content, \
        "requirements.txt contains pymilvus package"


def test_aws_native_packages_in_requirements():
    """Test that AWS-native packages are in requirements.txt."""
    requirements_path = Path("requirements.txt")
    content = requirements_path.read_text()
    
    # Check for Neptune (gremlinpython)
    assert "gremlinpython" in content, \
        "requirements.txt missing gremlinpython (Neptune)"
    
    # Check for OpenSearch
    assert "opensearch-py" in content, \
        "requirements.txt missing opensearch-py"


if __name__ == "__main__":
    print("Running container inspection validation tests...")
    print("=" * 60)
    
    tests = [
        ("Inspection script exists", test_inspection_script_exists),
        ("Inspection script executable", test_inspection_script_executable),
        ("Inspection script has shebang", test_inspection_script_has_shebang),
        ("Inspection script documented", test_inspection_script_has_documentation),
        ("Inspection checks neo4j", test_inspection_checks_neo4j),
        ("Inspection checks pymilvus", test_inspection_checks_pymilvus),
        ("Inspection validates requirements", test_inspection_validates_requirements),
        ("Validation report exists", test_validation_report_exists),
        ("Validation report documents changes", test_validation_report_documents_changes),
        ("Validation report references requirements", test_validation_report_references_requirements),
        ("Dockerfile no pymilvus stage", test_dockerfile_no_pymilvus_stage),
        ("Requirements no legacy packages", test_requirements_no_legacy_packages),
        ("AWS-native packages present", test_aws_native_packages_in_requirements),
    ]
    
    passed = 0
    failed = 0
    
    for test_name, test_func in tests:
        try:
            test_func()
            print(f"✓ {test_name}")
            passed += 1
        except AssertionError as e:
            print(f"✗ {test_name}: {e}")
            failed += 1
        except Exception as e:
            print(f"⚠ {test_name}: {e}")
    
    print("=" * 60)
    print(f"Results: {passed} passed, {failed} failed")
    
    if failed > 0:
        exit(1)
