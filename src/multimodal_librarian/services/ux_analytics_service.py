"""
User Experience Analytics Service

This service provides comprehensive analytics and insights for user experience
during application startup phases. It analyzes patterns from the UX logger
and provides actionable insights for improving startup user experience.

Key Features:
- User behavior pattern analysis
- Startup phase performance insights
- Abandonment prediction and analysis
- Fallback response effectiveness metrics
- User satisfaction scoring
- Actionable recommendations for UX improvements
"""

import asyncio
import logging
import statistics
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Tuple, Set
from dataclasses import dataclass, asdict
from collections import defaultdict, Counter
from enum import Enum

from ..logging.ux_logger import (
    UserExperienceLogger, get_ux_logger, UserRequestPattern, UserSession,
    RequestOutcome, UserBehaviorPattern, StartupUXMetrics
)
from ..startup.phase_manager import StartupPhase
from ..services.capability_service import CapabilityLevel

logger = logging.getLogger(__name__)


class AnalyticsInsightType(Enum):
    """Types of analytics insights."""
    PERFORMANCE = "performance"
    BEHAVIOR = "behavior"
    SATISFACTION = "satisfaction"
    ABANDONMENT = "abandonment"
    FALLBACK = "fallback"
    RECOMMENDATION = "recommendation"


class InsightSeverity(Enum):
    """Severity levels for insights."""
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"


@dataclass
class AnalyticsInsight:
    """A single analytics insight with actionable information."""
    insight_type: AnalyticsInsightType
    severity: InsightSeverity
    title: str
    description: str
    metric_value: Optional[float] = None
    metric_unit: Optional[str] = None
    recommendation: Optional[str] = None
    impact_score: float = 0.0  # 0-100, higher = more impactful
    confidence: float = 0.0  # 0-100, higher = more confident
    supporting_data: Dict[str, Any] = None
    timestamp: datetime = None
    
    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = datetime.now()
        if self.supporting_data is None:
            self.supporting_data = {}


@dataclass
class UserJourneyAnalysis:
    """Analysis of a user's journey through startup phases."""
    user_id: str
    session_id: str
    journey_start: datetime
    journey_end: Optional[datetime]
    phases_experienced: List[StartupPhase]
    total_requests: int
    successful_requests: int
    abandoned_requests: int
    fallback_requests: int
    
    # Journey metrics
    total_wait_time: float
    average_wait_time: float
    max_wait_time: float
    patience_score: float
    satisfaction_score: float
    engagement_score: float
    
    # Journey outcome
    journey_completed: bool
    abandonment_reason: Optional[str]
    final_behavior_pattern: Optional[UserBehaviorPattern]
    
    # Journey insights
    pain_points: List[str]
    positive_moments: List[str]
    improvement_opportunities: List[str]


@dataclass
class StartupPhaseAnalysis:
    """Analysis of user experience during a specific startup phase."""
    phase: StartupPhase
    phase_duration: float
    total_requests: int
    unique_users: int
    
    # Performance metrics
    average_response_time: float
    success_rate: float
    fallback_rate: float
    abandonment_rate: float
    
    # User behavior
    most_common_request_types: List[Tuple[str, int]]
    behavior_patterns: Dict[UserBehaviorPattern, int]
    
    # Pain points
    top_capability_gaps: List[Tuple[str, int]]
    common_abandonment_reasons: List[Tuple[str, int]]
    
    # Recommendations
    phase_recommendations: List[str]


@dataclass
class FallbackEffectivenessAnalysis:
    """Analysis of fallback response effectiveness."""
    total_fallback_responses: int
    acceptance_rate: float
    quality_distribution: Dict[CapabilityLevel, int]
    
    # Effectiveness by intent
    effectiveness_by_intent: Dict[str, Dict[str, Any]]
    
    # User feedback analysis
    positive_feedback_rate: float
    negative_feedback_rate: float
    common_feedback_themes: List[Tuple[str, int]]
    
    # Improvement opportunities
    low_performing_scenarios: List[Dict[str, Any]]
    high_performing_scenarios: List[Dict[str, Any]]
    
    # Recommendations
    fallback_recommendations: List[str]


class UserExperienceAnalyticsService:
    """
    Comprehensive analytics service for user experience during startup.
    
    Provides insights, recommendations, and actionable analytics based on
    user behavior patterns, startup performance, and satisfaction metrics.
    """
    
    def __init__(self, ux_logger: Optional[UserExperienceLogger] = None):
        """Initialize the UX analytics service."""
        self.ux_logger = ux_logger or get_ux_logger()
        self.insights_cache: Dict[str, List[AnalyticsInsight]] = {}
        self.cache_ttl = 300  # 5 minutes
        self.last_analysis_time: Optional[datetime] = None
        
        logger.info("UserExperienceAnalyticsService initialized")
    
    async def generate_comprehensive_analysis(self) -> Dict[str, Any]:
        """Generate a comprehensive UX analysis report."""
        if not self.ux_logger:
            logger.warning("No UX logger available for analysis")
            return {"error": "UX logger not available"}
        
        logger.info("Generating comprehensive UX analysis")
        
        try:
            # Get current UX data
            ux_summary = self.ux_logger.get_ux_summary()
            current_metrics = ux_summary["current_metrics"]
            request_patterns = self.ux_logger.request_patterns
            completed_sessions = self.ux_logger.completed_sessions
            
            # Generate different types of analysis
            analysis = {
                "summary": await self._generate_executive_summary(current_metrics, ux_summary),
                "user_journeys": await self._analyze_user_journeys(completed_sessions, request_patterns),
                "phase_analysis": await self._analyze_startup_phases(request_patterns),
                "behavior_patterns": await self._analyze_behavior_patterns(completed_sessions),
                "fallback_effectiveness": await self._analyze_fallback_effectiveness(request_patterns),
                "abandonment_analysis": await self._analyze_abandonment_patterns(request_patterns),
                "satisfaction_analysis": await self._analyze_user_satisfaction(completed_sessions),
                "insights": [asdict(insight) for insight in await self._generate_actionable_insights(request_patterns, completed_sessions)],
                "recommendations": await self._generate_recommendations(request_patterns, completed_sessions),
                "timestamp": datetime.now().isoformat(),
                "data_freshness": {
                    "total_patterns": len(request_patterns),
                    "analysis_period": ux_summary["startup_duration_seconds"],
                    "last_updated": datetime.now().isoformat()
                }
            }
            
            self.last_analysis_time = datetime.now()
            logger.info(f"Comprehensive analysis completed with {len(request_patterns)} patterns")
            
            return analysis
            
        except Exception as e:
            logger.error(f"Failed to generate comprehensive analysis: {e}")
            return {"error": str(e)}
    
    async def _generate_executive_summary(self, metrics: Dict[str, Any], ux_summary: Dict[str, Any]) -> Dict[str, Any]:
        """Generate executive summary of UX performance."""
        total_requests = metrics.get("total_requests", 0)
        
        if total_requests == 0:
            return {
                "status": "no_data",
                "message": "No user requests to analyze yet"
            }
        
        # Calculate key performance indicators
        success_rate = metrics.get("successful_requests", 0) / total_requests
        fallback_rate = metrics.get("fallback_requests", 0) / total_requests
        abandonment_rate = metrics.get("abandoned_requests", 0) / total_requests
        error_rate = metrics.get("error_requests", 0) / total_requests
        
        # Determine overall health score (0-100)
        health_score = (
            success_rate * 40 +  # 40% weight for success
            (1 - abandonment_rate) * 30 +  # 30% weight for retention
            fallback_rate * 20 +  # 20% weight for fallback acceptance
            (1 - error_rate) * 10  # 10% weight for error avoidance
        ) * 100
        
        # Determine health status
        if health_score >= 80:
            health_status = "excellent"
        elif health_score >= 60:
            health_status = "good"
        elif health_score >= 40:
            health_status = "fair"
        else:
            health_status = "poor"
        
        return {
            "health_score": round(health_score, 1),
            "health_status": health_status,
            "key_metrics": {
                "total_requests": total_requests,
                "success_rate": round(success_rate * 100, 1),
                "fallback_rate": round(fallback_rate * 100, 1),
                "abandonment_rate": round(abandonment_rate * 100, 1),
                "error_rate": round(error_rate * 100, 1)
            },
            "performance_indicators": {
                "average_wait_time": metrics.get("average_user_wait_time", 0),
                "p95_wait_time": metrics.get("p95_user_wait_time", 0),
                "user_retention_rate": metrics.get("user_retention_rate", 0),
                "fallback_acceptance_rate": metrics.get("fallback_acceptance_rate", 0)
            },
            "startup_duration": ux_summary.get("startup_duration_seconds", 0),
            "active_sessions": ux_summary.get("active_sessions", 0),
            "completed_sessions": ux_summary.get("completed_sessions", 0)
        }
    
    async def _analyze_user_journeys(self, sessions: List[UserSession], patterns: List[UserRequestPattern]) -> Dict[str, Any]:
        """Analyze individual user journeys through startup."""
        if not sessions:
            return {"message": "No completed user sessions to analyze"}
        
        journey_analyses = []
        
        for session in sessions:
            # Get patterns for this session
            session_patterns = [p for p in patterns if p.session_id == session.session_id]
            
            if not session_patterns:
                continue
            
            # Analyze journey
            journey = await self._analyze_single_journey(session, session_patterns)
            journey_analyses.append(journey)
        
        # Aggregate journey insights
        if not journey_analyses:
            return {"message": "No journey data available"}
        
        # Calculate journey statistics
        completed_journeys = [j for j in journey_analyses if j.journey_completed]
        abandoned_journeys = [j for j in journey_analyses if not j.journey_completed]
        
        completion_rate = len(completed_journeys) / len(journey_analyses) if journey_analyses else 0
        
        # Common pain points
        all_pain_points = []
        for journey in journey_analyses:
            all_pain_points.extend(journey.pain_points)
        
        common_pain_points = Counter(all_pain_points).most_common(5)
        
        # Common positive moments
        all_positive_moments = []
        for journey in journey_analyses:
            all_positive_moments.extend(journey.positive_moments)
        
        common_positive_moments = Counter(all_positive_moments).most_common(5)
        
        return {
            "total_journeys": len(journey_analyses),
            "completion_rate": round(completion_rate * 100, 1),
            "completed_journeys": len(completed_journeys),
            "abandoned_journeys": len(abandoned_journeys),
            "average_journey_duration": statistics.mean([
                (j.journey_end - j.journey_start).total_seconds() 
                for j in journey_analyses if j.journey_end
            ]) if any(j.journey_end for j in journey_analyses) else 0,
            "average_patience_score": statistics.mean([j.patience_score for j in journey_analyses]),
            "average_satisfaction_score": statistics.mean([j.satisfaction_score for j in journey_analyses]),
            "common_pain_points": common_pain_points,
            "common_positive_moments": common_positive_moments,
            "journey_details": [asdict(j) for j in journey_analyses[:10]]  # Top 10 for brevity
        }
    
    async def _analyze_single_journey(self, session: UserSession, patterns: List[UserRequestPattern]) -> UserJourneyAnalysis:
        """Analyze a single user's journey."""
        # Sort patterns by timestamp
        patterns.sort(key=lambda p: p.timestamp)
        
        # Calculate journey metrics
        total_wait_time = sum(p.user_wait_time_seconds or 0 for p in patterns)
        wait_times = [p.user_wait_time_seconds for p in patterns if p.user_wait_time_seconds]
        average_wait_time = statistics.mean(wait_times) if wait_times else 0
        max_wait_time = max(wait_times) if wait_times else 0
        
        # Identify pain points
        pain_points = []
        if any(p.outcome == RequestOutcome.ABANDONED for p in patterns):
            pain_points.append("request_abandonment")
        if average_wait_time > 30:
            pain_points.append("long_wait_times")
        if any(p.outcome == RequestOutcome.ERROR for p in patterns):
            pain_points.append("error_encounters")
        if len([p for p in patterns if p.fallback_used]) / len(patterns) > 0.7:
            pain_points.append("heavy_fallback_reliance")
        
        # Identify positive moments
        positive_moments = []
        if any(p.outcome == RequestOutcome.SUCCESS and (p.user_wait_time_seconds or 0) < 5 for p in patterns):
            positive_moments.append("quick_successful_responses")
        if any(p.fallback_used and p.fallback_quality == CapabilityLevel.ENHANCED for p in patterns):
            positive_moments.append("helpful_fallback_responses")
        if len(session.phases_experienced) > 1:
            positive_moments.append("phase_progression_witnessed")
        
        # Improvement opportunities
        improvement_opportunities = []
        if "long_wait_times" in pain_points:
            improvement_opportunities.append("reduce_response_times")
        if "heavy_fallback_reliance" in pain_points:
            improvement_opportunities.append("improve_model_loading_speed")
        if "request_abandonment" in pain_points:
            improvement_opportunities.append("better_progress_indication")
        
        return UserJourneyAnalysis(
            user_id=session.user_id or "anonymous",
            session_id=session.session_id,
            journey_start=session.start_time,
            journey_end=session.end_time,
            phases_experienced=list(session.phases_experienced),
            total_requests=len(patterns),
            successful_requests=len([p for p in patterns if p.outcome == RequestOutcome.SUCCESS]),
            abandoned_requests=len([p for p in patterns if p.outcome == RequestOutcome.ABANDONED]),
            fallback_requests=len([p for p in patterns if p.fallback_used]),
            total_wait_time=total_wait_time,
            average_wait_time=average_wait_time,
            max_wait_time=max_wait_time,
            patience_score=session.patience_score,
            satisfaction_score=session.satisfaction_score,
            engagement_score=session.engagement_score,
            journey_completed=session.end_time is not None and session.successful_requests > 0,
            abandonment_reason=None,  # Could be enhanced with more detailed tracking
            final_behavior_pattern=session.behavior_pattern,
            pain_points=pain_points,
            positive_moments=positive_moments,
            improvement_opportunities=improvement_opportunities
        )
    
    async def _analyze_startup_phases(self, patterns: List[UserRequestPattern]) -> Dict[str, Any]:
        """Analyze user experience across different startup phases."""
        if not patterns:
            return {"message": "No request patterns to analyze"}
        
        phase_analyses = {}
        
        for phase in StartupPhase:
            phase_patterns = [p for p in patterns if p.startup_phase == phase]
            
            if not phase_patterns:
                continue
            
            # Calculate phase metrics
            total_requests = len(phase_patterns)
            unique_users = len(set(p.user_id or p.session_id for p in phase_patterns))
            
            response_times = [p.response_time_seconds for p in phase_patterns if p.response_time_seconds]
            average_response_time = statistics.mean(response_times) if response_times else 0
            
            success_rate = len([p for p in phase_patterns if p.outcome == RequestOutcome.SUCCESS]) / total_requests
            fallback_rate = len([p for p in phase_patterns if p.fallback_used]) / total_requests
            abandonment_rate = len([p for p in phase_patterns if p.outcome == RequestOutcome.ABANDONED]) / total_requests
            
            # Most common request types
            request_types = Counter(p.request_type for p in phase_patterns)
            most_common_request_types = request_types.most_common(5)
            
            # Capability gaps
            capability_gaps = defaultdict(int)
            for pattern in phase_patterns:
                missing_capabilities = set(pattern.required_capabilities) - set(pattern.available_capabilities)
                for capability in missing_capabilities:
                    capability_gaps[capability] += 1
            
            top_capability_gaps = sorted(capability_gaps.items(), key=lambda x: x[1], reverse=True)[:5]
            
            # Abandonment reasons
            abandonment_reasons = Counter(
                p.abandonment_reason for p in phase_patterns 
                if p.abandonment_reason
            )
            common_abandonment_reasons = abandonment_reasons.most_common(3)
            
            # Generate phase-specific recommendations
            phase_recommendations = []
            if abandonment_rate > 0.2:
                phase_recommendations.append(f"High abandonment rate ({abandonment_rate:.1%}) - improve response times or fallback quality")
            if fallback_rate > 0.5:
                phase_recommendations.append(f"Heavy fallback usage ({fallback_rate:.1%}) - consider loading more models in this phase")
            if average_response_time > 15:
                phase_recommendations.append(f"Slow responses ({average_response_time:.1f}s avg) - optimize processing or add progress indicators")
            
            phase_analysis = StartupPhaseAnalysis(
                phase=phase,
                phase_duration=0,  # Would need phase manager integration
                total_requests=total_requests,
                unique_users=unique_users,
                average_response_time=average_response_time,
                success_rate=success_rate,
                fallback_rate=fallback_rate,
                abandonment_rate=abandonment_rate,
                most_common_request_types=most_common_request_types,
                behavior_patterns={},  # Would need session integration
                top_capability_gaps=top_capability_gaps,
                common_abandonment_reasons=common_abandonment_reasons,
                phase_recommendations=phase_recommendations
            )
            
            phase_analyses[phase.value] = asdict(phase_analysis)
        
        return {
            "phases_analyzed": len(phase_analyses),
            "phase_details": phase_analyses,
            "cross_phase_insights": await self._generate_cross_phase_insights(phase_analyses)
        }
    
    async def _generate_cross_phase_insights(self, phase_analyses: Dict[str, Any]) -> List[str]:
        """Generate insights across different startup phases."""
        insights = []
        
        if len(phase_analyses) < 2:
            return ["Insufficient phase data for cross-phase analysis"]
        
        # Compare abandonment rates across phases
        abandonment_rates = {
            phase: data["abandonment_rate"] 
            for phase, data in phase_analyses.items()
        }
        
        if abandonment_rates:
            worst_phase = max(abandonment_rates.items(), key=lambda x: x[1])
            best_phase = min(abandonment_rates.items(), key=lambda x: x[1])
            
            if worst_phase[1] > best_phase[1] * 2:
                insights.append(f"Phase {worst_phase[0]} has significantly higher abandonment ({worst_phase[1]:.1%}) than {best_phase[0]} ({best_phase[1]:.1%})")
        
        # Compare response times
        response_times = {
            phase: data["average_response_time"]
            for phase, data in phase_analyses.items()
        }
        
        if response_times:
            slowest_phase = max(response_times.items(), key=lambda x: x[1])
            fastest_phase = min(response_times.items(), key=lambda x: x[1])
            
            if slowest_phase[1] > fastest_phase[1] * 2:
                insights.append(f"Phase {slowest_phase[0]} is much slower ({slowest_phase[1]:.1f}s) than {fastest_phase[0]} ({fastest_phase[1]:.1f}s)")
        
        return insights
    
    async def _analyze_behavior_patterns(self, sessions: List[UserSession]) -> Dict[str, Any]:
        """Analyze user behavior patterns."""
        if not sessions:
            return {"message": "No user sessions to analyze"}
        
        # Behavior pattern distribution
        behavior_patterns = Counter(s.behavior_pattern for s in sessions if s.behavior_pattern)
        
        # Score distributions
        patience_scores = [s.patience_score for s in sessions if s.patience_score > 0]
        engagement_scores = [s.engagement_score for s in sessions if s.engagement_score > 0]
        satisfaction_scores = [s.satisfaction_score for s in sessions if s.satisfaction_score > 0]
        
        return {
            "total_sessions_analyzed": len(sessions),
            "behavior_pattern_distribution": dict(behavior_patterns),
            "score_analysis": {
                "patience": {
                    "average": statistics.mean(patience_scores) if patience_scores else 0,
                    "median": statistics.median(patience_scores) if patience_scores else 0,
                    "distribution": self._score_distribution(patience_scores)
                },
                "engagement": {
                    "average": statistics.mean(engagement_scores) if engagement_scores else 0,
                    "median": statistics.median(engagement_scores) if engagement_scores else 0,
                    "distribution": self._score_distribution(engagement_scores)
                },
                "satisfaction": {
                    "average": statistics.mean(satisfaction_scores) if satisfaction_scores else 0,
                    "median": statistics.median(satisfaction_scores) if satisfaction_scores else 0,
                    "distribution": self._score_distribution(satisfaction_scores)
                }
            },
            "behavior_insights": await self._generate_behavior_insights(behavior_patterns, sessions)
        }
    
    def _score_distribution(self, scores: List[float]) -> Dict[str, int]:
        """Calculate score distribution in ranges."""
        if not scores:
            return {}
        
        distribution = {
            "0-20": 0,
            "21-40": 0,
            "41-60": 0,
            "61-80": 0,
            "81-100": 0
        }
        
        for score in scores:
            if score <= 20:
                distribution["0-20"] += 1
            elif score <= 40:
                distribution["21-40"] += 1
            elif score <= 60:
                distribution["41-60"] += 1
            elif score <= 80:
                distribution["61-80"] += 1
            else:
                distribution["81-100"] += 1
        
        return distribution
    
    async def _generate_behavior_insights(self, behavior_patterns: Counter, sessions: List[UserSession]) -> List[str]:
        """Generate insights about user behavior patterns."""
        insights = []
        
        total_sessions = len(sessions)
        if total_sessions == 0:
            return insights
        
        # Analyze dominant patterns
        if behavior_patterns:
            most_common = behavior_patterns.most_common(1)[0]
            pattern_name = most_common[0].value if hasattr(most_common[0], 'value') else str(most_common[0])
            pattern_percentage = (most_common[1] / total_sessions) * 100
            
            insights.append(f"Most common behavior: {pattern_name} ({pattern_percentage:.1f}% of users)")
            
            # Pattern-specific insights
            if "impatient" in pattern_name.lower():
                insights.append("High impatience detected - consider faster initial responses or better progress indication")
            elif "patient" in pattern_name.lower():
                insights.append("Users show patience - opportunity to provide more detailed progress updates")
            elif "fallback" in pattern_name.lower():
                insights.append("Users accept fallback responses well - ensure fallback quality remains high")
        
        # Analyze score trends
        patience_scores = [s.patience_score for s in sessions if s.patience_score > 0]
        if patience_scores:
            avg_patience = statistics.mean(patience_scores)
            if avg_patience < 40:
                insights.append("Low average patience score - users are becoming frustrated with wait times")
            elif avg_patience > 70:
                insights.append("High patience score - users are tolerant of current startup experience")
        
        return insights
    
    async def _analyze_fallback_effectiveness(self, patterns: List[UserRequestPattern]) -> Dict[str, Any]:
        """Analyze the effectiveness of fallback responses."""
        fallback_patterns = [p for p in patterns if p.fallback_used]
        
        if not fallback_patterns:
            return {"message": "No fallback responses to analyze"}
        
        total_fallbacks = len(fallback_patterns)
        
        # Quality distribution
        quality_distribution = Counter(p.fallback_quality for p in fallback_patterns if p.fallback_quality)
        
        # Effectiveness by intent (simplified - would need more detailed tracking)
        intent_effectiveness = defaultdict(lambda: {"total": 0, "successful": 0})
        for pattern in fallback_patterns:
            if pattern.detected_intent:
                intent_key = pattern.detected_intent.value if hasattr(pattern.detected_intent, 'value') else str(pattern.detected_intent)
                intent_effectiveness[intent_key]["total"] += 1
                if pattern.outcome != RequestOutcome.ABANDONED:
                    intent_effectiveness[intent_key]["successful"] += 1
        
        # Convert to effectiveness rates
        effectiveness_by_intent = {}
        for intent, data in intent_effectiveness.items():
            effectiveness_by_intent[intent] = {
                "total_fallbacks": data["total"],
                "success_rate": data["successful"] / data["total"] if data["total"] > 0 else 0,
                "abandonment_rate": 1 - (data["successful"] / data["total"]) if data["total"] > 0 else 0
            }
        
        # Overall acceptance rate (not abandoned)
        acceptance_rate = len([p for p in fallback_patterns if p.outcome != RequestOutcome.ABANDONED]) / total_fallbacks
        
        # Generate recommendations
        fallback_recommendations = []
        if acceptance_rate < 0.7:
            fallback_recommendations.append("Low fallback acceptance rate - improve fallback response quality and relevance")
        
        low_quality_rate = quality_distribution.get(CapabilityLevel.BASIC, 0) / total_fallbacks
        if low_quality_rate > 0.5:
            fallback_recommendations.append("High proportion of basic quality fallbacks - consider loading more models earlier")
        
        return {
            "total_fallback_responses": total_fallbacks,
            "acceptance_rate": round(acceptance_rate * 100, 1),
            "quality_distribution": {k.value if hasattr(k, 'value') else str(k): v for k, v in quality_distribution.items()},
            "effectiveness_by_intent": effectiveness_by_intent,
            "fallback_recommendations": fallback_recommendations,
            "performance_summary": {
                "best_performing_quality": max(quality_distribution.items(), key=lambda x: x[1])[0].value if quality_distribution else None,
                "most_common_intent": max(effectiveness_by_intent.items(), key=lambda x: x[1]["total_fallbacks"])[0] if effectiveness_by_intent else None
            }
        }
    
    async def _analyze_abandonment_patterns(self, patterns: List[UserRequestPattern]) -> Dict[str, Any]:
        """Analyze user abandonment patterns."""
        abandoned_patterns = [p for p in patterns if p.outcome == RequestOutcome.ABANDONED]
        
        if not abandoned_patterns:
            return {"message": "No abandonment patterns to analyze"}
        
        total_requests = len(patterns)
        total_abandoned = len(abandoned_patterns)
        abandonment_rate = total_abandoned / total_requests
        
        # Abandonment by phase
        abandonment_by_phase = Counter(p.startup_phase for p in abandoned_patterns)
        
        # Abandonment reasons
        abandonment_reasons = Counter(p.abandonment_reason for p in abandoned_patterns if p.abandonment_reason)
        
        # Wait times before abandonment
        abandonment_wait_times = [p.user_wait_time_seconds for p in abandoned_patterns if p.user_wait_time_seconds]
        avg_abandonment_wait_time = statistics.mean(abandonment_wait_times) if abandonment_wait_times else 0
        
        # Request types most likely to be abandoned
        abandoned_request_types = Counter(p.request_type for p in abandoned_patterns)
        
        # Generate abandonment insights
        abandonment_insights = []
        if abandonment_rate > 0.2:
            abandonment_insights.append(f"High abandonment rate ({abandonment_rate:.1%}) indicates user experience issues")
        
        if avg_abandonment_wait_time > 0:
            abandonment_insights.append(f"Users abandon after waiting {avg_abandonment_wait_time:.1f}s on average")
        
        if abandonment_by_phase:
            worst_phase = max(abandonment_by_phase.items(), key=lambda x: x[1])
            abandonment_insights.append(f"Most abandonments occur in {worst_phase[0].value} phase ({worst_phase[1]} cases)")
        
        return {
            "total_abandoned_requests": total_abandoned,
            "abandonment_rate": round(abandonment_rate * 100, 1),
            "average_wait_before_abandonment": round(avg_abandonment_wait_time, 1),
            "abandonment_by_phase": {k.value: v for k, v in abandonment_by_phase.items()},
            "abandonment_reasons": dict(abandonment_reasons),
            "most_abandoned_request_types": abandoned_request_types.most_common(5),
            "abandonment_insights": abandonment_insights,
            "prevention_recommendations": await self._generate_abandonment_prevention_recommendations(abandoned_patterns)
        }
    
    async def _generate_abandonment_prevention_recommendations(self, abandoned_patterns: List[UserRequestPattern]) -> List[str]:
        """Generate recommendations to prevent user abandonment."""
        recommendations = []
        
        if not abandoned_patterns:
            return recommendations
        
        # Analyze common abandonment scenarios
        wait_times = [p.user_wait_time_seconds for p in abandoned_patterns if p.user_wait_time_seconds]
        if wait_times:
            avg_wait = statistics.mean(wait_times)
            if avg_wait > 30:
                recommendations.append("Implement better progress indicators for requests taking longer than 30 seconds")
            if avg_wait > 60:
                recommendations.append("Consider breaking down long-running operations into smaller, faster steps")
        
        # Analyze request types
        request_types = Counter(p.request_type for p in abandoned_patterns)
        if request_types:
            most_abandoned_type = request_types.most_common(1)[0]
            recommendations.append(f"Focus on improving {most_abandoned_type[0]} request handling - it has the highest abandonment rate")
        
        # Analyze capability gaps
        capability_gaps = defaultdict(int)
        for pattern in abandoned_patterns:
            missing_capabilities = set(pattern.required_capabilities) - set(pattern.available_capabilities)
            for capability in missing_capabilities:
                capability_gaps[capability] += 1
        
        if capability_gaps:
            top_gap = max(capability_gaps.items(), key=lambda x: x[1])
            recommendations.append(f"Prioritize loading {top_gap[0]} capability - it's the most requested missing feature")
        
        return recommendations
    
    async def _analyze_user_satisfaction(self, sessions: List[UserSession]) -> Dict[str, Any]:
        """Analyze user satisfaction metrics."""
        if not sessions:
            return {"message": "No user sessions to analyze"}
        
        satisfaction_scores = [s.satisfaction_score for s in sessions if s.satisfaction_score > 0]
        
        if not satisfaction_scores:
            return {"message": "No satisfaction scores available"}
        
        avg_satisfaction = statistics.mean(satisfaction_scores)
        median_satisfaction = statistics.median(satisfaction_scores)
        
        # Satisfaction distribution
        satisfaction_distribution = self._score_distribution(satisfaction_scores)
        
        # Factors affecting satisfaction
        high_satisfaction_sessions = [s for s in sessions if s.satisfaction_score > 70]
        low_satisfaction_sessions = [s for s in sessions if s.satisfaction_score < 40]
        
        # Analyze what makes users satisfied vs dissatisfied
        satisfaction_factors = {
            "high_satisfaction_characteristics": await self._analyze_satisfaction_factors(high_satisfaction_sessions, True),
            "low_satisfaction_characteristics": await self._analyze_satisfaction_factors(low_satisfaction_sessions, False)
        }
        
        return {
            "average_satisfaction": round(avg_satisfaction, 1),
            "median_satisfaction": round(median_satisfaction, 1),
            "satisfaction_distribution": satisfaction_distribution,
            "high_satisfaction_sessions": len(high_satisfaction_sessions),
            "low_satisfaction_sessions": len(low_satisfaction_sessions),
            "satisfaction_factors": satisfaction_factors,
            "satisfaction_insights": await self._generate_satisfaction_insights(sessions)
        }
    
    async def _analyze_satisfaction_factors(self, sessions: List[UserSession], high_satisfaction: bool) -> Dict[str, Any]:
        """Analyze factors that contribute to high or low satisfaction."""
        if not sessions:
            return {}
        
        # Calculate averages for this group
        avg_wait_time = statistics.mean([s.average_wait_time_seconds for s in sessions if s.average_wait_time_seconds]) if any(s.average_wait_time_seconds for s in sessions) else 0
        avg_success_rate = statistics.mean([s.successful_requests / s.total_requests for s in sessions if s.total_requests > 0]) if sessions else 0
        avg_fallback_rate = statistics.mean([s.fallback_requests / s.total_requests for s in sessions if s.total_requests > 0]) if sessions else 0
        
        # Common behavior patterns
        behavior_patterns = Counter(s.behavior_pattern for s in sessions if s.behavior_pattern)
        
        return {
            "session_count": len(sessions),
            "average_wait_time": round(avg_wait_time, 1),
            "average_success_rate": round(avg_success_rate * 100, 1),
            "average_fallback_rate": round(avg_fallback_rate * 100, 1),
            "common_behavior_patterns": dict(behavior_patterns.most_common(3)),
            "average_session_duration": statistics.mean([
                s.duration_seconds for s in sessions if s.duration_seconds
            ]) if any(s.duration_seconds for s in sessions) else 0
        }
    
    async def _generate_satisfaction_insights(self, sessions: List[UserSession]) -> List[str]:
        """Generate insights about user satisfaction."""
        insights = []
        
        satisfaction_scores = [s.satisfaction_score for s in sessions if s.satisfaction_score > 0]
        if not satisfaction_scores:
            return insights
        
        avg_satisfaction = statistics.mean(satisfaction_scores)
        
        if avg_satisfaction < 40:
            insights.append("Low user satisfaction - immediate attention needed to improve startup experience")
        elif avg_satisfaction < 60:
            insights.append("Moderate user satisfaction - room for improvement in startup experience")
        elif avg_satisfaction > 80:
            insights.append("High user satisfaction - current startup experience is working well")
        
        # Analyze satisfaction vs other metrics
        high_sat_sessions = [s for s in sessions if s.satisfaction_score > 70]
        low_sat_sessions = [s for s in sessions if s.satisfaction_score < 40]
        
        if high_sat_sessions and low_sat_sessions:
            high_wait = statistics.mean([s.average_wait_time_seconds for s in high_sat_sessions if s.average_wait_time_seconds]) if any(s.average_wait_time_seconds for s in high_sat_sessions) else 0
            low_wait = statistics.mean([s.average_wait_time_seconds for s in low_sat_sessions if s.average_wait_time_seconds]) if any(s.average_wait_time_seconds for s in low_sat_sessions) else 0
            
            if low_wait > high_wait * 1.5:
                insights.append("Wait time strongly correlates with satisfaction - focus on reducing response times")
        
        return insights
    
    async def _generate_actionable_insights(self, patterns: List[UserRequestPattern], sessions: List[UserSession]) -> List[AnalyticsInsight]:
        """Generate actionable insights from the analysis."""
        insights = []
        
        if not patterns:
            return insights
        
        total_requests = len(patterns)
        
        # Performance insights
        wait_times = [p.user_wait_time_seconds for p in patterns if p.user_wait_time_seconds]
        if wait_times:
            avg_wait = statistics.mean(wait_times)
            p95_wait = self._calculate_percentile(wait_times, 95)
            
            if avg_wait > 15:
                insights.append(AnalyticsInsight(
                    insight_type=AnalyticsInsightType.PERFORMANCE,
                    severity=InsightSeverity.WARNING if avg_wait < 30 else InsightSeverity.CRITICAL,
                    title="High Average Wait Time",
                    description=f"Users are waiting {avg_wait:.1f}s on average for responses",
                    metric_value=avg_wait,
                    metric_unit="seconds",
                    recommendation="Consider loading essential models earlier or improving fallback response quality",
                    impact_score=80,
                    confidence=95,
                    supporting_data={"p95_wait_time": p95_wait, "total_requests": total_requests}
                ))
        
        # Abandonment insights
        abandoned_count = len([p for p in patterns if p.outcome == RequestOutcome.ABANDONED])
        if abandoned_count > 0:
            abandonment_rate = abandoned_count / total_requests
            
            if abandonment_rate > 0.15:
                insights.append(AnalyticsInsight(
                    insight_type=AnalyticsInsightType.ABANDONMENT,
                    severity=InsightSeverity.CRITICAL if abandonment_rate > 0.25 else InsightSeverity.WARNING,
                    title="High User Abandonment Rate",
                    description=f"{abandonment_rate:.1%} of users abandon their requests",
                    metric_value=abandonment_rate * 100,
                    metric_unit="percent",
                    recommendation="Implement better progress indicators and reduce wait times for critical operations",
                    impact_score=90,
                    confidence=90,
                    supporting_data={"abandoned_requests": abandoned_count, "total_requests": total_requests}
                ))
        
        # Fallback insights
        fallback_patterns = [p for p in patterns if p.fallback_used]
        if fallback_patterns:
            fallback_rate = len(fallback_patterns) / total_requests
            
            if fallback_rate > 0.6:
                insights.append(AnalyticsInsight(
                    insight_type=AnalyticsInsightType.FALLBACK,
                    severity=InsightSeverity.INFO,
                    title="High Fallback Usage",
                    description=f"{fallback_rate:.1%} of requests use fallback responses",
                    metric_value=fallback_rate * 100,
                    metric_unit="percent",
                    recommendation="Consider loading more models in earlier phases to reduce fallback dependency",
                    impact_score=60,
                    confidence=85,
                    supporting_data={"fallback_requests": len(fallback_patterns)}
                ))
        
        # Satisfaction insights
        if sessions:
            satisfaction_scores = [s.satisfaction_score for s in sessions if s.satisfaction_score > 0]
            if satisfaction_scores:
                avg_satisfaction = statistics.mean(satisfaction_scores)
                
                if avg_satisfaction < 50:
                    insights.append(AnalyticsInsight(
                        insight_type=AnalyticsInsightType.SATISFACTION,
                        severity=InsightSeverity.CRITICAL,
                        title="Low User Satisfaction",
                        description=f"Average user satisfaction is {avg_satisfaction:.1f}/100",
                        metric_value=avg_satisfaction,
                        metric_unit="score",
                        recommendation="Focus on improving response times, fallback quality, and user communication",
                        impact_score=95,
                        confidence=80,
                        supporting_data={"session_count": len(sessions)}
                    ))
        
        return insights
    
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
    
    async def _generate_recommendations(self, patterns: List[UserRequestPattern], sessions: List[UserSession]) -> List[Dict[str, Any]]:
        """Generate actionable recommendations for improving UX."""
        recommendations = []
        
        if not patterns:
            return recommendations
        
        # Analyze current state
        total_requests = len(patterns)
        abandoned_count = len([p for p in patterns if p.outcome == RequestOutcome.ABANDONED])
        fallback_count = len([p for p in patterns if p.fallback_used])
        
        # Wait time recommendations
        wait_times = [p.user_wait_time_seconds for p in patterns if p.user_wait_time_seconds]
        if wait_times:
            avg_wait = statistics.mean(wait_times)
            
            if avg_wait > 20:
                recommendations.append({
                    "category": "Performance",
                    "priority": "High",
                    "title": "Reduce Response Times",
                    "description": f"Average wait time is {avg_wait:.1f}s, which may frustrate users",
                    "actions": [
                        "Load essential models in parallel during startup",
                        "Implement request queuing with position indicators",
                        "Add progress bars for long-running operations",
                        "Consider model caching to reduce cold start times"
                    ],
                    "expected_impact": "Reduce abandonment rate by 30-50%",
                    "implementation_effort": "Medium"
                })
        
        # Abandonment recommendations
        if abandoned_count > 0:
            abandonment_rate = abandoned_count / total_requests
            
            if abandonment_rate > 0.15:
                recommendations.append({
                    "category": "User Retention",
                    "priority": "Critical",
                    "title": "Reduce User Abandonment",
                    "description": f"{abandonment_rate:.1%} of users abandon requests",
                    "actions": [
                        "Implement real-time progress indicators",
                        "Provide estimated completion times",
                        "Offer alternative actions while waiting",
                        "Send proactive status updates for long operations"
                    ],
                    "expected_impact": "Improve user retention by 40-60%",
                    "implementation_effort": "Medium"
                })
        
        # Fallback recommendations
        if fallback_count > 0:
            fallback_rate = fallback_count / total_requests
            
            if fallback_rate > 0.5:
                recommendations.append({
                    "category": "Capability Management",
                    "priority": "Medium",
                    "title": "Optimize Model Loading Strategy",
                    "description": f"{fallback_rate:.1%} of requests require fallback responses",
                    "actions": [
                        "Analyze most requested capabilities and prioritize loading",
                        "Implement predictive model loading based on user patterns",
                        "Improve fallback response quality and helpfulness",
                        "Add capability-specific loading progress indicators"
                    ],
                    "expected_impact": "Reduce fallback dependency by 20-30%",
                    "implementation_effort": "High"
                })
        
        # User experience recommendations
        if sessions:
            satisfaction_scores = [s.satisfaction_score for s in sessions if s.satisfaction_score > 0]
            if satisfaction_scores:
                avg_satisfaction = statistics.mean(satisfaction_scores)
                
                if avg_satisfaction < 60:
                    recommendations.append({
                        "category": "User Experience",
                        "priority": "High",
                        "title": "Improve Overall User Satisfaction",
                        "description": f"User satisfaction score is {avg_satisfaction:.1f}/100",
                        "actions": [
                            "Implement user feedback collection system",
                            "Add contextual help and guidance during startup",
                            "Improve error messages and recovery suggestions",
                            "Provide clear expectations about startup process"
                        ],
                        "expected_impact": "Increase satisfaction score by 15-25 points",
                        "implementation_effort": "Medium"
                    })
        
        return recommendations
    
    async def get_real_time_insights(self) -> Dict[str, Any]:
        """Get real-time UX insights for monitoring dashboards."""
        if not self.ux_logger:
            return {"error": "UX logger not available"}
        
        try:
            # Get current metrics
            ux_summary = self.ux_logger.get_ux_summary()
            current_metrics = ux_summary["current_metrics"]
            
            # Calculate key indicators
            total_requests = current_metrics.get("total_requests", 0)
            
            if total_requests == 0:
                return {
                    "status": "no_data",
                    "message": "No user activity to analyze",
                    "timestamp": datetime.now().isoformat()
                }
            
            # Real-time health indicators
            success_rate = current_metrics.get("successful_requests", 0) / total_requests
            abandonment_rate = current_metrics.get("abandoned_requests", 0) / total_requests
            fallback_rate = current_metrics.get("fallback_requests", 0) / total_requests
            
            # Health status
            health_score = (success_rate * 0.4 + (1 - abandonment_rate) * 0.4 + fallback_rate * 0.2) * 100
            
            if health_score >= 80:
                health_status = "excellent"
            elif health_score >= 60:
                health_status = "good"
            elif health_score >= 40:
                health_status = "fair"
            else:
                health_status = "poor"
            
            # Active issues
            active_issues = []
            if abandonment_rate > 0.2:
                active_issues.append("High abandonment rate")
            if current_metrics.get("average_user_wait_time", 0) > 30:
                active_issues.append("Long wait times")
            if current_metrics.get("error_requests", 0) / total_requests > 0.1:
                active_issues.append("High error rate")
            
            return {
                "health_score": round(health_score, 1),
                "health_status": health_status,
                "key_metrics": {
                    "total_requests": total_requests,
                    "success_rate": round(success_rate * 100, 1),
                    "abandonment_rate": round(abandonment_rate * 100, 1),
                    "fallback_rate": round(fallback_rate * 100, 1),
                    "average_wait_time": current_metrics.get("average_user_wait_time", 0)
                },
                "active_issues": active_issues,
                "active_sessions": ux_summary.get("active_sessions", 0),
                "startup_duration": ux_summary.get("startup_duration_seconds", 0),
                "timestamp": datetime.now().isoformat()
            }
            
        except Exception as e:
            logger.error(f"Failed to get real-time insights: {e}")
            return {"error": str(e)}
    
    async def export_analytics_report(self, format_type: str = "json") -> str:
        """Export comprehensive analytics report."""
        try:
            analysis = await self.generate_comprehensive_analysis()
            
            if format_type == "json":
                import json
                # Custom serializer to handle enums and other non-serializable objects
                def serialize_obj(obj):
                    if hasattr(obj, 'value'):  # Handle enums
                        return obj.value
                    elif hasattr(obj, '__dict__'):  # Handle dataclass objects
                        return obj.__dict__
                    elif isinstance(obj, (set, frozenset)):  # Handle sets
                        return list(obj)
                    else:
                        return str(obj)
                
                return json.dumps(analysis, indent=2, default=serialize_obj)
            elif format_type == "summary":
                return await self._generate_text_summary(analysis)
            else:
                raise ValueError(f"Unsupported format: {format_type}")
                
        except Exception as e:
            logger.error(f"Failed to export analytics report: {e}")
            return f"Error generating report: {str(e)}"
    
    async def _generate_text_summary(self, analysis: Dict[str, Any]) -> str:
        """Generate a human-readable text summary of the analysis."""
        summary_lines = []
        
        summary_lines.append("USER EXPERIENCE ANALYTICS REPORT")
        summary_lines.append("=" * 50)
        summary_lines.append("")
        
        # Executive summary
        if "summary" in analysis:
            summary = analysis["summary"]
            summary_lines.append(f"Overall Health Score: {summary.get('health_score', 'N/A')}/100 ({summary.get('health_status', 'unknown')})")
            summary_lines.append("")
            
            key_metrics = summary.get("key_metrics", {})
            summary_lines.append("Key Metrics:")
            summary_lines.append(f"  • Total Requests: {key_metrics.get('total_requests', 0)}")
            summary_lines.append(f"  • Success Rate: {key_metrics.get('success_rate', 0)}%")
            summary_lines.append(f"  • Abandonment Rate: {key_metrics.get('abandonment_rate', 0)}%")
            summary_lines.append(f"  • Fallback Rate: {key_metrics.get('fallback_rate', 0)}%")
            summary_lines.append("")
        
        # Top insights
        if "insights" in analysis and analysis["insights"]:
            summary_lines.append("Top Insights:")
            for insight in analysis["insights"][:3]:
                severity_icon = "🔴" if insight["severity"] == "critical" else "🟡" if insight["severity"] == "warning" else "🔵"
                summary_lines.append(f"  {severity_icon} {insight['title']}: {insight['description']}")
            summary_lines.append("")
        
        # Top recommendations
        if "recommendations" in analysis and analysis["recommendations"]:
            summary_lines.append("Top Recommendations:")
            for rec in analysis["recommendations"][:3]:
                priority_icon = "🔥" if rec["priority"] == "Critical" else "⚡" if rec["priority"] == "High" else "📋"
                summary_lines.append(f"  {priority_icon} {rec['title']}")
                summary_lines.append(f"     {rec['description']}")
            summary_lines.append("")
        
        summary_lines.append(f"Report generated: {analysis.get('timestamp', 'Unknown')}")
        
        return "\n".join(summary_lines)


# Global analytics service instance
_ux_analytics_service: Optional[UserExperienceAnalyticsService] = None


def get_ux_analytics_service() -> Optional[UserExperienceAnalyticsService]:
    """Get the global UX analytics service instance."""
    return _ux_analytics_service


def initialize_ux_analytics_service(ux_logger: Optional[UserExperienceLogger] = None) -> UserExperienceAnalyticsService:
    """Initialize the global UX analytics service."""
    global _ux_analytics_service
    _ux_analytics_service = UserExperienceAnalyticsService(ux_logger)
    return _ux_analytics_service