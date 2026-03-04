"""
Query Processing Component for Multimodal Librarian.

This module implements unified knowledge query processing with conversation context,
unified search across books and conversation knowledge, and multi-source content
aggregation with equal priority for all knowledge sources.
"""

import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from ...models.core import (
    ContentType,
    ConversationThread,
    KnowledgeChunk,
    KnowledgeCitation,
    Message,
    MessageType,
    SourceType,
)
from ...models.knowledge_graph import KnowledgeGraphQueryResult, ReasoningPath

# Import search models first to avoid circular imports
from ...models.search_types import SearchResult
from ..conversation.conversation_manager import ConversationContext, ConversationManager
from ..kg_retrieval.query_decomposer import QueryDecomposer
from ..knowledge_graph.kg_query_engine import KnowledgeGraphQueryEngine
from ..vector_store.search_service import SemanticSearchService

logger = logging.getLogger(__name__)


@dataclass
class QueryContext:
    """Context information for query processing."""
    conversation_thread: Optional[ConversationThread] = None
    recent_messages: List[Message] = field(default_factory=list)
    user_id: Optional[str] = None
    session_id: Optional[str] = None
    query_history: List[str] = field(default_factory=list)
    preferred_sources: List[SourceType] = field(default_factory=list)
    domain_context: List[str] = field(default_factory=list)


@dataclass
class ProcessedQuery:
    """Processed query with enhanced metadata."""
    original_query: str
    processed_query: str
    query_intent: str  # factual, procedural, comparative, conversational
    key_concepts: List[str]
    context_keywords: List[str]
    conversation_context: Optional[str] = None
    temporal_context: Optional[datetime] = None
    
    @classmethod
    def from_raw_query(cls, query: str, context: Optional[QueryContext] = None) -> 'ProcessedQuery':
        """Create ProcessedQuery from raw query text with context analysis."""
        processed = cls._preprocess_query(query)
        intent = cls._classify_query_intent(query)
        concepts = cls._extract_key_concepts(processed)
        keywords = cls._extract_context_keywords(query, context)
        
        conversation_context = None
        if context and context.recent_messages:
            conversation_context = cls._build_conversation_context(context.recent_messages)
        
        return cls(
            original_query=query,
            processed_query=processed,
            query_intent=intent,
            key_concepts=concepts,
            context_keywords=keywords,
            conversation_context=conversation_context,
            temporal_context=datetime.now()
        )
    
    @staticmethod
    def _preprocess_query(query: str) -> str:
        """Preprocess query for better understanding."""
        # Basic preprocessing
        query = query.strip()
        
        # Expand contractions
        contractions = {
            "what's": "what is",
            "how's": "how is", 
            "where's": "where is",
            "when's": "when is",
            "why's": "why is",
            "can't": "cannot",
            "won't": "will not",
            "don't": "do not",
            "doesn't": "does not",
            "haven't": "have not",
            "hasn't": "has not",
            "wouldn't": "would not",
            "couldn't": "could not",
            "shouldn't": "should not"
        }
        
        query_lower = query.lower()
        for contraction, expansion in contractions.items():
            query_lower = query_lower.replace(contraction, expansion)
        
        return query_lower
    
    @staticmethod
    def _classify_query_intent(query: str) -> str:
        """Classify the intent of the query."""
        query_lower = query.lower()
        
        # Factual queries
        if any(pattern in query_lower for pattern in [
            'what is', 'what are', 'define', 'definition', 'meaning of', 'explain'
        ]):
            return 'factual'
        
        # Procedural queries
        elif any(pattern in query_lower for pattern in [
            'how to', 'how do', 'how can', 'steps to', 'process of', 'method'
        ]):
            return 'procedural'
        
        # Comparative queries
        elif any(pattern in query_lower for pattern in [
            'compare', 'difference', 'versus', 'vs', 'better than', 'similar to'
        ]):
            return 'comparative'
        
        # Conversational queries (follow-up questions)
        elif any(pattern in query_lower for pattern in [
            'also', 'additionally', 'furthermore', 'what about', 'and', 'but'
        ]):
            return 'conversational'
        
        else:
            return 'general'
    
    @staticmethod
    def _extract_key_concepts(query: str) -> List[str]:
        """Extract key concepts from the query."""
        # Simple concept extraction - could be enhanced with NLP
        import re

        # Remove stop words
        stop_words = {
            'the', 'a', 'an', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for',
            'of', 'with', 'by', 'is', 'are', 'was', 'were', 'be', 'been', 'being',
            'have', 'has', 'had', 'do', 'does', 'did', 'will', 'would', 'could',
            'should', 'may', 'might', 'can', 'what', 'how', 'when', 'where', 'why',
            'this', 'that', 'these', 'those', 'i', 'you', 'he', 'she', 'it', 'we', 'they'
        }
        
        # Extract words and filter
        words = re.findall(r'\b\w+\b', query.lower())
        concepts = [word for word in words if word not in stop_words and len(word) > 2]
        
        # Extract phrases (simple bigrams)
        phrases = []
        for i in range(len(words) - 1):
            if words[i] not in stop_words and words[i+1] not in stop_words:
                phrase = f"{words[i]} {words[i+1]}"
                if len(phrase) > 5:  # Minimum phrase length
                    phrases.append(phrase)
        
        return concepts + phrases[:5]  # Limit phrases
    
    @staticmethod
    def _extract_context_keywords(query: str, context: Optional[QueryContext]) -> List[str]:
        """Extract context keywords that might help with search."""
        keywords = []
        
        # Domain-specific keywords
        domain_patterns = {
            'technical': ['algorithm', 'code', 'programming', 'software', 'system', 'api', 'database'],
            'medical': ['patient', 'treatment', 'diagnosis', 'medical', 'health', 'disease', 'symptom'],
            'legal': ['law', 'legal', 'court', 'contract', 'regulation', 'compliance', 'statute'],
            'academic': ['research', 'study', 'analysis', 'theory', 'methodology', 'paper', 'journal'],
            'business': ['strategy', 'market', 'revenue', 'customer', 'sales', 'profit', 'business']
        }
        
        query_lower = query.lower()
        for domain, terms in domain_patterns.items():
            if any(term in query_lower for term in terms):
                keywords.append(f"domain:{domain}")
        
        # Context from conversation
        if context and context.domain_context:
            keywords.extend([f"context:{ctx}" for ctx in context.domain_context])
        
        return keywords
    
    @staticmethod
    def _build_conversation_context(messages: List[Message]) -> str:
        """Build conversation context from recent messages."""
        context_parts = []
        
        # Get last few user messages for context
        user_messages = [msg for msg in messages if msg.message_type == MessageType.USER][-3:]
        
        for msg in user_messages:
            # Truncate long messages
            content = msg.content[:100] + "..." if len(msg.content) > 100 else msg.content
            context_parts.append(content)
        
        return " | ".join(context_parts)


@dataclass
class UnifiedSearchResult:
    """Unified search result combining multiple sources."""
    chunks: List[KnowledgeChunk]
    citations: List[KnowledgeCitation]
    source_distribution: Dict[SourceType, int]
    reasoning_paths: List[ReasoningPath] = field(default_factory=list)
    total_results: int = 0
    search_metadata: Dict[str, Any] = field(default_factory=dict)


class UnifiedKnowledgeQueryProcessor:
    """
    Unified knowledge query processor that searches across all knowledge sources.
    
    This processor implements query preprocessing with conversation context,
    unified search across books and conversation knowledge, and multi-source
    content aggregation with equal priority for all knowledge sources.
    """
    
    def __init__(self, 
                 search_service: SemanticSearchService,
                 conversation_manager: ConversationManager,
                 kg_query_engine: Optional[KnowledgeGraphQueryEngine] = None,
                 query_decomposer: Optional[QueryDecomposer] = None):
        """
        Initialize the unified knowledge query processor.
        
        Args:
            search_service: Semantic search service for vector operations
            conversation_manager: Conversation manager for context
            kg_query_engine: Optional knowledge graph query engine
            query_decomposer: Optional QueryDecomposer for concept extraction
        """
        self.search_service = search_service
        self.conversation_manager = conversation_manager
        self.kg_query_engine = kg_query_engine
        self.query_decomposer = query_decomposer
        
        # Query processing statistics
        self.query_stats = {
            'total_queries': 0,
            'book_queries': 0,
            'conversation_queries': 0,
            'unified_queries': 0,
            'kg_enhanced_queries': 0,
            'average_response_time': 0.0
        }
        
        logger.info("Initialized UnifiedKnowledgeQueryProcessor")
    
    def process_query(self, 
                     query: str,
                     context: Optional[QueryContext] = None,
                     max_results: int = 20,
                     include_reasoning: bool = True) -> UnifiedSearchResult:
        """
        Process query with unified search across all knowledge sources.
        
        Args:
            query: User query text
            context: Optional query context with conversation info
            max_results: Maximum number of results to return
            include_reasoning: Whether to include knowledge graph reasoning
            
        Returns:
            UnifiedSearchResult with aggregated results from all sources
        """
        start_time = datetime.now()
        
        try:
            # Process the query
            processed_query = ProcessedQuery.from_raw_query(query, context)
            logger.info(f"Processing {processed_query.query_intent} query: {query[:50]}...")
            
            # Perform unified search
            search_result = self._perform_unified_search(processed_query, context, max_results)
            
            # Enhance with knowledge graph reasoning if available
            if include_reasoning and self.query_decomposer:
                search_result = self._enhance_with_reasoning(search_result, processed_query)
            
            # Update statistics
            self._update_query_stats(processed_query, start_time)
            
            logger.info(f"Unified query returned {search_result.total_results} results from {len(search_result.source_distribution)} source types")
            return search_result
            
        except Exception as e:
            logger.error(f"Query processing failed: {e}")
            # Return empty result on error
            return UnifiedSearchResult(
                chunks=[],
                citations=[],
                source_distribution={},
                total_results=0,
                search_metadata={'error': str(e)}
            )
    
    def process_conversational_query(self,
                                   query: str,
                                   thread_id: str,
                                   max_results: int = 15) -> UnifiedSearchResult:
        """
        Process query with full conversation context.
        
        Args:
            query: User query text
            thread_id: Conversation thread ID for context
            max_results: Maximum number of results to return
            
        Returns:
            UnifiedSearchResult with conversation-aware results
        """
        try:
            # Get conversation context
            conversation = self.conversation_manager.get_conversation(thread_id)
            if not conversation:
                logger.warning(f"Conversation {thread_id} not found")
                return self.process_query(query, max_results=max_results)
            
            # Build query context
            context = QueryContext(
                conversation_thread=conversation,
                recent_messages=conversation.messages[-10:],  # Last 10 messages
                user_id=conversation.user_id,
                query_history=[msg.content for msg in conversation.messages 
                             if msg.message_type == MessageType.USER][-5:],  # Last 5 user queries
                domain_context=self._extract_domain_context(conversation)
            )
            
            # Process with conversation context
            result = self.process_query(query, context, max_results)
            
            # Update statistics
            self.query_stats['conversation_queries'] += 1
            
            return result
            
        except Exception as e:
            logger.error(f"Conversational query processing failed: {e}")
            return self.process_query(query, max_results=max_results)
    
    def search_across_sources(self,
                            query: str,
                            source_weights: Optional[Dict[SourceType, float]] = None,
                            content_type_filter: Optional[ContentType] = None,
                            max_results: int = 20) -> UnifiedSearchResult:
        """
        Search across knowledge sources with configurable weighting.
        
        Args:
            query: Search query
            source_weights: Optional weights for different source types
            content_type_filter: Optional filter by content type
            max_results: Maximum results to return
            
        Returns:
            UnifiedSearchResult with weighted results
        """
        try:
            # Default equal weighting
            if source_weights is None:
                source_weights = {
                    SourceType.BOOK: 1.0,
                    SourceType.CONVERSATION: 1.0
                }
            
            all_chunks = []
            all_citations = []
            source_distribution = {}
            
            # Search each source type
            for source_type, weight in source_weights.items():
                if weight <= 0:
                    continue
                
                # Calculate results for this source
                source_results = int(max_results * weight / sum(source_weights.values()))
                
                # Perform source-specific search
                if source_type == SourceType.BOOK:
                    results = self.search_service.search_books_only(
                        query, 
                        top_k=source_results,
                        content_type=content_type_filter
                    )
                elif source_type == SourceType.CONVERSATION:
                    results = self.search_service.search_conversations_only(
                        query,
                        top_k=source_results
                    )
                else:
                    continue
                
                # Convert to knowledge chunks and citations
                for result in results:
                    chunk = self._search_result_to_chunk(result)
                    citation = self._search_result_to_citation(result)
                    
                    all_chunks.append(chunk)
                    all_citations.append(citation)
                
                source_distribution[source_type] = len(results)
            
            # Sort by relevance score
            combined_results = list(zip(all_chunks, all_citations))
            combined_results.sort(key=lambda x: x[1].relevance_score, reverse=True)
            
            # Limit to max_results
            combined_results = combined_results[:max_results]
            final_chunks, final_citations = zip(*combined_results) if combined_results else ([], [])
            
            return UnifiedSearchResult(
                chunks=list(final_chunks),
                citations=list(final_citations),
                source_distribution=source_distribution,
                total_results=len(final_chunks),
                search_metadata={
                    'source_weights': source_weights,
                    'content_type_filter': content_type_filter.value if content_type_filter else None
                }
            )
            
        except Exception as e:
            logger.error(f"Multi-source search failed: {e}")
            return UnifiedSearchResult(
                chunks=[],
                citations=[],
                source_distribution={},
                total_results=0,
                search_metadata={'error': str(e)}
            )
    
    def _perform_unified_search(self,
                              processed_query: ProcessedQuery,
                              context: Optional[QueryContext],
                              max_results: int) -> UnifiedSearchResult:
        """Perform unified search across all knowledge sources."""
        
        # Determine search strategy based on query intent and context
        if processed_query.query_intent == 'conversational' and context and context.recent_messages:
            # Boost conversation sources for conversational queries
            source_weights = {SourceType.CONVERSATION: 0.6, SourceType.BOOK: 0.4}
        else:
            # Equal weighting for other query types
            source_weights = {SourceType.CONVERSATION: 0.5, SourceType.BOOK: 0.5}
        
        # Perform weighted search
        result = self.search_across_sources(
            processed_query.processed_query,
            source_weights=source_weights,
            max_results=max_results
        )
        
        # Add query metadata
        result.search_metadata.update({
            'query_intent': processed_query.query_intent,
            'key_concepts': processed_query.key_concepts,
            'context_keywords': processed_query.context_keywords,
            'conversation_context': processed_query.conversation_context
        })
        
        # Update statistics
        self.query_stats['unified_queries'] += 1
        
        return result
    
    def _enhance_with_reasoning(self,
                              search_result: UnifiedSearchResult,
                              processed_query: ProcessedQuery) -> UnifiedSearchResult:
        """Enhance search results with knowledge graph reasoning."""
        try:
            if not self.query_decomposer:
                return search_result
            
            # Use QueryDecomposer for concept extraction
            import asyncio
            try:
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    # Cannot run async in already-running loop
                    import concurrent.futures
                    with concurrent.futures.ThreadPoolExecutor() as pool:
                        decomposition = pool.submit(
                            asyncio.run,
                            self.query_decomposer.decompose(
                                processed_query.original_query
                            )
                        ).result()
                else:
                    decomposition = loop.run_until_complete(
                        self.query_decomposer.decompose(
                            processed_query.original_query
                        )
                    )
            except RuntimeError:
                decomposition = asyncio.run(
                    self.query_decomposer.decompose(
                        processed_query.original_query
                    )
                )
            
            concept_names = [
                m.get('name', '')
                for m in decomposition.concept_matches[:5]
                if m.get('name')
            ]
            
            # Use KG_Query_Engine for re-ranking with pre-extracted concepts
            if self.kg_query_engine and concept_names:
                enhanced_chunks = self.kg_query_engine.enhance_vector_search(
                    processed_query.original_query,
                    search_result.chunks,
                    concept_names
                )
                search_result.chunks = enhanced_chunks
            
            # Update metadata
            search_result.search_metadata.update({
                'kg_enhanced': True,
                'concept_count': len(concept_names),
                'has_kg_matches': decomposition.has_kg_matches,
            })
            
            self.query_stats['kg_enhanced_queries'] += 1
            
        except Exception as e:
            logger.warning(f"KG enhancement failed: {e}")
        
        return search_result
    
    def _search_result_to_chunk(self, search_result: SearchResult) -> KnowledgeChunk:
        """Convert SearchResult to KnowledgeChunk."""
        return KnowledgeChunk(
            id=search_result.chunk_id,
            content=search_result.content,
            source_type=search_result.source_type,
            source_id=search_result.source_id,
            location_reference=search_result.location_reference,
            section=search_result.section,
            content_type=search_result.content_type
        )
    
    def _search_result_to_citation(self, search_result: SearchResult) -> KnowledgeCitation:
        """Convert SearchResult to KnowledgeCitation."""
        return KnowledgeCitation(
            source_type=search_result.source_type,
            source_title=search_result.source_id,  # Would be enhanced with actual title
            location_reference=search_result.location_reference,
            chunk_id=search_result.chunk_id,
            relevance_score=search_result.relevance_score
        )
    
    def _extract_domain_context(self, conversation: ConversationThread) -> List[str]:
        """Extract domain context from conversation history."""
        domain_keywords = []
        
        # Analyze recent messages for domain indicators
        recent_content = " ".join([
            msg.content for msg in conversation.messages[-10:]
            if msg.message_type in [MessageType.USER, MessageType.SYSTEM]
        ]).lower()
        
        # Domain detection patterns
        domain_patterns = {
            'technical': ['code', 'programming', 'software', 'algorithm', 'api', 'database', 'system'],
            'medical': ['health', 'medical', 'patient', 'treatment', 'diagnosis', 'disease'],
            'legal': ['law', 'legal', 'court', 'contract', 'regulation', 'compliance'],
            'academic': ['research', 'study', 'analysis', 'theory', 'methodology', 'paper'],
            'business': ['business', 'market', 'strategy', 'revenue', 'customer', 'sales']
        }
        
        for domain, keywords in domain_patterns.items():
            if any(keyword in recent_content for keyword in keywords):
                domain_keywords.append(domain)
        
        return domain_keywords[:3]  # Limit to top 3 domains
    
    def _update_query_stats(self, processed_query: ProcessedQuery, start_time: datetime):
        """Update query processing statistics."""
        end_time = datetime.now()
        response_time = (end_time - start_time).total_seconds()
        
        self.query_stats['total_queries'] += 1
        
        # Update average response time
        total_queries = self.query_stats['total_queries']
        current_avg = self.query_stats['average_response_time']
        self.query_stats['average_response_time'] = (
            (current_avg * (total_queries - 1) + response_time) / total_queries
        )
    
    def get_query_statistics(self) -> Dict[str, Any]:
        """Get query processing statistics."""
        return self.query_stats.copy()
    
    def reset_statistics(self):
        """Reset query processing statistics."""
        self.query_stats = {
            'total_queries': 0,
            'book_queries': 0,
            'conversation_queries': 0,
            'unified_queries': 0,
            'kg_enhanced_queries': 0,
            'average_response_time': 0.0
        }