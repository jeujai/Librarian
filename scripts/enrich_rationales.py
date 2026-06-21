#!/usr/bin/env python3
"""
Lean rationale enrichment for existing EXTRACTED_FROM edges.

For one or more documents, regenerate the per-concept ``rationale`` (and its
embedding) on the *existing* ``(:Concept)-[:EXTRACTED_FROM]->(:Chunk)`` edges,
WITHOUT re-running extraction.  This is the fast backfill path: it skips NER,
regex, relationship extraction, ConceptNet validation, UMLS linking, concept
embedding, and node/edge MERGEs -- all already done -- and does only the work
that produces rationale:

  1. Read the document's chunk text from Postgres (knowledge_chunks).
  2. Read the concept names already linked to each chunk from Neo4j.
  3. ONE lean LLM call per chunk: given the passage + those concept names,
     return ``[{name, rationale}]`` (one clause each, paraphrased).
  4. Batch-embed the rationale strings via the model server.
  5. Plain ``SET`` of ``rationale`` + ``rationale_embedding`` on the existing
     EXTRACTED_FROM edges (NOT ``ON CREATE`` -- the edges already exist).

The rationale embedding is compared to the query at inference time to boost
chunk ranking (see kg_retrieval_service rationale boost).

Scope / resume-safety: only edges with ``rationale IS NULL`` are selected, so
re-running skips already-enriched edges.  Non-destructive: no teardown, no new
nodes/edges, chunk/concept counts unchanged.

Usage:
    python scripts/enrich_rationales.py <source_id> [<source_id> ...]

Environment variables (or .env):
    NEO4J_URI            (default: bolt://localhost:7687)
    NEO4J_USER           (default: neo4j)
    NEO4J_PASSWORD       (default: password)
    PG_HOST              (default: localhost)
    PG_PORT              (default: 5432)
    PG_DB                (default: multimodal_librarian)
    PG_USER              (default: postgres)
    PG_PASSWORD          (default: postgres)
    MODEL_SERVER_URL     (default: http://localhost:8001)
    OLLAMA_URL           (default: http://localhost:11434)
    OLLAMA_MODEL         (default: llama3.2:3b)
    ENRICH_CONCURRENCY   (default: 8)     concurrent per-chunk LLM calls
    ENRICH_MAX_CONCEPTS  (default: 30)    concept names per LLM call (chunked)
    ENRICH_MAX_CHARS     (default: 2000)  passage chars sent to the LLM
"""

import argparse
import asyncio
import json
import logging
import os
import time
from typing import Any, Dict, List, Tuple

import asyncpg
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

PG_HOST = os.getenv("PG_HOST", "localhost")
PG_PORT = int(os.getenv("PG_PORT", "5432"))
PG_DB = os.getenv("PG_DB", "multimodal_librarian")
PG_USER = os.getenv("PG_USER", "postgres")
PG_PASSWORD = os.getenv("PG_PASSWORD", "postgres")

MODEL_SERVER_URL = os.getenv("MODEL_SERVER_URL", "http://localhost:8001")
OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "llama3.2:3b")

CONCURRENCY = int(os.getenv("ENRICH_CONCURRENCY", "8"))
MAX_CONCEPTS = int(os.getenv("ENRICH_MAX_CONCEPTS", "30"))
MAX_CHARS = int(os.getenv("ENRICH_MAX_CHARS", "2000"))
# Per-call read timeout for the Ollama generate call.  Dense chunks (many
# concepts -> long JSON output) can exceed the old 120s and trip an empty
# ReadTimeout; 180s default, env-tunable for retry passes over dense leftovers.
OLLAMA_TIMEOUT = float(os.getenv("OLLAMA_TIMEOUT", "180"))
EMBED_BATCH = 500

# Clinical filter: only enrich concepts worth a rationale.  Keep an edge iff its
# concept is EITHER UMLS-linked (SAME_AS/SIMILAR_TO -> :UMLSConcept) OR a clean
# multi-word phrase (same guard as the Part A bridge: multi_word_ prefix,
# alphabetic name, multi-token).  This drops the NER noise -- stopwords ("with",
# "related"), bare person/org names ("Erin", "La Jolla", "ASCO") -- that the first
# dry-run turned into junk rationales, and cuts LLM calls ~4x (far fewer concepts
# per chunk -> fewer MAX_CONCEPTS sub-batches), which is the real cost lever given
# Ollama runs effectively serial here.
_CLINICAL_FILTER = """  AND (
    EXISTS { (c)-[:SAME_AS]->(:UMLSConcept) }
    OR EXISTS { (c)-[:SIMILAR_TO]->(:UMLSConcept) }
    OR (
      c.concept_id STARTS WITH 'multi_word_'
      AND c.name =~ '^[A-Za-z][A-Za-z ]{4,}[A-Za-z]$'
      AND c.name CONTAINS ' '
    )
  )
"""

# Edges lacking a rationale, per document.  Chunk.chunk_id == the Postgres
# knowledge_chunks.id, so we join back to chunk text by that id.
_READ_QUERY = (
    "MATCH (c:Concept)-[r:EXTRACTED_FROM]->(ch:Chunk {source_id: $doc})\n"
    "WHERE r.rationale IS NULL\n"
    + _CLINICAL_FILTER
    + "RETURN ch.chunk_id AS chunk_id, c.concept_id AS cid, c.name AS name\n"
)

# --all variant: re-process every edge regardless of existing rationale
# (used for non-destructive --dry-run comparison against a known-good doc).
_READ_QUERY_ALL = (
    "MATCH (c:Concept)-[r:EXTRACTED_FROM]->(ch:Chunk {source_id: $doc})\n"
    "WHERE true\n"
    + _CLINICAL_FILTER
    + "RETURN ch.chunk_id AS chunk_id, c.concept_id AS cid, c.name AS name\n"
)

# Plain SET on the existing edge (NOT ON CREATE) -- the edge is already there.
_WRITE_QUERY = """
UNWIND $rows AS row
MATCH (c:Concept {concept_id: row.cid})-[r:EXTRACTED_FROM]->(ch:Chunk {chunk_id: row.chid})
SET r.rationale = row.rationale, r.rationale_embedding = row.emb
RETURN count(r) AS cnt
"""

_PROMPT = """You are given a passage from a clinical document and a list of \
concept names already extracted from it. For EACH concept name, write a brief \
one-clause reason it matters in THIS passage -- a paraphrase in your own words, \
NOT a quote copied from the text.

Return ONLY a JSON array. No markdown, no explanation, no extra text:
[{{"name": "<exact concept name>", "rationale": "<one clause>"}}]

Concept names:
{names}

Passage:
{text}

JSON:"""


def _norm(name: str) -> str:
    return (name or "").strip().lower()


def _parse_json_array(text: str) -> List[Dict[str, Any]]:
    """Extract a JSON array of objects from a (possibly noisy) LLM response."""
    if not text:
        return []
    t = text.strip()
    if t.startswith("```"):
        # strip ```json ... ``` fences
        t = t.split("```", 2)[-1] if t.count("```") >= 2 else t.strip("`")
    start = t.find("[")
    end = t.rfind("]")
    if start == -1 or end == -1 or end <= start:
        return []
    try:
        parsed = json.loads(t[start : end + 1])
    except (json.JSONDecodeError, TypeError):
        return []
    if not isinstance(parsed, list):
        return []
    return [p for p in parsed if isinstance(p, dict)]


async def _ollama_rationales(
    client: httpx.AsyncClient, names: List[str], text: str, chunk_id: str = ""
) -> Dict[str, str]:
    """One LLM call -> {normalized_name: rationale} for the given names."""
    prompt = _PROMPT.format(names="\n".join(f"- {n}" for n in names), text=text[:MAX_CHARS])
    try:
        resp = await client.post(
            f"{OLLAMA_URL}/api/generate",
            json={
                "model": OLLAMA_MODEL,
                "prompt": prompt,
                "stream": False,
                "options": {"temperature": 0.2, "num_predict": 4096, "num_ctx": 4096},
            },
            timeout=OLLAMA_TIMEOUT,
        )
        resp.raise_for_status()
        content = resp.json().get("response", "")
    except Exception as e:
        logger.warning(
            f"Ollama call failed (chunk {chunk_id or '?'}, {len(names)} concepts): "
            f"{type(e).__name__}: {e}"
        )
        return {}

    out: Dict[str, str] = {}
    for entry in _parse_json_array(content):
        name = entry.get("name")
        rationale = entry.get("rationale")
        if isinstance(name, str) and isinstance(rationale, str) and rationale.strip():
            out[_norm(name)] = rationale.strip()
    return out


async def _embed(client: httpx.AsyncClient, texts: List[str]) -> List[List[float]]:
    """Batch-embed via the model server (normalize=True for cosine parity)."""
    embeddings: List[List[float]] = []
    for start in range(0, len(texts), EMBED_BATCH):
        batch = texts[start : start + EMBED_BATCH]
        resp = await client.post(
            f"{MODEL_SERVER_URL}/embeddings",
            json={"texts": batch, "normalize": True},
            timeout=120.0,
        )
        resp.raise_for_status()
        embeddings.extend(resp.json().get("embeddings", []))
    return embeddings


async def _enrich_document(
    doc_id: str,
    driver,
    pg: asyncpg.Connection,
    http: httpx.AsyncClient,
    sem: asyncio.Semaphore,
    include_enriched: bool = False,
    dry_run: bool = False,
) -> Tuple[int, int]:
    """Enrich one document.  Returns (edges_updated, chunks_processed)."""
    # 1. Edges needing rationale, grouped by chunk.
    read_query = _READ_QUERY_ALL if include_enriched else _READ_QUERY
    cid_to_name: Dict[str, str] = {}
    async with driver.session() as session:
        result = await session.run(read_query, {"doc": doc_id})
        by_chunk: Dict[str, List[Tuple[str, str]]] = {}
        async for rec in result:
            by_chunk.setdefault(rec["chunk_id"], []).append((rec["cid"], rec["name"]))
            cid_to_name[rec["cid"]] = rec["name"]

    if not by_chunk:
        logger.info(f"[{doc_id}] no edges need rationale (already enriched?)")
        return (0, 0)

    # 2. Chunk text from Postgres (only the chunks we need).
    rows = await pg.fetch(
        "SELECT id, content FROM multimodal_librarian.knowledge_chunks "
        "WHERE source_id = $1::uuid",
        doc_id,
    )
    text_by_chunk = {str(r["id"]): (r["content"] or "") for r in rows}

    logger.info(
        f"[{doc_id}] {len(by_chunk)} chunks, "
        f"{sum(len(v) for v in by_chunk.values())} edges to enrich"
    )

    # 3. Per chunk: LLM -> rationales, then (unless dry-run) embed + SET this
    #    chunk's edges IMMEDIATELY.  Writing per-chunk rather than once at the
    #    end makes a multi-hour, multi-thousand-chunk backfill durable: a crash
    #    loses only the in-flight chunk, and a rerun resumes via the
    #    `r.rationale IS NULL` filter instead of redoing everything.
    stats = {"updated": 0, "done": 0, "generated": 0}
    dry_samples: List[Tuple[str, str]] = []
    total = len(by_chunk)

    async def _process_chunk(chunk_id: str, concepts: List[Tuple[str, str]]):
        text = text_by_chunk.get(chunk_id)
        if not text:
            stats["done"] += 1
            return
        # name -> [cids] (a name may map to several concept_ids in a chunk)
        name_to_cids: Dict[str, List[str]] = {}
        for cid, name in concepts:
            name_to_cids.setdefault(_norm(name), []).append(cid)
        # de-dup names preserving order
        seen: set = set()
        unique_names = [
            n for _, n in concepts if not (_norm(n) in seen or seen.add(_norm(n)))
        ]

        async with sem:
            merged: Dict[str, str] = {}
            for i in range(0, len(unique_names), MAX_CONCEPTS):
                sub = unique_names[i : i + MAX_CONCEPTS]
                merged.update(await _ollama_rationales(http, sub, text, chunk_id))

            # (cid, rationale) for THIS chunk only
            chunk_pairs = [
                (cid, rationale)
                for norm_name, rationale in merged.items()
                for cid in name_to_cids.get(norm_name, [])
            ]
            if not chunk_pairs:
                stats["done"] += 1
                return

            if dry_run:
                stats["generated"] += len(chunk_pairs)
                for cid, rationale in chunk_pairs:
                    if len(dry_samples) < 20:
                        dry_samples.append((cid, rationale))
                stats["done"] += 1
                return

            # Embed this chunk's distinct rationales, then SET its edges now.
            distinct = sorted({r for _, r in chunk_pairs})
            embs = await _embed(http, distinct)
            if len(embs) != len(distinct):
                logger.warning(
                    f"[{doc_id}] chunk {chunk_id}: embed mismatch "
                    f"({len(embs)} != {len(distinct)}); skipping {len(chunk_pairs)} edges"
                )
                stats["done"] += 1
                return
            emb_by_text = dict(zip(distinct, embs))
            write_rows = [
                {"cid": cid, "chid": chunk_id, "rationale": r, "emb": emb_by_text[r]}
                for cid, r in chunk_pairs
            ]
            async with driver.session() as session:
                res = await session.run(_WRITE_QUERY, {"rows": write_rows})
                rec = await res.single()
                stats["updated"] += rec["cnt"] if rec else 0

        stats["done"] += 1
        if stats["done"] % 50 == 0 or stats["done"] == total:
            logger.info(
                f"[{doc_id}] progress {stats['done']}/{total} chunks, "
                f"{stats['updated']} edges written"
            )

    await asyncio.gather(
        *(_process_chunk(cid, concepts) for cid, concepts in by_chunk.items())
    )

    if dry_run:
        for cid, rationale in dry_samples:
            logger.info(f"[dry-run] {cid_to_name.get(cid, cid)} :: {rationale}")
        logger.info(
            f"[{doc_id}] dry-run: {stats['generated']} rationales generated, not written"
        )
        return (0, total)

    if stats["updated"] == 0:
        logger.warning(f"[{doc_id}] LLM produced no usable rationales")
    else:
        logger.info(f"[{doc_id}] updated {stats['updated']} edges over {total} chunks")
    return (stats["updated"], total)


async def main(doc_ids: List[str], include_enriched: bool = False, dry_run: bool = False):
    driver = AsyncGraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))
    pg = await asyncpg.connect(
        host=PG_HOST, port=PG_PORT, database=PG_DB, user=PG_USER, password=PG_PASSWORD
    )
    sem = asyncio.Semaphore(CONCURRENCY)
    start = time.time()
    total_updated = 0
    total_chunks = 0

    mode = "DRY-RUN" if dry_run else ("ALL edges" if include_enriched else "resume-safe")
    logger.info(
        f"Enriching rationales for {len(doc_ids)} document(s) [{mode}] "
        f"(model={OLLAMA_MODEL}, concurrency={CONCURRENCY})"
    )

    async with httpx.AsyncClient() as http:
        # Fail fast if the model server is down (embeddings are required).
        try:
            h = await http.get(f"{MODEL_SERVER_URL}/health", timeout=5.0)
            logger.info(f"Model server health: {h.status_code}")
        except Exception as e:
            logger.error(f"Model server unreachable at {MODEL_SERVER_URL}: {e}")
            await pg.close()
            await driver.close()
            raise SystemExit(1)

        for doc_id in doc_ids:
            try:
                updated, chunks = await _enrich_document(
                    doc_id, driver, pg, http, sem, include_enriched, dry_run
                )
                total_updated += updated
                total_chunks += chunks
            except Exception as e:
                logger.error(f"[{doc_id}] enrichment failed: {e}")

    await pg.close()
    await driver.close()
    elapsed = time.time() - start
    logger.info(
        f"Done: {total_updated} edges enriched over {total_chunks} chunks "
        f"in {elapsed:.1f}s ({elapsed/60:.1f}min)"
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Lean rationale enrichment for EXTRACTED_FROM edges")
    parser.add_argument("source_ids", nargs="+", help="One or more document source_ids")
    parser.add_argument(
        "--all",
        action="store_true",
        dest="include_enriched",
        help="Re-process every edge, even those that already have a rationale",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Generate and print rationales but do not write to Neo4j",
    )
    args = parser.parse_args()
    asyncio.run(
        main(args.source_ids, include_enriched=args.include_enriched, dry_run=args.dry_run)
    )
