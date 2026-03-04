#!/usr/bin/env python3
"""
Rebuild Neo4j knowledge graph from chunks already stored in Milvus.

This script reads all chunks from Milvus for a given document and runs
the KG extraction pipeline to populate Neo4j with concepts and relationships
that reference the correct chunk UUIDs.
"""

import asyncio
import logging
import sys
import time
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
logger = logging.getLogger(__name__)

DOCUMENT_ID = "eeac6fa2-249a-4d9d-8c00-ba21b89ace69"


async def get_chunks_from_milvus(document_id: str):
    """Read all chunks for a document from Milvus."""
    from pymilvus import Collection, connections

    connections.connect('default', host='localhost', port='19530')
    collection = Collection('document_chunks')
    collection.load()

    # Query all chunks for this document
    # Milvus doesn't support string CONTAINS easily, so get all and filter
    all_results = collection.query(
        expr='id != ""',
        output_fields=['id', 'metadata'],
        limit=2000
    )

    chunks = []
    for r in all_results:
        meta = r.get('metadata', {})
        source_id = meta.get('source_id', '')
        if source_id == document_id:
            chunks.append({
                'id': r['id'],
                'content': meta.get('content', ''),
                'chunk_index': meta.get('chunk_index', 0),
                'chunk_type': meta.get('chunk_type', 'text'),
                'metadata': meta
            })

    connections.disconnect('default')
    logger.info(f"Retrieved {len(chunks)} chunks from Milvus for document {document_id}")
    return chunks


async def rebuild_kg(document_id: str, chunks: list):
    """Run KG extraction on chunks and persist to Neo4j."""
    from src.multimodal_librarian.clients.neo4j_client import Neo4jClient
    from src.multimodal_librarian.components.knowledge_graph.kg_builder import (
        KnowledgeGraphBuilder,
    )
    from src.multimodal_librarian.models.core import (
        ContentType,
        KnowledgeChunk,
        SourceType,
    )

    kg_builder = KnowledgeGraphBuilder()

    # Connect directly to Neo4j
    neo4j_client = Neo4jClient(
        uri="bolt://localhost:7687",
        user="neo4j",
        password="password",
        database="neo4j"
    )
    await neo4j_client.connect()
    logger.info("Connected to Neo4j")

    # Create fulltext index for concept search
    try:
        await neo4j_client.execute_query(
            "CREATE FULLTEXT INDEX concept_name_fulltext IF NOT EXISTS "
            "FOR (c:Concept) ON EACH [c.name]",
            {}
        )
        logger.info("Fulltext index created/verified")
    except Exception as e:
        logger.warning(f"Fulltext index creation: {e}")

    # Convert chunks to KnowledgeChunk objects
    knowledge_chunks = []
    for chunk in chunks:
        try:
            content_type = ContentType(chunk.get('chunk_type', 'general'))
        except ValueError:
            content_type = ContentType.GENERAL

        kc = KnowledgeChunk(
            id=chunk['id'],  # Use the SAME UUID as in Milvus
            content=chunk['content'],
            source_type=SourceType.BOOK,
            source_id=document_id,
            location_reference=str(chunk.get('chunk_index', 0)),
            section=chunk.get('metadata', {}).get('section', ''),
            content_type=content_type
        )
        knowledge_chunks.append(kc)

    logger.info(f"Processing {len(knowledge_chunks)} chunks for KG extraction")

    # Process in batches
    BATCH_SIZE = 50
    MAX_CONCURRENT = 10
    all_concepts = []
    all_relationships = []

    start_time = time.time()

    for batch_start in range(0, len(knowledge_chunks), BATCH_SIZE):
        batch_end = min(batch_start + BATCH_SIZE, len(knowledge_chunks))
        batch = knowledge_chunks[batch_start:batch_end]

        semaphore = asyncio.Semaphore(MAX_CONCURRENT)

        async def process_chunk(chunk):
            async with semaphore:
                return await kg_builder.process_knowledge_chunk_async(chunk)

        tasks = [process_chunk(c) for c in batch]
        extractions = await asyncio.gather(*tasks, return_exceptions=True)

        for i, extraction in enumerate(extractions):
            if isinstance(extraction, Exception):
                logger.warning(f"KG extraction failed for chunk {batch_start + i}: {extraction}")
                continue
            all_concepts.extend(extraction.extracted_concepts)
            all_relationships.extend(extraction.extracted_relationships)

        elapsed = time.time() - start_time
        logger.info(
            f"Batch {batch_start // BATCH_SIZE + 1}: "
            f"processed {batch_end}/{len(knowledge_chunks)} chunks "
            f"({elapsed:.0f}s elapsed, "
            f"{len(all_concepts)} concepts, {len(all_relationships)} relationships)"
        )

    # Generate embeddings for concepts
    concept_embeddings = {}
    try:
        from src.multimodal_librarian.clients.model_server_client import (
            get_model_client,
            initialize_model_client,
        )

        model_client = get_model_client()
        if model_client is None:
            model_client = await initialize_model_client()

        if model_client and model_client.enabled:
            concept_names = [c.concept_name for c in all_concepts]
            # Batch embeddings
            EMBED_BATCH = 100
            all_embeddings = []
            for i in range(0, len(concept_names), EMBED_BATCH):
                batch_names = concept_names[i:i + EMBED_BATCH]
                embeddings = await model_client.generate_embeddings(batch_names)
                if embeddings:
                    all_embeddings.extend(embeddings)
                else:
                    all_embeddings.extend([None] * len(batch_names))

            if len(all_embeddings) == len(concept_names):
                for concept, embedding in zip(all_concepts, all_embeddings):
                    if embedding is not None:
                        concept_embeddings[concept.concept_id] = embedding
                logger.info(f"Generated embeddings for {len(concept_embeddings)} concepts")
    except Exception as e:
        logger.warning(f"Failed to generate concept embeddings: {e}")

    # Persist to Neo4j
    logger.info(f"Persisting {len(all_concepts)} concepts and {len(all_relationships)} relationships to Neo4j...")

    concept_count = 0
    for concept in all_concepts:
        try:
            properties = {
                'concept_id': concept.concept_id,
                'name': concept.concept_name,
                'type': concept.concept_type,
                'confidence': concept.confidence,
                'source_document': document_id,
                'source_chunks': ','.join(concept.source_chunks) if concept.source_chunks else ''
            }
            embedding = concept_embeddings.get(concept.concept_id)

            if embedding is not None:
                properties['has_embedding'] = True
                await neo4j_client.execute_query(
                    """
                    MERGE (c:Concept {concept_id: $props.concept_id})
                    SET c += $props, c.embedding = $embedding
                    """,
                    {'props': properties, 'embedding': list(embedding) if hasattr(embedding, 'tolist') else embedding}
                )
            else:
                properties['has_embedding'] = False
                await neo4j_client.execute_query(
                    """
                    MERGE (c:Concept {concept_id: $props.concept_id})
                    SET c += $props
                    """,
                    {'props': properties}
                )
            concept_count += 1
        except Exception as e:
            logger.warning(f"Failed to persist concept {concept.concept_name}: {e}")

    # Persist relationships
    rel_count = 0
    for rel in all_relationships:
        try:
            await neo4j_client.execute_query(
                f"""
                MATCH (a:Concept {{concept_id: $subject_id}})
                MATCH (b:Concept {{concept_id: $object_id}})
                MERGE (a)-[r:{rel.predicate}]->(b)
                SET r.confidence = $confidence,
                    r.evidence_chunks = $evidence
                """,
                {
                    'subject_id': rel.subject_concept,
                    'object_id': rel.object_concept,
                    'confidence': rel.confidence,
                    'evidence': ','.join(rel.evidence_chunks) if rel.evidence_chunks else ''
                }
            )
            rel_count += 1
        except Exception as e:
            if 'not found' not in str(e).lower():
                logger.warning(f"Failed to persist relationship: {e}")

    elapsed = time.time() - start_time
    logger.info(f"KG rebuild complete in {elapsed:.0f}s: {concept_count} concepts, {rel_count} relationships")

    # Verify Chelsea concepts
    try:
        results = await neo4j_client.execute_query(
            "MATCH (c:Concept) WHERE toLower(c.name) CONTAINS 'chelsea' "
            "RETURN c.name as name, c.source_chunks as sc",
            {}
        )
        if results:
            logger.info(f"Chelsea concepts found: {len(results)}")
            for r in results:
                logger.info(f"  {r['name']}: source_chunks={r['sc']}")
        else:
            logger.warning("No Chelsea concepts found after rebuild!")
    except Exception as e:
        logger.warning(f"Chelsea verification failed: {e}")


async def main():
    logger.info("=" * 60)
    logger.info("REBUILDING KNOWLEDGE GRAPH FROM MILVUS")
    logger.info("=" * 60)

    chunks = await get_chunks_from_milvus(DOCUMENT_ID)
    if not chunks:
        logger.error("No chunks found in Milvus!")
        return 1

    await rebuild_kg(DOCUMENT_ID, chunks)
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
