"""Debug: trace Chelsea query through full RAG pipeline to see citation ordering."""
import asyncio
import logging
import sys

sys.path.insert(0, "/app/src")

logging.basicConfig(level=logging.INFO, format="%(name)s %(levelname)s %(message)s")
logging.getLogger("multimodal_librarian.services.rag_service").setLevel(logging.DEBUG)
logging.getLogger("multimodal_librarian.services.kg_retrieval_service").setLevel(logging.DEBUG)


async def main():
    from multimodal_librarian.clients.milvus_client import MilvusClient
    from multimodal_librarian.clients.model_server_client import ModelServerClient
    from multimodal_librarian.clients.neo4j_client import Neo4jClient
    from multimodal_librarian.services.kg_retrieval_service import KGRetrievalService
    from multimodal_librarian.services.rag_service import ContextPreparer

    neo4j = Neo4jClient(uri="bolt://neo4j:7687", user="neo4j", password="password")
    await neo4j.connect()
    model_client = ModelServerClient()
    milvus = MilvusClient(host="milvus", port=19530)
    await milvus.connect()

    service = KGRetrievalService(
        neo4j_client=neo4j, vector_client=milvus, model_client=model_client,
    )

    query = "What did our team observe at Chelsea?"
    result = await service.retrieve(query)

    print(f"\n{'='*60}")
    print(f"KG RETRIEVAL: {len(result.chunks)} chunks, fallback={result.fallback_used}")
    print(f"\nAll 15 chunks from KG retrieval (pre-boost):")
    for i, ch in enumerate(result.chunks):
        has_chelsea = "chelsea" in (ch.content or "").lower()
        doc_title = (ch.metadata or {}).get('title', (ch.metadata or {}).get('document_title', '?'))
        doc_id = (ch.metadata or {}).get('source_id', (ch.metadata or {}).get('document_id', '?'))
        print(f"  [{i:2d}] final={ch.final_score:.4f} kg={ch.kg_relevance_score:.4f} "
              f"sem={ch.semantic_score:.4f} chelsea={has_chelsea} "
              f"doc_id={doc_id[:30]} title={doc_title[:50]}")

    # Now simulate what RAG pipeline does: convert to DocumentChunks
    from multimodal_librarian.services.rag_service import DocumentChunk
    doc_chunks = []
    for ch in result.chunks:
        metadata = ch.metadata or {}
        doc_chunks.append(DocumentChunk(
            chunk_id=ch.chunk_id,
            document_id=metadata.get('source_id', metadata.get('document_id', 'unknown')),
            document_title=metadata.get('title', metadata.get('document_title', 'Unknown')),
            content=ch.content,
            page_number=metadata.get('page_number'),
            similarity_score=ch.final_score,
            source_type="librarian",
            metadata={**metadata, 'kg_retrieval': {'source': ch.source.value}},
        ))

    # Apply librarian boost (1.15)
    boost = 1.15
    print(f"\nAfter librarian boost ({boost}x, capped at 1.0):")
    for i, c in enumerate(doc_chunks):
        old = c.similarity_score
        c.similarity_score = min(1.0, c.similarity_score * boost)
        has_chelsea = "chelsea" in (c.content or "").lower()
        print(f"  [{i:2d}] {old:.4f} -> {c.similarity_score:.4f} "
              f"chelsea={has_chelsea} doc={c.document_title[:50]}")

    # Now run through prepare_context
    preparer = ContextPreparer()
    context, citations = preparer.prepare_context(doc_chunks, query)

    print(f"\nFinal citation order (as shown to user):")
    for i, cit in enumerate(citations, 1):
        has_chelsea = "chelsea" in (cit.excerpt or "").lower()
        print(f"  [{i}] score={cit.relevance_score:.4f} "
              f"chelsea={has_chelsea} "
              f"title={cit.document_title[:60]} page={cit.page_number}")

    await neo4j.close()

asyncio.run(main())
