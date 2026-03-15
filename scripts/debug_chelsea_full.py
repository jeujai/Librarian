"""Debug: run full KG retrieval for Chelsea query."""
import asyncio
import logging
import sys

sys.path.insert(0, "/app/src")

logging.basicConfig(level=logging.INFO, format="%(name)s %(levelname)s %(message)s")
logging.getLogger("multimodal_librarian.services.kg_retrieval_service").setLevel(logging.DEBUG)
logging.getLogger("multimodal_librarian.components.kg_retrieval").setLevel(logging.DEBUG)


async def main():
    from multimodal_librarian.clients.milvus_client import MilvusClient
    from multimodal_librarian.clients.model_server_client import ModelServerClient
    from multimodal_librarian.clients.neo4j_client import Neo4jClient
    from multimodal_librarian.services.kg_retrieval_service import KGRetrievalService

    neo4j = Neo4jClient(uri="bolt://neo4j:7687", user="neo4j", password="password")
    await neo4j.connect()
    model_client = ModelServerClient()
    milvus = MilvusClient(host="milvus", port=19530)
    await milvus.connect()

    service = KGRetrievalService(
        neo4j_client=neo4j, vector_client=milvus, model_client=model_client,
    )

    result = await service.retrieve("What did our team observe at Chelsea?")

    print(f"\n{'='*60}")
    print(f"RESULT: {len(result.chunks)} chunks, fallback={result.fallback_used}")
    print(f"Stage 1: {result.stage1_chunk_count}, Stage 2: {result.stage2_chunk_count}")
    for i, ch in enumerate(result.chunks[:10]):
        has_chelsea = "chelsea" in (ch.content or "").lower()
        print(f"  [{i}] score={ch.final_score:.4f} kg={ch.kg_relevance_score:.4f} "
              f"sem={ch.semantic_score:.4f} chelsea={has_chelsea} "
              f"concept={ch.concept_name} "
              f"content={ch.content[:80] if ch.content else 'EMPTY'}")

    await neo4j.close()

asyncio.run(main())
