"""
Tests for UMLSReasoningStrategy.

# Feature: medical-knowledge-finetuning
# Property 6: Relationship question references all path concepts
# Property 7: UMLS reasoning context contains relationship chain

Validates: Requirements 3.2, 3.3, 3.6
"""

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from multimodal_librarian.ml.umls_reasoning_strategy import (
    DEFAULT_ONE_HOP_TEMPLATES,
    DEFAULT_RELATIONSHIP_TYPES,
    ONE_HOP_QUESTION_TEMPLATES,
    TWO_HOP_QUESTION_TEMPLATES,
    _build_relationship_chain,
    _format_relationship,
    _generate_one_hop_question,
    _generate_two_hop_question,
)

# ---------------------------------------------------------------
# Hypothesis strategies for Property 6
# ---------------------------------------------------------------

# All relationship types that have dedicated templates, plus the
# default types to exercise the fallback path.
_KNOWN_RELATIONSHIP_TYPES = list(ONE_HOP_QUESTION_TEMPLATES.keys())

# Maximum template index across all one-hop template lists and the
# two-hop template list (used to cycle templates).
_MAX_ONE_HOP_TEMPLATE_INDEX = max(
    len(ts)
    for ts in list(ONE_HOP_QUESTION_TEMPLATES.values())
    + [DEFAULT_ONE_HOP_TEMPLATES]
)
_MAX_TWO_HOP_TEMPLATE_INDEX = len(TWO_HOP_QUESTION_TEMPLATES)
_MAX_TEMPLATE_INDEX = max(
    _MAX_ONE_HOP_TEMPLATE_INDEX, _MAX_TWO_HOP_TEMPLATE_INDEX
)


def _concept_name() -> st.SearchStrategy[str]:
    """Non-empty concept name with at least one non-whitespace char.

    Uses letters, digits, spaces, and hyphens — representative of
    real UMLS concept names like "Aspirin", "Type 2 Diabetes", or
    "ACE-inhibitor".
    """
    return st.text(
        alphabet=st.characters(
            whitelist_categories=("L", "N", "Zs", "Pd"),
            whitelist_characters="-' ",
        ),
        min_size=1,
        max_size=200,
    ).filter(lambda s: s.strip())


def _relationship_type() -> st.SearchStrategy[str]:
    """Known relationship type or arbitrary string (fallback path)."""
    return st.one_of(
        st.sampled_from(_KNOWN_RELATIONSHIP_TYPES),
        st.sampled_from(DEFAULT_RELATIONSHIP_TYPES),
        st.text(min_size=1, max_size=50).filter(
            lambda s: s.strip() and "_" not in s or s.replace("_", "")
        ),
    )


def _template_index() -> st.SearchStrategy[int]:
    """Non-negative template index (may exceed list length — wraps)."""
    return st.integers(min_value=0, max_value=_MAX_TEMPLATE_INDEX * 3)


# ---------------------------------------------------------------
# Property 6: Relationship question references all path concepts
# ---------------------------------------------------------------


@pytest.mark.pbt
@pytest.mark.unit
class TestRelationshipQuestionReferencesAllPathConcepts:
    """Property 6 — every concept in the path appears in the question.

    For a 1-hop path (A→B), both A and B must appear.
    For a 2-hop path (A→B→C), all three must appear.
    Case-insensitive matching is used because templates may alter
    casing through surrounding text but never omit a concept name.
    """

    # -----------------------------------------------------------
    # 1-hop: both concept_a and concept_b appear in the question
    # -----------------------------------------------------------

    @given(
        concept_a=_concept_name(),
        concept_b=_concept_name(),
        relationship=_relationship_type(),
        template_index=_template_index(),
    )
    @settings(max_examples=200)
    def test_one_hop_question_contains_concept_a(
        self,
        concept_a: str,
        concept_b: str,
        relationship: str,
        template_index: int,
    ) -> None:
        """concept_a always appears in a 1-hop question."""
        question = _generate_one_hop_question(
            concept_a=concept_a,
            concept_b=concept_b,
            relationship=relationship,
            template_index=template_index,
        )
        assert concept_a.lower() in question.lower(), (
            f"concept_a {concept_a!r} not found in question: "
            f"{question!r}"
        )

    @given(
        concept_a=_concept_name(),
        concept_b=_concept_name(),
        relationship=_relationship_type(),
        template_index=_template_index(),
    )
    @settings(max_examples=200)
    def test_one_hop_question_contains_concept_b(
        self,
        concept_a: str,
        concept_b: str,
        relationship: str,
        template_index: int,
    ) -> None:
        """concept_b always appears in a 1-hop question."""
        question = _generate_one_hop_question(
            concept_a=concept_a,
            concept_b=concept_b,
            relationship=relationship,
            template_index=template_index,
        )
        assert concept_b.lower() in question.lower(), (
            f"concept_b {concept_b!r} not found in question: "
            f"{question!r}"
        )

    @given(
        concept_a=_concept_name(),
        concept_b=_concept_name(),
        relationship=_relationship_type(),
        template_index=_template_index(),
    )
    @settings(max_examples=200)
    def test_one_hop_question_contains_both_concepts(
        self,
        concept_a: str,
        concept_b: str,
        relationship: str,
        template_index: int,
    ) -> None:
        """Both concept_a and concept_b appear in a 1-hop question."""
        question = _generate_one_hop_question(
            concept_a=concept_a,
            concept_b=concept_b,
            relationship=relationship,
            template_index=template_index,
        )
        q_lower = question.lower()
        assert concept_a.lower() in q_lower, (
            f"concept_a {concept_a!r} missing"
        )
        assert concept_b.lower() in q_lower, (
            f"concept_b {concept_b!r} missing"
        )

    # -----------------------------------------------------------
    # 1-hop: question is a non-empty string
    # -----------------------------------------------------------

    @given(
        concept_a=_concept_name(),
        concept_b=_concept_name(),
        relationship=_relationship_type(),
        template_index=_template_index(),
    )
    @settings(max_examples=100)
    def test_one_hop_question_is_non_empty(
        self,
        concept_a: str,
        concept_b: str,
        relationship: str,
        template_index: int,
    ) -> None:
        """1-hop question is always a non-empty string."""
        question = _generate_one_hop_question(
            concept_a=concept_a,
            concept_b=concept_b,
            relationship=relationship,
            template_index=template_index,
        )
        assert isinstance(question, str)
        assert len(question.strip()) > 0

    # -----------------------------------------------------------
    # 2-hop: all three concepts appear in the question
    # -----------------------------------------------------------

    @given(
        concept_a=_concept_name(),
        concept_b=_concept_name(),
        concept_c=_concept_name(),
        relationship_1=_relationship_type(),
        relationship_2=_relationship_type(),
        template_index=_template_index(),
    )
    @settings(max_examples=200)
    def test_two_hop_question_contains_concept_a(
        self,
        concept_a: str,
        concept_b: str,
        concept_c: str,
        relationship_1: str,
        relationship_2: str,
        template_index: int,
    ) -> None:
        """concept_a always appears in a 2-hop question."""
        question = _generate_two_hop_question(
            concept_a=concept_a,
            concept_b=concept_b,
            concept_c=concept_c,
            relationship_1=relationship_1,
            relationship_2=relationship_2,
            template_index=template_index,
        )
        assert concept_a.lower() in question.lower(), (
            f"concept_a {concept_a!r} not found in question: "
            f"{question!r}"
        )

    @given(
        concept_a=_concept_name(),
        concept_b=_concept_name(),
        concept_c=_concept_name(),
        relationship_1=_relationship_type(),
        relationship_2=_relationship_type(),
        template_index=_template_index(),
    )
    @settings(max_examples=200)
    def test_two_hop_question_contains_concept_b(
        self,
        concept_a: str,
        concept_b: str,
        concept_c: str,
        relationship_1: str,
        relationship_2: str,
        template_index: int,
    ) -> None:
        """concept_b always appears in a 2-hop question."""
        question = _generate_two_hop_question(
            concept_a=concept_a,
            concept_b=concept_b,
            concept_c=concept_c,
            relationship_1=relationship_1,
            relationship_2=relationship_2,
            template_index=template_index,
        )
        assert concept_b.lower() in question.lower(), (
            f"concept_b {concept_b!r} not found in question: "
            f"{question!r}"
        )

    @given(
        concept_a=_concept_name(),
        concept_b=_concept_name(),
        concept_c=_concept_name(),
        relationship_1=_relationship_type(),
        relationship_2=_relationship_type(),
        template_index=_template_index(),
    )
    @settings(max_examples=200)
    def test_two_hop_question_contains_concept_c(
        self,
        concept_a: str,
        concept_b: str,
        concept_c: str,
        relationship_1: str,
        relationship_2: str,
        template_index: int,
    ) -> None:
        """concept_c always appears in a 2-hop question."""
        question = _generate_two_hop_question(
            concept_a=concept_a,
            concept_b=concept_b,
            concept_c=concept_c,
            relationship_1=relationship_1,
            relationship_2=relationship_2,
            template_index=template_index,
        )
        assert concept_c.lower() in question.lower(), (
            f"concept_c {concept_c!r} not found in question: "
            f"{question!r}"
        )

    @given(
        concept_a=_concept_name(),
        concept_b=_concept_name(),
        concept_c=_concept_name(),
        relationship_1=_relationship_type(),
        relationship_2=_relationship_type(),
        template_index=_template_index(),
    )
    @settings(max_examples=200)
    def test_two_hop_question_contains_all_three_concepts(
        self,
        concept_a: str,
        concept_b: str,
        concept_c: str,
        relationship_1: str,
        relationship_2: str,
        template_index: int,
    ) -> None:
        """All three concepts appear in a 2-hop question."""
        question = _generate_two_hop_question(
            concept_a=concept_a,
            concept_b=concept_b,
            concept_c=concept_c,
            relationship_1=relationship_1,
            relationship_2=relationship_2,
            template_index=template_index,
        )
        q_lower = question.lower()
        assert concept_a.lower() in q_lower, (
            f"concept_a {concept_a!r} missing"
        )
        assert concept_b.lower() in q_lower, (
            f"concept_b {concept_b!r} missing"
        )
        assert concept_c.lower() in q_lower, (
            f"concept_c {concept_c!r} missing"
        )

    # -----------------------------------------------------------
    # 2-hop: question is a non-empty string
    # -----------------------------------------------------------

    @given(
        concept_a=_concept_name(),
        concept_b=_concept_name(),
        concept_c=_concept_name(),
        relationship_1=_relationship_type(),
        relationship_2=_relationship_type(),
        template_index=_template_index(),
    )
    @settings(max_examples=100)
    def test_two_hop_question_is_non_empty(
        self,
        concept_a: str,
        concept_b: str,
        concept_c: str,
        relationship_1: str,
        relationship_2: str,
        template_index: int,
    ) -> None:
        """2-hop question is always a non-empty string."""
        question = _generate_two_hop_question(
            concept_a=concept_a,
            concept_b=concept_b,
            concept_c=concept_c,
            relationship_1=relationship_1,
            relationship_2=relationship_2,
            template_index=template_index,
        )
        assert isinstance(question, str)
        assert len(question.strip()) > 0

    # -----------------------------------------------------------
    # 1-hop: known relationship types use dedicated templates
    # -----------------------------------------------------------

    @given(
        concept_a=_concept_name(),
        concept_b=_concept_name(),
        relationship=st.sampled_from(_KNOWN_RELATIONSHIP_TYPES),
        template_index=_template_index(),
    )
    @settings(max_examples=100)
    def test_one_hop_known_relationship_uses_dedicated_template(
        self,
        concept_a: str,
        concept_b: str,
        relationship: str,
        template_index: int,
    ) -> None:
        """Known relationship types produce questions from their
        dedicated template list, still containing both concepts."""
        question = _generate_one_hop_question(
            concept_a=concept_a,
            concept_b=concept_b,
            relationship=relationship,
            template_index=template_index,
        )
        q_lower = question.lower()
        assert concept_a.lower() in q_lower
        assert concept_b.lower() in q_lower

    # -----------------------------------------------------------
    # 1-hop: unknown relationship types fall back to defaults
    # -----------------------------------------------------------

    @given(
        concept_a=_concept_name(),
        concept_b=_concept_name(),
        template_index=_template_index(),
    )
    @settings(max_examples=100)
    def test_one_hop_unknown_relationship_uses_default_template(
        self,
        concept_a: str,
        concept_b: str,
        template_index: int,
    ) -> None:
        """Unknown relationship types fall back to default templates
        and still include both concept names."""
        unknown_rel = "UNKNOWN_RELATIONSHIP_XYZ"
        question = _generate_one_hop_question(
            concept_a=concept_a,
            concept_b=concept_b,
            relationship=unknown_rel,
            template_index=template_index,
        )
        q_lower = question.lower()
        assert concept_a.lower() in q_lower
        assert concept_b.lower() in q_lower


# ---------------------------------------------------------------
# Property 7: UMLS reasoning context contains relationship chain
# ---------------------------------------------------------------


@pytest.mark.pbt
@pytest.mark.unit
class TestUMLSReasoningContextContainsRelationshipChain:
    """Property 7 — the context field contains the relationship chain.

    For any InstructionTuningPair produced by UMLS_Reasoning_Strategy,
    the ``context`` field SHALL contain the relationship chain string
    (e.g. "Drug_A treats Disease_B") describing the traversed path.

    We test this at the function level by verifying that
    ``_build_relationship_chain`` produces a string that contains
    every concept name and every formatted relationship type, and
    that the chain is non-empty for valid paths.

    Validates: Requirements 3.6
    """

    # -----------------------------------------------------------
    # 1-hop: chain contains both concepts and the relationship
    # -----------------------------------------------------------

    @given(
        concept_a=_concept_name(),
        concept_b=_concept_name(),
        relationship=_relationship_type(),
    )
    @settings(max_examples=200)
    def test_one_hop_chain_contains_concept_a(
        self,
        concept_a: str,
        concept_b: str,
        relationship: str,
    ) -> None:
        """concept_a appears in the 1-hop relationship chain."""
        chain = _build_relationship_chain(
            concepts=[concept_a, concept_b],
            relationships=[relationship],
        )
        assert concept_a.lower() in chain.lower(), (
            f"concept_a {concept_a!r} not found in chain: {chain!r}"
        )

    @given(
        concept_a=_concept_name(),
        concept_b=_concept_name(),
        relationship=_relationship_type(),
    )
    @settings(max_examples=200)
    def test_one_hop_chain_contains_concept_b(
        self,
        concept_a: str,
        concept_b: str,
        relationship: str,
    ) -> None:
        """concept_b appears in the 1-hop relationship chain."""
        chain = _build_relationship_chain(
            concepts=[concept_a, concept_b],
            relationships=[relationship],
        )
        assert concept_b.lower() in chain.lower(), (
            f"concept_b {concept_b!r} not found in chain: {chain!r}"
        )

    @given(
        concept_a=_concept_name(),
        concept_b=_concept_name(),
        relationship=_relationship_type(),
    )
    @settings(max_examples=200)
    def test_one_hop_chain_contains_formatted_relationship(
        self,
        concept_a: str,
        concept_b: str,
        relationship: str,
    ) -> None:
        """The formatted relationship type appears in the 1-hop chain."""
        chain = _build_relationship_chain(
            concepts=[concept_a, concept_b],
            relationships=[relationship],
        )
        formatted_rel = _format_relationship(relationship)
        assert formatted_rel.lower() in chain.lower(), (
            f"formatted relationship {formatted_rel!r} not found in "
            f"chain: {chain!r}"
        )

    @given(
        concept_a=_concept_name(),
        concept_b=_concept_name(),
        relationship=_relationship_type(),
    )
    @settings(max_examples=200)
    def test_one_hop_chain_is_non_empty(
        self,
        concept_a: str,
        concept_b: str,
        relationship: str,
    ) -> None:
        """1-hop relationship chain is always a non-empty string."""
        chain = _build_relationship_chain(
            concepts=[concept_a, concept_b],
            relationships=[relationship],
        )
        assert isinstance(chain, str)
        assert len(chain.strip()) > 0

    @given(
        concept_a=_concept_name(),
        concept_b=_concept_name(),
        relationship=_relationship_type(),
    )
    @settings(max_examples=200)
    def test_one_hop_chain_has_correct_structure(
        self,
        concept_a: str,
        concept_b: str,
        relationship: str,
    ) -> None:
        """1-hop chain follows the pattern: concept_a rel concept_b."""
        chain = _build_relationship_chain(
            concepts=[concept_a, concept_b],
            relationships=[relationship],
        )
        formatted_rel = _format_relationship(relationship)
        # The chain should be "concept_a formatted_rel concept_b"
        expected = f"{concept_a} {formatted_rel} {concept_b}"
        assert chain == expected, (
            f"Expected chain {expected!r}, got {chain!r}"
        )

    # -----------------------------------------------------------
    # 2-hop: chain contains all three concepts and both rels
    # -----------------------------------------------------------

    @given(
        concept_a=_concept_name(),
        concept_b=_concept_name(),
        concept_c=_concept_name(),
        relationship_1=_relationship_type(),
        relationship_2=_relationship_type(),
    )
    @settings(max_examples=200)
    def test_two_hop_chain_contains_concept_a(
        self,
        concept_a: str,
        concept_b: str,
        concept_c: str,
        relationship_1: str,
        relationship_2: str,
    ) -> None:
        """concept_a appears in the 2-hop relationship chain."""
        chain = _build_relationship_chain(
            concepts=[concept_a, concept_b, concept_c],
            relationships=[relationship_1, relationship_2],
        )
        assert concept_a.lower() in chain.lower(), (
            f"concept_a {concept_a!r} not found in chain: {chain!r}"
        )

    @given(
        concept_a=_concept_name(),
        concept_b=_concept_name(),
        concept_c=_concept_name(),
        relationship_1=_relationship_type(),
        relationship_2=_relationship_type(),
    )
    @settings(max_examples=200)
    def test_two_hop_chain_contains_concept_b(
        self,
        concept_a: str,
        concept_b: str,
        concept_c: str,
        relationship_1: str,
        relationship_2: str,
    ) -> None:
        """concept_b appears in the 2-hop relationship chain."""
        chain = _build_relationship_chain(
            concepts=[concept_a, concept_b, concept_c],
            relationships=[relationship_1, relationship_2],
        )
        assert concept_b.lower() in chain.lower(), (
            f"concept_b {concept_b!r} not found in chain: {chain!r}"
        )

    @given(
        concept_a=_concept_name(),
        concept_b=_concept_name(),
        concept_c=_concept_name(),
        relationship_1=_relationship_type(),
        relationship_2=_relationship_type(),
    )
    @settings(max_examples=200)
    def test_two_hop_chain_contains_concept_c(
        self,
        concept_a: str,
        concept_b: str,
        concept_c: str,
        relationship_1: str,
        relationship_2: str,
    ) -> None:
        """concept_c appears in the 2-hop relationship chain."""
        chain = _build_relationship_chain(
            concepts=[concept_a, concept_b, concept_c],
            relationships=[relationship_1, relationship_2],
        )
        assert concept_c.lower() in chain.lower(), (
            f"concept_c {concept_c!r} not found in chain: {chain!r}"
        )

    @given(
        concept_a=_concept_name(),
        concept_b=_concept_name(),
        concept_c=_concept_name(),
        relationship_1=_relationship_type(),
        relationship_2=_relationship_type(),
    )
    @settings(max_examples=200)
    def test_two_hop_chain_contains_first_relationship(
        self,
        concept_a: str,
        concept_b: str,
        concept_c: str,
        relationship_1: str,
        relationship_2: str,
    ) -> None:
        """The first formatted relationship appears in the 2-hop chain."""
        chain = _build_relationship_chain(
            concepts=[concept_a, concept_b, concept_c],
            relationships=[relationship_1, relationship_2],
        )
        formatted_rel = _format_relationship(relationship_1)
        assert formatted_rel.lower() in chain.lower(), (
            f"relationship_1 {formatted_rel!r} not found in "
            f"chain: {chain!r}"
        )

    @given(
        concept_a=_concept_name(),
        concept_b=_concept_name(),
        concept_c=_concept_name(),
        relationship_1=_relationship_type(),
        relationship_2=_relationship_type(),
    )
    @settings(max_examples=200)
    def test_two_hop_chain_contains_second_relationship(
        self,
        concept_a: str,
        concept_b: str,
        concept_c: str,
        relationship_1: str,
        relationship_2: str,
    ) -> None:
        """The second formatted relationship appears in the 2-hop chain."""
        chain = _build_relationship_chain(
            concepts=[concept_a, concept_b, concept_c],
            relationships=[relationship_1, relationship_2],
        )
        formatted_rel = _format_relationship(relationship_2)
        assert formatted_rel.lower() in chain.lower(), (
            f"relationship_2 {formatted_rel!r} not found in "
            f"chain: {chain!r}"
        )

    @given(
        concept_a=_concept_name(),
        concept_b=_concept_name(),
        concept_c=_concept_name(),
        relationship_1=_relationship_type(),
        relationship_2=_relationship_type(),
    )
    @settings(max_examples=200)
    def test_two_hop_chain_is_non_empty(
        self,
        concept_a: str,
        concept_b: str,
        concept_c: str,
        relationship_1: str,
        relationship_2: str,
    ) -> None:
        """2-hop relationship chain is always a non-empty string."""
        chain = _build_relationship_chain(
            concepts=[concept_a, concept_b, concept_c],
            relationships=[relationship_1, relationship_2],
        )
        assert isinstance(chain, str)
        assert len(chain.strip()) > 0

    @given(
        concept_a=_concept_name(),
        concept_b=_concept_name(),
        concept_c=_concept_name(),
        relationship_1=_relationship_type(),
        relationship_2=_relationship_type(),
    )
    @settings(max_examples=200)
    def test_two_hop_chain_has_correct_structure(
        self,
        concept_a: str,
        concept_b: str,
        concept_c: str,
        relationship_1: str,
        relationship_2: str,
    ) -> None:
        """2-hop chain follows: concept_a rel1 concept_b rel2 concept_c."""
        chain = _build_relationship_chain(
            concepts=[concept_a, concept_b, concept_c],
            relationships=[relationship_1, relationship_2],
        )
        formatted_rel1 = _format_relationship(relationship_1)
        formatted_rel2 = _format_relationship(relationship_2)
        expected = (
            f"{concept_a} {formatted_rel1} {concept_b} "
            f"{formatted_rel2} {concept_c}"
        )
        assert chain == expected, (
            f"Expected chain {expected!r}, got {chain!r}"
        )

    # -----------------------------------------------------------
    # Edge cases: degenerate inputs produce empty chain
    # -----------------------------------------------------------

    def test_empty_concepts_produces_empty_chain(self) -> None:
        """An empty concepts list produces an empty chain."""
        chain = _build_relationship_chain(concepts=[], relationships=[])
        assert chain == ""

    def test_single_concept_produces_empty_chain(self) -> None:
        """A single concept with no relationships produces empty chain."""
        chain = _build_relationship_chain(
            concepts=["Aspirin"], relationships=[]
        )
        assert chain == ""

    def test_concepts_without_relationships_produces_empty_chain(
        self,
    ) -> None:
        """Two concepts but no relationships produces empty chain."""
        chain = _build_relationship_chain(
            concepts=["Aspirin", "Headache"], relationships=[]
        )
        assert chain == ""

# ---------------------------------------------------------------
# Unit test imports (Task 4.4)
# ---------------------------------------------------------------

import asyncio
from unittest.mock import AsyncMock, MagicMock

from multimodal_librarian.ml.models import InstructionTuningPair
from multimodal_librarian.ml.umls_reasoning_strategy import (
    UMLSReasoningStrategy,
    _count_tokens,
    _generate_one_hop_answer,
    _generate_two_hop_answer,
)

# ---------------------------------------------------------------
# Unit test data helpers (Task 4.4)
# ---------------------------------------------------------------

_ASPIRIN_CHUNK_CONTENT = (
    "Aspirin (acetylsalicylic acid) is a nonsteroidal "
    "anti-inflammatory drug (NSAID) used to treat pain, fever, "
    "and inflammation. It works by inhibiting cyclooxygenase "
    "enzymes (COX-1 and COX-2), which decreases the production "
    "of prostaglandins and thromboxanes. Aspirin is also used "
    "at low doses as an antiplatelet agent to prevent blood "
    "clots in patients at risk for cardiovascular events. "
    "Common side effects include gastrointestinal irritation "
    "and increased bleeding risk."
)

_HEADACHE_CHUNK_CONTENT = (
    "Headache is one of the most common neurological symptoms "
    "encountered in clinical practice. Primary headache disorders "
    "include migraine, tension-type headache, and cluster headache. "
    "Secondary headaches arise from underlying conditions such as "
    "infection, trauma, or vascular disorders. Diagnosis relies on "
    "clinical history and neurological examination. Treatment varies "
    "by headache type and may include analgesics, triptans, "
    "preventive medications, and lifestyle modifications."
)

_PHOTOPHOBIA_CHUNK_CONTENT = (
    "Photophobia is an abnormal sensitivity to light that is a "
    "common symptom of migraine, meningitis, and other neurological "
    "conditions. It results from activation of trigeminal sensory "
    "pathways and is often accompanied by phonophobia. Management "
    "focuses on treating the underlying condition and reducing "
    "light exposure during acute episodes."
)


def _make_one_hop_path(
    concept_a_name="Aspirin",
    concept_a_cui="C0004057",
    concept_a_semantic_type="Pharmacologic Substance",
    concept_b_name="Headache",
    concept_b_cui="C0018681",
    concept_b_semantic_type="Sign or Symptom",
    relationship_type="TREATS",
):
    """Build a 1-hop path dict matching the Neo4j query result shape."""
    return {
        "concept_a_name": concept_a_name,
        "concept_a_cui": concept_a_cui,
        "concept_a_semantic_type": concept_a_semantic_type,
        "concept_b_name": concept_b_name,
        "concept_b_cui": concept_b_cui,
        "concept_b_semantic_type": concept_b_semantic_type,
        "relationship_type": relationship_type,
    }


def _make_two_hop_path(
    concept_a_name="Aspirin",
    concept_a_cui="C0004057",
    concept_a_semantic_type="Pharmacologic Substance",
    concept_b_name="Headache",
    concept_b_cui="C0018681",
    concept_b_semantic_type="Sign or Symptom",
    concept_c_name="Photophobia",
    concept_c_cui="C0085636",
    concept_c_semantic_type="Sign or Symptom",
    relationship_type_1="TREATS",
    relationship_type_2="PRESENTS_WITH",
):
    """Build a 2-hop path dict matching the Neo4j query result shape."""
    return {
        "concept_a_name": concept_a_name,
        "concept_a_cui": concept_a_cui,
        "concept_a_semantic_type": concept_a_semantic_type,
        "concept_b_name": concept_b_name,
        "concept_b_cui": concept_b_cui,
        "concept_b_semantic_type": concept_b_semantic_type,
        "concept_c_name": concept_c_name,
        "concept_c_cui": concept_c_cui,
        "concept_c_semantic_type": concept_c_semantic_type,
        "relationship_type_1": relationship_type_1,
        "relationship_type_2": relationship_type_2,
    }


def _make_chunk_data(chunk_id, content):
    """Build a chunk data dict matching the vector store return shape."""
    return {
        "chunk_id": chunk_id,
        "content": content,
        "metadata": {"content": content},
    }


def _build_mock_neo4j(
    one_hop_paths=None,
    two_hop_paths=None,
    chunk_results=None,
):
    """Build a mock Neo4j client with configurable query responses."""
    client = MagicMock()
    if chunk_results is None:
        chunk_results = {}

    async def _execute_query(query, params=None):
        if params is None:
            params = {}
        if "relationship_types" in params and "limit" in params:
            if "r2" in query:
                return two_hop_paths or []
            return one_hop_paths or []
        if "cui" in params:
            return chunk_results.get(params["cui"], [])
        return []

    client.execute_query = AsyncMock(side_effect=_execute_query)
    return client


def _build_mock_vector(chunk_data_map=None):
    """Build a mock vector client with configurable chunk retrieval."""
    client = MagicMock()
    if chunk_data_map is None:
        chunk_data_map = {}

    async def _get_chunk(chunk_id):
        return chunk_data_map.get(chunk_id)

    client.get_chunk_by_id = AsyncMock(side_effect=_get_chunk)
    return client


def _build_strategy(
    one_hop_paths=None,
    two_hop_paths=None,
    chunk_results=None,
    chunk_data_map=None,
):
    """Build a UMLSReasoningStrategy with mocked dependencies."""
    neo4j = _build_mock_neo4j(one_hop_paths, two_hop_paths, chunk_results)
    vector = _build_mock_vector(chunk_data_map)
    traverser = MagicMock()
    traverser._neo4j_client = neo4j
    traverser._timeout_seconds = 3.0
    umls_client = MagicMock()
    return UMLSReasoningStrategy(traverser, umls_client, vector)


# ---------------------------------------------------------------
# Unit tests: Helper functions
# ---------------------------------------------------------------


@pytest.mark.unit
class TestFormatRelationship:
    """Tests for _format_relationship helper."""

    def test_treats(self):
        assert _format_relationship("TREATS") == "treats"

    def test_causes(self):
        assert _format_relationship("CAUSES") == "causes"

    def test_treated_by(self):
        assert _format_relationship("TREATED_BY") == "treated by"

    def test_presents_with(self):
        assert _format_relationship("PRESENTS_WITH") == "presents with"

    def test_is_a(self):
        assert _format_relationship("IS_A") == "is a"

    def test_part_of(self):
        assert _format_relationship("PART_OF") == "part of"

    def test_single_word(self):
        assert _format_relationship("INHIBITS") == "inhibits"


@pytest.mark.unit
class TestCountTokens:
    """Tests for _count_tokens helper."""

    def test_empty_string(self):
        assert _count_tokens("") == 0

    def test_single_word(self):
        assert _count_tokens("aspirin") == 1

    def test_multiple_words(self):
        assert _count_tokens("aspirin treats headache") == 3

    def test_extra_whitespace(self):
        # split() collapses multiple spaces
        assert _count_tokens("aspirin  treats   headache") == 3


# ---------------------------------------------------------------
# Unit tests: 1-hop question generation
# ---------------------------------------------------------------


@pytest.mark.unit
class TestOneHopQuestionGeneration:
    """Test 1-hop question generation with specific relationship chains.

    Validates: Requirements 3.1, 3.2
    """

    def test_aspirin_treats_headache(self):
        """Aspirin TREATS Headache produces a question with both concepts."""
        q = _generate_one_hop_question(
            concept_a="Aspirin",
            concept_b="Headache",
            relationship="TREATS",
            template_index=0,
            question_style="conversational",
        )
        assert "Aspirin" in q
        assert "Headache" in q

    def test_smoking_causes_lung_cancer(self):
        """Smoking CAUSES Lung Cancer produces a question with both concepts."""
        q = _generate_one_hop_question(
            concept_a="Smoking",
            concept_b="Lung Cancer",
            relationship="CAUSES",
            template_index=0,
            question_style="conversational",
        )
        assert "Smoking" in q
        assert "Lung Cancer" in q

    def test_diabetes_treated_by_insulin(self):
        """Diabetes TREATED_BY Insulin produces a question with both concepts."""
        q = _generate_one_hop_question(
            concept_a="Diabetes",
            concept_b="Insulin",
            relationship="TREATED_BY",
            template_index=0,
            question_style="conversational",
        )
        assert "Diabetes" in q
        assert "Insulin" in q

    def test_migraine_presents_with_photophobia(self):
        """Migraine PRESENTS_WITH Photophobia produces correct question."""
        q = _generate_one_hop_question(
            concept_a="Migraine",
            concept_b="Photophobia",
            relationship="PRESENTS_WITH",
            template_index=0,
            question_style="conversational",
        )
        assert "Migraine" in q
        assert "Photophobia" in q

    def test_medqa_style_treats(self):
        """MedQA style produces a clinical vignette question."""
        q = _generate_one_hop_question(
            concept_a="Metformin",
            concept_b="Type 2 Diabetes",
            relationship="TREATS",
            template_index=0,
            question_style="medqa",
        )
        assert "Metformin" in q
        assert "Type 2 Diabetes" in q

    def test_medmcqa_style_causes(self):
        """MedMCQA style produces a direct factual recall question."""
        q = _generate_one_hop_question(
            concept_a="Hypertension",
            concept_b="Stroke",
            relationship="CAUSES",
            template_index=0,
            question_style="medmcqa",
        )
        assert "Hypertension" in q
        assert "Stroke" in q

    def test_pubmedqa_style_treats(self):
        """PubMedQA style produces an evidence-based question."""
        q = _generate_one_hop_question(
            concept_a="Aspirin",
            concept_b="Headache",
            relationship="TREATS",
            template_index=0,
            question_style="pubmedqa",
        )
        assert "Aspirin" in q
        assert "Headache" in q

    def test_template_cycling_produces_different_questions(self):
        """Different template indices produce different questions."""
        q0 = _generate_one_hop_question(
            concept_a="Aspirin",
            concept_b="Headache",
            relationship="TREATS",
            template_index=0,
            question_style="conversational",
        )
        q1 = _generate_one_hop_question(
            concept_a="Aspirin",
            concept_b="Headache",
            relationship="TREATS",
            template_index=1,
            question_style="conversational",
        )
        assert q0 != q1
        assert "Aspirin" in q0 and "Aspirin" in q1


# ---------------------------------------------------------------
# Unit tests: 2-hop question generation
# ---------------------------------------------------------------


@pytest.mark.unit
class TestTwoHopQuestionGeneration:
    """Test 2-hop question generation with specific relationship chains.

    Validates: Requirements 3.2, 3.3
    """

    def test_aspirin_treats_headache_presents_with_photophobia(self):
        """Aspirin TREATS Headache PRESENTS_WITH Photophobia."""
        q = _generate_two_hop_question(
            concept_a="Aspirin",
            concept_b="Headache",
            concept_c="Photophobia",
            relationship_1="TREATS",
            relationship_2="PRESENTS_WITH",
            template_index=0,
            question_style="conversational",
        )
        assert "Aspirin" in q
        assert "Headache" in q
        assert "Photophobia" in q

    def test_smoking_causes_copd_treated_by_bronchodilators(self):
        """Smoking CAUSES COPD TREATED_BY Bronchodilators."""
        q = _generate_two_hop_question(
            concept_a="Smoking",
            concept_b="COPD",
            concept_c="Bronchodilators",
            relationship_1="CAUSES",
            relationship_2="TREATED_BY",
            template_index=0,
            question_style="conversational",
        )
        assert "Smoking" in q
        assert "COPD" in q
        assert "Bronchodilators" in q

    def test_medqa_style_two_hop(self):
        """MedQA style 2-hop question contains all three concepts."""
        q = _generate_two_hop_question(
            concept_a="Hypertension",
            concept_b="Heart Failure",
            concept_c="Dyspnea",
            relationship_1="CAUSES",
            relationship_2="PRESENTS_WITH",
            template_index=0,
            question_style="medqa",
        )
        assert "Hypertension" in q
        assert "Heart Failure" in q
        assert "Dyspnea" in q

    def test_mixed_style_two_hop(self):
        """Mixed style 2-hop question contains all three concepts."""
        q = _generate_two_hop_question(
            concept_a="Drug_A",
            concept_b="Disease_B",
            concept_c="Symptom_C",
            relationship_1="TREATS",
            relationship_2="PRESENTS_WITH",
            template_index=0,
            question_style="mixed",
        )
        assert "Drug_A" in q
        assert "Disease_B" in q
        assert "Symptom_C" in q


# ---------------------------------------------------------------
# Unit tests: Answer generation
# ---------------------------------------------------------------


@pytest.mark.unit
class TestOneHopAnswerGeneration:
    """Test 1-hop answer generation.

    Validates: Requirements 3.4, 3.6
    """

    def test_answer_contains_relationship_chain(self):
        """Answer includes the relationship chain string."""
        answer = _generate_one_hop_answer(
            concept_a="Aspirin",
            concept_b="Headache",
            relationship="TREATS",
            supporting_evidence="Aspirin inhibits COX enzymes.",
        )
        assert "Aspirin" in answer
        assert "Headache" in answer
        assert "treats" in answer.lower()
        assert "Relationship chain:" in answer

    def test_answer_contains_supporting_evidence(self):
        """Answer includes the supporting evidence text."""
        evidence = "Metformin reduces hepatic glucose production."
        answer = _generate_one_hop_answer(
            concept_a="Metformin",
            concept_b="Type 2 Diabetes",
            relationship="TREATS",
            supporting_evidence=evidence,
        )
        assert evidence in answer

    def test_answer_strips_evidence_whitespace(self):
        """Leading/trailing whitespace in evidence is stripped."""
        answer = _generate_one_hop_answer(
            concept_a="A",
            concept_b="B",
            relationship="CAUSES",
            supporting_evidence="  some evidence  ",
        )
        assert "  some evidence  " not in answer
        assert "some evidence" in answer


@pytest.mark.unit
class TestTwoHopAnswerGeneration:
    """Test 2-hop answer generation.

    Validates: Requirements 3.4, 3.6
    """

    def test_answer_contains_full_chain(self):
        """Answer includes the full 2-hop relationship chain."""
        answer = _generate_two_hop_answer(
            concept_a="Aspirin",
            concept_b="Headache",
            concept_c="Photophobia",
            relationship_1="TREATS",
            relationship_2="PRESENTS_WITH",
            supporting_evidence="Supporting text here.",
        )
        assert "Aspirin" in answer
        assert "Headache" in answer
        assert "Photophobia" in answer
        assert "treats" in answer.lower()
        assert "presents with" in answer.lower()
        assert "Relationship chain:" in answer

    def test_answer_contains_supporting_evidence(self):
        """Answer includes the supporting evidence text."""
        evidence = "Clinical studies show the pathway."
        answer = _generate_two_hop_answer(
            concept_a="A",
            concept_b="B",
            concept_c="C",
            relationship_1="CAUSES",
            relationship_2="TREATED_BY",
            supporting_evidence=evidence,
        )
        assert evidence in answer


# ---------------------------------------------------------------
# Unit tests: UMLSReasoningStrategy.generate() — 1-hop
# ---------------------------------------------------------------


@pytest.mark.unit
class TestUMLSReasoningStrategyOneHop:
    """Test 1-hop pair generation via generate().

    Validates: Requirements 3.1, 3.2, 3.4, 3.5, 3.6
    """

    @pytest.mark.asyncio
    async def test_basic_one_hop_generation(self):
        """Generate a single 1-hop pair: Aspirin TREATS Headache."""
        strategy = _build_strategy(
            one_hop_paths=[_make_one_hop_path()],
            chunk_results={
                "C0004057": [{"chunk_id": "chunk-asp-1"}],
                "C0018681": [{"chunk_id": "chunk-head-1"}],
            },
            chunk_data_map={
                "chunk-asp-1": _make_chunk_data(
                    "chunk-asp-1", _ASPIRIN_CHUNK_CONTENT
                ),
                "chunk-head-1": _make_chunk_data(
                    "chunk-head-1", _HEADACHE_CHUNK_CONTENT
                ),
            },
        )
        pairs = await strategy.generate(
            target_count=1, max_hops=1
        )
        assert len(pairs) == 1
        pair = pairs[0]
        assert isinstance(pair, InstructionTuningPair)
        assert pair.metadata.strategy == "umls_reasoning"
        assert "Aspirin" in pair.instruction
        assert "Headache" in pair.instruction
        # Context contains relationship chain (Property 7)
        assert "treats" in pair.context.lower()
        assert "Aspirin" in pair.context
        assert "Headache" in pair.context
        # Response contains relationship chain
        assert "Relationship chain:" in pair.response
        # Metadata
        assert "C0004057" in pair.metadata.source_concepts
        assert "C0018681" in pair.metadata.source_concepts
        assert 0.0 <= pair.metadata.confidence_score <= 1.0
        assert pair.metadata.relationship_chain is not None

    @pytest.mark.asyncio
    async def test_one_hop_specific_relationship_types(self):
        """Test different relationship types produce valid pairs."""
        for rel_type in ["CAUSES", "TREATED_BY", "PRESENTS_WITH", "IS_A", "PART_OF"]:
            strategy = _build_strategy(
                one_hop_paths=[
                    _make_one_hop_path(
                        concept_a_name="ConceptA",
                        concept_b_name="ConceptB",
                        relationship_type=rel_type,
                    )
                ],
                chunk_results={
                    "C0004057": [{"chunk_id": "chunk-1"}],
                    "C0018681": [{"chunk_id": "chunk-2"}],
                },
                chunk_data_map={
                    "chunk-1": _make_chunk_data(
                        "chunk-1", _ASPIRIN_CHUNK_CONTENT
                    ),
                    "chunk-2": _make_chunk_data(
                        "chunk-2", _HEADACHE_CHUNK_CONTENT
                    ),
                },
            )
            pairs = await strategy.generate(
                target_count=1, max_hops=1
            )
            assert len(pairs) == 1, (
                f"Expected 1 pair for {rel_type}, got {len(pairs)}"
            )
            assert "ConceptA" in pairs[0].instruction
            assert "ConceptB" in pairs[0].instruction

    @pytest.mark.asyncio
    async def test_one_hop_respects_target_count(self):
        """Stop generating once target_count is reached."""
        paths = [
            _make_one_hop_path(
                concept_a_name=f"Drug_{i}",
                concept_a_cui=f"C{i:07d}",
                concept_b_name=f"Disease_{i}",
                concept_b_cui=f"D{i:07d}",
            )
            for i in range(10)
        ]
        chunk_results = {}
        chunk_data_map = {}
        for i in range(10):
            a_cui = f"C{i:07d}"
            b_cui = f"D{i:07d}"
            a_cid = f"chunk-a-{i}"
            b_cid = f"chunk-b-{i}"
            chunk_results[a_cui] = [{"chunk_id": a_cid}]
            chunk_results[b_cui] = [{"chunk_id": b_cid}]
            chunk_data_map[a_cid] = _make_chunk_data(
                a_cid, _ASPIRIN_CHUNK_CONTENT
            )
            chunk_data_map[b_cid] = _make_chunk_data(
                b_cid, _HEADACHE_CHUNK_CONTENT
            )

        strategy = _build_strategy(
            one_hop_paths=paths,
            chunk_results=chunk_results,
            chunk_data_map=chunk_data_map,
        )
        pairs = await strategy.generate(target_count=3, max_hops=1)
        assert len(pairs) == 3

    @pytest.mark.asyncio
    async def test_one_hop_progress_callback(self):
        """Progress callback is invoked with (generated, target)."""
        strategy = _build_strategy(
            one_hop_paths=[_make_one_hop_path()],
            chunk_results={
                "C0004057": [{"chunk_id": "chunk-1"}],
                "C0018681": [{"chunk_id": "chunk-2"}],
            },
            chunk_data_map={
                "chunk-1": _make_chunk_data(
                    "chunk-1", _ASPIRIN_CHUNK_CONTENT
                ),
                "chunk-2": _make_chunk_data(
                    "chunk-2", _HEADACHE_CHUNK_CONTENT
                ),
            },
        )
        calls = []
        await strategy.generate(
            target_count=1,
            max_hops=1,
            progress_callback=lambda gen, tgt: calls.append((gen, tgt)),
        )
        assert len(calls) >= 1
        assert calls[-1][0] >= 1


# ---------------------------------------------------------------
# Unit tests: UMLSReasoningStrategy.generate() — 2-hop
# ---------------------------------------------------------------


@pytest.mark.unit
class TestUMLSReasoningStrategyTwoHop:
    """Test 2-hop pair generation via generate().

    Validates: Requirements 3.2, 3.3, 3.4, 3.5, 3.6
    """

    @pytest.mark.asyncio
    async def test_basic_two_hop_generation(self):
        """Generate a 2-hop pair: Aspirin TREATS Headache PRESENTS_WITH Photophobia."""
        strategy = _build_strategy(
            one_hop_paths=[],  # No 1-hop paths so budget goes to 2-hop
            two_hop_paths=[_make_two_hop_path()],
            chunk_results={
                "C0004057": [{"chunk_id": "chunk-asp"}],
                "C0018681": [{"chunk_id": "chunk-head"}],
                "C0085636": [{"chunk_id": "chunk-photo"}],
            },
            chunk_data_map={
                "chunk-asp": _make_chunk_data(
                    "chunk-asp", _ASPIRIN_CHUNK_CONTENT
                ),
                "chunk-head": _make_chunk_data(
                    "chunk-head", _HEADACHE_CHUNK_CONTENT
                ),
                "chunk-photo": _make_chunk_data(
                    "chunk-photo", _PHOTOPHOBIA_CHUNK_CONTENT
                ),
            },
        )
        pairs = await strategy.generate(target_count=1, max_hops=2)
        assert len(pairs) >= 1
        # Find the 2-hop pair (it should reference all three concepts)
        two_hop_pair = None
        for p in pairs:
            if "Photophobia" in p.instruction:
                two_hop_pair = p
                break
        assert two_hop_pair is not None, (
            "Expected a 2-hop pair referencing Photophobia"
        )
        assert "Aspirin" in two_hop_pair.instruction
        assert "Headache" in two_hop_pair.instruction
        assert "Photophobia" in two_hop_pair.instruction
        # Context contains relationship chain
        assert "Aspirin" in two_hop_pair.context
        assert "Headache" in two_hop_pair.context
        assert "Photophobia" in two_hop_pair.context
        # Metadata
        assert two_hop_pair.metadata.strategy == "umls_reasoning"
        assert "C0004057" in two_hop_pair.metadata.source_concepts
        assert "C0018681" in two_hop_pair.metadata.source_concepts
        assert "C0085636" in two_hop_pair.metadata.source_concepts

    @pytest.mark.asyncio
    async def test_max_hops_1_skips_two_hop(self):
        """When max_hops=1, no 2-hop pairs are generated."""
        strategy = _build_strategy(
            one_hop_paths=[_make_one_hop_path()],
            two_hop_paths=[_make_two_hop_path()],
            chunk_results={
                "C0004057": [{"chunk_id": "chunk-1"}],
                "C0018681": [{"chunk_id": "chunk-2"}],
                "C0085636": [{"chunk_id": "chunk-3"}],
            },
            chunk_data_map={
                "chunk-1": _make_chunk_data(
                    "chunk-1", _ASPIRIN_CHUNK_CONTENT
                ),
                "chunk-2": _make_chunk_data(
                    "chunk-2", _HEADACHE_CHUNK_CONTENT
                ),
                "chunk-3": _make_chunk_data(
                    "chunk-3", _PHOTOPHOBIA_CHUNK_CONTENT
                ),
            },
        )
        pairs = await strategy.generate(target_count=5, max_hops=1)
        for pair in pairs:
            # No pair should reference Photophobia (the 2-hop concept)
            assert "Photophobia" not in pair.instruction

    @pytest.mark.asyncio
    async def test_two_hop_budget_split(self):
        """With max_hops=2, budget is ~60% 1-hop, ~40% 2-hop."""
        one_hop_paths = [
            _make_one_hop_path(
                concept_a_name=f"DrugA_{i}",
                concept_a_cui=f"CA{i:05d}",
                concept_b_name=f"DiseaseB_{i}",
                concept_b_cui=f"CB{i:05d}",
            )
            for i in range(20)
        ]
        two_hop_paths = [
            _make_two_hop_path(
                concept_a_name=f"DrugX_{i}",
                concept_a_cui=f"CX{i:05d}",
                concept_b_name=f"DiseaseY_{i}",
                concept_b_cui=f"CY{i:05d}",
                concept_c_name=f"SymptomZ_{i}",
                concept_c_cui=f"CZ{i:05d}",
            )
            for i in range(20)
        ]
        chunk_results = {}
        chunk_data_map = {}
        for i in range(20):
            for prefix, cui_prefix in [
                ("a", "CA"), ("b", "CB"),
                ("x", "CX"), ("y", "CY"), ("z", "CZ"),
            ]:
                cui = f"{cui_prefix}{i:05d}"
                cid = f"chunk-{prefix}-{i}"
                chunk_results[cui] = [{"chunk_id": cid}]
                chunk_data_map[cid] = _make_chunk_data(
                    cid, _ASPIRIN_CHUNK_CONTENT
                )

        strategy = _build_strategy(
            one_hop_paths=one_hop_paths,
            two_hop_paths=two_hop_paths,
            chunk_results=chunk_results,
            chunk_data_map=chunk_data_map,
        )
        pairs = await strategy.generate(target_count=10, max_hops=2)
        assert len(pairs) == 10
        # Should have a mix of 1-hop and 2-hop pairs
        one_hop_count = sum(
            1 for p in pairs if len(p.metadata.source_concepts) == 2
        )
        two_hop_count = sum(
            1 for p in pairs if len(p.metadata.source_concepts) == 3
        )
        assert one_hop_count > 0, "Expected some 1-hop pairs"
        assert two_hop_count > 0, "Expected some 2-hop pairs"


# ---------------------------------------------------------------
# Unit tests: Skip behavior when no supporting chunks exist
# ---------------------------------------------------------------


@pytest.mark.unit
class TestSkipBehaviorNoSupportingChunks:
    """Test that paths with no supporting chunk content are skipped.

    Validates: Requirements 3.4, 3.5
    """

    @pytest.mark.asyncio
    async def test_one_hop_skipped_when_no_chunks_in_neo4j(self):
        """1-hop path skipped when Neo4j returns no chunk IDs."""
        strategy = _build_strategy(
            one_hop_paths=[_make_one_hop_path()],
            chunk_results={},  # No chunk results for any CUI
            chunk_data_map={},
        )
        pairs = await strategy.generate(target_count=5, max_hops=1)
        assert len(pairs) == 0

    @pytest.mark.asyncio
    async def test_one_hop_skipped_when_vector_returns_none(self):
        """1-hop path skipped when vector store returns None for chunks."""
        strategy = _build_strategy(
            one_hop_paths=[_make_one_hop_path()],
            chunk_results={
                "C0004057": [{"chunk_id": "chunk-missing"}],
                "C0018681": [{"chunk_id": "chunk-also-missing"}],
            },
            chunk_data_map={},  # No chunks in vector store
        )
        pairs = await strategy.generate(target_count=5, max_hops=1)
        assert len(pairs) == 0

    @pytest.mark.asyncio
    async def test_one_hop_skipped_when_chunk_content_empty(self):
        """1-hop path skipped when chunk content is empty string."""
        strategy = _build_strategy(
            one_hop_paths=[_make_one_hop_path()],
            chunk_results={
                "C0004057": [{"chunk_id": "chunk-empty"}],
            },
            chunk_data_map={
                "chunk-empty": _make_chunk_data("chunk-empty", ""),
            },
        )
        pairs = await strategy.generate(target_count=5, max_hops=1)
        assert len(pairs) == 0

    @pytest.mark.asyncio
    async def test_two_hop_skipped_when_no_chunks(self):
        """2-hop path skipped when no supporting chunks exist."""
        strategy = _build_strategy(
            one_hop_paths=[],
            two_hop_paths=[_make_two_hop_path()],
            chunk_results={},
            chunk_data_map={},
        )
        pairs = await strategy.generate(target_count=5, max_hops=2)
        assert len(pairs) == 0

    @pytest.mark.asyncio
    async def test_partial_chunk_availability(self):
        """Pair generated when at least one concept has chunk content."""
        strategy = _build_strategy(
            one_hop_paths=[_make_one_hop_path()],
            chunk_results={
                # Only concept_a has chunks, concept_b has none
                "C0004057": [{"chunk_id": "chunk-asp"}],
            },
            chunk_data_map={
                "chunk-asp": _make_chunk_data(
                    "chunk-asp", _ASPIRIN_CHUNK_CONTENT
                ),
            },
        )
        pairs = await strategy.generate(target_count=1, max_hops=1)
        # Should produce a pair since at least one concept has content
        assert len(pairs) == 1


# ---------------------------------------------------------------
# Unit tests: Error handling
# ---------------------------------------------------------------


@pytest.mark.unit
class TestUMLSReasoningStrategyErrorHandling:
    """Test graceful error handling for Neo4j and vector store failures.

    Validates: Requirements 3.1, 3.5
    """

    @pytest.mark.asyncio
    async def test_neo4j_connection_failure_returns_empty(self):
        """Neo4j connection failure returns empty list."""
        neo4j = MagicMock()
        neo4j.execute_query = AsyncMock(
            side_effect=ConnectionError("Neo4j down")
        )
        vector = MagicMock()
        vector.get_chunk_by_id = AsyncMock(return_value=None)
        traverser = MagicMock()
        traverser._neo4j_client = neo4j
        traverser._timeout_seconds = 3.0
        umls_client = MagicMock()

        strategy = UMLSReasoningStrategy(traverser, umls_client, vector)
        pairs = await strategy.generate(target_count=5)
        assert pairs == []

    @pytest.mark.asyncio
    async def test_neo4j_timeout_returns_empty(self):
        """Neo4j query timeout returns empty list."""
        neo4j = MagicMock()

        async def _slow_query(*args, **kwargs):
            await asyncio.sleep(10)
            return []

        neo4j.execute_query = AsyncMock(side_effect=_slow_query)
        vector = MagicMock()
        vector.get_chunk_by_id = AsyncMock(return_value=None)
        traverser = MagicMock()
        traverser._neo4j_client = neo4j
        traverser._timeout_seconds = 0.01  # Very short timeout
        umls_client = MagicMock()

        strategy = UMLSReasoningStrategy(traverser, umls_client, vector)
        pairs = await strategy.generate(target_count=5)
        assert pairs == []

    @pytest.mark.asyncio
    async def test_no_neo4j_client_returns_empty(self):
        """Missing Neo4j client on traverser returns empty list."""
        vector = MagicMock()
        vector.get_chunk_by_id = AsyncMock(return_value=None)
        traverser = MagicMock(spec=[])  # No _neo4j_client attribute
        umls_client = MagicMock()

        strategy = UMLSReasoningStrategy(traverser, umls_client, vector)
        pairs = await strategy.generate(target_count=5)
        assert pairs == []

    @pytest.mark.asyncio
    async def test_vector_store_failure_skips_pair(self):
        """Vector store failure for chunk retrieval skips that pair."""
        neo4j = MagicMock()

        async def _execute_query(query, params=None):
            if params is None:
                params = {}
            if "relationship_types" in params:
                return [_make_one_hop_path()]
            if "cui" in params:
                return [{"chunk_id": "chunk-fail"}]
            return []

        neo4j.execute_query = AsyncMock(side_effect=_execute_query)
        vector = MagicMock()
        vector.get_chunk_by_id = AsyncMock(
            side_effect=ConnectionError("Milvus down")
        )
        traverser = MagicMock()
        traverser._neo4j_client = neo4j
        traverser._timeout_seconds = 3.0
        umls_client = MagicMock()

        strategy = UMLSReasoningStrategy(traverser, umls_client, vector)
        pairs = await strategy.generate(target_count=5, max_hops=1)
        assert pairs == []

    @pytest.mark.asyncio
    async def test_empty_concept_names_skipped(self):
        """Paths with empty concept names are skipped."""
        strategy = _build_strategy(
            one_hop_paths=[
                _make_one_hop_path(concept_a_name="", concept_b_name="Headache"),
                _make_one_hop_path(concept_a_name="Aspirin", concept_b_name=""),
            ],
            chunk_results={
                "C0004057": [{"chunk_id": "chunk-1"}],
                "C0018681": [{"chunk_id": "chunk-2"}],
            },
            chunk_data_map={
                "chunk-1": _make_chunk_data("chunk-1", _ASPIRIN_CHUNK_CONTENT),
                "chunk-2": _make_chunk_data("chunk-2", _HEADACHE_CHUNK_CONTENT),
            },
        )
        pairs = await strategy.generate(target_count=5, max_hops=1)
        assert len(pairs) == 0

    @pytest.mark.asyncio
    async def test_empty_relationship_type_skipped(self):
        """Paths with empty relationship type are skipped."""
        strategy = _build_strategy(
            one_hop_paths=[
                _make_one_hop_path(relationship_type=""),
            ],
            chunk_results={
                "C0004057": [{"chunk_id": "chunk-1"}],
                "C0018681": [{"chunk_id": "chunk-2"}],
            },
            chunk_data_map={
                "chunk-1": _make_chunk_data("chunk-1", _ASPIRIN_CHUNK_CONTENT),
                "chunk-2": _make_chunk_data("chunk-2", _HEADACHE_CHUNK_CONTENT),
            },
        )
        pairs = await strategy.generate(target_count=5, max_hops=1)
        assert len(pairs) == 0


# ---------------------------------------------------------------
# Unit tests: Internal helpers
# ---------------------------------------------------------------


@pytest.mark.unit
class TestComputeConfidence:
    """Test _compute_confidence scoring logic."""

    def test_empty_content_returns_zero(self):
        assert UMLSReasoningStrategy._compute_confidence("", hops=1) == 0.0

    def test_short_content_lower_confidence(self):
        short = " ".join(["word"] * 60)
        long_ = " ".join(["word"] * 300)
        short_score = UMLSReasoningStrategy._compute_confidence(
            short, hops=1
        )
        long_score = UMLSReasoningStrategy._compute_confidence(
            long_, hops=1
        )
        assert short_score < long_score

    def test_more_hops_lower_confidence(self):
        content = " ".join(["word"] * 200)
        score_1 = UMLSReasoningStrategy._compute_confidence(
            content, hops=1
        )
        score_2 = UMLSReasoningStrategy._compute_confidence(
            content, hops=2
        )
        assert score_2 < score_1

    def test_confidence_bounded_zero_to_one(self):
        for n_words in [0, 10, 50, 200, 1000]:
            content = " ".join(["word"] * n_words)
            for hops in [1, 2, 3]:
                score = UMLSReasoningStrategy._compute_confidence(
                    content, hops=hops
                )
                assert 0.0 <= score <= 1.0, (
                    f"Score {score} out of bounds for "
                    f"{n_words} words, {hops} hops"
                )


@pytest.mark.unit
class TestExtractContent:
    """Test _extract_content helper."""

    def test_top_level_content(self):
        data = {"content": "Top level text"}
        assert UMLSReasoningStrategy._extract_content(data) == "Top level text"

    def test_metadata_content_fallback(self):
        data = {"metadata": {"content": "Metadata text"}}
        assert UMLSReasoningStrategy._extract_content(data) == "Metadata text"

    def test_empty_dict_returns_empty(self):
        assert UMLSReasoningStrategy._extract_content({}) == ""

    def test_top_level_takes_precedence(self):
        data = {
            "content": "Top level",
            "metadata": {"content": "Metadata"},
        }
        assert UMLSReasoningStrategy._extract_content(data) == "Top level"

    def test_none_metadata_returns_empty(self):
        data = {"content": "", "metadata": None}
        assert UMLSReasoningStrategy._extract_content(data) == ""


# ---------------------------------------------------------------
# Unit tests: Question style handling
# ---------------------------------------------------------------


@pytest.mark.unit
class TestQuestionStyleHandling:
    """Test question_style parameter handling in generate()."""

    @pytest.mark.asyncio
    async def test_invalid_style_falls_back_to_mixed(self):
        """Invalid question_style falls back to 'mixed' without error."""
        strategy = _build_strategy(
            one_hop_paths=[_make_one_hop_path()],
            chunk_results={
                "C0004057": [{"chunk_id": "chunk-1"}],
                "C0018681": [{"chunk_id": "chunk-2"}],
            },
            chunk_data_map={
                "chunk-1": _make_chunk_data(
                    "chunk-1", _ASPIRIN_CHUNK_CONTENT
                ),
                "chunk-2": _make_chunk_data(
                    "chunk-2", _HEADACHE_CHUNK_CONTENT
                ),
            },
        )
        # Should not raise, falls back to "mixed"
        pairs = await strategy.generate(
            target_count=1,
            max_hops=1,
            question_style="nonexistent_style",
        )
        assert len(pairs) == 1
        assert "Aspirin" in pairs[0].instruction

    @pytest.mark.asyncio
    async def test_each_valid_style_produces_pairs(self):
        """Each valid question style produces valid pairs."""
        for style in [
            "mixed",
            "conversational",
            "medqa",
            "medmcqa",
            "pubmedqa",
        ]:
            strategy = _build_strategy(
                one_hop_paths=[_make_one_hop_path()],
                chunk_results={
                    "C0004057": [{"chunk_id": "chunk-1"}],
                    "C0018681": [{"chunk_id": "chunk-2"}],
                },
                chunk_data_map={
                    "chunk-1": _make_chunk_data(
                        "chunk-1", _ASPIRIN_CHUNK_CONTENT
                    ),
                    "chunk-2": _make_chunk_data(
                        "chunk-2", _HEADACHE_CHUNK_CONTENT
                    ),
                },
            )
            pairs = await strategy.generate(
                target_count=1,
                max_hops=1,
                question_style=style,
            )
            assert len(pairs) == 1, (
                f"Expected 1 pair for style '{style}', got {len(pairs)}"
            )
            assert isinstance(pairs[0], InstructionTuningPair)


# ---------------------------------------------------------------
# Unit tests: No paths found
# ---------------------------------------------------------------


@pytest.mark.unit
class TestNoPathsFound:
    """Test behavior when Neo4j returns no paths."""

    @pytest.mark.asyncio
    async def test_no_one_hop_paths_returns_empty(self):
        """No 1-hop paths in Neo4j returns empty list."""
        strategy = _build_strategy(
            one_hop_paths=[],
            chunk_results={},
            chunk_data_map={},
        )
        pairs = await strategy.generate(target_count=5, max_hops=1)
        assert pairs == []

    @pytest.mark.asyncio
    async def test_no_two_hop_paths_returns_empty(self):
        """No 2-hop paths in Neo4j returns empty list."""
        strategy = _build_strategy(
            one_hop_paths=[],
            two_hop_paths=[],
            chunk_results={},
            chunk_data_map={},
        )
        pairs = await strategy.generate(target_count=5, max_hops=2)
        assert pairs == []

    @pytest.mark.asyncio
    async def test_no_paths_at_all_returns_empty(self):
        """No paths of any kind returns empty list."""
        strategy = _build_strategy()
        pairs = await strategy.generate(target_count=10)
        assert pairs == []
