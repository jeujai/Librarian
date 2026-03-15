"""
Multimodal Librarian - Production Application

This is the canonical production application for the multimodal librarian system.
Consolidated from main_minimal.py during configuration cleanup.
STABILIZED: Includes proven fixes for AWS Fargate deployment.

REFACTORED: Uses FastAPI lifespan context manager for proper startup/shutdown lifecycle.
This replaces the deprecated @app.on_event("startup") and @app.on_event("shutdown") decorators.
"""

import asyncio
import json
import os
import time
from contextlib import asynccontextmanager
from datetime import datetime
from typing import AsyncGenerator

import boto3
import psycopg2
from fastapi import FastAPI, HTTPException, Response
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

# Import basic configuration
try:
    from .config import (
        get_settings,
        is_local_development,
        validate_environment_configuration,
    )
    from .logging_config import configure_logging, get_logger

    # Configure logging
    configure_logging()
    logger = get_logger("main_minimal")
    
    # Get settings with validation
    settings = get_settings()
    
    # Validate environment configuration on startup
    config_validation = validate_environment_configuration()
    if not config_validation["valid"]:
        logger.error(f"Configuration validation failed: {config_validation['errors']}")
        if settings.strict_config_validation:
            raise ValueError(f"Configuration validation failed: {config_validation['errors']}")
    
    if config_validation["warnings"]:
        logger.warning(f"Configuration warnings: {config_validation['warnings']}")
    
    logger.info(f"Configuration loaded successfully for {config_validation['environment']} environment")
    logger.info(f"Enabled features: {', '.join(config_validation.get('features_enabled', []))}")
    
    CONFIG_AVAILABLE = True
except ImportError as e:
    print(f"Configuration not available: {e}")
    CONFIG_AVAILABLE = False
    logger = None
    settings = None


# ============================================================================
# LIFESPAN CONTEXT MANAGER
# ============================================================================
# This replaces the deprecated @app.on_event("startup") and @app.on_event("shutdown")
# decorators with a proper lifespan context manager as recommended by FastAPI.
# 
# Key benefits:
# - Cleaner separation of startup and shutdown logic
# - Better resource management with context manager pattern
# - Proper cleanup guaranteed even on exceptions
# - Supports async initialization and cleanup
# ============================================================================

@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """
    FastAPI lifespan context manager for application startup and shutdown.
    
    This implements the DI pattern from the dependency-injection-architecture spec:
    - No blocking initialization during startup
    - Background tasks for non-critical initialization
    - Proper cleanup of DI-managed services on shutdown
    - Health check responds within 100ms of Uvicorn starting
    
    Validates: Requirements 1.1, 1.3, 1.5, 3.4
    """
    # ========================================================================
    # STARTUP PHASE - Must complete quickly for health checks
    # ========================================================================
    startup_start_time = time.time()
    
    # Use print to bypass logger configuration issues during early startup
    print("=" * 80, flush=True)
    print("LIFESPAN STARTUP BEGINNING", flush=True)
    print("=" * 80, flush=True)
    
    if logger:
        logger.info("=" * 80)
        logger.info("LIFESPAN STARTUP BEGINNING")
        logger.info("=" * 80)
    
    # Initialize startup phase manager (non-blocking)
    try:
        from .startup.phase_manager import StartupPhaseManager
        app.state.startup_phase_manager = StartupPhaseManager()
        if logger:
            logger.info("StartupPhaseManager initialized successfully")
    except Exception as e:
        if logger:
            logger.warning(f"Failed to initialize StartupPhaseManager: {e}")
        app.state.startup_phase_manager = None
    
    # Initialize app state for various services (all set to None initially)
    app.state.startup_metrics_collector = None
    app.state.performance_tracker = None
    app.state.startup_alerts_service = None
    app.state.minimal_server = None
    app.state.async_db_init_manager = None
    app.state.alert_evaluation_task = None
    app.state.cache_service_initialized = False
    app.state.background_init_task = None
    
    # Initialize startup logger (non-blocking)
    try:
        print("STEP 1: Initializing startup logger...", flush=True)
        if logger:
            logger.info("STEP 1: Initializing startup logger...")
        from .logging.startup_logger import initialize_startup_logger
        startup_logger = initialize_startup_logger(app.state.startup_phase_manager)
        print("✓ STEP 1 COMPLETE: Startup logger initialized successfully", flush=True)
        if logger:
            logger.info("✓ Startup logger initialized successfully")
    except Exception as e:
        print(f"✗ STEP 1 FAILED: {e}", flush=True)
        if logger:
            logger.warning(f"✗ Failed to initialize startup logger: {e}")
    
    # Initialize minimal server for fast startup (non-blocking, with timeout)
    try:
        if logger:
            logger.info("STEP 2: Initializing minimal server...")
        from .startup.minimal_server import initialize_minimal_server
        app.state.minimal_server = await asyncio.wait_for(initialize_minimal_server(), timeout=5.0)
        if logger:
            logger.info("✓ Minimal server initialized successfully")
    except asyncio.TimeoutError:
        if logger:
            logger.error("✗ TIMEOUT: Minimal server initialization took longer than 5 seconds")
    except Exception as e:
        if logger:
            logger.error(f"✗ Failed to initialize minimal server: {e}")
    
    # Start background initialization in a separate task (non-blocking)
    if logger:
        logger.info("STEP 3: Starting background initialization...")
    app.state.background_init_task = asyncio.create_task(
        _background_initialization(app)
    )
    if logger:
        logger.info("✓ Background initialization task started")
    
    startup_duration = time.time() - startup_start_time
    
    if logger:
        logger.info("=" * 80)
        logger.info(f"✓ LIFESPAN STARTUP COMPLETED in {startup_duration:.3f}s - Uvicorn will now start listening")
        logger.info("=" * 80)
    
    print("=" * 80, flush=True)
    print(f"✓ LIFESPAN STARTUP COMPLETED in {startup_duration:.3f}s - Uvicorn will now start listening", flush=True)
    print("=" * 80, flush=True)
    
    # ========================================================================
    # YIELD - Application runs here
    # ========================================================================
    yield
    
    # ========================================================================
    # SHUTDOWN PHASE - Clean up all resources
    # ========================================================================
    if logger:
        logger.info("=" * 80)
        logger.info("LIFESPAN SHUTDOWN BEGINNING")
        logger.info("=" * 80)
    
    await _shutdown_cleanup(app)
    
    if logger:
        logger.info("=" * 80)
        logger.info("✓ LIFESPAN SHUTDOWN COMPLETED")
        logger.info("=" * 80)


async def _background_initialization(app: FastAPI):
    """
    Background initialization tasks that run after Uvicorn starts listening.
    
    This function runs as a background task and does not block the main startup.
    All initialization here is non-critical for health checks.
    
    Validates: Requirements 1.5
    """
    if logger:
        logger.info("=" * 80)
        logger.info("BACKGROUND INITIALIZATION STARTING")
        logger.info("=" * 80)
    
    # Initialize user experience logger for request pattern tracking
    try:
        if logger:
            logger.info("BG STEP 1: Initializing user experience logger...")
        from .logging.ux_logger import initialize_ux_logger
        ux_logger = initialize_ux_logger(app.state.startup_phase_manager)
        if logger:
            logger.info("BG STEP 1a: Starting UX logger...")
        await asyncio.wait_for(ux_logger.start_logging(), timeout=10.0)
        if logger:
            logger.info("✓ User experience logger initialized and started successfully")
    except asyncio.TimeoutError:
        if logger:
            logger.error("✗ TIMEOUT: UX logger start_logging() took longer than 10 seconds")
    except Exception as e:
        if logger:
            logger.warning(f"✗ Failed to initialize user experience logger: {e}")
    
    # Initialize PostgreSQL database connection
    try:
        if logger:
            logger.info("BG STEP 1.5: Initializing PostgreSQL database connection...")
        from .database.connection import db_manager
        await asyncio.wait_for(
            asyncio.to_thread(db_manager.initialize),
            timeout=30.0
        )
        app.state.db_manager_initialized = True
        if logger:
            logger.info("✓ PostgreSQL database connection initialized successfully")
    except asyncio.TimeoutError:
        app.state.db_manager_initialized = False
        if logger:
            logger.error("✗ TIMEOUT: PostgreSQL initialization took longer than 30 seconds")
    except Exception as e:
        app.state.db_manager_initialized = False
        if logger:
            logger.error(f"✗ Failed to initialize PostgreSQL database: {e}")
    
    # Initialize Model Status Service (single source of truth for model availability)
    try:
        if logger:
            logger.info("BG STEP 1.6: Initializing Model Status Service...")
        from .api.dependencies.services import get_model_status_service
        model_status_service = await asyncio.wait_for(
            get_model_status_service(),
            timeout=15.0
        )
        # Start background refresh to keep status up-to-date
        await model_status_service.start_background_refresh(interval_seconds=10.0)
        app.state.model_status_service = model_status_service
        app.state.model_status_service_initialized = True
        
        # Inject ModelStatusService into MinimalServer for unified status tracking
        if app.state.minimal_server:
            app.state.minimal_server.set_model_status_service(model_status_service)
            if logger:
                logger.info("✓ ModelStatusService injected into MinimalServer")
        
        if logger:
            logger.info("✓ Model Status Service initialized successfully")
    except asyncio.TimeoutError:
        app.state.model_status_service_initialized = False
        if logger:
            logger.error("✗ TIMEOUT: Model Status Service initialization took longer than 15 seconds")
    except Exception as e:
        app.state.model_status_service_initialized = False
        if logger:
            logger.warning(f"✗ Failed to initialize Model Status Service: {e}")
    
    # Initialize progressive loader with startup phase manager
    try:
        if logger:
            logger.info("BG STEP 2: Initializing progressive loader...")
        from .startup.progressive_loader import initialize_progressive_loader
        progressive_loader = await asyncio.wait_for(
            initialize_progressive_loader(app.state.startup_phase_manager), 
            timeout=120.0
        )
        if logger:
            logger.info("✓ Progressive loader initialized successfully")
    except asyncio.TimeoutError:
        if logger:
            logger.error("✗ TIMEOUT: Progressive loader initialization took longer than 120 seconds")
    except Exception as e:
        if logger:
            logger.error(f"✗ Failed to initialize progressive loader: {e}")
    
    # Start startup phase progression
    if app.state.startup_phase_manager:
        try:
            if logger:
                logger.info("BG STEP 3: Starting phase progression...")
            await asyncio.wait_for(app.state.startup_phase_manager.start_phase_progression(), timeout=10.0)
            if logger:
                logger.info("✓ Startup phase progression started successfully")
            
            # Initialize startup metrics tracking
            try:
                if logger:
                    logger.info("BG STEP 3a: Initializing startup metrics tracking...")
                from .monitoring.performance_tracker import track_performance
                from .monitoring.startup_metrics import track_startup_metrics
                
                app.state.startup_metrics_collector = await asyncio.wait_for(
                    track_startup_metrics(app.state.startup_phase_manager), 
                    timeout=10.0
                )
                if logger:
                    logger.info("BG STEP 3b: Initializing performance tracker...")
                app.state.performance_tracker = await asyncio.wait_for(
                    track_performance(app.state.startup_phase_manager, app.state.startup_metrics_collector), 
                    timeout=10.0
                )
                
                if logger:
                    logger.info("✓ Startup metrics tracking initialized successfully")
            except asyncio.TimeoutError:
                if logger:
                    logger.error("✗ TIMEOUT: Startup metrics tracking took longer than 10 seconds")
            except Exception as e:
                if logger:
                    logger.warning(f"✗ Failed to initialize startup metrics tracking: {e}")
                    
        except asyncio.TimeoutError:
            if logger:
                logger.error("✗ TIMEOUT: Phase progression start took longer than 10 seconds")
        except Exception as e:
            if logger:
                logger.error(f"✗ Failed to start phase progression: {e}")
    else:
        if logger:
            logger.warning("⚠ Startup phase manager not available, skipping phase progression")
    
    # Initialize cache service
    try:
        if logger:
            logger.info("BG STEP 4: Initializing cache service...")
        await asyncio.wait_for(_initialize_cache_service(app), timeout=30.0)
        if logger:
            logger.info("✓ Cache service initialized successfully")
    except asyncio.TimeoutError:
        if logger:
            logger.error("✗ TIMEOUT: Cache service initialization took longer than 30 seconds")
    except Exception as e:
        if logger:
            logger.error(f"✗ Failed to initialize cache service: {e}")
    
    # Start alert evaluation
    try:
        if logger:
            logger.info("BG STEP 5: Starting alert evaluation...")
        await asyncio.wait_for(_start_alert_evaluation(app), timeout=10.0)
        if logger:
            logger.info("✓ Alert evaluation started successfully")
    except asyncio.TimeoutError:
        if logger:
            logger.error("✗ TIMEOUT: Alert evaluation start took longer than 10 seconds")
    except Exception as e:
        if logger:
            logger.error(f"✗ Failed to start alert evaluation: {e}")
    
    # Initialize health monitoring
    try:
        if logger:
            logger.info("BG STEP 6: Initializing health monitoring...")
        await asyncio.wait_for(_initialize_health_monitoring(), timeout=10.0)
        if logger:
            logger.info("✓ Health monitoring initialized successfully")
    except asyncio.TimeoutError:
        if logger:
            logger.error("✗ TIMEOUT: Health monitoring initialization took longer than 10 seconds")
    except Exception as e:
        if logger:
            logger.error(f"✗ Failed to initialize health monitoring: {e}")
    
    # Initialize local memory monitoring (for local development)
    try:
        if logger:
            logger.info("BG STEP 6.5: Initializing local memory monitoring...")
        await asyncio.wait_for(_initialize_local_memory_monitoring(app), timeout=10.0)
        if logger:
            logger.info("✓ Local memory monitoring initialized successfully")
    except asyncio.TimeoutError:
        if logger:
            logger.error("✗ TIMEOUT: Local memory monitoring initialization took longer than 10 seconds")
    except Exception as e:
        if logger:
            logger.error(f"✗ Failed to initialize local memory monitoring: {e}")
    
    # Initialize local services logging (for local development)
    try:
        if logger:
            logger.info("BG STEP 6.6: Initializing local services logging...")
        await asyncio.wait_for(_initialize_local_services_logging(app), timeout=15.0)
        if logger:
            logger.info("✓ Local services logging initialized successfully")
    except asyncio.TimeoutError:
        if logger:
            logger.error("✗ TIMEOUT: Local services logging initialization took longer than 15 seconds")
    except Exception as e:
        if logger:
            logger.error(f"✗ Failed to initialize local services logging: {e}")
    
    # Initialize database query logging (for local development)
    try:
        if logger:
            logger.info("BG STEP 6.7: Initializing database query logging...")
        await asyncio.wait_for(_initialize_database_query_logging(app), timeout=10.0)
        if logger:
            logger.info("✓ Database query logging initialized successfully")
    except asyncio.TimeoutError:
        if logger:
            logger.error("✗ TIMEOUT: Database query logging initialization took longer than 10 seconds")
    except Exception as e:
        if logger:
            logger.error(f"✗ Failed to initialize database query logging: {e}")
    
    # Initialize local error tracking and alerting (for local development)
    try:
        if logger:
            logger.info("BG STEP 6.8: Initializing local error tracking and alerting...")
        await asyncio.wait_for(_initialize_local_error_alerting(app), timeout=15.0)
        if logger:
            logger.info("✓ Local error tracking and alerting initialized successfully")
    except asyncio.TimeoutError:
        if logger:
            logger.error("✗ TIMEOUT: Local error tracking and alerting initialization took longer than 15 seconds")
    except Exception as e:
        if logger:
            logger.error(f"✗ Failed to initialize local error tracking and alerting: {e}")
    
    # Initialize log search service (for local development)
    try:
        if logger:
            logger.info("BG STEP 6.9: Initializing log search service...")
        await asyncio.wait_for(_initialize_log_search_service(app), timeout=15.0)
        if logger:
            logger.info("✓ Log search service initialized successfully")
    except asyncio.TimeoutError:
        if logger:
            logger.error("✗ TIMEOUT: Log search service initialization took longer than 15 seconds")
    except Exception as e:
        if logger:
            logger.error(f"✗ Failed to initialize log search service: {e}")
    
    # Initialize startup alerts
    try:
        if logger:
            logger.info("BG STEP 7: Initializing startup alerts...")
        await asyncio.wait_for(_initialize_startup_alerts(app), timeout=10.0)
        if logger:
            logger.info("✓ Startup alerts initialized successfully")
    except asyncio.TimeoutError:
        if logger:
            logger.error("✗ TIMEOUT: Startup alerts initialization took longer than 10 seconds")
    except Exception as e:
        if logger:
            logger.error(f"✗ Failed to initialize startup alerts: {e}")
    
    # Initialize performance alerting (for local development)
    try:
        if logger:
            logger.info("BG STEP 7.1: Initializing performance alerting...")
        await asyncio.wait_for(_initialize_performance_alerting(app), timeout=20.0)
        if logger:
            logger.info("✓ Performance alerting initialized successfully")
    except asyncio.TimeoutError:
        if logger:
            logger.error("✗ TIMEOUT: Performance alerting initialization took longer than 20 seconds")
    except Exception as e:
        if logger:
            logger.error(f"✗ Failed to initialize performance alerting: {e}")
    
    # Initialize databases asynchronously
    try:
        if logger:
            logger.info("BG STEP 7.5: Starting async database initialization...")
        from .startup.async_database_init import initialize_databases_async
        app.state.async_db_init_manager = await initialize_databases_async()
        if logger:
            logger.info("✓ Async database initialization started (running in background)")
    except Exception as e:
        if logger:
            logger.error(f"✗ Failed to start async database initialization: {e}")
    
    # Start Redis pub/sub subscriber for Celery → WebSocket progress bridge
    try:
        if logger:
            logger.info("BG STEP 7.6: Starting Redis progress subscriber...")
        app.state.redis_progress_subscriber_task = asyncio.create_task(
            _redis_progress_subscriber(app)
        )
        if logger:
            logger.info("✓ Redis progress subscriber started")
    except Exception as e:
        if logger:
            logger.error(f"✗ Failed to start Redis progress subscriber: {e}")
    
    # Log application ready state
    try:
        if logger:
            logger.info("BG STEP 8: Logging application ready state...")
        from .logging.startup_logger import log_application_ready
        log_application_ready("basic", ["health_endpoints", "basic_api", "websocket_chat"])
        if logger:
            logger.info("✓ Application ready state logged")
    except ImportError:
        if logger:
            logger.warning("⚠ Startup logger not available for ready state logging")
    except Exception as e:
        if logger:
            logger.error(f"✗ Failed to log application ready state: {e}")
    
    if logger:
        logger.info("=" * 80)
        logger.info("✓ BACKGROUND INITIALIZATION COMPLETED SUCCESSFULLY")
        logger.info("=" * 80)


async def _redis_progress_subscriber(app: FastAPI):
    """
    Subscribe to Redis pub/sub channel for processing progress updates
    from Celery workers and forward them to WebSocket clients via
    ProcessingStatusService.
    
    This bridges the gap between Celery workers (separate processes that
    cannot access the in-process WebSocket ConnectionManager) and the
    FastAPI app process that owns the WebSocket connections.
    """
    import redis.asyncio as aioredis

    from .services.processing_status_integration import (
        PROGRESS_CHANNEL,
        notify_processing_completion,
        notify_processing_failure,
        notify_processing_status_update,
        set_processing_status_service,
    )

    broker_url = os.environ.get("CELERY_BROKER_URL", "redis://redis:6379/0")

    # Wait for ProcessingStatusService to be available via DI
    service = None
    for _ in range(30):
        try:
            from .api.dependencies.services import (
                get_processing_status_service as get_pss_di,
            )
            service = await get_pss_di()
            if service:
                set_processing_status_service(service)
                break
        except Exception:
            pass
        await asyncio.sleep(1)

    if not service:
        if logger:
            logger.warning("ProcessingStatusService not available, "
                           "Redis subscriber will not forward progress")
        return

    if logger:
        logger.info(f"Redis progress subscriber connecting to {broker_url}")

    try:
        redis_client = aioredis.from_url(broker_url)
        pubsub = redis_client.pubsub()
        await pubsub.subscribe(PROGRESS_CHANNEL)

        if logger:
            logger.info(f"Subscribed to Redis channel '{PROGRESS_CHANNEL}'")

        async for raw_message in pubsub.listen():
            if raw_message["type"] != "message":
                continue
            try:
                data = json.loads(raw_message["data"])
                msg_type = data.get("type")
                doc_id = data.get("document_id")

                if msg_type == "status_update":
                    await notify_processing_status_update(
                        document_id=doc_id,
                        status=data["status"],
                        progress_percentage=data["progress_percentage"],
                        current_step=data["current_step"],
                        error_message=data.get("error_message"),
                        metadata=data.get("metadata"),
                    )
                elif msg_type == "completion":
                    await notify_processing_completion(
                        document_id=doc_id,
                        title=data.get("title", "Document"),
                        page_count=data.get("page_count", 0),
                        chunk_count=data.get("chunk_count", 0),
                        concept_count=data.get("concept_count", 0),
                        processing_time_ms=data.get("processing_time_ms", 0),
                    )
                elif msg_type == "failure":
                    await notify_processing_failure(
                        document_id=doc_id,
                        error=data.get("error", "Unknown error"),
                        retry_available=data.get("retry_available", True),
                    )
                else:
                    if logger:
                        logger.warning(f"Unknown progress message type: {msg_type}")
            except Exception as e:
                if logger:
                    logger.error(f"Error processing Redis progress message: {e}")
    except asyncio.CancelledError:
        if logger:
            logger.info("Redis progress subscriber cancelled")
    except Exception as e:
        if logger:
            logger.error(f"Redis progress subscriber error: {e}")
    finally:
        try:
            await pubsub.unsubscribe(PROGRESS_CHANNEL)
            await redis_client.aclose()
        except Exception:
            pass


async def _initialize_cache_service(app: FastAPI):
    """Initialize cache service on startup."""
    try:
        from .services.cache_service import get_cache_service
        cache_service = await get_cache_service()
        app.state.cache_service_initialized = True
        if logger:
            logger.info("Cache service initialized successfully")
    except Exception as e:
        if logger:
            logger.warning(f"Failed to initialize cache service: {e}")
        app.state.cache_service_initialized = False


async def _start_alert_evaluation(app: FastAPI):
    """Start background alert evaluation task."""
    try:
        from .monitoring.alerting_service import get_alerting_service
        alerting_service = get_alerting_service()
        
        async def alert_evaluation_loop():
            """Background task for periodic alert evaluation."""
            while True:
                try:
                    await alerting_service.evaluate_alerts()
                    await asyncio.sleep(60)  # Evaluate every minute
                except Exception as e:
                    if logger:
                        logger.error(f"Error in alert evaluation: {e}")
                    await asyncio.sleep(60)  # Continue after error
        
        app.state.alert_evaluation_task = asyncio.create_task(alert_evaluation_loop())
        if logger:
            logger.info("Alert evaluation background task started")
    except Exception as e:
        if logger:
            logger.warning(f"Failed to start alert evaluation: {e}")


async def _initialize_health_monitoring():
    """Initialize health monitoring system on startup.
    
    Background health monitoring runs every 60 seconds after a 120-second
    initial delay. Health checks are designed to be non-blocking - they only
    check cached state and do not create new service instances.
    """
    try:
        from .monitoring.health_check_system import get_health_check_system
        health_system = get_health_check_system()
        
        # Start background health monitoring with 60-second interval
        # Health checks are non-blocking - they only check cached state
        health_system.start_monitoring(interval=60)
        
        if logger:
            logger.info("Health monitoring system initialized and started")
    except Exception as e:
        if logger:
            logger.warning(f"Failed to initialize health monitoring: {e}")


async def _initialize_local_memory_monitoring(app: FastAPI):
    """Initialize local memory monitoring for development environments."""
    try:
        # Only start memory monitoring in local development
        if is_local_development():
            from .monitoring.local_memory_monitor import start_local_memory_monitoring
            await start_local_memory_monitoring()
            app.state.local_memory_monitoring_active = True
            if logger:
                logger.info("Local memory monitoring started successfully")
        else:
            app.state.local_memory_monitoring_active = False
            if logger:
                logger.info("Local memory monitoring skipped (not in local development)")
    except Exception as e:
        app.state.local_memory_monitoring_active = False
        if logger:
            logger.warning(f"Failed to start local memory monitoring: {e}")


async def _initialize_local_services_logging(app: FastAPI):
    """Initialize local services structured logging for development environments."""
    try:
        # Only start local services logging in local development
        if is_local_development():
            from .logging.local_services_integration import (
                start_local_services_integration,
            )
            await start_local_services_integration()
            app.state.local_services_logging_active = True
            if logger:
                logger.info("Local services logging started successfully")
        else:
            app.state.local_services_logging_active = False
            if logger:
                logger.info("Local services logging skipped (not in local development)")
    except Exception as e:
        app.state.local_services_logging_active = False
        if logger:
            logger.warning(f"Failed to start local services logging: {e}")


async def _initialize_database_query_logging(app: FastAPI):
    """Initialize database query logging for development environments."""
    try:
        # Only start database query logging in local development
        if is_local_development():
            from .api.dependencies.services import get_database_query_logger
            query_logger = await get_database_query_logger()
            app.state.database_query_logging_active = True
            if logger:
                logger.info("Database query logging started successfully")
        else:
            app.state.database_query_logging_active = False
            if logger:
                logger.info("Database query logging skipped (not in local development)")
    except Exception as e:
        app.state.database_query_logging_active = False
        if logger:
            logger.warning(f"Failed to start database query logging: {e}")


async def _initialize_local_error_alerting(app: FastAPI):
    """Initialize local error tracking and alerting for development environments."""
    try:
        # Only start local error tracking and alerting in local development
        if is_local_development():
            from .monitoring.local_error_alerting_integration import (
                start_local_error_alerting_integration,
            )
            await start_local_error_alerting_integration()
            app.state.local_error_alerting_active = True
            if logger:
                logger.info("Local error tracking and alerting started successfully")
        else:
            app.state.local_error_alerting_active = False
            if logger:
                logger.info("Local error tracking and alerting skipped (not in local development)")
    except Exception as e:
        app.state.local_error_alerting_active = False
        if logger:
            logger.warning(f"Failed to start local error tracking and alerting: {e}")


async def _initialize_log_search_service(app: FastAPI):
    """Initialize log search service for local development environments."""
    try:
        # Only start log search service in local development
        if is_local_development():
            from .logging.log_search_service import LogSearchService
            log_search_service = LogSearchService()
            await log_search_service.initialize()
            app.state.log_search_service = log_search_service
            app.state.log_search_active = True
            if logger:
                logger.info("Log search service initialized successfully")
        else:
            app.state.log_search_active = False
            if logger:
                logger.info("Log search service skipped (not in local development)")
    except Exception as e:
        app.state.log_search_active = False
        if logger:
            logger.warning(f"Failed to initialize log search service: {e}")


async def _initialize_startup_alerts(app: FastAPI):
    """Initialize startup alerts service for health check failure monitoring."""
    try:
        if app.state.startup_phase_manager and app.state.startup_metrics_collector:
            from .api.routers.health import set_startup_alerts_service
            from .monitoring.startup_alerts import create_startup_alerts_service
            
            app.state.startup_alerts_service = await create_startup_alerts_service(
                app.state.startup_phase_manager, app.state.startup_metrics_collector
            )
            
            # Set the alerts service in the health router for integration
            set_startup_alerts_service(app.state.startup_alerts_service)
            
            if logger:
                logger.info("Startup alerts service initialized and integrated with health checks")
        else:
            if logger:
                logger.warning("Cannot initialize startup alerts service: missing dependencies")
    except Exception as e:
        if logger:
            logger.warning(f"Failed to initialize startup alerts service: {e}")


async def _initialize_performance_alerting(app: FastAPI):
    """Initialize performance alerting system for local development environments."""
    try:
        from .api.dependencies.database import get_database_factory
        from .config.local_config import LocalDatabaseConfig
        from .monitoring.local_performance_metrics import (
            LocalPerformanceMetricsCollector,
        )
        from .monitoring.performance_alerting_integration import (
            initialize_performance_alerting,
        )
        from .monitoring.performance_tracker import PerformanceTracker
        from .monitoring.query_performance_monitor import QueryPerformanceMonitor

        # Check if we're in local development mode
        config = LocalDatabaseConfig()
        if config.database_type != "local":
            if logger:
                logger.info("Skipping performance alerting initialization (not in local mode)")
            return
        
        # Get or create monitoring components
        database_factory = None
        performance_tracker = None
        metrics_collector = None
        query_monitor = None
        
        try:
            # Try to get database factory from app state
            if hasattr(app.state, 'database_factory'):
                database_factory = app.state.database_factory
            else:
                database_factory = get_database_factory()
        except Exception as e:
            if logger:
                logger.warning(f"Could not get database factory for performance alerting: {e}")
        
        try:
            # Try to get or create performance tracker
            if hasattr(app.state, 'performance_tracker'):
                performance_tracker = app.state.performance_tracker
            else:
                performance_tracker = PerformanceTracker()
                app.state.performance_tracker = performance_tracker
        except Exception as e:
            if logger:
                logger.warning(f"Could not initialize performance tracker: {e}")
        
        try:
            # Try to get or create metrics collector
            if hasattr(app.state, 'metrics_collector') and database_factory:
                metrics_collector = app.state.metrics_collector
            elif database_factory:
                metrics_collector = LocalPerformanceMetricsCollector(
                    database_factory=database_factory,
                    config=config
                )
                app.state.metrics_collector = metrics_collector
        except Exception as e:
            if logger:
                logger.warning(f"Could not initialize metrics collector: {e}")
        
        try:
            # Try to get or create query monitor
            if hasattr(app.state, 'query_monitor'):
                query_monitor = app.state.query_monitor
            else:
                query_monitor = QueryPerformanceMonitor()
                app.state.query_monitor = query_monitor
        except Exception as e:
            if logger:
                logger.warning(f"Could not initialize query monitor: {e}")
        
        # Initialize performance alerting with available components
        await initialize_performance_alerting(
            config=config,
            database_factory=database_factory,
            performance_tracker=performance_tracker,
            metrics_collector=metrics_collector,
            query_monitor=query_monitor
        )
        
        # Store reference in app state for cleanup
        app.state.performance_alerting_initialized = True
        
        if logger:
            logger.info("Performance alerting system initialized successfully")
            
    except Exception as e:
        if logger:
            logger.warning(f"Failed to initialize performance alerting system: {e}")
        # Don't raise exception - performance alerting is optional


async def _shutdown_cleanup(app: FastAPI):
    """
    Clean up all resources during application shutdown.
    
    This implements proper cleanup for DI-managed services as specified
    in the dependency-injection-architecture spec, now enhanced with
    comprehensive graceful shutdown procedures.
    
    Validates: Requirements 3.4
    """
    if logger:
        logger.info("Starting enhanced shutdown cleanup...")
    
    # Use the graceful shutdown handler for coordinated cleanup
    try:
        from .shutdown import get_shutdown_handler, perform_shutdown
        
        shutdown_handler = get_shutdown_handler()
        
        # Register any remaining cleanup tasks
        if app.state.background_init_task and not app.state.background_init_task.done():
            shutdown_handler.register_background_task(app.state.background_init_task)
        
        if app.state.alert_evaluation_task and not app.state.alert_evaluation_task.done():
            shutdown_handler.register_background_task(app.state.alert_evaluation_task)
        
        redis_sub = getattr(app.state, 'redis_progress_subscriber_task', None)
        if redis_sub and not redis_sub.done():
            shutdown_handler.register_background_task(redis_sub)
        
        # Perform graceful shutdown
        success = await perform_shutdown()
        
        if success:
            if logger:
                logger.info("✅ Enhanced graceful shutdown completed successfully")
        else:
            if logger:
                logger.warning("⚠️ Graceful shutdown completed with some errors")
        
    except ImportError:
        if logger:
            logger.warning("Graceful shutdown handler not available, falling back to basic cleanup")
        await _basic_shutdown_cleanup(app)
    except Exception as e:
        if logger:
            logger.error(f"Error in graceful shutdown: {e}")
        await _basic_shutdown_cleanup(app)


async def _basic_shutdown_cleanup(app: FastAPI):
    """
    Basic shutdown cleanup as fallback.
    
    This is the original shutdown cleanup logic, kept as a fallback
    in case the enhanced graceful shutdown handler is not available.
    """
    if logger:
        logger.info("Performing basic shutdown cleanup...")
    
    # Cancel background initialization task if still running
    if app.state.background_init_task and not app.state.background_init_task.done():
        app.state.background_init_task.cancel()
        try:
            await app.state.background_init_task
        except asyncio.CancelledError:
            pass
        if logger:
            logger.info("Background initialization task cancelled")
    
    # Cancel Redis progress subscriber if running
    redis_sub = getattr(app.state, 'redis_progress_subscriber_task', None)
    if redis_sub and not redis_sub.done():
        redis_sub.cancel()
        try:
            await redis_sub
        except asyncio.CancelledError:
            pass
        if logger:
            logger.info("Redis progress subscriber cancelled")
    
    # Shutdown progressive loader
    try:
        from .startup.progressive_loader import get_progressive_loader
        progressive_loader = get_progressive_loader()
        await progressive_loader.shutdown()
        if logger:
            logger.info("Progressive loader shutdown completed")
    except Exception as e:
        if logger:
            logger.error(f"Error during progressive loader shutdown: {e}")
    
    # Shutdown startup phase manager
    if app.state.startup_phase_manager:
        try:
            # Stop metrics tracking first
            if app.state.performance_tracker:
                try:
                    await app.state.performance_tracker.stop_tracking()
                    if logger:
                        logger.info("Performance tracker stopped")
                except Exception as e:
                    if logger:
                        logger.error(f"Error stopping performance tracker: {e}")
            
            if app.state.startup_metrics_collector:
                try:
                    await app.state.startup_metrics_collector.stop_collection()
                    if logger:
                        logger.info("Startup metrics collection stopped")
                except Exception as e:
                    if logger:
                        logger.error(f"Error stopping startup metrics collection: {e}")
            
            await app.state.startup_phase_manager.shutdown()
            if logger:
                logger.info("StartupPhaseManager shutdown completed")
        except Exception as e:
            if logger:
                logger.error(f"Error during StartupPhaseManager shutdown: {e}")
    
    # Stop health monitoring
    try:
        from .monitoring.health_check_system import get_health_check_system
        health_system = get_health_check_system()
        health_system.stop_monitoring()
        if logger:
            logger.info("Health monitoring system stopped")
    except Exception as e:
        if logger:
            logger.warning(f"Error during health monitoring shutdown: {e}")
    
    # Stop local memory monitoring
    if getattr(app.state, 'local_memory_monitoring_active', False):
        try:
            from .monitoring.local_memory_monitor import stop_local_memory_monitoring
            await stop_local_memory_monitoring()
            if logger:
                logger.info("Local memory monitoring stopped")
        except Exception as e:
            if logger:
                logger.warning(f"Error during local memory monitoring shutdown: {e}")
    
    # Stop local services logging
    if getattr(app.state, 'local_services_logging_active', False):
        try:
            from .logging.local_services_integration import (
                stop_local_services_integration,
            )
            await stop_local_services_integration()
            if logger:
                logger.info("Local services logging stopped")
        except Exception as e:
            if logger:
                logger.warning(f"Error during local services logging shutdown: {e}")
    
    # Stop local error tracking and alerting
    if getattr(app.state, 'local_error_alerting_active', False):
        try:
            from .monitoring.local_error_alerting_integration import (
                stop_local_error_alerting_integration,
            )
            await stop_local_error_alerting_integration()
            if logger:
                logger.info("Local error tracking and alerting stopped")
        except Exception as e:
            if logger:
                logger.warning(f"Error during local error tracking and alerting shutdown: {e}")
    
    # Stop performance alerting
    if getattr(app.state, 'performance_alerting_initialized', False):
        try:
            from .monitoring.performance_alerting_integration import (
                shutdown_performance_alerting,
            )
            await shutdown_performance_alerting()
            if logger:
                logger.info("Performance alerting system stopped")
        except Exception as e:
            if logger:
                logger.warning(f"Error during performance alerting shutdown: {e}")
    
    # Stop user experience logger
    try:
        from .logging.ux_logger import get_ux_logger
        ux_logger = get_ux_logger()
        if ux_logger:
            await ux_logger.stop_logging()
            if logger:
                logger.info("User experience logger stopped")
    except Exception as e:
        if logger:
            logger.warning(f"Error during user experience logger shutdown: {e}")
    
    # Stop startup alerts service
    if app.state.startup_alerts_service:
        try:
            await app.state.startup_alerts_service.stop_monitoring()
            if logger:
                logger.info("Startup alerts service stopped")
        except Exception as e:
            if logger:
                logger.warning(f"Error during startup alerts service shutdown: {e}")
    
    # Stop alert evaluation task
    if app.state.alert_evaluation_task:
        app.state.alert_evaluation_task.cancel()
        try:
            await app.state.alert_evaluation_task
        except asyncio.CancelledError:
            pass
        if logger:
            logger.info("Alert evaluation task stopped")
    
    # Disconnect cache service
    try:
        from .services.cache_service import get_cache_service
        cache_service = await get_cache_service()
        await cache_service.disconnect()
        if logger:
            logger.info("Cache service disconnected")
    except Exception as e:
        if logger:
            logger.warning(f"Error during cache service shutdown: {e}")
    
    # Clean up DI-managed services
    try:
        from .api.dependencies.services import cleanup_services
        await cleanup_services()
        if logger:
            logger.info("DI-managed services cleaned up")
    except Exception as e:
        if logger:
            logger.warning(f"Error during DI services cleanup: {e}")
    
    if logger:
        logger.info("Basic application shutdown completed")


# Simple health check response
def create_minimal_app() -> FastAPI:
    """Create a minimal FastAPI application for learning deployment."""
    
    # Use the lifespan context manager for proper startup/shutdown lifecycle
    app = FastAPI(
        title="Multimodal Librarian",
        description="Production AI-powered document management system",
        version="1.0.0",
        docs_url="/docs",
        redoc_url="/redoc",
        lifespan=lifespan,  # Use lifespan context manager instead of on_event decorators
    )
    
    app_start_time = time.time()
    
    # Initialize startup phase manager at module level
    # These need to be accessible across all functions
    # Note: These are now initialized in the lifespan context manager
    app.state.startup_phase_manager = None
    app.state.startup_metrics_collector = None
    app.state.performance_tracker = None
    
    if logger:
        logger.info("Starting minimal FastAPI application")
    
    # ============================================================================
    # CRITICAL: Add minimal health check endpoint BEFORE any middleware
    # This endpoint MUST bypass all middleware to respond immediately for ALB
    # ============================================================================
    from fastapi import Response
    
    @app.get("/health/simple", include_in_schema=False)
    async def alb_health_check():
        """
        Ultra-minimal health check for ALB that bypasses ALL middleware.
        
        CRITICAL REQUIREMENTS:
        - Must be registered BEFORE any middleware
        - Must NOT call get_minimal_server() or any initialization code
        - Must NOT access database, models, or any external services
        - Must return immediately (< 100ms)
        
        This endpoint is specifically designed for AWS ALB health checks
        which require fast, reliable responses without any dependencies.
        """
        return Response(
            content='{"status":"ok","timestamp":"' + datetime.now().isoformat() + '"}',
            media_type="application/json",
            status_code=200
        )
    
    if logger:
        logger.info("✓ Minimal ALB health check endpoint registered (bypasses all middleware)")
    
    # Add timeout middleware FIRST to prevent any request from blocking forever
    try:
        from .api.middleware.timeout_middleware import TimeoutMiddleware
        
        app.add_middleware(
            TimeoutMiddleware,
            timeout_seconds=30.0,  # 30 second timeout for most requests
            exclude_paths=["/health/simple", "/health/alb", "/ws/", "/static/", "/api/conversations/"]
        )
        
        if logger:
            logger.info("Request timeout middleware added (30s limit)")
            
    except ImportError as e:
        if logger:
            logger.warning(f"Failed to add timeout middleware: {e}")
    
    # Add logging middleware for comprehensive request/response logging
    try:
        from .api.middleware.logging_middleware import LoggingMiddleware

        # Add logging middleware (should be one of the first middlewares)
        app.add_middleware(
            LoggingMiddleware,
            exclude_paths=["/health/simple", "/static/", "/favicon.ico"]
        )
        
        if logger:
            logger.info("Comprehensive logging middleware added successfully")
            
    except ImportError as e:
        if logger:
            logger.warning(f"Failed to add logging middleware: {e}")
    
    # Add authentication middleware (optional by default for gradual rollout)
    try:
        from .api.middleware.auth_middleware import OptionalAuthenticationMiddleware
        from .config import get_settings

        # Use optional authentication middleware for gradual rollout
        # This adds user context when available but doesn't require authentication
        app.add_middleware(
            OptionalAuthenticationMiddleware,
            require_auth=False  # Start with optional auth for existing endpoints
        )
        
        if logger:
            logger.info("Optional authentication middleware added successfully")
            
    except ImportError as e:
        if logger:
            logger.warning(f"Failed to add authentication middleware: {e}")
    
    # Add user wait tracking middleware for startup UX monitoring
    try:
        from .api.middleware.user_wait_tracking_middleware import (
            UserWaitTrackingMiddleware,
        )
        
        app.add_middleware(
            UserWaitTrackingMiddleware,
            enabled=True  # Enable during startup for UX monitoring
        )
        
        if logger:
            logger.info("User wait tracking middleware added successfully")
            
    except ImportError as e:
        if logger:
            logger.warning(f"Failed to add user wait tracking middleware: {e}")
    
    # Add model availability middleware to ensure no "model not loaded" errors
    try:
        from .api.middleware.model_availability_middleware import (
            ModelAvailabilityMiddleware,
        )
        
        app.add_middleware(
            ModelAvailabilityMiddleware
        )
        
        if logger:
            logger.info("Model availability middleware added successfully - ensures no 'model not loaded' errors")
            
    except ImportError as e:
        if logger:
            logger.warning(f"Failed to add model availability middleware: {e}")
    
    # Add concurrent request handling middleware for graceful startup
    try:
        from .api.middleware.concurrent_request_handler import ConcurrentRequestHandler
        
        app.add_middleware(
            ConcurrentRequestHandler
        )
        
        if logger:
            logger.info("Concurrent request handling middleware added successfully - ensures graceful handling during startup")
            
    except ImportError as e:
        if logger:
            logger.warning(f"Failed to add concurrent request handling middleware: {e}")
    
    # Feature availability
    FEATURES = {
        "chat": True,
        "functional_chat": True,
        "conversation_context": True,
        "intelligent_responses": True,
        "static_files": True,
        "monitoring": True,
        "document_upload": True,        # Document upload functionality
        "document_management": True,    # Document management interface
        "pdf_processing": True,         # PDF processing pipeline
        "analytics": True,              # Document and usage analytics
        "document_analytics": True,     # Document processing statistics
        "usage_analytics": True,        # Usage patterns and insights
        "auth": True,
        "user_authentication": True,
        "jwt_tokens": True,
        "role_based_access": True,
        "conversations": False,
        "query": False,
        "export": False,
        "ml_training": False,
        "security": False,
        "vector_search": True,  # Available with OpenSearch
        "knowledge_graph": True,  # Available with Neptune
        "aws_native_databases": True,  # Primary feature
        "neptune_support": True,       # Graph database
        "opensearch_support": True,    # Vector search
        "legacy_databases": False,      # Neo4j/Milvus removed
        "comprehensive_logging": True,   # Structured logging with distributed tracing
        "distributed_tracing": True,     # Request tracing across services
        "performance_monitoring": True,  # Performance metrics collection
        "business_metrics": True,        # Business metrics tracking
        "error_tracking": True,          # Error pattern analysis
        "audit_logging": True            # Audit trail for security events
    }
    
    # Add inline functional chat router to avoid import issues
    import json
    from uuid import uuid4

    from fastapi import WebSocket, WebSocketDisconnect

    # Simple connection manager
    class InlineConnectionManager:
        def __init__(self):
            self.active_connections = {}
            self.conversation_history = {}
            self._gemini_model = None
            self._gemini_configured = False
            self._gemini_init_lock = asyncio.Lock()
        
        async def get_gemini_model_async(self):
            """Get or create cached Gemini model (lazy initialization, non-blocking)."""
            if self._gemini_configured:
                return self._gemini_model
            
            async with self._gemini_init_lock:
                # Double-check after acquiring lock
                if self._gemini_configured:
                    return self._gemini_model
                
                gemini_key = os.environ.get('GEMINI_API_KEY', '')
                if gemini_key and gemini_key not in ('', 'your-gemini-api-key-here'):
                    try:
                        import google.generativeai as genai

                        # Run blocking init in thread pool
                        loop = asyncio.get_event_loop()
                        def init_gemini():
                            genai.configure(api_key=gemini_key)
                            return genai.GenerativeModel('gemini-2.5-flash')
                        
                        self._gemini_model = await loop.run_in_executor(None, init_gemini)
                        self._gemini_configured = True
                        if logger:
                            logger.info("Gemini model initialized and cached")
                    except Exception as e:
                        if logger:
                            logger.warning(f"Failed to initialize Gemini: {e}")
                        self._gemini_configured = True  # Don't retry
                else:
                    self._gemini_configured = True  # No key, don't retry
                    
            return self._gemini_model
        
        async def connect(self, websocket: WebSocket, connection_id: str):
            await websocket.accept()
            self.active_connections[connection_id] = websocket
            self.conversation_history[connection_id] = []
        
        def disconnect(self, connection_id: str):
            if connection_id in self.active_connections:
                del self.active_connections[connection_id]
            if connection_id in self.conversation_history:
                del self.conversation_history[connection_id]
        
        async def send_personal_message(self, message: dict, connection_id: str):
            if connection_id in self.active_connections:
                websocket = self.active_connections[connection_id]
                try:
                    await websocket.send_text(json.dumps(message))
                except:
                    self.disconnect(connection_id)
        
        def add_to_history(self, connection_id: str, message: str, message_type: str):
            if connection_id in self.conversation_history:
                self.conversation_history[connection_id].append({
                    'content': message,
                    'type': message_type,
                    'timestamp': time.time()
                })
                # Keep only last 10 messages
                if len(self.conversation_history[connection_id]) > 10:
                    self.conversation_history[connection_id] = self.conversation_history[connection_id][-10:]
        
        def get_history(self, connection_id: str):
            return self.conversation_history.get(connection_id, [])
    
    # Initialize connection manager
    inline_manager = InlineConnectionManager()
    
    # Simple chat processor
    def process_inline_message(message: str, history: list = None) -> str:
        """Process message and return intelligent response."""
        message_lower = message.lower().strip()
        
        # Greeting
        if any(word in message_lower for word in ['hello', 'hi', 'hey', 'good morning']):
            return "Hello! I'm your Multimodal Librarian assistant. I can help you with questions, provide information, and maintain conversation context. What would you like to know?"
        
        # Questions about capabilities
        elif any(word in message_lower for word in ['what can you do', 'capabilities', 'features']):
            return "I can engage in conversations, answer questions, and provide information on various topics. I maintain conversation context and can help with research questions. This is a cost-optimized deployment running on AWS for ~$50/month."
        
        # System questions
        elif any(word in message_lower for word in ['system', 'aws', 'deployment', 'cost']):
            return "This system runs on AWS ECS with PostgreSQL and Redis, optimized for learning at ~$50/month. It demonstrates functional chat capabilities with intelligent responses and conversation context while maintaining cost efficiency."
        
        # Help requests
        elif any(word in message_lower for word in ['help', 'assist', 'support']):
            return "I'm here to help! I can answer questions, provide explanations, and assist with various topics. Try asking me about the system, AWS deployment, or any subject you're curious about."
        
        # Thanks
        elif any(word in message_lower for word in ['thank', 'thanks']):
            return "You're welcome! Is there anything else I can help you with? Feel free to ask more questions."
        
        # Goodbye
        elif any(word in message_lower for word in ['bye', 'goodbye']):
            return "Goodbye! Feel free to return anytime you need assistance. Have a great day!"
        
        # Context-aware responses
        elif history and len(history) > 1:
            return f"I understand you're asking about that. Based on our conversation, I can see we've been discussing various topics. This functional chat system maintains context and provides intelligent responses while being cost-optimized for learning."
        
        # Default response
        else:
            return f"That's an interesting point about '{message[:50]}...'. While I don't have specific information about that topic right now, I can help you explore related concepts. This learning deployment demonstrates functional chat capabilities - in a full system, I would search through knowledge bases for detailed answers."
    
    # Add chat status endpoint
    @app.get("/chat/status")
    async def get_inline_chat_status():
        return {
            "status": "active",
            "active_connections": len(inline_manager.active_connections),
            "features": {
                "websocket": True,
                "conversation_context": True,
                "intelligent_responses": True,
                "inline_processing": True
            },
            "deployment_type": "inline-functional",
            "cost_optimized": True
        }
    
    # NOTE: The main WebSocket endpoint at /ws/chat is now handled by chat.py router
    # which has full RAG integration. This inline endpoint is kept as a fallback
    # at a different path for debugging purposes.
    @app.websocket("/ws/chat-inline-fallback")
    async def websocket_inline_chat(websocket: WebSocket):
        connection_id = str(uuid4())
        await inline_manager.connect(websocket, connection_id)
        
        try:
            while True:
                # Receive message
                data = await websocket.receive_text()
                message_data = json.loads(data)
                message_type = message_data.get("type", "")
                
                if message_type == "start_conversation":
                    # Send conversation started message with expected format
                    thread_id = str(uuid4())
                    await inline_manager.send_personal_message({
                        "type": "conversation_started",
                        "thread_id": thread_id,
                        "timestamp": time.time(),
                        "features": {
                            "rag_enabled": False,
                            "document_aware_responses": False,
                            "citation_support": False,
                            "fallback_ai": True,
                            "conversation_memory": True
                        },
                        "rag_status": {"status": "unavailable", "reason": "inline_mode"},
                        "welcome_message": "🤖 Welcome to Multimodal Librarian! I can help you with questions and provide intelligent responses. Ask me anything!"
                    }, connection_id)
                    
                elif message_type == "chat_message":
                    user_message = message_data.get("message", "").strip()
                    
                    if not user_message:
                        continue
                    
                    # Send processing indicator
                    await inline_manager.send_personal_message({
                        "type": "processing",
                        "message": "Processing your message..."
                    }, connection_id)
                    
                    # Add to history
                    inline_manager.add_to_history(connection_id, user_message, 'user')
                    
                    # Try to use Gemini AI for response
                    response_text = None
                    ai_provider = "inline"
                    tokens_used = 0
                    
                    # Check for Gemini API key
                    gemini_key = os.environ.get('GEMINI_API_KEY', '')
                    
                    if gemini_key and gemini_key not in ('', 'your-gemini-api-key-here'):
                        try:
                            # Get cached Gemini model (lazy init on first use, non-blocking)
                            model = await inline_manager.get_gemini_model_async()
                            
                            if model:
                                # Build conversation context
                                history = inline_manager.get_history(connection_id)
                                conversation_parts = []
                                
                                # Add system context
                                conversation_parts.append("You are a helpful AI assistant called Multimodal Librarian. Provide clear, concise, and helpful responses. Answer questions directly and accurately.")
                                
                                # Add conversation history
                                for msg in history[-6:]:
                                    role = "User" if msg.get("type") == "user" else "Assistant"
                                    conversation_parts.append(f"{role}: {msg.get('content', '')}")
                                
                                prompt = "\n\n".join(conversation_parts)
                                
                                # Generate response asynchronously
                                response = await model.generate_content_async(prompt)
                                
                                response_text = response.text
                                ai_provider = "gemini"
                                
                                if logger:
                                    logger.info(f"Gemini response generated for {connection_id}")
                                
                        except Exception as ai_error:
                            if logger:
                                logger.warning(f"Gemini AI failed, using fallback: {ai_error}")
                            response_text = None
                    
                    # Fall back to simple processor if AI failed or not configured
                    if not response_text:
                        history = inline_manager.get_history(connection_id)
                        response_text = process_inline_message(user_message, history)
                        ai_provider = "inline_fallback"
                    
                    # Add response to history
                    inline_manager.add_to_history(connection_id, response_text, 'assistant')
                    
                    # Send response in expected format
                    await inline_manager.send_personal_message({
                        "type": "response",
                        "response": {
                            "text_content": response_text,
                            "visualizations": [],
                            "knowledge_citations": []
                        },
                        "metadata": {
                            "rag_enabled": False,
                            "fallback_mode": ai_provider == "inline_fallback",
                            "processing_time_ms": 50,
                            "confidence_score": 0.9 if ai_provider == "gemini" else 0.6,
                            "search_results_count": 0,
                            "fallback_used": ai_provider == "inline_fallback",
                            "ai_provider": ai_provider,
                            "tokens_used": tokens_used
                        },
                        "timestamp": time.time()
                    }, connection_id)
                    
                    # Send processing complete
                    await inline_manager.send_personal_message({
                        "type": "processing_complete"
                    }, connection_id)
                    
                elif message_type == "heartbeat":
                    # Respond to heartbeat/keepalive
                    await inline_manager.send_personal_message({
                        "type": "heartbeat_response",
                        "timestamp": time.time()
                    }, connection_id)
                    
                elif message_type == "session_info":
                    # Return session information
                    await inline_manager.send_personal_message({
                        "type": "session_info",
                        "data": {
                            "connection_id": connection_id,
                            "rag_available": False,
                            "ai_available": True,
                            "mode": "inline"
                        }
                    }, connection_id)
                    
                elif message_type in ("typing_start", "typing_stop"):
                    # Acknowledge typing indicators silently
                    pass
                    
                elif message_type == "clear_history":
                    # Clear conversation history
                    inline_manager.conversation_history[connection_id] = []
                    await inline_manager.send_personal_message({
                        "type": "history_cleared",
                        "timestamp": time.time()
                    }, connection_id)
                    
                elif message_type == "get_suggestions":
                    # Return conversation suggestions
                    await inline_manager.send_personal_message({
                        "type": "suggestions",
                        "suggestions": [
                            "What can you help me with?",
                            "Tell me about this system",
                            "What documents do I have?",
                            "How does this work?"
                        ]
                    }, connection_id)
                    
                elif message_type == "set_context":
                    # Acknowledge context setting
                    await inline_manager.send_personal_message({
                        "type": "context_set",
                        "context": message_data.get("context", {}),
                        "timestamp": time.time()
                    }, connection_id)
                    
                else:
                    # Log unknown message type but don't send error to avoid spamming UI
                    if logger:
                        logger.warning(f"Unknown message type from {connection_id}: {message_type}")
                
        except WebSocketDisconnect:
            inline_manager.disconnect(connection_id)
        except Exception as e:
            if logger:
                logger.error(f"WebSocket error: {e}")
            inline_manager.disconnect(connection_id)
    
    if logger:
        logger.info("Inline functional chat added successfully")
    
    # Mount static files for the unified interface
    try:
        static_path = os.path.join(os.path.dirname(__file__), "static")
        if os.path.exists(static_path):
            app.mount("/static", StaticFiles(directory=static_path), name="static")
            if logger:
                logger.info(f"Static files mounted from {static_path}")
        else:
            if logger:
                logger.warning(f"Static files directory not found: {static_path}")
    except Exception as e:
        if logger:
            logger.error(f"Failed to mount static files: {e}")
    
    # Add Authentication API router
    try:
        from .api.routers.auth import router as auth_router
        app.include_router(auth_router)
        FEATURES["auth"] = True
        FEATURES["user_authentication"] = True
        FEATURES["jwt_tokens"] = True
        FEATURES["role_based_access"] = True
        if logger:
            logger.info("Authentication API router added successfully")
    except ImportError as e:
        if logger:
            logger.warning(f"Failed to import Authentication router: {e}")
        FEATURES["auth"] = False
        FEATURES["user_authentication"] = False
        FEATURES["jwt_tokens"] = False
        FEATURES["role_based_access"] = False
    
    # Add AI-Powered Chat router (with fallback)
    try:
        from .api.routers.chat_ai import router as chat_ai_router
        app.include_router(chat_ai_router)
        FEATURES["ai_chat"] = True
        FEATURES["intelligent_responses"] = True
        if logger:
            logger.info("AI-Powered Chat router added successfully")
    except ImportError as e:
        if logger:
            logger.warning(f"Failed to import AI-Powered Chat router: {e}")
            logger.info("Falling back to simple AI chat router")
        
        # Fallback to simple AI chat router
        try:
            from .api.routers.chat_ai_simple import router as simple_chat_ai_router
            app.include_router(simple_chat_ai_router)
            FEATURES["ai_chat"] = True
            FEATURES["intelligent_responses"] = True
            FEATURES["ai_chat_mode"] = "simple"
            if logger:
                logger.info("Simple AI-Powered Chat router added successfully as fallback")
        except ImportError as e2:
            if logger:
                logger.error(f"Failed to import simple AI-Powered Chat router: {e2}")
            FEATURES["ai_chat"] = False
            FEATURES["intelligent_responses"] = False

    # Add Knowledge Graph API router if enabled
    if FEATURES.get("knowledge_graph", False):
        try:
            from src.multimodal_librarian.api.routers.knowledge_graph import (
                router as kg_router,
            )
            app.include_router(kg_router)
            if logger:
                logger.info("Knowledge Graph API router added successfully")
        except ImportError as e:
            if logger:
                logger.warning(f"Failed to import Knowledge Graph router: {e}")
            FEATURES["knowledge_graph"] = False
    
    # Add Document Management API router
    try:
        from .api.routers.documents import router as documents_router
        app.include_router(documents_router)
        FEATURES["document_upload"] = True
        FEATURES["document_management"] = True
        if logger:
            logger.info("Document Management API router added successfully")
    except ImportError as e:
        if logger:
            logger.warning(f"Failed to import Document Management router: {e}")
        FEATURES["document_upload"] = False
        FEATURES["document_management"] = False
    
    # Add Chat router with RAG integration
    try:
        from .api.routers.chat import router as chat_router
        app.include_router(chat_router, tags=["chat"])
        FEATURES["chat"] = True
        FEATURES["websocket_chat"] = True
        FEATURES["rag_integration"] = True
        if logger:
            logger.info("Chat router with RAG integration added successfully")
    except ImportError as e:
        if logger:
            logger.warning(f"Failed to import Chat router: {e}")
        FEATURES["chat"] = False
        FEATURES["websocket_chat"] = False
        FEATURES["rag_integration"] = False
    
    # Add Analytics API router
    try:
        from .api.routers.analytics import router as analytics_router
        app.include_router(analytics_router)
        FEATURES["analytics"] = True
        FEATURES["document_analytics"] = True
        FEATURES["usage_analytics"] = True
        if logger:
            logger.info("Analytics API router added successfully")
    except ImportError as e:
        if logger:
            logger.warning(f"Failed to import Analytics router: {e}")
        FEATURES["analytics"] = False
        FEATURES["document_analytics"] = False
        FEATURES["usage_analytics"] = False
    
    # Add Cache Management API router
    try:
        from .api.routers.cache_management import router as cache_router
        app.include_router(cache_router)
        FEATURES["cache_management"] = True
        FEATURES["performance_optimization"] = True
        FEATURES["redis_caching"] = True
        if logger:
            logger.info("Cache Management API router added successfully")
    except ImportError as e:
        if logger:
            logger.warning(f"Failed to import Cache Management router: {e}")
        FEATURES["cache_management"] = False
        FEATURES["performance_optimization"] = False
        FEATURES["redis_caching"] = False
    
    # Add Enrichment Management API router
    try:
        from .api.routers.enrichment import router as enrichment_router
        app.include_router(enrichment_router)
        FEATURES["enrichment_management"] = True
        FEATURES["yago_enrichment"] = True
        FEATURES["conceptnet_enrichment"] = True
        if logger:
            logger.info("Enrichment Management API router added successfully")
    except ImportError as e:
        if logger:
            logger.warning(f"Failed to import Enrichment Management router: {e}")
        FEATURES["enrichment_management"] = False
        FEATURES["yago_enrichment"] = False
        FEATURES["conceptnet_enrichment"] = False
    
    # Add Comprehensive Logging API router
    try:
        from .api.routers.logging import router as logging_router
        app.include_router(logging_router)
        FEATURES["comprehensive_logging"] = True
        FEATURES["distributed_tracing"] = True
        FEATURES["performance_monitoring"] = True
        FEATURES["business_metrics"] = True
        FEATURES["error_tracking"] = True
        if logger:
            logger.info("Comprehensive Logging API router added successfully")
    except ImportError as e:
        if logger:
            logger.warning(f"Failed to import Comprehensive Logging router: {e}")
        FEATURES["comprehensive_logging"] = False
        FEATURES["distributed_tracing"] = False
        FEATURES["performance_monitoring"] = False
        FEATURES["business_metrics"] = False
        FEATURES["error_tracking"] = False
    
    # Add AI Optimization API router
    try:
        from .api.routers.ai_optimization import router as ai_optimization_router
        app.include_router(ai_optimization_router)
        FEATURES["ai_optimization"] = True
        FEATURES["cost_monitoring"] = True
        FEATURES["request_batching"] = True
        FEATURES["prompt_optimization"] = True
        if logger:
            logger.info("AI Optimization API router added successfully")
    except ImportError as e:
        if logger:
            logger.warning(f"Failed to import AI Optimization router: {e}")
        FEATURES["ai_optimization"] = False
        FEATURES["cost_monitoring"] = False
        FEATURES["request_batching"] = False
        FEATURES["prompt_optimization"] = False
    
    # Add Health Check API router (Task 3.2.1 - Service Health Checks)
    try:
        from .api.routers.health_checks import router as health_checks_router
        app.include_router(health_checks_router)
        FEATURES["service_health_checks"] = True
        FEATURES["automatic_restart"] = True
        FEATURES["graceful_degradation"] = True
        FEATURES["health_monitoring"] = True
        if logger:
            logger.info("Health Check API router added successfully")
    except ImportError as e:
        if logger:
            logger.warning(f"Failed to import Health Check router: {e}")
        FEATURES["service_health_checks"] = False
        FEATURES["automatic_restart"] = False
        FEATURES["graceful_degradation"] = False
        FEATURES["health_monitoring"] = False

    # Add Startup-Optimized Health API router (Task 1.2 - Minimal Startup Mode)
    try:
        from .api.routers.health import router as startup_health_router
        app.include_router(startup_health_router)
        FEATURES["startup_health_checks"] = True
        FEATURES["minimal_server"] = True
        FEATURES["progressive_startup"] = True
        FEATURES["model_status_reporting"] = True
        if logger:
            logger.info("Startup-Optimized Health API router added successfully")
    except ImportError as e:
        if logger:
            logger.warning(f"Failed to import Startup Health router: {e}")
        FEATURES["startup_health_checks"] = False
        FEATURES["minimal_server"] = False
        FEATURES["progressive_startup"] = False
        FEATURES["model_status_reporting"] = False

    # Add Loading Progress API router (capabilities and loading status)
    try:
        from .api.routers.loading_progress import router as loading_progress_router
        app.include_router(loading_progress_router)
        FEATURES["loading_progress"] = True
        FEATURES["capability_advertising"] = True
        if logger:
            logger.info("Loading Progress API router added successfully")
    except ImportError as e:
        if logger:
            logger.warning(f"Failed to import Loading Progress router: {e}")
        FEATURES["loading_progress"] = False
        FEATURES["capability_advertising"] = False

    # Add Local Development Health API router (only in local environment)
    try:
        if is_local_development():
            from .api.routers.health_dashboard import router as health_dashboard_router
            from .api.routers.health_local import router as local_health_router
            from .api.routers.local_error_alerting import (
                router as local_error_alerting_router,
            )
            from .api.routers.local_performance_metrics import (
                router as local_performance_router,
            )
            from .api.routers.local_services_logging import (
                router as local_services_logging_router,
            )
            from .api.routers.log_search import router as log_search_router
            from .api.routers.log_search_ui import router as log_search_ui_router
            
            app.include_router(local_health_router)
            app.include_router(local_performance_router)
            app.include_router(health_dashboard_router)
            app.include_router(local_services_logging_router)
            app.include_router(local_error_alerting_router)
            app.include_router(log_search_router)
            app.include_router(log_search_ui_router)
            FEATURES["local_health_checks"] = True
            FEATURES["local_performance_metrics"] = True
            FEATURES["health_dashboard"] = True
            FEATURES["local_services_logging"] = True
            FEATURES["local_error_tracking"] = True
            FEATURES["local_alerting"] = True
            FEATURES["log_search"] = True
            FEATURES["log_aggregation"] = True
            FEATURES["log_analysis"] = True
            FEATURES["database_connectivity_monitoring"] = True
            FEATURES["service_dependency_health"] = True
            FEATURES["docker_container_monitoring"] = True
            FEATURES["structured_service_logging"] = True
            if logger:
                logger.info("Local Development Health API router added successfully")
                logger.info("Local Performance Metrics API router added successfully")
                logger.info("Health Dashboard router added successfully")
                logger.info("Local Services Logging API router added successfully")
                logger.info("Local Error Tracking and Alerting API router added successfully")
                logger.info("Log Search API router added successfully")
                logger.info("Log Search UI router added successfully")
        else:
            FEATURES["local_health_checks"] = False
            FEATURES["local_performance_metrics"] = False
            FEATURES["health_dashboard"] = False
            FEATURES["local_services_logging"] = False
            if logger:
                logger.debug("Local Health router skipped - not in local development environment")
    except ImportError as e:
        if logger:
            logger.warning(f"Failed to import Local Health/Performance routers: {e}")
        FEATURES["local_health_checks"] = False
        FEATURES["local_performance_metrics"] = False
        FEATURES["health_dashboard"] = False
        FEATURES["database_connectivity_monitoring"] = False
        FEATURES["service_dependency_health"] = False
        FEATURES["docker_container_monitoring"] = False

    # Add Concurrent Request Handling API router
    try:
        from .api.middleware.concurrent_integration import router as concurrent_router
        app.include_router(concurrent_router)
        FEATURES["concurrent_request_handling"] = True
        FEATURES["request_throttling"] = True
        FEATURES["graceful_degradation_concurrent"] = True
        if logger:
            logger.info("Concurrent Request Handling API router added successfully")
    except ImportError as e:
        if logger:
            logger.warning(f"Failed to import Concurrent Request Handling router: {e}")
        FEATURES["concurrent_request_handling"] = False
        FEATURES["request_throttling"] = False
        FEATURES["graceful_degradation_concurrent"] = False

    # Add Monitoring API router (Task 13.2 - Alerting and Dashboards)
    try:
        from .api.routers.monitoring import router as monitoring_router
        app.include_router(monitoring_router)
        FEATURES["alerting_system"] = True
        FEATURES["dashboard_monitoring"] = True
        FEATURES["real_time_alerts"] = True
        FEATURES["system_dashboards"] = True
        FEATURES["cost_alerts"] = True
        FEATURES["performance_dashboards"] = True
        if logger:
            logger.info("Monitoring API router added successfully")
    except ImportError as e:
        if logger:
            logger.warning(f"Failed to import Monitoring router: {e}")
        FEATURES["alerting_system"] = False
        FEATURES["dashboard_monitoring"] = False
        FEATURES["real_time_alerts"] = False
        FEATURES["system_dashboards"] = False
        FEATURES["cost_alerts"] = False
        FEATURES["performance_dashboards"] = False

    # Add Memory Optimization API router (Task 4.2.1 - Memory Optimization)
    try:
        from .api.routers.memory_optimization import (
            router as memory_optimization_router,
        )
        app.include_router(memory_optimization_router)
        FEATURES["memory_optimization"] = True
        FEATURES["memory_monitoring"] = True
        FEATURES["memory_leak_detection"] = True
        FEATURES["garbage_collection_optimization"] = True
        FEATURES["memory_profiling"] = True
        if logger:
            logger.info("Memory Optimization API router added successfully")
    except ImportError as e:
        if logger:
            logger.warning(f"Failed to import Memory Optimization router: {e}")
        FEATURES["memory_optimization"] = False
        FEATURES["memory_monitoring"] = False
        FEATURES["memory_leak_detection"] = False
        FEATURES["garbage_collection_optimization"] = False
        FEATURES["memory_profiling"] = False

    # Add Local Memory Monitoring API router (Local Development)
    try:
        from .api.routers.local_memory_monitoring import router as local_memory_router
        app.include_router(local_memory_router)
        FEATURES["local_memory_monitoring"] = True
        FEATURES["container_memory_monitoring"] = True
        FEATURES["memory_usage_tracking"] = True
        if logger:
            logger.info("Local Memory Monitoring API router added successfully")
    except ImportError as e:
        if logger:
            logger.warning(f"Failed to import Local Memory Monitoring router: {e}")
        FEATURES["local_memory_monitoring"] = False
        FEATURES["container_memory_monitoring"] = False
        FEATURES["memory_usage_tracking"] = False

    # Add Development Optimization API router (Local Development)
    try:
        from .api.routers.dev_optimization import router as dev_optimization_router
        app.include_router(dev_optimization_router)
        FEATURES["development_optimization"] = True
        FEATURES["dev_workflow_optimization"] = True
        FEATURES["dev_performance_monitoring"] = True
        FEATURES["dev_debugging_tools"] = True
        if logger:
            logger.info("Development Optimization API router added successfully")
    except ImportError as e:
        if logger:
            logger.warning(f"Failed to import Development Optimization router: {e}")
        FEATURES["development_optimization"] = False
        FEATURES["dev_workflow_optimization"] = False

    # Add Performance Debug API router (Local Development)
    try:
        from .api.routers.performance_debug import router as performance_debug_router
        app.include_router(performance_debug_router)
        FEATURES["performance_debugging"] = True
        FEATURES["performance_profiling"] = True
        FEATURES["resource_monitoring"] = True
        if logger:
            logger.info("Performance Debug API router added successfully")
    except ImportError as e:
        if logger:
            logger.warning(f"Failed to import Performance Debug router: {e}")
        FEATURES["performance_debugging"] = False
        FEATURES["performance_profiling"] = False
        FEATURES["dev_performance_monitoring"] = False
        FEATURES["dev_debugging_tools"] = False

    # Add Resource Usage Dashboard API router (Local Development)
    try:
        from .api.routers.resource_usage_dashboard import (
            router as resource_dashboard_router,
        )
        app.include_router(resource_dashboard_router)
        FEATURES["resource_usage_dashboard"] = True
        FEATURES["resource_monitoring"] = True
        FEATURES["resource_optimization"] = True
        FEATURES["container_resource_monitoring"] = True
        FEATURES["resource_efficiency_analysis"] = True
        if logger:
            logger.info("Resource Usage Dashboard API router added successfully")
    except ImportError as e:
        if logger:
            logger.warning(f"Failed to import Resource Usage Dashboard router: {e}")
        FEATURES["resource_usage_dashboard"] = False
        FEATURES["resource_optimization"] = False
        FEATURES["container_resource_monitoring"] = False
        FEATURES["resource_efficiency_analysis"] = False
    
    # Add Conversation Knowledge API router
    try:
        from .api.routers.conversation_knowledge import (
            router as conversation_knowledge_router,
        )
        app.include_router(conversation_knowledge_router)
        FEATURES["conversation_knowledge"] = True
        if logger:
            logger.info("Conversation Knowledge API router added successfully")
    except ImportError as e:
        if logger:
            logger.warning(f"Failed to import Conversation Knowledge router: {e}")
        FEATURES["conversation_knowledge"] = False
    
    # Add KG Explorer API router (neighborhood + search endpoints)
    try:
        from .api.routers.kg_explorer import router as kg_explorer_router
        app.include_router(kg_explorer_router)
        FEATURES["kg_explorer"] = True
        if logger:
            logger.info("KG Explorer API router added successfully")
    except ImportError as e:
        if logger:
            logger.warning(f"Failed to import KG Explorer router: {e}")
        FEATURES["kg_explorer"] = False
    
    @app.get("/")
    async def root():
        """Root endpoint."""
        return {
            "message": "Multimodal Librarian API - Production",
            "version": "1.0.0",
            "status": "running",
            "docs_url": "/docs",
            "config_available": CONFIG_AVAILABLE,
            "features": FEATURES,
            "deployment_type": "production"
        }
    
    @app.get("/features")
    async def get_features():
        """Get current feature availability."""
        return {
            "features": FEATURES,
            "deployment_type": "inline-functional",
            "cost_optimized": True,
            "fallbacks_enabled": True,
            "description": "Inline functional chat deployment with intelligent responses and conversation context",
            "chat_capabilities": {
                "intelligent_responses": True,
                "conversation_context": True,
                "websocket_communication": True,
                "inline_processing": True,
                "cost_optimized": True
            }
        }
    
    @app.get("/chat", response_class=HTMLResponse)
    async def serve_chat_interface():
        """Serve the full-featured chat interface from static files."""
        import os

        # Try multiple paths to find the static index.html
        possible_paths = [
            "src/multimodal_librarian/static/index.html",
            os.path.join(os.path.dirname(__file__), "static", "index.html"),
            "/app/src/multimodal_librarian/static/index.html",  # Docker path
        ]
        
        for path in possible_paths:
            try:
                with open(path, "r") as f:
                    if logger:
                        logger.info(f"Serving chat interface from: {path}")
                    return HTMLResponse(content=f.read())
            except FileNotFoundError:
                continue
        
        # Fallback error message if file not found
        if logger:
            logger.error("Could not find static/index.html for chat interface")
        return HTMLResponse(
            content="""
            <!DOCTYPE html>
            <html>
            <head>
                <title>Multimodal Librarian - Chat Interface</title>
                <style>
                    body { font-family: Arial, sans-serif; padding: 40px; text-align: center; }
                    .error { color: #d32f2f; margin: 20px 0; }
                    .btn { display: inline-block; padding: 10px 20px; background: #1976d2; color: white; text-decoration: none; border-radius: 4px; margin: 10px; }
                </style>
            </head>
            <body>
                <h1>Chat Interface Not Found</h1>
                <div class="error">The chat interface file could not be located.</div>
                <p>Please ensure the static files are properly deployed.</p>
                <a href="/docs" class="btn">API Documentation</a>
                <a href="/" class="btn">Back to Home</a>
            </body>
            </html>
            """,
            status_code=503
        )
    
    @app.get("/app", response_class=HTMLResponse)
    async def serve_unified_interface():
        """Serve the unified chat and document management interface."""
        try:
            with open("src/multimodal_librarian/templates/unified_interface.html", "r") as f:
                return HTMLResponse(content=f.read())
        except FileNotFoundError:
            return HTMLResponse(content="""
            <!DOCTYPE html>
            <html>
            <head>
                <title>Multimodal Librarian - Unified Interface</title>
                <meta name="viewport" content="width=device-width, initial-scale=1.0">
                <style>
                    body { font-family: Arial, sans-serif; padding: 20px; text-align: center; }
                    .error { color: #d32f2f; margin: 20px 0; }
                    .btn { display: inline-block; padding: 10px 20px; background: #1976d2; color: white; text-decoration: none; border-radius: 4px; margin: 10px; }
                </style>
            </head>
            <body>
                <h1>Unified Interface</h1>
                <div class="error">Unified interface is being set up. Please check back shortly.</div>
                <p>The unified chat and document management interface will be available here.</p>
                <a href="/chat" class="btn">Chat Interface</a>
                <a href="/documents" class="btn">Document Management</a>
                <a href="/" class="btn">Back to Home</a>
            </body>
            </html>
            """, status_code=503)

    @app.get("/documents", response_class=HTMLResponse)
    async def serve_document_interface():
        """Serve the document management interface."""
        try:
            from .templates.documents import get_documents_html
            return HTMLResponse(content=get_documents_html())
        except ImportError:
            # Fallback to serving the template file directly
            try:
                with open("src/multimodal_librarian/templates/documents.html", "r") as f:
                    return HTMLResponse(content=f.read())
            except FileNotFoundError:
                return HTMLResponse(content="""
                <!DOCTYPE html>
                <html>
                <head>
                    <title>Document Management - Multimodal Librarian</title>
                    <meta name="viewport" content="width=device-width, initial-scale=1.0">
                    <style>
                        body { font-family: Arial, sans-serif; padding: 20px; text-align: center; }
                        .error { color: #d32f2f; margin: 20px 0; }
                        .btn { display: inline-block; padding: 10px 20px; background: #1976d2; color: white; text-decoration: none; border-radius: 4px; margin: 10px; }
                    </style>
                </head>
                <body>
                    <h1>Document Management</h1>
                    <div class="error">Document management interface is being set up. Please check back shortly.</div>
                    <p>The document upload functionality is available via API endpoints:</p>
                    <ul style="text-align: left; max-width: 600px; margin: 0 auto;">
                        <li><strong>POST /api/documents/upload</strong> - Upload PDF documents</li>
                        <li><strong>GET /api/documents/</strong> - List uploaded documents</li>
                        <li><strong>GET /api/documents/{id}</strong> - Get document details</li>
                        <li><strong>DELETE /api/documents/{id}</strong> - Delete document</li>
                    </ul>
                    <a href="/docs" class="btn">View API Documentation</a>
                    <a href="/" class="btn">Back to Home</a>
                </body>
                </html>
                """, status_code=503)
    
    @app.get("/analytics", response_class=HTMLResponse)
    async def serve_analytics_dashboard():
        """Serve the analytics dashboard interface."""
        try:
            with open("src/multimodal_librarian/templates/analytics_dashboard.html", "r") as f:
                return HTMLResponse(content=f.read())
        except FileNotFoundError:
            return HTMLResponse(content="""
            <!DOCTYPE html>
            <html>
            <head>
                <title>Analytics Dashboard - Multimodal Librarian</title>
                <meta name="viewport" content="width=device-width, initial-scale=1.0">
                <style>
                    body { font-family: Arial, sans-serif; padding: 20px; text-align: center; }
                    .error { color: #d32f2f; margin: 20px 0; }
                    .btn { display: inline-block; padding: 10px 20px; background: #1976d2; color: white; text-decoration: none; border-radius: 4px; margin: 10px; }
                </style>
            </head>
            <body>
                <h1>Analytics Dashboard</h1>
                <div class="error">Analytics dashboard is being set up. Please check back shortly.</div>
                <p>The analytics dashboard will provide insights about document processing and usage patterns.</p>
                <a href="/api/analytics/dashboard/summary" class="btn">View Analytics API</a>
                <a href="/docs" class="btn">API Documentation</a>
                <a href="/" class="btn">Back to Home</a>
            </body>
            </html>
            """, status_code=503)
    
    @app.get("/monitoring", response_class=HTMLResponse)
    async def serve_monitoring_dashboard():
        """Serve the monitoring dashboard interface."""
        return HTMLResponse(content="""
        <!DOCTYPE html>
        <html lang="en">
        <head>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <title>Monitoring Dashboard - Multimodal Librarian</title>
            <style>
                body { font-family: Arial, sans-serif; margin: 40px; background: #f5f5f5; }
                .container { max-width: 800px; margin: 0 auto; background: white; padding: 30px; border-radius: 10px; box-shadow: 0 2px 10px rgba(0,0,0,0.1); }
                h1 { color: #2c3e50; text-align: center; margin-bottom: 30px; }
                .dashboard-links { display: grid; grid-template-columns: repeat(auto-fit, minmax(250px, 1fr)); gap: 20px; margin-top: 30px; }
                .dashboard-link { display: block; padding: 20px; background: #3498db; color: white; text-decoration: none; border-radius: 8px; text-align: center; transition: background 0.3s; }
                .dashboard-link:hover { background: #2980b9; }
                .dashboard-link h3 { margin: 0 0 10px 0; }
                .dashboard-link p { margin: 0; opacity: 0.9; }
                .status { text-align: center; margin: 20px 0; padding: 15px; background: #e8f5e8; border-radius: 5px; color: #27ae60; }
            </style>
        </head>
        <body>
            <div class="container">
                <h1>🔍 Monitoring Dashboard</h1>
                <div class="status">
                    <strong>System Status:</strong> Monitoring services are available
                </div>
                <div class="dashboard-links">
                    <a href="/resource-dashboard" class="dashboard-link">
                        <h3>📊 Resource Usage Dashboard</h3>
                        <p>Real-time system and container resource monitoring with optimization recommendations</p>
                    </a>
                    <a href="/api/v1/resource-dashboard/status" class="dashboard-link">
                        <h3>🔧 Dashboard API Status</h3>
                        <p>Check resource dashboard service status and configuration</p>
                    </a>
                    <a href="/api/v1/memory/status" class="dashboard-link">
                        <h3>💾 Memory Monitoring</h3>
                        <p>Local memory usage monitoring and analysis</p>
                    </a>
                    <a href="/health/simple" class="dashboard-link">
                        <h3>❤️ Health Check</h3>
                        <p>Basic system health status</p>
                    </a>
                </div>
            </div>
        </body>
        </html>
        """)

    @app.get("/resource-dashboard", response_class=HTMLResponse)
    async def serve_resource_dashboard():
        """Serve the resource usage dashboard interface."""
        try:
            with open("src/multimodal_librarian/templates/resource_dashboard.html", "r") as f:
                return HTMLResponse(content=f.read())
        except FileNotFoundError:
            return HTMLResponse(content="""
            <!DOCTYPE html>
            <html lang="en">
            <head>
                <meta charset="UTF-8">
                <meta name="viewport" content="width=device-width, initial-scale=1.0">
                <title>Resource Dashboard - Service Unavailable</title>
                <style>
                    body { font-family: Arial, sans-serif; margin: 40px; background: #f5f5f5; text-align: center; }
                    .container { max-width: 600px; margin: 0 auto; background: white; padding: 30px; border-radius: 10px; box-shadow: 0 2px 10px rgba(0,0,0,0.1); }
                    h1 { color: #e74c3c; }
                    .error { background: #ffeaea; padding: 20px; border-radius: 5px; margin: 20px 0; }
                    .back-link { display: inline-block; margin-top: 20px; padding: 10px 20px; background: #3498db; color: white; text-decoration: none; border-radius: 5px; }
                </style>
            </head>
            <body>
                <div class="container">
                    <h1>⚠️ Resource Dashboard Unavailable</h1>
                    <div class="error">
                        <p>The resource usage dashboard template is not available.</p>
                        <p>This may be because the local development environment is not fully set up.</p>
                    </div>
                    <p>You can still access the dashboard API endpoints:</p>
                    <ul>
                        <li><a href="/api/v1/resource-dashboard/status">Dashboard Status</a></li>
                        <li><a href="/api/v1/resource-dashboard/dashboards">Available Dashboards</a></li>
                        <li><a href="/api/v1/resource-dashboard/metrics/system">System Metrics</a></li>
                    </ul>
                    <a href="/monitoring" class="back-link">← Back to Monitoring</a>
                </div>
            </body>
            </html>
            """, status_code=503)
    
    # Startup Phase Status Endpoints
    @app.get("/startup/status")
    async def get_startup_status():
        """Get current startup phase status."""
        if not app.state.startup_phase_manager:
            return {
                "error": "StartupPhaseManager not available",
                "phase": "unknown",
                "status": "unavailable"
            }
        
        try:
            status = app.state.startup_phase_manager.get_current_status()
            return {
                "current_phase": status.current_phase.value,
                "phase_start_time": status.phase_start_time.isoformat(),
                "total_startup_time": status.total_startup_time,
                "health_check_ready": status.health_check_ready,
                "user_requests_ready": status.user_requests_ready,
                "capabilities": status.capabilities,
                "estimated_completion_times": status.estimated_completion_times,
                "model_count": len(status.model_statuses),
                "loaded_models": [
                    name for name, model_status in status.model_statuses.items()
                    if model_status.status == "loaded"
                ]
            }
        except Exception as e:
            return {
                "error": f"Failed to get startup status: {str(e)}",
                "phase": "error",
                "status": "error"
            }
    
    @app.get("/startup/progress")
    async def get_startup_progress():
        """Get detailed startup progress information."""
        if not app.state.startup_phase_manager:
            return {
                "error": "StartupPhaseManager not available",
                "progress": "unavailable"
            }
        
        try:
            return app.state.startup_phase_manager.get_phase_progress()
        except Exception as e:
            return {
                "error": f"Failed to get startup progress: {str(e)}",
                "progress": "error"
            }
    
    @app.get("/startup/capabilities")
    async def get_available_capabilities():
        """Get currently available capabilities."""
        if not app.state.startup_phase_manager:
            return {
                "error": "StartupPhaseManager not available",
                "capabilities": {}
            }
        
        try:
            capabilities = app.state.startup_phase_manager.get_available_capabilities()
            return {
                "capabilities": capabilities,
                "phase": app.state.startup_phase_manager.current_phase.value,
                "ready_for_requests": app.state.startup_phase_manager.status.user_requests_ready
            }
        except Exception as e:
            return {
                "error": f"Failed to get capabilities: {str(e)}",
                "capabilities": {}
            }
    
    @app.get("/health")
    async def health_check():
        """Comprehensive health check endpoint."""
        uptime = time.time() - app_start_time
        
        # Get startup phase information
        startup_info = {"status": "unavailable", "phase": "unknown"}
        if app.state.startup_phase_manager:
            try:
                startup_status = app.state.startup_phase_manager.get_current_status()
                startup_info = {
                    "status": "available",
                    "phase": startup_status.current_phase.value,
                    "health_check_ready": startup_status.health_check_ready,
                    "user_requests_ready": startup_status.user_requests_ready,
                    "total_startup_time": startup_status.total_startup_time,
                    "capabilities_count": len(startup_status.capabilities),
                    "loaded_models_count": len([
                        m for m in startup_status.model_statuses.values()
                        if m.status == "loaded"
                    ])
                }
            except Exception as e:
                startup_info = {
                    "status": "error",
                    "error": str(e),
                    "phase": "unknown"
                }
        
        # Check database health using the AWS-Native factory
        database_status = {"status": "disabled", "message": "Databases not enabled"}
        
        try:
            from .clients.database_factory import get_database_factory
            factory = get_database_factory()
            database_health = factory.health_check()
            database_status = database_health
        except Exception as e:
            database_status = {
                "overall_status": "error",
                "backend_type": "aws_native", 
                "services": {},
                "error": f"AWS-Native database factory failed: {str(e)}"
            }
        
        # Determine overall status based on startup phase and database health
        overall_status = "healthy"
        
        # If startup phase manager indicates we're not ready for health checks, report as starting
        if startup_info.get("health_check_ready") is False:
            overall_status = "starting"
        elif database_status.get("overall_status") in ["error", "unhealthy"]:
            overall_status = "degraded"
        elif database_status.get("overall_status") == "degraded":
            overall_status = "degraded"
        
        return {
            "overall_status": overall_status,
            "startup": startup_info,
            "services": {
                "api": {
                    "status": "healthy",
                    "service": "api",
                    "response_time_ms": 1.0,
                    "components": {
                        "uptime_seconds": str(uptime)
                    }
                },
                "databases": database_status
            },
            "uptime_seconds": uptime,
            "active_connections": 0,
            "active_threads": 0,
            "features": FEATURES,
            "deployment_type": "aws-native"
        }
    
    @app.get("/health/simple")
    async def simple_health_check():
        """Simple health check for load balancers."""
        return {"status": "ok", "timestamp": time.time()}
    
    @app.get("/health/minimal")
    async def minimal_health_check():
        """Minimal health check for ECS - basic server readiness."""
        if app.state.startup_phase_manager:
            try:
                startup_status = app.state.startup_phase_manager.get_current_status()
                if startup_status.health_check_ready:
                    return {
                        "status": "healthy",
                        "phase": startup_status.current_phase.value,
                        "ready": True,
                        "timestamp": time.time()
                    }
                else:
                    return {
                        "status": "starting",
                        "phase": startup_status.current_phase.value,
                        "ready": False,
                        "timestamp": time.time()
                    }
            except Exception as e:
                return {
                    "status": "error",
                    "error": str(e),
                    "ready": False,
                    "timestamp": time.time()
                }
        else:
            # Fallback when startup phase manager is not available
            uptime = time.time() - app_start_time
            return {
                "status": "healthy" if uptime > 30 else "starting",
                "phase": "unknown",
                "ready": uptime > 30,
                "uptime_seconds": uptime,
                "timestamp": time.time()
            }
    
    @app.get("/health/ready")
    async def readiness_health_check():
        """
        Readiness health check - essential models loaded.
        
        Uses ModelStatusService as the single source of truth for model availability.
        Essential models are considered ready when at least one of the core models
        (embedding or nlp) is loaded and the model server is connected.
        
        Validates: Requirements 7.1, 7.3
        """
        from .services.model_status_service import ModelServerStatus

        # Try to use ModelStatusService first (single source of truth)
        model_status_service = getattr(app.state, 'model_status_service', None)
        
        if model_status_service is not None:
            try:
                # Get status from ModelStatusService
                status = await model_status_service.get_status()
                
                # Check if model server is connected
                server_connected = status.server_status == ModelServerStatus.CONNECTED
                
                # Essential models: at least nlp model loaded for basic_chat capability
                # This allows the system to handle basic requests
                essential_models = ["nlp"]
                essential_loaded = all(
                    model_name in status.models and status.models[model_name].status == "loaded"
                    for model_name in essential_models
                )
                
                # Also check if basic_chat capability is available
                basic_chat_available = "basic_chat" in status.capabilities
                
                # System is ready if server is connected and essential models are loaded
                essential_models_ready = server_connected and (essential_loaded or basic_chat_available)
                
                # Get available capabilities
                available_capabilities = list(status.capabilities)
                
                # Get model statuses for response
                model_statuses = {
                    name: model.status
                    for name, model in status.models.items()
                }
                
                return {
                    "status": "ready" if essential_models_ready else "not_ready",
                    "server_connected": server_connected,
                    "server_ready": status.server_ready,
                    "essential_models_ready": essential_models_ready,
                    "model_statuses": model_statuses,
                    "capabilities": available_capabilities,
                    "timestamp": time.time()
                }
            except Exception as e:
                if logger:
                    logger.warning(f"ModelStatusService error in /health/ready: {e}")
                # Fall through to startup_phase_manager fallback
        
        # Fallback to startup_phase_manager if ModelStatusService unavailable
        if app.state.startup_phase_manager:
            try:
                startup_status = app.state.startup_phase_manager.get_current_status()
                essential_models_ready = startup_status.current_phase.value in ["essential", "full"]
                
                return {
                    "status": "ready" if essential_models_ready else "not_ready",
                    "phase": startup_status.current_phase.value,
                    "essential_models_ready": essential_models_ready,
                    "user_requests_ready": startup_status.user_requests_ready,
                    "capabilities": startup_status.capabilities,
                    "timestamp": time.time(),
                    "source": "startup_phase_manager"
                }
            except Exception as e:
                return {
                    "status": "error",
                    "error": str(e),
                    "ready": False,
                    "timestamp": time.time()
                }
        
        # Final fallback when neither service is available
        uptime = time.time() - app_start_time
        return {
            "status": "ready" if uptime > 120 else "not_ready",
            "phase": "unknown",
            "essential_models_ready": uptime > 120,
            "user_requests_ready": uptime > 30,
            "uptime_seconds": uptime,
            "timestamp": time.time(),
            "source": "uptime_fallback"
        }
    
    @app.get("/health/full")
    async def full_health_check():
        """
        Full health check - all models loaded.
        
        Uses ModelStatusService as the single source of truth for model availability.
        All models are considered ready when both embedding and nlp models are loaded
        and the model server is connected.
        
        Validates: Requirements 7.2, 7.3, 7.4
        """
        from .services.model_status_service import ModelServerStatus

        # Try to use ModelStatusService first (single source of truth)
        model_status_service = getattr(app.state, 'model_status_service', None)
        
        if model_status_service is not None:
            try:
                # Get status from ModelStatusService
                status = await model_status_service.get_status()
                
                # Check if model server is connected
                server_connected = status.server_status == ModelServerStatus.CONNECTED
                
                # All models: both embedding and nlp must be loaded
                all_models = ["embedding", "nlp"]
                all_loaded = all(
                    model_name in status.models and status.models[model_name].status == "loaded"
                    for model_name in all_models
                )
                
                # System is fully ready if server is connected and all models are loaded
                all_models_ready = server_connected and all_loaded
                
                # If server is disconnected, report not ready (Requirement 7.4)
                if not server_connected:
                    return {
                        "status": "not_ready",
                        "server_connected": False,
                        "server_ready": False,
                        "all_models_ready": False,
                        "error_message": status.error_message,
                        "capabilities": [],
                        "model_statuses": {},
                        "timestamp": time.time()
                    }
                
                # Get available capabilities
                available_capabilities = list(status.capabilities)
                
                # Get detailed model statuses for response
                model_statuses = {
                    name: {
                        "status": model.status,
                        "model_type": model.model_type,
                        "load_time_seconds": model.load_time_seconds,
                        "memory_mb": model.memory_mb,
                        "device": model.device
                    }
                    for name, model in status.models.items()
                }
                
                return {
                    "status": "ready" if all_models_ready else "not_ready",
                    "server_connected": server_connected,
                    "server_ready": status.server_ready,
                    "all_models_ready": all_models_ready,
                    "capabilities": available_capabilities,
                    "model_statuses": model_statuses,
                    "timestamp": time.time()
                }
            except Exception as e:
                if logger:
                    logger.warning(f"ModelStatusService error in /health/full: {e}")
                # Fall through to startup_phase_manager fallback
        
        # Fallback to startup_phase_manager if ModelStatusService unavailable
        if app.state.startup_phase_manager:
            try:
                startup_status = app.state.startup_phase_manager.get_current_status()
                all_models_ready = startup_status.current_phase.value == "full"
                
                return {
                    "status": "ready" if all_models_ready else "not_ready",
                    "phase": startup_status.current_phase.value,
                    "all_models_ready": all_models_ready,
                    "capabilities": startup_status.capabilities,
                    "model_statuses": {
                        name: {
                            "status": model.status,
                            "priority": model.priority,
                            "duration": model.duration_seconds
                        }
                        for name, model in startup_status.model_statuses.items()
                    },
                    "timestamp": time.time(),
                    "source": "startup_phase_manager"
                }
            except Exception as e:
                return {
                    "status": "error",
                    "error": str(e),
                    "ready": False,
                    "timestamp": time.time()
                }
        
        # Final fallback when neither service is available
        uptime = time.time() - app_start_time
        return {
            "status": "ready" if uptime > 300 else "not_ready",
            "phase": "unknown",
            "all_models_ready": uptime > 300,
            "uptime_seconds": uptime,
            "timestamp": time.time(),
            "source": "uptime_fallback"
        }
    
    @app.get("/config/aws-native")
    async def get_aws_native_config():
        """Get AWS-Native database configuration status."""
        try:
            from .config.aws_native_config import get_aws_native_config
            config = get_aws_native_config()
            validation = config.validate_configuration()
            env_info = config.get_environment_info()
            
            return {
                "configuration": validation,
                "environment": env_info,
                "timestamp": time.time()
            }
        except Exception as e:
            return {
                "error": f"Failed to get AWS-Native configuration: {str(e)}",
                "timestamp": time.time()
            }
    
    @app.get("/test/database")
    async def test_database_connection():
        """Test database connectivity."""
        try:
            # Get database credentials from AWS Secrets Manager
            secrets_client = boto3.client('secretsmanager', region_name='us-east-1')
            
            # Get database secret
            db_secret_response = secrets_client.get_secret_value(
                SecretId='multimodal-librarian/full-ml/database'
            )
            db_credentials = json.loads(db_secret_response['SecretString'])
            
            # Test PostgreSQL connection
            conn = psycopg2.connect(
                host=db_credentials['host'],
                port=db_credentials['port'],
                database=db_credentials['dbname'],
                user=db_credentials['username'],
                password=db_credentials['password'],
                connect_timeout=10
            )
            
            # Test basic query
            cursor = conn.cursor()
            cursor.execute("SELECT version();")
            db_version = cursor.fetchone()[0]
            cursor.close()
            conn.close()
            
            return {
                "status": "success",
                "database": "postgresql",
                "host": db_credentials['host'],
                "database_name": db_credentials['dbname'],
                "version": db_version,
                "connection_test": "passed"
            }
            
        except Exception as e:
            return {
                "status": "error",
                "database": "postgresql", 
                "error": str(e),
                "connection_test": "failed"
            }
    
    @app.get("/test/redis")
    async def test_redis_connection():
        """Test Redis connectivity."""
        try:
            # Get Redis credentials from AWS Secrets Manager
            secrets_client = boto3.client('secretsmanager', region_name='us-east-1')
            
            # Get Redis secret
            redis_secret_response = secrets_client.get_secret_value(
                SecretId='multimodal-librarian/full-ml/redis'
            )
            redis_credentials = json.loads(redis_secret_response['SecretString'])
            
            return {
                "status": "success",
                "database": "redis",
                "host": redis_credentials['host'],
                "port": redis_credentials['port'],
                "connection_test": "credentials_available"
            }
            
        except Exception as e:
            return {
                "status": "error",
                "database": "redis",
                "error": str(e),
                "connection_test": "failed"
            }
    
    @app.get("/config/validation")
    async def validate_configuration():
        """Validate current configuration and environment setup."""
        if not CONFIG_AVAILABLE:
            return {
                "status": "error",
                "message": "Configuration system not available",
                "valid": False,
                "timestamp": time.time()
            }
        
        try:
            from .config import (
                is_aws_production,
                is_local_development,
                validate_environment_configuration,
            )

            # Get comprehensive validation results
            validation = validate_environment_configuration()
            
            # Add runtime information
            validation.update({
                "runtime_info": {
                    "config_available": CONFIG_AVAILABLE,
                    "is_local_development": is_local_development(),
                    "is_aws_production": is_aws_production(),
                    "debug_mode": settings.debug,
                    "log_level": settings.log_level,
                    "api_docs_enabled": settings.enable_api_docs,
                    "hot_reload_enabled": getattr(settings, 'enable_hot_reload', False),
                },
                "database_config": {
                    "backend": settings.get_database_backend(),
                    "postgres_host": settings.postgres_host,
                    "postgres_port": settings.postgres_port,
                    "postgres_db": settings.postgres_db,
                    "neo4j_host": getattr(settings, 'neo4j_host', 'not_configured'),
                    "milvus_host": getattr(settings, 'milvus_host', 'not_configured'),
                    "redis_host": settings.redis_host,
                },
                "api_keys_status": {
                    "gemini_configured": bool(getattr(settings, 'gemini_api_key', None) or getattr(settings, 'google_api_key', None)),
                },
                "file_storage": {
                    "upload_dir": settings.upload_dir,
                    "media_dir": settings.media_dir,
                    "export_dir": settings.export_dir,
                    "max_file_size_mb": settings.max_file_size // (1024 * 1024),
                },
                "timestamp": time.time()
            })
            
            return validation
            
        except Exception as e:
            return {
                "status": "error",
                "message": f"Configuration validation error: {str(e)}",
                "valid": False,
                "timestamp": time.time()
            }

    @app.get("/config/environment/switch/{env_type}")
    async def switch_environment(env_type: str, force: bool = False):
        """Switch to a different environment."""
        try:
            from .config.environment_switcher import (
                EnvironmentType,
                get_environment_switcher,
            )

            # Validate environment type
            try:
                target_env = EnvironmentType(env_type.lower())
            except ValueError:
                return {
                    "success": False,
                    "message": f"Invalid environment type: {env_type}",
                    "valid_types": [e.value for e in EnvironmentType],
                    "timestamp": time.time()
                }
            
            switcher = get_environment_switcher()
            result = switcher.switch_environment(target_env, force=force)
            result["timestamp"] = time.time()
            
            return result
            
        except Exception as e:
            return {
                "success": False,
                "message": f"Environment switch error: {str(e)}",
                "timestamp": time.time()
            }

    @app.get("/config/environment/list")
    async def list_environments():
        """List all available environments."""
        try:
            from .config.environment_switcher import get_environment_switcher
            
            switcher = get_environment_switcher()
            result = switcher.list_environments()
            result["timestamp"] = time.time()
            
            return result
            
        except Exception as e:
            return {
                "status": "error",
                "message": f"Environment list error: {str(e)}",
                "timestamp": time.time()
            }

    @app.get("/config/environment/validate/{env_type}")
    async def validate_environment_endpoint(env_type: str):
        """Validate if an environment can be switched to."""
        try:
            from .config.environment_switcher import (
                EnvironmentType,
                get_environment_switcher,
            )

            # Validate environment type
            try:
                target_env = EnvironmentType(env_type.lower())
            except ValueError:
                return {
                    "valid": False,
                    "message": f"Invalid environment type: {env_type}",
                    "valid_types": [e.value for e in EnvironmentType],
                    "timestamp": time.time()
                }
            
            switcher = get_environment_switcher()
            result = switcher.validate_environment(target_env)
            result["timestamp"] = time.time()
            
            return result
            
        except Exception as e:
            return {
                "valid": False,
                "message": f"Environment validation error: {str(e)}",
                "timestamp": time.time()
            }

    @app.post("/config/environment/create-file/{env_type}")
    async def create_environment_file(env_type: str, output_path: str = None):
        """Create an environment file template for the specified environment."""
        try:
            from .config.environment_switcher import (
                EnvironmentType,
                get_environment_switcher,
            )

            # Validate environment type
            try:
                target_env = EnvironmentType(env_type.lower())
            except ValueError:
                return {
                    "success": False,
                    "message": f"Invalid environment type: {env_type}",
                    "valid_types": [e.value for e in EnvironmentType],
                    "timestamp": time.time()
                }
            
            switcher = get_environment_switcher()
            result = switcher.create_environment_file(target_env, output_path)
            result["timestamp"] = time.time()
            
            return result
            
        except Exception as e:
            return {
                "success": False,
                "message": f"Environment file creation error: {str(e)}",
                "timestamp": time.time()
            }

    @app.get("/config/environment")
    async def get_environment_info():
        """Get detailed environment information."""
        if not CONFIG_AVAILABLE:
            return {
                "status": "error",
                "message": "Configuration system not available",
                "timestamp": time.time()
            }
        
        try:
            env_info = settings.get_environment_info()
            
            # Add system environment variables
            env_info.update({
                "system_environment": {
                    "ML_ENVIRONMENT": os.getenv("ML_ENVIRONMENT", "not_set"),
                    "DATABASE_TYPE": os.getenv("DATABASE_TYPE", "not_set"),
                    "DEBUG": os.getenv("DEBUG", "not_set"),
                    "LOG_LEVEL": os.getenv("LOG_LEVEL", "not_set"),
                    "PYTHONPATH": os.getenv("PYTHONPATH", "not_set"),
                    "AWS_DEFAULT_REGION": os.getenv("AWS_DEFAULT_REGION", "not_set"),
                },
                "configuration_files": {
                    "env_local_exists": os.path.exists(".env.local"),
                    "env_exists": os.path.exists(".env"),
                    "config_source": ".env.local" if os.path.exists(".env.local") else ".env" if os.path.exists(".env") else "environment_variables",
                },
                "timestamp": time.time()
            })
            
            return env_info
            
        except Exception as e:
            return {
                "status": "error",
                "message": f"Environment info error: {str(e)}",
                "timestamp": time.time()
            }

    @app.get("/test/config")
    async def test_configuration():
        """Test configuration system."""
        if not CONFIG_AVAILABLE:
            return {
                "status": "error",
                "message": "Configuration system not available",
                "config_available": False
            }
        
        try:
            return {
                "status": "success",
                "config_available": True,
                "app_name": settings.app_name,
                "debug": settings.debug,
                "log_level": settings.log_level,
                "api_host": settings.api_host,
                "api_port": settings.api_port,
                "environment_variables": {
                    "ENVIRONMENT": os.getenv("ENVIRONMENT", "not_set"),
                    "AWS_DEFAULT_REGION": os.getenv("AWS_DEFAULT_REGION", "not_set"),
                    "PYTHONPATH": os.getenv("PYTHONPATH", "not_set"),
                    "LOG_LEVEL": os.getenv("LOG_LEVEL", "not_set")
                }
            }
        except Exception as e:
            return {
                "status": "error",
                "message": f"Configuration error: {str(e)}",
                "config_available": True
            }
    
    @app.get("/test/logging")
    async def test_logging():
        """Test logging system."""
        if not logger:
            return {
                "status": "error",
                "message": "Logger not available",
                "logging_available": False
            }
        
        try:
            logger.info("Test log message from /test/logging endpoint")
            logger.warning("Test warning message")
            logger.error("Test error message")
            
            return {
                "status": "success",
                "message": "Logging test completed - check CloudWatch logs",
                "logging_available": True,
                "log_level": settings.log_level if settings else "unknown"
            }
        except Exception as e:
            return {
                "status": "error",
                "message": f"Logging error: {str(e)}",
                "logging_available": True
            }
    
    # Add AWS-Native database test endpoint
    @app.get("/test/aws-native-databases")
    async def test_aws_native_databases():
        """Test AWS-Native database connectivity (Neptune and OpenSearch)."""
        try:
            from .clients.database_factory import get_database_factory
            factory = get_database_factory()
            
            # Perform comprehensive health check
            health_results = factory.health_check()
            
            # Get additional configuration info
            from .config.aws_native_config import get_aws_native_config
            config = get_aws_native_config()
            config_validation = config.validate_configuration()
            env_info = config.get_environment_info()
            
            return {
                "status": "success" if health_results["overall_status"] == "healthy" else "partial",
                "message": f"AWS-Native databases status: {health_results['overall_status']}",
                "aws_native_available": health_results["overall_status"] in ["healthy", "degraded"],
                "test_location": "ECS_TASK",
                "backend_type": "aws_native",
                "health_check": health_results,
                "configuration": config_validation,
                "environment": env_info,
                "services": {
                    "neptune": {
                        "enabled": config.enable_graph_db,
                        "status": health_results["services"].get("graph_db", {}).get("status", "unknown")
                    },
                    "opensearch": {
                        "enabled": config.enable_vector_search,
                        "status": health_results["services"].get("vector_db", {}).get("status", "unknown")
                    }
                }
            }
            
        except Exception as e:
            return {
                "status": "error",
                "message": f"Failed to test AWS-Native databases: {str(e)}",
                "aws_native_available": False,
                "test_location": "ECS_TASK",
                "backend_type": "aws_native",
                "error": str(e)
            }
    
    return app

# Create the app instance
app = create_minimal_app()

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "multimodal_librarian.main:app",
        host="0.0.0.0",
        port=8000,
        workers=1,
    )