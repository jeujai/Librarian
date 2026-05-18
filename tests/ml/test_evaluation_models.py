"""
Property-based tests for evaluation data models.

# Feature: llm-judge-evaluation, Property 3: Dimension score validation bounds
Validates: Requirements 2.5, 9.5

# Feature: llm-judge-evaluation, Property 2: Judge verdict JSON round-trip
Validates: Requirements 2.2, 11.1, 11.4
"""

from __future__ import annotations

import json

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st
from pydantic import ValidationError

from multimodal_librarian.ml.models import DimensionScores, JudgeVerdict

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

DIMENSION_FIELDS = (
    "factual_accuracy",
    "completeness",
    "clinical_relevance",
    "coherence",
)

VALID_RANGE = st.integers(min_value=1, max_value=5)
BELOW_RANGE = st.integers(max_value=0)
ABOVE_RANGE = st.integers(min_value=6)
OUT_OF_RANGE = st.one_of(BELOW_RANGE, ABOVE_RANGE)


# ---------------------------------------------------------------------------
# Property tests — DimensionScores validation bounds
# ---------------------------------------------------------------------------


class TestDimensionScoresValidationBounds:
    """Property 3: Dimension score validation bounds."""

    @given(
        factual_accuracy=VALID_RANGE,
        completeness=VALID_RANGE,
        clinical_relevance=VALID_RANGE,
        coherence=VALID_RANGE,
    )
    @settings(max_examples=100)
    def test_valid_scores_construct_successfully(
        self,
        factual_accuracy: int,
        completeness: int,
        clinical_relevance: int,
        coherence: int,
    ) -> None:
        """Any four integers in [1, 5] SHALL produce a valid DimensionScores."""
        scores = DimensionScores(
            factual_accuracy=factual_accuracy,
            completeness=completeness,
            clinical_relevance=clinical_relevance,
            coherence=coherence,
        )
        assert scores.factual_accuracy == factual_accuracy
        assert scores.completeness == completeness
        assert scores.clinical_relevance == clinical_relevance
        assert scores.coherence == coherence

    @given(
        factual_accuracy=VALID_RANGE,
        completeness=VALID_RANGE,
        clinical_relevance=VALID_RANGE,
        coherence=VALID_RANGE,
    )
    @settings(max_examples=100)
    def test_all_scores_within_bounds(
        self,
        factual_accuracy: int,
        completeness: int,
        clinical_relevance: int,
        coherence: int,
    ) -> None:
        """Every field on a valid DimensionScores is in [1, 5]."""
        scores = DimensionScores(
            factual_accuracy=factual_accuracy,
            completeness=completeness,
            clinical_relevance=clinical_relevance,
            coherence=coherence,
        )
        for field_name in DIMENSION_FIELDS:
            value = getattr(scores, field_name)
            assert 1 <= value <= 5, (
                f"{field_name}={value} is outside [1, 5]"
            )

    @given(bad_value=OUT_OF_RANGE)
    @settings(max_examples=100)
    @pytest.mark.parametrize("field_name", DIMENSION_FIELDS)
    def test_out_of_range_in_single_field_raises(
        self,
        field_name: str,
        bad_value: int,
    ) -> None:
        """An out-of-range value in any single field SHALL raise ValidationError."""
        kwargs = {f: 3 for f in DIMENSION_FIELDS}  # all valid defaults
        kwargs[field_name] = bad_value
        with pytest.raises(ValidationError):
            DimensionScores(**kwargs)

    @given(
        bad_fa=OUT_OF_RANGE,
        bad_co=OUT_OF_RANGE,
        bad_cr=OUT_OF_RANGE,
        bad_ch=OUT_OF_RANGE,
    )
    @settings(max_examples=100)
    def test_all_fields_out_of_range_raises(
        self,
        bad_fa: int,
        bad_co: int,
        bad_cr: int,
        bad_ch: int,
    ) -> None:
        """All four fields out of range SHALL raise ValidationError."""
        with pytest.raises(ValidationError):
            DimensionScores(
                factual_accuracy=bad_fa,
                completeness=bad_co,
                clinical_relevance=bad_cr,
                coherence=bad_ch,
            )

    def test_boundary_values_lower(self) -> None:
        """Score of 1 (lower bound) is accepted for all fields."""
        scores = DimensionScores(
            factual_accuracy=1,
            completeness=1,
            clinical_relevance=1,
            coherence=1,
        )
        for field_name in DIMENSION_FIELDS:
            assert getattr(scores, field_name) == 1

    def test_boundary_values_upper(self) -> None:
        """Score of 5 (upper bound) is accepted for all fields."""
        scores = DimensionScores(
            factual_accuracy=5,
            completeness=5,
            clinical_relevance=5,
            coherence=5,
        )
        for field_name in DIMENSION_FIELDS:
            assert getattr(scores, field_name) == 5

    def test_just_below_lower_bound_rejected(self) -> None:
        """Score of 0 (just below lower bound) is rejected."""
        with pytest.raises(ValidationError):
            DimensionScores(
                factual_accuracy=0,
                completeness=3,
                clinical_relevance=3,
                coherence=3,
            )

    def test_just_above_upper_bound_rejected(self) -> None:
        """Score of 6 (just above upper bound) is rejected."""
        with pytest.raises(ValidationError):
            DimensionScores(
                factual_accuracy=3,
                completeness=6,
                clinical_relevance=3,
                coherence=3,
            )

    def test_non_integer_type_rejected(self) -> None:
        """Non-integer types (float, string) are rejected or coerced."""
        # Pydantic v2 coerces float to int if strict mode is off,
        # but strings like "high" should fail.
        with pytest.raises(ValidationError):
            DimensionScores(
                factual_accuracy="high",  # type: ignore[arg-type]
                completeness=3,
                clinical_relevance=3,
                coherence=3,
            )

    def test_missing_field_rejected(self) -> None:
        """Omitting a required field SHALL raise ValidationError."""
        with pytest.raises(ValidationError):
            DimensionScores(
                factual_accuracy=3,
                completeness=3,
                clinical_relevance=3,
                # coherence omitted
            )


# ---------------------------------------------------------------------------
# Hypothesis strategies for JudgeVerdict generation
# ---------------------------------------------------------------------------

dimension_scores_strategy = st.builds(
    DimensionScores,
    factual_accuracy=VALID_RANGE,
    completeness=VALID_RANGE,
    clinical_relevance=VALID_RANGE,
    coherence=VALID_RANGE,
)

VALID_WINNERS = st.sampled_from(["A", "B", "TIE"])

# Use text() with a reasonable alphabet to cover unicode edge cases
# while keeping strings parseable (no null bytes).
explanation_strategy = st.text(
    alphabet=st.characters(
        blacklist_categories=("Cs",),  # exclude surrogates
    ),
    min_size=0,
    max_size=200,
)

judge_verdict_strategy = st.builds(
    JudgeVerdict,
    response_a_scores=dimension_scores_strategy,
    response_b_scores=dimension_scores_strategy,
    winner=VALID_WINNERS,
    explanation=explanation_strategy,
)


# ---------------------------------------------------------------------------
# Property tests — JudgeVerdict JSON round-trip (Property 2)
# ---------------------------------------------------------------------------


class TestJudgeVerdictRoundTrip:
    """
    # Feature: llm-judge-evaluation, Property 2: Judge verdict JSON round-trip

    Validates: Requirements 2.2, 11.1, 11.4

    Property 2 states: For any valid JudgeVerdict object (with dimension
    scores in [1,5], winner in {"A","B","TIE"}, and arbitrary explanation
    text), serializing it to JSON and then parsing that JSON string SHALL
    produce a JudgeVerdict equivalent to the original. Furthermore,
    serializing the parsed result back to JSON and re-parsing SHALL also
    produce an equivalent object.
    """

    @given(verdict=judge_verdict_strategy)
    @settings(max_examples=100)
    def test_single_round_trip(
        self,
        verdict: JudgeVerdict,
    ) -> None:
        """Serialize → deserialize produces an equivalent JudgeVerdict."""
        json_str = verdict.model_dump_json()
        restored = JudgeVerdict.model_validate_json(json_str)

        assert restored.response_a_scores == verdict.response_a_scores
        assert restored.response_b_scores == verdict.response_b_scores
        assert restored.winner == verdict.winner
        assert restored.explanation == verdict.explanation

    @given(verdict=judge_verdict_strategy)
    @settings(max_examples=100)
    def test_double_round_trip(
        self,
        verdict: JudgeVerdict,
    ) -> None:
        """Serialize → deserialize → serialize → deserialize is stable."""
        json_str_1 = verdict.model_dump_json()
        restored_1 = JudgeVerdict.model_validate_json(json_str_1)

        json_str_2 = restored_1.model_dump_json()
        restored_2 = JudgeVerdict.model_validate_json(json_str_2)

        assert restored_2.response_a_scores == verdict.response_a_scores
        assert restored_2.response_b_scores == verdict.response_b_scores
        assert restored_2.winner == verdict.winner
        assert restored_2.explanation == verdict.explanation

    @given(verdict=judge_verdict_strategy)
    @settings(max_examples=100)
    def test_json_string_is_valid_json(
        self,
        verdict: JudgeVerdict,
    ) -> None:
        """The serialized output is always valid JSON."""
        json_str = verdict.model_dump_json()
        parsed = json.loads(json_str)
        assert isinstance(parsed, dict)

    @given(verdict=judge_verdict_strategy)
    @settings(max_examples=100)
    def test_round_trip_preserves_all_dimension_scores(
        self,
        verdict: JudgeVerdict,
    ) -> None:
        """Each dimension score survives the round-trip unchanged."""
        json_str = verdict.model_dump_json()
        restored = JudgeVerdict.model_validate_json(json_str)

        for field_name in DIMENSION_FIELDS:
            orig_a = getattr(
                verdict.response_a_scores, field_name,
            )
            rest_a = getattr(
                restored.response_a_scores, field_name,
            )
            assert orig_a == rest_a, (
                f"response_a_scores.{field_name}: "
                f"{orig_a} != {rest_a}"
            )

            orig_b = getattr(
                verdict.response_b_scores, field_name,
            )
            rest_b = getattr(
                restored.response_b_scores, field_name,
            )
            assert orig_b == rest_b, (
                f"response_b_scores.{field_name}: "
                f"{orig_b} != {rest_b}"
            )

    @given(verdict=judge_verdict_strategy)
    @settings(max_examples=100)
    def test_round_trip_via_dict(
        self,
        verdict: JudgeVerdict,
    ) -> None:
        """Round-trip through model_dump dict also preserves equality."""
        d = verdict.model_dump()
        restored = JudgeVerdict.model_validate(d)

        assert restored.response_a_scores == verdict.response_a_scores
        assert restored.response_b_scores == verdict.response_b_scores
        assert restored.winner == verdict.winner
        assert restored.explanation == verdict.explanation

    @given(verdict=judge_verdict_strategy)
    @settings(max_examples=100)
    def test_winner_stays_normalized_after_round_trip(
        self,
        verdict: JudgeVerdict,
    ) -> None:
        """Winner is always uppercase A, B, or TIE after round-trip."""
        json_str = verdict.model_dump_json()
        restored = JudgeVerdict.model_validate_json(json_str)
        assert restored.winner in ("A", "B", "TIE")


# ---------------------------------------------------------------------------
# Hypothesis strategy for invalid winner strings
# ---------------------------------------------------------------------------

# Generate arbitrary text that is NOT case-insensitively "A", "B", or "TIE".
_invalid_winner_strategy = st.text(min_size=0, max_size=50).filter(
    lambda s: s.strip().upper() not in ("A", "B", "TIE")
)


# ---------------------------------------------------------------------------
# Property tests — Invalid winner defaults to tie (Property 12)
# ---------------------------------------------------------------------------


class TestInvalidWinnerDefaultsToTie:
    """
    # Feature: llm-judge-evaluation, Property 12: Invalid winner defaults
    # to tie

    Validates: Requirements 11.3

    Property 12 states: For any string that is not case-insensitively
    equal to "A", "B", or "tie", the JudgeVerdict winner validator SHALL
    normalize it to "TIE".
    """

    @given(
        invalid_winner=_invalid_winner_strategy,
        response_a_scores=dimension_scores_strategy,
        response_b_scores=dimension_scores_strategy,
    )
    @settings(max_examples=100)
    def test_invalid_winner_normalized_to_tie(
        self,
        invalid_winner: str,
        response_a_scores: DimensionScores,
        response_b_scores: DimensionScores,
    ) -> None:
        """Any unrecognized winner string SHALL be normalized to TIE."""
        verdict = JudgeVerdict(
            response_a_scores=response_a_scores,
            response_b_scores=response_b_scores,
            winner=invalid_winner,
            explanation="test",
        )
        assert verdict.winner == "TIE"

    @given(
        invalid_winner=_invalid_winner_strategy,
        response_a_scores=dimension_scores_strategy,
        response_b_scores=dimension_scores_strategy,
    )
    @settings(max_examples=100)
    def test_invalid_winner_round_trips_as_tie(
        self,
        invalid_winner: str,
        response_a_scores: DimensionScores,
        response_b_scores: DimensionScores,
    ) -> None:
        """An invalid winner normalized to TIE stays TIE after round-trip."""
        verdict = JudgeVerdict(
            response_a_scores=response_a_scores,
            response_b_scores=response_b_scores,
            winner=invalid_winner,
            explanation="test",
        )
        json_str = verdict.model_dump_json()
        restored = JudgeVerdict.model_validate_json(json_str)
        assert restored.winner == "TIE"

    @pytest.mark.parametrize(
        "invalid_value",
        [
            "",
            "C",
            "D",
            "winner",
            "DRAW",
            "none",
            "both",
            "neither",
            "AB",
            "ties",
            "  ",
            "a b",
            "TIE!",
            "123",
        ],
    )
    def test_specific_invalid_winners_become_tie(
        self,
        invalid_value: str,
    ) -> None:
        """Specific known-invalid winner strings all become TIE."""
        scores = DimensionScores(
            factual_accuracy=3,
            completeness=3,
            clinical_relevance=3,
            coherence=3,
        )
        verdict = JudgeVerdict(
            response_a_scores=scores,
            response_b_scores=scores,
            winner=invalid_value,
            explanation="test",
        )
        assert verdict.winner == "TIE"

    @pytest.mark.parametrize(
        "valid_value,expected",
        [
            ("A", "A"),
            ("a", "A"),
            ("  a  ", "A"),
            ("B", "B"),
            ("b", "B"),
            ("  b  ", "B"),
            ("TIE", "TIE"),
            ("tie", "TIE"),
            ("Tie", "TIE"),
            ("  tie  ", "TIE"),
        ],
    )
    def test_valid_winners_are_not_overridden(
        self,
        valid_value: str,
        expected: str,
    ) -> None:
        """Valid winner values (case-insensitive) are normalized, not defaulted."""
        scores = DimensionScores(
            factual_accuracy=3,
            completeness=3,
            clinical_relevance=3,
            coherence=3,
        )
        verdict = JudgeVerdict(
            response_a_scores=scores,
            response_b_scores=scores,
            winner=valid_value,
            explanation="test",
        )
        assert verdict.winner == expected
