"""Debug: find ALL LangChain chunks that mention 'observe' or page 114."""
import asyncio
import logging
import sys

sys.path.insert(0, "/app/src")
logging.basicConfig(level=logging.WARNING)


async def main():
    from multimodal_librarian.clients.milvus_client import MilvusClient

    milvus = MilvusClient(host="milvus", port=19530)
    await milvus.connect()

    # Search for "observed" content specifically
    queries = [
        "our team has observed that traditional approaches",
        "At Chelsea AI Ventures we observed",
        "Chelsea observed traditional approaches",
    ]
    
    seen_ids = set()
    for q in queries:
        print(f"\n=== Query: {q} ===")
        results = await milvus.semantic_search(query=q, top_k=20)
        for r in results:
            meta = r.get("metadata", {})
            content = meta.get("content", r.get("content", ""))
            chunk_id = r.get("id", meta.get("chunk_id", ""))
            title = meta.get("title", meta.get("document_title", "?"))
            page = meta.get("page_number", "?")
            score = r.get("score", 0)
            
            has_observe = "observ" in content.lower()
            has_chelsea = "chelsea" in content.lower()
            is_langchain = "langchain" in str(title).lower()
            
            if (has_observe and has_chelsea) or (is_langchain and has_observe):
                if chunk_id not in seen_ids:
                    seen_ids.add(chunk_id)
                    print(f"  chunk_id={chunk_id} score={score:.4f} page={page}")
                    print(f"  title={str(title)[:60]}")
                    print(f"  chelsea={has_chelsea} observe={has_observe}")
                    print(f"  content: {content[:300]}...")
                    print()

    # Also: directly query Milvus for LangChain source chunks
    print("\n=== Direct query: all LangChain chunks with 'observe' ===")
    # Get the LangChain source_id from postgres
    import psycopg2
    conn = psycopg2.connect(
        host="postgres", port=5432, dbname="multimodal_librarian",
        user="postgres", password="postgres"
    )
    cur = conn.cursor()
    cur.execute("""
        SELECT source_id, title FROM multimodal_librarian.knowledge_sources 
        WHERE title ILIKE '%langchain%'
    """)
    rows = cur.fetchall()
    print(f"  LangChain sources: {rows}")
    
    for source_id, title in rows:
        # Get all chunks for this source
        chunks = await milvus.get_chunks_by_ids([])  # Can't filter by source_id this way
        # Instead, use get_chunk_by_id with known IDs... 
        # Let's query postgres for chunk IDs
        cur.execute("""
            SELECT chunk_id, page_number FROM multimodal_librarian.knowledge_chunks
            WHERE source_id = %s AND page_number = 114
        """, (source_id,))
        page114_chunks = cur.fetchall()
        print(f"  Page 114 chunks for {title}: {page114_chunks}")
        
        if page114_chunks:
            for chunk_id, page_num in page114_chunks:
                chunk_data = await milvus.get_chunk_by_id(chunk_id)
                if chunk_data:
                    content = chunk_data.get("content", "")
                    has_observe = "observ" in content.lower()
                    has_chelsea = "chelsea" in content.lower()
                    print(f"    chunk_id={chunk_id} page={page_num}")
                    print(f"    chelsea={has_chelsea} observe={has_observe}")
                    print(f"    content: {content[:300]}...")
    
    cur.close()
    conn.close()

asyncio.run(main())
