"""Debug: trace Chelsea query through KG retrieval WITH reranker term boost."""
import asyncio
import logging
import sys

sys.path.insert(0, "/app/src")
logging.basicConfig(level=logging.WARNING)
logging.getLogger("multimodal_librarian.components.kg_retrieval.semantic_reranker").setLevel(logging.DEBUG)


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

    print(f"\nAfter reranker (includes term boost):")
    print(f"  {len(result.chunks)} chunks, fallback={result.fallback_used}")
    for i, ch in enumerate(result.chunks):
        has_chelsea = "chelsea" in (ch.content or "").lower()
        meta = ch.metadata or {}
        title = meta.get('title', meta.get('document_title', '?'))[:50]
        print(f"  [{i:2d}] final={ch.final_score:.4f} kg={ch.kg_relevance_score:.4f} "
              f"sem={ch.semantic_score:.4f} chelsea={has_chelsea} "
              f"title={title}")

    # Now simulate RAG pipeline: convert + boost + prepare_context
    from multimodal_librarian.services.rag_service import ContextPreparer, DocumentChunk
    doc_chunks = []
    for ch in result.chunks:
        meta = ch.metadata or {}
        doc_chunks.append(DocumentChunk(
            chunk_id=ch.chunk_id,
            document_id=meta.get('source_id', meta.get('document_id', 'unknown')),
            document_title=meta.get('title', meta.get('document_title', 'Unknown')),
            content=ch.content,
            page_number=meta.get('page_number'),
            similarity_score=ch.final_score,
            source_type="librarian",
            metadata={**meta, 'kg_retrieval': {'source': ch.source.value}},
        ))
    boost = 1.15
    for c in doc_chunks:
        c.similarity_score = min(1.0, c.similarity_score * boost)

    preparer = ContextPreparer()
    _, citations = preparer.prepare_context(doc_chunks, query)
    print(f"\nFinal citation order:")
    for i, cit in enumerate(citations, 1):
        has_chelsea = "chelsea" in (cit.excerpt or "").lower()
        print(f"  [{i}] score={cit.relevance_score:.4f} chelsea={has_chelsea} "
              f"title={cit.document_title[:55]} page={cit.page_number}")

    await neo4j.close()

asyncio.run(main())
