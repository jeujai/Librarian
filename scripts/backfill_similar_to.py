#!/usr/bin/env python3
"""
Backfill SIMILAR_TO edges for emergent seed concepts via ANN over embeddings.

Seeds (provenance='seed') are not linked to idiomatic paraphrases because the
within-document SIMILAR_TO gate is cosine 0.85 (kg_builder.py), too high for
paraphrase.  This backfill links each seed to its nearest Concept neighbours
using the already-persisted ``concept_embedding_index`` (768-dim cosine) at a
separate, lower *emergent* threshold (default 0.70, above the 0.65 query-match
floor and below the canonical 0.85 gate).

No model server call: embeddings already live on the Concept nodes.  Runs
purely off Neo4j.  Seeds are a curated, inherently-small set, so all seeds are
read in one selective query (the ``concept_provenance`` index makes the
``provenance='seed'`` equality cheap); only the ANN writes are paged.
``MERGE ... ON CREATE`` keeps writes idempotent, so re-runs are safe.

Direction is seed -> neighbour; retrieval traverses SIMILAR_TO undirected, so
direction is irrelevant.

Usage:
    python scripts/backfill_similar_to.py

Environment variables (or .env):
    NEO4J_URI                    (default: bolt://localhost:7687)
    NEO4J_USER                   (default: neo4j)
    NEO4J_PASSWORD               (default: password)
    EMERGENT_SIMILARITY_THRESHOLD(default: 0.70)  minimum cosine to link
    EMERGENT_SIMILAR_TOP_K       (default: 5)     neighbours per seed
    EMERGENT_SIMILAR_ANN_K       (default: 4*TOP_K or 20)  ANN candidate pool before filters
    SIMILAR_BATCH_SIZE           (default: 100)   seeds per ANN write batch
"""

import asyncio
import logging
import os
import time

from neo4j import AsyncGraphDatabase

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)
logger = logging.getLogger(__name__)

NEO4J_URI = os.getenv("NEO4J_URI", "bolt://localhost:7687")
NEO4J_USER = os.getenv("NEO4J_USER", "neo4j")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD", "password")

THRESHOLD = float(os.getenv("EMERGENT_SIMILARITY_THRESHOLD", "0.70"))
TOP_K = int(os.getenv("EMERGENT_SIMILAR_TOP_K", "5"))
BATCH_SIZE = int(os.getenv("SIMILAR_BATCH_SIZE", "100"))
# Candidate pool for the ANN before the single-word/grounded filters.  Must be
# larger than TOP_K so that filtering single-word near-duplicates ("restriction",
# "restrictions", "restricted") still leaves enough multi-word siblings
# ("practice restrictions") to reach TOP_K.
ANN_K = int(os.getenv("EMERGENT_SIMILAR_ANN_K", str(max(TOP_K * 4, 20))))

# Select all seeds with an embedding.  The equality predicate on provenance
# (RANGE index) is cheap; no ORDER BY / concept_id range, which would bias the
# planner onto the concept_id index and scan all ~675k Concepts.
_PAGE_QUERY = """
MATCH (c:Concept)
WHERE c.provenance = 'seed'
  AND c.embedding IS NOT NULL
RETURN c.concept_id AS cid, c.embedding AS emb
"""

# Batched ANN write: top-k vector search per row, keep neighbours above the
# threshold and excluding the seed itself, then MERGE SIMILAR_TO.  ``confidence``
# matches the within-doc Concept->Concept convention (celery_service.py); the
# separate emergent threshold is the adaptive-match lever.  ON CREATE keeps it
# idempotent / resume-safe.
#
# Two neighbour filters (§abstraction-concept-resolution):
#   1. Drop single-word neighbours — a bare head-term ("restriction") is never a
#      faithful paraphrase of a multi-word concept, and it dilutes the link.
#   2. Prefer grounded neighbours — siblings that already carry EXTRACTED_FROM
#      evidence resolve to retrievable chunks, not orphan concepts.
_BRIDGE_QUERY = """
UNWIND $rows AS row
CALL db.index.vector.queryNodes('concept_embedding_index', $ann_k, row.emb)
  YIELD node, score
WITH row.cid AS cid, node, score
WHERE score >= $threshold
  AND node.concept_id <> cid
  AND node.name IS NOT NULL
  AND size(split(trim(node.name), ' ')) >= 2
OPTIONAL MATCH (node)-[:EXTRACTED_FROM]->(ch:Chunk)
WITH cid, node, score, count(DISTINCT ch) AS grounded_chunks
ORDER BY (grounded_chunks > 0) DESC, score DESC
WITH cid, collect({cid: node.concept_id, score: score})[0..$top_k] AS neighbors
UNWIND neighbors AS n
MATCH (c:Concept {concept_id: cid})
MATCH (t:Concept {concept_id: n.cid})
MERGE (c)-[r:SIMILAR_TO]->(t)
ON CREATE SET r.confidence = n.score, r.created_at = $ts
RETURN count(r) AS cnt
"""


async def main():
    driver = AsyncGraphDatabase.driver(
        NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD)
    )

    logger.info(
        "Backfilling emergent SIMILAR_TO (seed -> Concept) via concept_embedding_index "
        "(threshold=%.2f, top_k=%d, ann_k=%d)",
        THRESHOLD,
        TOP_K,
        ANN_K,
    )

    start = time.time()

    async with driver.session() as session:
        result = await session.run(_PAGE_QUERY)
        seeds = [
            {"cid": r["cid"], "emb": r["emb"]}
            async for r in result
        ]

    if not seeds:
        logger.info("0 seeds with an embedding; nothing to do.")
        await driver.close()
        return

    logger.info(f"{len(seeds)} seed(s) with an embedding")

    linked = 0
    ts = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    for i in range(0, len(seeds), BATCH_SIZE):
        page = seeds[i : i + BATCH_SIZE]
        async with driver.session() as session:
            res = await session.run(
                _BRIDGE_QUERY,
                {
                    "rows": page,
                    "top_k": TOP_K,
                    "ann_k": ANN_K,
                    "threshold": THRESHOLD,
                    "ts": ts,
                },
            )
            rec = await res.single()
            linked += rec["cnt"] if rec else 0

    await driver.close()
    elapsed = time.time() - start
    logger.info(
        "Done: %s SIMILAR_TO edges created over %s seeds in %.1fs",
        f"{linked:,}",
        f"{len(seeds):,}",
        elapsed,
    )


if __name__ == "__main__":
    asyncio.run(main())
