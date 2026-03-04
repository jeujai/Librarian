#!/usr/bin/env python3
"""
Repopulate source_chunks for Concept nodes from deleted documents.

These concepts were extracted from duplicate documents that were later deleted.
Their source_chunks pointed to now-deleted chunk IDs. This script:
1. Loads all chunks from the surviving document
2. Finds concepts with empty source_chunks that came from deleted documents
3. For each concept, searches chunk content for the concept name
4. Updates source_chunks with matching chunk IDs from the surviving document
5. Updates source_document to point to the surviving document
"""

import psycopg2
from neo4j import GraphDatabase

PG_DSN = "host=postgres port=5432 dbname=multimodal_librarian user=postgres password=postgres"
NEO4J_URI = "bolt://neo4j:7687"
NEO4J_USER = "neo4j"
NEO4J_PASS = "password"
SURVIVING_DOC_ID = "096f4988-18c7-42a9-8121-e66be14b83aa"
DELETED_DOC_IDS = [
    "2df7ddfb-2a69-4a41-ae0c-bd194522b57c",
    "a4706bdf-32ff-491a-a424-be1258dd330d",
]
BATCH_SIZE = 200


def load_chunks():
    """Load all chunks from the surviving document."""
    conn = psycopg2.connect(PG_DSN)
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT id, content FROM multimodal_librarian.knowledge_chunks "
                "WHERE source_id = %s",
                (SURVIVING_DOC_ID,),
            )
            chunks = [(str(row[0]), row[1].lower()) for row in cur.fetchall()]
            print(f"Loaded {len(chunks)} chunks from surviving document")
            return chunks
    finally:
        conn.close()


def find_matching_chunks(concept_name: str, chunks: list) -> list:
    """Find chunk IDs whose content contains the concept name."""
    name_lower = concept_name.lower()
    # Skip very short or generic names that would match too many chunks
    if len(name_lower) < 3:
        return []
    return [cid for cid, content in chunks if name_lower in content]


def repopulate(chunks: list):
    """Repopulate source_chunks for orphaned concepts."""
    driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASS))

    try:
        with driver.session() as session:
            # Collect all orphaned concept IDs from deleted documents
            result = session.run(
                "MATCH (c:Concept) "
                "WHERE (c.source_chunks IS NULL OR c.source_chunks = '') "
                "  AND c.source_document IN $deleted_ids "
                "RETURN c.concept_id AS concept_id, c.name AS name",
                deleted_ids=DELETED_DOC_IDS,
            )
            orphans = [(r["concept_id"], r["name"]) for r in result]
            print(f"Found {len(orphans)} orphaned concepts from deleted documents")

            linked = 0
            no_match = 0
            skipped = 0

            for i in range(0, len(orphans), BATCH_SIZE):
                batch = orphans[i : i + BATCH_SIZE]
                updates = []

                for concept_id, name in batch:
                    if not name or len(name) < 3:
                        skipped += 1
                        continue

                    matching = find_matching_chunks(name, chunks)
                    if matching:
                        # Cap at 50 to avoid absurdly long strings
                        chunk_str = ",".join(matching[:50])
                        updates.append((concept_id, chunk_str))
                    else:
                        no_match += 1

                if updates:
                    with session.begin_transaction() as tx:
                        for concept_id, chunk_str in updates:
                            tx.run(
                                "MATCH (c:Concept {concept_id: $cid}) "
                                "SET c.source_chunks = $chunks, "
                                "    c.source_document = $doc_id",
                                cid=concept_id,
                                chunks=chunk_str,
                                doc_id=SURVIVING_DOC_ID,
                            )
                            linked += 1
                        tx.commit()

                processed = min(i + BATCH_SIZE, len(orphans))
                if processed % 1000 == 0 or processed == len(orphans):
                    print(
                        f"  {processed}/{len(orphans)} "
                        f"(linked={linked}, no_match={no_match}, skipped={skipped})"
                    )

            print(f"\nDone! Linked={linked}, No match={no_match}, Skipped={skipped}")

    finally:
        driver.close()


def verify():
    """Verify the fix."""
    driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASS))
    try:
        with driver.session() as session:
            # Check allow_dangerous_code specifically
            result = session.run(
                "MATCH (c:Concept) "
                "WHERE c.name IN ['allow_dangerous_code', 'allow_dangerous_code=True', "
                "  'allow_dangerous_requests', 'allow_dangerous_requests=True'] "
                "RETURN c.name AS name, "
                "  CASE WHEN c.source_chunks IS NOT NULL AND c.source_chunks <> '' "
                "    THEN size(split(c.source_chunks, ',')) ELSE 0 END AS chunk_count"
            )
            print("\nTarget concepts:")
            for r in result:
                print(f"  {r['name']}: {r['chunk_count']} chunks")

            # Overall stats
            result = session.run(
                "MATCH (c:Concept) "
                "WHERE c.source_document IN $deleted_ids "
                "RETURN count(c) AS still_orphaned",
                deleted_ids=[
                    "2df7ddfb-2a69-4a41-ae0c-bd194522b57c",
                    "a4706bdf-32ff-491a-a424-be1258dd330d",
                ],
            )
            print(f"Concepts still pointing to deleted docs: {result.single()['still_orphaned']}")

            result = session.run(
                "MATCH (c:Concept) "
                "WHERE c.source_chunks IS NOT NULL AND c.source_chunks <> '' "
                "RETURN count(c) AS with_chunks"
            )
            print(f"Total concepts with source_chunks: {result.single()['with_chunks']}")
    finally:
        driver.close()


if __name__ == "__main__":
    chunks = load_chunks()
    repopulate(chunks)
    verify()
