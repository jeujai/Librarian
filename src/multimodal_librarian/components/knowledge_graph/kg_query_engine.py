"""
Knowledge Graph Query Engine Component.

This component provides multi-hop reasoning, concept disambiguation,
and enhanced query processing using the knowledge graph.

Now queries Neo4j directly instead of using in-memory dictionaries.
Uses model server for embeddings (separate container).
"""

import asyncio
import logging
from typing import Any, Dict, List

import numpy as np

from ...clients.model_server_client import (
    ModelServerUnavailable,
    get_model_client,
    initialize_model_client,
)
from ...models.core import KnowledgeChunk
from ...models.knowledge_graph import (
    ConceptNode,
    KnowledgeGraphQueryResult,
    ReasoningPath,
    RelatedConcept,
    RelationshipEdge,
)

logger = logging.getLogger(__name__)


class KnowledgeGraphQueryEngine:
    """
    Query engine for knowledge graph operations.
    
    Now queries Neo4j directly for scalable concept lookups instead of
    relying on in-memory dictionaries that don't persist across restarts.
    """
    
    # UMLS scoring multipliers
    UMLS_BOOST = 1.2   # Boost for UMLS-grounded concepts matching query domain
    UMLS_PENALTY = 0.7  # Penalty for semantic type contradictions

    def __init__(self, kg_builder=None, umls_client=None):
        """
        Initialize the query engine.
        
        Args:
            kg_builder: Legacy parameter, kept for backward compatibility.
                       The engine now queries Neo4j directly.
            umls_client: Optional UMLSClient for semantic type scoring.
        """
        self.kg_builder = kg_builder  # Keep for backward compatibility
        self._umls_client = umls_client
        self._model_server_client = None
        self._neo4j_client = None
        self._neo4j_initialized = False
        logger.info("Knowledge Graph Query Engine initialized (queries Neo4j directly)")
    
    async def _get_neo4j_client(self):
        """Get or initialize the Neo4j client, reconnecting if connection is stale."""
        # Check if we have a client but it's disconnected
        if self._neo4j_client is not None:
            if not getattr(self._neo4j_client, '_is_connected', False):
                logger.info("Neo4j client connection is stale, reconnecting...")
                try:
                    await self._neo4j_client.connect()
                    logger.info("Neo4j client reconnected successfully")
                except Exception as e:
                    logger.warning(f"Failed to reconnect Neo4j client: {e}")
                    # Reset client to try fresh initialization
                    self._neo4j_client = None
                    self._neo4j_initialized = False
        
        # Initialize client if we don't have one
        if self._neo4j_client is None and not self._neo4j_initialized:
            try:
                from ...clients.database_factory import get_database_factory
                factory = get_database_factory()
                # get_graph_client is synchronous
                client = factory.get_graph_client()
                
                # Connect if not already connected
                if hasattr(client, 'connect') and not getattr(client, '_is_connected', False):
                    await client.connect()
                
                self._neo4j_client = client
                self._neo4j_initialized = True
                logger.info("Neo4j client initialized for KG query engine")
            except Exception as e:
                logger.warning(f"Failed to initialize Neo4j client: {e}")
                self._neo4j_initialized = True  # Don't retry on every call
        return self._neo4j_client
    
    async def _get_model_server_client(self):
        """Get or initialize the model server client."""
        if self._model_server_client is None:
            try:
                client = get_model_client()
                if client is None:
                    await initialize_model_client()
                    client = get_model_client()
                
                if client and client.enabled:
                    self._model_server_client = client
            except Exception as e:
                logger.warning(f"Model server not available: {e}")
        return self._model_server_client
    
    async def generate_embeddings_async(self, texts: List[str]) -> np.ndarray:
        """
        Generate embeddings asynchronously using model server (non-blocking).
        
        Raises:
            ModelServerUnavailable: If model server is not available
        """
        client = await self._get_model_server_client()
        if client is None:
            raise ModelServerUnavailable("Model server not available")
        
        embeddings = await client.generate_embeddings(texts)
        if embeddings:
            return np.array(embeddings)
        
        raise ModelServerUnavailable("Failed to generate embeddings from model server")
    
    # =========================================================================
    # Neo4j Query Methods
    # =========================================================================
    
    async def _find_concepts_by_name(self, name: str, limit: int = 10) -> List[Dict[str, Any]]:
        """
        Find concepts in Neo4j by name (case-insensitive partial match).
        
        Args:
            name: Concept name to search for
            limit: Maximum number of results
            
        Returns:
            List of concept dictionaries from Neo4j
        """
        client = await self._get_neo4j_client()
        if not client:
            return []
        
        try:
            query = """
            MATCH (c:Concept)
            WHERE toLower(c.name) CONTAINS toLower($name)
            RETURN c.concept_id as concept_id, 
                   c.name as name, 
                   c.type as type,
                   c.confidence as confidence,
                   c.source_document as source_document,
                   c.source_chunks as source_chunks
            LIMIT $limit
            """
            results = await client.execute_query(query, {"name": name, "limit": limit})
            return results
        except Exception as e:
            logger.error(f"Error finding concepts by name '{name}': {e}")
            return []
    
    async def _find_related_concepts_neo4j(
        self, 
        concept_name: str, 
        relationship_types: List[str],
        max_hops: int = 2,
        limit: int = 20
    ) -> List[Dict[str, Any]]:
        """
        Find related concepts in Neo4j by traversing relationships.
        
        Args:
            concept_name: Starting concept name
            relationship_types: Types of relationships to traverse
            max_hops: Maximum path length
            limit: Maximum number of results
            
        Returns:
            List of related concept dictionaries with path info
        """
        client = await self._get_neo4j_client()
        if not client:
            return []
        
        try:
            # Build relationship type filter
            rel_filter = "|".join(relationship_types) if relationship_types else "RELATED_TO"
            
            query = f"""
            MATCH (start:Concept)
            WHERE toLower(start.name) CONTAINS toLower($concept_name)
            WITH start LIMIT 1
            MATCH path = (start)-[r:{rel_filter}*1..{max_hops}]-(related:Concept)
            WHERE related <> start
            RETURN DISTINCT 
                related.concept_id as concept_id,
                related.name as name,
                related.type as type,
                related.confidence as confidence,
                related.source_document as source_document,
                related.source_chunks as source_chunks,
                length(path) as distance,
                [rel in relationships(path) | type(rel)] as relationship_types
            ORDER BY distance ASC, related.confidence DESC
            LIMIT $limit
            """
            results = await client.execute_query(
                query, 
                {"concept_name": concept_name, "limit": limit}
            )
            return results
        except Exception as e:
            logger.error(f"Error finding related concepts for '{concept_name}': {e}")
            return []
    
    async def _find_paths_between_concepts(
        self,
        start_name: str,
        end_name: str,
        max_hops: int = 3,
        limit: int = 5
    ) -> List[Dict[str, Any]]:
        """
        Find paths between two concepts in Neo4j.
        
        Args:
            start_name: Starting concept name
            end_name: Target concept name
            max_hops: Maximum path length
            limit: Maximum number of paths
            
        Returns:
            List of path dictionaries
        """
        client = await self._get_neo4j_client()
        if not client:
            return []
        
        try:
            query = f"""
            MATCH (start:Concept), (end:Concept)
            WHERE toLower(start.name) CONTAINS toLower($start_name)
              AND toLower(end.name) CONTAINS toLower($end_name)
              AND start <> end
            WITH start, end LIMIT 1
            MATCH path = shortestPath((start)-[*1..{max_hops}]-(end))
            RETURN 
                start.name as start_concept,
                end.name as end_concept,
                [node in nodes(path) | node.name] as path_nodes,
                [rel in relationships(path) | type(rel)] as path_relationships,
                length(path) as path_length
            LIMIT $limit
            """
            results = await client.execute_query(
                query,
                {"start_name": start_name, "end_name": end_name, "limit": limit}
            )
            return results if results else []
        except Exception as e:
            logger.error(f"Error finding paths between '{start_name}' and '{end_name}': {e}")
            return []
    
    
    # =========================================================================
    # Public API Methods (now async and using Neo4j)
    # =========================================================================
    
    async def multi_hop_reasoning_async(
        self, 
        start_concepts: List[str], 
        target_concepts: List[str], 
        max_hops: int = 3
    ) -> List[ReasoningPath]:
        """
        Find reasoning paths between concepts using Neo4j graph traversal.
        
        Args:
            start_concepts: List of starting concept names
            target_concepts: List of target concept names
            max_hops: Maximum path length
            
        Returns:
            List of ReasoningPath objects
        """
        try:
            reasoning_paths = []
            
            for start_concept in start_concepts[:3]:  # Limit to avoid too many queries
                for target_concept in target_concepts[:3]:
                    paths = await self._find_paths_between_concepts(
                        start_concept, target_concept, max_hops
                    )
                    
                    for path_data in paths:
                        # Convert Neo4j path to ReasoningPath
                        path_steps = []
                        path_nodes = path_data.get('path_nodes', [])
                        path_rels = path_data.get('path_relationships', [])
                        
                        for i in range(len(path_rels)):
                            if i < len(path_nodes) - 1:
                                edge = RelationshipEdge(
                                    subject_concept=path_nodes[i],
                                    predicate=path_rels[i],
                                    object_concept=path_nodes[i + 1],
                                    confidence=0.7  # Default confidence
                                )
                                path_steps.append(edge)
                        
                        if path_steps:
                            reasoning_path = ReasoningPath(
                                start_concept=path_data.get('start_concept', start_concept),
                                end_concept=path_data.get('end_concept', target_concept),
                                path_steps=path_steps,
                                reasoning_type="CAUSAL_CHAIN"
                            )
                            reasoning_path.calculate_confidence()
                            reasoning_path.get_path_length()
                            reasoning_paths.append(reasoning_path)
            
            # Sort by confidence
            reasoning_paths.sort(key=lambda p: p.total_confidence, reverse=True)
            
            logger.info(f"Found {len(reasoning_paths)} reasoning paths via Neo4j")
            return reasoning_paths[:10]
            
        except Exception as e:
            logger.error(f"Error in multi-hop reasoning: {e}")
            return []
    
    def multi_hop_reasoning(
        self, 
        start_concepts: List[str], 
        target_concepts: List[str], 
        max_hops: int = 3
    ) -> List[ReasoningPath]:
        """
        Synchronous wrapper for multi_hop_reasoning_async.
        
        For backward compatibility with existing code.
        """
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                # We're in an async context, create a task
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor() as executor:
                    future = executor.submit(
                        asyncio.run,
                        self.multi_hop_reasoning_async(start_concepts, target_concepts, max_hops)
                    )
                    return future.result(timeout=10)
            else:
                return loop.run_until_complete(
                    self.multi_hop_reasoning_async(start_concepts, target_concepts, max_hops)
                )
        except Exception as e:
            logger.error(f"Error in sync multi_hop_reasoning: {e}")
            return []
    
    async def get_related_concepts_async(
        self, 
        concept: str, 
        relationship_types: List[str], 
        max_distance: int = 2
    ) -> List[RelatedConcept]:
        """
        Find concepts related through specific relationship types using Neo4j.
        
        Args:
            concept: Concept name or ID to start from
            relationship_types: Types of relationships to traverse
            max_distance: Maximum path length
            
        Returns:
            List of RelatedConcept objects
        """
        try:
            results = await self._find_related_concepts_neo4j(
                concept, relationship_types, max_distance
            )
            
            related_concepts = []
            for r in results:
                concept_node = ConceptNode(
                    concept_id=r.get('concept_id', ''),
                    concept_name=r.get('name', ''),
                    concept_type=r.get('type', 'ENTITY'),
                    confidence=r.get('confidence', 0.5),
                    source_chunks=r.get('source_chunks', []) or [],
                    source_document=r.get('source_document')
                )
                
                # Create relationship path from the traversal
                rel_types = r.get('relationship_types', [])
                path = []
                for rel_type in rel_types:
                    edge = RelationshipEdge(
                        subject_concept=concept,
                        predicate=rel_type,
                        object_concept=concept_node.concept_name,
                        confidence=0.7
                    )
                    path.append(edge)
                
                distance = r.get('distance', 1)
                relevance = 1.0 / (1.0 + distance * 0.3)  # Decay with distance
                
                related_concept = RelatedConcept(
                    concept=concept_node,
                    relationship_path=path,
                    relevance_score=relevance * concept_node.confidence,
                    distance=distance
                )
                related_concepts.append(related_concept)
            
            # Sort by relevance
            related_concepts.sort(key=lambda rc: rc.relevance_score, reverse=True)
            
            logger.info(f"Found {len(related_concepts)} related concepts for '{concept}' via Neo4j")
            return related_concepts
            
        except Exception as e:
            logger.error(f"Error finding related concepts: {e}")
            return []
    
    def get_related_concepts(
        self, 
        concept: str, 
        relationship_types: List[str], 
        max_distance: int = 2
    ) -> List[RelatedConcept]:
        """
        Synchronous wrapper for get_related_concepts_async.
        
        For backward compatibility with existing code.
        """
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor() as executor:
                    future = executor.submit(
                        asyncio.run,
                        self.get_related_concepts_async(concept, relationship_types, max_distance)
                    )
                    return future.result(timeout=10)
            else:
                return loop.run_until_complete(
                    self.get_related_concepts_async(concept, relationship_types, max_distance)
                )
        except Exception as e:
            logger.error(f"Error in sync get_related_concepts: {e}")
            return []
    
    

    
    # =========================================================================
    # Helper Methods
    # =========================================================================
    
    def enhance_vector_search(
        self, 
        query: str, 
        vector_results: List[KnowledgeChunk],
        concept_names: List[str] = None
    ) -> List[KnowledgeChunk]:
        """
        Re-rank vector search results using pre-extracted KG concepts.

        Args:
            query: The original query string.
            vector_results: Vector search results to re-rank.
            concept_names: Pre-extracted concept names from QueryDecomposer.
                          When empty or None, returns original results unmodified.

        Returns:
            Re-ranked list of KnowledgeChunk results.
        """
        try:
            if not vector_results or not concept_names:
                return vector_results

            # Find related concepts for re-ranking
            related_concepts = []
            for name in concept_names[:3]:
                try:
                    loop = asyncio.get_event_loop()
                    if loop.is_running():
                        logger.debug("Event loop running, skipping KG enhancement")
                        return vector_results
                    related = loop.run_until_complete(
                        self.get_related_concepts_async(
                            name, 
                            ["RELATED_TO", "IS_A", "PART_OF"], 
                            max_distance=2
                        )
                    )
                    related_concepts.extend(related)
                except Exception:
                    continue

            if not related_concepts:
                return vector_results

            # Re-rank results based on concept relevance
            enhanced_results = self._rerank_by_concept_relevance(vector_results, related_concepts)

            logger.info(f"Enhanced {len(vector_results)} results using KG")
            return enhanced_results

        except Exception as e:
            logger.error(f"Error enhancing vector search: {e}")
            return vector_results
    
    def retrieve_with_reasoning(
        self, 
        query_concepts: List[str], 
        reasoning_paths: List[ReasoningPath]
    ) -> List[KnowledgeChunk]:
        """
        Retrieve knowledge following reasoning paths from knowledge graph.
        
        Note: This creates placeholder chunks. In practice, you'd retrieve
        actual chunks from the vector store using the chunk IDs.
        """
        try:
            retrieved_chunks = []
            chunk_ids = set()
            
            # Collect chunk IDs from reasoning paths
            for path in reasoning_paths:
                for step in path.path_steps:
                    chunk_ids.update(step.evidence_chunks)
            
            # Create placeholder chunks (would retrieve from vector store in practice)
            for chunk_id in chunk_ids:
                chunk = KnowledgeChunk(
                    id=chunk_id,
                    content=f"Content for chunk {chunk_id}",
                    embedding=np.zeros(384),
                    source_type="BOOK",
                    source_id="unknown",
                    location_reference="unknown",
                    section="unknown"
                )
                retrieved_chunks.append(chunk)
            
            logger.info(f"Retrieved {len(retrieved_chunks)} chunks using reasoning paths")
            return retrieved_chunks
            
        except Exception as e:
            logger.error(f"Error retrieving with reasoning: {e}")
            return []
    
    def explain_reasoning(self, result: KnowledgeGraphQueryResult) -> str:
        """Provide explanation of how knowledge graph contributed to response."""
        try:
            explanation_parts = []
            
            if result.reasoning_paths:
                explanation_parts.append(f"Found {len(result.reasoning_paths)} reasoning paths:")
                for i, path in enumerate(result.reasoning_paths[:3]):
                    explanation_parts.append(
                        f"  {i+1}. {path.get_path_description()} "
                        f"(confidence: {path.total_confidence:.2f})"
                    )
            
            if result.related_concepts:
                explanation_parts.append(f"Identified {len(result.related_concepts)} related concepts:")
                for concept in result.related_concepts[:5]:
                    explanation_parts.append(
                        f"  - {concept.concept.concept_name} "
                        f"(relevance: {concept.relevance_score:.2f})"
                    )
            
            if result.confidence_scores:
                avg_confidence = sum(result.confidence_scores.values()) / len(result.confidence_scores)
                explanation_parts.append(f"Average confidence score: {avg_confidence:.2f}")
            
            return "\n".join(explanation_parts)
            
        except Exception as e:
            logger.error(f"Error explaining reasoning: {e}")
            return "Unable to generate reasoning explanation"
    
    
    
    def _calculate_relevance_score(self, relationship_path: List[RelationshipEdge]) -> float:
        """Calculate relevance score for a relationship path."""
        if not relationship_path:
            return 0.0
        
        # Use geometric mean of relationship confidences
        confidences = [rel.confidence for rel in relationship_path]
        product = 1.0
        for conf in confidences:
            product *= max(conf, 0.1)  # Avoid zero
        
        return product ** (1.0 / len(confidences))
    
    def _rerank_by_concept_relevance(
        self, 
        chunks: List[KnowledgeChunk], 
        related_concepts: List[RelatedConcept]
    ) -> List[KnowledgeChunk]:
        """Re-rank chunks based on concept relevance with UMLS scoring."""
        if not related_concepts:
            return chunks
        
        # Create concept relevance map
        concept_names = {rc.concept.concept_name.lower() for rc in related_concepts}
        
        # Score chunks based on concept presence in content
        chunk_scores = []
        for chunk in chunks:
            score = 0.0
            content_lower = chunk.content.lower()
            
            for rc in related_concepts:
                concept_name = rc.concept.concept_name.lower()
                if concept_name in content_lower:
                    adjusted = rc.relevance_score
                    # Apply UMLS scoring when client is available
                    adjusted *= self._umls_score_factor(rc.concept)
                    score += adjusted
            
            chunk_scores.append((chunk, score))
        
        # Sort by score (higher is better), then by original order
        chunk_scores.sort(key=lambda x: x[1], reverse=True)
        return [chunk for chunk, score in chunk_scores]
    
    def _umls_score_factor(self, concept: ConceptNode) -> float:
        """Return UMLS-based scoring multiplier for a concept.

        - 1.2x boost when the concept has a UMLS CUI (grounded in UMLS)
        - 0.7x penalty when concept_type contradicts UMLS semantic type
          (i.e. concept has a UMLS CUI but concept_type is a generic
          non-biomedical NER label like ORG/PERSON/GPE)
        - 1.0 (no change) when UMLS client is unavailable
        """
        if self._umls_client is None:
            return 1.0

        umls_cui = concept.external_ids.get("umls_cui") if concept.external_ids else None
        if not umls_cui:
            return 1.0

        # Concept is UMLS-grounded — check for semantic type contradiction
        non_biomedical_types = {"ORG", "PERSON", "GPE", "LOC", "FAC", "NORP"}
        if concept.concept_type in non_biomedical_types:
            return self.UMLS_PENALTY

        return self.UMLS_BOOST
    
    def _expand_with_related_chunks(
        self, 
        chunks: List[KnowledgeChunk], 
        related_concepts: List[RelatedConcept]
    ) -> List[KnowledgeChunk]:
        """Expand results with chunks from related concepts."""
        expanded_chunks = list(chunks)
        existing_chunk_ids = {chunk.id for chunk in chunks}
        
        # Add chunks from related concepts
        for related_concept in related_concepts[:10]:
            concept = related_concept.concept
            for chunk_id in concept.source_chunks:
                if chunk_id not in existing_chunk_ids:
                    # Create placeholder chunk
                    chunk = KnowledgeChunk(
                        id=chunk_id,
                        content=f"Related content from concept {concept.concept_name}",
                        embedding=np.zeros(384),
                        source_type="BOOK",
                        source_id="unknown",
                        location_reference="unknown",
                        section="unknown"
                    )
                    expanded_chunks.append(chunk)
                    existing_chunk_ids.add(chunk_id)
        
        return expanded_chunks
    
    def _calculate_query_confidence_scores(
        self, 
        query_concepts: List[str], 
        reasoning_paths: List[ReasoningPath],
        related_concepts: List[RelatedConcept]
    ) -> Dict[str, float]:
        """Calculate confidence scores for query processing."""
        scores = {}
        
        # Concept recognition confidence
        if query_concepts:
            scores['concept_recognition'] = min(len(query_concepts) / 5.0, 1.0)
        
        # Reasoning path confidence
        if reasoning_paths:
            path_confidences = [path.total_confidence for path in reasoning_paths]
            scores['reasoning_paths'] = sum(path_confidences) / len(path_confidences)
        
        # Related concept confidence
        if related_concepts:
            relevance_scores = [rc.relevance_score for rc in related_concepts]
            scores['related_concepts'] = sum(relevance_scores) / len(relevance_scores)
        
        return scores
    
