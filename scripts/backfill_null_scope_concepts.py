#!/usr/bin/env python3
"""
Phase 1.5 reconciliation: backfill lifecycle fields + reconcile concept_id_unique.

The emergent-concepts migration (``migrate_emergent_concepts.py``) backfilled
``scope/bridge_status/provenance/owner_id`` on every Concept, stamped
``r.concept_type`` on every ``EXTRACTED_FROM`` edge, deduped by ``name_lower``,
recomputed ``concept_id = 'public:' + name_lower``, and created the
``(name_lower, scope)`` composite constraint.

Two residual gaps remain after that migration:

  1. A handful of Concepts written *after* the migration by the (then still
     ``concept_id``-keyed) enrichment/conversation write paths carry
     ``concept_id = 'public:' + name_lower`` but NULL
     ``scope/bridge_status/provenance`` and NULL ``r.concept_type`` on their
     ``EXTRACTED_FROM`` edges.  (Those write paths are now re-keyed, so this
     is a one-time sweep.)
  2. ``concept_id_unique`` is declared in ``neo4j_client.ensure_indexes()`` but
     absent from the live DB.  ``concept_id`` is provably unique (derived from
     the unique ``(name_lower, scope)`` key with scope hardcoded 'public'), so
     the constraint can be created safely.  A redundant range index
     (``concept_id_index``) previously blocked the constraint; the script drops
     it and ``ensure_indexes()`` no longer declares it.

This script is idempotent and re-runnable: the backfill is ``WHERE scope IS NULL
OR bridge_status IS NULL OR provenance IS NULL``, the stamp is ``WHERE
r.concept_type IS NULL``, and the constraint is ``IF NOT EXISTS``.

Usage (inside the app container, which reaches bolt://neo4j:7687):

    docker compose cp scripts/backfill_null_scope_concepts.py app:/tmp/backfill_null_scope_concepts.py
    docker compose exec -T app python /tmp/backfill_null_scope_concepts.py --dry-run
    docker compose exec -T app python /tmp/backfill_null_scope_concepts.py --apply

Environment (defaults match the container):
    NEO4J_URI        (default: bolt://neo4j:7687)
    NEO4J_USER       (default: neo4j)
    NEO4J_PASSWORD   (default: password)
"""

import argparse
import asyncio
import logging
import os
import time
from typing import Any, Dict

from neo4j import AsyncGraphDatabase

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)
logger = logging.getLogger(__name__)

NEO4J_URI = os.getenv("NEO4J_URI", "bolt://neo4j:7687")
NEO4J_USER = os.getenv("NEO4J_USER", "neo4j")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD", "password")

# ---------------------------------------------------------------------------
# Cypher
# ---------------------------------------------------------------------------

_MISSING_LIFECYCLE_COUNT = """
MATCH (c:Concept)
WHERE c.scope IS NULL OR c.bridge_status IS NULL OR c.provenance IS NULL
RETURN count(c) AS n
"""

_MISSING_EDGE_TYPE_COUNT = """
MATCH (c:Concept)-[r:EXTRACTED_FROM]->()
WHERE r.concept_type IS NULL
RETURN count(r) AS n
"""

# Backfill lifecycle fields on any Concept missing them. Bounded per tx so a
# large stray population never sits in a single long transaction.
_BACKFILL_LIFECYCLE = """
MATCH (c:Concept)
WHERE c.scope IS NULL OR c.bridge_status IS NULL OR c.provenance IS NULL
WITH c LIMIT 10000
SET c.scope = 'public',
    c.bridge_status = 'emergent',
    c.provenance = 'corpus-mined',
    c.owner_id = NULL
RETURN count(c) AS n
"""

# Stamp r.concept_type from the source node's type on edges lacking it.
# NOTE: there is no index on relationship properties, so the WHERE clause is
# a full edge scan (~11.5M edges) regardless of how many rows match. Run it as
# a single transaction with a long timeout rather than a drain loop (whose
# re-check would re-scan and hit the client transaction timeout).
_STAMP_EDGE_TYPE = """
MATCH (c:Concept)-[r:EXTRACTED_FROM]->()
WHERE r.concept_type IS NULL
SET r.concept_type = c.type
RETURN count(r) AS n
"""

_STAMP_TIMEOUT = 2700  # seconds — full edge scan over ~11.5M edges

_CREATE_CONCEPT_ID_CONSTRAINT = """
CREATE CONSTRAINT concept_id_unique IF NOT EXISTS
FOR (c:Concept) REQUIRE c.concept_id IS UNIQUE
"""

# A redundant range index on c.concept_id blocks the unique constraint (Neo4j
# rejects a uniqueness constraint while a non-unique index backs the property).
_DROP_CONCEPT_ID_INDEX = """
DROP INDEX concept_id_index IF EXISTS
"""


async def _single(session, query: str, params: Dict[str, Any] = None) -> Dict[str, Any]:
    res = await session.run(query, params or {})
    rec = await res.single()
    return dict(rec) if rec else {}


async def _drain(session, cypher: str, label: str) -> int:
    """Run a LIMIT-batched write repeatedly until no rows match."""
    total = 0
    while True:

        async def _tx(tx):
            result = await tx.run(cypher)
            rec = await result.single()
            return rec["n"] if rec else 0

        n = await session.execute_write(_tx)
        if not n:
            break
        total += n
        logger.info("%s: +%d (total %d)", label, n, total)
    return total


async def _stamp(session) -> int:
    """Stamp r.concept_type on all unstamped edges in one long-lived tx."""
    tx = await session.begin_transaction(timeout=_STAMP_TIMEOUT)
    try:
        res = await tx.run(_STAMP_EDGE_TYPE)
        rec = await res.single()
        await tx.commit()
        return rec["n"] if rec else 0
    except Exception:
        await tx.rollback()
        raise


async def _inspect(session) -> Dict[str, Any]:
    missing_nodes = await _single(session, _MISSING_LIFECYCLE_COUNT)
    missing_edges = await _single(session, _MISSING_EDGE_TYPE_COUNT)
    return {
        "missing_lifecycle": missing_nodes.get("n", 0),
        "missing_edge_type": missing_edges.get("n", 0),
    }


async def main(dry_run: bool, apply: bool) -> None:
    driver = AsyncGraphDatabase.driver(
        NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD)
    )
    start = time.time()

    try:
        await driver.verify_connectivity()
        logger.info("Connected to Neo4j at %s", NEO4J_URI)

        async with driver.session() as session:
            info = await _inspect(session)
            logger.info(
                "Concepts missing lifecycle fields: %s; "
                "EXTRACTED_FROM edges missing r.concept_type: %s",
                info["missing_lifecycle"],
                info["missing_edge_type"],
            )

            if dry_run:
                logger.info(
                    "DRY-RUN complete: no changes written. "
                    "Re-run with --apply to backfill."
                )
                return

            if not apply:
                logger.info("No action taken (pass --apply to write).")
                return

            backfilled = await _drain(session, _BACKFILL_LIFECYCLE, "backfill lifecycle")
            logger.info("Backfilled lifecycle fields on %s concepts", backfilled)

            stamped = await _stamp(session)
            logger.info("Stamped r.concept_type on %s EXTRACTED_FROM edges", stamped)

            await session.run(_DROP_CONCEPT_ID_INDEX)
            await session.run(_CREATE_CONCEPT_ID_CONSTRAINT)
            logger.info("Ensured concept_id_unique constraint (dropped redundant concept_id_index)")

            info = await _inspect(session)
            logger.info(
                "Post-backfill: %s concepts missing lifecycle, "
                "%s edges missing r.concept_type",
                info["missing_lifecycle"],
                info["missing_edge_type"],
            )

    finally:
        await driver.close()

    elapsed = time.time() - start
    logger.info("Backfill finished in %.1fs", elapsed)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Phase 1.5 reconciliation: backfill lifecycle fields + concept_id_unique"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Report what would change without writing anything",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Actually write the backfill and create concept_id_unique",
    )
    args = parser.parse_args()
    asyncio.run(main(dry_run=args.dry_run, apply=args.apply))
