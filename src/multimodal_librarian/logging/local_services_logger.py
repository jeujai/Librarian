"""
Local Services Structured Logging Configuration

This module configures structured logging for local development services including:
- PostgreSQL database logging
- Neo4j graph database logging  
- Milvus vector database logging
- Redis cache logging
- Docker container logging
- Service health monitoring logging

Key Features:
- Centralized log collection from all local services
- Structured JSON format for easy parsing and analysis
- Service-specific log parsing and enrichment
- Performance metrics extraction from service logs
- Error pattern detection and alerting
- Integration with existing structured logging infrastructure
"""

import asyncio
import json
import logging
import os
import re
import subprocess
import threading
import time
from collections import defaultdict, deque
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

import docker

from ..config import get_settings
from ..logging_config import get_logger
from ..monitoring.structured_logging_service import (
    get_structured_logging_service,
    log_error_structured,
    log_info_structured,
    log_warning_structured,
)


class ServiceType(Enum):
    """Types of local services being monitored."""
    POSTGRESQL = "postgresql"
    NEO4J = "neo4j"
    MILVUS = "milvus"
    REDIS = "redis"
    ETCD = "etcd"
    MINIO = "minio"
    APPLICATION = "application"


@dataclass
class ServiceLogEntry:
    """Structured log entry for local services."""
    timestamp: datetime
    service_type: ServiceType
    service_name: str
    container_name: str
    log_level: str
    message: str
    raw_log: str
    parsed_data: Dict[str, Any] = field(default_factory=dict)
    metrics: Dict[str, float] = field(default_factory=dict)
    error_info: Optional[Dict[str, Any]] = None
    correlation_id: Optional[str] = None


@dataclass
class ServiceHealthMetrics:
    """Health metrics for a local service."""
    service_type: ServiceType
    service_name: str
    container_name: str
    is_healthy: bool
    cpu_usage_percent: float
    memory_usage_mb: float
    disk_usage_mb: float
    network_io_mb: float
    uptime_seconds: float
    restart_count: int
    last_error: Optional[str] = None
    last_error_time: Optional[datetime] = None
    performance_metrics: Dict[str, float] = field(default_factory=dict)


class LocalServicesLogger:
    """
    Structured logging system for local development services.
    
    Monitors and collects logs from all Docker containers running local services,
    parses service-specific log formats, extracts metrics, and integrates with
    the main structured logging infrastructure.
    """
    
    def __init__(self):
        """Initialize the local services logger."""
        self.settings = get_settings()
        self.logger = get_logger("local_services_logger")
        self.structured_logging = get_structured_logging_service()
        
        # Docker client for container monitoring
        try:
            self.docker_client = docker.from_env()
        except Exception as e:
            self.logger.error(f"Failed to initialize Docker client: {e}")
            self.docker_client = None
        
        # Service configuration
        self.service_configs = self._load_service_configs()
        
        # Log storage and processing
        self._service_logs = deque(maxlen=50000)  # Last 50k service logs
        self._service_metrics = {}  # Current metrics for each service
        self._log_parsers = self._initialize_log_parsers()
        
        # Monitoring state
        self._monitoring_active = False
        self._monitoring_tasks = []
        self._log_processing_lock = threading.Lock()
        
        # Performance tracking
        self._processing_stats = {
            'logs_processed': 0,
            'logs_per_second': 0,
            'parsing_errors': 0,
            'last_processing_time': datetime.now()
        }
        
        self.logger.info("LocalServicesLogger initialized")
    
    def _load_service_configs(self) -> Dict[str, Dict[str, Any]]:
        """Load configuration for each local service."""
        return {
            'postgres': {
                'container_name': 'multimodal-librarian-local-postgres-1',
                'service_type': ServiceType.POSTGRESQL,
                'log_patterns': {
                    'error': r'ERROR:',
                    'warning': r'WARNING:',
                    'info': r'LOG:',
                    'statement': r'STATEMENT:',
                    'connection': r'connection',
                    'checkpoint': r'checkpoint'
                },
                'metrics_patterns': {
                    'duration': r'duration: ([\d.]+) ms',
                    'connections': r'connection authorized: user=(\w+)',
                    'queries': r'execute \w+: (.+)'
                }
            },
            'neo4j': {
                'container_name': 'multimodal-librarian-local-neo4j-1',
                'service_type': ServiceType.NEO4J,
                'log_patterns': {
                    'error': r'ERROR',
                    'warning': r'WARN',
                    'info': r'INFO',
                    'query': r'Query',
                    'transaction': r'Transaction',
                    'bolt': r'Bolt'
                },
                'metrics_patterns': {
                    'query_time': r'Query execution time: ([\d.]+)ms',
                    'memory_usage': r'Memory usage: ([\d.]+)MB',
                    'active_transactions': r'Active transactions: (\d+)'
                }
            },
            'milvus': {
                'container_name': 'multimodal-librarian-local-milvus-1',
                'service_type': ServiceType.MILVUS,
                'log_patterns': {
                    'error': r'\[ERROR\]',
                    'warning': r'\[WARN\]',
                    'info': r'\[INFO\]',
                    'debug': r'\[DEBUG\]',
                    'search': r'search',
                    'insert': r'insert',
                    'index': r'index'
                },
                'metrics_patterns': {
                    'search_latency': r'search latency: ([\d.]+)ms',
                    'insert_rate': r'insert rate: ([\d.]+) vectors/s',
                    'index_progress': r'index progress: ([\d.]+)%'
                }
            },
            'redis': {
                'container_name': 'multimodal-librarian-local-redis-1',
                'service_type': ServiceType.REDIS,
                'log_patterns': {
                    'error': r'# ERROR',
                    'warning': r'# WARNING',
                    'info': r'# INFO',
                    'connection': r'Accepted',
                    'command': r'Client'
                },
                'metrics_patterns': {
                    'memory_usage': r'used_memory_human:([\d.]+[KMG]B)',
                    'connected_clients': r'connected_clients:(\d+)',
                    'ops_per_sec': r'instantaneous_ops_per_sec:(\d+)'
                }
            },
            'etcd': {
                'container_name': 'multimodal-librarian-local-etcd-1',
                'service_type': ServiceType.ETCD,
                'log_patterns': {
                    'error': r'ERROR',
                    'warning': r'WARNING',
                    'info': r'INFO',
                    'raft': r'raft',
                    'election': r'election'
                },
                'metrics_patterns': {
                    'request_duration': r'request duration: ([\d.]+)ms',
                    'leader_changes': r'leader changed from \w+ to (\w+)'
                }
            },
            'minio': {
                'container_name': 'multimodal-librarian-local-minio-1',
                'service_type': ServiceType.MINIO,
                'log_patterns': {
                    'error': r'ERROR',
                    'warning': r'WARNING',
                    'info': r'INFO',
                    'api': r'API:',
                    'storage': r'Storage:'
                },
                'metrics_patterns': {
                    'request_time': r'request_time:([\d.]+)ms',
                    'bytes_received': r'bytes_received:(\d+)',
                    'bytes_sent': r'bytes_sent:(\d+)'
                }
            }
        }
    
    def _initialize_log_parsers(self) -> Dict[ServiceType, callable]:
        """Initialize service-specific log parsers."""
        return {
            ServiceType.POSTGRESQL: self._parse_postgresql_log,
            ServiceType.NEO4J: self._parse_neo4j_log,
            ServiceType.MILVUS: self._parse_milvus_log,
            ServiceType.REDIS: self._parse_redis_log,
            ServiceType.ETCD: self._parse_etcd_log,
            ServiceType.MINIO: self._parse_minio_log
        }
    
    async def start_monitoring(self) -> None:
        """Start monitoring all local services."""
        if self._monitoring_active:
            self.logger.warning("Local services monitoring already active")
            return
        
        if not self.docker_client:
            self.logger.error("Cannot start monitoring: Docker client not available")
            return
        
        self._monitoring_active = True
        
        # Start monitoring tasks for each service
        for service_name, config in self.service_configs.items():
            task = asyncio.create_task(
                self._monitor_service_logs(service_name, config)
            )
            self._monitoring_tasks.append(task)
        
        # Start health monitoring task
        health_task = asyncio.create_task(self._monitor_service_health())
        self._monitoring_tasks.append(health_task)
        
        # Start log processing task
        processing_task = asyncio.create_task(self._process_log_queue())
        self._monitoring_tasks.append(processing_task)
        
        self.logger.info("Started monitoring local services")
        
        # Log monitoring start
        log_info_structured(
            service="local_services_logger",
            operation="start_monitoring",
            message="Started monitoring local development services",
            metadata={
                'services_count': len(self.service_configs),
                'services': list(self.service_configs.keys())
            },
            tags={'category': 'monitoring', 'action': 'start'}
        )
    
    async def stop_monitoring(self) -> None:
        """Stop monitoring all local services."""
        if not self._monitoring_active:
            return
        
        self._monitoring_active = False
        
        # Cancel all monitoring tasks
        for task in self._monitoring_tasks:
            if not task.done():
                task.cancel()
        
        # Wait for tasks to complete
        if self._monitoring_tasks:
            await asyncio.gather(*self._monitoring_tasks, return_exceptions=True)
        
        self._monitoring_tasks.clear()
        
        self.logger.info("Stopped monitoring local services")
        
        # Log monitoring stop
        log_info_structured(
            service="local_services_logger",
            operation="stop_monitoring",
            message="Stopped monitoring local development services",
            metadata=self._processing_stats.copy(),
            tags={'category': 'monitoring', 'action': 'stop'}
        )
    
    async def _monitor_service_logs(self, service_name: str, config: Dict[str, Any]) -> None:
        """Monitor logs for a specific service."""
        container_name = config['container_name']
        service_type = config['service_type']
        
        try:
            # Get container
            container = self.docker_client.containers.get(container_name)
            
            # Stream logs
            log_stream = container.logs(stream=True, follow=True, tail=100)
            
            self.logger.info(f"Started monitoring logs for {service_name} ({container_name})")
            
            for log_line in log_stream:
                if not self._monitoring_active:
                    break
                
                try:
                    # Decode log line
                    log_text = log_line.decode('utf-8').strip()
                    if not log_text:
                        continue
                    
                    # Parse log entry
                    log_entry = await self._parse_service_log(
                        service_name, service_type, container_name, log_text, config
                    )
                    
                    if log_entry:
                        # Add to processing queue
                        with self._log_processing_lock:
                            self._service_logs.append(log_entry)
                        
                        # Update processing stats
                        self._processing_stats['logs_processed'] += 1
                
                except Exception as e:
                    self.logger.debug(f"Error processing log line for {service_name}: {e}")
                    self._processing_stats['parsing_errors'] += 1
        
        except docker.errors.NotFound:
            self.logger.warning(f"Container not found: {container_name}")
        except Exception as e:
            self.logger.error(f"Error monitoring {service_name} logs: {e}")
    
    async def _parse_service_log(self, service_name: str, service_type: ServiceType, 
                                container_name: str, log_text: str, 
                                config: Dict[str, Any]) -> Optional[ServiceLogEntry]:
        """Parse a service log line into structured format."""
        
        # Extract timestamp (try multiple formats)
        timestamp = self._extract_timestamp(log_text)
        
        # Determine log level
        log_level = self._extract_log_level(log_text, config['log_patterns'])
        
        # Extract metrics
        metrics = self._extract_metrics(log_text, config.get('metrics_patterns', {}))
        
        # Parse service-specific data
        parsed_data = {}
        error_info = None
        
        if service_type in self._log_parsers:
            try:
                parsed_data, error_info = self._log_parsers[service_type](log_text)
            except Exception as e:
                self.logger.debug(f"Error parsing {service_type.value} log: {e}")
        
        return ServiceLogEntry(
            timestamp=timestamp,
            service_type=service_type,
            service_name=service_name,
            container_name=container_name,
            log_level=log_level,
            message=log_text,
            raw_log=log_text,
            parsed_data=parsed_data,
            metrics=metrics,
            error_info=error_info
        )
    
    def _extract_timestamp(self, log_text: str) -> datetime:
        """Extract timestamp from log text."""
        # Try common timestamp patterns
        patterns = [
            r'(\d{4}-\d{2}-\d{2}[T\s]\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})?)',
            r'(\d{2}/\d{2}/\d{4} \d{2}:\d{2}:\d{2})',
            r'(\w{3} \d{2} \d{2}:\d{2}:\d{2})'
        ]
        
        for pattern in patterns:
            match = re.search(pattern, log_text)
            if match:
                try:
                    timestamp_str = match.group(1)
                    # Try parsing with different formats
                    for fmt in ['%Y-%m-%dT%H:%M:%S.%fZ', '%Y-%m-%d %H:%M:%S.%f',
                               '%Y-%m-%d %H:%M:%S', '%m/%d/%Y %H:%M:%S']:
                        try:
                            return datetime.strptime(timestamp_str, fmt)
                        except ValueError:
                            continue
                except Exception:
                    pass
        
        # Default to current time if no timestamp found
        return datetime.now()
    
    def _extract_log_level(self, log_text: str, patterns: Dict[str, str]) -> str:
        """Extract log level from log text."""
        log_text_upper = log_text.upper()
        
        # Check for explicit patterns first
        for level, pattern in patterns.items():
            if re.search(pattern, log_text, re.IGNORECASE):
                return level.upper()
        
        # Fallback to common level indicators
        if any(word in log_text_upper for word in ['ERROR', 'FATAL', 'CRITICAL']):
            return 'ERROR'
        elif any(word in log_text_upper for word in ['WARN', 'WARNING']):
            return 'WARNING'
        elif any(word in log_text_upper for word in ['INFO', 'INFORMATION']):
            return 'INFO'
        elif any(word in log_text_upper for word in ['DEBUG', 'TRACE']):
            return 'DEBUG'
        else:
            return 'INFO'  # Default level
    
    def _extract_metrics(self, log_text: str, patterns: Dict[str, str]) -> Dict[str, float]:
        """Extract numeric metrics from log text."""
        metrics = {}
        
        for metric_name, pattern in patterns.items():
            matches = re.findall(pattern, log_text)
            if matches:
                try:
                    # Take the first match and convert to float
                    value_str = matches[0]
                    # Handle units (MB, KB, etc.)
                    if value_str.endswith('MB'):
                        value = float(value_str[:-2])
                    elif value_str.endswith('KB'):
                        value = float(value_str[:-2]) / 1024
                    elif value_str.endswith('GB'):
                        value = float(value_str[:-2]) * 1024
                    else:
                        value = float(value_str)
                    
                    metrics[metric_name] = value
                except (ValueError, IndexError):
                    pass
        
        return metrics
    
    def _parse_postgresql_log(self, log_text: str) -> Tuple[Dict[str, Any], Optional[Dict[str, Any]]]:
        """Parse PostgreSQL-specific log data."""
        parsed_data = {}
        error_info = None
        
        # Extract SQL statements
        if 'STATEMENT:' in log_text:
            statement_match = re.search(r'STATEMENT:\s*(.+)', log_text)
            if statement_match:
                parsed_data['sql_statement'] = statement_match.group(1).strip()
        
        # Extract connection info
        if 'connection' in log_text.lower():
            if 'authorized' in log_text:
                user_match = re.search(r'user=(\w+)', log_text)
                db_match = re.search(r'database=(\w+)', log_text)
                if user_match:
                    parsed_data['user'] = user_match.group(1)
                if db_match:
                    parsed_data['database'] = db_match.group(1)
        
        # Extract error details
        if 'ERROR:' in log_text:
            error_match = re.search(r'ERROR:\s*(.+)', log_text)
            if error_match:
                error_info = {
                    'error_message': error_match.group(1).strip(),
                    'error_type': 'postgresql_error'
                }
        
        return parsed_data, error_info
    
    def _parse_neo4j_log(self, log_text: str) -> Tuple[Dict[str, Any], Optional[Dict[str, Any]]]:
        """Parse Neo4j-specific log data."""
        parsed_data = {}
        error_info = None
        
        # Extract Cypher queries
        if 'Query' in log_text:
            query_match = re.search(r'Query:\s*(.+)', log_text)
            if query_match:
                parsed_data['cypher_query'] = query_match.group(1).strip()
        
        # Extract Bolt connection info
        if 'Bolt' in log_text:
            if 'connected' in log_text.lower():
                parsed_data['connection_event'] = 'bolt_connected'
            elif 'disconnected' in log_text.lower():
                parsed_data['connection_event'] = 'bolt_disconnected'
        
        # Extract error details
        if 'ERROR' in log_text:
            error_match = re.search(r'ERROR\s+(.+)', log_text)
            if error_match:
                error_info = {
                    'error_message': error_match.group(1).strip(),
                    'error_type': 'neo4j_error'
                }
        
        return parsed_data, error_info
    
    def _parse_milvus_log(self, log_text: str) -> Tuple[Dict[str, Any], Optional[Dict[str, Any]]]:
        """Parse Milvus-specific log data."""
        parsed_data = {}
        error_info = None
        
        # Extract operation types
        if 'search' in log_text.lower():
            parsed_data['operation'] = 'search'
        elif 'insert' in log_text.lower():
            parsed_data['operation'] = 'insert'
        elif 'index' in log_text.lower():
            parsed_data['operation'] = 'index'
        
        # Extract collection info
        collection_match = re.search(r'collection[:\s]+(\w+)', log_text, re.IGNORECASE)
        if collection_match:
            parsed_data['collection'] = collection_match.group(1)
        
        # Extract error details
        if '[ERROR]' in log_text:
            error_match = re.search(r'\[ERROR\]\s*(.+)', log_text)
            if error_match:
                error_info = {
                    'error_message': error_match.group(1).strip(),
                    'error_type': 'milvus_error'
                }
        
        return parsed_data, error_info
    
    def _parse_redis_log(self, log_text: str) -> Tuple[Dict[str, Any], Optional[Dict[str, Any]]]:
        """Parse Redis-specific log data."""
        parsed_data = {}
        error_info = None
        
        # Extract client connections
        if 'Accepted' in log_text:
            client_match = re.search(r'Accepted\s+(.+)', log_text)
            if client_match:
                parsed_data['client_connection'] = client_match.group(1).strip()
        
        # Extract commands
        if 'Client' in log_text:
            command_match = re.search(r'Client\s+(.+)', log_text)
            if command_match:
                parsed_data['redis_command'] = command_match.group(1).strip()
        
        # Extract error details
        if '# ERROR' in log_text:
            error_match = re.search(r'# ERROR\s*(.+)', log_text)
            if error_match:
                error_info = {
                    'error_message': error_match.group(1).strip(),
                    'error_type': 'redis_error'
                }
        
        return parsed_data, error_info
    
    def _parse_etcd_log(self, log_text: str) -> Tuple[Dict[str, Any], Optional[Dict[str, Any]]]:
        """Parse etcd-specific log data."""
        parsed_data = {}
        error_info = None
        
        # Extract raft operations
        if 'raft' in log_text.lower():
            parsed_data['component'] = 'raft'
        
        # Extract leader election info
        if 'election' in log_text.lower():
            parsed_data['component'] = 'election'
        
        # Extract error details
        if 'ERROR' in log_text:
            error_match = re.search(r'ERROR\s+(.+)', log_text)
            if error_match:
                error_info = {
                    'error_message': error_match.group(1).strip(),
                    'error_type': 'etcd_error'
                }
        
        return parsed_data, error_info
    
    def _parse_minio_log(self, log_text: str) -> Tuple[Dict[str, Any], Optional[Dict[str, Any]]]:
        """Parse MinIO-specific log data."""
        parsed_data = {}
        error_info = None
        
        # Extract API operations
        if 'API:' in log_text:
            api_match = re.search(r'API:\s*(.+)', log_text)
            if api_match:
                parsed_data['api_operation'] = api_match.group(1).strip()
        
        # Extract storage operations
        if 'Storage:' in log_text:
            storage_match = re.search(r'Storage:\s*(.+)', log_text)
            if storage_match:
                parsed_data['storage_operation'] = storage_match.group(1).strip()
        
        # Extract error details
        if 'ERROR' in log_text:
            error_match = re.search(r'ERROR\s+(.+)', log_text)
            if error_match:
                error_info = {
                    'error_message': error_match.group(1).strip(),
                    'error_type': 'minio_error'
                }
        
        return parsed_data, error_info
    
    async def _process_log_queue(self) -> None:
        """Process queued service logs and send to structured logging."""
        while self._monitoring_active:
            try:
                # Process logs in batches
                logs_to_process = []
                
                with self._log_processing_lock:
                    # Get up to 100 logs for processing
                    for _ in range(min(100, len(self._service_logs))):
                        if self._service_logs:
                            logs_to_process.append(self._service_logs.popleft())
                
                # Process each log
                for log_entry in logs_to_process:
                    await self._process_service_log(log_entry)
                
                # Update processing rate
                self._update_processing_stats(len(logs_to_process))
                
                # Sleep briefly to avoid overwhelming the system
                await asyncio.sleep(0.1)
                
            except Exception as e:
                self.logger.error(f"Error in log processing queue: {e}")
                await asyncio.sleep(1)
    
    async def _process_service_log(self, log_entry: ServiceLogEntry) -> None:
        """Process a single service log entry."""
        try:
            # Generate correlation ID for related logs
            correlation_id = f"service_{log_entry.service_name}_{int(time.time())}"
            
            # Prepare metadata
            metadata = {
                'service_name': log_entry.service_name,
                'container_name': log_entry.container_name,
                'service_type': log_entry.service_type.value,
                'raw_log': log_entry.raw_log,
                'parsed_data': log_entry.parsed_data,
                'metrics': log_entry.metrics
            }
            
            # Prepare tags
            tags = {
                'category': 'service_log',
                'service_type': log_entry.service_type.value,
                'service_name': log_entry.service_name
            }
            
            # Add error information if present
            if log_entry.error_info:
                metadata['error_info'] = log_entry.error_info
                tags['has_error'] = 'true'
            
            # Log to structured logging service
            self.structured_logging.log_structured(
                level=log_entry.log_level,
                service=f"local_service_{log_entry.service_name}",
                operation="service_log",
                message=log_entry.message,
                correlation_id=correlation_id,
                metadata=metadata,
                tags=tags
            )
            
            # Log errors separately for alerting
            if log_entry.error_info:
                log_error_structured(
                    service="local_services_logger",
                    operation="service_error_detected",
                    message=f"Error detected in {log_entry.service_name}: {log_entry.error_info['error_message']}",
                    correlation_id=correlation_id,
                    metadata={
                        'service_name': log_entry.service_name,
                        'error_type': log_entry.error_info.get('error_type'),
                        'error_message': log_entry.error_info.get('error_message'),
                        'raw_log': log_entry.raw_log
                    },
                    tags={'category': 'service_error', 'service': log_entry.service_name}
                )
            
            # Update service metrics if present
            if log_entry.metrics:
                await self._update_service_metrics(log_entry)
        
        except Exception as e:
            self.logger.error(f"Error processing service log: {e}")
    
    async def _update_service_metrics(self, log_entry: ServiceLogEntry) -> None:
        """Update service metrics based on log entry."""
        service_key = f"{log_entry.service_name}_{log_entry.container_name}"
        
        if service_key not in self._service_metrics:
            self._service_metrics[service_key] = {
                'last_updated': datetime.now(),
                'metrics': {},
                'error_count': 0,
                'log_count': 0
            }
        
        service_metrics = self._service_metrics[service_key]
        service_metrics['last_updated'] = datetime.now()
        service_metrics['log_count'] += 1
        
        # Update metrics
        for metric_name, value in log_entry.metrics.items():
            service_metrics['metrics'][metric_name] = value
        
        # Update error count
        if log_entry.error_info:
            service_metrics['error_count'] += 1
    
    async def _monitor_service_health(self) -> None:
        """Monitor health of all local services."""
        while self._monitoring_active:
            try:
                health_metrics = await self._collect_service_health_metrics()
                
                for service_name, metrics in health_metrics.items():
                    # Log health metrics
                    log_info_structured(
                        service="local_services_logger",
                        operation="service_health_check",
                        message=f"Health check for {service_name}",
                        metadata={
                            'service_name': service_name,
                            'is_healthy': metrics.is_healthy,
                            'cpu_usage_percent': metrics.cpu_usage_percent,
                            'memory_usage_mb': metrics.memory_usage_mb,
                            'uptime_seconds': metrics.uptime_seconds,
                            'restart_count': metrics.restart_count,
                            'performance_metrics': metrics.performance_metrics
                        },
                        tags={
                            'category': 'service_health',
                            'service': service_name,
                            'healthy': str(metrics.is_healthy).lower()
                        }
                    )
                    
                    # Alert on unhealthy services
                    if not metrics.is_healthy:
                        log_error_structured(
                            service="local_services_logger",
                            operation="service_unhealthy",
                            message=f"Service {service_name} is unhealthy",
                            metadata={
                                'service_name': service_name,
                                'last_error': metrics.last_error,
                                'last_error_time': metrics.last_error_time.isoformat() if metrics.last_error_time else None,
                                'restart_count': metrics.restart_count
                            },
                            tags={'category': 'service_alert', 'service': service_name, 'alert_type': 'unhealthy'}
                        )
                
                # Sleep for 30 seconds between health checks
                await asyncio.sleep(30)
                
            except Exception as e:
                self.logger.error(f"Error in service health monitoring: {e}")
                await asyncio.sleep(30)
    
    def _collect_service_health_metrics_sync(self) -> Dict[str, ServiceHealthMetrics]:
        """Collect health metrics for all services (synchronous version).
        
        This method contains blocking Docker API calls and should be run in a thread pool.
        """
        health_metrics = {}
        
        if not self.docker_client:
            return health_metrics
        
        try:
            # Get all containers - blocking call
            containers = self.docker_client.containers.list(all=True)
            
            for container in containers:
                # Check if this is one of our monitored services
                container_name = container.name
                service_config = None
                service_name = None
                
                for svc_name, config in self.service_configs.items():
                    if config['container_name'] == container_name:
                        service_config = config
                        service_name = svc_name
                        break
                
                if not service_config:
                    continue
                
                # Get container stats - blocking call
                try:
                    stats = container.stats(stream=False)
                    
                    # Calculate CPU usage
                    cpu_usage = 0.0
                    if 'cpu_stats' in stats and 'precpu_stats' in stats:
                        cpu_delta = stats['cpu_stats']['cpu_usage']['total_usage'] - stats['precpu_stats']['cpu_usage']['total_usage']
                        system_delta = stats['cpu_stats']['system_cpu_usage'] - stats['precpu_stats']['system_cpu_usage']
                        if system_delta > 0:
                            cpu_usage = (cpu_delta / system_delta) * 100.0
                    
                    # Calculate memory usage
                    memory_usage = 0.0
                    if 'memory_stats' in stats and 'usage' in stats['memory_stats']:
                        memory_usage = stats['memory_stats']['usage'] / (1024 * 1024)  # Convert to MB
                    
                    # Get container info - blocking call
                    container.reload()
                    is_healthy = container.status == 'running'
                    
                    # Calculate uptime
                    uptime_seconds = 0.0
                    if container.attrs.get('State', {}).get('StartedAt'):
                        started_at = datetime.fromisoformat(
                            container.attrs['State']['StartedAt'].replace('Z', '+00:00')
                        )
                        uptime_seconds = (datetime.now(started_at.tzinfo) - started_at).total_seconds()
                    
                    # Get restart count
                    restart_count = container.attrs.get('RestartCount', 0)
                    
                    # Create health metrics
                    health_metrics[service_name] = ServiceHealthMetrics(
                        service_type=service_config['service_type'],
                        service_name=service_name,
                        container_name=container_name,
                        is_healthy=is_healthy,
                        cpu_usage_percent=cpu_usage,
                        memory_usage_mb=memory_usage,
                        disk_usage_mb=0.0,
                        network_io_mb=0.0,
                        uptime_seconds=uptime_seconds,
                        restart_count=restart_count
                    )
                    
                except Exception as e:
                    self.logger.debug(f"Error getting stats for {container_name}: {e}")
                    # Create minimal health metrics
                    health_metrics[service_name] = ServiceHealthMetrics(
                        service_type=service_config['service_type'],
                        service_name=service_name,
                        container_name=container_name,
                        is_healthy=False,
                        cpu_usage_percent=0.0,
                        memory_usage_mb=0.0,
                        disk_usage_mb=0.0,
                        network_io_mb=0.0,
                        uptime_seconds=0.0,
                        restart_count=0,
                        last_error=str(e),
                        last_error_time=datetime.now()
                    )
        
        except Exception as e:
            self.logger.error(f"Error collecting service health metrics: {e}")
        
        return health_metrics
    
    async def _collect_service_health_metrics(self) -> Dict[str, ServiceHealthMetrics]:
        """Collect health metrics for all services (async version).
        
        Runs the blocking Docker API calls in a thread pool to avoid blocking the event loop.
        """
        if not self.docker_client:
            return {}
        
        try:
            # Run blocking Docker calls in thread pool with timeout
            loop = asyncio.get_event_loop()
            result = await asyncio.wait_for(
                loop.run_in_executor(None, self._collect_service_health_metrics_sync),
                timeout=15.0  # 15 second timeout
            )
            return result
        except asyncio.TimeoutError:
            self.logger.warning("Docker service health metrics collection timed out")
            return {}
        except Exception as e:
            self.logger.debug(f"Error collecting service health metrics: {e}")
            return {}
    
    def _update_processing_stats(self, processed_count: int) -> None:
        """Update log processing statistics."""
        now = datetime.now()
        time_diff = (now - self._processing_stats['last_processing_time']).total_seconds()
        
        if time_diff > 0:
            self._processing_stats['logs_per_second'] = processed_count / time_diff
        
        self._processing_stats['last_processing_time'] = now
    
    def get_service_logs(self, service_name: Optional[str] = None, 
                        hours: int = 24, limit: int = 1000) -> List[Dict[str, Any]]:
        """Get service logs with optional filtering."""
        cutoff_time = datetime.now() - timedelta(hours=hours)
        
        with self._log_processing_lock:
            filtered_logs = []
            
            for log_entry in reversed(self._service_logs):
                if log_entry.timestamp < cutoff_time:
                    break
                
                if service_name and log_entry.service_name != service_name:
                    continue
                
                filtered_logs.append({
                    'timestamp': log_entry.timestamp.isoformat(),
                    'service_type': log_entry.service_type.value,
                    'service_name': log_entry.service_name,
                    'container_name': log_entry.container_name,
                    'log_level': log_entry.log_level,
                    'message': log_entry.message,
                    'parsed_data': log_entry.parsed_data,
                    'metrics': log_entry.metrics,
                    'error_info': log_entry.error_info
                })
                
                if len(filtered_logs) >= limit:
                    break
            
            return filtered_logs
    
    def get_service_metrics(self) -> Dict[str, Any]:
        """Get current service metrics."""
        return {
            'processing_stats': self._processing_stats.copy(),
            'service_metrics': {
                service_key: {
                    'last_updated': metrics['last_updated'].isoformat(),
                    'metrics': metrics['metrics'],
                    'error_count': metrics['error_count'],
                    'log_count': metrics['log_count']
                }
                for service_key, metrics in self._service_metrics.items()
            },
            'monitored_services': list(self.service_configs.keys()),
            'monitoring_active': self._monitoring_active
        }


# Global local services logger instance
_local_services_logger: Optional[LocalServicesLogger] = None


def get_local_services_logger() -> LocalServicesLogger:
    """Get the global local services logger instance."""
    global _local_services_logger
    if _local_services_logger is None:
        _local_services_logger = LocalServicesLogger()
    return _local_services_logger


async def start_local_services_monitoring() -> None:
    """Start monitoring local services."""
    logger = get_local_services_logger()
    await logger.start_monitoring()


async def stop_local_services_monitoring() -> None:
    """Stop monitoring local services."""
    logger = get_local_services_logger()
    await logger.stop_monitoring()