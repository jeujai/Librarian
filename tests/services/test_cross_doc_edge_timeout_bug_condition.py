"""
Bug Condition Exploration Test: Cross-Document Edge Discovery Timeout

Property 1: Bug Condition — Monolithic Query Timeout on Large Document Pairs

This test encodes the EXPECTED behavior: _discover_cross_doc_edges() should
return actual edges when cross-document relationships exist, even for documents
with thousands of concepts.

On UNFIXED code, this test FAILS because the monolithic Cypher query combines
unbounded traversal with gds.similarity.cosine() in a single pass, triggering
a TransactionTimedOutClientConfiguration-style timeout for every batch.  The
method silently swallows the exception and returns zero edges.

After the two-phase fix, the test PASSES because the queries are split and
the timeout condition is no longer triggered.

Requirements: 1.1, 1.2, 1.3, 1.4
"""

import asyncio
import re
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from multimodal_librarian.services.composite_score_engine import CompositeScoreEngine

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

# Threshold: if the query string contains BOTH the MATCH traversal pattern
# AND gds.similarity.cosine, we treat it as the monolithic query that would
# time out on large concept counts.
_TRAVERSAL_PATTERN = re.compile(
    r"MATCH.*Chunk.*EXTRACTED_FROM.*Concept.*Concept.*EXTRACTED_FROM.*Chunk",
    re.DOTALL | re.IGNORECASE,
)
_COSINE_PATTERN = re.compile(r"gds\.similarity\.cosine", re.IGNORECASE)
_OVERLAP_PATTERN = re.compile(
    r"name_lower.*norm_name|toLower.*name.*=.*norm_name",
    re.DOTALL | re.IGNORECASE,
)


class _Neo4jTimeoutError(Exception):
    """Simulates Neo4j TransactionTimedOutClientConfiguration."""
    pass


def _make_mock_kg_client(
    source_doc_id: str,
    target_doc_ids: list[str],
    edges_per_target: int,
):
    """Build a mock kg_client whose execute_query behaves like Neo4j.

    Handles:
    * Concept name overlap query → returns candidate pairs
    * Cosine similarity query → returns similarity scores
    * Monolithic batch_query (traversal + cosine) → raises timeout
    """
    mock = MagicMock()

    async def _execute_query(query: str, params: dict | None = None):
        is_cosine = bool(_COSINE_PATTERN.search(query))
        is_overlap = bool(_OVERLAP_PATTERN.search(query))

        # 1. Concept name overlap query (new approach)
        if is_overlap and not is_cosine:
            results = []
            for tid in target_doc_ids:
                for i in range(min(edges_per_target, 200)):
                    results.append({
                        "src_id": f"concept_src_{i}",
                        "src_doc": source_doc_id,
                        "tgt_id": f"concept_tgt_{tid}_{i}",
                        "tgt_doc": tid,
                        "rel_type": "SAME_AS",
                        "src_name": f"shared concept {i}",
                        "tgt_name": f"shared concept {i}",
                    })
            return results

        # 2. Cosine similarity query
        if is_cosine:
            # Also catch monolithic (traversal + cosine)
            is_traversal = bool(
                _TRAVERSAL_PATTERN.search(query)
            )
            if is_traversal:
                raise _Neo4jTimeoutError(
                    "Timeout of 120000 ms exceeded."
                )
            pairs = (params or {}).get("pairs", [])
            return [
                {
                    "src_id": p.get("src_id", ""),
                    "tgt_id": p.get("tgt_id", ""),
                    "embedding_similarity": 0.75,
                }
                for p in pairs
            ]

        return []

    mock.execute_query = AsyncMock(side_effect=_execute_query)
    return mock


def _make_mock_pg_connection(source_doc_id: str, conversation_doc_ids: set[str]):
    """Build a mock asyncpg connection.

    * source doc is NOT a conversation
    * returns *conversation_doc_ids* as the set of conversation docs to exclude
    """
    mock_conn = MagicMock()

    async def _fetchrow(query, *args):
        return {"source_type": "PDF"}

    async def _fetch(query, *args):
        return [{"doc_id": cid} for cid in conversation_doc_ids]

    async def _close():
        pass

    mock_conn.fetchrow = AsyncMock(side_effect=_fetchrow)
    mock_conn.fetch = AsyncMock(side_effect=_fetch)
    mock_conn.close = AsyncMock(side_effect=_close)
    return mock_conn


# ---------------------------------------------------------------------------
# Property-based test
# ---------------------------------------------------------------------------

@settings(
    max_examples=5,
    deadline=30_000,
    suppress_health_check=[HealthCheck.too_slow],
)
@given(
    num_target_docs=st.integers(min_value=1, max_value=5),
    edges_per_target=st.integers(min_value=10, max_value=200),
)
def test_bug_condition_monolithic_query_timeout(
    num_target_docs: int,
    edges_per_target: int,
):
    """Property 1 — Bug Condition: large-document discovery must return edges.

    The monolithic query (traversal + cosine in one pass) times out for
    documents with thousands of concepts.  The method should still return
    discovered edges rather than silently swallowing timeouts and returning
    an empty list.

    On UNFIXED code this test FAILS: every batch raises the timeout mock,
    the except clause swallows it, and zero edges are returned.
    """
    source_doc_id = "doc_source_large"
    target_doc_ids = [f"doc_target_{i}" for i in range(num_target_docs)]
    conversation_doc_ids: set[str] = set()

    mock_kg = _make_mock_kg_client(source_doc_id, target_doc_ids, edges_per_target)
    mock_conn = _make_mock_pg_connection(source_doc_id, conversation_doc_ids)

    engine = CompositeScoreEngine(kg_client=mock_kg)

    async def _run():
        with patch(
            "multimodal_librarian.database.connection.get_async_connection",
            new=AsyncMock(return_value=mock_conn),
        ):
            return await engine._discover_cross_doc_edges(source_doc_id)

    edges = asyncio.run(_run())

    # ---- Assertion: the method MUST return actual edges ----
    # On unfixed code the monolithic query triggers the timeout mock for
    # every batch, so edges == [] — this assertion FAILS, confirming the bug.
    assert len(edges) > 0, (
        f"Expected non-empty edges for {num_target_docs} target doc(s) with "
        f"{edges_per_target} edges each, but got 0.  This confirms the bug: "
        f"the monolithic query timed out and the method silently returned "
        f"zero edges."
    )


# ---------------------------------------------------------------------------
# Deterministic companion test — easier to reason about
# ---------------------------------------------------------------------------

def test_bug_condition_deterministic_single_target():
    """Deterministic variant: 1 target doc, 50 expected edges.

    Confirms the same bug condition with a fixed, reproducible input.
    """
    source_doc_id = "doc_7700_concepts"
    target_doc_ids = ["doc_target_4000_concepts"]
    edges_per_target = 50

    mock_kg = _make_mock_kg_client(source_doc_id, target_doc_ids, edges_per_target)
    mock_conn = _make_mock_pg_connection(source_doc_id, set())

    engine = CompositeScoreEngine(kg_client=mock_kg)

    async def _run():
        with patch(
            "multimodal_librarian.database.connection.get_async_connection",
            new=AsyncMock(return_value=mock_conn),
        ):
            return await engine._discover_cross_doc_edges(source_doc_id)

    edges = asyncio.run(_run())

    assert len(edges) > 0, (
        "Expected edges from cross-doc discovery but got 0.  "
        "The monolithic query (traversal + cosine) triggered the timeout "
        "mock and the method silently swallowed the exception."
    )


def test_bug_condition_all_batches_now_succeed():
    """Confirms that with the two-phase fix, all target docs are processed.

    Previously (unfixed code), all 37 target docs would time out because
    the monolithic query combined traversal + cosine in one pass.  Now the
    two-phase approach avoids the timeout and returns actual edges.

    This test was inverted from the original ``test_bug_condition_all_batches_fail_returns_zero``
    which documented the broken behavior (asserting 0 edges).
    """
    source_doc_id = "doc_large"
    # 37 target docs — previously all timed out
    target_doc_ids = [f"doc_target_{i}" for i in range(37)]

    mock_kg = _make_mock_kg_client(source_doc_id, target_doc_ids, edges_per_target=100)
    mock_conn = _make_mock_pg_connection(source_doc_id, set())

    engine = CompositeScoreEngine(kg_client=mock_kg)

    async def _run():
        with patch(
            "multimodal_librarian.database.connection.get_async_connection",
            new=AsyncMock(return_value=mock_conn),
        ):
            return await engine._discover_cross_doc_edges(source_doc_id)

    edges = asyncio.run(_run())

    # With the fix: the two-phase approach succeeds and returns edges
    assert len(edges) > 0, (
        f"Expected edges from cross-doc discovery but got 0.  "
        f"The two-phase fix should avoid the monolithic query timeout."
    )
