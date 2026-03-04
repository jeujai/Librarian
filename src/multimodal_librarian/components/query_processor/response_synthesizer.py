"""
Response Synthesis Component for Multimodal Librarian.

This module implements response synthesis functionality with OpenAI GPT-4 API integration,
unified citation tracking for books and conversation knowledge, and coherent response
generation from all knowledge sources.
"""

import logging
import uuid
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass, field
from datetime import datetime
import json

# Optional OpenAI import
try:
    import openai
    OPENAI_AVAILABLE = True
except ImportError:
    OPENAI_AVAILABLE = False
    openai = None

from ...models.core import (
    KnowledgeChunk, KnowledgeCitation, MultimediaResponse, SourceType,
    Visualization, AudioFile, VideoFile, ExportMetadata
)
from ...models.knowledge_graph import ReasoningPath
from .query_processor import UnifiedSearchResult, ProcessedQuery, QueryContext

logger = logging.getLogger(__name__)


@dataclass
class SynthesisContext:
    """Context for response synthesis."""
    query: str
    processed_query: ProcessedQuery
    search_results: UnifiedSearchResult
    query_context: Optional[QueryContext] = None
    synthesis_preferences: Dict[str, Any] = field(default_factory=dict)
    max_response_length: int = 2000
    include_citations: bool = True
    citation_style: str = "inline"  # inline, footnote, bibliography


@dataclass
class CitationTracker:
    """Tracks citations across all knowledge sources."""
    citations: List[KnowledgeCitation] = field(default_factory=list)
    source_counts: Dict[SourceType, int] = field(default_factory=dict)
    citation_map: Dict[str, int] = field(default_factory=dict)  # chunk_id -> citation_number
    
    def add_citation(self, citation: KnowledgeCitation) -> int:
        """Add a citation and return its number."""
        # Check if citation already exists
        for i, existing_citation in enumerate(self.citations):
            if existing_citation.chunk_id == citation.chunk_id:
                return i + 1
        
        # Add new citation
        self.citations.append(citation)
        citation_number = len(self.citations)
        self.citation_map[citation.chunk_id] = citation_number
        
        # Update source counts
        source_type = citation.source_type
        self.source_counts[source_type] = self.source_counts.get(source_type, 0) + 1
        
        return citation_number
    
    def get_citation_number(self, chunk_id: str) -> Optional[int]:
        """Get citation number for a chunk."""
        return self.citation_map.get(chunk_id)
    
    def get_citations_by_source(self, source_type: SourceType) -> List[KnowledgeCitation]:
        """Get all citations from a specific source type."""
        return [citation for citation in self.citations if citation.source_type == source_type]
    
    def format_citations(self, style: str = "inline") -> str:
        """Format citations according to specified style."""
        if not self.citations:
            return ""
        
        if style == "inline":
            return self._format_inline_citations()
        elif style == "footnote":
            return self._format_footnote_citations()
        elif style == "bibliography":
            return self._format_bibliography_citations()
        else:
            return self._format_inline_citations()
    
    def _format_inline_citations(self) -> str:
        """Format citations as inline references."""
        citation_parts = []
        
        for i, citation in enumerate(self.citations, 1):
            source_type_str = "Book" if citation.source_type == SourceType.BOOK else "Conversation"
            citation_parts.append(f"[{i}] {source_type_str}: {citation.source_title}, {citation.location_reference}")
        
        return "\n".join(citation_parts)
    
    def _format_footnote_citations(self) -> str:
        """Format citations as footnotes."""
        citation_parts = []
        
        for i, citation in enumerate(self.citations, 1):
            source_type_str = "Book" if citation.source_type == SourceType.BOOK else "Conversation"
            citation_parts.append(f"{i}. {source_type_str}: {citation.source_title} ({citation.location_reference})")
        
        return "\n".join(citation_parts)
    
    def _format_bibliography_citations(self) -> str:
        """Format citations as bibliography."""
        # Group by source type
        book_citations = self.get_citations_by_source(SourceType.BOOK)
        conversation_citations = self.get_citations_by_source(SourceType.CONVERSATION)
        
        bibliography_parts = []
        
        if book_citations:
            bibliography_parts.append("Books:")
            for citation in book_citations:
                bibliography_parts.append(f"  • {citation.source_title} ({citation.location_reference})")
        
        if conversation_citations:
            bibliography_parts.append("Conversations:")
            for citation in conversation_citations:
                bibliography_parts.append(f"  • {citation.source_title} ({citation.location_reference})")
        
        return "\n".join(bibliography_parts)


class ResponseSynthesizer:
    """
    Response synthesis component with OpenAI GPT-4 integration.
    
    This component integrates with OpenAI GPT-4 API for conversational text generation,
    creates unified citation tracking for books and conversation knowledge, and
    implements coherent response generation from all knowledge sources.
    """
    
    def __init__(self, openai_api_key: Optional[str] = None):
        """
        Initialize the response synthesizer.
        
        Args:
            openai_api_key: OpenAI API key for GPT-4 access
        """
        if openai_api_key and OPENAI_AVAILABLE:
            openai.api_key = openai_api_key
        elif openai_api_key and not OPENAI_AVAILABLE:
            logger.warning("OpenAI API key provided but openai package not installed")
        
        # Synthesis statistics
        self.synthesis_stats = {
            'total_responses': 0,
            'book_citations': 0,
            'conversation_citations': 0,
            'reasoning_enhanced_responses': 0,
            'average_response_length': 0,
            'average_citations_per_response': 0.0
        }
        
        logger.info("Initialized ResponseSynthesizer")
    
    def synthesize_response(self, 
                          synthesis_context: SynthesisContext) -> MultimediaResponse:
        """
        Generate coherent response from all knowledge sources.
        
        Args:
            synthesis_context: Context for response synthesis
            
        Returns:
            MultimediaResponse with synthesized content and citations
        """
        try:
            # Initialize citation tracker
            citation_tracker = CitationTracker()
            
            # Prepare knowledge context for synthesis
            knowledge_context = self._prepare_knowledge_context(
                synthesis_context.search_results,
                citation_tracker
            )
            
            # Generate response using GPT-4
            response_text = self._generate_response_with_gpt4(
                synthesis_context,
                knowledge_context,
                citation_tracker
            )
            
            # Create multimedia response
            multimedia_response = MultimediaResponse(
                text_content=response_text,
                knowledge_citations=citation_tracker.citations,
                export_metadata=ExportMetadata(
                    export_format="text",
                    created_at=datetime.now(),
                    file_size=len(response_text.encode('utf-8')),
                    includes_media=False
                )
            )
            
            # Update statistics
            self._update_synthesis_stats(multimedia_response, citation_tracker)
            
            logger.info(f"Synthesized response with {len(citation_tracker.citations)} citations")
            return multimedia_response
            
        except Exception as e:
            logger.error(f"Response synthesis failed: {e}")
            # Return error response
            return MultimediaResponse(
                text_content=f"I apologize, but I encountered an error while processing your query: {str(e)}",
                knowledge_citations=[],
                export_metadata=ExportMetadata(
                    export_format="text",
                    created_at=datetime.now()
                )
            )
    
    def synthesize_conversational_response(self,
                                         query: str,
                                         search_results: UnifiedSearchResult,
                                         conversation_context: Optional[str] = None,
                                         max_length: int = 1500) -> MultimediaResponse:
        """
        Generate conversational response with context awareness.
        
        Args:
            query: User query
            search_results: Unified search results
            conversation_context: Optional conversation context
            max_length: Maximum response length
            
        Returns:
            MultimediaResponse optimized for conversational flow
        """
        # Create synthesis context for conversational response
        processed_query = ProcessedQuery.from_raw_query(query)
        
        synthesis_context = SynthesisContext(
            query=query,
            processed_query=processed_query,
            search_results=search_results,
            max_response_length=max_length,
            synthesis_preferences={
                'conversational_tone': True,
                'context_aware': True,
                'conversation_context': conversation_context
            }
        )
        
        return self.synthesize_response(synthesis_context)
    
    def synthesize_multi_source_response(self,
                                       query: str,
                                       search_results: UnifiedSearchResult,
                                       emphasize_sources: bool = True) -> MultimediaResponse:
        """
        Generate response that explicitly highlights multiple knowledge sources.
        
        Args:
            query: User query
            search_results: Unified search results
            emphasize_sources: Whether to emphasize source diversity
            
        Returns:
            MultimediaResponse with explicit source attribution
        """
        processed_query = ProcessedQuery.from_raw_query(query)
        
        synthesis_context = SynthesisContext(
            query=query,
            processed_query=processed_query,
            search_results=search_results,
            synthesis_preferences={
                'emphasize_sources': emphasize_sources,
                'source_diversity': True,
                'explicit_attribution': True
            },
            citation_style="bibliography"
        )
        
        return self.synthesize_response(synthesis_context)
    
    def _prepare_knowledge_context(self,
                                 search_results: UnifiedSearchResult,
                                 citation_tracker: CitationTracker) -> str:
        """Prepare knowledge context from search results."""
        context_parts = []
        
        # Group chunks by source type for balanced representation
        book_chunks = [chunk for chunk in search_results.chunks if chunk.source_type == SourceType.BOOK]
        conversation_chunks = [chunk for chunk in search_results.chunks if chunk.source_type == SourceType.CONVERSATION]
        
        # Add book knowledge
        if book_chunks:
            context_parts.append("=== BOOK KNOWLEDGE ===")
            for chunk in book_chunks[:10]:  # Limit to top 10
                citation_num = citation_tracker.add_citation(
                    KnowledgeCitation(
                        source_type=chunk.source_type,
                        source_title=chunk.source_id,
                        location_reference=chunk.location_reference,
                        chunk_id=chunk.id,
                        relevance_score=0.8  # Default relevance
                    )
                )
                context_parts.append(f"[{citation_num}] {chunk.content}")
        
        # Add conversation knowledge
        if conversation_chunks:
            context_parts.append("\n=== CONVERSATION KNOWLEDGE ===")
            for chunk in conversation_chunks[:10]:  # Limit to top 10
                citation_num = citation_tracker.add_citation(
                    KnowledgeCitation(
                        source_type=chunk.source_type,
                        source_title=f"Conversation {chunk.source_id[:8]}",
                        location_reference=chunk.location_reference,
                        chunk_id=chunk.id,
                        relevance_score=0.8  # Default relevance
                    )
                )
                context_parts.append(f"[{citation_num}] {chunk.content}")
        
        # Add reasoning paths if available
        if search_results.reasoning_paths:
            context_parts.append("\n=== REASONING PATHS ===")
            for i, path in enumerate(search_results.reasoning_paths[:3]):  # Top 3 paths
                context_parts.append(f"Path {i+1}: {path.get_path_description()}")
        
        return "\n".join(context_parts)
    
    def _generate_response_with_gpt4(self,
                                   synthesis_context: SynthesisContext,
                                   knowledge_context: str,
                                   citation_tracker: CitationTracker) -> str:
        """Generate response using GPT-4 API."""
        try:
            if not OPENAI_AVAILABLE:
                logger.warning("OpenAI not available, using fallback response generation")
                return self._generate_fallback_response(synthesis_context, citation_tracker)
            
            # Build system prompt
            system_prompt = self._build_system_prompt(synthesis_context)
            
            # Build user prompt with knowledge context
            user_prompt = self._build_user_prompt(
                synthesis_context.query,
                knowledge_context,
                synthesis_context
            )
            
            # Call GPT-4 API
            response = openai.ChatCompletion.create(
                model="gpt-4",
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                max_tokens=synthesis_context.max_response_length,
                temperature=0.7,
                top_p=0.9
            )
            
            response_text = response.choices[0].message.content.strip()
            
            # Add citations if requested
            if synthesis_context.include_citations:
                citations_text = citation_tracker.format_citations(synthesis_context.citation_style)
                if citations_text:
                    response_text += f"\n\n**Sources:**\n{citations_text}"
            
            return response_text
            
        except Exception as e:
            logger.error(f"GPT-4 API call failed: {e}")
            # Fallback to template-based response
            return self._generate_fallback_response(synthesis_context, citation_tracker)
    
    def _build_system_prompt(self, synthesis_context: SynthesisContext) -> str:
        """Build system prompt for GPT-4."""
        base_prompt = """You are a knowledgeable AI assistant that synthesizes information from multiple sources including books and conversation history. Your task is to provide accurate, comprehensive, and well-cited responses.

Key guidelines:
1. Synthesize information from ALL provided sources equally
2. Maintain factual accuracy and cite sources using the provided citation numbers
3. Provide balanced perspectives when sources offer different viewpoints
4. Use clear, engaging language appropriate for the query type
5. Reference both book knowledge and conversation knowledge when relevant
6. When using information, include the citation number in brackets [1], [2], etc."""
        
        # Add context-specific instructions
        preferences = synthesis_context.synthesis_preferences
        
        if preferences.get('conversational_tone'):
            base_prompt += "\n7. Use a conversational, friendly tone that builds on previous discussion"
        
        if preferences.get('emphasize_sources'):
            base_prompt += "\n8. Explicitly mention when information comes from different types of sources (books vs conversations)"
        
        if preferences.get('source_diversity'):
            base_prompt += "\n9. Highlight the diversity of knowledge sources and how they complement each other"
        
        return base_prompt
    
    def _build_user_prompt(self,
                         query: str,
                         knowledge_context: str,
                         synthesis_context: SynthesisContext) -> str:
        """Build user prompt with query and knowledge context."""
        prompt_parts = []
        
        # Add conversation context if available
        if synthesis_context.query_context and synthesis_context.query_context.conversation_thread:
            conversation_context = synthesis_context.synthesis_preferences.get('conversation_context')
            if conversation_context:
                prompt_parts.append(f"Previous conversation context: {conversation_context}")
        
        # Add the main query
        prompt_parts.append(f"User Query: {query}")
        
        # Add knowledge context
        prompt_parts.append(f"Available Knowledge:\n{knowledge_context}")
        
        # Add specific instructions based on query intent
        if synthesis_context.processed_query.query_intent == 'comparative':
            prompt_parts.append("Please provide a comparative analysis using the available sources.")
        elif synthesis_context.processed_query.query_intent == 'procedural':
            prompt_parts.append("Please provide step-by-step guidance based on the available information.")
        elif synthesis_context.processed_query.query_intent == 'conversational':
            prompt_parts.append("Please respond in a conversational manner that builds on the previous discussion.")
        
        prompt_parts.append("Please synthesize a comprehensive response using the provided knowledge sources.")
        
        return "\n\n".join(prompt_parts)
    
    def _generate_fallback_response(self,
                                  synthesis_context: SynthesisContext,
                                  citation_tracker: CitationTracker) -> str:
        """Generate fallback response when GPT-4 is unavailable."""
        logger.warning("Using fallback response generation")
        
        # Simple template-based response
        response_parts = []
        
        response_parts.append(f"Based on the available knowledge sources, here's what I found regarding your query: \"{synthesis_context.query}\"")
        
        # Add information from top chunks
        top_chunks = synthesis_context.search_results.chunks[:3]
        for chunk in top_chunks:
            citation_num = citation_tracker.get_citation_number(chunk.id)
            if citation_num:
                # Extract first sentence or first 100 characters
                content_preview = chunk.content[:200] + "..." if len(chunk.content) > 200 else chunk.content
                response_parts.append(f"According to source [{citation_num}]: {content_preview}")
        
        # Add source summary
        source_dist = synthesis_context.search_results.source_distribution
        if len(source_dist) > 1:
            response_parts.append(f"This information comes from {sum(source_dist.values())} sources across {len(source_dist)} different types of knowledge.")
        
        # Add citations
        if synthesis_context.include_citations:
            citations_text = citation_tracker.format_citations(synthesis_context.citation_style)
            if citations_text:
                response_parts.append(f"\n**Sources:**\n{citations_text}")
        
        return "\n\n".join(response_parts)
    
    def _update_synthesis_stats(self,
                              response: MultimediaResponse,
                              citation_tracker: CitationTracker):
        """Update synthesis statistics."""
        self.synthesis_stats['total_responses'] += 1
        
        # Count citations by source type
        book_citations = len(citation_tracker.get_citations_by_source(SourceType.BOOK))
        conversation_citations = len(citation_tracker.get_citations_by_source(SourceType.CONVERSATION))
        
        self.synthesis_stats['book_citations'] += book_citations
        self.synthesis_stats['conversation_citations'] += conversation_citations
        
        # Update averages
        total_responses = self.synthesis_stats['total_responses']
        
        # Average response length
        response_length = len(response.text_content)
        current_avg_length = self.synthesis_stats['average_response_length']
        self.synthesis_stats['average_response_length'] = (
            (current_avg_length * (total_responses - 1) + response_length) / total_responses
        )
        
        # Average citations per response
        total_citations = len(citation_tracker.citations)
        current_avg_citations = self.synthesis_stats['average_citations_per_response']
        self.synthesis_stats['average_citations_per_response'] = (
            (current_avg_citations * (total_responses - 1) + total_citations) / total_responses
        )
    
    def get_synthesis_statistics(self) -> Dict[str, Any]:
        """Get response synthesis statistics."""
        return self.synthesis_stats.copy()
    
    def reset_statistics(self):
        """Reset synthesis statistics."""
        self.synthesis_stats = {
            'total_responses': 0,
            'book_citations': 0,
            'conversation_citations': 0,
            'reasoning_enhanced_responses': 0,
            'average_response_length': 0,
            'average_citations_per_response': 0.0
        }


class UnifiedResponseGenerator:
    """
    Unified response generator that combines query processing and response synthesis.
    
    This class provides a high-level interface for generating responses from queries
    by combining the query processor and response synthesizer components.
    """
    
    def __init__(self,
                 query_processor,  # UnifiedKnowledgeQueryProcessor
                 response_synthesizer: ResponseSynthesizer):
        """
        Initialize the unified response generator.
        
        Args:
            query_processor: Unified knowledge query processor
            response_synthesizer: Response synthesizer component
        """
        self.query_processor = query_processor
        self.response_synthesizer = response_synthesizer
        
        logger.info("Initialized UnifiedResponseGenerator")
    
    def generate_response(self,
                        query: str,
                        context: Optional[QueryContext] = None,
                        max_results: int = 15,
                        max_response_length: int = 2000) -> MultimediaResponse:
        """
        Generate complete response from query to final output.
        
        Args:
            query: User query
            context: Optional query context
            max_results: Maximum search results to consider
            max_response_length: Maximum response length
            
        Returns:
            MultimediaResponse with synthesized content
        """
        try:
            # Process query and get search results
            search_results = self.query_processor.process_query(
                query=query,
                context=context,
                max_results=max_results,
                include_reasoning=True
            )
            
            # Create synthesis context
            processed_query = ProcessedQuery.from_raw_query(query, context)
            synthesis_context = SynthesisContext(
                query=query,
                processed_query=processed_query,
                search_results=search_results,
                query_context=context,
                max_response_length=max_response_length
            )
            
            # Synthesize response
            response = self.response_synthesizer.synthesize_response(synthesis_context)
            
            logger.info(f"Generated unified response for query: {query[:50]}...")
            return response
            
        except Exception as e:
            logger.error(f"Unified response generation failed: {e}")
            return MultimediaResponse(
                text_content=f"I apologize, but I encountered an error while processing your query: {str(e)}",
                knowledge_citations=[],
                export_metadata=ExportMetadata(
                    export_format="text",
                    created_at=datetime.now()
                )
            )
    
    def generate_conversational_response(self,
                                       query: str,
                                       thread_id: str,
                                       max_response_length: int = 1500) -> MultimediaResponse:
        """
        Generate response with full conversational context.
        
        Args:
            query: User query
            thread_id: Conversation thread ID
            max_response_length: Maximum response length
            
        Returns:
            MultimediaResponse with conversational context
        """
        try:
            # Process conversational query
            search_results = self.query_processor.process_conversational_query(
                query=query,
                thread_id=thread_id,
                max_results=15
            )
            
            # Get conversation context
            conversation_context = None
            if hasattr(self.query_processor, 'conversation_manager'):
                conversation = self.query_processor.conversation_manager.get_conversation(thread_id)
                if conversation and conversation.messages:
                    recent_messages = conversation.messages[-5:]  # Last 5 messages
                    conversation_context = " | ".join([
                        msg.content[:100] for msg in recent_messages 
                        if msg.message_type == MessageType.USER
                    ])
            
            # Synthesize conversational response
            response = self.response_synthesizer.synthesize_conversational_response(
                query=query,
                search_results=search_results,
                conversation_context=conversation_context,
                max_length=max_response_length
            )
            
            return response
            
        except Exception as e:
            logger.error(f"Conversational response generation failed: {e}")
            return MultimediaResponse(
                text_content=f"I apologize, but I encountered an error while processing your conversational query: {str(e)}",
                knowledge_citations=[],
                export_metadata=ExportMetadata(
                    export_format="text",
                    created_at=datetime.now()
                )
            )