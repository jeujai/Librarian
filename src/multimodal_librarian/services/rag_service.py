"""
RAG Service - Retrieval-Augmented Generation for document-aware chat

This service implements the critical missing component that connects the existing
chat system with document knowledge using vector search and AI generation.
Enhanced with knowledge graph reasoning for improved context understanding.

Now supports optional KG-guided retrieval via KGRetrievalService for precise
chunk retrieval using Neo4j knowledge graph source_chunks pointers.
"""

import asyncio
import hashlib
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
from ..components.kg_retrieval.relevance_detector import compute_chunk_noun_score
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
    from ..components.kg_retrieval.relevance_detector import RelevanceDetector
    from ..models.kg_retrieval import (
        KGRetrievalResult,
        QueryDecomposition,
        RetrievedChunk,
    )
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
    knowledge_source_type: Optional[str] = None  # "conversation" or "book"

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

    async def _classify_query_intent(
        self,
        query: str,
        conversation_context: Optional[List[Dict[str, str]]] = None,
    ) -> Tuple[str, Optional[str]]:
        """Use the LLM to decide if the query needs document retrieval.

        Returns:
            (intent, enhanced_query)
            - intent: "search", "web_search", "status_report", or "no_search"
            - enhanced_query: A rewritten query when context resolution was applied,
              or None if the original query should be used as-is.
        """
        context_block = ""
        if conversation_context and len(conversation_context) > 1:
            context_lines = "\n".join(
                f"{msg['role']}: {msg['content']}"
                for msg in conversation_context[-3:]
            )
            context_block = f"\nConversation context:\n{context_lines}\n"

        prompt = [
            {
                "role": "user",
                "content": f"""You are a query classifier for a document knowledge-base assistant called Librarian.

Given the user's message, decide whether it requires searching the document library.
{context_block}
User message: "{query}"

Reply with EXACTLY one line in one of these formats:
SEARCH: <rewritten query optimized for document search>
WEB_SEARCH: <rewritten query optimized for web search>
STATUS_REPORT
THROUGHPUT_REPORT
ENRICHMENT_REPORT
FAILED_UPLOADS_REPORT
SYSTEM_COMMANDS
NO_SEARCH

Use SEARCH when the user is asking a factual, topical, or analytical question that could be answered or enriched by documents in the library. Even if the conversation context already contains a previous answer to a similar question, the user may be re-asking to get a cited, document-backed response — always use SEARCH in that case.
Use WEB_SEARCH only for questions explicitly about current events, breaking news, or clearly time-sensitive information that a static document library cannot answer.
Use STATUS_REPORT when the user is asking about document processing status, upload progress, job status, or processing statistics. Examples: "show me upload stats", "what's processing?", "any uploads running?", "how are my documents doing?", "processing status". Do NOT use STATUS_REPORT for questions about document content — only for questions about the processing pipeline itself.
Use THROUGHPUT_REPORT when the user is asking about upload telemetry, processing throughput, performance metrics, processing times, or speed of document uploads. Examples: "upload telemetry", "Show me upload telemetry", "upload telemetry stats", "how long did processing take?", "how fast were documents processed?". Do NOT use THROUGHPUT_REPORT for questions about document content.
Use ENRICHMENT_REPORT when the user is asking about knowledge graph enrichment status, enrichment results, concept enrichment, YAGO/ConceptNet hits, or enrichment metrics. Examples: "show me the enrichments", "enrichment status", "show enrichment results", "how did enrichment go?", "concept enrichment stats", "YAGO hits", "ConceptNet enrichment". Do NOT use ENRICHMENT_REPORT for questions about document content.
Use FAILED_UPLOADS_REPORT when the user is asking about failed uploads, upload errors, processing failures, or documents that failed to process. Examples: "show me failed uploads", "what uploads failed?", "failed documents", "upload errors", "processing failures", "which documents had errors?". Do NOT use FAILED_UPLOADS_REPORT for questions about document content.
Use SYSTEM_COMMANDS when the user is asking what system commands, instrumentation, reports, or admin tools are available. Examples: "show me available system instrumentation", "what reports can I run?", "system commands", "what admin tools are available?", "show me available commands", "help with system reports".
Use NO_SEARCH ONLY for greetings ("hi", "hello"), farewells ("bye", "thanks"), or meta-questions about the assistant itself ("what can you do?"). Nothing else qualifies as NO_SEARCH.

When in doubt, use SEARCH. If the user message is already a good search query, repeat it after SEARCH:.
Reply with only one line, nothing else."""
            }
        ]

        try:
            response = await self.ai_service.generate_response(
                messages=prompt,
                temperature=0.0,
                max_tokens=150,
            )
            answer = response.content.strip()

            if answer.upper().startswith("NO_SEARCH"):
                logger.info(f"Query classified as NO_SEARCH: '{query}'")
                return "no_search", None

            if answer.upper().startswith("STATUS_REPORT"):
                logger.info(f"Query classified as STATUS_REPORT: '{query}'")
                return "status_report", None

            if answer.upper().startswith("THROUGHPUT_REPORT"):
                logger.info(f"Query classified as THROUGHPUT_REPORT: '{query}'")
                return "throughput_report", None

            if answer.upper().startswith("ENRICHMENT_REPORT"):
                logger.info(f"Query classified as ENRICHMENT_REPORT: '{query}'")
                return "enrichment_report", None

            if answer.upper().startswith("FAILED_UPLOADS_REPORT"):
                logger.info(f"Query classified as FAILED_UPLOADS_REPORT: '{query}'")
                return "failed_uploads_report", None

            if answer.upper().startswith("SYSTEM_COMMANDS"):
                logger.info(f"Query classified as SYSTEM_COMMANDS: '{query}'")
                return "system_commands", None

            if answer.upper().startswith("WEB_SEARCH:"):
                rewritten = answer[len("WEB_SEARCH:"):].strip().strip('"')
                if rewritten and len(rewritten) < len(query) * 3:
                    # Reject rewrites that lost too much content
                    if len(rewritten) < len(query) * 0.5:
                        logger.warning(
                            f"Rejecting too-short WEB_SEARCH rewrite: "
                            f"'{query}' -> '{rewritten}'"
                        )
                        return "web_search", None
                    if rewritten.lower() != query.lower():
                        logger.info(f"Query classified as WEB_SEARCH, rewritten: '{query}' -> '{rewritten}'")
                        return "web_search", rewritten
                    logger.info(f"Query classified as WEB_SEARCH (no rewrite needed): '{query}'")
                    return "web_search", None
                return "web_search", None

            if answer.upper().startswith("SEARCH:"):
                rewritten = answer[len("SEARCH:"):].strip().strip('"')
                if rewritten and len(rewritten) < len(query) * 3:
                    # Reject rewrites that lost too much content
                    if len(rewritten) < len(query) * 0.5:
                        logger.warning(
                            f"Rejecting too-short SEARCH rewrite: "
                            f"'{query}' -> '{rewritten}'"
                        )
                        return "search", None
                    if rewritten.lower() != query.lower():
                        logger.info(f"Query classified as SEARCH, rewritten: '{query}' -> '{rewritten}'")
                        return "search", rewritten
                    logger.info(f"Query classified as SEARCH (no rewrite needed): '{query}'")
                    return "search", None
                return "search", None

            # Unrecognized format — default to retrieval
            logger.warning(f"Unexpected intent classification response: {answer!r}")
            return "search", None

        except Exception as e:
            logger.warning(f"Query intent classification failed: {e}")
            return "search", None  # Default to retrieval on error
    
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
            kg_metadata['skip_retrieval'] is True when the LLM determines
            the query does not need document search.
        """
        try:
            kg_metadata = {}
            related_concepts = []

            # Step 1: LLM-based intent classification + query rewriting.
            # This single call decides whether retrieval is needed and,
            # when conversation context is present, rewrites the query.
            intent, rewritten_query = await self._classify_query_intent(
                query, conversation_context
            )

            if intent == "no_search":
                kg_metadata['skip_retrieval'] = True
                return query, [], kg_metadata

            if intent == "web_search":
                kg_metadata['web_search_only'] = True
                kg_metadata['web_query'] = rewritten_query or query
                return rewritten_query or query, [], kg_metadata

            enhanced_query = rewritten_query if rewritten_query else query
            
            # Step 2: Extract concepts via QueryDecomposer
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
            
            return enhanced_query, related_concepts, kg_metadata
            
        except Exception as e:
            logger.error(f"Query processing failed: {e}")
            return query, [], {}

class ContextPreparer:
    """Prepare and rank document context for AI generation."""
    
    def __init__(self, max_context_length: int = 32000):
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
        
        # Deduplicate: conversation sources often produce duplicate chunks with
        # the same document_id (from KG + semantic paths). Collapse those.
        # Book/document sources from different pages are NOT deduplicated —
        # multiple pages from the same book are valuable context.
        # Book/document sources from the SAME page ARE deduplicated —
        # overlapping chunks or duplicate embeddings from the same page
        # provide no additional value and confuse the citation list.
        # Web search sources share a synthetic document_id ("web_brave")
        # so deduplicate those by URL instead.
        seen_conv_doc_ids = set()
        seen_urls = set()
        seen_doc_pages: set = set()
        deduped_chunks = []
        for chunk in selected_chunks:
            url = chunk.metadata.get('url') if chunk.metadata else None
            is_web = chunk.source_type and 'web' in str(chunk.source_type).lower()
            source_type = chunk.metadata.get('source_type', '') if chunk.metadata else ''
            is_conversation = source_type == 'conversation'
            # Debug: log every chunk's dedup-relevant fields
            if is_web and url:
                if url not in seen_urls:
                    seen_urls.add(url)
                    deduped_chunks.append(chunk)
            elif is_conversation:
                if chunk.document_id not in seen_conv_doc_ids:
                    seen_conv_doc_ids.add(chunk.document_id)
                    deduped_chunks.append(chunk)
            else:
                # Book/document chunks: keep different pages, drop same-page dupes.
                # Chunks without a page number are always kept (keyed by chunk_id).
                # Use document_title (not document_id) because the same book
                # may have been ingested more than once with different IDs.
                page = chunk.page_number
                if page is None and chunk.metadata:
                    page = chunk.metadata.get('page_number')
                if page is not None:
                    # Normalize to int for consistent dedup key
                    try:
                        page = int(page)
                    except (ValueError, TypeError):
                        pass
                    doc_page_key = (chunk.document_title, page)
                    if doc_page_key in seen_doc_pages:
                        logger.debug(
                            "Dedup: dropping same-page duplicate "
                            "title=%s page=%s chunk_id=%s",
                            chunk.document_title[:40], page,
                            chunk.chunk_id[:12],
                        )
                        continue
                    seen_doc_pages.add(doc_page_key)
                deduped_chunks.append(chunk)
        logger.info(
            "Citation dedup: %d chunks -> %d after same-page dedup",
            len(selected_chunks), len(deduped_chunks),
        )
        selected_chunks = deduped_chunks
        
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
                knowledge_source_type=chunk.metadata.get('source_type') if chunk.metadata else None,
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
        relevance_detector: Optional["RelevanceDetector"] = None,
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
            relevance_detector: Optional RelevanceDetector for identifying irrelevant
                                results via score distribution and concept specificity
                                analysis. Requirements: 4.1, 4.2, 4.4
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
        
        # Relevance detection (Requirements 4.1, 4.2, 4.4)
        self.relevance_detector = relevance_detector
        self._last_relevance_verdict = None

        # Retrieval result cache: ensures identical queries return
        # identical citation lists within a session.  Keyed by
        # SHA-256(query + user_id + document_filter).
        self._retrieval_cache: Dict[str, List["DocumentChunk"]] = {}
        self._max_retrieval_cache_size = 64
        
        if self.use_source_prioritization:
            logger.info("RAG Service initialized with source prioritization support")
        elif self.use_kg_retrieval:
            logger.info("RAG Service initialized with KG-guided retrieval support")
        else:
            logger.info("RAG Service initialized with knowledge graph support")

    def clear_retrieval_cache(self) -> int:
        """Clear the retrieval cache. Returns number of entries cleared."""
        count = len(self._retrieval_cache)
        self._retrieval_cache.clear()
        logger.info(f"Cleared {count} retrieval cache entries")
        return count
        
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
        
        # Reset cached relevance verdict for this request (Req 4.6)
        self._last_relevance_verdict = None
        
        try:
            # Step 1: Process and enhance query with knowledge graph
            processed_query, related_concepts, kg_metadata = await self.query_processor.process_query(
                query, conversation_context
            )
            
            # Step 1b: If the LLM classified this as not needing retrieval,
            # skip search entirely and go straight to fallback response.
            if kg_metadata.get('skip_retrieval'):
                logger.info(f"Skipping retrieval for query (non-streaming): '{query}'")
                ai_response = await self._generate_fallback_response(
                    query, conversation_context, preferred_ai_provider,
                    skip_retrieval=True,
                )
                processing_time = int((time.time() - start_time) * 1000)
                return RAGResponse(
                    response=ai_response.content,
                    sources=[],
                    confidence_score=0.5,
                    processing_time_ms=processing_time,
                    tokens_used=ai_response.tokens_used,
                    search_results_count=0,
                    fallback_used=True,
                    metadata={
                        "processed_query": processed_query,
                        "skip_retrieval": True,
                        "ai_provider": ai_response.provider,
                        "ai_model": ai_response.model,
                    }
                )
            
            # Step 1c: WEB_SEARCH — bypass library retrieval, go straight to SearXNG
            if kg_metadata.get('web_search_only'):
                web_query = kg_metadata.get('web_query', query)
                logger.info(
                    f"WEB_SEARCH route (non-streaming) for query: '{query}' "
                    f"(web_query: '{web_query}')"
                )

                web_chunks: List[DocumentChunk] = []
                if self.searxng_client is not None and self.searxng_enabled:
                    try:
                        web_results = await self.searxng_client.search(
                            web_query, max_results=self.searxng_max_results,
                        )
                        web_chunks = self._convert_web_results(web_results)
                    except Exception as e:
                        logger.warning(f"SearXNG web search failed for WEB_SEARCH route: {e}")

                if web_chunks:
                    context, citations = self.context_preparer.prepare_context(web_chunks, query)
                    ai_response = await self._generate_document_aware_response(
                        query, context, conversation_context, preferred_ai_provider, kg_metadata
                    )
                    fallback_used = False
                else:
                    ai_response = await self._generate_fallback_response(
                        query, conversation_context, preferred_ai_provider,
                        skip_retrieval=True,
                    )
                    fallback_used = True
                    citations = []

                processing_time = int((time.time() - start_time) * 1000)
                return RAGResponse(
                    response=ai_response.content,
                    sources=citations if not fallback_used else [],
                    confidence_score=0.7 if not fallback_used else 0.5,
                    processing_time_ms=processing_time,
                    tokens_used=ai_response.tokens_used,
                    search_results_count=len(web_chunks),
                    fallback_used=fallback_used,
                    metadata={
                        "processed_query": processed_query,
                        "web_search_only": True,
                        "ai_provider": ai_response.provider,
                        "ai_model": ai_response.model,
                    }
                )

            # Step 2: Search for relevant document chunks with KG enhancement
            search_results = await self._search_documents(
                processed_query, user_id, document_filter, related_concepts, kg_metadata,
                raw_query=query,
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
            
            # Include relevance detection diagnostic data (Req 4.6)
            if self._last_relevance_verdict is not None:
                v = self._last_relevance_verdict
                response_metadata["relevance_detection"] = {
                    "is_relevant": v.is_relevant,
                    "confidence_adjustment_factor": v.confidence_adjustment_factor,
                    "reasoning": v.reasoning,
                    "score_distribution": {
                        "variance": v.score_distribution.variance,
                        "spread": v.score_distribution.spread,
                        "is_semantic_floor": v.score_distribution.is_semantic_floor,
                        "chunk_count": v.score_distribution.chunk_count,
                        "is_indeterminate": v.score_distribution.is_indeterminate,
                    },
                    "concept_specificity": {
                        "average_specificity": v.concept_specificity.average_specificity,
                        "is_low_specificity": v.concept_specificity.is_low_specificity,
                        "high_specificity_count": v.concept_specificity.high_specificity_count,
                        "low_specificity_count": v.concept_specificity.low_specificity_count,
                    },
                    "query_term_coverage": {
                        "proper_nouns": v.query_term_coverage.proper_nouns,
                        "covered_nouns": v.query_term_coverage.covered_nouns,
                        "uncovered_nouns": v.query_term_coverage.uncovered_nouns,
                        "coverage_ratio": v.query_term_coverage.coverage_ratio,
                        "has_proper_noun_gap": v.query_term_coverage.has_proper_noun_gap,
                        "has_cooccurrence_gap": v.query_term_coverage.has_cooccurrence_gap,
                        "key_nouns": v.query_term_coverage.key_nouns,
                        "adaptive_threshold": v.query_term_coverage.adaptive_threshold,
                        "detected_domain": v.query_term_coverage.detected_domain,
                    },
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
            
            # Step 1b: If the LLM classified this as not needing retrieval,
            # skip search entirely and go straight to fallback response.
            if kg_metadata.get('skip_retrieval'):
                logger.info(f"Skipping retrieval for query: '{query}'")
                
                # Yield empty first chunk (no citations)
                yield RAGStreamingChunk(
                    content="",
                    is_final=False,
                    citations=[],
                    search_results_count=0,
                    metadata={
                        "processed_query": processed_query,
                        "related_concepts": [],
                        "skip_retrieval": True,
                    }
                )
                
                # Stream fallback response (general AI, no document context)
                async for ai_chunk in self._generate_fallback_response_stream(
                    query, conversation_context, preferred_ai_provider,
                    skip_retrieval=True,
                ):
                    cumulative_content += ai_chunk.content
                    cumulative_tokens = ai_chunk.tokens_used
                    
                    yield RAGStreamingChunk(
                        content=ai_chunk.content,
                        is_final=False,
                        tokens_used=cumulative_tokens,
                        metadata=ai_chunk.metadata
                    )
                
                processing_time = int((time.time() - start_time) * 1000)
                yield RAGStreamingChunk(
                    content="",
                    is_final=True,
                    citations=[],
                    confidence_score=0.5,
                    processing_time_ms=processing_time,
                    tokens_used=cumulative_tokens,
                    search_results_count=0,
                    fallback_used=True,
                    metadata={
                        "processed_query": processed_query,
                        "skip_retrieval": True,
                        "ai_provider": "gemini",
                    }
                )
                return
            
            # Step 1c: WEB_SEARCH — bypass library retrieval, go straight
            # to SearXNG, then generate a document-aware response from
            # web results only.
            if kg_metadata.get('web_search_only'):
                web_query = kg_metadata.get('web_query', query)
                logger.info(
                    f"WEB_SEARCH route for query: '{query}' "
                    f"(web_query: '{web_query}')"
                )

                web_chunks: List[DocumentChunk] = []
                if (
                    self.searxng_client is not None
                    and self.searxng_enabled
                ):
                    try:
                        web_results = await self.searxng_client.search(
                            web_query,
                            max_results=self.searxng_max_results,
                        )
                        web_chunks = self._convert_web_results(
                            web_results
                        )
                    except Exception as e:
                        logger.warning(
                            "SearXNG web search failed for "
                            f"WEB_SEARCH route: {e}"
                        )

                if web_chunks:
                    context, citations = (
                        self.context_preparer.prepare_context(
                            web_chunks, query
                        )
                    )
                    yield RAGStreamingChunk(
                        content="",
                        is_final=False,
                        citations=citations,
                        search_results_count=len(web_chunks),
                        metadata={
                            "processed_query": processed_query,
                            "related_concepts": [],
                            "web_search_only": True,
                        }
                    )
                    async for ai_chunk in self._generate_document_aware_response_stream(
                        query, context, conversation_context,
                        preferred_ai_provider, kg_metadata
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
                    yield RAGStreamingChunk(
                        content="",
                        is_final=False,
                        citations=[],
                        search_results_count=0,
                        metadata={
                            "processed_query": processed_query,
                            "related_concepts": [],
                            "web_search_only": True,
                        }
                    )
                    async for ai_chunk in self._generate_fallback_response_stream(
                        query, conversation_context,
                        preferred_ai_provider,
                        skip_retrieval=True,
                    ):
                        cumulative_content += ai_chunk.content
                        cumulative_tokens = ai_chunk.tokens_used
                        yield RAGStreamingChunk(
                            content=ai_chunk.content,
                            is_final=False,
                            tokens_used=cumulative_tokens,
                            metadata=ai_chunk.metadata
                        )
                    citations = []
                    fallback_used = True

                processing_time = int(
                    (time.time() - start_time) * 1000
                )
                yield RAGStreamingChunk(
                    content="",
                    is_final=True,
                    citations=citations if not fallback_used else [],
                    confidence_score=0.7 if not fallback_used else 0.4,
                    processing_time_ms=processing_time,
                    tokens_used=cumulative_tokens,
                    search_results_count=len(web_chunks),
                    fallback_used=fallback_used,
                    metadata={
                        "processed_query": processed_query,
                        "web_search_only": True,
                        "ai_provider": "gemini",
                    }
                )
                return
            
            # Step 2: Search for relevant document chunks (non-streaming)
            search_results = await self._search_documents(
                processed_query, user_id, document_filter, related_concepts, kg_metadata,
                raw_query=query,
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
        
        system_prompt = f"""You are Librarian, a helpful and knowledgeable AI assistant. You help users find answers by summarizing and synthesizing information from their document library and, when relevant, supplementary web search results.

Your role is to report what the documents say — you are a research assistant summarizing source material, not providing personal advice.

SOURCES:
{context}{kg_context}

Instructions:
- Use the provided sources to answer the user's question
- Always cite sources using the format [Source X] when referencing information
- IMPORTANT: Only reference sources that actually appear above. Do NOT fabricate or hallucinate source numbers beyond what is provided
- Sources may come from the user's document library or from web search — use all of them
- If knowledge graph insights are provided, use them to enhance your understanding
- If the sources don't fully answer the question, say so and provide what information you can
- When sources contain medical, legal, financial, or other professional content, summarize what the documents say. Frame answers as "According to [Source X]..." rather than as personal advice. You may add a brief disclaimer that users should consult a qualified professional.
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
            max_tokens=2048
        ):
            yield chunk

    async def _generate_fallback_response_stream(
        self,
        query: str,
        conversation_context: Optional[List[Dict[str, str]]] = None,
        preferred_provider: Optional[str] = None,
        skip_retrieval: bool = False,
    ) -> AsyncGenerator[AIResponse, None]:
        """Generate streaming fallback response when no documents found."""
        
        # Prepare messages
        messages = []
        
        # Use a conversational prompt when retrieval was intentionally skipped
        if skip_retrieval:
            system_content = (
                "You are Librarian, a friendly and knowledgeable AI assistant. "
                "Respond naturally to the user's message. You can help with general questions, "
                "conversation, and guidance. Keep responses concise and helpful."
            )
        else:
            system_content = (
                "You are a helpful AI assistant. The user asked a question but no relevant "
                "documents were found in their library. Provide a helpful general response "
                "and suggest they might want to upload relevant documents if their question "
                "is about specific content."
            )
        
        # Add system context
        messages.append({
            "role": "system",
            "content": system_content,
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
            max_tokens=2048
        ):
            yield chunk
    
    
    async def _search_documents(
        self,
        query: str,
        user_id: str,
        document_filter: Optional[List[str]] = None,
        related_concepts: Optional[List[str]] = None,
        kg_metadata: Optional[Dict[str, Any]] = None,
        raw_query: Optional[str] = None
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
        # Check retrieval cache for deterministic results.
        # Key on the RAW (user-typed) query, not the LLM-processed one,
        # because process_query may rewrite the query non-deterministically
        # when conversation context grows (e.g. "that" triggers enhancement).
        # Also exclude user_id since it's a random connection_id per WebSocket.
        cache_query = raw_query if raw_query is not None else query
        filter_key = json.dumps(
            sorted(document_filter) if document_filter else [],
            sort_keys=True,
        )
        cache_key = hashlib.sha256(
            f"{cache_query}|{filter_key}".encode('utf-8')
        ).hexdigest()
        cached = self._retrieval_cache.get(cache_key)
        if cached is not None:
            logger.info(
                f"Retrieval cache hit for query: {query[:50]}..."
            )
            return cached

        # Phase 1: Retrieval
        chunks = await self._retrieval_phase(
            query, user_id, document_filter, related_concepts, kg_metadata,
        )

        # Extract precomputed decomposition for relevance detection (Req 4.1)
        query_decomposition = (kg_metadata or {}).get('_decomposition')

        # Phase 2: Post-Processing (tag, supplement, boost, rank)
        chunks = await self._post_processing_phase(
            query, chunks, query_decomposition=query_decomposition,
        )

        # Cache the result for deterministic repeated queries
        if len(self._retrieval_cache) >= self._max_retrieval_cache_size:
            oldest = next(iter(self._retrieval_cache))
            del self._retrieval_cache[oldest]
        self._retrieval_cache[cache_key] = chunks

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
        query_decomposition: Optional["QueryDecomposition"] = None,
    ) -> List[DocumentChunk]:
        """Phase 2: Tag, optionally supplement with web results, boost, and rank.

        1. Tag all retrieval-phase chunks as LIBRARIAN (Req 2.2).
        2. Invoke RelevanceDetector if available (Req 4.1, 4.2, 4.7).
        3. If result count < threshold and SearXNG is available, fetch web results (Req 3.1, 3.2).
        4. Apply librarian_boost_factor to LIBRARIAN chunks, capped at 1.0 (Req 2.3).
        5. Merge and sort by boosted score descending; LIBRARIAN wins ties (Req 2.4, 2.5).

        Requirements: 2.1, 2.2, 2.3, 2.4, 2.5, 3.1, 3.2, 3.5, 3.6, 4.1, 4.2, 4.3, 4.7
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

        # Relevance detection trigger (Requirements 4.1, 4.2, 4.7)
        relevance_detected_irrelevant = False
        if self.relevance_detector is not None and query_decomposition is not None:
            try:
                # Build lightweight RetrievedChunk wrappers so the detector
                # can read final_score (it operates on RetrievedChunk, not
                # DocumentChunk).
                from ..models.kg_retrieval import RetrievalSource
                from ..models.kg_retrieval import RetrievedChunk as _RC
                rc_chunks = [
                    _RC(
                        chunk_id=c.chunk_id or "",
                        content=c.content or "",
                        source=RetrievalSource.SEMANTIC_FALLBACK,
                        final_score=c.similarity_score,
                    )
                    for c in librarian_chunks
                ]
                verdict = await self.relevance_detector.evaluate(
                    rc_chunks, query_decomposition,
                )
                self._last_relevance_verdict = verdict
                relevance_detected_irrelevant = not verdict.is_relevant
                tc = verdict.query_term_coverage
                logger.info(
                    f"Relevance detection: "
                    f"is_relevant={verdict.is_relevant}, "
                    f"factor="
                    f"{verdict.confidence_adjustment_factor}, "
                    f"semantic_floor="
                    f"{verdict.score_distribution.is_semantic_floor}, "
                    f"low_specificity="
                    f"{verdict.concept_specificity.is_low_specificity}, "
                    f"proper_noun_count="
                    f"{len(tc.proper_nouns)}, "
                    f"adaptive_threshold="
                    f"{tc.adaptive_threshold:.2f}, "
                    f"coverage_ratio="
                    f"{tc.coverage_ratio:.2f}, "
                    f"detected_domain="
                    f"{tc.detected_domain}, "
                    f"has_proper_noun_gap="
                    f"{tc.has_proper_noun_gap}, "
                    f"has_cooccurrence_gap="
                    f"{tc.has_cooccurrence_gap}, "
                    f"proper_nouns={tc.proper_nouns}, "
                    f"key_nouns={tc.key_nouns}, "
                    f"uncovered={tc.uncovered_nouns}, "
                    f"scores=["
                    f"{', '.join(f'{c.final_score:.4f}' for c in rc_chunks[:5])}], "
                    f"concepts="
                    f"{len(query_decomposition.concept_matches)}"
                )
            except Exception as e:
                logger.warning(f"Relevance detection failed, using original logic: {e}")
                self._last_relevance_verdict = None
        else:
            logger.info(
                f"Relevance detection skipped: "
                f"detector={'present' if self.relevance_detector else 'None'}, "
                f"decomposition={'present' if query_decomposition else 'None'}"
            )

        if (
            (librarian_results_thin or librarian_results_irrelevant or relevance_detected_irrelevant)
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

        # When librarian results are irrelevant, drop them so they don't
        # pollute the response.  This applies regardless of whether web
        # results were fetched — if the relevance detector flagged the
        # librarian chunks as irrelevant and web search also returned
        # nothing, we should still drop them so the fallback response
        # path is used instead of presenting misleading citations.
        #
        # However, when the relevance detector fired (proper-noun gap),
        # keep any librarian chunks whose content actually contains the
        # query's proper nouns — those are genuinely relevant (e.g. a
        # conversation chunk that previously answered the same question).
        #
        # Co-occurrence gap: when the detector fired because no chunk
        # contains ALL key PROPN tokens together (e.g. "President" +
        # "Venezuela"), only keep chunks that contain ALL key nouns —
        # not just one of them.
        if librarian_results_irrelevant or relevance_detected_irrelevant:
            tc = (
                self._last_relevance_verdict.query_term_coverage
                if self._last_relevance_verdict is not None
                else None
            )
            if (
                relevance_detected_irrelevant
                and tc is not None
                and tc.has_cooccurrence_gap
                and tc.key_nouns
            ):
                # Co-occurrence drop: retain chunks meeting adaptive
                # threshold instead of requiring ALL key nouns.
                adaptive_thresh = tc.adaptive_threshold
                for c in librarian_chunks:
                    c.metadata['chunk_noun_score'] = compute_chunk_noun_score(
                        c.content or "", tc.key_nouns,
                    )
                kept = [
                    c for c in librarian_chunks
                    if c.metadata['chunk_noun_score'] >= adaptive_thresh
                ]
                if not kept and librarian_chunks:
                    # Fallback: retain top chunks by chunk_noun_score
                    librarian_chunks.sort(
                        key=lambda c: c.metadata.get('chunk_noun_score', 0.0),
                        reverse=True,
                    )
                    kept = librarian_chunks[:self.web_search_result_count_threshold]
                dropped = len(librarian_chunks) - len(kept)
                logger.info(
                    f"Co-occurrence drop (adaptive): kept {len(kept)}, "
                    f"dropped {dropped} librarian chunks "
                    f"(key_nouns: {[kn.lower() for kn in tc.key_nouns]}, "
                    f"adaptive_threshold: {adaptive_thresh:.2f})"
                )
                librarian_chunks = kept
            elif (
                relevance_detected_irrelevant
                and tc is not None
                and tc.proper_nouns
            ):
                # Selective drop: keep chunks containing proper nouns
                proper_nouns_lower = [
                    pn.lower() for pn in tc.proper_nouns
                ]
                kept = [
                    c for c in librarian_chunks
                    if any(
                        pn in (c.content or "").lower()
                        for pn in proper_nouns_lower
                    )
                ]
                dropped = len(librarian_chunks) - len(kept)
                logger.info(
                    f"Selective drop: kept {len(kept)}, "
                    f"dropped {dropped} irrelevant librarian "
                    f"chunks (proper nouns: {proper_nouns_lower})"
                )
                librarian_chunks = kept
            else:
                # Full drop: no proper noun info or score-based
                logger.info(
                    f"Dropping {len(librarian_chunks)} irrelevant "
                    f"librarian chunks (best score "
                    f"{best_librarian_score:.3f} < threshold "
                    f"{self.relevance_confidence_threshold})"
                )
                librarian_chunks = []

        # Per-chunk key-noun filter: even when the batch-level relevance
        # verdict is "relevant" (because at least one chunk genuinely matches),
        # individual chunks that don't meet the adaptive threshold are noise.
        # Uses graduated scoring instead of requiring ALL key nouns.
        tc = (
            self._last_relevance_verdict.query_term_coverage
            if self._last_relevance_verdict is not None
            else None
        )
        if (
            tc is not None
            and len(tc.key_nouns) >= 2
            and librarian_chunks
        ):
            adaptive_thresh = tc.adaptive_threshold
            before_count = len(librarian_chunks)
            # Compute chunk_noun_score for any chunks that don't have it yet
            for c in librarian_chunks:
                if 'chunk_noun_score' not in c.metadata:
                    c.metadata['chunk_noun_score'] = compute_chunk_noun_score(
                        c.content or "", tc.key_nouns,
                    )
            kept = [
                c for c in librarian_chunks
                if c.metadata['chunk_noun_score'] >= adaptive_thresh
            ]
            if not kept and librarian_chunks:
                # Fallback: retain top chunks by chunk_noun_score
                librarian_chunks.sort(
                    key=lambda c: c.metadata.get('chunk_noun_score', 0.0),
                    reverse=True,
                )
                kept = librarian_chunks[:self.web_search_result_count_threshold]
            dropped = before_count - len(kept)
            if dropped > 0:
                logger.info(
                    f"Per-chunk key-noun filter (adaptive): "
                    f"kept {len(kept)}, "
                    f"dropped {dropped} chunks below "
                    f"adaptive_threshold {adaptive_thresh:.2f} "
                    f"(key_nouns: "
                    f"{[kn.lower() for kn in tc.key_nouns]})"
                )
            # Log per-chunk noun scores for observability
            for c in kept:
                logger.info(
                    f"Chunk noun score: "
                    f"chunk_id={c.chunk_id}, "
                    f"chunk_noun_score="
                    f"{c.metadata.get('chunk_noun_score', 0.0):.2f}, "
                    f"similarity_score="
                    f"{c.similarity_score:.4f}"
                )
            librarian_chunks = kept

        # Web search trigger based on surviving chunk count after
        # adaptive threshold filtering (Requirements 6.1, 6.2, 6.3, 6.4, 6.5).
        # This is an independent signal — existing thin/irrelevant triggers above
        # remain active.
        if (
            tc is not None
            and tc.key_nouns
            and self.searxng_client is not None
            and self.searxng_enabled
        ):
            adaptive_thresh = tc.adaptive_threshold
            surviving_count = sum(
                1 for c in librarian_chunks
                if c.metadata.get('chunk_noun_score', 0.0)
                >= adaptive_thresh
            )
            if surviving_count < self.web_search_result_count_threshold:
                logger.info(
                    f"Adaptive web search trigger: "
                    f"{surviving_count} chunks above "
                    f"adaptive_threshold "
                    f"{adaptive_thresh:.2f} < threshold "
                    f"{self.web_search_result_count_threshold}"
                    f", triggering web search"
                )
                try:
                    web_results = await self.searxng_client.search(
                        query, max_results=self.searxng_max_results,
                    )
                    adaptive_web_chunks = self._convert_web_results(web_results)
                    web_chunks.extend(adaptive_web_chunks)
                except Exception as e:
                    logger.warning(f"SearXNG web search (adaptive trigger) failed: {e}")
            else:
                logger.info(
                    f"Adaptive web search not triggered: "
                    f"{surviving_count} chunks above "
                    f"adaptive_threshold "
                    f"{adaptive_thresh:.2f} >= threshold "
                    f"{self.web_search_result_count_threshold}"
                )

        # Dedup-aware thin results check: ContextPreparer collapses
        # conversation chunks by document_id, so 4 raw chunks from
        # 2 conversation threads become 2 citations.  Count effective
        # unique citations and trigger web search if below threshold.
        if (
            librarian_chunks
            and not web_chunks
            and self.searxng_client is not None
            and self.searxng_enabled
        ):
            seen_conv_ids: set = set()
            effective_count = 0
            for c in librarian_chunks:
                src_type = (
                    c.metadata.get('source_type', '')
                    if c.metadata else ''
                )
                if src_type == 'conversation':
                    if c.document_id not in seen_conv_ids:
                        seen_conv_ids.add(c.document_id)
                        effective_count += 1
                else:
                    effective_count += 1
            if effective_count < self.web_search_result_count_threshold:
                logger.info(
                    f"Dedup-aware thin results trigger: "
                    f"{len(librarian_chunks)} raw chunks -> "
                    f"{effective_count} effective citations "
                    f"< threshold "
                    f"{self.web_search_result_count_threshold}"
                    f", triggering web search"
                )
                try:
                    web_results = await self.searxng_client.search(
                        query,
                        max_results=self.searxng_max_results,
                    )
                    web_chunks = self._convert_web_results(
                        web_results,
                    )
                except Exception as e:
                    logger.warning(
                        f"SearXNG web search "
                        f"(dedup-aware trigger) "
                        f"failed: {e}"
                    )

        # Merge and sort — primary: final_score DESC, secondary: chunk_noun_score DESC,
        # tertiary: LIBRARIAN wins ties (Req 2.4, 2.5, 3.3, 4.1, 4.2, 4.3)
        all_chunks = librarian_chunks + web_chunks
        all_chunks.sort(
            key=lambda c: (
                c.similarity_score,
                c.metadata.get('chunk_noun_score', 0.0),
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
            # Fallback: extract page number from [Page N] markers in content
            if chunk.page_number is None and chunk.content:
                import re
                m = re.search(r'\[Page\s+(\d+)', chunk.content)
                if m:
                    try:
                        chunk.page_number = int(m.group(1))
                    except ValueError:
                        pass
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
            # NOTE: source_type is intentionally None so results include both
            # document-derived and conversation-derived chunks (SourceType.BOOK
            # and SourceType.CONVERSATION). The RAG pipeline treats all knowledge
            # sources uniformly — ranking and boosting are source-type-agnostic.
            # See: Conversation Knowledge Integration spec, Requirements 5.1, 5.3.
            if hasattr(self.vector_client, 'semantic_search_async'):
                # OpenSearch has async version
                search_results = await self.vector_client.semantic_search_async(
                    query=enhanced_query,
                    top_k=self.max_search_results,
                    source_type=None,
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
                
                # Fallback: extract page number from [Page N] markers in content
                if chunk.page_number is None and chunk.content:
                    import re
                    m = re.search(r'\[Page\s+(\d+)', chunk.content)
                    if m:
                        try:
                            chunk.page_number = int(m.group(1))
                        except ValueError:
                            pass
                
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

    # ------------------------------------------------------------------
    # Keyword search supplement (Postgres full-text index)
    # ------------------------------------------------------------------

    # Regex for terms that embeddings handle poorly: code identifiers
    # (contain underscores, dots, equals), quoted strings, and
    # camelCase / PascalCase tokens.
    _CODE_TERM_RE = re.compile(
        r"""
        [\w]+[._=][\w=.]+   # underscore/dot/equals-separated identifiers
        | [A-Z][a-z]+[A-Z]  # camelCase start
        | "[^"]{3,}"         # double-quoted strings
        | '[^']{3,}'         # single-quoted strings
        """,
        re.VERBOSE,
    )

    def _extract_keyword_terms(self, query: str) -> List[str]:
        """Extract distinctive terms suitable for keyword search.

        Returns code-like identifiers and multi-word quoted phrases that
        embedding models typically struggle with.
        """
        terms: List[str] = []
        for m in self._CODE_TERM_RE.finditer(query):
            term = m.group().strip("\"'")
            if len(term) >= 4:
                terms.append(term)

        # Also grab any word containing underscores (common code pattern)
        for word in query.split():
            cleaned = word.strip("?,.:;!\"'()[]{}=<>")
            if "_" in cleaned and len(cleaned) >= 4 and cleaned not in terms:
                terms.append(cleaned)

        return terms

    async def _keyword_search_postgres(
        self,
        query: str,
        document_filter: Optional[List[str]] = None,
        exclude_chunk_ids: Optional[set] = None,
        max_results: int = 5,
    ) -> List[DocumentChunk]:
        """Search Postgres knowledge_chunks using the GIN full-text index.

        Only runs when the query contains code-like or precise terms that
        embeddings may miss.  Returns chunks not already in the semantic
        result set (identified by *exclude_chunk_ids*).
        """
        terms = self._extract_keyword_terms(query)
        if not terms:
            return []

        try:
            from sqlalchemy import text as sa_text

            from ..database.connection import db_manager

            if not db_manager.AsyncSessionLocal:
                db_manager.initialize()

            # Build a Postgres full-text query.  Use plainto_tsquery for
            # each term (handles special chars safely) joined with OR.
            # Also do an ILIKE fallback for code identifiers that
            # to_tsvector tokenises differently (e.g. underscores).
            ts_clauses = []
            ilike_clauses = []
            params: Dict[str, Any] = {}
            for i, term in enumerate(terms):
                pname = f"t{i}"
                ts_clauses.append(
                    f"to_tsvector('english', kc.content) "
                    f"@@ plainto_tsquery('english', :{pname})"
                )
                ilike_clauses.append(f"kc.content ILIKE :{pname}_like")
                params[pname] = term
                params[f"{pname}_like"] = f"%{term}%"

            where_ts = " OR ".join(ts_clauses)
            where_ilike = " OR ".join(ilike_clauses)

            filter_clause = ""
            if document_filter:
                filter_clause = "AND kc.source_id = ANY(:doc_filter)"
                params["doc_filter"] = document_filter

            sql = f"""
                SELECT kc.id, kc.source_id, kc.content, kc.metadata,
                       ks.title AS document_title
                FROM multimodal_librarian.knowledge_chunks kc
                JOIN multimodal_librarian.knowledge_sources ks
                  ON kc.source_id = ks.id
                WHERE ({where_ts} OR {where_ilike})
                  {filter_clause}
                ORDER BY kc.created_at DESC
                LIMIT :lim
            """
            params["lim"] = max_results * 3  # fetch extra, dedup below

            async with db_manager.get_async_session() as session:
                result = await session.execute(sa_text(sql), params)
                rows = result.fetchall()

            if not rows:
                return []

            exclude = exclude_chunk_ids or set()
            chunks: List[DocumentChunk] = []
            for row in rows:
                chunk_id = str(row[0])
                if chunk_id in exclude:
                    continue
                source_id = str(row[1])
                content = row[2] or ""
                metadata = row[3] if isinstance(row[3], dict) else (
                    json.loads(row[3]) if row[3] else {}
                )
                doc_title = row[4] or metadata.get("title", "Unknown")

                page_number = metadata.get("page_number")

                chunk = DocumentChunk(
                    chunk_id=chunk_id,
                    document_id=source_id,
                    document_title=doc_title,
                    content=content,
                    page_number=page_number,
                    section_title=metadata.get("section_title"),
                    chunk_type=metadata.get("chunk_type", "text"),
                    # Assign a score between semantic threshold and
                    # confidence threshold so keyword-only hits appear
                    # in results but don't outrank strong semantic hits.
                    similarity_score=0.60,
                    metadata={**metadata, "keyword_match": True},
                )
                chunks.append(chunk)
                if len(chunks) >= max_results:
                    break

            logger.info(
                "Keyword search: %d terms -> %d rows -> %d new chunks",
                len(terms), len(rows), len(chunks),
            )
            return chunks

        except Exception as e:
            logger.warning("Keyword search failed (non-fatal): %s", e)
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
        
        system_prompt = f"""You are Librarian, a helpful and knowledgeable AI assistant. You help users find answers by summarizing and synthesizing information from their document library and, when relevant, supplementary web search results.

Your role is to report what the documents say — you are a research assistant summarizing source material, not providing personal advice.

SOURCES:
{context}{kg_context}

Instructions:
- Use the provided sources to answer the user's question
- Always cite sources using the format [Source X] when referencing information
- Sources may come from the user's document library or from web search — use all of them
- If knowledge graph insights are provided, use them to enhance your understanding of relationships between concepts
- If the sources don't fully answer the question, say so and provide what information you can
- When sources contain medical, legal, financial, or other professional content, summarize what the documents say. Frame answers as "According to [Source X]..." rather than as personal advice. You may add a brief disclaimer that users should consult a qualified professional.
- Be accurate and helpful in your responses
- If you're unsure about something, acknowledge the uncertainty"""

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
        preferred_provider: Optional[str] = None,
        skip_retrieval: bool = False,
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
        
        # Use a conversational prompt when retrieval was intentionally skipped
        if skip_retrieval:
            system_content = (
                "You are Librarian, a friendly and knowledgeable AI assistant. "
                "Respond naturally to the user's message. You can help with general questions, "
                "conversation, and guidance. Keep responses concise and helpful."
            )
        else:
            system_content = (
                "You are a helpful AI assistant. The user asked a question but no relevant "
                "documents were found in their library. Provide a helpful general response "
                "and suggest they might want to upload relevant documents if their question "
                "is about specific content."
            )
        
        # Add system context — insert at the beginning
        system_message = {
            "role": "system",
            "content": system_content,
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
        
        # Apply relevance detection adjustment (Requirements 4.4, 4.5)
        verdict = self._last_relevance_verdict
        if verdict is not None:
            if not verdict.is_relevant:
                confidence = min(confidence, 0.3)
            else:
                confidence *= verdict.confidence_adjustment_factor
        
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
                    embedding=np.zeros(768),  # Placeholder embedding
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