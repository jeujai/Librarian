"""
Enrichment Service for Knowledge Graph External Enrichment.

This service orchestrates YAGO (local Neo4j) and ConceptNet enrichment for
concepts, managing caching, circuit breakers, and Neo4j persistence.
"""

import asyncio
import logging
import time
from datetime import datetime
from typing import Any, Dict, List, Optional

from ..clients.conceptnet_client import ConceptNetClient
from ..components.yago.local_client import YagoLocalClient
from ..components.yago.models import YagoEntityData
from ..models.enrichment import (
    CircuitBreakerOpenError,
    ConceptNetRelation,
    EnrichedConcept,
    EnrichmentError,
    EnrichmentResult,
)
from ..models.knowledge_graph import ConceptNode
from .circuit_breaker import get_circuit_breaker
from .enrichment_cache import EnrichmentCache, get_enrichment_cache

logger = logging.getLogger(__name__)

# Confidence threshold for storing Q-numbers
YAGO_CONFIDENCE_THRESHOLD = 0.7


class EnrichmentService:
    """
    Orchestrates external knowledge base enrichment for concepts.
    
    Features:
    - YAGO entity lookup from local Neo4j and Q-number storage
    - Instance-of relationship creation from YAGO data
    - ConceptNet relationship storage
    - Cross-document linking via shared Q-numbers
    - Caching and circuit breaker integration
    """
    
    def __init__(
        self,
        yago_client: Optional[YagoLocalClient] = None,
        conceptnet_client: Optional[ConceptNetClient] = None,
        cache: Optional[EnrichmentCache] = None,
        kg_service: Optional[Any] = None,  # KnowledgeGraphService - avoid circular import
        model_client: Optional[Any] = None  # ModelServerClient for embedding generation
    ):
        """
        Initialize the enrichment service.
        
        Args:
            yago_client: YAGO local client for Neo4j queries (injected via Depends)
            conceptnet_client: ConceptNet API client
            cache: Enrichment cache
            kg_service: Knowledge graph service for Neo4j operations
            model_client: Model server client for generating embeddings
                         on newly created Concept nodes
        """
        self.yago = yago_client  # Use injected client (may be None for graceful degradation)
        self.cache = cache or get_enrichment_cache()
        self.kg_service = kg_service
        self.model_client = model_client
        
        # Pass Neo4j client to ConceptNetClient for local queries
        neo4j_client = kg_service.client if kg_service else None
        self.conceptnet = conceptnet_client or ConceptNetClient(neo4j_client=neo4j_client)
        
        # Circuit breakers
        self._yago_breaker = get_circuit_breaker("yago")
        self._conceptnet_breaker = get_circuit_breaker("conceptnet")
        
        logger.info("EnrichmentService initialized")
    
    async def enrich_concepts(
        self,
        concepts: List[ConceptNode],
        document_id: str
    ) -> EnrichmentResult:
        """
        Enrich a list of concepts with external knowledge using batch processing.

        This method implements batch API requests for efficiency (Requirement 4.5),
        error isolation (Requirement 4.3), circuit breaker integration
        (Requirement 7.3), and deferred enrichment marking (Requirement 7.5).

        Args:
            concepts: Concepts extracted from document
            document_id: Source document identifier

        Returns:
            EnrichmentResult with statistics and enriched concepts
        """
        start_time = time.time()
        result = EnrichmentResult()
        result.concepts_processed = len(concepts)

        if not concepts:
            logger.info("No concepts to enrich")
            return result

        logger.info(
            f"Starting batch enrichment for {len(concepts)} concepts "
            f"from document {document_id}"
        )

        # Check circuit breaker states
        yago_available = self._yago_breaker.allow_request()
        conceptnet_available = self._conceptnet_breaker.allow_request()

        # Track API calls for statistics
        api_calls_made = 0

        # Separate concepts into cached and uncached for batch processing
        uncached_yago = []
        uncached_conceptnet = []
        cached_yago: Dict[str, YagoEntityData] = {}
        cached_conceptnet: Dict[str, List[ConceptNetRelation]] = {}

        # Check cache for each concept
        for concept in concepts:
            # Check YAGO cache
            cached_wd = self.cache.get_yago(concept.concept_name)
            if cached_wd is not None:
                cached_yago[concept.concept_name] = cached_wd
            else:
                uncached_yago.append(concept.concept_name)

            # Check ConceptNet cache
            cached_cn = self.cache.get_conceptnet(concept.concept_name)
            if cached_cn is not None:
                cached_conceptnet[concept.concept_name] = cached_cn
            else:
                uncached_conceptnet.append(concept.concept_name)

        # Batch fetch from YAGO local (if circuit breaker allows)
        yago_results: Dict[str, Optional[YagoEntityData]] = {}
        if yago_available and uncached_yago and self.yago is not None:
            try:
                yago_results = await self.yago.batch_search_entities(uncached_yago)

                # Cache the results
                for name, entity in yago_results.items():
                    if entity:
                        self.cache.set_yago(name, entity)

            except Exception as e:
                logger.warning(f"Batch YAGO search failed: {e}")
                yago_results = {}

        # Batch fetch from ConceptNet (if circuit breaker allows)
        conceptnet_results: Dict[str, List[ConceptNetRelation]] = {}
        if conceptnet_available and uncached_conceptnet:
            try:
                conceptnet_results = await self.conceptnet.batch_get_relationships(
                    uncached_conceptnet
                )
                api_calls_made += len(uncached_conceptnet)

                # Cache the results
                for name, relations in conceptnet_results.items():
                    if relations:
                        self.cache.set_conceptnet(name, relations)

            except Exception as e:
                logger.warning(f"Batch ConceptNet fetch failed: {e}")
                # Fall back to individual processing
                conceptnet_results = {}

        # Process concepts concurrently with bounded parallelism
        CONCURRENCY = 10
        semaphore = asyncio.Semaphore(CONCURRENCY)
        deferred_count = 0

        async def _process_one(concept):
            async with semaphore:
                return await self._process_concept_with_batch_data(
                    concept=concept,
                    document_id=document_id,
                    yago_entity=(
                        cached_yago.get(concept.concept_name) or
                        yago_results.get(concept.concept_name)
                    ),
                    conceptnet_relations=(
                        cached_conceptnet.get(concept.concept_name) or
                        conceptnet_results.get(concept.concept_name, [])
                    ),
                    yago_available=yago_available,
                    conceptnet_available=conceptnet_available
                )

        # Fire all concepts concurrently (semaphore limits parallelism)
        tasks = [_process_one(c) for c in concepts]
        settled = await asyncio.gather(*tasks, return_exceptions=True)

        for concept, outcome in zip(concepts, settled):
            if isinstance(outcome, CircuitBreakerOpenError):
                deferred = EnrichedConcept(
                    concept_id=concept.concept_id,
                    concept_name=concept.concept_name,
                    enrichment_deferred=True
                )
                result.enriched_concepts.append(deferred)
                deferred_count += 1
                result.errors.append(
                    f"Circuit breaker open for {concept.concept_name}: {outcome}"
                )
            elif isinstance(outcome, EnrichmentError):
                result.errors.append(
                    f"Enrichment failed for {concept.concept_name}: {outcome}"
                )
                logger.warning(
                    f"Enrichment error for concept '{concept.concept_name}': {outcome}"
                )
                result.enriched_concepts.append(EnrichedConcept(
                    concept_id=concept.concept_id,
                    concept_name=concept.concept_name
                ))
            elif isinstance(outcome, Exception):
                result.errors.append(
                    f"Unexpected error for {concept.concept_name}: {outcome}"
                )
                logger.error(f"Unexpected enrichment error: {outcome}", exc_info=True)
                result.enriched_concepts.append(EnrichedConcept(
                    concept_id=concept.concept_id,
                    concept_name=concept.concept_name
                ))
            else:
                enriched = outcome
                result.enriched_concepts.append(enriched)

                if enriched.enrichment_deferred:
                    deferred_count += 1
                elif enriched.is_enriched:
                    result.concepts_enriched += 1

                if enriched.has_yago:
                    result.yago_hits += 1

                if enriched.has_conceptnet:
                    result.conceptnet_hits += 1

        # Calculate final statistics
        result.duration_ms = (time.time() - start_time) * 1000

        # --- Batch-persist all ConceptNet relationships in bulk ---
        # Collect (concept, relations) pairs from successful enrichments
        # and persist them all at once instead of per-concept.
        cn_pairs = []
        for enriched_concept in result.enriched_concepts:
            if enriched_concept.conceptnet_relations:
                # Find the original ConceptNode for this enriched concept
                orig = next(
                    (c for c in concepts
                     if c.concept_id == enriched_concept.concept_id),
                    None,
                )
                if orig:
                    cn_pairs.append(
                        (orig, enriched_concept.conceptnet_relations)
                    )
        if cn_pairs:
            try:
                await self._batch_persist_all_conceptnet(
                    cn_pairs, document_id
                )
            except Exception as e:
                logger.warning(
                    f"Batch ConceptNet persistence failed: {e}"
                )

        # --- Step 6: Compute composite cross-document scores ---
        if self.kg_service and self.kg_service.client:
            from .composite_score_engine import CompositeScoreEngine
            engine = CompositeScoreEngine(self.kg_service.client)
            composite_result = await engine.compute_composite_scores(document_id)
            logger.info(
                f"Composite scoring: {composite_result.edges_discovered} edges, "
                f"{composite_result.document_pairs} doc pairs, "
                f"{composite_result.duration_ms:.0f}ms"
            )

        result.api_calls = api_calls_made
        cache_stats = self.cache.get_stats()
        result.cache_hits = (
            len(cached_yago) + len(cached_conceptnet)
        )

        # Log enrichment statistics (Requirement 4.4)
        self._log_enrichment_statistics(
            result=result,
            document_id=document_id,
            deferred_count=deferred_count,
            yago_available=yago_available,
            conceptnet_available=conceptnet_available,
            cache_stats=cache_stats
        )

        return result

    async def _process_concept_with_batch_data(
        self,
        concept: ConceptNode,
        document_id: str,
        yago_entity: Optional[YagoEntityData],
        conceptnet_relations: List[ConceptNetRelation],
        yago_available: bool,
        conceptnet_available: bool
    ) -> EnrichedConcept:
        """
        Process a single concept using pre-fetched batch data.

        Args:
            concept: Concept to enrich
            document_id: Source document identifier
            yago_entity: Pre-fetched YAGO entity (or None)
            conceptnet_relations: Pre-fetched ConceptNet relations
            yago_available: Whether YAGO circuit breaker allows requests
            conceptnet_available: Whether ConceptNet circuit breaker allows

        Returns:
            EnrichedConcept with enrichment data
        """
        enriched = EnrichedConcept(
            concept_id=concept.concept_id,
            concept_name=concept.concept_name
        )

        # Check if both APIs are unavailable - mark as deferred
        if not yago_available and not conceptnet_available:
            enriched.enrichment_deferred = True
            return enriched

        # Process YAGO enrichment
        if yago_available and yago_entity:
            enriched.yago_entity = yago_entity

            # Store to Neo4j if confidence threshold met
            if yago_entity.confidence >= YAGO_CONFIDENCE_THRESHOLD:
                await self._persist_yago_enrichment(
                    concept, yago_entity, document_id
                )

                # Create cross-document links
                cross_links = await self.create_cross_document_links(
                    concept, yago_entity.entity_id
                )
                enriched.cross_document_links = cross_links
        elif not yago_available:
            # Mark YAGO as deferred if circuit breaker is open
            enriched.enrichment_deferred = True

        # Process ConceptNet enrichment
        # NOTE: Neo4j persistence is done in bulk at the batch level
        # by enrich_concepts() after all concepts are processed.
        if conceptnet_available and conceptnet_relations:
            enriched.conceptnet_relations = conceptnet_relations
        elif not conceptnet_available and not yago_available:
            # Both unavailable - already marked as deferred above
            pass

        return enriched

    def _log_enrichment_statistics(
        self,
        result: EnrichmentResult,
        document_id: str,
        deferred_count: int,
        yago_available: bool,
        conceptnet_available: bool,
        cache_stats: Any
    ) -> None:
        """
        Log comprehensive enrichment statistics (Requirement 4.4).

        Args:
            result: Enrichment result with statistics
            document_id: Source document identifier
            deferred_count: Number of concepts with deferred enrichment
            yago_available: Whether YAGO was available
            conceptnet_available: Whether ConceptNet was available
            cache_stats: Cache statistics
        """
        logger.info(
            "Enrichment complete",
            extra={
                "document_id": document_id,
                "concepts_processed": result.concepts_processed,
                "concepts_enriched": result.concepts_enriched,
                "yago_hits": result.yago_hits,
                "conceptnet_hits": result.conceptnet_hits,
                "cache_hits": result.cache_hits,
                "api_calls": result.api_calls,
                "deferred_count": deferred_count,
                "error_count": len(result.errors),
                "duration_ms": round(result.duration_ms, 1),
                "yago_available": yago_available,
                "conceptnet_available": conceptnet_available,
                "cache_yago_size": cache_stats.yago_size,
                "cache_conceptnet_size": cache_stats.conceptnet_size,
                "cache_yago_hit_rate": round(
                    cache_stats.yago_hit_rate, 2
                ),
                "cache_conceptnet_hit_rate": round(
                    cache_stats.conceptnet_hit_rate, 2
                )
            }
        )

        # Log summary message
        logger.info(
            f"Enrichment summary: "
            f"{result.concepts_enriched}/{result.concepts_processed} enriched, "
            f"{result.yago_hits} YAGO, {result.conceptnet_hits} ConceptNet, "
            f"{result.cache_hits} cache hits, {result.api_calls} API calls, "
            f"{deferred_count} deferred, {len(result.errors)} errors, "
            f"{result.duration_ms:.1f}ms"
        )
    
    async def enrich_single_concept(
        self,
        concept: ConceptNode,
        document_id: str
    ) -> EnrichedConcept:
        """
        Enrich a single concept with YAGO and ConceptNet data.
        
        Args:
            concept: Concept to enrich
            document_id: Source document identifier
            
        Returns:
            EnrichedConcept with enrichment data
        """
        enriched = EnrichedConcept(
            concept_id=concept.concept_id,
            concept_name=concept.concept_name
        )
        
        # Check circuit breakers
        yago_available = self._yago_breaker.allow_request()
        conceptnet_available = self._conceptnet_breaker.allow_request()
        
        if not yago_available and not conceptnet_available:
            enriched.enrichment_deferred = True
            return enriched
        
        # YAGO enrichment
        if yago_available:
            enriched.yago_entity = await self._get_yago_entity(concept)
            
            # Store to Neo4j if confidence threshold met
            if enriched.yago_entity and enriched.yago_entity.confidence >= YAGO_CONFIDENCE_THRESHOLD:
                await self._persist_yago_enrichment(concept, enriched.yago_entity, document_id)
                
                # Create cross-document links
                cross_links = await self.create_cross_document_links(
                    concept, enriched.yago_entity.entity_id
                )
                enriched.cross_document_links = cross_links
        
        # ConceptNet enrichment
        if conceptnet_available:
            enriched.conceptnet_relations = await self._get_conceptnet_relations(concept)
            
            # Store to Neo4j
            if enriched.conceptnet_relations:
                await self._persist_conceptnet_enrichment(concept, enriched.conceptnet_relations, document_id)
        
        return enriched
    
    async def create_cross_document_links(
        self,
        concept: ConceptNode,
        q_number: str
    ) -> List[str]:
        """
        Create SAME_AS relationships for concepts sharing a Q-number.

        This method finds all other concepts in the knowledge graph that
        share the same YAGO Q-number and creates bidirectional SAME_AS
        relationships between them, enabling cross-document entity linking.

        Uses Chunk-based EXTRACTED_FROM traversal to derive document IDs
        instead of reading source_document properties.

        Args:
            concept: The concept being enriched
            q_number: YAGO Q-number

        Returns:
            List of concept IDs that were linked

        Requirements: 10.2
        """
        if not self.kg_service:
            return []

        linked_concepts = []

        try:
            # Find other concepts with the same Q-number, deriving document IDs from Chunk traversal
            query = """
            MATCH (c:Concept)
            WHERE c.yago_qid = $q_number AND c.concept_id <> $concept_id
            OPTIONAL MATCH (c)-[:EXTRACTED_FROM]->(ch:Chunk)
            RETURN c.concept_id as concept_id, collect(DISTINCT ch.source_id) as document_ids
            """

            results = await self.kg_service.client.execute_query(query, {
                "q_number": q_number,
                "concept_id": concept.concept_id
            })

            # Derive the current concept's source_ids from its Chunk nodes
            current_source_ids = set()
            if concept.source_document:
                current_source_ids.add(concept.source_document)
            # Also check Chunk nodes for the current concept
            try:
                current_query = """
                MATCH (c:Concept {concept_id: $concept_id})-[:EXTRACTED_FROM]->(ch:Chunk)
                RETURN collect(DISTINCT ch.source_id) as source_ids
                """
                current_results = await self.kg_service.client.execute_query(
                    current_query, {"concept_id": concept.concept_id}
                )
                for rec in current_results:
                    current_source_ids.update(sid for sid in rec.get("source_ids", []) if sid)
            except Exception:
                pass  # Fall back to in-memory source_document

            # Create SAME_AS relationships with each matching concept from different documents
            for result in results:
                other_concept_id = result["concept_id"]
                other_document_ids = set(
                    sid for sid in result.get("document_ids", []) if sid
                )

                # Only link concepts from different documents (no overlapping source_ids)
                if other_document_ids and not other_document_ids.intersection(current_source_ids):
                    success = await self.kg_service.create_same_as_relationship(
                        concept_id_1=concept.concept_id,
                        concept_id_2=other_concept_id,
                        q_number=q_number
                    )

                    if success:
                        linked_concepts.append(other_concept_id)
                        logger.debug(
                            f"Created SAME_AS link: {concept.concept_id} <-> "
                            f"{other_concept_id} (Q: {q_number})"
                        )

            if linked_concepts:
                logger.info(
                    f"Created {len(linked_concepts)} cross-document links "
                    f"for Q-number {q_number}"
                )

        except Exception as e:
            logger.warning(f"Error creating cross-document links: {e}")

        return linked_concepts
    
    async def find_documents_by_entity(self, q_number: str) -> List[str]:
        """
        Find all documents containing concepts linked to a YAGO entity.
        
        This method delegates to KnowledgeGraphService for the actual query.
        
        Args:
            q_number: YAGO Q-number
            
        Returns:
            List of document IDs
            
        Requirements: 5.3
        """
        if not self.kg_service:
            return []
        
        try:
            return await self.kg_service.find_documents_by_entity(q_number)
        except Exception as e:
            logger.warning(f"Error finding documents by entity: {e}")
            return []
    
    async def query_cross_document_concepts(
        self,
        concept_id: str,
        max_hops: int = 2
    ) -> List[Dict[str, Any]]:
        """
        Query for related concepts across documents via SAME_AS relationships.
        
        This method finds concepts from other documents that share the same
        YAGO entity, enabling cross-document knowledge discovery.
        
        Args:
            concept_id: Starting concept ID
            max_hops: Maximum SAME_AS hops to traverse
            
        Returns:
            List of related concepts from other documents
            
        Requirements: 5.2
        """
        if not self.kg_service:
            return []
        
        try:
            return await self.kg_service.query_with_same_as_traversal(
                concept_id, max_hops
            )
        except Exception as e:
            logger.warning(
                f"Error querying cross-document concepts for {concept_id}: {e}"
            )
            return []
    
    # =========================================================================
    # Private Methods - YAGO
    # =========================================================================
    
    async def _get_yago_entity(self, concept: ConceptNode) -> Optional[YagoEntityData]:
        """Get YAGO entity for a concept, using cache if available.
        
        Uses injected YAGO local client with graceful degradation.
        """
        # Graceful degradation: if no client available, skip YAGO lookup
        if self.yago is None:
            return None
        
        # Check cache first
        cached = self.cache.get_yago(concept.concept_name)
        if cached is not None:
            return cached
        
        # Query YAGO local data
        try:
            results = await self.yago.search_entities(concept.concept_name, limit=1)
            
            if results:
                # Convert search result to full entity data
                entity = await self.yago.get_entity(results[0].entity_id)
                if entity:
                    self.cache.set_yago(concept.concept_name, entity)
                return entity
            
            return None
            
        except Exception as e:
            logger.warning(f"YAGO lookup failed for '{concept.concept_name}': {e}")
            return None

    async def _get_yago_entity_by_name(self, name: str) -> Optional[YagoEntityData]:
        """Get YAGO entity by concept name for batch processing."""
        if self.yago is None:
            return None
        
        try:
            results = await self.yago.search_entities(name, limit=1)
            if results:
                return await self.yago.get_entity(results[0].entity_id)
            return None
        except Exception as e:
            logger.warning(f"YAGO lookup failed for '{name}': {e}")
            return None
    
    async def _persist_yago_enrichment(
        self,
        concept: ConceptNode,
        entity: YagoEntityData,
        document_id: str
    ) -> None:
        """Persist YAGO enrichment to Neo4j."""
        if not self.kg_service:
            return

        try:
            # Update concept node with YAGO data
            update_query = """
            MATCH (c:Concept {concept_id: $concept_id})
            SET c.yago_qid = $q_number,
                c.yago_label = $label,
                c.yago_description = $description,
                c.enriched_at = $enriched_at
            RETURN elementId(c) as node_id
            """

            result = await self.kg_service.client.execute_query(update_query, {
                "concept_id": concept.concept_id,
                "q_number": entity.entity_id,
                "label": entity.label,
                "description": entity.description or "",
                "enriched_at": datetime.utcnow().isoformat()
            })

            if not result:
                logger.warning(
                    f"Concept node not found for update: {concept.concept_id}"
                )
                return

            concept_node_id = result[0]["node_id"]

            # Use instance-of data from YAGO entity directly
            if entity.instance_of:
                external_nodes = await self._create_external_entity_nodes(
                    entity.instance_of
                )

                # Create INSTANCE_OF relationships
                await self._create_instance_of_relationships(
                    concept_node_id,
                    external_nodes,
                    entity.confidence
                )

            logger.debug(
                f"Persisted YAGO enrichment for {concept.concept_name}: "
                f"{entity.entity_id}"
            )

        except Exception as e:
            logger.warning(f"Error persisting YAGO enrichment: {e}")
    
    async def _create_external_entity_nodes(
        self,
        instance_of_ids: List[str]
    ) -> List[Dict[str, Any]]:
        """
        Create External_Entity_Node entries for YAGO instance-of classes.

        Looks up each entity ID in YAGO local data and creates/reuses
        ExternalEntity nodes in Neo4j.

        Args:
            instance_of_ids: List of YAGO entity IDs from instance-of

        Returns:
            List of node dictionaries with 'id', 'q_number', 'label', etc.

        Requirements: 2.2, 2.4, 2.5
        """
        if not self.kg_service:
            return []

        external_nodes = []

        for entity_id in instance_of_ids:
            try:
                # Check if External Entity node already exists (deduplication)
                check_query = """
                MATCH (e:ExternalEntity {q_number: $q_number})
                RETURN e, elementId(e) as node_id
                """

                result = await self.kg_service.client.execute_query(
                    check_query,
                    {"q_number": entity_id}
                )

                if result:
                    # Reuse existing node (Requirement 2.5)
                    node_data = dict(result[0]["e"])
                    node_data["id"] = result[0]["node_id"]
                    external_nodes.append(node_data)
                    logger.debug(
                        f"Reusing existing ExternalEntity: {entity_id}"
                    )
                else:
                    # Look up label from YAGO local data
                    label = entity_id
                    description = ""
                    if self.yago:
                        yago_entity = await self.yago.get_entity(entity_id)
                        if yago_entity:
                            label = yago_entity.label
                            description = yago_entity.description or ""

                    # Create new External Entity node (Requirement 2.2)
                    node = await self.kg_service.create_node(
                        label="ExternalEntity",
                        properties={
                            "q_number": entity_id,
                            "label": label,
                            "description": description,
                            "source": "yago",
                            "fetched_at": datetime.utcnow().isoformat(),
                            "created_at": datetime.utcnow().isoformat(),
                            "updated_at": datetime.utcnow().isoformat()
                        },
                        merge_on=["q_number"]
                    )
                    if node:
                        external_nodes.append(node)
                        logger.debug(
                            f"Created ExternalEntity: {entity_id} ({label})"
                        )

            except Exception as e:
                logger.warning(
                    f"Error creating External Entity for {entity_id}: {e}"
                )

        return external_nodes

    async def _create_instance_of_relationships(
        self,
        concept_node_id,
        external_nodes: List[Dict[str, Any]],
        confidence: float
    ) -> int:
        """
        Create INSTANCE_OF relationships from Concept to External Entity nodes.

        Args:
            concept_node_id: Neo4j node ID of the concept
            external_nodes: List of External Entity node dictionaries
            confidence: Confidence score for the relationships

        Returns:
            Number of relationships created

        Requirements: 2.3, 8.4
        """
        if not self.kg_service:
            return 0

        relationships_created = 0

        for external_node in external_nodes:
            try:
                external_node_id = external_node.get("id")
                if not external_node_id:
                    continue

                # Create INSTANCE_OF relationship with required properties
                # (Requirement 8.4: confidence, fetched_at)
                await self.kg_service.create_relationship(
                    from_node_id=concept_node_id,
                    to_node_id=external_node_id,
                    relationship_type="INSTANCE_OF",
                    properties={
                        "confidence": confidence,
                        "fetched_at": datetime.utcnow().isoformat(),
                        "source": "yago"
                    }
                )
                relationships_created += 1

            except Exception as e:
                logger.warning(
                    f"Error creating INSTANCE_OF relationship to "
                    f"{external_node.get('q_number', 'unknown')}: {e}"
                )

        if relationships_created > 0:
            logger.debug(
                f"Created {relationships_created} INSTANCE_OF relationships"
            )

        return relationships_created
    
    # =========================================================================
    # Private Methods - ConceptNet
    # =========================================================================
    
    async def _get_conceptnet_relations(self, concept: ConceptNode) -> List[ConceptNetRelation]:
        """Get ConceptNet relations for a concept, using cache if available."""
        # Check cache first
        cached = self.cache.get_conceptnet(concept.concept_name)
        if cached is not None:
            return cached
        
        # Query ConceptNet API
        try:
            relations = await self.conceptnet.get_relationships(concept.concept_name)
            
            if relations:
                # Cache the result
                self.cache.set_conceptnet(concept.concept_name, relations)
            
            return relations
            
        except Exception as e:
            logger.warning(f"ConceptNet lookup failed for '{concept.concept_name}': {e}")
            return []
    
    async def _batch_persist_all_conceptnet(
        self,
        concept_relation_pairs: List[tuple],
        document_id: str,
    ) -> int:
        """Persist ConceptNet relationships for ALL concepts in bulk.

        Instead of N separate _store_conceptnet_relationships calls
        (each doing 3+ Neo4j queries), this method:
          1. Batch-resolves all source concept node IDs (1 query)
          2. Batch-checks all target concept existence (1 query)
          3. Batch-creates missing target nodes with embeddings (1-2 queries)
          4. Batch-creates relationships grouped by type (1 query per type)

        Args:
            concept_relation_pairs: list of (ConceptNode, [ConceptNetRelation])
            document_id: Source document identifier

        Returns:
            Total relationships created
        """
        if not self.kg_service or not concept_relation_pairs:
            return 0

        import re
        total_rels = 0

        try:
            # 1. Batch-resolve source concept node IDs
            all_concept_ids = list({
                c.concept_id for c, _ in concept_relation_pairs
            })
            src_map: Dict[str, str] = {}  # concept_id -> elementId
            for batch_start in range(0, len(all_concept_ids), 500):
                batch = all_concept_ids[batch_start:batch_start + 500]
                try:
                    res = await self.kg_service.client.execute_query(
                        """
                        UNWIND $ids AS cid
                        MATCH (c:Concept {concept_id: cid})
                        RETURN c.concept_id AS cid,
                               elementId(c) AS nid
                        """,
                        {'ids': batch},
                    )
                    for rec in (res or []):
                        src_map[rec['cid']] = rec['nid']
                except Exception as e:
                    logger.warning(
                        f"Batch source concept lookup failed: {e}"
                    )

            # 2. Collect all unique target names across all relations
            all_target_names: set = set()
            for _, relations in concept_relation_pairs:
                for r in relations:
                    all_target_names.add(r.object)
            all_target_names = list(all_target_names)

            # 3. Batch-check which targets already exist
            target_map: Dict[str, str] = {}  # lowered name -> elementId
            for batch_start in range(0, len(all_target_names), 500):
                batch = all_target_names[
                    batch_start:batch_start + 500
                ]
                try:
                    res = await self.kg_service.client.execute_query(
                        """
                        UNWIND $names AS tname
                        OPTIONAL MATCH (c:Concept)
                        WHERE toLower(c.name) = toLower(tname)
                        WITH tname,
                             collect(elementId(c))[0] AS nid
                        WHERE nid IS NOT NULL
                        RETURN tname, nid AS node_id
                        """,
                        {'names': batch},
                    )
                    for rec in (res or []):
                        target_map[
                            rec['tname'].lower()
                        ] = rec['node_id']
                except Exception as e:
                    logger.warning(
                        f"Batch target lookup failed: {e}"
                    )

            # 4. Create missing target nodes in bulk
            missing = [
                n for n in all_target_names
                if n.lower() not in target_map
            ]
            if missing:
                # Generate embeddings in one call
                emb_map: Dict[str, list] = {}
                if self.model_client:
                    EMB_BATCH = 500
                    for eb_start in range(0, len(missing), EMB_BATCH):
                        sub = missing[eb_start:eb_start + EMB_BATCH]
                        try:
                            embs = (
                                await self.model_client
                                .generate_embeddings(sub)
                            )
                            if embs and len(embs) == len(sub):
                                for name, emb in zip(sub, embs):
                                    emb_map[name] = emb
                        except Exception as e:
                            logger.debug(
                                f"Batch embedding for targets failed: {e}"
                            )

                # Build rows and MERGE in sub-batches
                now_ts = datetime.utcnow().isoformat()
                # Build a weight map from all relations
                name_weights: Dict[str, float] = {}
                for _, relations in concept_relation_pairs:
                    for r in relations:
                        if r.object not in name_weights:
                            name_weights[r.object] = r.weight

                rows_no_emb = []
                rows_with_emb = []
                for name in missing:
                    row = {
                        'concept_id': (
                            f"conceptnet_"
                            f"{name.lower().replace(' ', '_')}"
                        ),
                        'name': name,
                        'type': 'EXTERNAL',
                        'confidence': name_weights.get(name, 0.0),
                        'created_at': now_ts,
                        'updated_at': now_ts,
                    }
                    emb = emb_map.get(name)
                    if emb is not None:
                        row['embedding'] = emb
                        rows_with_emb.append(row)
                    else:
                        rows_no_emb.append(row)

                for rows, has_emb in [
                    (rows_no_emb, False),
                    (rows_with_emb, True),
                ]:
                    if not rows:
                        continue
                    emb_set = (
                        ", c.embedding = row.embedding"
                        if has_emb else ""
                    )
                    for sb in range(0, len(rows), 500):
                        sub = rows[sb:sb + 500]
                        try:
                            res = (
                                await self.kg_service.client
                                .execute_query(
                                    f"""
                                    UNWIND $rows AS row
                                    MERGE (c:Concept
                                        {{concept_id: row.concept_id}})
                                    ON CREATE SET
                                        c.name = row.name,
                                        c.type = row.type,
                                        c.confidence = row.confidence,
                                        c.created_at = row.created_at,
                                        c.updated_at =
                                            row.updated_at{emb_set}
                                    ON MATCH SET
                                        c.updated_at = row.updated_at
                                    RETURN row.name AS name,
                                           elementId(c) AS node_id
                                    """,
                                    {'rows': sub},
                                )
                            )
                            for rec in (res or []):
                                target_map[
                                    rec['name'].lower()
                                ] = rec['node_id']
                        except Exception as e:
                            logger.warning(
                                f"Batch create targets failed: {e}"
                            )

            # 5. Collect ALL relationships across all concepts
            rels_by_type: Dict[str, list] = {}
            now_ts = datetime.utcnow().isoformat()
            for concept, relations in concept_relation_pairs:
                src_nid = src_map.get(concept.concept_id)
                if not src_nid:
                    continue
                for relation in relations:
                    tgt_nid = target_map.get(relation.object.lower())
                    if not tgt_nid:
                        continue
                    edge_label = self._map_conceptnet_relation(
                        relation.relation
                    )
                    sanitized = re.sub(
                        r'[^A-Za-z0-9_]', '_', edge_label
                    )
                    rels_by_type.setdefault(sanitized, []).append({
                        'from_id': str(src_nid),
                        'to_id': str(tgt_nid),
                        'weight': relation.weight,
                        'source_uri': relation.source_uri,
                        'fetched_at': now_ts,
                        'source': 'conceptnet',
                    })

            # 6. Batch-create relationships by type
            for rel_type, rel_rows in rels_by_type.items():
                for sb in range(0, len(rel_rows), 500):
                    sub = rel_rows[sb:sb + 500]
                    try:
                        res = (
                            await self.kg_service.client
                            .execute_query(
                                f"""
                                UNWIND $rows AS row
                                MATCH (a)
                                    WHERE elementId(a) = row.from_id
                                MATCH (b)
                                    WHERE elementId(b) = row.to_id
                                MERGE (a)-[r:{rel_type}]->(b)
                                ON CREATE SET
                                    r.weight = row.weight,
                                    r.source_uri = row.source_uri,
                                    r.fetched_at = row.fetched_at,
                                    r.source = row.source
                                ON MATCH SET r.weight = row.weight
                                RETURN count(r) AS cnt
                                """,
                                {'rows': sub},
                            )
                        )
                        cnt = res[0]['cnt'] if res else 0
                        total_rels += cnt
                    except Exception as e:
                        logger.warning(
                            f"Batch rel MERGE ({rel_type}) failed: {e}"
                        )

            logger.info(
                f"Batch ConceptNet persistence: "
                f"{total_rels} relationships for "
                f"{len(concept_relation_pairs)} concepts"
            )

        except Exception as e:
            logger.warning(
                f"_batch_persist_all_conceptnet failed: {e}"
            )

        return total_rels

    async def _store_conceptnet_relationships(
        self,
        concept: ConceptNode,
        relations: List[ConceptNetRelation],
        document_id: str
    ) -> int:
        """
        Store ConceptNet relationships to Neo4j using batched UNWIND queries.

        Groups relations by mapped edge label and persists each group in a
        single UNWIND query for dramatically better throughput.

        Args:
            concept: The source concept node
            relations: List of ConceptNet relationships to store
            document_id: Source document identifier

        Returns:
            Number of relationships successfully stored

        Requirements: 3.2, 3.4
        """
        if not self.kg_service or not relations:
            return 0

        relationships_created = 0

        try:
            # Get concept node ID
            query = """
            MATCH (c:Concept {concept_id: $concept_id})
            RETURN elementId(c) as node_id
            """

            result = await self.kg_service.client.execute_query(query, {
                "concept_id": concept.concept_id
            })

            if not result:
                logger.warning(
                    f"Concept node not found for ConceptNet storage: "
                    f"{concept.concept_id}"
                )
                return 0

            concept_node_id = result[0]["node_id"]

            # Separate relations into those with existing targets vs new targets.
            # Batch-check which target concepts already exist.
            target_names = list({r.object for r in relations})
            target_map: Dict[str, str] = {}  # lowered name -> elementId

            if target_names:
                check_query = """
                UNWIND $names AS tname
                MATCH (c:Concept)
                WHERE toLower(c.name) = toLower(tname)
                RETURN tname, elementId(c) AS node_id
                LIMIT 1
                """
                # Neo4j UNWIND + LIMIT doesn't scope per-row, so query individually
                # but in a single batch via UNWIND + collect
                check_query = """
                UNWIND $names AS tname
                OPTIONAL MATCH (c:Concept)
                WHERE toLower(c.name) = toLower(tname)
                WITH tname, collect(elementId(c))[0] AS nid
                WHERE nid IS NOT NULL
                RETURN tname, nid AS node_id
                """
                try:
                    existing = await self.kg_service.client.execute_query(
                        check_query, {"names": target_names}
                    )
                    for rec in (existing or []):
                        target_map[rec["tname"].lower()] = rec["node_id"]
                except Exception as e:
                    logger.warning(f"Batch target lookup failed: {e}")

            # Create missing target concept nodes in batch
            missing_names = [n for n in target_names if n.lower() not in target_map]
            if missing_names:
                # Generate embeddings for all missing concepts in one call
                embeddings_map: Dict[str, list] = {}
                if self.model_client:
                    try:
                        embs = await self.model_client.generate_embeddings(missing_names)
                        if embs and len(embs) == len(missing_names):
                            for name, emb in zip(missing_names, embs):
                                embeddings_map[name] = emb
                    except Exception as emb_err:
                        logger.debug(f"Batch embedding for ConceptNet targets failed: {emb_err}")

                # Find weight for each missing name from relations
                name_weights = {}
                for r in relations:
                    if r.object in missing_names and r.object not in name_weights:
                        name_weights[r.object] = r.weight

                rows_no_emb = []
                rows_with_emb = []
                now_ts = datetime.utcnow().isoformat()
                for name in missing_names:
                    row = {
                        'concept_id': f"conceptnet_{name.lower().replace(' ', '_')}",
                        'name': name,
                        'type': 'EXTERNAL',
                        'confidence': name_weights.get(name, 0.0),
                        'created_at': now_ts,
                        'updated_at': now_ts,
                    }
                    emb = embeddings_map.get(name)
                    if emb is not None:
                        row['embedding'] = emb
                        rows_with_emb.append(row)
                    else:
                        rows_no_emb.append(row)

                for rows, has_emb in [(rows_no_emb, False), (rows_with_emb, True)]:
                    if not rows:
                        continue
                    emb_set = ", c.embedding = row.embedding" if has_emb else ""
                    try:
                        res = await self.kg_service.client.execute_query(
                            f"""
                            UNWIND $rows AS row
                            MERGE (c:Concept {{concept_id: row.concept_id}})
                            ON CREATE SET c.name = row.name, c.type = row.type,
                                          c.confidence = row.confidence,
                                          c.created_at = row.created_at,
                                          c.updated_at = row.updated_at{emb_set}
                            ON MATCH SET c.updated_at = row.updated_at
                            RETURN row.name AS name, elementId(c) AS node_id
                            """,
                            {'rows': rows}
                        )
                        for rec in (res or []):
                            target_map[rec["name"].lower()] = rec["node_id"]
                    except Exception as e:
                        logger.warning(f"Batch create ConceptNet targets failed: {e}")

            # Group relations by edge label and batch-create relationships
            import re
            rels_by_type: Dict[str, list] = {}
            now_ts = datetime.utcnow().isoformat()
            for relation in relations:
                target_nid = target_map.get(relation.object.lower())
                if not target_nid:
                    continue
                edge_label = self._map_conceptnet_relation(relation.relation)
                sanitized = re.sub(r'[^A-Za-z0-9_]', '_', edge_label)
                rels_by_type.setdefault(sanitized, []).append({
                    'from_id': str(concept_node_id),
                    'to_id': str(target_nid),
                    'weight': relation.weight,
                    'source_uri': relation.source_uri,
                    'fetched_at': now_ts,
                    'source': 'conceptnet',
                })

            for rel_type, rel_rows in rels_by_type.items():
                try:
                    res = await self.kg_service.client.execute_query(
                        f"""
                        UNWIND $rows AS row
                        MATCH (a) WHERE elementId(a) = row.from_id
                        MATCH (b) WHERE elementId(b) = row.to_id
                        MERGE (a)-[r:{rel_type}]->(b)
                        ON CREATE SET r.weight = row.weight,
                                      r.source_uri = row.source_uri,
                                      r.fetched_at = row.fetched_at,
                                      r.source = row.source
                        ON MATCH SET r.weight = row.weight
                        RETURN count(r) AS cnt
                        """,
                        {'rows': rel_rows}
                    )
                    cnt = res[0]['cnt'] if res else 0
                    relationships_created += cnt
                except Exception as e:
                    logger.warning(f"Batch ConceptNet rel MERGE ({rel_type}) failed: {e}")

            if relationships_created > 0:
                logger.debug(
                    f"Stored {relationships_created}/{len(relations)} "
                    f"ConceptNet relations for {concept.concept_name}"
                )

        except Exception as e:
            logger.warning(f"Error storing ConceptNet relationships: {e}")

        return relationships_created

    async def _persist_conceptnet_enrichment(
        self,
        concept: ConceptNode,
        relations: List[ConceptNetRelation],
        document_id: str
    ) -> None:
        """
        Persist ConceptNet relationships to Neo4j.

        Alias for _store_conceptnet_relationships for backward compatibility.
        """
        await self._store_conceptnet_relationships(concept, relations, document_id)
    
    async def _create_conceptnet_relationship(
        self,
        from_node_id: int,
        relation: ConceptNetRelation,
        document_id: str
    ) -> bool:
        """
        Create a ConceptNet relationship edge in Neo4j.

        Maps ConceptNet relation type to Neo4j edge label and stores
        weight and source_uri properties on the edge.

        Args:
            from_node_id: Neo4j node ID of the source concept
            relation: ConceptNet relationship to create
            document_id: Source document identifier

        Returns:
            True if relationship was created successfully, False otherwise

        Requirements: 3.2, 3.4, 8.5
        """
        if not self.kg_service:
            return False

        try:
            # Find or create target concept node
            target_query = """
            MATCH (c:Concept)
            WHERE toLower(c.name) = toLower($target_name)
            RETURN elementId(c) as node_id
            LIMIT 1
            """

            target_result = await self.kg_service.client.execute_query(
                target_query,
                {"target_name": relation.object}
            )

            if not target_result:
                # Create a new concept node for the target
                properties = {
                    "concept_id": f"conceptnet_{relation.object.lower().replace(' ', '_')}",
                    "name": relation.object,
                    "type": "EXTERNAL",
                    "confidence": relation.weight,
                }

                # Generate embedding for the new concept so it's
                # discoverable via semantic search in the query pipeline.
                if self.model_client:
                    try:
                        embeddings = await self.model_client.generate_embeddings([relation.object])
                        if embeddings and len(embeddings) == 1:
                            properties["embedding"] = embeddings[0]
                    except Exception as emb_err:
                        logger.debug(f"Embedding generation failed for ConceptNet concept '{relation.object}': {emb_err}")

                target_node = await self.kg_service.create_node(
                    label="Concept",
                    properties=properties,
                    merge_on=["concept_id"]
                )
                target_node_id = target_node["id"]
            else:
                target_node_id = target_result[0]["node_id"]

            # Map ConceptNet relation type to Neo4j edge label (Requirement 3.2)
            edge_label = self._map_conceptnet_relation(relation.relation)

            # Create the relationship with weight and source_uri (Requirement 3.4, 8.5)
            await self.kg_service.create_relationship(
                from_node_id=from_node_id,
                to_node_id=target_node_id,
                relationship_type=edge_label,
                properties={
                    "weight": relation.weight,
                    "source_uri": relation.source_uri,
                    "fetched_at": datetime.utcnow().isoformat(),
                    "source": "conceptnet"
                }
            )

            return True

        except Exception as e:
            logger.debug(f"Error creating ConceptNet relationship: {e}")
            return False
    
    def _map_conceptnet_relation(self, relation_type: str) -> str:
        """
        Map ConceptNet relation type to Neo4j edge label.

        Converts CamelCase ConceptNet relation types to UPPER_SNAKE_CASE
        Neo4j edge labels for consistency with graph database conventions.

        Args:
            relation_type: ConceptNet relation type (e.g., "IsA", "PartOf")

        Returns:
            Neo4j edge label (e.g., "IS_A", "PART_OF")

        Requirements: 3.2, 3.3
        """
        # Mapping from ConceptNet CamelCase to Neo4j UPPER_SNAKE_CASE
        # Supports all relationship types from Requirement 3.3:
        # IsA, PartOf, UsedFor, CapableOf, HasProperty, AtLocation,
        # Causes, HasPrerequisite, MotivatedByGoal, RelatedTo
        mapping = {
            "IsA": "IS_A",
            "PartOf": "PART_OF",
            "UsedFor": "USED_FOR",
            "CapableOf": "CAPABLE_OF",
            "HasProperty": "HAS_PROPERTY",
            "AtLocation": "AT_LOCATION",
            "Causes": "CAUSES",
            "HasPrerequisite": "HAS_PREREQUISITE",
            "MotivatedByGoal": "MOTIVATED_BY_GOAL",
            "RelatedTo": "RELATED_TO",
            # Additional common ConceptNet relations
            "Synonym": "SYNONYM",
            "Antonym": "ANTONYM",
            "DerivedFrom": "DERIVED_FROM",
            "DefinedAs": "DEFINED_AS",
            "HasA": "HAS_A",
            "MadeOf": "MADE_OF",
            "ReceivesAction": "RECEIVES_ACTION",
            "CreatedBy": "CREATED_BY",
            "SymbolOf": "SYMBOL_OF",
            "LocatedNear": "LOCATED_NEAR",
            "HasContext": "HAS_CONTEXT",
            "SimilarTo": "SIMILAR_TO",
            "EtymologicallyRelatedTo": "ETYMOLOGICALLY_RELATED_TO",
            "EtymologicallyDerivedFrom": "ETYMOLOGICALLY_DERIVED_FROM",
            "CausesDesire": "CAUSES_DESIRE",
            "HasSubevent": "HAS_SUBEVENT",
            "HasFirstSubevent": "HAS_FIRST_SUBEVENT",
            "HasLastSubevent": "HAS_LAST_SUBEVENT",
            "InstanceOf": "INSTANCE_OF",
            "MannerOf": "MANNER_OF",
            "Entails": "ENTAILS",
            "DistinctFrom": "DISTINCT_FROM",
            "NotDesires": "NOT_DESIRES",
            "NotUsedFor": "NOT_USED_FOR",
            "NotCapableOf": "NOT_CAPABLE_OF",
            "NotHasProperty": "NOT_HAS_PROPERTY",
            "Desires": "DESIRES",
            "ObstructedBy": "OBSTRUCTED_BY",
            "FormOf": "FORM_OF",
            "ExternalURL": "EXTERNAL_URL",
            "dbpedia": "DBPEDIA_LINK",
            "dbpedia/genre": "DBPEDIA_GENRE",
            "dbpedia/influencedBy": "DBPEDIA_INFLUENCED_BY",
        }
        return mapping.get(relation_type, "RELATED_TO")


# Global service instance
_enrichment_service: Optional[EnrichmentService] = None


def get_enrichment_service() -> EnrichmentService:
    """
    Get or create the global enrichment service instance.
    
    Returns:
        EnrichmentService singleton instance
    """
    global _enrichment_service
    
    if _enrichment_service is None:
        _enrichment_service = EnrichmentService()
    
    return _enrichment_service


async def get_enrichment_service_with_kg() -> EnrichmentService:
    """
    Get enrichment service with knowledge graph service injected.
    
    Returns:
        EnrichmentService with KG service
    """
    from .knowledge_graph_service import get_knowledge_graph_service
    
    service = get_enrichment_service()
    if service.kg_service is None:
        service.kg_service = get_knowledge_graph_service()
    
    return service
