#!/usr/bin/env python3
"""
Local Environment Configuration Validation Script

This script validates that all environment variables are properly configured
for local development services. It checks both the .env.local file and
docker-compose.local.yml configuration.

Usage:
    python scripts/validate-local-env-config.py
    python scripts/validate-local-env-config.py --fix-missing
    python scripts/validate-local-env-config.py --create-env
"""

import os
import sys
import argparse
import json
from pathlib import Path
from typing import Dict, List, Any, Optional
import yaml


class LocalEnvValidator:
    """Validator for local development environment configuration."""
    
    def __init__(self, workspace_root: str = "."):
        """Initialize validator with workspace root."""
        self.workspace_root = Path(workspace_root)
        self.env_local_path = self.workspace_root / ".env.local"
        self.env_example_path = self.workspace_root / ".env.local.example"
        self.docker_compose_path = self.workspace_root / "docker-compose.local.yml"
        
        # Required environment variables for local development
        self.required_vars = {
            # Environment selection
            "ML_ENVIRONMENT": "local",
            "ML_DATABASE_TYPE": "local", 
            "DATABASE_TYPE": "local",
            
            # Application settings
            "DEBUG": "true",
            "LOG_LEVEL": "INFO",
            "API_HOST": "0.0.0.0",
            "API_PORT": "8000",
            "API_WORKERS": "1",
            
            # PostgreSQL
            "POSTGRES_HOST": "postgres",
            "POSTGRES_PORT": "5432",
            "POSTGRES_DB": "multimodal_librarian",
            "POSTGRES_USER": "ml_user",
            "POSTGRES_PASSWORD": "ml_password",
            
            # Neo4j
            "NEO4J_HOST": "neo4j",
            "NEO4J_PORT": "7687",
            "NEO4J_USER": "neo4j",
            "NEO4J_PASSWORD": "ml_password",
            
            # Milvus
            "MILVUS_HOST": "milvus",
            "MILVUS_PORT": "19530",
            
            # Redis
            "REDIS_HOST": "redis",
            "REDIS_PORT": "6379",
            
            # Security
            "SECRET_KEY": "local-dev-secret-key-change-in-production",
            "REQUIRE_AUTH": "false",
        }
        
        # Optional but recommended variables
        self.recommended_vars = {
            "OPENAI_API_KEY": "your-openai-api-key-here",
            "GOOGLE_API_KEY": "your-google-api-key-here",
            "ANTHROPIC_API_KEY": "your-anthropic-api-key-here",
            "UPLOAD_DIR": "/app/uploads",
            "MEDIA_DIR": "/app/media",
            "EXPORT_DIR": "/app/exports",
            "CHUNK_SIZE": "512",
            "CHUNK_OVERLAP": "50",
            "EMBEDDING_MODEL": "all-MiniLM-L6-v2",
        }
        
        # Variables that should match between services
        self.service_consistency_vars = [
            "POSTGRES_HOST", "POSTGRES_PORT", "POSTGRES_DB", "POSTGRES_USER", "POSTGRES_PASSWORD",
            "NEO4J_HOST", "NEO4J_PORT", "NEO4J_USER", "NEO4J_PASSWORD",
            "MILVUS_HOST", "MILVUS_PORT",
            "REDIS_HOST", "REDIS_PORT"
        ]
    
    def validate_env_file(self) -> Dict[str, Any]:
        """Validate .env.local file."""
        results = {
            "file_exists": self.env_local_path.exists(),
            "missing_required": [],
            "missing_recommended": [],
            "invalid_values": [],
            "warnings": []
        }
        
        if not results["file_exists"]:
            results["warnings"].append(f".env.local file not found at {self.env_local_path}")
            return results
        
        # Load environment variables from file
        env_vars = self._load_env_file(self.env_local_path)
        
        # Check required variables
        for var, default_value in self.required_vars.items():
            if var not in env_vars:
                results["missing_required"].append(var)
            elif not env_vars[var].strip():
                results["invalid_values"].append(f"{var} is empty")
        
        # Check recommended variables
        for var, default_value in self.recommended_vars.items():
            if var not in env_vars:
                results["missing_recommended"].append(var)
            elif env_vars[var] == default_value and "api-key" in default_value.lower():
                results["warnings"].append(f"{var} still has placeholder value")
        
        # Check for insecure values
        if env_vars.get("SECRET_KEY") == self.required_vars["SECRET_KEY"]:
            results["warnings"].append("SECRET_KEY is using default value - change for production")
        
        if env_vars.get("POSTGRES_PASSWORD") == "ml_password":
            results["warnings"].append("POSTGRES_PASSWORD is using default value")
        
        if env_vars.get("NEO4J_PASSWORD") == "ml_password":
            results["warnings"].append("NEO4J_PASSWORD is using default value")
        
        return results
    
    def validate_docker_compose(self) -> Dict[str, Any]:
        """Validate docker-compose.local.yml configuration."""
        results = {
            "file_exists": self.docker_compose_path.exists(),
            "services_configured": [],
            "missing_services": [],
            "env_var_mismatches": [],
            "warnings": []
        }
        
        if not results["file_exists"]:
            results["warnings"].append(f"docker-compose.local.yml not found at {self.docker_compose_path}")
            return results
        
        try:
            with open(self.docker_compose_path, 'r') as f:
                compose_config = yaml.safe_load(f)
        except Exception as e:
            results["warnings"].append(f"Failed to parse docker-compose.local.yml: {e}")
            return results
        
        services = compose_config.get("services", {})
        
        # Check required services
        required_services = ["multimodal-librarian", "postgres", "neo4j", "milvus", "redis"]
        for service in required_services:
            if service in services:
                results["services_configured"].append(service)
            else:
                results["missing_services"].append(service)
        
        # Check application service environment variables
        app_service = services.get("multimodal-librarian", {})
        app_env = app_service.get("environment", [])
        
        # Convert environment list to dict
        app_env_dict = {}
        for env_var in app_env:
            if "=" in env_var:
                key, value = env_var.split("=", 1)
                key = key.strip("- ")
                app_env_dict[key] = value
        
        # Check for required environment variables in docker-compose
        for var in ["ML_ENVIRONMENT", "ML_DATABASE_TYPE", "POSTGRES_HOST", "NEO4J_HOST", "MILVUS_HOST"]:
            if var not in app_env_dict:
                results["env_var_mismatches"].append(f"Missing {var} in application service environment")
        
        # Check service dependencies
        app_depends_on = app_service.get("depends_on", {})
        for service in ["postgres", "neo4j", "milvus", "redis"]:
            if service not in app_depends_on:
                results["warnings"].append(f"Application service missing dependency on {service}")
        
        return results
    
    def validate_service_consistency(self) -> Dict[str, Any]:
        """Validate consistency between .env.local and docker-compose.local.yml."""
        results = {
            "consistent": True,
            "mismatches": [],
            "warnings": []
        }
        
        if not (self.env_local_path.exists() and self.docker_compose_path.exists()):
            results["warnings"].append("Cannot validate consistency - missing files")
            return results
        
        # Load environment variables
        env_vars = self._load_env_file(self.env_local_path)
        
        # Load docker-compose configuration
        try:
            with open(self.docker_compose_path, 'r') as f:
                compose_config = yaml.safe_load(f)
        except Exception as e:
            results["warnings"].append(f"Failed to parse docker-compose.local.yml: {e}")
            return results
        
        # Check database service configurations
        services = compose_config.get("services", {})
        
        # PostgreSQL consistency
        postgres_service = services.get("postgres", {})
        postgres_env = postgres_service.get("environment", [])
        postgres_env_dict = self._parse_env_list(postgres_env)
        
        postgres_checks = [
            ("POSTGRES_DB", "POSTGRES_DB"),
            ("POSTGRES_USER", "POSTGRES_USER"),
            ("POSTGRES_PASSWORD", "POSTGRES_PASSWORD")
        ]
        
        for env_var, compose_var in postgres_checks:
            env_value = env_vars.get(env_var)
            compose_value = postgres_env_dict.get(compose_var, "").replace("${", "").replace("}", "").split(":-")[-1]
            
            if env_value and compose_value and env_value != compose_value:
                results["mismatches"].append(f"PostgreSQL {env_var}: .env.local='{env_value}' vs docker-compose='{compose_value}'")
                results["consistent"] = False
        
        # Neo4j consistency
        neo4j_service = services.get("neo4j", {})
        neo4j_env = neo4j_service.get("environment", [])
        neo4j_env_dict = self._parse_env_list(neo4j_env)
        
        # Neo4j uses NEO4J_AUTH format: user/password
        neo4j_auth = neo4j_env_dict.get("NEO4J_AUTH", "")
        if neo4j_auth and "/" in neo4j_auth:
            auth_parts = neo4j_auth.replace("${", "").replace("}", "").split("/")
            if len(auth_parts) == 2:
                compose_user = auth_parts[0].split(":-")[-1]
                compose_password = auth_parts[1].split(":-")[-1]
                
                env_user = env_vars.get("NEO4J_USER")
                env_password = env_vars.get("NEO4J_PASSWORD")
                
                if env_user and compose_user and env_user != compose_user:
                    results["mismatches"].append(f"Neo4j user: .env.local='{env_user}' vs docker-compose='{compose_user}'")
                    results["consistent"] = False
                
                if env_password and compose_password and env_password != compose_password:
                    results["mismatches"].append(f"Neo4j password: .env.local='{env_password}' vs docker-compose='{compose_password}'")
                    results["consistent"] = False
        
        return results
    
    def create_env_file(self) -> bool:
        """Create .env.local file from .env.local.example."""
        if not self.env_example_path.exists():
            print(f"Error: {self.env_example_path} not found")
            return False
        
        if self.env_local_path.exists():
            response = input(f"{self.env_local_path} already exists. Overwrite? (y/N): ")
            if response.lower() != 'y':
                print("Aborted")
                return False
        
        try:
            # Copy example file to .env.local
            with open(self.env_example_path, 'r') as src:
                content = src.read()
            
            with open(self.env_local_path, 'w') as dst:
                dst.write(content)
            
            print(f"Created {self.env_local_path} from {self.env_example_path}")
            print("Please edit the file to add your API keys and customize settings")
            return True
            
        except Exception as e:
            print(f"Error creating .env.local: {e}")
            return False
    
    def fix_missing_vars(self) -> bool:
        """Add missing required variables to .env.local."""
        if not self.env_local_path.exists():
            print("Error: .env.local file not found. Use --create-env first.")
            return False
        
        # Load current environment variables
        env_vars = self._load_env_file(self.env_local_path)
        
        # Find missing required variables
        missing_vars = []
        for var, default_value in self.required_vars.items():
            if var not in env_vars:
                missing_vars.append((var, default_value))
        
        if not missing_vars:
            print("No missing required variables found")
            return True
        
        print(f"Adding {len(missing_vars)} missing variables to .env.local:")
        
        # Append missing variables
        try:
            with open(self.env_local_path, 'a') as f:
                f.write("\n# Added by validation script\n")
                for var, default_value in missing_vars:
                    f.write(f"{var}={default_value}\n")
                    print(f"  + {var}={default_value}")
            
            print(f"Successfully updated {self.env_local_path}")
            return True
            
        except Exception as e:
            print(f"Error updating .env.local: {e}")
            return False
    
    def _load_env_file(self, file_path: Path) -> Dict[str, str]:
        """Load environment variables from file."""
        env_vars = {}
        
        try:
            with open(file_path, 'r') as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith('#') and '=' in line:
                        key, value = line.split('=', 1)
                        env_vars[key.strip()] = value.strip()
        except Exception as e:
            print(f"Warning: Failed to load {file_path}: {e}")
        
        return env_vars
    
    def _parse_env_list(self, env_list: List[str]) -> Dict[str, str]:
        """Parse environment variable list from docker-compose."""
        env_dict = {}
        
        for env_var in env_list:
            env_var = env_var.strip("- ")
            if "=" in env_var:
                key, value = env_var.split("=", 1)
                env_dict[key] = value
        
        return env_dict
    
    def run_validation(self) -> Dict[str, Any]:
        """Run complete validation."""
        print("Validating local development environment configuration...")
        print("=" * 60)
        
        results = {
            "env_file": self.validate_env_file(),
            "docker_compose": self.validate_docker_compose(),
            "consistency": self.validate_service_consistency(),
            "overall_status": "unknown"
        }
        
        # Determine overall status
        env_ok = (results["env_file"]["file_exists"] and 
                 not results["env_file"]["missing_required"])
        
        compose_ok = (results["docker_compose"]["file_exists"] and 
                     not results["docker_compose"]["missing_services"])
        
        consistency_ok = results["consistency"]["consistent"]
        
        if env_ok and compose_ok and consistency_ok:
            results["overall_status"] = "success"
        elif env_ok and compose_ok:
            results["overall_status"] = "warning"
        else:
            results["overall_status"] = "error"
        
        return results
    
    def print_results(self, results: Dict[str, Any]) -> None:
        """Print validation results."""
        # Environment file results
        print("1. Environment File (.env.local)")
        print("-" * 30)
        
        env_results = results["env_file"]
        if env_results["file_exists"]:
            print("✓ .env.local file exists")
        else:
            print("✗ .env.local file missing")
        
        if env_results["missing_required"]:
            print(f"✗ Missing required variables ({len(env_results['missing_required'])}):")
            for var in env_results["missing_required"]:
                print(f"    - {var}")
        else:
            print("✓ All required variables present")
        
        if env_results["missing_recommended"]:
            print(f"⚠ Missing recommended variables ({len(env_results['missing_recommended'])}):")
            for var in env_results["missing_recommended"]:
                print(f"    - {var}")
        
        if env_results["warnings"]:
            print("⚠ Warnings:")
            for warning in env_results["warnings"]:
                print(f"    - {warning}")
        
        print()
        
        # Docker Compose results
        print("2. Docker Compose Configuration")
        print("-" * 30)
        
        compose_results = results["docker_compose"]
        if compose_results["file_exists"]:
            print("✓ docker-compose.local.yml file exists")
        else:
            print("✗ docker-compose.local.yml file missing")
        
        if compose_results["services_configured"]:
            print(f"✓ Services configured ({len(compose_results['services_configured'])}):")
            for service in compose_results["services_configured"]:
                print(f"    - {service}")
        
        if compose_results["missing_services"]:
            print(f"✗ Missing services ({len(compose_results['missing_services'])}):")
            for service in compose_results["missing_services"]:
                print(f"    - {service}")
        
        if compose_results["env_var_mismatches"]:
            print("✗ Environment variable issues:")
            for issue in compose_results["env_var_mismatches"]:
                print(f"    - {issue}")
        
        if compose_results["warnings"]:
            print("⚠ Warnings:")
            for warning in compose_results["warnings"]:
                print(f"    - {warning}")
        
        print()
        
        # Consistency results
        print("3. Configuration Consistency")
        print("-" * 30)
        
        consistency_results = results["consistency"]
        if consistency_results["consistent"]:
            print("✓ Configuration is consistent between files")
        else:
            print("✗ Configuration inconsistencies found:")
            for mismatch in consistency_results["mismatches"]:
                print(f"    - {mismatch}")
        
        if consistency_results["warnings"]:
            print("⚠ Warnings:")
            for warning in consistency_results["warnings"]:
                print(f"    - {warning}")
        
        print()
        
        # Overall status
        print("Overall Status")
        print("-" * 30)
        
        status = results["overall_status"]
        if status == "success":
            print("✓ Configuration is valid and ready for local development")
        elif status == "warning":
            print("⚠ Configuration is mostly valid but has warnings")
        else:
            print("✗ Configuration has errors that need to be fixed")
        
        print()
        
        # Recommendations
        if status != "success":
            print("Recommendations")
            print("-" * 30)
            
            if not env_results["file_exists"]:
                print("• Run with --create-env to create .env.local from template")
            
            if env_results["missing_required"]:
                print("• Run with --fix-missing to add missing required variables")
            
            if env_results["missing_recommended"]:
                print("• Add API keys for external services (OpenAI, Google, etc.)")
            
            if not consistency_results["consistent"]:
                print("• Check and fix configuration mismatches between files")
            
            print()


def main():
    """Main function."""
    parser = argparse.ArgumentParser(
        description="Validate local development environment configuration"
    )
    parser.add_argument(
        "--create-env",
        action="store_true",
        help="Create .env.local from .env.local.example"
    )
    parser.add_argument(
        "--fix-missing",
        action="store_true", 
        help="Add missing required variables to .env.local"
    )
    parser.add_argument(
        "--workspace-root",
        default=".",
        help="Workspace root directory (default: current directory)"
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output results in JSON format"
    )
    
    args = parser.parse_args()
    
    # Initialize validator
    validator = LocalEnvValidator(args.workspace_root)
    
    # Handle special actions
    if args.create_env:
        success = validator.create_env_file()
        sys.exit(0 if success else 1)
    
    if args.fix_missing:
        success = validator.fix_missing_vars()
        sys.exit(0 if success else 1)
    
    # Run validation
    results = validator.run_validation()
    
    if args.json:
        print(json.dumps(results, indent=2))
    else:
        validator.print_results(results)
    
    # Exit with appropriate code
    status = results["overall_status"]
    if status == "success":
        sys.exit(0)
    elif status == "warning":
        sys.exit(1)
    else:
        sys.exit(2)


if __name__ == "__main__":
    main()