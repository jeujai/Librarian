"""
RAG Service - Retrieval-Augmented Generation for document-aware chat

This service implements the critical missing component that connects the existing
chat system with document knowledge using vector search and AI generation.
Enhanced with knowledge graph reasoning for improved context understanding.

Now supports optional KG-guided retrieval via KGRetrievalService for precise
chunk retrieval using Neo4j knowledge graph source_chunks pointers.
"""

import asyncio
import json
import logging
import re
import time
from dataclasses import dataclass
from datetime import datetime
from typing import (
    TYPE_CHECKING,
    Any,
    AsyncGenerator,
    Dict,
    List,
    Optional,
    Protocol,
    Tuple,
    runtime_checkable,
)
from uuid import uuid4

from ..components.kg_retrieval.query_decomposer import QueryDecomposer
from ..components.knowledge_graph.kg_builder import KnowledgeGraphBuilder
from ..components.knowledge_graph.kg_query_engine import KnowledgeGraphQueryEngine
from ..config import get_settings
from ..utils.text_utils import truncate_content
from .ai_service import AIResponse, AIService

# Runtime import for SearchSourceType — used by the post-processing phase
from .source_prioritization_engine import SearchSourceType

# Type checking imports for KG retrieval integration
if TYPE_CHECKING:
    from ..clients.searxng_client import SearXNGClient, SearXNGResult
    from ..models.kg_retrieval import KGRetrievalResult, RetrievedChunk
    from .kg_retrieval_service import KGRetrievalService
    from .source_prioritization_engine import (
        PrioritizedSearchResults,
        SourcePrioritizationEngine,
    )

# Import VectorStoreClient protocol for type hints
# This allows RAGService to work with both Milvus and OpenSearch
try:
    from ..clients.protocols import VectorStoreClient
except ImportError:
    # Fallback if protocols not available
    @runtime_checkable
    class VectorStoreClient(Protocol):
        async def semantic_search(self, query: str, top_k: int = 10, filters: Any = None) -> List[Dict[str, Any]]: ...
        async def connect(self) -> None: ...
        def is_connected(self) -> bool: ...

logger = logging.getLogger(__name__)

@dataclass
class DocumentChunk:
    """Document chunk with metadata."""
    chunk_id: str
    document_id: str
    document_title: str
    content: str
    page_number: Optional[int] = None
    section_title: Optional[str] = None
    chunk_type: str = "text"
    similarity_score: float = 0.0
    metadata: Dict[str, Any] = None
    source_type: Optional[str] = None  # "librarian", "web_search", or "llm_fallback"
    
    def __post_init__(self):
        if self.metadata is None:
            self.metadata = {}

@dataclass
class CitationSource:
    """Citation source information with excerpt.
    
    Attributes:
        document_id: Unique identifier for the source document
        document_title: Title of the source document
        page_number: Page number where the chunk is located (if available)
        chunk_id: Unique identifier for the chunk
        relevance_score: Relevance score from semantic search (0.0 to 1.0)
        excerpt: The actual chunk text content used as context
        section_title: Section title where the chunk is located (if available)
        content_truncated: True if the excerpt was truncated to fit max length
        excerpt_error: Error indicator if excerpt retrieval failed
        source_type: Source type for prioritization ("librarian", "web_search", "llm_fallback")
    """
    document_id: str
    document_title: str
    page_number: Optional[int]
    chunk_id: str
    relevance_score: float
    excerpt: str
    section_title: Optional[str] = None
    content_truncated: bool = False
    excerpt_error: Optional[str] = None
    source_type: Optional[str] = None  # "librarian", "web_search", or "llm_fallback"
    url: Optional[str] = None  # URL for web search sources

@dataclass
class RAGResponse:
    """RAG response with citations and metadata."""
    response: str
    sources: List[CitationSource]
    confidence_score: float
    processing_time_ms: int
    tokens_used: int
    search_results_count: int
    fallback_used: bool = False
    metadata: Dict[str, Any] = None
    
    def __post_init__(self):
        if self.metadata is None:
            self.metadata = {}


@dataclass
class RAGStreamingChunk:
    """A chunk of RAG streaming response.
    
    Used for progressive content delivery with citations upfront.
    """
    content: str
    is_final: bool
    citations: Optional[List[CitationSource]] = None
    confidence_score: float = 0.0
    processing_time_ms: int = 0
    tokens_used: int = 0
    search_results_count: int = 0
    fallback_used: bool = False
    metadata: Optional[Dict[str, Any]] = None

class QueryProcessor:
    """Process and enhance user queries for better retrieval using knowledge graph."""
    
    # Patterns that signal a query depends on prior conversation context
    _CONTEXT_DEPENDENT_PATTERNS = [
        re.compile(r'\b(it|its|this|that|these|those|they|them|their|theirs)\b', re.IGNORECASE),
        re.compile(r'\b(the same|above|previous|earlier|prior|aforementioned)\b', re.IGNORECASE),
        re.compile(r'\b(you (said|mentioned|told|explained|described|noted))\b', re.IGNORECASE),
        re.compile(r'\b(more about|tell me more|go on|continue|elaborate|expand on)\b', re.IGNORECASE),
        re.compile(r'\bwhat about\b', re.IGNORECASE),
        re.compile(r'\b(also|too|as well|in addition)\b', re.IGNORECASE),
        re.compile(r'\b(instead|rather|alternatively)\b', re.IGNORECASE),
        re.compile(r'\bwhy not\b', re.IGNORECASE),
    ]
    
    def __init__(self, ai_service: AIService, query_decomposer: Optional[QueryDecomposer] = None):
        self.ai_service = ai_service
        self.query_decomposer = query_decomposer
    
    @staticmethod
    def _needs_context_resolution(query: str) -> bool:
        """Check if a query contains unresolved references that need conversation context.
        
        Returns True for queries like "tell me more about that" or "why?"
        Returns False for self-contained queries like "What did our team observe in Chelsea?"
        """
        words = query.split()
        if len(words) < 4:
            return True  # Very short queries are likely follow-ups
        
        for pattern in QueryProcessor._CONTEXT_DEPENDENT_PATTERNS:
            if pattern.search(query):
                return True
        
        return False
    
    async def process_query(
        self, 
        query: str, 
        conversation_context: Optional[List[Dict[str, str]]] = None
    ) -> Tuple[str, List[str], Dict[str, Any]]:
        """
        Process and enhance user query using knowledge graph reasoning.
        
        Args:
            query: Original user query
            conversation_context: Recent conversation messages
            
        Returns:
            Tuple of (enhanced_query, related_concepts, kg_metadata)
            kg_metadata includes '_decomposition' key with the raw
            QueryDecomposition object for downstream reuse.
        """
        try:
            kg_metadata = {}
            related_concepts = []
            
            # Step 1: Extract concepts via QueryDecomposer
            if self.query_decomposer:
                try:
                    decomposition = await self.query_decomposer.decompose(query)
                    
                    # Map concept_matches to name strings (top 5)
                    related_concepts = [
                        m.get('name', '')
                        for m in decomposition.concept_matches[:5]
                        if m.get('name')
                    ]
                    
                    # Construct kg_metadata from decomposition
                    kg_metadata = {
                        "related_concepts": len(decomposition.concept_matches),
                        "has_kg_matches": decomposition.has_kg_matches,
                        "match_types": list({
                            m.get('match_type', 'unknown')
                            for m in decomposition.concept_matches
                        }),
                        "entities": decomposition.entities[:5],
                        # Stash the full decomposition for downstream reuse
                        # (avoids redundant decomposition in KG retrieval)
                        "_decomposition": decomposition,
                    }
                    
                    logger.info(f"QueryDecomposer found {len(related_concepts)} related concepts for query")
                    
                except Exception as e:
                    logger.warning(f"QueryDecomposer failed: {e}")
            
            # Step 2: Enhance query with AI only if it needs context resolution
            enhanced_query = query
            if (conversation_context and len(conversation_context) > 1
                    and self._needs_context_resolution(query)):
                context_text = "\n".join([
                    f"{msg['role']}: {msg['content']}" 
                    for msg in conversation_context[-3:]  # Last 3 messages
                ])
                
                # Include related concepts in enhancement prompt
                concept_hint = ""
                if related_concepts:
                    concept_hint = f"\nRelated concepts to consider: {', '.join(related_concepts)}"
                
                enhancement_prompt = [
                    {
                        "role": "user",
                        "content": f"""Given this conversation context:
{context_text}

Please enhance this search query to better find relevant documents: "{query}"{concept_hint}

Return only the enhanced query, no explanation. Keep it concise and focused on key concepts."""
                    }
                ]
                
                try:
                    response = await self.ai_service.generate_response(
                        messages=enhancement_prompt,
                        temperature=0.3,
                        max_tokens=100
                    )
                    enhanced_query = response.content.strip().strip('"')
                    
                    # Use enhanced query if it's reasonable
                    if len(enhanced_query) > 0 and len(enhanced_query) < len(query) * 2:
                        logger.info(f"Enhanced query: '{query}' -> '{enhanced_query}'")
                    else:
                        enhanced_query = query
                except Exception as e:
                    logger.warning(f"Query enhancement failed: {e}")
                    enhanced_query = query
            
            return enhanced_query, related_concepts, kg_metadata
            
        except Exception as e:
            logger.error(f"Query processing failed: {e}")
            return query, [], {}

class ContextPreparer:
    """Prepare and rank document context for AI generation."""
    
    def __init__(self, max_context_length: int = 8000):
        self.max_context_length = max_context_length
    
    def prepare_context(
        self, 
        chunks: List[DocumentChunk],
        query: str,
        max_chunks: int = 10
    ) -> Tuple[str, List[CitationSource]]:
        """
        Prepare context from document chunks with intelligent ranking.
        
        Args:
            chunks: Retrieved document chunks
            query: Original user query
            max_chunks: Maximum number of chunks to include
            
        Returns:
            Tuple of (formatted_context, citation_sources)
        """
        if not chunks:
            return "", []
        
        # Rank chunks by relevance and diversity
        ranked_chunks = self._rank_chunks(chunks, query)
        
        # Select chunks within context length limit
        selected_chunks = self._select_chunks_by_length(ranked_chunks[:max_chunks])
        
        # Format context
        context_parts = []
        citations = []
        
        for i, chunk in enumerate(selected_chunks, 1):
            # Truncate excerpt content and track if truncation occurred
            excerpt_text = ""
            content_truncated = False
            excerpt_error = None
            
            if chunk.content:
                # Strip [Page N] markers — internal extraction artifacts
                excerpt_text = re.sub(r'\[Page\s+\d+\]', '', chunk.content).strip()
            else:
                excerpt_error = "not_found"
            
            # Create citation source with truncation info and source type
            citation = CitationSource(
                document_id=chunk.document_id,
                document_title=chunk.document_title,
                page_number=chunk.page_number,
                chunk_id=chunk.chunk_id,
                relevance_score=chunk.similarity_score,
                excerpt=excerpt_text,
                section_title=chunk.section_title,
                content_truncated=content_truncated,
                excerpt_error=excerpt_error,
                source_type=chunk.source_type,  # Include source type (Requirement 5.5)
                url=chunk.metadata.get('url') if chunk.metadata else None,
            )
            citations.append(citation)
            
            # Format context entry
            source_info = f"[Source {i}: {chunk.document_title}"
            if chunk.page_number:
                source_info += f", Page {chunk.page_number}"
            if chunk.section_title:
                source_info += f", Section: {chunk.section_title}"
            source_info += "]"
            
            context_parts.append(f"{source_info}\n{chunk.content}")
        
        formatted_context = "\n\n---\n\n".join(context_parts)
        
        logger.info(f"Prepared context with {len(selected_chunks)} chunks, {len(formatted_context)} characters")
        
        return formatted_context, citations
    
    def _rank_chunks(self, chunks: List[DocumentChunk], query: str) -> List[DocumentChunk]:
        """Rank chunks by relevance and diversity."""
        # Sort by similarity score first
        chunks_by_score = sorted(chunks, key=lambda x: x.similarity_score, reverse=True)
        
        # Apply diversity filtering to avoid too many chunks from same document
        ranked_chunks = []
        document_counts = {}
        max_per_document = 3
        
        for chunk in chunks_by_score:
            doc_count = document_counts.get(chunk.document_id, 0)
            
            if doc_count < max_per_document:
                ranked_chunks.append(chunk)
                document_counts[chunk.document_id] = doc_count + 1
        
        return ranked_chunks
    
    def _select_chunks_by_length(self, chunks: List[DocumentChunk]) -> List[DocumentChunk]:
        """Select chunks that fit within context length limit."""
        selected = []
        current_length = 0
        
        for chunk in chunks:
            # Estimate length including formatting
            chunk_length = len(chunk.content) + 100  # Add overhead for formatting
            
            if current_length + chunk_length <= self.max_context_length:
                selected.append(chunk)
                current_length += chunk_length
            else:
                break
        
        return selected

class RAGService:
    """
    Main RAG service that connects chat with document knowledge.
    
    This is the critical missing component that enables document-aware responses
    by combining vector search with AI generation, enhanced with knowledge graph reasoning.
    
    Now supports optional KG-guided retrieval via KGRetrievalService for precise
    chunk retrieval using Neo4j knowledge graph source_chunks pointers.
    
    Requires dependency injection for OpenSearchClient and AIService, enabling:
    - Testability through mock injection
    - Lazy initialization via FastAPI DI
    - Graceful degradation when services unavailable
    
    Usage:
        # DI pattern (required):
        rag_service = RAGService(
            vector_client=injected_client,  # Works with Milvus or OpenSearch
            ai_service=injected_ai_service,
            kg_retrieval_service=injected_kg_service  # Optional
        )
        
        # Via FastAPI DI (recommended):
        from api.dependencies import get_rag_service
        async def endpoint(service = Depends(get_rag_service)):
            ...
    """
    
    def __init__(
        self,
        vector_client: VectorStoreClient = None,
        ai_service: AIService = None,
        kg_builder: Optional[KnowledgeGraphBuilder] = None,
        kg_query_engine: Optional[KnowledgeGraphQueryEngine] = None,
        kg_retrieval_service: Optional["KGRetrievalService"] = None,
        source_prioritization_engine: Optional["SourcePrioritizationEngine"] = None,
        query_decomposer: Optional["QueryDecomposer"] = None,
        searxng_client: Optional["SearXNGClient"] = None,
        # Legacy parameter for backward compatibility
        opensearch_client: Any = None
    ):
        """
        Initialize RAG service with dependency injection.
        
        Args:
            vector_client: VectorStoreClient instance (Milvus or OpenSearch).
            ai_service: AIService instance (required).
            kg_builder: Optional KnowledgeGraphBuilder instance. If None, creates new instance.
            kg_query_engine: Optional KnowledgeGraphQueryEngine instance. If None, creates new instance.
            kg_retrieval_service: Optional KGRetrievalService for KG-guided retrieval.
                                  When provided, enables two-stage retrieval using Neo4j
                                  source_chunks for precise chunk retrieval.
            source_prioritization_engine: Optional SourcePrioritizationEngine for
                                         prioritizing Librarian documents over external sources.
                                         Requirements: 5.1, 5.5, 5.6
            query_decomposer: Optional QueryDecomposer for concept extraction.
                              Replaces legacy KG_Query_Engine concept extraction.
                              Requirements: 2.1, 2.2, 2.3
            searxng_client: Optional SearXNGClient for supplementary web search.
                            When provided and enabled, web results supplement thin
                            Librarian results. Requirements: 5.3, 6.1, 6.2, 6.3
            opensearch_client: DEPRECATED - use vector_client instead. Kept for backward compatibility.
            
        Raises:
            ValueError: If vector_client/opensearch_client or ai_service is None.
        """
        # Support both new vector_client and legacy opensearch_client parameter
        self.vector_client = vector_client or opensearch_client
        
        if self.vector_client is None:
            raise ValueError("vector_client is required - use FastAPI DI to inject it")
        if ai_service is None:
            raise ValueError("ai_service is required - use FastAPI DI to inject it")
        
        # Use injected dependencies (required)
        self.ai_service = ai_service
        
        # Legacy alias for backward compatibility
        self.opensearch_client = self.vector_client
        
        # Initialize knowledge graph components
        self.kg_builder = kg_builder if kg_builder is not None else KnowledgeGraphBuilder()
        self.kg_query_engine = kg_query_engine if kg_query_engine is not None else KnowledgeGraphQueryEngine(self.kg_builder)
        
        # KG-guided retrieval service (optional, Requirement 7.2)
        self.kg_retrieval_service = kg_retrieval_service
        self.use_kg_retrieval = kg_retrieval_service is not None
        
        # Source prioritization engine (optional, Requirements 5.1, 5.5, 5.6)
        self.source_prioritization_engine = source_prioritization_engine
        self.use_source_prioritization = source_prioritization_engine is not None
        
        # QueryDecomposer for concept extraction (Requirements 2.1, 2.2, 2.3)
        self.query_decomposer = query_decomposer
        
        # Initialize processors — pass query_decomposer instead of kg_query_engine
        self.query_processor = QueryProcessor(self.ai_service, self.query_decomposer)
        self.context_preparer = ContextPreparer()
        self.settings = get_settings()
        
        # Configuration
        # Lower threshold to 0.35 to capture more relevant results
        # Semantic similarity scores are typically in 0.3-0.6 range for relevant content
        self.min_similarity_threshold = 0.35
        # Higher bar for deciding if librarian results are truly relevant.
        # Chunks between min_similarity (0.35) and this value are "noise" —
        # they passed the floor but shouldn't prevent web search fallback.
        # For Milvus L2 distance: 1/(1+d), scores ~0.36-0.45 are typical
        # for unrelated content; genuinely relevant content scores > 0.5.
        self.relevance_confidence_threshold = 0.5
        self.max_search_results = 15
        self.fallback_to_general_ai = True
        self.use_knowledge_graph = True  # Enable KG features
        
        # SearXNG / post-processing settings (Requirements 5.3, 6.1, 6.2, 6.3)
        self.searxng_client = searxng_client
        self.searxng_enabled: bool = searxng_client is not None
        self.librarian_boost_factor: float = self.settings.librarian_boost_factor
        self.web_search_result_count_threshold: int = self.settings.web_search_result_count_threshold
        self.searxng_max_results: int = self.settings.searxng_max_results
        
        if self.use_source_prioritization:
            logger.info("RAG Service initialized with source prioritization support")
        elif self.use_kg_retrieval:
            logger.info("RAG Service initialized with KG-guided retrieval support")
        else:
            logger.info("RAG Service initialized with knowledge graph support")
        
    async def generate_response(
        self,
        query: str,
        user_id: str,
        conversation_context: Optional[List[Dict[str, str]]] = None,
        document_filter: Optional[List[str]] = None,
        preferred_ai_provider: Optional[str] = None
    ) -> RAGResponse:
        """
        Generate document-aware response using RAG pipeline.
        
        Args:
            query: User query
            user_id: User identifier for document filtering
            conversation_context: Recent conversation messages
            document_filter: Optional list of specific document IDs to search
            preferred_ai_provider: Preferred AI provider
            
        Returns:
            RAG response with citations and metadata
        """
        start_time = time.time()
        
        try:
            # Step 1: Process and enhance query with knowledge graph
            processed_query, related_concepts, kg_metadata = await self.query_processor.process_query(
                query, conversation_context
            )
            
            # Step 2: Search for relevant document chunks with KG enhancement
            search_results = await self._search_documents(
                processed_query, user_id, document_filter, related_concepts, kg_metadata
            )
            
            # Remove internal-only decomposition object before metadata goes to response
            kg_metadata.pop('_decomposition', None)
            
            # Step 3: Prepare context from search results
            context, citations = self.context_preparer.prepare_context(
                search_results, query
            )
            
            # Step 4: Generate AI response
            if context and citations:
                # Generate document-aware response with KG context
                ai_response = await self._generate_document_aware_response(
                    query, context, conversation_context, preferred_ai_provider, kg_metadata
                )
                fallback_used = False
            else:
                # Fallback to general AI response
                ai_response = await self._generate_fallback_response(
                    query, conversation_context, preferred_ai_provider
                )
                fallback_used = True
                citations = []
            
            processing_time = int((time.time() - start_time) * 1000)
            
            # Calculate confidence score with KG factors
            confidence_score = self._calculate_confidence_score(
                search_results, ai_response, fallback_used, kg_metadata
            )
            
            # Check if KG-guided retrieval was used (from chunk metadata)
            kg_retrieval_metadata = {}
            if search_results:
                first_chunk_metadata = search_results[0].metadata or {}
                if 'kg_retrieval' in first_chunk_metadata:
                    # Aggregate KG retrieval stats
                    kg_sources = {}
                    for chunk in search_results:
                        chunk_kg_meta = (chunk.metadata or {}).get('kg_retrieval', {})
                        source = chunk_kg_meta.get('source', 'unknown')
                        kg_sources[source] = kg_sources.get(source, 0) + 1
                    
                    kg_retrieval_metadata = {
                        'kg_retrieval_used': True,
                        'kg_retrieval_sources': kg_sources,
                    }
            
            # Merge KG metadata into response metadata
            response_metadata = {
                "processed_query": processed_query,
                "ai_provider": ai_response.provider,
                "ai_model": ai_response.model,
                "search_threshold": self.min_similarity_threshold,
                "context_length": len(context) if context else 0,
                "related_concepts": related_concepts,
                **kg_metadata,
                **kg_retrieval_metadata,
            }
            
            return RAGResponse(
                response=ai_response.content,
                sources=citations,
                confidence_score=confidence_score,
                processing_time_ms=processing_time,
                tokens_used=ai_response.tokens_used,
                search_results_count=len(search_results),
                fallback_used=fallback_used,
                metadata=response_metadata
            )
            
        except Exception as e:
            logger.error(f"RAG generation failed: {e}")
            
            # Emergency fallback
            try:
                fallback_response = await self._generate_fallback_response(
                    query, conversation_context, preferred_ai_provider
                )
                processing_time = int((time.time() - start_time) * 1000)
                
                return RAGResponse(
                    response=fallback_response.content,
                    sources=[],
                    confidence_score=0.3,  # Low confidence for error fallback
                    processing_time_ms=processing_time,
                    tokens_used=fallback_response.tokens_used,
                    search_results_count=0,
                    fallback_used=True,
                    metadata={"error": str(e), "emergency_fallback": True}
                )
            except Exception as fallback_error:
                logger.error(f"Emergency fallback also failed: {fallback_error}")
                
                return RAGResponse(
                    response="I apologize, but I'm experiencing technical difficulties and cannot process your request right now. Please try again later.",
                    sources=[],
                    confidence_score=0.0,
                    processing_time_ms=int((time.time() - start_time) * 1000),
                    tokens_used=0,
                    search_results_count=0,
                    fallback_used=True,
                    metadata={"error": str(e), "fallback_error": str(fallback_error)}
                )

    async def generate_response_stream(
        self,
        query: str,
        user_id: str,
        conversation_context: Optional[List[Dict[str, str]]] = None,
        document_filter: Optional[List[str]] = None,
        preferred_ai_provider: Optional[str] = None
    ) -> AsyncGenerator[RAGStreamingChunk, None]:
        """
        Generate streaming document-aware response using RAG pipeline.
        
        This method yields chunks progressively:
        1. First chunk contains citations (search results)
        2. Subsequent chunks contain AI-generated content
        3. Final chunk contains complete metadata
        
        Args:
            query: User query
            user_id: User identifier for document filtering
            conversation_context: Recent conversation messages
            document_filter: Optional list of specific document IDs to search
            preferred_ai_provider: Preferred AI provider
            
        Yields:
            RAGStreamingChunk objects with progressive content
        """
        start_time = time.time()
        cumulative_content = ""
        cumulative_tokens = 0
        
        try:
            # Step 1: Process and enhance query with knowledge graph
            processed_query, related_concepts, kg_metadata = await self.query_processor.process_query(
                query, conversation_context
            )
            
            # Step 2: Search for relevant document chunks (non-streaming)
            search_results = await self._search_documents(
                processed_query, user_id, document_filter, related_concepts, kg_metadata
            )
            
            # Remove internal-only decomposition object before metadata goes to response
            kg_metadata.pop('_decomposition', None)
            
            # Step 3: Prepare context from search results
            context, citations = self.context_preparer.prepare_context(
                search_results, query
            )
            
            # Step 4: Yield first chunk with citations
            yield RAGStreamingChunk(
                content="",
                is_final=False,
                citations=citations,
                search_results_count=len(search_results),
                metadata={
                    "processed_query": processed_query,
                    "related_concepts": related_concepts,
                    **kg_metadata
                }
            )
            
            # Step 5: Generate AI response with streaming
            if context and citations:
                # Stream document-aware response
                async for ai_chunk in self._generate_document_aware_response_stream(
                    query, context, conversation_context, preferred_ai_provider, kg_metadata
                ):
                    cumulative_content += ai_chunk.content
                    cumulative_tokens = ai_chunk.tokens_used
                    
                    yield RAGStreamingChunk(
                        content=ai_chunk.content,
                        is_final=False,
                        tokens_used=cumulative_tokens,
                        metadata=ai_chunk.metadata
                    )
                
                fallback_used = False
            else:
                # Stream fallback response
                async for ai_chunk in self._generate_fallback_response_stream(
                    query, conversation_context, preferred_ai_provider
                ):
                    cumulative_content += ai_chunk.content
                    cumulative_tokens = ai_chunk.tokens_used
                    
                    yield RAGStreamingChunk(
                        content=ai_chunk.content,
                        is_final=False,
                        tokens_used=cumulative_tokens,
                        metadata=ai_chunk.metadata
                    )
                
                fallback_used = True
                citations = []
            
            # Step 6: Calculate final confidence score
            # Create a mock AIResponse for confidence calculation
            mock_response = AIResponse(
                content=cumulative_content,
                provider="gemini",
                model="gemini-2.5-flash",
                tokens_used=cumulative_tokens,
                processing_time_ms=0
            )
            confidence_score = self._calculate_confidence_score(
                search_results, mock_response, fallback_used, kg_metadata
            )
            
            processing_time = int((time.time() - start_time) * 1000)
            
            # Check if KG-guided retrieval was used
            kg_retrieval_metadata = {}
            if search_results:
                first_chunk_metadata = search_results[0].metadata or {}
                if 'kg_retrieval' in first_chunk_metadata:
                    kg_sources = {}
                    for chunk in search_results:
                        chunk_kg_meta = (chunk.metadata or {}).get('kg_retrieval', {})
                        source = chunk_kg_meta.get('source', 'unknown')
                        kg_sources[source] = kg_sources.get(source, 0) + 1
                    
                    kg_retrieval_metadata = {
                        'kg_retrieval_used': True,
                        'kg_retrieval_sources': kg_sources,
                    }
            
            # Step 7: Yield final chunk with complete metadata
            yield RAGStreamingChunk(
                content="",
                is_final=True,
                citations=citations,
                confidence_score=confidence_score,
                processing_time_ms=processing_time,
                tokens_used=cumulative_tokens,
                search_results_count=len(search_results),
                fallback_used=fallback_used,
                metadata={
                    "processed_query": processed_query,
                    "ai_provider": "gemini",
                    "search_threshold": self.min_similarity_threshold,
                    "context_length": len(context) if context else 0,
                    "related_concepts": related_concepts,
                    **kg_metadata,
                    **kg_retrieval_metadata
                }
            )
            
        except Exception as e:
            logger.error(f"RAG streaming generation failed: {e}")
            
            # Yield error chunk
            processing_time = int((time.time() - start_time) * 1000)
            yield RAGStreamingChunk(
                content="I apologize, but I'm experiencing technical difficulties. Please try again.",
                is_final=True,
                confidence_score=0.0,
                processing_time_ms=processing_time,
                tokens_used=0,
                search_results_count=0,
                fallback_used=True,
                metadata={"error": str(e), "streaming_error": True}
            )

    async def _generate_document_aware_response_stream(
        self,
        query: str,
        context: str,
        conversation_context: Optional[List[Dict[str, str]]] = None,
        preferred_provider: Optional[str] = None,
        kg_metadata: Optional[Dict[str, Any]] = None
    ) -> AsyncGenerator[AIResponse, None]:
        """Generate streaming AI response using document context."""
        
        # Build system prompt with document context and KG insights
        kg_context = ""
        if kg_metadata and kg_metadata.get('kg_explanation'):
            kg_context = f"\n\nKNOWLEDGE GRAPH INSIGHTS:\n{kg_metadata['kg_explanation']}"
        
        system_prompt = f"""You are a helpful AI assistant for the Multimodal Librarian system. You help users understand and work with their uploaded documents.

DOCUMENT CONTEXT:
{context}{kg_context}

Instructions:
- Use the provided document context to answer the user's question
- Always cite sources using the format [Source X] when referencing document information
- If knowledge graph insights are provided, use them to enhance your understanding
- If the context doesn't fully answer the question, say so and provide what information you can
- Be accurate and helpful in your responses"""

        # Prepare messages for AI
        messages = []
        
        # Add conversation context if available
        if conversation_context:
            for msg in conversation_context[-5:]:
                if msg['role'] in ['user', 'assistant']:
                    messages.append(msg)
        
        # Add current query with system context
        messages.append({
            "role": "user",
            "content": f"{system_prompt}\n\nUser Question: {query}"
        })
        
        # Generate streaming response
        async for chunk in self.ai_service.generate_response_stream(
            messages=messages,
            temperature=0.7,
            max_tokens=1024
        ):
            yield chunk

    async def _generate_fallback_response_stream(
        self,
        query: str,
        conversation_context: Optional[List[Dict[str, str]]] = None,
        preferred_provider: Optional[str] = None
    ) -> AsyncGenerator[AIResponse, None]:
        """Generate streaming fallback response when no documents found."""
        
        # Prepare messages
        messages = []
        
        # Add system context
        messages.append({
            "role": "system",
            "content": "You are a helpful AI assistant. The user asked a question but no relevant documents were found in their library. Provide a helpful general response and suggest they might want to upload relevant documents if their question is about specific content."
        })
        
        # Add conversation context
        if conversation_context:
            for msg in conversation_context[-5:]:
                if msg['role'] in ['user', 'assistant']:
                    messages.append(msg)
        
        # Add current query
        messages.append({
            "role": "user",
            "content": query
        })
        
        # Generate streaming response
        async for chunk in self.ai_service.generate_response_stream(
            messages=messages,
            temperature=0.7,
            max_tokens=1024
        ):
            yield chunk
    
    
    async def _search_documents(
        self,
        query: str,
        user_id: str,
        document_filter: Optional[List[str]] = None,
        related_concepts: Optional[List[str]] = None,
        kg_metadata: Optional[Dict[str, Any]] = None
    ) -> List[DocumentChunk]:
        """Search for relevant document chunks using a two-phase pipeline.

        Phase 1 (Retrieval): KG-guided retrieval first, semantic search fallback.
        Phase 2 (Post-Processing): Tag sources, optionally supplement with web
        results, apply Librarian boost, merge and rank.

        The old source-prioritization-as-search-strategy branch has been removed.
        Source prioritization logic now lives in the post-processing phase.

        Args:
            query: Processed query text
            user_id: User identifier
            document_filter: Optional document ID filter
            related_concepts: Related concept names from query decomposition
            kg_metadata: Metadata from process_query, may contain '_decomposition'
                         with a precomputed QueryDecomposition to avoid redundant work.

        Requirements: 1.5, 2.1
        """
        # Phase 1: Retrieval
        chunks = await self._retrieval_phase(
            query, user_id, document_filter, related_concepts, kg_metadata,
        )

        # Phase 2: Post-Processing (tag, supplement, boost, rank)
        chunks = await self._post_processing_phase(query, chunks)

        return chunks


    async def _retrieval_phase(
        self,
        query: str,
        user_id: str,
        document_filter: Optional[List[str]] = None,
        related_concepts: Optional[List[str]] = None,
        kg_metadata: Optional[Dict[str, Any]] = None,
    ) -> List[DocumentChunk]:
        """Phase 1: Retrieve chunks via KG-guided retrieval, falling back to semantic search.

        KG Retrieval is attempted first when available. If it returns usable chunks
        that pass document filtering, those are used directly and semantic search is
        skipped. Otherwise (KG unavailable, empty results, or exception) the method
        falls back to plain semantic search.

        Requirements: 1.1, 1.2, 1.3, 1.4
        """
        # Try KG retrieval first (Requirement 1.1)
        if self.use_kg_retrieval and self.kg_retrieval_service:
            try:
                precomputed_decomposition = (kg_metadata or {}).get('_decomposition')
                kg_result = await self.kg_retrieval_service.retrieve(
                    query,
                    top_k=self.max_search_results,
                    precomputed_decomposition=precomputed_decomposition,
                )

                # Use KG results if we got chunks and didn't fall back to semantic (Req 1.2)
                if kg_result.chunks and not kg_result.fallback_used:
                    logger.info(
                        f"KG-guided retrieval returned {len(kg_result.chunks)} chunks "
                        f"in {kg_result.retrieval_time_ms}ms"
                    )
                    chunks = self._convert_kg_results(kg_result)

                    if document_filter:
                        chunks = [c for c in chunks if c.document_id in document_filter]

                    # Check if the best KG result is actually relevant.
                    # KG retrieval can return low-quality matches when the
                    # full-text index matches generic words (e.g. "president"
                    # matching a concept in a LangChain book). If the top
                    # score is below the confidence threshold, discard KG
                    # results and fall through to semantic search, which
                    # feeds into post-processing where web search can help.
                    if chunks:
                        best_kg_score = max(c.similarity_score for c in chunks)
                        if best_kg_score < self.relevance_confidence_threshold:
                            logger.info(
                                f"KG results below confidence threshold "
                                f"({best_kg_score:.3f} < {self.relevance_confidence_threshold}), "
                                f"falling back to semantic search"
                            )
                        else:
                            return chunks
                    else:
                        logger.info("KG results filtered out, falling back to semantic search")
            except Exception as e:
                # Requirement 1.4: log and proceed without propagating
                logger.warning(f"KG retrieval failed, falling back to semantic: {e}")

        # Fallback to semantic search (Requirement 1.3)
        return await self._semantic_search_documents(
            query, user_id, document_filter, related_concepts
        )

    async def _post_processing_phase(
        self,
        query: str,
        librarian_chunks: List[DocumentChunk],
    ) -> List[DocumentChunk]:
        """Phase 2: Tag, optionally supplement with web results, boost, and rank.

        1. Tag all retrieval-phase chunks as LIBRARIAN (Req 2.2).
        2. If result count < threshold and SearXNG is available, fetch web results (Req 3.1, 3.2).
        3. Apply librarian_boost_factor to LIBRARIAN chunks, capped at 1.0 (Req 2.3).
        4. Merge and sort by boosted score descending; LIBRARIAN wins ties (Req 2.4, 2.5).

        Requirements: 2.1, 2.2, 2.3, 2.4, 2.5, 3.1, 3.2, 3.5, 3.6
        """
        # Tag all retrieval-phase results as LIBRARIAN
        for chunk in librarian_chunks:
            chunk.source_type = SearchSourceType.LIBRARIAN.value

        web_chunks: List[DocumentChunk] = []

        # Supplement with web search if Librarian results are thin (Req 3.1)
        # Use strict < so that exactly-at-threshold counts do NOT trigger web search.
        # Also trigger when the best Librarian score is below the similarity
        # threshold — low-relevance results shouldn't block web supplementation.
        best_librarian_score = max(
            (c.similarity_score for c in librarian_chunks), default=0.0
        )
        librarian_results_thin = (
            len(librarian_chunks) < self.web_search_result_count_threshold
        )
        librarian_results_irrelevant = (
            best_librarian_score < self.relevance_confidence_threshold
        )
        if (
            (librarian_results_thin or librarian_results_irrelevant)
            and self.searxng_client is not None
            and self.searxng_enabled
        ):
            try:
                web_results = await self.searxng_client.search(
                    query, max_results=self.searxng_max_results,
                )
                web_chunks = self._convert_web_results(web_results)
            except Exception as e:
                logger.warning(f"SearXNG web search failed: {e}")

        # Apply Librarian boost (Req 2.3)
        for chunk in librarian_chunks:
            chunk.similarity_score = min(
                1.0, chunk.similarity_score * self.librarian_boost_factor,
            )
            chunk.metadata['librarian_boost_applied'] = True

        # When web results were fetched and librarian results are irrelevant,
        # drop the librarian chunks so they don't pollute the response.
        # A query about Venezuelan politics shouldn't return LangChain book pages.
        if web_chunks and librarian_results_irrelevant:
            logger.info(
                f"Dropping {len(librarian_chunks)} irrelevant librarian chunks "
                f"(best score {best_librarian_score:.3f} < "
                f"threshold {self.relevance_confidence_threshold})"
            )
            librarian_chunks = []

        # Merge and sort — LIBRARIAN wins ties via stable sort key (Req 2.4, 2.5)
        all_chunks = librarian_chunks + web_chunks
        all_chunks.sort(
            key=lambda c: (
                c.similarity_score,
                c.source_type == SearchSourceType.LIBRARIAN.value,
            ),
            reverse=True,
        )

        return all_chunks[:self.max_search_results]

    def _convert_web_results(self, web_results: List["SearXNGResult"]) -> List[DocumentChunk]:
        """Convert SearXNG results to DocumentChunks tagged as WEB_SEARCH.

        SearXNG scores are unbounded (can be 4.0, 16.0, etc.) so we
        normalize them to the 0-1 range using the max score in the batch.
        This keeps them comparable with librarian scores and prevents
        absurd display values like "1600% relevant".

        Requirements: 3.4
        """
        if not web_results:
            return []

        max_score = max(r.score for r in web_results) or 1.0

        chunks = []
        for result in web_results:
            # Normalize to 0-1 range; cap at 0.95 so librarian results
            # with genuine relevance can still outrank web results.
            normalized_score = min(0.95, result.score / max_score)
            chunk = DocumentChunk(
                chunk_id=f"web_{hash(result.url)}",
                document_id=f"web_{result.engine}",
                document_title=result.title,
                content=result.content,
                similarity_score=normalized_score,
                source_type=SearchSourceType.WEB_SEARCH.value,
                metadata={
                    'url': result.url,
                    'engine': result.engine,
                    'source_type': 'web_search',
                    'raw_score': result.score,
                },
            )
            chunks.append(chunk)
        return chunks



    
    def _convert_kg_results(self, kg_result: "KGRetrievalResult") -> List[DocumentChunk]:
        """Convert KGRetrievalResult to list of DocumentChunks.
        
        Maps the RetrievedChunk objects from KG retrieval to the DocumentChunk
        format used by the rest of the RAG pipeline.
        
        Args:
            kg_result: Result from KGRetrievalService.retrieve()
            
        Returns:
            List of DocumentChunk objects
            
        Requirements: 7.2
        """
        chunks = []
        
        for retrieved_chunk in kg_result.chunks:
            # Extract metadata from the retrieved chunk
            metadata = retrieved_chunk.metadata or {}
            
            # Create DocumentChunk from RetrievedChunk
            chunk = DocumentChunk(
                chunk_id=retrieved_chunk.chunk_id,
                document_id=metadata.get('source_id', metadata.get('document_id', 'unknown')),
                document_title=metadata.get('title', metadata.get('document_title', 'Unknown Document')),
                content=retrieved_chunk.content,
                page_number=metadata.get('page_number'),
                section_title=metadata.get('section_title'),
                chunk_type=metadata.get('chunk_type', 'text'),
                similarity_score=retrieved_chunk.final_score,
                metadata={
                    **metadata,
                    # Add KG retrieval metadata
                    'kg_retrieval': {
                        'source': retrieved_chunk.source.value,
                        'concept_name': retrieved_chunk.concept_name,
                        'relationship_path': retrieved_chunk.relationship_path,
                        'kg_relevance_score': retrieved_chunk.kg_relevance_score,
                        'semantic_score': retrieved_chunk.semantic_score,
                    }
                }
            )
            chunks.append(chunk)
        
        return chunks
    
    def _convert_prioritized_results(
        self,
        prioritized_results: "PrioritizedSearchResults"
    ) -> List[DocumentChunk]:
        """Convert PrioritizedSearchResults to list of DocumentChunks.
        
        Maps the PrioritizedSearchResult objects from source prioritization
        to the DocumentChunk format used by the rest of the RAG pipeline.
        
        Args:
            prioritized_results: Result from SourcePrioritizationEngine
            
        Returns:
            List of DocumentChunk objects with source_type set
            
        Requirements: 5.5
        """
        chunks = []
        
        for result in prioritized_results.results:
            # Create DocumentChunk from PrioritizedSearchResult
            chunk = DocumentChunk(
                chunk_id=result.chunk_id,
                document_id=result.document_id,
                document_title=result.document_title,
                content=result.content,
                page_number=result.page_number,
                section_title=result.section_title,
                chunk_type='text',
                similarity_score=result.score,
                source_type=result.source_type.value,  # "librarian", "web_search", etc.
                metadata={
                    **result.metadata,
                    'source_prioritization': {
                        'source_type': result.source_type.value,
                        'original_score': result.original_score,
                        'boosted_score': result.score,
                        'boost_applied': result.score != result.original_score
                    }
                }
            )
            chunks.append(chunk)
        
        return chunks
    
    async def _semantic_search_documents(
        self,
        query: str,
        user_id: str,
        document_filter: Optional[List[str]] = None,
        related_concepts: Optional[List[str]] = None
    ) -> List[DocumentChunk]:
        """Search for relevant document chunks using semantic search with KG enhancement."""
        try:
            # Ensure vector client connection (works with both Milvus and OpenSearch)
            # Check if is_connected method exists and use it
            if hasattr(self.vector_client, 'is_connected'):
                if not self.vector_client.is_connected():
                    if hasattr(self.vector_client, 'connect'):
                        await self.vector_client.connect()
            elif hasattr(self.vector_client, '_connected'):
                if not self.vector_client._connected:
                    await self.vector_client.connect()
            
            # Build enhanced search query with related concepts
            search_queries = [query]
            if related_concepts and self.use_knowledge_graph:
                # Add related concepts as additional search terms
                for concept in related_concepts[:3]:  # Top 3 related concepts
                    search_queries.append(concept)
                
                # Create combined query
                enhanced_query = f"{query} {' '.join(related_concepts[:3])}"
                logger.info(f"Enhanced search with concepts: {enhanced_query}")
            else:
                enhanced_query = query
            
            # Perform semantic search with enhanced query
            # Use the standard semantic_search method from VectorStoreClient protocol
            # This works with both Milvus and OpenSearch
            if hasattr(self.vector_client, 'semantic_search_async'):
                # OpenSearch has async version
                search_results = await self.vector_client.semantic_search_async(
                    query=enhanced_query,
                    top_k=self.max_search_results,
                    source_type="document",
                    source_id=None
                )
            else:
                # Milvus uses standard semantic_search
                search_results = await self.vector_client.semantic_search(
                    query=enhanced_query,
                    top_k=self.max_search_results
                )
            
            # Convert to DocumentChunk objects
            chunks = []
            for result in search_results:
                # Get similarity score - handle different result formats
                # Milvus returns 'score', OpenSearch returns 'similarity_score'
                similarity_score = result.get('similarity_score', result.get('score', 0))
                
                # Skip results below similarity threshold
                if similarity_score < self.min_similarity_threshold:
                    continue
                
                # Get metadata - handle different result formats
                metadata = result.get('metadata', {})
                
                chunk = DocumentChunk(
                    chunk_id=result.get('chunk_id', result.get('id', result.get('doc_id', str(uuid4())))),
                    document_id=result.get('source_id', metadata.get('source_id', 'unknown')),
                    document_title=result.get('document_title', metadata.get('title', 'Unknown Document')),
                    content=result.get('content', metadata.get('content', '')),
                    page_number=result.get('page_number', metadata.get('page_number')),
                    section_title=result.get('section_title', metadata.get('section_title')),
                    chunk_type=result.get('chunk_type', metadata.get('chunk_type', 'text')),
                    similarity_score=similarity_score,
                    metadata=metadata
                )
                
                # Apply document filter if specified
                if document_filter and chunk.document_id not in document_filter:
                    continue
                
                chunks.append(chunk)
            
            # Re-rank results using knowledge graph if available
            if chunks and related_concepts and self.use_knowledge_graph:
                chunks = self._rerank_with_knowledge_graph(chunks, query, related_concepts)
            
            # Note: Enrichment with document titles is now done in _search_documents
            # after all retrieval phases complete
            
            logger.info(f"Found {len(chunks)} relevant chunks for query: {query[:50]}...")
            return chunks
            
        except Exception as e:
            logger.error(f"Document search failed: {e}")
            return []
    
    def _rerank_with_knowledge_graph(
        self, 
        chunks: List[DocumentChunk], 
        query: str, 
        related_concepts: List[str]
    ) -> List[DocumentChunk]:
        """Re-rank search results using knowledge graph relationships."""
        try:
            # Score chunks based on concept presence
            for chunk in chunks:
                kg_boost = 0.0
                content_lower = chunk.content.lower()
                
                # Boost score if chunk contains related concepts
                for concept in related_concepts:
                    if concept.lower() in content_lower:
                        kg_boost += 0.1  # 10% boost per related concept
                
                # Apply knowledge graph boost to similarity score
                chunk.similarity_score = min(1.0, chunk.similarity_score + kg_boost)
                
                # Add KG metadata
                chunk.metadata['kg_boost'] = kg_boost
                chunk.metadata['related_concepts_found'] = [
                    concept for concept in related_concepts 
                    if concept.lower() in content_lower
                ]
            
            # Re-sort by enhanced similarity score
            chunks.sort(key=lambda x: x.similarity_score, reverse=True)
            
            logger.info(f"Re-ranked {len(chunks)} chunks using knowledge graph")
            return chunks
            
        except Exception as e:
            logger.error(f"Knowledge graph re-ranking failed: {e}")
            return chunks
    
    async def _generate_document_aware_response(
        self,
        query: str,
        context: str,
        conversation_context: Optional[List[Dict[str, str]]] = None,
        preferred_provider: Optional[str] = None,
        kg_metadata: Optional[Dict[str, Any]] = None
    ) -> AIResponse:
        """Generate AI response using document context and knowledge graph insights."""
        
        # Build system prompt with document context and KG insights
        kg_context = ""
        if kg_metadata and kg_metadata.get('kg_explanation'):
            kg_context = f"\n\nKNOWLEDGE GRAPH INSIGHTS:\n{kg_metadata['kg_explanation']}"
        
        system_prompt = f"""You are a helpful AI assistant for the Multimodal Librarian system. You help users understand and work with their uploaded documents.

DOCUMENT CONTEXT:
{context}{kg_context}

Instructions:
- Use the provided document context to answer the user's question
- Always cite sources using the format [Source X] when referencing document information
- If knowledge graph insights are provided, use them to enhance your understanding of relationships between concepts
- If the context doesn't fully answer the question, say so and provide what information you can
- Be accurate and helpful in your responses
- If you're unsure about something from the documents, acknowledge the uncertainty"""

        # Prepare messages for AI
        messages = []
        
        # Add conversation context if available
        if conversation_context:
            for msg in conversation_context[-5:]:  # Last 5 messages for context
                if msg['role'] in ['user', 'assistant']:
                    messages.append(msg)
        
        # Add current query with system context
        messages.append({
            "role": "user",
            "content": f"{system_prompt}\n\nUser Question: {query}"
        })
        
        # Generate response
        return await self.ai_service.generate_response(
            messages=messages,
            temperature=0.7,
            max_tokens=2048,
            preferred_provider=preferred_provider
        )
    
    async def _generate_fallback_response(
        self,
        query: str,
        conversation_context: Optional[List[Dict[str, str]]] = None,
        preferred_provider: Optional[str] = None
    ) -> AIResponse:
        """Generate general AI response when no relevant documents found."""
        
        # Prepare messages
        messages = []
        
        # Add conversation context
        if conversation_context:
            for msg in conversation_context[-5:]:
                if msg['role'] in ['user', 'assistant']:
                    messages.append(msg)
        
        # Add current query
        messages.append({
            "role": "user",
            "content": query
        })
        
        # Add system context about no documents found
        system_message = {
            "role": "system",
            "content": "You are a helpful AI assistant. The user asked a question but no relevant documents were found in their library. Provide a helpful general response and suggest they might want to upload relevant documents if their question is about specific content."
        }
        
        # Insert system message at the beginning
        messages.insert(0, system_message)
        
        return await self.ai_service.generate_response(
            messages=messages,
            temperature=0.7,
            max_tokens=2048,
            preferred_provider=preferred_provider
        )
    
    def _calculate_confidence_score(
        self,
        search_results: List[DocumentChunk],
        ai_response: AIResponse,
        fallback_used: bool,
        kg_metadata: Optional[Dict[str, Any]] = None
    ) -> float:
        """Calculate confidence score for the response including KG factors."""
        if fallback_used:
            return 0.4  # Lower confidence for fallback responses
        
        if not search_results:
            return 0.3
        
        # Base confidence from search results
        avg_similarity = sum(chunk.similarity_score for chunk in search_results) / len(search_results)
        confidence = avg_similarity
        
        # Adjust based on number of results
        if len(search_results) >= 3:
            confidence += 0.1
        elif len(search_results) == 1:
            confidence -= 0.1
        
        # Boost confidence if knowledge graph provided insights
        if kg_metadata:
            if kg_metadata.get('reasoning_paths', 0) > 0:
                confidence += 0.05  # 5% boost for reasoning paths
            if kg_metadata.get('related_concepts', 0) > 0:
                confidence += 0.05  # 5% boost for related concepts
            
            # Use KG confidence scores if available
            kg_confidence_scores = kg_metadata.get('confidence_scores', {})
            if kg_confidence_scores:
                avg_kg_confidence = sum(kg_confidence_scores.values()) / len(kg_confidence_scores)
                confidence = (confidence + avg_kg_confidence) / 2
        
        # Adjust based on AI response confidence if available
        if hasattr(ai_response, 'confidence_score') and ai_response.confidence_score:
            confidence = (confidence + ai_response.confidence_score) / 2
        
        return max(0.1, min(1.0, confidence))
    
    async def search_documents(
        self,
        query: str,
        user_id: str,
        limit: int = 10,
        similarity_threshold: float = None
    ) -> List[DocumentChunk]:
        """
        Search documents without generating response (for UI search features).
        
        Args:
            query: Search query
            user_id: User identifier
            limit: Maximum results to return
            similarity_threshold: Minimum similarity score
            
        Returns:
            List of matching document chunks
        """
        if similarity_threshold is None:
            similarity_threshold = self.min_similarity_threshold
        
        # Use the internal search method with KG enhancement
        all_results = await self._search_documents(query, user_id, None, [])
        
        # Filter by threshold and limit
        filtered_results = [
            chunk for chunk in all_results 
            if chunk.similarity_score >= similarity_threshold
        ]
        
        return filtered_results[:limit]
    
    def get_service_status(self) -> Dict[str, Any]:
        """Get RAG service status information."""
        # Get vector client health - works with both Milvus and OpenSearch
        vector_health = {}
        vector_connected = False
        try:
            if hasattr(self.vector_client, 'health_check'):
                # health_check might be sync or async, handle both
                import asyncio
                if asyncio.iscoroutinefunction(self.vector_client.health_check):
                    # For async health_check, we can't call it from sync context
                    # Just check connection status
                    vector_health = {"status": "unknown", "note": "async health check not available in sync context"}
                else:
                    vector_health = self.vector_client.health_check()
            
            # Check connection status
            if hasattr(self.vector_client, 'is_connected'):
                vector_connected = self.vector_client.is_connected()
            elif hasattr(self.vector_client, '_connected'):
                vector_connected = self.vector_client._connected
        except Exception as e:
            vector_health = {"status": "error", "error": str(e)}
        
        ai_status = self.ai_service.get_provider_status()
        
        # Get knowledge graph status
        kg_stats = self.kg_builder.get_knowledge_graph_stats()
        
        # Get KG retrieval service status (Requirement 7.4)
        kg_retrieval_status = {
            "enabled": self.use_kg_retrieval,
            "available": self.kg_retrieval_service is not None,
        }
        if self.kg_retrieval_service:
            try:
                kg_retrieval_status["cache_stats"] = self.kg_retrieval_service.get_cache_stats()
            except Exception as e:
                kg_retrieval_status["cache_stats_error"] = str(e)
        
        # Get source prioritization engine status (Requirements 5.1, 5.5, 5.6)
        source_prioritization_status = {
            "enabled": self.use_source_prioritization,
            "available": self.source_prioritization_engine is not None,
        }
        if self.source_prioritization_engine:
            try:
                source_prioritization_status["config"] = self.source_prioritization_engine.get_engine_status()
            except Exception as e:
                source_prioritization_status["config_error"] = str(e)
        
        return {
            "status": "active",
            "vector_client_connected": vector_connected,
            "vector_client_health": vector_health,
            # Legacy aliases for backward compatibility
            "opensearch_connected": vector_connected,
            "opensearch_health": vector_health,
            "ai_providers": ai_status,
            "knowledge_graph": {
                "enabled": self.use_knowledge_graph,
                "total_concepts": kg_stats.total_concepts,
                "total_relationships": kg_stats.total_relationships,
                "concept_types": len(kg_stats.concept_types),
                "relationship_types": len(kg_stats.relationship_types)
            },
            "kg_retrieval": kg_retrieval_status,
            "source_prioritization": source_prioritization_status,
            "configuration": {
                "min_similarity_threshold": self.min_similarity_threshold,
                "max_search_results": self.max_search_results,
                "fallback_enabled": self.fallback_to_general_ai,
                "knowledge_graph_enabled": self.use_knowledge_graph,
                "kg_retrieval_enabled": self.use_kg_retrieval,
                "source_prioritization_enabled": self.use_source_prioritization
            },
            "features": {
                "document_search": True,
                "context_preparation": True,
                "query_enhancement": True,
                "citation_generation": True,
                "fallback_responses": True,
                "confidence_scoring": True,
                "knowledge_graph_reasoning": self.use_knowledge_graph,
                "concept_extraction": self.use_knowledge_graph,
                "multi_hop_reasoning": self.use_knowledge_graph,
                "kg_guided_retrieval": self.use_kg_retrieval,
                "source_prioritization": self.use_source_prioritization
            }
        }
    
    async def process_document_for_knowledge_graph(
        self, 
        document_id: str, 
        document_title: str, 
        content_chunks: List[str]
    ) -> Dict[str, Any]:
        """
        Process document content to extract knowledge graph concepts and relationships.
        
        Args:
            document_id: Unique document identifier
            document_title: Document title
            content_chunks: List of text chunks from the document
            
        Returns:
            Dictionary with extraction results and statistics
        """
        if not self.use_knowledge_graph:
            return {"status": "disabled", "message": "Knowledge graph processing is disabled"}
        
        try:
            extraction_results = []
            total_concepts = 0
            total_relationships = 0
            
            logger.info(f"Processing document {document_id} for knowledge graph extraction")
            
            for i, chunk_content in enumerate(content_chunks):
                chunk_id = f"{document_id}_chunk_{i}"
                
                # Create a knowledge chunk for processing
                import numpy as np

                from ..models.core import KnowledgeChunk
                
                knowledge_chunk = KnowledgeChunk(
                    id=chunk_id,
                    content=chunk_content,
                    embedding=np.zeros(384),  # Placeholder embedding
                    source_type="DOCUMENT",
                    source_id=document_id,
                    location_reference=f"chunk_{i}",
                    section=document_title
                )
                
                # Extract concepts and relationships
                extraction = self.kg_builder.process_knowledge_chunk(knowledge_chunk)
                extraction_results.append(extraction)
                
                total_concepts += len(extraction.extracted_concepts)
                total_relationships += len(extraction.extracted_relationships)
            
            # Get updated knowledge graph statistics
            kg_stats = self.kg_builder.get_knowledge_graph_stats()
            
            logger.info(f"Extracted {total_concepts} concepts and {total_relationships} relationships from document {document_id}")
            
            return {
                "status": "success",
                "document_id": document_id,
                "chunks_processed": len(content_chunks),
                "concepts_extracted": total_concepts,
                "relationships_extracted": total_relationships,
                "knowledge_graph_stats": {
                    "total_concepts": kg_stats.total_concepts,
                    "total_relationships": kg_stats.total_relationships,
                    "concepts_by_type": kg_stats.concepts_by_type,
                    "relationships_by_type": kg_stats.relationships_by_type
                },
                "extraction_results": [
                    {
                        "chunk_id": result.chunk_id,
                        "concepts": len(result.extracted_concepts),
                        "relationships": len(result.extracted_relationships),
                        "confidence": result.confidence_score
                    }
                    for result in extraction_results
                ]
            }
            
        except Exception as e:
            logger.error(f"Knowledge graph processing failed for document {document_id}: {e}")
            return {
                "status": "error",
                "document_id": document_id,
                "error": str(e),
                "message": "Failed to process document for knowledge graph extraction"
            }
    
    async def get_knowledge_graph_insights(self, query: str) -> Dict[str, Any]:
        """
        Get knowledge graph insights for a query without performing full RAG.

        Uses QueryDecomposer for concept extraction and KG_Query_Engine for
        multi-hop reasoning and related concept discovery.

        Args:
            query: User query to analyze

        Returns:
            Dictionary with knowledge graph insights
        """
        if not self.query_decomposer:
            return {"status": "disabled", "message": "QueryDecomposer not available"}

        try:
            # Step 1: Extract concepts via QueryDecomposer
            decomposition = await self.query_decomposer.decompose(query)

            if not decomposition.has_kg_matches:
                return {
                    "status": "success",
                    "query": query,
                    "reasoning_paths": [],
                    "related_concepts": [],
                    "confidence_scores": {},
                    "explanation": "No recognizable concepts found in query"
                }

            concept_names = decomposition.entities[:5]

            # Step 2: Multi-hop reasoning between concepts
            reasoning_paths = []
            if len(concept_names) > 1 and self.kg_query_engine:
                reasoning_paths = await self.kg_query_engine.multi_hop_reasoning_async(
                    concept_names[:len(concept_names) // 2 + 1],
                    concept_names[len(concept_names) // 2:],
                    max_hops=3
                )

            # Step 3: Find related concepts
            all_related = []
            if self.kg_query_engine:
                for name in concept_names[:5]:
                    related = await self.kg_query_engine.get_related_concepts_async(
                        name,
                        ["RELATED_TO", "IS_A", "PART_OF", "CAUSES", "SIMILAR_TO"],
                        max_distance=2
                    )
                    all_related.extend(related)

            # Deduplicate by concept_id
            seen = set()
            unique_related = []
            for rc in all_related:
                if rc.concept.concept_id not in seen:
                    seen.add(rc.concept.concept_id)
                    unique_related.append(rc)
            unique_related.sort(key=lambda rc: rc.relevance_score, reverse=True)

            # Calculate confidence scores
            confidence_scores = self.kg_query_engine._calculate_query_confidence_scores(
                concept_names, reasoning_paths, unique_related[:20]
            ) if self.kg_query_engine else {}

            return {
                "status": "success",
                "query": query,
                "reasoning_paths": [
                    {
                        "start": path.start_concept,
                        "end": path.end_concept,
                        "steps": len(path.path_steps),
                        "confidence": path.total_confidence,
                        "description": path.get_path_description()
                    }
                    for path in reasoning_paths
                ],
                "related_concepts": [
                    {
                        "name": rc.concept.concept_name,
                        "type": rc.concept.concept_type,
                        "relevance": rc.relevance_score,
                        "distance": rc.distance
                    }
                    for rc in unique_related[:20]
                ],
                "confidence_scores": confidence_scores,
                "explanation": f"Found {len(concept_names)} concepts via QueryDecomposer"
            }

        except Exception as e:
            logger.error(f"Knowledge graph insights failed for query '{query}': {e}")
            return {
                "status": "error",
                "query": query,
                "error": str(e),
                "message": "Failed to generate knowledge graph insights"
            }

# DEPRECATED: Module-level singleton pattern removed in favor of FastAPI DI
# Use api/dependencies/services.py get_rag_service() instead
#
# Migration guide:
#   Old: from .rag_service import get_rag_service
#        service = get_rag_service()
#
#   New: from ..api.dependencies import get_rag_service
#        # In FastAPI endpoint:
#        async def endpoint(service = Depends(get_rag_service)):
#            ...#            ...