#!/usr/bin/env python3
"""
Embed clinically-relevant UMLSConcept nodes for semantic concept bridging.

Generates embeddings (via the model server) for UMLSConcept nodes that the
post-extraction semantic bridge can match against the ``umls_embedding_index``.
Scope is intentionally limited (not all ~1.6M UMLSConcepts) to:

  * UMLSConcepts already linked by an exact-name SAME_AS edge (the canonical
    targets that document concepts actually map to), AND/OR
  * UMLSConcepts carrying a clinically-relevant semantic type (Disease,
    Drug/Pharmacologic Substance, Procedure, Finding, Sign/Symptom, etc.).

Embeds ``preferred_name`` and writes it back to ``u.embedding``.  Run this
ONCE (and after loading new UMLS data) BEFORE backfilling documents, so the
vector index is populated when ``bridge_concepts_semantic`` runs.

Usage:
    python scripts/embed_umls_concepts.py

Environment variables (or .env):
    NEO4J_URI           (default: bolt://localhost:7687)
    NEO4J_USER          (default: neo4j)
    NEO4J_PASSWORD      (default: password)
    MODEL_SERVER_URL    (default: http://localhost:8001)
    UMLS_CLINICAL_TUIS  (optional: comma-separated TUI override)
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
BATCH_SIZE = int(os.getenv("EMBED_BATCH_SIZE", "256"))  # UMLS concepts per embedding request
# Throttle: seconds to sleep between batches (eases load on the Colima VM).
BATCH_SLEEP = float(os.getenv("EMBED_BATCH_SLEEP", "0"))

# Clinically-relevant UMLS semantic type TUIs (default set).
_DEFAULT_CLINICAL_TUIS = [
    "T047",  # Disease or Syndrome
    "T048",  # Mental or Behavioral Dysfunction
    "T191",  # Neoplastic Process
    "T046",  # Pathologic Function
    "T019",  # Congenital Abnormality
    "T020",  # Acquired Abnormality
    "T190",  # Anatomical Abnormality
    "T037",  # Injury or Poisoning
    "T184",  # Sign or Symptom
    "T033",  # Finding
    "T034",  # Laboratory or Test Result
    "T201",  # Clinical Attribute
    "T121",  # Pharmacologic Substance
    "T200",  # Clinical Drug
    "T195",  # Antibiotic
    "T125",  # Hormone
    "T129",  # Immunologic Factor
    "T061",  # Therapeutic or Preventive Procedure
    "T060",  # Diagnostic Procedure
    "T059",  # Laboratory Procedure
    "T058",  # Health Care Activity
    "T023",  # Body Part, Organ, or Organ Component
]

_env_tuis = os.getenv("UMLS_CLINICAL_TUIS", "").strip()
CLINICAL_TUIS = (
    [t.strip() for t in _env_tuis.split(",") if t.strip()]
    if _env_tuis
    else _DEFAULT_CLINICAL_TUIS
)

# Rough size of the clinical subset, used only for progress %/ETA display.
# An exact count requires the global EXISTS predicate over all ~1.6M
# UMLSConcepts, which exceeds Neo4j's transaction timeout, so we estimate.
ESTIMATED_TOTAL = int(os.getenv("UMLS_EST_TOTAL", "1137037"))

# Cursor-paginated selection of clinically-relevant UMLSConcepts lacking an
# embedding.  Anchoring on ``u.cui > $last`` with ``ORDER BY u.cui`` forces an
# indexed forward range scan, so each page evaluates the EXISTS predicate only
# on a small forward slice (sub-100ms/page) instead of re-scanning all 1.6M
# nodes every batch (which times out).  ``embedding IS NULL`` is kept purely
# for resume-safety; the cui cursor is the primary driver.
_PAGE_QUERY = """
MATCH (u:UMLSConcept)
WHERE u.cui > $last
  AND u.preferred_name IS NOT NULL
  AND u.embedding IS NULL
  AND (
    EXISTS { MATCH (:Concept)-[:SAME_AS]->(u) }
    OR EXISTS {
        MATCH (u)-[:HAS_SEMANTIC_TYPE]->(st:UMLSSemanticType)
        WHERE st.type_id IN $tuis
    }
  )
RETURN u.cui AS cui, u.preferred_name AS name
ORDER BY u.cui
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

    logger.info(f"Clinical TUIs in scope: {CLINICAL_TUIS}")
    logger.info(
        f"Embedding clinically-relevant UMLSConcepts "
        f"(estimated ~{ESTIMATED_TOTAL:,}) via cui-cursor pagination"
    )

    processed = 0
    updated = 0
    failed = 0
    start = time.time()
    last_cui = os.getenv("EMBED_START_CUI", "")

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

        # Forward cursor over u.cui: each page evaluates the EXISTS predicate
        # only on the slice after last_cui, so it stays fast at corpus scale.
        while True:
            async with driver.session() as session:
                result = await session.run(
                    _PAGE_QUERY,
                    {
                        "last": last_cui,
                        "tuis": CLINICAL_TUIS,
                        "limit": BATCH_SIZE,
                    },
                )
                batch = [
                    {"cui": r["cui"], "name": r["name"]}
                    async for r in result
                ]

            if not batch:
                break

            last_cui = batch[-1]["cui"]
            names = [b["name"] for b in batch]
            embeddings = await generate_embeddings(http_client, names)

            if embeddings and len(embeddings) == len(batch):
                async with driver.session() as session:
                    await session.run(
                        "UNWIND $rows AS row "
                        "MATCH (u:UMLSConcept {cui: row.cui}) "
                        "SET u.embedding = row.embedding",
                        {
                            "rows": [
                                {"cui": item["cui"], "embedding": emb}
                                for item, emb in zip(batch, embeddings)
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
                f"rate={rate:.0f}/s eta=~{eta_min:.0f}min last_cui={last_cui}"
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
