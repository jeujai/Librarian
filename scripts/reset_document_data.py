#!/usr/bin/env python3
"""
Reset all document-related data while preserving ConceptNet and YAGO.

This script clears:
  1. PostgreSQL: Truncates all document/chunk/conversation tables
  2. Milvus: Drops and recreates the knowledge_chunks collection
  3. Neo4j: Deletes all Concept and Chunk nodes (preserves ConceptNetConcept + YagoEntity)
  4. MinIO: Empties the 'documents' bucket
  5. Redis: Flushes all keys

After running, you can re-upload a PDF and the full pipeline will run clean.

Usage (from inside librarian-app-1):
    python /app/scripts/reset_document_data.py

Usage (from host):
    docker exec librarian-app-1 python /app/scripts/reset_document_data.py
"""

import sys
import time


def reset_postgres():
    """Truncate all document-related PostgreSQL tables."""
    import psycopg2

    print("\n[1/5] PostgreSQL — truncating tables...")
    conn = psycopg2.connect(
        host="postgres", port=5432,
        dbname="multimodal_librarian", user="postgres", password="postgres",
    )
    conn.autocommit = True
    try:
        with conn.cursor() as cur:
            # Order matters for FK constraints — TRUNCATE CASCADE handles it
            tables = [
                "bridge_chunks",
                "messages",
                "conversation_threads",
                "enrichment_status",
                "export_history",
                "performance_metrics",
                "processing_jobs",
                "user_feedback",
                "knowledge_chunks",
                "knowledge_sources",
            ]
            for table in tables:
                cur.execute(
                    f"TRUNCATE TABLE multimodal_librarian.{table} CASCADE"
                )
                print(f"  Truncated {table}")

            # Verify
            cur.execute(
                "SELECT count(*) FROM multimodal_librarian.knowledge_sources"
            )
            count = cur.fetchone()[0]
            print(f"  Verification: knowledge_sources = {count}")
    finally:
        conn.close()
    print("  PostgreSQL done.")


def reset_milvus():
    """Drop and recreate the knowledge_chunks Milvus collection."""
    from pymilvus import (
        Collection,
        CollectionSchema,
        DataType,
        FieldSchema,
        connections,
        utility,
    )

    print("\n[2/5] Milvus — resetting knowledge_chunks collection...")
    connections.connect(host="milvus", port="19530")

    collection_name = "knowledge_chunks"

    if utility.has_collection(collection_name):
        utility.drop_collection(collection_name)
        print(f"  Dropped collection '{collection_name}'")
    else:
        print(f"  Collection '{collection_name}' not found, creating fresh")

    # Recreate with the same schema the app uses
    fields = [
        FieldSchema(name="id", dtype=DataType.VARCHAR, is_primary=True, max_length=512),
        FieldSchema(name="vector", dtype=DataType.FLOAT_VECTOR, dim=768),
        FieldSchema(name="metadata", dtype=DataType.JSON),
    ]
    schema = CollectionSchema(fields=fields, description="Knowledge chunks with embeddings")
    collection = Collection(name=collection_name, schema=schema)

    # Create IVF_FLAT index matching existing config
    index_params = {
        "metric_type": "L2",
        "index_type": "IVF_FLAT",
        "params": {"nlist": 1024},
    }
    collection.create_index(field_name="vector", index_params=index_params)
    collection.load()

    print(f"  Recreated collection '{collection_name}' with index")
    print(f"  Entities: {collection.num_entities}")
    connections.disconnect("default")
    print("  Milvus done.")


def reset_neo4j():
    """Delete all Concept and Chunk nodes, preserving ConceptNetConcept and YagoEntity."""
    from neo4j import GraphDatabase

    print("\n[3/5] Neo4j — deleting Concept and Chunk nodes...")
    driver = GraphDatabase.driver("bolt://neo4j:7687", auth=("neo4j", "password"))

    try:
        with driver.session() as session:
            # Drop the vector index so ensure_indexes can recreate it at 768 dims
            try:
                session.run("DROP INDEX concept_embedding_index IF EXISTS")
                print("  Dropped concept_embedding_index")
            except Exception as e:
                print(f"  Could not drop concept_embedding_index: {e}")

            # Count before
            result = session.run("MATCH (c:Concept) RETURN count(c) AS cnt")
            concept_before = result.single()["cnt"]
            result = session.run("MATCH (ch:Chunk) RETURN count(ch) AS cnt")
            chunk_before = result.single()["cnt"]
            print(f"  Concept nodes before: {concept_before}")
            print(f"  Chunk nodes before: {chunk_before}")

            # Delete Concept nodes in batches (DETACH DELETE removes EXTRACTED_FROM edges)
            # Use small batches (1000) to avoid Neo4j memory pool limits
            total_deleted = 0
            while True:
                result = session.run(
                    "MATCH (c:Concept) "
                    "WITH c LIMIT 1000 "
                    "DETACH DELETE c "
                    "RETURN count(*) AS deleted"
                )
                deleted = result.single()["deleted"]
                if deleted == 0:
                    break
                total_deleted += deleted
                if total_deleted % 10000 == 0:
                    print(f"  Deleted {total_deleted} Concept nodes so far...")

            print(f"  Total Concept nodes deleted: {total_deleted}")

            # Delete Chunk nodes in batches
            total_chunks_deleted = 0
            while True:
                result = session.run(
                    "MATCH (ch:Chunk) "
                    "WITH ch LIMIT 1000 "
                    "DETACH DELETE ch "
                    "RETURN count(*) AS deleted"
                )
                deleted = result.single()["deleted"]
                if deleted == 0:
                    break
                total_chunks_deleted += deleted
                if total_chunks_deleted % 10000 == 0:
                    print(f"  Deleted {total_chunks_deleted} Chunk nodes so far...")

            print(f"  Total Chunk nodes deleted: {total_chunks_deleted}")

            # Verify preserved namespaces
            result = session.run(
                "MATCH (n) RETURN labels(n) AS labels, count(n) AS cnt "
                "ORDER BY cnt DESC"
            )
            print("  Remaining nodes:")
            for record in result:
                print(f"    {record['labels']}: {record['cnt']}")
    finally:
        driver.close()
    print("  Neo4j done.")


def reset_minio():
    """Empty the 'documents' bucket in MinIO."""
    import boto3

    print("\n[4/5] MinIO — emptying documents bucket...")
    s3 = boto3.client(
        "s3",
        endpoint_url="http://minio:9000",
        aws_access_key_id="minioadmin",
        aws_secret_access_key="minioadmin",
    )

    bucket = "documents"
    deleted_count = 0

    # List and delete all objects
    paginator = s3.get_paginator("list_objects_v2")
    for page in paginator.paginate(Bucket=bucket):
        contents = page.get("Contents", [])
        if not contents:
            break
        objects = [{"Key": obj["Key"]} for obj in contents]
        s3.delete_objects(Bucket=bucket, Delete={"Objects": objects})
        deleted_count += len(objects)
        print(f"  Deleted {deleted_count} objects...")

    print(f"  Total objects deleted: {deleted_count}")
    print("  MinIO done.")


def reset_redis():
    """Flush all Redis keys."""
    import redis

    print("\n[5/5] Redis — flushing all keys...")
    r = redis.Redis(host="redis", port=6379, db=0)
    before = r.dbsize()
    r.flushall()
    print(f"  Flushed {before} keys")
    print("  Redis done.")


def main():
    print("=" * 60)
    print("  DOCUMENT DATA RESET")
    print("  Preserves: ConceptNet, YAGO, user accounts, sessions")
    print("=" * 60)

    # Confirmation
    if "--yes" not in sys.argv:
        print("\nThis will DELETE all documents, chunks, vectors,")
        print("concepts, conversations, and cached data.")
        print("\nRun with --yes to skip this prompt.")
        answer = input("\nProceed? [y/N] ").strip().lower()
        if answer != "y":
            print("Aborted.")
            return

    start = time.time()

    reset_postgres()
    reset_milvus()
    reset_neo4j()
    reset_minio()
    reset_redis()

    elapsed = time.time() - start
    print(f"\n{'=' * 60}")
    print(f"  Reset complete in {elapsed:.1f}s")
    print(f"  Ready for fresh document upload.")
    print(f"{'=' * 60}")


if __name__ == "__main__":
    main()
