"""Debug: show detailed content of Chelsea-containing chunks."""
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
    query = "What did our team observe at Chelsea?"
    result = await svc.retrieve(query)

    print(f"Total chunks: {len(result.chunks)}")
    print(f"\n=== ALL CHUNKS WITH SCORES ===")
    for i, ch in enumerate(result.chunks):
        has_chelsea = "chelsea" in (ch.content or "").lower()
        has_observe = "observ" in (ch.content or "").lower()
        meta = ch.metadata or {}
        title = meta.get('title', meta.get('document_title', '?'))[:60]
        page = meta.get('page_number', '?')
        print(f"\n--- [{i}] final={ch.final_score:.4f} kg={ch.kg_relevance_score:.4f} "
              f"sem={ch.semantic_score:.4f} ---")
        print(f"    title={title} page={page}")
        print(f"    chelsea={has_chelsea} observe={has_observe}")
        print(f"    concept={ch.concept_name} source={ch.source.value}")
        if has_chelsea:
            # Show first 200 chars of content
            print(f"    content: {(ch.content or '')[:200]}...")

    # Also check: is page 114 from LangChain even in the Stage 1 candidates?
    print(f"\n=== QUERY DECOMPOSITION ===")
    if result.query_decomposition:
        d = result.query_decomposition
        print(f"  entities: {d.entities}")
        print(f"  actions: {d.actions}")
        print(f"  subjects: {d.subjects}")
        print(f"  concept_matches: {len(d.concept_matches)}")
        for cm in d.concept_matches[:10]:
            print(f"    - {cm.get('name')} (score={cm.get('match_score', cm.get('similarity_score', '?'))})")

    await neo4j.close()

asyncio.run(main())
