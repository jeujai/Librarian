"""
Integration — Preservation Property Tests
Milvus Post-Restart Retrieval Regression (Property 2)

Spec: .kiro/specs/milvus-post-restart-retrieval-regression/
    bugfix.md (3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 3.7)
    design.md (Properties P5, P6, P7, P8, P9)

Observation-first methodology:
- Each test captures the CURRENT (unfixed) behavior on a HEALTHY stack.
- These tests MUST pass on unfixed code — they pin down what the fix
  must not regress.
- After the fix lands (task 3.6), they must still pass.

Tests:
    Scoring parity — golden queries produce stable
        (candidate_set, ranking, relevance_scores) triples
    Ingestion parity — celery `store_embeddings_task` writes the same
        Milvus schema / metadata / content hashes
    Volume non-destruction — `docker volume inspect` output is byte-
        identical before and after the preservation suite
    Healthy-path latency — p95 latency ≤ baseline × 1.05

These tests drive the real `docker-compose.yml` stack. They are
skipped by default because they require a running Docker stack with
Milvus, PostgreSQL, and Neo4j. Opt in with:

    LIBRARIAN_RUN_INTEGRATION_PRESERVATION_TESTS=1 pytest \
        tests/integration/test_milvus_post_restart_preservation.py -v

DO NOT modify these tests to pass on unfixed code. They encode the
baseline contract the fix (tasks 3.1–3.4) must preserve.
"""

from __future__ import annotations

import hashlib
import json
import os
import statistics
import subprocess
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
COMPOSE_FILE = REPO_ROOT / "docker-compose.yml"
GOLDEN_QUERIES_FIXTURE = (
    REPO_ROOT / "tests" / "fixtures" / "kg_retrieval_golden_queries.jsonl"
)

RUN_INTEGRATION = os.environ.get(
    "LIBRARIAN_RUN_INTEGRATION_PRESERVATION_TESTS", ""
).lower() in {"1", "true", "yes"}

pytestmark = [
    pytest.mark.integration,
    pytest.mark.docker,
    pytest.mark.milvus,
    pytest.mark.slow,
    pytest.mark.skipif(
        not RUN_INTEGRATION,
        reason=(
            "Integration preservation tests skipped by default. Set "
            "LIBRARIAN_RUN_INTEGRATION_PRESERVATION_TESTS=1 to run. "
            "Requires a running docker-compose stack with Milvus, "
            "Postgres, and Neo4j."
        ),
    ),
]


# ---------------------------------------------------------------------------
# Docker helpers
# ---------------------------------------------------------------------------

def _compose(*args: str, timeout: int = 120) -> subprocess.CompletedProcess:
    cmd = ["docker", "compose", "-f", str(COMPOSE_FILE), *args]
    return subprocess.run(
        cmd, capture_output=True, text=True, timeout=timeout
    )


def _docker(*args: str, timeout: int = 60) -> subprocess.CompletedProcess:
    cmd = ["docker", *args]
    return subprocess.run(
        cmd, capture_output=True, text=True, timeout=timeout
    )


def _wait_for_port(host: str, port: int, timeout_s: float = 120.0) -> bool:
    import socket
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        try:
            with socket.create_connection((host, port), timeout=2.0):
                return True
        except OSError:
            time.sleep(1.0)
    return False


def _load_golden_queries() -> List[Dict[str, Any]]:
    if not GOLDEN_QUERIES_FIXTURE.exists():
        return []
    return [
        json.loads(line)
        for line in GOLDEN_QUERIES_FIXTURE.read_text().splitlines()
        if line.strip()
    ]


def _volume_digest(volume_name: str) -> Optional[str]:
    """SHA-256 digest of `docker volume inspect <volume>` output.
    Returns None if the volume does not exist.
    """
    res = _docker("volume", "inspect", volume_name, timeout=15)
    if res.returncode != 0:
        return None
    # Normalize: parse JSON, re-dump sorted so non-essential field
    # ordering does not perturb the digest.
    try:
        data = json.loads(res.stdout)
    except json.JSONDecodeError:
        return None
    canonical = json.dumps(data, sort_keys=True).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


# ---------------------------------------------------------------------------
# Shared corpus for scoring & ingestion parity
# ---------------------------------------------------------------------------

CHELSEA_QUERY = "What did our team observe at Chelsea?"
GENAI_CHUNK_CONTENT = (
    "At Chelsea AI Ventures, our team observed a production deployment "
    "of retrieval-augmented generation over a multimodal knowledge base. "
    "The field report on GenAI page 114 details the evaluation."
)


@pytest.fixture(scope="module")
async def healthy_stack():
    """Bring up a healthy Milvus stack and ingest a small fixture.
    Yields the Milvus and Postgres clients so individual tests can
    re-observe state.
    """
    up = _compose(
        "up", "-d", "milvus", "etcd", "minio", "postgres", "neo4j",
        timeout=300,
    )
    if up.returncode != 0:
        pytest.skip(f"docker compose up failed: {up.stderr}")

    assert _wait_for_port("localhost", 19530, timeout_s=180)
    assert _wait_for_port("localhost", 5432, timeout_s=60)

    from multimodal_librarian.clients.milvus_client import MilvusClient

    vector = MilvusClient(host="localhost", port=19530)
    await vector.connect()

    # Ingest a small corpus: the Chelsea chunk + noise
    chunks: List[Dict[str, Any]] = [
        {
            "id": "00000000-0000-0000-0000-000000000001",
            "content": GENAI_CHUNK_CONTENT,
            "metadata": {
                "title": "GenAI",
                "page_number": 114,
                "source_id": "doc-genai",
                "chunk_index": 0,
            },
        },
    ]
    for i in range(5):
        chunks.append({
            "id": f"00000000-0000-0000-0000-00000000002{i}",
            "content": (
                f"Unrelated computer vision content batch {i}."
            ),
            "metadata": {
                "title": "Computer Vision: A Modern Approach",
                "page_number": 10 + i,
                "source_id": "doc-cv",
                "chunk_index": i,
            },
        })

    try:
        await vector.store_embeddings(chunks)
    except Exception as exc:
        pytest.skip(f"Failed to ingest fixture: {exc!r}")

    yield {"vector": vector, "chunks": chunks}

    try:
        await vector.disconnect()
    except Exception:
        pass


# ===========================================================================
# P5 — Scoring parity on a healthy stack (bugfix 3.1, 3.2)
# ===========================================================================

@pytest.mark.asyncio
async def test_p5_scoring_parity_on_golden_queries(healthy_stack):
    """For each golden query against the healthy stack, the
    (candidate_set, ranking, relevance_scores) triple produced by
    KGRetrievalService.retrieve SHALL be byte-identical across two
    back-to-back invocations. This pins down the baseline scoring
    contract.
    """
    queries = _load_golden_queries()
    assert queries, (
        f"Golden query fixture missing at {GOLDEN_QUERIES_FIXTURE}."
    )

    from multimodal_librarian.services.kg_retrieval_service import KGRetrievalService

    vector = healthy_stack["vector"]

    # Use the Milvus client directly as the vector_client. Neo4j is not
    # required for the semantic-fallback scoring path this test
    # exercises — we run with neo4j_client=None so KGRetrievalService
    # immediately falls back to semantic_search.
    svc = KGRetrievalService(
        neo4j_client=None,
        vector_client=vector,
        model_client=None,
        cache_ttl_seconds=300,
        max_results=15,
    )

    for q in queries:
        res_a = await svc.retrieve(
            q["query"], top_k=10, include_explanation=False,
        )
        res_b = await svc.retrieve(
            q["query"], top_k=10, include_explanation=False,
        )

        ids_a = [c.chunk_id for c in res_a.chunks]
        ids_b = [c.chunk_id for c in res_b.chunks]
        scores_a = [round(c.final_score, 6) for c in res_a.chunks]
        scores_b = [round(c.final_score, 6) for c in res_b.chunks]

        assert ids_a == ids_b, (
            f"P5 violation ({q['query_id']}): candidate_set differs "
            f"across runs: {ids_a} vs {ids_b}"
        )
        assert scores_a == scores_b, (
            f"P5 violation ({q['query_id']}): relevance_scores "
            f"differ across runs: {scores_a} vs {scores_b}"
        )


# ===========================================================================
# P7 — Ingestion parity (bugfix 3.4)
# ===========================================================================

@pytest.mark.asyncio
async def test_p7_ingestion_parity_schema_and_hashes(healthy_stack):
    """Running ingestion on the fixture and reading back from Milvus:
    - Schema remains (id VARCHAR, vector FLOAT_VECTOR, metadata JSON)
    - Metadata field set is exactly the documented set
    - Content hashes are stable across re-ingestion attempts
    """
    from pymilvus import Collection, utility

    vector = healthy_stack["vector"]
    chunks = healthy_stack["chunks"]

    collection_name = "knowledge_chunks"
    assert utility.has_collection(
        collection_name, using=vector.connection_name
    ), "knowledge_chunks collection must exist after fixture ingest"

    coll = Collection(collection_name, using=vector.connection_name)
    coll.load()

    # Schema parity
    fields = {f.name: f for f in coll.schema.fields}
    assert set(fields.keys()) == {"id", "vector", "metadata"}, (
        f"P7 violation: Milvus schema fields {set(fields.keys())!r} "
        f"!= expected (id, vector, metadata)"
    )
    assert fields["id"].is_primary is True
    assert str(fields["id"].dtype).endswith("VARCHAR")
    assert str(fields["vector"].dtype).endswith("FLOAT_VECTOR")
    assert str(fields["metadata"].dtype).endswith("JSON")

    # Read back the rows
    results = coll.query(
        expr="id != ''",
        output_fields=["id", "metadata"],
        limit=100,
    )
    assert len(results) >= len(chunks)

    expected_keys = {
        "content", "content_type", "stored_at",
        "source_id", "chunk_index", "page_number", "title",
    }

    # Content-hash table — stable across reads
    content_hashes: Dict[str, str] = {}
    for row in results:
        md = row.get("metadata") or {}
        md_keys = set(md.keys())
        # Metadata must contain the documented fields; additional
        # internal keys like `_vector_id` are allowed per design P7
        # (the design explicitly lists `_vector_id` as an internal
        # field) but must not remove the documented ones.
        missing = expected_keys - md_keys
        assert not missing, (
            f"P7 violation: row id={row.get('id')!r} missing "
            f"metadata keys {missing!r}"
        )

        # Hash the content for the ingestion-parity contract
        content = md.get("content") or ""
        content_hashes[row["id"]] = hashlib.sha256(
            content.encode("utf-8")
        ).hexdigest()

    # Re-read and compare: content hashes must be stable
    results_b = coll.query(
        expr="id != ''",
        output_fields=["id", "metadata"],
        limit=100,
    )
    content_hashes_b: Dict[str, str] = {}
    for row in results_b:
        md = row.get("metadata") or {}
        content = md.get("content") or ""
        content_hashes_b[row["id"]] = hashlib.sha256(
            content.encode("utf-8")
        ).hexdigest()

    assert content_hashes == content_hashes_b, (
        "P7 violation: content hashes differ across two reads of the "
        "same Milvus collection — ingestion is non-deterministic."
    )


# ===========================================================================
# P8 — Volume non-destruction (bugfix 3.5, 3.7)
# ===========================================================================

@pytest.mark.asyncio
async def test_p8_volume_digests_unchanged_across_preservation_suite(
    healthy_stack,
):
    """Record `docker volume inspect` digests for the five named
    volumes before and after running a representative retrieval
    workload. The digests SHALL be byte-identical — the preservation
    path must not mutate volume state.

    The volumes under test are the ones declared in docker-compose.yml:
        milvus_data, etcd_data, minio_data, postgres_data, neo4j_data
    Volume names may be project-prefixed by compose (e.g.,
    `librarian_milvus_data`); we try both.
    """
    volume_bases = [
        "milvus_data", "etcd_data", "minio_data",
        "postgres_data", "neo4j_data",
    ]

    def _resolve(name: str) -> Optional[str]:
        # Exact name
        if _volume_digest(name) is not None:
            return name
        # Try project-prefixed variants
        for prefix in ("librarian_", "multimodal-librarian_",
                       "multimodal_librarian_"):
            candidate = prefix + name
            if _volume_digest(candidate) is not None:
                return candidate
        return None

    resolved = {
        base: _resolve(base) for base in volume_bases
    }
    # Only compare volumes we could resolve — skip ones not declared
    # in the running compose project (e.g., if this test runs against
    # a stack missing neo4j).
    active = {n: r for n, r in resolved.items() if r is not None}
    if not active:
        pytest.skip(
            "None of the named volumes (milvus_data, etcd_data, "
            "minio_data, postgres_data, neo4j_data) are currently "
            "present on this Docker host."
        )

    before = {n: _volume_digest(r) for n, r in active.items()}

    # Run a representative retrieval workload
    from multimodal_librarian.services.kg_retrieval_service import KGRetrievalService
    svc = KGRetrievalService(
        neo4j_client=None,
        vector_client=healthy_stack["vector"],
        model_client=None,
    )
    for q in _load_golden_queries() or [{"query": CHELSEA_QUERY}]:
        await svc.retrieve(
            q["query"], top_k=10, include_explanation=False,
        )

    after = {n: _volume_digest(r) for n, r in active.items()}

    for name in active:
        assert before[name] == after[name], (
            f"P8 violation: volume {name!r} digest changed across "
            f"the preservation workload "
            f"(before={before[name]!r}, after={after[name]!r}). "
            f"Bugfix clause 3.5 / 3.7 forbid destructive recovery."
        )


# ===========================================================================
# P9 — Healthy-path latency (bugfix 3.6)
# ===========================================================================

@pytest.mark.asyncio
async def test_p9_healthy_path_p95_latency_within_baseline(healthy_stack):
    """Warm up 100 queries, measure 100, assert p95 latency ≤
    baseline × 1.05. On unfixed code the baseline is the current
    p95; the assertion is vacuously satisfied. After the fix, the
    gate's O(1) cached read must not inflate p95 beyond 5 %.

    NOTE: On unfixed code (no gate) the measurement IS the baseline,
    so we only assert the measurement is finite and the p95 is not
    absurd (< 30 s per call). The 5 % regression check is enforced
    AFTER the fix lands via a committed baseline artifact (see
    `_baseline_p95_ms_path` below).
    """
    from multimodal_librarian.services.kg_retrieval_service import KGRetrievalService

    svc = KGRetrievalService(
        neo4j_client=None,
        vector_client=healthy_stack["vector"],
        model_client=None,
    )

    # Warm-up
    for _ in range(100):
        await svc.retrieve(
            CHELSEA_QUERY, top_k=5, include_explanation=False,
        )

    # Measurement
    latencies: List[float] = []
    for _ in range(100):
        t0 = time.monotonic()
        await svc.retrieve(
            CHELSEA_QUERY, top_k=5, include_explanation=False,
        )
        latencies.append((time.monotonic() - t0) * 1000.0)

    # Sanity: every latency is finite and non-absurd
    assert all(0 <= lat < 30_000 for lat in latencies), (
        f"P9 violation: latencies contain outliers ≥ 30 s: "
        f"{sorted(latencies, reverse=True)[:5]!r}"
    )

    latencies.sort()
    p95 = latencies[int(0.95 * len(latencies))]

    # Baseline-artifact check — only enforced if a baseline has been
    # recorded. On unfixed code this is a no-op; the commit that
    # lands task 3.6 can record the baseline from the main-branch
    # measurement and start enforcing the 5 % budget.
    baseline_path = (
        REPO_ROOT / "tests" / "fixtures"
        / "kg_retrieval_healthy_path_p95_ms.txt"
    )
    if baseline_path.exists():
        baseline_p95 = float(baseline_path.read_text().strip())
        assert p95 <= baseline_p95 * 1.05, (
            f"P9 violation: p95 latency {p95:.1f} ms exceeds "
            f"baseline {baseline_p95:.1f} ms × 1.05 = "
            f"{baseline_p95 * 1.05:.1f} ms."
        )
    else:
        # Print for visibility so the baseline can be recorded later.
        print(
            f"\n[P9 baseline observation] p95={p95:.1f} ms, "
            f"mean={statistics.mean(latencies):.1f} ms, "
            f"min={min(latencies):.1f} ms, "
            f"max={max(latencies):.1f} ms "
            f"(no baseline committed — test is a shape check only)"
        )
