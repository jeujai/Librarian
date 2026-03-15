"""Debug: show scores for ALL 87 stage1 chunks, find target's position."""
import asyncio
import logging
import sys

sys.path.insert(0, "/app/src")
logging.basicConfig(level=logging.WARNING)
logging.getLogger("multimodal_librarian.components.kg_retrieval.semantic_reranker").setLevel(logging.DEBUG)

TARGET = "b68a837a-6564-4bff-b0d2-51d4e76d1f87"


async def main():
    from multimodal_librarian.clients.milvus_client import MilvusClient
    from multimodal_librarian.clients.model_server_client import ModelServerClient
    from multimodal_librarian.clients.neo4j_client import Neo4jClient
    from multimodal_librarian.components.kg_retrieval.semantic_reranker import (
        SemanticReranker,
    )
    from multimodal_librarian.services.kg_retrieval_service import KGRetrievalService

    neo4j = Neo4jClient(uri="bolt://neo4j:7687", user="neo4j", password="password")
    await neo4j.connect()
    model = ModelServerClient()
    milvus = MilvusClient(host="milvus", port=19530)
    await milvus.connect()

    svc = KGRetrievalService(
        neo4j_client=neo4j, vector_client=milvus, model_client=model,
    )
    
    # Monkey-patch reranker to capture all scored chunks before top_k cut
    original_rerank = svc._semantic_reranker.rerank
    all_scored = []
    
    async def patched_rerank(chunks, query, top_k=15, decomposition=None):
        result = await original_rerank(chunks, query, top_k=len(chunks), decomposition=decomposition)
        all_scored.extend(result)
        # Return only top_k
        return result[:top_k]
    
    svc._semantic_reranker.rerank = patched_rerank
    
    query = "What did our team observe at Chelsea?"
    result = await svc.retrieve(query)
    
    # Find target in all scored chunks
    print(f"Total scored chunks: {len(all_scored)}")
    target_pos = None
    for i, ch in enumerate(all_scored):
        if ch.chunk_id == TARGET:
            target_pos = i
            has_chelsea = "chelsea" in (ch.content or "").lower()
            has_observe = "observ" in (ch.content or "").lower()
            meta = ch.metadata or {}
            title = meta.get('title', meta.get('document_title', '?'))[:60]
            page = meta.get('page_number', '?')
            print(f"\n  TARGET at position {i}/{len(all_scored)}:")
            print(f"    final={ch.final_score:.4f} kg={ch.kg_relevance_score:.4f} sem={ch.semantic_score:.4f}")
            print(f"    chelsea={has_chelsea} observe={has_observe}")
            print(f"    title={title} page={page}")
            print(f"    concept={ch.concept_name} source={ch.source.value}")
            break
    
    if target_pos is None:
        print("  TARGET not found in scored chunks at all!")
        # Check if it was pre-filtered out
        print("  It may have been eliminated during pre-filtering")
    
    # Show the top 20 and the chunks around the target
    print(f"\n=== Top 20 scored chunks ===")
    for i, ch in enumerate(all_scored[:20]):
        has_chelsea = "chelsea" in (ch.content or "").lower()
        has_observe = "observ" in (ch.content or "").lower()
        meta = ch.metadata or {}
        title = meta.get('title', meta.get('document_title', '?'))[:50]
        marker = " <<<TARGET" if ch.chunk_id == TARGET else ""
        print(f"  [{i:2d}] final={ch.final_score:.4f} kg={ch.kg_relevance_score:.4f} "
              f"sem={ch.semantic_score:.4f} chel={has_chelsea} obs={has_observe} "
              f"title={title}{marker}")

    await neo4j.close()

asyncio.run(main())
