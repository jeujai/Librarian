#!/usr/bin/env python3
"""
UMLS Synonym Migration Script.

Creates UMLSSynonym nodes and HAS_SYNONYM relationships from existing
UMLSConcept.lower_synonyms list properties. This enables index-backed
synonym lookups instead of full-scan list property queries.

Safe to run multiple times (uses MERGE for idempotency).

Usage:
    python scripts/migrate_umls_synonyms.py
    python scripts/migrate_umls_synonyms.py --batch-size 10000
    docker compose exec app python scripts/migrate_umls_synonyms.py
"""

import argparse
import asyncio
import os

import structlog

logger = structlog.get_logger(__name__)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="migrate_umls_synonyms",
        description="Create UMLSSynonym nodes from existing UMLSConcept data",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=5000,
        help="Nodes per batch (default: 5000)",
    )
    parser.add_argument(
        "--neo4j-uri",
        default=None,
        help="Neo4j bolt URI (default: env NEO4J_URI)",
    )
    parser.add_argument(
        "--neo4j-user",
        default=None,
        help="Neo4j username (default: env NEO4J_USER)",
    )
    parser.add_argument(
        "--neo4j-password",
        default=None,
        help="Neo4j password (default: env NEO4J_PASSWORD)",
    )
    return parser


async def run_migration(args: argparse.Namespace) -> None:
    from multimodal_librarian.clients.neo4j_client import Neo4jClient
    from multimodal_librarian.components.knowledge_graph.umls_loader import (  # noqa: E501
        UMLSLoader,
    )

    uri = args.neo4j_uri or os.environ.get(
        "NEO4J_URI", "bolt://localhost:7687"
    )
    user = args.neo4j_user or os.environ.get("NEO4J_USER", "neo4j")
    password = args.neo4j_password or os.environ.get(
        "NEO4J_PASSWORD", "password"
    )

    client = Neo4jClient(uri=uri, user=user, password=password)
    await client.connect()

    try:
        loader = UMLSLoader(neo4j_client=client)

        # Ensure the UMLSSynonym RANGE index exists
        logger.info("creating_indexes")
        await loader.create_indexes()
        logger.info("indexes_created")

        # Run the migration
        logger.info(
            "starting_synonym_migration",
            batch_size=args.batch_size,
        )
        result = await loader.migrate_synonyms(
            batch_size=args.batch_size
        )

        logger.info(
            "migration_summary",
            nodes_created=result.nodes_created,
            relationships_created=result.relationships_created,
            batches_completed=result.batches_completed,
            batches_failed=result.batches_failed,
            elapsed_seconds=result.elapsed_seconds,
        )

        if result.batches_failed > 0:
            logger.warning(
                "migration_had_failures",
                batches_failed=result.batches_failed,
                message=(
                    "Some batches failed. Re-run to"
                    " retry (MERGE is idempotent)."
                ),
            )
    finally:
        await client.close()


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    asyncio.run(run_migration(args))


if __name__ == "__main__":
    main()
