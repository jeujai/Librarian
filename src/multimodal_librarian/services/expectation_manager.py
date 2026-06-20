"""
Expectation Manager Service

This service manages user expectations during system startup and loading phases.
It provides clear communication about current limitations, estimated wait times,
and what users can expect at different capability levels.

Key Features:
- Clear expectation setting
- Realistic time estimates
- Capability-based messaging
- User experience optimization
- Progressive disclosure of features
"""

import time
import logging
from typing import Dict, Any, List, Optional, Tuple
from datetime import datetime, timedelta
from dataclasses import dataclass
from enum import Enum

from ..services.capability_service import get_capability_service, CapabilityLevel
from ..services.fallback_service import get_fallback_service, UserIntent, FallbackResponse
from ..startup.minimal_server import get_minimal_server
from ..logging_config import get_logger

logger = get_logger("expectation_manager")


class ExpectationLevel(Enum):
    """Levels of user expectations to manage."""
    IMMEDIATE = "immediate"        # User expects instant response
    SHORT_WAIT = "short_wait"      # User can wait 30-60 seconds
    MEDIUM_WAIT = "medium_wait"    # User can wait 2-5 minutes
    LONG_WAIT = "long_wait"        # User willing to wait longer


@dataclass
class ExpectationResponse:
    """Response with managed expectations."""
    primary_message: str
    expectation_message: str
    timeline_message: str
    capability_explanation: str
    next_steps: List[str]
    patience_level_appropriate: bool
    should_queue_request: bool
    alternative_suggestions: List[str]
    progress_indicators: Dict[str, Any]


class OperatingMode(Enum):
    """System operating modes."""
    FULL = "full"
    DEGRADED = "degraded"
    STARTUP = "startup"
    MAINTENANCE = "maintenance"


class QualityLevel(Enum):
    """Quality levels for indicators."""
    OPTIMAL = "optimal"
    GOOD = "good"
    BASIC = "basic"
    LIMITED = "limited"


@dataclass
class QualityIndicator:
    """Quality indicator for UI display."""
    symbol: str
    level: QualityLevel
    description: str
    user_message: str
    color_code: str


@dataclass
class ExpectationContext:
    """Context object for capabilities endpoint."""
    current_mode: OperatingMode
    quality_indicator: QualityIndicator
    available_capabilities: List[str]
    loading_capabilities: List[str]
    estimated_times: Dict[str, Any]
    progress_percentage: float
    upgrade_message: str
    limitations: List[str]
    alternatives: List[str]


class ExpectationManager:
    """Service for managing user expectations during startup and loading."""
    
    def __init__(self):
        self.capability_service = get_capability_service()
        self.fallback_service = get_fallback_service()
    
    def assess_user_patience(
        self, 
        user_message: str, 
        request_intent: UserIntent,
        previous_interactions: int = 0
    ) -> ExpectationLevel:
        """Assess user's likely patience level based on their request."""
        message_lower = user_message.lower()
        
        # Immediate expectation indicators
        immediate_indicators = [
            "quick", "fast", "now", "immediately", "urgent", "asap",
            "right now", "instantly", "real-time"
        ]
        
        # Long wait tolerance indicators
        patient_indicators = [
            "when ready", "take your time", "no rush", "whenever",
            "complex", "detailed", "comprehensive", "thorough"
        ]
        
        # Check for immediate expectation
        if any(indicator in message_lower for indicator in immediate_indicators):
            return ExpectationLevel.IMMEDIATE
        
        # Check for patience indicators
        if any(indicator in message_lower for indicator in patient_indicators):
            return ExpectationLevel.LONG_WAIT
        
        # Intent-based assessment
        if request_intent in [UserIntent.SYSTEM_STATUS, UserIntent.CONVERSATION]:
            return ExpectationLevel.IMMEDIATE
        elif request_intent in [UserIntent.COMPLEX_ANALYSIS, UserIntent.DOCUMENT_PROCESSING]:
            return ExpectationLevel.MEDIUM_WAIT
        elif request_intent == UserIntent.CREATIVE_TASK:
            return ExpectationLevel.LONG_WAIT
        
        # Adjust based on previous interactions
        if previous_interactions > 3:
            # User has been waiting, likely getting impatient
            return ExpectationLevel.IMMEDIATE
        elif previous_interactions > 1:
            return ExpectationLevel.SHORT_WAIT
        
        # Default to short wait
        return ExpectationLevel.SHORT_WAIT
    
    def get_expectation_context(self) -> ExpectationContext:
        """Get current expectation context for the capabilities endpoint."""
        try:
            capabilities = self.capability_service.get_capability_summary()
            current_level = capabilities.get("overall", {}).get("current_level", "startup")
            progress = self.capability_service.get_loading_progress()
            progress_pct = float(progress.get("overall_progress", 0))

            if progress_pct >= 100:
                mode = OperatingMode.FULL
                indicator = QualityIndicator(
                    symbol="✓",
                    level=QualityLevel.OPTIMAL,
                    description="All systems operational",
                    user_message="Full capabilities available",
                    color_code="#22C55E"
                )
                limitations = []
                alternatives = []
                upgrade_message = "All capabilities loaded"
            elif progress_pct >= 70:
                mode = OperatingMode.DEGRADED
                indicator = QualityIndicator(
                    symbol="~",
                    level=QualityLevel.GOOD,
                    description="Most systems operational",
                    user_message="Most capabilities available, some loading",
                    color_code="#3B82F6"
                )
                limitations = ["Advanced analysis may be slower"]
                alternatives = ["Basic features are fully available"]
                upgrade_message = "Loading advanced features"
            elif progress_pct >= 30:
                mode = OperatingMode.STARTUP
                indicator = QualityIndicator(
                    symbol="⚡",
                    level=QualityLevel.BASIC,
                    description="System starting up",
                    user_message="Basic capabilities available, more loading",
                    color_code="#F59E0B"
                )
                limitations = ["Knowledge graph", "Full document analysis"]
                alternatives = ["Basic chat is available", "Simple document queries"]
                upgrade_message = "Loading core features — please wait"
            else:
                mode = OperatingMode.STARTUP
                indicator = QualityIndicator(
                    symbol="⚡",
                    level=QualityLevel.LIMITED,
                    description="System initializing",
                    user_message="System starting up — limited features",
                    color_code="#EF4444"
                )
                limitations = ["Most features are loading"]
                alternatives = ["Try again in a moment"]
                upgrade_message = "System starting up"

            available = capabilities.get("available", ["basic_chat"])
            if isinstance(available, str):
                available = [available]
            loading = capabilities.get("loading", ["rag", "kg_search"])
            if isinstance(loading, str):
                loading = [loading]
            eta_info = self._get_eta_information()

            return ExpectationContext(
                current_mode=mode,
                quality_indicator=indicator,
                available_capabilities=available,
                loading_capabilities=loading,
                estimated_times={"full_capabilities": eta_info.get("eta_seconds", 60)},
                progress_percentage=progress_pct,
                upgrade_message=upgrade_message,
                limitations=limitations,
                alternatives=alternatives,
            )
        except Exception as e:
            logger.error(f"Error building expectation context: {e}")
            return ExpectationContext(
                current_mode=OperatingMode.STARTUP,
                quality_indicator=QualityIndicator(
                    symbol="⚡",
                    level=QualityLevel.BASIC,
                    description="Basic mode",
                    user_message="System starting up",
                    color_code="#FFA500",
                ),
                available_capabilities=["simple_text"],
                loading_capabilities=["basic_chat", "document_analysis"],
                estimated_times={"full_capabilities": 120},
                progress_percentage=10.0,
                upgrade_message="System loading — please wait",
                limitations=["Most features loading"],
                alternatives=["Try again in a moment"],
            )

    def manage_expectations(
        self, 
        user_message: str,
        current_capabilities: Optional[List[str]] = None,
        missing_capabilities: Optional[List[str]] = None,
        previous_interactions: int = 0
    ) -> ExpectationResponse:
        """Generate expectation management response."""
        try:
            # Analyze the request
            request_intent = self.fallback_service.analyze_intent(user_message)
            
            # Get current system state
            capabilities = self.capability_service.get_capability_summary()
            current_level = capabilities["overall"]["current_level"]
            
            # Assess user patience
            patience_level = self.assess_user_patience(
                user_message, request_intent, previous_interactions
            )
            
            # Get ETA information
            eta_info = self._get_eta_information()
            eta_seconds = eta_info.get("eta_seconds", 60)
            
            # Generate response
            return ExpectationResponse(
                primary_message=f"I'm currently in {current_level} mode with some capabilities available.",
                expectation_message="Enhanced features are loading in the background.",
                timeline_message=f"Full capabilities will be ready in {self._format_eta_description(eta_seconds)}.",
                capability_explanation=f"Currently available: {current_level} features.",
                next_steps=["Try available features now", "Wait for full capabilities"],
                patience_level_appropriate=eta_seconds <= 120,
                should_queue_request=patience_level in [ExpectationLevel.MEDIUM_WAIT, ExpectationLevel.LONG_WAIT],
                alternative_suggestions=["Use basic features", "Check progress"],
                progress_indicators={"eta_seconds": eta_seconds, "current_level": current_level}
            )
            
        except Exception as e:
            logger.error(f"Error managing expectations: {e}")
            return self._generate_default_expectation_response()
    
    def _get_eta_information(self) -> Dict[str, Any]:
        """Get ETA information for capabilities."""
        try:
            progress = self.capability_service.get_loading_progress()
            return {
                "eta_seconds": self._extract_eta_seconds(progress),
                "progress_percent": progress.get("overall_progress", 0)
            }
        except Exception as e:
            logger.error(f"Error getting ETA: {e}")
            return {"eta_seconds": 60, "progress_percent": 0}
    
    def _extract_eta_seconds(self, progress: Dict[str, Any]) -> int:
        """Extract ETA seconds from progress information."""
        completion = progress.get("estimated_completion")
        if completion:
            try:
                completion_time = datetime.fromisoformat(completion.replace('Z', '+00:00'))
                now = datetime.now(completion_time.tzinfo)
                return max(0, int((completion_time - now).total_seconds()))
            except Exception:
                pass
        
        # Fallback estimation based on overall progress
        progress_percent = progress.get("overall_progress", 0)
        if progress_percent >= 90:
            return 30
        elif progress_percent >= 50:
            return 120
        else:
            return 300
    
    def _format_eta_description(self, eta_seconds: Optional[int]) -> str:
        """Format ETA into user-friendly description."""
        if not eta_seconds or eta_seconds <= 0:
            return "Ready now"
        elif eta_seconds <= 30:
            return "Ready in seconds"
        elif eta_seconds <= 60:
            return "Ready in about 1 minute"
        elif eta_seconds <= 120:
            return "Ready in about 2 minutes"
        elif eta_seconds <= 300:
            return f"Ready in about {eta_seconds // 60} minutes"
        else:
            return "Ready soon"
    
    def _generate_default_expectation_response(self) -> ExpectationResponse:
        """Generate default expectation response for error cases."""
        return ExpectationResponse(
            primary_message="I'm currently starting up and loading my capabilities.",
            expectation_message="Please wait a moment while I get ready to help you.",
            timeline_message="Full capabilities will be available shortly.",
            capability_explanation="Basic features are available now, with more coming online.",
            next_steps=["Wait for startup to complete", "Try basic requests"],
            patience_level_appropriate=True,
            should_queue_request=False,
            alternative_suggestions=["Ask simple questions", "Check system status"],
            progress_indicators={"overall_progress": 0, "eta_description": "Loading..."}
        )
    
    def create_expectation_aware_response(
        self,
        user_message: str,
        base_response: Dict[str, Any],
        previous_interactions: int = 0
    ) -> Dict[str, Any]:
        """Enhance a response with expectation management."""
        try:
            expectation_response = self.manage_expectations(
                user_message=user_message,
                previous_interactions=previous_interactions
            )
            
            # Enhance base response with expectation management
            enhanced_response = {
                **base_response,
                "expectation_management": {
                    "primary_message": expectation_response.primary_message,
                    "expectation_message": expectation_response.expectation_message,
                    "timeline_message": expectation_response.timeline_message,
                    "capability_explanation": expectation_response.capability_explanation,
                    "next_steps": expectation_response.next_steps,
                    "alternatives": expectation_response.alternative_suggestions,
                    "progress_indicators": expectation_response.progress_indicators,
                    "should_queue": expectation_response.should_queue_request,
                    "patience_appropriate": expectation_response.patience_level_appropriate
                },
                "user_guidance": {
                    "recommended_action": (
                        "queue_request" if expectation_response.should_queue_request
                        else "try_now" if expectation_response.patience_level_appropriate
                        else "simplify_request"
                    ),
                    "expectation_level": "appropriate" if expectation_response.patience_level_appropriate else "needs_adjustment"
                }
            }
            
            return enhanced_response
            
        except Exception as e:
            logger.error(f"Error creating expectation-aware response: {e}")
            return base_response


# Global expectation manager instance
_expectation_manager = None

def get_expectation_manager() -> ExpectationManager:
    """Get the global expectation manager instance."""
    global _expectation_manager
    if _expectation_manager is None:
        _expectation_manager = ExpectationManager()
    return _expectation_manager