"""
Configuration management for the Multimodal Librarian system.

This module handles environment variables, application settings, and configuration
for all components of the system.
"""

import os
from functools import lru_cache
from typing import Optional

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""
    
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
        # Allow model_server_* fields without Pydantic v2 namespace warnings.
        # The default ('model_',) conflicts with our model_server_* settings.
        protected_namespaces=(),
    )
    
    # Application settings
    app_name: str = Field(default="Multimodal Librarian", description="Application name")
    debug: bool = Field(default=False, description="Debug mode")
    log_level: str = Field(default="INFO", description="Logging level")
    
    # API settings
    api_host: str = Field(default="0.0.0.0", description="API host")
    api_port: int = Field(default=8000, description="API port")
    api_workers: int = Field(default=1, description="Number of API workers")
    api_key: Optional[str] = Field(default=None, description="API key for authentication")
    
    # Security and middleware settings
    require_auth: bool = Field(default=False, description="Require authentication for API access")
    allowed_origins: list = Field(default=["*"], description="Allowed CORS origins")
    rate_limit_per_minute: int = Field(default=60, description="Rate limit per minute per IP")
    websocket_timeout: int = Field(default=300, description="WebSocket timeout in seconds")
    
    # Encryption settings
    encryption_key: Optional[str] = Field(default=None, description="Base64 encoded encryption key")
    
    # Security settings
    secret_key: str = Field(default="your-secret-key-change-in-production", description="Secret key for JWT")
    access_token_expire_minutes: int = Field(default=30, description="Access token expiration time")
    
    # Password policy settings
    min_password_length: int = Field(default=8, description="Minimum password length")
    require_password_complexity: bool = Field(default=True, description="Require complex passwords")
    
    # Session settings
    session_timeout_minutes: int = Field(default=60, description="Session timeout in minutes")
    max_concurrent_sessions: int = Field(default=5, description="Maximum concurrent sessions per user")
    
    # Audit settings
    audit_log_retention_days: int = Field(default=365, description="Audit log retention period in days")
    enable_detailed_audit: bool = Field(default=True, description="Enable detailed audit logging")
    
    # Data retention settings
    data_retention_days: int = Field(default=2555, description="Default data retention period (7 years)")
    auto_cleanup_enabled: bool = Field(default=False, description="Enable automatic data cleanup")
    
    # Database settings
    postgres_host: str = Field(default="localhost", description="PostgreSQL host")
    postgres_port: int = Field(default=5432, description="PostgreSQL port")
    postgres_db: str = Field(default="multimodal_librarian", description="PostgreSQL database name")
    postgres_user: str = Field(default="postgres", description="PostgreSQL username")
    postgres_password: str = Field(default="", description="PostgreSQL password")
    
    @property
    def postgres_url(self) -> str:
        """Get PostgreSQL connection URL."""
        return f"postgresql://{self.postgres_user}:{self.postgres_password}@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
    
    # Vector database settings
    milvus_host: str = Field(default="localhost", description="Milvus host")
    milvus_port: int = Field(default=19530, description="Milvus port")
    milvus_collection_name: str = Field(default="knowledge_chunks", description="Milvus collection name")
    
    # External API settings (Gemini only)
    google_api_key: Optional[str] = Field(default=None, description="Google API key for Gemini")
    gemini_api_key: Optional[str] = Field(default=None, description="Gemini API key for AI generation")
    gemini_model: str = Field(default="gemini-2.0-flash-exp", description="Gemini model to use")
    
    # Ollama Configuration (Local LLM)
    ollama_host: str = Field(default="http://localhost:11434", description="Ollama API host URL")
    ollama_model: str = Field(default="llama3.2:3b", description="Ollama model to use")
    ollama_enabled: bool = Field(default=True, description="Enable Ollama for local LLM")
    ollama_timeout: float = Field(default=120.0, description="Ollama request timeout in seconds")
    # Bridge generation provider: "ollama" (local, fast) or "gemini" (cloud, higher quality)
    bridge_generation_provider: str = Field(default="ollama", description="Provider for bridge generation")
    
    @property
    def GEMINI_API_KEY(self) -> Optional[str]:
        """Get Gemini API key (alias for compatibility)."""
        return self.gemini_api_key or self.google_api_key
    
    # File storage settings
    upload_dir: str = Field(default="uploads", description="Directory for uploaded files")
    media_dir: str = Field(default="media", description="Directory for generated media")
    export_dir: str = Field(default="exports", description="Directory for exported files")
    max_file_size: int = Field(default=100 * 1024 * 1024, description="Maximum file size in bytes (100MB)")
    
    # Processing settings
    chunk_size: int = Field(default=512, description="Default chunk size for text processing")
    chunk_overlap: int = Field(default=50, description="Default chunk overlap")
    embedding_model: str = Field(default="BAAI/bge-base-en-v1.5", description="Sentence transformer model")
    
    # Model server settings
    model_server_url: str = Field(default="http://model-server:8001", description="Model server base URL")
    model_server_enabled: bool = Field(default=True, description="Enable model server for embeddings/NLP")
    model_server_timeout: float = Field(default=30.0, description="Model server request timeout in seconds")
    
    # Embedding-aware chunking thresholds
    # Calibrate chunk token counts to the embedding model's optimal input length.
    # Initial values informed by Reimers & Gurevych (2019) and transformer architecture constraints.
    # All thresholds are tunable via environment variables and the retrieval quality metrics feedback loop.
    target_embedding_tokens: int = Field(
        default=256,
        description=(
            "Optimal token count for the embedding model. bge-base-en-v1.5 supports up "
            "to 512 tokens; embeddings degrade when input length diverges from training "
            "distribution. Tune per model — bge-base-en-v1.5 handles 512."
        ),
    )
    max_embedding_tokens: int = Field(
        default=512,
        description=(
            "Hard upper token limit for the embedding model. Most transformer models "
            "truncate beyond this due to positional encoding ceiling. Tokens past this "
            "limit are silently lost."
        ),
    )
    min_embedding_tokens: int = Field(
        default=64,
        description=(
            "Minimum viable chunk token count. Below ~50 tokens, embeddings become noisy "
            "due to insufficient context for meaningful representation. 64 provides a "
            "conservative floor."
        ),
    )
    
    # Concept extraction thresholds
    # Control multi-word phrase discovery (seed list + PMI collocation) and acronym extraction.
    # All values are empirical starting points for tuning via retrieval quality metrics.
    pmi_threshold: float = Field(
        default=5.0,
        description=(
            "Pointwise Mutual Information threshold for collocation detection. "
            "A value of 5.0 means the bigram co-occurs ~32x more often than expected "
            "by chance — conservative enough to filter noise while catching genuine "
            "collocations."
        ),
    )
    multi_word_seed_confidence: float = Field(
        default=0.85,
        description=(
            "Base confidence for seed-list multi-word phrase matches. High specificity — "
            "a curated phrase appearing in text is almost certainly a concept. Slightly "
            "below 1.0 to account for polysemy."
        ),
    )
    multi_word_pmi_confidence: float = Field(
        default=0.65,
        description=(
            "Base confidence for PMI-discovered multi-word concepts. Lower than seed "
            "matches because statistical collocation can produce false positives "
            "(e.g. 'the following' has high PMI but is not a concept)."
        ),
    )
    acronym_confidence: float = Field(
        default=0.6,
        description=(
            "Base confidence for acronym extraction. Acronyms are inherently ambiguous "
            "without context ('API' is clear, 'IT' could be a pronoun). Lower confidence "
            "reflects this ambiguity."
        ),
    )
    frequency_boost_increment: float = Field(
        default=0.02,
        description=(
            "Confidence boost per additional occurrence of a concept within a chunk. "
            "Grounded in TF-IDF theory — repeated mentions within a focused text segment "
            "increase the likelihood that the term is topically significant."
        ),
    )
    frequency_boost_cap: float = Field(
        default=0.1,
        description=(
            "Maximum cumulative frequency boost applied to concept confidence. "
            "Caps the boost at +0.1 to prevent high-frequency but low-value terms "
            "from dominating."
        ),
    )
    
    # Concept bisection detection
    overlap_window: int = Field(
        default=20,
        description=(
            "Number of tokens to inspect on each side of a proposed chunk boundary "
            "for concept bisection. When a multi-word concept spans the boundary, "
            "the boundary is shifted to keep the concept in a single chunk."
        ),
    )
    
    # Enrichment settings
    enrichment_batch_size: int = Field(default=500, description="Number of concepts to enrich per batch")
    enrichment_checkpoint_interval: int = Field(default=500, description="Save enrichment checkpoint every N concepts")

    # SearXNG web search settings
    searxng_host: str = Field(
        default="searxng",
        description="SearXNG service hostname",
    )
    searxng_port: int = Field(
        default=8080,
        description="SearXNG service port",
    )
    searxng_timeout: float = Field(
        default=10.0,
        description="SearXNG request timeout in seconds",
    )
    searxng_enabled: bool = Field(
        default=False,
        description="Enable SearXNG web search",
    )
    searxng_max_results: int = Field(
        default=5,
        description="Maximum web search results to fetch",
    )
    web_search_result_count_threshold: int = Field(
        default=3,
        description="Minimum Librarian results before web search is triggered",
    )
    librarian_boost_factor: float = Field(
        default=1.15,
        description=(
            "Multiplicative boost applied to Librarian document scores during "
            "post-processing. Keeps Librarian results above equivalently-scored "
            "web results without capping everything to 1.0. A value of 1.15 "
            "turns a 0.82 into 0.943, preserving score differentiation."
        ),
    )

    # Relevance detection thresholds
    relevance_spread_threshold: float = Field(
        default=0.05,
        description="Minimum final_score spread to avoid semantic floor detection",
    )
    relevance_variance_threshold: float = Field(
        default=0.001,
        description="Minimum final_score variance to avoid semantic floor detection",
    )
    relevance_specificity_threshold: float = Field(
        default=0.3,
        description="Minimum concept specificity score to be considered domain-specific",
    )

    # Knowledge graph settings
    neo4j_uri: Optional[str] = Field(default=None, description="Neo4j connection URI")
    neo4j_user: Optional[str] = Field(default=None, description="Neo4j username")
    neo4j_password: Optional[str] = Field(default=None, description="Neo4j password")
    
    # External knowledge base settings
    yago_endpoint: str = Field(default="https://yago-knowledge.org/sparql/query", description="YAGO SPARQL endpoint")
    conceptnet_api_base: str = Field(default="http://api.conceptnet.io", description="ConceptNet API base URL")
    
    # Redis settings for caching
    redis_host: str = Field(default="localhost", description="Redis host")
    redis_port: int = Field(default=6379, description="Redis port")
    redis_db: int = Field(default=0, description="Redis database number")
    redis_password: Optional[str] = Field(default=None, description="Redis password")
    redis_ssl: bool = Field(default=False, description="Use SSL for Redis connection")
    
    # Cache TTL settings (in seconds)
    cache_embedding_ttl: int = Field(default=86400, description="Embedding cache TTL (24 hours)")
    cache_search_result_ttl: int = Field(default=3600, description="Search result cache TTL (1 hour)")
    cache_conversation_ttl: int = Field(default=7200, description="Conversation cache TTL (2 hours)")
    cache_ai_response_ttl: int = Field(default=1800, description="AI response cache TTL (30 minutes)")
    cache_database_query_ttl: int = Field(default=600, description="Database query cache TTL (10 minutes)")
    cache_analytics_ttl: int = Field(default=300, description="Analytics cache TTL (5 minutes)")
    cache_knowledge_graph_ttl: int = Field(default=3600, description="Knowledge graph cache TTL (1 hour)")
    
    # Cache size limits
    cache_max_memory_mb: int = Field(default=512, description="Maximum cache memory in MB")
    cache_max_entries_per_type: int = Field(default=10000, description="Maximum entries per cache type")
    
    # Cache performance settings
    cache_compression_enabled: bool = Field(default=True, description="Enable cache compression")
    cache_compression_threshold: int = Field(default=1024, description="Compression threshold in bytes")
    cache_batch_size: int = Field(default=100, description="Cache batch operation size")
    
    # Cache feature flags
    cache_enable_embedding: bool = Field(default=True, description="Enable embedding caching")
    cache_enable_search: bool = Field(default=True, description="Enable search result caching")
    cache_enable_conversation: bool = Field(default=True, description="Enable conversation caching")
    cache_enable_ai_response: bool = Field(default=True, description="Enable AI response caching")
    cache_enable_database: bool = Field(default=True, description="Enable database query caching")
    cache_enable_analytics: bool = Field(default=True, description="Enable analytics caching")
    cache_enable_knowledge_graph: bool = Field(default=True, description="Enable knowledge graph caching")
    
    # Comprehensive logging settings
    logging_enable_structured: bool = Field(default=True, description="Enable structured logging")
    logging_enable_distributed_tracing: bool = Field(default=True, description="Enable distributed tracing")
    logging_enable_performance_tracking: bool = Field(default=True, description="Enable performance tracking")
    logging_enable_business_metrics: bool = Field(default=True, description="Enable business metrics")
    logging_enable_error_tracking: bool = Field(default=True, description="Enable error tracking")
    logging_enable_audit_trail: bool = Field(default=True, description="Enable audit trail")
    
    # Logging retention settings
    logging_retention_days: int = Field(default=30, description="Log retention period in days")
    logging_max_entries: int = Field(default=50000, description="Maximum log entries to keep in memory")
    logging_export_enabled: bool = Field(default=True, description="Enable log export functionality")
    
    # Distributed tracing settings
    tracing_sample_rate: float = Field(default=1.0, description="Tracing sample rate (0.0 to 1.0)")
    tracing_max_spans: int = Field(default=5000, description="Maximum spans to keep in memory")
    
    # Performance monitoring settings
    performance_alert_threshold_ms: int = Field(default=5000, description="Performance alert threshold in milliseconds")
    performance_error_rate_threshold: float = Field(default=5.0, description="Error rate alert threshold percentage")
    
    # Business metrics settings
    business_metrics_aggregation_interval: int = Field(default=300, description="Business metrics aggregation interval in seconds")
    business_metrics_retention_hours: int = Field(default=168, description="Business metrics retention in hours (7 days)")
    
    # Error tracking settings
    error_pattern_max_entries: int = Field(default=100, description="Maximum error entries per pattern")
    error_alert_threshold: int = Field(default=10, description="Error count threshold for alerts")
    
    # Audit logging settings
    audit_log_sensitive_data: bool = Field(default=False, description="Include sensitive data in audit logs")
    audit_log_user_actions: bool = Field(default=True, description="Log user actions")
    audit_log_system_events: bool = Field(default=True, description="Log system events")
    audit_log_security_events: bool = Field(default=True, description="Log security events")
    
    def __init__(self, **kwargs):
        """Initialize settings and create necessary directories."""
        super().__init__(**kwargs)
        self._create_directories()
    
    def _create_directories(self) -> None:
        """Create necessary directories if they don't exist."""
        directories = [self.upload_dir, self.media_dir, self.export_dir]
        for directory in directories:
            try:
                os.makedirs(directory, exist_ok=True)
            except (OSError, PermissionError) as e:
                # Skip directory creation if we don't have permissions
                # This is common in containerized environments or during testing
                pass
    
    def is_local_environment(self) -> bool:
        """Check if running in local development environment."""
        ml_env = os.getenv("ML_ENVIRONMENT", "local").lower()
        db_type = os.getenv("DATABASE_TYPE", "local").lower()
        return ml_env in ["local", "development", "dev"] or db_type == "local"
    
    def is_aws_environment(self) -> bool:
        """Check if running in AWS production environment."""
        ml_env = os.getenv("ML_ENVIRONMENT", "local").lower()
        db_type = os.getenv("DATABASE_TYPE", "local").lower()
        return ml_env in ["aws", "production", "prod"] or db_type == "aws"
    
    def get_database_backend(self) -> str:
        """Get the database backend type."""
        if self.is_local_environment():
            return "local"
        elif self.is_aws_environment():
            return "aws"
        else:
            return "local"  # Default to local
    
    def get_enabled_features(self) -> list:
        """Get list of enabled features."""
        features = []
        # Add basic features that are always available
        features.extend(["api", "health_checks", "configuration"])
        
        # Add conditional features based on API keys
        if self.google_api_key or self.gemini_api_key:
            features.append("gemini_integration")
        
        return features
    
    def get_environment_info(self) -> dict:
        """Get environment information."""
        return {
            "environment": get_environment_type(),
            "database_backend": self.get_database_backend(),
            "is_local": self.is_local_environment(),
            "is_aws": self.is_aws_environment(),
            "debug_mode": self.debug,
            "features_enabled": self.get_enabled_features(),
        }


@lru_cache()
def get_settings() -> Settings:
    """Get cached application settings."""
    return Settings()


def reload_settings() -> Settings:
    """Reload settings (useful for testing and development)."""
    get_settings.cache_clear()
    return get_settings()


def get_environment_type() -> str:
    """Get the current environment type."""
    settings = get_settings()
    ml_env = os.getenv("ML_ENVIRONMENT", "local").lower()
    db_type = os.getenv("DATABASE_TYPE", "local").lower()
    
    if ml_env in ["aws", "production", "prod"] or db_type == "aws":
        return "aws"
    else:
        return "local"


def is_local_development() -> bool:
    """Check if running in local development mode."""
    return get_environment_type() == "local"


def is_aws_production() -> bool:
    """Check if running in AWS production mode."""
    return get_environment_type() == "aws"


def validate_environment_configuration() -> dict:
    """Validate the current environment configuration."""
    settings = get_settings()
    env_type = get_environment_type()
    
    validation_results = {
        "valid": True,
        "errors": [],
        "warnings": [],
        "environment": env_type,
        "features_enabled": [],
    }
    
    # Basic validation
    if env_type == "aws":
        # Check for AWS-specific requirements
        if not os.getenv("AWS_REGION"):
            validation_results["warnings"].append("AWS_REGION not set")
    
    # Check API keys for AI features (Gemini only)
    if not any([settings.google_api_key, settings.gemini_api_key]):
        validation_results["warnings"].append("No Gemini API key configured - AI features will be limited")
    
    return validation_results