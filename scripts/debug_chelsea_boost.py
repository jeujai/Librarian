"""Debug: show what entities/actions are being used for boost."""
import asyncio
import re
import sys

sys.path.insert(0, "/app/src")

async def main():
    from multimodal_librarian.clients.model_server_client import ModelServerClient
    from multimodal_librarian.clients.neo4j_client import Neo4jClient
    from multimodal_librarian.components.kg_retrieval import QueryDecomposer

    neo4j = Neo4jClient(uri="bolt://neo4j:7687", user="neo4j", password="password")
    await neo4j.connect()
    model = ModelServerClient()

    decomposer = QueryDecomposer(neo4j_client=neo4j, model_server_client=model)
    d = await decomposer.decompose("What did our team observe at Chelsea?")

    print(f"entities ({len(d.entities)}): {d.entities}")
    print(f"actions ({len(d.actions)}): {d.actions}")
    print(f"subjects ({len(d.subjects)}): {d.subjects}")

    # What the reranker uses for boost
    boost_entities = {e.lower() for e in d.entities if len(e) > 2}
    boost_actions = {a.lower() for a in d.actions if len(a) > 2}
    print(f"\nboost_entities ({len(boost_entities)}): {sorted(boost_entities)}")
    print(f"boost_actions ({len(boost_actions)}): {sorted(boost_actions)}")

    # Check: how many of these entities match a generic chunk?
    test_content = "we saw that the model performs well when we examine the data"
    content_lower = test_content.lower()
    matched = [e for e in boost_entities if e in content_lower]
    print(f"\nTest content: '{test_content}'")
    print(f"Matched entities: {matched}")

    await neo4j.close()

asyncio.run(main())
