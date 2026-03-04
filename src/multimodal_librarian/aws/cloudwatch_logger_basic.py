"""
Enhanced CloudWatch logging and metrics integration for AWS deployment.

This module provides comprehensive CloudWatch integration for the learning deployment,
including custom metrics publishing, structured logging, X-Ray tracing, and enhanced
monitoring capabilities for Task 10.
"""

import os
import json
import logging
import time
from datetime import datetime
from typing import Dict, Any, Optional, List
from functools import wraps

import boto3
from botocore.exceptions import ClientError, NoCredentialsError

from ..config import get_settings


class CloudWatchLogger:
    """Enhanced CloudWatch integration for comprehensive monitoring."""
    
    def __init__(self):
        self.settings = get_settings()
        self.project_name = getattr(self.settings, 'project_name', 'multimodal-librarian')
        self.environment = getattr(self.settings, 'environment', 'learning')
        self.namespace = f"{self.project_name}/{self.environment}"
        
        # Initialize AWS clients
        self.cloudwatch_client = None
        self.logs_client = None
        self.xray_client = None
        self._initialize_clients()
        
        # Metrics buffer for batch publishing
        self._metrics_buffer = []
        self._buffer_size = 20  # CloudWatch limit
        
        # Logger for this module
        self.logger = logging.getLogger(__name__)
        
        # Enhanced logging configuration
        self._setup_enhanced_logging()
    
    def _initialize_clients(self):
        """Initialize AWS clients if running in AWS environment."""
        try:
            # Check if we're running in AWS (ECS, EC2, Lambda)
            if self._is_aws_environment():
                self.cloudwatch_client = boto3.client('cloudwatch')
                self.logs_client = boto3.client('logs')
                self.xray_client = boto3.client('xray')
                self.logger.info("CloudWatch clients initialized for AWS environment")
            else:
                self.logger.info("Not in AWS environment, CloudWatch integration disabled")
        except (NoCredentialsError, ClientError) as e:
            self.logger.warning(f"Could not initialize CloudWatch clients: {e}")
        except Exception as e:
            self.logger.error(f"Unexpected error initializing CloudWatch: {e}")
    
    def _setup_enhanced_logging(self):
        """Set up enhanced logging configuration for different log groups."""
        # Configure structured logging format
        formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )
        
        # Create specialized loggers for different components
        self.app_logger = logging.getLogger('multimodal_librarian.app')
        self.chat_logger = logging.getLogger('multimodal_librarian.chat')
        self.ml_logger = logging.getLogger('multimodal_librarian.ml')
        self.security_logger = logging.getLogger('multimodal_librarian.security')
        self.performance_logger = logging.getLogger('multimodal_librarian.performance')
        
        # Set up handlers if in AWS environment
        if self._is_aws_environment():
            self._setup_cloudwatch_handlers(formatter)
    
    def _setup_cloudwatch_handlers(self, formatter):
        """Set up CloudWatch log handlers for different log groups."""
        try:
            # This would typically use a CloudWatch logs handler
            # For now, we'll use the standard logging and rely on ECS log driver
            pass
        except Exception as e:
            self.logger.warning(f"Could not set up CloudWatch handlers: {e}")
    
    def _is_aws_environment(self) -> bool:
        """Check if running in AWS environment."""
        # Check for ECS metadata endpoint
        if os.environ.get('ECS_CONTAINER_METADATA_URI_V4'):
            return True
        
        # Check for EC2 metadata endpoint
        try:
            import requests
            response = requests.get(
                'http://169.254.169.254/latest/meta-data/instance-id',
                timeout=2
            )
            return response.status_code == 200
        except:
            pass
        
        # Check for Lambda environment
        if os.environ.get('AWS_LAMBDA_FUNCTION_NAME'):
            return True
        
        # Check for explicit AWS environment variable
        if os.environ.get('AWS_ENVIRONMENT') == 'true':
            return True
        
        return False
    
    def put_metric(self, metric_name: str, value: float, unit: str = 'Count', 
                   dimensions: Optional[Dict[str, str]] = None) -> bool:
        """Put a single metric to CloudWatch."""
        if not self.cloudwatch_client:
            return False
        
        try:
            metric_data = {
                'MetricName': metric_name,
                'Value': value,
                'Unit': unit,
                'Timestamp': datetime.utcnow()
            }
            
            if dimensions:
                metric_data['Dimensions'] = [
                    {'Name': key, 'Value': str(value)} 
                    for key, value in dimensions.items()
                ]
            
            # Add to buffer
            self._metrics_buffer.append(metric_data)
            
            # Flush buffer if full
            if len(self._metrics_buffer) >= self._buffer_size:
                return self._flush_metrics_buffer()
            
            return True
            
        except Exception as e:
            self.logger.error(f"Error putting metric {metric_name}: {e}")
            return False
    
    def put_metrics_batch(self, metrics: List[Dict[str, Any]]) -> bool:
        """Put multiple metrics to CloudWatch in batch."""
        if not self.cloudwatch_client:
            return False
        
        try:
            # Process metrics in batches of 20 (CloudWatch limit)
            for i in range(0, len(metrics), self._buffer_size):
                batch = metrics[i:i + self._buffer_size]
                
                # Format metrics for CloudWatch
                metric_data = []
                for metric in batch:
                    formatted_metric = {
                        'MetricName': metric['name'],
                        'Value': metric['value'],
                        'Unit': metric.get('unit', 'Count'),
                        'Timestamp': datetime.utcnow()
                    }
                    
                    if 'dimensions' in metric:
                        formatted_metric['Dimensions'] = [
                            {'Name': key, 'Value': str(value)} 
                            for key, value in metric['dimensions'].items()
                        ]
                    
                    metric_data.append(formatted_metric)
                
                # Send batch to CloudWatch
                self.cloudwatch_client.put_metric_data(
                    Namespace=self.namespace,
                    MetricData=metric_data
                )
            
            self.logger.debug(f"Successfully sent {len(metrics)} metrics to CloudWatch")
            return True
            
        except Exception as e:
            self.logger.error(f"Error putting metrics batch: {e}")
            return False
    
    def _flush_metrics_buffer(self) -> bool:
        """Flush the metrics buffer to CloudWatch."""
        if not self._metrics_buffer or not self.cloudwatch_client:
            return False
        
        try:
            self.cloudwatch_client.put_metric_data(
                Namespace=self.namespace,
                MetricData=self._metrics_buffer
            )
            
            self.logger.debug(f"Flushed {len(self._metrics_buffer)} metrics to CloudWatch")
            self._metrics_buffer.clear()
            return True
            
        except Exception as e:
            self.logger.error(f"Error flushing metrics buffer: {e}")
            return False
    
    def flush_metrics(self) -> bool:
        """Manually flush any pending metrics."""
        return self._flush_metrics_buffer()
    
    def log_to_specific_group(self, log_group: str, level: str, message: str, 
                             extra_data: Optional[Dict[str, Any]] = None):
        """Log to a specific CloudWatch log group."""
        log_entry = {
            'timestamp': datetime.utcnow().isoformat(),
            'level': level.upper(),
            'message': message,
            'namespace': self.namespace,
            'log_group': log_group
        }
        
        if extra_data:
            log_entry.update(extra_data)
        
        # Route to appropriate logger based on log group
        if log_group == 'chat':
            self.chat_logger.info(json.dumps(log_entry))
        elif log_group == 'ml':
            self.ml_logger.info(json.dumps(log_entry))
        elif log_group == 'security':
            self.security_logger.warning(json.dumps(log_entry))
        elif log_group == 'performance':
            self.performance_logger.info(json.dumps(log_entry))
        else:
            self.app_logger.info(json.dumps(log_entry))
    
    def log_security_event(self, event_type: str, details: Dict[str, Any], 
                          severity: str = 'INFO'):
        """Log security events to dedicated security log group."""
        self.log_to_specific_group('security', severity, f'Security event: {event_type}', {
            'event_type': event_type,
            'severity': severity,
            **details
        })
        
        # Also create a security metric
        self.put_metric('SecurityEvents', 1, 'Count', {'EventType': event_type})
    
    def log_performance_metric(self, operation: str, duration: float, 
                              additional_metrics: Optional[Dict[str, float]] = None):
        """Log performance metrics with detailed timing information."""
        performance_data = {
            'operation': operation,
            'duration_ms': duration * 1000,
            'timestamp': datetime.utcnow().isoformat()
        }
        
        if additional_metrics:
            performance_data.update(additional_metrics)
        
        self.log_to_specific_group('performance', 'INFO', 
                                 f'Performance metric: {operation}', performance_data)
        
        # Create performance metrics
        self.put_metric(f'{operation}Duration', duration * 1000, 'Milliseconds')
        
        if additional_metrics:
            for metric_name, value in additional_metrics.items():
                self.put_metric(f'{operation}{metric_name}', value, 'Count')
    
    def start_xray_trace(self, trace_name: str) -> Optional[str]:
        """Start an X-Ray trace segment."""
        if not self.xray_client:
            return None
        
        try:
            # This is a simplified X-Ray integration
            # In practice, you'd use the X-Ray SDK
            trace_id = f"{trace_name}-{int(time.time())}"
            self.log_structured('info', f'Started X-Ray trace: {trace_name}', {
                'trace_id': trace_id,
                'trace_name': trace_name
            })
            return trace_id
        except Exception as e:
            self.logger.warning(f"Could not start X-Ray trace: {e}")
            return None
    
    def end_xray_trace(self, trace_id: str, success: bool = True, 
                      metadata: Optional[Dict[str, Any]] = None):
        """End an X-Ray trace segment."""
        if not self.xray_client or not trace_id:
            return
        
        try:
            self.log_structured('info', f'Ended X-Ray trace: {trace_id}', {
                'trace_id': trace_id,
                'success': success,
                'metadata': metadata or {}
            })
        except Exception as e:
            self.logger.warning(f"Could not end X-Ray trace: {e}")
    
    def log_structured(self, level: str, message: str, extra_data: Optional[Dict[str, Any]] = None):
        """Log structured data that can be easily queried in CloudWatch Logs Insights."""
        log_entry = {
            'timestamp': datetime.utcnow().isoformat(),
            'level': level.upper(),
            'message': message,
            'namespace': self.namespace
        }
        
        if extra_data:
            log_entry.update(extra_data)
        
        # Use standard logging with JSON format for CloudWatch
        logger = logging.getLogger('cloudwatch_structured')
        
        if level.upper() == 'ERROR':
            logger.error(json.dumps(log_entry))
        elif level.upper() == 'WARNING':
            logger.warning(json.dumps(log_entry))
        elif level.upper() == 'INFO':
            logger.info(json.dumps(log_entry))
        else:
            logger.debug(json.dumps(log_entry))

    def log_to_specific_group(self, log_group: str, level: str, message: str, 
                             extra_data: Optional[Dict[str, Any]] = None):
        """Log to a specific CloudWatch log group."""
        log_entry = {
            'timestamp': datetime.utcnow().isoformat(),
            'level': level.upper(),
            'message': message,
            'namespace': self.namespace,
            'log_group': log_group
        }
        
        if extra_data:
            log_entry.update(extra_data)
        
        # Route to appropriate logger based on log group
        if log_group == 'chat':
            self.chat_logger.info(json.dumps(log_entry))
        elif log_group == 'ml':
            self.ml_logger.info(json.dumps(log_entry))
        elif log_group == 'security':
            self.security_logger.warning(json.dumps(log_entry))
        elif log_group == 'performance':
            self.performance_logger.info(json.dumps(log_entry))
        else:
            self.app_logger.info(json.dumps(log_entry))
    
    def log_security_event(self, event_type: str, details: Dict[str, Any], 
                          severity: str = 'INFO'):
        """Log security events to dedicated security log group."""
        self.log_to_specific_group('security', severity, f'Security event: {event_type}', {
            'event_type': event_type,
            'severity': severity,
            **details
        })
        
        # Also create a security metric
        self.put_metric('SecurityEvents', 1, 'Count', {'EventType': event_type})
    
    def log_performance_metric(self, operation: str, duration: float, 
                              additional_metrics: Optional[Dict[str, float]] = None):
        """Log performance metrics with detailed timing information."""
        performance_data = {
            'operation': operation,
            'duration_ms': duration * 1000,
            'timestamp': datetime.utcnow().isoformat()
        }
        
        if additional_metrics:
            performance_data.update(additional_metrics)
        
        self.log_to_specific_group('performance', 'INFO', 
                                 f'Performance metric: {operation}', performance_data)
        
        # Create performance metrics
        self.put_metric(f'{operation}Duration', duration * 1000, 'Milliseconds')
        
        if additional_metrics:
            for metric_name, value in additional_metrics.items():
                self.put_metric(f'{operation}{metric_name}', value, 'Count')
    
    def start_xray_trace(self, trace_name: str) -> Optional[str]:
        """Start an X-Ray trace segment."""
        if not self.xray_client:
            return None
        
        try:
            # This is a simplified X-Ray integration
            # In practice, you'd use the X-Ray SDK
            trace_id = f"{trace_name}-{int(time.time())}"
            self.log_structured('info', f'Started X-Ray trace: {trace_name}', {
                'trace_id': trace_id,
                'trace_name': trace_name
            })
            return trace_id
        except Exception as e:
            self.logger.warning(f"Could not start X-Ray trace: {e}")
            return None
    
    def end_xray_trace(self, trace_id: str, success: bool = True, 
                      metadata: Optional[Dict[str, Any]] = None):
        """End an X-Ray trace segment."""
        if not self.xray_client or not trace_id:
            return
        
        try:
            self.log_structured('info', f'Ended X-Ray trace: {trace_id}', {
                'trace_id': trace_id,
                'success': success,
                'metadata': metadata or {}
            })
        except Exception as e:
            self.logger.warning(f"Could not end X-Ray trace: {e}")
    
    def create_custom_dashboard_data(self) -> Dict[str, Any]:
        """Create comprehensive dashboard data for CloudWatch."""
        return {
            'dashboard_name': f'{self.project_name}-{self.environment}-comprehensive',
            'widgets': [
                {
                    'type': 'metric',
                    'properties': {
                        'metrics': [
                            [self.namespace, 'ChatMessages'],
                            ['.', 'MLTrainingRequests'],
                            ['.', 'ActiveWebSocketConnections'],
                            ['.', 'ChunkingOperations'],
                            ['.', 'ErrorRate'],
                            ['.', 'ResponseTime'],
                            ['.', 'SecurityEvents']
                        ],
                        'period': 300,
                        'stat': 'Sum',
                        'region': 'us-east-1',
                        'title': 'Application Metrics Overview'
                    }
                },
                {
                    'type': 'log',
                    'properties': {
                        'query': f'SOURCE \'/aws/ecs/{self.project_name}-{self.environment}/application\' | fields @timestamp, @message | filter @message like /ERROR/ | sort @timestamp desc | limit 20',
                        'region': 'us-east-1',
                        'title': 'Recent Application Errors'
                    }
                },
                {
                    'type': 'log',
                    'properties': {
                        'query': f'SOURCE \'/aws/security/{self.project_name}-{self.environment}\' | fields @timestamp, @message | sort @timestamp desc | limit 10',
                        'region': 'us-east-1',
                        'title': 'Recent Security Events'
                    }
                }
            ]
        }
    
    def record_api_call(self, endpoint: str, method: str, response_time: float, 
                       status_code: int, user_id: Optional[str] = None):
        """Record API call metrics."""
        # Response time metric
        self.put_metric(
            'ResponseTime',
            response_time * 1000,  # Convert to milliseconds
            'Milliseconds',
            {'Endpoint': endpoint, 'Method': method}
        )
        
        # Request count metric
        self.put_metric(
            'RequestCount',
            1,
            'Count',
            {'Endpoint': endpoint, 'Method': method, 'StatusCode': str(status_code)}
        )
        
        # Error rate metric
        if status_code >= 400:
            self.put_metric(
                'ErrorCount',
                1,
                'Count',
                {'Endpoint': endpoint, 'Method': method, 'StatusCode': str(status_code)}
            )
        
        # Log structured data
        self.log_structured('info', 'API call recorded', {
            'endpoint': endpoint,
            'method': method,
            'response_time_ms': response_time * 1000,
            'status_code': status_code,
            'user_id': user_id
        })
    
    def record_chat_activity(self, event_type: str, **kwargs):
        """Record chat-related metrics."""
        if event_type == 'websocket_connect':
            self.put_metric('WebSocketConnections', 1, 'Count')
            self.put_metric('ActiveWebSocketConnections', kwargs.get('active_count', 1), 'Count')
        
        elif event_type == 'websocket_disconnect':
            self.put_metric('WebSocketDisconnections', 1, 'Count')
            self.put_metric('ActiveWebSocketConnections', kwargs.get('active_count', 0), 'Count')
        
        elif event_type == 'message_sent':
            self.put_metric('ChatMessages', 1, 'Count')
            if kwargs.get('message_length'):
                self.put_metric('MessageLength', kwargs['message_length'], 'Count')
        
        elif event_type == 'conversation_started':
            self.put_metric('ConversationsStarted', 1, 'Count')
        
        # Log structured data
        self.log_structured('info', f'Chat activity: {event_type}', kwargs)
    
    def record_ml_training_activity(self, event_type: str, **kwargs):
        """Record ML training related metrics."""
        if event_type == 'training_request':
            self.put_metric('MLTrainingRequests', 1, 'Count')
            if kwargs.get('batch_size'):
                self.put_metric('TrainingBatchSize', kwargs['batch_size'], 'Count')
        
        elif event_type == 'chunk_processed':
            self.put_metric('ChunkingOperations', 1, 'Count')
            if kwargs.get('processing_time'):
                self.put_metric('ChunkProcessingTime', kwargs['processing_time'], 'Seconds')
        
        elif event_type == 'pdf_processed':
            self.put_metric('PDFProcessed', 1, 'Count')
            if kwargs.get('processing_time'):
                self.put_metric('PDFProcessingTime', kwargs['processing_time'], 'Seconds')
        
        elif event_type == 'vector_search':
            self.put_metric('VectorSearches', 1, 'Count')
            if kwargs.get('search_time'):
                self.put_metric('VectorSearchLatency', kwargs['search_time'], 'Milliseconds')
        
        elif event_type == 'knowledge_graph_query':
            self.put_metric('KnowledgeGraphQueries', 1, 'Count')
            if kwargs.get('query_time'):
                self.put_metric('KnowledgeGraphQueryTime', kwargs['query_time'], 'Milliseconds')
        
        # Log structured data
        self.log_structured('info', f'ML training activity: {event_type}', kwargs)
    
    def record_error(self, error_type: str, error_message: str, **kwargs):
        """Record error metrics and logs."""
        self.put_metric('ErrorRate', 1, 'Count', {'ErrorType': error_type})
        
        # Log structured error
        self.log_structured('error', f'{error_type}: {error_message}', {
            'error_type': error_type,
            'error_message': error_message,
            **kwargs
        })
    
    def create_custom_dashboard_widget_data(self) -> Dict[str, Any]:
        """Create widget data for custom CloudWatch dashboard."""
        return {
            'custom_metrics': [
                {
                    'name': 'ChatMessages',
                    'namespace': self.namespace,
                    'stat': 'Sum',
                    'period': 300
                },
                {
                    'name': 'MLTrainingRequests',
                    'namespace': self.namespace,
                    'stat': 'Sum',
                    'period': 300
                },
                {
                    'name': 'ActiveWebSocketConnections',
                    'namespace': self.namespace,
                    'stat': 'Average',
                    'period': 300
                },
                {
                    'name': 'ChunkingOperations',
                    'namespace': self.namespace,
                    'stat': 'Sum',
                    'period': 300
                },
                {
                    'name': 'ErrorRate',
                    'namespace': self.namespace,
                    'stat': 'Sum',
                    'period': 300
                }
            ]
        }


# Global CloudWatch logger instance
_cloudwatch_logger = None

def get_cloudwatch_logger() -> CloudWatchLogger:
    """Get the global CloudWatch logger instance."""
    global _cloudwatch_logger
    if _cloudwatch_logger is None:
        _cloudwatch_logger = CloudWatchLogger()
    return _cloudwatch_logger


def cloudwatch_metric(metric_name: str, unit: str = 'Count', dimensions: Optional[Dict[str, str]] = None):
    """Decorator to automatically record metrics for function calls."""
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            start_time = time.time()
            cw_logger = get_cloudwatch_logger()
            
            try:
                result = func(*args, **kwargs)
                
                # Record success metric
                cw_logger.put_metric(metric_name, 1, unit, dimensions)
                
                # Record execution time if it's a timed operation
                if unit == 'Seconds' or 'time' in metric_name.lower():
                    execution_time = time.time() - start_time
                    cw_logger.put_metric(f"{metric_name}ExecutionTime", execution_time, 'Seconds', dimensions)
                
                return result
                
            except Exception as e:
                # Record error metric
                error_dimensions = dict(dimensions) if dimensions else {}
                error_dimensions['ErrorType'] = type(e).__name__
                cw_logger.put_metric(f"{metric_name}Errors", 1, 'Count', error_dimensions)
                
                # Log error
                cw_logger.record_error(type(e).__name__, str(e), function=func.__name__)
                
                raise
        
        return wrapper
    return decorator


# Enhanced decorators for comprehensive monitoring
def track_performance(operation_name: str):
    """Decorator to track performance metrics with X-Ray tracing."""
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            cw_logger = get_cloudwatch_logger()
            start_time = time.time()
            trace_id = cw_logger.start_xray_trace(f"{operation_name}_{func.__name__}")
            
            try:
                result = func(*args, **kwargs)
                duration = time.time() - start_time
                
                # Log performance metrics
                cw_logger.log_performance_metric(operation_name, duration, {
                    'function': func.__name__,
                    'success': True
                })
                
                cw_logger.end_xray_trace(trace_id, success=True, metadata={
                    'duration': duration,
                    'function': func.__name__
                })
                
                return result
                
            except Exception as e:
                duration = time.time() - start_time
                
                # Log error metrics
                cw_logger.log_performance_metric(operation_name, duration, {
                    'function': func.__name__,
                    'success': False,
                    'error': type(e).__name__
                })
                
                cw_logger.end_xray_trace(trace_id, success=False, metadata={
                    'duration': duration,
                    'function': func.__name__,
                    'error': str(e)
                })
                
                raise
        
        return wrapper
    return decorator


def track_security_events(event_type: str):
    """Decorator to track security-related events."""
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            cw_logger = get_cloudwatch_logger()
            
            try:
                result = func(*args, **kwargs)
                
                # Log successful security event
                cw_logger.log_security_event(event_type, {
                    'function': func.__name__,
                    'success': True,
                    'timestamp': datetime.utcnow().isoformat()
                }, severity='INFO')
                
                return result
                
            except Exception as e:
                # Log failed security event
                cw_logger.log_security_event(event_type, {
                    'function': func.__name__,
                    'success': False,
                    'error': str(e),
                    'timestamp': datetime.utcnow().isoformat()
                }, severity='WARNING')
                
                raise
        
        return wrapper
    return decorator


def track_business_metrics(metric_name: str, metric_value_func=None):
    """Decorator to track business-specific metrics."""
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            cw_logger = get_cloudwatch_logger()
            
            try:
                result = func(*args, **kwargs)
                
                # Calculate metric value
                if metric_value_func:
                    metric_value = metric_value_func(result)
                else:
                    metric_value = 1
                
                # Record business metric
                cw_logger.put_metric(metric_name, metric_value, 'Count', {
                    'Function': func.__name__,
                    'Status': 'Success'
                })
                
                return result
                
            except Exception as e:
                # Record failure metric
                cw_logger.put_metric(f"{metric_name}Failures", 1, 'Count', {
                    'Function': func.__name__,
                    'ErrorType': type(e).__name__
                })
                
                raise
        
        return wrapper
    return decorator


# Enhanced usage decorators
def track_api_calls_enhanced(func):
    """Enhanced decorator to track API call metrics with performance and security."""
    return track_performance('APICall')(track_security_events('api_access')(func))


def track_ml_operations_enhanced(func):
    """Enhanced decorator to track ML operation metrics with performance tracking."""
    return track_performance('MLOperation')(track_business_metrics('MLOperations')(func))


def track_chat_operations_enhanced(func):
    """Enhanced decorator to track chat operation metrics with user activity."""
    return track_performance('ChatOperation')(track_business_metrics('ChatOperations')(func))