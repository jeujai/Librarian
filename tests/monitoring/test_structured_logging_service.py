"""
Tests for the structured logging service.

This test suite validates:
- Structured log entry creation and storage
- Correlation ID tracking and indexing
- Log aggregation rules and filtering
- Log retention policies and archival
- Export functionality
- API endpoints
"""

import pytest
import asyncio
import json
import tempfile
import os
from datetime import datetime, timedelta
from unittest.mock import Mock, patch
from typing import Dict, Any

from src.multimodal_librarian.monitoring.structured_logging_service import (
    StructuredLoggingService,
    StructuredLogEntry,
    LogAggregationRule,
    LogRetentionPolicy,
    get_structured_logging_service,
    log_structured,
    log_info_structured,
    log_warning_structured,
    log_error_structured,
    structured_trace_operation
)


class TestStructuredLoggingService:
    """Test cases for StructuredLoggingService."""
    
    @pytest.fixture
    def logging_service(self):
        """Create a fresh logging service instance for testing."""
        return StructuredLoggingService()
    
    @pytest.fixture
    def sample_log_entry(self):
        """Create a sample structured log entry."""
        return {
            "level": "INFO",
            "service": "test_service",
            "operation": "test_operation",
            "message": "Test message",
            "metadata": {"key": "value", "number": 42},
            "tags": {"environment": "test", "component": "logging"}
        }
    
    def test_log_structured_basic(self, logging_service, sample_log_entry):
        """Test basic structured logging functionality."""
        
        # Log a structured entry
        correlation_id = logging_service.log_structured(**sample_log_entry)
        
        # Verify correlation ID is generated
        assert correlation_id is not None
        assert len(correlation_id) > 0
        
        # Verify log is stored
        assert len(logging_service._structured_logs) == 1
        
        # Verify log content
        stored_log = logging_service._structured_logs[0]
        assert stored_log.level == "INFO"
        assert stored_log.service == "test_service"
        assert stored_log.operation == "test_operation"
        assert stored_log.message == "Test message"
        assert stored_log.correlation_id == correlation_id
        assert stored_log.metadata == {"key": "value", "number": 42}
        assert stored_log.tags == {"environment": "test", "component": "logging"}
    
    def test_log_structured_with_correlation_id(self, logging_service, sample_log_entry):
        """Test structured logging with provided correlation ID."""
        
        custom_correlation_id = "custom-correlation-123"
        
        # Log with custom correlation ID
        returned_correlation_id = logging_service.log_structured(
            correlation_id=custom_correlation_id,
            **sample_log_entry
        )
        
        # Verify custom correlation ID is used
        assert returned_correlation_id == custom_correlation_id
        
        # Verify log is indexed by correlation ID
        logs = logging_service.get_logs_by_correlation(custom_correlation_id)
        assert len(logs) == 1
        assert logs[0]["correlation_id"] == custom_correlation_id
    
    def test_correlation_id_indexing(self, logging_service):
        """Test correlation ID indexing and retrieval."""
        
        correlation_id = "test-correlation-456"
        
        # Log multiple entries with same correlation ID
        for i in range(3):
            logging_service.log_structured(
                level="INFO",
                service="test_service",
                operation=f"operation_{i}",
                message=f"Message {i}",
                correlation_id=correlation_id
            )
        
        # Retrieve logs by correlation ID
        logs = logging_service.get_logs_by_correlation(correlation_id)
        
        # Verify all logs are retrieved
        assert len(logs) == 3
        
        # Verify logs are sorted by timestamp
        timestamps = [log["timestamp"] for log in logs]
        assert timestamps == sorted(timestamps)
        
        # Verify all have same correlation ID
        for log in logs:
            assert log["correlation_id"] == correlation_id
    
    def test_trace_id_indexing(self, logging_service):
        """Test trace ID indexing and retrieval."""
        
        trace_id = "test-trace-789"
        
        # Log multiple entries with same trace ID
        for i in range(2):
            logging_service.log_structured(
                level="INFO",
                service="test_service",
                operation=f"operation_{i}",
                message=f"Message {i}",
                trace_id=trace_id
            )
        
        # Retrieve logs by trace ID
        logs = logging_service.get_logs_by_trace(trace_id)
        
        # Verify logs are retrieved
        assert len(logs) == 2
        for log in logs:
            assert log["trace_id"] == trace_id
    
    def test_user_id_indexing(self, logging_service):
        """Test user ID indexing and retrieval."""
        
        user_id = "test-user-123"
        
        # Log entries for user
        logging_service.log_structured(
            level="INFO",
            service="test_service",
            operation="user_action",
            message="User performed action",
            user_id=user_id
        )
        
        # Retrieve logs by user ID
        logs = logging_service.get_logs_by_user(user_id, hours=1)
        
        # Verify logs are retrieved
        assert len(logs) == 1
        assert logs[0]["user_id"] == user_id
    
    def test_service_indexing(self, logging_service):
        """Test service indexing and retrieval."""
        
        service_name = "test_service"
        
        # Log entries for service
        logging_service.log_structured(
            level="INFO",
            service=service_name,
            operation="service_operation",
            message="Service performed operation"
        )
        
        # Retrieve logs by service
        logs = logging_service.get_logs_by_service(service_name, hours=1)
        
        # Verify logs are retrieved
        assert len(logs) == 1
        assert logs[0]["service"] == service_name
    
    def test_log_search(self, logging_service):
        """Test log search functionality."""
        
        # Log entries with different content
        logging_service.log_structured(
            level="INFO",
            service="search_service",
            operation="search_operation",
            message="This is a searchable message"
        )
        
        logging_service.log_structured(
            level="ERROR",
            service="other_service",
            operation="other_operation",
            message="This is another message"
        )
        
        # Search for specific text
        results = logging_service.search_logs("searchable", hours=1)
        assert len(results) == 1
        assert "searchable" in results[0]["message"]
        
        # Search with service filter
        results = logging_service.search_logs("message", service="other_service", hours=1)
        assert len(results) == 1
        assert results[0]["service"] == "other_service"
        
        # Search with level filter
        results = logging_service.search_logs("message", level="ERROR", hours=1)
        assert len(results) == 1
        assert results[0]["level"] == "ERROR"
    
    def test_aggregation_rules(self, logging_service):
        """Test log aggregation rules."""
        
        # Create aggregation rule
        rule = LogAggregationRule(
            name="test_rule",
            service_pattern="test_*",
            level_filter={"INFO", "WARNING"},
            time_window_minutes=60,
            max_entries=100
        )
        
        logging_service.add_aggregation_rule(rule)
        
        # Log entries that match the rule
        logging_service.log_structured(
            level="INFO",
            service="test_service",
            operation="test_op",
            message="Matching message"
        )
        
        logging_service.log_structured(
            level="ERROR",
            service="test_service",
            operation="test_op",
            message="Non-matching level"
        )
        
        logging_service.log_structured(
            level="INFO",
            service="other_service",
            operation="test_op",
            message="Non-matching service"
        )
        
        # Get aggregated logs
        aggregated = logging_service.get_aggregated_logs("test_rule")
        
        # Verify only matching logs are aggregated
        assert len(aggregated) == 1
        assert aggregated[0]["level"] == "INFO"
        assert aggregated[0]["service"] == "test_service"
    
    def test_aggregation_rule_patterns(self, logging_service):
        """Test pattern matching in aggregation rules."""
        
        # Test wildcard patterns
        rule = LogAggregationRule(
            name="wildcard_test",
            service_pattern="api_*",
            operation_pattern="*_handler"
        )
        
        logging_service.add_aggregation_rule(rule)
        
        # Log matching entry
        logging_service.log_structured(
            level="INFO",
            service="api_gateway",
            operation="request_handler",
            message="Matching entry"
        )
        
        # Log non-matching entries
        logging_service.log_structured(
            level="INFO",
            service="web_service",
            operation="request_handler",
            message="Non-matching service"
        )
        
        logging_service.log_structured(
            level="INFO",
            service="api_gateway",
            operation="process_request",
            message="Non-matching operation"
        )
        
        # Verify only matching entry is aggregated
        aggregated = logging_service.get_aggregated_logs("wildcard_test")
        assert len(aggregated) == 1
        assert aggregated[0]["service"] == "api_gateway"
        assert aggregated[0]["operation"] == "request_handler"
    
    def test_log_statistics(self, logging_service):
        """Test log statistics generation."""
        
        # Log various entries
        logging_service.log_structured(
            level="INFO",
            service="service_a",
            operation="op_1",
            message="Info message",
            user_id="user_1",
            duration_ms=100.0
        )
        
        logging_service.log_structured(
            level="ERROR",
            service="service_b",
            operation="op_2",
            message="Error message",
            user_id="user_2",
            duration_ms=200.0,
            error_type="TestError"
        )
        
        logging_service.log_structured(
            level="WARNING",
            service="service_a",
            operation="op_1",
            message="Warning message",
            user_id="user_1",
            duration_ms=150.0
        )
        
        # Get statistics
        stats = logging_service.get_log_statistics(hours=1)
        
        # Verify statistics
        assert stats["total_logs"] == 3
        assert stats["level_distribution"]["INFO"] == 1
        assert stats["level_distribution"]["ERROR"] == 1
        assert stats["level_distribution"]["WARNING"] == 1
        assert stats["service_distribution"]["service_a"] == 2
        assert stats["service_distribution"]["service_b"] == 1
        assert stats["active_users"] == 2
        assert stats["average_duration_ms"] == 150.0  # (100 + 200 + 150) / 3
    
    def test_export_logs(self, logging_service):
        """Test log export functionality."""
        
        # Log some entries
        correlation_id = logging_service.log_structured(
            level="INFO",
            service="export_test",
            operation="test_export",
            message="Export test message"
        )
        
        # Export logs
        with tempfile.TemporaryDirectory() as temp_dir:
            filepath = os.path.join(temp_dir, "test_export.json")
            
            result_filepath = logging_service.export_structured_logs(
                filepath=filepath,
                format="json",
                hours=1
            )
            
            # Verify file was created
            assert os.path.exists(result_filepath)
            assert result_filepath == filepath
            
            # Verify file content
            with open(filepath, 'r') as f:
                export_data = json.load(f)
            
            assert "logs" in export_data
            assert len(export_data["logs"]) == 1
            assert export_data["logs"][0]["correlation_id"] == correlation_id
    
    def test_export_by_correlation_id(self, logging_service):
        """Test log export filtered by correlation ID."""
        
        # Log entries with different correlation IDs
        correlation_id_1 = logging_service.log_structured(
            level="INFO",
            service="test",
            operation="op1",
            message="Message 1"
        )
        
        correlation_id_2 = logging_service.log_structured(
            level="INFO",
            service="test",
            operation="op2",
            message="Message 2"
        )
        
        # Export logs for specific correlation ID
        with tempfile.TemporaryDirectory() as temp_dir:
            filepath = os.path.join(temp_dir, "correlation_export.json")
            
            logging_service.export_structured_logs(
                filepath=filepath,
                correlation_id=correlation_id_1
            )
            
            # Verify only logs with specified correlation ID are exported
            with open(filepath, 'r') as f:
                export_data = json.load(f)
            
            assert len(export_data["logs"]) == 1
            assert export_data["logs"][0]["correlation_id"] == correlation_id_1
    
    def test_convenience_functions(self):
        """Test convenience logging functions."""
        
        # Test log_structured function
        correlation_id = log_structured(
            "INFO",
            "convenience_test",
            "test_operation",
            "Test message"
        )
        
        assert correlation_id is not None
        
        # Test specific level functions
        log_info_structured("test_service", "info_op", "Info message")
        log_warning_structured("test_service", "warning_op", "Warning message")
        log_error_structured("test_service", "error_op", "Error message")
        
        # Verify logs were created
        service = get_structured_logging_service()
        logs = service.get_logs_by_service("test_service", hours=1)
        assert len(logs) >= 3  # At least the 3 we just logged
    
    @pytest.mark.asyncio
    async def test_structured_trace_operation(self):
        """Test structured trace operation context manager."""
        
        # Test successful operation
        async with structured_trace_operation(
            "test_service",
            "test_operation",
            metadata={"test": True}
        ) as correlation_id:
            assert correlation_id is not None
            # Simulate some work
            await asyncio.sleep(0.01)
        
        # Verify logs were created
        service = get_structured_logging_service()
        logs = service.get_logs_by_correlation(correlation_id)
        
        # Should have start and complete logs
        assert len(logs) >= 2
        
        # Find start and complete logs
        start_log = next((log for log in logs if log["operation"].endswith("_start")), None)
        complete_log = next((log for log in logs if log["operation"].endswith("_complete")), None)
        
        assert start_log is not None
        assert complete_log is not None
        assert start_log["tags"]["operation_phase"] == "start"
        assert complete_log["tags"]["operation_phase"] == "complete"
        assert complete_log["tags"]["status"] == "success"
    
    @pytest.mark.asyncio
    async def test_structured_trace_operation_error(self):
        """Test structured trace operation with error."""
        
        correlation_id = None
        
        # Test operation with error
        try:
            async with structured_trace_operation(
                "test_service",
                "failing_operation"
            ) as cid:
                correlation_id = cid
                raise ValueError("Test error")
        except ValueError:
            pass  # Expected
        
        # Verify error log was created
        service = get_structured_logging_service()
        logs = service.get_logs_by_correlation(correlation_id)
        
        # Find error log
        error_log = next((log for log in logs if log["operation"].endswith("_error")), None)
        
        assert error_log is not None
        assert error_log["level"] == "ERROR"
        assert error_log["tags"]["operation_phase"] == "error"
        assert error_log["tags"]["status"] == "failed"
        assert error_log["error_type"] == "ValueError"
    
    def test_processing_stats_update(self, logging_service):
        """Test processing statistics updates."""
        
        # Log several entries to update stats
        for i in range(5):
            logging_service.log_structured(
                level="INFO",
                service="stats_test",
                operation=f"operation_{i}",
                message=f"Message {i}"
            )
        
        # Verify processing stats are updated
        stats = logging_service._log_processing_stats
        assert stats["total_logs_processed"] >= 5
        assert stats["average_processing_time_ms"] > 0
        assert stats["last_processing_time"] is not None
    
    def test_retention_policy_management(self, logging_service):
        """Test retention policy management."""
        
        # Create retention policy
        policy = LogRetentionPolicy(
            name="test_policy",
            retention_days=30,
            archive_after_days=7,
            compression_enabled=True,
            archive_location="test_archive"
        )
        
        logging_service.add_retention_policy(policy)
        
        # Verify policy is stored
        assert "test_policy" in logging_service._retention_policies
        stored_policy = logging_service._retention_policies["test_policy"]
        assert stored_policy.name == "test_policy"
        assert stored_policy.retention_days == 30
        assert stored_policy.archive_after_days == 7
    
    def test_aggregation_rule_management(self, logging_service):
        """Test aggregation rule management."""
        
        # Create and add rule
        rule = LogAggregationRule(
            name="management_test",
            service_pattern="test_*",
            max_entries=50
        )
        
        logging_service.add_aggregation_rule(rule)
        
        # Verify rule is stored
        assert "management_test" in logging_service._aggregation_rules
        
        # Remove rule
        logging_service.remove_aggregation_rule("management_test")
        
        # Verify rule is removed
        assert "management_test" not in logging_service._aggregation_rules
        assert "management_test" not in logging_service._aggregated_logs
    
    def test_time_window_filtering(self, logging_service):
        """Test time window filtering in queries."""
        
        # Mock datetime to control timestamps
        with patch('src.multimodal_librarian.monitoring.structured_logging_service.datetime') as mock_datetime:
            # Set current time
            current_time = datetime(2024, 1, 15, 12, 0, 0)
            mock_datetime.now.return_value = current_time
            
            # Create log entry with mocked timestamp
            log_entry = StructuredLogEntry(
                timestamp=current_time - timedelta(hours=2),  # 2 hours ago
                level="INFO",
                service="time_test",
                operation="test_op",
                message="Old message",
                correlation_id="test-correlation"
            )
            
            logging_service._structured_logs.append(log_entry)
            logging_service._service_index["time_test"].append(log_entry)
            
            # Query with 1 hour window (should not find the log)
            logs_1h = logging_service.get_logs_by_service("time_test", hours=1)
            assert len(logs_1h) == 0
            
            # Query with 3 hour window (should find the log)
            logs_3h = logging_service.get_logs_by_service("time_test", hours=3)
            assert len(logs_3h) == 1


class TestStructuredLoggingIntegration:
    """Integration tests for structured logging with other components."""
    
    def test_global_service_instance(self):
        """Test global service instance management."""
        
        # Get service instances
        service1 = get_structured_logging_service()
        service2 = get_structured_logging_service()
        
        # Verify same instance is returned
        assert service1 is service2
        
        # Log to one instance
        correlation_id = service1.log_structured(
            level="INFO",
            service="global_test",
            operation="test_op",
            message="Global test message"
        )
        
        # Verify log is accessible from other instance
        logs = service2.get_logs_by_correlation(correlation_id)
        assert len(logs) == 1
    
    def test_compatibility_with_base_logging(self):
        """Test compatibility with base logging service."""
        
        logging_service = StructuredLoggingService()
        
        # Mock base logging service
        with patch.object(logging_service, 'base_logging_service') as mock_base:
            # Log structured entry
            logging_service.log_structured(
                level="INFO",
                service="compatibility_test",
                operation="test_op",
                message="Compatibility test"
            )
            
            # Verify base logging service was called
            mock_base.log_structured.assert_called_once()
    
    def test_error_handling_in_logging(self):
        """Test error handling during logging operations."""
        
        logging_service = StructuredLoggingService()
        
        # Mock an error in processing
        with patch.object(logging_service, '_apply_aggregation_rules', side_effect=Exception("Test error")):
            # Logging should still work despite aggregation error
            correlation_id = logging_service.log_structured(
                level="INFO",
                service="error_test",
                operation="test_op",
                message="Error handling test"
            )
            
            # Verify log was still stored
            assert correlation_id is not None
            logs = logging_service.get_logs_by_correlation(correlation_id)
            assert len(logs) == 1
    
    def test_thread_safety(self):
        """Test thread safety of logging operations."""
        
        logging_service = StructuredLoggingService()
        
        import threading
        import time
        
        results = []
        
        def log_worker(worker_id):
            """Worker function for threading test."""
            for i in range(10):
                correlation_id = logging_service.log_structured(
                    level="INFO",
                    service=f"worker_{worker_id}",
                    operation=f"operation_{i}",
                    message=f"Worker {worker_id} message {i}"
                )
                results.append(correlation_id)
                time.sleep(0.001)  # Small delay
        
        # Create and start multiple threads
        threads = []
        for worker_id in range(3):
            thread = threading.Thread(target=log_worker, args=(worker_id,))
            threads.append(thread)
            thread.start()
        
        # Wait for all threads to complete
        for thread in threads:
            thread.join()
        
        # Verify all logs were created
        assert len(results) == 30  # 3 workers * 10 logs each
        assert len(set(results)) == 30  # All correlation IDs should be unique
        
        # Verify logs are accessible
        total_logs = 0
        for correlation_id in results:
            logs = logging_service.get_logs_by_correlation(correlation_id)
            assert len(logs) == 1
            total_logs += len(logs)
        
        assert total_logs == 30


if __name__ == "__main__":
    pytest.main([__file__])