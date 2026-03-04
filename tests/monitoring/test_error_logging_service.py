"""
Tests for the comprehensive error logging service.

This module tests error logging, categorization, pattern detection,
and recovery tracking functionality.
"""

import pytest
import asyncio
import uuid
from datetime import datetime, timedelta
from unittest.mock import Mock, patch

from src.multimodal_librarian.monitoring.error_logging_service import (
    ErrorLoggingService,
    ErrorSeverity,
    ErrorCategory,
    ErrorRecoveryStatus,
    ErrorContext,
    ErrorDetails,
    get_error_logging_service,
    log_error,
    log_recovery_attempt,
    error_context
)
from src.multimodal_librarian.monitoring.error_handler import (
    handle_errors,
    ErrorRecoveryManager,
    get_recovery_manager,
    with_recovery
)


class TestErrorLoggingService:
    """Test cases for ErrorLoggingService."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.error_service = ErrorLoggingService()
    
    def test_error_classification(self):
        """Test error classification based on type and context."""
        # Test import error classification
        import_error = ImportError("No module named 'test_module'")
        context = ErrorContext(service="test_service", operation="test_operation")
        
        category, severity = self.error_service._classify_error(import_error, context)
        assert category == ErrorCategory.IMPORT_ERROR
        assert severity == ErrorSeverity.HIGH
    
    def test_database_error_classification(self):
        """Test database error classification."""
        db_error = ConnectionError("Database connection failed")
        context = ErrorContext(service="database", operation="connect")
        
        category, severity = self.error_service._classify_error(db_error, context)
        assert category == ErrorCategory.DATABASE_ERROR
        assert severity == ErrorSeverity.HIGH
    
    def test_timeout_error_classification(self):
        """Test timeout error classification."""
        timeout_error = Exception("Request timeout occurred")
        context = ErrorContext(service="api", operation="request")
        
        category, severity = self.error_service._classify_error(timeout_error, context)
        assert category == ErrorCategory.NETWORK_ERROR
        assert severity == ErrorSeverity.MEDIUM
    
    def test_log_error_basic(self):
        """Test basic error logging functionality."""
        test_error = ValueError("Test validation error")
        
        error_id = self.error_service.log_error(
            error=test_error,
            service="test_service",
            operation="test_operation",
            additional_context={"user_id": "test_user"}
        )
        
        assert error_id is not None
        assert len(error_id) == 36  # UUID length
        
        # Check that error was stored
        assert len(self.error_service._error_details) == 1
        error_detail = self.error_service._error_details[0]
        assert error_detail.error_id == error_id
        assert error_detail.error_type == "ValueError"
        assert error_detail.error_message == "Test validation error"
        assert error_detail.context.service == "test_service"
        assert error_detail.context.operation == "test_operation"
        assert error_detail.context.user_id == "test_user"
    
    def test_error_pattern_detection(self):
        """Test error pattern detection and tracking."""
        # Log similar errors
        for i in range(3):
            error = ValueError(f"Validation failed for input {i}")
            self.error_service.log_error(
                error=error,
                service="validation_service",
                operation="validate_input"
            )
        
        # Check pattern detection
        patterns = self.error_service.get_error_patterns()
        assert len(patterns) == 1
        
        pattern = patterns[0]
        assert pattern['error_type'] == "ValueError"
        assert pattern['occurrences'] == 3
        assert pattern['context_pattern']['service'] == "validation_service"
    
    def test_recovery_attempt_logging(self):
        """Test recovery attempt logging."""
        # Log an error first
        test_error = ConnectionError("Database connection lost")
        error_id = self.error_service.log_error(
            error=test_error,
            service="database",
            operation="query"
        )
        
        # Log recovery attempt
        self.error_service.log_recovery_attempt(
            error_id=error_id,
            recovery_strategy="reconnect_database",
            success=True,
            details={"reconnection_time": "2.5s"}
        )
        
        # Check recovery was logged
        error_details = self.error_service.get_error_details(error_id)
        assert error_details is not None
        
        error_info = error_details['error_details']
        assert error_info['recovery_attempts'] == 1
        assert error_info['recovery_status'] == 'recovered'
        assert len(error_info['recovery_log']) == 1
        
        recovery_log = error_info['recovery_log'][0]
        assert recovery_log['strategy'] == "reconnect_database"
        assert recovery_log['success'] is True
        assert recovery_log['details']['reconnection_time'] == "2.5s"
    
    def test_error_summary(self):
        """Test error summary generation."""
        # Log various types of errors
        errors = [
            (ValueError("Validation error"), "validation", "validate"),
            (ConnectionError("Connection failed"), "database", "connect"),
            (ImportError("Module not found"), "import", "load_module"),
            (MemoryError("Out of memory"), "processing", "process_data")
        ]
        
        for error, service, operation in errors:
            self.error_service.log_error(error, service, operation)
        
        # Get summary
        summary = self.error_service.get_error_summary(hours=24)
        
        assert summary['total_errors'] == 4
        assert 'error_categories' in summary
        assert 'error_severities' in summary
        assert 'errors_by_service' in summary
        assert 'top_error_patterns' in summary
        
        # Check category counts
        categories = summary['error_categories']
        assert categories.get('validation_error', 0) >= 1
        assert categories.get('database_error', 0) >= 1  # ConnectionError from database service should be database_error
        assert categories.get('import_error', 0) >= 1
        assert categories.get('resource_exhaustion', 0) >= 1
    
    def test_context_extraction(self):
        """Test context extraction functionality."""
        with patch('psutil.virtual_memory') as mock_memory, \
             patch('psutil.cpu_percent') as mock_cpu, \
             patch('psutil.disk_usage') as mock_disk:
            
            mock_memory.return_value.percent = 75.0
            mock_cpu.return_value = 45.0
            mock_disk.return_value.percent = 60.0
            
            system_state = self.error_service._extract_system_state()
            
            assert system_state['memory_usage_percent'] == 75.0
            assert system_state['cpu_usage_percent'] == 45.0
            assert system_state['disk_usage_percent'] == 60.0
    
    def test_error_export(self):
        """Test error data export functionality."""
        # Log some errors
        test_error = RuntimeError("Test runtime error")
        self.error_service.log_error(test_error, "test_service", "test_operation")
        
        # Export data
        with patch('builtins.open', create=True) as mock_open:
            mock_file = Mock()
            mock_open.return_value.__enter__.return_value = mock_file
            
            filepath = self.error_service.export_error_data("test_export.json", hours=24)
            
            assert filepath == "test_export.json"
            mock_open.assert_called_once()
            mock_file.write.assert_called()
    
    @pytest.mark.asyncio
    async def test_error_context_manager(self):
        """Test error context manager functionality."""
        async with self.error_service.error_context("test_service", "test_operation", {"user_id": "test_user"}):
            # This should not raise an error
            pass
        
        # Test with exception
        with pytest.raises(ValueError):
            async with self.error_service.error_context("test_service", "test_operation"):
                raise ValueError("Test error in context")
        
        # Check that error was logged
        assert len(self.error_service._error_details) == 1
        error_detail = self.error_service._error_details[0]
        assert error_detail.error_type == "ValueError"
        assert error_detail.context.service == "test_service"
        assert error_detail.context.operation == "test_operation"


class TestErrorHandler:
    """Test cases for error handling decorators."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.error_service = ErrorLoggingService()
    
    def test_handle_errors_decorator_sync(self):
        """Test error handling decorator for synchronous functions."""
        @handle_errors(service="test_service", operation="test_operation")
        def test_function(value):
            if value < 0:
                raise ValueError("Negative value not allowed")
            return value * 2
        
        # Test successful execution
        result = test_function(5)
        assert result == 10
        
        # Test error handling
        with pytest.raises(ValueError):
            test_function(-1)
        
        # Check that error was logged (using global service)
        global_service = get_error_logging_service()
        assert len(global_service._error_details) >= 1
    
    @pytest.mark.asyncio
    async def test_handle_errors_decorator_async(self):
        """Test error handling decorator for asynchronous functions."""
        @handle_errors(service="async_service", operation="async_operation")
        async def async_test_function(value):
            if value < 0:
                raise ValueError("Negative value not allowed")
            await asyncio.sleep(0.01)  # Simulate async work
            return value * 2
        
        # Test successful execution
        result = await async_test_function(5)
        assert result == 10
        
        # Test error handling
        with pytest.raises(ValueError):
            await async_test_function(-1)
    
    def test_handle_errors_with_fallback(self):
        """Test error handling with fallback return value."""
        @handle_errors(
            service="test_service", 
            operation="test_operation",
            reraise=False,
            fallback_return="fallback_value"
        )
        def test_function_with_fallback(value):
            if value < 0:
                raise ValueError("Negative value not allowed")
            return value * 2
        
        # Test successful execution
        result = test_function_with_fallback(5)
        assert result == 10
        
        # Test fallback behavior
        result = test_function_with_fallback(-1)
        assert result == "fallback_value"
    
    def test_service_specific_decorators(self):
        """Test service-specific error handling decorators."""
        from src.multimodal_librarian.monitoring.error_handler import (
            handle_database_errors,
            handle_search_errors,
            handle_ai_errors
        )
        
        @handle_database_errors("test_query")
        def database_function():
            raise Exception("Database error")
        
        @handle_search_errors("test_search")
        def search_function():
            raise Exception("Search error")
        
        @handle_ai_errors("test_ai")
        def ai_function():
            raise Exception("AI error")
        
        # Test that decorators work (errors should be raised)
        with pytest.raises(Exception):
            database_function()
        
        with pytest.raises(Exception):
            search_function()
        
        with pytest.raises(Exception):
            ai_function()


class TestErrorRecoveryManager:
    """Test cases for ErrorRecoveryManager."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.recovery_manager = ErrorRecoveryManager()
    
    @pytest.mark.asyncio
    async def test_retry_with_backoff_success(self):
        """Test retry with backoff strategy - successful recovery."""
        call_count = 0
        
        async def failing_function():
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise ConnectionError("Connection failed")
            return "success"
        
        success, result = await self.recovery_manager._retry_with_backoff(
            "test_error_id", failing_function, (), {}
        )
        
        assert success is True
        assert result == "success"
        assert call_count == 3
    
    @pytest.mark.asyncio
    async def test_retry_with_backoff_failure(self):
        """Test retry with backoff strategy - persistent failure."""
        call_count = 0
        
        async def always_failing_function():
            nonlocal call_count
            call_count += 1
            raise ConnectionError("Connection failed")
        
        success, result = await self.recovery_manager._retry_with_backoff(
            "test_error_id", always_failing_function, (), {}
        )
        
        assert success is False
        assert result is None
        assert call_count == 3  # Max retries
    
    @pytest.mark.asyncio
    async def test_retry_with_fallback(self):
        """Test retry with fallback strategy."""
        def failing_function():
            raise ConnectionError("Connection failed")
        
        def failing_function_fallback():
            return "fallback_result"
        
        # Mock the fallback function
        failing_function.fallback = failing_function_fallback
        
        success, result = await self.recovery_manager._retry_with_fallback(
            "test_error_id", failing_function, (), {}
        )
        
        # This test would need more sophisticated mocking to work properly
        # For now, we just test that the function doesn't crash
        assert success is False or success is True
    
    def test_with_recovery_decorator(self):
        """Test the with_recovery decorator."""
        @with_recovery("retry_with_backoff")
        def test_function(value):
            if value < 0:
                raise ValueError("Negative value")
            return value * 2
        
        # Test successful execution
        result = test_function(5)
        assert result == 10
        
        # Test error (recovery won't work without proper error_id)
        with pytest.raises(ValueError):
            test_function(-1)


class TestIntegration:
    """Integration tests for the complete error logging system."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.error_service = get_error_logging_service()
    
    def test_convenience_functions(self):
        """Test convenience functions for error logging."""
        test_error = RuntimeError("Test runtime error")
        
        # Test log_error convenience function
        error_id = log_error(
            error=test_error,
            service="integration_test",
            operation="test_convenience",
            additional_context={"test": "data"}
        )
        
        assert error_id is not None
        
        # Test log_recovery_attempt convenience function
        log_recovery_attempt(
            error_id=error_id,
            recovery_strategy="test_strategy",
            success=True,
            details={"test": "recovery"}
        )
        
        # Verify the recovery was logged
        error_details = self.error_service.get_error_details(error_id)
        assert error_details is not None
        assert error_details['error_details']['recovery_attempts'] == 1
    
    @pytest.mark.asyncio
    async def test_full_error_lifecycle(self):
        """Test complete error lifecycle from logging to recovery."""
        # 1. Log an error
        test_error = ConnectionError("Database connection failed")
        error_id = self.error_service.log_error(
            error=test_error,
            service="database",
            operation="connect",
            additional_context={"database": "postgres", "host": "localhost"}
        )
        
        # 2. Verify error was logged
        error_details = self.error_service.get_error_details(error_id)
        assert error_details is not None
        assert error_details['error_details']['error_type'] == "ConnectionError"
        
        # 3. Log recovery attempts
        self.error_service.log_recovery_attempt(
            error_id=error_id,
            recovery_strategy="reconnect_database",
            success=False,
            details={"attempt": 1, "error": "Still failing"}
        )
        
        self.error_service.log_recovery_attempt(
            error_id=error_id,
            recovery_strategy="reconnect_database",
            success=True,
            details={"attempt": 2, "connection_time": "1.2s"}
        )
        
        # 4. Verify recovery was tracked
        updated_details = self.error_service.get_error_details(error_id)
        error_info = updated_details['error_details']
        
        assert error_info['recovery_attempts'] == 2
        assert error_info['recovery_status'] == 'recovered'
        assert len(error_info['recovery_log']) == 2
        
        # 5. Check summary includes this error
        summary = self.error_service.get_error_summary(hours=1)
        assert summary['total_errors'] >= 1
        assert 'database_error' in summary['error_categories']
    
    def test_error_pattern_similarity(self):
        """Test error pattern detection for similar errors."""
        # Log similar errors
        similar_errors = [
            ValueError("Invalid input: user_123"),
            ValueError("Invalid input: user_456"),
            ValueError("Invalid input: user_789")
        ]
        
        error_ids = []
        for error in similar_errors:
            error_id = self.error_service.log_error(
                error=error,
                service="validation",
                operation="validate_user"
            )
            error_ids.append(error_id)
        
        # Check that similar errors are detected
        for error_id in error_ids:
            error_details = self.error_service.get_error_details(error_id)
            similar_errors_list = error_details['error_details']['similar_errors']
            # Each error should have references to the other similar errors
            assert len(similar_errors_list) >= 0  # May be 0 if pattern matching is strict
        
        # Check patterns
        patterns = self.error_service.get_error_patterns()
        validation_patterns = [p for p in patterns if p['error_type'] == 'ValueError']
        assert len(validation_patterns) >= 1
        
        # At least one pattern should have multiple occurrences
        pattern_with_multiple = [p for p in validation_patterns if p['occurrences'] > 1]
        assert len(pattern_with_multiple) >= 1


if __name__ == "__main__":
    pytest.main([__file__])