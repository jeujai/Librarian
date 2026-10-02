#!/usr/bin/env python3
"""
Human-gate freeze: flip a Concept's bridge_status from 'emergent' to 'canonical'.

Per the emergent-concepts architecture (§5.4, §4.1), ``bridge_status='canonical'``
is reached ONLY by explicit human gate — a ``SAME_AS`` to UMLS does NOT flip it.
This script is that gate: it marks a named public concept as frozen/canonical.

Freezing is reversible: the prior ``provenance`` is backed up to
``prior_provenance`` before being nulled (the doc §4.2/§8 convention is that
canonical nodes carry ``provenance IS NULL``), so ``--unfreeze`` restores it
losslessly. Idempotent: re-freezing a frozen concept is a no-op on the lifecycle
fields (only ``updated_at`` changes).

Usage:
    python scripts/freeze_concept.py "work restrictions"
    python scripts/freeze_concept.py "work restrictions" --unfreeze
    python scripts/freeze_concept.py "work restrictions" --dry-run

Environment variables (or .env):
    NEO4J_URI          (default: bolt://localhost:7687)
    NEO4J_USER         (default: neo4j)
    NEO4J_PASSWORD     (default: password)
"""

import argparse
import asyncio
import os
from datetime import datetime

from neo4j import AsyncGraphDatabase

NEO4J_URI = os.getenv("NEO4J_URI", "bolt://localhost:7687")
NEO4J_USER = os.getenv("NEO4J_USER", "neo4j")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD", "password")

_FREEZE = """
MATCH (c:Concept {name_lower: toLower($name), scope: 'public'})
SET c.bridge_status = 'canonical',
    c.prior_provenance = COALESCE(c.prior_provenance, c.provenance),
    c.provenance = NULL,
    c.updated_at = $ts
RETURN c.name AS name, c.bridge_status AS bridge_status,
       c.provenance AS provenance, c.prior_provenance AS prior_provenance
"""

_UNFREEZE = """
MATCH (c:Concept {name_lower: toLower($name), scope: 'public'})
SET c.bridge_status = 'emergent',
    c.provenance = c.prior_provenance,
    c.prior_provenance = NULL,
    c.updated_at = $ts
RETURN c.name AS name, c.bridge_status AS bridge_status,
       c.provenance AS provenance, c.prior_provenance AS prior_provenance
"""

_READ = """
MATCH (c:Concept {name_lower: toLower($name), scope: 'public'})
RETURN c.name AS name, c.bridge_status AS bridge_status,
       c.provenance AS provenance, c.prior_provenance AS prior_provenance
"""


async def main():
    parser = argparse.ArgumentParser(
        description="Freeze (canonicalize) or unfreeze a public Concept."
    )
    parser.add_argument("name", help="Concept name (case-insensitive)")
    parser.add_argument(
        "--unfreeze",
        action="store_true",
        help="Restore bridge_status='emergent' and the backed-up provenance",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print current state and intended change without writing",
    )
    args = parser.parse_args()

    driver = AsyncGraphDatabase.driver(
        NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD)
    )
    ts = datetime.utcnow().isoformat()

    try:
        async with driver.session() as session:
            result = await session.run(_READ, {"name": args.name})
            rec = await result.single()
            if rec is None:
                print(f"No public Concept named {args.name!r} found.")
                await driver.close()
                raise SystemExit(1)

            before = rec.data()
            action = "unfreeze" if args.unfreeze else "freeze"
            print(f"Current: {before}")
            print(f"Would {action}: "
                  f"bridge_status={'emergent' if args.unfreeze else 'canonical'}")

            if args.dry_run:
                await driver.close()
                return

            query = _UNFREEZE if args.unfreeze else _FREEZE
            result = await session.run(query, {"name": args.name, "ts": ts})
            rec = await result.single()
            print(f"After:   {rec.data() if rec else None}")

    finally:
        await driver.close()


if __name__ == "__main__":
    asyncio.run(main())
