#!/usr/bin/env python3
"""
Inspect container image for legacy database packages.

This script inspects a Docker container image to verify that
legacy database packages (neo4j, pymilvus) are not present.

Requirements: 7.2, 7.3

Usage:
    python scripts/inspect-container-for-legacy-packages.py [image_name]
    
Example:
    python scripts/inspect-container-for-legacy-packages.py multimodal-librarian:legacy-cleanup
"""

import subprocess
import sys
import json
from typing import List, Tuple, Dict


def run_command(cmd: List[str]) -> Tuple[int, str, str]:
    """Run a shell command and return exit code, stdout, stderr."""
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=60
        )
        return result.returncode, result.stdout, result.stderr
    except subprocess.TimeoutExpired:
        return -1, "", "Command timed out"
    except Exception as e:
        return -1, "", str(e)


def check_docker_available() -> bool:
    """Check if Docker is available."""
    code, stdout, stderr = run_command(["docker", "version"])
    return code == 0


def check_image_exists(image_name: str) -> bool:
    """Check if the Docker image exists."""
    code, stdout, stderr = run_command(["docker", "images", "-q", image_name])
    return code == 0 and stdout.strip() != ""


def get_installed_packages(image_name: str) -> Tuple[bool, List[str]]:
    """Get list of installed Python packages in the container."""
    code, stdout, stderr = run_command([
        "docker", "run", "--rm", image_name,
        "pip", "list", "--format=json"
    ])
    
    if code != 0:
        print(f"Error getting package list: {stderr}")
        return False, []
    
    try:
        packages = json.loads(stdout)
        return True, [pkg["name"].lower() for pkg in packages]
    except json.JSONDecodeError:
        # Fallback to plain text parsing
        lines = stdout.strip().split("\n")
        packages = []
        for line in lines[2:]:  # Skip header lines
            parts = line.split()
            if parts:
                packages.append(parts[0].lower())
        return True, packages


def check_package_not_present(image_name: str, package_name: str) -> Tuple[bool, str]:
    """
    Check that a specific package is not present in the container.
    
    Returns:
        (is_absent, message)
    """
    code, stdout, stderr = run_command([
        "docker", "run", "--rm", image_name,
        "pip", "show", package_name
    ])
    
    # If pip show returns non-zero, package is not installed (good!)
    if code != 0:
        return True, f"✓ {package_name} is NOT installed"
    else:
        return False, f"✗ {package_name} IS INSTALLED (should not be present)"


def get_image_size(image_name: str) -> str:
    """Get the size of the Docker image."""
    code, stdout, stderr = run_command([
        "docker", "images", image_name,
        "--format", "{{.Size}}"
    ])
    
    if code == 0:
        return stdout.strip()
    return "Unknown"


def inspect_container(image_name: str) -> Dict[str, any]:
    """
    Inspect container image for legacy packages.
    
    Returns a dictionary with inspection results.
    """
    results = {
        "image_name": image_name,
        "docker_available": False,
        "image_exists": False,
        "neo4j_absent": False,
        "pymilvus_absent": False,
        "image_size": "Unknown",
        "all_packages": [],
        "errors": []
    }
    
    # Check Docker availability
    if not check_docker_available():
        results["errors"].append("Docker is not available")
        return results
    
    results["docker_available"] = True
    
    # Check image exists
    if not check_image_exists(image_name):
        results["errors"].append(f"Image '{image_name}' does not exist")
        return results
    
    results["image_exists"] = True
    
    # Get image size
    results["image_size"] = get_image_size(image_name)
    
    # Check neo4j package
    neo4j_absent, neo4j_msg = check_package_not_present(image_name, "neo4j")
    results["neo4j_absent"] = neo4j_absent
    print(neo4j_msg)
    
    # Check pymilvus package
    pymilvus_absent, pymilvus_msg = check_package_not_present(image_name, "pymilvus")
    results["pymilvus_absent"] = pymilvus_absent
    print(pymilvus_msg)
    
    # Get all packages
    success, packages = get_installed_packages(image_name)
    if success:
        results["all_packages"] = packages
        
        # Double-check for legacy packages in full list
        if "neo4j" in packages:
            results["neo4j_absent"] = False
            results["errors"].append("neo4j found in package list")
        
        if "pymilvus" in packages:
            results["pymilvus_absent"] = False
            results["errors"].append("pymilvus found in package list")
    
    return results


def main():
    """Main function."""
    # Get image name from command line or use default
    if len(sys.argv) > 1:
        image_name = sys.argv[1]
    else:
        image_name = "multimodal-librarian:legacy-cleanup"
    
    print("=" * 70)
    print("Container Image Inspection for Legacy Packages")
    print("=" * 70)
    print(f"Image: {image_name}")
    print()
    
    # Run inspection
    results = inspect_container(image_name)
    
    # Print results
    print()
    print("=" * 70)
    print("Inspection Results")
    print("=" * 70)
    
    print(f"Docker Available: {'✓' if results['docker_available'] else '✗'}")
    print(f"Image Exists: {'✓' if results['image_exists'] else '✗'}")
    print(f"Image Size: {results['image_size']}")
    print()
    
    print("Legacy Package Checks:")
    print(f"  neo4j absent: {'✓' if results['neo4j_absent'] else '✗'}")
    print(f"  pymilvus absent: {'✓' if results['pymilvus_absent'] else '✗'}")
    print()
    
    if results["all_packages"]:
        print(f"Total packages installed: {len(results['all_packages'])}")
        
        # Check for AWS-native packages
        aws_packages = [
            pkg for pkg in results["all_packages"]
            if "gremlin" in pkg or "opensearch" in pkg or "boto" in pkg
        ]
        if aws_packages:
            print(f"AWS-native packages found: {', '.join(aws_packages)}")
    
    if results["errors"]:
        print()
        print("Errors:")
        for error in results["errors"]:
            print(f"  ✗ {error}")
    
    print()
    print("=" * 70)
    
    # Determine overall success
    if not results["docker_available"]:
        print("⚠ Docker not available - cannot inspect image")
        print("   Run this script when Docker daemon is running")
        return 2
    
    if not results["image_exists"]:
        print(f"⚠ Image '{image_name}' not found")
        print("   Build the image first with:")
        print(f"   docker build -t {image_name} .")
        return 2
    
    if results["neo4j_absent"] and results["pymilvus_absent"]:
        print("✓ SUCCESS: No legacy database packages found in container")
        print()
        print("Requirements Validated:")
        print("  ✓ Requirement 7.2: neo4j package not in image")
        print("  ✓ Requirement 7.3: pymilvus package not in image")
        return 0
    else:
        print("✗ FAILURE: Legacy database packages found in container")
        if not results["neo4j_absent"]:
            print("  ✗ neo4j package is present (should be removed)")
        if not results["pymilvus_absent"]:
            print("  ✗ pymilvus package is present (should be removed)")
        return 1


if __name__ == "__main__":
    sys.exit(main())
