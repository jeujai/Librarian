"""
Source Prioritization Engine for RAG Retrieval.

This module implements source prioritization for RAG retrieval, ensuring
Librarian documents are searched first and ranked higher than external sources.

Requirements: 5.1, 5.5, 5.6
"""

import logging
import time
from enum import Enum
from typing import TYPE_CHECKING, Any, Dict, List, Optional

from pydantic import BaseModel, Field

if TYPE_CHECKING:
    from ..clients.protocols import VectorStoreClient
    from ..components.knowledge_graph.kg_query_engine import KnowledgeGraphQueryEngine

logger = logging.getLogger(__name__)


class SearchSourceType(Enum):
    """
    Source types for search results in RAG retrieval.
    
    This enum is distinct from models.core.SourceType which represents
    document source types (BOOK, CONVERSATION). This enum represents
    the origin of search results for prioritization purposes.
    
    Requirements: 5.5
    """
    LIBRARIAN = "librarian"      # Documents uploaded to Multimodal Librarian
    WEB_SEARCH = "web_search"    # External web search results
    LLM_FALLBACK = "llm_fallback"  # AI-generated responses without context


class PrioritizedSearchResult(BaseModel):
    """
    Search result with source type annotation for prioritization.
    
    This model extends basic search results with source type information
    and tracks both original and boosted scores for transparency.
    
    Requirements: 5.5
    """
    chunk_id: str
    document_id: str
    document_title: str
    content: str
    score: float = Field(ge=0.0, le=1.0, description="Final score after boost")
    original_score: float = Field(ge=0.0, le=1.0, description="Score before boost")
    source_type: SearchSourceType
    page_number: Optional[int] = None
    section_title: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)
    
    class Config:
        use_enum_values = False  # Keep enum objects, not just values


class PrioritizedSearchResults(BaseModel):
    """
    Collection of prioritized search results with aggregated metadata.
    
    Requirements: 5.1, 5.5
    """
    results: List[PrioritizedSearchResult] = Field(default_factory=list)
    librarian_count: int = 0
    web_count: int = 0
    total_count: int = 0
    search_time_ms: int = 0
    
    class Config:
        use_enum_values = False



class SourcePrioritizationEngine:
    """
    Manages search source prioritization for RAG retrieval.
    
    This engine ensures Librarian documents are searched first and ranked
    higher than external sources. It applies a configurable boost factor
    to Librarian document scores to ensure they rank above equivalent
    external results.
    
    The prioritization order is:
    1. Librarian documents (uploaded PDFs) - highest priority
    2. Web search results (optional) - secondary
    3. LLM fallback - tertiary (when no relevant documents found)
    
    Requirements: 5.1, 5.5, 5.6
    
    Usage:
        engine = SourcePrioritizationEngine(
            vector_client=injected_client,
            librarian_boost_factor=1.5
        )
        results = await engine.search_with_prioritization(
            query="What is machine learning?",
            user_id="user123"
        )
    """
    
    def __init__(
        self,
        vector_client: "VectorStoreClient",
        kg_query_engine: Optional["KnowledgeGraphQueryEngine"] = None,
        web_search_client: Optional[Any] = None,
        librarian_boost_factor: float = 1.5,
        min_confidence_threshold: float = 0.35
    ):
        """
        Initialize the source prioritization engine.
        
        Args:
            vector_client: Vector store client for Librarian document search.
                          Works with both Milvus (local) and OpenSearch (AWS).
            kg_query_engine: Optional knowledge graph query engine for
                            enhanced retrieval.
            web_search_client: Optional web search client for external results.
                              Currently not implemented.
            librarian_boost_factor: Score multiplier for Librarian results.
                                   Default 1.5 means 50% boost. Must be >= 1.0.
            min_confidence_threshold: Minimum score threshold for results.
                                     Results below this are filtered out.
        
        Raises:
            ValueError: If vector_client is None or boost_factor < 1.0
            
        Requirements: 5.6
        """
        if vector_client is None:
            raise ValueError("vector_client is required")
        if librarian_boost_factor < 1.0:
            raise ValueError("librarian_boost_factor must be >= 1.0")
        
        self.vector_client = vector_client
        self.kg_query_engine = kg_query_engine
        self.web_search_client = web_search_client
        self.librarian_boost_factor = librarian_boost_factor
        self.min_confidence_threshold = min_confidence_threshold
        
        logger.info(
            f"SourcePrioritizationEngine initialized with "
            f"boost_factor={librarian_boost_factor}, "
            f"threshold={min_confidence_threshold}"
        )
    
    async def search_with_prioritization(
        self,
        query: str,
        user_id: str,
        min_confidence: Optional[float] = None,
        max_results: int = 10,
        enable_web_search: bool = False,
        document_filter: Optional[List[str]] = None
    ) -> PrioritizedSearchResults:
        """
        Search with source prioritization.
        
        Searches Librarian documents first, applies boost factor to scores,
        and optionally merges with web search results while maintaining
        priority ordering.
        
        Args:
            query: Search query text
            user_id: User identifier for filtering user-specific documents
            min_confidence: Minimum confidence threshold. Uses instance
                           default if not specified.
            max_results: Maximum number of results to return
            enable_web_search: Whether to include web search as fallback.
                              Currently not implemented.
            document_filter: Optional list of document IDs to restrict search
            
        Returns:
            PrioritizedSearchResults with source-tagged and ranked results
            
        Requirements: 5.1, 5.5, 5.6
        """
        start_time = time.time()
        threshold = min_confidence if min_confidence is not None else self.min_confidence_threshold
        
        try:
            # Step 1: Search Librarian documents first (Requirement 5.1)
            librarian_results = await self._search_librarian_documents(
                query=query,
                user_id=user_id,
                max_results=max_results,
                min_confidence=threshold,
                document_filter=document_filter
            )
            
            # Step 2: Apply Librarian boost (Requirement 5.6)
            boosted_results = self._apply_librarian_boost(librarian_results)
            
            # Step 3: Optionally search web (Requirement 5.3)
            web_results: List[PrioritizedSearchResult] = []
            if enable_web_search and self.web_search_client is not None:
                # Web search integration - placeholder for future implementation
                logger.debug("Web search enabled but not yet implemented")
            
            # Step 4: Merge and rank results
            final_results = self._merge_and_rank_results(boosted_results, web_results)
            
            # Limit to max_results
            final_results = final_results[:max_results]
            
            search_time_ms = int((time.time() - start_time) * 1000)
            
            return PrioritizedSearchResults(
                results=final_results,
                librarian_count=len([r for r in final_results if r.source_type == SearchSourceType.LIBRARIAN]),
                web_count=len([r for r in final_results if r.source_type == SearchSourceType.WEB_SEARCH]),
                total_count=len(final_results),
                search_time_ms=search_time_ms
            )
            
        except Exception as e:
            logger.error(f"Search with prioritization failed: {e}")
            search_time_ms = int((time.time() - start_time) * 1000)
            return PrioritizedSearchResults(
                results=[],
                librarian_count=0,
                web_count=0,
                total_count=0,
                search_time_ms=search_time_ms
            )
    
    async def _search_librarian_documents(
        self,
        query: str,
        user_id: str,
        max_results: int,
        min_confidence: float,
        document_filter: Optional[List[str]] = None
    ) -> List[PrioritizedSearchResult]:
        """
        Search Librarian documents using vector store.
        
        Args:
            query: Search query
            user_id: User identifier
            max_results: Maximum results to return
            min_confidence: Minimum confidence threshold
            document_filter: Optional document ID filter
            
        Returns:
            List of PrioritizedSearchResult from Librarian documents
        """
        try:
            # Ensure connection
            if hasattr(self.vector_client, 'is_connected'):
                if not self.vector_client.is_connected():
                    if hasattr(self.vector_client, 'connect'):
                        await self.vector_client.connect()
            
            # Perform semantic search
            if hasattr(self.vector_client, 'semantic_search_async'):
                search_results = await self.vector_client.semantic_search_async(
                    query=query,
                    top_k=max_results,
                    source_type="document",
                    source_id=None
                )
            else:
                search_results = await self.vector_client.semantic_search(
                    query=query,
                    top_k=max_results
                )
            
            # Convert to PrioritizedSearchResult
            results = []
            for result in search_results:
                # Get similarity score - handle different result formats
                similarity_score = result.get('similarity_score', result.get('score', 0))
                
                # Skip results below threshold
                if similarity_score < min_confidence:
                    continue
                
                # Get metadata
                metadata = result.get('metadata', {})
                
                # Get document ID
                document_id = result.get('source_id', metadata.get('source_id', 'unknown'))
                
                # Apply document filter if specified
                if document_filter and document_id not in document_filter:
                    continue
                
                prioritized_result = PrioritizedSearchResult(
                    chunk_id=result.get('chunk_id', result.get('id', result.get('doc_id', ''))),
                    document_id=document_id,
                    document_title=result.get('document_title', metadata.get('title', 'Unknown Document')),
                    content=result.get('content', metadata.get('content', '')),
                    score=similarity_score,  # Will be boosted later
                    original_score=similarity_score,
                    source_type=SearchSourceType.LIBRARIAN,
                    page_number=result.get('page_number', metadata.get('page_number')),
                    section_title=result.get('section_title', metadata.get('section_title')),
                    metadata=metadata
                )
                results.append(prioritized_result)
            
            logger.info(f"Found {len(results)} Librarian results for query: {query[:50]}...")
            return results
            
        except Exception as e:
            logger.error(f"Librarian document search failed: {e}")
            return []
    
    def _apply_librarian_boost(
        self,
        results: List[PrioritizedSearchResult]
    ) -> List[PrioritizedSearchResult]:
        """
        Apply boost factor to Librarian document scores.
        
        Multiplies the score of Librarian results by the boost factor,
        capping at 1.0 to maintain valid score range.
        
        Args:
            results: Search results to boost
            
        Returns:
            Results with boosted scores
            
        Requirements: 5.6
        """
        boosted_results = []
        
        for result in results:
            if result.source_type == SearchSourceType.LIBRARIAN:
                # Apply boost, cap at 1.0
                boosted_score = min(1.0, result.original_score * self.librarian_boost_factor)
                
                # Create new result with boosted score
                boosted_result = PrioritizedSearchResult(
                    chunk_id=result.chunk_id,
                    document_id=result.document_id,
                    document_title=result.document_title,
                    content=result.content,
                    score=boosted_score,
                    original_score=result.original_score,
                    source_type=result.source_type,
                    page_number=result.page_number,
                    section_title=result.section_title,
                    metadata={
                        **result.metadata,
                        'librarian_boost_applied': True,
                        'boost_factor': self.librarian_boost_factor
                    }
                )
                boosted_results.append(boosted_result)
            else:
                boosted_results.append(result)
        
        logger.debug(f"Applied Librarian boost to {len(boosted_results)} results")
        return boosted_results
    
    def _merge_and_rank_results(
        self,
        librarian_results: List[PrioritizedSearchResult],
        web_results: List[PrioritizedSearchResult]
    ) -> List[PrioritizedSearchResult]:
        """
        Merge results from multiple sources, maintaining priority.
        
        Combines Librarian and web results, sorting by boosted score.
        Librarian results naturally rank higher due to boost factor.
        
        Args:
            librarian_results: Results from Librarian documents (boosted)
            web_results: Results from web search
            
        Returns:
            Merged and ranked results
            
        Requirements: 5.1
        """
        # Combine all results
        all_results = librarian_results + web_results
        
        # Sort by score (descending) - Librarian results rank higher due to boost
        all_results.sort(key=lambda x: x.score, reverse=True)
        
        logger.debug(
            f"Merged {len(librarian_results)} Librarian + "
            f"{len(web_results)} web results = {len(all_results)} total"
        )
        
        return all_results
    
    def get_engine_status(self) -> Dict[str, Any]:
        """
        Get current engine configuration and status.
        
        Returns:
            Dictionary with engine configuration
        """
        return {
            "librarian_boost_factor": self.librarian_boost_factor,
            "min_confidence_threshold": self.min_confidence_threshold,
            "web_search_enabled": self.web_search_client is not None,
            "kg_query_enabled": self.kg_query_engine is not None,
            "vector_client_type": type(self.vector_client).__name__
        }
