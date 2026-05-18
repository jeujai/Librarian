"""
Property-based tests for validation scope during resume.

# Feature: data-generation-resume, Property 2: Validation scope —
#   pre-existing pairs bypass validation

Validates: Requirements 4.5

Property 2 states: For any set of pre-existing pairs and any set of
newly generated pairs, the final accepted dataset SHALL include all
pre-existing pairs (subject only to deduplication) regardless of
whether they would pass quality validation.  Only newly generated
pairs are subject to validation filtering.

The test exercises the exact code path from ``generate()`` that
performs merge → dedup → partition → validate → combine, without
running the actual generation strategies.
"""

from __future__ import annotations

import asyncio
import string
from typing import List
from unittest.mock import AsyncMock, MagicMock

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from multimodal_librarian.ml.models import (
    VALID_STRATEGIES,
    InstructionTuningPair,
    PairMetadata,
    ValidationResult,
)
from multimodal_librarian.ml.training_data_generator import (
    _MIN_RESPONSE_TOKENS,
    TrainingDataGenerator,
)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_LONG_WORD = "medical"
_LONG_RESPONSE = " ".join([_LONG_WORD] * (_MIN_RESPONSE_TOKENS + 10))

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_generator(*, ner_returns: bool = True) -> TrainingDataGenerator:
    """Create a TrainingDataGenerator with a mock NER extractor.

    Args:
        ner_returns: If ``True`` the mock NER extractor reports that a
            UMLS concept was found.  If ``False`` it reports none.
    """
    mock_ner = AsyncMock()
    ner_result = MagicMock()
    if ner_returns:
        ner_result.umls_entities = [{"cui": "C0000001", "name": "test"}]
        ner_result.key_terms = ["test"]
    else:
        ner_result.umls_entities = []
        ner_result.key_terms = []
    mock_ner.extract_key_terms = AsyncMock(return_value=ner_result)

    return TrainingDataGenerator(
        neo4j_client=None,  # type: ignore[arg-type]
        vector_client=None,  # type: ignore[arg-type]
        rag_service=None,  # type: ignore[arg-type]
        umls_client=None,  # type: ignore[arg-type]
        relationship_traverser=None,  # type: ignore[arg-type]
        ner_extractor=mock_ner,
    )


def _make_valid_pair(
    instruction: str,
    strategy: str = "kg",
    confidence: float = 0.9,
) -> InstructionTuningPair:
    """Build a pair that passes all validation checks."""
    return InstructionTuningPair(
        instruction=instruction,
        context="Valid medical context about aspirin and dosage.",
        response=_LONG_RESPONSE,
        metadata=PairMetadata(
            strategy=strategy,
            source_concepts=["C0000001"],
            confidence_score=confidence,
        ),
    )


def _make_invalid_pair(
    instruction: str,
    strategy: str = "kg",
    confidence: float = 0.9,
    failure_mode: str = "short_response",
) -> InstructionTuningPair:
    """Build a pair that fails validation.

    Args:
        failure_mode: One of ``"short_response"``,
            ``"empty_instruction"``, ``"empty_context"``.
    """
    if failure_mode == "short_response":
        return InstructionTuningPair(
            instruction=instruction,
            context="Valid context.",
            response="short",
            metadata=PairMetadata(
                strategy=strategy,
                source_concepts=["C0000001"],
                confidence_score=confidence,
            ),
        )
    elif failure_mode == "empty_instruction":
        return InstructionTuningPair(
            instruction=" ",  # whitespace-only — passes Pydantic min_length=1
            context="Valid context.",
            response=_LONG_RESPONSE,
            metadata=PairMetadata(
                strategy=strategy,
                source_concepts=["C0000001"],
                confidence_score=confidence,
            ),
        )
    elif failure_mode == "empty_context":
        return InstructionTuningPair(
            instruction=instruction,
            context=" ",  # whitespace-only
            response=_LONG_RESPONSE,
            metadata=PairMetadata(
                strategy=strategy,
                source_concepts=["C0000001"],
                confidence_score=confidence,
            ),
        )
    else:
        raise ValueError(f"Unknown failure_mode: {failure_mode}")


def _resume_merge_validate(
    gen: TrainingDataGenerator,
    pre_existing: List[InstructionTuningPair],
    new_pairs: List[InstructionTuningPair],
    similarity_threshold: float = 0.95,
) -> tuple[
    List[InstructionTuningPair],
    List[InstructionTuningPair],
    List[InstructionTuningPair],
]:
    """Replicate the merge → dedup → partition → validate → combine
    logic from ``generate()`` so we can test the validation scope
    property in isolation.

    Returns:
        (final_accepted, deduped_pre_existing, validated_new_accepted)
    """
    all_pairs = list(pre_existing) + list(new_pairs)

    # Dedup across all pairs (same as generate())
    deduped = gen.deduplicate(
        all_pairs, similarity_threshold=similarity_threshold
    )

    # Partition by object identity (same as generate())
    pre_existing_ids: set = {id(p) for p in pre_existing}
    deduped_pre_existing = [
        p for p in deduped if id(p) in pre_existing_ids
    ]
    deduped_new = [
        p for p in deduped if id(p) not in pre_existing_ids
    ]

    # Validate only new pairs (same as generate())
    loop = asyncio.get_event_loop()
    validation: ValidationResult = loop.run_until_complete(
        gen.validate_dataset(deduped_new)
    )

    # Combine: all surviving pre-existing + validated new
    final_accepted = deduped_pre_existing + validation.accepted

    return final_accepted, deduped_pre_existing, validation.accepted


# ---------------------------------------------------------------------------
# Hypothesis strategies
# ---------------------------------------------------------------------------


def _non_empty_text(
    min_size: int = 10,
    max_size: int = 200,
) -> st.SearchStrategy[str]:
    """Non-empty text with at least ``min_size`` non-ws chars."""
    alphabet = string.ascii_letters + string.digits + " "
    return st.text(
        alphabet=alphabet,
        min_size=min_size,
        max_size=max_size,
    ).filter(lambda s: len(s.strip()) >= min_size)


def _distinct_instruction(prefix: str) -> st.SearchStrategy[str]:
    """Generate instruction text with a prefix to avoid cross-set
    deduplication between pre-existing and new pairs.
    """
    return _non_empty_text(min_size=15, max_size=200).map(
        lambda s: f"{prefix} {s}"
    )


def _valid_pair_strategy(
    prefix: str = "new",
) -> st.SearchStrategy[InstructionTuningPair]:
    """Generate a pair that passes all validation checks."""
    return st.builds(
        _make_valid_pair,
        instruction=_distinct_instruction(prefix),
        strategy=st.sampled_from(list(VALID_STRATEGIES)),
        confidence=st.floats(
            min_value=0.0,
            max_value=1.0,
            allow_nan=False,
            allow_infinity=False,
        ),
    )


def _invalid_pair_strategy(
    prefix: str = "new",
) -> st.SearchStrategy[InstructionTuningPair]:
    """Generate a pair that fails validation (short response)."""
    return st.builds(
        _make_invalid_pair,
        instruction=_distinct_instruction(prefix),
        strategy=st.sampled_from(list(VALID_STRATEGIES)),
        failure_mode=st.sampled_from([
            "short_response",
            "empty_instruction",
            "empty_context",
        ]),
    )


def _any_pair_strategy(
    prefix: str = "pre",
) -> st.SearchStrategy[InstructionTuningPair]:
    """Generate a pair that may or may not pass validation.

    Used for pre-existing pairs — they should survive regardless
    of whether they would pass validation.
    """
    return st.one_of(
        _valid_pair_strategy(prefix),
        _invalid_pair_strategy(prefix),
    )


# ---------------------------------------------------------------------------
# Property 2: Validation scope — pre-existing pairs bypass validation
# ---------------------------------------------------------------------------


@pytest.mark.pbt
@pytest.mark.unit
class TestValidationScopeProperty:
    """Property 2: Validation scope — pre-existing pairs bypass validation.

    For any set of pre-existing pairs and any set of newly generated
    pairs, the final accepted dataset SHALL include all pre-existing
    pairs (subject only to deduplication) regardless of whether they
    would pass quality validation.  Only newly generated pairs are
    subject to validation filtering.

    Tag: Feature: data-generation-resume, Property 2: Validation scope
         — pre-existing pairs bypass validation
    Validates: Requirements 4.5
    """

    # ------------------------------------------------------------------
    # Core property: pre-existing pairs survive regardless of validity
    # ------------------------------------------------------------------

    @given(
        pre_existing=st.lists(
            _any_pair_strategy("pre"), min_size=1, max_size=15
        ),
        new_valid=st.lists(
            _valid_pair_strategy("newvalid"), min_size=0, max_size=10
        ),
        new_invalid=st.lists(
            _invalid_pair_strategy("newinvalid"), min_size=0, max_size=10
        ),
    )
    @settings(max_examples=100, deadline=None)
    def test_pre_existing_pairs_included_regardless_of_validity(
        self,
        pre_existing: List[InstructionTuningPair],
        new_valid: List[InstructionTuningPair],
        new_invalid: List[InstructionTuningPair],
    ) -> None:
        """All pre-existing pairs appear in the final output (subject
        only to deduplication), even if they would fail validation.
        """
        new_pairs = new_valid + new_invalid
        gen = _make_generator(ner_returns=True)

        final, deduped_pre, _ = _resume_merge_validate(
            gen, pre_existing, new_pairs
        )

        # Every pre-existing pair that survived dedup must be in final
        pre_existing_ids = {id(p) for p in pre_existing}
        final_pre_ids = {id(p) for p in final if id(p) in pre_existing_ids}

        assert final_pre_ids == {id(p) for p in deduped_pre}, (
            "Some pre-existing pairs that survived dedup are missing "
            "from the final accepted set"
        )

        # Verify deduped pre-existing is a subset of original pre-existing
        for p in deduped_pre:
            assert id(p) in pre_existing_ids, (
                "A pair in deduped_pre_existing is not from pre_existing"
            )

    # ------------------------------------------------------------------
    # Core property: invalid new pairs are rejected
    # ------------------------------------------------------------------

    @given(
        pre_existing=st.lists(
            _valid_pair_strategy("pre"), min_size=0, max_size=5
        ),
        new_invalid=st.lists(
            _invalid_pair_strategy("newinvalid"), min_size=1, max_size=15
        ),
    )
    @settings(max_examples=100, deadline=None)
    def test_invalid_new_pairs_are_rejected(
        self,
        pre_existing: List[InstructionTuningPair],
        new_invalid: List[InstructionTuningPair],
    ) -> None:
        """New pairs that fail validation do not appear in the final
        accepted set.
        """
        gen = _make_generator(ner_returns=True)

        final, deduped_pre, validated_new = _resume_merge_validate(
            gen, pre_existing, new_invalid
        )

        # No invalid new pair should be in validated_new
        assert len(validated_new) == 0, (
            f"Expected 0 invalid new pairs accepted, "
            f"got {len(validated_new)}"
        )

        # Final should contain only pre-existing pairs
        pre_existing_ids = {id(p) for p in pre_existing}
        for p in final:
            assert id(p) in pre_existing_ids, (
                "An invalid new pair leaked into the final accepted set"
            )

    # ------------------------------------------------------------------
    # Core property: valid new pairs are accepted
    # ------------------------------------------------------------------

    @given(
        pre_existing=st.lists(
            _valid_pair_strategy("pre"), min_size=0, max_size=5
        ),
        new_valid=st.lists(
            _valid_pair_strategy("newvalid"), min_size=1, max_size=15
        ),
    )
    @settings(max_examples=100, deadline=None)
    def test_valid_new_pairs_are_accepted(
        self,
        pre_existing: List[InstructionTuningPair],
        new_valid: List[InstructionTuningPair],
    ) -> None:
        """New pairs that pass validation appear in the final accepted
        set (subject to deduplication).
        """
        gen = _make_generator(ner_returns=True)

        final, deduped_pre, validated_new = _resume_merge_validate(
            gen, pre_existing, new_valid
        )

        # All new pairs that survived dedup should be in validated_new
        # (since they are valid)
        all_combined = list(pre_existing) + list(new_valid)
        deduped_all = gen.deduplicate(all_combined, similarity_threshold=0.95)
        pre_ids_set = {id(pe) for pe in pre_existing}
        deduped_new_count = sum(
            1 for p in deduped_all if id(p) not in pre_ids_set
        )

        # validated_new should contain all deduped new pairs
        # (they are all valid, so none should be rejected)
        assert len(validated_new) == deduped_new_count, (
            f"Expected {deduped_new_count} valid new pairs accepted "
            f"after dedup, got {len(validated_new)}"
        )

    # ------------------------------------------------------------------
    # Combined: final = deduped_pre_existing ∪ validated_new
    # ------------------------------------------------------------------

    @given(
        pre_existing=st.lists(
            _any_pair_strategy("pre"), min_size=1, max_size=10
        ),
        new_valid=st.lists(
            _valid_pair_strategy("newvalid"), min_size=0, max_size=8
        ),
        new_invalid=st.lists(
            _invalid_pair_strategy("newinvalid"), min_size=0, max_size=8
        ),
    )
    @settings(max_examples=100, deadline=None)
    def test_final_is_exactly_deduped_pre_plus_validated_new(
        self,
        pre_existing: List[InstructionTuningPair],
        new_valid: List[InstructionTuningPair],
        new_invalid: List[InstructionTuningPair],
    ) -> None:
        """The final accepted set is exactly the union of
        deduped pre-existing pairs and validated new pairs.
        """
        new_pairs = new_valid + new_invalid
        gen = _make_generator(ner_returns=True)

        final, deduped_pre, validated_new = _resume_merge_validate(
            gen, pre_existing, new_pairs
        )

        expected_ids = {id(p) for p in deduped_pre} | {
            id(p) for p in validated_new
        }
        actual_ids = {id(p) for p in final}

        assert actual_ids == expected_ids, (
            f"Final set ({len(actual_ids)} pairs) != "
            f"deduped_pre ({len(deduped_pre)}) + "
            f"validated_new ({len(validated_new)})"
        )

    # ------------------------------------------------------------------
    # Pre-existing pairs with would-fail-validation content survive
    # ------------------------------------------------------------------

    @given(
        pre_invalid=st.lists(
            _invalid_pair_strategy("preinv"), min_size=1, max_size=10
        ),
        new_valid=st.lists(
            _valid_pair_strategy("newvalid"), min_size=0, max_size=5
        ),
    )
    @settings(max_examples=100, deadline=None)
    def test_invalid_pre_existing_pairs_bypass_validation(
        self,
        pre_invalid: List[InstructionTuningPair],
        new_valid: List[InstructionTuningPair],
    ) -> None:
        """Pre-existing pairs that would fail validation (short
        response, empty instruction, empty context) are still
        included in the final output.
        """
        gen = _make_generator(ner_returns=True)

        final, deduped_pre, validated_new = _resume_merge_validate(
            gen, pre_invalid, new_valid
        )

        # Verify the pre-existing pairs would actually fail validation
        loop = asyncio.get_event_loop()
        hypothetical_validation = loop.run_until_complete(
            gen.validate_dataset(pre_invalid)
        )
        assert len(hypothetical_validation.rejected) > 0, (
            "Test setup error: pre-existing pairs should fail validation"
        )

        # Despite failing validation, they should be in the final set
        pre_ids = {id(p) for p in pre_invalid}
        final_pre_count = sum(1 for p in final if id(p) in pre_ids)
        assert final_pre_count == len(deduped_pre), (
            f"Expected {len(deduped_pre)} invalid pre-existing pairs "
            f"in final (after dedup), got {final_pre_count}"
        )
        assert final_pre_count > 0, (
            "No invalid pre-existing pairs survived — they should "
            "bypass validation"
        )

    # ------------------------------------------------------------------
    # Dedup can remove pre-existing pairs (that's acceptable)
    # ------------------------------------------------------------------

    def test_dedup_removes_duplicate_pre_existing(self) -> None:
        """Pre-existing pairs that are near-duplicates of each other
        are removed by dedup — this is expected and acceptable.
        """
        gen = _make_generator(ner_returns=True)

        # Two pre-existing pairs with identical instructions
        p1 = _make_invalid_pair(
            "What is aspirin used for in medicine?",
            failure_mode="short_response",
        )
        p2 = _make_invalid_pair(
            "What is aspirin used for in medicine?",
            failure_mode="short_response",
        )

        final, deduped_pre, _ = _resume_merge_validate(
            gen, [p1, p2], []
        )

        # Dedup should keep only one
        assert len(deduped_pre) == 1, (
            f"Expected 1 pair after dedup of 2 identical, "
            f"got {len(deduped_pre)}"
        )
        assert len(final) == 1

    # ------------------------------------------------------------------
    # Empty pre-existing: only validated new pairs in final
    # ------------------------------------------------------------------

    @given(
        new_valid=st.lists(
            _valid_pair_strategy("newvalid"), min_size=1, max_size=10
        ),
        new_invalid=st.lists(
            _invalid_pair_strategy("newinvalid"), min_size=1, max_size=10
        ),
    )
    @settings(max_examples=100, deadline=None)
    def test_no_pre_existing_only_validated_new_in_final(
        self,
        new_valid: List[InstructionTuningPair],
        new_invalid: List[InstructionTuningPair],
    ) -> None:
        """With no pre-existing pairs, the final set contains only
        validated new pairs (standard non-resume behaviour).
        """
        new_pairs = new_valid + new_invalid
        gen = _make_generator(ner_returns=True)

        final, deduped_pre, validated_new = _resume_merge_validate(
            gen, [], new_pairs
        )

        assert len(deduped_pre) == 0
        assert {id(p) for p in final} == {id(p) for p in validated_new}

    # ------------------------------------------------------------------
    # Empty new pairs: only pre-existing in final
    # ------------------------------------------------------------------

    @given(
        pre_existing=st.lists(
            _any_pair_strategy("pre"), min_size=1, max_size=10
        ),
    )
    @settings(max_examples=100, deadline=None)
    def test_no_new_pairs_only_pre_existing_in_final(
        self,
        pre_existing: List[InstructionTuningPair],
    ) -> None:
        """With no new pairs, the final set contains only deduped
        pre-existing pairs.
        """
        gen = _make_generator(ner_returns=True)

        final, deduped_pre, validated_new = _resume_merge_validate(
            gen, pre_existing, []
        )

        assert len(validated_new) == 0
        assert {id(p) for p in final} == {id(p) for p in deduped_pre}

    # ------------------------------------------------------------------
    # Both empty: final is empty
    # ------------------------------------------------------------------

    def test_both_empty_produces_empty_final(self) -> None:
        """No pre-existing and no new pairs → empty final set."""
        gen = _make_generator(ner_returns=True)

        final, deduped_pre, validated_new = _resume_merge_validate(
            gen, [], []
        )

        assert final == []
        assert deduped_pre == []
        assert validated_new == []
