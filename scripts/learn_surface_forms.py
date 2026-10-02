#!/usr/bin/env python3
"""
Learn corpus-derived surface forms for seed concepts (provenance='seed').

Implements the paraphrase-case pipeline from corpus-derived-surface-forms/design.md:
bootstrap-propose (bare name -> recall -> re-propose with chunk context) followed by
a co-occurrence + cross-encoder select gate.  Learned surface forms are written back
to ``Concept.surface_forms``, replacing the hand-written ones in seed_emergent_concepts.py.

Run backfill_similar_to.py FIRST: the abstraction case ("work restrictions" -> "practice
restrictions") is a SIMILAR_TO link, not a surface form.  Once that edge exists, the
abstraction-case concept keeps its evidence via the link, so replacing its hand-written
surface forms with the corpus-derived set is safe.

Usage:
    python scripts/learn_surface_forms.py --dry-run   # default: preview only
    python scripts/learn_surface_forms.py --write      # persist to Neo4j

Environment variables (or .env):
    NEO4J_URI / NEO4J_USER / NEO4J_PASSWORD
    PG_HOST / PG_PORT / PG_DB / PG_USER / PG_PASSWORD
    MODEL_SERVER_URL      (default: http://localhost:8001)  cross-encoder /rerank
    DEEPSEEK_API_KEY      (required)                        proposal LLM
    DEEPSEEK_MODEL        (default: deepseek-chat)
    DEEPSEEK_BASE_URL     (default: https://api.deepseek.com)
    COOCCUR_THRESHOLD     (default: 0.40)  same-sentence anchor co-occurrence floor
    MIN_SCORE             (default: 0.505) cross-encoder precision floor
"""

import asyncio
import logging
import os
import sys
from datetime import datetime, timezone

import asyncpg
import httpx
from neo4j import AsyncGraphDatabase

from multimodal_librarian.components.kg_retrieval.surface_form_learner import (
    BARE_PROPOSE_TEMPLATE,
    CONTEXT_PROPOSE_TEMPLATE,
    anchors_for,
    evaluate_candidates,
    parse_json_list,
)

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

DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY", "")
DEEPSEEK_MODEL = os.getenv("DEEPSEEK_MODEL", "deepseek-chat")
DEEPSEEK_BASE_URL = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com")

COOCCUR_THRESHOLD = float(os.getenv("COOCCUR_THRESHOLD", "0.40"))
MIN_SCORE = float(os.getenv("MIN_SCORE", "0.505"))

RECALL_LIMIT = 50
CONTEXT_CHARS = 3000

_TARGET_QUERY = """
MATCH (c:Concept)
WHERE c.provenance = 'seed'
RETURN c.name AS name, c.concept_type AS concept_type,
       c.surface_forms AS existing_surface_forms
"""

_WRITE_QUERY = """
MATCH (c:Concept {name_lower: toLower($name), scope: 'public'})
SET c.surface_forms = $forms, c.updated_at = $ts
RETURN c.name AS name
"""


async def _propose(http: httpx.AsyncClient, prompt: str) -> str:
    resp = await http.post(
        f"{DEEPSEEK_BASE_URL}/chat/completions",
        headers={"Authorization": f"Bearer {DEEPSEEK_API_KEY}"},
        json={
            "model": DEEPSEEK_MODEL,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0,
            "max_tokens": 900,
        },
        timeout=120.0,
    )
    resp.raise_for_status()
    return resp.json()["choices"][0]["message"]["content"] or ""


async def _recall(pg: asyncpg.Connection, phrase: str, limit: int) -> list:
    rows = await pg.fetch(
        "SELECT content FROM multimodal_librarian.knowledge_chunks "
        "WHERE content ILIKE $1 LIMIT $2",
        f"%{phrase}%",
        limit,
    )
    return [r["content"] or "" for r in rows]


async def _rerank(http: httpx.AsyncClient, query: str, documents: list) -> list:
    resp = await http.post(
        f"{MODEL_SERVER_URL}/rerank",
        json={"query": query, "documents": documents},
        timeout=120.0,
    )
    resp.raise_for_status()
    return resp.json().get("scores", [])


async def _learn_one(pg, http, name, concept_type):
    """Bootstrap-propose + co-occurrence/ce select for a single concept."""
    anchors = anchors_for(concept_type, name)

    round0 = parse_json_list(
        await _propose(
            http, BARE_PROPOSE_TEMPLATE.format(concept=name, ctype=concept_type or "")
        )
    )
    # Build context from round-0 candidates' chunks, then re-propose.
    context_chunks: list = []
    for cand in round0:
        for chunk in await _recall(pg, cand, 3):
            context_chunks.append(chunk)
    context = " ".join(context_chunks[:10])[:CONTEXT_CHARS]
    round1 = parse_json_list(
        await _propose(
            http,
            CONTEXT_PROPOSE_TEMPLATE.format(
                concept=name, ctype=concept_type or "", context=context
            ),
        )
    )

    candidates = list(dict.fromkeys(round0 + round1))
    chunks_by_candidate = {}
    score_by_candidate = {}
    for cand in candidates:
        chunks = await _recall(pg, cand, RECALL_LIMIT)
        chunks_by_candidate[cand] = chunks
        if chunks:
            score_by_candidate[cand] = (await _rerank(http, cand, [chunks[0]]))[0]

    survivors = evaluate_candidates(
        candidates,
        anchors,
        chunks_by_candidate,
        score_by_candidate,
        min_score=MIN_SCORE,
        cooccur_threshold=COOCCUR_THRESHOLD,
    )
    return candidates, survivors


async def main(write: bool):
    if not DEEPSEEK_API_KEY:
        logger.error("DEEPSEEK_API_KEY is required for surface-form proposal.")
        return

    driver = AsyncGraphDatabase.driver(
        NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD)
    )
    pg = await asyncpg.connect(
        host=PG_HOST, port=PG_PORT, database=PG_DB,
        user=PG_USER, password=PG_PASSWORD,
    )

    try:
        async with driver.session() as session:
            result = await session.run(_TARGET_QUERY)
            concepts = [
                {
                    "name": r["name"],
                    "concept_type": r["concept_type"],
                    "existing": r.get("existing_surface_forms") or [],
                }
                async for r in result
            ]

        if not concepts:
            logger.info("0 seed concepts; nothing to do.")
            return

        logger.info(f"{len(concepts)} seed concept(s) to learn surface forms for")

        ts = datetime.now(timezone.utc).isoformat()
        async with httpx.AsyncClient() as http:
            for concept in concepts:
                name = concept["name"]
                existing = concept["existing"]
                candidates, survivors = await _learn_one(
                    pg, http, name, concept["concept_type"]
                )
                logger.info(
                    f"{name!r}: {len(candidates)} candidates -> "
                    f"{len(survivors)} survivors {survivors}"
                )
                if not survivors:
                    logger.warning(
                        f"{name!r}: no survivors; keeping existing surface forms "
                        f"(not wiping to empty)"
                    )
                    continue
                if set(survivors) == set(existing):
                    logger.info(f"{name!r}: unchanged; skip write")
                    continue
                if write:
                    async with driver.session() as session:
                        await session.run(
                            _WRITE_QUERY,
                            {"name": name, "forms": survivors, "ts": ts},
                        )
                    logger.info(
                        f"{name!r}: wrote {len(survivors)} surface forms "
                        f"(replacing {len(existing)})"
                    )
                else:
                    logger.info(
                        f"{name!r}: DRY RUN — would replace {existing} with {survivors}"
                    )

    finally:
        await pg.close()
        await driver.close()


if __name__ == "__main__":
    write = "--write" in sys.argv
    if write:
        logger.info("WRITE MODE: surface forms will be persisted to Neo4j.")
    else:
        logger.info("DRY RUN: no writes. Pass --write to persist.")
    asyncio.run(main(write=write))
