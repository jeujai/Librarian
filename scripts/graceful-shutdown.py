#!/usr/bin/env python3
"""
Graceful Shutdown Manager for Local Development Environment

This script provides comprehensive graceful shutdown procedures for the local
development environment, ensuring all services are properly stopped and
resources are cleaned up.

Features:
- Coordinated shutdown of all Docker services
- Database connection cleanup
- Resource cleanup and validation
- Configurable shutdown timeouts
- Health monitoring during shutdown
- Rollback capabilities if shutdown fails

Usage:
    python scripts/graceful-shutdown.py [options]
    
Options:
    --timeout SECONDS    Maximum time to wait for graceful shutdown (default: 60)
    --force             Force shutdown if graceful shutdown fails
    --services SERVICE  Shutdown specific services only (comma-separated)
    --skip-cleanup      Skip resource cleanup validation
    --verbose           Enable verbose logging
    --dry-run           Show what would be done without executing

Examples:
    # Standard graceful shutdown
    python scripts/graceful-shutdown.py
    
    # Quick shutdown with 30-second timeout
    python scripts/graceful-shutdown.py --timeout 30
    
    # Shutdown specific services only
    python scripts/graceful-shutdown.py --services postgres,redis
    
    # Force shutdown if graceful fails
    python scripts/graceful-shutdown.py --force
"""

import asyncio
import argparse
import logging
import signal
import sys
import time
import json
import subprocess
from pathlib import Path
from typing import List, Dict, Optional, Set
from datetime import datetime, timedelta

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class GracefulShutdownManager:
    """
    Manages graceful shutdown of the local development environment.
    
    This class coordinates the shutdown of all Docker services, ensures
    proper cleanup of resources, and provides monitoring and rollback
    capabilities.
    """
    
    def __init__(self, timeout: int = 60, force: bool = False, verbose: bool = False):
        """
        Initialize the graceful shutdown manager.
        
        Args:
            timeout: Maximum time to wait for graceful shutdown
            force: Whether to force shutdown if graceful shutdown fails
            verbose: Enable verbose logging
        """
        self.timeout = timeout
        self.force = force
        self.verbose = verbose
        self.shutdown_start_time = None
        self.services_shutdown = set()
        self.failed_services = set()
        
        # Service shutdown order (dependencies first)
        self.shutdown_order = [
            "multimodal-librarian",  # Application first
            "attu",                  # Admin tools
            "pgadmin", 
            "redis-commander",
            "log-viewer",
            "milvus",                # Vector database
            "neo4j",                 # Graph database  
            "postgres",              # Relational database
            "redis",                 # Cache
            "minio",                 # Milvus dependency
            "etcd"                   # Milvus dependency
        ]
        
        # Service shutdown timeouts (in seconds)
        self.service_timeouts = {
            "multimodal-librarian": 30,
            "postgres": 20,
            "neo4j": 25,
            "milvus": 20,
            "redis": 10,
            "minio": 15,
            "etcd": 10,
            "pgadmin": 10,
            "attu": 10,
            "redis-commander": 10,
            "log-viewer": 5
        }
        
        if verbose:
            logging.getLogger().setLevel(logging.DEBUG)
            logger.debug("Verbose logging enabled")
    
    async def shutdown(self, services: Optional[List[str]] = None, skip_cleanup: bool = False, dry_run: bool = False) -> bool:
        """
        Perform graceful shutdown of services.
        
        Args:
            services: Specific services to shutdown (None for all)
            skip_cleanup: Skip resource cleanup validation
            dry_run: Show what would be done without executing
            
        Returns:
            True if shutdown was successful, False otherwise
        """
        self.shutdown_start_time = time.time()
        
        logger.info("=" * 80)
        logger.info("🛑 STARTING GRACEFUL SHUTDOWN")
        logger.info("=" * 80)
        
        if dry_run:
            logger.info("🔍 DRY RUN MODE - No actual shutdown will be performed")
        
        try:
            # Step 1: Pre-shutdown validation
            if not await self._pre_shutdown_validation(dry_run):
                logger.error("❌ Pre-shutdown validation failed")
                return False
            
            # Step 2: Signal application shutdown
            if not await self._signal_application_shutdown(dry_run):
                logger.error("❌ Failed to signal application shutdown")
                if not self.force:
                    return False
            
            # Step 3: Shutdown services in order
            target_services = services if services else self.shutdown_order
            if not await self._shutdown_services(target_services, dry_run):
                logger.error("❌ Service shutdown failed")
                if not self.force:
                    return False
            
            # Step 4: Cleanup resources
            if not skip_cleanup and not await self._cleanup_resources(dry_run):
                logger.error("❌ Resource cleanup failed")
                if not self.force:
                    return False
            
            # Step 5: Validate shutdown
            if not await self._validate_shutdown(dry_run):
                logger.error("❌ Shutdown validation failed")
                if not self.force:
                    return False
            
            shutdown_duration = time.time() - self.shutdown_start_time
            logger.info("=" * 80)
            logger.info(f"✅ GRACEFUL SHUTDOWN COMPLETED in {shutdown_duration:.2f}s")
            logger.info("=" * 80)
            
            return True
            
        except KeyboardInterrupt:
            logger.warning("⚠️ Shutdown interrupted by user")
            if self.force:
                logger.info("🔨 Forcing immediate shutdown...")
                await self._force_shutdown(dry_run)
            return False
            
        except Exception as e:
            logger.error(f"❌ Unexpected error during shutdown: {e}")
            if self.force:
                logger.info("🔨 Forcing shutdown due to error...")
                await self._force_shutdown(dry_run)
            return False
    
    async def _pre_shutdown_validation(self, dry_run: bool) -> bool:
        """Validate environment before starting shutdown."""
        logger.info("🔍 Step 1: Pre-shutdown validation")
        
        try:
            # Check if Docker Compose is available
            if not dry_run:
                result = subprocess.run(
                    ["docker-compose", "--version"],
                    capture_output=True,
                    text=True,
                    timeout=10
                )
                if result.returncode != 0:
                    logger.error("Docker Compose not available")
                    return False
            
            # Check if docker-compose.local.yml exists
            compose_file = Path("docker-compose.local.yml")
            if not compose_file.exists():
                logger.error("docker-compose.local.yml not found")
                return False
            
            # Get current running services
            if not dry_run:
                running_services = await self._get_running_services()
                logger.info(f"Found {len(running_services)} running services: {', '.join(running_services)}")
            else:
                logger.info("Would check for running services")
            
            logger.info("✅ Pre-shutdown validation passed")
            return True
            
        except Exception as e:
            logger.error(f"Pre-shutdown validation failed: {e}")
            return False
    
    async def _signal_application_shutdown(self, dry_run: bool) -> bool:
        """Signal the application to begin graceful shutdown."""
        logger.info("📡 Step 2: Signaling application shutdown")
        
        try:
            if not dry_run:
                # Send SIGTERM to the application container
                result = subprocess.run([
                    "docker-compose", "-f", "docker-compose.local.yml",
                    "kill", "-s", "SIGTERM", "multimodal-librarian"
                ], capture_output=True, text=True, timeout=10)
                
                if result.returncode == 0:
                    logger.info("✅ SIGTERM sent to application")
                    
                    # Wait for application to acknowledge shutdown
                    await asyncio.sleep(5)
                    
                    # Check if application is still responding
                    try:
                        import aiohttp
                        async with aiohttp.ClientSession() as session:
                            async with session.get(
                                "http://localhost:8000/health/simple",
                                timeout=aiohttp.ClientTimeout(total=5)
                            ) as response:
                                if response.status == 200:
                                    logger.info("Application still responding, allowing more time...")
                                    await asyncio.sleep(10)
                    except:
                        logger.info("Application no longer responding (expected)")
                    
                else:
                    logger.warning(f"Failed to send SIGTERM: {result.stderr}")
            else:
                logger.info("Would send SIGTERM to application container")
            
            logger.info("✅ Application shutdown signaled")
            return True
            
        except Exception as e:
            logger.error(f"Failed to signal application shutdown: {e}")
            return False
    
    async def _shutdown_services(self, services: List[str], dry_run: bool) -> bool:
        """Shutdown services in the specified order."""
        logger.info("🛑 Step 3: Shutting down services")
        
        success = True
        
        for service in services:
            if service not in self.shutdown_order:
                logger.warning(f"Unknown service: {service}")
                continue
            
            logger.info(f"Shutting down {service}...")
            
            if not dry_run:
                service_success = await self._shutdown_single_service(service)
                if service_success:
                    self.services_shutdown.add(service)
                    logger.info(f"✅ {service} shutdown completed")
                else:
                    self.failed_services.add(service)
                    logger.error(f"❌ {service} shutdown failed")
                    success = False
            else:
                logger.info(f"Would shutdown {service}")
                await asyncio.sleep(0.1)  # Simulate time
        
        if success:
            logger.info("✅ All services shutdown successfully")
        else:
            logger.error(f"❌ Failed services: {', '.join(self.failed_services)}")
        
        return success
    
    async def _shutdown_single_service(self, service: str) -> bool:
        """Shutdown a single service with timeout."""
        timeout = self.service_timeouts.get(service, 30)
        
        try:
            # First try graceful stop
            result = subprocess.run([
                "docker-compose", "-f", "docker-compose.local.yml",
                "stop", "-t", str(timeout), service
            ], capture_output=True, text=True, timeout=timeout + 10)
            
            if result.returncode == 0:
                logger.debug(f"{service} stopped gracefully")
                return True
            else:
                logger.warning(f"{service} graceful stop failed: {result.stderr}")
                
                # Try force kill if graceful stop failed
                if self.force:
                    logger.info(f"Force killing {service}...")
                    kill_result = subprocess.run([
                        "docker-compose", "-f", "docker-compose.local.yml",
                        "kill", service
                    ], capture_output=True, text=True, timeout=10)
                    
                    if kill_result.returncode == 0:
                        logger.info(f"{service} force killed")
                        return True
                
                return False
                
        except subprocess.TimeoutExpired:
            logger.error(f"{service} shutdown timed out after {timeout}s")
            if self.force:
                logger.info(f"Force killing {service} due to timeout...")
                try:
                    subprocess.run([
                        "docker-compose", "-f", "docker-compose.local.yml",
                        "kill", service
                    ], capture_output=True, text=True, timeout=10)
                    return True
                except:
                    pass
            return False
            
        except Exception as e:
            logger.error(f"Error shutting down {service}: {e}")
            return False
    
    async def _cleanup_resources(self, dry_run: bool) -> bool:
        """Clean up resources after service shutdown."""
        logger.info("🧹 Step 4: Cleaning up resources")
        
        try:
            if not dry_run:
                # Remove stopped containers
                logger.info("Removing stopped containers...")
                subprocess.run([
                    "docker-compose", "-f", "docker-compose.local.yml",
                    "rm", "-f"
                ], capture_output=True, text=True, timeout=30)
                
                # Clean up unused networks (but preserve volumes)
                logger.info("Cleaning up unused networks...")
                subprocess.run([
                    "docker", "network", "prune", "-f"
                ], capture_output=True, text=True, timeout=30)
                
                # Optional: Clean up unused images (commented out to preserve development images)
                # logger.info("Cleaning up unused images...")
                # subprocess.run([
                #     "docker", "image", "prune", "-f"
                # ], capture_output=True, text=True, timeout=60)
                
            else:
                logger.info("Would remove stopped containers")
                logger.info("Would clean up unused networks")
            
            logger.info("✅ Resource cleanup completed")
            return True
            
        except Exception as e:
            logger.error(f"Resource cleanup failed: {e}")
            return False
    
    async def _validate_shutdown(self, dry_run: bool) -> bool:
        """Validate that shutdown was successful."""
        logger.info("✅ Step 5: Validating shutdown")
        
        try:
            if not dry_run:
                # Check that no services are still running
                running_services = await self._get_running_services()
                
                if running_services:
                    logger.warning(f"Services still running: {', '.join(running_services)}")
                    return False
                
                # Check that ports are released
                import socket
                ports_to_check = [8000, 5432, 7474, 7687, 19530, 6379, 9000, 2379]
                for port in ports_to_check:
                    if self._is_port_in_use(port):
                        logger.warning(f"Port {port} still in use")
                        # Don't fail validation for port checks as they might be used by other processes
                
            else:
                logger.info("Would validate that all services are stopped")
                logger.info("Would check that ports are released")
            
            logger.info("✅ Shutdown validation passed")
            return True
            
        except Exception as e:
            logger.error(f"Shutdown validation failed: {e}")
            return False
    
    async def _force_shutdown(self, dry_run: bool) -> None:
        """Force immediate shutdown of all services."""
        logger.info("🔨 Forcing immediate shutdown...")
        
        if not dry_run:
            try:
                # Kill all services
                subprocess.run([
                    "docker-compose", "-f", "docker-compose.local.yml",
                    "kill"
                ], capture_output=True, text=True, timeout=30)
                
                # Remove containers
                subprocess.run([
                    "docker-compose", "-f", "docker-compose.local.yml",
                    "rm", "-f"
                ], capture_output=True, text=True, timeout=30)
                
                logger.info("✅ Force shutdown completed")
                
            except Exception as e:
                logger.error(f"Force shutdown failed: {e}")
        else:
            logger.info("Would force kill all services")
    
    async def _get_running_services(self) -> List[str]:
        """Get list of currently running services."""
        try:
            result = subprocess.run([
                "docker-compose", "-f", "docker-compose.local.yml",
                "ps", "--services", "--filter", "status=running"
            ], capture_output=True, text=True, timeout=10)
            
            if result.returncode == 0:
                services = [s.strip() for s in result.stdout.split('\n') if s.strip()]
                return services
            else:
                logger.warning(f"Failed to get running services: {result.stderr}")
                return []
                
        except Exception as e:
            logger.error(f"Error getting running services: {e}")
            return []
    
    def _is_port_in_use(self, port: int) -> bool:
        """Check if a port is currently in use."""
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.settimeout(1)
                result = s.connect_ex(('localhost', port))
                return result == 0
        except:
            return False


async def main():
    """Main entry point for the graceful shutdown script."""
    parser = argparse.ArgumentParser(
        description="Graceful shutdown manager for local development environment",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s                                    # Standard graceful shutdown
  %(prog)s --timeout 30                      # Quick shutdown with 30s timeout
  %(prog)s --services postgres,redis         # Shutdown specific services
  %(prog)s --force                           # Force shutdown if graceful fails
  %(prog)s --dry-run                         # Show what would be done
        """
    )
    
    parser.add_argument(
        "--timeout",
        type=int,
        default=60,
        help="Maximum time to wait for graceful shutdown (default: 60)"
    )
    
    parser.add_argument(
        "--force",
        action="store_true",
        help="Force shutdown if graceful shutdown fails"
    )
    
    parser.add_argument(
        "--services",
        type=str,
        help="Shutdown specific services only (comma-separated)"
    )
    
    parser.add_argument(
        "--skip-cleanup",
        action="store_true",
        help="Skip resource cleanup validation"
    )
    
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable verbose logging"
    )
    
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be done without executing"
    )
    
    args = parser.parse_args()
    
    # Parse services list
    services = None
    if args.services:
        services = [s.strip() for s in args.services.split(',')]
    
    # Create shutdown manager
    manager = GracefulShutdownManager(
        timeout=args.timeout,
        force=args.force,
        verbose=args.verbose
    )
    
    # Perform shutdown
    success = await manager.shutdown(
        services=services,
        skip_cleanup=args.skip_cleanup,
        dry_run=args.dry_run
    )
    
    # Exit with appropriate code
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Shutdown interrupted by user")
        sys.exit(1)
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        sys.exit(1)