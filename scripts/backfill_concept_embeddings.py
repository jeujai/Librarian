#!/usr/bin/env python3
"""
Backfill embeddings for Neo4j Concept nodes that are missing them.

Reads all concepts without embeddings, generates embeddings via the
model server, and writes them back to Neo4j in batches.

Usage:
    python scripts/backfill_concept_embeddings.py

Environment variables (or .env):
    NEO4J_URI          (default: bolt://localhost:7687)
    NEO4J_USER         (default: neo4j)
    NEO4J_PASSWORD     (default: password)
    MODEL_SERVER_URL   (default: http://localhost:8001)
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
BATCH_SIZE = 64  # concepts per embedding request


async def generate_embeddings(
    client: httpx.AsyncClient, texts: list[str]
) -> list[list[float]] | None:
    """Call model server to generate embeddings."""
    try:
        resp = await client.post(
            f"{MODEL_SERVER_URL}/embeddings",
            json={"texts": texts},
            timeout=60.0,
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

    # Count missing embeddings
    async with driver.session() as session:
        result = await session.run(
            "MATCH (c:Concept) WHERE c.embedding IS NULL "
            "RETURN count(c) AS cnt"
        )
        record = await result.single()
        total = record["cnt"]
        logger.info(f"Found {total} concepts without embeddings")

    if total == 0:
        logger.info("Nothing to backfill")
        await driver.close()
        return

    processed = 0
    updated = 0
    failed = 0
    start = time.time()

    async with httpx.AsyncClient() as http_client:
        # Verify model server is reachable
        try:
            health = await http_client.get(
                f"{MODEL_SERVER_URL}/health", timeout=5.0
            )
            logger.info(
                f"Model server health: {health.status_code}"
            )
        except Exception as e:
            logger.error(
                f"Model server unreachable at {MODEL_SERVER_URL}: {e}"
            )
            await driver.close()
            sys.exit(1)

        # Process in batches — always SKIP 0 because each batch we
        # process removes rows from the WHERE c.embedding IS NULL set.
        while True:
            async with driver.session() as session:
                result = await session.run(
                    "MATCH (c:Concept) WHERE c.embedding IS NULL "
                    "RETURN c.concept_id AS cid, c.name AS name "
                    "ORDER BY c.concept_id "
                    "LIMIT $limit",
                    {"limit": BATCH_SIZE},
                )
                batch = [
                    {"cid": r["cid"], "name": r["name"]}
                    async for r in result
                ]

            if not batch:
                break

            names = [b["name"] for b in batch]
            embeddings = await generate_embeddings(http_client, names)

            if embeddings and len(embeddings) == len(batch):
                # Write embeddings back
                async with driver.session() as session:
                    for item, emb in zip(batch, embeddings):
                        try:
                            await session.run(
                                "MATCH (c:Concept {concept_id: $cid}) "
                                "SET c.embedding = $embedding",
                                {"cid": item["cid"], "embedding": emb},
                            )
                            updated += 1
                        except Exception as e:
                            logger.warning(
                                f"Failed to update {item['cid']}: {e}"
                            )
                            failed += 1
            else:
                logger.warning(
                    f"Skipping batch at offset {offset}: "
                    f"embedding generation returned "
                    f"{len(embeddings) if embeddings else 0} "
                    f"for {len(batch)} concepts"
                )
                failed += len(batch)

            processed += len(batch)
            elapsed = time.time() - start
            rate = processed / elapsed if elapsed > 0 else 0
            logger.info(
                f"Progress: {processed}/{total} "
                f"({processed*100//total}%) "
                f"updated={updated} failed={failed} "
                f"rate={rate:.0f}/s"
            )

    await driver.close()
    elapsed = time.time() - start
    logger.info(
        f"Done: {updated} updated, {failed} failed "
        f"in {elapsed:.1f}s"
    )


if __name__ == "__main__":
    asyncio.run(main())
