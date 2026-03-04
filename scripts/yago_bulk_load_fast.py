#!/usr/bin/env python3
"""
YAGO 4.5 Fast Bulk Load Script

Optimized version that uses UNWIND batch imports for 10-50x faster loading.
Processes the extracted yago-tiny.ttl (or yago-full.ttl) and loads entities
into Neo4j using batched Cypher queries.

Usage:
    python scripts/yago_bulk_load_fast.py [--dump-dir ./yago-dumps] [--batch-size 2000]

Requirements:
    - Neo4j must be running (bolt://localhost:7687)
    - yago-dumps/extracted/yago-tiny.ttl must exist (run regular script with --download-only first)
"""

import argparse
import json
import logging
import re
import sys
import time
from pathlib import Path

from neo4j import GraphDatabase

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger("yago_fast_load")

# Suppress neo4j deprecation warnings
logging.getLogger("neo4j.notifications").setLevel(logging.ERROR)

# IRI prefixes
YAGO_RESOURCE = "http://yago-knowledge.org/resource/"
SCHEMA_ORG = "http://schema.org/"
WIKIDATA_ENTITY = "http://www.wikidata.org/entity/"

# Regex for language-tagged literals
_LANG_RE = re.compile(r'^"(.+)"@([\w-]+)$')
_PLAIN_RE = re.compile(r'^"(.+)"$')
_TYPED_RE = re.compile(r'^"(.+)"\^\^(.+)$')


def parse_literal(obj_str):
    """Parse a Turtle literal into (value, lang)."""
    m = _LANG_RE.match(obj_str)
    if m:
        return m.group(1), m.group(2).lower()
    m = _TYPED_RE.match(obj_str)
    if m:
        return m.group(1), None
    m = _PLAIN_RE.match(obj_str)
    if m:
        return m.group(1), None
    return obj_str, None


def is_english(lang):
    if lang is None:
        return True
    return lang in ("en", "en-us", "en-gb", "en-ca")


def expand_prefix(prefixed, prefixes):
    if prefixed.startswith("<") and prefixed.endswith(">"):
        return prefixed[1:-1]
    if ":" in prefixed:
        prefix, local = prefixed.split(":", 1)
        if prefix in prefixes:
            return prefixes[prefix] + local
    return prefixed


def iri_to_id(iri):
    if iri.startswith(YAGO_RESOURCE):
        return iri[len(YAGO_RESOURCE):]
    if iri.startswith(SCHEMA_ORG):
        return iri[len(SCHEMA_ORG):]
    return iri


def extract_yago_id(prefixed):
    if ":" in prefixed:
        return prefixed.split(":", 1)[1]
    return prefixed


def extract_wikidata_qid(iri):
    if iri.startswith(WIKIDATA_ENTITY):
        qid = iri[len(WIKIDATA_ENTITY):]
        if qid.startswith("Q"):
            return qid
    return None


def stream_entities(ttl_path):
    """Stream-parse a YAGO TTL file, yielding entity dicts.

    Each entity dict has: entity_id, label, description, instance_of,
    subclass_of, aliases, see_also.
    """
    prefixes = {}
    current_subject = None
    current_data = None
    line_count = 0

    with open(ttl_path, "r", encoding="utf-8") as f:
        for raw_line in f:
            line_count += 1
            line = raw_line.strip()

            if not line:
                continue

            if line.startswith("@prefix"):
                parts = line.split()
                if len(parts) >= 3:
                    prefix = parts[1].rstrip(":")
                    iri = parts[2].strip("<>")
                    prefixes[prefix] = iri
                continue

            if line.startswith("#"):
                continue
            if line.startswith(("ys:", "sh:")):
                continue
            if (line.startswith(" ") or line.startswith("\t")) and current_subject is None:
                continue

            # Parse triple
            if line.endswith(" ."):
                line = line[:-2]
            elif line.endswith("\t."):
                line = line[:-2]
            elif line.endswith("."):
                line = line[:-1]
            elif line.endswith(" ;"):
                line = line[:-2]
            elif line.endswith("\t;"):
                line = line[:-2]
            elif line.endswith(";"):
                line = line[:-1]
            line = line.strip()

            parts = line.split("\t")
            if len(parts) < 3:
                parts = line.split(None, 2)

            if len(parts) >= 3:
                subj = expand_prefix(parts[0].strip(), prefixes)
                pred = expand_prefix(parts[1].strip(), prefixes)
                obj_raw = parts[2].strip()

                if not subj.startswith(YAGO_RESOURCE) and not subj.startswith(SCHEMA_ORG):
                    continue

                entity_id = iri_to_id(subj)
            elif len(parts) == 2 and current_subject is not None:
                # Turtle continuation line (after ;) — reuse current subject
                pred = expand_prefix(parts[0].strip(), prefixes)
                obj_raw = parts[1].strip()
                entity_id = current_subject
            else:
                continue

            if entity_id != current_subject:
                if current_subject is not None and current_data:
                    entity = build_entity(current_subject, current_data)
                    if entity is not None:
                        yield entity

                current_subject = entity_id
                current_data = {
                    "labels": [], "descriptions": [], "aliases": [],
                    "types": [], "subclass_of": [], "same_as": [],
                    "see_also": [], "wikidata_id": None,
                }

            # Accumulate
            accumulate(pred, obj_raw, current_data)

            if line_count % 5_000_000 == 0:
                logger.info(f"Parsed {line_count:,} lines...")

    # Last entity
    if current_subject is not None and current_data:
        entity = build_entity(current_subject, current_data)
        if entity is not None:
            yield entity

    logger.info(f"Finished parsing: {line_count:,} lines total")


def accumulate(pred, obj_raw, data):
    if pred in ("http://www.w3.org/2000/01/rdf-schema#label", f"{SCHEMA_ORG}name"):
        value, lang = parse_literal(obj_raw)
        data["labels"].append(value)
    elif pred in ("http://www.w3.org/2000/01/rdf-schema#comment", f"{SCHEMA_ORG}description"):
        value, lang = parse_literal(obj_raw)
        data["descriptions"].append(value)
    elif pred == f"{SCHEMA_ORG}alternateName":
        value, lang = parse_literal(obj_raw)
        data["aliases"].append(value)
    elif pred == "http://www.w3.org/1999/02/22-rdf-syntax-ns#type":
        type_id = extract_yago_id(obj_raw)
        if type_id:
            data["types"].append(type_id)
    elif pred == "http://www.w3.org/2000/01/rdf-schema#subClassOf":
        parent_id = extract_yago_id(obj_raw)
        if parent_id:
            data["subclass_of"].append(parent_id)
    elif pred in ("http://www.w3.org/2002/07/owl#sameAs", f"{SCHEMA_ORG}sameAs"):
        value, _ = parse_literal(obj_raw)
        qid = extract_wikidata_qid(value)
        if qid:
            data["wikidata_id"] = qid
        data["same_as"].append(value)


def build_entity(entity_id, data):
    label = data["labels"][0] if data["labels"] else None
    has_subclass = bool(data["subclass_of"])
    has_types = bool(data["types"])
    # Keep entities with labels OR those that participate in the class hierarchy
    if not label and not has_subclass and not has_types:
        return None
    description = data["descriptions"][0] if data["descriptions"] else None
    eid = data.get("wikidata_id") or entity_id
    return {
        "entity_id": eid,
        "label": label or eid,  # fallback to entity_id for class nodes
        "description": description or "",
        "instance_of": data["types"],
        "subclass_of": data["subclass_of"],
        "aliases": data["aliases"],
        "see_also": data["see_also"],
    }


def batch_create_entities(tx, batch):
    """Create YagoEntity nodes in bulk using UNWIND."""
    rows = []
    for e in batch:
        rows.append({
            "entity_id": e["entity_id"],
            "label": e["label"],
            "description": e["description"],
            "data": json.dumps(e),
        })
    tx.run(
        """
        UNWIND $rows AS row
        MERGE (e:YagoEntity {entity_id: row.entity_id})
        SET e.label = row.label,
            e.description = row.description,
            e.data = row.data
        """,
        rows=rows,
    )


def batch_create_relationships(tx, rel_batch):
    """Create relationships in bulk using UNWIND.

    rel_batch is a list of dicts: {source_id, target_id, rel_type}
    We group by rel_type and run one UNWIND per type.
    """
    by_type = {}
    for r in rel_batch:
        by_type.setdefault(r["rel_type"], []).append(r)

    for rel_type, rels in by_type.items():
        rows = [{"source": r["source_id"], "target": r["target_id"]} for r in rels]
        if rel_type == "INSTANCE_OF":
            tx.run(
                """
                UNWIND $rows AS row
                MATCH (e:YagoEntity {entity_id: row.source})
                MATCH (t:YagoEntity {entity_id: row.target})
                MERGE (e)-[:INSTANCE_OF]->(t)
                """,
                rows=rows,
            )
        elif rel_type == "SUBCLASS_OF":
            tx.run(
                """
                UNWIND $rows AS row
                MATCH (e:YagoEntity {entity_id: row.source})
                MERGE (t:YagoEntity {entity_id: row.target})
                MERGE (e)-[:SUBCLASS_OF]->(t)
                """,
                rows=rows,
            )


def flush_batch(driver, batch):
    """Create entities and their relationships in one go."""
    # 1. Create entity nodes
    with driver.session() as session:
        session.execute_write(batch_create_entities, batch)

    # 2. Collect and create relationships for this batch
    rels = []
    for e in batch:
        for tid in e["instance_of"]:
            if tid:
                rels.append({"source_id": e["entity_id"], "target_id": tid, "rel_type": "INSTANCE_OF"})
        for tid in e["subclass_of"]:
            if tid:
                rels.append({"source_id": e["entity_id"], "target_id": tid, "rel_type": "SUBCLASS_OF"})

    if rels:
        with driver.session() as session:
            session.execute_write(batch_create_relationships, rels)

    return len(rels)


def post_load_cleanup(driver):
    """Prune dead-end labelless nodes after bulk load.

    Removes YagoEntity nodes that:
    - Have no real label (label == entity_id, i.e. fallback was used)
    - Have no inbound edges (nothing points to them via
      INSTANCE_OF or SUBCLASS_OF)

    These are leaf taxonomy nodes that add no enrichment value.
    """
    logger.info("=" * 60)
    logger.info("POST-LOAD CLEANUP: pruning dead-end labelless nodes")

    with driver.session() as session:
        # Count before
        r = session.run(
            "MATCH (e:YagoEntity) RETURN count(e) as c"
        )
        before = r.single()["c"]

        # Single pass — remove only true leaf dead-ends, no cascade
        total_deleted = 0
        while True:
            r = session.run(
                """
                MATCH (e:YagoEntity)
                WHERE e.label = e.entity_id
                  AND NOT ()-[:SUBCLASS_OF]->(e)
                  AND NOT ()-[:INSTANCE_OF]->(e)
                WITH e LIMIT 10000
                DETACH DELETE e
                RETURN count(*) as deleted
                """
            )
            deleted = r.single()["deleted"]
            total_deleted += deleted
            if deleted > 0:
                logger.info(f"  Pruned {total_deleted:,} so far...")
            if deleted < 10000:
                break

        r = session.run(
            "MATCH (e:YagoEntity) RETURN count(e) as c"
        )
        after = r.single()["c"]

    logger.info(f"Pruned {total_deleted:,} dead-end labelless nodes")
    logger.info(f"Nodes: {before:,} -> {after:,}")
    logger.info("=" * 60)


def main():
    parser = argparse.ArgumentParser(description="Fast YAGO bulk load with UNWIND batching")
    parser.add_argument("--dump-dir", type=Path, default=Path("./yago-dumps"))
    parser.add_argument("--batch-size", type=int, default=2000, help="Entities per UNWIND batch")
    parser.add_argument("--neo4j-uri", default="bolt://localhost:7687")
    parser.add_argument("--neo4j-user", default="neo4j")
    parser.add_argument("--neo4j-password", default="password")
    args = parser.parse_args()

    ttl_path = args.dump_dir / "extracted" / "yago-tiny.ttl"
    if not ttl_path.exists():
        logger.error(f"TTL file not found: {ttl_path}")
        logger.error("Run: python scripts/yago_bulk_load.py --download-only first")
        sys.exit(1)

    logger.info("=" * 60)
    logger.info("YAGO 4.5 FAST BULK LOAD (UNWIND batching)")
    logger.info(f"TTL: {ttl_path} ({ttl_path.stat().st_size / (1024**3):.2f} GB)")
    logger.info(f"Batch size: {args.batch_size}")
    logger.info("=" * 60)

    driver = GraphDatabase.driver(args.neo4j_uri, auth=(args.neo4j_user, args.neo4j_password))

    # Ensure indexes
    with driver.session() as session:
        session.run("CREATE INDEX yago_entity_id_index IF NOT EXISTS FOR (e:YagoEntity) ON (e.entity_id)")
        session.run("CREATE INDEX yago_entity_label_index IF NOT EXISTS FOR (e:YagoEntity) ON (e.label)")
    logger.info("Indexes ensured")

    logger.info("Loading entities and relationships (single pass)...")
    start = time.time()
    entity_count = 0
    rel_count = 0
    batch = []

    for entity in stream_entities(ttl_path):
        batch.append(entity)

        if len(batch) >= args.batch_size:
            rels = flush_batch(driver, batch)
            entity_count += len(batch)
            rel_count += rels
            batch = []

            if entity_count % 10_000 == 0:
                elapsed = time.time() - start
                rate = entity_count / elapsed if elapsed > 0 else 0
                logger.info(
                    f"Entities: {entity_count:,} | "
                    f"Rels: {rel_count:,} | "
                    f"Rate: {rate:,.0f} ent/sec | "
                    f"Elapsed: {elapsed:.0f}s"
                )

    # Flush remaining
    if batch:
        rels = flush_batch(driver, batch)
        entity_count += len(batch)
        rel_count += rels

    total_time = time.time() - start

    logger.info("=" * 60)
    logger.info("YAGO 4.5 FAST BULK LOAD COMPLETE")
    logger.info("=" * 60)
    logger.info(f"Entities:       {entity_count:,}")
    logger.info(f"Relationships:  {rel_count:,}")
    logger.info(f"Total time:     {total_time:.0f}s")
    if total_time > 0:
        logger.info(f"Avg rate:       {entity_count / total_time:,.0f} ent/sec")

    # Verify
    with driver.session() as session:
        r = session.run("MATCH (e:YagoEntity) RETURN count(e) as c")
        actual = r.single()["c"]
        logger.info(f"Verified: {actual:,} YagoEntity nodes in Neo4j")

    # Post-load housekeeping
    post_load_cleanup(driver)

    driver.close()


if __name__ == "__main__":
    main()
