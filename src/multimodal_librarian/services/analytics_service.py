"""
Analytics Service for Document and Chat Insights

This service provides comprehensive analytics for document processing,
content analysis, and user interaction patterns.
"""

import logging
from typing import Dict, List, Any, Optional
from datetime import datetime, timedelta
from collections import defaultdict, Counter
import json

from ..services.upload_service_mock import UploadServiceMock
from ..models.documents import Document, DocumentStatus

logger = logging.getLogger(__name__)


class AnalyticsService:
    """
    Service for generating analytics and insights about documents and usage.
    
    Provides statistics, content analysis, and user interaction metrics.
    """
    
    def __init__(self, upload_service: Optional[UploadServiceMock] = None):
        """Initialize analytics service."""
        self.upload_service = upload_service or UploadServiceMock()
    
    async def get_document_statistics(self, user_id: str = "default_user") -> Dict[str, Any]:
        """
        Get comprehensive document processing statistics.
        
        Args:
            user_id: User identifier for filtering
            
        Returns:
            Dictionary with document statistics
        """
        try:
            # Add timeout protection and error handling
            import asyncio
            
            # Get all user documents with timeout
            try:
                doc_list = await asyncio.wait_for(
                    self.upload_service.list_documents(
                        user_id=user_id,
                        page_size=1000  # Get all documents
                    ),
                    timeout=5.0  # 5 second timeout
                )
            except asyncio.TimeoutError:
                logger.warning(f"Document list timeout for user {user_id}, returning empty statistics")
                return self._empty_statistics()
            except Exception as e:
                logger.warning(f"Document list error for user {user_id}: {e}, returning empty statistics")
                return self._empty_statistics()
            
            documents = doc_list.documents
            total_count = len(documents)
            
            if total_count == 0:
                return self._empty_statistics()
            
            # Calculate basic statistics
            total_size = sum(doc.file_size for doc in documents)
            avg_size = total_size / total_count if total_count > 0 else 0
            
            # Status distribution
            status_counts = Counter(doc.status.value for doc in documents)
            
            # File type distribution
            file_types = Counter(
                doc.filename.split('.')[-1].lower() if '.' in doc.filename else 'unknown'
                for doc in documents
            )
            
            # Upload timeline (last 30 days)
            now = datetime.utcnow()
            thirty_days_ago = now - timedelta(days=30)
            
            recent_uploads = [
                doc for doc in documents 
                if doc.upload_timestamp >= thirty_days_ago
            ]
            
            # Daily upload counts
            daily_uploads = defaultdict(int)
            for doc in recent_uploads:
                day_key = doc.upload_timestamp.strftime('%Y-%m-%d')
                daily_uploads[day_key] += 1
            
            # Size distribution
            size_ranges = {
                'small': 0,      # < 1MB
                'medium': 0,     # 1MB - 10MB
                'large': 0,      # 10MB - 50MB
                'xlarge': 0      # > 50MB
            }
            
            for doc in documents:
                size_mb = doc.file_size / (1024 * 1024)
                if size_mb < 1:
                    size_ranges['small'] += 1
                elif size_mb < 10:
                    size_ranges['medium'] += 1
                elif size_mb < 50:
                    size_ranges['large'] += 1
                else:
                    size_ranges['xlarge'] += 1
            
            return {
                'overview': {
                    'total_documents': total_count,
                    'total_size_bytes': total_size,
                    'total_size_mb': round(total_size / (1024 * 1024), 2),
                    'average_size_mb': round(avg_size / (1024 * 1024), 2),
                    'recent_uploads_30d': len(recent_uploads)
                },
                'status_distribution': dict(status_counts),
                'file_type_distribution': dict(file_types),
                'size_distribution': size_ranges,
                'upload_timeline': dict(daily_uploads),
                'generated_at': now.isoformat()
            }
            
        except Exception as e:
            logger.error(f"Error generating document statistics: {e}")
            return self._empty_statistics()
    
    async def get_content_insights(self, user_id: str = "default_user") -> Dict[str, Any]:
        """
        Generate content summaries and key insights from documents.
        
        Args:
            user_id: User identifier for filtering
            
        Returns:
            Dictionary with content insights
        """
        try:
            # Add timeout protection
            import asyncio
            
            # Get all user documents with timeout
            try:
                doc_list = await asyncio.wait_for(
                    self.upload_service.list_documents(
                        user_id=user_id,
                        page_size=1000
                    ),
                    timeout=5.0  # 5 second timeout
                )
            except asyncio.TimeoutError:
                logger.warning(f"Document list timeout for user {user_id}, returning empty insights")
                return self._empty_content_insights()
            except Exception as e:
                logger.warning(f"Document list error for user {user_id}: {e}, returning empty insights")
                return self._empty_content_insights()
            
            documents = doc_list.documents
            
            if not documents:
                return self._empty_content_insights()
            
            # Analyze document titles and descriptions
            title_words = []
            description_words = []
            
            for doc in documents:
                if doc.title:
                    title_words.extend(self._extract_keywords(doc.title))
                if doc.description:
                    description_words.extend(self._extract_keywords(doc.description))
            
            # Most common keywords
            title_keywords = Counter(title_words).most_common(10)
            description_keywords = Counter(description_words).most_common(10)
            
            # Document categories (based on file types and keywords)
            categories = self._categorize_documents(documents)
            
            # Content quality metrics
            quality_metrics = self._analyze_content_quality(documents)
            
            return {
                'content_overview': {
                    'total_documents': len(documents),
                    'documents_with_descriptions': sum(1 for doc in documents if doc.description),
                    'avg_title_length': self._avg_length([doc.title for doc in documents if doc.title]),
                    'avg_description_length': self._avg_length([doc.description for doc in documents if doc.description])
                },
                'top_keywords': {
                    'titles': title_keywords,
                    'descriptions': description_keywords
                },
                'document_categories': categories,
                'quality_metrics': quality_metrics,
                'generated_at': datetime.utcnow().isoformat()
            }
            
        except Exception as e:
            logger.error(f"Error generating content insights: {e}")
            return self._empty_content_insights()
    
    async def get_similarity_analysis(self, user_id: str = "default_user") -> Dict[str, Any]:
        """
        Analyze document similarity and create content clusters.
        
        Args:
            user_id: User identifier for filtering
            
        Returns:
            Dictionary with similarity analysis
        """
        try:
            # Add timeout protection
            import asyncio
            
            # Get all user documents with timeout
            try:
                doc_list = await asyncio.wait_for(
                    self.upload_service.list_documents(
                        user_id=user_id,
                        page_size=1000
                    ),
                    timeout=5.0  # 5 second timeout
                )
            except asyncio.TimeoutError:
                logger.warning(f"Document list timeout for user {user_id}, returning empty similarity analysis")
                return self._empty_similarity_analysis()
            except Exception as e:
                logger.warning(f"Document list error for user {user_id}: {e}, returning empty similarity analysis")
                return self._empty_similarity_analysis()
            
            documents = doc_list.documents
            
            if len(documents) < 2:
                return self._empty_similarity_analysis()
            
            # Simple similarity analysis based on titles and descriptions
            similarity_pairs = []
            clusters = self._create_simple_clusters(documents)
            
            # Find similar documents
            for i, doc1 in enumerate(documents):
                for j, doc2 in enumerate(documents[i+1:], i+1):
                    similarity_score = self._calculate_text_similarity(
                        f"{doc1.title} {doc1.description or ''}",
                        f"{doc2.title} {doc2.description or ''}"
                    )
                    
                    if similarity_score > 0.3:  # Threshold for similarity
                        similarity_pairs.append({
                            'document1': {
                                'id': doc1.id,
                                'title': doc1.title,
                                'filename': doc1.filename
                            },
                            'document2': {
                                'id': doc2.id,
                                'title': doc2.title,
                                'filename': doc2.filename
                            },
                            'similarity_score': round(similarity_score, 3)
                        })
            
            # Sort by similarity score
            similarity_pairs.sort(key=lambda x: x['similarity_score'], reverse=True)
            
            return {
                'similarity_overview': {
                    'total_documents': len(documents),
                    'similar_pairs_found': len(similarity_pairs),
                    'clusters_identified': len(clusters)
                },
                'similar_documents': similarity_pairs[:20],  # Top 20 similar pairs
                'content_clusters': clusters,
                'generated_at': datetime.utcnow().isoformat()
            }
            
        except Exception as e:
            logger.error(f"Error generating similarity analysis: {e}")
            return self._empty_similarity_analysis()
    
    async def get_usage_analytics(self, user_id: str = "default_user") -> Dict[str, Any]:
        """
        Generate usage analytics for chat and document interactions.
        
        Args:
            user_id: User identifier for filtering
            
        Returns:
            Dictionary with usage analytics
        """
        try:
            # Mock usage data (in production, this would come from actual logs)
            now = datetime.utcnow()
            
            # Simulate some usage patterns
            mock_chat_sessions = 15
            mock_document_views = 45
            mock_search_queries = 28
            
            # Generate mock daily activity for last 7 days
            daily_activity = {}
            for i in range(7):
                date = (now - timedelta(days=i)).strftime('%Y-%m-%d')
                daily_activity[date] = {
                    'chat_messages': max(0, 10 + (i * 2) + (i % 3)),
                    'document_uploads': max(0, 2 + (i % 2)),
                    'search_queries': max(0, 5 + (i * 1.5))
                }
            
            # Popular features
            feature_usage = {
                'document_upload': 85,
                'chat_interactions': 92,
                'document_search': 67,
                'rag_queries': 78,
                'document_management': 56
            }
            
            return {
                'usage_overview': {
                    'total_chat_sessions': mock_chat_sessions,
                    'total_document_views': mock_document_views,
                    'total_search_queries': mock_search_queries,
                    'avg_session_duration_minutes': 12.5,
                    'most_active_day': max(daily_activity.keys(), key=lambda k: daily_activity[k]['chat_messages'])
                },
                'daily_activity': daily_activity,
                'feature_usage_percentage': feature_usage,
                'user_engagement': {
                    'return_user': True,
                    'engagement_score': 78,
                    'preferred_features': ['chat_interactions', 'document_upload', 'rag_queries']
                },
                'generated_at': now.isoformat()
            }
            
        except Exception as e:
            logger.error(f"Error generating usage analytics: {e}")
            return {
                'usage_overview': {},
                'daily_activity': {},
                'feature_usage_percentage': {},
                'user_engagement': {},
                'generated_at': datetime.utcnow().isoformat()
            }
    
    def _empty_statistics(self) -> Dict[str, Any]:
        """Return empty statistics structure."""
        return {
            'overview': {
                'total_documents': 0,
                'total_size_bytes': 0,
                'total_size_mb': 0,
                'average_size_mb': 0,
                'recent_uploads_30d': 0
            },
            'status_distribution': {},
            'file_type_distribution': {},
            'size_distribution': {'small': 0, 'medium': 0, 'large': 0, 'xlarge': 0},
            'upload_timeline': {},
            'generated_at': datetime.utcnow().isoformat()
        }
    
    def _empty_content_insights(self) -> Dict[str, Any]:
        """Return empty content insights structure."""
        return {
            'content_overview': {
                'total_documents': 0,
                'documents_with_descriptions': 0,
                'avg_title_length': 0,
                'avg_description_length': 0
            },
            'top_keywords': {'titles': [], 'descriptions': []},
            'document_categories': {},
            'quality_metrics': {},
            'generated_at': datetime.utcnow().isoformat()
        }
    
    def _empty_similarity_analysis(self) -> Dict[str, Any]:
        """Return empty similarity analysis structure."""
        return {
            'similarity_overview': {
                'total_documents': 0,
                'similar_pairs_found': 0,
                'clusters_identified': 0
            },
            'similar_documents': [],
            'content_clusters': {},
            'generated_at': datetime.utcnow().isoformat()
        }
    
    def _extract_keywords(self, text: str) -> List[str]:
        """Extract keywords from text."""
        if not text:
            return []
        
        # Simple keyword extraction (remove common words)
        stop_words = {'the', 'a', 'an', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for', 'of', 'with', 'by', 'is', 'are', 'was', 'were', 'be', 'been', 'being', 'have', 'has', 'had', 'do', 'does', 'did', 'will', 'would', 'could', 'should'}
        
        words = text.lower().split()
        keywords = [word.strip('.,!?;:"()[]{}') for word in words if len(word) > 2 and word.lower() not in stop_words]
        
        return keywords
    
    def _avg_length(self, texts: List[str]) -> float:
        """Calculate average length of texts."""
        if not texts:
            return 0.0
        return sum(len(text) for text in texts) / len(texts)
    
    def _categorize_documents(self, documents: List[Document]) -> Dict[str, int]:
        """Categorize documents based on file types and content."""
        categories = defaultdict(int)
        
        for doc in documents:
            # Categorize by file extension
            if doc.filename:
                ext = doc.filename.split('.')[-1].lower() if '.' in doc.filename else 'unknown'
                if ext == 'pdf':
                    categories['PDF Documents'] += 1
                elif ext in ['txt', 'md']:
                    categories['Text Files'] += 1
                elif ext in ['doc', 'docx']:
                    categories['Word Documents'] += 1
                else:
                    categories['Other Files'] += 1
            
            # Categorize by content keywords
            content = f"{doc.title} {doc.description or ''}".lower()
            if any(word in content for word in ['report', 'analysis', 'study']):
                categories['Reports & Analysis'] += 1
            elif any(word in content for word in ['manual', 'guide', 'documentation']):
                categories['Documentation'] += 1
            elif any(word in content for word in ['research', 'paper', 'article']):
                categories['Research Papers'] += 1
        
        return dict(categories)
    
    def _analyze_content_quality(self, documents: List[Document]) -> Dict[str, Any]:
        """Analyze content quality metrics."""
        if not documents:
            return {}
        
        # Quality indicators
        has_description = sum(1 for doc in documents if doc.description and len(doc.description.strip()) > 10)
        has_meaningful_title = sum(1 for doc in documents if doc.title and len(doc.title.strip()) > 5)
        
        return {
            'description_coverage': round((has_description / len(documents)) * 100, 1),
            'meaningful_titles': round((has_meaningful_title / len(documents)) * 100, 1),
            'avg_title_words': round(sum(len(doc.title.split()) for doc in documents if doc.title) / len(documents), 1),
            'content_richness_score': round(((has_description + has_meaningful_title) / (len(documents) * 2)) * 100, 1)
        }
    
    def _create_simple_clusters(self, documents: List[Document]) -> Dict[str, List[str]]:
        """Create simple content clusters based on keywords."""
        clusters = defaultdict(list)
        
        for doc in documents:
            content = f"{doc.title} {doc.description or ''}".lower()
            
            # Simple clustering based on common themes
            if any(word in content for word in ['machine', 'learning', 'ai', 'artificial']):
                clusters['AI & Machine Learning'].append(doc.title)
            elif any(word in content for word in ['business', 'strategy', 'management']):
                clusters['Business & Strategy'].append(doc.title)
            elif any(word in content for word in ['technical', 'engineering', 'development']):
                clusters['Technical Documentation'].append(doc.title)
            elif any(word in content for word in ['research', 'study', 'analysis']):
                clusters['Research & Analysis'].append(doc.title)
            else:
                clusters['General Documents'].append(doc.title)
        
        return dict(clusters)
    
    def _calculate_text_similarity(self, text1: str, text2: str) -> float:
        """Calculate simple text similarity based on common words."""
        if not text1 or not text2:
            return 0.0
        
        words1 = set(self._extract_keywords(text1))
        words2 = set(self._extract_keywords(text2))
        
        if not words1 or not words2:
            return 0.0
        
        intersection = len(words1.intersection(words2))
        union = len(words1.union(words2))
        
        return intersection / union if union > 0 else 0.0


# Service instance
_analytics_service_instance = None

def get_analytics_service() -> AnalyticsService:
    """Get analytics service instance."""
    global _analytics_service_instance
    if _analytics_service_instance is None:
        _analytics_service_instance = AnalyticsService()
    return _analytics_service_instance