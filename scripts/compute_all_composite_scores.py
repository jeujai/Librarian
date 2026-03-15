#!/usr/bin/env python3
"""One-off script to compute composite scores for all existing documents.

Run inside the Docker container:
    docker exec librarian-app-1 python /app/scripts/compute_all_composite_scores.py
"""
import asyncio
import os
import sys

# Ensure the app source is on the path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))


async def main():
    from multimodal_librarian.clients.database_factory import get_database_factory
    from multimodal_librarian.services.composite_score_engine import (
        CompositeScoreEngine,
    )

    factory = get_database_factory()
    client = factory.get_graph_client()

    if not getattr(client, '_is_connected', False):
        await client.connect()

    # Get all distinct document IDs via Chunk traversal
    results = await client.execute_query(
        "MATCH (c:Concept)-[:EXTRACTED_FROM]->(ch:Chunk) "
        "WHERE ch.source_id <> 'conceptnet' "
        "RETURN DISTINCT ch.source_id AS doc_id"
    )
    doc_ids = [r['doc_id'] for r in results if r.get('doc_id')]
    print(f"Found {len(doc_ids)} documents to process")

    engine = CompositeScoreEngine(client)

    for i, doc_id in enumerate(doc_ids, 1):
        try:
            result = await engine.compute_composite_scores(doc_id)
            print(
                f"[{i}/{len(doc_ids)}] {doc_id}: "
                f"{result.edges_discovered} edges, "
                f"{result.document_pairs} pairs, "
                f"{result.related_docs_created} RELATED_DOCS, "
                f"{result.duration_ms:.0f}ms"
            )
        except Exception as exc:
            print(f"[{i}/{len(doc_ids)}] {doc_id}: ERROR - {exc}")

    # Verify
    count_result = await client.execute_query(
        "MATCH ()-[r:RELATED_DOCS]->() RETURN count(r) AS cnt"
    )
    total = count_result[0]['cnt'] if count_result else 0
    print(f"\nDone. Total RELATED_DOCS edges in Neo4j: {total}")


if __name__ == '__main__':
    asyncio.run(main())
