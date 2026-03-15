"""Debug: show concept hits per chunk to understand kg_relevance scoring."""
import asyncio
import logging
import math
import sys

sys.path.insert(0, "/app/src")
logging.basicConfig(level=logging.WARNING)


async def main():
    from multimodal_librarian.clients.milvus_client import MilvusClient
    from multimodal_librarian.clients.model_server_client import ModelServerClient
    from multimodal_librarian.clients.neo4j_client import Neo4jClient
    from multimodal_librarian.services.kg_retrieval_service import KGRetrievalService

    neo4j = Neo4jClient(uri="bolt://neo4j:7687", user="neo4j", password="password")
    await neo4j.connect()
    model = ModelServerClient()
    milvus = MilvusClient(host="milvus", port=19530)
    await milvus.connect()

    svc = KGRetrievalService(
        neo4j_client=neo4j, vector_client=milvus, model_client=model,
    )
    query = "What did our team observe at Chelsea?"

    # Decompose
    decomp = await svc._decompose_query_safe(query)
    # Get direct chunks with concept hits
    direct_ids, direct_mappings, chunk_concept_hits = (
        await svc._retrieve_direct_chunks(decomp.concept_matches)
    )

    # Resolve to get content
    all_resolved = await svc._chunk_resolver.resolve_chunks(
        list(direct_ids), direct_mappings
    )
    id_to_chunk = {c.chunk_id: c for c in all_resolved}

    print(f"Direct chunks: {len(direct_ids)}")
    print(f"\nChunks with concept hits (sorted by kg_relevance):")
    rows = []
    for cid, hits in chunk_concept_hits.items():
        norm_scores = [min(1.0, max(0.1, h["match_score"] / 10.0)) for h in hits]
        base = max(norm_scores)
        bonus = math.log2(max(1, len(hits))) * 0.1
        kg_rel = min(1.0, base + bonus)
        ch = id_to_chunk.get(cid)
        title = "?"
        has_chelsea = False
        if ch:
            title = (ch.metadata or {}).get('title',
                     (ch.metadata or {}).get('document_title', '?'))[:50]
            has_chelsea = "chelsea" in (ch.content or "").lower()
        concepts = [f"{h['concept_name']}({h['match_score']:.1f})" for h in hits]
        rows.append((kg_rel, base, bonus, len(hits), has_chelsea, title, concepts))

    rows.sort(key=lambda r: r[0], reverse=True)
    for kg, base, bonus, n, chel, title, concepts in rows[:20]:
        print(f"  kg={kg:.4f} base={base:.4f} bonus={bonus:.4f} "
              f"n_concepts={n} chelsea={chel} title={title}")
        print(f"    concepts: {concepts}")

    await neo4j.close()

asyncio.run(main())
