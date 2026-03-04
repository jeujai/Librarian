"""Logging configuration for YAGO components."""

import structlog

from multimodal_librarian.logging_config import get_logger


def get_yago_logger(name: str) -> structlog.BoundLogger:
    """Get a structured logger for YAGO components."""
    return get_logger(f"yago.{name}")


class YagoLoggerMixin:
    """Mixin class to add YAGO-specific logging capabilities."""

    @property
    def logger(self) -> structlog.BoundLogger:
        """Get logger instance for this class."""
        return get_yago_logger(self.__class__.__name__)


def log_progress(
    operation: str,
    processed: int,
    total: int | None = None,
    rate: float | None = None,
) -> dict:
    """Create a log context for progress updates."""
    context = {
        "operation": operation,
        "processed": processed,
    }
    if total is not None:
        context["total"] = total
        context["percentage"] = round(processed / total * 100, 2) if total > 0 else 0
    if rate is not None:
        context["rate_per_second"] = round(rate, 2)
    return context


def log_import_metrics(
    entities_imported: int,
    relationships_created: int,
    failed_batches: int,
    duration_seconds: float,
) -> dict:
    """Create a log context for import metrics."""
    return {
        "entities_imported": entities_imported,
        "relationships_created": relationships_created,
        "failed_batches": failed_batches,
        "duration_seconds": round(duration_seconds, 2),
        "entities_per_second": round(entities_imported / duration_seconds, 2) if duration_seconds > 0 else 0,
    }