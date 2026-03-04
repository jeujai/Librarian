"""
Graceful Shutdown Module for Multimodal Librarian

This module provides comprehensive graceful shutdown handling for the application,
ensuring all resources are properly cleaned up when the application receives
shutdown signals.

Key Components:
- GracefulShutdownHandler: Main shutdown coordination class
- Signal handling for SIGTERM and SIGINT
- Database connection cleanup
- Background task cancellation
- Resource cleanup and validation

Usage:
    from multimodal_librarian.shutdown import (
        get_shutdown_handler,
        register_cleanup_function,
        register_background_task,
        request_shutdown,
        perform_shutdown
    )
"""

from .graceful_shutdown_handler import (
    GracefulShutdownHandler,
    get_shutdown_handler,
    register_cleanup_function,
    register_background_task,
    wait_for_shutdown,
    request_shutdown,
    perform_shutdown,
    get_shutdown_status
)

__all__ = [
    "GracefulShutdownHandler",
    "get_shutdown_handler",
    "register_cleanup_function", 
    "register_background_task",
    "wait_for_shutdown",
    "request_shutdown",
    "perform_shutdown",
    "get_shutdown_status"
]