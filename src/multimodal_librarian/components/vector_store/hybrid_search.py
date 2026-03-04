"""
Hybrid Search Engine for Multimodal Librarian.

This module implements hybrid search combining vector similarity with keyword matching,
advanced re-ranking using cross-encoders, and query expansion for improved search accuracy.
"""

import asyncio
import logging
import math
import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional, Set, Tuple

import numpy as np
from scipy import sparse

# LAZY IMPORTS: sentence_transformers is imported lazily to prevent blocking during startup
# from sentence_transformers import SentenceTransformer, CrossEncoder
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

from ...models.core import ContentType, KnowledgeChunk, SourceType

# Import search models first to avoid circular imports
from ...models.search_types import (
    HybridSearchResult,
    QueryComplexity,
    QueryContext,
    QueryEntity,
    QueryIntent,
    QueryRelation,
    SearchFacets,
    SearchQuery,
    SearchResult,
    UnderstoodQuery,
)
from .vector_store import VectorStore, VectorStoreError

logger = logging.getLogger(__name__)


@dataclass
class TfidfIndex:
    """
    TF-IDF index for keyword search.
    
    Stores the vectorizer, document vectors, and metadata for efficient
    keyword-based search operations.
    """
    vectorizer: TfidfVectorizer
    document_vectors: sparse.csr_matrix  # Sparse matrix of TF-IDF vectors
    document_ids: List[str]  # Chunk IDs in order
    document_metadata: Dict[str, Dict[str, Any]]  # Metadata keyed by chunk_id
    last_updated: datetime = field(default_factory=datetime.now)
    
    def __post_init__(self):
        """Validate index consistency."""
        if len(self.document_ids) != self.document_vectors.shape[0]:
            raise ValueError(
                f"Mismatch: {len(self.document_ids)} document IDs but "
                f"{self.document_vectors.shape[0]} document vectors"
            )


@dataclass
class HybridSearchConfig:
    """Configuration for hybrid search parameters."""
    vector_weight: float = 0.7  # Weight for vector similarity
    keyword_weight: float = 0.3  # Weight for keyword matching
    rerank_top_k: int = 50  # Number of results to re-rank
    final_top_k: int = 10  # Final number of results to return
    query_expansion_terms: int = 5  # Number of expansion terms to add
    enable_cross_encoder: bool = True  # Use cross-encoder for re-ranking
    enable_query_expansion: bool = True  # Enable query expansion
    enable_faceted_search: bool = True  # Enable faceted search
    cache_results: bool = True  # Cache search results
    cache_ttl_seconds: int = 300  # Cache TTL in seconds


class QueryExpander:
    """Handles query expansion using various techniques."""
    
    def __init__(self):
        self.synonym_dict = self._load_synonyms()
        self.domain_terms = self._load_domain_terms()
    
    def expand_query(self, query: SearchQuery, search_results: List[SearchResult]) -> str:
        """
        Expand query with related terms from various sources.
        
        Args:
            query: Original search query
            search_results: Initial search results for context
            
        Returns:
            Expanded query string
        """
        expanded_terms = set(query.key_terms)
        
        # Add synonyms
        for term in query.key_terms:
            if term in self.synonym_dict:
                expanded_terms.update(self.synonym_dict[term][:2])  # Top 2 synonyms
        
        # Add domain-specific terms
        for term in query.key_terms:
            if term in self.domain_terms:
                expanded_terms.update(self.domain_terms[term][:2])
        
        # Add terms from top search results (pseudo-relevance feedback)
        if search_results:
            result_terms = self._extract_terms_from_results(search_results[:3])
            expanded_terms.update(result_terms[:2])
        
        # Combine original and expanded terms
        all_terms = list(expanded_terms)
        expanded_query = f"{query.processed_query} {' '.join(all_terms[:5])}"
        
        logger.debug(f"Expanded query from '{query.original_query}' to '{expanded_query}'")
        return expanded_query
    
    def _load_synonyms(self) -> Dict[str, List[str]]:
        """Load synonym dictionary for query expansion."""
        # Basic synonym mapping - in production, this could be loaded from a file or API
        return {
            "machine learning": ["ml", "artificial intelligence", "ai", "deep learning"],
            "neural network": ["nn", "deep network", "artificial neural network"],
            "database": ["db", "data store", "repository", "storage"],
            "algorithm": ["method", "procedure", "technique", "approach"],
            "optimization": ["optimization", "tuning", "improvement", "enhancement"],
            "performance": ["speed", "efficiency", "throughput", "latency"],
            "security": ["safety", "protection", "privacy", "encryption"],
            "analysis": ["examination", "study", "investigation", "evaluation"],
            "implementation": ["development", "coding", "programming", "building"],
            "framework": ["library", "toolkit", "platform", "system"]
        }
    
    def _load_domain_terms(self) -> Dict[str, List[str]]:
        """Load domain-specific term mappings."""
        return {
            "python": ["programming", "code", "script", "development"],
            "javascript": ["js", "web", "frontend", "backend"],
            "react": ["component", "jsx", "frontend", "ui"],
            "docker": ["container", "deployment", "devops", "kubernetes"],
            "aws": ["cloud", "amazon", "ec2", "s3", "lambda"],
            "api": ["endpoint", "rest", "http", "service"],
            "data": ["information", "dataset", "records", "analytics"],
            "model": ["algorithm", "prediction", "training", "inference"]
        }
    
    def _extract_terms_from_results(self, results: List[SearchResult]) -> List[str]:
        """Extract relevant terms from search results for expansion."""
        text = " ".join([result.content for result in results])
        
        # Simple term extraction - could be enhanced with NLP
        words = re.findall(r'\b[a-zA-Z]{3,}\b', text.lower())
        word_counts = Counter(words)
        
        # Return most frequent terms that aren't too common
        common_words = {'the', 'and', 'for', 'are', 'but', 'not', 'you', 'all', 'can', 'had', 'her', 'was', 'one', 'our', 'out', 'day', 'get', 'has', 'him', 'his', 'how', 'man', 'new', 'now', 'old', 'see', 'two', 'way', 'who', 'boy', 'did', 'its', 'let', 'put', 'say', 'she', 'too', 'use'}
        
        relevant_terms = [
            word for word, count in word_counts.most_common(10)
            if word not in common_words and len(word) > 3
        ]
        
        return relevant_terms[:5]


class CrossEncoderReranker:
    """Handles result re-ranking using cross-encoder models via model server."""
    
    def __init__(self):
        self._model_server_client = None
        logger.info("CrossEncoderReranker created (using model server)")
    
    async def _get_model_server_client(self):
        """Get or initialize the model server client."""
        if self._model_server_client is None:
            try:
                from ...clients.model_server_client import (
                    get_model_client,
                    initialize_model_client,
                )
                
                client = get_model_client()
                if client is None:
                    await initialize_model_client()
                    client = get_model_client()
                
                if client and client.enabled:
                    self._model_server_client = client
            except Exception as e:
                logger.warning(f"Model server not available: {e}")
        return self._model_server_client
    
    def rerank_results(self, query: str, results: List[HybridSearchResult]) -> List[HybridSearchResult]:
        """
        Re-rank search results using hybrid scores (sync version).
        
        For cross-encoder re-ranking, use rerank_results_async().
        
        Args:
            query: Search query
            results: Initial search results
            
        Returns:
            Re-ranked results with updated scores
        """
        if not results:
            return results
        
        # Use hybrid scores as final scores
        for result in results:
            result.final_score = result.hybrid_score
        
        # Sort by final score
        results.sort(key=lambda x: x.final_score, reverse=True)
        return results
    
    async def rerank_results_async(self, query: str, results: List[HybridSearchResult]) -> List[HybridSearchResult]:
        """
        Re-rank search results using model server (async version).
        
        Args:
            query: Search query
            results: Initial search results
            
        Returns:
            Re-ranked results with updated scores
        """
        if not results:
            return results
        
        # For now, use hybrid scores as final scores
        # Cross-encoder re-ranking can be added to model server later
        for result in results:
            result.final_score = result.hybrid_score
        
        # Sort by final score
        results.sort(key=lambda x: x.final_score, reverse=True)
        return results


class HybridSearchEngine:
    """
    Advanced hybrid search engine combining vector similarity with keyword matching.
    
    Features:
    - Hybrid scoring (vector + keyword)
    - Cross-encoder re-ranking
    - Query expansion
    - Faceted search
    - Result caching
    - Performance analytics
    """
    
    def __init__(self, vector_store: VectorStore, config: Optional[HybridSearchConfig] = None):
        """
        Initialize hybrid search engine.
        
        Args:
            vector_store: Vector database instance
            config: Search configuration parameters
        """
        self.vector_store = vector_store
        self.config = config or HybridSearchConfig()
        
        # Initialize components
        self.query_expander = QueryExpander()
        self.reranker = CrossEncoderReranker()
        self.tfidf_vectorizer = TfidfVectorizer(
            max_features=10000,
            stop_words='english',
            ngram_range=(1, 2)
        )
        
        # TF-IDF index for keyword search
        self._tfidf_index: Optional[TfidfIndex] = None
        self._document_cache: Dict[str, Dict[str, Any]] = {}  # Cache of indexed documents
        
        # Caching and analytics
        self.result_cache = {}
        self.search_analytics = defaultdict(int)
        self.tfidf_fitted = False
        
        logger.info("Hybrid search engine initialized")
    
    async def search(
        self,
        query: str,
        top_k: Optional[int] = None,
        source_type: Optional[SourceType] = None,
        content_type: Optional[ContentType] = None,
        source_id: Optional[str] = None,
        enable_reranking: bool = True,
        enable_expansion: bool = True
    ) -> Tuple[List[HybridSearchResult], SearchFacets]:
        """
        Perform hybrid search with advanced features.
        
        Args:
            query: Search query string
            top_k: Number of results to return
            source_type: Filter by source type
            content_type: Filter by content type
            source_id: Filter by source ID
            enable_reranking: Whether to use cross-encoder re-ranking
            enable_expansion: Whether to expand the query
            
        Returns:
            Tuple of (search results, facets)
        """
        top_k = top_k or self.config.final_top_k
        
        # Check cache first
        cache_key = self._generate_cache_key(query, source_type, content_type, source_id)
        if self.config.cache_results and cache_key in self.result_cache:
            cached_result = self.result_cache[cache_key]
            if (datetime.now() - cached_result['timestamp']).seconds < self.config.cache_ttl_seconds:
                logger.debug(f"Returning cached results for query: {query}")
                return cached_result['results'], cached_result['facets']
        
        # Process query
        search_query = SearchQuery.from_text(query)
        
        # Step 1: Vector similarity search
        vector_results = await self._vector_search(search_query, source_type, content_type, source_id)
        
        # Step 2: Keyword matching
        keyword_results = await self._keyword_search(search_query, source_type, content_type, source_id)
        
        # Step 3: Combine and score results
        hybrid_results = self._combine_results(vector_results, keyword_results, search_query)
        
        # Step 4: Query expansion and re-search if enabled
        if enable_expansion and self.config.enable_query_expansion:
            expanded_query = self.query_expander.expand_query(search_query, [r.search_result for r in hybrid_results[:5]])
            if expanded_query != search_query.processed_query:
                expanded_search_query = SearchQuery.from_text(expanded_query)
                expanded_vector_results = await self._vector_search(expanded_search_query, source_type, content_type, source_id)
                expanded_keyword_results = await self._keyword_search(expanded_search_query, source_type, content_type, source_id)
                expanded_hybrid_results = self._combine_results(expanded_vector_results, expanded_keyword_results, expanded_search_query)
                
                # Merge with original results
                hybrid_results = self._merge_result_sets(hybrid_results, expanded_hybrid_results)
        
        # Step 5: Cross-encoder re-ranking if enabled
        if enable_reranking and self.config.enable_cross_encoder:
            hybrid_results = self.reranker.rerank_results(query, hybrid_results[:self.config.rerank_top_k])
        else:
            # Use hybrid scores as final scores
            for result in hybrid_results:
                result.final_score = result.hybrid_score
        
        # Step 6: Generate facets
        facets = self._generate_facets(hybrid_results)
        
        # Step 7: Limit results
        final_results = hybrid_results[:top_k]
        
        # Cache results
        if self.config.cache_results:
            self.result_cache[cache_key] = {
                'results': final_results,
                'facets': facets,
                'timestamp': datetime.now()
            }
        
        # Update analytics
        self.search_analytics['total_searches'] += 1
        self.search_analytics[f'query_type_{search_query.query_type}'] += 1
        
        logger.info(f"Hybrid search completed: {len(final_results)} results for '{query}'")
        return final_results, facets
    
    async def build_keyword_index(
        self,
        documents: List[Dict[str, Any]]
    ) -> None:
        """
        Build TF-IDF index from documents for keyword search.
        
        This method creates a TF-IDF index from the provided documents,
        enabling efficient keyword-based search operations. The index
        is cached for performance.
        
        Args:
            documents: List of document dictionaries with 'chunk_id', 'content',
                      and optional metadata fields
                      
        Requirements: 7.5 - Cache TF-IDF vectors for indexed documents
        """
        if not documents:
            logger.warning("No documents provided for keyword index")
            return
        
        try:
            # Extract content and metadata
            contents = []
            chunk_ids = []
            metadata = {}
            
            for doc in documents:
                chunk_id = doc.get('chunk_id')
                content = doc.get('content', '')
                
                if not chunk_id or not content:
                    continue
                
                contents.append(content)
                chunk_ids.append(chunk_id)
                metadata[chunk_id] = {
                    'source_type': doc.get('source_type'),
                    'source_id': doc.get('source_id'),
                    'content_type': doc.get('content_type'),
                    'section': doc.get('section', ''),
                    'location_reference': doc.get('location_reference', ''),
                    'created_at': doc.get('created_at'),
                    'is_bridge': doc.get('is_bridge', False),
                }
                
                # Cache document for later retrieval
                self._document_cache[chunk_id] = doc
            
            if not contents:
                logger.warning("No valid documents to index")
                return
            
            # Create new vectorizer for this index
            vectorizer = TfidfVectorizer(
                max_features=10000,
                stop_words='english',
                ngram_range=(1, 2),
                min_df=1,  # Include terms that appear in at least 1 document
                max_df=0.95,  # Exclude terms that appear in >95% of documents
            )
            
            # Fit and transform documents
            document_vectors = vectorizer.fit_transform(contents)
            
            # Create the index
            self._tfidf_index = TfidfIndex(
                vectorizer=vectorizer,
                document_vectors=document_vectors,
                document_ids=chunk_ids,
                document_metadata=metadata,
                last_updated=datetime.now()
            )
            
            self.tfidf_fitted = True
            logger.info(f"Built TF-IDF index with {len(chunk_ids)} documents, "
                       f"{document_vectors.shape[1]} features")
            
        except Exception as e:
            logger.error(f"Failed to build keyword index: {e}")
            raise
    
    async def _vector_search(
        self,
        query: SearchQuery,
        source_type: Optional[SourceType] = None,
        content_type: Optional[ContentType] = None,
        source_id: Optional[str] = None
    ) -> List[SearchResult]:
        """Perform vector similarity search (non-blocking)."""
        try:
            # Use async version to avoid blocking the event loop
            if hasattr(self.vector_store, 'semantic_search_async'):
                vector_results = await self.vector_store.semantic_search_async(
                    query.processed_query,
                    top_k=self.config.rerank_top_k,
                    source_type=source_type,
                    content_type=content_type,
                    source_id=source_id
                )
            else:
                # Fallback to sync version in thread pool to avoid blocking
                loop = asyncio.get_event_loop()
                vector_results = await loop.run_in_executor(
                    None,  # Use default executor
                    lambda: self.vector_store.semantic_search(
                        query.processed_query,
                        top_k=self.config.rerank_top_k,
                        source_type=source_type,
                        content_type=content_type,
                        source_id=source_id
                    )
                )
            
            return [SearchResult.from_vector_result(result) for result in vector_results]
            
        except Exception as e:
            logger.error(f"Vector search failed: {e}")
            return []
    
    async def _keyword_search(
        self,
        query: SearchQuery,
        source_type: Optional[SourceType] = None,
        content_type: Optional[ContentType] = None,
        source_id: Optional[str] = None
    ) -> List[SearchResult]:
        """
        Perform keyword-based search using TF-IDF.
        
        Uses the pre-built TF-IDF index to find documents matching
        the query terms. Returns results with TF-IDF similarity scores.
        
        Args:
            query: Search query with processed text and key terms
            source_type: Optional filter by source type
            content_type: Optional filter by content type
            source_id: Optional filter by source ID
            
        Returns:
            List of SearchResult objects with keyword similarity scores
            
        Requirements: 7.1, 7.2 - Implement keyword search using TF-IDF
        """
        try:
            # Check if index is available
            if self._tfidf_index is None or not self.tfidf_fitted:
                logger.debug("TF-IDF index not available, skipping keyword search")
                return []
            
            # Transform query using the fitted vectorizer
            query_vector = self._tfidf_index.vectorizer.transform([query.processed_query])
            
            # Calculate cosine similarity between query and all documents
            similarities = cosine_similarity(
                query_vector, 
                self._tfidf_index.document_vectors
            ).flatten()
            
            # Get indices of documents with non-zero similarity, sorted by score
            non_zero_indices = np.where(similarities > 0)[0]
            if len(non_zero_indices) == 0:
                logger.debug(f"No keyword matches found for query: {query.processed_query}")
                return []
            
            # Sort by similarity score (descending)
            sorted_indices = non_zero_indices[np.argsort(similarities[non_zero_indices])[::-1]]
            
            # Build results with filtering
            results = []
            for idx in sorted_indices[:self.config.rerank_top_k]:
                chunk_id = self._tfidf_index.document_ids[idx]
                score = float(similarities[idx])
                metadata = self._tfidf_index.document_metadata.get(chunk_id, {})
                
                # Apply filters
                if source_type and metadata.get('source_type') != source_type:
                    continue
                if content_type and metadata.get('content_type') != content_type:
                    continue
                if source_id and metadata.get('source_id') != source_id:
                    continue
                
                # Get full document from cache
                doc = self._document_cache.get(chunk_id, {})
                content = doc.get('content', '')
                
                # Handle enum conversion for source_type
                doc_source_type = metadata.get('source_type')
                if isinstance(doc_source_type, str):
                    try:
                        doc_source_type = SourceType(doc_source_type)
                    except ValueError:
                        doc_source_type = SourceType.BOOK  # Default to BOOK
                elif doc_source_type is None:
                    doc_source_type = SourceType.BOOK
                
                # Handle enum conversion for content_type
                doc_content_type = metadata.get('content_type')
                if isinstance(doc_content_type, str):
                    try:
                        doc_content_type = ContentType(doc_content_type)
                    except ValueError:
                        doc_content_type = ContentType.GENERAL  # Default to GENERAL
                elif doc_content_type is None:
                    doc_content_type = ContentType.GENERAL
                
                # Create SearchResult
                result = SearchResult(
                    chunk_id=chunk_id,
                    content=content,
                    source_type=doc_source_type,
                    source_id=metadata.get('source_id', ''),
                    content_type=doc_content_type,
                    location_reference=metadata.get('location_reference', ''),
                    section=metadata.get('section', ''),
                    similarity_score=score,
                    relevance_score=score,
                    is_bridge=metadata.get('is_bridge', False),
                    created_at=metadata.get('created_at'),
                )
                results.append(result)
            
            logger.debug(f"Keyword search found {len(results)} results for query: {query.processed_query}")
            return results
            
        except Exception as e:
            logger.error(f"Keyword search failed: {e}")
            return []
    
    def _combine_results(
        self,
        vector_results: List[SearchResult],
        keyword_results: List[SearchResult],
        query: SearchQuery
    ) -> List[HybridSearchResult]:
        """
        Combine vector and keyword results with hybrid scoring.
        
        Implements weighted combination of vector and keyword scores,
        with fallback to keyword results when vector search returns empty.
        
        Args:
            vector_results: Results from vector similarity search
            keyword_results: Results from keyword/TF-IDF search
            query: The search query
            
        Returns:
            List of HybridSearchResult with combined scores
            
        Requirements: 7.3 - Combine keyword scores with vector scores using configurable weights
        Requirements: 7.4 - Return keyword search results as fallback when vector returns empty
        """
        # Create a map of all unique results
        result_map = {}
        
        # Check if we need to use keyword fallback
        use_keyword_fallback = len(vector_results) == 0 and len(keyword_results) > 0
        
        if use_keyword_fallback:
            logger.info("Vector search returned no results, using keyword fallback")
        
        # Add vector results
        for result in vector_results:
            hybrid_result = HybridSearchResult(
                search_result=result,
                vector_score=result.similarity_score,
                keyword_score=0.0,
                hybrid_score=0.0
            )
            result_map[result.chunk_id] = hybrid_result
        
        # Add keyword results and update scores
        for result in keyword_results:
            if result.chunk_id in result_map:
                result_map[result.chunk_id].keyword_score = result.similarity_score
            else:
                hybrid_result = HybridSearchResult(
                    search_result=result,
                    vector_score=0.0,
                    keyword_score=result.similarity_score,
                    hybrid_score=0.0
                )
                result_map[result.chunk_id] = hybrid_result
        
        # Calculate hybrid scores
        for hybrid_result in result_map.values():
            if use_keyword_fallback:
                # When using keyword fallback, use keyword score directly
                hybrid_result.hybrid_score = hybrid_result.keyword_score
                hybrid_result.explanation = f"Keyword fallback: {hybrid_result.keyword_score:.3f}"
            else:
                # Normal hybrid scoring with configurable weights
                hybrid_result.hybrid_score = (
                    self.config.vector_weight * hybrid_result.vector_score +
                    self.config.keyword_weight * hybrid_result.keyword_score
                )
                hybrid_result.explanation = (
                    f"Vector: {hybrid_result.vector_score:.3f} (w={self.config.vector_weight}) | "
                    f"Keyword: {hybrid_result.keyword_score:.3f} (w={self.config.keyword_weight})"
                )
        
        # Sort by hybrid score
        results = list(result_map.values())
        results.sort(key=lambda x: x.hybrid_score, reverse=True)
        
        return results
    
    def _merge_result_sets(
        self,
        original_results: List[HybridSearchResult],
        expanded_results: List[HybridSearchResult]
    ) -> List[HybridSearchResult]:
        """Merge original and expanded search results."""
        result_map = {r.search_result.chunk_id: r for r in original_results}
        
        # Add expanded results that aren't already present
        for result in expanded_results:
            if result.search_result.chunk_id not in result_map:
                # Reduce score slightly for expanded results
                result.hybrid_score *= 0.9
                result_map[result.search_result.chunk_id] = result
        
        # Sort combined results
        combined_results = list(result_map.values())
        combined_results.sort(key=lambda x: x.hybrid_score, reverse=True)
        
        return combined_results
    
    def _generate_facets(self, results: List[HybridSearchResult]) -> SearchFacets:
        """Generate search facets from results."""
        facets = SearchFacets()
        
        for result in results:
            sr = result.search_result
            
            # Source type facets
            source_type_key = sr.source_type.value
            facets.source_types[source_type_key] = facets.source_types.get(source_type_key, 0) + 1
            
            # Content type facets
            content_type_key = sr.content_type.value
            facets.content_types[content_type_key] = facets.content_types.get(content_type_key, 0) + 1
            
            # Source facets
            facets.sources[sr.source_id] = facets.sources.get(sr.source_id, 0) + 1
            
            # Section facets
            if sr.section:
                facets.sections[sr.section] = facets.sections.get(sr.section, 0) + 1
            
            # Date range facets
            if sr.created_at:
                date_key = sr.created_at.strftime('%Y-%m')
                facets.date_ranges[date_key] = facets.date_ranges.get(date_key, 0) + 1
        
        return facets
    
    def _generate_cache_key(
        self,
        query: str,
        source_type: Optional[SourceType],
        content_type: Optional[ContentType],
        source_id: Optional[str]
    ) -> str:
        """Generate cache key for search results."""
        key_parts = [query.lower()]
        if source_type:
            key_parts.append(f"st:{source_type.value}")
        if content_type:
            key_parts.append(f"ct:{content_type.value}")
        if source_id:
            key_parts.append(f"si:{source_id}")
        
        return "|".join(key_parts)
    
    def get_search_analytics(self) -> Dict[str, Any]:
        """Get search analytics and performance metrics."""
        return {
            'total_searches': self.search_analytics['total_searches'],
            'cache_size': len(self.result_cache),
            'query_types': {
                key.replace('query_type_', ''): value
                for key, value in self.search_analytics.items()
                if key.startswith('query_type_')
            },
            'cache_hit_rate': self._calculate_cache_hit_rate()
        }
    
    def _calculate_cache_hit_rate(self) -> float:
        """Calculate cache hit rate."""
        total = self.search_analytics['total_searches']
        if total == 0:
            return 0.0
        
        # This is a simplified calculation - in practice, you'd track cache hits separately
        return min(0.3, len(self.result_cache) / total)
    
    def clear_cache(self):
        """Clear the result cache."""
        self.result_cache.clear()
        logger.info("Search result cache cleared")