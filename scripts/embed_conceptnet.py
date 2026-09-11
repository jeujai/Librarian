#!/usr/bin/env python3
"""
Embed ConceptNetConcept nodes for colloquial-to-clinical concept bridging.

Generates embeddings (via the model server) for ConceptNetConcept node names
and writes them back to ``c.embedding``.  Once embedded, the
``conceptnet_embedding_index`` vector index enables semantic search over
ConceptNet concepts, bridging colloquial user terms (e.g. "tummy ache") to
clinical UMLS concepts (e.g. "Abdominal Pain").

Run this ONCE after importing ConceptNet data, BEFORE the query decomposer
can use the ConceptNet bridge path.

Usage:
    python scripts/embed_conceptnet.py

Environment variables (or .env):
    NEO4J_URI           (default: bolt://localhost:7687)
    NEO4J_USER          (default: neo4j)
    NEO4J_PASSWORD      (default: password)
    MODEL_SERVER_URL    (default: http://localhost:8001)
    EMBED_BATCH_SIZE    (default: 128)
    EMBED_BATCH_SLEEP   (default: 0.1 — seconds between batches)
"""

import asyncio
import logging
import os
import sys
import time

import httpx
from neo4j import AsyncGraphDatabase

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)
logger = logging.getLogger(__name__)

NEO4J_URI = os.getenv("NEO4J_URI", "bolt://localhost:7687")
NEO4J_USER = os.getenv("NEO4J_USER", "neo4j")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD", "password")
MODEL_SERVER_URL = os.getenv("MODEL_SERVER_URL", "http://localhost:8001")
BATCH_SIZE = int(os.getenv("EMBED_BATCH_SIZE", "128"))
BATCH_SLEEP = float(os.getenv("EMBED_BATCH_SLEEP", "0.1"))

# Rough count for progress display.  An exact COUNT(*) over ~1.78M nodes
# takes several seconds and isn't worth repeating every batch.
ESTIMATED_TOTAL = int(os.getenv("CONCEPTNET_EST_TOTAL", "1780000"))

# Cursor-paginated selection over ConceptNetConcept nodes lacking an
# embedding.  Anchoring on ``c.name > $last`` with ``ORDER BY c.name``
# forces an indexed forward scan so each page is fast regardless of
# corpus position.  ``embedding IS NULL`` is for resume-safety.
_PAGE_QUERY = """
MATCH (c:ConceptNetConcept)
WHERE c.name > $last
  AND c.name IS NOT NULL
  AND c.embedding IS NULL
RETURN c.name AS name
ORDER BY c.name
LIMIT $limit
"""


async def generate_embeddings(
    client: httpx.AsyncClient, texts: list[str]
) -> list[list[float]] | None:
    """Call model server to generate embeddings."""
    try:
        resp = await client.post(
            f"{MODEL_SERVER_URL}/embeddings",
            json={"texts": texts},
            timeout=120.0,
        )
        resp.raise_for_status()
        data = resp.json()
        return data.get("embeddings")
    except Exception as e:
        logger.error(f"Embedding request failed: {e}")
        return None


async def main():
    driver = AsyncGraphDatabase.driver(
        NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD)
    )

    logger.info(
        f"Embedding ConceptNetConcept nodes (estimated ~{ESTIMATED_TOTAL:,}) "
        f"via name-cursor pagination, batch_size={BATCH_SIZE}"
    )

    processed = 0
    updated = 0
    failed = 0
    start = time.time()
    last_name = os.getenv("EMBED_START_NAME", "")

    async with httpx.AsyncClient() as http_client:
        try:
            health = await http_client.get(
                f"{MODEL_SERVER_URL}/health", timeout=5.0
            )
            logger.info(f"Model server health: {health.status_code}")
        except Exception as e:
            logger.error(f"Model server unreachable at {MODEL_SERVER_URL}: {e}")
            await driver.close()
            sys.exit(1)

        while True:
            async with driver.session() as session:
                result = await session.run(
                    _PAGE_QUERY,
                    {
                        "last": last_name,
                        "limit": BATCH_SIZE,
                    },
                )
                batch = [r["name"] async for r in result]

            if not batch:
                break

            last_name = batch[-1]
            embeddings = await generate_embeddings(http_client, batch)

            if embeddings and len(embeddings) == len(batch):
                async with driver.session() as session:
                    await session.run(
                        "UNWIND $rows AS row "
                        "MATCH (c:ConceptNetConcept {name: row.name}) "
                        "SET c.embedding = row.embedding",
                        {
                            "rows": [
                                {"name": name, "embedding": emb}
                                for name, emb in zip(batch, embeddings)
                            ]
                        },
                    )
                    updated += len(batch)
            else:
                logger.warning(
                    f"Skipping batch: embedding generation returned "
                    f"{len(embeddings) if embeddings else 0} for {len(batch)} concepts"
                )
                failed += len(batch)

            processed += len(batch)
            elapsed = time.time() - start
            rate = processed / elapsed if elapsed > 0 else 0
            pct = min(100, processed * 100 // ESTIMATED_TOTAL) if ESTIMATED_TOTAL else 0
            eta_min = (
                (ESTIMATED_TOTAL - processed) / rate / 60
                if rate > 0 and processed < ESTIMATED_TOTAL
                else 0
            )
            logger.info(
                f"Progress: {processed:,}/~{ESTIMATED_TOTAL:,} "
                f"(~{pct}%) updated={updated:,} failed={failed:,} "
                f"rate={rate:.0f}/s eta=~{eta_min:.0f}min last_name={last_name[:60]}"
            )

            if BATCH_SLEEP > 0:
                await asyncio.sleep(BATCH_SLEEP)

    await driver.close()
    elapsed = time.time() - start
    logger.info(
        f"Done: {updated:,} updated, {failed:,} failed in {elapsed:.1f}s "
        f"({elapsed/60:.1f}min)"
    )


if __name__ == "__main__":
    asyncio.run(main())
