"""Debug: trace chunk b68a837a through the KG retrieval pipeline."""
import asyncio
import logging
import sys

sys.path.insert(0, "/app/src")
logging.basicConfig(level=logging.WARNING)

TARGET = "b68a837a-6564-4bff-b0d2-51d4e76d1f87"


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

    # Step 1: Check Neo4j concepts for this chunk
    print(f"=== Neo4j concepts for target chunk {TARGET} ===")
    cypher = """
    MATCH (c:Concept)-[:EXTRACTED_FROM]->(ch:Chunk {chunk_id: $chunk_id})
    RETURN c.concept_id as concept_id, c.name as name
    ORDER BY c.name
    """
    results = await neo4j.execute_query(cypher, {"chunk_id": TARGET})
    if results:
        print(f"  {len(results)} concepts link to this chunk:")
        for r in results:
            print(f"    - {r['name']} ({r['concept_id']})")
    else:
        print("  NO concepts link to this chunk in Neo4j!")
        # Check if chunk node exists
        cypher2 = "MATCH (ch:Chunk {chunk_id: $chunk_id}) RETURN ch.chunk_id as cid"
        r2 = await neo4j.execute_query(cypher2, {"chunk_id": TARGET})
        if r2:
            print("  Chunk node exists but no EXTRACTED_FROM edges")
        else:
            print("  Chunk node does NOT exist in Neo4j!")

    # Step 2: Check if it's in Milvus
    print(f"\n=== Milvus lookup for target chunk ===")
    chunk_data = await milvus.get_chunk_by_id(TARGET)
    if chunk_data:
        content = chunk_data.get("content", "")
        has_chelsea = "chelsea" in content.lower()
        has_observe = "observ" in content.lower()
        print(f"  Found in Milvus: chelsea={has_chelsea} observe={has_observe}")
        print(f"  Content length: {len(content)}")
        # Find the Chelsea mention position
        idx = content.lower().find("chelsea")
        if idx >= 0:
            print(f"  Chelsea at position {idx}/{len(content)}: ...{content[max(0,idx-30):idx+80]}...")
    else:
        print("  NOT found in Milvus!")

    # Step 3: Run full retrieval and check if target appears
    print(f"\n=== Full KG retrieval ===")
    svc = KGRetrievalService(
        neo4j_client=neo4j, vector_client=milvus, model_client=model,
    )
    result = await svc.retrieve("What did our team observe at Chelsea?")
    
    found = False
    for i, ch in enumerate(result.chunks):
        if ch.chunk_id == TARGET:
            found = True
            print(f"  TARGET FOUND at position {i}!")
            print(f"    final={ch.final_score:.4f} kg={ch.kg_relevance_score:.4f} sem={ch.semantic_score:.4f}")
            print(f"    concept={ch.concept_name} source={ch.source.value}")
            break
    
    if not found:
        print(f"  TARGET NOT in final results ({len(result.chunks)} chunks)")
        print(f"  Stage 1 count: {result.stage1_chunk_count}")
        print(f"  Stage 2 count: {result.stage2_chunk_count}")

    await neo4j.close()

asyncio.run(main())
