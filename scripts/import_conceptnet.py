#!/usr/bin/env python3
"""
ConceptNet 5.7 English assertion importer for Neo4j.

Imports ConceptNet English-only triples into the existing Neo4j
instance under a separate label namespace
(:ConceptNetConcept, :ConceptNetRelation) for use as a local
validation gate in the concept extraction pipeline.

Usage:
    python scripts/import_conceptnet.py \
        --neo4j-uri bolt://localhost:7687 \
        --neo4j-user neo4j \
        --neo4j-password password \
        --file-path conceptnet-assertions-5.7.0.csv.gz \
        --batch-size 5000
"""

import argparse
import asyncio
import csv
import gzip
import json
import logging
import time
from dataclasses import dataclass
from io import TextIOWrapper
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class ImportStats:
    """Statistics from a ConceptNet import run."""

    concepts_imported: int = 0
    relationships_imported: int = 0
    duplicates_skipped: int = 0
    errors: int = 0
    duration_seconds: float = 0.0


class ConceptNetImporter:
    """Imports ConceptNet 5.7 English assertions into Neo4j."""

    CONCEPTNET_CSV_URL = (
        "https://s3.amazonaws.com/conceptnet/downloads/2019/"
        "edges/conceptnet-assertions-5.7.0.csv.gz"
    )

    def __init__(
        self,
        neo4j_uri: str,
        neo4j_user: str,
        neo4j_password: str,
    ) -> None:
        self.neo4j_uri = neo4j_uri
        self.neo4j_user = neo4j_user
        self.neo4j_password = neo4j_password
        self._client: Any = None

    async def _get_client(self) -> Any:
        """Lazily create and connect the Neo4j client."""
        if self._client is None:
            from multimodal_librarian.clients.neo4j_client import (  # type: ignore[import-untyped]  # noqa: E501
                Neo4jClient,
            )

            self._client = Neo4jClient(
                uri=self.neo4j_uri,
                user=self.neo4j_user,
                password=self.neo4j_password,
            )
            await self._client.connect()
        return self._client

    async def close(self) -> None:
        """Disconnect the Neo4j client."""
        if self._client is not None:
            await self._client.disconnect()
            self._client = None

    @staticmethod
    def parse_conceptnet_uri(uri: str) -> str:
        """
        Convert a ConceptNet URI to a normalized name.

        Produces lowercase with spaces replacing underscores
        and hyphens.

        Examples:
            /c/en/some_concept      -> "some concept"
            /c/en/New-York          -> "new york"
            /c/en/machine_learning/n -> "machine learning"
        """
        # Strip the /c/en/ prefix
        if uri.startswith("/c/en/"):
            name = uri[len("/c/en/"):]
        else:
            name = uri

        # Remove trailing POS tag / extra path segments
        if "/" in name:
            name = name.split("/")[0]

        # Normalize: underscores/hyphens -> spaces, lowercase
        name = (
            name.replace("_", " ")
            .replace("-", " ")
            .lower()
            .strip()
        )
        return name

    @staticmethod
    def parse_relation_uri(uri: str) -> str:
        """
        Extract the relation type from a relation URI.

        Examples:
            /r/IsA    -> "IsA"
            /r/PartOf -> "PartOf"
        """
        if uri.startswith("/r/"):
            return uri[len("/r/"):]
        return uri

    def parse_assertion_line(
        self, line: List[str]
    ) -> Optional[Dict[str, Any]]:
        """
        Parse a single ConceptNet CSV assertion line.

        ConceptNet CSV format (tab-separated):
          assertion_uri  relation  start_uri  end_uri  json

        Returns a dict or None if not English-only.
        """
        if len(line) < 5:
            return None

        relation_uri = line[1]
        start_uri = line[2]
        end_uri = line[3]
        metadata_str = line[4]

        # Filter to English-only concepts
        if not start_uri.startswith("/c/en/"):
            return None
        if not end_uri.startswith("/c/en/"):
            return None

        # Parse weight from JSON metadata
        weight = 1.0
        try:
            metadata = json.loads(metadata_str)
            weight = float(metadata.get("weight", 1.0))
        except (json.JSONDecodeError, ValueError, TypeError):
            pass

        return {
            "concept1_uri": start_uri,
            "concept1_name": self.parse_conceptnet_uri(start_uri),
            "concept2_uri": end_uri,
            "concept2_name": self.parse_conceptnet_uri(end_uri),
            "relation": self.parse_relation_uri(relation_uri),
            "weight": weight,
            "assertion_uri": line[0],
        }

    async def create_indexes(self) -> None:
        """Create indexes on :ConceptNetConcept for fast lookup."""
        client = await self._get_client()

        queries = [
            (
                "CREATE INDEX conceptnet_name IF NOT EXISTS "
                "FOR (n:ConceptNetConcept) ON (n.name)"
            ),
            (
                "CREATE INDEX conceptnet_uri IF NOT EXISTS "
                "FOR (n:ConceptNetConcept) ON (n.uri)"
            ),
        ]
        for query in queries:
            try:
                await client.execute_write_query(query)
                logger.info("Created index: %s", query)
            except Exception as e:
                logger.warning("Index creation note: %s", e)

    async def _import_batch(
        self,
        batch: List[Dict[str, Any]],
        stats: ImportStats,
    ) -> None:
        """Import a batch of parsed assertions into Neo4j."""
        client = await self._get_client()

        # Deduplicate nodes within the batch
        nodes_data: List[Dict[str, str]] = []
        seen_uris: set[str] = set()
        for item in batch:
            for prefix in ("concept1", "concept2"):
                uri = item[f"{prefix}_uri"]
                if uri not in seen_uris:
                    seen_uris.add(uri)
                    nodes_data.append({
                        "name": item[f"{prefix}_name"],
                        "uri": uri,
                        "language": "en",
                    })

        rels_data = [
            {
                "start_uri": item["concept1_uri"],
                "end_uri": item["concept2_uri"],
                "relation_type": item["relation"],
                "weight": item["weight"],
                "source_uri": item["assertion_uri"],
            }
            for item in batch
        ]

        # MERGE concept nodes
        node_query = """
        UNWIND $nodes AS node
        MERGE (c:ConceptNetConcept {uri: node.uri})
        ON CREATE SET
            c.name = node.name,
            c.language = node.language
        """
        try:
            await client.execute_write_query(
                node_query, {"nodes": nodes_data}
            )
            stats.concepts_imported += len(nodes_data)
        except Exception as e:
            logger.error("Error importing concept batch: %s", e)
            stats.errors += 1

        # MERGE relationships
        rel_query = """
        UNWIND $rels AS rel
        MATCH (a:ConceptNetConcept {uri: rel.start_uri})
        MATCH (b:ConceptNetConcept {uri: rel.end_uri})
        MERGE (a)-[r:ConceptNetRelation {
            source_uri: rel.source_uri
        }]->(b)
        ON CREATE SET
            r.relation_type = rel.relation_type,
            r.weight = rel.weight
        """
        try:
            await client.execute_write_query(
                rel_query, {"rels": rels_data}
            )
            stats.relationships_imported += len(rels_data)
        except Exception as e:
            logger.error("Error importing rel batch: %s", e)
            stats.errors += 1

    async def import_assertions(
        self,
        file_path: str,
        batch_size: int = 5000,
    ) -> ImportStats:
        """
        Parse ConceptNet 5.7 CSV and batch-import into Neo4j.

        Args:
            file_path: Path to the ConceptNet CSV (gz or plain).
            batch_size: Assertions per Neo4j batch write.

        Returns:
            ImportStats with counts of imported data.
        """
        stats = ImportStats()
        start_time = time.time()

        await self.create_indexes()

        batch: List[Dict[str, Any]] = []
        lines_processed = 0

        if file_path.endswith(".gz"):
            fh = gzip.open(
                file_path, mode="rt", encoding="utf-8"
            )
        else:
            fh = open(
                file_path, mode="r", encoding="utf-8"
            )

        try:
            reader = csv.reader(fh, delimiter="\t")
            for line in reader:
                lines_processed += 1
                parsed = self.parse_assertion_line(line)
                if parsed is None:
                    continue

                batch.append(parsed)

                if len(batch) >= batch_size:
                    await self._import_batch(batch, stats)
                    batch = []

                    progress = batch_size * 10
                    if lines_processed % progress == 0:
                        logger.info(
                            "Processed %d lines, "
                            "%d concepts, %d rels",
                            lines_processed,
                            stats.concepts_imported,
                            stats.relationships_imported,
                        )

            if batch:
                await self._import_batch(batch, stats)
        finally:
            fh.close()

        stats.duration_seconds = time.time() - start_time

        logger.info(
            "Import complete: %d concepts, %d rels, "
            "%d dupes skipped, %d errors, %.1fs",
            stats.concepts_imported,
            stats.relationships_imported,
            stats.duplicates_skipped,
            stats.errors,
            stats.duration_seconds,
        )

        return stats


def parse_args() -> argparse.Namespace:
    """Parse CLI arguments."""
    parser = argparse.ArgumentParser(
        description=(
            "Import ConceptNet 5.7 English assertions "
            "into Neo4j"
        )
    )
    parser.add_argument(
        "--neo4j-uri",
        default="bolt://localhost:7687",
        help="Neo4j URI (default: bolt://localhost:7687)",
    )
    parser.add_argument(
        "--neo4j-user",
        default="neo4j",
        help="Neo4j username (default: neo4j)",
    )
    parser.add_argument(
        "--neo4j-password",
        default="password",
        help="Neo4j password (default: password)",
    )
    parser.add_argument(
        "--file-path",
        required=True,
        help="Path to ConceptNet CSV (gzipped or plain)",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=5000,
        help="Batch size for Neo4j imports (default: 5000)",
    )
    return parser.parse_args()


async def main() -> None:
    """CLI entry point."""
    args = parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format=(
            "%(asctime)s - %(name)s - "
            "%(levelname)s - %(message)s"
        ),
    )

    importer = ConceptNetImporter(
        neo4j_uri=args.neo4j_uri,
        neo4j_user=args.neo4j_user,
        neo4j_password=args.neo4j_password,
    )

    try:
        stats = await importer.import_assertions(
            file_path=args.file_path,
            batch_size=args.batch_size,
        )
        print("\nImport Statistics:")
        print(
            f"  Concepts imported:     "
            f" {stats.concepts_imported}"
        )
        print(
            f"  Relationships imported:"
            f" {stats.relationships_imported}"
        )
        print(
            f"  Duplicates skipped:    "
            f" {stats.duplicates_skipped}"
        )
        print(f"  Errors:                {stats.errors}")
        print(
            f"  Duration:              "
            f" {stats.duration_seconds:.1f}s"
        )
    finally:
        await importer.close()


if __name__ == "__main__":
    asyncio.run(main())
