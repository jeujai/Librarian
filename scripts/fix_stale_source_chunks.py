#!/usr/bin/env python3
"""
Fix stale source_chunks on Neo4j Concept nodes.

After deleting duplicate documents from PostgreSQL, the Concept nodes in Neo4j
still reference chunk IDs from the deleted documents. This script:
1. Loads all valid chunk IDs from PostgreSQL (surviving document)
2. Reads all Concept nodes with source_chunks from Neo4j
3. Filters each node's source_chunks to keep only valid IDs
4. Updates the node in Neo4j (clears if no valid IDs remain)
"""

import psycopg2
from neo4j import GraphDatabase

# Config
PG_DSN = "host=postgres port=5432 dbname=multimodal_librarian user=postgres password=postgres"
NEO4J_URI = "bolt://neo4j:7687"
NEO4J_USER = "neo4j"
NEO4J_PASS = "password"
SURVIVING_DOC_ID = "096f4988-18c7-42a9-8121-e66be14b83aa"
BATCH_SIZE = 500


def load_valid_chunk_ids():
    """Load all chunk IDs from the surviving document in PostgreSQL."""
    conn = psycopg2.connect(PG_DSN)
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT id FROM multimodal_librarian.knowledge_chunks WHERE source_id = %s",
                (SURVIVING_DOC_ID,),
            )
            ids = {str(row[0]) for row in cur.fetchall()}
            print(f"Loaded {len(ids)} valid chunk IDs from PostgreSQL")
            return ids
    finally:
        conn.close()


def fix_source_chunks(valid_ids: set):
    """Fix stale source_chunks on all Concept nodes."""
    driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASS))

    try:
        with driver.session() as session:
            # Count concepts with source_chunks
            result = session.run(
                "MATCH (c:Concept) WHERE c.source_chunks IS NOT NULL AND c.source_chunks <> '' "
                "RETURN count(c) AS total"
            )
            total = result.single()["total"]
            print(f"Found {total} Concept nodes with source_chunks")

            # Process in batches using SKIP/LIMIT
            updated = 0
            cleared = 0
            unchanged = 0
            offset = 0

            while offset < total:
                # Fetch a batch of concepts
                batch_result = session.run(
                    "MATCH (c:Concept) "
                    "WHERE c.source_chunks IS NOT NULL AND c.source_chunks <> '' "
                    "RETURN c.concept_id AS concept_id, c.source_chunks AS source_chunks "
                    "SKIP $offset LIMIT $limit",
                    offset=offset,
                    limit=BATCH_SIZE,
                )
                records = list(batch_result)

                if not records:
                    break

                # Build update batch
                updates = []  # (concept_id, new_source_chunks)

                for record in records:
                    concept_id = record["concept_id"]
                    old_chunks_str = record["source_chunks"]

                    # Parse existing chunk IDs
                    old_ids = [
                        cid.strip()
                        for cid in old_chunks_str.split(",")
                        if cid.strip()
                    ]

                    # Filter to valid only
                    new_ids = [cid for cid in old_ids if cid in valid_ids]

                    if len(new_ids) == len(old_ids):
                        unchanged += 1
                        continue

                    new_chunks_str = ",".join(new_ids) if new_ids else ""
                    updates.append((concept_id, new_chunks_str))

                # Apply updates in a single transaction
                if updates:
                    with session.begin_transaction() as tx:
                        for concept_id, new_chunks_str in updates:
                            if new_chunks_str:
                                tx.run(
                                    "MATCH (c:Concept {concept_id: $cid}) "
                                    "SET c.source_chunks = $chunks",
                                    cid=concept_id,
                                    chunks=new_chunks_str,
                                )
                                updated += 1
                            else:
                                tx.run(
                                    "MATCH (c:Concept {concept_id: $cid}) "
                                    "SET c.source_chunks = ''",
                                    cid=concept_id,
                                )
                                cleared += 1
                        tx.commit()

                offset += BATCH_SIZE
                print(
                    f"  Processed {min(offset, total)}/{total} "
                    f"(updated={updated}, cleared={cleared}, unchanged={unchanged})"
                )

            print(f"\nDone! Updated={updated}, Cleared={cleared}, Unchanged={unchanged}")
            print(f"Total processed: {updated + cleared + unchanged}")

    finally:
        driver.close()


def verify():
    """Quick verification after fix."""
    driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASS))
    try:
        with driver.session() as session:
            # Sample a few concepts and check their source_chunks
            result = session.run(
                "MATCH (c:Concept) "
                "WHERE c.source_chunks IS NOT NULL AND c.source_chunks <> '' "
                "RETURN c.name AS name, c.source_chunks AS source_chunks "
                "LIMIT 5"
            )
            print("\nVerification - sample concepts with source_chunks:")
            for record in result:
                chunks = record["source_chunks"].split(",")
                print(f"  {record['name']}: {len(chunks)} chunk(s)")

            # Count concepts with vs without source_chunks
            result = session.run(
                "MATCH (c:Concept) "
                "RETURN "
                "  sum(CASE WHEN c.source_chunks IS NOT NULL AND c.source_chunks <> '' THEN 1 ELSE 0 END) AS with_chunks, "
                "  sum(CASE WHEN c.source_chunks IS NULL OR c.source_chunks = '' THEN 1 ELSE 0 END) AS without_chunks"
            )
            record = result.single()
            print(f"\nConcepts with source_chunks: {record['with_chunks']}")
            print(f"Concepts without source_chunks: {record['without_chunks']}")
    finally:
        driver.close()


if __name__ == "__main__":
    valid_ids = load_valid_chunk_ids()
    fix_source_chunks(valid_ids)
    verify()
