"""
Test utilities and helper functions for local database testing.

This module provides utility functions and classes to support
database testing, including data validation, performance measurement,
and test result analysis.
"""

import time
import asyncio
import json
import logging
from typing import Dict, Any, List, Optional, Callable, Union
from dataclasses import dataclass, field
from contextlib import asynccontextmanager
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)


# =============================================================================
# Performance Measurement Utilities
# =============================================================================

@dataclass
class PerformanceMetrics:
    """Container for performance measurement results."""
    operation_name: str
    start_time: float
    end_time: float
    duration: float
    success: bool
    error_message: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    @property
    def duration_ms(self) -> float:
        """Duration in milliseconds."""
        return self.duration * 1000
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "operation_name": self.operation_name,
            "start_time": self.start_time,
            "end_time": self.end_time,
            "duration": self.duration,
            "duration_ms": self.duration_ms,
            "success": self.success,
            "error_message": self.error_message,
            "metadata": self.metadata
        }


class PerformanceTracker:
    """Track performance metrics for database operations."""
    
    def __init__(self):
        self.metrics: List[PerformanceMetrics] = []
    
    @asynccontextmanager
    async def measure(self, operation_name: str, **metadata):
        """Context manager to measure operation performance."""
        start_time = time.time()
        success = True
        error_message = None
        
        try:
            yield
        except Exception as e:
            success = False
            error_message = str(e)
            raise
        finally:
            end_time = time.time()
            duration = end_time - start_time
            
            metric = PerformanceMetrics(
                operation_name=operation_name,
                start_time=start_time,
                end_time=end_time,
                duration=duration,
                success=success,
                error_message=error_message,
                metadata=metadata
            )
            
            self.metrics.append(metric)
    
    def get_metrics(self, operation_name: Optional[str] = None) -> List[PerformanceMetrics]:
        """Get metrics, optionally filtered by operation name."""
        if operation_name is None:
            return self.metrics.copy()
        return [m for m in self.metrics if m.operation_name == operation_name]
    
    def get_summary(self) -> Dict[str, Any]:
        """Get performance summary statistics."""
        if not self.metrics:
            return {"total_operations": 0}
        
        successful_metrics = [m for m in self.metrics if m.success]
        failed_metrics = [m for m in self.metrics if not m.success]
        
        durations = [m.duration for m in successful_metrics]
        
        summary = {
            "total_operations": len(self.metrics),
            "successful_operations": len(successful_metrics),
            "failed_operations": len(failed_metrics),
            "success_rate": len(successful_metrics) / len(self.metrics) if self.metrics else 0,
        }
        
        if durations:
            summary.update({
                "avg_duration": sum(durations) / len(durations),
                "min_duration": min(durations),
                "max_duration": max(durations),
                "total_duration": sum(durations),
                "avg_duration_ms": (sum(durations) / len(durations)) * 1000,
                "min_duration_ms": min(durations) * 1000,
                "max_duration_ms": max(durations) * 1000,
            })
        
        # Group by operation name
        operations = {}
        for metric in self.metrics:
            op_name = metric.operation_name
            if op_name not in operations:
                operations[op_name] = []
            operations[op_name].append(metric)
        
        summary["operations"] = {}
        for op_name, op_metrics in operations.items():
            op_durations = [m.duration for m in op_metrics if m.success]
            op_summary = {
                "count": len(op_metrics),
                "success_count": len([m for m in op_metrics if m.success]),
                "failure_count": len([m for m in op_metrics if not m.success]),
            }
            
            if op_durations:
                op_summary.update({
                    "avg_duration": sum(op_durations) / len(op_durations),
                    "min_duration": min(op_durations),
                    "max_duration": max(op_durations),
                    "avg_duration_ms": (sum(op_durations) / len(op_durations)) * 1000,
                })
            
            summary["operations"][op_name] = op_summary
        
        return summary
    
    def clear(self):
        """Clear all metrics."""
        self.metrics.clear()
    
    def export_to_json(self, filepath: str):
        """Export metrics to JSON file."""
        data = {
            "summary": self.get_summary(),
            "metrics": [m.to_dict() for m in self.metrics]
        }
        
        with open(filepath, 'w') as f:
            json.dump(data, f, indent=2, default=str)


# =============================================================================
# Data Validation Utilities
# =============================================================================

class DataValidator:
    """Validate test data integrity and consistency."""
    
    @staticmethod
    def validate_user_data(user_data: Dict[str, Any]) -> List[str]:
        """Validate user data structure and content."""
        errors = []
        
        required_fields = ["id", "username", "email", "role"]
        for field in required_fields:
            if field not in user_data:
                errors.append(f"Missing required field: {field}")
        
        if "email" in user_data:
            email = user_data["email"]
            if "@" not in email or "." not in email:
                errors.append(f"Invalid email format: {email}")
        
        if "role" in user_data:
            valid_roles = ["admin", "ml_researcher", "user", "read_only"]
            if user_data["role"] not in valid_roles:
                errors.append(f"Invalid role: {user_data['role']}")
        
        return errors
    
    @staticmethod
    def validate_document_data(doc_data: Dict[str, Any]) -> List[str]:
        """Validate document data structure and content."""
        errors = []
        
        required_fields = ["id", "user_id", "title", "filename"]
        for field in required_fields:
            if field not in doc_data:
                errors.append(f"Missing required field: {field}")
        
        if "file_size" in doc_data:
            if not isinstance(doc_data["file_size"], int) or doc_data["file_size"] <= 0:
                errors.append("file_size must be a positive integer")
        
        if "status" in doc_data:
            valid_statuses = ["uploaded", "processing", "completed", "failed"]
            if doc_data["status"] not in valid_statuses:
                errors.append(f"Invalid status: {doc_data['status']}")
        
        return errors
    
    @staticmethod
    def validate_vector_data(vector_data: Dict[str, Any]) -> List[str]:
        """Validate vector data structure and content."""
        errors = []
        
        required_fields = ["id", "vector"]
        for field in required_fields:
            if field not in vector_data:
                errors.append(f"Missing required field: {field}")
        
        if "vector" in vector_data:
            vector = vector_data["vector"]
            if not isinstance(vector, list):
                errors.append("vector must be a list")
            elif not all(isinstance(x, (int, float)) for x in vector):
                errors.append("vector must contain only numeric values")
            elif len(vector) == 0:
                errors.append("vector cannot be empty")
        
        return errors
    
    @staticmethod
    def validate_knowledge_node(node_data: Dict[str, Any]) -> List[str]:
        """Validate knowledge graph node data."""
        errors = []
        
        required_fields = ["id", "name", "node_type"]
        for field in required_fields:
            if field not in node_data:
                errors.append(f"Missing required field: {field}")
        
        if "node_type" in node_data:
            valid_types = ["Document", "Concept", "Author", "Topic"]
            if node_data["node_type"] not in valid_types:
                errors.append(f"Invalid node_type: {node_data['node_type']}")
        
        return errors


# =============================================================================
# Database Connection Testing Utilities
# =============================================================================

class DatabaseHealthChecker:
    """Check health and connectivity of database services."""
    
    def __init__(self, performance_tracker: Optional[PerformanceTracker] = None):
        self.performance_tracker = performance_tracker or PerformanceTracker()
    
    async def check_postgres_health(self, client) -> Dict[str, Any]:
        """Check PostgreSQL health and performance."""
        async with self.performance_tracker.measure("postgres_health_check"):
            health = await client.health_check()
        
        # Additional checks
        try:
            async with self.performance_tracker.measure("postgres_simple_query"):
                result = await client.execute_query("SELECT version()")
            
            health["version_check"] = True
            health["version"] = result[0]["version"] if result else "unknown"
        except Exception as e:
            health["version_check"] = False
            health["version_error"] = str(e)
        
        return health
    
    async def check_neo4j_health(self, client) -> Dict[str, Any]:
        """Check Neo4j health and performance."""
        async with self.performance_tracker.measure("neo4j_health_check"):
            health = await client.health_check()
        
        # Additional checks
        try:
            async with self.performance_tracker.measure("neo4j_simple_query"):
                result = await client.execute_query("CALL dbms.components() YIELD name, versions")
            
            health["components_check"] = True
            health["components"] = result if result else []
        except Exception as e:
            health["components_check"] = False
            health["components_error"] = str(e)
        
        return health
    
    async def check_milvus_health(self, client) -> Dict[str, Any]:
        """Check Milvus health and performance."""
        async with self.performance_tracker.measure("milvus_health_check"):
            health = await client.health_check()
        
        # Additional checks
        try:
            async with self.performance_tracker.measure("milvus_list_collections"):
                collections = await client.list_collections()
            
            health["collections_check"] = True
            health["collections"] = collections
        except Exception as e:
            health["collections_check"] = False
            health["collections_error"] = str(e)
        
        return health
    
    async def check_all_services(self, clients: Dict[str, Any]) -> Dict[str, Any]:
        """Check health of all database services."""
        results = {}
        
        if "postgres" in clients:
            results["postgres"] = await self.check_postgres_health(clients["postgres"])
        
        if "neo4j" in clients:
            results["neo4j"] = await self.check_neo4j_health(clients["neo4j"])
        
        if "milvus" in clients:
            results["milvus"] = await self.check_milvus_health(clients["milvus"])
        
        # Overall health summary
        all_healthy = all(
            result.get("status") == "healthy" 
            for result in results.values()
        )
        
        results["overall"] = {
            "status": "healthy" if all_healthy else "unhealthy",
            "services_checked": len(results),
            "healthy_services": len([r for r in results.values() if r.get("status") == "healthy"]),
            "check_timestamp": datetime.utcnow().isoformat()
        }
        
        return results


# =============================================================================
# Test Data Generation Utilities
# =============================================================================

class TestDataGenerator:
    """Generate test data for various scenarios."""
    
    @staticmethod
    def generate_random_vector(dimension: int = 384) -> List[float]:
        """Generate a random normalized vector."""
        import random
        
        vector = [random.gauss(0, 1) for _ in range(dimension)]
        magnitude = sum(x**2 for x in vector) ** 0.5
        
        if magnitude > 0:
            vector = [x / magnitude for x in vector]
        
        return vector
    
    @staticmethod
    def generate_similar_vector(base_vector: List[float], similarity: float = 0.8) -> List[float]:
        """Generate a vector similar to the base vector."""
        import random
        import math
        
        if not (0 <= similarity <= 1):
            raise ValueError("Similarity must be between 0 and 1")
        
        # Generate noise vector
        noise = [random.gauss(0, 1) for _ in range(len(base_vector))]
        noise_magnitude = sum(x**2 for x in noise) ** 0.5
        if noise_magnitude > 0:
            noise = [x / noise_magnitude for x in noise]
        
        # Mix base vector with noise based on similarity
        angle = math.acos(similarity)
        cos_angle = math.cos(angle)
        sin_angle = math.sin(angle)
        
        similar_vector = [
            cos_angle * base + sin_angle * noise_val
            for base, noise_val in zip(base_vector, noise)
        ]
        
        # Normalize the result
        magnitude = sum(x**2 for x in similar_vector) ** 0.5
        if magnitude > 0:
            similar_vector = [x / magnitude for x in similar_vector]
        
        return similar_vector
    
    @staticmethod
    def generate_test_documents(count: int, user_ids: List[str]) -> List[Dict[str, Any]]:
        """Generate test document data."""
        import random
        
        documents = []
        
        subjects = [
            "Machine Learning", "Deep Learning", "Natural Language Processing",
            "Computer Vision", "Data Science", "Artificial Intelligence",
            "Neural Networks", "Reinforcement Learning", "Statistics"
        ]
        
        for i in range(count):
            subject = random.choice(subjects)
            user_id = random.choice(user_ids)
            
            doc = {
                "id": f"test-gen-doc-{i+1:04d}",
                "user_id": user_id,
                "title": f"{subject} Guide {i+1:04d}",
                "filename": f"{subject.lower().replace(' ', '_')}_guide_{i+1:04d}.pdf",
                "description": f"Comprehensive guide to {subject.lower()}",
                "file_size": random.randint(1048576, 10485760),  # 1-10MB
                "page_count": random.randint(50, 300),
                "status": random.choice(["completed", "completed", "completed", "processing"]),
                "mime_type": "application/pdf",
                "upload_timestamp": datetime.utcnow() - timedelta(days=random.randint(1, 30))
            }
            
            documents.append(doc)
        
        return documents
    
    @staticmethod
    def generate_test_conversations(count: int, user_ids: List[str]) -> List[Dict[str, Any]]:
        """Generate test conversation data."""
        import random
        
        conversations = []
        
        topics = [
            "Machine Learning Questions", "Deep Learning Help", "NLP Implementation",
            "Computer Vision Project", "Data Analysis Discussion", "AI Ethics Debate",
            "Model Training Issues", "Feature Engineering Tips", "Performance Optimization"
        ]
        
        for i in range(count):
            topic = random.choice(topics)
            user_id = random.choice(user_ids)
            
            conv = {
                "thread_id": f"test-gen-thread-{i+1:04d}",
                "user_id": user_id,
                "title": f"{topic} {i+1:04d}",
                "created_at": datetime.utcnow() - timedelta(hours=random.randint(1, 168)),  # Last week
                "message_count": random.randint(2, 20),
                "is_active": random.choice([True, True, True, False])  # Mostly active
            }
            
            conversations.append(conv)
        
        return conversations


# =============================================================================
# Test Result Analysis Utilities
# =============================================================================

class TestResultAnalyzer:
    """Analyze and report on test results."""
    
    def __init__(self):
        self.results = []
    
    def add_result(self, test_name: str, success: bool, duration: float, **metadata):
        """Add a test result."""
        result = {
            "test_name": test_name,
            "success": success,
            "duration": duration,
            "timestamp": datetime.utcnow().isoformat(),
            "metadata": metadata
        }
        self.results.append(result)
    
    def get_summary(self) -> Dict[str, Any]:
        """Get test results summary."""
        if not self.results:
            return {"total_tests": 0}
        
        successful_tests = [r for r in self.results if r["success"]]
        failed_tests = [r for r in self.results if not r["success"]]
        
        durations = [r["duration"] for r in self.results]
        
        return {
            "total_tests": len(self.results),
            "successful_tests": len(successful_tests),
            "failed_tests": len(failed_tests),
            "success_rate": len(successful_tests) / len(self.results),
            "avg_duration": sum(durations) / len(durations),
            "min_duration": min(durations),
            "max_duration": max(durations),
            "total_duration": sum(durations),
            "failed_test_names": [r["test_name"] for r in failed_tests]
        }
    
    def export_results(self, filepath: str):
        """Export results to JSON file."""
        data = {
            "summary": self.get_summary(),
            "results": self.results
        }
        
        with open(filepath, 'w') as f:
            json.dump(data, f, indent=2, default=str)


# =============================================================================
# Async Test Utilities
# =============================================================================

async def wait_for_condition(
    condition_func: Callable[[], bool],
    timeout: float = 30.0,
    check_interval: float = 0.5,
    error_message: str = "Condition not met within timeout"
) -> bool:
    """Wait for a condition to become true."""
    start_time = time.time()
    
    while time.time() - start_time < timeout:
        try:
            if condition_func():
                return True
        except Exception:
            pass  # Ignore errors during condition check
        
        await asyncio.sleep(check_interval)
    
    raise TimeoutError(error_message)


async def wait_for_async_condition(
    condition_func: Callable[[], Any],
    timeout: float = 30.0,
    check_interval: float = 0.5,
    error_message: str = "Async condition not met within timeout"
) -> bool:
    """Wait for an async condition to become true."""
    start_time = time.time()
    
    while time.time() - start_time < timeout:
        try:
            result = await condition_func()
            if result:
                return True
        except Exception:
            pass  # Ignore errors during condition check
        
        await asyncio.sleep(check_interval)
    
    raise TimeoutError(error_message)


def retry_on_failure(max_retries: int = 3, delay: float = 1.0):
    """Decorator to retry a function on failure."""
    def decorator(func):
        async def wrapper(*args, **kwargs):
            last_exception = None
            
            for attempt in range(max_retries):
                try:
                    if asyncio.iscoroutinefunction(func):
                        return await func(*args, **kwargs)
                    else:
                        return func(*args, **kwargs)
                except Exception as e:
                    last_exception = e
                    if attempt < max_retries - 1:
                        await asyncio.sleep(delay)
                    else:
                        raise last_exception
            
            raise last_exception
        
        return wrapper
    return decorator


# =============================================================================
# Logging Utilities
# =============================================================================

class TestLogger:
    """Enhanced logging for test scenarios."""
    
    def __init__(self, name: str):
        self.logger = logging.getLogger(name)
        self.test_logs = []
    
    def log_test_start(self, test_name: str, **context):
        """Log test start with context."""
        message = f"Starting test: {test_name}"
        if context:
            message += f" | Context: {context}"
        
        self.logger.info(message)
        self.test_logs.append({
            "event": "test_start",
            "test_name": test_name,
            "timestamp": datetime.utcnow().isoformat(),
            "context": context
        })
    
    def log_test_end(self, test_name: str, success: bool, duration: float, **metadata):
        """Log test end with results."""
        status = "PASSED" if success else "FAILED"
        message = f"Test {status}: {test_name} | Duration: {duration:.3f}s"
        
        if metadata:
            message += f" | Metadata: {metadata}"
        
        if success:
            self.logger.info(message)
        else:
            self.logger.error(message)
        
        self.test_logs.append({
            "event": "test_end",
            "test_name": test_name,
            "success": success,
            "duration": duration,
            "timestamp": datetime.utcnow().isoformat(),
            "metadata": metadata
        })
    
    def log_operation(self, operation: str, success: bool, duration: float, **details):
        """Log database operation."""
        status = "SUCCESS" if success else "FAILED"
        message = f"Operation {status}: {operation} | Duration: {duration:.3f}s"
        
        if details:
            message += f" | Details: {details}"
        
        self.logger.debug(message)
        self.test_logs.append({
            "event": "operation",
            "operation": operation,
            "success": success,
            "duration": duration,
            "timestamp": datetime.utcnow().isoformat(),
            "details": details
        })
    
    def get_logs(self) -> List[Dict[str, Any]]:
        """Get all test logs."""
        return self.test_logs.copy()
    
    def clear_logs(self):
        """Clear test logs."""
        self.test_logs.clear()
    
    def export_logs(self, filepath: str):
        """Export logs to JSON file."""
        with open(filepath, 'w') as f:
            json.dump(self.test_logs, f, indent=2, default=str)