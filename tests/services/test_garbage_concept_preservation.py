"""
Preservation Property Tests: Legitimate Domain Concepts Unchanged

Property 2: Preservation — Legitimate domain concepts with valid names and
at least one DOMAIN_CONCEPT_TYPES type MUST continue to pass through
cross-document edge discovery after the garbage concept fix is applied.

These tests are written BEFORE the fix and MUST PASS on UNFIXED code
(observation-first methodology). They capture the baseline behavior that
the fix must preserve.

Observed behaviors on UNFIXED code:
- Valid multi-token domain concepts (e.g., "machine learning" with type "TOPIC")
  pass through edge discovery
- UMLS-typed concepts (e.g., "Disease or Syndrome") pass through edge discovery
- Trusted NER-typed concepts (e.g., "ORG", "PERSON") pass through edge discovery
- Per-edge scoring formula produces identical results for qualifying edges
- Concept pairs where at least one has a DOMAIN_CONCEPT_TYPES type pass through

Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 3.6
"""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

from hypothesis import HealthCheck, given, note, settings
from hypothesis import strategies as st

from multimodal_librarian.services.composite_score_engine import CompositeScoreEngine

# -------------------------------------------------------------------
# Constants
# -------------------------------------------------------------------

DOMAIN_CONCEPT_TYPES = CompositeScoreEngine.DOMAIN_CONCEPT_TYPES

UMLS_TYPES = [
    "Disease or Syndrome", "Bacterium", "Virus",
    "Eukaryote", "Organic Chemical", "ORGANISM", "TREATMENT",
]

NER_TYPES_ALWAYS_TRUSTED = ["ORG", "PERSON"]

NER_TYPES_MULTI_TOKEN = [
    "GPE", "LOC", "FAC", "LAW", "WORK_OF_ART",
    "EVENT", "LANGUAGE", "TOPIC",
]

ALL_DOMAIN_TYPES = list(DOMAIN_CONCEPT_TYPES)


# -------------------------------------------------------------------
# Hypothesis strategies
# -------------------------------------------------------------------

# Strategy for a single alphabetic word (no garbage characters)
_alpha_word_st = st.text(
    alphabet=st.characters(whitelist_categories=("L",)),
    min_size=2,
    max_size=12,
).filter(lambda w: w.isalpha() and len(w) >= 2)

# Strategy for a legitimate multi-token concept name:
# 2-4 alphabetic words joined by spaces, no garbage patterns
legitimate_concept_name_st = st.lists(
    _alpha_word_st,
    min_size=2,
    max_size=4,
).map(lambda words: " ".join(words))

# Strategy for a domain concept type (at least one must be from DOMAIN_CONCEPT_TYPES)
domain_type_st = st.sampled_from(ALL_DOMAIN_TYPES)

# Strategy for UMLS types specifically
umls_type_st = st.sampled_from(UMLS_TYPES)

# Strategy for NER types that are always trusted
ner_trusted_st = st.sampled_from(NER_TYPES_ALWAYS_TRUSTED)

# Strategy for any concept type (including None for NULL)
any_type_st = st.one_of(
    st.sampled_from(ALL_DOMAIN_TYPES),
    st.none(),
    st.just("CODE_TERM"),
    st.just("UNKNOWN"),
)


# -------------------------------------------------------------------
# Mock helpers
# -------------------------------------------------------------------

def _make_overlap_record(
    src_name, tgt_name, src_doc="doc_src", tgt_doc="doc_tgt",
    src_id=None, tgt_id=None,
    src_type=None, tgt_type=None,
):
    """Build a record matching the overlap query RETURN clause.

    Includes src_type/tgt_type fields that will be present after
    the Cypher query is modified (task 3.2). On unfixed code these
    fields are simply ignored by the processing loop.
    """
    rec = {
        "src_id": src_id or f"concept_{src_name.replace(' ', '_')}_src",
        "tgt_id": tgt_id or f"concept_{tgt_name.replace(' ', '_')}_tgt",
        "src_name": src_name,
        "tgt_name": tgt_name,
        "tgt_doc": tgt_doc,
        "src_doc": src_doc,
        "rel_type": "SAME_AS",
    }
    # Include type fields (will be used after fix, ignored before)
    if src_type is not None:
        rec["src_type"] = src_type
    if tgt_type is not None:
        rec["tgt_type"] = tgt_type
    return rec


def _make_mock_kg(overlap_records):
    """Mock kg_client returning overlap_records for the overlap query
    and cosine similarity 0.85 for phase-2 queries."""
    mock = MagicMock()
    call_count = {"i": 0}

    async def _execute_query(query, params=None):
        idx = call_count["i"]
        call_count["i"] += 1
        if idx == 0:
            return overlap_records
        # Phase 2 cosine similarity
        pairs = params.get("pairs", []) if params else []
        return [
            {
                "src_id": p["src_id"],
                "tgt_id": p["tgt_id"],
                "embedding_similarity": 0.85,
            }
            for p in pairs
        ]

    mock.execute_query = AsyncMock(side_effect=_execute_query)
    return mock


def _make_mock_pg():
    """Mock asyncpg connection. Source doc is NOT a conversation."""
    mock_conn = MagicMock()

    async def _fetchrow(query, *args):
        return {"source_type": "PDF"}

    async def _fetch(query, *args):
        return []  # no conversation docs

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


# ===================================================================
# Property 2a: Valid multi-token domain concepts pass through
# ===================================================================

@settings(
    max_examples=30,
    deadline=30_000,
    suppress_health_check=[HealthCheck.too_slow],
)
@given(
    concept_name=legitimate_concept_name_st,
    concept_type=domain_type_st,
)
def test_legitimate_domain_concepts_pass_through(concept_name, concept_type):
    """Valid multi-token domain concept names (alphabetic words joined
    by spaces, no garbage patterns) with at least one DOMAIN_CONCEPT_TYPES
    type MUST pass through edge discovery.

    On UNFIXED code: PASSES (no filtering exists, everything passes through).
    After fix: MUST STILL PASS (the new filter should not touch these).

    Requirement: 3.1
    """
    note(f"Testing legitimate concept: {concept_name!r} type={concept_type}")

    records = [
        _make_overlap_record(
            src_name=concept_name,
            tgt_name=concept_name,
            src_type=concept_type,
            tgt_type=concept_type,
        ),
    ]
    mock_kg = _make_mock_kg(records)
    mock_conn = _make_mock_pg()
    engine = CompositeScoreEngine(kg_client=mock_kg)

    candidates = _run_discover(engine, "doc_src", mock_conn)

    assert len(candidates) == 1, (
        f"Legitimate domain concept {concept_name!r} (type={concept_type}) "
        f"was incorrectly filtered — got {len(candidates)} candidates, "
        f"expected 1"
    )


# ===================================================================
# Property 2b: UMLS-typed concepts pass through
# ===================================================================

@settings(
    max_examples=30,
    deadline=30_000,
    suppress_health_check=[HealthCheck.too_slow],
)
@given(
    concept_name=legitimate_concept_name_st,
    umls_type=umls_type_st,
)
def test_umls_typed_concepts_pass_through(concept_name, umls_type):
    """Concepts with UMLS semantic types (e.g., "Disease or Syndrome",
    "Organic Chemical") MUST pass through edge discovery regardless
    of token count.

    On UNFIXED code: PASSES (no filtering).
    After fix: MUST STILL PASS (UMLS types are in DOMAIN_CONCEPT_TYPES).

    Requirement: 3.2
    """
    note(f"Testing UMLS concept: {concept_name!r} type={umls_type}")

    records = [
        _make_overlap_record(
            src_name=concept_name,
            tgt_name=concept_name,
            src_type=umls_type,
            tgt_type=None,  # Only one side has a type
        ),
    ]
    mock_kg = _make_mock_kg(records)
    mock_conn = _make_mock_pg()
    engine = CompositeScoreEngine(kg_client=mock_kg)

    candidates = _run_discover(engine, "doc_src", mock_conn)

    assert len(candidates) == 1, (
        f"UMLS-typed concept {concept_name!r} (type={umls_type}) "
        f"was incorrectly filtered — got {len(candidates)} candidates, "
        f"expected 1"
    )


# ===================================================================
# Property 2c: Trusted NER-typed concepts pass through
# ===================================================================

@settings(
    max_examples=20,
    deadline=30_000,
    suppress_health_check=[HealthCheck.too_slow],
)
@given(
    concept_name=legitimate_concept_name_st,
    ner_type=ner_trusted_st,
)
def test_trusted_ner_typed_concepts_pass_through(concept_name, ner_type):
    """Concepts with trusted NER types (ORG, PERSON) MUST pass through
    edge discovery.

    On UNFIXED code: PASSES (no filtering).
    After fix: MUST STILL PASS (ORG/PERSON are in DOMAIN_CONCEPT_TYPES).

    Requirement: 3.3
    """
    note(f"Testing NER concept: {concept_name!r} type={ner_type}")

    records = [
        _make_overlap_record(
            src_name=concept_name,
            tgt_name=concept_name,
            src_type=ner_type,
            tgt_type=None,  # Only source has a type
        ),
    ]
    mock_kg = _make_mock_kg(records)
    mock_conn = _make_mock_pg()
    engine = CompositeScoreEngine(kg_client=mock_kg)

    candidates = _run_discover(engine, "doc_src", mock_conn)

    assert len(candidates) == 1, (
        f"NER-typed concept {concept_name!r} (type={ner_type}) "
        f"was incorrectly filtered — got {len(candidates)} candidates, "
        f"expected 1"
    )


# ===================================================================
# Property 2d: Type gate — at least one DOMAIN_CONCEPT_TYPES type
# ===================================================================

@settings(
    max_examples=30,
    deadline=30_000,
    suppress_health_check=[HealthCheck.too_slow],
)
@given(
    concept_name=legitimate_concept_name_st,
    domain_type=domain_type_st,
    other_type=st.one_of(st.none(), st.just("CODE_TERM"), st.just("UNKNOWN")),
    domain_on_src=st.booleans(),
)
def test_type_gate_allows_one_domain_type(
    concept_name, domain_type, other_type, domain_on_src,
):
    """Concept pairs where at least one concept has a type in
    DOMAIN_CONCEPT_TYPES MUST pass through the type gate.

    On UNFIXED code: PASSES (no type gate exists).
    After fix: MUST STILL PASS (type gate only blocks pairs where
    NEITHER concept has a domain type).

    Requirement: 3.1, 3.2, 3.3
    """
    if domain_on_src:
        src_type = domain_type
        tgt_type = other_type
    else:
        src_type = other_type
        tgt_type = domain_type

    note(
        f"Testing type gate: name={concept_name!r} "
        f"src_type={src_type} tgt_type={tgt_type}"
    )

    records = [
        _make_overlap_record(
            src_name=concept_name,
            tgt_name=concept_name,
            src_type=src_type,
            tgt_type=tgt_type,
        ),
    ]
    mock_kg = _make_mock_kg(records)
    mock_conn = _make_mock_pg()
    engine = CompositeScoreEngine(kg_client=mock_kg)

    candidates = _run_discover(engine, "doc_src", mock_conn)

    assert len(candidates) == 1, (
        f"Concept pair with at least one domain type was incorrectly "
        f"filtered — name={concept_name!r} src_type={src_type} "
        f"tgt_type={tgt_type}, got {len(candidates)} candidates, "
        f"expected 1"
    )


# ===================================================================
# Property 2e: Scoring formula identical for qualifying edges
# ===================================================================

@settings(
    max_examples=40,
    deadline=10_000,
    suppress_health_check=[HealthCheck.too_slow],
)
@given(
    emb_sim=st.floats(min_value=0.0, max_value=1.0),
    cn_weight=st.one_of(
        st.floats(min_value=0.0, max_value=1.0),
        st.none(),
    ),
)
def test_scoring_formula_identical_for_qualifying_edges(emb_sim, cn_weight):
    """The per-edge scoring formula (type_weight * 0.4 +
    embedding_similarity * 0.45 + cn_weight * 0.15) MUST produce
    identical results for edges that pass through the filter.

    On UNFIXED code: PASSES (scoring formula is unchanged).
    After fix: MUST STILL PASS (fix only adds filtering, not scoring changes).

    Requirement: 3.4
    """
    edge_dict = {
        "src_id": "concept_a",
        "src_doc": "doc_1",
        "tgt_id": "concept_b",
        "tgt_doc": "doc_2",
        "rel_type": "SAME_AS",
        "cn_weight": cn_weight,
        "embedding_similarity": emb_sim,
    }

    engine = CompositeScoreEngine(kg_client=MagicMock())
    result = engine._compute_edge_score(edge_dict)

    # SAME_AS forces cn_weight to 1.0
    expected_cn = 1.0
    tw = CompositeScoreEngine.TYPE_WEIGHTS["SAME_AS"]
    expected = max(0.0, min(
        tw * 0.4 + emb_sim * 0.45 + expected_cn * 0.15,
        1.0,
    ))

    assert abs(result.edge_score - expected) < 1e-9, (
        f"Score {result.edge_score} != expected {expected} "
        f"for emb_sim={emb_sim}, cn_weight={cn_weight}"
    )
    assert 0.0 <= result.edge_score <= 1.0


# ===================================================================
# Property 2f: Multiple legitimate concepts all preserved
# ===================================================================

def test_multiple_legitimate_concepts_all_preserved():
    """When multiple legitimate domain concepts are in the query
    results, ALL of them must pass through edge discovery.

    On UNFIXED code: PASSES (no filtering).
    After fix: MUST STILL PASS (none of these are garbage).

    Requirements: 3.1, 3.2, 3.3
    """
    legitimate_concepts = [
        ("machine learning", "TOPIC"),
        ("neural network", "TOPIC"),
        ("clinical trial", "Disease or Syndrome"),
        ("deep reinforcement learning", "TOPIC"),
        ("natural language processing", "TOPIC"),
        ("Google DeepMind", "ORG"),
        ("Alan Turing", "PERSON"),
        ("Escherichia coli", "Bacterium"),
    ]

    records = []
    for i, (name, ctype) in enumerate(legitimate_concepts):
        records.append(
            _make_overlap_record(
                src_name=name,
                tgt_name=name,
                src_id=f"src_{i}",
                tgt_id=f"tgt_{i}",
                src_type=ctype,
                tgt_type=ctype,
            )
        )

    mock_kg = _make_mock_kg(records)
    mock_conn = _make_mock_pg()
    engine = CompositeScoreEngine(kg_client=mock_kg)

    candidates = _run_discover(engine, "doc_src", mock_conn)

    assert len(candidates) == len(legitimate_concepts), (
        f"Expected {len(legitimate_concepts)} legitimate concepts "
        f"but got {len(candidates)} candidates. Some legitimate "
        f"concepts were incorrectly filtered."
    )

    # Verify all src_ids are present
    candidate_src_ids = {c["src_id"] for c in candidates}
    for i, (name, _) in enumerate(legitimate_concepts):
        assert f"src_{i}" in candidate_src_ids, (
            f"Legitimate concept {name!r} (src_{i}) was incorrectly "
            f"filtered from candidates"
        )


# ===================================================================
# Property 2g: Conversation document exclusion unchanged
# ===================================================================

@settings(
    max_examples=15,
    deadline=30_000,
    suppress_health_check=[HealthCheck.too_slow],
)
@given(
    concept_name=legitimate_concept_name_st,
    concept_type=domain_type_st,
)
def test_conversation_doc_exclusion_preserved(concept_name, concept_type):
    """Conversation documents MUST continue to be excluded from
    cross-document edge discovery, even for legitimate concepts.

    On UNFIXED code: PASSES (conversation exclusion already works).
    After fix: MUST STILL PASS (fix doesn't touch conversation logic).

    Requirement: 3.6
    """
    conv_doc = "conv_doc_1"

    # Record from a conversation document
    records = [
        _make_overlap_record(
            src_name=concept_name,
            tgt_name=concept_name,
            tgt_doc=conv_doc,
            src_type=concept_type,
            tgt_type=concept_type,
        ),
    ]

    mock_kg = _make_mock_kg(records)

    # Mark conv_doc_1 as a conversation document
    mock_conn = MagicMock()

    async def _fetchrow(query, *args):
        return {"source_type": "PDF"}

    async def _fetch(query, *args):
        return [{"doc_id": conv_doc}]

    mock_conn.fetchrow = AsyncMock(side_effect=_fetchrow)
    mock_conn.fetch = AsyncMock(side_effect=_fetch)
    mock_conn.close = AsyncMock()

    engine = CompositeScoreEngine(kg_client=mock_kg)
    candidates = _run_discover(engine, "doc_src", mock_conn)

    for c in candidates:
        assert c["tgt_doc"] != conv_doc, (
            f"Conversation document {conv_doc} appeared in results "
            f"for concept {concept_name!r}"
        )


# ===================================================================
# Property 2h: Both domain types — pair always passes
# ===================================================================

@settings(
    max_examples=20,
    deadline=30_000,
    suppress_health_check=[HealthCheck.too_slow],
)
@given(
    concept_name=legitimate_concept_name_st,
    src_type=domain_type_st,
    tgt_type=domain_type_st,
)
def test_both_domain_types_always_pass(concept_name, src_type, tgt_type):
    """When BOTH concepts have a DOMAIN_CONCEPT_TYPES type, the pair
    MUST always pass through.

    On UNFIXED code: PASSES (no type gate).
    After fix: MUST STILL PASS (both have domain types).

    Requirements: 3.1, 3.2, 3.3
    """
    records = [
        _make_overlap_record(
            src_name=concept_name,
            tgt_name=concept_name,
            src_type=src_type,
            tgt_type=tgt_type,
        ),
    ]
    mock_kg = _make_mock_kg(records)
    mock_conn = _make_mock_pg()
    engine = CompositeScoreEngine(kg_client=mock_kg)

    candidates = _run_discover(engine, "doc_src", mock_conn)

    assert len(candidates) == 1, (
        f"Concept pair with both domain types was incorrectly "
        f"filtered — name={concept_name!r} src_type={src_type} "
        f"tgt_type={tgt_type}, got {len(candidates)} candidates"
    )
