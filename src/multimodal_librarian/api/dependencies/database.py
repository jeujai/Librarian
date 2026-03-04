"""
FastAPI Dependencies for Database Components

This module provides backward compatibility for imports from the original
database.py dependency module. All dependencies have been consolidated
into services.py for a single source of truth.

DEPRECATED: Import directly from services.py or the __init__.py module instead.

Example:
    # Old (deprecated):
    from api.dependencies.database import get_vector_store
    
    # New (recommended):
    from api.dependencies import get_vector_store
    # or
    from api.dependencies.services import get_vector_store
"""

import logging
import warnings

logger = logging.getLogger(__name__)

# Re-export all component dependencies from services.py for backward compatibility
from .services import (
    # Component dependencies
    get_vector_store,
    get_vector_store_optional,
    get_search_service,
    get_search_service_optional,
    get_conversation_manager,
    get_conversation_manager_optional,
    get_query_processor,
    get_query_processor_optional,
    get_multimedia_generator,
    get_export_engine,
    # Cache management
    clear_dependency_cache,
    clear_all_caches,
)

# Log deprecation warning on import (only once)
logger.debug(
    "database.py is deprecated. Import from api.dependencies or api.dependencies.services instead."
)

__all__ = [
    # Component dependencies
    "get_vector_store",
    "get_vector_store_optional",
    "get_search_service",
    "get_search_service_optional",
    "get_conversation_manager",
    "get_conversation_manager_optional",
    "get_query_processor",
    "get_query_processor_optional",
    "get_multimedia_generator",
    "get_export_engine",
    # Cache management
    "clear_dependency_cache",
    "clear_all_caches",
]
