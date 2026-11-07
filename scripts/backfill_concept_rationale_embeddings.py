#!/usr/bin/env python3
"""
Materialize concept-level rationale embeddings (streamed mean, degree-capped).

For every :Concept with at least one :EXTRACTED_FROM edge carrying an
``r.rationale_embedding``, set ``c.rationale_embedding`` to the mean of those
edge embeddings.  Means are accumulated incrementally in numpy (running sum +
count), so only the current edge's vector is in memory at a time and the math
is vectorized — much faster than a Cypher ``reduce`` that re-scans each
concept's embeddings once per dimension.

Concepts whose degree exceeds ``DEGREE_CAP`` are skipped: their rationale mean
is diluted across thousands of heterogeneous passages (mostly stopwords and
generic terms) and would only inject noise into the rationale index.  The
rationale bridge is meant for focused, low-degree concepts whose co-text
paraphrase is specific (e.g. "cytomegalovirus pneumonitis", not "disease").

Edges are fetched via ``concept_id`` point lookups (``concept_id_unique``
index), NOT a full label scan — the original scan over all ~4.9M edges is what
tripped the 120s transaction timeout.  Batches are bounded by total edge count
(``TOTAL_DEG_LIMIT``) so a single transaction stays well under that timeout.

Non-destructive, idempotent, resume-safe: only concepts whose
``rationale_embedding`` is NULL are computed.

The vector index (``concept_rationale_embedding_index``) MUST be dropped
before the bulk run and re-created afterwards: a live HNSW index makes every
``SET c.rationale_embedding`` pay a synchronous index insertion (~0.5s each,
growing with index size), which turns a ~20-minute backfill into ~10 hours.
Bulk-load the property first, then build the index once (Neo4j builds HNSW in
parallel, far faster than incremental inserts).

    # once, before the run:
    #   DROP INDEX concept_rationale_embedding_index IF EXISTS

Usage (inside the app container, via stdin pipe so the host need not install
the neo4j driver):
    docker compose exec -T app python3 - < scripts/backfill_concept_rationale_embeddings.py

    # once, after the run:
    #   CALL db.index.vector.createNodeIndex(
    #       'concept_rationale_embedding_index', 'Concept',
    #       'rationale_embedding', 768, 'cosine')

Environment variables (or .env):
    NEO4J_URI        (default: bolt://neo4j:7687)
    NEO4J_USER       (default: neo4j)
    NEO4J_PASSWORD   (default: password)
    DEGREE_CAP       (default: 5000)  skip concepts with more edges than this
    TOTAL_DEG_LIMIT  (default: 20000) max summed degree per batch
    MAX_CONCEPTS     (default: 0 = all) cap for a smoke test
"""

import asyncio
import logging
import os
import time

import numpy as np
from neo4j import AsyncGraphDatabase
from neo4j.exceptions import ClientError

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)
logger = logging.getLogger(__name__)

NEO4J_URI = os.getenv("NEO4J_URI", "bolt://neo4j:7687")
NEO4J_USER = os.getenv("NEO4J_USER", "neo4j")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD", "password")
DEGREE_CAP = int(os.getenv("DEGREE_CAP", "5000"))
TOTAL_DEG_LIMIT = int(os.getenv("TOTAL_DEG_LIMIT", "20000"))
MAX_CONCEPTS = int(os.getenv("MAX_CONCEPTS", "0"))

# Concepts that still need materialization, with edge count so batches can be
# sized by total degree.  No ORDER BY; the grouping in `WITH c, count(r)` dedups.
_CONCEPTS_QUERY = (
    "MATCH (c:Concept)-[r:EXTRACTED_FROM]->(:Chunk) "
    "WHERE r.rationale_embedding IS NOT NULL AND c.rationale_embedding IS NULL "
    "WITH c, count(r) AS deg "
    "WHERE deg < $cap "
    "RETURN c.concept_id AS cid, deg"
)

_SKIPPED_COUNT_QUERY = (
    "MATCH (c:Concept)-[r:EXTRACTED_FROM]->(:Chunk) "
    "WHERE r.rationale_embedding IS NOT NULL AND c.rationale_embedding IS NULL "
    "WITH c, count(r) AS deg "
    "WHERE deg >= $cap "
    "RETURN count(c) AS skipped"
)

_EDGES_QUERY = (
    "UNWIND $cids AS cid "
    "MATCH (c:Concept {concept_id: cid})-[r:EXTRACTED_FROM]->(:Chunk) "
    "WHERE r.rationale_embedding IS NOT NULL "
    "RETURN c.concept_id AS cid, r.rationale_embedding AS emb"
)

_WRITE_QUERY = (
    "UNWIND $rows AS row "
    "MATCH (c:Concept {concept_id: row.cid}) "
    "SET c.rationale_embedding = row.emb "
    "RETURN count(c) AS cnt"
)


def _chunks_by_degree(rows, limit):
    """Group (cid, deg) rows into batches whose summed degree <= limit."""
    batch = []
    total = 0
    for cid, deg in rows:
        if total + deg > limit and batch:
            yield [c for c, _ in batch]
            batch = []
            total = 0
        batch.append((cid, deg))
        total += deg
    if batch:
        yield [c for c, _ in batch]


async def _process_batch(driver, cids) -> int:
    """Stream edge embeddings for a batch and write their means."""
    sums: dict[str, np.ndarray] = {}
    counts: dict[str, int] = {}
    async with driver.session() as session:
        result = await session.run(_EDGES_QUERY, {"cids": list(cids)})
        async for rec in result:
            cid = rec["cid"]
            emb = rec["emb"]
            if not emb:
                continue
            arr = np.asarray(emb, dtype=np.float64)
            if cid in sums:
                sums[cid] += arr
                counts[cid] += 1
            else:
                sums[cid] = arr.copy()
                counts[cid] = 1

    rows = [
        {"cid": cid, "emb": (sums[cid] / counts[cid]).tolist()}
        for cid in sums
    ]
    if not rows:
        return 0

    async with driver.session() as session:
        async def _tx(tx):
            res = await tx.run(_WRITE_QUERY, {"rows": rows})
            rec = await res.single()
            return rec["cnt"] if rec else 0

        return await session.execute_write(_tx)


async def _process_batch_robust(driver, cids, stats) -> None:
    """Process a batch, falling back to one-at-a-time on timeout."""
    try:
        stats["written"] += await _process_batch(driver, cids)
        stats["pages"] += 1
        return
    except ClientError as e:
        if "Timeout" not in str(e):
            logger.warning(f"Batch failed: {type(e).__name__}: {e}")
            stats["failed"] += len(cids)
            stats["pages"] += 1
            return
        logger.info(f"Batch of {len(cids)} timed out; falling back to one-at-a-time")
        for cid in cids:
            try:
                stats["written"] += await _process_batch(driver, [cid])
            except Exception as e2:
                logger.warning(f"Concept {cid} failed: {type(e2).__name__}: {e2}")
                stats["failed"] += 1
        stats["pages"] += 1


async def main():
    driver = AsyncGraphDatabase.driver(
        NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD)
    )

    rows: list[tuple[str, int]] = []
    async with driver.session() as session:
        result = await session.run(_CONCEPTS_QUERY, {"cap": DEGREE_CAP})
        async for rec in result:
            rows.append((rec["cid"], rec["deg"]))

    skipped = 0
    async with driver.session() as session:
        rec = await (await session.run(_SKIPPED_COUNT_QUERY, {"cap": DEGREE_CAP})).single()
        skipped = rec["skipped"] if rec else 0

    if MAX_CONCEPTS:
        rows = rows[:MAX_CONCEPTS]

    logger.info(
        f"{len(rows)} concepts to materialize (degree < {DEGREE_CAP}); "
        f"{skipped} skipped (degree >= {DEGREE_CAP})"
    )

    if not rows:
        logger.info("Nothing to backfill")
        await driver.close()
        return

    stats = {"written": 0, "failed": 0, "pages": 0}
    start = time.time()
    batches = list(_chunks_by_degree(rows, TOTAL_DEG_LIMIT))
    logger.info(f"{len(batches)} batches (total degree <= {TOTAL_DEG_LIMIT} each)")
    for i, batch in enumerate(batches, start=1):
        await _process_batch_robust(driver, batch, stats)
        if i % 50 == 0 or i == len(batches):
            elapsed = time.time() - start
            logger.info(
                f"progress {i}/{len(batches)} batches, "
                f"{stats['written']}/{len(rows)} concepts, "
                f"{stats['failed']} failed, {elapsed:.0f}s"
            )

    await driver.close()
    logger.info(
        f"Done: {stats['written']} written, {stats['failed']} failed, "
        f"{skipped} skipped (deg >= {DEGREE_CAP}) in {time.time() - start:.0f}s"
    )


if __name__ == "__main__":
    asyncio.run(main())
