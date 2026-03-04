"""
Session Cache Service for User-Specific Caching

This module provides session-based caching functionality that maintains
user-specific cache data with automatic cleanup and session management.
"""

import asyncio
import logging
import uuid
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Set
from dataclasses import dataclass, field
import threading
import weakref

from .multi_level_cache_manager import get_multi_level_cache_manager

logger = logging.getLogger(__name__)


@dataclass
class SessionInfo:
    """Session information and metadata."""
    session_id: str
    user_id: Optional[str] = None
    created_at: datetime = field(default_factory=datetime.now)
    last_activity: datetime = field(default_factory=datetime.now)
    ip_address: Optional[str] = None
    user_agent: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    cache_keys: Set[str] = field(default_factory=set)
    
    @property
    def is_expired(self) -> bool:
        """Check if session has expired."""
        return (datetime.now() - self.last_activity).total_seconds() > 7200  # 2 hours
    
    def touch(self):
        """Update last activity timestamp."""
        self.last_activity = datetime.now()


@dataclass
class SessionCacheStats:
    """Session cache statistics."""
    total_sessions: int = 0
    active_sessions: int = 0
    expired_sessions: int = 0
    total_cache_entries: int = 0
    cache_hits: int = 0
    cache_misses: int = 0
    cleanup_runs: int = 0
    last_cleanup: Optional[datetime] = None
    
    @property
    def hit_rate(self) -> float:
        total = self.cache_hits + self.cache_misses
        return (self.cache_hits / total * 100) if total > 0 else 0.0


class SessionCacheService:
    """
    Session-based caching service for user-specific data.
    
    Features:
    - User session management with automatic expiration
    - Session-scoped cache entries
    - Automatic cleanup of expired sessions
    - Session activity tracking
    - Cache statistics and monitoring
    - Thread-safe operations
    """
    
    def __init__(self, session_ttl: int = 7200):  # 2 hours default
        """Initialize session cache service."""
        self.session_ttl = session_ttl
        self.sessions: Dict[str, SessionInfo] = {}
        self.session_lock = threading.RLock()
        self.cache_manager = None
        self.stats = SessionCacheStats()
        self.cleanup_task: Optional[asyncio.Task] = None
        self.is_running = False
        
        logger.info(f"Session cache service initialized with TTL: {session_ttl}s")
    
    async def initialize(self):
        """Initialize the session cache service."""
        if self.cache_manager is None:
            self.cache_manager = await get_multi_level_cache_manager()
        
        # Start cleanup task
        if not self.is_running:
            self.cleanup_task = asyncio.create_task(self._cleanup_loop())
            self.is_running = True
            logger.info("Session cache service initialized and cleanup started")
    
    async def shutdown(self):
        """Shutdown the session cache service."""
        self.is_running = False
        if self.cleanup_task:
            self.cleanup_task.cancel()
            try:
                await self.cleanup_task
            except asyncio.CancelledError:
                pass
        logger.info("Session cache service shutdown")
    
    def create_session(
        self, 
        user_id: Optional[str] = None,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> str:
        """
        Create a new session.
        
        Args:
            user_id: Optional user identifier
            ip_address: Client IP address
            user_agent: Client user agent
            metadata: Additional session metadata
            
        Returns:
            Session ID
        """
        session_id = str(uuid.uuid4())
        
        with self.session_lock:
            session_info = SessionInfo(
                session_id=session_id,
                user_id=user_id,
                ip_address=ip_address,
                user_agent=user_agent,
                metadata=metadata or {}
            )
            
            self.sessions[session_id] = session_info
            self.stats.total_sessions += 1
            self.stats.active_sessions += 1
        
        logger.info(f"Created session: {session_id} for user: {user_id}")
        return session_id
    
    def get_session(self, session_id: str) -> Optional[SessionInfo]:
        """Get session information."""
        with self.session_lock:
            session = self.sessions.get(session_id)
            if session and not session.is_expired:
                session.touch()
                return session
            elif session and session.is_expired:
                # Remove expired session
                del self.sessions[session_id]
                self.stats.active_sessions -= 1
                self.stats.expired_sessions += 1
            return None
    
    def is_session_valid(self, session_id: str) -> bool:
        """Check if session is valid and active."""
        return self.get_session(session_id) is not None
    
    def touch_session(self, session_id: str) -> bool:
        """Update session activity timestamp."""
        with self.session_lock:
            session = self.sessions.get(session_id)
            if session and not session.is_expired:
                session.touch()
                return True
            return False
    
    def _get_session_cache_key(self, session_id: str, key: str) -> str:
        """Generate session-specific cache key."""
        return f"session:{session_id}:{key}"
    
    async def get(self, session_id: str, key: str) -> Optional[Any]:
        """
        Get value from session cache.
        
        Args:
            session_id: Session identifier
            key: Cache key
            
        Returns:
            Cached value or None if not found
        """
        if not self.is_session_valid(session_id):
            self.stats.cache_misses += 1
            return None
        
        if not self.cache_manager:
            await self.initialize()
        
        try:
            session_key = self._get_session_cache_key(session_id, key)
            value = await self.cache_manager.get(session_key)
            
            if value is not None:
                self.stats.cache_hits += 1
                logger.debug(f"Session cache hit: {session_id}:{key}")
            else:
                self.stats.cache_misses += 1
            
            return value
            
        except Exception as e:
            logger.error(f"Session cache get failed for {session_id}:{key}: {e}")
            self.stats.cache_misses += 1
            return None
    
    async def set(
        self, 
        session_id: str, 
        key: str, 
        value: Any, 
        ttl: Optional[int] = None
    ) -> bool:
        """
        Set value in session cache.
        
        Args:
            session_id: Session identifier
            key: Cache key
            value: Value to cache
            ttl: Time to live in seconds (defaults to session TTL)
            
        Returns:
            True if successful, False otherwise
        """
        if not self.is_session_valid(session_id):
            return False
        
        if not self.cache_manager:
            await self.initialize()
        
        try:
            session_key = self._get_session_cache_key(session_id, key)
            cache_ttl = ttl or self.session_ttl
            
            success = await self.cache_manager.set(session_key, value, cache_ttl)
            
            if success:
                # Track cache key for cleanup
                with self.session_lock:
                    session = self.sessions.get(session_id)
                    if session:
                        session.cache_keys.add(session_key)
                        self.stats.total_cache_entries += 1
                
                logger.debug(f"Session cache set: {session_id}:{key}")
            
            return success
            
        except Exception as e:
            logger.error(f"Session cache set failed for {session_id}:{key}: {e}")
            return False
    
    async def delete(self, session_id: str, key: str) -> bool:
        """
        Delete value from session cache.
        
        Args:
            session_id: Session identifier
            key: Cache key
            
        Returns:
            True if successful, False otherwise
        """
        if not self.cache_manager:
            await self.initialize()
        
        try:
            session_key = self._get_session_cache_key(session_id, key)
            success = await self.cache_manager.delete(session_key)
            
            if success:
                # Remove from tracked keys
                with self.session_lock:
                    session = self.sessions.get(session_id)
                    if session and session_key in session.cache_keys:
                        session.cache_keys.remove(session_key)
                        self.stats.total_cache_entries -= 1
                
                logger.debug(f"Session cache delete: {session_id}:{key}")
            
            return success
            
        except Exception as e:
            logger.error(f"Session cache delete failed for {session_id}:{key}: {e}")
            return False
    
    async def clear_session(self, session_id: str) -> int:
        """
        Clear all cache entries for a session.
        
        Args:
            session_id: Session identifier
            
        Returns:
            Number of entries cleared
        """
        if not self.cache_manager:
            await self.initialize()
        
        cleared_count = 0
        
        with self.session_lock:
            session = self.sessions.get(session_id)
            if not session:
                return 0
            
            # Get all cache keys for this session
            cache_keys = list(session.cache_keys)
        
        # Delete all cache entries
        for cache_key in cache_keys:
            try:
                if await self.cache_manager.delete(cache_key):
                    cleared_count += 1
            except Exception as e:
                logger.warning(f"Failed to delete cache key {cache_key}: {e}")
        
        # Update session and stats
        with self.session_lock:
            if session_id in self.sessions:
                self.sessions[session_id].cache_keys.clear()
                self.stats.total_cache_entries -= cleared_count
        
        if cleared_count > 0:
            logger.info(f"Cleared {cleared_count} cache entries for session: {session_id}")
        
        return cleared_count
    
    async def destroy_session(self, session_id: str) -> bool:
        """
        Destroy a session and clear all its cache entries.
        
        Args:
            session_id: Session identifier
            
        Returns:
            True if successful, False otherwise
        """
        try:
            # Clear cache entries
            await self.clear_session(session_id)
            
            # Remove session
            with self.session_lock:
                if session_id in self.sessions:
                    del self.sessions[session_id]
                    self.stats.active_sessions -= 1
            
            logger.info(f"Destroyed session: {session_id}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to destroy session {session_id}: {e}")
            return False
    
    async def get_session_cache_keys(self, session_id: str) -> List[str]:
        """Get all cache keys for a session."""
        with self.session_lock:
            session = self.sessions.get(session_id)
            if session:
                return list(session.cache_keys)
            return []
    
    async def get_session_cache_stats(self, session_id: str) -> Dict[str, Any]:
        """Get cache statistics for a specific session."""
        with self.session_lock:
            session = self.sessions.get(session_id)
            if not session:
                return {'error': 'Session not found'}
            
            return {
                'session_id': session_id,
                'user_id': session.user_id,
                'created_at': session.created_at.isoformat(),
                'last_activity': session.last_activity.isoformat(),
                'cache_entries': len(session.cache_keys),
                'is_expired': session.is_expired,
                'metadata': session.metadata
            }
    
    def get_active_sessions(self) -> List[str]:
        """Get list of active session IDs."""
        with self.session_lock:
            active = []
            for session_id, session in self.sessions.items():
                if not session.is_expired:
                    active.append(session_id)
            return active
    
    def get_session_count(self) -> Dict[str, int]:
        """Get session count statistics."""
        with self.session_lock:
            active_count = 0
            expired_count = 0
            
            for session in self.sessions.values():
                if session.is_expired:
                    expired_count += 1
                else:
                    active_count += 1
            
            return {
                'total': len(self.sessions),
                'active': active_count,
                'expired': expired_count
            }
    
    async def cleanup_expired_sessions(self) -> Dict[str, int]:
        """Clean up expired sessions and their cache entries."""
        if not self.cache_manager:
            await self.initialize()
        
        expired_sessions = []
        
        # Find expired sessions
        with self.session_lock:
            for session_id, session in list(self.sessions.items()):
                if session.is_expired:
                    expired_sessions.append(session_id)
        
        # Clean up expired sessions
        total_cleared_entries = 0
        for session_id in expired_sessions:
            try:
                cleared = await self.clear_session(session_id)
                total_cleared_entries += cleared
                
                # Remove session
                with self.session_lock:
                    if session_id in self.sessions:
                        del self.sessions[session_id]
                        self.stats.active_sessions -= 1
                        self.stats.expired_sessions += 1
                
            except Exception as e:
                logger.error(f"Failed to cleanup expired session {session_id}: {e}")
        
        self.stats.cleanup_runs += 1
        self.stats.last_cleanup = datetime.now()
        
        result = {
            'expired_sessions': len(expired_sessions),
            'cleared_cache_entries': total_cleared_entries
        }
        
        if len(expired_sessions) > 0:
            logger.info(f"Cleaned up {len(expired_sessions)} expired sessions, {total_cleared_entries} cache entries")
        
        return result
    
    async def _cleanup_loop(self):
        """Background cleanup loop for expired sessions."""
        while self.is_running:
            try:
                await asyncio.sleep(300)  # Run every 5 minutes
                
                if not self.is_running:
                    break
                
                await self.cleanup_expired_sessions()
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Session cleanup loop error: {e}")
                await asyncio.sleep(60)  # Wait before retrying
    
    def get_comprehensive_stats(self) -> Dict[str, Any]:
        """Get comprehensive session cache statistics."""
        session_counts = self.get_session_count()
        
        return {
            'sessions': {
                'total_created': self.stats.total_sessions,
                'currently_active': session_counts['active'],
                'expired': session_counts['expired'],
                'cleanup_runs': self.stats.cleanup_runs,
                'last_cleanup': self.stats.last_cleanup.isoformat() if self.stats.last_cleanup else None
            },
            'cache': {
                'total_entries': self.stats.total_cache_entries,
                'cache_hits': self.stats.cache_hits,
                'cache_misses': self.stats.cache_misses,
                'hit_rate_percent': self.stats.hit_rate
            },
            'configuration': {
                'session_ttl_seconds': self.session_ttl,
                'cleanup_running': self.is_running
            }
        }
    
    async def health_check(self) -> Dict[str, Any]:
        """Perform health check on session cache service."""
        session_counts = self.get_session_count()
        
        health = {
            'status': 'healthy',
            'initialized': self.cache_manager is not None,
            'cleanup_running': self.is_running,
            'active_sessions': session_counts['active'],
            'expired_sessions': session_counts['expired'],
            'total_cache_entries': self.stats.total_cache_entries
        }
        
        # Check for issues
        if session_counts['expired'] > session_counts['active'] * 2:
            health['status'] = 'warning'
            health['warning'] = 'High number of expired sessions - cleanup may be needed'
        
        if not self.is_running:
            health['status'] = 'degraded'
            health['warning'] = 'Cleanup task not running'
        
        return health


# Global session cache service instance
_session_cache_service = None

async def get_session_cache_service() -> SessionCacheService:
    """Get global session cache service instance."""
    global _session_cache_service
    if _session_cache_service is None:
        _session_cache_service = SessionCacheService()
        await _session_cache_service.initialize()
    return _session_cache_service