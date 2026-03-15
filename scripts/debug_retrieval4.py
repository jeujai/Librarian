#!/usr/bin/env python3
"""Debug script to trace the Chelsea query through the KG retrieval pipeline.
Properly initializes model server client for semantic matching."""

import asyncio
import logging
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

logging.basicConfig(level=logging.INFO, format='%(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

for name in ['neo4j', 'httpx', 'httpcore', 'urllib3', 'asyncio',
             'multimodal_librarian.config', 'multimodal_librarian.logging',
             'multimodal_librarian.monitoring']:
    logging.getLogger(name).setLevel(logging.WARNING)


async def main():
    from multimodal_librarian.clients.database_factory import get_database_factory
    from multimodal_librarian.clients.model_server_client import (
        get_model_client,
        initialize_model_client,
    )

    factory = get_database_factory()
    neo4j_client = factory.get_graph_client()
    milvus_client = factory.get_vector_client()

    # Properly initialize model server client (async)
    await initialize_model_client()
    model_client = get_model_client()

    await neo4j_client.connect()
    await milvus_client.connect()

    query = "What did our team observe at Chelsea?"
    target_chunk = "31154efa-5bad-4b94-befa-ebf7cee956a3"

    print(f"\n{'='*60}")
    print(f"Query: {query}")
    print(f"Target chunk: {target_chunk}")
    print(f"Model client available: {model_client is not None}")
    if model_client:
        print(f"Model client enabled: {model_client.enabled}")
    print(f"{'='*60}\n")

    # Step 1: QueryDecomposer
    from multimodal_librarian.components.kg_retrieval.query_decomposer import (
        QueryDecomposer,
    )
    decomposer = QueryDecomposer(neo4j_client=neo4j_client, model_server_client=model_client)
    decomposition = await decomposer.decompose(query)

    print(f"--- QueryDecomposer Results ---")
    print(f"has_kg_matches: {decomposition.has_kg_matches}")
    print(f"concept_matches ({len(decomposition.concept_matches)}):")
    for m in decomposition.concept_matches:
        print(f"  - {m.get('name')} (id={m.get('concept_id')}, "
              f"type={m.get('match_type')}, "
              f"sim={m.get('similarity_score', 'N/A'):.3f}" if isinstance(m.get('similarity_score'), (int, float)) else
              f"  - {m.get('name')} (id={m.get('concept_id')}, "
              f"type={m.get('match_type')}, "
              f"sim={m.get('similarity_score', 'N/A')}, "
              f"match_score={m.get('match_score', 'N/A')})")

    # Step 2: Full KG retrieval with model client
    from multimodal_librarian.services.kg_retrieval_service import KGRetrievalService
    kg_service = KGRetrievalService(
        neo4j_client=neo4j_client,
        vector_client=milvus_client,
        model_client=model_client,
    )

    result = await kg_service.retrieve(
        query, top_k=15, precomputed_decomposition=decomposition
    )

    print(f"\n--- Full KG Retrieval Result ---")
    print(f"Total chunks: {len(result.chunks)}")
    print(f"Fallback used: {result.fallback_used}")
    print(f"Stage 1 count: {result.stage1_chunk_count}")
    print(f"Stage 2 count: {result.stage2_chunk_count}")

    target_in_results = False
    for i, chunk in enumerate(result.chunks):
        is_target = chunk.chunk_id == target_chunk
        if is_target:
            target_in_results = True
        marker = " <<<< TARGET" if is_target else ""
        print(f"  [{i+1:2d}] chunk={chunk.chunk_id[:12]}... "
              f"kg={chunk.kg_relevance_score:.3f} "
              f"sem={chunk.semantic_score:.3f} "
              f"final={chunk.final_score:.3f} "
              f"concept={chunk.concept_name}{marker}")

    if not target_in_results:
        print(f"\n  *** TARGET CHUNK NOT IN FINAL RESULTS ***")
        # Check if it was in stage 1
        direct_ids, direct_mappings = await kg_service._retrieve_direct_chunks(
            decomposition.concept_matches
        )
        print(f"  Target in direct chunks: {target_chunk in direct_ids}")

    # Step 3: Check what _convert_kg_results produces (simulating RAG service)
    print(f"\n--- Simulated RAG Service Check ---")
    print(f"relevance_confidence_threshold = 0.5")
    if result.chunks:
        best_score = max(c.final_score for c in result.chunks)
        print(f"Best final_score from KG: {best_score:.3f}")
        print(f"Would pass threshold: {best_score >= 0.5}")
        target_chunks = [c for c in result.chunks if c.chunk_id == target_chunk]
        if target_chunks:
            tc = target_chunks[0]
            print(f"Target chunk final_score: {tc.final_score:.3f}")
            print(f"Target chunk position: {[c.chunk_id for c in result.chunks].index(target_chunk) + 1}")

    await neo4j_client.close()


if __name__ == '__main__':
    asyncio.run(main())
