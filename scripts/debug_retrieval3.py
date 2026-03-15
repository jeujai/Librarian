"""Debug: test QueryDecomposer concept matching for Chelsea query."""
import asyncio
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

async def main():
    query = "What did our team observe at Chelsea?"
    print(f"Query: {query}\n", flush=True)

    # Use the database factory to get properly configured clients
    from multimodal_librarian.clients.database_factory import get_database_factory
    factory = get_database_factory()
    
    graph_client = factory.get_graph_client()
    await graph_client.connect()
    print("Neo4j connected", flush=True)

    # Connect model server
    from multimodal_librarian.clients.model_server_client import (
        get_model_client,
        initialize_model_client,
    )
    await initialize_model_client()
    model_client = get_model_client()
    print(f"Model server: {model_client is not None and getattr(model_client, 'enabled', False)}", flush=True)

    # Test QueryDecomposer
    from multimodal_librarian.components.kg_retrieval.query_decomposer import (
        QueryDecomposer,
    )
    
    print(f"\n--- Decompose with threshold=0.80 (default) ---", flush=True)
    decomposer = QueryDecomposer(
        neo4j_client=graph_client,
        model_server_client=model_client,
        similarity_threshold=0.80,
    )
    result = await decomposer.decompose(query)
    print(f"Entities: {result.entities}", flush=True)
    print(f"Actions: {result.actions}", flush=True)
    print(f"Subjects: {result.subjects}", flush=True)
    print(f"has_kg_matches: {result.has_kg_matches}", flush=True)
    print(f"Concept matches ({len(result.concept_matches)}):", flush=True)
    for m in result.concept_matches[:15]:
        score = m.get('similarity_score', m.get('match_score', '?'))
        print(f"  - {m.get('name', '?')} (type={m.get('match_type', '?')}, score={score})", flush=True)

    print(f"\n--- Decompose with threshold=0.60 ---", flush=True)
    decomposer2 = QueryDecomposer(
        neo4j_client=graph_client,
        model_server_client=model_client,
        similarity_threshold=0.60,
    )
    result2 = await decomposer2.decompose(query)
    print(f"has_kg_matches: {result2.has_kg_matches}", flush=True)
    print(f"Concept matches ({len(result2.concept_matches)}):", flush=True)
    for m in result2.concept_matches[:15]:
        score = m.get('similarity_score', m.get('match_score', '?'))
        print(f"  - {m.get('name', '?')} (type={m.get('match_type', '?')}, score={score})", flush=True)

    # Also test lexical matching directly
    print(f"\n--- Direct lexical matching ---", flush=True)
    lexical = await decomposer._find_entity_matches(query)
    print(f"Lexical matches ({len(lexical)}):", flush=True)
    for m in lexical[:15]:
        score = m.get('match_score', '?')
        print(f"  - {m.get('name', '?')} (score={score})", flush=True)

    await graph_client.disconnect()
    print("\nDone.", flush=True)

asyncio.run(main())
