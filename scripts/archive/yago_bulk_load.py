#!/usr/bin/env python3
"""
YAGO 4.5 Bulk Load Script

Downloads YAGO 4.5 zip archives, extracts Turtle files, parses them,
and loads entities into Neo4j for local querying.

Usage:
    python scripts/yago_bulk_load.py [--dump-dir /path] [--batch-size 1000]
    python scripts/yago_bulk_load.py --clear
    python scripts/yago_bulk_load.py --test --test-entities 1000
    python scripts/yago_bulk_load.py --download-only
    python scripts/yago_bulk_load.py --full  # use full dataset (~12GB)

Requirements:
    - Neo4j must be running
    - unzip command available (for extracting YAGO zip archives)
    - ~15GB disk space for full dataset, ~500MB for tiny
"""

import argparse
import asyncio
import logging
import os
import sys
from pathlib import Path

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from multimodal_librarian.clients.neo4j_client import Neo4jClient
from multimodal_librarian.components.yago.loader import YagoNeo4jLoader
from multimodal_librarian.components.yago.processor import YagoDumpProcessor

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger("yago_bulk_load")


def _create_neo4j_client() -> Neo4jClient:
    """Create a Neo4j client using environment variables."""
    return Neo4jClient(
        uri=os.getenv("NEO4J_URI", "bolt://localhost:7687"),
        user=os.getenv("NEO4J_USER", "neo4j"),
        password=os.getenv("NEO4J_PASSWORD", "password"),
    )


async def ensure_indexes(neo4j_client: Neo4jClient) -> None:
    """Ensure required indexes exist for YAGO data."""
    logger.info("Creating YAGO indexes...")

    index_statements = [
        "CREATE INDEX yago_entity_id_index IF NOT EXISTS "
        "FOR (e:YagoEntity) ON (e.entity_id)",
        "CREATE INDEX yago_entity_label_index IF NOT EXISTS "
        "FOR (e:YagoEntity) ON (e.label)",
    ]

    for stmt in index_statements:
        try:
            await neo4j_client.execute_query(stmt)
        except Exception as e:
            logger.debug(f"Index creation note: {e}")

    logger.info("YAGO indexes ensured")


async def run_bulk_load(
    dump_dir: Path,
    batch_size: int = 1000,
    clear_existing: bool = False,
    variant: str = "tiny",
    download_only: bool = False,
) -> None:
    """Run the complete YAGO 4.5 bulk load process.

    Args:
        dump_dir: Directory to store dump files.
        batch_size: Entities per batch import.
        clear_existing: Clear existing data first.
        variant: 'tiny' (~200MB) or 'full' (~12GB).
        download_only: Only download, don't process/import.
    """
    logger.info("=" * 60)
    logger.info("YAGO 4.5 BULK LOAD")
    logger.info(f"Variant: {variant}")
    logger.info("=" * 60)

    processor = YagoDumpProcessor(
        dump_dir=dump_dir,
        memory_limit_bytes=512 * 1024 * 1024,
    )

    # Step 1: Download YAGO zip
    logger.info("[1/5] Downloading YAGO 4.5 zip...")
    zip_path = await processor.download(variant=variant, resume=True)
    logger.info(f"  Downloaded: {zip_path}")

    # Step 2: Extract TTL files
    logger.info("[2/5] Extracting TTL files...")
    extracted = processor.extract_zip(variant=variant)
    for p in extracted:
        logger.info(f"  {p.name}: {p.stat().st_size / (1024**2):.1f} MB")

    if download_only:
        logger.info("Download-only mode. Exiting.")
        return

    # Step 3: Connect to Neo4j
    logger.info("[3/5] Connecting to Neo4j...")
    neo4j_client = _create_neo4j_client()
    await neo4j_client.connect()
    logger.info("Connected to Neo4j successfully")

    # Step 4: Ensure indexes
    logger.info("[4/5] Ensuring Neo4j indexes...")
    await ensure_indexes(neo4j_client)

    if clear_existing:
        logger.info("Clearing existing YAGO data...")
        loader = YagoNeo4jLoader(
            neo4j_client=neo4j_client, batch_size=batch_size
        )
        await loader.clear_all()
        logger.info("Existing data cleared")

    # Step 5: Process and import
    logger.info("[5/5] Processing YAGO dumps and importing...")
    logger.info(f"Batch size: {batch_size}")

    loader = YagoNeo4jLoader(
        neo4j_client=neo4j_client,
        batch_size=batch_size,
    )

    entity_count = 0
    async for entity in processor.process(variant=variant):
        await loader.create_entity_node(entity)

        relationships = []
        for target_id in entity.instance_of:
            if target_id:
                relationships.append(
                    {"target_id": target_id, "type": "INSTANCE_OF"}
                )
        for target_id in entity.subclass_of:
            if target_id:
                relationships.append(
                    {"target_id": target_id, "type": "SUBCLASS_OF"}
                )

        if relationships:
            await loader.create_relationships(
                entity.entity_id, relationships
            )

        entity_count += 1

        if entity_count % 10000 == 0:
            progress = loader.get_progress()
            logger.info(
                f"Imported {entity_count:,} entities "
                f"(rels: {progress['relationships_created']:,})"
            )

    stats = await loader.get_stats()

    logger.info("=" * 60)
    logger.info("YAGO 4.5 BULK LOAD COMPLETE")
    logger.info("=" * 60)
    logger.info(f"Entities imported: {stats.entity_count:,}")
    logger.info(f"Relationships: {stats.relationship_count:,}")
    logger.info(f"  INSTANCE_OF: {stats.instance_of_count:,}")
    logger.info(f"  SUBCLASS_OF: {stats.subclass_of_count:,}")
    logger.info(
        f"Est. storage: "
        f"{stats.storage_bytes / (1024**3):.1f} GB"
    )

    await neo4j_client.close()
    logger.info("Neo4j connection closed")


async def run_quick_test(
    dump_dir: Path,
    entity_limit: int = 1000,
    batch_size: int = 100,
    variant: str = "tiny",
) -> None:
    """Run a quick test with limited entities."""
    logger.info("=" * 60)
    logger.info("YAGO 4.5 BULK LOAD - QUICK TEST")
    logger.info(f"Limiting to {entity_limit:,} entities")
    logger.info(f"Variant: {variant}")
    logger.info("=" * 60)

    processor = YagoDumpProcessor(
        dump_dir=dump_dir,
        memory_limit_bytes=512 * 1024 * 1024,
    )

    # Step 1: Download
    logger.info("[1/5] Downloading YAGO zip...")
    zip_path = dump_dir / processor.YAGO_ZIPS[variant]["filename"]
    if not zip_path.exists():
        await processor.download(variant=variant, resume=True)
    else:
        logger.info(f"  Already downloaded: {zip_path}")

    # Step 2: Extract
    logger.info("[2/5] Extracting TTL files...")
    processor.extract_zip(variant=variant)

    # Step 3: Connect to Neo4j
    logger.info("[3/5] Connecting to Neo4j...")
    neo4j_client = _create_neo4j_client()
    await neo4j_client.connect()

    logger.info("[4/5] Ensuring Neo4j indexes...")
    await ensure_indexes(neo4j_client)

    logger.info("Clearing existing YAGO data...")
    loader = YagoNeo4jLoader(
        neo4j_client=neo4j_client, batch_size=batch_size
    )
    await loader.clear_all()

    logger.info(f"[5/5] Processing (limited to {entity_limit:,})...")

    entity_count = 0
    async for entity in processor.process(
        file_keys=["facts"],
        variant=variant,
    ):
        if entity_count >= entity_limit:
            break

        await loader.create_entity_node(entity)

        relationships = []
        for tid in entity.instance_of:
            if tid:
                relationships.append(
                    {"target_id": tid, "type": "INSTANCE_OF"}
                )
        for tid in entity.subclass_of:
            if tid:
                relationships.append(
                    {"target_id": tid, "type": "SUBCLASS_OF"}
                )

        if relationships:
            await loader.create_relationships(
                entity.entity_id, relationships
            )

        entity_count += 1
        if entity_count % 500 == 0:
            logger.info(f"Processed {entity_count:,}...")

    stats = await loader.get_stats()

    logger.info("=" * 60)
    logger.info("QUICK TEST COMPLETE")
    logger.info("=" * 60)
    logger.info(f"Entities: {stats.entity_count:,}")
    logger.info(f"Relationships: {stats.relationship_count:,}")
    logger.info(f"  INSTANCE_OF: {stats.instance_of_count:,}")
    logger.info(f"  SUBCLASS_OF: {stats.subclass_of_count:,}")

    await neo4j_client.close()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Download YAGO 4.5 and bulk-load to Neo4j"
    )
    parser.add_argument(
        "--dump-dir",
        type=Path,
        default=Path("./yago-dumps"),
        help="Directory to store YAGO dump files",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=1000,
        help="Entities per batch import",
    )
    parser.add_argument(
        "--clear",
        action="store_true",
        help="Clear existing data before loading",
    )
    parser.add_argument(
        "--test",
        action="store_true",
        help="Quick test with limited entities",
    )
    parser.add_argument(
        "--test-entities",
        type=int,
        default=1000,
        help="Entity count for test mode",
    )
    parser.add_argument(
        "--full",
        action="store_true",
        help="Use full dataset (~12GB) instead of tiny (~200MB)",
    )
    parser.add_argument(
        "--download-only",
        action="store_true",
        help="Only download files, skip import",
    )

    args = parser.parse_args()
    variant = "full" if args.full else "tiny"

    args.dump_dir.mkdir(parents=True, exist_ok=True)
    logger.info(f"Using dump directory: {args.dump_dir}")

    if args.test:
        asyncio.run(
            run_quick_test(
                dump_dir=args.dump_dir,
                entity_limit=args.test_entities,
                batch_size=args.batch_size,
                variant=variant,
            )
        )
    else:
        asyncio.run(
            run_bulk_load(
                dump_dir=args.dump_dir,
                batch_size=args.batch_size,
                clear_existing=args.clear,
                variant=variant,
                download_only=args.download_only,
            )
        )


if __name__ == "__main__":
    main()
