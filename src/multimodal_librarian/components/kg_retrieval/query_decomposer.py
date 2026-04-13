"""
Query Decomposer Component for Knowledge Graph-Guided Retrieval.

This component decomposes user queries into structured components by:
1. Extracting named entities by matching against Neo4j concept names
2. Identifying action words (observed, found, discovered, etc.)
3. Identifying subject references (our team, the system, etc.)

Requirements: 4.1, 4.2, 4.3, 4.4, 4.5
"""

import asyncio
import hashlib
import logging
from typing import Any, Dict, List, Optional, Set

from ...models.kg_retrieval import QueryDecomposition

logger = logging.getLogger(__name__)


# =============================================================================
# Constants
# =============================================================================

# Common action words to identify in queries
# These indicate what the user is asking about (observations, findings, etc.)
ACTION_WORDS: Set[str] = {
    'observed', 'found', 'discovered', 'noted', 'reported',
    'identified', 'analyzed', 'concluded', 'determined', 'saw',
    'mentioned', 'stated', 'described', 'explained', 'discussed',
    'showed', 'demonstrated', 'revealed', 'indicated', 'suggested',
    'confirmed', 'verified', 'documented', 'recorded', 'highlighted',
    'examined', 'investigated', 'explored', 'studied', 'reviewed',
    'assessed', 'evaluated', 'measured', 'tested', 'compared',
    'observe', 'find', 'discover', 'note', 'report',
    'identify', 'analyze', 'conclude', 'determine', 'see',
    'mention', 'state', 'describe', 'explain', 'discuss',
    'show', 'demonstrate', 'reveal', 'indicate', 'suggest',
}

# Common subject reference patterns
# These indicate who/what is performing the action
SUBJECT_PATTERNS: Set[str] = {
    'our team', 'the team', 'we', 'the system', 'the author',
    'the researchers', 'the study', 'the analysis', 'the report',
    'the paper', 'the document', 'the article', 'the book',
    'the chapter', 'the section', 'the findings', 'the results',
    'they', 'the experts', 'the scientists', 'the engineers',
    'the developers', 'the analysts', 'the investigators',
    'our analysis', 'our research', 'our findings', 'our study',
    'this research', 'this study', 'this analysis', 'this report',
}

# Stopwords to filter out when extracting content words
STOPWORDS: Set[str] = {
    'what', 'did', 'our', 'the', 'a', 'an', 'is', 'are', 'was', 'were',
    'at', 'in', 'on', 'to', 'for', 'of', 'with', 'by', 'from', 'about',
    'how', 'why', 'when', 'where', 'who', 'which', 'that', 'this', 'these',
    'those', 'it', 'its', 'they', 'them', 'their', 'we', 'us', 'you', 'your',
    'i', 'me', 'my', 'he', 'she', 'him', 'her', 'his', 'and', 'or', 'but',
    'if', 'then', 'else', 'so', 'as', 'be', 'been', 'being', 'have', 'has',
    'had', 'do', 'does', 'done', 'will', 'would', 'could', 'should', 'can',
    'may', 'might', 'must', 'shall', 'team', 'observe', 'observed',
}


class QueryDecomposer:
    """
    Decomposes user queries into structured components.
    
    Uses Neo4j to identify named entities and extracts action words
    and subject references using pattern matching.
    
    Follows FastAPI DI patterns - no connections at construction time.
    
    Example:
        decomposer = QueryDecomposer(neo4j_client=client)
        result = await decomposer.decompose("What did our team observe at Chelsea?")
        # result.entities = ["Chelsea AI Ventures"]
        # result.actions = ["observe"]
        # result.subjects = ["our team"]
    """
    
    def __init__(
        self,
        neo4j_client: Optional[Any] = None,
        model_server_client: Optional[Any] = None,
        similarity_threshold: float = 0.75,
        semantic_max_results: int = 20,
        semantic_enabled: bool = True,
    ):
        """
        Initialize QueryDecomposer with optional Neo4j and model server clients.
        
        Args:
            neo4j_client: Neo4j client for concept matching (injected via DI).
                         If None, entity extraction will be skipped.
            model_server_client: Model server client for embedding generation
                                (injected via DI). If None, semantic matching
                                is silently skipped.
            similarity_threshold: Minimum cosine similarity for semantic matches
                                 (default 0.7).
            semantic_max_results: Max concepts returned from vector search
                                (default 10).
            semantic_enabled: Toggle semantic matching on/off (default True).
        """
        self._neo4j_client = neo4j_client
        self._model_server_client = model_server_client
        self._similarity_threshold = similarity_threshold
        self._semantic_max_results = semantic_max_results
        self._semantic_enabled = semantic_enabled
        # Cache query embeddings so identical query text always produces
        # the same vector within a session, eliminating floating-point
        # non-determinism from repeated embedding calls.
        # Key: SHA-256 of query text, Value: embedding list
        self._embedding_cache: Dict[str, List[float]] = {}
        self._max_embedding_cache_size = 128
        logger.debug("QueryDecomposer initialized")
    
    async def decompose(self, query: str) -> QueryDecomposition:
        """
        Decompose query into entities, actions, and subjects.
        
        This method:
        1. Extracts action words from the query
        2. Extracts subject references from the query
        3. Finds entity matches in Neo4j knowledge graph
        
        Args:
            query: User query text
            
        Returns:
            QueryDecomposition with extracted components.
            If no concepts are recognized, has_kg_matches will be False,
            signaling that fallback mode should be used.
        """
        if not query or not query.strip():
            logger.warning("Empty query provided to decompose")
            return QueryDecomposition(
                original_query=query or "",
                has_kg_matches=False
            )
        
        query = query.strip()
        logger.debug(f"Decomposing query: {query[:100]}...")
        
        # Extract actions and subjects (these don't require Neo4j)
        actions = self._extract_actions(query)
        subjects = self._extract_subjects(query)
        
        # Find entity matches in Neo4j (lexical + semantic)
        entities: List[str] = []
        concept_matches: List[Dict[str, Any]] = []
        
        # Run lexical and semantic matching concurrently.
        # We still fire both in parallel for speed, but semantic results
        # are the primary signal.  Lexical (Lucene) is only used as a
        # fallback when semantic matching was UNAVAILABLE (no model server
        # or no embeddings).  When semantic ran successfully but returned
        # nothing, that means no concepts are relevant — don't fall back
        # to Lucene which would reintroduce false positives.
        lexical_matches: List[Dict[str, Any]] = []
        semantic_matches: List[Dict[str, Any]] = []
        semantic_was_available = (
            self._model_server_client is not None
            and self._semantic_enabled
            and self._neo4j_client is not None
        )
        
        if self._neo4j_client:
            try:
                lexical_coro = self._find_entity_matches(query)
                semantic_coro = self._find_semantic_matches(query)
                lexical_matches, semantic_matches = await asyncio.gather(
                    lexical_coro, semantic_coro
                )
            except Exception as e:
                logger.warning(f"Error finding matches: {e}")
        else:
            logger.debug("No Neo4j client available, skipping entity extraction")
        
        # Semantic-first strategy:
        # Semantic matching embeds the FULL query ("president of Venezuela")
        # and does cosine similarity against concept embeddings, so it
        # captures compositional meaning.  Lucene tokenizes into individual
        # words ("president OR venezuela") and matches any concept containing
        # either word, which produces false positives for unrelated content.
        #
        # - If semantic returned results: use them (best quality).
        # - If semantic was available but returned nothing: trust it —
        #   no concepts are relevant.  Do NOT fall back to Lucene.
        # - If semantic was unavailable (no model server): fall back to
        #   Lucene as a best-effort.
        if semantic_matches:
            concept_matches = semantic_matches
            # --- determinism diagnostic: log every concept + score ---
            _diag = [
                f"{m.get('name','?')[:40]}|sim={m.get('similarity_score',0):.4f}"
                for m in semantic_matches
            ]
            logger.info(
                f"DETERMINISM_DIAG semantic_matches ({len(semantic_matches)}): {_diag}"
            )
            logger.info(
                f"Using {len(semantic_matches)} semantic concept matches "
                f"(lexical fallback not needed)"
            )
        elif not semantic_was_available and lexical_matches:
            # Semantic matching was unavailable — use lexical as fallback
            for match in lexical_matches:
                match['match_type'] = 'lexical'
            concept_matches = lexical_matches
            logger.info(
                f"Semantic matching unavailable, using "
                f"{len(lexical_matches)} lexical matches as fallback"
            )
        else:
            concept_matches = []
            if semantic_was_available:
                logger.info(
                    "Semantic matching found no relevant concepts "
                    "(lexical fallback suppressed)"
                )
            else:
                logger.info("No concept matches found")
        
        entities = [
            m.get('name', '') for m in concept_matches if m.get('name')
        ]
        
        has_kg_matches = len(concept_matches) > 0
        
        result = QueryDecomposition(
            original_query=query,
            entities=entities,
            actions=actions,
            subjects=subjects,
            concept_matches=concept_matches,
            has_kg_matches=has_kg_matches
        )
        
        logger.info(
            f"Query decomposition complete: "
            f"{len(entities)} entities, {len(actions)} actions, {len(subjects)} subjects, "
            f"has_kg_matches={has_kg_matches}"
        )
        
        return result

    async def _find_entity_matches(self, query: str) -> List[Dict[str, Any]]:
        """
        Find concept matches in Neo4j for query words.
        
        OPTIMIZED: Uses full-text index and batched query for maximum performance.
        
        Uses a multi-phase approach:
        1. Tokenize query into words
        2. Filter out stopwords and short words
        3. Prioritize proper nouns (capitalized words)
        4. Query Neo4j using full-text index for ALL matching concepts in ONE query
        5. Deduplicate and sort by relevance
        
        Args:
            query: User query text
            
        Returns:
            List of concept dictionaries from Neo4j with fields:
            - concept_id: Unique identifier
            - name: Concept name
            - type: Concept type (ENTITY, TOPIC, etc.)
            - confidence: Extraction confidence
            - source_document: Document ID
            - source_chunks: Comma-separated chunk IDs
        """
        if not self._neo4j_client:
            return []
        
        # Validate that _neo4j_client is actually a client, not a coroutine
        if asyncio.iscoroutine(self._neo4j_client):
            logger.error("Neo4j client is a coroutine, not an actual client! Resetting...")
            self._neo4j_client = None
            return []
        
        # Ensure Neo4j connection is active before querying
        try:
            if hasattr(self._neo4j_client, '_is_connected') and not self._neo4j_client._is_connected:
                logger.info("Neo4j client connection is stale in QueryDecomposer, reconnecting...")
                if hasattr(self._neo4j_client, 'connect'):
                    await self._neo4j_client.connect()
                    logger.info("Neo4j client reconnected successfully in QueryDecomposer")
        except Exception as e:
            logger.warning(f"Failed to reconnect Neo4j client in QueryDecomposer: {e}")
            return []
        
        # Tokenize query
        original_words = query.split()
        words = [w.strip('?.,!"\';:()[]{}') for w in original_words]
        
        # Build list of (lowercase_word, original_word) pairs
        word_pairs = [
            (w.lower(), orig) 
            for w, orig in zip(words, original_words) 
            if w and len(w) > 2
        ]
        
        # Filter out stopwords and action words (we want entities, not verbs)
        content_words = [
            (w, orig) for w, orig in word_pairs
            if w not in STOPWORDS and w not in ACTION_WORDS
        ]
        
        if not content_words:
            logger.debug("No content words found in query after filtering")
            return []
        
        # Identify proper nouns for prioritization
        proper_nouns = {w for w, orig in content_words if orig and orig[0].isupper()}
        all_words = [w for w, _ in content_words]
        
        # OPTIMIZATION: Try full-text index first (fastest), fall back to CONTAINS
        try:
            # Build full-text search query string (OR between words)
            search_terms = " OR ".join(all_words)
            
            # Use full-text index for faster search
            cypher_query = """
            CALL db.index.fulltext.queryNodes('concept_name_fulltext', $search_terms)
            YIELD node as c, score
            WITH c, score
            WHERE size(c.name) < 150
            RETURN DISTINCT
                c.concept_id as concept_id, 
                c.name as name, 
                c.type as type,
                c.confidence as confidence,
                c.source_document as source_document,
                c.source_chunks as source_chunks,
                score as match_score
            ORDER BY score DESC
            LIMIT 30
            """
            
            results = await self._neo4j_client.execute_query(
                cypher_query,
                {"search_terms": search_terms}
            )
            
            if results:
                return self._process_concept_results(results, proper_nouns, all_words)
            
        except Exception as e:
            logger.debug(f"Full-text search failed, falling back to CONTAINS: {e}")
        
        # Fallback: Use CONTAINS with batched UNWIND query
        try:
            cypher_query = """
            UNWIND $words as word
            MATCH (c:Concept)
            WHERE c.name_lower CONTAINS word
            WITH c, word, size(c.name) as name_length
            WHERE name_length < 150
            RETURN DISTINCT
                c.concept_id as concept_id, 
                c.name as name, 
                c.type as type,
                c.confidence as confidence,
                c.source_document as source_document,
                c.source_chunks as source_chunks,
                word as matched_word,
                name_length
            ORDER BY name_length ASC
            LIMIT 30
            """
            
            results = await self._neo4j_client.execute_query(
                cypher_query,
                {"words": all_words}
            )
            
            return self._process_concept_results(results, proper_nouns, all_words)
                        
        except Exception as e:
            logger.warning(f"Error in Neo4j query: {e}", exc_info=True)
            return []

    async def _find_semantic_matches(self, query: str) -> List[Dict[str, Any]]:
        """
        Find concepts via vector similarity search.
        
        Embeds the query using the model server client and performs
        approximate nearest-neighbor search against the Neo4j vector index.
        
        Args:
            query: User query text
            
        Returns:
            List of concept match dicts annotated with match_type="semantic".
            Returns empty list if model server is unavailable or semantic
            matching is disabled.
        """
        if not self._model_server_client or not self._semantic_enabled:
            return []

        if not self._neo4j_client:
            return []

        try:
            # Use cached embedding if available to ensure deterministic
            # results for identical queries within the same session.
            cache_key = hashlib.sha256(query.encode('utf-8')).hexdigest()
            query_embedding = self._embedding_cache.get(cache_key)

            if query_embedding is None:
                embeddings = await self._model_server_client.generate_embeddings([query])
                if not embeddings:
                    return []
                query_embedding = embeddings[0]
                # Evict oldest entries if cache is full
                if len(self._embedding_cache) >= self._max_embedding_cache_size:
                    oldest_key = next(iter(self._embedding_cache))
                    del self._embedding_cache[oldest_key]
                self._embedding_cache[cache_key] = query_embedding

            cypher = """
            CALL db.index.vector.queryNodes(
                'concept_embedding_index', $top_k, $embedding
            )
            YIELD node, score
            WHERE score >= $threshold
            RETURN node.concept_id AS concept_id,
                   node.name AS name,
                   node.type AS type,
                   node.confidence AS confidence,
                   node.source_document AS source_document,
                   node.source_chunks AS source_chunks,
                   score AS similarity_score
            """
            results = await self._neo4j_client.execute_query(cypher, {
                'embedding': query_embedding,
                'top_k': self._semantic_max_results,
                'threshold': self._similarity_threshold,
            })

            return [
                {**record, 'match_type': 'semantic'}
                for record in (results or [])
            ]
        except Exception as e:
            logger.warning(f"Semantic matching failed, falling back to lexical only: {e}")
            return []

    def _process_concept_results(
        self, 
        results: List[Dict[str, Any]], 
        proper_nouns: Set[str],
        all_words: List[str]
    ) -> List[Dict[str, Any]]:
        """Process and deduplicate concept results from Neo4j.

        Applies a word-coverage penalty so that partial matches are
        down-weighted.  For example, if the query content words are
        ["president", "venezuela"] but a concept name only contains
        "president", its coverage is 1/2 = 0.5 and the Lucene score
        is multiplied by 0.5.  This prevents generic single-word
        matches from dominating when the user's intent is a more
        specific multi-word concept.

        Sorting strategy (after coverage adjustment):
        1. Adjusted match score (higher = better).
        2. Proper noun matches get a small boost.
        3. Name length is used only as a tiebreaker (shorter = more specific).
        """
        found_concepts: List[Dict[str, Any]] = []
        seen_ids: Set[str] = set()

        num_query_words = max(len(all_words), 1)

        for r in results or []:
            concept_id = r.get('concept_id')
            if concept_id and concept_id not in seen_ids:
                seen_ids.add(concept_id)
                name = r.get('name', '').lower()
                matched_word = r.get('matched_word', '')

                # Check if any proper noun matches this concept
                is_proper_noun = any(
                    pn in name for pn in proper_nouns
                ) or matched_word in proper_nouns

                # Preserve the full-text match score
                raw_match_score = r.get('match_score', 0) or 0

                # Word-coverage penalty: how many of the query's content
                # words appear in this concept's name?  A concept that
                # only matches 1 out of 2 query words gets its score
                # halved, discouraging weak partial matches.
                words_covered = sum(1 for w in all_words if w in name)
                coverage_ratio = words_covered / num_query_words
                match_score = raw_match_score * coverage_ratio

                found_concepts.append({
                    'concept_id': concept_id,
                    'name': r.get('name', ''),
                    'type': r.get('type', 'ENTITY'),
                    'confidence': r.get('confidence', 0.5),
                    'source_document': r.get('source_document'),
                    'source_chunks': r.get('source_chunks', ''),
                    'matched_word': matched_word,
                    'is_proper_noun_match': is_proper_noun,
                    'match_score': match_score,
                    'raw_match_score': raw_match_score,
                    'word_coverage': coverage_ratio,
                })

        # Sort by: adjusted score descending (primary), proper noun boost,
        # then name length ascending as tiebreaker
        found_concepts.sort(
            key=lambda c: (
                -(c.get('match_score', 0) or 0),          # Higher score first
                not c.get('is_proper_noun_match', False),  # Proper nouns first (tiebreaker)
                len(c.get('name', ''))                     # Shorter names first (tiebreaker)
            )
        )

        # Limit to top 10 concepts
        result = found_concepts[:10]

        logger.debug(
            f"Found {len(result)} concept matches (optimized): "
            f"{[c.get('name', '')[:30] + ' cov=' + str(round(c.get('word_coverage', 0) * 100)) + '%' for c in result[:3]]}"
        )

        return result
    
    def _extract_actions(self, query: str) -> List[str]:
        """
        Extract action words from query.
        
        Identifies verbs that indicate what the user is asking about,
        such as "observed", "found", "discovered", etc.
        
        Args:
            query: User query text
            
        Returns:
            List of action words found in the query (lowercase)
        """
        # Tokenize and lowercase
        words = query.lower().split()
        words = [w.strip('?.,!"\';:()[]{}') for w in words]
        
        # Find matches with ACTION_WORDS
        actions = [w for w in words if w in ACTION_WORDS]
        
        # Deduplicate while preserving order
        seen: Set[str] = set()
        unique_actions: List[str] = []
        for action in actions:
            if action not in seen:
                seen.add(action)
                unique_actions.append(action)
        
        logger.debug(f"Extracted actions: {unique_actions}")
        return unique_actions
    
    def _extract_subjects(self, query: str) -> List[str]:
        """
        Extract subject references from query.
        
        Identifies phrases that indicate who/what is performing the action,
        such as "our team", "the researchers", etc.
        
        Args:
            query: User query text
            
        Returns:
            List of subject references found in the query (lowercase)
        """
        query_lower = query.lower()
        
        # Find matches with SUBJECT_PATTERNS
        subjects: List[str] = []
        for pattern in SUBJECT_PATTERNS:
            if pattern in query_lower:
                subjects.append(pattern)
        
        # Sort by length (longer patterns are more specific)
        subjects.sort(key=len, reverse=True)
        
        # Remove overlapping patterns (keep longer ones)
        # e.g., if "our team" and "team" both match, keep only "our team"
        filtered_subjects: List[str] = []
        for subject in subjects:
            is_substring = any(
                subject != other and subject in other 
                for other in filtered_subjects
            )
            if not is_substring:
                filtered_subjects.append(subject)
        
        logger.debug(f"Extracted subjects: {filtered_subjects}")
        return filtered_subjects
    
    def set_neo4j_client(self, client: Any) -> None:
        """
        Set the Neo4j client after initialization.
        
        Useful for lazy initialization or testing.
        
        Args:
            client: Neo4j client instance
        """
        # Validate that client is not a coroutine
        if asyncio.iscoroutine(client):
            logger.error("Attempted to set Neo4j client to a coroutine! Ignoring.")
            return
        
        self._neo4j_client = client
        logger.debug("Neo4j client set on QueryDecomposer")

    def set_model_server_client(self, client: Any) -> None:
        """
        Set the model server client after initialization.
        
        Useful for lazy initialization or testing.
        
        Args:
            client: Model server client instance
        """
        if asyncio.iscoroutine(client):
            logger.error("Attempted to set model server client to a coroutine! Ignoring.")
            return
        
        self._model_server_client = client
        logger.debug("Model server client set on QueryDecomposer")
    
    @property
    def has_neo4j_client(self) -> bool:
        """Check if Neo4j client is available."""
        return self._neo4j_client is not None

    @property
    def has_model_server_client(self) -> bool:
        """Check if model server client is available."""
        return self._model_server_client is not None
