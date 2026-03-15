"""Debug: trace KG scoring for Chelsea chunks — why did dedup make things worse?"""
import asyncio
import logging
import math
import re
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

    # Decompose query to see concept matches
    query = "What did our team observe at Chelsea?"
    decomposition = await svc._decompose_query_safe(query)

    print("=== CONCEPT MATCHES ===")
    for cm in decomposition.concept_matches:
        name = cm.get("name", "?")
        match_type = cm.get("match_type", "?")
        score = cm.get("match_score", cm.get("similarity_score", "?"))
        print(f"  {name} ({match_type}) score={score}")

    # Run Stage 1 to get direct chunks with concept hits
    direct_chunk_ids, direct_mappings, chunk_concept_hits = (
        await svc._retrieve_direct_chunks(decomposition.concept_matches)
    )

    # Show concept hits for Chelsea-related chunks
    print(f"\n=== CHUNKS WITH MULTIPLE CONCEPT HITS ===")
    multi_hit_chunks = {cid: hits for cid, hits in chunk_concept_hits.items() if len(hits) > 1}
    print(f"  {len(multi_hit_chunks)} chunks have >1 concept hit")

    # Resolve a sample to see content
    sample_ids = list(multi_hit_chunks.keys())[:10]
    if sample_ids:
        resolved = await svc._chunk_resolver.resolve_chunks(sample_ids, direct_mappings)
        for chunk in resolved:
            hits = chunk_concept_hits.get(chunk.chunk_id, [])
            meta = chunk.metadata or {}
            title = meta.get("title", meta.get("document_title", "?"))[:50]
            page = meta.get("page_number", "?")
            has_chelsea = "chelsea" in (chunk.content or "").lower()
            has_observe = "observ" in (chunk.content or "").lower()

            # Simulate scoring WITH dedup (current)
            normalized_scores = [min(1.0, max(0.1, h["match_score"] / 10.0)) for h in hits]
            base_score = max(normalized_scores)
            distinct_names_dedup = {
                re.sub(r'[^a-z0-9\s]', '', h["concept_name"].lower()).strip()
                for h in hits
            }
            coverage_dedup = math.log2(max(1, len(distinct_names_dedup))) * 0.1
            kg_score_dedup = min(1.0, base_score + coverage_dedup)

            # Simulate scoring WITHOUT dedup (old)
            num_raw = len(hits)
            coverage_raw = math.log2(max(1, num_raw)) * 0.1
            kg_score_raw = min(1.0, base_score + coverage_raw)

            print(f"\n  chunk={chunk.chunk_id[:12]}... title={title} page={page}")
            print(f"    chelsea={has_chelsea} observe={has_observe}")
            print(f"    {len(hits)} concept hits, {len(distinct_names_dedup)} distinct (deduped)")
            print(f"    base_score={base_score:.4f}")
            print(f"    OLD kg_score={kg_score_raw:.4f} (coverage={coverage_raw:.4f}, {num_raw} concepts)")
            print(f"    NEW kg_score={kg_score_dedup:.4f} (coverage={coverage_dedup:.4f}, {len(distinct_names_dedup)} concepts)")
            for h in hits:
                norm = min(1.0, max(0.1, h["match_score"] / 10.0))
                dedup_name = re.sub(r'[^a-z0-9\s]', '', h["concept_name"].lower()).strip()
                print(f"      concept='{h['concept_name']}' -> '{dedup_name}' score={h['match_score']:.4f} norm={norm:.4f}")

    # Now show single-hit Chelsea chunks for comparison
    print(f"\n=== SINGLE-HIT CHELSEA CHUNKS ===")
    # Find Chelsea concept IDs
    chelsea_concept_ids = set()
    for cm in decomposition.concept_matches:
        if "chelsea" in cm.get("name", "").lower():
            chelsea_concept_ids.add(cm.get("concept_id", ""))

    single_chelsea = []
    for cid, hits in chunk_concept_hits.items():
        if len(hits) == 1 and hits[0].get("concept_id") in chelsea_concept_ids:
            single_chelsea.append(cid)

    print(f"  {len(single_chelsea)} chunks with only 1 Chelsea concept hit")
    if single_chelsea[:5]:
        resolved2 = await svc._chunk_resolver.resolve_chunks(single_chelsea[:5], direct_mappings)
        for chunk in resolved2:
            hits = chunk_concept_hits.get(chunk.chunk_id, [])
            meta = chunk.metadata or {}
            title = meta.get("title", meta.get("document_title", "?"))[:50]
            page = meta.get("page_number", "?")
            norm = min(1.0, max(0.1, hits[0]["match_score"] / 10.0))
            print(f"  chunk={chunk.chunk_id[:12]}... title={title} page={page} kg={norm:.4f}")

    await neo4j.close()

asyncio.run(main())
