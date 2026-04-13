"""
Semantic Reranker Component for Knowledge Graph-Guided Retrieval.

This component re-ranks candidate chunks from Stage 1 (KG-based retrieval)
using semantic similarity to the query. It combines KG-based relevance scores
with semantic similarity scores for final ranking.

OPTIMIZED: Added query embedding cache and pre-filtering to reduce embedding calls.

Requirements: 3.2
"""

import hashlib
import logging
import re
import time
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

from ...config.scoring_weights import BRIDGE_WEIGHT, KG_WEIGHT
from ...models.kg_retrieval import RetrievedChunk

logger = logging.getLogger(__name__)


class SemanticReranker:
    """
    Re-ranks candidate chunks using semantic similarity.

    Combines KG-based relevance scores with semantic similarity
    for final ranking. Uses the model server for query embedding
    generation.

    OPTIMIZED:
    - Query embedding cache to avoid regenerating embeddings for repeated queries
    - Pre-filtering by KG score to limit chunks before expensive embedding generation
    - Batch size limits to prevent memory issues with large chunk sets

    Follows FastAPI DI patterns - no connections at construction time.

    Example:
        reranker = SemanticReranker(model_client=client)
        ranked = await reranker.rerank(chunks, "What did our team observe?")
    """

    # Default weights for combining scores — sourced from
    # config.scoring_weights so quality gate and reranker stay in sync.
    DEFAULT_KG_WEIGHT = KG_WEIGHT
    DEFAULT_SEMANTIC_WEIGHT = BRIDGE_WEIGHT
    
    # Optimization constants
    MAX_CHUNKS_FOR_CROSS_ENCODER = 12  # Keep low for CPU cross-encoder performance
    MAX_CHUNKS_FOR_BI_ENCODER = 50  # Bi-encoder is fast, can handle more
    QUERY_CACHE_SIZE = 50  # Max cached query embeddings
    QUERY_CACHE_TTL_SECONDS = 300  # 5 minutes

    def __init__(
        self,
        model_client: Optional[Any] = None,
        kg_weight: float = DEFAULT_KG_WEIGHT,
        semantic_weight: float = DEFAULT_SEMANTIC_WEIGHT,
    ):
        """
        Initialize SemanticReranker.

        Args:
            model_client: Model server client for embedding generation
                         (injected via DI). If None, falls back to KG scores only.
            kg_weight: Weight for KG-based scores (default 0.7)
            semantic_weight: Weight for semantic scores (default 0.3)

        Note:
            Weights should sum to 1.0 for normalized final scores.
            If they don't, scores will still be valid but not normalized.
        """
        self._model_client = model_client
        self._kg_weight = kg_weight
        self._semantic_weight = semantic_weight
        
        # Query embedding cache: hash -> (embedding, timestamp)
        self._query_cache: Dict[str, Tuple[np.ndarray, float]] = {}

        # Chunk content embedding cache: SHA-256(content) -> embedding
        # Ensures identical chunk text always produces the same embedding
        # across reranking calls, eliminating floating-point non-determinism.
        self._chunk_embedding_cache: Dict[str, List[float]] = {}
        self._max_chunk_cache_size = 512

        # Validate weights
        if self._kg_weight < 0 or self._semantic_weight < 0:
            logger.warning("Negative weights provided, using absolute values")
            self._kg_weight = abs(self._kg_weight)
            self._semantic_weight = abs(self._semantic_weight)

        weight_sum = self._kg_weight + self._semantic_weight
        if abs(weight_sum - 1.0) > 0.01:
            logger.warning(
                f"Weights sum to {weight_sum:.2f}, not 1.0. "
                "Final scores will not be normalized."
            )

        logger.debug(
            f"SemanticReranker initialized with weights: "
            f"kg={self._kg_weight}, semantic={self._semantic_weight}"
        )

    async def rerank(
        self,
        chunks: List[RetrievedChunk],
        query: str,
        top_k: int = 15,
        decomposition: Optional[Any] = None,
    ) -> List[RetrievedChunk]:
        """
        Re-rank chunks using semantic similarity.

        OPTIMIZED: Pre-filters chunks by KG score and caches query embeddings.

        This method:
        1. Pre-filters to top N chunks by KG score (reduces embedding calls)
        2. Gets query embedding from cache or generates new one
        3. Generates embeddings for filtered chunk contents
        4. Calculates cosine similarity between query and each chunk
        5. Combines KG scores with semantic scores using configured weights
        6. Applies query-term content boost using decomposition
        7. Sorts by final score and returns top_k results

        Args:
            chunks: Candidate chunks from Stage 1 (KG retrieval)
            query: Original query for embedding generation
            top_k: Maximum chunks to return (default 15)
            decomposition: Optional QueryDecomposition with extracted
                entities and actions from the query decomposer.

        Returns:
            Re-ranked list of chunks, sorted by final_score descending.
            Each chunk will have updated semantic_score and final_score.

        Validates: Requirement 3.2 - semantic re-ranking for relevance ordering
        """
        if not chunks:
            logger.debug("No chunks provided for reranking")
            return []

        if not query or not query.strip():
            logger.warning("Empty query provided, returning chunks sorted by KG score")
            return self._sort_by_kg_score(chunks, top_k)

        query = query.strip()
        logger.debug(f"Reranking {len(chunks)} chunks for query: {query[:50]}...")

        # If no model client, fall back to KG scores only
        if not self._model_client:
            logger.warning(
                "No model client available, falling back to KG scores only"
            )
            return self._sort_by_kg_score(chunks, top_k)

        try:
            # Get query embedding first — needed for semantic pre-filter
            query_embedding = await self._get_query_embedding_cached(query)
            if query_embedding is None:
                logger.warning(
                    "Failed to generate query embedding, falling back to KG scores"
                )
                return self._sort_by_kg_score(chunks, top_k)

            # Check if cross-encoder is enabled (disabled by default for CPU performance)
            import os
            use_cross_encoder = os.environ.get("USE_CROSS_ENCODER", "false").lower() == "true"
            
            # Use appropriate chunk limit based on reranking method
            max_chunks = self.MAX_CHUNKS_FOR_CROSS_ENCODER if use_cross_encoder else self.MAX_CHUNKS_FOR_BI_ENCODER

            # Pre-filter chunks by semantic similarity to query
            chunks_to_rerank = self._prefilter_chunks(chunks, query_embedding, max_chunks)
            logger.debug(f"Pre-filtered to {len(chunks_to_rerank)} chunks for reranking")
            
            # Attempt cross-encoder scoring; fall back to bi-encoder on failure
            cross_encoder_success = False
            if use_cross_encoder:
                try:
                    cross_encoder_scores = await self._model_client.rerank(
                        query, [c.content for c in chunks_to_rerank]
                    )
                    if len(cross_encoder_scores) != len(chunks_to_rerank):
                        logger.warning(
                            f"Cross-encoder score count mismatch: expected "
                            f"{len(chunks_to_rerank)}, got {len(cross_encoder_scores)}. "
                            "Falling back to bi-encoder."
                        )
                    else:
                        for chunk, score in zip(chunks_to_rerank, cross_encoder_scores):
                            chunk.semantic_score = score
                        cross_encoder_success = True
                        logger.info(
                            f"Cross-encoder scoring succeeded for {len(chunks_to_rerank)} chunks"
                        )
                except Exception as e:
                    logger.warning(f"Cross-encoder reranking failed, falling back to bi-encoder: {e}")

            if cross_encoder_success:
                # Rescale cross-encoder scores: BGE reranker v2 m3 outputs
                # sigmoid-normalized scores centered around 0.5 (neutral).
                # To make the geometric formula effective, we rescale so that:
                #   - 0.5 (neutral) → 0.1 (strong penalty in geometric mean)
                #   - 1.0 (highly relevant) → 1.0
                #   - 0.0 (irrelevant) → 0.0
                # Using a power transform: rescaled = (2 * max(0, score - 0.5))^2
                # This maps [0.5, 1.0] → [0, 1] with quadratic emphasis on high scores
                for chunk in chunks_to_rerank:
                    raw = chunk.semantic_score
                    if raw <= 0.5:
                        chunk.semantic_score = 0.05  # Floor for neutral/irrelevant
                    else:
                        # Map (0.5, 1.0] → (0.05, 1.0] with quadratic curve
                        normalized = (raw - 0.5) * 2  # [0, 1]
                        chunk.semantic_score = 0.05 + 0.95 * (normalized ** 1.5)
                    logger.debug(
                        f"Cross-encoder score rescaled: {raw:.4f} → {chunk.semantic_score:.4f}"
                    )
                chunks_with_scores = chunks_to_rerank
            else:
                # Bi-encoder fallback: generate chunk embeddings and calculate cosine similarities
                chunks_with_scores = await self._calculate_semantic_scores(
                    chunks_to_rerank, query_embedding
                )

            # Calculate final scores and sort
            for chunk in chunks_with_scores:
                chunk.final_score = self._calculate_final_score(
                    chunk.kg_relevance_score,
                    chunk.semantic_score,
                )
                print(
                    f"GEOM_DIAG kg={chunk.kg_relevance_score:.4f} "
                    f"sem={chunk.semantic_score:.4f} "
                    f"final={chunk.final_score:.4f} "
                    f"content={((chunk.content or '')[:80]).replace(chr(10),' ')}",
                    flush=True
                )

            # Query-term content boost using decomposition.
            # The query decomposer already extracts entities (proper nouns
            # like "Chelsea") and actions (verbs like "observe") via NLP.
            # Chunks containing more of these key terms rank higher.
            #   - Entity match: +0.03 per entity found in content
            #   - Action match: +0.01 per action found in content
            #   - Synergy bonus: +0.03 when BOTH entity AND action match
            #     (a chunk with both the subject and verb from the query
            #      is far more likely to be the answer)
            # This is case-insensitive and uses substring matching to
            # handle morphological variants (observe/observed/observing).
            boost_entities: set = set()
            boost_actions: set = set()
            if decomposition is not None:
                # Only use proper-noun entities for boosting.
                # The decomposer's entities list includes both named
                # entities ("Chelsea") and generic concept matches
                # ("we saw", "we examine"). Generic phrases match too
                # many chunks and dilute the boost signal. Filter to
                # entities whose first word is capitalized and isn't a
                # common pronoun/determiner.
                _skip = {"we", "our", "the", "a", "an", "after"}
                for e in getattr(decomposition, 'entities', []):
                    if len(e) <= 2:
                        continue
                    first_word = e.split()[0] if e.split() else e
                    if first_word[0].isupper() and first_word.lower() not in _skip:
                        boost_entities.add(e.lower())
                boost_actions = {
                    a.lower() for a in getattr(decomposition, 'actions', [])
                    if len(a) > 2
                }
            else:
                # Fallback: extract proper nouns from query text
                query_words = re.findall(r'[A-Za-z]+', query)
                boost_entities = {
                    w.lower() for w in query_words
                    if len(w) > 2 and w[0].isupper()
                }

            if boost_entities or boost_actions:
                ENTITY_BOOST = 0.03
                ACTION_BOOST = 0.01
                SYNERGY_BOOST = 0.03  # bonus when both entity+action match
                for chunk in chunks_with_scores:
                    content_lower = (chunk.content or "").lower()
                    entity_matched = False
                    action_matched = False
                    boost = 0.0
                    for ent in boost_entities:
                        if ent in content_lower:
                            boost += ENTITY_BOOST
                            entity_matched = True
                    for act in boost_actions:
                        # Substring match handles morphology:
                        # "observe" matches "observed", "observing"
                        if act in content_lower:
                            boost += ACTION_BOOST
                            action_matched = True
                    # Synergy: chunk contains both entity and action
                    if entity_matched and action_matched:
                        boost += SYNERGY_BOOST
                    if boost > 0:
                        chunk.final_score += boost

            # Sort by final score descending
            chunks_with_scores.sort(key=lambda c: c.final_score, reverse=True)

            # Return top_k results
            result = chunks_with_scores[:top_k]

            logger.info(
                f"Reranked {len(chunks)} chunks to {len(result)} results. "
                f"Top score: {result[0].final_score:.3f}" if result else ""
            )

            return result

        except Exception as e:
            logger.error(f"Error during semantic reranking: {e}")
            # Fall back to KG scores on error
            return self._sort_by_kg_score(chunks, top_k)

    def _prefilter_chunks(
        self, chunks: List[RetrievedChunk], query_embedding: np.ndarray, max_chunks: int
    ) -> List[RetrievedChunk]:
        """
        Pre-filter chunks by semantic similarity to the query embedding.

        Uses vectorized cosine similarity between the query embedding and
        stored chunk embeddings to select the most relevant candidates
        before full reranking.

        Args:
            chunks: All candidate chunks
            query_embedding: Shape (D,) query vector
            max_chunks: Maximum number of chunks to return

        Returns:
            Filtered list of chunks (max max_chunks)

        Requirements: 1.1, 1.2, 1.3, 5.1
        """
        if len(chunks) <= max_chunks:
            return chunks

        # Separate chunks into those with and without embeddings
        chunks_with_emb: List[Tuple[int, RetrievedChunk]] = []
        chunks_without_emb: List[RetrievedChunk] = []
        for i, chunk in enumerate(chunks):
            if chunk.has_embedding():
                chunks_with_emb.append((i, chunk))
            else:
                chunks_without_emb.append(chunk)

        if not chunks_with_emb:
            # No embeddings available — return first max_chunks
            return chunks[:max_chunks]

        # Build numpy matrix from chunk embeddings and compute similarities
        embedding_matrix = np.array(
            [chunk.embedding for _, chunk in chunks_with_emb], dtype=np.float64
        )
        similarities = self._batch_cosine_similarities(query_embedding, embedding_matrix)

        # Pair similarities with chunks and sort descending
        scored = sorted(
            zip(similarities, [chunk for _, chunk in chunks_with_emb]),
            key=lambda x: x[0],
            reverse=True,
        )

        # Always preserve chunks with high KG relevance scores
        # (direct concept matches) regardless of semantic similarity
        # But cap at half the limit to leave room for semantic diversity
        KG_PRESERVE_THRESHOLD = 0.7
        MAX_KG_PRESERVED = max_chunks // 2
        selected: List[RetrievedChunk] = []
        selected_ids: set = set()

        # First pass: preserve high-KG-score chunks (up to half the limit)
        high_kg_chunks = []
        for _sim, chunk in scored:
            if chunk.kg_relevance_score >= KG_PRESERVE_THRESHOLD:
                high_kg_chunks.append(chunk)
        for chunk in chunks_without_emb:
            if chunk.kg_relevance_score >= KG_PRESERVE_THRESHOLD:
                high_kg_chunks.append(chunk)
        
        # Sort by KG score and take top MAX_KG_PRESERVED
        high_kg_chunks.sort(key=lambda c: c.kg_relevance_score, reverse=True)
        for chunk in high_kg_chunks[:MAX_KG_PRESERVED]:
            selected.append(chunk)
            selected_ids.add(id(chunk))

        # Fill remaining slots by semantic similarity
        remaining = max_chunks - len(selected)

        for _sim, chunk in scored:
            if remaining <= 0:
                break
            if id(chunk) not in selected_ids:
                selected.append(chunk)
                remaining -= 1

        for chunk in chunks_without_emb:
            if remaining <= 0:
                break
            if id(chunk) not in selected_ids:
                selected.append(chunk)
                remaining -= 1

        return selected

    def _get_query_hash(self, query: str) -> str:
        """Generate a hash for the query string."""
        return hashlib.md5(query.lower().encode()).hexdigest()

    async def _get_query_embedding_cached(self, query: str) -> Optional[np.ndarray]:
        """
        Get query embedding from cache or generate new one.
        
        OPTIMIZATION: Caches query embeddings to avoid regenerating
        for repeated or similar queries.
        
        Args:
            query: Query text
            
        Returns:
            Query embedding or None if generation fails
        """
        query_hash = self._get_query_hash(query)
        current_time = time.time()
        
        # Check cache
        if query_hash in self._query_cache:
            embedding, timestamp = self._query_cache[query_hash]
            if current_time - timestamp < self.QUERY_CACHE_TTL_SECONDS:
                logger.debug(f"Query embedding cache hit for: {query[:30]}...")
                return embedding
            else:
                # Expired, remove from cache
                del self._query_cache[query_hash]
        
        # Generate new embedding
        embedding = await self._generate_query_embedding(query)
        
        if embedding is not None:
            # Add to cache (with LRU eviction if needed)
            if len(self._query_cache) >= self.QUERY_CACHE_SIZE:
                # Remove oldest entry
                oldest_hash = min(
                    self._query_cache.keys(),
                    key=lambda h: self._query_cache[h][1]
                )
                del self._query_cache[oldest_hash]
            
            self._query_cache[query_hash] = (embedding, current_time)
            logger.debug(f"Cached query embedding for: {query[:30]}...")
        
        return embedding

    async def _generate_query_embedding(
        self, query: str
    ) -> Optional[np.ndarray]:
        """
        Generate embedding for the query using model server.

        Args:
            query: Query text to embed

        Returns:
            Numpy array of embedding or None if generation fails
        """
        if not self._model_client:
            return None

        try:
            # Use model server to generate embedding
            embeddings = await self._model_client.generate_embeddings(
                [query], normalize=True
            )

            if embeddings and len(embeddings) > 0:
                return np.array(embeddings[0])

            logger.warning("Model server returned empty embeddings for query")
            return None

        except Exception as e:
            logger.warning(f"Error generating query embedding: {e}")
            return None

    async def _calculate_semantic_scores(
        self,
        chunks: List[RetrievedChunk],
        query_embedding: np.ndarray,
    ) -> List[RetrievedChunk]:
        """
        Calculate semantic similarity scores for all chunks.

        OPTIMIZED: Uses stored embeddings from Milvus when available,
        only generates embeddings for chunks that don't have them.

        Args:
            chunks: List of chunks to score
            query_embedding: Pre-computed query embedding

        Returns:
            Same chunks with semantic_score updated
        """
        if not chunks:
            return chunks

        # Separate chunks with and without embeddings
        chunks_with_embeddings = []
        chunks_without_embeddings = []
        
        for chunk in chunks:
            if chunk.has_embedding():
                chunks_with_embeddings.append(chunk)
            else:
                chunks_without_embeddings.append(chunk)

        logger.debug(
            f"Reranking: {len(chunks_with_embeddings)} with stored embeddings, "
            f"{len(chunks_without_embeddings)} need generation"
        )

        # Calculate scores for chunks with stored embeddings (fast path)
        for chunk in chunks_with_embeddings:
            chunk_emb = np.array(chunk.embedding)
            similarity = self._cosine_similarity(query_embedding, chunk_emb)
            # Normalize similarity from [-1, 1] to [0, 1]
            chunk.semantic_score = (similarity + 1.0) / 2.0

        # Generate embeddings only for chunks that don't have them
        if chunks_without_embeddings and self._model_client:
            # Check chunk embedding cache first
            chunks_needing_generation = []
            for chunk in chunks_without_embeddings:
                cache_key = hashlib.sha256(
                    (chunk.content or "").encode('utf-8')
                ).hexdigest()
                cached_emb = self._chunk_embedding_cache.get(cache_key)
                if cached_emb is not None:
                    chunk_emb = np.array(cached_emb)
                    similarity = self._cosine_similarity(
                        query_embedding, chunk_emb
                    )
                    chunk.semantic_score = (similarity + 1.0) / 2.0
                    chunk.embedding = cached_emb
                else:
                    chunks_needing_generation.append(chunk)

            if chunks_needing_generation:
                chunk_texts = [
                    chunk.content
                    for chunk in chunks_needing_generation
                ]

                try:
                    chunk_embeddings = (
                        await self._model_client.generate_embeddings(
                            chunk_texts, normalize=True
                        )
                    )

                    if chunk_embeddings and len(chunk_embeddings) == len(
                        chunks_needing_generation
                    ):
                        for chunk, embedding in zip(
                            chunks_needing_generation, chunk_embeddings
                        ):
                            chunk_emb = np.array(embedding)
                            similarity = self._cosine_similarity(
                                query_embedding, chunk_emb
                            )
                            chunk.semantic_score = (
                                (similarity + 1.0) / 2.0
                            )
                            chunk.embedding = embedding
                            # Cache the generated embedding
                            ck = hashlib.sha256(
                                (chunk.content or "").encode('utf-8')
                            ).hexdigest()
                            if len(self._chunk_embedding_cache) >= self._max_chunk_cache_size:
                                oldest = next(iter(self._chunk_embedding_cache))
                                del self._chunk_embedding_cache[oldest]
                            self._chunk_embedding_cache[ck] = embedding
                    else:
                        logger.warning(
                            f"Embedding count mismatch: expected "
                            f"{len(chunks_needing_generation)}, "
                            f"got {len(chunk_embeddings) if chunk_embeddings else 0}"
                        )
                        for chunk in chunks_needing_generation:
                            chunk.semantic_score = 0.5

                except Exception as e:
                    logger.warning(f"Error generating embeddings: {e}")
                    for chunk in chunks_needing_generation:
                        chunk.semantic_score = 0.5
        elif chunks_without_embeddings:
            # No model client, set default scores
            for chunk in chunks_without_embeddings:
                chunk.semantic_score = 0.5

        return chunks

    def _cosine_similarity(
        self, vec1: np.ndarray, vec2: np.ndarray
    ) -> float:
        """
        Calculate cosine similarity between two vectors.

        Args:
            vec1: First vector
            vec2: Second vector

        Returns:
            Cosine similarity in range [-1, 1]
        """
        # Handle edge cases
        if vec1 is None or vec2 is None:
            return 0.0

        norm1 = np.linalg.norm(vec1)
        norm2 = np.linalg.norm(vec2)

        if norm1 == 0 or norm2 == 0:
            return 0.0

        return float(np.dot(vec1, vec2) / (norm1 * norm2))

    def _batch_cosine_similarities(
        self, query_embedding: np.ndarray, chunk_embeddings: np.ndarray
    ) -> np.ndarray:
        """
        Compute cosine similarities between a query vector and multiple chunk vectors
        using vectorized numpy operations.

        Args:
            query_embedding: Shape (D,) query vector
            chunk_embeddings: Shape (N, D) matrix of chunk vectors

        Returns:
            Shape (N,) array of cosine similarities in [-1, 1].
            Zero-norm vectors yield 0.0.
        """
        query_norm = np.linalg.norm(query_embedding)
        if query_norm == 0:
            return np.zeros(chunk_embeddings.shape[0])

        chunk_norms = np.linalg.norm(chunk_embeddings, axis=1)
        dot_products = chunk_embeddings @ query_embedding

        # Avoid division by zero: where chunk norm is 0, result is 0.0
        safe_norms = np.where(chunk_norms == 0, 1.0, chunk_norms)
        similarities = dot_products / (safe_norms * query_norm)
        similarities = np.where(chunk_norms == 0, 0.0, similarities)

        return similarities


    def _calculate_final_score(
        self, kg_score: float, semantic_score: float
    ) -> float:
        """
        Calculate weighted final score using geometric mean.

        Uses a weighted geometric mean so that both KG relevance and
        semantic relevance must be present for a high score.  A near-zero
        semantic score (cross-encoder says content is irrelevant) tanks
        the result even if the KG score is high — preventing concept
        name collisions (e.g. "Chelsea" the company vs "chelsea()" the
        function) from dominating the ranking.

        Formula: kg^KG_WEIGHT × semantic^SEMANTIC_WEIGHT

        A small floor (1e-6) is applied to each input to avoid zero
        products when one signal is legitimately absent.

        Args:
            kg_score: Score from knowledge graph (0-1)
            semantic_score: Score from semantic similarity (0-1)

        Returns:
            Weighted geometric mean score

        Validates: Requirement 3.2 - weighted scoring for relevance
        """
        floor = 1e-6
        kg = max(kg_score, floor)
        sem = max(semantic_score, floor)
        return (kg ** self._kg_weight) * (sem ** self._semantic_weight)

    def _sort_by_kg_score(
        self, chunks: List[RetrievedChunk], top_k: int
    ) -> List[RetrievedChunk]:
        """
        Sort chunks by KG relevance score only (fallback).

        Used when semantic scoring is not available.

        Args:
            chunks: Chunks to sort
            top_k: Maximum chunks to return

        Returns:
            Sorted chunks with final_score set to kg_relevance_score
        """
        for chunk in chunks:
            chunk.final_score = chunk.kg_relevance_score

        sorted_chunks = sorted(
            chunks, key=lambda c: c.kg_relevance_score, reverse=True
        )

        return sorted_chunks[:top_k]

    def set_model_client(self, client: Any) -> None:
        """
        Set the model client after initialization.

        Useful for lazy initialization or testing.

        Args:
            client: Model server client instance
        """
        self._model_client = client
        logger.debug("Model client set on SemanticReranker")

    @property
    def has_model_client(self) -> bool:
        """Check if model client is available."""
        return self._model_client is not None

    @property
    def kg_weight(self) -> float:
        """Get the KG score weight."""
        return self._kg_weight

    @property
    def semantic_weight(self) -> float:
        """Get the semantic score weight."""
        return self._semantic_weight

    def get_weights(self) -> dict:
        """Get the current weight configuration."""
        return {
            "kg_weight": self._kg_weight,
            "semantic_weight": self._semantic_weight,
        }

    def clear_query_cache(self) -> int:
        """
        Clear the query embedding cache.
        
        Returns:
            Number of entries cleared
        """
        count = len(self._query_cache)
        self._query_cache.clear()
        logger.debug(f"Cleared {count} query embedding cache entries")
        return count

    def get_cache_stats(self) -> dict:
        """Get query embedding cache statistics."""
        return {
            "cache_size": len(self._query_cache),
            "max_cache_size": self.QUERY_CACHE_SIZE,
            "cache_ttl_seconds": self.QUERY_CACHE_TTL_SECONDS,
            "max_chunks_cross_encoder": self.MAX_CHUNKS_FOR_CROSS_ENCODER,
            "max_chunks_bi_encoder": self.MAX_CHUNKS_FOR_BI_ENCODER,
        }
