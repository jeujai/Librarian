"""Configuration for the model server."""

import os
from typing import List, Optional

from pydantic import Field
from pydantic_settings import BaseSettings


class ModelServerSettings(BaseSettings):
    """Settings for the model server."""
    
    # Server configuration
    host: str = Field(default="0.0.0.0", env="MODEL_SERVER_HOST")
    port: int = Field(default=8001, env="MODEL_SERVER_PORT")
    log_level: str = Field(default="INFO", env="LOG_LEVEL")
    
    # Embedding model configuration
    embedding_model: str = Field(
        default="all-MiniLM-L6-v2",
        env="EMBEDDING_MODEL",
        description="Sentence transformer model for embeddings"
    )
    embedding_device: str = Field(
        default="cpu",
        env="EMBEDDING_DEVICE",
        description="Device for embedding model (cpu, cuda, mps)"
    )
    embedding_batch_size: int = Field(
        default=32,
        env="EMBEDDING_BATCH_SIZE",
        description="Maximum batch size for embedding generation"
    )
    
    # NLP model configuration
    nlp_model: str = Field(
        default="en_core_web_sm",
        env="NLP_MODEL",
        description="Spacy model for NLP tasks"
    )
    nlp_batch_size: int = Field(
        default=100,
        env="NLP_BATCH_SIZE",
        description="Maximum batch size for NLP processing"
    )
    
    # Model loading configuration
    preload_models: bool = Field(
        default=True,
        env="PRELOAD_MODELS",
        description="Load models on startup"
    )
    model_cache_dir: Optional[str] = Field(
        default=None,
        env="MODEL_CACHE_DIR",
        description="Directory for caching downloaded models"
    )
    
    # CORS configuration
    cors_origins: List[str] = Field(
        default=["*"],
        env="CORS_ORIGINS",
        description="Allowed CORS origins"
    )
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


# Global settings instance
_settings: Optional[ModelServerSettings] = None


def get_settings() -> ModelServerSettings:
    """Get the model server settings singleton."""
    global _settings
    if _settings is None:
        _settings = ModelServerSettings()
    return _settings
