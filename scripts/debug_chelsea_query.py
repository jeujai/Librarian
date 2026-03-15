"""Debug: trace KG Stage 1 for the Chelsea query step by step."""
import asyncio
import logging
import os
import sys

sys.path.insert(0, "/app/src")

# Ensure container-internal hostnames
os.environ.setdefault("NEO4J_URI", "bolt://neo4j:7687")
os.environ.setdefault("NEO4J_HOST", "neo4j")
os.environ.setdefault("NEO4J_USER", "neo4j")
os.environ.setdefault("NEO4J_PASSWORD", "password")
os.environ.setdefault("MILVUS_HOST", "milvus")
os.environ.setdefault("MILVUS_PORT", "19530")
os.environ.setdefault("MODEL_SERVER_URL", "http://model-server:8001")

logging.basicConfig(level=logging.INFO, format="%(name)s %(levelname)s %(message)s")
# Enable DEBUG for the retrieval service
logging.getLogger("multimodal_librarian.services.kg_retrieval_service").setLevel(logging.DEBUG)
logging.getLogger("multimodal_librarian.components.kg_retrieval").setLevel(logging.DEBUG)

async def main():
    from multimodal_librarian.clients.milvus_client import MilvusClient
    from multimodal_librarian.clients.model_server_client import ModelServerClient
    from multimodal_librarian.clients.neo4j_client import Neo4jClient
    from multimodal_librarian.components.kg_retrieval.query_decomposer import (
        QueryDecomposer,
    )
    from multimodal_librarian.services.kg_retrieval_service import KGRetrievalService

    neo4j = Neo4jClient(uri="bolt://neo4j:7687", user="neo4j", password="password")
    await neo4j.connect()
    model_client = ModelServerClient()
    milvus = MilvusClient(host="milvus", port=19530)
    await milvus.connect()

    query = "What did our team observe at Chelsea?"

    # Step 1: Decompose
    decomposer = QueryDecomposer(neo4j_client=neo4j, model_server_client=model_client)
    decomposition = await decomposer.decompose(query)
    print(f"\n{'='*60}")
    print(f"DECOMPOSITION: {len(decomposition.concept_matches)} concepts, has_kg={decomposition.has_kg_matches}")
    for i, cm in enumerate(decomposition.concept_matches[:8]):
        print(f"  [{i}] id={cm.get('concept_id','?')[:30]}, name={cm.get('name','?')}, "
              f"sim={cm.get('similarity_score','?')}, type={cm.get('match_type','?')}")

    # Step 2: Manually run _retrieve_direct_chunks
    service = KGRetrievalService(
        neo4j_client=neo4j, vector_client=milvus, model_client=model_client,
    )
    print(f"\n{'='*60}")
    print("STAGE 1a: _retrieve_direct_chunks")
    direct_ids, direct_mappings, chunk_hits = await service._retrieve_direct_chunks(
        decomposition.concept_matches
    )
    print(f"  direct chunk IDs: {len(direct_ids)}")
    for cid in list(direct_ids)[:10]:
        hits = chunk_hits.get(cid, [])
        concepts = [h['concept_name'] for h in hits]
        print(f"    {cid[:30]}... concepts={concepts}")

    # Step 3: Manually run _retrieve_related_chunks
    print(f"\n{'='*60}")
    print("STAGE 1b: _retrieve_related_chunks")
    related_ids, related_mappings = await service._retrieve_related_chunks(
        decomposition.concept_matches
    )
    print(f"  related chunk IDs: {len(related_ids)}")

    all_ids = direct_ids | set(related_ids)
    print(f"\n  TOTAL unique chunk IDs: {len(all_ids)}")

    # Step 4: Resolve chunks
    print(f"\n{'='*60}")
    print("STAGE 1c: resolve_chunks")
    all_mappings = {**direct_mappings, **{k: v for k, v in related_mappings.items() if k not in direct_mappings}}
    resolved = await service._chunk_resolver.resolve_chunks(list(all_ids), all_mappings)
    print(f"  resolved: {len(resolved)} of {len(all_ids)}")
    for ch in resolved[:5]:
        print(f"    {ch.chunk_id[:30]}... content_len={len(ch.content or '')}")

    # Step 5: Aggregate
    print(f"\n{'='*60}")
    print("STAGE 1d: _aggregate_and_deduplicate")
    direct_chunks = [c for c in resolved if c.chunk_id in direct_ids]
    related_chunks = [c for c in resolved if c.chunk_id not in direct_ids]
    aggregated = service._aggregate_and_deduplicate(
        direct_chunks, related_chunks, all_mappings, chunk_hits
    )
    print(f"  aggregated: {len(aggregated)}")
    for ch in aggregated[:10]:
        print(f"    {ch.chunk_id[:30]}... kg_score={ch.kg_relevance_score:.4f}, "
              f"concept={ch.concept_name}, content={ch.content[:60] if ch.content else 'EMPTY'}")

    await neo4j.close()

asyncio.run(main())
