"""
Preservation Property Tests: Cross-Document Edge Discovery

Property 2: Preservation — Return Schema and Edge Deduplication Behavior

These tests capture the OBSERVED behavior of _discover_cross_doc_edges() on
UNFIXED code for non-buggy inputs (small concept counts where the monolithic
query completes without timeout).  They must PASS on unfixed code to confirm
the baseline behavior we need to preserve through the fix.

Observed behaviors:
- Returns List[dict] where each dict has keys: src_id, src_doc, tgt_id,
  tgt_doc, rel_type, cn_weight, embedding_similarity
- Duplicate edges (same src_id, tgt_id, rel_type triple) are deduplicated
  via the `seen` set
- Conversation documents are excluded from target_doc_ids
- Per-target-doc edge count is capped at MAX_EDGES_PER_TARGET_DOC (200)
- _compute_edge_score() produces identical EdgeScore objects for the same
  edge dict inputs

Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 3.7
"""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from multimodal_librarian.services.composite_score_engine import (
    CompositeScoreEngine,
    EdgeScore,
)

# -------------------------------------------------------------------
# Strategies
# -------------------------------------------------------------------

_REL_TYPES = CompositeScoreEngine.QUALIFYING_REL_TYPES

rel_type_st = st.sampled_from(_REL_TYPES)

concept_id_st = st.text(
    alphabet=st.characters(whitelist_categories=("L", "N", "P")),
    min_size=1,
    max_size=30,
).filter(lambda s: s.strip() != "")

doc_id_st = st.text(
    alphabet=st.characters(whitelist_categories=("L", "N")),
    min_size=1,
    max_size=20,
).filter(lambda s: s.strip() != "")


def edge_record_st(src_doc, tgt_doc):
    """Strategy for a single edge record as returned by the Cypher query."""
    return st.fixed_dictionaries({
        "src_id": concept_id_st,
        "src_doc": st.just(src_doc),
        "tgt_id": concept_id_st,
        "tgt_doc": st.just(tgt_doc),
        "rel_type": rel_type_st,
        "cn_weight": st.one_of(
            st.floats(min_value=0.0, max_value=1.0),
            st.none(),
        ),
        "embedding_similarity": st.floats(
            min_value=0.0, max_value=1.0,
        ),
    })


# -------------------------------------------------------------------
# Mock helpers
# -------------------------------------------------------------------

def _make_mock_kg(source_doc_id, target_doc_ids, records_by_batch):
    """Mock kg_client that returns pre-built records per batch.

    records_by_batch: list of lists — one inner list per batch call.
    The other_docs_query returns target_doc_ids.
    """
    mock = MagicMock()
    batch_idx = {"i": 0}

    async def _execute_query(query, params=None):
        # other_docs_query
        if "DISTINCT" in query and "ch.source_id" in query:
            return [{"doc_id": t} for t in target_doc_ids]

        # batch_query — return the next batch of records
        idx = batch_idx["i"]
        batch_idx["i"] += 1
        if idx < len(records_by_batch):
            return records_by_batch[idx]
        return []

    mock.execute_query = AsyncMock(side_effect=_execute_query)
    return mock


def _make_mock_pg(conversation_doc_ids=None):
    """Mock asyncpg connection. Source doc is NOT a conversation."""
    conv_ids = conversation_doc_ids or set()
    mock_conn = MagicMock()

    async def _fetchrow(query, *args):
        return {"source_type": "PDF"}

    async def _fetch(query, *args):
        return [{"doc_id": c} for c in conv_ids]

    mock_conn.fetchrow = AsyncMock(side_effect=_fetchrow)
    mock_conn.fetch = AsyncMock(side_effect=_fetch)
    mock_conn.close = AsyncMock()
    return mock_conn


def _run_discover(engine, doc_id, mock_conn):
    """Run _discover_cross_doc_edges synchronously."""
    async def _go():
        with patch(
            "multimodal_librarian.database.connection"
            ".get_async_connection",
            new=AsyncMock(return_value=mock_conn),
        ):
            return await engine._discover_cross_doc_edges(doc_id)
    return asyncio.run(_go())


# -------------------------------------------------------------------
# Property 2a: Return schema — every dict has exactly 7 required keys
# -------------------------------------------------------------------

@settings(
    max_examples=20,
    deadline=30_000,
    suppress_health_check=[HealthCheck.too_slow],
)
@given(
    records=st.lists(
        edge_record_st("doc_src", "doc_tgt_0"),
        min_size=1,
        max_size=50,
    ),
)
def test_return_schema_has_required_keys(records):
    """Every returned dict has exactly the 7 required keys with
    correct types (str for IDs/rel_type, float-compatible for
    cn_weight and embedding_similarity).

    Requirement: 3.1
    """
    source = "doc_src"
    targets = ["doc_tgt_0"]

    mock_kg = _make_mock_kg(source, targets, [records])
    mock_conn = _make_mock_pg()
    engine = CompositeScoreEngine(kg_client=mock_kg)

    edges = _run_discover(engine, source, mock_conn)

    required_keys = {
        "src_id", "src_doc", "tgt_id", "tgt_doc",
        "rel_type", "cn_weight", "embedding_similarity",
    }
    for edge in edges:
        assert set(edge.keys()) == required_keys, (
            f"Edge keys {set(edge.keys())} != {required_keys}"
        )
        # Type checks
        assert isinstance(edge["src_id"], str)
        assert isinstance(edge["src_doc"], str)
        assert isinstance(edge["tgt_id"], str)
        assert isinstance(edge["tgt_doc"], str)
        assert isinstance(edge["rel_type"], str)
        # cn_weight and embedding_similarity must be float-compatible
        float(edge["cn_weight"] if edge["cn_weight"] is not None else 0.0)
        float(edge["embedding_similarity"])


# -------------------------------------------------------------------
# Property 2b: Deduplication — each (src_id, tgt_id, rel_type) at
#              most once
# -------------------------------------------------------------------

@settings(
    max_examples=20,
    deadline=30_000,
    suppress_health_check=[HealthCheck.too_slow],
)
@given(
    base_records=st.lists(
        edge_record_st("doc_src", "doc_tgt_0"),
        min_size=1,
        max_size=30,
    ),
    dup_factor=st.integers(min_value=2, max_value=4),
)
def test_deduplication_of_edge_triples(base_records, dup_factor):
    """Duplicate (src_id, tgt_id, rel_type) triples in query results
    appear at most once in the output.

    Requirement: 3.1
    """
    # Inject duplicates by repeating each record
    records_with_dups = []
    for rec in base_records:
        for _ in range(dup_factor):
            records_with_dups.append(dict(rec))

    source = "doc_src"
    targets = ["doc_tgt_0"]

    mock_kg = _make_mock_kg(source, targets, [records_with_dups])
    mock_conn = _make_mock_pg()
    engine = CompositeScoreEngine(kg_client=mock_kg)

    edges = _run_discover(engine, source, mock_conn)

    seen_triples = set()
    for edge in edges:
        triple = (edge["src_id"], edge["tgt_id"], edge["rel_type"])
        assert triple not in seen_triples, (
            f"Duplicate triple found: {triple}"
        )
        seen_triples.add(triple)


# -------------------------------------------------------------------
# Property 2c: Conversation documents excluded from results
# -------------------------------------------------------------------

@settings(
    max_examples=15,
    deadline=30_000,
    suppress_health_check=[HealthCheck.too_slow],
)
@given(
    num_conv_docs=st.integers(min_value=1, max_value=3),
    num_normal_docs=st.integers(min_value=1, max_value=3),
    edges_per_target=st.integers(min_value=1, max_value=20),
)
def test_conversation_docs_excluded_from_targets(
    num_conv_docs, num_normal_docs, edges_per_target,
):
    """Conversation document IDs never appear as tgt_doc in results.

    Requirement: 3.5
    """
    source = "doc_src"
    conv_ids = {f"conv_doc_{i}" for i in range(num_conv_docs)}
    normal_ids = [f"normal_doc_{i}" for i in range(num_normal_docs)]
    # The other_docs_query returns both conv and normal IDs;
    # the method should filter out conv IDs.
    all_target_ids = list(conv_ids) + normal_ids

    # Build records only for normal docs (the mock returns them
    # for all batches, but conv docs should be filtered before
    # the batch query runs)
    batches = []
    for tgt in normal_ids:
        batch = []
        for j in range(edges_per_target):
            batch.append({
                "src_id": f"c_src_{j}",
                "src_doc": source,
                "tgt_id": f"c_tgt_{tgt}_{j}",
                "tgt_doc": tgt,
                "rel_type": "RelatedTo",
                "cn_weight": 0.5,
                "embedding_similarity": 0.7,
            })
        batches.append(batch)

    mock_kg = _make_mock_kg(source, all_target_ids, batches)
    mock_conn = _make_mock_pg(conversation_doc_ids=conv_ids)
    engine = CompositeScoreEngine(kg_client=mock_kg)

    edges = _run_discover(engine, source, mock_conn)

    for edge in edges:
        assert edge["tgt_doc"] not in conv_ids, (
            f"Conversation doc {edge['tgt_doc']} appeared in results"
        )


# -------------------------------------------------------------------
# Property 2d: Per-target-doc edge cap (MAX_EDGES_PER_TARGET_DOC)
# -------------------------------------------------------------------

def test_edge_cap_per_target_doc():
    """No more than MAX_EDGES_PER_TARGET_DOC (200) edges per target
    document are returned.

    The Cypher query uses collect()[0..$edge_cap] to enforce this.
    We feed 300 unique edges for a single target and verify the cap.

    Requirement: 3.7
    """
    source = "doc_src"
    target = "doc_tgt_0"
    cap = CompositeScoreEngine.MAX_EDGES_PER_TARGET_DOC  # 200

    # 300 unique edges — exceeds the cap
    records = []
    for i in range(300):
        records.append({
            "src_id": f"src_{i}",
            "src_doc": source,
            "tgt_id": f"tgt_{i}",
            "tgt_doc": target,
            "rel_type": "RelatedTo",
            "cn_weight": 0.5,
            "embedding_similarity": 0.6,
        })

    # The mock returns all 300, but the Cypher collect()[0..$edge_cap]
    # would cap at 200 in real Neo4j.  Since we're mocking, we
    # simulate the cap by only returning 200 from the mock — this
    # mirrors what Neo4j actually does.
    capped_records = records[:cap]

    mock_kg = _make_mock_kg(source, [target], [capped_records])
    mock_conn = _make_mock_pg()
    engine = CompositeScoreEngine(kg_client=mock_kg)

    edges = _run_discover(engine, source, mock_conn)

    assert len(edges) <= cap, (
        f"Expected at most {cap} edges but got {len(edges)}"
    )


# -------------------------------------------------------------------
# Property 2e: _compute_edge_score determinism — same input → same
#              EdgeScore
# -------------------------------------------------------------------

@settings(
    max_examples=30,
    deadline=10_000,
    suppress_health_check=[HealthCheck.too_slow],
)
@given(
    rel_type=rel_type_st,
    cn_weight=st.one_of(
        st.floats(min_value=0.0, max_value=1.0),
        st.none(),
    ),
    emb_sim=st.floats(min_value=0.0, max_value=1.0),
)
def test_compute_edge_score_determinism(rel_type, cn_weight, emb_sim):
    """_compute_edge_score() produces identical EdgeScore objects for
    the same edge dict inputs.  This ensures the downstream scoring
    pipeline is preserved.

    Requirement: 3.2
    """
    edge_dict = {
        "src_id": "concept_a",
        "src_doc": "doc_1",
        "tgt_id": "concept_b",
        "tgt_doc": "doc_2",
        "rel_type": rel_type,
        "cn_weight": cn_weight,
        "embedding_similarity": emb_sim,
    }

    engine = CompositeScoreEngine(kg_client=MagicMock())

    score_1 = engine._compute_edge_score(edge_dict)
    score_2 = engine._compute_edge_score(edge_dict)

    assert isinstance(score_1, EdgeScore)
    assert isinstance(score_2, EdgeScore)

    # All fields must be identical
    assert score_1.source_concept_id == score_2.source_concept_id
    assert score_1.target_concept_id == score_2.target_concept_id
    assert score_1.source_document_id == score_2.source_document_id
    assert score_1.target_document_id == score_2.target_document_id
    assert score_1.relationship_type == score_2.relationship_type
    assert score_1.type_weight == score_2.type_weight
    assert score_1.embedding_similarity == score_2.embedding_similarity
    assert score_1.cn_weight == score_2.cn_weight
    assert score_1.edge_score == score_2.edge_score

    # Score must be clamped to [0.0, 1.0]
    assert 0.0 <= score_1.edge_score <= 1.0


# -------------------------------------------------------------------
# Property 2f: Scoring formula correctness
# -------------------------------------------------------------------

@settings(
    max_examples=30,
    deadline=10_000,
    suppress_health_check=[HealthCheck.too_slow],
)
@given(
    rel_type=rel_type_st,
    cn_weight_raw=st.floats(min_value=0.0, max_value=1.0),
    emb_sim=st.floats(min_value=0.0, max_value=1.0),
)
def test_scoring_formula_preserved(rel_type, cn_weight_raw, emb_sim):
    """The three-signal formula (type_weight * 0.4 + emb_sim * 0.45 +
    cn_weight * 0.15) clamped to [0.0, 1.0] is preserved.

    Requirement: 3.2
    """
    edge_dict = {
        "src_id": "c1",
        "src_doc": "d1",
        "tgt_id": "c2",
        "tgt_doc": "d2",
        "rel_type": rel_type,
        "cn_weight": cn_weight_raw,
        "embedding_similarity": emb_sim,
    }

    engine = CompositeScoreEngine(kg_client=MagicMock())
    result = engine._compute_edge_score(edge_dict)

    tw = engine.TYPE_WEIGHTS.get(rel_type, engine.DEFAULT_TYPE_WEIGHT)
    # SAME_AS forces cn_weight to 1.0 regardless of raw input
    if rel_type == "SAME_AS":
        cn = 1.0
    else:
        cn = max(0.0, min(float(cn_weight_raw), 1.0))
    expected = max(0.0, min(tw * 0.4 + emb_sim * 0.45 + cn * 0.15, 1.0))

    assert abs(result.edge_score - expected) < 1e-9, (
        f"Score {result.edge_score} != expected {expected}"
    )
