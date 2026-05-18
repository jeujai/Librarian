#!/usr/bin/env python3
"""
Repopulate Milvus from Postgres.

Reads all knowledge_chunks and bridge_chunks from Postgres,
generates embeddings via the model-server, and inserts them
into a freshly created Milvus collection using the runtime
schema: id (VARCHAR), vector (FLOAT_VECTOR 768), metadata (JSON).

Usage:
    docker exec librarian-app-1 python /app/scripts/repopulate_milvus.py
"""

import json
import logging
import sys
import time
from datetime import datetime

import psycopg2
import requests
from pymilvus import (
    Collection,
    CollectionSchema,
    DataType,
    FieldSchema,
    connections,
    utility,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

MILVUS_HOST = "milvus"
MILVUS_PORT = "19530"
COLLECTION_NAME = "knowledge_chunks"
EMBEDDING_DIM = 768  # BAAI/bge-base-en-v1.5
MODEL_SERVER_URL = "http://model-server:8001/embeddings"
BATCH_SIZE = 200  # texts per embedding request

PG_HOST = "postgres"
PG_PORT = 5432
PG_USER = "postgres"
PG_PASSWORD = "postgres"
PG_DB = "multimodal_librarian"
PG_SCHEMA = "multimodal_librarian"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def create_collection() -> Collection:
    """Create the collection with the runtime schema (id, vector, metadata)."""
    if utility.has_collection(COLLECTION_NAME):
        logger.info("Dropping existing collection %s", COLLECTION_NAME)
        utility.drop_collection(COLLECTION_NAME)

    fields = [
        FieldSchema("id", DataType.VARCHAR, max_length=512, is_primary=True),
        FieldSchema("vector", DataType.FLOAT_VECTOR, dim=EMBEDDING_DIM),
        FieldSchema("metadata", DataType.JSON),
    ]
    schema = CollectionSchema(fields, description="Knowledge chunks with embeddings")
    col = Collection(COLLECTION_NAME, schema, consistency_level="Strong")
    logger.info("Created collection %s (id, vector, metadata)", COLLECTION_NAME)
    return col


def embed_texts(texts: list[str]) -> list[list[float]]:
    """Call the model-server to embed a batch of texts."""
    resp = requests.post(
        MODEL_SERVER_URL,
        json={"texts": texts, "normalize": True},
        timeout=300,
    )
    resp.raise_for_status()
    return resp.json()["embeddings"]


def fetch_knowledge_chunks(cur) -> list[dict]:
    """Fetch all knowledge_chunks from Postgres."""
    cur.execute(f"""
        SELECT kc.id::text, kc.source_id::text, kc.content,
               kc.chunk_index, kc.content_type::text,
               kc.metadata, kc.created_at,
               ks.title AS source_title
        FROM {PG_SCHEMA}.knowledge_chunks kc
        LEFT JOIN {PG_SCHEMA}.knowledge_sources ks ON kc.source_id = ks.id
        ORDER BY kc.id
    """)
    rows = cur.fetchall()
    chunks = []
    for row in rows:
        pg_metadata = row[5] if isinstance(row[5], dict) else {}
        metadata = {
            "content": row[2] or "",
            "content_type": row[4] or "text",
            "source_id": row[1] or "",
            "chunk_index": row[3] or 0,
            "title": row[7] or pg_metadata.get("title", ""),
            "stored_at": datetime.utcnow().isoformat(),
        }
        # Merge any extra metadata from Postgres
        for k, v in pg_metadata.items():
            if k not in metadata:
                metadata[k] = v

        chunks.append({
            "id": row[0],
            "content": row[2] or "",
            "metadata": metadata,
        })
    return chunks


def fetch_bridge_chunks(cur) -> list[dict]:
    """Fetch all bridge_chunks from Postgres."""
    cur.execute(f"""
        SELECT bridge_id, source_chunk_id::text, content,
               confidence_score, created_at
        FROM {PG_SCHEMA}.bridge_chunks
        ORDER BY id
    """)
    rows = cur.fetchall()
    chunks = []
    for row in rows:
        bridge_id = row[0] or ""
        chunk_id = f"bridge_{bridge_id}" if bridge_id else f"bridge_{row[1]}"
        metadata = {
            "content": row[2] or "",
            "content_type": "bridge",
            "source_id": row[1] or "",
            "chunk_index": 0,
            "confidence_score": row[3] or 0.0,
            "stored_at": datetime.utcnow().isoformat(),
        }
        chunks.append({
            "id": chunk_id,
            "content": row[2] or "",
            "metadata": metadata,
        })
    return chunks


def insert_batch(col: Collection, chunks: list[dict], embeddings: list[list[float]]):
    """Insert a batch into Milvus using the runtime schema."""
    data = [
        [c["id"] for c in chunks],          # id
        embeddings,                           # vector
        [c["metadata"] for c in chunks],     # metadata (JSON)
    ]
    col.insert(data)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main():
    start = time.time()

    logger.info("Connecting to Milvus at %s:%s", MILVUS_HOST, MILVUS_PORT)
    connections.connect(host=MILVUS_HOST, port=MILVUS_PORT)

    col = create_collection()

    logger.info("Connecting to Postgres at %s:%s/%s", PG_HOST, PG_PORT, PG_DB)
    conn = psycopg2.connect(
        host=PG_HOST, port=PG_PORT, user=PG_USER, password=PG_PASSWORD, dbname=PG_DB
    )
    cur = conn.cursor()

    logger.info("Fetching knowledge_chunks from Postgres...")
    knowledge = fetch_knowledge_chunks(cur)
    logger.info("Fetched %d knowledge_chunks", len(knowledge))

    logger.info("Fetching bridge_chunks from Postgres...")
    bridges = fetch_bridge_chunks(cur)
    logger.info("Fetched %d bridge_chunks", len(bridges))

    all_chunks = knowledge + bridges
    logger.info("Total chunks to embed: %d", len(all_chunks))

    cur.close()
    conn.close()

    total = len(all_chunks)
    inserted = 0
    failed = 0

    for i in range(0, total, BATCH_SIZE):
        batch = all_chunks[i : i + BATCH_SIZE]
        texts = [c["content"] for c in batch]

        non_empty = [(j, t) for j, t in enumerate(texts) if t.strip()]
        if not non_empty:
            logger.warning("Batch %d-%d: all empty, skipping", i, i + len(batch))
            continue

        try:
            indices, clean_texts = zip(*non_empty)
            embs = embed_texts(list(clean_texts))

            zero = [0.0] * EMBEDDING_DIM
            full_embs = [zero] * len(batch)
            for idx, emb in zip(indices, embs):
                full_embs[idx] = emb

            insert_batch(col, batch, full_embs)
            inserted += len(batch)

        except Exception as e:
            logger.error("Batch %d-%d failed: %s", i, i + len(batch), e)
            failed += len(batch)

        if (i // BATCH_SIZE) % 10 == 0 or i + BATCH_SIZE >= total:
            elapsed = time.time() - start
            pct = (i + len(batch)) / total * 100
            logger.info(
                "Progress: %d/%d (%.1f%%) | Inserted: %d | Failed: %d | Elapsed: %.0fs",
                i + len(batch), total, pct, inserted, failed, elapsed,
            )

    logger.info("Creating IVF_FLAT index on vector field...")
    col.create_index(
        "vector",
        {
            "index_type": "IVF_FLAT",
            "metric_type": "L2",
            "params": {"nlist": 1024},
        },
    )

    logger.info("Loading collection into memory...")
    col.load()
    logger.info("Collection loaded. Entity count: %d", col.num_entities)

    elapsed = time.time() - start
    logger.info(
        "Done! Inserted: %d, Failed: %d, Time: %.0fs (%.1f min)",
        inserted, failed, elapsed, elapsed / 60,
    )

    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
