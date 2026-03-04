"""
Enhanced Search Service with Fallback Management.

This module provides an enhanced search service that integrates with the fallback manager
for automatic health monitoring, fallback detection, and service switching.
"""

import logging
import asyncio
from typing import Dict, Any, Optional, List
from datetime import datetime
import uuid

from ...models.search_types import SearchResult, SearchQuery, SearchResponse
from ...models.core import SourceType, ContentType
from .vector_store import VectorStore
from .search_service import EnhancedSemanticSearchService, SearchRequest
from .search_service_simple import SimpleSemanticSearchService, SimpleSearchRequest
from .fallback_manager import FallbackManager, FallbackConfig, FallbackEvent, ServiceStatus

logger = logging.getLogger(__name__)


class SearchServiceWithFallback:
    """
    Enhanced search service with automatic fallback management.
    
    Provides health monitoring, automatic fallback detection, and service switching
    for reliable search operations.
    """
    
    def __init__(
        self, 
        vector_store: VectorStore, 
        config=None,
        fallback_config: Optional[FallbackConfig] = None
    ):
        """
        Initialize enhanced search service with fallback management.
        
        Args:
            vector_store: Vector database instance
            config: Search configuration
            fallback_config: Fallback manager configuration
        """
        self.vector_store = vector_store
        self.config = config
        
        # Initialize fallback manager
        self.fallback_manager = FallbackManager(fallback_config)
        
        # Initialize search services
        self.primary_service = EnhancedSemanticSearchService(vector_store, config)
        self.fallback_service = SimpleSemanticSearchService(vector_store)
        
        # Register services with fallback manager
        self.fallback_manager.register_service("primary", self.primary_service, is_primary=True)
        self.fallback_manager.register_service("fallback", self.fallback_service, is_primary=False)
        
        # Add notification callback
        self.fallback_manager.add_notification_callback(self._handle_fallback_notification)
        
        # Current active service
        self.current_service = self.primary_service
        self.current_service_name = "primary"
        
        # Performance tracking
        self.performance_stats = {
            'total_searches': 0,
            'primary_searches': 0,
            'fallback_searches': 0,
            'avg_response_time': 0.0,
            'fallback_activations': 0,
            'service_switches': 0
        }
        
        logger.info("Enhanced search service with fallback management initialized")
    
    async def start(self) -> None:
        """Start the search service and fallback monitoring."""
        try:
            # Start fallback monitoring
            await self.fallback_manager.start_monitoring()
            logger.info("Search service with fallback management started")
        except Exception as e:
            logger.error(f"Failed to start search service: {e}")
            raise
    
    async def stop(self) -> None:
        """Stop the search service and fallback monitoring."""
        try:
            await self.fallback_manager.stop_monitoring()
            logger.info("Search service with fallback management stopped")
        except Exception as e:
            logger.error(f"Error stopping search service: {e}")
    
    async def search(self, request: SearchRequest):
        """
        Perform search with automatic fallback handling.
        
        Args:
            request: Search request
            
        Returns:
            Search response with results and metadata
        """
        start_time = datetime.now()
        service_used = self.current_service_name
        
        try:
            # Check if we need to switch services based on fallback status
            await self._update_current_service()
            
            # Perform search with current service
            response = await self.current_service.search(request)
            
            # Update performance stats
            search_time_ms = (datetime.now() - start_time).total_seconds() * 1000
            await self._update_performance_stats(service_used, search_time_ms, success=True)
            
            return response
            
        except Exception as e:
            # Update performance stats for failure
            search_time_ms = (datetime.now() - start_time).total_seconds() * 1000
            await self._update_performance_stats(service_used, search_time_ms, success=False)
            
            logger.error(f"Search failed with {service_used} service: {e}")
            
            # Try fallback if not already using it
            if self.current_service_name == "primary":
                try:
                    logger.info("Attempting fallback search")
                    fallback_response = await self.fallback_service.search(request.to_simple_request())
                    
                    # Update stats for successful fallback
                    await self._update_performance_stats("fallback", search_time_ms, success=True)
                    
                    return fallback_response
                    
                except Exception as fallback_error:
                    logger.error(f"Fallback search also failed: {fallback_error}")
            
            # If all else fails, return empty response
            from .search_service_simple import SimpleSearchResponse
            return SimpleSearchResponse(
                results=[],
                search_time_ms=search_time_ms,
                session_id=request.session_id
            )
    
    async def _update_current_service(self) -> None:
        """Update the current active service based on fallback status."""
        # Check if primary service is in fallback
        if self.fallback_manager.is_service_in_fallback("primary"):
            if self.current_service_name == "primary":
                # Switch to fallback service
                self.current_service = self.fallback_service
                self.current_service_name = "fallback"
                self.performance_stats['service_switches'] += 1
                logger.info("Switched to fallback search service")
        else:
            if self.current_service_name == "fallback":
                # Switch back to primary service
                self.current_service = self.primary_service
                self.current_service_name = "primary"
                self.performance_stats['service_switches'] += 1
                logger.info("Switched back to primary search service")
    
    async def _update_performance_stats(
        self, 
        service_name: str, 
        response_time_ms: float, 
        success: bool
    ) -> None:
        """
        Update performance statistics.
        
        Args:
            service_name: Name of service used
            response_time_ms: Response time in milliseconds
            success: Whether the operation was successful
        """
        self.performance_stats['total_searches'] += 1
        
        if service_name == "primary":
            self.performance_stats['primary_searches'] += 1
        elif service_name == "fallback":
            self.performance_stats['fallback_searches'] += 1
        
        # Update average response time
        total_searches = self.performance_stats['total_searches']
        current_avg = self.performance_stats['avg_response_time']
        self.performance_stats['avg_response_time'] = (
            (current_avg * (total_searches - 1) + response_time_ms) / total_searches
        )
    
    def _handle_fallback_notification(self, event: FallbackEvent) -> None:
        """
        Handle fallback notifications.
        
        Args:
            event: Fallback event information
        """
        if event.resolved:
            logger.info(
                f"Service '{event.service_name}' recovered from fallback "
                f"(reason: {event.reason.value})"
            )
        else:
            logger.warning(
                f"Fallback activated for service '{event.service_name}' "
                f"(reason: {event.reason.value}): {event.message}"
            )
            self.performance_stats['fallback_activations'] += 1
    
    async def record_result_interaction(
        self,
        session_id: str,
        query: str,
        chunk_id: str,
        interaction_type: str,
        position: Optional[int] = None,
        rating: Optional[float] = None
    ) -> None:
        """Record user interaction with search results."""
        try:
            # Delegate to current service if it supports interaction recording
            if hasattr(self.current_service, 'record_result_interaction'):
                await self.current_service.record_result_interaction(
                    session_id, query, chunk_id, interaction_type, position, rating
                )
        except Exception as e:
            logger.error(f"Failed to record interaction: {e}")
    
    async def get_search_analytics(self, hours: int = 24) -> Dict[str, Any]:
        """Get comprehensive search analytics including fallback information."""
        try:
            # Get analytics from current service
            service_analytics = {}
            if hasattr(self.current_service, 'get_search_analytics'):
                service_analytics = await self.current_service.get_search_analytics(hours)
            
            # Get fallback statistics
            fallback_stats = self.fallback_manager.get_fallback_statistics()
            
            # Get service status
            service_status = {
                name: metrics.to_dict() 
                for name, metrics in self.fallback_manager.get_all_service_status().items()
            }
            
            # Combine all analytics
            return {
                'service_analytics': service_analytics,
                'performance_stats': self.performance_stats.copy(),
                'fallback_statistics': fallback_stats,
                'service_status': service_status,
                'current_service': self.current_service_name,
                'active_fallbacks': [
                    event.to_dict() 
                    for event in self.fallback_manager.get_active_fallbacks().values()
                ],
                'recent_fallback_history': [
                    event.to_dict() 
                    for event in self.fallback_manager.get_fallback_history(hours)
                ]
            }
            
        except Exception as e:
            logger.error(f"Failed to get analytics: {e}")
            return {'error': str(e)}
    
    def health_check(self) -> bool:
        """Check if the search service is healthy."""
        try:
            # Check current service health
            current_healthy = self.current_service.health_check()
            
            # Check fallback manager health
            fallback_healthy = len(self.fallback_manager.services) > 0
            
            return current_healthy and fallback_healthy
            
        except Exception as e:
            logger.error(f"Health check failed: {e}")
            return False
    
    def get_performance_stats(self) -> Dict[str, Any]:
        """Get performance statistics."""
        return self.performance_stats.copy()
    
    def get_service_status(self) -> Dict[str, Any]:
        """Get current service status information."""
        return {
            'current_service': self.current_service_name,
            'primary_service_status': self.fallback_manager.get_service_status("primary"),
            'fallback_service_status': self.fallback_manager.get_service_status("fallback"),
            'active_fallbacks': list(self.fallback_manager.get_active_fallbacks().keys()),
            'performance_stats': self.performance_stats.copy()
        }
    
    async def manual_fallback(self, reason: str = "Manual fallback triggered") -> bool:
        """
        Manually trigger fallback to secondary service.
        
        Args:
            reason: Reason for manual fallback
            
        Returns:
            True if fallback was triggered successfully
        """
        return await self.fallback_manager.manual_fallback("primary", reason)
    
    async def manual_recovery(self) -> bool:
        """
        Manually trigger recovery to primary service.
        
        Returns:
            True if recovery was triggered successfully
        """
        return await self.fallback_manager.manual_recovery("primary")
    
    def get_fallback_manager(self) -> FallbackManager:
        """Get the fallback manager instance for advanced operations."""
        return self.fallback_manager


# Backward compatibility
EnhancedSearchService = SearchServiceWithFallback