"""
Graceful Shutdown Handler for Multimodal Librarian Application

This module provides comprehensive graceful shutdown handling for the application,
ensuring all resources are properly cleaned up when the application receives
shutdown signals (SIGTERM, SIGINT).

Features:
- Signal handler registration for SIGTERM and SIGINT
- Coordinated shutdown of all application components
- Database connection cleanup
- Background task cancellation
- Resource cleanup and validation
- Configurable shutdown timeouts
- Shutdown status monitoring

Usage:
    from multimodal_librarian.shutdown.graceful_shutdown_handler import GracefulShutdownHandler
    
    # Initialize shutdown handler
    shutdown_handler = GracefulShutdownHandler()
    
    # Register shutdown handler with FastAPI app
    shutdown_handler.register_with_app(app)
    
    # Register custom cleanup functions
    shutdown_handler.register_cleanup_function(my_cleanup_function)
    
    # Start monitoring (optional)
    await shutdown_handler.start_monitoring()

Integration with FastAPI Lifespan:
    The shutdown handler integrates with FastAPI's lifespan context manager
    to ensure proper cleanup during application shutdown.
"""

import asyncio
import logging
import signal
import time
import threading
from typing import List, Callable, Optional, Dict, Any
from contextlib import asynccontextmanager
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)


class GracefulShutdownHandler:
    """
    Handles graceful shutdown of the application and all its components.
    
    This class provides a centralized way to manage application shutdown,
    ensuring all resources are properly cleaned up and all components
    are given time to finish their work gracefully.
    """
    
    def __init__(self, shutdown_timeout: int = 30, force_timeout: int = 60):
        """
        Initialize the graceful shutdown handler.
        
        Args:
            shutdown_timeout: Time to wait for graceful shutdown (seconds)
            force_timeout: Time to wait before forcing shutdown (seconds)
        """
        self.shutdown_timeout = shutdown_timeout
        self.force_timeout = force_timeout
        self.shutdown_requested = False
        self.shutdown_completed = False
        self.shutdown_start_time = None
        
        # Cleanup functions to call during shutdown
        self.cleanup_functions: List[Callable] = []
        
        # Background tasks to cancel during shutdown
        self.background_tasks: List[asyncio.Task] = []
        
        # Shutdown status tracking
        self.shutdown_status = {
            "phase": "running",
            "components_shutdown": [],
            "errors": [],
            "start_time": None,
            "end_time": None
        }
        
        # Thread-safe event for shutdown coordination
        self.shutdown_event = asyncio.Event()
        
        logger.info("GracefulShutdownHandler initialized")
    
    def register_cleanup_function(self, func: Callable) -> None:
        """
        Register a cleanup function to be called during shutdown.
        
        Args:
            func: Function to call during shutdown (can be sync or async)
        """
        self.cleanup_functions.append(func)
        logger.debug(f"Registered cleanup function: {func.__name__}")
    
    def register_background_task(self, task: asyncio.Task) -> None:
        """
        Register a background task to be cancelled during shutdown.
        
        Args:
            task: Background task to cancel during shutdown
        """
        self.background_tasks.append(task)
        logger.debug(f"Registered background task: {task.get_name()}")
    
    def setup_signal_handlers(self) -> None:
        """Set up signal handlers for graceful shutdown."""
        def signal_handler(signum, frame):
            logger.info(f"📡 Received signal {signum}, initiating graceful shutdown...")
            self.request_shutdown()
        
        # Register signal handlers
        signal.signal(signal.SIGTERM, signal_handler)
        signal.signal(signal.SIGINT, signal_handler)
        
        logger.info("Signal handlers registered for SIGTERM and SIGINT")
    
    def request_shutdown(self) -> None:
        """Request graceful shutdown of the application."""
        if self.shutdown_requested:
            logger.warning("Shutdown already requested")
            return
        
        self.shutdown_requested = True
        self.shutdown_start_time = time.time()
        self.shutdown_status["phase"] = "shutdown_requested"
        self.shutdown_status["start_time"] = datetime.now().isoformat()
        
        logger.info("🛑 Graceful shutdown requested")
        
        # Set the shutdown event to notify waiting coroutines
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                loop.call_soon_threadsafe(self.shutdown_event.set)
        except RuntimeError:
            # No event loop running, will be handled by lifespan
            pass
    
    async def wait_for_shutdown(self) -> None:
        """Wait for shutdown to be requested."""
        await self.shutdown_event.wait()
    
    async def perform_shutdown(self) -> bool:
        """
        Perform the actual graceful shutdown.
        
        Returns:
            True if shutdown was successful, False otherwise
        """
        if self.shutdown_completed:
            logger.warning("Shutdown already completed")
            return True
        
        logger.info("=" * 80)
        logger.info("🛑 STARTING GRACEFUL APPLICATION SHUTDOWN")
        logger.info("=" * 80)
        
        self.shutdown_status["phase"] = "shutting_down"
        
        try:
            # Phase 1: Cancel background tasks
            await self._cancel_background_tasks()
            
            # Phase 2: Execute cleanup functions
            await self._execute_cleanup_functions()
            
            # Phase 3: Close database connections
            await self._close_database_connections()
            
            # Phase 4: Final cleanup
            await self._final_cleanup()
            
            self.shutdown_completed = True
            self.shutdown_status["phase"] = "completed"
            self.shutdown_status["end_time"] = datetime.now().isoformat()
            
            shutdown_duration = time.time() - self.shutdown_start_time
            logger.info("=" * 80)
            logger.info(f"✅ GRACEFUL SHUTDOWN COMPLETED in {shutdown_duration:.2f}s")
            logger.info("=" * 80)
            
            return True
            
        except Exception as e:
            logger.error(f"❌ Error during graceful shutdown: {e}")
            self.shutdown_status["errors"].append(str(e))
            self.shutdown_status["phase"] = "failed"
            return False
    
    async def _cancel_background_tasks(self) -> None:
        """Cancel all registered background tasks."""
        logger.info("🔄 Phase 1: Cancelling background tasks...")
        
        if not self.background_tasks:
            logger.info("No background tasks to cancel")
            return
        
        # Cancel all tasks
        for task in self.background_tasks:
            if not task.done():
                task.cancel()
                logger.debug(f"Cancelled task: {task.get_name()}")
        
        # Wait for tasks to complete cancellation
        if self.background_tasks:
            try:
                await asyncio.wait_for(
                    asyncio.gather(*self.background_tasks, return_exceptions=True),
                    timeout=10.0
                )
                logger.info("✅ All background tasks cancelled")
            except asyncio.TimeoutError:
                logger.warning("⚠️ Some background tasks did not cancel within timeout")
        
        self.shutdown_status["components_shutdown"].append("background_tasks")
    
    async def _execute_cleanup_functions(self) -> None:
        """Execute all registered cleanup functions."""
        logger.info("🧹 Phase 2: Executing cleanup functions...")
        
        if not self.cleanup_functions:
            logger.info("No cleanup functions to execute")
            return
        
        for func in self.cleanup_functions:
            try:
                logger.debug(f"Executing cleanup function: {func.__name__}")
                
                if asyncio.iscoroutinefunction(func):
                    await asyncio.wait_for(func(), timeout=5.0)
                else:
                    # Run sync function in thread pool to avoid blocking
                    await asyncio.get_event_loop().run_in_executor(None, func)
                
                logger.debug(f"✅ Cleanup function completed: {func.__name__}")
                
            except asyncio.TimeoutError:
                logger.error(f"⚠️ Cleanup function timed out: {func.__name__}")
                self.shutdown_status["errors"].append(f"Timeout: {func.__name__}")
            except Exception as e:
                logger.error(f"❌ Error in cleanup function {func.__name__}: {e}")
                self.shutdown_status["errors"].append(f"{func.__name__}: {e}")
        
        logger.info("✅ Cleanup functions executed")
        self.shutdown_status["components_shutdown"].append("cleanup_functions")
    
    async def _close_database_connections(self) -> None:
        """Close all database connections."""
        logger.info("🗄️ Phase 3: Closing database connections...")
        
        try:
            from ..clients.database_factory import graceful_shutdown as db_shutdown
            await asyncio.wait_for(db_shutdown(), timeout=15.0)
            logger.info("✅ Database connections closed")
            self.shutdown_status["components_shutdown"].append("database_connections")
        except asyncio.TimeoutError:
            logger.error("⚠️ Database connection shutdown timed out")
            self.shutdown_status["errors"].append("Database shutdown timeout")
        except Exception as e:
            logger.error(f"❌ Error closing database connections: {e}")
            self.shutdown_status["errors"].append(f"Database shutdown: {e}")
    
    async def _final_cleanup(self) -> None:
        """Perform final cleanup operations."""
        logger.info("🏁 Phase 4: Final cleanup...")
        
        try:
            # Clear task references
            self.background_tasks.clear()
            
            # Clear cleanup function references
            self.cleanup_functions.clear()
            
            # Log final status
            logger.info(f"Components shutdown: {', '.join(self.shutdown_status['components_shutdown'])}")
            if self.shutdown_status["errors"]:
                logger.warning(f"Errors during shutdown: {len(self.shutdown_status['errors'])}")
            
            logger.info("✅ Final cleanup completed")
            self.shutdown_status["components_shutdown"].append("final_cleanup")
            
        except Exception as e:
            logger.error(f"❌ Error during final cleanup: {e}")
            self.shutdown_status["errors"].append(f"Final cleanup: {e}")
    
    def get_shutdown_status(self) -> Dict[str, Any]:
        """Get current shutdown status."""
        status = self.shutdown_status.copy()
        
        if self.shutdown_start_time:
            status["duration_seconds"] = time.time() - self.shutdown_start_time
        
        status["shutdown_requested"] = self.shutdown_requested
        status["shutdown_completed"] = self.shutdown_completed
        
        return status
    
    @asynccontextmanager
    async def lifespan_context(self, app):
        """
        FastAPI lifespan context manager with graceful shutdown.
        
        This can be used as a FastAPI lifespan context manager to ensure
        graceful shutdown is properly handled.
        
        Usage:
            shutdown_handler = GracefulShutdownHandler()
            
            @asynccontextmanager
            async def lifespan(app: FastAPI):
                async with shutdown_handler.lifespan_context(app):
                    yield
            
            app = FastAPI(lifespan=lifespan)
        """
        # Setup signal handlers
        self.setup_signal_handlers()
        
        # Store app reference
        self.app = app
        
        logger.info("Application startup completed with graceful shutdown handler")
        
        try:
            yield
        finally:
            # Perform graceful shutdown
            if not self.shutdown_completed:
                await self.perform_shutdown()


# Global shutdown handler instance
_shutdown_handler: Optional[GracefulShutdownHandler] = None


def get_shutdown_handler() -> GracefulShutdownHandler:
    """Get or create the global shutdown handler instance."""
    global _shutdown_handler
    
    if _shutdown_handler is None:
        _shutdown_handler = GracefulShutdownHandler()
    
    return _shutdown_handler


def register_cleanup_function(func: Callable) -> None:
    """Register a cleanup function with the global shutdown handler."""
    handler = get_shutdown_handler()
    handler.register_cleanup_function(func)


def register_background_task(task: asyncio.Task) -> None:
    """Register a background task with the global shutdown handler."""
    handler = get_shutdown_handler()
    handler.register_background_task(task)


async def wait_for_shutdown() -> None:
    """Wait for shutdown to be requested."""
    handler = get_shutdown_handler()
    await handler.wait_for_shutdown()


def request_shutdown() -> None:
    """Request graceful shutdown of the application."""
    handler = get_shutdown_handler()
    handler.request_shutdown()


async def perform_shutdown() -> bool:
    """Perform graceful shutdown of the application."""
    handler = get_shutdown_handler()
    return await handler.perform_shutdown()


def get_shutdown_status() -> Dict[str, Any]:
    """Get current shutdown status."""
    handler = get_shutdown_handler()
    return handler.get_shutdown_status()