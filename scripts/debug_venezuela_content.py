"""Debug: show content of top Venezuela chunks to understand why they match."""
import asyncio
import sys

sys.path.insert(0, "/app/src")

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

    # Capture all scored chunks
    original_rerank = svc._semantic_reranker.rerank
    all_scored = []
    async def patched_rerank(chunks, query, top_k=15, decomposition=None):
        result = await original_rerank(chunks, query, top_k=len(chunks), decomposition=decomposition)
        all_scored.extend(result)
        return result[:top_k]
    svc._semantic_reranker.rerank = patched_rerank

    query = "Who is the President of Venezuela?"
    result = await svc.retrieve(query)

    # Show top 5 with full content
    print(f"=== Top 5 chunks with content ===\n")
    for i, ch in enumerate(all_scored[:5]):
        meta = ch.metadata or {}
        title = meta.get('title', meta.get('document_title', '?'))[:80]
        has_venezuela = "venezuela" in (ch.content or "").lower()
        has_president = "president" in (ch.content or "").lower()
        print(f"[{i}] final={ch.final_score:.4f} kg={ch.kg_relevance_score:.4f} sem={ch.semantic_score:.4f}")
        print(f"    concept={ch.concept_name} source={ch.source.value}")
        print(f"    title={title}")
        print(f"    venezuela_in_content={has_venezuela} president_in_content={has_president}")
        print(f"    CONTENT (first 500 chars):")
        print(f"    {(ch.content or '')[:500]}")
        print()

    # Check: does ANY chunk contain BOTH "venezuela" AND "president"?
    both_count = 0
    for ch in all_scored:
        content_lower = (ch.content or "").lower()
        if "venezuela" in content_lower and "president" in content_lower:
            both_count += 1
            meta = ch.metadata or {}
            title = meta.get('title', meta.get('document_title', '?'))[:80]
            print(f"  BOTH match: concept={ch.concept_name} title={title}")
            print(f"    final={ch.final_score:.4f}")
    print(f"\nChunks with BOTH 'venezuela' AND 'president': {both_count}")

    await neo4j.close()

asyncio.run(main())
