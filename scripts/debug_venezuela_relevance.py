"""Debug: check what RelevanceDetector says about Venezuela query."""
import asyncio
import logging
import sys

sys.path.insert(0, "/app/src")
logging.basicConfig(level=logging.WARNING)
logging.getLogger("multimodal_librarian.components.kg_retrieval.relevance_detector").setLevel(logging.DEBUG)
logging.getLogger("multimodal_librarian.services.rag_service").setLevel(logging.DEBUG)

async def main():
    from multimodal_librarian.clients.milvus_client import MilvusClient
    from multimodal_librarian.clients.model_server_client import ModelServerClient
    from multimodal_librarian.clients.neo4j_client import Neo4jClient
    from multimodal_librarian.components.kg_retrieval.relevance_detector import (
        RelevanceDetector,
        analyze_concept_specificity,
        analyze_query_term_coverage,
        analyze_score_distribution,
    )
    from multimodal_librarian.services.kg_retrieval_service import KGRetrievalService

    neo4j = Neo4jClient(uri="bolt://neo4j:7687", user="neo4j", password="password")
    await neo4j.connect()
    model = ModelServerClient()
    milvus = MilvusClient(host="milvus", port=19530)
    await milvus.connect()

    svc = KGRetrievalService(
        neo4j_client=neo4j, vector_client=milvus, model_client=model,
    )

    query = "Who is the President of Venezuela?"
    
    # Get the decomposition
    decomposition = await svc._query_decomposer.decompose(query)
    print(f"=== Query Decomposition ===")
    print(f"  entities: {decomposition.entities}")
    print(f"  actions: {decomposition.actions}")
    print(f"  concept_matches: {len(decomposition.concept_matches)}")
    for cm in decomposition.concept_matches:
        print(f"    {cm}")
    
    # Get KG results
    kg_result = await svc.retrieve(query)
    print(f"\n=== KG Result ===")
    print(f"  chunks: {len(kg_result.chunks)}")
    print(f"  fallback_used: {kg_result.fallback_used}")
    
    # Now test the RelevanceDetector
    # Try to load spacy
    try:
        import spacy
        nlp = spacy.load("en_core_web_sm")
        print(f"\n  spaCy loaded: en_core_web_sm")
    except Exception as e:
        nlp = None
        print(f"\n  spaCy NOT available: {e}")
    
    detector = RelevanceDetector(spacy_nlp=nlp)
    
    # Build lightweight RetrievedChunk wrappers like _post_processing_phase does
    from multimodal_librarian.models.kg_retrieval import RetrievalSource
    from multimodal_librarian.models.kg_retrieval import RetrievedChunk as RC
    rc_chunks = [
        RC(
            chunk_id=c.chunk_id or "",
            content=c.content or "",
            source=RetrievalSource.SEMANTIC_FALLBACK,
            final_score=c.final_score,
        )
        for c in kg_result.chunks
    ]
    
    verdict = detector.evaluate(rc_chunks, decomposition)
    print(f"\n=== Relevance Verdict ===")
    print(f"  is_relevant: {verdict.is_relevant}")
    print(f"  factor: {verdict.confidence_adjustment_factor}")
    print(f"  reasoning: {verdict.reasoning}")
    print(f"\n  Score Distribution:")
    print(f"    variance: {verdict.score_distribution.variance:.6f}")
    print(f"    spread: {verdict.score_distribution.spread:.4f}")
    print(f"    is_semantic_floor: {verdict.score_distribution.is_semantic_floor}")
    print(f"\n  Concept Specificity:")
    print(f"    average: {verdict.concept_specificity.average_specificity:.2f}")
    print(f"    is_low: {verdict.concept_specificity.is_low_specificity}")
    print(f"    per_concept: {verdict.concept_specificity.per_concept_scores}")
    print(f"\n  Query Term Coverage:")
    print(f"    proper_nouns: {verdict.query_term_coverage.proper_nouns}")
    print(f"    covered: {verdict.query_term_coverage.covered_nouns}")
    print(f"    uncovered: {verdict.query_term_coverage.uncovered_nouns}")
    print(f"    has_gap: {verdict.query_term_coverage.has_proper_noun_gap}")

    await neo4j.close()

asyncio.run(main())
