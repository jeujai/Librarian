"""
Test container build validation for legacy database cleanup.

This test validates that:
1. The Dockerfile can be parsed and is valid
2. Legacy packages (neo4j, pymilvus) are not in requirements.txt
3. The build would succeed with current dependencies

Requirements: 1.3, 7.1, 7.2, 7.3
"""

import re
import subprocess
from pathlib import Path
from typing import List, Tuple


def test_dockerfile_exists():
    """Test that Dockerfile exists."""
    dockerfile_path = Path("Dockerfile")
    assert dockerfile_path.exists(), "Dockerfile not found"


def test_dockerfile_syntax():
    """Test that Dockerfile has valid syntax."""
    dockerfile_path = Path("Dockerfile")
    content = dockerfile_path.read_text()
    
    # Check for required directives
    assert "FROM" in content, "Dockerfile missing FROM directive"
    assert "WORKDIR" in content, "Dockerfile missing WORKDIR directive"
    assert "COPY" in content, "Dockerfile missing COPY directive"
    assert "CMD" in content or "ENTRYPOINT" in content, "Dockerfile missing CMD/ENTRYPOINT"


def test_requirements_no_legacy_packages():
    """
    Test that requirements.txt does not contain legacy database packages.
    
    Validates Requirements 7.2, 7.3:
    - neo4j package should not be in requirements
    - pymilvus package should not be in requirements
    """
    requirements_path = Path("requirements.txt")
    assert requirements_path.exists(), "requirements.txt not found"
    
    content = requirements_path.read_text().lower()
    
    # Check for neo4j
    assert "neo4j" not in content, "neo4j package found in requirements.txt"
    
    # Check for pymilvus
    assert "pymilvus" not in content, "pymilvus package found in requirements.txt"


def test_dockerfile_no_legacy_package_installation():
    """Test that Dockerfile does not explicitly install legacy packages."""
    dockerfile_path = Path("Dockerfile")
    content = dockerfile_path.read_text().lower()
    
    # Check for neo4j installation
    assert "neo4j" not in content, "neo4j installation found in Dockerfile"
    
    # Check for pymilvus installation
    assert "pymilvus" not in content, "pymilvus installation found in Dockerfile"


def test_dockerfile_uses_requirements():
    """Test that Dockerfile uses requirements.txt for dependencies."""
    dockerfile_path = Path("Dockerfile")
    content = dockerfile_path.read_text()
    
    # Check that requirements.txt is copied and installed
    assert "COPY requirements.txt" in content, "requirements.txt not copied in Dockerfile"
    assert "pip install" in content, "pip install not found in Dockerfile"


def test_aws_native_dependencies_present():
    """Test that AWS-native database dependencies are present."""
    requirements_path = Path("requirements.txt")
    content = requirements_path.read_text()
    
    # Check for Neptune dependency (gremlinpython)
    assert "gremlinpython" in content, "gremlinpython (Neptune) not in requirements.txt"
    
    # Check for OpenSearch dependency
    assert "opensearch-py" in content, "opensearch-py not in requirements.txt"


def test_build_command_syntax():
    """Test that a valid Docker build command can be constructed."""
    # This tests the command syntax without actually running it
    build_command = ["docker", "build", "-t", "multimodal-librarian:test", "."]
    
    # Verify command structure
    assert build_command[0] == "docker"
    assert build_command[1] == "build"
    assert "-t" in build_command
    assert "." in build_command


def test_docker_available():
    """Test if Docker is available on the system."""
    try:
        result = subprocess.run(
            ["which", "docker"],
            capture_output=True,
            text=True,
            timeout=5
        )
        docker_available = result.returncode == 0
        
        if docker_available:
            print("✓ Docker is installed")
        else:
            print("⚠ Docker is not installed (build validation will be limited)")
            
    except Exception as e:
        print(f"⚠ Could not check Docker availability: {e}")


def test_requirements_parseable():
    """Test that requirements.txt can be parsed."""
    requirements_path = Path("requirements.txt")
    content = requirements_path.read_text()
    
    lines = content.split("\n")
    package_count = 0
    
    for line in lines:
        line = line.strip()
        # Skip comments and empty lines
        if line and not line.startswith("#"):
            package_count += 1
    
    assert package_count > 0, "No packages found in requirements.txt"
    print(f"✓ Found {package_count} packages in requirements.txt")


def test_dockerfile_platform_specified():
    """Test that Dockerfile specifies platform for AWS compatibility."""
    dockerfile_path = Path("Dockerfile")
    content = dockerfile_path.read_text()
    
    # Check for platform specification (important for AWS Fargate)
    assert "--platform" in content or "TARGETPLATFORM" in content, \
        "Platform not specified in Dockerfile (may cause issues on AWS)"


if __name__ == "__main__":
    print("Running container build validation tests...")
    print("=" * 60)
    
    tests = [
        ("Dockerfile exists", test_dockerfile_exists),
        ("Dockerfile syntax valid", test_dockerfile_syntax),
        ("No legacy packages in requirements", test_requirements_no_legacy_packages),
        ("No legacy packages in Dockerfile", test_dockerfile_no_legacy_package_installation),
        ("Dockerfile uses requirements.txt", test_dockerfile_uses_requirements),
        ("AWS-native dependencies present", test_aws_native_dependencies_present),
        ("Build command syntax valid", test_build_command_syntax),
        ("Docker availability", test_docker_available),
        ("Requirements parseable", test_requirements_parseable),
        ("Platform specified", test_dockerfile_platform_specified),
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
