"""
Property-based and unit tests for JudgeService.

# Feature: llm-judge-evaluation, Property 1: Prompt construction includes
# all inputs with correct A/B ordering
Validates: Requirements 1.1, 1.2, 3.1

# Feature: llm-judge-evaluation, Property 4: Dimension score clamping
Validates: Requirements 2.6

# Feature: llm-judge-evaluation, Property 5: Winner mapping consistency
Validates: Requirements 3.2
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from multimodal_librarian.ml.judge_service import JudgeParseError, JudgeService

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

# Strategy for non-empty text strings that avoid null bytes (which would
# break string containment checks in pathological ways).  We keep the
# alphabet broad enough to exercise unicode handling while staying
# realistic for medical Q&A content.
_nonempty_text = st.text(
    alphabet=st.characters(
        blacklist_categories=("Cs",),  # exclude surrogates
        blacklist_characters=("\x00",),
    ),
    min_size=1,
    max_size=300,
)


def _make_judge_service() -> JudgeService:
    """Create a JudgeService with a dummy DeepSeek service.

    Only prompt-construction methods are exercised, so the
    DeepSeek service is never called.
    """
    mock_deepseek = MagicMock()
    return JudgeService(deepseek_service=mock_deepseek)


# ---------------------------------------------------------------------------
# Property tests — Prompt construction includes all inputs (Property 1)
# ---------------------------------------------------------------------------


class TestPromptConstructionIncludesAllInputs:
    """
    # Feature: llm-judge-evaluation, Property 1: Prompt construction
    # includes all inputs with correct A/B ordering

    Validates: Requirements 1.1, 1.2, 3.1

    Property 1 states: For any question text, gold answer, base response,
    and fine-tuned response, calling ``build_judge_prompt`` SHALL produce
    a prompt that contains all four input strings, labels them as
    "Response A" and "Response B", and the A/B ordering matches the
    caller's assignment.
    """

    # ------------------------------------------------------------------
    # Core property: all four inputs appear in the prompt
    # ------------------------------------------------------------------

    @given(
        question=_nonempty_text,
        gold_answer=_nonempty_text,
        response_a=_nonempty_text,
        response_b=_nonempty_text,
    )
    @settings(max_examples=100)
    def test_prompt_contains_all_four_inputs(
        self,
        question: str,
        gold_answer: str,
        response_a: str,
        response_b: str,
    ) -> None:
        """The prompt SHALL contain the question, gold answer,
        response_a, and response_b verbatim."""
        service = _make_judge_service()
        prompt = service.build_judge_prompt(
            question=question,
            gold_answer=gold_answer,
            response_a=response_a,
            response_b=response_b,
        )

        assert question in prompt, (
            "Question text not found in prompt"
        )
        assert gold_answer in prompt, (
            "Gold answer not found in prompt"
        )
        assert response_a in prompt, (
            "Response A text not found in prompt"
        )
        assert response_b in prompt, (
            "Response B text not found in prompt"
        )

    # ------------------------------------------------------------------
    # A/B labels are present
    # ------------------------------------------------------------------

    @given(
        question=_nonempty_text,
        gold_answer=_nonempty_text,
        response_a=_nonempty_text,
        response_b=_nonempty_text,
    )
    @settings(max_examples=100)
    def test_prompt_contains_response_a_and_b_labels(
        self,
        question: str,
        gold_answer: str,
        response_a: str,
        response_b: str,
    ) -> None:
        """The prompt SHALL label the two responses as
        "Response A" and "Response B"."""
        service = _make_judge_service()
        prompt = service.build_judge_prompt(
            question=question,
            gold_answer=gold_answer,
            response_a=response_a,
            response_b=response_b,
        )

        assert "Response A" in prompt
        assert "Response B" in prompt

    # ------------------------------------------------------------------
    # Correct ordering: response_a appears under the A label,
    # response_b appears under the B label
    # ------------------------------------------------------------------

    @given(
        question=_nonempty_text,
        gold_answer=_nonempty_text,
        response_a=_nonempty_text,
        response_b=_nonempty_text,
    )
    @settings(max_examples=100)
    def test_response_a_appears_under_a_label(
        self,
        question: str,
        gold_answer: str,
        response_a: str,
        response_b: str,
    ) -> None:
        """response_a SHALL appear after the "Response A" heading
        and before the "Response B" heading in the prompt."""
        service = _make_judge_service()
        prompt = service.build_judge_prompt(
            question=question,
            gold_answer=gold_answer,
            response_a=response_a,
            response_b=response_b,
        )

        a_label_pos = prompt.index("## Response A")
        b_label_pos = prompt.index("## Response B")
        a_text_pos = prompt.index(response_a, a_label_pos)

        assert a_label_pos < a_text_pos < b_label_pos, (
            "response_a should appear between the A and B labels"
        )

    @given(
        question=_nonempty_text,
        gold_answer=_nonempty_text,
        response_a=_nonempty_text,
        response_b=_nonempty_text,
    )
    @settings(max_examples=100)
    def test_response_b_appears_under_b_label(
        self,
        question: str,
        gold_answer: str,
        response_a: str,
        response_b: str,
    ) -> None:
        """response_b SHALL appear after the "Response B" heading."""
        service = _make_judge_service()
        prompt = service.build_judge_prompt(
            question=question,
            gold_answer=gold_answer,
            response_a=response_a,
            response_b=response_b,
        )

        b_label = "## Response B"
        b_label_pos = prompt.index(b_label)
        search_start = b_label_pos + len(b_label)
        b_text_pos = prompt.index(response_b, search_start)

        assert b_text_pos >= search_start, (
            "response_b should appear after the B label"
        )

    # ------------------------------------------------------------------
    # Scoring instructions are present
    # ------------------------------------------------------------------

    @given(
        question=_nonempty_text,
        gold_answer=_nonempty_text,
        response_a=_nonempty_text,
        response_b=_nonempty_text,
    )
    @settings(max_examples=100)
    def test_prompt_contains_scoring_dimensions(
        self,
        question: str,
        gold_answer: str,
        response_a: str,
        response_b: str,
    ) -> None:
        """The prompt SHALL include scoring instructions for all
        four dimensions on a 1-5 scale."""
        service = _make_judge_service()
        prompt = service.build_judge_prompt(
            question=question,
            gold_answer=gold_answer,
            response_a=response_a,
            response_b=response_b,
        )

        prompt_lower = prompt.lower()
        assert "factual accuracy" in prompt_lower
        assert "completeness" in prompt_lower
        assert "clinical relevance" in prompt_lower
        assert "coherence" in prompt_lower
        # Scale instruction
        assert "1" in prompt and "5" in prompt

    # ------------------------------------------------------------------
    # Winner instruction is present
    # ------------------------------------------------------------------

    @given(
        question=_nonempty_text,
        gold_answer=_nonempty_text,
        response_a=_nonempty_text,
        response_b=_nonempty_text,
    )
    @settings(max_examples=100)
    def test_prompt_contains_winner_instruction(
        self,
        question: str,
        gold_answer: str,
        response_a: str,
        response_b: str,
    ) -> None:
        """The prompt SHALL request a winner designation of
        "A", "B", or "tie"."""
        service = _make_judge_service()
        prompt = service.build_judge_prompt(
            question=question,
            gold_answer=gold_answer,
            response_a=response_a,
            response_b=response_b,
        )

        # The prompt should mention all three possible winner values
        assert '"A"' in prompt
        assert '"B"' in prompt
        assert '"tie"' in prompt

    # ------------------------------------------------------------------
    # JSON format instruction is present
    # ------------------------------------------------------------------

    @given(
        question=_nonempty_text,
        gold_answer=_nonempty_text,
        response_a=_nonempty_text,
        response_b=_nonempty_text,
    )
    @settings(max_examples=100)
    def test_prompt_requests_json_output(
        self,
        question: str,
        gold_answer: str,
        response_a: str,
        response_b: str,
    ) -> None:
        """The prompt SHALL request a structured JSON response."""
        service = _make_judge_service()
        prompt = service.build_judge_prompt(
            question=question,
            gold_answer=gold_answer,
            response_a=response_a,
            response_b=response_b,
        )

        assert "json" in prompt.lower()
        assert "response_a_scores" in prompt
        assert "response_b_scores" in prompt
        assert "winner" in prompt
        assert "explanation" in prompt

    # ------------------------------------------------------------------
    # Position label correctness via judge_pair's A/B assignment
    # ------------------------------------------------------------------

    @given(
        question=_nonempty_text,
        gold_answer=_nonempty_text,
        base_response=_nonempty_text,
        finetuned_response=_nonempty_text,
    )
    @settings(max_examples=100)
    def test_base_is_a_ordering(
        self,
        question: str,
        gold_answer: str,
        base_response: str,
        finetuned_response: str,
    ) -> None:
        """When base is assigned to A, the prompt SHALL place the
        base response under the A label and the finetuned response
        under the B label."""
        service = _make_judge_service()

        # Simulate the base_is_A assignment from judge_pair
        prompt = service.build_judge_prompt(
            question=question,
            gold_answer=gold_answer,
            response_a=base_response,       # base → A
            response_b=finetuned_response,  # finetuned → B
        )

        a_label_pos = prompt.index("## Response A")
        b_label_pos = prompt.index("## Response B")

        # Base response appears in the A section
        base_pos = prompt.index(base_response, a_label_pos)
        assert a_label_pos < base_pos < b_label_pos

        # Finetuned response appears in the B section
        ft_pos = prompt.index(finetuned_response, b_label_pos)
        assert ft_pos > b_label_pos

    @given(
        question=_nonempty_text,
        gold_answer=_nonempty_text,
        base_response=_nonempty_text,
        finetuned_response=_nonempty_text,
    )
    @settings(max_examples=100)
    def test_base_is_b_ordering(
        self,
        question: str,
        gold_answer: str,
        base_response: str,
        finetuned_response: str,
    ) -> None:
        """When base is assigned to B, the prompt SHALL place the
        finetuned response under the A label and the base response
        under the B label."""
        service = _make_judge_service()

        # Simulate the base_is_B assignment from judge_pair
        prompt = service.build_judge_prompt(
            question=question,
            gold_answer=gold_answer,
            response_a=finetuned_response,  # finetuned → A
            response_b=base_response,       # base → B
        )

        a_label_pos = prompt.index("## Response A")
        b_label_pos = prompt.index("## Response B")

        # Finetuned response appears in the A section
        ft_pos = prompt.index(finetuned_response, a_label_pos)
        assert a_label_pos < ft_pos < b_label_pos

        # Base response appears in the B section
        base_pos = prompt.index(base_response, b_label_pos)
        assert base_pos > b_label_pos


# ---------------------------------------------------------------------------
# Property tests — Dimension score clamping (Property 4)
# ---------------------------------------------------------------------------


class TestDimensionScoreClamping:
    """
    # Feature: llm-judge-evaluation, Property 4: Dimension score clamping

    Validates: Requirements 2.6

    Property 4 states: For any integer value, the clamping function
    SHALL produce ``max(1, min(5, value))``. The clamped result is
    always in [1, 5].
    """

    # ------------------------------------------------------------------
    # Core property: clamped result equals max(1, min(5, value))
    # ------------------------------------------------------------------

    @given(value=st.integers(min_value=-1000, max_value=1000))
    @settings(max_examples=100)
    def test_clamp_equals_max_min_formula(self, value: int) -> None:
        """For any integer, _clamp_score SHALL return
        max(1, min(5, value))."""
        expected = max(1, min(5, value))
        result = JudgeService._clamp_score(value, "test_field")
        assert result == expected

    # ------------------------------------------------------------------
    # Clamped result is always in [1, 5]
    # ------------------------------------------------------------------

    @given(value=st.integers(min_value=-10_000, max_value=10_000))
    @settings(max_examples=100)
    def test_clamped_result_always_in_valid_range(
        self, value: int
    ) -> None:
        """The clamped result SHALL always be in [1, 5]."""
        result = JudgeService._clamp_score(value, "test_field")
        assert 1 <= result <= 5

    # ------------------------------------------------------------------
    # Values already in [1, 5] are returned unchanged
    # ------------------------------------------------------------------

    @given(value=st.integers(min_value=1, max_value=5))
    @settings(max_examples=100)
    def test_in_range_values_unchanged(self, value: int) -> None:
        """Values in [1, 5] SHALL pass through unchanged."""
        result = JudgeService._clamp_score(value, "test_field")
        assert result == value

    # ------------------------------------------------------------------
    # Values below 1 are clamped to 1
    # ------------------------------------------------------------------

    @given(value=st.integers(max_value=0))
    @settings(max_examples=100)
    def test_below_range_clamped_to_one(self, value: int) -> None:
        """Values below 1 SHALL be clamped to 1."""
        result = JudgeService._clamp_score(value, "test_field")
        assert result == 1

    # ------------------------------------------------------------------
    # Values above 5 are clamped to 5
    # ------------------------------------------------------------------

    @given(value=st.integers(min_value=6))
    @settings(max_examples=100)
    def test_above_range_clamped_to_five(self, value: int) -> None:
        """Values above 5 SHALL be clamped to 5."""
        result = JudgeService._clamp_score(value, "test_field")
        assert result == 5

    # ------------------------------------------------------------------
    # Clamping is idempotent
    # ------------------------------------------------------------------

    @given(value=st.integers(min_value=-1000, max_value=1000))
    @settings(max_examples=100)
    def test_clamping_is_idempotent(self, value: int) -> None:
        """Clamping a value twice SHALL produce the same result
        as clamping once."""
        first = JudgeService._clamp_score(value, "test_field")
        second = JudgeService._clamp_score(first, "test_field")
        assert first == second

    # ------------------------------------------------------------------
    # Non-numeric values raise JudgeParseError
    # ------------------------------------------------------------------

    @given(
        value=st.text(
            alphabet=st.characters(
                whitelist_categories=("L",),  # letters only
            ),
            min_size=1,
            max_size=20,
        ).filter(lambda s: not s.lstrip("-").isdigit())
    )
    @settings(max_examples=100)
    def test_non_numeric_raises_parse_error(
        self, value: str
    ) -> None:
        """Non-numeric values SHALL raise JudgeParseError."""
        with pytest.raises(JudgeParseError):
            JudgeService._clamp_score(value, "test_field")

    # ------------------------------------------------------------------
    # _clamp_dimension_scores applies clamping to all four dimensions
    # ------------------------------------------------------------------

    @given(
        fa=st.integers(min_value=-100, max_value=100),
        co=st.integers(min_value=-100, max_value=100),
        cr=st.integers(min_value=-100, max_value=100),
        ch=st.integers(min_value=-100, max_value=100),
    )
    @settings(max_examples=100)
    def test_clamp_dimension_scores_clamps_all_fields(
        self,
        fa: int,
        co: int,
        cr: int,
        ch: int,
    ) -> None:
        """_clamp_dimension_scores SHALL clamp every dimension
        to [1, 5]."""
        raw = {
            "factual_accuracy": fa,
            "completeness": co,
            "clinical_relevance": cr,
            "coherence": ch,
        }
        result = JudgeService._clamp_dimension_scores(
            raw, "test"
        )
        assert 1 <= result.factual_accuracy <= 5
        assert 1 <= result.completeness <= 5
        assert 1 <= result.clinical_relevance <= 5
        assert 1 <= result.coherence <= 5

        # Each field matches the clamping formula
        assert result.factual_accuracy == max(1, min(5, fa))
        assert result.completeness == max(1, min(5, co))
        assert result.clinical_relevance == max(1, min(5, cr))
        assert result.coherence == max(1, min(5, ch))


# ---------------------------------------------------------------------------
# Property tests — Winner mapping consistency (Property 5)
# ---------------------------------------------------------------------------


class TestWinnerMappingConsistency:
    """
    # Feature: llm-judge-evaluation, Property 5: Winner mapping consistency

    Validates: Requirements 3.2

    Property 5 states: For any combination of ``position_label`` ∈
    {"base_is_A", "base_is_B"} and verdict ``winner`` ∈ {"A", "B", "TIE"},
    the mapped winner SHALL be: "base" if the verdict winner matches the
    base model's position, "finetuned" if it matches the fine-tuned model's
    position, or "tie" if the verdict is "TIE".
    """

    # ------------------------------------------------------------------
    # Core property: exhaustive enumeration of all 6 combinations
    # ------------------------------------------------------------------

    @given(
        base_is_a=st.booleans(),
        verdict_winner=st.sampled_from(["A", "B", "TIE"]),
    )
    @settings(max_examples=100)
    def test_winner_mapping_matches_expected(
        self,
        base_is_a: bool,
        verdict_winner: str,
    ) -> None:
        """For any (base_is_a, verdict_winner) pair, _map_winner
        SHALL return the correct model identity."""
        result = JudgeService._map_winner(verdict_winner, base_is_a)

        if verdict_winner == "TIE":
            assert result == "tie"
        elif verdict_winner == "A":
            expected = "base" if base_is_a else "finetuned"
            assert result == expected
        elif verdict_winner == "B":
            expected = "finetuned" if base_is_a else "base"
            assert result == expected

    # ------------------------------------------------------------------
    # TIE always maps to "tie" regardless of position
    # ------------------------------------------------------------------

    @given(base_is_a=st.booleans())
    @settings(max_examples=100)
    def test_tie_always_maps_to_tie(self, base_is_a: bool) -> None:
        """A verdict of "TIE" SHALL always map to "tie"
        regardless of position assignment."""
        result = JudgeService._map_winner("TIE", base_is_a)
        assert result == "tie"

    # ------------------------------------------------------------------
    # Swapping position swaps the mapped winner (for A and B)
    # ------------------------------------------------------------------

    @given(verdict_winner=st.sampled_from(["A", "B"]))
    @settings(max_examples=100)
    def test_swapping_position_swaps_winner(
        self, verdict_winner: str
    ) -> None:
        """For a non-tie verdict, swapping base_is_a SHALL swap
        the mapped winner between "base" and "finetuned"."""
        result_a_true = JudgeService._map_winner(
            verdict_winner, base_is_a=True
        )
        result_a_false = JudgeService._map_winner(
            verdict_winner, base_is_a=False
        )

        # The two results should be different
        assert result_a_true != result_a_false
        # And together they should cover both model identities
        assert {result_a_true, result_a_false} == {
            "base",
            "finetuned",
        }

    # ------------------------------------------------------------------
    # Mapped winner is always one of the three valid values
    # ------------------------------------------------------------------

    @given(
        base_is_a=st.booleans(),
        verdict_winner=st.sampled_from(["A", "B", "TIE"]),
    )
    @settings(max_examples=100)
    def test_mapped_winner_is_valid_identity(
        self,
        base_is_a: bool,
        verdict_winner: str,
    ) -> None:
        """The mapped winner SHALL always be one of "base",
        "finetuned", or "tie"."""
        result = JudgeService._map_winner(verdict_winner, base_is_a)
        assert result in {"base", "finetuned", "tie"}

    # ------------------------------------------------------------------
    # Unrecognised verdict winners default to "tie"
    # ------------------------------------------------------------------

    @given(
        base_is_a=st.booleans(),
        verdict_winner=st.text(min_size=1, max_size=20).filter(
            lambda s: s.upper() not in ("A", "B", "TIE")
        ),
    )
    @settings(max_examples=100)
    def test_unrecognised_winner_defaults_to_tie(
        self,
        base_is_a: bool,
        verdict_winner: str,
    ) -> None:
        """Any verdict winner not in {"A", "B", "TIE"} SHALL
        be treated as a tie."""
        result = JudgeService._map_winner(verdict_winner, base_is_a)
        assert result == "tie"

    # ------------------------------------------------------------------
    # Symmetry: if A wins for base_is_A=True, then B wins for
    # base_is_A=False should give the same model identity
    # ------------------------------------------------------------------

    @given(data=st.data())
    @settings(max_examples=100)
    def test_symmetry_a_and_b_mirror(self, data: st.DataObject) -> None:
        """Selecting "A" with base_is_A=True SHALL produce the
        same model identity as selecting "B" with base_is_A=False,
        and vice versa."""
        # "A" when base is A → "base"
        # "B" when base is B (i.e. base_is_a=False) → "base"
        result_a_base_a = JudgeService._map_winner("A", base_is_a=True)
        result_b_base_b = JudgeService._map_winner("B", base_is_a=False)
        assert result_a_base_a == result_b_base_b == "base"

        # "B" when base is A → "finetuned"
        # "A" when base is B (i.e. base_is_a=False) → "finetuned"
        result_b_base_a = JudgeService._map_winner("B", base_is_a=True)
        result_a_base_b = JudgeService._map_winner("A", base_is_a=False)
        assert result_b_base_a == result_a_base_b == "finetuned"



# ---------------------------------------------------------------------------
# Property tests — Code fence JSON extraction (Property 11)
# ---------------------------------------------------------------------------


class TestCodeFenceJsonExtraction:
    """
    # Feature: llm-judge-evaluation, Property 11: Code fence JSON extraction

    Validates: Requirements 11.2

    Property 11 states: For any valid ``JudgeVerdict`` JSON string,
    wrapping it in markdown code fences (````` ```json ... ``` `````)
    or prepending/appending arbitrary non-JSON text SHALL still parse
    correctly via ``parse_judge_response``, producing a ``JudgeVerdict``
    equivalent to parsing the raw JSON directly.
    """

    # Strategy for valid dimension scores (1–5).
    _valid_score = st.integers(min_value=1, max_value=5)

    # Strategy for valid winner values.
    _valid_winner = st.sampled_from(["A", "B", "tie"])

    # Strategy for explanation text — printable strings that won't
    # break JSON serialisation.
    _explanation_text = st.text(
        alphabet=st.characters(
            whitelist_categories=("L", "N", "P", "Z"),
            blacklist_characters=(
                "\x00",
                "\\",
                '"',
            ),
        ),
        min_size=0,
        max_size=200,
    )

    # Strategy for arbitrary surrounding text that does NOT contain
    # a valid JSON object (to avoid confusing the extractor).
    _surrounding_text = st.text(
        alphabet=st.characters(
            whitelist_categories=("L", "N", "Z"),
            blacklist_characters=("\x00", "{", "}"),
        ),
        min_size=0,
        max_size=100,
    )

    def _build_verdict_json(
        self,
        fa_a: int,
        co_a: int,
        cr_a: int,
        ch_a: int,
        fa_b: int,
        co_b: int,
        cr_b: int,
        ch_b: int,
        winner: str,
        explanation: str,
    ) -> str:
        """Build a valid JudgeVerdict JSON string from components."""
        import json

        obj = {
            "response_a_scores": {
                "factual_accuracy": fa_a,
                "completeness": co_a,
                "clinical_relevance": cr_a,
                "coherence": ch_a,
            },
            "response_b_scores": {
                "factual_accuracy": fa_b,
                "completeness": co_b,
                "clinical_relevance": cr_b,
                "coherence": ch_b,
            },
            "winner": winner,
            "explanation": explanation,
        }
        return json.dumps(obj)

    def _assert_verdicts_equivalent(
        self, v1: JudgeVerdict, v2: JudgeVerdict
    ) -> None:
        """Assert two JudgeVerdict objects are semantically equal."""
        assert v1.response_a_scores == v2.response_a_scores
        assert v1.response_b_scores == v2.response_b_scores
        assert v1.winner == v2.winner
        assert v1.explanation == v2.explanation

    # ------------------------------------------------------------------
    # Core property: ```json ... ``` fenced JSON parses equivalently
    # ------------------------------------------------------------------

    @given(
        fa_a=_valid_score,
        co_a=_valid_score,
        cr_a=_valid_score,
        ch_a=_valid_score,
        fa_b=_valid_score,
        co_b=_valid_score,
        cr_b=_valid_score,
        ch_b=_valid_score,
        winner=_valid_winner,
        explanation=_explanation_text,
    )
    @settings(max_examples=100)
    def test_json_code_fence_parses_equivalently(
        self,
        fa_a: int,
        co_a: int,
        cr_a: int,
        ch_a: int,
        fa_b: int,
        co_b: int,
        cr_b: int,
        ch_b: int,
        winner: str,
        explanation: str,
    ) -> None:
        """Wrapping valid JSON in ```json ... ``` fences SHALL
        parse to an equivalent JudgeVerdict as the raw JSON."""
        service = _make_judge_service()
        raw_json = self._build_verdict_json(
            fa_a, co_a, cr_a, ch_a,
            fa_b, co_b, cr_b, ch_b,
            winner, explanation,
        )

        fenced = f"```json\n{raw_json}\n```"

        verdict_raw = service.parse_judge_response(raw_json)
        verdict_fenced = service.parse_judge_response(fenced)

        self._assert_verdicts_equivalent(verdict_raw, verdict_fenced)

    # ------------------------------------------------------------------
    # ``` ... ``` fences without the json language tag
    # ------------------------------------------------------------------

    @given(
        fa_a=_valid_score,
        co_a=_valid_score,
        cr_a=_valid_score,
        ch_a=_valid_score,
        fa_b=_valid_score,
        co_b=_valid_score,
        cr_b=_valid_score,
        ch_b=_valid_score,
        winner=_valid_winner,
        explanation=_explanation_text,
    )
    @settings(max_examples=100)
    def test_plain_code_fence_parses_equivalently(
        self,
        fa_a: int,
        co_a: int,
        cr_a: int,
        ch_a: int,
        fa_b: int,
        co_b: int,
        cr_b: int,
        ch_b: int,
        winner: str,
        explanation: str,
    ) -> None:
        """Wrapping valid JSON in ``` ... ``` fences (no language
        tag) SHALL parse to an equivalent JudgeVerdict."""
        service = _make_judge_service()
        raw_json = self._build_verdict_json(
            fa_a, co_a, cr_a, ch_a,
            fa_b, co_b, cr_b, ch_b,
            winner, explanation,
        )

        fenced = f"```\n{raw_json}\n```"

        verdict_raw = service.parse_judge_response(raw_json)
        verdict_fenced = service.parse_judge_response(fenced)

        self._assert_verdicts_equivalent(verdict_raw, verdict_fenced)

    # ------------------------------------------------------------------
    # JSON with arbitrary text prepended and appended
    # ------------------------------------------------------------------

    @given(
        fa_a=_valid_score,
        co_a=_valid_score,
        cr_a=_valid_score,
        ch_a=_valid_score,
        fa_b=_valid_score,
        co_b=_valid_score,
        cr_b=_valid_score,
        ch_b=_valid_score,
        winner=_valid_winner,
        explanation=_explanation_text,
        prefix=_surrounding_text,
        suffix=_surrounding_text,
    )
    @settings(max_examples=100)
    def test_surrounding_text_parses_equivalently(
        self,
        fa_a: int,
        co_a: int,
        cr_a: int,
        ch_a: int,
        fa_b: int,
        co_b: int,
        cr_b: int,
        ch_b: int,
        winner: str,
        explanation: str,
        prefix: str,
        suffix: str,
    ) -> None:
        """Prepending and appending arbitrary non-JSON text to
        valid JSON SHALL still parse to an equivalent JudgeVerdict."""
        service = _make_judge_service()
        raw_json = self._build_verdict_json(
            fa_a, co_a, cr_a, ch_a,
            fa_b, co_b, cr_b, ch_b,
            winner, explanation,
        )

        wrapped = f"{prefix}\n{raw_json}\n{suffix}"

        verdict_raw = service.parse_judge_response(raw_json)
        verdict_wrapped = service.parse_judge_response(wrapped)

        self._assert_verdicts_equivalent(verdict_raw, verdict_wrapped)

    # ------------------------------------------------------------------
    # JSON in code fences with surrounding text
    # ------------------------------------------------------------------

    @given(
        fa_a=_valid_score,
        co_a=_valid_score,
        cr_a=_valid_score,
        ch_a=_valid_score,
        fa_b=_valid_score,
        co_b=_valid_score,
        cr_b=_valid_score,
        ch_b=_valid_score,
        winner=_valid_winner,
        explanation=_explanation_text,
        prefix=_surrounding_text,
        suffix=_surrounding_text,
    )
    @settings(max_examples=100)
    def test_fenced_json_with_surrounding_text(
        self,
        fa_a: int,
        co_a: int,
        cr_a: int,
        ch_a: int,
        fa_b: int,
        co_b: int,
        cr_b: int,
        ch_b: int,
        winner: str,
        explanation: str,
        prefix: str,
        suffix: str,
    ) -> None:
        """JSON in ```json ... ``` fences with arbitrary text
        before and after the fences SHALL parse equivalently."""
        service = _make_judge_service()
        raw_json = self._build_verdict_json(
            fa_a, co_a, cr_a, ch_a,
            fa_b, co_b, cr_b, ch_b,
            winner, explanation,
        )

        wrapped = (
            f"{prefix}\n"
            f"```json\n{raw_json}\n```\n"
            f"{suffix}"
        )

        verdict_raw = service.parse_judge_response(raw_json)
        verdict_wrapped = service.parse_judge_response(wrapped)

        self._assert_verdicts_equivalent(verdict_raw, verdict_wrapped)

    # ------------------------------------------------------------------
    # Typical LLM preamble pattern
    # ------------------------------------------------------------------

    @given(
        fa_a=_valid_score,
        co_a=_valid_score,
        cr_a=_valid_score,
        ch_a=_valid_score,
        fa_b=_valid_score,
        co_b=_valid_score,
        cr_b=_valid_score,
        ch_b=_valid_score,
        winner=_valid_winner,
        explanation=_explanation_text,
    )
    @settings(max_examples=100)
    def test_llm_preamble_pattern(
        self,
        fa_a: int,
        co_a: int,
        cr_a: int,
        ch_a: int,
        fa_b: int,
        co_b: int,
        cr_b: int,
        ch_b: int,
        winner: str,
        explanation: str,
    ) -> None:
        """A typical LLM response with a preamble like
        'Here is my evaluation:' followed by fenced JSON SHALL
        parse equivalently to the raw JSON."""
        service = _make_judge_service()
        raw_json = self._build_verdict_json(
            fa_a, co_a, cr_a, ch_a,
            fa_b, co_b, cr_b, ch_b,
            winner, explanation,
        )

        llm_response = (
            "Here is my evaluation of the two responses:\n\n"
            f"```json\n{raw_json}\n```\n\n"
            "I hope this helps with your assessment."
        )

        verdict_raw = service.parse_judge_response(raw_json)
        verdict_llm = service.parse_judge_response(llm_response)

        self._assert_verdicts_equivalent(verdict_raw, verdict_llm)
