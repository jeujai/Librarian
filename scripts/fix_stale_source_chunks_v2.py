#!/usr/bin/env python3
"""
Fix stale source_chunks on Neo4j Concept nodes (v2 - no pagination issues).

Collects ALL concept_ids first, then processes them in batches by ID.
"""

import psycopg2
from neo4j import GraphDatabase

PG_DSN = "host=postgres port=5432 dbname=multimodal_librarian user=postgres password=postgres"
NEO4J_URI = "bolt://neo4j:7687"
NEO4J_USER = "neo4j"
NEO4J_PASS = "password"
SURVIVING_DOC_ID = "096f4988-18c7-42a9-8121-e66be14b83aa"
BATCH_SIZE = 200


def load_valid_chunk_ids():
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
    driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASS))

    try:
        with driver.session() as session:
            # Step 1: Collect ALL concept_ids that have source_chunks
            result = session.run(
                "MATCH (c:Concept) "
                "WHERE c.source_chunks IS NOT NULL AND c.source_chunks <> '' "
                "RETURN c.concept_id AS concept_id"
            )
            all_concept_ids = [r["concept_id"] for r in result]
            print(f"Collected {len(all_concept_ids)} concept IDs to process")

            updated = 0
            cleared = 0
            unchanged = 0

            # Step 2: Process in batches by concept_id
            for i in range(0, len(all_concept_ids), BATCH_SIZE):
                batch_ids = all_concept_ids[i : i + BATCH_SIZE]

                # Fetch source_chunks for this batch
                batch_result = session.run(
                    "MATCH (c:Concept) "
                    "WHERE c.concept_id IN $ids "
                    "RETURN c.concept_id AS concept_id, c.source_chunks AS source_chunks",
                    ids=batch_ids,
                )

                updates = []
                for record in batch_result:
                    concept_id = record["concept_id"]
                    old_str = record["source_chunks"] or ""

                    if not old_str:
                        unchanged += 1
                        continue

                    old_ids = [cid.strip() for cid in old_str.split(",") if cid.strip()]
                    new_ids = [cid for cid in old_ids if cid in valid_ids]

                    if len(new_ids) == len(old_ids):
                        unchanged += 1
                        continue

                    updates.append((concept_id, ",".join(new_ids) if new_ids else ""))

                # Apply updates
                if updates:
                    with session.begin_transaction() as tx:
                        for concept_id, new_str in updates:
                            tx.run(
                                "MATCH (c:Concept {concept_id: $cid}) SET c.source_chunks = $chunks",
                                cid=concept_id,
                                chunks=new_str,
                            )
                            if new_str:
                                updated += 1
                            else:
                                cleared += 1
                        tx.commit()

                processed = min(i + BATCH_SIZE, len(all_concept_ids))
                if processed % 1000 == 0 or processed == len(all_concept_ids):
                    print(f"  {processed}/{len(all_concept_ids)} (updated={updated}, cleared={cleared}, unchanged={unchanged})")

            print(f"\nDone! Updated={updated}, Cleared={cleared}, Unchanged={unchanged}")

    finally:
        driver.close()


def verify(valid_ids: set):
    driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASS))
    try:
        with driver.session() as session:
            # Check for any remaining stale IDs
            result = session.run(
                "MATCH (c:Concept) "
                "WHERE c.source_chunks IS NOT NULL AND c.source_chunks <> '' "
                "RETURN c.source_chunks AS sc LIMIT 100"
            )
            stale_found = 0
            total_checked = 0
            for record in result:
                for cid in record["sc"].split(","):
                    cid = cid.strip()
                    if cid:
                        total_checked += 1
                        if cid not in valid_ids:
                            stale_found += 1

            print(f"\nVerification: checked {total_checked} chunk refs across 100 concepts")
            print(f"Stale references found: {stale_found}")

            # Final counts
            result = session.run(
                "MATCH (c:Concept) "
                "RETURN "
                "  sum(CASE WHEN c.source_chunks IS NOT NULL AND c.source_chunks <> '' THEN 1 ELSE 0 END) AS with_chunks, "
                "  sum(CASE WHEN c.source_chunks IS NULL OR c.source_chunks = '' THEN 1 ELSE 0 END) AS without_chunks"
            )
            r = result.single()
            print(f"Concepts with source_chunks: {r['with_chunks']}")
            print(f"Concepts without source_chunks: {r['without_chunks']}")
    finally:
        driver.close()


if __name__ == "__main__":
    valid_ids = load_valid_chunk_ids()
    fix_source_chunks(valid_ids)
    verify(valid_ids)
