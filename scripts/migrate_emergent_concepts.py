#!/usr/bin/env python3
"""
One-shot dedup migration for the emergent-concepts architecture (Phase 1 step 3).

Prepares the live ``Concept`` graph for the ``(name_lower, scope)`` composite
identity that the emergent-concepts architecture introduces (see
``docs/emergent-concepts-architecture.md`` §4.2).  Today a concept's
``concept_id`` is type-prefixed (``{type}_{normalized}``), so one surface form
extracted by different extractors becomes multiple nodes sharing one
``name_lower`` (~41k duplicates across ~94k nodes).  This script:

  1. Backfills ``bridge_status='emergent'``, ``provenance='corpus-mined'``,
     ``scope='public'``, ``owner_id=NULL`` on every existing Concept.
  2. Stamps ``r.concept_type`` on every ``EXTRACTED_FROM`` edge from its source
     node's type (preserves the per-chunk extractor type before re-pointing).
  3. Dedups each duplicated ``name_lower`` via ``apoc.refactor.mergeNodes``
     (earliest ``created_at`` wins; all relationships re-pointed to the
     survivor; edge properties preserved).
  4. Recomputes ``concept_id`` as the derived surrogate ``public:{name_lower}``.
  5. Creates the ``(name_lower, scope)`` composite uniqueness constraint.

Idempotent / resumable: backfill is ``WHERE bridge_status IS NULL``, the stamp
is ``WHERE r.concept_type IS NULL``, and the dedup no-ops once each name_lower
has a single node.

Usage (inside the app container, which reaches bolt://neo4j:7687):

    docker compose cp scripts/migrate_emergent_concepts.py app:/tmp/migrate_emergent_concepts.py
    docker compose exec -T app python /tmp/migrate_emergent_concepts.py --dry-run
    docker compose exec -T app python /tmp/migrate_emergent_concepts.py --apply

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
from typing import Any, Dict, List, Tuple

from neo4j import AsyncGraphDatabase

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)
logger = logging.getLogger(__name__)

NEO4J_URI = os.getenv("NEO4J_URI", "bolt://neo4j:7687")
NEO4J_USER = os.getenv("NEO4J_USER", "neo4j")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD", "password")

_DEDUP_BATCH = 200  # name_lower groups per transaction


# ---------------------------------------------------------------------------
# Cypher
# ---------------------------------------------------------------------------

_CONCEPT_COUNTS = """
MATCH (c:Concept)
RETURN count(c) AS total,
       count(DISTINCT c.name_lower) AS distinct_name_lower
"""

_DUP_GROUP_STATS = """
MATCH (c:Concept)
WITH c.name_lower AS nl, count(*) AS cnt
WHERE cnt > 1
RETURN count(nl) AS groups, sum(cnt) AS nodes_in_groups, sum(cnt - 1) AS nodes_to_delete
"""

_DUP_NAME_LOWERS = """
MATCH (c:Concept)
WITH c.name_lower AS nl, count(*) AS cnt
WHERE cnt > 1
RETURN nl
ORDER BY cnt DESC, nl ASC
"""

_SHOW_CONSTRAINTS = """
SHOW CONSTRAINTS
YIELD name, labelsOrTypes, properties, type, entityType
RETURN name, labelsOrTypes, properties, type, entityType
"""

_BACKFILL = """
MATCH (c:Concept)
WHERE c.bridge_status IS NULL
WITH c LIMIT 10000
SET c.bridge_status = 'emergent',
    c.provenance = 'corpus-mined',
    c.scope = 'public',
    c.owner_id = NULL
RETURN count(c) AS n
"""

_STAMP_LIMIT = 500_000        # edges per apoc.periodic.iterate chunk
_STAMP_PARALLEL = False       # True only if benchmark shows a material speedup
_STAMP_CHUNK_TIMEOUT = 2700   # seconds per chunk (server db.transaction.timeout=120s default)


def _stamp_query(limit: int, parallel: bool) -> str:
    return (
        "CALL apoc.periodic.iterate("
        "'MATCH (c:Concept)-[r:EXTRACTED_FROM]->() "
        "WHERE r.concept_type IS NULL RETURN r, c.type AS ct "
        f"LIMIT {limit}', "
        "'SET r.concept_type = ct', "
        f"{{batchSize: 10000, parallel: {str(parallel).lower()}}}"
        ") YIELD total, committedOperations, failedOperations "
        "RETURN total AS stamped, committedOperations, failedOperations"
    )

_MERGE_GROUP = """
MATCH (c:Concept {name_lower: $nl})
WITH c
ORDER BY coalesce(c.created_at, 0) ASC, elementId(c) ASC
WITH collect(c) AS nodes
CALL apoc.refactor.mergeNodes(nodes, {properties: 'discard', mergeRels: false})
YIELD node
RETURN count(node) AS merged
"""

_RECOMPUTE_CONCEPT_ID = """
MATCH (c:Concept)
WHERE c.name_lower IS NOT NULL AND c.concept_id <> 'public:' + c.name_lower
WITH c LIMIT 10000
SET c.concept_id = 'public:' + c.name_lower
RETURN count(c) AS n
"""

_CREATE_COMPOSITE_CONSTRAINT = """
CREATE CONSTRAINT concept_scope_unique IF NOT EXISTS
FOR (c:Concept) REQUIRE (c.name_lower, c.scope) IS UNIQUE
"""

# Legacy constraints from the Docker seed files that describe the OLD schema.
# Dropped if present (they conflict in spirit with the new name_lower identity).
_STALE_CONSTRAINT_NAMES = {
    "concept_name_unique",          # 02_create_constraints.cypher: c.name IS UNIQUE
    "concept_name_type_unique",     # 00_schema_initialization.cypher: (c.name, c.type) IS UNIQUE
}


def _apoc_available_check() -> str:
    return "RETURN apoc.version() AS v"


async def _single(session, query: str, params: Dict[str, Any] = None) -> Dict[str, Any]:
    """Run a query and return its single record (or {} if none)."""
    res = await session.run(query, params or {})
    rec = await res.single()
    return dict(rec) if rec else {}


async def _inspect(session) -> Dict[str, Any]:
    counts = await _single(session, _CONCEPT_COUNTS)
    dup = await _single(session, _DUP_GROUP_STATS)
    return {**counts, **dup}


async def _list_constraints(session) -> List[Dict[str, Any]]:
    res = await session.run(_SHOW_CONSTRAINTS)
    return [dict(rec) async for rec in res]


def _stale_constraints(constraints: List[Dict[str, Any]]) -> List[str]:
    stale = []
    for c in constraints:
        name = c.get("name", "")
        if name in _STALE_CONSTRAINT_NAMES:
            stale.append(name)
    return stale


async def _verify_apoc(session) -> None:
    """Confirm APOC (apoc.refactor.mergeNodes) is callable, or abort."""
    try:
        rec = await _single(session, _apoc_available_check())
        logger.info("APOC version: %s", rec.get("v"))
    except Exception as e:
        logger.error(
            "APOC is not available (needed for apoc.refactor.mergeNodes): %s. "
            "Ensure NEO4J_PLUGINS includes 'apoc' and procedures are unrestricted.",
            e,
        )
        raise SystemExit(1)


async def _drain(session, cypher: str, label: str) -> int:
    """Run a LIMIT-batched write repeatedly, committing each batch in its own
    transaction, until no rows match. Returns the total number of affected rows."""
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


async def _backfill(session) -> int:
    return await _drain(session, _BACKFILL, "backfill")


async def _stamp(session) -> int:
    # apoc.periodic.iterate over ~11.5M edges takes hours. A single outer tx
    # would need a timeout longer than the whole run (fragile if the connection
    # drops), so process in bounded LIMIT chunks, each committed in its own tx
    # with a client timeout that overrides the server's 120s db.transaction.timeout.
    total = 0
    while True:
        tx = await session.begin_transaction(timeout=_STAMP_CHUNK_TIMEOUT)
        try:
            res = await tx.run(_stamp_query(_STAMP_LIMIT, _STAMP_PARALLEL))
            rec = await res.single()
            await tx.commit()
        except Exception:
            await tx.rollback()
            raise
        n = rec.get("stamped", 0) if rec else 0
        if not n:
            break
        total += n
        logger.info("stamp: +%d edges (total %d)", n, total)
    return total


async def _dedup(driver) -> Tuple[int, int]:
    """Merge duplicated name_lower groups. Returns (groups_processed, nodes_deleted)."""
    # Read the list of duplicated name_lower values first.
    async with driver.session() as session:
        res = await session.run(_DUP_NAME_LOWERS)
        name_lowers = [rec["nl"] async for rec in res]

    if not name_lowers:
        logger.info("No duplicated name_lower groups to merge.")
        return (0, 0)

    total = len(name_lowers)
    groups_done = 0
    for start in range(0, total, _DEDUP_BATCH):
        batch = name_lowers[start : start + _DEDUP_BATCH]

        async def _tx(tx):
            for nl in batch:
                await tx.run(_MERGE_GROUP, {"nl": nl})

        async with driver.session() as session:
            await session.execute_write(_tx)

        groups_done += len(batch)
        if groups_done % 5000 == 0 or groups_done == total:
            logger.info("dedup progress %d/%d groups", groups_done, total)

    # Nodes deleted = the count we started with (each group had cnt>1).
    async with driver.session() as session:
        dup = await _single(session, _DUP_GROUP_STATS)
    nodes_deleted = dup.get("nodes_to_delete", 0)
    return (total, nodes_deleted)


async def _recompute_concept_id(session) -> int:
    return await _drain(session, _RECOMPUTE_CONCEPT_ID, "recompute concept_id")


async def _create_constraint(session) -> None:
    await session.run(_CREATE_COMPOSITE_CONSTRAINT)


async def _drop_stale_constraints(session, stale: List[str]) -> None:
    for name in stale:
        try:
            await session.run(f"DROP CONSTRAINT `{name}` IF EXISTS")
            logger.info("Dropped stale constraint %s", name)
        except Exception as e:
            logger.warning("Could not drop stale constraint %s: %s", name, e)


async def main(dry_run: bool, apply: bool) -> None:
    driver = AsyncGraphDatabase.driver(
        NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD)
    )
    start = time.time()

    try:
        await driver.verify_connectivity()
        logger.info("Connected to Neo4j at %s", NEO4J_URI)

        async with driver.session() as session:
            await _verify_apoc(session)
            info = await _inspect(session)
            constraints = await _list_constraints(session)
            stale = _stale_constraints(constraints)

            logger.info(
                "Concept nodes: %s total, %s distinct name_lower",
                info.get("total"),
                info.get("distinct_name_lower"),
            )
            logger.info(
                "Duplicated name_lower: %s groups, %s nodes in groups, "
                "%s nodes to delete",
                info.get("groups"),
                info.get("nodes_in_groups"),
                info.get("nodes_to_delete"),
            )
            if stale:
                logger.warning("Stale legacy constraints found: %s", stale)
            else:
                logger.info("No stale legacy constraints found.")

            if dry_run:
                logger.info(
                    "DRY-RUN complete: no changes written. "
                    "Re-run with --apply to migrate."
                )
                return

            if not apply:
                logger.info("No action taken (pass --apply to write).")
                return

            # --- apply path ---
            if stale:
                await _drop_stale_constraints(session, stale)

            backfilled = await _backfill(session)
            logger.info("Backfilled %s concepts", backfilled)

            stamped = await _stamp(session)
            logger.info("Stamped r.concept_type on %s EXTRACTED_FROM edges", stamped)

        groups, nodes_deleted = await _dedup(driver)
        logger.info("Dedup merged %s groups (deleted ~%s nodes)", groups, nodes_deleted)

        async with driver.session() as session:
            recomputed = await _recompute_concept_id(session)
            logger.info("Recomputed concept_id on %s nodes", recomputed)

            await _create_constraint(session)
            logger.info("Composite constraint concept_scope_unique ensured")

            # Sanity check
            info = await _inspect(session)
            logger.info(
                "Post-migration: %s concepts, %s distinct name_lower, "
                "%s duplicate groups remaining",
                info.get("total"),
                info.get("distinct_name_lower"),
                info.get("groups"),
            )

    finally:
        await driver.close()

    elapsed = time.time() - start
    logger.info("Migration finished in %.1fs (%.1fmin)", elapsed, elapsed / 60)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Emergent-concepts dedup migration (Phase 1 step 3)"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Report what would change without writing anything",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Actually write the migration (backfill, stamp, dedup, recompute, constraint)",
    )
    args = parser.parse_args()
    asyncio.run(main(dry_run=args.dry_run, apply=args.apply))
