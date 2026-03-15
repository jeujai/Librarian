"""Debug: check if a specific chunk exists in Milvus and its score for a query."""
import asyncio
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

async def main():
    from multimodal_librarian.clients.milvus_client import MilvusClient
    from multimodal_librarian.config import get_settings
    settings = get_settings()
    
    milvus = MilvusClient(host=settings.milvus_host, port=settings.milvus_port)
    await milvus.connect()
    
    # Check if the page 114 chunk exists in Milvus
    chunk_id = "31154efa-5bad-4b94-befa-ebf7cee956a3"
    print(f"Looking up chunk {chunk_id} in Milvus...", flush=True)
    
    result = await milvus.get_chunk_by_id(chunk_id)
    if result:
        meta = result.get('metadata', {})
        content = result.get('content', meta.get('content', ''))
        print(f"FOUND in Milvus!", flush=True)
        print(f"  source_id: {meta.get('source_id', '?')}", flush=True)
        print(f"  page_number: {meta.get('page_number', '?')}", flush=True)
        print(f"  title: {meta.get('title', '?')}", flush=True)
        print(f"  content (first 200): {content[:200]}", flush=True)
        
        # Now compute similarity between query and this chunk
        query = "What did our team observe at Chelsea?"
        print(f"\nComputing embedding similarity for query: '{query}'", flush=True)
        
        await milvus._ensure_embedding_model()
        query_emb = await milvus.generate_embedding_async(query)
        
        # Get the chunk's embedding by searching with high top_k
        # and checking if our chunk appears
        results = await milvus.semantic_search(query, top_k=100)
        found = False
        for i, r in enumerate(results):
            rid = r.get('id', '')
            if rid == chunk_id:
                print(f"\nChunk found at rank {i+1} out of {len(results)}", flush=True)
                print(f"  score: {r.get('score', '?')}", flush=True)
                print(f"  raw_score (L2 dist): {r.get('raw_score', '?')}", flush=True)
                found = True
                break
        
        if not found:
            print(f"\nChunk NOT found in top {len(results)} results!", flush=True)
            print("It may be below the similarity threshold or not indexed.", flush=True)
            
            # Try a more targeted search
            print("\nTrying targeted search: 'Chelsea AI Ventures team observed'", flush=True)
            results2 = await milvus.semantic_search("Chelsea AI Ventures team observed regulated industries", top_k=10)
            for i, r in enumerate(results2):
                rid = r.get('id', '')
                score = r.get('score', 0)
                meta2 = r.get('metadata', {})
                title = meta2.get('title', '?')[:50]
                marker = " <-- TARGET" if rid == chunk_id else ""
                print(f"  {i+1}. score={score:.4f} id={rid[:12]}... title={title}{marker}", flush=True)
    else:
        print(f"NOT FOUND in Milvus - chunk may not be indexed", flush=True)
    
    await milvus.disconnect()
    print("\nDone.", flush=True)

asyncio.run(main())
