"""
Neo4j Configuration for Multimodal Librarian

This module provides configuration settings and utilities for Neo4j integration.
"""

import os
from typing import Dict, Any
from pydantic import BaseSettings, Field


class Neo4jConfig(BaseSettings):
    """Neo4j configuration settings."""
    
    # AWS Secrets Manager settings
    secret_name: str = Field(
        default="multimodal-librarian/full-ml/neo4j",
        description="AWS Secrets Manager secret name for Neo4j credentials"
    )
    
    aws_region: str = Field(
        default="us-east-1",
        description="AWS region for Secrets Manager"
    )
    
    # Connection settings
    max_connection_lifetime: int = Field(
        default=3600,
        description="Maximum connection lifetime in seconds"
    )
    
    max_connection_pool_size: int = Field(
        default=50,
        description="Maximum number of connections in the pool"
    )
    
    connection_acquisition_timeout: int = Field(
        default=60,
        description="Connection acquisition timeout in seconds"
    )
    
    # Health check settings
    health_check_interval: int = Field(
        default=30,
        description="Health check interval in seconds"
    )
    
    # Query settings
    default_query_timeout: int = Field(
        default=30,
        description="Default query timeout in seconds"
    )
    
    # Feature flags
    enable_knowledge_graph: bool = Field(
        default=True,
        description="Enable knowledge graph functionality"
    )
    
    enable_auto_processing: bool = Field(
        default=False,
        description="Enable automatic document processing to knowledge graph"
    )
    
    # Processing settings
    max_entities_per_document: int = Field(
        default=100,
        description="Maximum entities to extract per document"
    )
    
    max_relationships_per_document: int = Field(
        default=200,
        description="Maximum relationships to extract per document"
    )
    
    class Config:
        env_prefix = "NEO4J_"
        case_sensitive = False


# Global configuration instance
_config: Neo4jConfig = None


def get_neo4j_config() -> Neo4jConfig:
    """Get Neo4j configuration instance."""
    global _config
    
    if _config is None:
        _config = Neo4jConfig()
    
    return _config


def is_neo4j_enabled() -> bool:
    """Check if Neo4j functionality is enabled."""
    config = get_neo4j_config()
    return config.enable_knowledge_graph


def get_connection_config() -> Dict[str, Any]:
    """Get Neo4j connection configuration."""
    config = get_neo4j_config()
    
    return {
        "max_connection_lifetime": config.max_connection_lifetime,
        "max_connection_pool_size": config.max_connection_pool_size,
        "connection_acquisition_timeout": config.connection_acquisition_timeout,
        "encrypted": False,  # VPC internal communication
        "trust": True
    }


def get_query_config() -> Dict[str, Any]:
    """Get Neo4j query configuration."""
    config = get_neo4j_config()
    
    return {
        "timeout": config.default_query_timeout
    }


def get_processing_config() -> Dict[str, Any]:
    """Get document processing configuration."""
    config = get_neo4j_config()
    
    return {
        "max_entities": config.max_entities_per_document,
        "max_relationships": config.max_relationships_per_document,
        "auto_processing": config.enable_auto_processing
    }