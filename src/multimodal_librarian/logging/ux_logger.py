"""
User Experience Logger for Multimodal Librarian Application

This module implements comprehensive logging for user request patterns during startup phases,
fallback response usage, user wait times, and user experience analytics.

Key Features:
- User request pattern logging during startup
- Fallback response usage tracking
- User wait time and abandonment monitoring
- User experience analytics and insights
- Integration with startup metrics and phase manager
"""

import asyncio
import time
import logging
import json
import uuid
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Set, Tuple
from dataclasses import dataclass, field, asdict
from enum import Enum
import statistics
from collections import defaultdict, Counter

from ..startup.phase_manager import StartupPhase, StartupPhaseManager
from ..services.fallback_service import UserIntent, FallbackResponse
from ..services.capability_service import CapabilityLevel

logger = logging.getLogger(__name__)


class RequestOutcome(Enum):
    """Possible outcomes for user requests."""
    SUCCESS = "success"
    FALLBACK_USED = "fallback_used"
    TIMEOUT = "timeout"
    ERROR = "error"
    ABANDONED = "abandoned"


class UserBehaviorPattern(Enum):
    """Patterns of user behavior during startup."""
    PATIENT_WAITER = "patient_waiter"  # Waits for full capabilities
    IMPATIENT_ABANDONER = "impatient_abandoner"  # Leaves quickly
    FALLBACK_ACCEPTER = "fallback_accepter"  # Uses fallback responses
    RETRY_PERSISTENT = "retry_persistent"  # Keeps trying same request
    EXPLORER = "explorer"  # Tries different features
    STATUS_CHECKER = "status_checker"  # Frequently checks status


@dataclass
class UserRequestPattern:
    """Detailed pattern information for a user request during startup."""
    request_id: str
    user_id: Optional[str]
    session_id: str
    timestamp: datetime
    startup_phase: StartupPhase
    startup_elapsed_seconds: float
    
    # Request details
    endpoint: str
    request_type: str
    user_message: Optional[str]
    detected_intent: Optional[UserIntent]
    intent_confidence: float
    required_capabilities: List[str]
    available_capabilities: List[str]
    
    # Response details
    response_time_seconds: Optional[float]
    outcome: RequestOutcome
    fallback_used: bool
    fallback_quality: Optional[CapabilityLevel]
    fallback_response: Optional[str]
    
    # User experience metrics
    user_wait_time_seconds: Optional[float]
    estimated_wait_time_seconds: Optional[float]
    queue_position: Optional[int]
    retry_count: int
    abandonment_reason: Optional[str]
    
    # Context information
    previous_requests_count: int
    time_since_last_request_seconds: Optional[float]
    concurrent_users: int
    system_load_level: str  # "low", "medium", "high"
    
    # Error information
    error_message: Optional[str]
    error_type: Optional[str]
    
    # Metadata
    user_agent: Optional[str]
    ip_address: Optional[str]
    referrer: Optional[str]


@dataclass
class UserSession:
    """Information about a user's session during startup."""
    session_id: str
    user_id: Optional[str]
    start_time: datetime
    end_time: Optional[datetime] = None
    duration_seconds: Optional[float] = None
    
    # Request patterns
    total_requests: int = 0
    successful_requests: int = 0
    fallback_requests: int = 0
    abandoned_requests: int = 0
    error_requests: int = 0
    
    # Timing patterns
    average_wait_time_seconds: Optional[float] = None
    max_wait_time_seconds: Optional[float] = None
    total_wait_time_seconds: float = 0.0
    
    # Behavior patterns
    behavior_pattern: Optional[UserBehaviorPattern] = None
    patience_score: float = 0.0  # 0-100, higher = more patient
    engagement_score: float = 0.0  # 0-100, higher = more engaged
    satisfaction_score: float = 0.0  # 0-100, estimated satisfaction
    
    # Request types used
    request_types_used: Set[str] = field(default_factory=set)
    intents_detected: Set[UserIntent] = field(default_factory=set)
    
    # Phase interaction
    phases_experienced: Set[StartupPhase] = field(default_factory=set)
    phase_transition_reactions: List[Dict[str, Any]] = field(default_factory=list)


@dataclass
class StartupUXMetrics:
    """Aggregated user experience metrics for a startup session."""
    startup_session_id: str
    startup_start_time: datetime
    startup_end_time: Optional[datetime] = None
    
    # Overall metrics
    total_users: int = 0
    total_requests: int = 0
    total_sessions: int = 0
    
    # Request outcome distribution
    successful_requests: int = 0
    fallback_requests: int = 0
    abandoned_requests: int = 0
    error_requests: int = 0
    timeout_requests: int = 0
    
    # Timing metrics
    average_user_wait_time: Optional[float] = None
    median_user_wait_time: Optional[float] = None
    p95_user_wait_time: Optional[float] = None
    abandonment_threshold_seconds: float = 30.0
    
    # User behavior patterns
    behavior_pattern_distribution: Dict[UserBehaviorPattern, int] = field(default_factory=dict)
    average_patience_score: float = 0.0
    average_engagement_score: float = 0.0
    average_satisfaction_score: float = 0.0
    
    # Phase-specific metrics
    requests_by_phase: Dict[StartupPhase, int] = field(default_factory=dict)
    fallback_usage_by_phase: Dict[StartupPhase, int] = field(default_factory=dict)
    abandonment_by_phase: Dict[StartupPhase, int] = field(default_factory=dict)
    
    # Intent and capability analysis
    most_common_intents: List[Tuple[UserIntent, int]] = field(default_factory=list)
    capability_gaps: List[Tuple[str, int]] = field(default_factory=list)  # (capability, request_count)
    
    # Conversion metrics
    user_retention_rate: float = 0.0  # % of users who stay through startup
    fallback_acceptance_rate: float = 0.0  # % of users who accept fallback responses
    retry_rate: float = 0.0  # % of requests that are retried


class UserExperienceLogger:
    """
    Comprehensive logger for user experience patterns during application startup.
    
    This logger tracks user request patterns, fallback usage, wait times, and
    provides analytics for optimizing the startup user experience.
    """
    
    def __init__(self, phase_manager: Optional[StartupPhaseManager] = None):
        """Initialize the user experience logger."""
        self.phase_manager = phase_manager
        self.startup_session_id = f"ux_startup_{int(time.time())}"
        self.startup_time = datetime.now()
        
        # Current tracking data
        self.active_sessions: Dict[str, UserSession] = {}
        self.request_patterns: List[UserRequestPattern] = []
        self.completed_sessions: List[UserSession] = []
        
        # Aggregated metrics
        self.current_metrics = StartupUXMetrics(
            startup_session_id=self.startup_session_id,
            startup_start_time=self.startup_time
        )
        
        # Request tracking
        self._active_requests: Dict[str, Dict[str, Any]] = {}
        self._user_request_counts: Dict[str, int] = defaultdict(int)
        self._user_last_request_times: Dict[str, datetime] = {}
        
        # Analytics state
        self._is_collecting = False
        self._collection_task: Optional[asyncio.Task] = None
        self._analytics_update_interval = 30.0  # Update analytics every 30 seconds
        
        # Configuration
        self.abandonment_timeout = 30.0  # Consider request abandoned after 30s
        self.session_timeout = 300.0  # Consider session ended after 5 minutes of inactivity
        
        logger.info(f"UserExperienceLogger initialized for startup session {self.startup_session_id}")
    
    async def start_logging(self) -> None:
        """Start logging user experience patterns."""
        if self._is_collecting:
            logger.warning("UX logging already started")
            return
        
        self._is_collecting = True
        logger.info("Starting user experience logging")
        
        # Start analytics collection task
        self._collection_task = asyncio.create_task(self._analytics_loop())
    
    async def stop_logging(self) -> None:
        """Stop logging and finalize metrics."""
        if not self._is_collecting:
            return
        
        self._is_collecting = False
        logger.info("Stopping user experience logging")
        
        # Cancel collection task
        if self._collection_task and not self._collection_task.done():
            self._collection_task.cancel()
            try:
                await self._collection_task
            except asyncio.CancelledError:
                pass
        
        # Finalize all active sessions
        await self._finalize_all_sessions()
        
        # Update final metrics
        await self._update_aggregated_metrics()
        
        self.current_metrics.startup_end_time = datetime.now()
        
        logger.info(f"UX logging stopped. Processed {len(self.request_patterns)} requests "
                   f"across {len(self.completed_sessions)} sessions")
    
    async def log_user_request_start(
        self,
        request_id: str,
        user_id: Optional[str] = None,
        session_id: Optional[str] = None,
        endpoint: str = "unknown",
        request_type: str = "unknown",
        user_message: Optional[str] = None,
        required_capabilities: Optional[List[str]] = None,
        user_agent: Optional[str] = None,
        ip_address: Optional[str] = None,
        referrer: Optional[str] = None
    ) -> None:
        """Log the start of a user request with detailed context."""
        if not self._is_collecting:
            return
        
        current_time = datetime.now()
        startup_elapsed = (current_time - self.startup_time).total_seconds()
        
        # Generate session ID if not provided
        if not session_id:
            session_id = f"session_{user_id or 'anon'}_{int(time.time())}"
        
        # Get current startup phase
        current_phase = self.phase_manager.current_phase if self.phase_manager else StartupPhase.MINIMAL
        
        # Analyze user intent if message provided
        detected_intent = None
        intent_confidence = 0.0
        if user_message:
            try:
                from ..services.fallback_service import get_fallback_service
                fallback_service = get_fallback_service()
                intent_analysis = fallback_service.analyze_user_intent(user_message)
                detected_intent = intent_analysis.primary_intent
                intent_confidence = intent_analysis.confidence
            except Exception as e:
                logger.debug(f"Failed to analyze user intent: {e}")
        
        # Get available capabilities
        available_capabilities = []
        if self.phase_manager:
            try:
                status = self.phase_manager.get_current_status()
                available_capabilities = [
                    model_name for model_name, model_status in status.model_statuses.items()
                    if model_status.status == "loaded"
                ]
            except Exception as e:
                logger.debug(f"Failed to get available capabilities: {e}")
        
        # Track user session
        await self._ensure_user_session(session_id, user_id, current_time)
        
        # Count previous requests for this user
        previous_requests = self._user_request_counts.get(user_id or session_id, 0)
        
        # Calculate time since last request
        time_since_last = None
        last_request_time = self._user_last_request_times.get(user_id or session_id)
        if last_request_time:
            time_since_last = (current_time - last_request_time).total_seconds()
        
        # Estimate system load
        concurrent_users = len(self.active_sessions)
        active_requests = len(self._active_requests)
        if active_requests > 10 or concurrent_users > 5:
            system_load = "high"
        elif active_requests > 5 or concurrent_users > 2:
            system_load = "medium"
        else:
            system_load = "low"
        
        # Store active request info
        self._active_requests[request_id] = {
            "start_time": current_time,
            "user_id": user_id,
            "session_id": session_id,
            "endpoint": endpoint,
            "request_type": request_type,
            "user_message": user_message,
            "detected_intent": detected_intent,
            "intent_confidence": intent_confidence,
            "required_capabilities": required_capabilities or [],
            "available_capabilities": available_capabilities,
            "startup_phase": current_phase,
            "startup_elapsed": startup_elapsed,
            "previous_requests": previous_requests,
            "time_since_last": time_since_last,
            "concurrent_users": concurrent_users,
            "system_load": system_load,
            "user_agent": user_agent,
            "ip_address": ip_address,
            "referrer": referrer
        }
        
        # Update user tracking
        self._user_request_counts[user_id or session_id] += 1
        self._user_last_request_times[user_id or session_id] = current_time
        
        logger.debug(f"Started tracking user request: {request_id} from {user_id or 'anonymous'} "
                    f"in phase {current_phase.value} (intent: {detected_intent})")
    
    async def log_user_request_completion(
        self,
        request_id: str,
        outcome: RequestOutcome,
        response_time_seconds: Optional[float] = None,
        fallback_used: bool = False,
        fallback_quality: Optional[CapabilityLevel] = None,
        fallback_response: Optional[str] = None,
        error_message: Optional[str] = None,
        error_type: Optional[str] = None,
        queue_position: Optional[int] = None,
        estimated_wait_time_seconds: Optional[float] = None
    ) -> None:
        """Log the completion of a user request."""
        if not self._is_collecting or request_id not in self._active_requests:
            return
        
        completion_time = datetime.now()
        request_info = self._active_requests[request_id]
        start_time = request_info["start_time"]
        
        # Calculate actual wait time
        actual_wait_time = (completion_time - start_time).total_seconds()
        
        # Determine abandonment reason if applicable
        abandonment_reason = None
        if outcome == RequestOutcome.ABANDONED:
            if actual_wait_time > self.abandonment_timeout:
                abandonment_reason = "timeout_exceeded"
            elif error_message:
                abandonment_reason = "error_encountered"
            else:
                abandonment_reason = "user_initiated"
        
        # Create request pattern record
        pattern = UserRequestPattern(
            request_id=request_id,
            user_id=request_info["user_id"],
            session_id=request_info["session_id"],
            timestamp=start_time,
            startup_phase=request_info["startup_phase"],
            startup_elapsed_seconds=request_info["startup_elapsed"],
            
            # Request details
            endpoint=request_info["endpoint"],
            request_type=request_info["request_type"],
            user_message=request_info["user_message"],
            detected_intent=request_info["detected_intent"],
            intent_confidence=request_info["intent_confidence"],
            required_capabilities=request_info["required_capabilities"],
            available_capabilities=request_info["available_capabilities"],
            
            # Response details
            response_time_seconds=response_time_seconds,
            outcome=outcome,
            fallback_used=fallback_used,
            fallback_quality=fallback_quality,
            fallback_response=fallback_response,
            
            # User experience metrics
            user_wait_time_seconds=actual_wait_time,
            estimated_wait_time_seconds=estimated_wait_time_seconds,
            queue_position=queue_position,
            retry_count=0,  # Will be updated if this is a retry
            abandonment_reason=abandonment_reason,
            
            # Context information
            previous_requests_count=request_info["previous_requests"],
            time_since_last_request_seconds=request_info["time_since_last"],
            concurrent_users=request_info["concurrent_users"],
            system_load_level=request_info["system_load"],
            
            # Error information
            error_message=error_message,
            error_type=error_type,
            
            # Metadata
            user_agent=request_info["user_agent"],
            ip_address=request_info["ip_address"],
            referrer=request_info["referrer"]
        )
        
        # Check if this is a retry of a previous request
        await self._detect_and_mark_retries(pattern)
        
        # Add to patterns list
        self.request_patterns.append(pattern)
        
        # Update user session
        await self._update_user_session(pattern)
        
        # Remove from active requests
        del self._active_requests[request_id]
        
        # Log completion
        outcome_text = outcome.value
        fallback_text = f" [FALLBACK: {fallback_quality.value}]" if fallback_used else ""
        wait_text = f" (waited {actual_wait_time:.1f}s)"
        phase_text = f" in {pattern.startup_phase.value} phase"
        
        logger.info(f"User request {outcome_text}: {request_id}{fallback_text}{wait_text}{phase_text}")
        
        # Send to log aggregator if available
        await self._send_to_aggregator(pattern)
    
    async def log_fallback_response_usage(
        self,
        request_id: str,
        fallback_response: FallbackResponse,
        user_acceptance: Optional[bool] = None,
        user_feedback: Optional[str] = None
    ) -> None:
        """Log detailed fallback response usage."""
        if not self._is_collecting:
            return
        
        # Find the corresponding request pattern
        pattern = None
        for p in self.request_patterns:
            if p.request_id == request_id:
                pattern = p
                break
        
        if not pattern:
            logger.warning(f"No request pattern found for fallback usage: {request_id}")
            return
        
        # Update pattern with fallback details
        pattern.fallback_response = fallback_response.response_text
        pattern.fallback_quality = fallback_response.response_quality
        
        # Log fallback usage details
        logger.info(f"Fallback response used for {request_id}: "
                   f"quality={fallback_response.response_quality.value}, "
                   f"helpful={fallback_response.helpful_now}, "
                   f"acceptance={user_acceptance}")
        
        # Track fallback effectiveness
        await self._track_fallback_effectiveness(pattern, fallback_response, user_acceptance, user_feedback)
    
    async def log_user_abandonment(
        self,
        user_id: Optional[str],
        session_id: str,
        abandonment_reason: str,
        context: Optional[Dict[str, Any]] = None
    ) -> None:
        """Log when a user abandons their session."""
        if not self._is_collecting:
            return
        
        current_time = datetime.now()
        
        # Update user session
        session = self.active_sessions.get(session_id)
        if session:
            session.end_time = current_time
            session.duration_seconds = (current_time - session.start_time).total_seconds()
            
            # Mark any active requests as abandoned
            abandoned_requests = []
            for request_id, request_info in list(self._active_requests.items()):
                if request_info["session_id"] == session_id:
                    await self.log_user_request_completion(
                        request_id=request_id,
                        outcome=RequestOutcome.ABANDONED,
                        response_time_seconds=None
                    )
                    abandoned_requests.append(request_id)
            
            logger.info(f"User session abandoned: {session_id} (reason: {abandonment_reason}, "
                       f"duration: {session.duration_seconds:.1f}s, "
                       f"abandoned_requests: {len(abandoned_requests)})")
            
            # Move to completed sessions
            self.completed_sessions.append(session)
            del self.active_sessions[session_id]
    
    async def _ensure_user_session(self, session_id: str, user_id: Optional[str], current_time: datetime) -> None:
        """Ensure a user session exists and is being tracked."""
        if session_id not in self.active_sessions:
            session = UserSession(
                session_id=session_id,
                user_id=user_id,
                start_time=current_time
            )
            self.active_sessions[session_id] = session
            
            # Add current startup phase to phases experienced
            if self.phase_manager:
                session.phases_experienced.add(self.phase_manager.current_phase)
            
            logger.debug(f"Started tracking user session: {session_id}")
    
    async def _update_user_session(self, pattern: UserRequestPattern) -> None:
        """Update user session with request pattern information."""
        session = self.active_sessions.get(pattern.session_id)
        if not session:
            return
        
        # Update request counts
        session.total_requests += 1
        
        if pattern.outcome == RequestOutcome.SUCCESS:
            session.successful_requests += 1
        elif pattern.outcome == RequestOutcome.FALLBACK_USED:
            session.fallback_requests += 1
        elif pattern.outcome == RequestOutcome.ABANDONED:
            session.abandoned_requests += 1
        elif pattern.outcome == RequestOutcome.ERROR:
            session.error_requests += 1
        
        # Update timing metrics
        if pattern.user_wait_time_seconds:
            session.total_wait_time_seconds += pattern.user_wait_time_seconds
            
            if session.average_wait_time_seconds is None:
                session.average_wait_time_seconds = pattern.user_wait_time_seconds
            else:
                # Running average
                total_requests = session.successful_requests + session.fallback_requests
                if total_requests > 0:
                    session.average_wait_time_seconds = session.total_wait_time_seconds / total_requests
            
            if session.max_wait_time_seconds is None or pattern.user_wait_time_seconds > session.max_wait_time_seconds:
                session.max_wait_time_seconds = pattern.user_wait_time_seconds
        
        # Track request types and intents
        session.request_types_used.add(pattern.request_type)
        if pattern.detected_intent:
            session.intents_detected.add(pattern.detected_intent)
        
        # Track phases experienced
        session.phases_experienced.add(pattern.startup_phase)
        
        # Update behavior analysis
        await self._analyze_user_behavior(session, pattern)
    
    async def _analyze_user_behavior(self, session: UserSession, latest_pattern: UserRequestPattern) -> None:
        """Analyze and update user behavior patterns."""
        # Calculate patience score (0-100)
        patience_factors = []
        
        # Factor 1: Average wait time tolerance
        if session.average_wait_time_seconds:
            if session.average_wait_time_seconds > 60:
                patience_factors.append(90)  # Very patient
            elif session.average_wait_time_seconds > 30:
                patience_factors.append(70)  # Moderately patient
            elif session.average_wait_time_seconds > 10:
                patience_factors.append(50)  # Somewhat patient
            else:
                patience_factors.append(30)  # Impatient
        
        # Factor 2: Abandonment rate
        if session.total_requests > 0:
            abandonment_rate = session.abandoned_requests / session.total_requests
            patience_factors.append(max(0, 100 - (abandonment_rate * 100)))
        
        # Factor 3: Fallback acceptance
        if session.total_requests > 0:
            fallback_rate = session.fallback_requests / session.total_requests
            if fallback_rate > 0.7:
                patience_factors.append(80)  # Accepts fallbacks well
            elif fallback_rate > 0.3:
                patience_factors.append(60)  # Sometimes accepts fallbacks
            else:
                patience_factors.append(40)  # Prefers full responses
        
        if patience_factors:
            session.patience_score = statistics.mean(patience_factors)
        
        # Calculate engagement score (0-100)
        engagement_factors = []
        
        # Factor 1: Request frequency
        if session.start_time:
            session_duration = (datetime.now() - session.start_time).total_seconds()
            if session_duration > 0:
                request_rate = session.total_requests / (session_duration / 60)  # requests per minute
                if request_rate > 2:
                    engagement_factors.append(90)  # Highly engaged
                elif request_rate > 1:
                    engagement_factors.append(70)  # Moderately engaged
                elif request_rate > 0.5:
                    engagement_factors.append(50)  # Somewhat engaged
                else:
                    engagement_factors.append(30)  # Low engagement
        
        # Factor 2: Request type diversity
        diversity_score = len(session.request_types_used) * 20  # Up to 100 for 5+ types
        engagement_factors.append(min(100, diversity_score))
        
        # Factor 3: Phase persistence (staying through phases)
        phase_persistence = len(session.phases_experienced) * 33  # Up to 100 for all 3 phases
        engagement_factors.append(min(100, phase_persistence))
        
        if engagement_factors:
            session.engagement_score = statistics.mean(engagement_factors)
        
        # Calculate satisfaction score (0-100)
        satisfaction_factors = []
        
        # Factor 1: Success rate
        if session.total_requests > 0:
            success_rate = (session.successful_requests + session.fallback_requests) / session.total_requests
            satisfaction_factors.append(success_rate * 100)
        
        # Factor 2: Error rate (inverse)
        if session.total_requests > 0:
            error_rate = session.error_requests / session.total_requests
            satisfaction_factors.append(max(0, 100 - (error_rate * 100)))
        
        # Factor 3: Wait time satisfaction
        if session.average_wait_time_seconds:
            if session.average_wait_time_seconds < 5:
                satisfaction_factors.append(100)  # Excellent
            elif session.average_wait_time_seconds < 15:
                satisfaction_factors.append(80)   # Good
            elif session.average_wait_time_seconds < 30:
                satisfaction_factors.append(60)   # Acceptable
            else:
                satisfaction_factors.append(30)   # Poor
        
        if satisfaction_factors:
            session.satisfaction_score = statistics.mean(satisfaction_factors)
        
        # Determine behavior pattern
        session.behavior_pattern = self._classify_behavior_pattern(session)
    
    def _classify_behavior_pattern(self, session: UserSession) -> UserBehaviorPattern:
        """Classify user behavior pattern based on session data."""
        # Patient waiter: High patience, low abandonment
        if session.patience_score > 70 and session.abandoned_requests == 0:
            return UserBehaviorPattern.PATIENT_WAITER
        
        # Impatient abandoner: Low patience, high abandonment
        if session.patience_score < 40 and session.abandoned_requests > session.successful_requests:
            return UserBehaviorPattern.IMPATIENT_ABANDONER
        
        # Fallback accepter: High fallback usage, good satisfaction
        if (session.total_requests > 0 and 
            session.fallback_requests / session.total_requests > 0.5 and 
            session.satisfaction_score > 60):
            return UserBehaviorPattern.FALLBACK_ACCEPTER
        
        # Retry persistent: Multiple requests of same type
        request_type_counts = Counter()
        for pattern in self.request_patterns:
            if pattern.session_id == session.session_id:
                request_type_counts[pattern.request_type] += 1
        
        if any(count > 2 for count in request_type_counts.values()):
            return UserBehaviorPattern.RETRY_PERSISTENT
        
        # Explorer: High diversity in request types
        if len(session.request_types_used) > 3:
            return UserBehaviorPattern.EXPLORER
        
        # Status checker: Frequent status-related requests
        status_requests = sum(1 for pattern in self.request_patterns 
                            if pattern.session_id == session.session_id and 
                            pattern.request_type in ["health", "status", "capabilities"])
        if status_requests > 2:
            return UserBehaviorPattern.STATUS_CHECKER
        
        # Default to patient waiter
        return UserBehaviorPattern.PATIENT_WAITER
    
    async def _detect_and_mark_retries(self, pattern: UserRequestPattern) -> None:
        """Detect if this request is a retry and mark it accordingly."""
        # Look for similar requests from the same user/session
        similar_requests = [
            p for p in self.request_patterns
            if (p.user_id == pattern.user_id or p.session_id == pattern.session_id) and
            p.request_type == pattern.request_type and
            p.detected_intent == pattern.detected_intent and
            (pattern.timestamp - p.timestamp).total_seconds() < 300  # Within 5 minutes
        ]
        
        if similar_requests:
            pattern.retry_count = len(similar_requests)
            logger.debug(f"Detected retry #{pattern.retry_count} for request {pattern.request_id}")
    
    async def _track_fallback_effectiveness(
        self,
        pattern: UserRequestPattern,
        fallback_response: FallbackResponse,
        user_acceptance: Optional[bool],
        user_feedback: Optional[str]
    ) -> None:
        """Track the effectiveness of fallback responses."""
        # This could be expanded to include more sophisticated tracking
        # For now, just log the information
        effectiveness_data = {
            "request_id": pattern.request_id,
            "fallback_quality": fallback_response.response_quality.value,
            "helpful_now": fallback_response.helpful_now,
            "user_acceptance": user_acceptance,
            "user_feedback": user_feedback,
            "estimated_ready_time": fallback_response.estimated_full_ready_time,
            "limitations_count": len(fallback_response.limitations),
            "alternatives_count": len(fallback_response.available_alternatives)
        }
        
        logger.debug(f"Fallback effectiveness data: {json.dumps(effectiveness_data, default=str)}")
    
    async def _analytics_loop(self) -> None:
        """Main analytics loop that updates metrics periodically."""
        try:
            while self._is_collecting:
                await self._update_aggregated_metrics()
                await self._cleanup_expired_sessions()
                await asyncio.sleep(self._analytics_update_interval)
        except asyncio.CancelledError:
            logger.info("Analytics loop cancelled")
            raise
        except Exception as e:
            logger.error(f"Error in analytics loop: {e}")
    
    async def _update_aggregated_metrics(self) -> None:
        """Update aggregated UX metrics."""
        # Count totals
        self.current_metrics.total_users = len(set(
            p.user_id for p in self.request_patterns if p.user_id
        )) + len(set(
            p.session_id for p in self.request_patterns if not p.user_id
        ))
        
        self.current_metrics.total_requests = len(self.request_patterns)
        self.current_metrics.total_sessions = len(self.active_sessions) + len(self.completed_sessions)
        
        # Count outcomes
        outcome_counts = Counter(p.outcome for p in self.request_patterns)
        self.current_metrics.successful_requests = outcome_counts[RequestOutcome.SUCCESS]
        self.current_metrics.fallback_requests = outcome_counts[RequestOutcome.FALLBACK_USED]
        self.current_metrics.abandoned_requests = outcome_counts[RequestOutcome.ABANDONED]
        self.current_metrics.error_requests = outcome_counts[RequestOutcome.ERROR]
        self.current_metrics.timeout_requests = outcome_counts[RequestOutcome.TIMEOUT]
        
        # Calculate timing metrics
        wait_times = [p.user_wait_time_seconds for p in self.request_patterns if p.user_wait_time_seconds]
        if wait_times:
            self.current_metrics.average_user_wait_time = statistics.mean(wait_times)
            self.current_metrics.median_user_wait_time = statistics.median(wait_times)
            self.current_metrics.p95_user_wait_time = self._calculate_percentile(wait_times, 95)
        
        # Calculate behavior pattern distribution
        all_sessions = list(self.active_sessions.values()) + self.completed_sessions
        behavior_counts = Counter(s.behavior_pattern for s in all_sessions if s.behavior_pattern)
        self.current_metrics.behavior_pattern_distribution = dict(behavior_counts)
        
        # Calculate average scores
        if all_sessions:
            self.current_metrics.average_patience_score = statistics.mean(
                s.patience_score for s in all_sessions if s.patience_score > 0
            ) if any(s.patience_score > 0 for s in all_sessions) else 0.0
            
            self.current_metrics.average_engagement_score = statistics.mean(
                s.engagement_score for s in all_sessions if s.engagement_score > 0
            ) if any(s.engagement_score > 0 for s in all_sessions) else 0.0
            
            self.current_metrics.average_satisfaction_score = statistics.mean(
                s.satisfaction_score for s in all_sessions if s.satisfaction_score > 0
            ) if any(s.satisfaction_score > 0 for s in all_sessions) else 0.0
        
        # Calculate phase-specific metrics
        phase_counts = Counter(p.startup_phase for p in self.request_patterns)
        self.current_metrics.requests_by_phase = dict(phase_counts)
        
        fallback_by_phase = Counter(
            p.startup_phase for p in self.request_patterns if p.fallback_used
        )
        self.current_metrics.fallback_usage_by_phase = dict(fallback_by_phase)
        
        abandonment_by_phase = Counter(
            p.startup_phase for p in self.request_patterns if p.outcome == RequestOutcome.ABANDONED
        )
        self.current_metrics.abandonment_by_phase = dict(abandonment_by_phase)
        
        # Calculate intent analysis
        intent_counts = Counter(
            p.detected_intent for p in self.request_patterns if p.detected_intent
        )
        self.current_metrics.most_common_intents = intent_counts.most_common(10)
        
        # Calculate capability gaps
        capability_gap_counts = defaultdict(int)
        for pattern in self.request_patterns:
            missing_capabilities = set(pattern.required_capabilities) - set(pattern.available_capabilities)
            for capability in missing_capabilities:
                capability_gap_counts[capability] += 1
        
        self.current_metrics.capability_gaps = sorted(
            capability_gap_counts.items(), key=lambda x: x[1], reverse=True
        )[:10]
        
        # Calculate conversion metrics
        if self.current_metrics.total_sessions > 0:
            completed_sessions = [s for s in all_sessions if s.end_time is not None]
            successful_sessions = [s for s in completed_sessions if s.successful_requests > 0]
            
            self.current_metrics.user_retention_rate = (
                len(successful_sessions) / len(completed_sessions) * 100
                if completed_sessions else 0.0
            )
        
        if self.current_metrics.total_requests > 0:
            self.current_metrics.fallback_acceptance_rate = (
                self.current_metrics.fallback_requests / self.current_metrics.total_requests * 100
            )
            
            retry_requests = sum(1 for p in self.request_patterns if p.retry_count > 0)
            self.current_metrics.retry_rate = retry_requests / self.current_metrics.total_requests * 100
    
    def _calculate_percentile(self, values: List[float], percentile: int) -> float:
        """Calculate the specified percentile of a list of values."""
        if not values:
            return 0.0
        
        sorted_values = sorted(values)
        index = (percentile / 100) * (len(sorted_values) - 1)
        
        if index.is_integer():
            return sorted_values[int(index)]
        else:
            lower_index = int(index)
            upper_index = lower_index + 1
            weight = index - lower_index
            
            if upper_index >= len(sorted_values):
                return sorted_values[lower_index]
            
            return sorted_values[lower_index] * (1 - weight) + sorted_values[upper_index] * weight
    
    async def _cleanup_expired_sessions(self) -> None:
        """Clean up sessions that have been inactive for too long."""
        current_time = datetime.now()
        expired_sessions = []
        
        for session_id, session in list(self.active_sessions.items()):
            # Check if session has been inactive
            last_activity = session.start_time
            
            # Find the most recent request for this session
            for pattern in reversed(self.request_patterns):
                if pattern.session_id == session_id:
                    last_activity = pattern.timestamp
                    break
            
            # Check if session has expired
            if (current_time - last_activity).total_seconds() > self.session_timeout:
                expired_sessions.append(session_id)
        
        # Move expired sessions to completed
        for session_id in expired_sessions:
            session = self.active_sessions[session_id]
            session.end_time = current_time
            session.duration_seconds = (current_time - session.start_time).total_seconds()
            
            self.completed_sessions.append(session)
            del self.active_sessions[session_id]
            
            logger.debug(f"Expired inactive session: {session_id}")
    
    async def _finalize_all_sessions(self) -> None:
        """Finalize all active sessions."""
        current_time = datetime.now()
        
        for session in self.active_sessions.values():
            session.end_time = current_time
            session.duration_seconds = (current_time - session.start_time).total_seconds()
            self.completed_sessions.append(session)
        
        self.active_sessions.clear()
    
    async def _send_to_aggregator(self, pattern: UserRequestPattern) -> None:
        """Send request pattern to log aggregator if available."""
        try:
            from ..logging.log_aggregator import get_log_aggregator, add_log_entry
            from ..logging.startup_logger import StartupLogEntry, LogLevel
            
            aggregator = get_log_aggregator()
            if aggregator:
                # Convert pattern to log entry
                log_entry = StartupLogEntry(
                    timestamp=pattern.timestamp.isoformat(),
                    level=LogLevel.INFO.value,
                    event_type="user_request_pattern",
                    phase=pattern.startup_phase.value,
                    message=f"User request: {pattern.request_type} -> {pattern.outcome.value}",
                    metadata=asdict(pattern)
                )
                add_log_entry(log_entry)
        except ImportError:
            pass  # Log aggregator not available
        except Exception as e:
            logger.debug(f"Failed to send pattern to aggregator: {str(e)}")
    
    def get_ux_summary(self) -> Dict[str, Any]:
        """Get a comprehensive summary of user experience metrics."""
        return {
            "startup_session_id": self.startup_session_id,
            "startup_duration_seconds": (datetime.now() - self.startup_time).total_seconds(),
            "current_metrics": asdict(self.current_metrics),
            "active_sessions": len(self.active_sessions),
            "completed_sessions": len(self.completed_sessions),
            "total_patterns_logged": len(self.request_patterns),
            "active_requests": len(self._active_requests)
        }
    
    def export_patterns(self, format_type: str = "json") -> str:
        """Export all user request patterns in the specified format."""
        if format_type == "json":
            return json.dumps([asdict(p) for p in self.request_patterns], indent=2, default=str)
        elif format_type == "csv":
            # Basic CSV export - could be enhanced
            import csv
            import io
            
            output = io.StringIO()
            if self.request_patterns:
                writer = csv.DictWriter(output, fieldnames=asdict(self.request_patterns[0]).keys())
                writer.writeheader()
                for pattern in self.request_patterns:
                    writer.writerow(asdict(pattern))
            
            return output.getvalue()
        else:
            raise ValueError(f"Unsupported format type: {format_type}")


# Global user experience logger instance
_ux_logger: Optional[UserExperienceLogger] = None


def get_ux_logger() -> Optional[UserExperienceLogger]:
    """Get the global user experience logger instance."""
    return _ux_logger


def initialize_ux_logger(phase_manager: Optional[StartupPhaseManager] = None) -> UserExperienceLogger:
    """Initialize the global user experience logger."""
    global _ux_logger
    _ux_logger = UserExperienceLogger(phase_manager)
    return _ux_logger


# Convenience functions for logging user request patterns
async def log_user_request_start(
    request_id: str,
    user_id: Optional[str] = None,
    session_id: Optional[str] = None,
    endpoint: str = "unknown",
    request_type: str = "unknown",
    user_message: Optional[str] = None,
    required_capabilities: Optional[List[str]] = None,
    user_agent: Optional[str] = None,
    ip_address: Optional[str] = None,
    referrer: Optional[str] = None
) -> None:
    """Convenience function to log user request start."""
    if _ux_logger:
        await _ux_logger.log_user_request_start(
            request_id=request_id,
            user_id=user_id,
            session_id=session_id,
            endpoint=endpoint,
            request_type=request_type,
            user_message=user_message,
            required_capabilities=required_capabilities,
            user_agent=user_agent,
            ip_address=ip_address,
            referrer=referrer
        )


async def log_user_request_completion(
    request_id: str,
    outcome: RequestOutcome,
    response_time_seconds: Optional[float] = None,
    fallback_used: bool = False,
    fallback_quality: Optional[CapabilityLevel] = None,
    fallback_response: Optional[str] = None,
    error_message: Optional[str] = None,
    error_type: Optional[str] = None,
    queue_position: Optional[int] = None,
    estimated_wait_time_seconds: Optional[float] = None
) -> None:
    """Convenience function to log user request completion."""
    if _ux_logger:
        await _ux_logger.log_user_request_completion(
            request_id=request_id,
            outcome=outcome,
            response_time_seconds=response_time_seconds,
            fallback_used=fallback_used,
            fallback_quality=fallback_quality,
            fallback_response=fallback_response,
            error_message=error_message,
            error_type=error_type,
            queue_position=queue_position,
            estimated_wait_time_seconds=estimated_wait_time_seconds
        )


async def log_fallback_response_usage(
    request_id: str,
    fallback_response: FallbackResponse,
    user_acceptance: Optional[bool] = None,
    user_feedback: Optional[str] = None
) -> None:
    """Convenience function to log fallback response usage."""
    if _ux_logger:
        await _ux_logger.log_fallback_response_usage(
            request_id=request_id,
            fallback_response=fallback_response,
            user_acceptance=user_acceptance,
            user_feedback=user_feedback
        )


async def log_user_abandonment(
    user_id: Optional[str],
    session_id: str,
    abandonment_reason: str,
    context: Optional[Dict[str, Any]] = None
) -> None:
    """Convenience function to log user abandonment."""
    if _ux_logger:
        await _ux_logger.log_user_abandonment(
            user_id=user_id,
            session_id=session_id,
            abandonment_reason=abandonment_reason,
            context=context
        )