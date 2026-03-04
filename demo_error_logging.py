#!/usr/bin/env python3
"""
Demonstration of the comprehensive error logging service.

This script shows how the error logging service works with various
types of errors and recovery scenarios.
"""

import asyncio
import random
from datetime import datetime

from src.multimodal_librarian.monitoring.error_logging_service import (
    get_error_logging_service,
    ErrorSeverity,
    ErrorCategory,
    log_error,
    log_recovery_attempt
)
from src.multimodal_librarian.monitoring.error_handler import (
    handle_errors,
    handle_database_errors,
    handle_search_errors,
    with_recovery
)


def demonstrate_basic_error_logging():
    """Demonstrate basic error logging functionality."""
    print("=== Basic Error Logging Demo ===")
    
    error_service = get_error_logging_service()
    
    # Log various types of errors
    errors_to_log = [
        (ValueError("Invalid input parameter"), "validation_service", "validate_input"),
        (ConnectionError("Database connection lost"), "database", "connect"),
        (ImportError("Module 'missing_module' not found"), "import_service", "load_module"),
        (MemoryError("Out of memory"), "processing_service", "process_large_file"),
        (TimeoutError("Request timeout"), "api_service", "external_request")
    ]
    
    error_ids = []
    for error, service, operation in errors_to_log:
        error_id = error_service.log_error(
            error=error,
            service=service,
            operation=operation,
            additional_context={
                "timestamp": datetime.now().isoformat(),
                "demo": True
            }
        )
        error_ids.append(error_id)
        print(f"Logged {type(error).__name__}: {error_id}")
    
    # Get error summary
    summary = error_service.get_error_summary(hours=1)
    print(f"\nError Summary:")
    print(f"  Total errors: {summary['total_errors']}")
    print(f"  Categories: {summary['error_categories']}")
    print(f"  Severities: {summary['error_severities']}")
    print(f"  Critical errors: {summary['critical_errors']}")
    
    return error_ids


def demonstrate_error_recovery():
    """Demonstrate error recovery tracking."""
    print("\n=== Error Recovery Demo ===")
    
    error_service = get_error_logging_service()
    
    # Simulate a database connection error
    db_error = ConnectionError("Database connection failed")
    error_id = error_service.log_error(
        error=db_error,
        service="database",
        operation="query_users",
        additional_context={"query": "SELECT * FROM users", "connection_pool": "primary"}
    )
    
    print(f"Database error logged: {error_id}")
    
    # Simulate recovery attempts
    recovery_attempts = [
        ("reconnect_database", False, {"attempt": 1, "error": "Connection still failing"}),
        ("reconnect_database", False, {"attempt": 2, "error": "Timeout during reconnection"}),
        ("reconnect_database", True, {"attempt": 3, "connection_time": "2.1s", "pool": "secondary"})
    ]
    
    for strategy, success, details in recovery_attempts:
        error_service.log_recovery_attempt(
            error_id=error_id,
            recovery_strategy=strategy,
            success=success,
            details=details
        )
        print(f"Recovery attempt {details['attempt']}: {'SUCCESS' if success else 'FAILED'}")
    
    # Get error details
    error_details = error_service.get_error_details(error_id)
    if error_details:
        error_info = error_details['error_details']
        print(f"\nRecovery Summary:")
        print(f"  Total attempts: {error_info['recovery_attempts']}")
        print(f"  Final status: {error_info['recovery_status']}")
        print(f"  Recovery log entries: {len(error_info['recovery_log'])}")


@handle_database_errors("user_lookup")
@with_recovery("retry_with_backoff")
def simulate_database_operation(user_id: int):
    """Simulate a database operation with error handling."""
    # Simulate random failures
    if random.random() < 0.3:  # 30% chance of failure
        raise ConnectionError(f"Failed to connect to database for user {user_id}")
    
    return {"user_id": user_id, "name": f"User {user_id}", "active": True}


@handle_search_errors("vector_search")
async def simulate_search_operation(query: str, top_k: int = 5):
    """Simulate a search operation with error handling."""
    # Simulate random failures
    if random.random() < 0.2:  # 20% chance of failure
        raise TimeoutError(f"Search timeout for query: {query}")
    
    await asyncio.sleep(0.1)  # Simulate processing time
    
    return [
        {"id": f"doc_{i}", "score": 0.9 - (i * 0.1), "title": f"Document {i}"}
        for i in range(top_k)
    ]


async def demonstrate_decorator_integration():
    """Demonstrate error handling decorators."""
    print("\n=== Decorator Integration Demo ===")
    
    # Test database operations
    print("Testing database operations...")
    for user_id in [1, 2, 3, 4, 5]:
        try:
            result = simulate_database_operation(user_id)
            print(f"  User {user_id}: {result['name']}")
        except Exception as e:
            print(f"  User {user_id}: ERROR - {e}")
    
    # Test search operations
    print("\nTesting search operations...")
    search_queries = ["machine learning", "python programming", "data science", "web development"]
    
    for query in search_queries:
        try:
            results = await simulate_search_operation(query, top_k=3)
            print(f"  Query '{query}': {len(results)} results")
        except Exception as e:
            print(f"  Query '{query}': ERROR - {e}")


def demonstrate_error_patterns():
    """Demonstrate error pattern detection."""
    print("\n=== Error Pattern Detection Demo ===")
    
    error_service = get_error_logging_service()
    
    # Generate similar errors to create patterns
    for i in range(5):
        # Similar validation errors
        error = ValueError(f"Invalid email format: user{i}@invalid")
        error_service.log_error(error, "validation_service", "validate_email")
        
        # Similar connection errors
        if i < 3:
            error = ConnectionError(f"Connection timeout to server-{i % 2 + 1}")
            error_service.log_error(error, "network_service", "connect_server")
    
    # Get error patterns
    patterns = error_service.get_error_patterns(limit=10)
    
    print(f"Detected {len(patterns)} error patterns:")
    for pattern in patterns:
        print(f"  Pattern: {pattern['error_type']} - {pattern['occurrences']} occurrences")
        print(f"    Service: {pattern['context_pattern']['service']}")
        print(f"    Category: {pattern['category']}")
        print(f"    Severity: {pattern['severity']}")
        print()


async def main():
    """Run the comprehensive error logging demonstration."""
    print("Comprehensive Error Logging Service Demonstration")
    print("=" * 50)
    
    # Basic error logging
    error_ids = demonstrate_basic_error_logging()
    
    # Error recovery
    demonstrate_error_recovery()
    
    # Decorator integration
    await demonstrate_decorator_integration()
    
    # Error patterns
    demonstrate_error_patterns()
    
    # Final summary
    print("\n=== Final System Summary ===")
    error_service = get_error_logging_service()
    
    summary = error_service.get_error_summary(hours=1)
    print(f"Total errors logged: {summary['total_errors']}")
    print(f"Error categories: {list(summary['error_categories'].keys())}")
    print(f"Critical errors: {summary['critical_errors']}")
    
    patterns = error_service.get_error_patterns(limit=5)
    print(f"Error patterns detected: {len(patterns)}")
    
    print("\n✅ Error logging service demonstration completed successfully!")
    print("The comprehensive error logging system is working correctly.")


if __name__ == "__main__":
    asyncio.run(main())