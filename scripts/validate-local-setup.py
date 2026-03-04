#!/usr/bin/env python3
"""
Local Development Setup Validation Script

This script validates the local development setup configuration.
"""

import os
import sys
import yaml
from pathlib import Path


def validate_docker_compose():
    """Validate docker-compose.local.yml configuration."""
    print("🔍 Validating docker-compose.local.yml...")
    
    compose_file = Path("docker-compose.local.yml")
    if not compose_file.exists():
        print("❌ docker-compose.local.yml not found")
        return False
    
    try:
        with open(compose_file) as f:
            config = yaml.safe_load(f)
        
        # Check required services
        required_services = [
            "multimodal-librarian",
            "postgres", 
            "neo4j",
            "milvus",
            "etcd",
            "minio",
            "redis"
        ]
        
        services = config.get("services", {})
        missing_services = [svc for svc in required_services if svc not in services]
        
        if missing_services:
            print(f"❌ Missing required services: {missing_services}")
            return False
        
        # Check volumes
        required_volumes = [
            "postgres_data",
            "neo4j_data", 
            "milvus_data",
            "etcd_data",
            "minio_data",
            "redis_data"
        ]
        
        volumes = config.get("volumes", {})
        missing_volumes = [vol for vol in required_volumes if vol not in volumes]
        
        if missing_volumes:
            print(f"❌ Missing required volumes: {missing_volumes}")
            return False
        
        # Check networks
        if "networks" not in config:
            print("❌ No networks defined")
            return False
        
        print("✅ docker-compose.local.yml validation passed")
        return True
        
    except yaml.YAMLError as e:
        print(f"❌ YAML parsing error: {e}")
        return False
    except Exception as e:
        print(f"❌ Validation error: {e}")
        return False


def validate_env_template():
    """Validate .env.local.example template."""
    print("🔍 Validating .env.local.example...")
    
    env_file = Path(".env.local.example")
    if not env_file.exists():
        print("❌ .env.local.example not found")
        return False
    
    try:
        with open(env_file) as f:
            content = f.read()
        
        # Check for required environment variables
        required_vars = [
            "ML_ENVIRONMENT",
            "DATABASE_TYPE",
            "ML_POSTGRES_HOST",
            "ML_NEO4J_HOST", 
            "ML_MILVUS_HOST",
            "OPENAI_API_KEY",
            "SECRET_KEY"
        ]
        
        missing_vars = [var for var in required_vars if var not in content]
        
        if missing_vars:
            print(f"❌ Missing required environment variables: {missing_vars}")
            return False
        
        print("✅ .env.local.example validation passed")
        return True
        
    except Exception as e:
        print(f"❌ Environment template validation error: {e}")
        return False


def validate_scripts():
    """Validate required scripts exist and are executable."""
    print("🔍 Validating scripts...")
    
    required_scripts = [
        "scripts/wait-for-services.sh",
        "scripts/seed-local-data.py"
    ]
    
    for script_path in required_scripts:
        script = Path(script_path)
        if not script.exists():
            print(f"❌ Script not found: {script_path}")
            return False
        
        if not os.access(script, os.X_OK):
            print(f"⚠️  Script not executable: {script_path}")
            print(f"   Run: chmod +x {script_path}")
    
    print("✅ Scripts validation passed")
    return True


def validate_documentation():
    """Validate documentation exists."""
    print("🔍 Validating documentation...")
    
    required_docs = [
        "docs/local-development-setup.md"
    ]
    
    for doc_path in required_docs:
        doc = Path(doc_path)
        if not doc.exists():
            print(f"❌ Documentation not found: {doc_path}")
            return False
    
    print("✅ Documentation validation passed")
    return True


def main():
    """Main validation function."""
    print("🚀 Validating local development setup...")
    print("")
    
    validations = [
        validate_docker_compose,
        validate_env_template,
        validate_scripts,
        validate_documentation
    ]
    
    results = []
    for validation in validations:
        results.append(validation())
        print("")
    
    if all(results):
        print("🎉 All validations passed!")
        print("")
        print("📋 Next steps:")
        print("1. Copy .env.local.example to .env.local")
        print("2. Edit .env.local with your API keys")
        print("3. Run: make dev-local")
        print("4. Wait for services: ./scripts/wait-for-services.sh")
        print("")
        print("🔗 Service URLs will be:")
        print("   • Application: http://localhost:8000")
        print("   • Neo4j Browser: http://localhost:7474")
        print("   • MinIO Console: http://localhost:9001")
        return 0
    else:
        print("❌ Some validations failed!")
        print("Please fix the issues above before proceeding.")
        return 1


if __name__ == "__main__":
    sys.exit(main())