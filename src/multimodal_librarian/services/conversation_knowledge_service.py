"""
Conversation Knowledge Service — orchestrates the full pipeline for converting
a conversation thread into queryable knowledge:

    cleanup → chunk → embed → store vectors → extract KG concepts

The pipeline is fail-fast: any stage failure aborts the entire operation.
KG failure is FATAL (no graceful degradation).
"""

import json
import logging
import re
import uuid as uuid_module
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, List, Optional

from ..clients.model_server_client import ModelServerClient
from ..components.conversation.conversation_manager import ConversationManager
from ..components.knowledge_graph.conceptnet_validator import ConceptNetValidator
from ..components.knowledge_graph.kg_builder import (
    ConceptExtractor,
    RelationshipExtractor,
)
from ..components.vector_store.vector_store import VectorStore
from ..models.core import KnowledgeChunk, RelationshipType
from ..models.knowledge_graph import ConceptNode, RelationshipEdge

logger = logging.getLogger(__name__)

# Regex patterns for extracting source citations from AI response text.
# Each pattern captures the citation name/title in group 1.
CITATION_PATTERNS = [
    re.compile(r"Source:\s*(.+?)(?:\n|$)"),
    re.compile(r"from\s+[\"'](.+?)[\"']"),
    re.compile(r"according to\s+[\"'](.+?)[\"']"),
    re.compile(r"(?:cited|referenced) in\s+(.+?)(?:\.|,|\n|$)"),
    re.compile(r"\[Source:\s*(.+?)\]"),
    re.compile(r"📄\s*(.+?)(?:\n|$)"),
]


@dataclass
class ConversionResult:
    """Result of a conversation knowledge conversion pipeline run."""
    thread_id: str
    chunks_created: int
    concepts_extracted: int
    relationships_extracted: int
    chunks_cleaned: int
    concepts_cleaned: int


@dataclass
class CleanupResult:
    """Result of cleanup phase before re-ingestion."""
    vectors_deleted: int
    concepts_deleted: int


class ConversationKnowledgeService:
    """Orchestrates conversation → knowledge pipeline.

    Pipeline stages (fail-fast):
        0. Cleanup existing vectors + KG data for the thread
        1. Retrieve conversation and convert to KnowledgeChunks
        2. Generate embeddings via model server
        3. Store chunks in vector store
        4. Extract concepts/relationships and persist to Neo4j
    """

    def __init__(
        self,
        conversation_manager: ConversationManager,
        vector_store: VectorStore,
        model_server_client: ModelServerClient,
        neo4j_client: Any,
        conceptnet_validator: Optional[ConceptNetValidator] = None,
    ):
        self._conversation_manager = conversation_manager
        self._vector_store = vector_store
        self._model_client = model_server_client
        self._neo4j_client = neo4j_client
        self._concept_extractor = ConceptExtractor()
        self._relationship_extractor = RelationshipExtractor()
        self._conceptnet_validator = conceptnet_validator

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _source_id_for_thread(thread_id: str) -> str:
        """Deterministic UUID5 source ID matching knowledge_sources table."""
        return str(uuid_module.uuid5(uuid_module.NAMESPACE_URL, thread_id))

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def convert_conversation(
        self, thread_id: str, title: Optional[str] = None
    ) -> ConversionResult:
        """Full pipeline: cleanup → chunk → embed → store → KG extract.

        Raises on any stage failure (fail-fast, no graceful degradation).

        Args:
            thread_id: Conversation thread identifier.
            title: Optional title for the knowledge source document.
                   When provided, the linked knowledge source record is
                   updated after a successful conversion.

        Returns:
            ConversionResult with counts from each stage.

        Raises:
            ValueError: If thread not found or has no messages.
            Exception: Propagated from any pipeline stage on failure.
        """
        # Retrieve conversation
        conversation = self._conversation_manager.get_conversation(thread_id)
        if conversation is None:
            raise ValueError(f"Conversation thread {thread_id} not found")
        if not conversation.messages:
            logger.info(
                f"Conversation {thread_id} has no messages, "
                "skipping conversion"
            )
            return ConversionResult(
                thread_id=thread_id,
                chunks_created=0,
                concepts_extracted=0,
                relationships_extracted=0,
                chunks_cleaned=0,
                concepts_cleaned=0,
            )

        # Phase 0: Cleanup existing data for idempotent re-ingestion
        source_id = self._source_id_for_thread(thread_id)
        cleanup = await self._cleanup_existing(thread_id, source_id)

        # Phase 1: Convert conversation to knowledge chunks
        chunks = self._conversation_manager.convert_to_knowledge_chunks(conversation)
        # Align chunk source_id with knowledge_sources.id (UUID5)
        for chunk in chunks:
            chunk.source_id = source_id
        if not chunks:
            return ConversionResult(
                thread_id=thread_id,
                chunks_created=0,
                concepts_extracted=0,
                relationships_extracted=0,
                chunks_cleaned=cleanup.vectors_deleted,
                concepts_cleaned=cleanup.concepts_deleted,
            )

        # Phase 2: Generate embeddings
        chunks = await self._generate_embeddings(chunks)

        # Phase 3: Store vectors
        await self._store_vectors(chunks)

        # Phase 4: Extract and store KG concepts (FATAL on failure)
        concepts_count, relationships_count = await self._extract_and_store_concepts(
            chunks, source_id
        )

        # Phase 5: Persist knowledge_sources row so document listing shows it
        conv_title = title or self._derive_title(conversation)
        await self._persist_knowledge_source(
            thread_id, conv_title, len(chunks)
        )

        # Phase 6: Update knowledge source title if provided
        if title:
            self._conversation_manager.update_conversation_title(thread_id, title)

        result = ConversionResult(
            thread_id=thread_id,
            chunks_created=len(chunks),
            concepts_extracted=concepts_count,
            relationships_extracted=relationships_count,
            chunks_cleaned=cleanup.vectors_deleted,
            concepts_cleaned=cleanup.concepts_deleted,
        )
        logger.info(
            f"Conversation {thread_id} converted: "
            f"{result.chunks_created} chunks, {result.concepts_extracted} concepts, "
            f"{result.relationships_extracted} relationships"
        )
        return result

    # ------------------------------------------------------------------
    # Pipeline stages
    # ------------------------------------------------------------------

    async def _cleanup_existing(self, thread_id: str, source_id: str) -> CleanupResult:
        """Remove existing vectors (by thread_id) and KG nodes (by source_id).

        Also cleans up any legacy KG nodes stored under the raw thread_id.
        """
        vectors_deleted = 0
        try:
            # Delete vectors stored under UUID5 source_id (new format)
            if hasattr(self._vector_store, 'delete_chunks_by_source_async'):
                vectors_deleted = await self._vector_store.delete_chunks_by_source_async(source_id)
            else:
                vectors_deleted = self._vector_store.delete_chunks_by_source(source_id)
            # Also clean up legacy vectors stored under raw thread_id
            if thread_id != source_id:
                if hasattr(self._vector_store, 'delete_chunks_by_source_async'):
                    vectors_deleted += await self._vector_store.delete_chunks_by_source_async(thread_id)
                else:
                    vectors_deleted += self._vector_store.delete_chunks_by_source(thread_id)
            logger.info(f"Cleanup: deleted {vectors_deleted} vectors for thread {thread_id}")
        except Exception as e:
            logger.error(f"Cleanup: vector deletion failed for thread {thread_id}: {e}")
            raise

        concepts_deleted = await self._remove_kg_data(source_id)
        # Also clean up any legacy concepts stored under the raw thread_id
        if thread_id != source_id:
            concepts_deleted += await self._remove_kg_data(thread_id)
        return CleanupResult(
            vectors_deleted=vectors_deleted,
            concepts_deleted=concepts_deleted,
        )

    async def _generate_embeddings(
        self, chunks: List[KnowledgeChunk]
    ) -> List[KnowledgeChunk]:
        """Generate embeddings via model server, assign to chunks.

        Only text content is embedded (no multimedia metadata).
        Raises on failure (fail-fast).
        """
        texts = [chunk.content for chunk in chunks]
        try:
            embeddings = await self._model_client.generate_embeddings(texts)
        except Exception as e:
            logger.error(f"Embedding generation failed: {e}")
            raise

        for chunk, embedding in zip(chunks, embeddings):
            chunk.embedding = embedding

        logger.info(f"Generated embeddings for {len(chunks)} chunks")
        return chunks

    async def _store_vectors(self, chunks: List[KnowledgeChunk]) -> int:
        """Store chunks in vector store.

        Chunks have source_type=CONVERSATION (set by ConversationManager)
        and source_id=UUID5 (overridden in convert_conversation to match
        the knowledge_sources.id).  Raises on failure (fail-fast).

        Uses the async store_embeddings_async path to properly await the
        underlying vector client (Milvus or OpenSearch).
        """
        try:
            if hasattr(self._vector_store, 'store_embeddings_async'):
                await self._vector_store.store_embeddings_async(chunks)
            else:
                self._vector_store.store_embeddings(chunks)
        except Exception as e:
            logger.error(f"Vector storage failed: {e}")
            raise

        logger.info(f"Stored {len(chunks)} chunks in vector store")
        return len(chunks)

    def _derive_title(self, conversation) -> str:
        """Derive a title from conversation content."""
        if conversation.knowledge_summary:
            return conversation.knowledge_summary.strip()[:200]
        for msg in conversation.messages:
            if hasattr(msg, 'message_type'):
                from ..models.core import MessageType
                if msg.message_type == MessageType.USER and msg.content.strip():
                    return msg.content.strip()[:200]
        return f"Conversation {conversation.thread_id[:8]}"

    def _deduplicate_relationships(
        self, relationships: List[RelationshipEdge]
    ) -> List[RelationshipEdge]:
        """Deduplicate relationships, keeping max confidence and merged evidence.

        Mirrors ``KnowledgeGraphBuilder._deduplicate_relationships``: one edge
        per unique (subject, predicate, object) triple.
        """
        unique: Dict[str, RelationshipEdge] = {}

        for rel in relationships:
            key = f"{rel.subject_concept}_{rel.predicate}_{rel.object_concept}"

            if key in unique:
                existing = unique[key]
                existing.confidence = max(existing.confidence, rel.confidence)
                for chunk_id in rel.evidence_chunks:
                    existing.add_evidence_chunk(chunk_id)
            else:
                unique[key] = rel

        return list(unique.values())

    def _extract_source_citations(
        self,
        response_text: str,
        response_concepts: List[ConceptNode],
        chunk_id: str,
    ) -> tuple:
        """Extract source citations from response text.

        Scans *response_text* for citation patterns (e.g. ``Source: X``,
        ``from "X"``).  For each unique citation found, creates a
        ``ConceptNode`` with ``concept_type="CITED_SOURCE"`` and a
        ``CITES`` edge from every *response_concept* to that citation
        concept.

        Returns:
            (citation_concepts, citation_relationships)
        """
        seen_names: set = set()
        citation_concepts: List[ConceptNode] = []
        citation_relationships: List[RelationshipEdge] = []

        for pattern in CITATION_PATTERNS:
            for match in pattern.finditer(response_text):
                name = match.group(1).strip()
                if not name or name in seen_names:
                    continue
                seen_names.add(name)

                concept_id = str(
                    uuid_module.uuid5(uuid_module.NAMESPACE_URL, f"citation:{name}")
                )
                citation_node = ConceptNode(
                    concept_id=concept_id,
                    concept_name=name,
                    concept_type="CITED_SOURCE",
                    confidence=0.8,
                    source_chunks=[chunk_id],
                )
                citation_concepts.append(citation_node)

                # CITES edge from each response concept to the citation
                for resp in response_concepts:
                    edge = RelationshipEdge(
                        subject_concept=resp.concept_name,
                        predicate="CITES",
                        object_concept=name,
                        confidence=min(resp.confidence, 0.8),
                        relationship_type=RelationshipType.ASSOCIATIVE,
                    )
                    citation_relationships.append(edge)

        if citation_concepts:
            logger.info(
                "Citation extraction: found %d citations, "
                "created %d CITES edges",
                len(citation_concepts),
                len(citation_relationships),
            )

        return citation_concepts, citation_relationships

    async def _match_citation_to_existing_source(
        self, citation_name: str
    ) -> Optional[str]:
        """Check if a citation matches an existing knowledge source.

        Performs a case-insensitive lookup against the ``title`` column
        of ``multimodal_librarian.knowledge_sources``.

        Returns:
            The source ``id`` (as a string) if found, ``None`` otherwise.
            Also returns ``None`` if the DB lookup fails (graceful
            degradation — logged as a warning).
        """
        from ..database.connection import get_async_connection

        try:
            conn = await get_async_connection()
            try:
                row = await conn.fetchrow(
                    "SELECT id FROM multimodal_librarian.knowledge_sources "
                    "WHERE LOWER(title) = LOWER($1) LIMIT 1",
                    citation_name,
                )
                if row:
                    return str(row["id"])
                return None
            finally:
                await conn.close()
        except Exception:
            logger.warning(
                "Citation-to-source lookup failed for '%s'",
                citation_name,
                exc_info=True,
            )
            return None

    async def _extract_concepts_segment_aware(
        self, chunk: KnowledgeChunk
    ) -> tuple:
        """Extract concepts separately from prompt and response segments.

        If the chunk carries segment metadata (populated by
        ``convert_to_knowledge_chunks``), concepts are extracted per-role
        and PROMPTED_BY edges link every response concept back to every
        prompt concept within the same chunk.

        For legacy chunks without segment metadata the method falls back
        to full-content extraction with no PROMPTED_BY edges.

        Returns:
            (all_concepts, prompted_by_edges, response_concepts)
            *response_concepts* is the subset extracted from assistant
            segments (empty list for legacy chunks).
        """
        segments = []
        if chunk.knowledge_metadata is not None:
            segments = chunk.knowledge_metadata.segments or []

        # Legacy / no-segment path
        if not segments:
            concepts, _ner_failed, _llm_failed = (
                await self._concept_extractor.extract_all_concepts_async(
                    chunk.content
                )
            )
            return concepts, [], []

        prompt_concepts: List[ConceptNode] = []
        response_concepts: List[ConceptNode] = []

        for seg in segments:
            role = seg.get("role", "")
            content = seg.get("content", "")
            if not content:
                continue

            extracted, _ner_failed, _llm_failed = (
                await self._concept_extractor.extract_all_concepts_async(
                    content
                )
            )
            if role == "user":
                prompt_concepts.extend(extracted)
            else:
                response_concepts.extend(extracted)

        # Build PROMPTED_BY edges: each response concept → each prompt concept
        prompted_by_edges: List[RelationshipEdge] = []
        if prompt_concepts and response_concepts:
            for resp_concept in response_concepts:
                for prompt_concept in prompt_concepts:
                    edge = RelationshipEdge(
                        subject_concept=resp_concept.concept_name,
                        predicate="PROMPTED_BY",
                        object_concept=prompt_concept.concept_name,
                        confidence=min(
                            resp_concept.confidence,
                            prompt_concept.confidence,
                        ),
                        relationship_type=RelationshipType.ASSOCIATIVE,
                    )
                    prompted_by_edges.append(edge)

        all_concepts = prompt_concepts + response_concepts
        logger.info(
            "Segment-aware extraction: %d prompt concepts, "
            "%d response concepts, %d PROMPTED_BY edges",
            len(prompt_concepts),
            len(response_concepts),
            len(prompted_by_edges),
        )
        return all_concepts, prompted_by_edges, response_concepts

    async def _persist_knowledge_source(
        self, thread_id: str, title: str, chunk_count: int
    ) -> None:
        """Insert a knowledge_sources row so the document listing shows it.

        Uses UPSERT (ON CONFLICT) for idempotent re-ingestion.
        """
        from ..database.connection import get_async_connection

        try:
            conn = await get_async_connection()
            try:
                # Get a valid user_id from existing users
                user_row = await conn.fetchrow(
                    "SELECT id FROM multimodal_librarian.users LIMIT 1"
                )
                if not user_row:
                    # Create a default user
                    default_uid = uuid_module.uuid4()
                    await conn.execute("""
                        INSERT INTO multimodal_librarian.users
                            (id, username, email, password_hash)
                        VALUES ($1, 'chat_user',
                                'chat@multimodal-librarian.local',
                                'not_for_login')
                        ON CONFLICT (username) DO NOTHING
                    """, default_uid)
                    user_row = await conn.fetchrow(
                        "SELECT id FROM multimodal_librarian.users "
                        "WHERE username = 'chat_user'"
                    )
                    if not user_row:
                        user_row = {'id': default_uid}

                user_uuid = user_row['id']
                source_id = uuid_module.uuid5(
                    uuid_module.NAMESPACE_URL, thread_id
                )
                now = datetime.utcnow()
                metadata = json.dumps({
                    'chunk_count': chunk_count,
                    'source_thread_id': thread_id,
                })

                await conn.execute(
                    """
                    INSERT INTO multimodal_librarian.knowledge_sources (
                        id, user_id, title, file_path, file_size,
                        processing_status, metadata, source_type,
                        created_at, updated_at
                    ) VALUES (
                        $1::uuid, $2::uuid, $3, $4, 0,
                        'COMPLETED'::multimodal_librarian.processing_status,
                        $5::jsonb,
                        'CONVERSATION'::multimodal_librarian.source_type,
                        $6, $7
                    )
                    ON CONFLICT (id) DO UPDATE SET
                        title = EXCLUDED.title,
                        processing_status = EXCLUDED.processing_status,
                        metadata = EXCLUDED.metadata,
                        updated_at = EXCLUDED.updated_at
                    """,
                    source_id,
                    user_uuid,
                    title,
                    f"conversation://{thread_id}",
                    metadata,
                    now,
                    now,
                )
                logger.info(
                    f"Persisted knowledge_source {source_id} "
                    f"for conversation {thread_id}"
                )
            finally:
                await conn.close()
        except Exception as e:
            logger.warning(
                f"Failed to persist knowledge_source for "
                f"conversation {thread_id}: {e}"
            )

    async def _extract_and_store_concepts(
        self, chunks: List[KnowledgeChunk], thread_id: str
    ) -> tuple:
        """Extract concepts from chunks and persist to Neo4j.

        KG failure is FATAL — raises on any error.

        Returns:
            (total_concepts, total_relationships) counts.
        """
        total_concepts = 0
        total_relationships = 0
        now_ts = datetime.utcnow().isoformat()

        for chunk in chunks:
            # Segment-aware concept extraction: extracts concepts
            # separately from user prompt and assistant response
            # segments, creating PROMPTED_BY edges between them.
            concepts, prompted_by_edges, resp_concepts = (
                await self._extract_concepts_segment_aware(chunk)
            )

            # ConceptNet validation gate: filter concepts and collect
            # ConceptNet-sourced relationships when the validator is available.
            conceptnet_relationships: List[RelationshipEdge] = []
            if self._conceptnet_validator is not None:
                try:
                    validation_result = (
                        await self._conceptnet_validator.validate_concepts(concepts)
                    )
                    concepts = validation_result.validated_concepts
                    conceptnet_relationships = validation_result.conceptnet_relationships
                    logger.info(
                        "ConceptNet validation: kept %d concepts, "
                        "discarded %d, found %d ConceptNet relationships",
                        len(concepts),
                        validation_result.discarded_count,
                        len(conceptnet_relationships),
                    )
                except Exception:
                    logger.warning(
                        "ConceptNet validation failed, using raw concepts",
                        exc_info=True,
                    )

            # Set source_document on all concepts
            for concept in concepts:
                concept.source_document = thread_id
                concept.add_source_chunk(chunk.id)

            # Extract relationships between concepts
            relationships: List[RelationshipEdge] = (
                self._relationship_extractor.extract_relationships_pattern(
                    chunk.content, concepts
                )
            )

            # Embedding-based relationship extraction
            # (SIMILAR_TO edges via cosine similarity > 0.6)
            if (
                self._model_client is not None
                and len(concepts) >= 2
            ):
                try:
                    extractor = self._relationship_extractor
                    embedding_rels: List[RelationshipEdge] = (
                        await extractor
                        .extract_relationships_embedding_async(
                            concepts, self._model_client
                        )
                    )
                    relationships.extend(embedding_rels)
                    logger.info(
                        "Embedding extraction: found %d "
                        "SIMILAR_TO relationships",
                        len(embedding_rels),
                    )
                except Exception:
                    logger.warning(
                        "Embedding relationship extraction failed, skipping",
                        exc_info=True,
                    )

            # Combine pattern, embedding, and ConceptNet relationships
            relationships.extend(conceptnet_relationships)

            # Merge PROMPTED_BY edges from segment-aware extraction
            relationships.extend(prompted_by_edges)

            # Extract source citations from response segments
            segments = []
            if chunk.knowledge_metadata is not None:
                segments = chunk.knowledge_metadata.segments or []
            response_segments = [
                s for s in segments
                if s.get("role") == "assistant" and s.get("content")
            ]
            # Use response concepts from segment-aware extraction;
            # fall back to all concepts for legacy chunks.
            resp_concepts_for_cite = (
                resp_concepts if resp_concepts else list(concepts)
            )

            for seg in response_segments:
                cite_concepts, cite_rels = self._extract_source_citations(
                    seg["content"], resp_concepts_for_cite, chunk.id,
                )
                # For each citation, check if it matches an existing source
                for cite_node in cite_concepts:
                    source_id = await self._match_citation_to_existing_source(
                        cite_node.concept_name
                    )
                    if source_id:
                        derived_edge = RelationshipEdge(
                            subject_concept=cite_node.concept_name,
                            predicate="DERIVED_FROM",
                            object_concept=source_id,
                            confidence=cite_node.confidence,
                            relationship_type=RelationshipType.ASSOCIATIVE,
                        )
                        cite_rels.append(derived_edge)
                    cite_node.source_document = thread_id

                concepts.extend(cite_concepts)
                relationships.extend(cite_rels)

            # Ensure every relationship carries evidence for this chunk
            for rel in relationships:
                rel.add_evidence_chunk(chunk.id)

            # Deduplicate: one edge per (subject, predicate, object),
            # max confidence, merged evidence chunks.
            relationships = self._deduplicate_relationships(relationships)

            # Calculate overall confidence score (arithmetic mean of all
            # concept + relationship confidences) for observability.
            all_confidences = (
                [c.confidence for c in concepts]
                + [r.confidence for r in relationships]
            )
            overall_confidence = (
                sum(all_confidences) / len(all_confidences)
                if all_confidences
                else 0.0
            )
            logger.info(
                "Chunk %s extraction confidence: %.3f "
                "(%d concepts, %d relationships)",
                chunk.id,
                overall_confidence,
                len(concepts),
                len(relationships),
            )

            # Persist concepts to Neo4j
            if concepts:
                concept_id_map = await self._persist_concepts(
                    concepts, thread_id, now_ts
                )
                total_concepts += len(concept_id_map)

                # Persist relationships to Neo4j
                if relationships:
                    rels_persisted = await self._persist_relationships(
                        relationships, concept_id_map, thread_id, now_ts
                    )
                    total_relationships += rels_persisted

        return total_concepts, total_relationships

    # ------------------------------------------------------------------
    # Neo4j helpers
    # ------------------------------------------------------------------

    async def _remove_kg_data(self, source_id: str) -> int:
        """Delete Chunk nodes, EXTRACTED_FROM relationships, and orphaned
        Concepts for *source_id* from Neo4j using the three-step
        Chunk-based deletion pattern.

        Also cleans up any legacy concepts that may have been stored
        under the raw thread_id instead of the UUID5 source_id.
        """
        if not self._neo4j_client:
            logger.warning("No Neo4j client available, skipping KG cleanup")
            return 0

        try:
            # Step 1: Delete EXTRACTED_FROM relationships to this source's Chunk nodes
            result_rels = await self._neo4j_client.execute_write_query(
                """
                MATCH (ch:Chunk {source_id: $source_id})<-[r:EXTRACTED_FROM]-(c:Concept)
                DELETE r
                RETURN count(r) AS deleted_rels
                """,
                {"source_id": source_id},
            )
            deleted_rels = result_rels[0]["deleted_rels"] if result_rels else 0

            # Step 2: Delete Chunk nodes for this source_id
            result_chunks = await self._neo4j_client.execute_write_query(
                """
                MATCH (ch:Chunk {source_id: $source_id})
                DELETE ch
                RETURN count(ch) AS deleted_chunks
                """,
                {"source_id": source_id},
            )
            deleted_chunks = result_chunks[0]["deleted_chunks"] if result_chunks else 0

            # Step 3: Delete orphaned Concepts (no remaining EXTRACTED_FROM and no SAME_AS)
            result_concepts = await self._neo4j_client.execute_write_query(
                """
                MATCH (c:Concept)
                WHERE NOT EXISTS { MATCH (c)-[:EXTRACTED_FROM]->() }
                  AND NOT EXISTS { MATCH (c)<-[:SAME_AS]-() }
                DETACH DELETE c
                RETURN count(c) AS deleted_concepts
                """,
                {},
            )
            deleted_concepts = result_concepts[0]["deleted_concepts"] if result_concepts else 0

            logger.info(
                f"Cleanup: KG deletion for source {source_id}: "
                f"{deleted_rels} EXTRACTED_FROM rels, "
                f"{deleted_chunks} Chunk nodes, "
                f"{deleted_concepts} orphaned Concepts"
            )
            return deleted_concepts
        except Exception as e:
            logger.error(f"Cleanup: KG deletion failed for source {source_id}: {e}")
            raise

    async def _persist_concepts(
        self,
        concepts: List[ConceptNode],
        thread_id: str,
        now_ts: str,
    ) -> Dict[str, str]:
        """MERGE concept nodes into Neo4j.

        Returns {concept_id: neo4j_element_id}.

        Uses graph-native Chunk nodes and EXTRACTED_FROM relationships
        instead of source_chunks/source_document properties on
        Concept nodes.
        """
        # Generate embeddings for concept names
        concept_names = [c.concept_name for c in concepts]
        concept_embeddings: List[Optional[List[float]]] = [
            None
        ] * len(concepts)
        try:
            embeddings = (
                await self._model_client.generate_embeddings(
                    concept_names
                )
            )
            if (
                embeddings
                and len(embeddings) == len(concept_names)
            ):
                concept_embeddings = embeddings
            else:
                logger.warning(
                    "Embedding count mismatch for concepts: "
                    "got %d for %d names",
                    len(embeddings) if embeddings else 0,
                    len(concept_names),
                )
        except Exception as e:
            logger.warning(
                "Failed to generate concept embeddings: %s",
                e,
            )

        # --- Step 1: MERGE Chunk nodes ---
        chunk_rows = []
        seen_chunk_ids: set = set()
        for c in concepts:
            for chunk_id in (c.source_chunks or []):
                if chunk_id and chunk_id not in seen_chunk_ids:
                    seen_chunk_ids.add(chunk_id)
                    chunk_rows.append({
                        "chunk_id": chunk_id,
                        "source_id": thread_id,
                        "created_at": now_ts,
                    })

        if chunk_rows:
            try:
                await self._neo4j_client.execute_write_query(
                    """
                    UNWIND $rows AS row
                    MERGE (ch:Chunk {chunk_id: row.chunk_id})
                    ON CREATE SET
                        ch.source_id = row.source_id,
                        ch.created_at = row.created_at
                    RETURN ch.chunk_id AS chunk_id
                    """,
                    {"rows": chunk_rows},
                )
            except Exception as e:
                logger.warning("Chunk MERGE failed: %s", e)

        # --- Step 2: MERGE Concept nodes ---
        # No source_chunks/source_document properties written.
        rows = [
            {
                "concept_id": c.concept_id,
                "name": c.concept_name,
                "type": c.concept_type,
                "confidence": c.confidence,
                "created_at": now_ts,
                "updated_at": now_ts,
                "embedding": emb,
            }
            for c, emb in zip(concepts, concept_embeddings)
        ]

        logger.info(
            "Persisting %d concepts to Neo4j "
            "(client type: %s, connected: %s, "
            "thread_id: %s)",
            len(rows),
            type(self._neo4j_client).__name__,
            getattr(
                self._neo4j_client, '_is_connected', 'N/A'
            ),
            thread_id,
        )

        result = await self._neo4j_client.execute_write_query(
            """
            UNWIND $rows AS row
            MERGE (c:Concept {concept_id: row.concept_id})
            ON CREATE SET c.name = row.name,
                          c.type = row.type,
                          c.concept_type = row.type,
                          c.confidence = row.confidence,
                          c.name_lower = toLower(row.name),
                          c.created_at = row.created_at,
                          c.updated_at = row.updated_at,
                          c.embedding = row.embedding
            ON MATCH SET c.updated_at = row.updated_at,
                         c.concept_type = CASE WHEN c.concept_type IS NULL
                                          THEN row.type
                                          ELSE c.concept_type END,
                         c.embedding = CASE
                           WHEN row.embedding IS NOT NULL
                           THEN row.embedding
                           ELSE c.embedding
                         END
            RETURN c.concept_id AS concept_id,
                   elementId(c) AS node_id
            """,
            {"rows": rows},
        )

        logger.info(
            "Neo4j MERGE returned %d records",
            len(result) if result else 0,
        )

        concept_id_map: Dict[str, str] = {}
        for rec in result or []:
            concept_id_map[rec["concept_id"]] = rec["node_id"]

        # --- Step 3: MERGE EXTRACTED_FROM relationships ---
        ef_rows = []
        for c in concepts:
            if c.concept_id not in concept_id_map:
                continue
            for chunk_id in (c.source_chunks or []):
                if chunk_id:
                    ef_rows.append({
                        "concept_id": c.concept_id,
                        "chunk_id": chunk_id,
                        "created_at": now_ts,
                    })

        if ef_rows:
            try:
                await self._neo4j_client.execute_write_query(
                    """
                    UNWIND $rows AS row
                    MATCH (c:Concept {
                        concept_id: row.concept_id
                    })
                    MATCH (ch:Chunk {
                        chunk_id: row.chunk_id
                    })
                    MERGE (c)-[r:EXTRACTED_FROM]->(ch)
                    ON CREATE SET
                        r.created_at = row.created_at
                    RETURN count(r) AS cnt
                    """,
                    {"rows": ef_rows},
                )
            except Exception as e:
                logger.warning(
                    "EXTRACTED_FROM MERGE failed: %s", e
                )

        # Verification read
        try:
            verify = await self._neo4j_client.execute_query(
                "MATCH (ch:Chunk {source_id: $sid})"
                "<-[:EXTRACTED_FROM]-(c:Concept) "
                "RETURN count(DISTINCT c) AS cnt",
                {"sid": thread_id},
            )
            logger.info(
                "VERIFY: concepts linked to Chunks "
                "with source_id=%s: %s",
                thread_id,
                verify,
            )
        except Exception as ve:
            logger.warning(
                "Verification read failed: %s", ve
            )

        logger.info(
            "Persisted %d concepts, "
            "concept_id_map has %d entries",
            len(rows),
            len(concept_id_map),
        )

        return concept_id_map

    async def _persist_relationships(
        self,
        relationships: List[RelationshipEdge],
        concept_id_map: Dict[str, str],
        thread_id: str,
        now_ts: str,
    ) -> int:
        """MERGE relationship edges into Neo4j. Returns count persisted."""
        # Group by sanitised relationship type (Neo4j requires static rel types)
        rels_by_type: Dict[str, list] = {}
        for rel in relationships:
            from_id = concept_id_map.get(rel.subject_concept)
            to_id = concept_id_map.get(rel.object_concept)
            if from_id and to_id:
                sanitized = re.sub(r"[^A-Za-z0-9_]", "_", rel.predicate)
                rels_by_type.setdefault(sanitized, []).append(
                    {
                        "from_id": str(from_id),
                        "to_id": str(to_id),
                        "confidence": rel.confidence,
                        "evidence_chunks": (
                            ",".join(rel.evidence_chunks) if rel.evidence_chunks else ""
                        ),
                        "source_document": thread_id,
                        "created_at": now_ts,
                    }
                )

        total = 0
        for rel_type, rel_rows in rels_by_type.items():
            try:
                result = await self._neo4j_client.execute_write_query(
                    f"""
                    UNWIND $rows AS row
                    MATCH (a) WHERE elementId(a) = row.from_id
                    MATCH (b) WHERE elementId(b) = row.to_id
                    MERGE (a)-[r:{rel_type}]->(b)
                    ON CREATE SET r.confidence = row.confidence,
                                  r.evidence_chunks = row.evidence_chunks,
                                  r.source_document = row.source_document,
                                  r.created_at = row.created_at
                    ON MATCH SET r.confidence = row.confidence
                    RETURN count(r) AS cnt
                    """,
                    {"rows": rel_rows},
                )
                cnt = result[0]["cnt"] if result else 0
                total += cnt
            except Exception as e:
                logger.error(f"Relationship MERGE ({rel_type}) failed: {e}")
                raise

        return total
