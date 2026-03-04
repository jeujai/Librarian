"""
Logging Module for Multimodal Librarian

This module provides comprehensive logging capabilities including:
- Startup logging and phase tracking
- User experience logging and analytics
- Log aggregation and analysis
- Log search and filtering
- Structured logging services

The module integrates with the application startup process to provide
detailed insights into performance, errors, and user interactions.
"""

from .startup_logger import StartupLogger, StartupLogEntry
from .ux_logger import UserExperienceLogger
from .log_aggregator import LogAggregator, get_log_aggregator, initialize_log_aggregator
from .log_search_service import LogSearchService, get_log_search_service, initialize_log_search_service

__all__ = [
    "StartupLogger",
    "StartupLogEntry", 
    "UserExperienceLogger",
    "LogAggregator",
    "get_log_aggregator",
    "initialize_log_aggregator",
    "LogSearchService",
    "get_log_search_service",
    "initialize_log_search_service"
]