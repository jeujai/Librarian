#!/usr/bin/env python3
"""
Neo4j Optimization Validation Script

This script validates that Neo4j performance optimizations are correctly
configured in the Docker Compose file and configuration files.
"""

import yaml
import os
import sys
from pathlib import Path


def validate_docker_compose_config():
    """Validate Neo4j configuration in Docker Compose file."""
    print("🔍 Validating Docker Compose Neo4j configuration...")
    
    compose_file = Path("docker-compose.local.yml")
    if not compose_file.exists():
        print(f"❌ Docker Compose file not found: {compose_file}")
        return False
    
    try:
        with open(compose_file, 'r') as f:
            compose_config = yaml.safe_load(f)
        
        neo4j_service = compose_config.get('services', {}).get('neo4j', {})
        if not neo4j_service:
            print("❌ Neo4j service not found in Docker Compose")
            return False
        
        environment = neo4j_service.get('environment', [])
        env_dict = {}
        
        # Convert environment list to dictionary
        for env_var in environment:
            if isinstance(env_var, str) and '=' in env_var:
                key, value = env_var.split('=', 1)
                env_dict[key.strip('- ')] = value
        
        # Validate memory settings
        memory_checks = [
            ('NEO4J_server_memory_heap_initial__size', '512m'),
            ('NEO4J_server_memory_heap_max__size', '1G'),
            ('NEO4J_server_memory_pagecache_size', '512m'),
            ('NEO4J_server_memory_off__heap_max__size', '256m'),
        ]
        
        print("   Memory Configuration:")
        for env_key, expected_value in memory_checks:
            actual_value = env_dict.get(env_key)
            if actual_value == expected_value:
                print(f"   ✅ {env_key}: {actual_value}")
            else:
                print(f"   ❌ {env_key}: expected {expected_value}, got {actual_value}")
                return False
        
        # Validate performance settings
        performance_checks = [
            ('NEO4J_dbms_query__cache__size', '1000'),
            ('NEO4J_cypher_default__language__version', '5'),
            ('NEO4J_cypher_lenient__create__relationship', 'true'),
        ]
        
        print("   Performance Configuration:")
        for env_key, expected_value in performance_checks:
            actual_value = env_dict.get(env_key)
            if actual_value == expected_value:
                print(f"   ✅ {env_key}: {actual_value}")
            else:
                print(f"   ❌ {env_key}: expected {expected_value}, got {actual_value}")
                return False
        
        # Validate resource limits
        deploy_config = neo4j_service.get('deploy', {})
        resources = deploy_config.get('resources', {})
        limits = resources.get('limits', {})
        
        print("   Resource Limits:")
        if limits.get('memory') == '1.5G':
            print(f"   ✅ Memory limit: {limits.get('memory')}")
        else:
            print(f"   ❌ Memory limit: expected 1.5G, got {limits.get('memory')}")
            return False
        
        if limits.get('cpus') == '1.5':
            print(f"   ✅ CPU limit: {limits.get('cpus')}")
        else:
            print(f"   ❌ CPU limit: expected 1.5, got {limits.get('cpus')}")
            return False
        
        # Validate health check
        healthcheck = neo4j_service.get('healthcheck', {})
        if healthcheck.get('interval') == '30s':
            print(f"   ✅ Health check interval: {healthcheck.get('interval')}")
        else:
            print(f"   ❌ Health check interval: expected 30s, got {healthcheck.get('interval')}")
            return False
        
        return True
        
    except Exception as e:
        print(f"❌ Error reading Docker Compose file: {e}")
        return False


def validate_neo4j_config_file():
    """Validate Neo4j configuration file."""
    print("\n🔍 Validating Neo4j configuration file...")
    
    config_file = Path("database/neo4j/neo4j.conf")
    if not config_file.exists():
        print(f"❌ Neo4j config file not found: {config_file}")
        return False
    
    try:
        with open(config_file, 'r') as f:
            config_content = f.read()
        
        # Check for key configuration settings
        config_checks = [
            ('server.memory.heap.initial_size=512m', 'Initial heap size'),
            ('server.memory.heap.max_size=1G', 'Maximum heap size'),
            ('server.memory.pagecache.size=512m', 'Page cache size'),
            ('server.memory.off_heap.max_size=256m', 'Off-heap memory limit'),
            ('dbms.query_cache_size=1000', 'Query cache size'),
            ('cypher.default_language_version=5', 'Cypher version'),
            ('cypher.runtime=parallel', 'Parallel runtime'),
            ('cypher.planner=cost', 'Cost-based planner'),
            ('dbms.usage_report.enabled=false', 'Usage reporting disabled'),
            ('dbms.logs.query.enabled=false', 'Query logging disabled'),
        ]
        
        print("   Configuration Settings:")
        for setting, description in config_checks:
            if setting in config_content:
                print(f"   ✅ {description}: {setting}")
            else:
                print(f"   ❌ {description}: {setting} not found")
                return False
        
        return True
        
    except Exception as e:
        print(f"❌ Error reading Neo4j config file: {e}")
        return False


def validate_file_structure():
    """Validate that required files exist."""
    print("\n🔍 Validating file structure...")
    
    required_files = [
        "docker-compose.local.yml",
        "database/neo4j/neo4j.conf",
        "scripts/monitor-neo4j-performance.py",
        "tests/performance/test_neo4j_performance_optimization.py",
        "docs/neo4j-performance-optimization-guide.md",
    ]
    
    all_exist = True
    for file_path in required_files:
        if Path(file_path).exists():
            print(f"   ✅ {file_path}")
        else:
            print(f"   ❌ {file_path} not found")
            all_exist = False
    
    return all_exist


def validate_documentation():
    """Validate that documentation is comprehensive."""
    print("\n🔍 Validating documentation...")
    
    doc_file = Path("docs/neo4j-performance-optimization-guide.md")
    if not doc_file.exists():
        print(f"❌ Documentation file not found: {doc_file}")
        return False
    
    try:
        with open(doc_file, 'r') as f:
            doc_content = f.read()
        
        # Check for key documentation sections
        doc_sections = [
            "Memory Optimization",
            "Query Performance Optimization",
            "Transaction Optimization",
            "Development-Specific Optimizations",
            "Performance Monitoring",
            "Performance Validation",
            "Troubleshooting",
        ]
        
        print("   Documentation Sections:")
        for section in doc_sections:
            if section in doc_content:
                print(f"   ✅ {section}")
            else:
                print(f"   ❌ {section} section missing")
                return False
        
        return True
        
    except Exception as e:
        print(f"❌ Error reading documentation: {e}")
        return False


def main():
    """Main validation function."""
    print("🚀 Neo4j Performance Optimization Validation")
    print("=" * 60)
    
    validations = [
        ("Docker Compose Configuration", validate_docker_compose_config),
        ("Neo4j Configuration File", validate_neo4j_config_file),
        ("File Structure", validate_file_structure),
        ("Documentation", validate_documentation),
    ]
    
    all_passed = True
    results = []
    
    for name, validation_func in validations:
        try:
            result = validation_func()
            results.append((name, result))
            if not result:
                all_passed = False
        except Exception as e:
            print(f"❌ Error in {name} validation: {e}")
            results.append((name, False))
            all_passed = False
    
    # Summary
    print("\n" + "=" * 60)
    print("📊 VALIDATION SUMMARY")
    print("=" * 60)
    
    for name, result in results:
        status = "✅ PASSED" if result else "❌ FAILED"
        print(f"{name}: {status}")
    
    if all_passed:
        print("\n🎉 All validations passed! Neo4j optimization is correctly configured.")
        print("\nNext steps:")
        print("1. Start the services: docker compose -f docker-compose.local.yml up -d")
        print("2. Monitor performance: python scripts/monitor-neo4j-performance.py")
        print("3. Run performance tests: pytest tests/performance/test_neo4j_performance_optimization.py")
        return 0
    else:
        print("\n❌ Some validations failed. Please review the configuration.")
        return 1


if __name__ == "__main__":
    sys.exit(main())