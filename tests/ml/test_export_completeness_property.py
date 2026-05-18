"""
Property-based tests for export completeness after resume.

# Feature: data-generation-resume, Property 3: Export completeness
#   after resume

Validates: Requirements 4.3, 4.6

Property 3 states: For any set of pre-existing pairs and any set of
new pairs, the exported JSONL file SHALL contain exactly the union of
(all pre-existing pairs that survive deduplication) and (all new pairs
that survive both deduplication and validation), with no pairs lost or
invented.

The test exercises the merge → dedup → partition → validate → export →
parse round-trip, verifying that the JSONL file on disk faithfully
represents the expected final dataset.
"""

from __future__ import annotations

import asyncio
import string
import tempfile
from pathlib import Path
from typing import List, Set, Tuple
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


def _resume_merge_validate_export(
    gen: TrainingDataGenerator,
    pre_existing: List[InstructionTuningPair],
    new_pairs: List[InstructionTuningPair],
    output_path: Path,
    similarity_threshold: float = 0.95,
    seed: int = 42,
) -> Tuple[
    List[InstructionTuningPair],
    List[InstructionTuningPair],
    List[InstructionTuningPair],
]:
    """Replicate the merge → dedup → partition → validate → export
    logic from ``generate()`` and write the result to a JSONL file.

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

    # Export to JSONL (same as generate())
    gen.export_jsonl(final_accepted, output_path, seed=seed)

    return final_accepted, deduped_pre_existing, validation.accepted


def _pair_identity(pair: InstructionTuningPair) -> Tuple:
    """Return a hashable identity tuple for content-based comparison.

    Used to compare pairs across the export → parse round-trip where
    object identity (``id()``) is lost.
    """
    return (
        pair.instruction,
        pair.context,
        pair.response,
        pair.metadata.strategy,
        tuple(sorted(pair.metadata.source_concepts)),
        pair.metadata.confidence_score,
    )


def _pair_identity_set(
    pairs: List[InstructionTuningPair],
) -> Set[Tuple]:
    """Build a set of content-based identity tuples from a list of pairs."""
    return {_pair_identity(p) for p in pairs}


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
# Property 3: Export completeness after resume
# ---------------------------------------------------------------------------


@pytest.mark.pbt
@pytest.mark.unit
class TestExportCompletenessProperty:
    """Property 3: Export completeness after resume.

    For any set of pre-existing and new pairs, the exported JSONL file
    SHALL contain exactly the union of (pre-existing pairs surviving
    dedup) and (new pairs surviving both dedup and validation), with
    no pairs lost or invented.

    Tag: Feature: data-generation-resume, Property 3: Export
         completeness after resume
    Validates: Requirements 4.3, 4.6
    """

    # ------------------------------------------------------------------
    # Core property: exported JSONL matches expected final set
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
    def test_exported_jsonl_matches_expected_final_set(
        self,
        pre_existing: List[InstructionTuningPair],
        new_valid: List[InstructionTuningPair],
        new_invalid: List[InstructionTuningPair],
    ) -> None:
        """The exported JSONL file contains exactly the expected pairs
        after merge → dedup → validate, with no pairs lost or invented.
        """
        new_pairs = new_valid + new_invalid
        gen = _make_generator(ner_returns=True)

        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / "training_data.jsonl"

            final, deduped_pre, validated_new = (
                _resume_merge_validate_export(
                    gen, pre_existing, new_pairs, output_path
                )
            )

            # Parse the exported JSONL back
            parsed = TrainingDataGenerator.parse_jsonl(output_path)

            # Content-based comparison (object identity is lost after
            # serialize → deserialize round-trip)
            expected_identities = _pair_identity_set(final)
            parsed_identities = _pair_identity_set(parsed)

            assert parsed_identities == expected_identities, (
                f"Exported JSONL content mismatch: "
                f"expected {len(expected_identities)} unique pairs, "
                f"got {len(parsed_identities)}. "
                f"Missing: {expected_identities - parsed_identities}, "
                f"Extra: {parsed_identities - expected_identities}"
            )

    # ------------------------------------------------------------------
    # Pair count: exported file has correct number of lines
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
    def test_exported_pair_count_matches_final_accepted(
        self,
        pre_existing: List[InstructionTuningPair],
        new_valid: List[InstructionTuningPair],
        new_invalid: List[InstructionTuningPair],
    ) -> None:
        """The number of lines in the exported JSONL equals the number
        of pairs in the final accepted set.
        """
        new_pairs = new_valid + new_invalid
        gen = _make_generator(ner_returns=True)

        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / "training_data.jsonl"

            final, _, _ = _resume_merge_validate_export(
                gen, pre_existing, new_pairs, output_path
            )

            parsed = TrainingDataGenerator.parse_jsonl(output_path)

            assert len(parsed) == len(final), (
                f"Expected {len(final)} pairs in JSONL, "
                f"got {len(parsed)}"
            )

    # ------------------------------------------------------------------
    # No invented pairs: every parsed pair exists in the input
    # ------------------------------------------------------------------

    @given(
        pre_existing=st.lists(
            _any_pair_strategy("pre"), min_size=1, max_size=10
        ),
        new_valid=st.lists(
            _valid_pair_strategy("newvalid"), min_size=1, max_size=8
        ),
        new_invalid=st.lists(
            _invalid_pair_strategy("newinvalid"), min_size=0, max_size=5
        ),
    )
    @settings(max_examples=100, deadline=None)
    def test_no_invented_pairs_in_export(
        self,
        pre_existing: List[InstructionTuningPair],
        new_valid: List[InstructionTuningPair],
        new_invalid: List[InstructionTuningPair],
    ) -> None:
        """Every pair in the exported JSONL must originate from either
        the pre-existing set or the new pairs set — no pairs are
        invented during the pipeline.
        """
        new_pairs = new_valid + new_invalid
        gen = _make_generator(ner_returns=True)

        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / "training_data.jsonl"

            _resume_merge_validate_export(
                gen, pre_existing, new_pairs, output_path
            )

            parsed = TrainingDataGenerator.parse_jsonl(output_path)

            # All input pairs (before any filtering)
            all_input_identities = _pair_identity_set(
                pre_existing + new_pairs
            )
            parsed_identities = _pair_identity_set(parsed)

            invented = parsed_identities - all_input_identities
            assert not invented, (
                f"Found {len(invented)} invented pairs in export "
                f"that don't exist in any input set"
            )

    # ------------------------------------------------------------------
    # No lost pairs: every expected pair appears in the export
    # ------------------------------------------------------------------

    @given(
        pre_existing=st.lists(
            _any_pair_strategy("pre"), min_size=1, max_size=10
        ),
        new_valid=st.lists(
            _valid_pair_strategy("newvalid"), min_size=1, max_size=8
        ),
    )
    @settings(max_examples=100, deadline=None)
    def test_no_lost_pairs_in_export(
        self,
        pre_existing: List[InstructionTuningPair],
        new_valid: List[InstructionTuningPair],
    ) -> None:
        """Every pair that should be in the final set (deduped
        pre-existing + validated new) actually appears in the
        exported JSONL — no pairs are silently dropped.
        """
        gen = _make_generator(ner_returns=True)

        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / "training_data.jsonl"

            final, deduped_pre, validated_new = (
                _resume_merge_validate_export(
                    gen, pre_existing, new_valid, output_path
                )
            )

            parsed = TrainingDataGenerator.parse_jsonl(output_path)

            expected_identities = _pair_identity_set(final)
            parsed_identities = _pair_identity_set(parsed)

            lost = expected_identities - parsed_identities
            assert not lost, (
                f"Found {len(lost)} pairs missing from export that "
                f"should have been included"
            )

    # ------------------------------------------------------------------
    # Invalid new pairs excluded from export
    # ------------------------------------------------------------------

    @given(
        pre_existing=st.lists(
            _valid_pair_strategy("pre"), min_size=0, max_size=5
        ),
        new_invalid=st.lists(
            _invalid_pair_strategy("newinvalid"), min_size=1, max_size=10
        ),
    )
    @settings(max_examples=100, deadline=None)
    def test_invalid_new_pairs_excluded_from_export(
        self,
        pre_existing: List[InstructionTuningPair],
        new_invalid: List[InstructionTuningPair],
    ) -> None:
        """New pairs that fail validation do not appear in the
        exported JSONL file.
        """
        gen = _make_generator(ner_returns=True)

        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / "training_data.jsonl"

            final, deduped_pre, validated_new = (
                _resume_merge_validate_export(
                    gen, pre_existing, new_invalid, output_path
                )
            )

            parsed = TrainingDataGenerator.parse_jsonl(output_path)
            parsed_identities = _pair_identity_set(parsed)

            # None of the invalid new pairs should be in the export
            # (unless they happen to share content with a pre-existing
            # pair, which the prefix strategy makes unlikely)
            invalid_identities = _pair_identity_set(new_invalid)
            pre_identities = _pair_identity_set(pre_existing)
            truly_leaked = (
                parsed_identities & invalid_identities
            ) - pre_identities
            assert not truly_leaked, (
                f"Found {len(truly_leaked)} invalid new pairs "
                f"in export"
            )

    # ------------------------------------------------------------------
    # Pre-existing invalid pairs present in export
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
    def test_invalid_pre_existing_pairs_present_in_export(
        self,
        pre_invalid: List[InstructionTuningPair],
        new_valid: List[InstructionTuningPair],
    ) -> None:
        """Pre-existing pairs that would fail validation still appear
        in the exported JSONL — they bypass validation.
        """
        gen = _make_generator(ner_returns=True)

        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / "training_data.jsonl"

            final, deduped_pre, _ = _resume_merge_validate_export(
                gen, pre_invalid, new_valid, output_path
            )

            parsed = TrainingDataGenerator.parse_jsonl(output_path)
            parsed_identities = _pair_identity_set(parsed)

            # All deduped pre-existing pairs should be in the export
            deduped_pre_identities = _pair_identity_set(deduped_pre)
            missing = deduped_pre_identities - parsed_identities
            assert not missing, (
                f"Found {len(missing)} pre-existing pairs missing "
                f"from export — they should bypass validation"
            )

    # ------------------------------------------------------------------
    # JSONL round-trip preserves pair content
    # ------------------------------------------------------------------

    @given(
        pairs=st.lists(
            _valid_pair_strategy("rt"), min_size=1, max_size=15
        ),
    )
    @settings(max_examples=100, deadline=None)
    def test_jsonl_round_trip_preserves_content(
        self,
        pairs: List[InstructionTuningPair],
    ) -> None:
        """Pairs written to JSONL and parsed back have identical
        content — the export → parse round-trip is lossless.
        """
        gen = _make_generator(ner_returns=True)

        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / "round_trip.jsonl"

            gen.export_jsonl(pairs, output_path, seed=42)
            parsed = TrainingDataGenerator.parse_jsonl(output_path)

            original_identities = _pair_identity_set(pairs)
            parsed_identities = _pair_identity_set(parsed)

            assert parsed_identities == original_identities, (
                f"Round-trip content mismatch: "
                f"lost {original_identities - parsed_identities}, "
                f"gained {parsed_identities - original_identities}"
            )
            assert len(parsed) == len(pairs), (
                f"Round-trip count mismatch: "
                f"{len(pairs)} → {len(parsed)}"
            )

    # ------------------------------------------------------------------
    # Empty inputs: export produces empty file
    # ------------------------------------------------------------------

    def test_both_empty_produces_empty_export(
        self,
        tmp_path: Path,
    ) -> None:
        """No pre-existing and no new pairs → empty JSONL file."""
        gen = _make_generator(ner_returns=True)
        output_path = tmp_path / "training_data.jsonl"

        final, deduped_pre, validated_new = (
            _resume_merge_validate_export(gen, [], [], output_path)
        )

        parsed = TrainingDataGenerator.parse_jsonl(output_path)

        assert parsed == []
        assert final == []
        assert deduped_pre == []
        assert validated_new == []

    # ------------------------------------------------------------------
    # Only pre-existing: export contains only deduped pre-existing
    # ------------------------------------------------------------------

    @given(
        pre_existing=st.lists(
            _any_pair_strategy("pre"), min_size=1, max_size=10
        ),
    )
    @settings(max_examples=100, deadline=None)
    def test_only_pre_existing_export_matches(
        self,
        pre_existing: List[InstructionTuningPair],
    ) -> None:
        """With no new pairs, the export contains exactly the deduped
        pre-existing pairs.
        """
        gen = _make_generator(ner_returns=True)

        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / "training_data.jsonl"

            final, deduped_pre, validated_new = (
                _resume_merge_validate_export(
                    gen, pre_existing, [], output_path
                )
            )

            parsed = TrainingDataGenerator.parse_jsonl(output_path)

            assert len(validated_new) == 0
            assert _pair_identity_set(parsed) == _pair_identity_set(
                deduped_pre
            )

    # ------------------------------------------------------------------
    # Only new pairs: export contains only validated new pairs
    # ------------------------------------------------------------------

    @given(
        new_valid=st.lists(
            _valid_pair_strategy("newvalid"), min_size=1, max_size=10
        ),
        new_invalid=st.lists(
            _invalid_pair_strategy("newinvalid"), min_size=0, max_size=5
        ),
    )
    @settings(max_examples=100, deadline=None)
    def test_only_new_pairs_export_matches(
        self,
        new_valid: List[InstructionTuningPair],
        new_invalid: List[InstructionTuningPair],
    ) -> None:
        """With no pre-existing pairs, the export contains only
        validated new pairs (standard non-resume behaviour).
        """
        new_pairs = new_valid + new_invalid
        gen = _make_generator(ner_returns=True)

        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / "training_data.jsonl"

            final, deduped_pre, validated_new = (
                _resume_merge_validate_export(
                    gen, [], new_pairs, output_path
                )
            )

            parsed = TrainingDataGenerator.parse_jsonl(output_path)

            assert len(deduped_pre) == 0
            assert _pair_identity_set(parsed) == _pair_identity_set(
                validated_new
            )

    # ------------------------------------------------------------------
    # Deterministic shuffle: same seed → same order
    # ------------------------------------------------------------------

    @given(
        pre_existing=st.lists(
            _valid_pair_strategy("pre"), min_size=2, max_size=8
        ),
        new_valid=st.lists(
            _valid_pair_strategy("newvalid"), min_size=2, max_size=8
        ),
    )
    @settings(max_examples=50, deadline=None)
    def test_deterministic_shuffle_with_same_seed(
        self,
        pre_existing: List[InstructionTuningPair],
        new_valid: List[InstructionTuningPair],
    ) -> None:
        """Exporting with the same seed produces the same ordering."""
        gen = _make_generator(ner_returns=True)

        with tempfile.TemporaryDirectory() as tmpdir:
            path_a = Path(tmpdir) / "export_a.jsonl"
            path_b = Path(tmpdir) / "export_b.jsonl"

            _resume_merge_validate_export(
                gen, pre_existing, new_valid, path_a, seed=123
            )
            _resume_merge_validate_export(
                gen, pre_existing, new_valid, path_b, seed=123
            )

            parsed_a = TrainingDataGenerator.parse_jsonl(path_a)
            parsed_b = TrainingDataGenerator.parse_jsonl(path_b)

            # Same seed → identical ordering
            assert len(parsed_a) == len(parsed_b)
            for pa, pb in zip(parsed_a, parsed_b):
                assert _pair_identity(pa) == _pair_identity(pb), (
                    "Same seed produced different ordering"
                )
