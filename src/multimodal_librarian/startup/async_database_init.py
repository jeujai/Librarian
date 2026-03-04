"""
Asynchronous Database Initialization Manager

This module handles asynchronous initialization of database connections (OpenSearch and Neptune)
to prevent blocking the health check endpoint during startup.

Key Features:
- Non-blocking database initialization
- Respects SKIP_* environment variables
- Configurable timeouts
- Graceful error handling
- Status tracking
"""

import asyncio
import logging
import os
from datetime import datetime
from enum import Enum
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


class DatabaseInitStatus(Enum):
    """Database initialization status states."""
    NOT_STARTED = "not_started"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


class AsyncDatabaseInitManager:
    """
    Manages asynchronous initialization of database connections.
    
    This ensures that database initialization doesn't block the health check endpoint,
    allowing the application to pass ALB health checks while databases initialize in the background.
    """
    
    def __init__(self):
        """Initialize the async database init manager."""
        self.opensearch_status = DatabaseInitStatus.NOT_STARTED
        self.neptune_status = DatabaseInitStatus.NOT_STARTED
        self.opensearch_error: Optional[str] = None
        self.neptune_error: Optional[str] = None
        self.start_time: Optional[datetime] = None
        self.completion_time: Optional[datetime] = None
        
        # Read environment variables
        self.skip_opensearch = os.getenv('SKIP_OPENSEARCH_INIT', 'false').lower() == 'true'
        self.skip_neptune = os.getenv('SKIP_NEPTUNE_INIT', 'false').lower() == 'true'
        self.skip_vector_search = os.getenv('ENABLE_VECTOR_SEARCH', 'true').lower() == 'false'
        self.opensearch_timeout = int(os.getenv('OPENSEARCH_TIMEOUT', '10'))
        self.neptune_timeout = int(os.getenv('NEPTUNE_TIMEOUT', '10'))
        
        logger.info(f"AsyncDatabaseInitManager initialized:")
        logger.info(f"  - SKIP_OPENSEARCH_INIT: {self.skip_opensearch}")
        logger.info(f"  - SKIP_NEPTUNE_INIT: {self.skip_neptune}")
        logger.info(f"  - ENABLE_VECTOR_SEARCH: {not self.skip_vector_search}")
        logger.info(f"  - OPENSEARCH_TIMEOUT: {self.opensearch_timeout}s")
        logger.info(f"  - NEPTUNE_TIMEOUT: {self.neptune_timeout}s")
    
    async def initialize_databases(self) -> None:
        """
        Initialize databases asynchronously in the background.
        
        This method runs in a background task and doesn't block the main application startup.
        """
        self.start_time = datetime.now()
        logger.info("=" * 80)
        logger.info("ASYNC DATABASE INITIALIZATION STARTING")
        logger.info("=" * 80)
        
        # Initialize databases in parallel
        tasks = []
        
        if not self.skip_opensearch and not self.skip_vector_search:
            tasks.append(self._initialize_opensearch())
        else:
            self.opensearch_status = DatabaseInitStatus.SKIPPED
            logger.info("OpenSearch initialization skipped (SKIP_OPENSEARCH_INIT=true or ENABLE_VECTOR_SEARCH=false)")
        
        if not self.skip_neptune:
            tasks.append(self._initialize_neptune())
        else:
            self.neptune_status = DatabaseInitStatus.SKIPPED
            logger.info("Neptune initialization skipped (SKIP_NEPTUNE_INIT=true)")
        
        if tasks:
            # Run all initialization tasks in parallel
            await asyncio.gather(*tasks, return_exceptions=True)
        
        self.completion_time = datetime.now()
        duration = (self.completion_time - self.start_time).total_seconds()
        
        logger.info("=" * 80)
        logger.info(f"ASYNC DATABASE INITIALIZATION COMPLETED in {duration:.2f}s")
        logger.info(f"  - OpenSearch: {self.opensearch_status.value}")
        logger.info(f"  - Neptune: {self.neptune_status.value}")
        logger.info("=" * 80)
    
    async def _initialize_opensearch(self) -> None:
        """Initialize OpenSearch connection asynchronously."""
        self.opensearch_status = DatabaseInitStatus.IN_PROGRESS
        logger.info("Initializing OpenSearch connection...")
        
        try:
            # Import here to avoid blocking at module level
            from ..clients.opensearch_client import OpenSearchClient

            # Run initialization with timeout
            opensearch_client = await asyncio.wait_for(
                asyncio.to_thread(self._init_opensearch_sync),
                timeout=self.opensearch_timeout
            )
            
            self.opensearch_status = DatabaseInitStatus.COMPLETED
            logger.info("✓ OpenSearch initialization completed successfully")
            
        except asyncio.TimeoutError:
            self.opensearch_status = DatabaseInitStatus.FAILED
            self.opensearch_error = f"Initialization timed out after {self.opensearch_timeout}s"
            logger.error(f"✗ OpenSearch initialization failed: {self.opensearch_error}")
            
        except Exception as e:
            self.opensearch_status = DatabaseInitStatus.FAILED
            self.opensearch_error = str(e)
            logger.error(f"✗ OpenSearch initialization failed: {e}")
    
    def _init_opensearch_sync(self):
        """Synchronous OpenSearch initialization (runs in thread pool)."""
        from ..clients.opensearch_client import OpenSearchClient
        
        client = OpenSearchClient()
        # Try to connect
        client.connect()
        return client
    
    async def _initialize_neptune(self) -> None:
        """Initialize Neptune connection asynchronously."""
        self.neptune_status = DatabaseInitStatus.IN_PROGRESS
        logger.info("Initializing Neptune connection...")
        
        try:
            # Import here to avoid blocking at module level
            from ..clients.neptune_client import get_neptune_client

            # Run initialization with timeout
            neptune_client = await asyncio.wait_for(
                asyncio.to_thread(self._init_neptune_sync),
                timeout=self.neptune_timeout
            )
            
            self.neptune_status = DatabaseInitStatus.COMPLETED
            logger.info("✓ Neptune initialization completed successfully")
            
            # Create enrichment indexes after successful connection
            await self._create_enrichment_indexes()
            
        except asyncio.TimeoutError:
            self.neptune_status = DatabaseInitStatus.FAILED
            self.neptune_error = f"Initialization timed out after {self.neptune_timeout}s"
            logger.error(f"✗ Neptune initialization failed: {self.neptune_error}")
            
        except Exception as e:
            self.neptune_status = DatabaseInitStatus.FAILED
            self.neptune_error = str(e)
            logger.error(f"✗ Neptune initialization failed: {e}")
    
    def _init_neptune_sync(self):
        """Synchronous Neptune initialization (runs in thread pool)."""
        from ..clients.neptune_client import get_neptune_client
        
        client = get_neptune_client()
        # Try to connect
        client.connect()
        return client
    
    async def _create_enrichment_indexes(self) -> None:
        """
        Create enrichment indexes after Neptune initialization.
        
        Creates indexes on:
        - ExternalEntity.q_number: For fast YAGO entity lookups
        - Concept.yago_qid: For fast entity resolution
        
        These indexes support efficient cross-document linking and
        entity disambiguation queries.
        
        Requirements: 8.1, 8.2
        """
        try:
            logger.info("Creating enrichment indexes...")
            
            from ..services.knowledge_graph_service import get_knowledge_graph_service
            
            kg_service = get_knowledge_graph_service()
            result = await kg_service.ensure_enrichment_indexes()
            
            if result["status"] == "success":
                logger.info(
                    f"✓ Enrichment indexes created: "
                    f"{len(result.get('indexes_created', []))} created, "
                    f"{len(result.get('indexes_skipped', []))} skipped"
                )
            elif result["status"] == "partial":
                logger.warning(
                    f"⚠ Enrichment indexes partially created: "
                    f"{len(result.get('indexes_created', []))} created, "
                    f"{len(result.get('errors', []))} errors"
                )
            elif result["status"] == "skipped":
                logger.info("Enrichment indexes already exist, skipped creation")
            else:
                logger.warning(
                    f"✗ Enrichment index creation failed: "
                    f"{result.get('errors', [])}"
                )
                
        except Exception as e:
            # Don't fail Neptune initialization if index creation fails
            logger.warning(f"⚠ Failed to create enrichment indexes: {e}")
    
    def get_status(self) -> Dict[str, Any]:
        """Get current database initialization status."""
        duration = None
        if self.start_time:
            end_time = self.completion_time or datetime.now()
            duration = (end_time - self.start_time).total_seconds()
        
        return {
            "opensearch": {
                "status": self.opensearch_status.value,
                "error": self.opensearch_error,
                "skipped": self.skip_opensearch or self.skip_vector_search
            },
            "neptune": {
                "status": self.neptune_status.value,
                "error": self.neptune_error,
                "skipped": self.skip_neptune
            },
            "overall_status": self._get_overall_status(),
            "start_time": self.start_time.isoformat() if self.start_time else None,
            "completion_time": self.completion_time.isoformat() if self.completion_time else None,
            "duration_seconds": duration
        }
    
    def _get_overall_status(self) -> str:
        """Get overall initialization status."""
        statuses = [self.opensearch_status, self.neptune_status]
        
        # Remove skipped from consideration
        active_statuses = [s for s in statuses if s != DatabaseInitStatus.SKIPPED]
        
        if not active_statuses:
            return "all_skipped"
        
        if all(s == DatabaseInitStatus.COMPLETED for s in active_statuses):
            return "completed"
        elif any(s == DatabaseInitStatus.FAILED for s in active_statuses):
            return "failed"
        elif any(s == DatabaseInitStatus.IN_PROGRESS for s in active_statuses):
            return "in_progress"
        else:
            return "not_started"
    
    def is_opensearch_ready(self) -> bool:
        """Check if OpenSearch is ready to use."""
        return self.opensearch_status == DatabaseInitStatus.COMPLETED
    
    def is_neptune_ready(self) -> bool:
        """Check if Neptune is ready to use."""
        return self.neptune_status == DatabaseInitStatus.COMPLETED
    
    def is_any_database_ready(self) -> bool:
        """Check if any database is ready to use."""
        return self.is_opensearch_ready() or self.is_neptune_ready()


# Global instance
_async_db_init_manager: Optional[AsyncDatabaseInitManager] = None


def get_async_db_init_manager() -> AsyncDatabaseInitManager:
    """Get or create the global async database init manager."""
    global _async_db_init_manager
    if _async_db_init_manager is None:
        _async_db_init_manager = AsyncDatabaseInitManager()
    return _async_db_init_manager


async def initialize_databases_async() -> AsyncDatabaseInitManager:
    """
    Initialize databases asynchronously.
    
    This function should be called during application startup to begin
    database initialization in the background.
    
    Returns:
        AsyncDatabaseInitManager instance
    """
    manager = get_async_db_init_manager()
    # Start initialization in background task
    asyncio.create_task(manager.initialize_databases())
    return manager
