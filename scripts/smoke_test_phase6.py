#!/usr/bin/env python
"""Phase 6 (content privacy scope) smoke tests against the live local stack.

Exercises the real code paths for the privacy data plane:

  1. Write path      — ``_persist_concepts`` stamps ``scope``/``owner_id``/
                       ``concept_id`` on private concepts and EXTRACTED_FROM
                       edges still resolve (no ``concept_id_map`` mismatch).
  2. Retrieval       — ``_search_concept_index`` scope filter: owner sees own
                       private + public; another user and ``None`` see public
                       only.
  3. Traversal       — ``RelationshipTraverser`` does not leak another user's
                       private concept through a SIMILAR_TO hop.
  4. Deletion        — the guarded orphan predicate removes only the owner's
                       private concepts; other users' private + non-orphan
                       public concepts survive.

All fixtures are created under a unique ``zzz_smoke_*`` prefix and removed in a
``finally`` block. Read-only tests touch only those fixtures; the deletion test
uses the exact Step 3 predicate with an added name-prefix guard so it cannot
collide with the pre-existing orphaned public concepts in the corpus.

Requires the local stack (Neo4j bolt://localhost:7687, model server
http://localhost:8001) to be running. Run with:

    venv/bin/python scripts/smoke_test_phase6.py
"""

import asyncio
import logging
import sys
import time
import uuid

# Silence the verbose service-health logging so results are readable.
logging.basicConfig(level=logging.WARNING)

from multimodal_librarian.clients.model_server_client import ModelServerClient  # noqa: E402
from multimodal_librarian.clients.neo4j_client import Neo4jClient  # noqa: E402
from multimodal_librarian.components.kg_retrieval.query_decomposer import (  # noqa: E402
    QueryDecomposer,
)
from multimodal_librarian.components.kg_retrieval.relationship_traverser import (  # noqa: E402
    RelationshipTraverser,
)
from multimodal_librarian.models.knowledge_graph import ConceptNode  # noqa: E402
from multimodal_librarian.services.conversation_knowledge_service import (  # noqa: E402
    ConversationKnowledgeService,
)


RESULTS = []


def check(name: str, ok: bool, detail: str = "") -> None:
    RESULTS.append((name, ok, detail))
    tag = "PASS" if ok else "FAIL"
    print(f"  [{tag}] {name}" + (f"  -- {detail}" if detail else ""))


async def connect_neo4j() -> Neo4jClient:
    client = Neo4jClient(uri="bolt://localhost:7687", user="neo4j", password="password")
    await client.connect()
    return client


async def test_write_path(neo4j, model, prefix: str, user_a: str) -> None:
    print("\n== Test 1: write path (scope/owner_id/concept_id stamping + EXTRACTED_FROM) ==")
    svc = ConversationKnowledgeService(
        conversation_manager=None,
        vector_store=None,
        model_server_client=model,
        neo4j_client=neo4j,
    )

    name_a = f"{prefix}_privconcept"
    name_pub = f"{prefix}_pubconcept"
    chunk_a = f"{prefix}_chunk_a"
    chunk_pub = f"{prefix}_chunk_pub"

    concepts = [
        ConceptNode(
            concept_id=f"private:{name_a.lower()}",
            concept_name=name_a,
            concept_type="ENTITY",
            confidence=0.9,
            source_chunks=[chunk_a],
            scope="private",
            owner_id=user_a,
            provenance="corpus-mined",
        ),
        ConceptNode(
            concept_id=f"public:{name_pub.lower()}",
            concept_name=name_pub,
            concept_type="ENTITY",
            confidence=0.9,
            source_chunks=[chunk_pub],
            scope="public",
            owner_id=None,
            provenance="corpus-mined",
        ),
    ]

    now_ts = time.strftime("%Y-%m-%dT%H:%M:%S")
    concept_id_map = await svc._persist_concepts(
        concepts, thread_id=f"{prefix}_thread", now_ts=now_ts
    )
    check("persist returned both concept ids", len(concept_id_map) >= 2,
          f"map keys={sorted(concept_id_map.keys())}")

    rows = await neo4j.execute_query(
        """
        MATCH (c:Concept {name_lower: $name_lower})
        RETURN c.scope AS scope, c.owner_id AS owner_id,
               c.concept_id AS concept_id, c.embedding IS NOT NULL AS has_embedding
        """,
        {"name_lower": name_a.lower()},
    )
    check("private node exists", bool(rows), f"rows={rows}")
    if rows:
        r = rows[0]
        check("private scope stamped", r["scope"] == "private", f"scope={r['scope']}")
        check("private owner_id stamped", r["owner_id"] == user_a, f"owner_id={r['owner_id']}")
        check("private concept_id stamped", r["concept_id"] == f"private:{name_a.lower()}",
              f"concept_id={r['concept_id']}")
        check("private embedding present", r["has_embedding"] is True, f"has_embedding={r['has_embedding']}")

    pub_rows = await neo4j.execute_query(
        "MATCH (c:Concept {name_lower: $name_lower}) RETURN c.scope AS scope, c.concept_id AS concept_id",
        {"name_lower": name_pub.lower()},
    )
    check("public node exists", bool(pub_rows), f"rows={pub_rows}")
    if pub_rows:
        check("public scope stamped", pub_rows[0]["scope"] == "public",
              f"scope={pub_rows[0]['scope']}")
        check("public concept_id stamped",
              pub_rows[0]["concept_id"] == f"public:{name_pub.lower()}",
              f"concept_id={pub_rows[0]['concept_id']}")

    # EXTRACTED_FROM edges must resolve for both (the concept_id_map mismatch risk).
    ef = await neo4j.execute_query(
        """
        MATCH (c:Concept {name_lower: $name_lower})-[r:EXTRACTED_FROM]->(ch:Chunk {chunk_id: $chunk_id})
        RETURN count(r) AS cnt
        """,
        {"name_lower": name_a.lower(), "chunk_id": chunk_a},
    )
    check("private EXTRACTED_FROM edge resolves", bool(ef) and ef[0]["cnt"] == 1,
          f"cnt={ef[0]['cnt'] if ef else None}")

    ef_pub = await neo4j.execute_query(
        """
        MATCH (c:Concept {name_lower: $name_lower})-[r:EXTRACTED_FROM]->(ch:Chunk {chunk_id: $chunk_id})
        RETURN count(r) AS cnt
        """,
        {"name_lower": name_pub.lower(), "chunk_id": chunk_pub},
    )
    check("public EXTRACTED_FROM edge resolves", bool(ef_pub) and ef_pub[0]["cnt"] == 1,
          f"cnt={ef_pub[0]['cnt'] if ef_pub else None}")


async def test_retrieval(neo4j, model, prefix: str, user_a: str, user_b: str) -> None:
    print("\n== Test 2: retrieval scope filter ==")
    name_a = f"{prefix}_privconcept"
    name_pub = f"{prefix}_pubconcept"
    cid_a = f"private:{name_a.lower()}"
    cid_pub = f"public:{name_pub.lower()}"

    decomposer = QueryDecomposer(neo4j_client=neo4j, model_server_client=model)
    emb_a = (await model.generate_embeddings([name_a]))[0]
    emb_pub = (await model.generate_embeddings([name_pub]))[0]

    def ids(matches):
        return {m.get("concept_id") for m in matches}

    r_owner = await decomposer._search_concept_index(emb_a, 0.0, 10, user_a)
    check("owner sees own private concept", cid_a in ids(r_owner),
          f"matched={sorted(ids(r_owner))}")

    r_other = await decomposer._search_concept_index(emb_a, 0.0, 10, user_b)
    check("other user does NOT see private concept", cid_a not in ids(r_other),
          f"matched={sorted(ids(r_other))}")

    r_none = await decomposer._search_concept_index(emb_a, 0.0, 10, None)
    check("user_id=None does NOT see private concept", cid_a not in ids(r_none),
          f"matched={sorted(ids(r_none))}")

    r_pub_other = await decomposer._search_concept_index(emb_pub, 0.0, 10, user_b)
    check("other user sees public concept", cid_pub in ids(r_pub_other),
          f"matched={sorted(ids(r_pub_other))}")

    r_pub_none = await decomposer._search_concept_index(emb_pub, 0.0, 10, None)
    check("user_id=None sees public concept", cid_pub in ids(r_pub_none),
          f"matched={sorted(ids(r_pub_none))}")


async def test_traversal(neo4j, prefix: str, user_a: str, user_b: str) -> None:
    print("\n== Test 3: traversal does not leak other user's private concept ==")
    name_pub = f"{prefix}_pubconcept"
    name_a = f"{prefix}_privconcept"
    cid_pub = f"public:{name_pub.lower()}"
    cid_a = f"private:{name_a.lower()}"
    chunk_a = f"{prefix}_chunk_a"

    # Link the public concept to the private concept via SIMILAR_TO.
    await neo4j.execute_write_query(
        """
        MATCH (a:Concept {concept_id: $cid_pub}), (b:Concept {concept_id: $cid_a})
        MERGE (a)-[r:SIMILAR_TO]->(b)
        RETURN count(r) AS cnt
        """,
        {"cid_pub": cid_pub, "cid_a": cid_a},
    )

    traverser = RelationshipTraverser(neo4j_client=neo4j, timeout_seconds=10.0)
    matches = [{"concept_id": cid_pub}, {"concept_id": cid_a}]

    r_owner = await traverser.traverse(matches, user_id=user_a)
    owner_chunks = set(r_owner.chunk_concept_connections.keys())
    check("owner traversal reaches own private chunk", chunk_a in owner_chunks,
          f"chunks={sorted(owner_chunks)}")

    r_other = await traverser.traverse(matches, user_id=user_b)
    other_chunks = set(r_other.chunk_concept_connections.keys())
    check("other user traversal does NOT reach private chunk", chunk_a not in other_chunks,
          f"chunks={sorted(other_chunks)}")


async def test_deletion(neo4j, prefix: str, user_a: str, user_b: str) -> None:
    print("\n== Test 4: guarded orphan-deletion predicate ==")
    a_orphan = f"{prefix}_orphan_a"
    b_orphan = f"{prefix}_orphan_b"
    pub_orphan = f"{prefix}_orphan_pub"
    pub_kept = f"{prefix}_kept_pub"
    kept_chunk = f"{prefix}_kept_chunk"

    # Create orphan fixtures directly (no EXTRACTED_FROM, no SAME_AS).
    await neo4j.execute_write_query(
        """
        UNWIND $rows AS row
        MERGE (c:Concept {name_lower: toLower(row.name), scope: row.scope})
        ON CREATE SET c.name = row.name,
                      c.name_lower = toLower(row.name),
                      c.scope = row.scope,
                      c.owner_id = row.owner_id,
                      c.concept_id = row.concept_id,
                      c.bridge_status = 'emergent',
                      c.provenance = 'corpus-mined'
        """,
        {"rows": [
            {"name": a_orphan, "scope": "private", "owner_id": user_a,
             "concept_id": f"private:{a_orphan.lower()}"},
            {"name": b_orphan, "scope": "private", "owner_id": user_b,
             "concept_id": f"private:{b_orphan.lower()}"},
            {"name": pub_orphan, "scope": "public", "owner_id": None,
             "concept_id": f"public:{pub_orphan.lower()}"},
        ]},
    )
    # Non-orphan public concept: has an EXTRACTED_FROM edge, so must survive.
    await neo4j.execute_write_query(
        """
        MERGE (c:Concept {name_lower: $nl, scope: 'public'})
        ON CREATE SET c.name = $name, c.name_lower = $nl, c.scope = 'public',
                      c.concept_id = $cid, c.bridge_status = 'emergent',
                      c.provenance = 'corpus-mined'
        MERGE (ch:Chunk {chunk_id: $chunk_id})
        MERGE (c)-[r:EXTRACTED_FROM]->(ch)
        """,
        {"nl": pub_kept.lower(), "name": pub_kept,
         "cid": f"public:{pub_kept.lower()}", "chunk_id": kept_chunk},
    )

    # The exact Step 3 predicate, scoped to fixtures with a name-prefix guard so
    # it cannot touch pre-existing orphaned public concepts in the corpus.
    await neo4j.execute_write_query(
        """
        MATCH (c:Concept)
        WHERE c.name_lower STARTS WITH $prefix
          AND NOT EXISTS { MATCH (c)-[:EXTRACTED_FROM]->() }
          AND NOT EXISTS { MATCH (c)<-[:SAME_AS]-() }
          AND c.bridge_status <> 'canonical'
          AND c.provenance = 'corpus-mined'
          AND (c.scope = 'public'
               OR (c.scope = 'private' AND c.owner_id = $owner_id))
        DETACH DELETE c
        """,
        {"prefix": f"{prefix}_orphan", "owner_id": user_a},
    )

    async def count(name_lower: str) -> int:
        r = await neo4j.execute_query(
            "MATCH (c:Concept {name_lower: $nl}) RETURN count(c) AS n",
            {"nl": name_lower},
        )
        return r[0]["n"] if r else 0

    check("owner's private orphan removed", await count(a_orphan.lower()) == 0,
          f"remaining={await count(a_orphan.lower())}")
    check("other user's private orphan survives", await count(b_orphan.lower()) == 1,
          f"remaining={await count(b_orphan.lower())}")
    check("public orphan removed", await count(pub_orphan.lower()) == 0,
          f"remaining={await count(pub_orphan.lower())}")
    check("non-orphan public concept survives", await count(pub_kept.lower()) == 1,
          f"remaining={await count(pub_kept.lower())}")


async def cleanup(neo4j, prefix: str) -> None:
    try:
        await neo4j.execute_write_query(
            "MATCH (c:Concept) WHERE c.name_lower STARTS WITH $prefix DETACH DELETE c",
            {"prefix": prefix},
        )
        await neo4j.execute_write_query(
            "MATCH (ch:Chunk) WHERE ch.chunk_id STARTS WITH $prefix DETACH DELETE ch",
            {"prefix": prefix},
        )
    except Exception as e:  # noqa: BLE001
        print(f"  [WARN] cleanup failed: {e}")


async def main() -> int:
    prefix = f"zzz_smoke_{int(time.time())}_{uuid.uuid4().hex[:6]}"
    user_a = f"smoke_user_a_{prefix.rsplit('_', 1)[-1]}"
    user_b = f"smoke_user_b_{prefix.rsplit('_', 1)[-1]}"

    neo4j = None
    model = None
    try:
        neo4j = await connect_neo4j()
        model = ModelServerClient(base_url="http://localhost:8001", timeout=30.0)

        # Pre-flight: report corpus state for context.
        pre = await neo4j.execute_query(
            """
            MATCH (c:Concept)
            WHERE NOT EXISTS { MATCH (c)-[:EXTRACTED_FROM]->() }
              AND NOT EXISTS { MATCH (c)<-[:SAME_AS]-() }
              AND c.bridge_status <> 'canonical'
              AND c.provenance = 'corpus-mined'
            RETURN c.scope AS scope, count(*) AS n
            """
        )
        print(f"Pre-flight orphan corpus-mined concepts: {pre}")

        await test_write_path(neo4j, model, prefix, user_a)
        await test_retrieval(neo4j, model, prefix, user_a, user_b)
        await test_traversal(neo4j, prefix, user_a, user_b)
        await test_deletion(neo4j, prefix, user_a, user_b)

    finally:
        if neo4j is not None:
            await cleanup(neo4j, prefix)
            await neo4j.close()
        if model is not None:
            await model.close()

    print("\n" + "=" * 60)
    passed = sum(1 for _, ok, _ in RESULTS if ok)
    failed = [r for r in RESULTS if not r[1]]
    print(f"SMOKE RESULTS: {passed}/{len(RESULTS)} passed")
    if failed:
        for name, _, detail in failed:
            print(f"  FAILED: {name} -- {detail}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
