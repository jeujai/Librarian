"""
Bug Condition Exploration Test: Garbage Concepts Pass Through Edge Discovery

Property 1: Bug Condition — Garbage concept names and NULL concept_type pairs
should be EXCLUDED from cross-document edge discovery candidates.

This test encodes the EXPECTED (correct) behavior. On UNFIXED code it MUST FAIL,
confirming that garbage concepts currently pass through unfiltered. After the fix
is applied, this same test will PASS, confirming the bug is resolved.

Garbage categories tested:
- PDF artifact characters: ?, +, = adjacent to word boundaries
- Hyphenation breaks: "sec- tion", "includ- ing"
- Generic filler phrases: "less than", "more than", "such as", etc.
- Table/figure references: "Table 15.2", "Figure 3"
- Time expressions: "10 years", "30 days"
- Stage/phase labels: "stage 2", "phase 3"
- Citations: "et al.", "et al"
- NULL concept_type pairs: both concepts lack domain-specific type

Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 1.6
"""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

from hypothesis import HealthCheck, given, note, settings
from hypothesis import strategies as st

from multimodal_librarian.services.composite_score_engine import CompositeScoreEngine

# -------------------------------------------------------------------
# Constants: garbage concept name examples by category
# -------------------------------------------------------------------

PDF_ARTIFACT_NAMES = [
    "? Weight", "n +", "p =", "+ +", "= 0",
    "? value", "p + q",
]

HYPHENATION_BREAK_NAMES = [
    "sec- tion", "includ- ing", "treat- ment",
    "infor- mation", "devel- opment",
]

GENERIC_PHRASE_NAMES = [
    "less than", "more than", "more than two",
    "information about", "such as", "as well",
    "due to", "based on", "according to",
    "in order", "at least", "up to",
    "each of", "one of",
]

TABLE_REF_NAMES = [
    "Table 15.2", "Table 3", "Figure 3",
    "Fig 12", "figure 7",
]

TIME_EXPRESSION_NAMES = [
    "10 years", "30 days", "6 months",
    "2 weeks", "24 hours", "15 minutes",
]

STAGE_LABEL_NAMES = [
    "stage 2", "phase 3", "step 1",
    "grade 4", "level 5", "type 2",
]

CITATION_NAMES = [
    "et al.", "et al",
]

ALL_GARBAGE_NAMES = (
    PDF_ARTIFACT_NAMES
    + HYPHENATION_BREAK_NAMES
    + GENERIC_PHRASE_NAMES
    + TABLE_REF_NAMES
    + TIME_EXPRESSION_NAMES
    + STAGE_LABEL_NAMES
    + CITATION_NAMES
)


# -------------------------------------------------------------------
# Hypothesis strategies for garbage concept names
# -------------------------------------------------------------------

pdf_artifact_st = st.one_of(
    # "? Word" pattern
    st.builds(
        lambda c, w: f"{c} {w}",
        st.sampled_from(list("?+=")),
        st.text(
            alphabet=st.characters(whitelist_categories=("L",)),
            min_size=2, max_size=10,
        ),
    ),
    # "word ?" pattern
    st.builds(
        lambda w, c: f"{w} {c}",
        st.text(
            alphabet=st.characters(whitelist_categories=("L",)),
            min_size=1, max_size=8,
        ),
        st.sampled_from(list("?+=")),
    ),
    # "x + y" pattern
    st.builds(
        lambda a, c, b: f"{a} {c} {b}",
        st.text(
            alphabet=st.characters(whitelist_categories=("L",)),
            min_size=1, max_size=5,
        ),
        st.sampled_from(list("?+=")),
        st.text(
            alphabet=st.characters(whitelist_categories=("L",)),
            min_size=1, max_size=5,
        ),
    ),
)

hyphenation_st = st.builds(
    lambda a, b: f"{a}- {b}",
    st.text(
        alphabet=st.characters(whitelist_categories=("L",)),
        min_size=2, max_size=8,
    ),
    st.text(
        alphabet=st.characters(whitelist_categories=("L",)),
        min_size=2, max_size=8,
    ),
)

generic_phrase_st = st.sampled_from(GENERIC_PHRASE_NAMES)

table_ref_st = st.builds(
    lambda prefix, num: f"{prefix} {num}",
    st.sampled_from(["Table", "table", "Figure", "figure", "Fig", "fig"]),
    st.integers(min_value=1, max_value=99).map(str),
)

time_expr_st = st.builds(
    lambda n, unit: f"{n} {unit}",
    st.integers(min_value=1, max_value=100).map(str),
    st.sampled_from([
        "years", "year", "days", "day", "months", "month",
        "weeks", "week", "hours", "hour", "minutes", "minute",
    ]),
)

stage_label_st = st.builds(
    lambda prefix, n: f"{prefix} {n}",
    st.sampled_from([
        "stage", "Stage", "phase", "Phase", "step", "Step",
        "grade", "Grade", "level", "Level", "type", "Type",
    ]),
    st.integers(min_value=1, max_value=20).map(str),
)

citation_st = st.sampled_from(["et al.", "et al"])

# Combined strategy: any garbage name
garbage_name_st = st.one_of(
    pdf_artifact_st,
    hyphenation_st,
    generic_phrase_st,
    table_ref_st,
    time_expr_st,
    stage_label_st,
    citation_st,
)


# -------------------------------------------------------------------
# Mock helpers (matching existing test patterns)
# -------------------------------------------------------------------

def _make_overlap_record(
    src_name, tgt_name, src_doc="doc_src", tgt_doc="doc_tgt",
    src_id=None, tgt_id=None,
    src_type=None, tgt_type=None,
):
    """Build a record matching the overlap query RETURN clause."""
    rec = {
        "src_id": src_id or f"concept_{src_name.replace(' ', '_')}",
        "tgt_id": tgt_id or f"concept_{tgt_name.replace(' ', '_')}_tgt",
        "src_name": src_name,
        "tgt_name": tgt_name,
        "tgt_doc": tgt_doc,
        "src_doc": src_doc,
        "rel_type": "SAME_AS",
    }
    if src_type is not None:
        rec["src_type"] = src_type
    if tgt_type is not None:
        rec["tgt_type"] = tgt_type
    return rec


def _make_mock_kg(overlap_records):
    """Mock kg_client returning overlap_records for the first query
    and empty phase-2 results for subsequent queries."""
    mock = MagicMock()
    call_count = {"i": 0}

    async def _execute_query(query, params=None):
        idx = call_count["i"]
        call_count["i"] += 1
        if idx == 0:
            return overlap_records
        # Phase 2 cosine similarity — return 1.0 for all pairs
        # (garbage concepts with identical names get perfect similarity)
        pairs = params.get("pairs", []) if params else []
        return [
            {
                "src_id": p["src_id"],
                "tgt_id": p["tgt_id"],
                "embedding_similarity": 1.0,
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


def _get_candidate_src_names(candidates, overlap_records):
    """Map candidate src_ids back to concept names from the overlap records."""
    id_to_name = {}
    for rec in overlap_records:
        id_to_name[rec["src_id"]] = rec["src_name"]
        id_to_name[rec["tgt_id"]] = rec["tgt_name"]
    names = set()
    for c in candidates:
        if c["src_id"] in id_to_name:
            names.add(id_to_name[c["src_id"]])
        if c["tgt_id"] in id_to_name:
            names.add(id_to_name[c["tgt_id"]])
    return names


# ===================================================================
# Property 1a: PDF artifact names should be excluded
# ===================================================================

@settings(
    max_examples=30,
    deadline=30_000,
    suppress_health_check=[HealthCheck.too_slow],
)
@given(garbage_name=pdf_artifact_st)
def test_pdf_artifact_names_excluded(garbage_name):
    """Concept names containing PDF artifact characters (?, +, =)
    adjacent to word boundaries should be excluded from candidates.

    On UNFIXED code this test FAILS — confirming the bug exists.
    Requirement: 1.1
    """
    note(f"Testing PDF artifact name: {garbage_name!r}")

    records = [
        _make_overlap_record(
            src_name=garbage_name,
            tgt_name=garbage_name,
        ),
    ]
    mock_kg = _make_mock_kg(records)
    mock_conn = _make_mock_pg()
    engine = CompositeScoreEngine(kg_client=mock_kg)

    candidates = _run_discover(engine, "doc_src", mock_conn)

    # Expected: garbage concept excluded from candidates
    assert len(candidates) == 0, (
        f"PDF artifact concept {garbage_name!r} was NOT filtered — "
        f"got {len(candidates)} candidates instead of 0"
    )


# ===================================================================
# Property 1b: Hyphenation break names should be excluded
# ===================================================================

@settings(
    max_examples=30,
    deadline=30_000,
    suppress_health_check=[HealthCheck.too_slow],
)
@given(garbage_name=hyphenation_st)
def test_hyphenation_break_names_excluded(garbage_name):
    """Concept names with hyphenation breaks (e.g. "sec- tion")
    should be excluded from candidates.

    On UNFIXED code this test FAILS — confirming the bug exists.
    Requirement: 1.2
    """
    note(f"Testing hyphenation break name: {garbage_name!r}")

    records = [
        _make_overlap_record(
            src_name=garbage_name,
            tgt_name=garbage_name,
        ),
    ]
    mock_kg = _make_mock_kg(records)
    mock_conn = _make_mock_pg()
    engine = CompositeScoreEngine(kg_client=mock_kg)

    candidates = _run_discover(engine, "doc_src", mock_conn)

    assert len(candidates) == 0, (
        f"Hyphenation break concept {garbage_name!r} was NOT filtered — "
        f"got {len(candidates)} candidates instead of 0"
    )


# ===================================================================
# Property 1c: Generic filler phrases should be excluded
# ===================================================================

@settings(
    max_examples=30,
    deadline=30_000,
    suppress_health_check=[HealthCheck.too_slow],
)
@given(garbage_name=generic_phrase_st)
def test_generic_phrase_names_excluded(garbage_name):
    """Generic non-domain phrases (e.g. "less than", "such as")
    should be excluded from candidates.

    On UNFIXED code this test FAILS — confirming the bug exists.
    Requirement: 1.3
    """
    note(f"Testing generic phrase name: {garbage_name!r}")

    records = [
        _make_overlap_record(
            src_name=garbage_name,
            tgt_name=garbage_name,
        ),
    ]
    mock_kg = _make_mock_kg(records)
    mock_conn = _make_mock_pg()
    engine = CompositeScoreEngine(kg_client=mock_kg)

    candidates = _run_discover(engine, "doc_src", mock_conn)

    assert len(candidates) == 0, (
        f"Generic phrase concept {garbage_name!r} was NOT filtered — "
        f"got {len(candidates)} candidates instead of 0"
    )


# ===================================================================
# Property 1d: Table/figure refs, time expressions, stage labels,
#              citations should be excluded
# ===================================================================

@settings(
    max_examples=30,
    deadline=30_000,
    suppress_health_check=[HealthCheck.too_slow],
)
@given(
    garbage_name=st.one_of(
        table_ref_st, time_expr_st, stage_label_st, citation_st,
    ),
)
def test_table_time_stage_citation_names_excluded(garbage_name):
    """Table references, time expressions, stage/phase labels, and
    citations should be excluded from candidates.

    On UNFIXED code this test FAILS — confirming the bug exists.
    Requirement: 1.4
    """
    note(f"Testing table/time/stage/citation name: {garbage_name!r}")

    records = [
        _make_overlap_record(
            src_name=garbage_name,
            tgt_name=garbage_name,
        ),
    ]
    mock_kg = _make_mock_kg(records)
    mock_conn = _make_mock_pg()
    engine = CompositeScoreEngine(kg_client=mock_kg)

    candidates = _run_discover(engine, "doc_src", mock_conn)

    assert len(candidates) == 0, (
        f"Garbage concept {garbage_name!r} was NOT filtered — "
        f"got {len(candidates)} candidates instead of 0"
    )


# ===================================================================
# Property 1e: Combined — any garbage name should be excluded
# ===================================================================

@settings(
    max_examples=50,
    deadline=30_000,
    suppress_health_check=[HealthCheck.too_slow],
)
@given(garbage_name=garbage_name_st)
def test_any_garbage_name_excluded(garbage_name):
    """Any garbage concept name (from any category) should be
    excluded from cross-document edge candidates.

    On UNFIXED code this test FAILS — confirming the bug exists.
    Requirements: 1.1, 1.2, 1.3, 1.4
    """
    records = [
        _make_overlap_record(
            src_name=garbage_name,
            tgt_name=garbage_name,
        ),
    ]
    mock_kg = _make_mock_kg(records)
    mock_conn = _make_mock_pg()
    engine = CompositeScoreEngine(kg_client=mock_kg)

    candidates = _run_discover(engine, "doc_src", mock_conn)

    assert len(candidates) == 0, (
        f"Garbage concept {garbage_name!r} was NOT filtered — "
        f"got {len(candidates)} candidates instead of 0"
    )


# ===================================================================
# Property 1f: NULL concept_type pairs should be excluded
# ===================================================================

def test_null_type_pair_excluded():
    """When both concepts in a matched pair have NULL concept_type,
    the pair should be excluded from candidates even if the name
    looks valid.

    On UNFIXED code this test FAILS — the query doesn't even return
    concept_type, so there's no type gate at all.
    Requirement: 1.5
    """
    # Use a name that looks valid but both concepts have NULL type
    records = [
        _make_overlap_record(
            src_name="some concept",
            tgt_name="some concept",
        ),
    ]
    mock_kg = _make_mock_kg(records)
    mock_conn = _make_mock_pg()
    engine = CompositeScoreEngine(kg_client=mock_kg)

    candidates = _run_discover(engine, "doc_src", mock_conn)

    # On unfixed code, concept_type is not returned by the query
    # and there is no type gate, so this pair passes through.
    # Expected behavior: pairs where both concepts have NULL type
    # should be excluded.
    assert len(candidates) == 0, (
        f"NULL concept_type pair was NOT filtered — "
        f"got {len(candidates)} candidates. "
        f"Both concepts have NULL type but pair was included."
    )


# ===================================================================
# Property 1g: Mixed garbage + legitimate — only garbage excluded
# ===================================================================

def test_mixed_garbage_and_legitimate_concepts():
    """When query results contain both garbage and legitimate concepts,
    only garbage concepts should be excluded. Legitimate concepts
    should remain in candidates.

    On UNFIXED code this test FAILS — garbage concepts pass through.
    Requirements: 1.1, 1.3, 1.6
    """
    records = [
        # Garbage: PDF artifact
        _make_overlap_record(
            src_name="? Weight",
            tgt_name="? Weight",
            src_id="garbage_1_src",
            tgt_id="garbage_1_tgt",
        ),
        # Garbage: generic phrase
        _make_overlap_record(
            src_name="less than",
            tgt_name="less than",
            src_id="garbage_2_src",
            tgt_id="garbage_2_tgt",
        ),
        # Garbage: hyphenation break
        _make_overlap_record(
            src_name="sec- tion",
            tgt_name="sec- tion",
            src_id="garbage_3_src",
            tgt_id="garbage_3_tgt",
        ),
        # Legitimate: real domain concept
        _make_overlap_record(
            src_name="machine learning",
            tgt_name="machine learning",
            src_id="legit_1_src",
            tgt_id="legit_1_tgt",
            src_type="TOPIC",
            tgt_type="TOPIC",
        ),
    ]
    mock_kg = _make_mock_kg(records)
    mock_conn = _make_mock_pg()
    engine = CompositeScoreEngine(kg_client=mock_kg)

    candidates = _run_discover(engine, "doc_src", mock_conn)

    candidate_ids = {c["src_id"] for c in candidates}

    # Garbage concepts should NOT be in candidates
    assert "garbage_1_src" not in candidate_ids, (
        "PDF artifact '? Weight' was NOT filtered from candidates"
    )
    assert "garbage_2_src" not in candidate_ids, (
        "Generic phrase 'less than' was NOT filtered from candidates"
    )
    assert "garbage_3_src" not in candidate_ids, (
        "Hyphenation break 'sec- tion' was NOT filtered from candidates"
    )

    # Legitimate concept SHOULD be in candidates
    assert "legit_1_src" in candidate_ids, (
        "Legitimate concept 'machine learning' was incorrectly filtered"
    )


# ===================================================================
# Property 1h: Deterministic examples — known garbage from bug report
# ===================================================================

def test_known_garbage_from_bug_report():
    """Specific garbage concepts mentioned in the original bug report
    should be excluded from candidates.

    On UNFIXED code this test FAILS — all garbage passes through.
    Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 1.6
    """
    known_garbage = [
        "? Weight",
        "sec- tion",
        "less than",
        "Table 15.2",
        "10 years",
        "stage 2",
        "et al.",
    ]

    for name in known_garbage:
        records = [
            _make_overlap_record(
                src_name=name,
                tgt_name=name,
                src_id=f"src_{name}",
                tgt_id=f"tgt_{name}",
            ),
        ]
        mock_kg = _make_mock_kg(records)
        mock_conn = _make_mock_pg()
        engine = CompositeScoreEngine(kg_client=mock_kg)

        candidates = _run_discover(engine, "doc_src", mock_conn)

        assert len(candidates) == 0, (
            f"Known garbage concept {name!r} from bug report was NOT "
            f"filtered — got {len(candidates)} candidates instead of 0"
        )
