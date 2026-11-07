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
    ENRICH_BACKEND       (default: vllm)  "vllm" or "ollama"
    VLLM_URL             (default: http://127.0.0.1:8002)
    VLLM_MODEL           (default: mlx-community/Llama-3.2-3B-Instruct-4bit)
    GEN_MAX_TOKENS       (default: 700)   max output tokens per LLM call
    GEN_TEMPERATURE      (default: 0.2)
    OLLAMA_URL           (default: http://localhost:11434)
    OLLAMA_MODEL         (default: llama3.2:3b)
    ENRICH_CONCURRENCY   (default: 32)    concurrent per-chunk LLM calls
    ENRICH_MAX_CONCEPTS  (default: 20)    concept names per LLM call (chunked)
    ENRICH_MAX_CHARS     (default: 9000)  passage chars sent to the LLM
    ENRICH_DENSE_TEXT_CHARS  (default: 4000)  chunks longer than this use
    ENRICH_DENSE_MAX_CONCEPTS (default: 10)   fewer concepts per call
"""

import argparse
import asyncio
import json
import logging
import os
import random
import time
from typing import Any, Dict, List, Optional, Tuple

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

# Rationale-generation backend: "vllm" (HTTP to a vllm-metal server, default)
# or "ollama" (HTTP to a local Ollama server).  vllm-metal supports concurrent
# batching, so it runs one process with high ENRICH_CONCURRENCY.
BACKEND = os.getenv("ENRICH_BACKEND", "vllm")
GEN_MAX_TOKENS = int(os.getenv("GEN_MAX_TOKENS", "700"))
GEN_TEMPERATURE = float(os.getenv("GEN_TEMPERATURE", "0.2"))

VLLM_URL = os.getenv("VLLM_URL", "http://127.0.0.1:8002")
VLLM_MODEL = os.getenv("VLLM_MODEL", "mlx-community/Llama-3.2-3B-Instruct-4bit")

_DEFAULT_CONCURRENCY = {"ollama": "8", "vllm": "32"}.get(BACKEND, "1")
CONCURRENCY = int(os.getenv("ENRICH_CONCURRENCY", _DEFAULT_CONCURRENCY))
WRITE_CONCURRENCY = int(os.getenv("ENRICH_WRITE_CONCURRENCY", "1"))
MAX_CONCEPTS = int(os.getenv("ENRICH_MAX_CONCEPTS", "20"))
# Sized to the largest observed chunk (~8.4k chars ~= 2.1k tokens) so full text
# fits under the vLLM 4096-token context; the old 2000-char truncation was the
# root cause of "Not mentioned in the passage" no-ops on dense table chunks.
MAX_CHARS = int(os.getenv("ENRICH_MAX_CHARS", "9000"))
# For text longer than DENSE_TEXT_CHARS, shrink each sub-batch to
# DENSE_MAX_CONCEPTS names: grounding 20 names against a multi-thousand-char
# table in one call is too much for the 3B model (first sub-batch yielded 0).
DENSE_TEXT_CHARS = int(os.getenv("ENRICH_DENSE_TEXT_CHARS", "4000"))
DENSE_MAX_CONCEPTS = int(os.getenv("ENRICH_DENSE_MAX_CONCEPTS", "10"))
# Per-call read timeout for the Ollama generate call.  Dense chunks (many
# concepts -> long JSON output) can exceed the old 120s and trip an empty
# ReadTimeout; 180s default, env-tunable for retry passes over dense leftovers.
OLLAMA_TIMEOUT = float(os.getenv("OLLAMA_TIMEOUT", "900"))
EMBED_BATCH = 500

# Clinical filter: only enrich concepts worth a rationale.  Keep an edge iff its
# concept is EITHER UMLS-linked (SAME_AS/SIMILAR_TO -> :UMLSConcept) OR a clean
# multi-word phrase (same guard as the Part A bridge: multi_word_ prefix,
# alphabetic name, multi-token).  This drops the NER noise -- stopwords ("with",
# "related"), bare person/org names ("Erin", "La Jolla", "ASCO") -- that the first
# dry-run turned into junk rationales, and cuts LLM calls ~4x (far fewer concepts
# per chunk -> fewer MAX_CONCEPTS sub-batches), which is the real cost lever given
# Ollama runs effectively serial here.
_CLINICAL_FILTER = """  AND c.name CONTAINS ' '
  AND (
    EXISTS { (c)-[:SAME_AS]->(:UMLSConcept) }
    OR EXISTS { (c)-[:SIMILAR_TO]->(:UMLSConcept) }
    OR (
      c.concept_id STARTS WITH 'multi_word_'
      AND c.name =~ '^[A-Za-z][A-Za-z ]{4,}[A-Za-z]$'
    )
  )
"""

# Shard by the first hex nibble of chunk_id (a Postgres UUID, uniformly
# distributed).  `shard_chars` is a list of the hex chars this process owns, so
# N processes each handle a disjoint, roughly-equal subset of chunks.
_SHARD_CLAUSE = "  AND substring(ch.chunk_id, 0, 1) IN $shard_chars\n"
_ALL_HEX = list("0123456789abcdef")


def shard_chars_for(index: int, total: int) -> List[str]:
    """Return the hex-nibble prefixes owned by shard `index` of `total`."""
    if total <= 1:
        return _ALL_HEX
    buckets = []
    for i, ch in enumerate(_ALL_HEX):
        buckets.append(ch)
    # Distribute 16 nibbles across `total` shards as evenly as possible.
    per = 16 // total
    rem = 16 % total
    start = index * per + min(index, rem)
    end = start + per + (1 if index < rem else 0)
    return _ALL_HEX[start:end]


# Edges lacking a rationale, per document.  Chunk.chunk_id == the Postgres
# knowledge_chunks.id, so we join back to chunk text by that id.
_READ_QUERY = (
    "MATCH (c:Concept)-[r:EXTRACTED_FROM]->(ch:Chunk {source_id: $doc})\n"
    "WHERE r.rationale IS NULL\n"
    + _SHARD_CLAUSE
    + _CLINICAL_FILTER
    + "RETURN ch.chunk_id AS chunk_id, c.concept_id AS cid, c.name AS name\n"
)

# --all variant: re-process every edge regardless of existing rationale
# (used for non-destructive --dry-run comparison against a known-good doc).
_READ_QUERY_ALL = (
    "MATCH (c:Concept)-[r:EXTRACTED_FROM]->(ch:Chunk {source_id: $doc})\n"
    "WHERE true\n"
    + _SHARD_CLAUSE
    + _CLINICAL_FILTER
    + "RETURN ch.chunk_id AS chunk_id, c.concept_id AS cid, c.name AS name\n"
)

# --zero-chunks-only variant: like the resume-safe query, but additionally
# restrict to chunks that came out of the previous pass with NO rationale at
# all (every EXTRACTED_FROM edge into the chunk is still null).  Partial-
# coverage chunks are left untouched; this concentrates a tuned retry pass
# (smaller MAX_CONCEPTS, longer timeout) on the genuine zero-yield failures --
# typically dense chunks that timed out or that the small model couldn't parse
# in one shot -- rather than redoing chunks that already have some coverage.
_ZERO_CHUNK_GUARD = (
    "  AND NOT EXISTS { (:Concept)-[rr:EXTRACTED_FROM]->(ch) "
    "WHERE rr.rationale IS NOT NULL }\n"
)
_READ_QUERY_ZERO_CHUNKS = (
    "MATCH (c:Concept)-[r:EXTRACTED_FROM]->(ch:Chunk {source_id: $doc})\n"
    "WHERE r.rationale IS NULL\n"
    + _ZERO_CHUNK_GUARD
    + _SHARD_CLAUSE
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

# Recompute the concept-level rationale embedding (mean of its edge rationale
# embeddings).  Mirrors celery_service._RECOMPUTE_RATIONALE_EMBEDDING_QUERY so
# concept_rationale_embedding_index reflects the enrichment pass.  The mean is
# un-normalized: the vector index uses cosine (magnitude-invariant).
_RECOMPUTE_RATIONALE_EMBEDDING_QUERY = """
UNWIND $cids AS cid
MATCH (c:Concept {concept_id: cid})-[r:EXTRACTED_FROM]->(:Chunk)
WHERE r.rationale_embedding IS NOT NULL
WITH c, collect(r.rationale_embedding) AS embs
WITH c, embs, size(embs) AS n, size(embs[0]) AS d
UNWIND range(0, d - 1) AS i
WITH c, i, reduce(s = 0.0, e IN embs | s + e[i]) / n AS mean_i
WITH c, i, mean_i
ORDER BY c.concept_id, i
WITH c, collect(mean_i) AS mean_vec
SET c.rationale_embedding = mean_vec
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


def _extract_json_objects(text: str) -> List[Dict[str, Any]]:
    """Extract complete JSON objects via brace-balanced scanning.

    Tolerant of a missing closing ']' or trailing prose: llama3.2:3b often
    emits a valid array of {"name","rationale"} objects then stops
    (done_reason=stop) without the closing bracket, which makes a strict
    array parse discard the whole batch.
    """
    objs: List[Dict[str, Any]] = []
    i, n = 0, len(text)
    while i < n:
        if text[i] != "{":
            i += 1
            continue
        depth = 0
        in_str = False
        esc = False
        j = i
        while j < n:
            ch = text[j]
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = not in_str
            elif not in_str:
                if ch == "{":
                    depth += 1
                elif ch == "}":
                    depth -= 1
                    if depth == 0:
                        try:
                            o = json.loads(text[i : j + 1])
                            if isinstance(o, dict):
                                objs.append(o)
                        except (json.JSONDecodeError, TypeError):
                            pass
                        break
            j += 1
        i = j + 1
    return objs


def _parse_json_array(text: str) -> List[Dict[str, Any]]:
    """Extract a JSON array of objects from a (possibly noisy) LLM response.

    Fast path parses a well-formed ``[ ... ]`` array; fallback recovers the
    objects when the model omits the closing ']' or appends trailing prose.
    """
    if not text:
        return []
    t = text.strip()
    if t.startswith("```"):
        # strip ```json ... ``` fences
        t = t.split("```", 2)[-1] if t.count("```") >= 2 else t.strip("`")
    start = t.find("[")
    end = t.rfind("]")
    if start != -1 and end != -1 and end > start:
        try:
            parsed = json.loads(t[start : end + 1])
            if isinstance(parsed, list):
                dicts = [p for p in parsed if isinstance(p, dict)]
                if dicts:
                    return dicts
        except (json.JSONDecodeError, TypeError):
            pass
    # Tolerant fallback for unclosed arrays / trailing prose.
    return _extract_json_objects(t)


def _is_noop_rationale(text: str) -> bool:
    """True if the rationale is a non-answer (the model couldn't ground the name)."""
    t = (text or "").strip().strip('".').strip().lower()
    if not t:
        return True
    if t in {"n/a", "na", "none", "none mentioned", "not applicable",
             "not stated", "unknown"}:
        return True
    return t.startswith("not mentioned")


def _parse_rationales(content: str) -> Dict[str, str]:
    """Map a raw LLM response to {normalized_name: rationale}."""
    out: Dict[str, str] = {}
    for entry in _parse_json_array(content):
        name = entry.get("name")
        rationale = entry.get("rationale")
        if (
            isinstance(name, str)
            and isinstance(rationale, str)
            and rationale.strip()
            and not _is_noop_rationale(rationale)
        ):
            out[_norm(name)] = rationale.strip()
    return out


async def _ollama_rationales(
    client_ref: List[httpx.AsyncClient],
    names: List[str],
    text: str,
    chunk_id: str = "",
) -> Dict[str, str]:
    """One LLM call -> {normalized_name: rationale} for the given names.

    Uses a mutable client reference so that a single transport error triggers
    one client replacement for all concurrent tasks, rather than each task
    having to create its own ephemeral client.
    """
    prompt = _PROMPT.format(names="\n".join(f"- {n}" for n in names), text=text[:MAX_CHARS])
    for attempt in (0, 1):
        try:
            resp = await client_ref[0].post(
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
            break
        except Exception as e:
            is_transport = (
                "client has been closed" in str(e).lower()
                or type(e).__name__ in ("ReadError", "RemoteProtocolError",
                                         "ConnectError", "PoolTimeout",
                                         "NetworkError")
            )
            if attempt == 0 and (is_transport or isinstance(e, httpx.HTTPError)):
                logger.info(
                    f"Replacing broken httpx client after {type(e).__name__} "
                    f"(chunk {chunk_id or '?'}, {len(names)} concepts)"
                )
                try:
                    await client_ref[0].aclose()
                except Exception:
                    pass
                client_ref[0] = httpx.AsyncClient()
                continue
            logger.warning(
                f"Ollama call failed (chunk {chunk_id or '?'}, {len(names)} concepts): "
                f"{type(e).__name__}: {e}"
            )
            return {}

    return _parse_rationales(content)


# vLLM (vllm-metal) serves an OpenAI-compatible /v1/chat/completions endpoint.
# The system prompt mirrors the one that produced clean JSON in the Metal
# benchmark: a chat template (system + user messages) avoids the raw-prompt
# repetition/degeneration the 4-bit model exhibited under MLX.
_VLLM_SYSTEM = (
    "You are a medical rationale extractor. Given a clinical passage and a list "
    "of concept names, for EACH concept name write a brief one-clause reason it "
    "matters in THIS passage, paraphrased. Return ONLY a JSON array of objects "
    '[{"name": "<exact concept name>", "rationale": "<one clause>"}]. '
    "No markdown, no explanation, no repetition."
)


async def _vllm_rationales(
    client_ref: List[httpx.AsyncClient],
    names: List[str],
    text: str,
    chunk_id: str = "",
) -> Dict[str, str]:
    """One chat-completions call -> {normalized_name: rationale} for `names`."""
    payload = {
        "model": VLLM_MODEL,
        "messages": [
            {"role": "system", "content": _VLLM_SYSTEM},
            {
                "role": "user",
                "content": (
                    "Concept names:\n"
                    + "\n".join(f"- {n}" for n in names)
                    + "\n\nPassage:\n"
                    + text[:MAX_CHARS]
                ),
            },
        ],
        "max_tokens": GEN_MAX_TOKENS,
        "temperature": GEN_TEMPERATURE,
    }
    for attempt in (0, 1):
        try:
            resp = await client_ref[0].post(
                f"{VLLM_URL}/v1/chat/completions", json=payload, timeout=300.0
            )
            resp.raise_for_status()
            data = resp.json()
            content = data["choices"][0]["message"]["content"]
            break
        except Exception as e:
            is_transport = (
                "client has been closed" in str(e).lower()
                or type(e).__name__ in ("ReadError", "RemoteProtocolError",
                                         "ConnectError", "PoolTimeout",
                                         "NetworkError")
            )
            if attempt == 0 and (is_transport or isinstance(e, httpx.HTTPError)):
                logger.info(
                    f"Replacing broken httpx client after {type(e).__name__} "
                    f"(chunk {chunk_id or '?'}, {len(names)} concepts)"
                )
                try:
                    await client_ref[0].aclose()
                except Exception:
                    pass
                client_ref[0] = httpx.AsyncClient()
                continue
            logger.warning(
                f"vLLM call failed (chunk {chunk_id or '?'}, {len(names)} concepts): "
                f"{type(e).__name__}: {e}"
            )
            return {}

    return _parse_rationales(content)


async def _embed(
    client_ref: List[httpx.AsyncClient], texts: List[str]
) -> List[List[float]]:
    """Batch-embed via the model server (normalize=True for cosine parity).

    Uses a mutable client reference so a broken client is replaced once for
    all concurrent tasks.
    """
    embeddings: List[List[float]] = []
    for start in range(0, len(texts), EMBED_BATCH):
        batch = texts[start : start + EMBED_BATCH]
        for attempt in (0, 1):
            try:
                resp = await client_ref[0].post(
                    f"{MODEL_SERVER_URL}/embeddings",
                    json={"texts": batch, "normalize": True},
                    timeout=120.0,
                )
                resp.raise_for_status()
                embeddings.extend(resp.json().get("embeddings", []))
                break
            except Exception as e:
                is_transport = (
                    "client has been closed" in str(e).lower()
                    or type(e).__name__ in ("ReadError", "RemoteProtocolError",
                                             "ConnectError", "PoolTimeout",
                                             "NetworkError")
                )
                if attempt == 0 and (is_transport or isinstance(e, httpx.HTTPError)):
                    logger.info(
                        f"Replacing broken httpx client after embed "
                        f"{type(e).__name__}"
                    )
                    try:
                        await client_ref[0].aclose()
                    except Exception:
                        pass
                    client_ref[0] = httpx.AsyncClient()
                    continue
                raise
    return embeddings


async def _write_with_retry(session, write_tx_fn, *, max_retries: int = 5, base_delay: float = 1.0):
    """Execute a Neo4j write transaction with exponential backoff + jitter.

    Retries on LockAcquisitionTimeout and other transient errors.  The retry
    budget (5 attempts × up to ~31s delay) comfortably exceeds the 10s Neo4j
    lock-acquisition timeout while keeping total stall well under the 900s
    Ollama timeout.
    """
    for attempt in range(max_retries + 1):
        try:
            return await session.execute_write(write_tx_fn)
        except Exception as e:
            msg = str(e)
            is_transient = (
                "LockAcquisitionTimeout" in msg
                or "TransientError" in msg
                or "Unable to acquire lock" in msg
                or "BookmarkTimeout" in msg
                or "ForbiddenDueToTransactionNotOpen" in msg
            )
            if not is_transient or attempt == max_retries:
                raise
            delay = base_delay * (2 ** attempt) + random.uniform(0, base_delay)
            logger.info(
                f"Write lock contention (attempt {attempt + 1}/{max_retries}), "
                f"retrying in {delay:.1f}s"
            )
            await asyncio.sleep(delay)


async def _recompute_centroids(driver, cids: set) -> int:
    """Recompute concept-level rationale embeddings (mean of edge rationale
    embeddings) for the given concept ids, batched to bound transaction size."""
    cid_list = list(cids)
    BATCH = 2000
    total = 0
    for start in range(0, len(cid_list), BATCH):
        batch = cid_list[start : start + BATCH]
        try:
            async with driver.session() as session:
                res = await session.run(
                    _RECOMPUTE_RATIONALE_EMBEDDING_QUERY, {"cids": batch}
                )
                summary = await res.consume()
                total += (
                    summary.counters.properties_set
                    if summary and summary.counters
                    else 0
                )
        except Exception as e:
            logger.warning(
                f"centroid recompute failed for batch {start}: {e}"
            )
    logger.info(f"recomputed centroids for {len(cid_list)} concepts")
    return total


async def _enrich_document(
    doc_id: str,
    driver,
    pg: asyncpg.Connection,
    http: httpx.AsyncClient,
    sem: asyncio.Semaphore,
    include_enriched: bool = False,
    dry_run: bool = False,
    zero_chunks_only: bool = False,
    shard_chars: Optional[List[str]] = None,
) -> Tuple[int, int]:
    """Enrich one document.  Returns (edges_updated, chunks_processed)."""
    # 1. Edges needing rationale, grouped by chunk.
    if zero_chunks_only:
        read_query = _READ_QUERY_ZERO_CHUNKS
    elif include_enriched:
        read_query = _READ_QUERY_ALL
    else:
        read_query = _READ_QUERY
    shard_chars = shard_chars or _ALL_HEX
    cid_to_name: Dict[str, str] = {}
    async with driver.session() as session:
        result = await session.run(
            read_query, {"doc": doc_id, "shard_chars": shard_chars}
        )
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
    write_sem = asyncio.Semaphore(WRITE_CONCURRENCY)
    # Concept ids whose edges were written this pass, for centroid recompute.
    written_cids: set = set()
    # Mutable reference: when any task detects a broken httpx client, it
    # replaces the shared client once so all concurrent tasks benefit.
    client_ref: List[httpx.AsyncClient] = [http]

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
        batch_size = DENSE_MAX_CONCEPTS if len(text) > DENSE_TEXT_CHARS else MAX_CONCEPTS

        async with sem:
            merged: Dict[str, str] = {}
            for i in range(0, len(unique_names), batch_size):
                sub = unique_names[i : i + batch_size]
                if BACKEND == "vllm":
                    merged.update(await _vllm_rationales(client_ref, sub, text, chunk_id))
                else:
                    merged.update(await _ollama_rationales(client_ref, sub, text, chunk_id))

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
            embs = await _embed(client_ref, distinct)
            if len(embs) != len(distinct):
                logger.warning(
                    f"[{doc_id}] chunk {chunk_id}: embed mismatch "
                    f"({len(embs)} != {len(distinct)}); skipping {len(chunk_pairs)} edges"
                )
                stats["done"] += 1
                return
            emb_by_text = dict(zip(distinct, embs))
            # Sort rows by concept_id so all writers lock concepts in the
            # same order, preventing deadlocks under contention.
            write_rows = sorted(
                (
                    {"cid": cid, "chid": chunk_id, "rationale": r, "emb": emb_by_text[r]}
                    for cid, r in chunk_pairs
                ),
                key=lambda row: row["cid"],
            )
            async def _write_tx(tx):
                res = await tx.run(_WRITE_QUERY, {"rows": write_rows})
                rec = await res.single()
                return rec["cnt"] if rec else 0

            # Writer semaphore limits concurrent Neo4j write transactions
            # to reduce lock contention on hot Concept nodes, plus manual
            # exponential-backoff retry for transient LockAcquisitionTimeout.
            async with write_sem:
                async with driver.session() as session:
                    stats["updated"] += await _write_with_retry(session, _write_tx)
                    written_cids.update(cid for cid, _ in chunk_pairs)

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

    # Recompute concept-level rationale centroids for the concepts we touched.
    if written_cids:
        await _recompute_centroids(driver, written_cids)

    return (stats["updated"], total)


async def main(
    doc_ids: List[str],
    include_enriched: bool = False,
    dry_run: bool = False,
    zero_chunks_only: bool = False,
    shard: int = 0,
    shard_total: int = 1,
):
    driver = AsyncGraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))
    pg = await asyncpg.connect(
        host=PG_HOST, port=PG_PORT, database=PG_DB, user=PG_USER, password=PG_PASSWORD
    )
    sem = asyncio.Semaphore(CONCURRENCY)
    start = time.time()
    total_updated = 0
    total_chunks = 0

    shard_chars = shard_chars_for(shard, shard_total)

    mode = (
        "DRY-RUN"
        if dry_run
        else (
            "zero-chunks-only"
            if zero_chunks_only
            else ("ALL edges" if include_enriched else "resume-safe")
        )
    )
    model_desc = VLLM_MODEL if BACKEND == "vllm" else OLLAMA_MODEL
    logger.info(
        f"Enriching rationales for {len(doc_ids)} document(s) [{mode}] "
        f"(backend={BACKEND}, model={model_desc}, concurrency={CONCURRENCY}, "
        f"shard={shard}/{shard_total})"
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
                    doc_id, driver, pg, http, sem, include_enriched,
                    dry_run, zero_chunks_only, shard_chars,
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
    parser.add_argument(
        "--zero-chunks-only",
        action="store_true",
        dest="zero_chunks_only",
        help="Only reprocess chunks that have NO rationale on any edge "
        "(targeted retry of zero-yield chunks; tune with ENRICH_MAX_CONCEPTS/OLLAMA_TIMEOUT)",
    )
    parser.add_argument(
        "--shard",
        type=int,
        default=0,
        help="Zero-based shard index (chunks partitioned by chunk_id first hex nibble)",
    )
    parser.add_argument(
        "--shard-total",
        type=int,
        default=1,
        help="Total number of shards across all worker processes",
    )
    args = parser.parse_args()
    asyncio.run(
        main(
            args.source_ids,
            include_enriched=args.include_enriched,
            dry_run=args.dry_run,
            zero_chunks_only=args.zero_chunks_only,
            shard=args.shard,
            shard_total=args.shard_total,
        )
    )
