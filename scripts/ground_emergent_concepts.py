#!/usr/bin/env python3
"""
Ground emergent seed concepts (provenance='seed') via EXTRACTED_FROM edges.

A seed Concept is born out-of-band (see seed_emergent_concepts.py) with an
embedding but no EXTRACTED_FROM edges, so it only surfaces through a 2-hop
``query -> seed -> document concept -> chunk`` path that hop-distance decay
punishes.  This backfill links each seed to the chunks that actually express
its meaning.

Grounding is *context-aware*, not literal.  A seed's ``name`` is the query-side
label (often generic: "management guidelines"), while its ``surface_forms`` are
the corpus-side expressions that disambiguate it ("management of HCP").  We
therefore:

1. RECALL literal candidates with an ILIKE substring match on name + surface
   forms (cheap, high recall).
2. PRECISION-filter them with the model-server cross-encoder (BAAI/bge-reranker
   -v2-m3), scoring each candidate against the *surface forms only* (falling
   back to the name when a seed has no surface forms).  The cross-encoder's
   sigmoid output saturates at ~0.50 for irrelevant chunks and rises sharply
   for genuinely-relevant ones, so a single threshold cleanly separates the
   two — unlike the generic name, whose literal matches fan out to dozens of
   unrelated "management guidelines"/"work restrictions" chunks.

3. GROUND the chunks that score >= GROUND_MIN_SCORE (MERGE + ON CREATE, resume
   safe), and DELETE any stale EXTRACTED_FROM edge pointing at a chunk that no
   longer passes the semantic bar (cleanup of the original literal-only run).

Target set is ``provenance='seed'`` ONLY.  ``Chunk.chunk_id`` ==
``str(knowledge_chunks.id)`` (Postgres UUID), matching the pipeline write in
celery_service.py.

Usage:
    python scripts/ground_emergent_concepts.py

Environment variables (or .env):
    NEO4J_URI          (default: bolt://localhost:7687)
    NEO4J_USER         (default: neo4j)
    NEO4J_PASSWORD     (default: password)
    PG_HOST            (default: localhost)
    PG_PORT            (default: 5432)
    PG_DB              (default: multimodal_librarian)
    PG_USER            (default: postgres)
    PG_PASSWORD        (default: postgres)
    MODEL_SERVER_URL   (default: http://localhost:8001)
    GROUND_MIN_SCORE   (default: 0.505)  cross-encoder relevance cutoff
    GROUND_MAX_CHUNKS  (default: 200)    literal candidates per concept (cap)
    GROUND_WRITE_BATCH (default: 200)    edges per UNWIND write batch
"""

import asyncio
import logging
import os
import sys
import time
from datetime import datetime

import asyncpg
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

PG_HOST = os.getenv("PG_HOST", "localhost")
PG_PORT = int(os.getenv("PG_PORT", "5432"))
PG_DB = os.getenv("PG_DB", "multimodal_librarian")
PG_USER = os.getenv("PG_USER", "postgres")
PG_PASSWORD = os.getenv("PG_PASSWORD", "postgres")

MODEL_SERVER_URL = os.getenv("MODEL_SERVER_URL", "http://localhost:8001")
MIN_SCORE = float(os.getenv("GROUND_MIN_SCORE", "0.505"))

MIN_NAME_LEN = 3
MAX_CHUNKS_PER_CONCEPT = int(os.getenv("GROUND_MAX_CHUNKS", "200"))
WRITE_BATCH = int(os.getenv("GROUND_WRITE_BATCH", "200"))
RERANK_BATCH = int(os.getenv("GROUND_RERANK_BATCH", "128"))

# All seeds (curated terms).  We target the full seed set every run so the
# semantic filter both adds the surface-form chunks it missed before AND prunes
# the literal-only noise edges from the original run.
_TARGET_QUERY = """
MATCH (c:Concept)
WHERE c.provenance = 'seed'
RETURN c.concept_id AS cid, c.name AS name, c.concept_type AS type,
       c.surface_forms AS surface_forms
"""

_EDGES_QUERY = """
MATCH (c:Concept {name_lower: toLower($name), scope: 'public'})-[r:EXTRACTED_FROM]->(ch:Chunk)
RETURN ch.chunk_id AS chunk_id
"""


def _chunk_query(n_terms: int) -> str:
    """Literal-phrase recall on the seed name PLUS its surface forms.

    Each term is an ILIKE substring condition; $i::text pins the parameter type
    for asyncpg.  This only builds the candidate pool — the cross-encoder does
    the actual relevance filtering downstream.
    """
    conds = " OR ".join(
        f"content ILIKE '%' || ${i}::text || '%'" for i in range(1, n_terms + 1)
    )
    return (
        "SELECT id, content FROM multimodal_librarian.knowledge_chunks "
        f"WHERE {conds} LIMIT {MAX_CHUNKS_PER_CONCEPT}"
    )


def _content_query(n_ids: int) -> str:
    """Fetch content for an arbitrary set of chunk UUIDs (edge-only recall)."""
    placeholders = ", ".join(f"${i}::uuid" for i in range(1, n_ids + 1))
    return (
        "SELECT id, content FROM multimodal_librarian.knowledge_chunks "
        f"WHERE id IN ({placeholders})"
    )


# Identical to the pipeline write at celery_service.py (MERGE + ON CREATE).
_WRITE_QUERY = """
UNWIND $rows AS row
MATCH (c:Concept {name_lower: toLower(row.name), scope: 'public'})
MATCH (ch:Chunk {chunk_id: row.chunk_id})
MERGE (c)-[r:EXTRACTED_FROM]->(ch)
ON CREATE SET r.created_at = row.created_at, r.concept_type = row.concept_type
RETURN count(r) AS cnt
"""

_DELETE_QUERY = """
MATCH (c:Concept {name_lower: toLower($name), scope: 'public'})-[r:EXTRACTED_FROM]->(ch:Chunk)
WHERE ch.chunk_id IN $chunk_ids
DELETE r
RETURN count(r) AS cnt
"""


async def _write_with_retry(session, rows, *, max_retries: int = 5, base_delay: float = 1.0):
    """Write one UNWIND batch, retrying on transient Neo4j lock timeouts."""

    async def _write_tx(tx):
        res = await tx.run(_WRITE_QUERY, {"rows": rows})
        rec = await res.single()
        return rec["cnt"] if rec else 0

    for attempt in range(max_retries + 1):
        try:
            return await session.execute_write(_write_tx)
        except Exception as e:
            msg = str(e)
            is_transient = (
                "LockAcquisitionTimeout" in msg
                or "TransientError" in msg
                or "Unable to acquire lock" in msg
                or "BookmarkTimeout" in msg
                or "ForbiddenDueToTransactionNotOpen" in msg
            )
            if not is_transient or attempt == max_retries:
                raise
            delay = base_delay * (2 ** attempt)
            logger.info(
                f"Write lock contention (attempt {attempt + 1}/{max_retries}), "
                f"retrying in {delay:.1f}s"
            )
            await asyncio.sleep(delay)


async def _rerank(http: httpx.AsyncClient, query: str, documents: list) -> list:
    """Cross-encoder score a list of documents against a query, in batches."""
    scores: list = []
    for i in range(0, len(documents), RERANK_BATCH):
        batch = documents[i : i + RERANK_BATCH]
        resp = await http.post(
            f"{MODEL_SERVER_URL}/rerank",
            json={"query": query, "documents": batch},
        )
        resp.raise_for_status()
        scores.extend(resp.json().get("scores", []))
    return scores


async def main(dry_run: bool = False):
    driver = AsyncGraphDatabase.driver(
        NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD)
    )
    pg = await asyncpg.connect(
        host=PG_HOST, port=PG_PORT, database=PG_DB,
        user=PG_USER, password=PG_PASSWORD,
    )

    start = time.time()
    try:
        async with driver.session() as session:
            result = await session.run(_TARGET_QUERY)
            seeds = [
                {
                    "cid": r["cid"],
                    "name": r["name"],
                    "type": r["type"] or "ENTITY",
                    "surface_forms": r.get("surface_forms") or [],
                }
                async for r in result
            ]

        if not seeds:
            logger.info("0 seeds needing grounding; nothing to do.")
            await pg.close()
            await driver.close()
            return

        logger.info(f"{len(seeds)} seed(s) to ground (context-aware)")

        now_ts = datetime.utcnow().isoformat()
        total_merged = 0
        total_deleted = 0
        async with httpx.AsyncClient(timeout=300.0) as http:
            for seed in seeds:
                name = (seed["name"] or "").strip()
                surface_forms = [
                    sf.strip()
                    for sf in (seed.get("surface_forms") or [])
                    if sf and str(sf).strip()
                ]
                terms = [name] + surface_forms
                terms = [t for t in terms if len(t) >= MIN_NAME_LEN]

                # 1. Recall literal candidates (id + content).
                id_to_content = {}
                if terms:
                    for row in await pg.fetch(_chunk_query(len(terms)), *terms):
                        id_to_content[str(row["id"])] = row["content"] or ""

                # 2. Existing EXTRACTED_FROM edges (for cleanup).
                edge_ids = set()
                async with driver.session() as session:
                    res = await session.run(_EDGES_QUERY, {"name": name})
                    async for r in res:
                        edge_ids.add(str(r["chunk_id"]))

                all_ids = set(id_to_content) | edge_ids
                if not all_ids:
                    continue

                # 3. Fetch content for edge-only chunks (no longer literal hits).
                missing = [i for i in edge_ids if i not in id_to_content]
                if missing:
                    for row in await pg.fetch(_content_query(len(missing)), *missing):
                        id_to_content[str(row["id"])] = row["content"] or ""

                # 4. Score against surface forms (specific) or name (fallback).
                score_query = " ".join(surface_forms) if surface_forms else name
                ids = list(all_ids)
                contents = [id_to_content.get(i) or "" for i in ids]
                scores = await _rerank(http, score_query, contents)

                keep_ids = [i for i, sc in zip(ids, scores) if sc >= MIN_SCORE]
                drop_ids = [i for i, sc in zip(ids, scores) if sc < MIN_SCORE]

                # 5. MERGE keep.
                merge_rows = [
                    {
                        "name": name,
                        "chunk_id": i,
                        "concept_type": seed["type"],
                        "created_at": now_ts,
                    }
                    for i in keep_ids
                ]
                if not dry_run:
                    for j in range(0, len(merge_rows), WRITE_BATCH):
                        async with driver.session() as session:
                            total_merged += await _write_with_retry(
                                session, merge_rows[j : j + WRITE_BATCH]
                            )

                # 6. DELETE stale noise edges (only those that existed).
                drop_existing = [i for i in drop_ids if i in edge_ids]
                if drop_existing and not dry_run:
                    async with driver.session() as session:
                        res = await session.run(
                            _DELETE_QUERY,
                            {"name": name, "chunk_ids": drop_existing},
                        )
                        rec = await res.single()
                        total_deleted += rec["cnt"] if rec else 0

                logger.info(
                    f"{name!r}: keep={len(keep_ids)} drop={len(drop_ids)} "
                    f"(deleted {len(drop_existing)} stale edges)"
                )

        elapsed = time.time() - start
        logger.info(
            f"Done: {total_merged} edges merged, {total_deleted} noise edges "
            f"deleted in {elapsed:.1f}s"
        )

    finally:
        await pg.close()
        await driver.close()


if __name__ == "__main__":
    dry_run = "--dry-run" in sys.argv
    if dry_run:
        logger.info("DRY RUN: no edges will be merged or deleted.")
    asyncio.run(main(dry_run=dry_run))
