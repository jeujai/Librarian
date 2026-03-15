"""Debug: find the LangChain page 114 chunk and trace why it's missing from KG retrieval."""
import asyncio
import logging
import sys

sys.path.insert(0, "/app/src")
logging.basicConfig(level=logging.WARNING)


async def main():
    from multimodal_librarian.clients.milvus_client import MilvusClient
    from multimodal_librarian.clients.neo4j_client import Neo4jClient

    milvus = MilvusClient(host="milvus", port=19530)
    await milvus.connect()
    neo4j = Neo4jClient(uri="bolt://neo4j:7687", user="neo4j", password="password")
    await neo4j.connect()

    # Step 1: Find the target chunk via semantic_search
    print("=== STEP 1: Semantic search for target chunk ===")
    results = await milvus.semantic_search(
        query="At Chelsea AI Ventures our team has observed",
        top_k=30,
    )

    target_chunk_id = None
    for r in results:
        meta = r.get("metadata", {})
        content = meta.get("content", r.get("content", ""))
        chunk_id = r.get("id", meta.get("chunk_id", ""))
        title = meta.get("title", meta.get("document_title", "?"))
        page = meta.get("page_number", "?")
        has_chelsea = "chelsea" in content.lower()
        has_observe = "observ" in content.lower()

        if has_chelsea and has_observe:
            print(f"  FOUND TARGET: chunk_id={chunk_id} page={page} title={str(title)[:60]}")
            print(f"    content: {content[:250]}...")
            target_chunk_id = chunk_id
            break

    if not target_chunk_id:
        print("  Not found via first search. Trying broader...")
        results2 = await milvus.semantic_search(
            query="Chelsea AI Ventures observed",
            top_k=50,
        )
        for r in results2:
            meta = r.get("metadata", {})
            content = meta.get("content", r.get("content", ""))
            chunk_id = r.get("id", meta.get("chunk_id", ""))
            if "chelsea ai ventures" in content.lower():
                target_chunk_id = chunk_id
                print(f"  FOUND: chunk_id={chunk_id}")
                print(f"    content: {content[:250]}...")
                break

    if not target_chunk_id:
        print("  Could not find target chunk!")
        await neo4j.close()
        return

    # Step 2: Check what concepts link to this chunk in Neo4j
    print(f"\n=== STEP 2: Neo4j concepts for chunk {target_chunk_id} ===")
    cypher = """
    MATCH (c:Concept)-[:EXTRACTED_FROM]->(ch:Chunk {chunk_id: $chunk_id})
    RETURN c.concept_id as concept_id, c.name as name
    """
    neo4j_results = await neo4j.execute_query(cypher, {"chunk_id": target_chunk_id})
    if neo4j_results:
        for r in neo4j_results:
            print(f"  Concept: {r['name']} (id={r['concept_id']})")
    else:
        print("  NO concepts link to this chunk!")
        cypher2 = "MATCH (ch:Chunk {chunk_id: $chunk_id}) RETURN ch.chunk_id as cid"
        r2 = await neo4j.execute_query(cypher2, {"chunk_id": target_chunk_id})
        if r2:
            print(f"  Chunk node exists but has no EXTRACTED_FROM relationships")
        else:
            print(f"  Chunk node does NOT exist in Neo4j!")

    # Step 3: Check Chelsea concept's chunks
    print(f"\n=== STEP 3: Chelsea concept's chunks ===")
    cypher3 = """
    MATCH (c:Concept)-[:EXTRACTED_FROM]->(ch:Chunk)
    WHERE toLower(c.name) CONTAINS 'chelsea'
    RETURN c.name as concept_name, c.concept_id as concept_id,
           collect(ch.chunk_id) as chunk_ids
    """
    results3 = await neo4j.execute_query(cypher3, {})
    for r in (results3 or []):
        chunk_ids = r.get("chunk_ids", [])
        has_target = target_chunk_id in chunk_ids if target_chunk_id else False
        print(f"  Concept '{r['concept_name']}': {len(chunk_ids)} chunks, "
              f"contains_target={has_target}")

    await neo4j.close()

asyncio.run(main())
