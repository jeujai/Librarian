"""
Environment switching utilities for the Multimodal Librarian system.

This module provides utilities for switching between local development and AWS production
environments, including configuration validation and environment setup.
"""

import os
import shutil
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional

from ..config.config import get_settings


class EnvironmentType(Enum):
    """Supported environment types."""
    LOCAL = "local"
    AWS = "aws"
    DEVELOPMENT = "development"
    PRODUCTION = "production"


@dataclass
class EnvironmentConfig:
    """Environment configuration settings."""
    name: str
    database_type: str
    ml_environment: str
    debug: bool
    log_level: str
    api_docs_enabled: bool
    hot_reload_enabled: bool
    required_env_vars: List[str]
    optional_env_vars: List[str]
    description: str


class EnvironmentSwitcher:
    """Utility class for switching between environments."""
    
    # Predefined environment configurations
    ENVIRONMENTS = {
        EnvironmentType.LOCAL: EnvironmentConfig(
            name="Local Development",
            database_type="local",
            ml_environment="local",
            debug=True,
            log_level="DEBUG",
            api_docs_enabled=True,
            hot_reload_enabled=True,
            required_env_vars=[
                "POSTGRES_HOST", "POSTGRES_PORT", "POSTGRES_DB", 
                "POSTGRES_USER", "POSTGRES_PASSWORD",
                "NEO4J_HOST", "NEO4J_PORT", "NEO4J_USER", "NEO4J_PASSWORD",
                "MILVUS_HOST", "MILVUS_PORT",
                "REDIS_HOST", "REDIS_PORT"
            ],
            optional_env_vars=[
                "OPENAI_API_KEY", "GOOGLE_API_KEY", "GEMINI_API_KEY", "ANTHROPIC_API_KEY"
            ],
            description="Local development environment with Docker Compose services"
        ),
        EnvironmentType.AWS: EnvironmentConfig(
            name="AWS Production",
            database_type="aws",
            ml_environment="aws",
            debug=False,
            log_level="INFO",
            api_docs_enabled=False,
            hot_reload_enabled=False,
            required_env_vars=[
                "NEPTUNE_ENDPOINT", "OPENSEARCH_ENDPOINT", 
                "AWS_REGION", "POSTGRES_HOST", "POSTGRES_DB",
                "POSTGRES_USER", "POSTGRES_PASSWORD"
            ],
            optional_env_vars=[
                "AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY",
                "OPENAI_API_KEY", "GOOGLE_API_KEY", "GEMINI_API_KEY", "ANTHROPIC_API_KEY"
            ],
            description="AWS production environment with managed services"
        )
    }
    
    def __init__(self):
        """Initialize the environment switcher."""
        self.current_env = self._detect_current_environment()
    
    def _detect_current_environment(self) -> EnvironmentType:
        """Detect the current environment based on configuration."""
        settings = get_settings()
        
        if settings.is_local_environment():
            return EnvironmentType.LOCAL
        elif settings.is_aws_environment():
            return EnvironmentType.AWS
        else:
            # Default to local if unclear
            return EnvironmentType.LOCAL
    
    def get_current_environment(self) -> EnvironmentType:
        """Get the current environment type."""
        return self.current_env
    
    def get_environment_info(self, env_type: Optional[EnvironmentType] = None) -> Dict[str, Any]:
        """Get information about an environment."""
        if env_type is None:
            env_type = self.current_env
        
        config = self.ENVIRONMENTS.get(env_type)
        if not config:
            raise ValueError(f"Unknown environment type: {env_type}")
        
        settings = get_settings()
        
        return {
            "environment_type": env_type.value,
            "name": config.name,
            "description": config.description,
            "is_current": env_type == self.current_env,
            "configuration": {
                "database_type": config.database_type,
                "ml_environment": config.ml_environment,
                "debug": config.debug,
                "log_level": config.log_level,
                "api_docs_enabled": config.api_docs_enabled,
                "hot_reload_enabled": config.hot_reload_enabled,
            },
            "required_variables": config.required_env_vars,
            "optional_variables": config.optional_env_vars,
            "current_settings": {
                "database_backend": settings.get_database_backend(),
                "debug": settings.debug,
                "log_level": settings.log_level,
                "features_enabled": settings.get_enabled_features(),
            }
        }
    
    def validate_environment(self, env_type: EnvironmentType) -> Dict[str, Any]:
        """Validate if an environment can be switched to."""
        config = self.ENVIRONMENTS.get(env_type)
        if not config:
            raise ValueError(f"Unknown environment type: {env_type}")
        
        validation_result = {
            "valid": True,
            "errors": [],
            "warnings": [],
            "missing_required": [],
            "missing_optional": [],
            "environment": env_type.value
        }
        
        # Check required environment variables
        for var in config.required_env_vars:
            if not os.getenv(var):
                validation_result["missing_required"].append(var)
                validation_result["errors"].append(f"Required environment variable missing: {var}")
        
        # Check optional environment variables
        for var in config.optional_env_vars:
            if not os.getenv(var):
                validation_result["missing_optional"].append(var)
                validation_result["warnings"].append(f"Optional environment variable missing: {var}")
        
        # Environment-specific validations
        if env_type == EnvironmentType.LOCAL:
            # Check if Docker Compose services are likely available
            if not self._check_local_services():
                validation_result["warnings"].append("Local Docker Compose services may not be running")
        
        elif env_type == EnvironmentType.AWS:
            # Check AWS credentials
            if not (os.getenv("AWS_ACCESS_KEY_ID") or os.getenv("AWS_PROFILE")):
                validation_result["warnings"].append("No AWS credentials configured")
        
        validation_result["valid"] = len(validation_result["errors"]) == 0
        return validation_result
    
    def _check_local_services(self) -> bool:
        """Check if local Docker Compose services are likely available."""
        # This is a simple check - in a real implementation, you might
        # try to connect to the services or check Docker Compose status
        compose_files = [
            "docker-compose.local.yml",
            "docker-compose.yml"
        ]
        
        return any(Path(f).exists() for f in compose_files)
    
    def switch_environment(self, env_type: EnvironmentType, force: bool = False) -> Dict[str, Any]:
        """Switch to a different environment."""
        if env_type == self.current_env and not force:
            return {
                "success": True,
                "message": f"Already in {env_type.value} environment",
                "environment": env_type.value,
                "no_change": True
            }
        
        # Validate the target environment
        validation = self.validate_environment(env_type)
        if not validation["valid"] and not force:
            return {
                "success": False,
                "message": f"Cannot switch to {env_type.value} environment",
                "errors": validation["errors"],
                "validation": validation
            }
        
        config = self.ENVIRONMENTS[env_type]
        
        try:
            # Set core environment variables for the switch
            os.environ["ML_ENVIRONMENT"] = config.ml_environment
            os.environ["DATABASE_TYPE"] = config.database_type
            os.environ["ML_DATABASE_TYPE"] = config.database_type
            os.environ["DEBUG"] = str(config.debug).lower()
            os.environ["LOG_LEVEL"] = config.log_level
            
            # Reload settings to pick up the new environment
            reload_settings()
            
            # Update current environment
            self.current_env = env_type
            
            # Validate the new configuration
            new_validation = validate_environment_configuration()
            
            return {
                "success": True,
                "message": f"Successfully switched to {config.name} environment",
                "environment": env_type.value,
                "previous_environment": self._detect_current_environment().value,
                "validation": new_validation,
                "warnings": validation.get("warnings", [])
            }
            
        except Exception as e:
            return {
                "success": False,
                "message": f"Failed to switch environment: {str(e)}",
                "environment": env_type.value,
                "error": str(e)
            }
    
    def create_environment_file(self, env_type: EnvironmentType, output_path: str = None) -> Dict[str, Any]:
        """Create an environment file template for the specified environment."""
        config = self.ENVIRONMENTS.get(env_type)
        if not config:
            raise ValueError(f"Unknown environment type: {env_type}")
        
        if output_path is None:
            output_path = f".env.{env_type.value}"
        
        # Generate environment file content
        content = self._generate_env_file_content(env_type, config)
        
        try:
            # Write the environment file
            with open(output_path, 'w') as f:
                f.write(content)
            
            return {
                "success": True,
                "message": f"Environment file created: {output_path}",
                "path": output_path,
                "environment": env_type.value
            }
            
        except Exception as e:
            return {
                "success": False,
                "message": f"Failed to create environment file: {str(e)}",
                "error": str(e)
            }
    
    def _generate_env_file_content(self, env_type: EnvironmentType, config: EnvironmentConfig) -> str:
        """Generate environment file content for the specified environment."""
        content = f"""# =============================================================================
# {config.name.upper()} ENVIRONMENT CONFIGURATION
# =============================================================================
# Generated environment file for {config.description}
# Copy this file to .env.local and customize the values

# Environment Configuration
ML_ENVIRONMENT={config.ml_environment}
DATABASE_TYPE={config.database_type}
ML_DATABASE_TYPE={config.database_type}

# Application Settings
DEBUG={str(config.debug).lower()}
LOG_LEVEL={config.log_level}
API_HOST=0.0.0.0
API_PORT=8000

# Configuration Validation
VALIDATE_CONFIG_ON_STARTUP=true
STRICT_CONFIG_VALIDATION=false

"""
        
        if env_type == EnvironmentType.LOCAL:
            content += """# =============================================================================
# LOCAL DATABASE CONFIGURATION
# =============================================================================
# PostgreSQL Configuration
POSTGRES_HOST=postgres
POSTGRES_PORT=5432
POSTGRES_DB=multimodal_librarian
POSTGRES_USER=ml_user
POSTGRES_PASSWORD=ml_password

# Neo4j Configuration
NEO4J_HOST=neo4j
NEO4J_PORT=7687
NEO4J_URI=bolt://neo4j:7687
NEO4J_USER=neo4j
NEO4J_PASSWORD=ml_password

# Milvus Configuration
MILVUS_HOST=milvus
MILVUS_PORT=19530
MILVUS_COLLECTION_NAME=knowledge_chunks

# Redis Configuration
REDIS_HOST=redis
REDIS_PORT=6379
REDIS_DB=0
CACHE_TTL=3600

"""
        
        elif env_type == EnvironmentType.AWS:
            content += """# =============================================================================
# AWS PRODUCTION CONFIGURATION
# =============================================================================
# AWS Settings
AWS_REGION=us-east-1
# AWS_ACCESS_KEY_ID=your-access-key-id
# AWS_SECRET_ACCESS_KEY=your-secret-access-key

# AWS Neptune (Knowledge Graph)
NEPTUNE_ENDPOINT=your-neptune-cluster-endpoint.region.neptune.amazonaws.com
NEPTUNE_PORT=8182

# AWS OpenSearch (Vector Search)
OPENSEARCH_ENDPOINT=your-opensearch-domain-endpoint.region.es.amazonaws.com
OPENSEARCH_PORT=443
OPENSEARCH_INDEX_NAME=knowledge_chunks

# PostgreSQL (AWS RDS)
POSTGRES_HOST=your-rds-endpoint.region.rds.amazonaws.com
POSTGRES_PORT=5432
POSTGRES_DB=multimodal_librarian
POSTGRES_USER=your-db-user
POSTGRES_PASSWORD=your-db-password

"""
        
        # Add common configuration
        content += """# =============================================================================
# EXTERNAL API KEYS
# =============================================================================
# AI/LLM Service API Keys (Required for AI functionality)
# OPENAI_API_KEY=your-openai-api-key-here
# GOOGLE_API_KEY=your-google-api-key-here
# GEMINI_API_KEY=your-gemini-api-key-here
# ANTHROPIC_API_KEY=your-anthropic-api-key-here

# =============================================================================
# SECURITY CONFIGURATION
# =============================================================================
SECRET_KEY=change-this-in-production-use-32-chars-minimum
ENCRYPTION_KEY=change-this-base64-encoded-key-in-production
REQUIRE_AUTH=false

# =============================================================================
# FEATURE FLAGS
# =============================================================================
ENABLE_DOCUMENT_UPLOAD=true
ENABLE_KNOWLEDGE_GRAPH=true
ENABLE_VECTOR_SEARCH=true
ENABLE_AI_CHAT=true
ENABLE_ANALYTICS=true

# =============================================================================
# FILE STORAGE
# =============================================================================
UPLOAD_DIR=/app/uploads
MEDIA_DIR=/app/media
EXPORT_DIR=/app/exports
MAX_FILE_SIZE=10737418240

# =============================================================================
# PROCESSING SETTINGS
# =============================================================================
CHUNK_SIZE=512
CHUNK_OVERLAP=50
EMBEDDING_MODEL=all-MiniLM-L6-v2
"""
        
        return content
    
    def list_environments(self) -> Dict[str, Any]:
        """List all available environments."""
        environments = {}
        
        for env_type, config in self.ENVIRONMENTS.items():
            environments[env_type.value] = {
                "name": config.name,
                "description": config.description,
                "is_current": env_type == self.current_env,
                "database_type": config.database_type,
                "debug": config.debug,
                "required_vars_count": len(config.required_env_vars),
                "optional_vars_count": len(config.optional_env_vars)
            }
        
        return {
            "current_environment": self.current_env.value,
            "available_environments": environments,
            "total_count": len(environments)
        }


# Global instance
_environment_switcher: Optional[EnvironmentSwitcher] = None


def get_environment_switcher() -> EnvironmentSwitcher:
    """Get the global environment switcher instance."""
    global _environment_switcher
    if _environment_switcher is None:
        _environment_switcher = EnvironmentSwitcher()
    return _environment_switcher


def switch_to_local() -> Dict[str, Any]:
    """Switch to local development environment."""
    switcher = get_environment_switcher()
    return switcher.switch_environment(EnvironmentType.LOCAL)


def switch_to_aws() -> Dict[str, Any]:
    """Switch to AWS production environment."""
    switcher = get_environment_switcher()
    return switcher.switch_environment(EnvironmentType.AWS)


def get_current_environment_info() -> Dict[str, Any]:
    """Get information about the current environment."""
    switcher = get_environment_switcher()
    return switcher.get_environment_info()


def validate_current_environment() -> Dict[str, Any]:
    """Validate the current environment configuration."""
    switcher = get_environment_switcher()
    current_env = switcher.get_current_environment()
    return switcher.validate_environment(current_env)


def create_local_env_file(output_path: str = ".env.local") -> Dict[str, Any]:
    """Create a local development environment file."""
    switcher = get_environment_switcher()
    return switcher.create_environment_file(EnvironmentType.LOCAL, output_path)


def create_aws_env_file(output_path: str = ".env.aws") -> Dict[str, Any]:
    """Create an AWS production environment file."""
    switcher = get_environment_switcher()
    return switcher.create_environment_file(EnvironmentType.AWS, output_path)