"""Debug script to test RAG retrieval for a specific query."""
import asyncio
import json
import os
import sys

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

async def main():
    query = "What did our team observe at Chelsea?"
    print(f"Query: {query}\n", flush=True)
    
    # Step 1: Test Milvus semantic search directly
    print("=" * 60, flush=True)
    print("STEP 1: Direct Milvus semantic search", flush=True)
    print("=" * 60, flush=True)
    
    from multimodal_librarian.clients.milvus_client import MilvusClient
    from multimodal_librarian.config import get_settings
    settings = get_settings()
    print(f"Milvus host: {settings.milvus_host}:{settings.milvus_port}", flush=True)
    milvus = MilvusClient(
        host=settings.milvus_host,
        port=settings.milvus_port,
    )
    await milvus.connect()
    
    results = await milvus.semantic_search(query, top_k=15)
    print(f"Got {len(results)} results from Milvus\n", flush=True)
    
    for i, r in enumerate(results):
        score = r.get('score', 0)
        raw = r.get('raw_score', '?')
        source_id = r.get('source_id', '?')
        meta = r.get('metadata', {})
        page = meta.get('page_number', '?')
        title = meta.get('title', '?')[:60]
        content = r.get('content', meta.get('content', ''))[:100]
        print(f"{i+1}. score={score:.4f} raw_dist={raw} page={page}", flush=True)
        print(f"   title: {title}", flush=True)
        print(f"   content: {content}", flush=True)
        print(flush=True)
    
    # Step 2: Test QueryDecomposer
    print("=" * 60, flush=True)
    print("STEP 2: QueryDecomposer concept matching", flush=True)
    print("=" * 60, flush=True)
    
    try:
        from multimodal_librarian.clients.model_server_client import (
            get_model_client,
            initialize_model_client,
        )
        from multimodal_librarian.clients.neo4j_client import Neo4jClient
        from multimodal_librarian.components.kg_retrieval.query_decomposer import (
            QueryDecomposer,
        )
        
        neo4j = Neo4jClient()
        await neo4j.connect()
        
        await initialize_model_client()
        model_client = get_model_client()
        
        decomposer = QueryDecomposer(
            neo4j_client=neo4j,
            model_server_client=model_client,
        )
        
        decomposition = await decomposer.decompose(query)
        print(f"Entities: {decomposition.entities}", flush=True)
        print(f"Actions: {decomposition.actions}", flush=True)
        print(f"Subjects: {decomposition.subjects}", flush=True)
        print(f"has_kg_matches: {decomposition.has_kg_matches}", flush=True)
        print(f"Concept matches ({len(decomposition.concept_matches)}):", flush=True)
        for m in decomposition.concept_matches[:10]:
            print(f"  - {m.get('name', '?')} (type={m.get('match_type', '?')}, "
                  f"score={m.get('similarity_score', m.get('match_score', '?'))})", flush=True)
        print(flush=True)
    except Exception as e:
        print(f"QueryDecomposer error: {e}", flush=True)
    
    # Step 3: Search for "Chelsea" specifically in Milvus
    print("=" * 60, flush=True)
    print("STEP 3: Milvus search for 'Chelsea observation team'", flush=True)
    print("=" * 60, flush=True)
    
    results2 = await milvus.semantic_search("Chelsea observation team", top_k=10)
    for i, r in enumerate(results2):
        score = r.get('score', 0)
        meta = r.get('metadata', {})
        page = meta.get('page_number', '?')
        title = meta.get('title', '?')[:60]
        content = r.get('content', meta.get('content', ''))[:100]
        print(f"{i+1}. score={score:.4f} page={page} title={title}", flush=True)
        print(f"   {content}", flush=True)
        print(flush=True)
    
    # Step 4: Search for the exact book + page to see if the chunk exists
    print("=" * 60, flush=True)
    print("STEP 4: Search for 'Generative AI LangChain Chelsea page 113'", flush=True)
    print("=" * 60, flush=True)
    
    results3 = await milvus.semantic_search("Generative AI LangChain Chelsea page 113 team observe", top_k=5)
    for i, r in enumerate(results3):
        score = r.get('score', 0)
        meta = r.get('metadata', {})
        page = meta.get('page_number', '?')
        title = meta.get('title', '?')[:60]
        content = r.get('content', meta.get('content', ''))[:150]
        print(f"{i+1}. score={score:.4f} page={page} title={title}", flush=True)
        print(f"   {content}", flush=True)
        print(flush=True)

    await milvus.disconnect()
    print("Done.", flush=True)

if __name__ == "__main__":
    asyncio.run(main())
