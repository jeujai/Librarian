#!/usr/bin/env python3
"""
Seed emergent bootstrap concepts (provenance='seed') into Neo4j.

Writes a ``Concept`` node for each curated term with ``bridge_status='emergent'``,
``provenance='seed'``, ``scope='public'``, and a 768-dim embedding into
``concept_embedding_index`` — the "explicitly curated, inserted out-of-band" birth
mechanism (§5.5) for terms that appear in no document (so they can never be
``corpus-mined``).

Idempotent: MERGEs on ``(name_lower, scope='public')``. ``ON MATCH`` never flips
provenance/bridge_status/scope (a pre-existing ``corpus-mined`` term stays
``corpus-mined``); it only touches ``updated_at`` and backfills a missing embedding.

Usage:
    python scripts/seed_emergent_concepts.py

Environment variables (or .env):
    NEO4J_URI          (default: bolt://localhost:7687)
    NEO4J_USER         (default: neo4j)
    NEO4J_PASSWORD     (default: password)
    MODEL_SERVER_URL   (default: http://localhost:8001)
"""

import asyncio
import logging
import os
from datetime import datetime

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

# Each entry is a canonical bootstrap term (concept name).
#   str  -> concept_type="ENTITY", confidence=0.5, surface_forms=[]
#   dict -> {"name": ..., "concept_type": "PROCESS", "confidence": 0.6,
#            "surface_forms": ["category III", ...]}
#
# These are compositional noun-chunks that ConceptNet (only atomic
# "work"/"restriction"/"management"/"guideline") and UMLS (biomedical) do not
# cover.  See docs/emergent-concepts-architecture.md §1, §5.5.
#
# ``surface_forms`` is the literal-phrase bridge for the idiomatic-paraphrase
# case (§6.2): a seed's curated sense rarely appears verbatim in the source
# document.  "work restrictions" (the SHEA bloodborne-pathogen sense) is
# written as "category III / exposure-prone procedures" and "should not be
# prohibited from patient-care activities"; "management guidelines" as
# "management of HCP".  Grounding matches chunks against the seed name PLUS
# these surface forms, so the seed reaches its real evidence even though the
# name itself never appears.  Substrings, not embeddings — exact and noise-free.
SEED_CONCEPTS = [
    {"name": "management guidelines", "concept_type": "PROCESS", "confidence": 0.6,
     "surface_forms": ["management of HCP", "management of healthcare personnel"]},
    {"name": "work restrictions", "concept_type": "RESTRICTION", "confidence": 0.7,
     "surface_forms": ["category III", "prohibited from", "practice restrictions",
                       "patient-care activities"]},
    # Idiomatic paraphrase of "work restrictions" as used in the medical
    # literature (e.g. the SHEA bloodborne-pathogen guideline).  Without this
    # sibling seed, backfill_similar_to.py has no "practice restrictions" node
    # to bridge "work restrictions" -> "practice restrictions" (cosine 0.817).
    {"name": "practice restrictions", "concept_type": "RESTRICTION", "confidence": 0.7,
     "surface_forms": ["category III", "prohibited from", "patient-care activities"]},
    # Operational/regulatory compounds UMLS (biomedical) does not cover — folded
    # in from the chunking framework's _MEDICAL_MULTI_WORD_SEED so they live here
    # as vetted provenance='seed' knowledge rather than a Python-only fallback.
    {"name": "exposure-prone procedures", "concept_type": "PROCEDURE", "confidence": 0.7,
     "surface_forms": ["exposure prone procedure"]},
    {"name": "healthcare personnel", "concept_type": "ENTITY", "confidence": 0.6,
     "surface_forms": ["health care worker", "healthcare worker", "health care personnel"]},
]

DEFAULT_CONCEPT_TYPE = "ENTITY"
DEFAULT_CONFIDENCE = 0.5


def normalize_entry(entry):
    """Return (name, concept_type, confidence, surface_forms) from a str or dict entry."""
    if isinstance(entry, dict):
        name = entry["name"]
        return (
            name,
            entry.get("concept_type", DEFAULT_CONCEPT_TYPE),
            entry.get("confidence", DEFAULT_CONFIDENCE),
            entry.get("surface_forms", []),
        )
    return entry, DEFAULT_CONCEPT_TYPE, DEFAULT_CONFIDENCE, []


async def generate_embeddings(
    client: httpx.AsyncClient, texts: list
) -> list | None:
    """Call the model server to embed the seed terms (768-dim, normalized)."""
    try:
        resp = await client.post(
            f"{MODEL_SERVER_URL}/embeddings",
            json={"texts": texts, "normalize": True},
            timeout=60.0,
        )
        resp.raise_for_status()
        return resp.json().get("embeddings")
    except Exception as e:
        logger.error(f"Embedding request failed: {e}")
        return None


async def ensure_vector_index(session) -> None:
    """Best-effort vector index creation (idempotent; 'already exists' is fine)."""
    try:
        await session.run(
            "CALL db.index.vector.createNodeIndex("
            "'concept_embedding_index', 'Concept', 'embedding', 768, 'cosine')"
        )
    except Exception as e:
        logger.info(f"Vector index ensure skipped (may already exist): {e}")


async def seed(session, rows: list) -> int:
    """MERGE the seed rows and return the number written."""
    query = """
        UNWIND $rows AS row
        MERGE (c:Concept {name_lower: toLower(row.name), scope: 'public'})
        ON CREATE SET
            c.name = row.name,
            c.type = row.type,
            c.concept_type = row.type,
            c.confidence = row.confidence,
            c.name_lower = toLower(row.name),
            c.scope = 'public',
            c.bridge_status = 'emergent',
            c.provenance = 'seed',
            c.owner_id = NULL,
            c.concept_id = 'public:' + toLower(row.name),
            c.surface_forms = row.surface_forms,
            c.created_at = row.created_at,
            c.updated_at = row.updated_at,
            c.embedding = row.embedding
        ON MATCH SET
            c.updated_at = row.updated_at,
            c.embedding = COALESCE(c.embedding, row.embedding),
            c.surface_forms = row.surface_forms
        RETURN row.name AS name, elementId(c) AS node_id
    """
    result = await session.run(query, {"rows": rows})
    records = [r async for r in result]
    return len(records)


async def verify(session, names: list) -> None:
    """Read back seeded concepts and print their lifecycle fields."""
    if not names:
        return
    result = await session.run(
        "MATCH (c:Concept) WHERE c.name_lower IN $lowers "
        "RETURN c.name AS name, c.provenance AS provenance, "
        "c.bridge_status AS bridge_status, c.scope AS scope, "
        "c.owner_id AS owner_id, c.concept_id AS concept_id, "
        "size(c.embedding) AS dim, c.surface_forms AS surface_forms "
        "ORDER BY c.name_lower",
        {"lowers": [n.lower() for n in names]},
    )
    records = [r async for r in result]
    if not records:
        logger.info("No seeded concepts found.")
        return
    print(f"\n{len(records)} seed concept(s):")
    for r in records:
        sf = r.get("surface_forms") or []
        print(
            f"  {r['name']:40s} provenance={r['provenance']} "
            f"bridge_status={r['bridge_status']} scope={r['scope']} "
            f"owner_id={r['owner_id']} concept_id={r['concept_id']} "
            f"dim={r['dim']} surface_forms={sf}"
        )


async def reclaim_orphaned(session, names: list) -> int:
    """Flip orphaned corpus-mined nodes (no EXTRACTED_FROM evidence) that a seed
    MERGEs onto, so the curated seed provenance supersedes the dead corpus-mined
    one.  A seed that lands on a node whose evidence was deleted should own it."""
    query = """
        UNWIND $names AS name
        MATCH (c:Concept {name_lower: toLower(name), scope: 'public'})
        WHERE c.provenance = 'corpus-mined'
          AND NOT EXISTS { (c)-[:EXTRACTED_FROM]->(:Chunk) }
        SET c.provenance = 'seed', c.bridge_status = 'emergent'
        RETURN count(c) AS n
    """
    result = await session.run(query, {"names": names})
    rec = await result.single()
    return rec["n"] if rec else 0


async def main():
    if not SEED_CONCEPTS:
        logger.info("0 seeds; nothing to do.")
        return

    entries = [normalize_entry(e) for e in SEED_CONCEPTS]
    names = [e[0] for e in entries]

    driver = AsyncGraphDatabase.driver(
        NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD)
    )

    try:
        async with driver.session() as session:
            await ensure_vector_index(session)

        async with httpx.AsyncClient() as http_client:
            embeddings = await generate_embeddings(http_client, names)
            if not embeddings or len(embeddings) != len(names):
                logger.error(
                    "Model server returned no/mismatched embeddings "
                    f"({len(embeddings) if embeddings else 0} for {len(names)}); "
                    "aborting — seeds must carry an embedding."
                )
                await driver.close()
                return

            now_ts = datetime.utcnow().isoformat()
            rows = [
                {
                    "name": name,
                    "type": ctype,
                    "confidence": confidence,
                    "surface_forms": surface_forms,
                    "embedding": emb,
                    "created_at": now_ts,
                    "updated_at": now_ts,
                }
                for (name, ctype, confidence, surface_forms), emb in zip(entries, embeddings)
            ]

            async with driver.session() as session:
                written = await seed(session, rows)
                reclaimed = await reclaim_orphaned(session, names)
                await verify(session, names)

        logger.info(
            f"Done: {written} seed concept(s) written, "
            f"{reclaimed} orphaned corpus-mined node(s) reclaimed as seed."
        )
    finally:
        await driver.close()


if __name__ == "__main__":
    asyncio.run(main())
