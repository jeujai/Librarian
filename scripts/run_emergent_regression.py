#!/usr/bin/env python3
"""
Run the emergent-concept regression set (idiomatic query -> expected concept).

Loads ``tests/fixtures/emergent_concept_golden_queries.jsonl`` and, for each
record, decomposes the query with the live ``QueryDecomposer`` and asserts that
every ``expected_concepts`` name appears in the top-``top_k`` concept matches.
This makes the emergent/canonical match-threshold split falsifiable (§8): a
pair fails when the expected concept does not surface, giving a concrete signal
to tune ``EMERGENT_SIMILARITY_THRESHOLD`` / ``CANONICAL_SIMILARITY_THRESHOLD``.

Host-runnable (mirrors scripts/debug_retrieval.py): inserts the local src tree,
connects to Neo4j + the model server directly — no FastAPI, no Docker.

Usage:
    python scripts/run_emergent_regression.py

Environment variables (or .env):
    EMERGENT_REGRESSION_FIXTURE (default: tests/fixtures/emergent_concept_golden_queries.jsonl)
    NEO4J_URI                   (default: bolt://localhost:7687)
    NEO4J_USER                  (default: neo4j)
    NEO4J_PASSWORD              (default: password)
    MODEL_SERVER_URL            (default: http://localhost:8001)
    EMERGENT_SIMILARITY_THRESHOLD (default: 0.65)
    CANONICAL_SIMILARITY_THRESHOLD (default: 0.75)

Exit code 0 if every pair passes, 1 if any pair fails.
"""

import asyncio
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

_DEFAULT_FIXTURE = os.path.join(
    os.path.dirname(__file__), "..", "tests", "fixtures",
    "emergent_concept_golden_queries.jsonl",
)
FIXTURE_PATH = os.path.abspath(
    os.getenv("EMERGENT_REGRESSION_FIXTURE", _DEFAULT_FIXTURE)
)

NEO4J_URI = os.getenv("NEO4J_URI", "bolt://localhost:7687")
NEO4J_USER = os.getenv("NEO4J_USER", "neo4j")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD", "password")
MODEL_SERVER_URL = os.getenv("MODEL_SERVER_URL", "http://localhost:8001")
EMERGENT_THRESHOLD = float(os.getenv("EMERGENT_SIMILARITY_THRESHOLD", "0.65"))
CANONICAL_THRESHOLD = float(os.getenv("CANONICAL_SIMILARITY_THRESHOLD", "0.75"))


def load_fixture(path: str) -> list:
    records = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            records.append(json.loads(line))
    return records


async def main():
    if not os.path.exists(FIXTURE_PATH):
        print(f"Fixture not found: {FIXTURE_PATH}")
        sys.exit(1)

    from multimodal_librarian.clients.model_server_client import (
        get_model_client,
        initialize_model_client,
    )
    from multimodal_librarian.clients.neo4j_client import Neo4jClient
    from multimodal_librarian.components.kg_retrieval.query_decomposer import (
        QueryDecomposer,
    )

    neo4j = Neo4jClient(uri=NEO4J_URI, user=NEO4J_USER, password=NEO4J_PASSWORD)
    await neo4j.connect()
    await initialize_model_client(base_url=MODEL_SERVER_URL)
    model_client = get_model_client()

    decomposer = QueryDecomposer(
        neo4j_client=neo4j,
        model_server_client=model_client,
        similarity_threshold=EMERGENT_THRESHOLD,
        canonical_similarity_threshold=CANONICAL_THRESHOLD,
    )

    records = load_fixture(FIXTURE_PATH)
    print(
        f"Emergent regression: {len(records)} pairs "
        f"(emergent={EMERGENT_THRESHOLD}, canonical={CANONICAL_THRESHOLD})\n"
    )

    failures = 0
    for rec in records:
        query = rec["query"]
        expected = rec["expected_concepts"]
        top_k = int(rec.get("top_k", 10))

        decomposition = await decomposer.decompose(query)
        matches = decomposition.concept_matches[:top_k]
        matched_names = {m.get("name", "").strip().lower() for m in matches}

        missing = [n for n in expected if n.lower() not in matched_names]
        status = "PASS" if not missing else "FAIL"

        print(f"[{status}] {rec['query_id']}: {query!r}")
        if rec.get("note"):
            print(f"       note: {rec['note']}")
        print(f"       top-{top_k} matches: {sorted(matched_names) or '[]'}")
        if missing:
            failures += 1
            print(f"       MISSING: {missing}")

    print(f"\n{len(records) - failures}/{len(records)} pairs passed")
    try:
        await model_client.close()
    except Exception:
        pass
    await neo4j.close()
    sys.exit(1 if failures else 0)


if __name__ == "__main__":
    asyncio.run(main())
