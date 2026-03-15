"""Debug: show scores for 'Who is the President of Venezuela?' query."""
import asyncio
import logging
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

    # Monkey-patch reranker to capture all scored chunks
    original_rerank = svc._semantic_reranker.rerank
    all_scored = []

    async def patched_rerank(chunks, query, top_k=15, decomposition=None):
        result = await original_rerank(chunks, query, top_k=len(chunks), decomposition=decomposition)
        all_scored.extend(result)
        return result[:top_k]

    svc._semantic_reranker.rerank = patched_rerank

    query = "Who is the President of Venezuela?"
    result = await svc.retrieve(query)

    print(f"Total scored chunks: {len(all_scored)}")
    print(f"Final result chunks: {len(result.chunks)}")

    print(f"\n=== Top 20 scored chunks ===")
    for i, ch in enumerate(all_scored[:20]):
        meta = ch.metadata or {}
        title = meta.get('title', meta.get('document_title', '?'))[:60]
        page = meta.get('page_number', '?')
        content_preview = (ch.content or "")[:100].replace('\n', ' ')
        print(f"  [{i:2d}] final={ch.final_score:.4f} kg={ch.kg_relevance_score:.4f} "
              f"sem={ch.semantic_score:.4f}")
        print(f"       concept={ch.concept_name} source={ch.source.value}")
        print(f"       title={title} page={page}")
        print(f"       content={content_preview}")
        print()

    # Show what concepts were matched
    concepts_seen = set()
    for ch in all_scored:
        if ch.concept_name:
            concepts_seen.add(ch.concept_name)
    print(f"\n=== Concepts matched ({len(concepts_seen)}) ===")
    for c in sorted(concepts_seen):
        print(f"  {c}")

    await neo4j.close()

asyncio.run(main())
