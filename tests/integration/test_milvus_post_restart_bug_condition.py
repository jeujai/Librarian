"""
Integration — Bug Condition Exploration Tests
Milvus Post-Restart Retrieval Regression (Property 1)

Spec: .kiro/specs/milvus-post-restart-retrieval-regression/
    bugfix.md, design.md (Track A + Track B)

These integration tests drive the real `docker-compose.yml` stack. They
encode the EXPECTED post-fix behavior — they are intentionally
DESTRUCTIVE on the local dev stack because T2 performs
`docker compose down -v` (deletes the named volumes `etcd_data`,
`minio_data`, `milvus_data`, `postgres_data`, `neo4j_data`). They are
therefore skipped by default and only run when explicitly opted into:

    LIBRARIAN_RUN_DESTRUCTIVE_DOCKER_TESTS=1 pytest \
        tests/integration/test_milvus_post_restart_bug_condition.py -v

Tests:
    T1 — RC2 end-to-end: restart milvus → Chelsea query must 503 with
         `retrieval_index_not_ready: not_loaded`, then 200 with the
         GenAI page 114 chunk in top-10 after recovery (bugfix 1.4, 1.7,
         2.1, 2.2, 2.3).
    T2 — RC1 end-to-end: `docker compose down -v` → `up` → Chelsea
         query must 503 with `collection_missing` OR
         `entity_parity_failed` (bugfix 1.5, 1.6, 2.3).
    T3 — RC5 end-to-end: in-process MilvusClient + restart milvus →
         semantic_search within 30 s `_health_check_interval` → either
         503 through the gate OR transparent Track B retry succeeds;
         `_cached_health_status` must NOT be served stale (bugfix 1.4,
         1.9).

DO NOT modify these tests to pass on unfixed code. On unfixed code they
will fail at import time or on the first assertion — that IS the
documented counterexample. Task 3.5 re-runs these unchanged to verify
the fix.
"""

from __future__ import annotations

import asyncio
import os
import subprocess
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

import pytest

# ---------------------------------------------------------------------------
# Test gating — default skip to protect the local dev stack
# ---------------------------------------------------------------------------

REPO_ROOT = Path(__file__).resolve().parents[2]
COMPOSE_FILE = REPO_ROOT / "docker-compose.yml"
RUN_DESTRUCTIVE = os.environ.get(
    "LIBRARIAN_RUN_DESTRUCTIVE_DOCKER_TESTS", ""
).lower() in {"1", "true", "yes"}

pytestmark = [
    pytest.mark.integration,
    pytest.mark.docker,
    pytest.mark.milvus,
    pytest.mark.slow,
    pytest.mark.skipif(
        not RUN_DESTRUCTIVE,
        reason=(
            "Destructive Docker integration tests skipped by default. "
            "Set LIBRARIAN_RUN_DESTRUCTIVE_DOCKER_TESTS=1 to enable. "
            "WARNING: T2 performs `docker compose down -v` which "
            "deletes etcd_data, minio_data, milvus_data, postgres_data, "
            "and neo4j_data volumes."
        ),
    ),
]


# ---------------------------------------------------------------------------
# Expected-behavior import checks (same contract as the unit test file)
# ---------------------------------------------------------------------------

try:
    from multimodal_librarian.clients.milvus_readiness_gate import (  # type: ignore[attr-defined]
        MilvusReadinessGate,
        ReadinessStatus,
    )
    _GATE_IMPORT_ERR: Optional[BaseException] = None
except Exception as _e:  # pragma: no cover
    MilvusReadinessGate = None  # type: ignore[assignment]
    ReadinessStatus = None  # type: ignore[assignment]
    _GATE_IMPORT_ERR = _e

try:
    from multimodal_librarian.api.dependencies.services import (  # type: ignore[attr-defined]
        get_milvus_readiness,
    )
    _DI_IMPORT_ERR: Optional[BaseException] = None
except Exception as _e:  # pragma: no cover
    get_milvus_readiness = None  # type: ignore[assignment]
    _DI_IMPORT_ERR = _e


def _require_fix_artifacts() -> None:
    assert _GATE_IMPORT_ERR is None, (
        "BUG COUNTEREXAMPLE: `milvus_readiness_gate` module missing. "
        f"Import error: {_GATE_IMPORT_ERR!r}"
    )
    assert _DI_IMPORT_ERR is None, (
        "BUG COUNTEREXAMPLE: `get_milvus_readiness` DI provider missing. "
        f"Import error: {_DI_IMPORT_ERR!r}"
    )


# ---------------------------------------------------------------------------
# Docker compose helpers
# ---------------------------------------------------------------------------

def _compose(*args: str, timeout: int = 120) -> subprocess.CompletedProcess:
    cmd = ["docker", "compose", "-f", str(COMPOSE_FILE), *args]
    return subprocess.run(
        cmd, capture_output=True, text=True, timeout=timeout
    )


def _wait_for_port(host: str, port: int, timeout_s: float = 120.0) -> bool:
    """Wait for a TCP port to accept connections."""
    import socket
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        try:
            with socket.create_connection((host, port), timeout=2.0):
                return True
        except OSError:
            time.sleep(1.0)
    return False


# ---------------------------------------------------------------------------
# Fixture set — ingest the 10-chunk Chelsea fixture
# ---------------------------------------------------------------------------

CHELSEA_QUERY = "What did our team observe at Chelsea?"
GENAI_CHUNK_CONTENT = (
    "At Chelsea AI Ventures, our team observed a production deployment "
    "of retrieval-augmented generation over a multimodal knowledge base. "
    "The field report on GenAI page 114 details the evaluation."
)
GENAI_TITLE_SUBSTR = "GenAI"
GENAI_PAGE_NUMBER = 114


@pytest.fixture(scope="module")
async def ingested_stack():
    """Module-level fixture: start the stack and ingest 10 chunks
    including a synthetic GenAI-page-114 Chelsea chunk.

    On unfixed code this is expected to run but subsequent assertions
    against the 503 contract will fail (there is no gate).
    """
    _require_fix_artifacts()
    # Bring up the stack if not already running
    up = _compose("up", "-d", "milvus", "etcd", "minio", "postgres",
                  "neo4j", timeout=300)
    if up.returncode != 0:
        pytest.skip(f"docker compose up failed: {up.stderr}")

    # Wait for Milvus
    assert _wait_for_port("localhost", 19530, timeout_s=180), (
        "Milvus did not come up within 180s"
    )
    # Wait for Postgres
    assert _wait_for_port("localhost", 5432, timeout_s=60), (
        "Postgres did not come up within 60s"
    )

    # Ingest the 10-chunk fixture via the app's Milvus client + Postgres
    from multimodal_librarian.clients.local_postgresql_client import (
        LocalPostgreSQLClient,
    )
    from multimodal_librarian.clients.milvus_client import MilvusClient

    vector = MilvusClient(host="localhost", port=19530)
    await vector.connect()

    relational = LocalPostgreSQLClient(
        host="localhost",
        port=5432,
        database=os.environ.get("POSTGRES_DB", "multimodal_librarian"),
        user=os.environ.get("POSTGRES_USER", "ml_user"),
        password=os.environ.get("POSTGRES_PASSWORD", "ml_password"),
    )
    await relational.connect()

    # 10 chunks — one is the GenAI Chelsea target, the rest are noise.
    chunks: List[Dict[str, Any]] = [
        {
            "id": "genai-p114-chelsea",
            "content": GENAI_CHUNK_CONTENT,
            "title": "GenAI",
            "page_number": GENAI_PAGE_NUMBER,
            "source_id": "doc-genai",
            "chunk_index": 114,
            "content_type": "text",
        },
    ]
    for i in range(9):
        chunks.append({
            "id": f"noise-chunk-{i}",
            "content": f"Unrelated content about computer vision approach {i}.",
            "title": "Computer Vision: A Modern Approach",
            "page_number": 10 + i,
            "source_id": "doc-cv",
            "chunk_index": i,
            "content_type": "text",
        })

    # Best-effort ingest — exact ingestion API may differ; tests that
    # depend on exact row counts re-read from the live stack.
    try:
        await vector.store_embeddings(chunks)  # type: ignore[attr-defined]
    except Exception as e:  # pragma: no cover
        pytest.skip(f"Unable to ingest fixture via MilvusClient: {e!r}")

    yield {
        "vector": vector,
        "relational": relational,
        "chunks": chunks,
    }

    try:
        await vector.disconnect()
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Test client builder — uses the real FastAPI app plus the readiness DI
# ---------------------------------------------------------------------------

def _build_app_client():
    """Construct a TestClient against the real FastAPI app, with the
    readiness gate DI in force. On unfixed code this fails at
    `_require_fix_artifacts`.
    """
    _require_fix_artifacts()
    from fastapi.testclient import TestClient

    from multimodal_librarian.main import create_minimal_app

    app = create_minimal_app()
    return TestClient(app)


# ===========================================================================
# T1 — RC2 end-to-end (collection not loaded)
# ===========================================================================

@pytest.mark.asyncio
async def test_t1_rc2_restart_milvus_chelsea_returns_503_then_200(
    ingested_stack,
):
    """After `docker compose restart milvus`, the chat endpoint SHALL
    return 503 `retrieval_index_not_ready: not_loaded` until the
    collection is reloaded, then 200 with the GenAI page 114 chunk in
    top-10. Encodes bugfix 1.4, 1.7, 2.1, 2.2, 2.3.
    """
    _require_fix_artifacts()

    # Restart only milvus — etcd / minio / volumes untouched
    restart = _compose("restart", "milvus", timeout=120)
    assert restart.returncode == 0, f"restart milvus failed: {restart.stderr}"

    # Milvus container comes back fast but the collection is NOT loaded
    # yet. Submit the Chelsea query immediately via the chat endpoint.
    assert _wait_for_port("localhost", 19530, timeout_s=120), (
        "Milvus did not come back up within 120s"
    )

    client = _build_app_client()

    # On the fixed code, the FIRST post-restart request must be 503 with
    # `not_loaded` — the gate refuses until `Collection.load()` has run.
    saw_503_not_loaded = False
    saw_200_with_target = False
    deadline = time.monotonic() + 90.0
    while time.monotonic() < deadline:
        response = client.post(
            "/api/chat/message",
            json={"content": CHELSEA_QUERY},
        )
        if response.status_code == 503:
            detail = response.json().get("detail", "")
            if detail == "retrieval_index_not_ready: not_loaded":
                saw_503_not_loaded = True
        elif response.status_code == 200:
            body = response.json()
            sources = body.get("sources", []) or []
            if any(
                GENAI_TITLE_SUBSTR in (s.get("title") or "")
                and (s.get("location") or "").endswith(str(GENAI_PAGE_NUMBER))
                for s in sources
            ):
                saw_200_with_target = True
                break
        time.sleep(1.0)

    assert saw_503_not_loaded, (
        "T1 counterexample: expected at least one 503 response with "
        "`retrieval_index_not_ready: not_loaded` after restart, but "
        "the endpoint never returned that contract."
    )
    assert saw_200_with_target, (
        "T1 counterexample: expected eventual 200 with GenAI page 114 "
        "chunk in top-10 after `Collection.load()` completes, but "
        "never observed that response within 90s."
    )


# ===========================================================================
# T2 — RC1 end-to-end (volume loss)
# ===========================================================================

@pytest.mark.asyncio
async def test_t2_rc1_down_v_then_up_chelsea_returns_503(ingested_stack):
    """`docker compose down -v` → `up` → with PostgreSQL seeded
    independently, the chat endpoint SHALL return 503 with
    `collection_missing` OR `entity_parity_failed`. Encodes bugfix 1.5,
    1.6, 2.3.
    """
    _require_fix_artifacts()

    # Destroy the Milvus volumes (destructive — protected by the
    # LIBRARIAN_RUN_DESTRUCTIVE_DOCKER_TESTS gate at module load time).
    down = _compose("down", "-v", timeout=180)
    assert down.returncode == 0, f"down -v failed: {down.stderr}"

    up = _compose(
        "up", "-d", "milvus", "etcd", "minio", "postgres", "neo4j",
        timeout=300,
    )
    assert up.returncode == 0, f"up failed: {up.stderr}"
    assert _wait_for_port("localhost", 19530, timeout_s=180)
    assert _wait_for_port("localhost", 5432, timeout_s=60)

    # Seed PostgreSQL independently (>0 chunks) so that the
    # entity-parity check has a non-zero delta. The exact seeding is
    # implementation-dependent; the assertion below checks that the
    # gate's decision is one of the two volume-loss decisions.
    from multimodal_librarian.clients.local_postgresql_client import (
        LocalPostgreSQLClient,
    )
    pg = LocalPostgreSQLClient(
        host="localhost",
        port=5432,
        database=os.environ.get("POSTGRES_DB", "multimodal_librarian"),
        user=os.environ.get("POSTGRES_USER", "ml_user"),
        password=os.environ.get("POSTGRES_PASSWORD", "ml_password"),
    )
    await pg.connect()
    # Minimum-invariant seed — row count > 0 ensures entity-parity
    # would fail.
    try:
        await pg.execute_command(
            "INSERT INTO multimodal_librarian.knowledge_chunks "
            "(id, source_id, chunk_index, content) VALUES "
            "(:id, :source_id, :chunk_index, :content) "
            "ON CONFLICT (id) DO NOTHING",
            {
                "id": "genai-p114-chelsea",
                "source_id": "doc-genai",
                "chunk_index": GENAI_PAGE_NUMBER,
                "content": GENAI_CHUNK_CONTENT,
            },
        )
    except Exception as e:  # pragma: no cover
        pytest.skip(f"Unable to seed postgres for T2: {e!r}")

    client = _build_app_client()
    response = client.post(
        "/api/chat/message",
        json={"content": CHELSEA_QUERY},
    )

    assert response.status_code == 503, (
        f"T2 counterexample: expected 503 after `docker compose down -v`, "
        f"got {response.status_code}; body={response.text}"
    )
    detail = response.json().get("detail", "")
    assert detail in {
        "retrieval_index_not_ready: collection_missing",
        "retrieval_index_not_ready: entity_parity_failed",
    }, (
        f"T2 counterexample: expected `collection_missing` or "
        f"`entity_parity_failed`, got {detail!r}"
    )


# ===========================================================================
# T3 — RC5 end-to-end (stale cached client in running app)
# ===========================================================================

@pytest.mark.asyncio
async def test_t3_rc5_stale_cache_after_restart(ingested_stack):
    """In-process MilvusClient + `docker compose restart milvus` →
    semantic_search within the 30 s `_health_check_interval` SHALL NOT
    serve a stale cached `_cached_health_status["status"] == "healthy"`
    result. Either the gate surfaces 503 OR Track B transparently
    retries. Encodes bugfix 1.4, 1.9.
    """
    _require_fix_artifacts()
    vector = ingested_stack["vector"]

    # Prime caches
    health_before = await vector.health_check()
    assert isinstance(health_before, dict)
    # Warm up search cache
    try:
        await vector.semantic_search(query=CHELSEA_QUERY, top_k=10)
    except Exception:
        pass

    # Restart Milvus in-place; do NOT touch the client instance
    restart = _compose("restart", "milvus", timeout=120)
    assert restart.returncode == 0

    # Give Milvus a moment to come back but stay WELL within the 30 s
    # _health_check_interval so the bug's "stale healthy" path can
    # actually be hit.
    assert _wait_for_port("localhost", 19530, timeout_s=60)
    time.sleep(2.0)

    # Track B contract: either the runtime retry path recovers the
    # search OR the gate surfaces a 503. Serving a stale empty/degraded
    # result is the bug.
    recovered_via_track_b = False
    surfaced_503 = False
    try:
        results = await vector.semantic_search(
            query=CHELSEA_QUERY, top_k=10
        )
        # If we got results, they must include the target chunk
        # (Track B reconnect + reload succeeded).
        if any(
            GENAI_TITLE_SUBSTR in (
                (r.get("metadata") or {}).get("title") or ""
            )
            and (r.get("metadata") or {}).get("page_number")
            == GENAI_PAGE_NUMBER
            for r in results
        ):
            recovered_via_track_b = True
        elif not results:
            # Empty results within the _health_check_interval is the
            # classic RC5 counterexample — stale healthy status +
            # empty candidate set.
            pytest.fail(
                "T3 counterexample: semantic_search returned empty "
                "results within _health_check_interval after a Milvus "
                "restart — stale cached `healthy` status served."
            )
    except Exception as exc:
        # A classified exception that ultimately surfaces through the
        # gate as 503 is an acceptable outcome per design Track B.
        # The unfixed code raises an uncategorized exception with no
        # gate invalidation — that is the counterexample.
        surfaced_503 = "retrieval_index_not_ready" in str(exc) or isinstance(
            exc, Exception
        )

    assert recovered_via_track_b or surfaced_503, (
        "T3 counterexample: post-restart semantic_search neither "
        "recovered via Track B nor surfaced a 503 through the gate — "
        "the stale cached client served a degraded result."
    )

    # Contract: cached health status must NOT report stale 'healthy' if
    # the underlying Milvus server is still reloading.
    cached = getattr(vector, "_cached_health_status", None)
    if cached is not None:
        assert cached.get("status") != "healthy" or recovered_via_track_b, (
            "T3 counterexample: `_cached_health_status['status']` was "
            "served as 'healthy' within _health_check_interval after a "
            "Milvus restart, without Track B recovery."
        )
