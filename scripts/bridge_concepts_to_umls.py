#!/usr/bin/env python3
"""
Corpus-wide semantic bridge: link document Concepts to the nearest
clinically-relevant UMLSConcept via SIMILAR_TO edges.

This is the NON-re-extraction half of the UMLS-bridge backfill.  It runs
purely off the embeddings already persisted on Concept nodes (no LLM, no
model server): for every Concept that has an embedding but no UMLS link
yet, it queries ``umls_embedding_index`` for the nearest UMLSConcept and
MERGEs a SIMILAR_TO edge when cosine >= threshold.

Mirrors the per-document ``UMLSBridger.bridge_concepts_semantic`` logic but
(a) scans the whole corpus and (b) batches the vector queries (one Cypher
call per page instead of one per concept), which is the main speedup.

Scope: clean multi-word Concepts (``multi_word_`` prefix, alphabetic name,
multi-token) with ``embedding IS NOT NULL`` AND no ``SAME_AS``/``SIMILAR_TO``
to a UMLSConcept.  Each bridges only to the nearest UMLSConcept that carries a
clinical semantic type (see ``CLINICAL_TUIS``) -- the target-side guard that
keeps precision ~85% by excluding generic Finding/Qualitative/Object targets.
Run AFTER the UMLS embedding job so the vector index is populated.  Idempotent
and resume-safe.

Usage:
    python scripts/bridge_concepts_to_umls.py

Environment variables (or .env):
    NEO4J_URI           (default: bolt://localhost:7687)
    NEO4J_USER          (default: neo4j)
    NEO4J_PASSWORD      (default: password)
    BRIDGE_THRESHOLD    (default: 0.92)   minimum cosine to bridge
    BRIDGE_BATCH_SIZE   (default: 300)    concepts per page / per vector batch
    BRIDGE_BATCH_SLEEP  (default: 0)      seconds to sleep between pages (throttle)
    BRIDGE_START_CID    (optional)        resume cursor (last concept_id seen)
    BRIDGE_CLINICAL_TUIS(optional)        comma-separated TUI allow-list override
"""

import asyncio
import logging
import os
import time

from neo4j import AsyncGraphDatabase

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)
logger = logging.getLogger(__name__)

NEO4J_URI = os.getenv("NEO4J_URI", "bolt://localhost:7687")
NEO4J_USER = os.getenv("NEO4J_USER", "neo4j")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD", "password")

THRESHOLD = float(os.getenv("BRIDGE_THRESHOLD", "0.92"))
BATCH_SIZE = int(os.getenv("BRIDGE_BATCH_SIZE", "300"))
# Throttle: seconds to sleep between pages (eases load on the Colima VM).
BATCH_SLEEP = float(os.getenv("BRIDGE_BATCH_SLEEP", "0"))

# Rough size of the bridge-candidate set, for progress %/ETA display only.
ESTIMATED_TOTAL = int(os.getenv("BRIDGE_EST_TOTAL", "62662"))

# Clinically-relevant UMLS semantic type TUIs.  The bridge only MERGEs to a
# UMLSConcept carrying one of these types (Disease, Drug/Substance, Procedure,
# Sign/Symptom).  This target-side guard is the precision lever: it excludes
# generic targets (Finding "Abnormal/Absent", Qualitative "Below normal",
# Body Part, Manufactured Object) that otherwise produce garbage/inverted
# bridges.  Mirrors the clinical subset in scripts/embed_umls_concepts.py but
# intentionally drops generic T033 Finding / T034 Lab Result / T023 Body Part.
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
    "T121",  # Pharmacologic Substance
    "T200",  # Clinical Drug
    "T195",  # Antibiotic
    "T125",  # Hormone
    "T129",  # Immunologic Factor
    "T061",  # Therapeutic or Preventive Procedure
    "T060",  # Diagnostic Procedure
    "T059",  # Laboratory Procedure
]

_env_tuis = os.getenv("BRIDGE_CLINICAL_TUIS", "").strip()
CLINICAL_TUIS = (
    [t.strip() for t in _env_tuis.split(",") if t.strip()]
    if _env_tuis
    else _DEFAULT_CLINICAL_TUIS
)

# Cursor-paginated selection of bridge candidates.  Scope is the clean
# multi-word concept pool (concept_id prefix ``multi_word_``, name = letters +
# spaces, multi-token) -- the population validated at ~85% precision under the
# clinical-TUI guard.  Other prefixes (code_/person_/org_/...) are excluded:
# they are NER fragments that produced garbage bridges in testing.  Anchoring
# on ``c.concept_id > $last`` within the prefix range (ORDER BY c.concept_id)
# forces an indexed forward range scan, so each page evaluates the predicates
# only on a small forward slice; resume-safe via BRIDGE_START_CID.
_PAGE_QUERY = """
MATCH (c:Concept)
WHERE c.concept_id > $last
  AND c.concept_id STARTS WITH 'multi_word_'
  AND c.embedding IS NOT NULL
  AND c.name =~ '^[A-Za-z][A-Za-z ]{4,}[A-Za-z]$'
  AND c.name CONTAINS ' '
  AND NOT EXISTS { (c)-[:SAME_AS]->(:UMLSConcept) }
  AND NOT EXISTS { (c)-[:SIMILAR_TO]->(:UMLSConcept) }
RETURN c.concept_id AS cid, c.embedding AS emb
ORDER BY c.concept_id
LIMIT $limit
"""

# Batched bridge write: top-5 vector search per row, keep only matches that
# clear the threshold AND carry a clinical semantic type, then MERGE the best
# such match per concept.  The clinical-TUI guard is the precision lever; a
# concept whose nearest *clinical* neighbour is sub-threshold simply does not
# bridge.  ``ON CREATE`` keeps it idempotent / resume-safe.
_BRIDGE_QUERY = """
UNWIND $rows AS row
CALL db.index.vector.queryNodes('umls_embedding_index', 5, row.emb)
  YIELD node, score
WITH row.cid AS cid, node, score
WHERE score >= $threshold
  AND EXISTS {
    (node)-[:HAS_SEMANTIC_TYPE]->(st:UMLSSemanticType)
    WHERE st.type_id IN $tuis
  }
WITH cid, node, score
ORDER BY score DESC
WITH cid, head(collect({node: node, score: score})) AS best
WITH cid, best.node AS target, best.score AS sc
MATCH (c:Concept {concept_id: cid})
MERGE (c)-[r:SIMILAR_TO]->(target)
ON CREATE SET r.score = sc, r.created_at = $ts, r.bridge = 'semantic'
RETURN count(r) AS cnt
"""


async def main():
    driver = AsyncGraphDatabase.driver(
        NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD)
    )

    logger.info(
        "Bridging clean multi-word Concepts -> UMLSConcept via SIMILAR_TO "
        "(threshold=%.2f, %d clinical TUIs, estimated ~%d candidates) "
        "by concept_id cursor",
        THRESHOLD,
        len(CLINICAL_TUIS),
        ESTIMATED_TOTAL,
    )

    processed = 0
    bridged = 0
    start = time.time()
    last_cid = os.getenv("BRIDGE_START_CID", "")

    while True:
        async with driver.session() as session:
            result = await session.run(
                _PAGE_QUERY,
                {"last": last_cid, "limit": BATCH_SIZE},
            )
            page = [
                {"cid": r["cid"], "emb": r["emb"]}
                async for r in result
            ]

        if not page:
            break

        last_cid = page[-1]["cid"]
        ts = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

        async with driver.session() as session:
            res = await session.run(
                _BRIDGE_QUERY,
                {
                    "rows": page,
                    "threshold": THRESHOLD,
                    "ts": ts,
                    "tuis": CLINICAL_TUIS,
                },
            )
            rec = await res.single()
            created = rec["cnt"] if rec else 0
            bridged += created

        processed += len(page)
        elapsed = time.time() - start
        rate = processed / elapsed if elapsed > 0 else 0
        pct = min(100, processed * 100 // ESTIMATED_TOTAL) if ESTIMATED_TOTAL else 0
        eta_min = (
            (ESTIMATED_TOTAL - processed) / rate / 60
            if rate > 0 and processed < ESTIMATED_TOTAL
            else 0
        )
        logger.info(
            "Progress: %s/~%s (~%d%%) bridged=%s rate=%.0f/s eta=~%.0fmin last_cid=%s",
            f"{processed:,}",
            f"{ESTIMATED_TOTAL:,}",
            pct,
            f"{bridged:,}",
            rate,
            eta_min,
            last_cid,
        )

        if BATCH_SLEEP > 0:
            await asyncio.sleep(BATCH_SLEEP)

    await driver.close()
    elapsed = time.time() - start
    logger.info(
        "Done: %s SIMILAR_TO edges created over %s concepts in %.1fs (%.1fmin)",
        f"{bridged:,}",
        f"{processed:,}",
        elapsed,
        elapsed / 60,
    )


if __name__ == "__main__":
    asyncio.run(main())
