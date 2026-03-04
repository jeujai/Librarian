"""
Local Services Logging Configuration

This module provides configuration for structured logging of local development services.
It defines logging levels, output formats, retention policies, and service-specific
configurations for PostgreSQL, Neo4j, Milvus, Redis, and other local services.
"""

import os
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path

from ..config import get_settings


class LogFormat(Enum):
    """Log output formats."""
    JSON = "json"
    STRUCTURED = "structured"
    PLAIN = "plain"
    DOCKER = "docker"


class LogLevel(Enum):
    """Log levels for local services."""
    DEBUG = "DEBUG"
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"


@dataclass
class ServiceLoggingConfig:
    """Configuration for a specific service's logging."""
    service_name: str
    container_name: str
    log_level: LogLevel = LogLevel.INFO
    log_format: LogFormat = LogFormat.JSON
    enable_metrics_extraction: bool = True
    enable_error_detection: bool = True
    enable_performance_monitoring: bool = True
    custom_log_patterns: Dict[str, str] = field(default_factory=dict)
    custom_metrics_patterns: Dict[str, str] = field(default_factory=dict)
    log_file_path: Optional[str] = None
    max_log_size_mb: int = 100
    log_retention_days: int = 7
    enable_log_rotation: bool = True


@dataclass
class LocalLoggingConfig:
    """Main configuration for local services logging."""
    # Global settings
    enable_local_logging: bool = True
    log_output_directory: str = "./logs/local_services"
    global_log_level: LogLevel = LogLevel.INFO
    global_log_format: LogFormat = LogFormat.JSON
    
    # Monitoring settings
    enable_health_monitoring: bool = True
    health_check_interval_seconds: int = 30
    enable_performance_metrics: bool = True
    metrics_collection_interval_seconds: int = 60
    
    # Log processing settings
    log_buffer_size: int = 10000
    log_processing_batch_size: int = 100
    log_processing_interval_seconds: float = 0.1
    
    # Retention and archival
    default_retention_days: int = 30
    enable_log_compression: bool = True
    enable_log_archival: bool = True
    archive_directory: str = "./logs/archive"
    
    # Error handling
    enable_error_alerting: bool = True
    error_alert_threshold: int = 5  # errors per minute
    enable_error_pattern_detection: bool = True
    
    # Service-specific configurations
    service_configs: Dict[str, ServiceLoggingConfig] = field(default_factory=dict)
    
    def __post_init__(self):
        """Initialize default service configurations."""
        if not self.service_configs:
            self.service_configs = self._create_default_service_configs()
    
    def _create_default_service_configs(self) -> Dict[str, ServiceLoggingConfig]:
        """Create default configurations for all local services."""
        return {
            'postgres': ServiceLoggingConfig(
                service_name='postgres',
                container_name='multimodal-librarian-local-postgres-1',
                log_level=LogLevel.INFO,
                enable_metrics_extraction=True,
                custom_log_patterns={
                    'slow_query': r'duration: ([\d.]+) ms.*statement: (.+)',
                    'connection_event': r'connection (authorized|received|terminated)',
                    'checkpoint': r'checkpoint (starting|complete)',
                    'autovacuum': r'automatic (vacuum|analyze)',
                    'lock_timeout': r'canceling statement due to lock timeout',
                    'deadlock': r'deadlock detected'
                },
                custom_metrics_patterns={
                    'query_duration_ms': r'duration: ([\d.]+) ms',
                    'connections_count': r'connection authorized: user=(\w+)',
                    'buffer_usage': r'buffer usage: ([\d.]+)',
                    'checkpoint_duration': r'checkpoint complete: wrote (\d+) buffers'
                }
            ),
            'neo4j': ServiceLoggingConfig(
                service_name='neo4j',
                container_name='multimodal-librarian-local-neo4j-1',
                log_level=LogLevel.INFO,
                enable_metrics_extraction=True,
                custom_log_patterns={
                    'cypher_query': r'Query `(.+)` took (\d+) ms',
                    'bolt_connection': r'Bolt session \[(.+)\] (OPEN|CLOSE)',
                    'transaction': r'Transaction \[(.+)\] (started|committed|rolled back)',
                    'memory_warning': r'WARNING.*memory',
                    'gds_operation': r'GDS.*operation: (.+)',
                    'apoc_operation': r'APOC.*procedure: (.+)'
                },
                custom_metrics_patterns={
                    'query_execution_time_ms': r'took (\d+) ms',
                    'memory_usage_mb': r'memory usage: ([\d.]+)MB',
                    'active_transactions': r'active transactions: (\d+)',
                    'page_cache_hits': r'page cache hits: (\d+)',
                    'page_cache_misses': r'page cache misses: (\d+)'
                }
            ),
            'milvus': ServiceLoggingConfig(
                service_name='milvus',
                container_name='multimodal-librarian-local-milvus-1',
                log_level=LogLevel.INFO,
                enable_metrics_extraction=True,
                custom_log_patterns={
                    'search_operation': r'search.*collection: (\w+).*topk: (\d+)',
                    'insert_operation': r'insert.*collection: (\w+).*rows: (\d+)',
                    'index_operation': r'index.*collection: (\w+).*field: (\w+)',
                    'collection_operation': r'(create|drop|load|release) collection: (\w+)',
                    'segment_operation': r'segment.*operation: (.+)',
                    'flush_operation': r'flush.*collection: (\w+)'
                },
                custom_metrics_patterns={
                    'search_latency_ms': r'search latency: ([\d.]+)ms',
                    'insert_rate_per_sec': r'insert rate: ([\d.]+) vectors/s',
                    'index_progress_percent': r'index progress: ([\d.]+)%',
                    'memory_usage_mb': r'memory usage: ([\d.]+)MB',
                    'disk_usage_mb': r'disk usage: ([\d.]+)MB',
                    'collection_size': r'collection size: (\d+) vectors'
                }
            ),
            'redis': ServiceLoggingConfig(
                service_name='redis',
                container_name='multimodal-librarian-local-redis-1',
                log_level=LogLevel.INFO,
                enable_metrics_extraction=True,
                custom_log_patterns={
                    'client_connection': r'Accepted (\d+\.\d+\.\d+\.\d+:\d+)',
                    'client_disconnection': r'Client closed connection',
                    'command_execution': r'Client addr=(.+) name=(.+) cmd=(.+)',
                    'memory_warning': r'WARNING.*memory',
                    'persistence_operation': r'(Background saving|AOF rewrite)',
                    'slow_log': r'Slow log entry'
                },
                custom_metrics_patterns={
                    'connected_clients': r'connected_clients:(\d+)',
                    'used_memory_mb': r'used_memory:(\d+)',
                    'ops_per_sec': r'instantaneous_ops_per_sec:(\d+)',
                    'keyspace_hits': r'keyspace_hits:(\d+)',
                    'keyspace_misses': r'keyspace_misses:(\d+)',
                    'expired_keys': r'expired_keys:(\d+)'
                }
            ),
            'etcd': ServiceLoggingConfig(
                service_name='etcd',
                container_name='multimodal-librarian-local-etcd-1',
                log_level=LogLevel.INFO,
                enable_metrics_extraction=True,
                custom_log_patterns={
                    'raft_operation': r'raft.*term: (\d+).*index: (\d+)',
                    'leader_election': r'(became leader|lost leadership)',
                    'client_request': r'client request.*method: (\w+)',
                    'compaction': r'compaction.*revision: (\d+)',
                    'snapshot': r'snapshot.*index: (\d+)',
                    'member_change': r'member.*added|removed'
                },
                custom_metrics_patterns={
                    'request_duration_ms': r'request duration: ([\d.]+)ms',
                    'raft_term': r'term: (\d+)',
                    'raft_index': r'index: (\d+)',
                    'db_size_mb': r'database size: ([\d.]+)MB',
                    'active_connections': r'active connections: (\d+)'
                }
            ),
            'minio': ServiceLoggingConfig(
                service_name='minio',
                container_name='multimodal-librarian-local-minio-1',
                log_level=LogLevel.INFO,
                enable_metrics_extraction=True,
                custom_log_patterns={
                    'api_request': r'API: (\w+) (.+) \[(.+)\]',
                    'storage_operation': r'Storage: (PUT|GET|DELETE) (.+)',
                    'bucket_operation': r'Bucket: (create|delete) (.+)',
                    'healing_operation': r'Healing.*object: (.+)',
                    'replication': r'Replication.*bucket: (.+)',
                    'lifecycle': r'Lifecycle.*action: (.+)'
                },
                custom_metrics_patterns={
                    'request_duration_ms': r'request_time:([\d.]+)ms',
                    'bytes_received': r'bytes_received:(\d+)',
                    'bytes_sent': r'bytes_sent:(\d+)',
                    'objects_count': r'objects_count:(\d+)',
                    'storage_used_mb': r'storage_used:([\d.]+)MB'
                }
            )
        }


def get_local_logging_config() -> LocalLoggingConfig:
    """Get the local logging configuration."""
    settings = get_settings()
    
    # Create base configuration
    config = LocalLoggingConfig()
    
    # Override with environment variables if present
    config.enable_local_logging = _get_env_bool('ML_LOCAL_LOGGING_ENABLED', config.enable_local_logging)
    config.log_output_directory = os.getenv('ML_LOCAL_LOG_DIR', config.log_output_directory)
    config.global_log_level = LogLevel(os.getenv('ML_LOCAL_LOG_LEVEL', config.global_log_level.value))
    config.global_log_format = LogFormat(os.getenv('ML_LOCAL_LOG_FORMAT', config.global_log_format.value))
    
    # Health monitoring settings
    config.enable_health_monitoring = _get_env_bool('ML_HEALTH_MONITORING_ENABLED', config.enable_health_monitoring)
    config.health_check_interval_seconds = int(os.getenv('ML_HEALTH_CHECK_INTERVAL', str(config.health_check_interval_seconds)))
    
    # Performance monitoring settings
    config.enable_performance_metrics = _get_env_bool('ML_PERFORMANCE_METRICS_ENABLED', config.enable_performance_metrics)
    config.metrics_collection_interval_seconds = int(os.getenv('ML_METRICS_INTERVAL', str(config.metrics_collection_interval_seconds)))
    
    # Log processing settings
    config.log_buffer_size = int(os.getenv('ML_LOG_BUFFER_SIZE', str(config.log_buffer_size)))
    config.log_processing_batch_size = int(os.getenv('ML_LOG_BATCH_SIZE', str(config.log_processing_batch_size)))
    
    # Retention settings
    config.default_retention_days = int(os.getenv('ML_LOG_RETENTION_DAYS', str(config.default_retention_days)))
    config.enable_log_compression = _get_env_bool('ML_LOG_COMPRESSION_ENABLED', config.enable_log_compression)
    config.enable_log_archival = _get_env_bool('ML_LOG_ARCHIVAL_ENABLED', config.enable_log_archival)
    config.archive_directory = os.getenv('ML_LOG_ARCHIVE_DIR', config.archive_directory)
    
    # Error handling settings
    config.enable_error_alerting = _get_env_bool('ML_ERROR_ALERTING_ENABLED', config.enable_error_alerting)
    config.error_alert_threshold = int(os.getenv('ML_ERROR_ALERT_THRESHOLD', str(config.error_alert_threshold)))
    
    # Ensure directories exist
    _ensure_directories_exist(config)
    
    return config


def _get_env_bool(env_var: str, default: bool) -> bool:
    """Get boolean value from environment variable."""
    value = os.getenv(env_var, str(default)).lower()
    return value in ('true', '1', 'yes', 'on', 'enabled')


def _ensure_directories_exist(config: LocalLoggingConfig) -> None:
    """Ensure all required directories exist."""
    directories = [
        config.log_output_directory,
        config.archive_directory
    ]
    
    for directory in directories:
        Path(directory).mkdir(parents=True, exist_ok=True)


def get_service_logging_config(service_name: str) -> Optional[ServiceLoggingConfig]:
    """Get logging configuration for a specific service."""
    config = get_local_logging_config()
    return config.service_configs.get(service_name)


def update_service_logging_config(service_name: str, updates: Dict[str, Any]) -> None:
    """Update logging configuration for a specific service."""
    config = get_local_logging_config()
    
    if service_name in config.service_configs:
        service_config = config.service_configs[service_name]
        
        # Update configuration fields
        for key, value in updates.items():
            if hasattr(service_config, key):
                setattr(service_config, key, value)


def create_docker_logging_config() -> Dict[str, Any]:
    """Create Docker Compose logging configuration for local services."""
    config = get_local_logging_config()
    
    if not config.enable_local_logging:
        return {}
    
    # Base logging configuration for Docker Compose
    base_logging = {
        "driver": "json-file",
        "options": {
            "max-size": "10m",
            "max-file": "3",
            "labels": "service,environment"
        }
    }
    
    # Service-specific logging configurations
    service_logging_configs = {}
    
    for service_name, service_config in config.service_configs.items():
        service_logging_configs[service_name] = {
            "logging": {
                **base_logging,
                "options": {
                    **base_logging["options"],
                    "tag": f"multimodal-librarian-{service_name}",
                    "labels": f"service={service_name},environment=local"
                }
            }
        }
    
    return service_logging_configs


def get_log_aggregation_rules() -> List[Dict[str, Any]]:
    """Get log aggregation rules for local services."""
    return [
        {
            "name": "postgres_slow_queries",
            "service_pattern": "postgres",
            "log_pattern": r"duration: (\d+\.\d+) ms.*statement:",
            "threshold_ms": 1000,
            "action": "alert"
        },
        {
            "name": "neo4j_memory_warnings",
            "service_pattern": "neo4j",
            "log_pattern": r"WARNING.*memory",
            "action": "alert"
        },
        {
            "name": "milvus_search_performance",
            "service_pattern": "milvus",
            "log_pattern": r"search latency: ([\d.]+)ms",
            "threshold_ms": 500,
            "action": "monitor"
        },
        {
            "name": "redis_memory_usage",
            "service_pattern": "redis",
            "log_pattern": r"used_memory:([\d.]+)",
            "threshold_mb": 200,
            "action": "monitor"
        },
        {
            "name": "service_errors",
            "service_pattern": "*",
            "log_pattern": r"ERROR|FATAL|CRITICAL",
            "action": "alert"
        },
        {
            "name": "connection_issues",
            "service_pattern": "*",
            "log_pattern": r"connection.*failed|timeout|refused",
            "action": "alert"
        }
    ]


def get_performance_monitoring_config() -> Dict[str, Any]:
    """Get performance monitoring configuration for local services."""
    return {
        "enable_monitoring": True,
        "collection_interval_seconds": 60,
        "metrics_to_collect": [
            "cpu_usage_percent",
            "memory_usage_mb",
            "disk_io_mb_per_sec",
            "network_io_mb_per_sec",
            "container_restart_count"
        ],
        "service_specific_metrics": {
            "postgres": [
                "active_connections",
                "query_duration_avg_ms",
                "buffer_hit_ratio",
                "checkpoint_frequency"
            ],
            "neo4j": [
                "bolt_connections",
                "cypher_query_count",
                "page_cache_hit_ratio",
                "transaction_count"
            ],
            "milvus": [
                "search_requests_per_sec",
                "insert_requests_per_sec",
                "index_build_progress",
                "collection_count"
            ],
            "redis": [
                "connected_clients",
                "operations_per_sec",
                "keyspace_hit_ratio",
                "memory_fragmentation_ratio"
            ]
        },
        "alert_thresholds": {
            "cpu_usage_percent": 80,
            "memory_usage_percent": 85,
            "disk_usage_percent": 90,
            "error_rate_per_minute": 5,
            "response_time_ms": 1000
        }
    }


def export_logging_config_to_file(filepath: str = "local_logging_config.json") -> str:
    """Export the current logging configuration to a JSON file."""
    import json
    
    config = get_local_logging_config()
    
    # Convert to serializable format
    config_dict = {
        "enable_local_logging": config.enable_local_logging,
        "log_output_directory": config.log_output_directory,
        "global_log_level": config.global_log_level.value,
        "global_log_format": config.global_log_format.value,
        "enable_health_monitoring": config.enable_health_monitoring,
        "health_check_interval_seconds": config.health_check_interval_seconds,
        "enable_performance_metrics": config.enable_performance_metrics,
        "metrics_collection_interval_seconds": config.metrics_collection_interval_seconds,
        "log_buffer_size": config.log_buffer_size,
        "log_processing_batch_size": config.log_processing_batch_size,
        "default_retention_days": config.default_retention_days,
        "enable_log_compression": config.enable_log_compression,
        "enable_log_archival": config.enable_log_archival,
        "archive_directory": config.archive_directory,
        "enable_error_alerting": config.enable_error_alerting,
        "error_alert_threshold": config.error_alert_threshold,
        "service_configs": {
            name: {
                "service_name": svc_config.service_name,
                "container_name": svc_config.container_name,
                "log_level": svc_config.log_level.value,
                "log_format": svc_config.log_format.value,
                "enable_metrics_extraction": svc_config.enable_metrics_extraction,
                "enable_error_detection": svc_config.enable_error_detection,
                "enable_performance_monitoring": svc_config.enable_performance_monitoring,
                "custom_log_patterns": svc_config.custom_log_patterns,
                "custom_metrics_patterns": svc_config.custom_metrics_patterns,
                "max_log_size_mb": svc_config.max_log_size_mb,
                "log_retention_days": svc_config.log_retention_days,
                "enable_log_rotation": svc_config.enable_log_rotation
            }
            for name, svc_config in config.service_configs.items()
        },
        "log_aggregation_rules": get_log_aggregation_rules(),
        "performance_monitoring": get_performance_monitoring_config()
    }
    
    # Write to file
    with open(filepath, 'w') as f:
        json.dump(config_dict, f, indent=2)
    
    return filepath