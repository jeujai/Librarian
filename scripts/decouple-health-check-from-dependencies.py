#!/usr/bin/env python3
"""
Decouple Health Check from Complex Dependencies

This script modifies the health check endpoint to not depend on OpenSearch,
vector stores, or other complex components that may fail during initialization.

The health check should only verify that the HTTP server is running and responding.
"""

import sys
import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


def create_simple_health_router():
    """Create a simplified health router that doesn't depend on complex components."""
    
    health_router_content = '''"""
Simple Health Check Router - Decoupled from Complex Dependencies

This router provides basic health checks that don't depend on OpenSearch,
vector stores, or other components that may fail during initialization.
"""

import time
import logging
from datetime import datetime
from fastapi import APIRouter
from fastapi.responses import JSONResponse

router = APIRouter(prefix="/api/health", tags=["Health"])
logger = logging.getLogger(__name__)

# Track when the server started
_server_start_time = time.time()


@router.get("/simple")
async def simple_health_check():
    """
    Simple health check for load balancers.
    
    This endpoint returns quickly with minimal processing.
    It does NOT depend on any external services or complex initialization.
    """
    try:
        uptime = time.time() - _server_start_time
        
        response = {
            "status": "ok",
            "uptime_seconds": uptime,
            "timestamp": datetime.now().isoformat()
        }
        
        return JSONResponse(content=response, status_code=200)
        
    except Exception as e:
        logger.error(f"Simple health check failed: {e}")
        return JSONResponse(
            content={
                "status": "error",
                "error": str(e),
                "timestamp": datetime.now().isoformat()
            },
            status_code=503
        )


@router.get("/minimal")
async def minimal_health_check():
    """
    Minimal health check - basic server readiness.
    
    This endpoint checks if the minimal server is initialized,
    but does NOT require complex dependencies like OpenSearch.
    """
    try:
        # Try to get minimal server status, but don't fail if it's not available
        try:
            from ...startup.minimal_server import get_minimal_server
            server = get_minimal_server()
            status = server.get_status()
            
            is_healthy = status.health_check_ready and status.status.value != "error"
            
            response = {
                "status": "healthy" if is_healthy else "starting",
                "server_status": status.status.value,
                "uptime_seconds": status.uptime_seconds,
                "ready": status.health_check_ready,
                "timestamp": datetime.now().isoformat()
            }
            
            status_code = 200 if is_healthy else 503
            
        except Exception as e:
            # If minimal server is not available, just return basic health
            logger.warning(f"Minimal server not available: {e}")
            uptime = time.time() - _server_start_time
            
            response = {
                "status": "healthy" if uptime > 5 else "starting",
                "uptime_seconds": uptime,
                "ready": uptime > 5,
                "timestamp": datetime.now().isoformat(),
                "note": "minimal_server_unavailable"
            }
            
            status_code = 200 if uptime > 5 else 503
        
        return JSONResponse(content=response, status_code=status_code)
        
    except Exception as e:
        logger.error(f"Minimal health check failed: {e}")
        return JSONResponse(
            content={
                "status": "error",
                "error": str(e),
                "ready": False,
                "timestamp": datetime.now().isoformat()
            },
            status_code=503
        )


@router.get("/ready")
async def readiness_health_check():
    """
    Readiness health check - checks if app is ready to serve requests.
    
    This is more comprehensive than /simple but still doesn't require
    all complex dependencies to be fully initialized.
    """
    try:
        uptime = time.time() - _server_start_time
        
        # Basic readiness: server has been up for at least 10 seconds
        is_ready = uptime > 10
        
        # Try to get more detailed status if available
        capabilities = {}
        try:
            from ...startup.minimal_server import get_minimal_server
            server = get_minimal_server()
            status = server.get_status()
            capabilities = status.capabilities
            
            # Consider ready if basic capabilities are available
            is_ready = is_ready or any(capabilities.values())
            
        except Exception as e:
            logger.debug(f"Could not get detailed status: {e}")
        
        response = {
            "status": "ready" if is_ready else "not_ready",
            "uptime_seconds": uptime,
            "capabilities": capabilities,
            "timestamp": datetime.now().isoformat()
        }
        
        status_code = 200 if is_ready else 503
        return JSONResponse(content=response, status_code=status_code)
        
    except Exception as e:
        logger.error(f"Readiness health check failed: {e}")
        return JSONResponse(
            content={
                "status": "error",
                "error": str(e),
                "ready": False,
                "timestamp": datetime.now().isoformat()
            },
            status_code=503
        )


@router.get("/")
async def root_health_check():
    """Root health check endpoint."""
    return await simple_health_check()
'''
    
    return health_router_content


def backup_and_replace_health_router():
    """Backup the current health router and replace with simplified version."""
    try:
        import shutil
        from pathlib import Path
        
        health_router_path = Path("src/multimodal_librarian/api/routers/health.py")
        backup_path = Path("src/multimodal_librarian/api/routers/health.py.backup")
        
        if not health_router_path.exists():
            logger.error(f"Health router not found at {health_router_path}")
            return False
        
        # Create backup
        logger.info(f"Creating backup at {backup_path}")
        shutil.copy2(health_router_path, backup_path)
        
        # Write new simplified version
        logger.info(f"Writing simplified health router to {health_router_path}")
        new_content = create_simple_health_router()
        
        with open(health_router_path, 'w') as f:
            f.write(new_content)
        
        logger.info("✓ Health router replaced with simplified version")
        logger.info(f"✓ Backup saved to {backup_path}")
        
        return True
        
    except Exception as e:
        logger.error(f"Failed to replace health router: {e}")
        return False


def add_search_service_alias():
    """Add SearchService alias to search_service.py."""
    try:
        search_service_path = "src/multimodal_librarian/components/vector_store/search_service.py"
        
        with open(search_service_path, 'r') as f:
            content = f.read()
        
        if 'SearchService = ' in content:
            logger.info("✓ SearchService alias already exists")
            return True
        
        # Add alias
        alias_code = "\n# Backward compatibility alias\nSearchService = EnhancedSemanticSearchService\n"
        
        with open(search_service_path, 'a') as f:
            f.write(alias_code)
        
        logger.info("✓ Added SearchService alias")
        return True
        
    except Exception as e:
        logger.error(f"Failed to add SearchService alias: {e}")
        return False


def main():
    """Main execution function."""
    logger.info("=" * 80)
    logger.info("DECOUPLING HEALTH CHECK FROM COMPLEX DEPENDENCIES")
    logger.info("=" * 80)
    
    results = {}
    
    # Fix 1: Replace health router with simplified version
    logger.info("\n1. Replacing health router with simplified version...")
    results['health_router'] = backup_and_replace_health_router()
    
    # Fix 2: Add SearchService alias
    logger.info("\n2. Adding SearchService compatibility alias...")
    results['search_service_alias'] = add_search_service_alias()
    
    # Summary
    logger.info("\n" + "=" * 80)
    logger.info("SUMMARY")
    logger.info("=" * 80)
    
    for fix_name, success in results.items():
        status = "✓ SUCCESS" if success else "✗ FAILED"
        logger.info(f"{status}: {fix_name}")
    
    if all(results.values()):
        logger.info("\n✓ All fixes applied successfully!")
        logger.info("\nNext steps:")
        logger.info("1. Rebuild your Docker container")
        logger.info("2. Redeploy to ECS")
        logger.info("3. Monitor /health/simple endpoint")
        logger.info("\nThe health check will now respond even if OpenSearch is not configured.")
        return 0
    else:
        logger.error("\n✗ Some fixes failed. Please review the errors above.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
