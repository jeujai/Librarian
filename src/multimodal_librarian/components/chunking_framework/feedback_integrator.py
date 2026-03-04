"""
User Feedback Integration System.

This module implements user feedback collection, analysis, and integration
with the configuration optimization system.
"""

import logging
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass
from datetime import datetime, timedelta
import json
import uuid
import numpy as np
from collections import defaultdict, Counter
import re

from ...models.chunking import OptimizationStrategy
from ...database.connection import get_database_connection
from .performance_tracker import UserFeedbackData, PerformanceTracker

logger = logging.getLogger(__name__)


@dataclass
class FeedbackAnalysis:
    """Analysis of user feedback patterns."""
    domain_name: str
    total_feedback_count: int
    average_rating: float
    sentiment_score: float
    issue_categories: Dict[str, int]
    improvement_suggestions: List[str]
    priority_issues: List[str]
    confidence_score: float
    analysis_timestamp: datetime


@dataclass
class FeedbackTrigger:
    """Trigger for optimization based on feedback."""
    trigger_id: str
    domain_name: str
    trigger_type: str  # 'rating_decline', 'issue_spike', 'negative_sentiment'
    severity: str  # 'low', 'medium', 'high'
    feedback_evidence: List[str]  # Feedback IDs that triggered this
    suggested_optimizations: List[str]
    created_at: datetime


class FeedbackIntegrator:
    """
    User feedback integration system with analysis and optimization triggers.
    
    Implements feedback collection, sentiment analysis, issue categorization,
    and automated optimization trigger generation.
    """
    
    def __init__(self, performance_tracker: PerformanceTracker):
        """Initialize the feedback integrator."""
        self.performance_tracker = performance_tracker
        
        # Feedback analysis configuration
        self.analysis_config = {
            'min_feedback_for_analysis': 5,
            'analysis_window_days': 30,
            'rating_decline_threshold': 0.5,
            'negative_sentiment_threshold': -0.3,
            'issue_spike_threshold': 3
        }
        
        # Issue categorization patterns
        self.issue_patterns = {
            'chunk_quality': [
                r'\b(quality|accuracy|wrong|incorrect|inaccurate)\b',
                r'\b(poor|bad|terrible) (quality|content)\b',
                r'\b(not accurate|inaccurate|wrong information)\b'
            ],
            'relevance': [
                r'\b(relevant|irrelevant|unrelated|off-topic)\b',
                r'\b(not relevant|doesn\'t match|unrelated to)\b',
                r'\b(wrong topic|different subject)\b'
            ],
            'completeness': [
                r'\b(incomplete|missing|partial|cut off)\b',
                r'\b(not complete|lacks|missing information)\b',
                r'\b(truncated|abbreviated)\b'
            ],
            'bridge_quality': [
                r'\b(connection|bridge|transition|flow)\b',
                r'\b(doesn\'t connect|poor transition|abrupt)\b',
                r'\b(missing context|no connection)\b'
            ],
            'processing_speed': [
                r'\b(slow|fast|speed|performance|time)\b',
                r'\b(takes too long|very slow|too fast)\b',
                r'\b(processing time|response time)\b'
            ],
            'search_results': [
                r'\b(search|results|finding|retrieval)\b',
                r'\b(can\'t find|no results|poor search)\b',
                r'\b(search quality|result quality)\b'
            ]
        }
        
        # Sentiment analysis keywords
        self.sentiment_keywords = {
            'positive': [
                'good', 'great', 'excellent', 'amazing', 'perfect', 'helpful',
                'accurate', 'relevant', 'useful', 'clear', 'comprehensive'
            ],
            'negative': [
                'bad', 'terrible', 'awful', 'poor', 'wrong', 'useless',
                'irrelevant', 'confusing', 'incomplete', 'inaccurate', 'slow'
            ],
            'neutral': [
                'okay', 'fine', 'average', 'normal', 'standard', 'typical'
            ]
        }
        
        logger.info("Initialized Feedback Integrator")
    
    def collect_feedback(self, user_id: str, domain_name: str, 
                        feedback_type: str, rating: Optional[float] = None,
                        feedback_text: str = "", chunk_ids: List[str] = None,
                        affected_components: List[str] = None) -> str:
        """
        Collect user feedback and trigger analysis.
        
        Args:
            user_id: ID of the user providing feedback
            domain_name: Domain the feedback relates to
            feedback_type: Type of feedback (rating, issue_report, suggestion)
            rating: Numerical rating (1.0-5.0) if applicable
            feedback_text: Text description of feedback
            chunk_ids: IDs of chunks the feedback relates to
            affected_components: Components affected by the feedback
            
        Returns:
            Feedback ID
        """
        feedback_data = UserFeedbackData(
            feedback_id=str(uuid.uuid4()),
            user_id=user_id,
            domain_name=domain_name,
            feedback_type=feedback_type,
            rating=rating,
            feedback_text=feedback_text,
            affected_components=affected_components or [],
            chunk_ids=chunk_ids or [],
            timestamp=datetime.now(),
            processed=False
        )
        
        # Store feedback through performance tracker
        self.performance_tracker.collect_user_feedback(feedback_data)
        
        # Trigger immediate analysis if needed
        self._check_immediate_triggers(feedback_data)
        
        logger.info(f"Collected feedback {feedback_data.feedback_id} from user {user_id} "
                   f"for domain {domain_name}")
        
        return feedback_data.feedback_id
    
    def analyze_feedback_patterns(self, domain_name: str, 
                                 analysis_window_days: int = None) -> FeedbackAnalysis:
        """
        Analyze feedback patterns for a domain.
        
        Args:
            domain_name: Domain to analyze
            analysis_window_days: Days of feedback to analyze
            
        Returns:
            Feedback analysis results
        """
        window_days = analysis_window_days or self.analysis_config['analysis_window_days']
        cutoff_date = datetime.now() - timedelta(days=window_days)
        
        # Get feedback data
        feedback_data = self._get_domain_feedback(domain_name, cutoff_date)
        
        if len(feedback_data) < self.analysis_config['min_feedback_for_analysis']:
            return FeedbackAnalysis(
                domain_name=domain_name,
                total_feedback_count=len(feedback_data),
                average_rating=0.0,
                sentiment_score=0.0,
                issue_categories={},
                improvement_suggestions=[],
                priority_issues=[],
                confidence_score=0.0,
                analysis_timestamp=datetime.now()
            )
        
        # Calculate metrics
        ratings = [f.rating for f in feedback_data if f.rating is not None]
        average_rating = np.mean(ratings) if ratings else 0.0
        
        # Analyze sentiment
        sentiment_score = self._analyze_overall_sentiment(feedback_data)
        
        # Categorize issues
        issue_categories = self._categorize_issues(feedback_data)
        
        # Generate improvement suggestions
        improvement_suggestions = self._generate_improvement_suggestions(
            issue_categories, average_rating, sentiment_score
        )
        
        # Identify priority issues
        priority_issues = self._identify_priority_issues(issue_categories, feedback_data)
        
        # Calculate confidence score
        confidence_score = min(1.0, len(feedback_data) / 20.0)  # Higher confidence with more feedback
        
        analysis = FeedbackAnalysis(
            domain_name=domain_name,
            total_feedback_count=len(feedback_data),
            average_rating=average_rating,
            sentiment_score=sentiment_score,
            issue_categories=issue_categories,
            improvement_suggestions=improvement_suggestions,
            priority_issues=priority_issues,
            confidence_score=confidence_score,
            analysis_timestamp=datetime.now()
        )
        
        # Store analysis results
        self._store_feedback_analysis(analysis)
        
        return analysis
    
    def generate_optimization_triggers(self, domain_name: str) -> List[FeedbackTrigger]:
        """
        Generate optimization triggers based on feedback analysis.
        
        Args:
            domain_name: Domain to analyze
            
        Returns:
            List of optimization triggers
        """
        analysis = self.analyze_feedback_patterns(domain_name)
        triggers = []
        
        # Rating decline trigger
        if analysis.average_rating < 3.0 and analysis.total_feedback_count >= 5:
            trigger = FeedbackTrigger(
                trigger_id=str(uuid.uuid4()),
                domain_name=domain_name,
                trigger_type='rating_decline',
                severity='high' if analysis.average_rating < 2.0 else 'medium',
                feedback_evidence=[],  # Would include specific feedback IDs
                suggested_optimizations=[
                    'chunk_size_adjustment',
                    'bridge_threshold_tuning',
                    'quality_improvement'
                ],
                created_at=datetime.now()
            )
            triggers.append(trigger)
        
        # Negative sentiment trigger
        if analysis.sentiment_score < self.analysis_config['negative_sentiment_threshold']:
            trigger = FeedbackTrigger(
                trigger_id=str(uuid.uuid4()),
                domain_name=domain_name,
                trigger_type='negative_sentiment',
                severity='medium',
                feedback_evidence=[],
                suggested_optimizations=[
                    'content_quality_improvement',
                    'relevance_optimization'
                ],
                created_at=datetime.now()
            )
            triggers.append(trigger)
        
        # Issue spike triggers
        for issue_type, count in analysis.issue_categories.items():
            if count >= self.analysis_config['issue_spike_threshold']:
                trigger = FeedbackTrigger(
                    trigger_id=str(uuid.uuid4()),
                    domain_name=domain_name,
                    trigger_type='issue_spike',
                    severity='high' if count >= 5 else 'medium',
                    feedback_evidence=[],
                    suggested_optimizations=self._get_issue_specific_optimizations(issue_type),
                    created_at=datetime.now()
                )
                triggers.append(trigger)
        
        # Store triggers
        for trigger in triggers:
            self._store_feedback_trigger(trigger)
        
        return triggers
    
    def generate_feedback_driven_strategies(self, domain_name: str) -> List[OptimizationStrategy]:
        """
        Generate optimization strategies based on user feedback.
        
        Args:
            domain_name: Domain to optimize
            
        Returns:
            List of feedback-driven optimization strategies
        """
        analysis = self.analyze_feedback_patterns(domain_name)
        strategies = []
        
        # Strategy based on rating issues
        if analysis.average_rating < 3.5:
            if 'chunk_quality' in analysis.priority_issues:
                strategy = OptimizationStrategy(
                    type="feedback_driven_quality",
                    target_metrics=["chunk_quality_score", "user_satisfaction_score"],
                    adjustments={
                        "increase_quality_thresholds": True,
                        "enhance_validation": True,
                        "improve_boundary_detection": True
                    },
                    expected_improvement=0.2,
                    confidence=analysis.confidence_score
                )
                strategies.append(strategy)
            
            if 'relevance' in analysis.priority_issues:
                strategy = OptimizationStrategy(
                    type="feedback_driven_relevance",
                    target_metrics=["retrieval_effectiveness", "user_satisfaction_score"],
                    adjustments={
                        "improve_semantic_matching": True,
                        "enhance_context_preservation": True,
                        "optimize_embedding_generation": True
                    },
                    expected_improvement=0.15,
                    confidence=analysis.confidence_score
                )
                strategies.append(strategy)
        
        # Strategy based on specific issue categories
        if analysis.issue_categories.get('bridge_quality', 0) >= 3:
            strategy = OptimizationStrategy(
                type="feedback_driven_bridge_improvement",
                target_metrics=["bridge_success_rate", "user_satisfaction_score"],
                adjustments={
                    "lower_bridge_thresholds": True,
                    "improve_bridge_validation": True,
                    "enhance_contextual_bridging": True
                },
                expected_improvement=0.18,
                confidence=analysis.confidence_score
            )
            strategies.append(strategy)
        
        if analysis.issue_categories.get('processing_speed', 0) >= 2:
            strategy = OptimizationStrategy(
                type="feedback_driven_performance",
                target_metrics=["processing_efficiency", "user_satisfaction_score"],
                adjustments={
                    "enable_caching": True,
                    "optimize_batch_processing": True,
                    "reduce_validation_overhead": True
                },
                expected_improvement=0.12,
                confidence=analysis.confidence_score
            )
            strategies.append(strategy)
        
        return strategies
    
    def _check_immediate_triggers(self, feedback_data: UserFeedbackData) -> None:
        """Check for immediate optimization triggers from new feedback."""
        
        # Critical rating trigger
        if feedback_data.rating is not None and feedback_data.rating <= 1.5:
            logger.warning(f"Critical rating received for domain {feedback_data.domain_name}: "
                          f"{feedback_data.rating}/5.0")
            # Could trigger immediate optimization here
        
        # Negative sentiment trigger
        sentiment = feedback_data.get_sentiment_score()
        if sentiment < -0.7:
            logger.warning(f"Highly negative feedback for domain {feedback_data.domain_name}: "
                          f"sentiment={sentiment:.3f}")
    
    def _get_domain_feedback(self, domain_name: str, cutoff_date: datetime) -> List[UserFeedbackData]:
        """Get feedback data for a domain within the analysis window."""
        try:
            with get_database_connection() as conn:
                cursor = conn.cursor()
                
                query = """
                SELECT feedback_id, chunk_id, user_id, interaction_type,
                       feedback_score, context_query, timestamp
                FROM interaction_feedback
                WHERE timestamp >= %s
                ORDER BY timestamp DESC
                """
                
                cursor.execute(query, (cutoff_date,))
                results = cursor.fetchall()
                
                feedback_data = []
                for row in results:
                    # Filter by domain name (simplified - in practice would need better domain mapping)
                    feedback = UserFeedbackData(
                        feedback_id=row[0],
                        user_id=row[2],
                        domain_name=domain_name,  # Simplified
                        feedback_type=row[3],
                        rating=row[4] if row[4] != 0.0 else None,
                        feedback_text=row[5] or "",
                        affected_components=[],
                        chunk_ids=[row[1]] if row[1] else [],
                        timestamp=row[6],
                        processed=True
                    )
                    feedback_data.append(feedback)
                
                return feedback_data
        
        except Exception as e:
            logger.error(f"Failed to get domain feedback: {e}")
            return []
    
    def _analyze_overall_sentiment(self, feedback_data: List[UserFeedbackData]) -> float:
        """Analyze overall sentiment from feedback text."""
        if not feedback_data:
            return 0.0
        
        sentiment_scores = []
        
        for feedback in feedback_data:
            if feedback.feedback_text:
                score = self._calculate_text_sentiment(feedback.feedback_text)
                sentiment_scores.append(score)
            
            # Also consider rating as sentiment indicator
            if feedback.rating is not None:
                # Convert 1-5 rating to -1 to 1 sentiment
                rating_sentiment = (feedback.rating - 3.0) / 2.0
                sentiment_scores.append(rating_sentiment)
        
        return np.mean(sentiment_scores) if sentiment_scores else 0.0
    
    def _calculate_text_sentiment(self, text: str) -> float:
        """Calculate sentiment score from text using keyword analysis."""
        text_lower = text.lower()
        
        positive_count = sum(1 for word in self.sentiment_keywords['positive'] if word in text_lower)
        negative_count = sum(1 for word in self.sentiment_keywords['negative'] if word in text_lower)
        neutral_count = sum(1 for word in self.sentiment_keywords['neutral'] if word in text_lower)
        
        total_sentiment_words = positive_count + negative_count + neutral_count
        
        if total_sentiment_words == 0:
            return 0.0
        
        # Calculate weighted sentiment score
        sentiment_score = (positive_count - negative_count) / total_sentiment_words
        return max(-1.0, min(1.0, sentiment_score))
    
    def _categorize_issues(self, feedback_data: List[UserFeedbackData]) -> Dict[str, int]:
        """Categorize issues mentioned in feedback."""
        issue_counts = defaultdict(int)
        
        for feedback in feedback_data:
            if not feedback.feedback_text:
                continue
            
            text_lower = feedback.feedback_text.lower()
            
            for issue_category, patterns in self.issue_patterns.items():
                for pattern in patterns:
                    if re.search(pattern, text_lower, re.IGNORECASE):
                        issue_counts[issue_category] += 1
                        break  # Count each feedback only once per category
        
        return dict(issue_counts)
    
    def _generate_improvement_suggestions(self, issue_categories: Dict[str, int],
                                        average_rating: float, sentiment_score: float) -> List[str]:
        """Generate improvement suggestions based on feedback analysis."""
        suggestions = []
        
        # Rating-based suggestions
        if average_rating < 2.5:
            suggestions.append("Urgent: Address fundamental quality issues")
        elif average_rating < 3.5:
            suggestions.append("Focus on improving overall user satisfaction")
        
        # Sentiment-based suggestions
        if sentiment_score < -0.5:
            suggestions.append("Address negative user sentiment through quality improvements")
        
        # Issue-specific suggestions
        for issue_type, count in issue_categories.items():
            if count >= 3:
                if issue_type == 'chunk_quality':
                    suggestions.append("Improve chunk quality through better boundary detection")
                elif issue_type == 'relevance':
                    suggestions.append("Enhance relevance scoring and content matching")
                elif issue_type == 'completeness':
                    suggestions.append("Ensure complete information preservation in chunks")
                elif issue_type == 'bridge_quality':
                    suggestions.append("Improve bridge generation and validation")
                elif issue_type == 'processing_speed':
                    suggestions.append("Optimize processing performance and response times")
                elif issue_type == 'search_results':
                    suggestions.append("Enhance search and retrieval capabilities")
        
        return suggestions[:5]  # Limit to top 5 suggestions
    
    def _identify_priority_issues(self, issue_categories: Dict[str, int],
                                feedback_data: List[UserFeedbackData]) -> List[str]:
        """Identify priority issues based on frequency and severity."""
        
        # Weight issues by frequency and severity
        issue_priorities = {}
        
        for issue_type, count in issue_categories.items():
            # Base priority on frequency
            priority_score = count
            
            # Adjust for severity based on ratings
            related_ratings = []
            for feedback in feedback_data:
                if feedback.rating is not None and feedback.feedback_text:
                    text_lower = feedback.feedback_text.lower()
                    for pattern in self.issue_patterns.get(issue_type, []):
                        if re.search(pattern, text_lower, re.IGNORECASE):
                            related_ratings.append(feedback.rating)
                            break
            
            if related_ratings:
                avg_rating = np.mean(related_ratings)
                # Lower ratings increase priority
                severity_multiplier = (5.0 - avg_rating) / 4.0
                priority_score *= severity_multiplier
            
            issue_priorities[issue_type] = priority_score
        
        # Return top 3 priority issues
        sorted_issues = sorted(issue_priorities.items(), key=lambda x: x[1], reverse=True)
        return [issue for issue, score in sorted_issues[:3] if score > 1.0]
    
    def _get_issue_specific_optimizations(self, issue_type: str) -> List[str]:
        """Get optimization strategies specific to an issue type."""
        optimization_map = {
            'chunk_quality': ['chunk_size_adjustment', 'boundary_optimization', 'quality_validation'],
            'relevance': ['semantic_matching_improvement', 'context_preservation', 'embedding_optimization'],
            'completeness': ['chunk_overlap_adjustment', 'information_preservation', 'boundary_refinement'],
            'bridge_quality': ['bridge_threshold_tuning', 'bridge_validation_improvement', 'contextual_bridging'],
            'processing_speed': ['performance_optimization', 'caching_implementation', 'batch_processing'],
            'search_results': ['retrieval_optimization', 'ranking_improvement', 'query_processing']
        }
        
        return optimization_map.get(issue_type, ['general_optimization'])
    
    def _store_feedback_analysis(self, analysis: FeedbackAnalysis) -> None:
        """Store feedback analysis results in database."""
        try:
            with get_database_connection() as conn:
                cursor = conn.cursor()
                
                # Create table if it doesn't exist
                create_table_query = """
                CREATE TABLE IF NOT EXISTS feedback_analyses (
                    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                    domain_name VARCHAR(100) NOT NULL,
                    total_feedback_count INTEGER,
                    average_rating FLOAT,
                    sentiment_score FLOAT,
                    issue_categories JSONB,
                    improvement_suggestions TEXT[],
                    priority_issues TEXT[],
                    confidence_score FLOAT,
                    analysis_timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
                """
                cursor.execute(create_table_query)
                
                insert_query = """
                INSERT INTO feedback_analyses 
                (domain_name, total_feedback_count, average_rating, sentiment_score,
                 issue_categories, improvement_suggestions, priority_issues, 
                 confidence_score, analysis_timestamp)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                """
                
                cursor.execute(insert_query, (
                    analysis.domain_name, analysis.total_feedback_count,
                    analysis.average_rating, analysis.sentiment_score,
                    json.dumps(analysis.issue_categories), analysis.improvement_suggestions,
                    analysis.priority_issues, analysis.confidence_score,
                    analysis.analysis_timestamp
                ))
                
                conn.commit()
        
        except Exception as e:
            logger.error(f"Failed to store feedback analysis: {e}")
    
    def _store_feedback_trigger(self, trigger: FeedbackTrigger) -> None:
        """Store feedback trigger in database."""
        try:
            with get_database_connection() as conn:
                cursor = conn.cursor()
                
                # Create table if it doesn't exist
                create_table_query = """
                CREATE TABLE IF NOT EXISTS feedback_triggers (
                    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                    trigger_id VARCHAR(100) UNIQUE NOT NULL,
                    domain_name VARCHAR(100) NOT NULL,
                    trigger_type VARCHAR(50) NOT NULL,
                    severity VARCHAR(20) NOT NULL,
                    feedback_evidence TEXT[],
                    suggested_optimizations TEXT[],
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    processed BOOLEAN DEFAULT FALSE
                )
                """
                cursor.execute(create_table_query)
                
                insert_query = """
                INSERT INTO feedback_triggers 
                (trigger_id, domain_name, trigger_type, severity, feedback_evidence,
                 suggested_optimizations, created_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                """
                
                cursor.execute(insert_query, (
                    trigger.trigger_id, trigger.domain_name, trigger.trigger_type,
                    trigger.severity, trigger.feedback_evidence,
                    trigger.suggested_optimizations, trigger.created_at
                ))
                
                conn.commit()
        
        except Exception as e:
            logger.error(f"Failed to store feedback trigger: {e}")