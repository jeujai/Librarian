#!/usr/bin/env python3
"""
Backfill Milvus metadata with page_number from PostgreSQL.

Connects to PostgreSQL to get chunk_id -> page_number mapping,
then updates Milvus metadata JSON for chunks missing page_number.

Uses ID-based batching (not offset) to avoid the 16,384 offset limit.
"""

import json
import sys

import psycopg2
from pymilvus import MilvusClient

# Config
PG_DSN = "host=postgres dbname=multimodal_librarian user=postgres password=postgres"
MILVUS_URI = "http://milvus:19530"
COLLECTION = "knowledge_chunks"
BATCH_SIZE = 500


def main():
    # 1. Get page_number mapping from PostgreSQL
    print("Connecting to PostgreSQL...")
    pg = psycopg2.connect(PG_DSN)
    cur = pg.cursor()
    
    cur.execute("""
        SELECT id::text, location_reference
        FROM multimodal_librarian.knowledge_chunks
        WHERE location_reference IS NOT NULL
          AND location_reference != ''
    """)
    
    pg_map = {}
    for chunk_id, loc_ref in cur.fetchall():
        try:
            page = int(loc_ref)
            pg_map[chunk_id] = page
        except (ValueError, TypeError):
            pass
    
    cur.close()
    pg.close()
    print(f"Got {len(pg_map)} chunks with page numbers from PostgreSQL")
    
    if not pg_map:
        print("No page numbers to backfill.")
        return
    
    # 2. Connect to Milvus and load collection
    print("Connecting to Milvus...")
    mc = MilvusClient(uri=MILVUS_URI)
    
    print(f"Loading collection '{COLLECTION}'...")
    mc.load_collection(COLLECTION)
    print("Collection loaded.")
    
    # 3. Process in batches by ID
    all_ids = list(pg_map.keys())
    updated = 0
    skipped = 0
    errors = 0
    
    for i in range(0, len(all_ids), BATCH_SIZE):
        batch_ids = all_ids[i:i + BATCH_SIZE]
        batch_num = i // BATCH_SIZE + 1
        total_batches = (len(all_ids) + BATCH_SIZE - 1) // BATCH_SIZE
        
        try:
            # Query Milvus for these specific IDs
            results = mc.get(
                collection_name=COLLECTION,
                ids=batch_ids,
                output_fields=["metadata"]
            )
            
            if not results:
                continue
            
            # Build upsert data for chunks that need updating
            to_upsert = []
            for row in results:
                chunk_id = row["id"]
                meta = row.get("metadata", {})
                
                if isinstance(meta, str):
                    try:
                        meta = json.loads(meta)
                    except json.JSONDecodeError:
                        meta = {}
                
                # Skip if already has page_number
                if meta.get("page_number") is not None:
                    skipped += 1
                    continue
                
                # Add page_number from PG
                pg_page = pg_map.get(chunk_id)
                if pg_page is not None:
                    meta["page_number"] = pg_page
                    to_upsert.append({
                        "id": chunk_id,
                        "metadata": meta
                    })
            
            if to_upsert:
                # Need vectors for upsert - query them
                vec_results = mc.get(
                    collection_name=COLLECTION,
                    ids=[r["id"] for r in to_upsert],
                    output_fields=["vector"]
                )
                vec_map = {r["id"]: r["vector"] for r in vec_results}
                
                upsert_data = []
                for item in to_upsert:
                    vec = vec_map.get(item["id"])
                    if vec:
                        upsert_data.append({
                            "id": item["id"],
                            "vector": vec,
                            "metadata": item["metadata"]
                        })
                
                if upsert_data:
                    mc.upsert(
                        collection_name=COLLECTION,
                        data=upsert_data
                    )
                    updated += len(upsert_data)
            
            print(f"  Batch {batch_num}/{total_batches}: updated={len(to_upsert)}, skipped(already has page)={skipped}")
            
        except Exception as e:
            errors += 1
            print(f"  Batch {batch_num} error: {e}")
            if errors > 5:
                print("Too many errors, stopping.")
                break
    
    print(f"\nDone. Updated: {updated}, Skipped: {skipped}, Errors: {errors}")


if __name__ == "__main__":
    main()
