"""
Logging configuration for the Multimodal Librarian system.

This module sets up structured logging with rich formatting for development
and JSON formatting for production environments.
"""

import logging
import sys
from typing import Any, Dict

import structlog
from rich.console import Console
from rich.logging import RichHandler

from .config import get_settings


def configure_logging() -> None:
    """Configure structured logging for the application."""
    settings = get_settings()
    
    # Configure standard library logging
    if settings.debug:
        logging.basicConfig(
            format="%(message)s",
            level=getattr(logging, settings.log_level.upper()),
            handlers=[
                RichHandler(
                    console=Console(stderr=True),
                    show_time=True,
                    show_path=True,
                    markup=True,
                    rich_tracebacks=True,
                )
            ],
        )
    else:
        logging.basicConfig(
            format="%(message)s",
            stream=sys.stdout,
            level=getattr(logging, settings.log_level.upper()),
        )
    
    # Configure structlog
    processors = [
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.StackInfoRenderer(),
        structlog.dev.set_exc_info,
    ]
    
    if settings.debug:
        # Development: use rich formatting
        processors.extend([
            structlog.dev.ConsoleRenderer(colors=True),
        ])
    else:
        # Production: use JSON formatting
        processors.extend([
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.JSONRenderer(),
        ])
    
    structlog.configure(
        processors=processors,
        wrapper_class=structlog.make_filtering_bound_logger(
            getattr(logging, settings.log_level.upper())
        ),
        logger_factory=structlog.WriteLoggerFactory(),
        cache_logger_on_first_use=True,
    )


def get_logger(name: str) -> structlog.BoundLogger:
    """Get a structured logger instance."""
    return structlog.get_logger(name)


class LoggerMixin:
    """Mixin class to add logging capabilities to any class."""
    
    @property
    def logger(self) -> structlog.BoundLogger:
        """Get logger instance for this class."""
        return get_logger(self.__class__.__name__)


def log_function_call(func_name: str, **kwargs: Any) -> Dict[str, Any]:
    """Create a log context for function calls."""
    return {
        "function": func_name,
        "parameters": {k: str(v) for k, v in kwargs.items()},
    }


def log_performance(operation: str, duration: float, **metadata: Any) -> Dict[str, Any]:
    """Create a log context for performance metrics."""
    return {
        "operation": operation,
        "duration_seconds": duration,
        "metadata": metadata,
    }