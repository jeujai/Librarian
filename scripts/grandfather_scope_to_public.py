#!/usr/bin/env python3
"""
Grandfather pre-scope content to ``scope='public'`` (one-time sweep).

Phase 6 introduced the ``scope`` column private-by-default, but every document
ingested *before* that differentiation predates the privacy model (single test
user; "private" was never a real signal).  This sweep flips that historical
content to public so it is visible to any caller, and drops the orphaned
``:Concept`` nodes the deleted private content left behind.

What it does:

  1. Postgres ``knowledge_sources.scope``  ``private`` -> ``public``
  2. Postgres ``conversation_threads.scope`` ``private`` -> ``public``
  3. Neo4j: ``DETACH DELETE`` every ``:Concept {scope:'private'}`` with no
     ``EXTRACTED_FROM`` evidence (debris from already-deleted private docs /
     conversations).  Private concepts that still hold chunks are NOT touched
     and are reported so they can be re-keyed deliberately.

Future uploads stay private-by-default; only the public checkbox overrides.
This script does not change that default — it only re-scopes existing rows.

Usage:
    venv/bin/python scripts/grandfather_scope_to_public.py --dry-run
    venv/bin/python scripts/grandfather_scope_to_public.py --apply

Environment variables (or .env):
    PG_HOST/PORT/DB/USER/PASSWORD  (defaults: localhost / 5432 /
                                    multimodal_librarian / postgres / postgres)
    NEO4J_URI/USER/PASSWORD         (defaults: bolt://localhost:7687 / neo4j / password)
"""

import argparse
import asyncio
import logging
import os

import asyncpg
from neo4j import AsyncGraphDatabase

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)
logger = logging.getLogger(__name__)

PG_HOST = os.getenv("PG_HOST", "localhost")
PG_PORT = int(os.getenv("PG_PORT", "5432"))
PG_DB = os.getenv("PG_DB", "multimodal_librarian")
PG_USER = os.getenv("PG_USER", "postgres")
PG_PASSWORD = os.getenv("PG_PASSWORD", "postgres")

NEO4J_URI = os.getenv("NEO4J_URI", "bolt://localhost:7687")
NEO4J_USER = os.getenv("NEO4J_USER", "neo4j")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD", "password")

_DOC_COUNT = (
    "SELECT count(*) FROM multimodal_librarian.knowledge_sources "
    "WHERE scope = 'private'"
)
_THREAD_COUNT = (
    "SELECT count(*) FROM multimodal_librarian.conversation_threads "
    "WHERE scope = 'private'"
)
_DOC_FLIP = (
    "UPDATE multimodal_librarian.knowledge_sources "
    "SET scope = 'public' WHERE scope = 'private'"
)
_THREAD_FLIP = (
    "UPDATE multimodal_librarian.conversation_threads "
    "SET scope = 'public' WHERE scope = 'private'"
)

_ORPHAN_PRIVATE_CONCEPT_COUNT = """
MATCH (c:Concept)
WHERE c.scope = 'private'
  AND NOT EXISTS { (c)-[:EXTRACTED_FROM]->(:Chunk) }
RETURN count(c) AS n
"""
_LIVE_PRIVATE_CONCEPT_COUNT = """
MATCH (c:Concept)
WHERE c.scope = 'private'
  AND EXISTS { (c)-[:EXTRACTED_FROM]->(:Chunk) }
RETURN count(c) AS n
"""
_ORPHAN_PRIVATE_CONCEPT_DELETE = """
MATCH (c:Concept)
WHERE c.scope = 'private'
  AND NOT EXISTS { (c)-[:EXTRACTED_FROM]->(:Chunk) }
DETACH DELETE c
RETURN count(c) AS n
"""


async def _single(session, query: str) -> int:
    res = await session.run(query)
    rec = await res.single()
    return rec["n"] if rec else 0


async def main(dry_run: bool, apply: bool) -> None:
    pg = await asyncpg.connect(
        host=PG_HOST, port=PG_PORT, database=PG_DB,
        user=PG_USER, password=PG_PASSWORD,
    )
    driver = AsyncGraphDatabase.driver(
        NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD)
    )

    try:
        doc_n = await pg.fetchval(_DOC_COUNT)
        thread_n = await pg.fetchval(_THREAD_COUNT)
        logger.info(
            "Postgres: %d private knowledge_sources, %d private conversation_threads",
            doc_n, thread_n,
        )

        async with driver.session() as session:
            orphan_n = await _single(session, _ORPHAN_PRIVATE_CONCEPT_COUNT)
            live_n = await _single(session, _LIVE_PRIVATE_CONCEPT_COUNT)
            logger.info(
                "Neo4j: %d orphaned private concepts (deletable), "
                "%d live private concepts (left untouched)",
                orphan_n, live_n,
            )

            if dry_run:
                logger.info("DRY-RUN complete: no changes written.")
                return
            if not apply:
                logger.info("No action taken (pass --apply to write).")
                return

            await pg.execute(_DOC_FLIP)
            await pg.execute(_THREAD_FLIP)
            logger.info(
                "Flipped %d knowledge_sources + %d conversation_threads to public",
                doc_n, thread_n,
            )

            deleted = await _single(session, _ORPHAN_PRIVATE_CONCEPT_DELETE)
            logger.info("Deleted %d orphaned private concepts", deleted)

            if live_n:
                logger.warning(
                    "%d private concepts still hold EXTRACTED_FROM chunks and "
                    "were NOT re-keyed; handle them deliberately.", live_n,
                )

    finally:
        await pg.close()
        await driver.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Grandfather pre-scope content to public (one-time sweep)"
    )
    parser.add_argument("--dry-run", action="store_true",
                        help="Report counts without writing anything")
    parser.add_argument("--apply", action="store_true",
                        help="Actually flip scope and delete orphaned concepts")
    args = parser.parse_args()
    asyncio.run(main(dry_run=args.dry_run, apply=args.apply))
